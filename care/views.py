from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import *
from .forms import PetForm, SearchForm
from .services.stays import (
    eligibility,
    reserve,
    complete_task,
    report_incident,
    can_view,
    cancel,
)


@login_required
def home(request):
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
            "excluded": excluded,
            "searched": form.is_bound and form.is_valid(),
            "nav": "Explore",
        },
    )


@login_required
@require_POST
def book(request, pk):
    form = SearchForm(request.POST, user=request.user)
    if not form.is_valid():
        messages.error(request, "Please select valid dates and pets.")
        return redirect("explore")
    d = form.cleaned_data
    try:
        booking = reserve(
            request.user, pk, [p.pk for p in d["pets"]], d["starts"], d["ends"]
        )
        return redirect("stay", pk=booking.pk)
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
        return redirect("explore")


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
            "events": booking.events.select_related("actor", "pet").order_by(
                "-created_at"
            ),
            "nav": "Bookings",
        },
    )


@login_required
def bookings(request):
    return render(
        request,
        "care/bookings.html",
        {
            "bookings": Booking.objects.filter(owner=request.user)
            .select_related("provider")
            .order_by("-created_at"),
            "nav": "Bookings",
        },
    )


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
    stays = Booking.objects.filter(provider__in=providers, status="active")
    tasks = (
        CareTask.objects.filter(booking__in=stays)
        .select_related("pet")
        .order_by("completed_at", "due_at")
    )
    return render(
        request,
        "care/operations.html",
        {
            "stays": stays,
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
    try:
        complete_task(request.user, pk)
        messages.success(request, "Care recorded in the stay timeline.")
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    return redirect("operations")


@login_required
@require_POST
def emergency(request, pk):
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
            "incidents": Incident.objects.filter(status="open").select_related(
                "booking__provider"
            ),
            "overdue": CareTask.objects.filter(
                critical=True, completed_at=None, due_at__lt=timezone.now()
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
        p = Provider.objects.select_for_update().get(pk=pk)
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
    qs = Booking.objects.filter(owner=request.user)
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
