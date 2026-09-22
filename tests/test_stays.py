from datetime import timedelta
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from care.models import *
from care.services.stays import *


class SafetyTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("parent", password="test-pass-long")
        self.operator = User.objects.create_user("provider", password="test-pass-long")
        self.stranger = User.objects.create_user("stranger", password="test-pass-long")
        self.city = Jurisdiction.objects.create(city="Bengaluru", state="Karnataka")
        self.rule = ComplianceRule.objects.create(
            jurisdiction=self.city,
            version=1,
            reviewed=True,
            required_credentials=["identity"],
            required_vaccines=["rabies"],
        )
        self.provider = Provider.objects.create(
            owner=self.operator,
            name="Boarder",
            jurisdiction=self.city,
            kind="facility",
            locality="Test locality",
            capacity=1,
            species=["dog"],
        )
        self.pet = Pet.objects.create(owner=self.owner, name="Uno", species="dog")
        self.start = timezone.localdate()
        self.end = self.start + timedelta(days=2)
        Credential.objects.create(
            provider=self.provider,
            category="identity",
            status="verified",
            expires=self.end,
            verified_by=self.operator,
            verified_at=timezone.now(),
        )
        HealthRecord.objects.create(
            pet=self.pet,
            kind="rabies",
            status="verified",
            expires=self.end,
            verified_by=self.operator,
            verified_at=timezone.now(),
        )

    def reserve(self):
        return reserve(
            self.owner, self.provider.pk, [self.pet.pk], self.start, self.end
        )

    def test_expired_health_blocks_and_rolls_back(self):
        self.pet.records.update(expires=self.start)
        with self.assertRaises(ValidationError):
            self.reserve()
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(CapacityDay.objects.count(), 0)

    def test_verified_label_without_reviewer_is_not_verification(self):
        self.pet.records.update(verified_by=None)
        with self.assertRaises(ValidationError):
            self.reserve()

    def test_resident_cat_is_hard_exclusion(self):
        self.provider.resident_species = ["cat"]
        self.provider.save()
        with self.assertRaises(ValidationError):
            self.reserve()

    def test_medication_competency_is_hard_exclusion(self):
        self.pet.medication_required = True
        self.pet.save()
        with self.assertRaises(ValidationError):
            self.reserve()

    def test_expired_credentials_block(self):
        self.provider.credentials.update(expires=self.start)
        with self.assertRaises(ValidationError):
            self.reserve()

    def test_unknown_jurisdiction_fails_closed(self):
        self.rule.reviewed = False
        self.rule.save()
        with self.assertRaises(ValidationError):
            self.reserve()

    def test_home_boarding_prohibited(self):
        self.provider.kind = "home"
        self.provider.save()
        with self.assertRaises(ValidationError):
            self.reserve()

    def test_overbooking_rejected(self):
        self.reserve()
        with self.assertRaises(ValidationError):
            self.reserve()
        self.assertEqual(Booking.objects.count(), 1)

    def test_pet_ownership(self):
        with self.assertRaises(PermissionDenied):
            reserve(
                self.stranger, self.provider.pk, [self.pet.pk], self.start, self.end
            )

    def test_multiple_pets_each_checked(self):
        self.provider.capacity = 3
        self.provider.save()
        other = Pet.objects.create(owner=self.owner, name="Other", species="dog")
        with self.assertRaises(ValidationError):
            reserve(
                self.owner,
                self.provider.pk,
                [self.pet.pk, other.pk],
                self.start,
                self.end,
            )

    def test_cancellation_releases_once(self):
        b = self.reserve()
        cancel(self.owner, b.pk)
        cancel(self.owner, b.pk)
        self.assertEqual(CapacityDay.objects.first().reserved, 0)
        self.reserve()

    def test_care_is_attributed_and_idempotent(self):
        b = self.reserve()
        b.status = "active"
        b.save()
        t = CareTask.objects.create(
            booking=b, pet=self.pet, kind="Feed", due_at=timezone.now()
        )
        with self.assertRaises(PermissionDenied):
            complete_task(self.owner, t.pk)
        complete_task(self.operator, t.pk)
        complete_task(self.operator, t.pk)
        self.assertEqual(b.events.count(), 1)
        self.assertEqual(b.events.first().actor, self.operator)

    def test_incident_hold_and_critical_notifications(self):
        b = self.reserve()
        with self.assertRaises(PermissionDenied):
            report_incident(self.stranger, b.pk, "injury", "Observed injury")
        incident = report_incident(self.owner, b.pk, "injury", "Observed injury")
        self.assertTrue(incident.evidence_hold)
        self.assertEqual(Notification.objects.filter(critical=True).count(), 2)

    def test_critical_escalation_is_idempotent(self):
        b = self.reserve()
        b.status = "active"
        b.save()
        CareTask.objects.create(
            booking=b,
            pet=self.pet,
            kind="Medicine",
            due_at=timezone.now() - timedelta(minutes=5),
            critical=True,
        )
        self.assertEqual(escalate_overdue(), 1)
        self.assertEqual(escalate_overdue(), 0)

    def test_evidence_instance_immutable(self):
        b = self.reserve()
        e = CareEvent.objects.create(booking=b, actor=self.owner, kind="Test")
        e.notes = "Changed"
        with self.assertRaises(ValueError):
            e.save()

    def test_non_participant_cannot_read_stay(self):
        b = self.reserve()
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(f"/stays/{b.pk}/").status_code, 403)

    def test_parent_cannot_use_provider_or_trust_views(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get("/operations/").status_code, 403)
        self.assertEqual(self.client.get("/trust/").status_code, 403)

    def test_parent_pages_render(self):
        b = self.reserve()
        self.client.force_login(self.owner)
        for url in [
            "/",
            "/explore/",
            "/bookings/",
            "/profile/",
            "/messages/",
            f"/stays/{b.pk}/",
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_provider_dashboard_renders(self):
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get("/operations/").status_code, 200)

    def test_search_displays_only_eligible(self):
        self.client.force_login(self.owner)
        response = self.client.get(
            "/explore/",
            {
                "city": "Bengaluru",
                "starts": self.start.isoformat(),
                "ends": self.end.isoformat(),
                "pets": [self.pet.pk],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Boarder")

    def test_handover_requires_both_parties(self):
        b = self.reserve()
        b.status = "confirmed"
        b.save()
        acknowledge_handover(
            self.operator, b.pk, "Alert and comfortable", "Bed", "Food", True
        )
        b.refresh_from_db()
        self.assertEqual(b.status, "confirmed")
        acknowledge_handover(self.owner, b.pk)
        b.refresh_from_db()
        self.assertEqual(b.status, "active")
