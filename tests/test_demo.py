from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from care.demo import DEMO_USERS, DEMO_CITY
from care.models import Booking, CareTask, Message, Pet, Provider
from care.services.stays import reserve


@override_settings(ENABLE_DEMO_LOGIN=True, SECURE_SSL_REDIRECT=False)
class PublicDemoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_public_demo', stdout=StringIO())

    def test_sample_data_and_repeat_seed(self):
        before = [m.objects.count() for m in (User, Pet, Provider, Booking, Message)]
        call_command('seed_public_demo', stdout=StringIO())
        self.assertEqual(before, [m.objects.count() for m in (User, Pet, Provider, Booking, Message)])
        self.assertEqual(before, [2, 2, 3, 3, 2])
        for user in User.objects.all():
            self.assertFalse(user.has_usable_password())
            self.assertFalse(user.is_staff or user.is_superuser)

    def test_parent_login_and_populated_pages(self):
        response = self.client.post('/demo/login/', {'role': 'parent'}, follow=True)
        self.assertContains(response, 'Milo')
        self.assertContains(response, 'Luna')
        self.assertContains(response, 'Read-only')
        for path in ['/profile/', '/bookings/', '/messages/', '/explore/']:
            self.assertEqual(self.client.get(path).status_code, 200)
        for booking in Booking.objects.all():
            self.assertEqual(self.client.get(f'/stays/{booking.pk}/').status_code, 200)
        response = self.client.get('/explore/', {'city': DEMO_CITY,
            'starts': timezone.localdate(), 'ends': timezone.localdate()+timedelta(days=2),
            'pets': Pet.objects.get(name='Milo').pk})
        self.assertContains(response, 'Green House')
        self.assertContains(response, 'Quiet Tails')
        self.assertEqual(self.client.post('/logout/').status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_provider_login_and_writes_blocked(self):
        response = self.client.post('/demo/login/', {'role': 'provider'}, follow=True)
        self.assertContains(response, 'Evening walk')
        task = CareTask.objects.first()
        self.client.post(f'/tasks/{task.pk}/complete/')
        task.refresh_from_db()
        self.assertIsNone(task.completed_at)
        self.assertEqual(self.client.get('/admin/').status_code, 403)
        self.assertEqual(self.client.get('/trust/').status_code, 403)

    def test_parent_writes_blocked_and_real_accounts_unchanged(self):
        self.client.post('/demo/login/', {'role': 'parent'})
        booking = Booking.objects.get(status='reserved')
        self.client.post(f'/stays/{booking.pk}/cancel/')
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'reserved')
        self.client.post('/profile/', {'name': 'Unwanted', 'species': 'dog'})
        self.assertFalse(Pet.objects.filter(name='Unwanted').exists())
        real = User.objects.create_user('real_owner')
        self.client.force_login(real)
        self.client.post('/profile/', {'name': 'Real pet', 'species': 'dog'})
        self.assertTrue(Pet.objects.filter(owner=real, name='Real pet').exists())
        self.assertEqual(self.client.get(f'/stays/{booking.pk}/').status_code, 403)
        with self.assertRaises(PermissionDenied):
            reserve(real, booking.provider_id, [Pet.objects.get(owner=real).pk],
                    timezone.localdate(), timezone.localdate()+timedelta(days=1))

    def test_csrf_role_and_feature_gate(self):
        self.assertEqual(Client(enforce_csrf_checks=True).post('/demo/login/', {'role': 'parent'}).status_code, 403)
        self.assertEqual(self.client.get('/demo/login/').status_code, 405)
        self.assertEqual(self.client.post('/demo/login/', {'role': 'admin'}).status_code, 404)
        with self.settings(ENABLE_DEMO_LOGIN=False):
            self.assertEqual(self.client.post('/demo/login/', {'role': 'parent'}).status_code, 404)
            self.assertNotContains(self.client.get('/login/'), 'Try as pet parent')
        parent = User.objects.get(username=DEMO_USERS['parent'])
        parent.is_staff = True
        parent.save()
        self.client.post('/demo/login/', {'role': 'parent'})
        self.assertNotIn('_auth_user_id', self.client.session)
