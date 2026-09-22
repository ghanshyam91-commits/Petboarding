"""Provider lifecycle transitions with participant checks and auditable custody."""
from copy import copy
from datetime import time, timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from care.models import (Booking, Provider, StaffMembership, CapacityDay, CareTask,
                         CareEvent, CustodyEvent, AuditEntry)
from .stays import can_operate, eligibility, acknowledge_handover


def visible_bookings(user):
    operated = Provider.objects.filter(Q(owner=user) | Q(
        staffmembership__user=user, staffmembership__role__in=['manager', 'caregiver']))
    return Booking.objects.filter(Q(owner=user) | Q(provider__in=operated)).distinct()


def _locked_booking(booking_id):
    # Keep lock order consistent with reservation/cancellation writers.
    provider_id = Booking.objects.values_list('provider_id', flat=True).get(pk=booking_id)
    Provider.objects.select_for_update().get(pk=provider_id)
    return Booking.objects.select_for_update().select_related('provider').get(pk=booking_id)


def _validate_reserved_stay(booking):
    pets = list(booking.pets.all())
    if not pets:
        raise ValidationError('Add a pet before confirming this stay.')
    if booking.ends <= timezone.localdate():
        raise ValidationError('This stay has already passed its checkout date.')
    if any(p.owner_id != booking.owner_id for p in pets):
        raise ValidationError('The pet owner no longer matches this reservation.')
    # Capacity already includes this booking: remove its contribution from the
    # additional-space comparison without mutating any persisted capacity.
    provider = copy(booking.provider)
    original_capacity = provider.capacity
    provider.capacity += len(pets)
    errors = eligibility(provider, pets, max(booking.starts, timezone.localdate()), booking.ends)
    if len(pets) > original_capacity:
        errors.append('This stay exceeds the provider capacity.')
    if errors:
        raise ValidationError(errors)
    for pet in pets:
        routine = booking.care_snapshot.get(str(pet.pk), {}).get('routine', [])
        if not isinstance(routine, list):
            raise ValidationError('The saved care routine needs correction before check-in.')
        for item in routine:
            try:
                parsed = time.fromisoformat(item['time'])
                valid = isinstance(item['kind'], str) and 0 < len(item['kind'].strip()) <= 50
                if parsed.tzinfo is not None or not valid:
                    raise ValueError
            except (TypeError, KeyError, ValueError):
                raise ValidationError('The saved care routine needs valid task names and local times.')


def _audit(user, booking, action):
    AuditEntry.objects.create(actor=user, action=action, object_type='booking', object_id=booking.pk)


@transaction.atomic
def confirm_booking(user, booking_id):
    booking = _locked_booking(booking_id)
    if not can_operate(user, booking.provider):
        raise PermissionDenied
    if booking.status == 'confirmed':
        return booking
    if booking.status != 'reserved':
        raise ValidationError('Only a pending reservation can be confirmed.')
    _validate_reserved_stay(booking)
    booking.status = 'confirmed'
    booking.save(update_fields=['status'])
    CareEvent.objects.create(booking=booking, actor=user, kind='Stay confirmed',
                             notes='The provider accepted this unpaid reservation.')
    _audit(user, booking, 'stay_confirmed')
    return booking


@transaction.atomic
def checkin_booking(user, booking_id, condition='', belongings='', food_and_medicines='', emergency_verified=False):
    booking = _locked_booking(booking_id)
    if user != booking.owner and not can_operate(user, booking.provider):
        raise PermissionDenied
    if booking.status not in ('confirmed', 'active'):
        raise ValidationError('Confirm the reservation before check-in.')
    if booking.status == 'confirmed':
        if not booking.starts <= timezone.localdate() < booking.ends:
            raise ValidationError('Check-in is available only during the booked stay dates.')
        _validate_reserved_stay(booking)
    return acknowledge_handover(user, booking_id, condition, belongings,
                                food_and_medicines, emergency_verified)


@transaction.atomic
def checkout_booking(user, booking_id, condition='', belongings=''):
    booking = _locked_booking(booking_id)
    provider_side = can_operate(user, booking.provider) and user != booking.owner
    if user != booking.owner and not provider_side:
        raise PermissionDenied
    kind = 'checkout_provider_ack' if provider_side else 'checkout_owner_ack'
    existing = booking.custody_events.filter(kind=kind).first()
    if booking.status == 'completed' and existing:
        return booking
    if booking.status != 'active':
        raise ValidationError('Only an active stay can check out.')
    if existing:
        return booking
    if booking.tasks.filter(critical=True, completed_at=None, due_at__lte=timezone.now()).exists():
        raise ValidationError('Resolve due critical care tasks before checkout.')
    provider_ack = booking.custody_events.filter(kind='checkout_provider_ack').first()
    if provider_side:
        if not condition.strip() or not belongings.strip():
            raise ValidationError('Record the pet condition and returned belongings before checkout.')
        details = {'condition': condition.strip()[:4000], 'belongings': belongings.strip()[:4000]}
    else:
        if not provider_ack:
            raise ValidationError('The provider must record checkout condition and belongings first.')
        details = provider_ack.details
    CustodyEvent.objects.create(booking=booking, actor=user, kind=kind, details=details)
    _audit(user, booking, kind)
    if booking.custody_events.filter(kind='checkout_provider_ack').exists() and booking.custody_events.filter(kind='checkout_owner_ack').exists():
        count = booking.pets.count()
        day = booking.starts
        while day < booking.ends:
            slot = CapacityDay.objects.select_for_update().filter(provider=booking.provider, day=day).first()
            if not slot or slot.reserved < count:
                raise ValidationError('Capacity records need review before checkout can finish.')
            slot.reserved -= count
            slot.save(update_fields=['reserved'])
            day += timedelta(days=1)
        booking.status = 'completed'
        booking.save(update_fields=['status'])
        CareEvent.objects.create(booking=booking, actor=user, kind='Check-out complete',
                                 notes='Both parties acknowledged pet condition and returned belongings.')
        _audit(user, booking, 'stay_completed')
    return booking


def _active_operator(user, booking_id):
    booking = _locked_booking(booking_id)
    if not can_operate(user, booking.provider):
        raise PermissionDenied
    if booking.status != 'active':
        raise ValidationError('Care can only be recorded for an active stay.')
    return booking


def _pet(booking, pet_id):
    pet = booking.pets.filter(pk=pet_id).first()
    if not pet:
        raise ValidationError('Choose a pet belonging to this stay.')
    return pet


@transaction.atomic
def record_care_event(user, booking_id, pet_id, kind, notes):
    booking = _active_operator(user, booking_id)
    pet = _pet(booking, pet_id)
    if not kind.strip() or len(kind) > 80 or not notes.strip() or len(notes) > 4000:
        raise ValidationError('Add an update type and a care note (up to 4,000 characters).')
    event = CareEvent.objects.create(booking=booking, pet=pet, actor=user, kind=kind.strip(), notes=notes.strip())
    _audit(user, booking, 'care_update_recorded')
    return event


@transaction.atomic
def create_care_task(user, booking_id, pet_id, kind, due_at, critical=False):
    booking = _active_operator(user, booking_id)
    pet = _pet(booking, pet_id)
    if not kind.strip() or len(kind) > 50:
        raise ValidationError('Add a task name of up to 50 characters.')
    if timezone.is_naive(due_at):
        due_at = timezone.make_aware(due_at)
    day = timezone.localtime(due_at).date()
    if due_at < timezone.now() or not booking.starts <= day < booking.ends:
        raise ValidationError('Schedule the task in the future and before the checkout date.')
    task = CareTask.objects.create(booking=booking, pet=pet, kind=kind.strip(), due_at=due_at, critical=critical)
    _audit(user, booking, 'care_task_scheduled')
    return task
