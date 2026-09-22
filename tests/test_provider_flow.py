from datetime import timedelta
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from care.models import (Pet, Provider, Jurisdiction, ComplianceRule, Credential,
                         HealthRecord, Booking, CapacityDay, CareTask, CareEvent,
                         CustodyEvent, StaffMembership)
from care.services.stays import reserve
from care.services.provider_flow import (visible_bookings, confirm_booking,
    checkin_booking, checkout_booking, record_care_event, create_care_task)


class ProviderFlowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('flow-parent')
        self.operator = User.objects.create_user('flow-provider')
        self.stranger = User.objects.create_user('flow-stranger')
        self.city = Jurisdiction.objects.create(city='Flow City', state='Test')
        ComplianceRule.objects.create(jurisdiction=self.city, version=1, reviewed=True,
            required_credentials=['identity'], required_vaccines=['rabies'])
        self.provider = Provider.objects.create(owner=self.operator, jurisdiction=self.city,
            name='Flow stay', kind='facility', capacity=1, species=['dog'])
        self.pet = Pet.objects.create(owner=self.owner, name='Milo', species='dog',
            routine=[{'time': '09:00', 'kind': 'Breakfast'}])
        self.start = timezone.localdate()
        self.end = self.start + timedelta(days=3)
        Credential.objects.create(provider=self.provider, category='identity', status='verified',
            expires=self.end, verified_by=self.operator, verified_at=timezone.now())
        HealthRecord.objects.create(pet=self.pet, kind='rabies', status='verified',
            expires=self.end, verified_by=self.operator, verified_at=timezone.now())
        self.booking = reserve(self.owner, self.provider.pk, [self.pet.pk], self.start, self.end)

    def activate(self):
        confirm_booking(self.operator, self.booking.pk)
        checkin_booking(self.operator, self.booking.pk, 'Comfortable', 'Lead', 'Food', True)
        checkin_booking(self.owner, self.booking.pk)
        self.booking.refresh_from_db()

    def test_full_two_party_lifecycle_keeps_capacity_until_checkout(self):
        confirm_booking(self.operator, self.booking.pk)
        confirm_booking(self.operator, self.booking.pk)
        self.assertEqual(CareEvent.objects.filter(kind='Stay confirmed').count(), 1)
        self.assertTrue(all(s.reserved == 1 for s in CapacityDay.objects.all()))
        with self.assertRaises(ValidationError):
            checkin_booking(self.owner, self.booking.pk)
        checkin_booking(self.operator, self.booking.pk, 'Comfortable', 'Lead', 'Food', True)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'confirmed')
        checkin_booking(self.owner, self.booking.pk)
        checkin_booking(self.owner, self.booking.pk)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'active')
        self.assertEqual(self.booking.tasks.count(), 3)
        with self.assertRaises(ValidationError):
            checkout_booking(self.owner, self.booking.pk)
        checkout_booking(self.operator, self.booking.pk, 'Comfortable', 'Lead returned')
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'active')
        checkout_booking(self.owner, self.booking.pk)
        checkout_booking(self.owner, self.booking.pk)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'completed')
        self.assertTrue(all(s.reserved == 0 for s in CapacityDay.objects.all()))
        self.assertEqual(CustodyEvent.objects.filter(kind__startswith='checkout_').count(), 2)
        self.assertEqual(CareEvent.objects.filter(kind='Check-out complete').count(), 1)

    def test_confirm_rechecks_credentials_without_double_counting_reserved_capacity(self):
        confirm_booking(self.operator, self.booking.pk)  # capacity=1 already fully reserved
        self.booking.status = 'reserved'
        self.booking.save()
        self.provider.credentials.update(expires=self.start)
        with self.assertRaises(ValidationError):
            confirm_booking(self.operator, self.booking.pk)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'reserved')

    def test_checkin_revalidates_health_and_arrival_date(self):
        confirm_booking(self.operator, self.booking.pk)
        self.pet.records.update(expires=self.start)
        with self.assertRaises(ValidationError):
            checkin_booking(self.operator, self.booking.pk, 'Good', '', '', True)
        self.pet.records.update(expires=self.end)
        self.booking.starts += timedelta(days=1)
        self.booking.save()
        with self.assertRaises(ValidationError):
            checkin_booking(self.operator, self.booking.pk, 'Good', '', '', True)
        self.assertEqual(CustodyEvent.objects.count(), 0)

    def test_parent_and_stranger_cannot_confirm_or_record_care(self):
        for user in (self.owner, self.stranger):
            with self.assertRaises(PermissionDenied):
                confirm_booking(user, self.booking.pk)
        self.activate()
        for user in (self.owner, self.stranger):
            with self.assertRaises(PermissionDenied):
                record_care_event(user, self.booking.pk, self.pet.pk, 'Walk', 'Happy')
        with self.assertRaises(PermissionDenied):
            checkout_booking(self.stranger, self.booking.pk, 'Good', 'Lead')

    def test_provider_and_authorized_caregiver_see_bookings_without_parent_access_leak(self):
        self.assertIn(self.booking, visible_bookings(self.operator))
        self.assertIn(self.booking, visible_bookings(self.owner))
        self.assertFalse(visible_bookings(self.stranger).exists())
        StaffMembership.objects.create(provider=self.provider, user=self.stranger, role='frontdesk')
        self.assertFalse(visible_bookings(self.stranger).exists())
        StaffMembership.objects.filter(user=self.stranger).update(role='caregiver')
        self.assertIn(self.booking, visible_bookings(self.stranger))

    def test_manual_care_and_tasks_require_stay_pet_and_valid_times(self):
        self.activate()
        other = Pet.objects.create(owner=self.stranger, name='Other', species='dog')
        with self.assertRaises(ValidationError):
            record_care_event(self.operator, self.booking.pk, other.pk, 'Walk', 'Happy')
        event = record_care_event(self.operator, self.booking.pk, self.pet.pk, 'Walk', 'Comfortable after a short walk.')
        self.assertEqual(event.actor, self.operator)
        with self.assertRaises(ValidationError):
            create_care_task(self.operator, self.booking.pk, self.pet.pk, 'Meal', timezone.now()-timedelta(hours=1))
        task = create_care_task(self.operator, self.booking.pk, self.pet.pk, 'Meal', timezone.now()+timedelta(hours=1))
        self.assertEqual(task.booking, self.booking)
        with self.assertRaises(ValidationError):
            create_care_task(self.operator, self.booking.pk, self.pet.pk, 'Meal', timezone.now()+timedelta(days=7))

    def test_checkout_blocks_due_critical_care_and_requires_return_record(self):
        self.activate()
        with self.assertRaises(ValidationError):
            checkout_booking(self.operator, self.booking.pk, '', '')
        task = CareTask.objects.create(booking=self.booking, pet=self.pet, kind='Medicine', critical=True,
            due_at=timezone.now()-timedelta(minutes=1))
        with self.assertRaises(ValidationError):
            checkout_booking(self.operator, self.booking.pk, 'Good', 'Lead')
        self.assertFalse(CustodyEvent.objects.filter(kind='checkout_provider_ack').exists())
        task.completed_at=timezone.now()
        task.save()
        checkout_booking(self.operator, self.booking.pk, 'Good', 'Lead')
        self.assertTrue(CustodyEvent.objects.filter(kind='checkout_provider_ack').exists())

    def test_malformed_routine_fails_with_validation_instead_of_checkin_server_error(self):
        self.booking.care_snapshot = {str(self.pet.pk): {'routine': [{'time': 'not-a-time'}]}}
        self.booking.save()
        with self.assertRaises(ValidationError):
            confirm_booking(self.operator, self.booking.pk)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'reserved')

    def test_provider_cannot_reserve_own_facility(self):
        own_pet = Pet.objects.create(owner=self.operator, name='Own pet', species='dog')
        with self.assertRaises(ValidationError):
            reserve(self.operator, self.provider.pk, [own_pet.pk], self.start, self.end)
        self.assertEqual(Booking.objects.count(), 1)

    def test_future_task_cannot_be_completed(self):
        from care.services.stays import complete_task
        self.activate()
        task = CareTask.objects.create(booking=self.booking, pet=self.pet, kind='Dinner',
                                       due_at=timezone.now()+timedelta(hours=2))
        with self.assertRaises(ValidationError):
            complete_task(self.operator, task.pk)
        task.refresh_from_db()
        self.assertIsNone(task.completed_at)
        self.assertFalse(CareEvent.objects.filter(kind='Dinner').exists())

    def test_completed_stay_tasks_do_not_escalate(self):
        from care.services.stays import escalate_overdue
        self.activate()
        checkout_booking(self.operator, self.booking.pk, 'Comfortable', 'Lead returned')
        checkout_booking(self.owner, self.booking.pk)
        CareTask.objects.create(booking=self.booking, pet=self.pet, kind='Medication', critical=True,
                               due_at=timezone.now()-timedelta(minutes=1))
        self.assertEqual(escalate_overdue(), 0)
        self.assertFalse(self.booking.incidents.exists())
