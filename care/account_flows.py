"""Self-service account entry and owner-only listing submissions."""
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .demo import DEMO_CITY
from .models import AuditEntry, CapacityDay, Jurisdiction, Provider


class SignupForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, label="Your name")
    email = forms.EmailField(max_length=254, label="Email address")

    class Meta(UserCreationForm.Meta):
        fields = ("first_name", "email", "username")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.pop("autofocus", None)

    def clean_email(self):
        value = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise forms.ValidationError("An account already uses this email. Please sign in.")
        return value


class ProviderListingForm(forms.ModelForm):
    species = forms.MultipleChoiceField(
        choices=[("dog", "Dogs"), ("cat", "Cats")],
        widget=forms.CheckboxSelectMultiple, label="Pets you care for",
    )
    resident_species = forms.MultipleChoiceField(
        choices=[("dog", "Dogs"), ("cat", "Cats")], required=False,
        widget=forms.CheckboxSelectMultiple, label="Resident pets at your space",
    )
    nightly_rupees = forms.DecimalField(
        min_value=Decimal("1.00"), max_value=Decimal("1000000.00"),
        max_digits=9, decimal_places=2, label="Price per pet per night (₹)",
        help_text="The listed price is an unpaid reservation estimate.",
    )

    class Meta:
        model = Provider
        fields = [
            "name", "jurisdiction", "kind", "locality", "private_address",
            "species", "resident_species", "capacity", "nightly_rupees",
            "care_description", "overnight_supervision", "medication_competent",
            "accepts_aggression", "ac",
        ]
        labels = {"jurisdiction": "City", "capacity": "Maximum pets at a time",
                  "care_description": "How you care for pets", "ac": "Air-conditioned space",
                  "accepts_aggression": "Equipped to handle pets with an aggression history"}
        widgets = {"private_address": forms.Textarea(attrs={"rows": 3}),
                   "care_description": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["jurisdiction"].queryset = Jurisdiction.objects.exclude(
            city=DEMO_CITY).order_by("city")
        self.fields["capacity"].min_value = 1
        if self.instance.pk:
            self.initial["nightly_rupees"] = Decimal(self.instance.nightly_paise) / 100

    def clean_capacity(self):
        value = self.cleaned_data["capacity"]
        if value < 1:
            raise forms.ValidationError("Capacity must be at least one pet.")
        if self.instance.pk:
            occupied = CapacityDay.objects.filter(provider=self.instance).aggregate(
                highest=Max("reserved"))["highest"] or 0
            if value < occupied:
                raise forms.ValidationError(
                    f"Capacity cannot be lower than the {occupied} pets already reserved.")
        return value


@require_http_methods(["GET", "POST"])
def signup(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = SignupForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.is_staff = False
        user.is_superuser = False
        user.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Welcome to SafeStay. Add your pet’s care passport to get started.")
        return redirect("home")
    return render(request, "care/signup.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def account(request):
    provider = None
    provider_id = request.POST.get("provider_id") if request.method == "POST" else request.GET.get("provider")
    if provider_id and not provider_id.isdecimal():
        from django.http import Http404
        raise Http404
    # The provider row serializes listing changes against capacity reservations.
    with transaction.atomic():
        if provider_id:
            owned = Provider.objects.filter(owner=request.user)
            if request.method == "POST":
                owned = owned.select_for_update()
            provider = get_object_or_404(owned, pk=provider_id)
        form = ProviderListingForm(request.POST if request.method == "POST" else None, instance=provider)
        if request.method == "POST" and form.is_valid():
            listing = form.save(commit=False)
            listing.owner = request.user
            listing.nightly_paise = int(form.cleaned_data["nightly_rupees"] * 100)
            listing.suspended = True
            listing.save()
            AuditEntry.objects.create(actor=request.user, action="provider_listing_submitted",
                                      object_type="provider", object_id=listing.pk,
                                      detail={"pending_review": True})
            messages.success(request, "Listing submitted for platform review. New reservations remain paused until approved.")
            return redirect("account")
    return render(request, "care/account.html", {
        "form": form, "editing_provider": provider,
        "owned_providers": Provider.objects.filter(owner=request.user).select_related("jurisdiction"),
        "cities_available": form.fields["jurisdiction"].queryset.exists(),
        "nav": "Account",
    })
