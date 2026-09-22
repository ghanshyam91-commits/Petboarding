from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone


class Pet(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    name = models.CharField(max_length=80)
    species = models.CharField(max_length=12, choices=[("dog", "Dog"), ("cat", "Cat")])
    breed = models.CharField(max_length=100, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    sex = models.CharField(max_length=20, blank=True)
    neutered = models.BooleanField(default=False)
    microchip = models.CharField(max_length=80, blank=True)
    compatible_cats = models.BooleanField(default=False)
    compatible_dogs = models.BooleanField(default=False)
    aggression_history = models.BooleanField(default=False)
    medication_required = models.BooleanField(default=False)
    health = models.JSONField(default=dict, blank=True)
    behaviour = models.JSONField(default=dict, blank=True)
    routine = models.JSONField(default=list, blank=True)
    emergency = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name


class HealthRecord(models.Model):
    pet = models.ForeignKey(Pet, on_delete=models.PROTECT, related_name="records")
    kind = models.CharField(max_length=80)
    status = models.CharField(
        max_length=16,
        choices=[
            (x, x.title())
            for x in ["unverified", "pending", "verified", "expired", "rejected"]
        ],
        default="pending",
    )
    expires = models.DateField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    private_document_key = models.CharField(max_length=300, blank=True)


class Jurisdiction(models.Model):
    city = models.CharField(max_length=100, unique=True)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=2, default="IN")

    def __str__(self):
        return self.city


class ComplianceRule(models.Model):
    jurisdiction = models.ForeignKey(Jurisdiction, on_delete=models.PROTECT)
    version = models.PositiveIntegerField()
    effective_at = models.DateTimeField(default=timezone.now)
    home_boarding_allowed = models.BooleanField(default=False)
    required_credentials = models.JSONField(default=list)
    required_vaccines = models.JSONField(default=list)
    reviewed = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["jurisdiction", "version"], name="unique_rule_version"
            )
        ]


class Provider(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    jurisdiction = models.ForeignKey(Jurisdiction, on_delete=models.PROTECT)
    kind = models.CharField(
        max_length=20,
        choices=[
            ("facility", "Facility"),
            ("home", "Home boarding"),
            ("daycare", "Daycare"),
            ("sitter", "Pet sitter"),
        ],
    )
    locality = models.CharField(max_length=100)
    private_address = models.TextField(blank=True)
    species = models.JSONField(default=list)
    resident_species = models.JSONField(default=list)
    capacity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    medication_competent = models.BooleanField(default=False)
    accepts_aggression = models.BooleanField(default=False)
    overnight_supervision = models.BooleanField(default=False)
    ac = models.BooleanField(default=False)
    suspended = models.BooleanField(default=False)
    nightly_paise = models.PositiveIntegerField(default=120000)
    care_description = models.TextField(blank=True)
    audit = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name


class Credential(models.Model):
    provider = models.ForeignKey(
        Provider, on_delete=models.PROTECT, related_name="credentials"
    )
    category = models.CharField(max_length=80)
    status = models.CharField(max_length=20, default="pending")
    issued = models.DateField(null=True, blank=True)
    expires = models.DateField()
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    issuing_authority = models.CharField(max_length=200, blank=True)
    private_document_key = models.CharField(max_length=300, blank=True)


class StaffMembership(models.Model):
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    role = models.CharField(
        max_length=20,
        choices=[
            (x, x.title()) for x in ["manager", "caregiver", "transport", "frontdesk"]
        ],
    )
    training = models.JSONField(default=list)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "user"], name="unique_staff")
        ]


class Booking(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT)
    pets = models.ManyToManyField(Pet)
    starts = models.DateField()
    ends = models.DateField()
    status = models.CharField(
        max_length=25,
        default="reserved",
        choices=[
            (x, x.title())
            for x in ["reserved", "confirmed", "active", "completed", "cancelled"]
        ],
    )
    quote = models.JSONField(default=dict)
    care_snapshot = models.JSONField(default=dict)
    emergency_consent = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends__gt=models.F("starts")), name="valid_stay_dates"
            )
        ]


class CapacityDay(models.Model):
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT)
    day = models.DateField()
    reserved = models.PositiveIntegerField(default=0)
    blocked = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "day"], name="unique_capacity_day"
            )
        ]


class CareTask(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="tasks")
    pet = models.ForeignKey(Pet, on_delete=models.PROTECT)
    kind = models.CharField(max_length=50)
    due_at = models.DateTimeField()
    critical = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    escalated_at = models.DateTimeField(null=True, blank=True)

    @property
    def state(self):
        if self.completed_at:
            return "Completed"
        if self.escalated_at:
            return "Escalated"
        if self.due_at < timezone.now():
            return "Late"
        return "Upcoming"


class AppendOnly(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Append-only record")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Append-only record")


class CareEvent(AppendOnly):
    booking = models.ForeignKey(
        Booking, on_delete=models.PROTECT, related_name="events"
    )
    pet = models.ForeignKey(Pet, on_delete=models.PROTECT, null=True, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(max_length=80)
    notes = models.TextField(blank=True)


class Incident(models.Model):
    booking = models.ForeignKey(
        Booking, on_delete=models.PROTECT, related_name="incidents"
    )
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    category = models.CharField(max_length=80)
    description = models.TextField()
    status = models.CharField(max_length=20, default="open")
    evidence_hold = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AuditEntry(AppendOnly):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True
    )
    action = models.CharField(max_length=100)
    object_type = models.CharField(max_length=80)
    object_id = models.PositiveBigIntegerField()
    detail = models.JSONField(default=dict)


class LedgerEntry(AppendOnly):
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT)
    kind = models.CharField(max_length=30)
    amount_paise = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default="INR")
    external_id = models.CharField(max_length=200, unique=True)


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT)
    message = models.TextField()
    critical = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default="queued")
    attempts = models.PositiveIntegerField(default=0)
    acknowledged_at = models.DateTimeField(null=True, blank=True)


class Review(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.PROTECT)
    ratings = models.JSONField(default=dict)
    text = models.TextField()
    matched_listing = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)


class Message(models.Model):
    booking = models.ForeignKey(
        Booking, on_delete=models.PROTECT, related_name="messages"
    )
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    text = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)


class Trial(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT)
    pet = models.ForeignKey(Pet, on_delete=models.PROTECT)
    kind = models.CharField(
        max_length=20,
        choices=[
            ("video", "Video call"),
            ("meet", "Meet and greet"),
            ("daycare", "Daycare trial"),
            ("short_stay", "Short stay"),
        ],
    )
    scheduled_at = models.DateTimeField()
    outcome = models.CharField(
        max_length=30,
        default="pending",
        choices=[
            (x, x.replace("_", " ").title())
            for x in ["pending", "suitable", "with_conditions", "unsuitable"]
        ],
    )
    owner_notes = models.TextField(blank=True)
    provider_notes = models.TextField(blank=True)


class CustodyEvent(AppendOnly):
    booking = models.ForeignKey(
        Booking, on_delete=models.PROTECT, related_name="custody_events"
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(max_length=30)
    details = models.JSONField(default=dict)


class Handover(models.Model):
    booking = models.OneToOneField(
        Booking, on_delete=models.PROTECT, related_name="handover"
    )
    condition = models.TextField()
    belongings = models.TextField()
    food_and_medicines = models.TextField()
    emergency_verified = models.BooleanField(default=False)
    owner_ack_at = models.DateTimeField(null=True)
    provider_ack_at = models.DateTimeField(null=True)


class Dispute(models.Model):
    booking = models.ForeignKey(
        Booking, on_delete=models.PROTECT, related_name="disputes"
    )
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField()
    status = models.CharField(max_length=20, default="open")
    evidence_hold = models.BooleanField(default=True)
    decision = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class InsurancePolicy(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.PROTECT)
    insurer = models.CharField(max_length=200)
    coverage = models.JSONField()
    exclusions = models.TextField()
    deductible_paise = models.PositiveIntegerField()
    maximum_paise = models.PositiveIntegerField()
    claim_procedure = models.TextField()
    terms_version = models.CharField(max_length=100)


class Consent(AppendOnly):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    purpose = models.CharField(max_length=100)
    version = models.CharField(max_length=40)
    granted = models.BooleanField()


class PrivacyRequest(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(
        max_length=20, choices=[("export", "Export"), ("delete", "Delete")]
    )
    status = models.CharField(max_length=20, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)


class RateBucket(models.Model):
    key = models.CharField(max_length=64)
    window = models.PositiveBigIntegerField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["key", "window"], name="unique_rate_bucket")
        ]

from .evidence_models import HealthEvidence
