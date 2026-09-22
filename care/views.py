from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.utils import timezone
from .models import *
from .forms import PetForm, SearchForm
from .demo import DEMO_CITY
from .context import workspace
from .services.provider_flow import visible_bookings
from .passport_flows import health_review_queue
from .services.stays import (
    eligibility,
    reserve,
    complete_task,
    report_incident,
    can_view,
    can_operate,
    cancel,
)


@login_required
def home(request):
    if workspace(request)["is_provider"]:
        return redirect("operations")
    bookings = (
        Booking.objects.filter(owner=request.user)
        .select_related("provider")
        .order_by("-created_at")
    )
    active = bookings.filter(status="active").first()
    return render(
        request,
        "care/home.html",
        {
            "active": active,
            "bookings": bookings[:3],
            "pets": Pet.objects.filter(owner=request.user),
            "events": active.events.order_by("-created_at")[:8] if active else [],
            "nav": "Home",
        },
    )


@login_required
def explore(request):
    form = SearchForm(
        request.GET or None,
        user=request.user,
        initial={
            "city": "Bengaluru",
            "starts": timezone.localdate(),
            "ends": timezone.localdate() + timedelta(days=2),
        },
    )
    results = []
    excluded = 0
    if form.is_bound and form.is_valid():
        d = form.cleaned_data
        for provider in Provider.objects.filter(
            jurisdiction__city=d["city"]
        ).select_related("jurisdiction"):
            errors = eligibility(provider, list(d["pets"]), d["starts"], d["ends"])
            if errors:
                excluded += 1
            else:
                results.append(provider)
        results.sort(key=lambda p: (not p.overnight_supervision, p.nightly_paise))
    return render(
        request,
        "care/explore.html",
        {
            "form": form,
            "providers": results,
            "demo_providers": Provider.objects.filter(jurisdiction__city=DEMO_CITY)
                .select_related("jurisdiction") if getattr(request, "is_demo", False) and not request.GET else [],
            "excluded": excluded,
            "searched": form.is_bound and form.is_valid(),
            "nav": "Explore",
        },
    )


@login_required
@require_POST
def book(request, pk):
    get_object_or_404(Provider, pk=pk)
    form = SearchForm(request.POST, user=request.user)
    if not form.is_valid():
        messages.error(request, "Please select valid dates and pets.")
        return redirect(reverse("explore") + "?" + _search_query(request.POST))
    d = form.cleaned_data
    try:
        booking = reserve(
            request.user, pk, [p.pk for p in d["pets"]], d["starts"], d["ends"]
        )
        return redirect("stay", pk=booking.pk)
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
        return redirect(reverse("explore") + "?" + _search_query(request.POST))


@login_required
def stay(request, pk):
    booking = get_object_or_404(Booking.objects.select_related("provider"), pk=pk)
    if not can_view(request.user, booking):
        raise PermissionDenied
    return render(
        request,
        "care/stay.html",
        {
            "booking": booking,
            "can_operate": can_operate(request.user, booking.provider),
            "is_owner": request.user == booking.owner,
            "handover": Handover.objects.filter(booking=booking).first(),
            "checkout_record": booking.custody_events.filter(kind="checkout_provider_ack").first(),
            "stay_review": Review.objects.filter(booking=booking).first(),
            "checkin_available": booking.starts <= timezone.localdate() < booking.ends,
            "review_categories": [(x, x.replace("_", " ").title()) for x in ["cleanliness", "communication", "care_quality", "update_reliability", "description_accuracy", "handling", "overall"]],
            "care_pets": [{"pet": pet, "care": booking.care_snapshot.get(str(pet.pk), {}), "emergency": booking.emergency_consent.get(str(pet.pk), {})} for pet in booking.pets.all()],
            "events": booking.events.select_related("actor", "pet").order_by(
                "-created_at"
            ),
            "nav": "Bookings",
        },
    )


@login_required
def bookings(request):
    qs = visible_bookings(request.user).select_related("provider", "owner").order_by("-created_at")
    status = request.GET.get("status", "")
    if status in dict(Booking._meta.get_field("status").choices):
        qs = qs.filter(status=status)
    else:
        status = ""
    return render(request, "care/bookings.html", {"bookings": qs, "status": status, "nav": "Bookings"})


@login_required
def profile(request):
    form = PetForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        pet = form.save(commit=False)
        pet.owner = request.user
        pet.save()
        messages.success(
            request,
            "Pet passport created. Health verification is required before booking.",
        )
        return redirect("profile")
    return render(
        request,
        "care/profile.html",
        {
            "form": form,
            "pets": Pet.objects.filter(owner=request.user).prefetch_related("records"),
            "nav": "Profile",
        },
    )


@login_required
def operations(request):
    providers = Provider.objects.filter(owner=request.user) | Provider.objects.filter(
        staffmembership__user=request.user,
        staffmembership__role__in=["manager", "caregiver"],
    )
    if not providers.exists():
        raise PermissionDenied
    stays = Booking.objects.filter(provider__in=providers, status="active").select_related("provider", "owner")
    tasks = (
        CareTask.objects.filter(booking__in=stays, due_at__date__lte=timezone.localdate())
        .select_related("pet", "booking__provider")
        .order_by("completed_at", "due_at")
    )
    return render(
        request,
        "care/operations.html",
        {
            "stays": stays,
            "providers": providers.distinct(),
            "upcoming": Booking.objects.filter(provider__in=providers, status__in=["reserved", "confirmed"]).select_related("provider", "owner").order_by("starts"),
            "pending_count": tasks.filter(completed_at=None).count(),
            "now": timezone.now(),
            "tasks": tasks,
            "overdue": tasks.filter(
                completed_at=None, due_at__lt=timezone.now()
            ).count(),
            "nav": "Operations",
        },
    )


@login_required
@require_POST
def task_complete(request, pk):
    get_object_or_404(CareTask, pk=pk)
    try:
        complete_task(request.user, pk)
        messages.success(request, "Care recorded in the stay timeline.")
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    return redirect("operations")


@login_required
@require_POST
def emergency(request, pk):
    get_object_or_404(Booking, pk=pk)
    try:
        incident = report_incident(
            request.user, pk, "emergency", request.POST.get("description", "")[:4000]
        )
        messages.success(
            request,
            f"Incident #{incident.pk} recorded. Contact the emergency veterinarian directly; automated delivery is not configured.",
        )
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    return redirect("stay", pk=pk)


@login_required
@require_POST
def cancellation(request, pk):
    get_object_or_404(Booking, pk=pk)
    try:
        cancel(request.user, pk)
        messages.success(
            request,
            "Unpaid reservation cancelled. No payment was collected; refund ₹0.",
        )
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    return redirect("stay", pk=pk)


@login_required
def trust(request):
    if not request.user.is_staff:
        raise PermissionDenied
    return render(
        request,
        "care/trust.html",
        {
            "health_queue": health_review_queue(),
            "disputes": Dispute.objects.filter(status="open").select_related("booking__provider"),
            "incidents": Incident.objects.filter(status="open").select_related(
                "booking__provider"
            ),
            "overdue": CareTask.objects.filter(
                booking__status="active", critical=True, completed_at=None, due_at__lt=timezone.now()
            ).count(),
            "providers": Provider.objects.all(),
            "active_count": Booking.objects.filter(status="active").count(),
            "nav": "Trust",
        },
    )


@login_required
@require_POST
def suspend(request, pk):
    if not request.user.is_staff:
        raise PermissionDenied
    from django.db import transaction

    with transaction.atomic():
        p = get_object_or_404(Provider.objects.select_for_update(), pk=pk)
        p.suspended = True
        p.save()
        AuditEntry.objects.create(
            actor=request.user,
            action="provider_suspended",
            object_type="provider",
            object_id=p.pk,
        )
    messages.success(request, "Provider suspended. New reservations are blocked.")
    return redirect("trust")


@login_required
def inbox(request):
    qs = visible_bookings(request.user).select_related("provider", "owner").prefetch_related("messages").order_by("-created_at")
    return render(request, "care/inbox.html", {"bookings": qs, "nav": "Messages"})


@login_required
@require_POST
def send_message(request, pk):
    b = get_object_or_404(Booking, pk=pk)
    if not can_view(request.user, b):
        raise PermissionDenied
    text = request.POST.get("text", "").strip()
    if text and len(text) <= 2000:
        Message.objects.create(booking=b, sender=request.user, text=text)
        messages.success(request, "Message sent.")
    else:
        messages.error(request, "Enter a message of 1–2,000 characters.")
    return redirect("stay", pk=pk)


@login_required
@require_POST
def handover(request, pk):
    from .services.stays import acknowledge_handover

    try:
        acknowledge_handover(
            request.user,
            pk,
            request.POST.get("condition", "")[:4000],
            request.POST.get("belongings", "")[:4000],
            request.POST.get("food", "")[:4000],
            request.POST.get("emergency_verified") == "on",
        )
        messages.success(request, "Handover acknowledgement recorded.")
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    return redirect("stay", pk=pk)


@login_required
@require_POST
def review(request, pk):
    from django.db import transaction

    b = get_object_or_404(Booking, pk=pk, owner=request.user, status="completed")
    categories = [
        "cleanliness",
        "communication",
        "care_quality",
        "update_reliability",
        "description_accuracy",
        "handling",
        "overall",
    ]
    try:
        ratings = {c: int(request.POST.get(c, 0)) for c in categories}
        if any(v < 1 or v > 5 for v in ratings.values()):
            raise ValueError
    except ValueError:
        messages.error(request, "Each review category must be rated 1–5.")
        return redirect("stay", pk=pk)
    with transaction.atomic():
        b = Booking.objects.select_for_update().get(pk=b.pk)
        if not Review.objects.filter(booking=b).exists():
            Review.objects.create(
                booking=b,
                ratings=ratings,
                text=request.POST.get("text", "")[:4000],
                matched_listing=request.POST.get("matched_listing") == "on",
            )
            AuditEntry.objects.create(
                actor=request.user,
                action="verified_stay_review_created",
                object_type="booking",
                object_id=b.pk,
            )
    messages.success(request, "Verified stay review saved.")
    return redirect("stay", pk=pk)


@login_required
@require_POST
def dispute(request, pk):
    b = get_object_or_404(Booking, pk=pk)
    if not can_view(request.user, b):
        raise PermissionDenied
    reason = request.POST.get("reason", "").strip()[:4000]
    if reason:
        from django.db import transaction

        with transaction.atomic():
            case = Dispute.objects.create(
                booking=b, opened_by=request.user, reason=reason
            )
            AuditEntry.objects.create(
                actor=request.user,
                action="dispute_opened_evidence_hold",
                object_type="dispute",
                object_id=case.pk,
            )
        messages.success(request, f"Dispute #{case.pk} opened with evidence hold.")
    else:
        messages.error(request, "Describe the issue before opening a case.")
    return redirect("stay", pk=pk)


@login_required
@require_POST
def privacy_request(request):
    kind = request.POST.get("kind")
    if kind in ["export", "delete"]:
        PrivacyRequest.objects.get_or_create(
            user=request.user, kind=kind, status="pending"
        )
        messages.success(
            request,
            "Privacy request recorded for review. Evidence retention obligations will be assessed before deletion.",
        )
    return redirect("profile")


def _search_query(data):
    from django.http import QueryDict
    query = QueryDict(mutable=True)
    for key in ("city", "starts", "ends", "pets"):
        query.setlist(key, data.getlist(key))
    return query.urlencode()
