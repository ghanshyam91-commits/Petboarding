from datetime import timedelta, datetime, time
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from care.models import *

ACTIVE = ["reserved", "confirmed", "active"]


def eligibility(provider, pets, starts, ends):
    failures = []
    if starts < timezone.localdate() or ends <= starts:
        failures.append("Choose valid future stay dates.")
    if provider.suspended:
        failures.append("Provider is suspended.")
    rule = (
        ComplianceRule.objects.filter(
            jurisdiction=provider.jurisdiction, effective_at__lte=timezone.now()
        )
        .order_by("-version")
        .first()
    )
    if not rule or not rule.reviewed:
        return failures + ["Local compliance requirements have not been reviewed."]
    if provider.kind == "home" and not rule.home_boarding_allowed:
        failures.append("Home boarding is not permitted by the current local rule.")
    for category in rule.required_credentials:
        if not provider.credentials.filter(
            category=category,
            status="verified",
            expires__gte=ends,
            verified_by__isnull=False,
            verified_at__isnull=False,
        ).exists():
            failures.append(
                f"{category.title()} verification must remain valid through checkout."
            )
    for pet in pets:
        if pet.species not in provider.species:
            failures.append(f"{pet.name}: species is not supported.")
        if "cat" in provider.resident_species and not pet.compatible_cats:
            failures.append(f"{pet.name}: incompatible with resident cats.")
        if "dog" in provider.resident_species and not pet.compatible_dogs:
            failures.append(f"{pet.name}: incompatible with resident dogs.")
        if pet.medication_required and not provider.medication_competent:
            failures.append(f"{pet.name}: medication competency unavailable.")
        if pet.aggression_history and not provider.accepts_aggression:
            failures.append(f"{pet.name}: handling needs are unsupported.")
        for vaccine in rule.required_vaccines:
            if not pet.records.filter(
                kind=vaccine,
                status="verified",
                expires__gte=ends,
                verified_by__isnull=False,
                verified_at__isnull=False,
            ).exists():
                failures.append(
                    f"{pet.name}: verified {vaccine} must remain valid through checkout."
                )
    day = starts
    while day < ends:
        slot = CapacityDay.objects.filter(provider=provider, day=day).first()
        if (
            slot and (slot.blocked or slot.reserved + len(pets) > provider.capacity)
        ) or len(pets) > provider.capacity:
            failures.append("No safe capacity for all pets on the selected dates.")
            break
        day += timedelta(days=1)
    return failures


def quote(provider, pets, starts, ends):
    nights = (ends - starts).days
    if nights <= 0 or not pets:
        raise ValidationError("Choose pets and a valid date range.")
    base = provider.nightly_paise * nights
    additional = base * (len(pets) - 1)
    return {
        "nights": nights,
        "pets": len(pets),
        "base_paise": base,
        "additional_paise": additional,
        "fees_paise": 0,
        "total_paise": base + additional,
        "currency": "INR",
        "payment_enabled": False,
    }


@transaction.atomic
def reserve(owner, provider_id, pet_ids, starts, ends):
    provider = Provider.objects.select_for_update().get(pk=provider_id)
    from care.demo import is_demo_user
    if is_demo_user(owner) != is_demo_user(provider.owner):
        raise PermissionDenied("Demo stays must remain separate from real bookings.")
    ids = set(pet_ids)
    pets = list(Pet.objects.select_for_update().filter(pk__in=ids, owner=owner))
    if not pets or len(pets) != len(ids):
        raise PermissionDenied("Select only your own pets.")
    if (ends - starts).days > 60:
        raise ValidationError("Stays are limited to 60 nights.")
    errors = eligibility(provider, pets, starts, ends)
    if errors:
        raise ValidationError(errors)
    booking = Booking.objects.create(
        owner=owner,
        provider=provider,
        starts=starts,
        ends=ends,
        quote=quote(provider, pets, starts, ends),
        care_snapshot={
            str(p.pk): {"routine": p.routine, "health": p.health} for p in pets
        },
        emergency_consent={str(p.pk): p.emergency for p in pets},
    )
    booking.pets.set(pets)
    day = starts
    while day < ends:
        slot, _ = CapacityDay.objects.get_or_create(provider=provider, day=day)
        slot.reserved += len(pets)
        slot.save()
        day += timedelta(days=1)
    AuditEntry.objects.create(
        actor=owner,
        action="capacity_reserved",
        object_type="booking",
        object_id=booking.pk,
    )
    return booking


def can_operate(user, provider):
    return (
        user == provider.owner
        or StaffMembership.objects.filter(
            provider=provider, user=user, role__in=["manager", "caregiver"]
        ).exists()
    )


def can_view(user, booking):
    return user == booking.owner or can_operate(user, booking.provider) or user.is_staff


@transaction.atomic
def complete_task(user, task_id):
    task = (
        CareTask.objects.select_for_update()
        .select_related("booking__provider")
        .get(pk=task_id)
    )
    if not can_operate(user, task.booking.provider):
        raise PermissionDenied
    if task.booking.status != "active":
        raise ValidationError("Care can only be recorded for an active stay.")
    if task.completed_at:
        return task
    task.completed_at = timezone.now()
    task.completed_by = user
    task.save()
    CareEvent.objects.create(
        booking=task.booking,
        pet=task.pet,
        actor=user,
        kind=task.kind,
        notes="Care task completed"
        + (" after its scheduled time." if task.completed_at > task.due_at else "."),
    )
    AuditEntry.objects.create(
        actor=user, action="task_completed", object_type="caretask", object_id=task.pk
    )
    return task


@transaction.atomic
def report_incident(user, booking_id, category, description):
    booking = (
        Booking.objects.select_for_update()
        .select_related("provider")
        .get(pk=booking_id)
    )
    if not can_view(user, booking):
        raise PermissionDenied
    if not description.strip():
        raise ValidationError("Describe the observation.")
    incident = Incident.objects.create(
        booking=booking, reporter=user, category=category, description=description
    )
    CareEvent.objects.create(
        booking=booking, actor=user, kind="Emergency reported", notes=description
    )
    AuditEntry.objects.create(
        actor=user,
        action="incident_opened_evidence_hold",
        object_type="incident",
        object_id=incident.pk,
    )
    for recipient in {booking.owner, booking.provider.owner}:
        Notification.objects.create(
            user=recipient,
            booking=booking,
            message=f"Emergency #{incident.pk}: {description}",
            critical=True,
        )
    return incident


@transaction.atomic
def cancel(user, booking_id):
    # Lock provider before booking, the same order used by reservation writers.
    lookup = Booking.objects.get(pk=booking_id)
    provider = Provider.objects.select_for_update().get(pk=lookup.provider_id)
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    if user != booking.owner and user != provider.owner:
        raise PermissionDenied
    if booking.status == "cancelled":
        return booking
    if booking.status != "reserved":
        raise ValidationError(
            "Only unpaid reservations support self-service cancellation."
        )
    day = booking.starts
    while day < booking.ends:
        slot = CapacityDay.objects.get(provider=provider, day=day)
        slot.reserved -= booking.pets.count()
        slot.save()
        day += timedelta(days=1)
    booking.status = "cancelled"
    booking.save()
    AuditEntry.objects.create(
        actor=user,
        action="reservation_cancelled",
        object_type="booking",
        object_id=booking.pk,
        detail={"refund_paise": 0, "reason": "No payment collected"},
    )
    return booking


@transaction.atomic
def acknowledge_handover(
    user,
    booking_id,
    condition="",
    belongings="",
    food_and_medicines="",
    emergency_verified=False,
):
    booking = (
        Booking.objects.select_for_update()
        .select_related("provider")
        .get(pk=booking_id)
    )
    if user != booking.owner and not can_operate(user, booking.provider):
        raise PermissionDenied
    if booking.status not in ["confirmed", "active"]:
        raise ValidationError("Only confirmed stays can check in.")
    h = Handover.objects.filter(booking=booking).first()
    if not h:
        if not can_operate(user, booking.provider):
            raise ValidationError("The provider must record the handover first.")
        if not condition.strip() or not emergency_verified:
            raise ValidationError("Record pet condition and verify emergency contacts.")
        h = Handover.objects.create(
            booking=booking,
            condition=condition,
            belongings=belongings,
            food_and_medicines=food_and_medicines,
            emergency_verified=True,
        )
    if user == booking.owner:
        if h.owner_ack_at:
            return h
        h.owner_ack_at = timezone.now()
    else:
        if h.provider_ack_at:
            return h
        h.provider_ack_at = timezone.now()
    h.save()
    CustodyEvent.objects.create(
        booking=booking,
        actor=user,
        kind="checkin_acknowledged",
        details={
            "condition": h.condition,
            "belongings": h.belongings,
            "food_and_medicines": h.food_and_medicines,
        },
    )
    if h.owner_ack_at and h.provider_ack_at and booking.status != "active":
        booking.status = "active"
        booking.save()
        for pet in booking.pets.all():
            routine = booking.care_snapshot.get(str(pet.pk), {}).get("routine", [])
            day = booking.starts
            while day < booking.ends:
                for item in routine:
                    due = timezone.make_aware(
                        datetime.combine(day, time.fromisoformat(item["time"]))
                    )
                    CareTask.objects.create(
                        booking=booking,
                        pet=pet,
                        kind=item["kind"],
                        due_at=due,
                        critical=item.get("critical", False),
                    )
                day += timedelta(days=1)
        CareEvent.objects.create(
            booking=booking,
            actor=user,
            kind="Check-in complete",
            notes="Both parties acknowledged handover.",
        )
    return h


@transaction.atomic
def escalate_overdue():
    count = 0
    for task in (
        CareTask.objects.select_for_update()
        .filter(
            critical=True,
            completed_at=None,
            escalated_at=None,
            due_at__lt=timezone.now(),
        )
        .select_related("booking__provider", "pet")
    ):
        task.escalated_at = timezone.now()
        task.save()
        report_incident(
            task.booking.provider.owner,
            task.booking_id,
            "missed_medication",
            f"Critical care overdue: {task.kind} for {task.pet.name}.",
        )
        count += 1
    return count
