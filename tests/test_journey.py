"""HTTP-level owner/provider journey, using only the isolated test database."""
from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from care.models import (Pet, Provider, Jurisdiction, ComplianceRule, Credential,
    HealthRecord, Booking, CapacityDay, CareTask, Review)


class StayJourneyTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user('journey-parent')
        self.provider_user = User.objects.create_user('journey-provider')
        self.unrelated = User.objects.create_user('journey-outsider')
        self.start = timezone.localdate()
        self.end = self.start + timedelta(days=2)
        city = Jurisdiction.objects.create(city='Bengaluru', state='Karnataka')
        ComplianceRule.objects.create(jurisdiction=city, version=1, reviewed=True,
            required_credentials=['identity'], required_vaccines=['rabies'])
        self.provider = Provider.objects.create(owner=self.provider_user, jurisdiction=city,
            name='Journey Boarding', kind='facility', species=['dog'], capacity=2)
        self.pet = Pet.objects.create(owner=self.parent, name='Journey Milo', species='dog')
        Credential.objects.create(provider=self.provider, category='identity', status='verified',
            expires=self.end, verified_by=self.provider_user, verified_at=timezone.now())
        HealthRecord.objects.create(pet=self.pet, kind='rabies', status='verified',
            expires=self.end, verified_by=self.provider_user, verified_at=timezone.now())
        self.owner_client = Client()
        self.owner_client.force_login(self.parent)
        self.provider_client = Client()
        self.provider_client.force_login(self.provider_user)
        self.outsider_client = Client()
        self.outsider_client.force_login(self.unrelated)

    def book(self):
        response = self.owner_client.post(reverse('book', args=[self.provider.pk]), {
            'city': 'Bengaluru', 'starts': self.start.isoformat(),
            'ends': self.end.isoformat(), 'pets': [self.pet.pk]})
        self.assertEqual(response.status_code, 302)
        booking = Booking.objects.get(owner=self.parent)
        self.assertEqual(response.url, reverse('stay', args=[booking.pk]))
        return booking

    def post_stay(self, client, route, booking, data=None):
        response = client.post(reverse(route, args=[booking.pk]), data or {}, follow=True)
        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        return response

    def test_complete_owner_provider_journey(self):
        search = self.owner_client.get(reverse('explore'), {
            'city': 'Bengaluru', 'starts': self.start.isoformat(),
            'ends': self.end.isoformat(), 'pets': [self.pet.pk]})
        self.assertContains(search, 'Journey Boarding')
        booking = self.book()
        self.assertEqual(booking.status, 'reserved')
        for route in ('bookings', 'inbox'):
            response = self.provider_client.get(reverse(route))
            self.assertContains(response, 'Journey Boarding')
        self.post_stay(self.provider_client, 'confirm_stay', booking)
        self.assertEqual(booking.status, 'confirmed')
        self.post_stay(self.provider_client, 'handover', booking, {
            'condition': 'Alert and comfortable', 'belongings': 'Lead and bed',
            'food': 'Labelled food portions', 'emergency_verified': 'on'})
        self.assertEqual(booking.status, 'confirmed')
        self.post_stay(self.owner_client, 'handover', booking)
        self.assertEqual(booking.status, 'active')
        self.post_stay(self.provider_client, 'record_care', booking, {
            'pet': self.pet.pk, 'kind': 'Walk', 'notes': 'Enjoyed a calm walk in the garden.'})
        self.assertTrue(booking.events.filter(kind='Walk', actor=self.provider_user).exists())
        self.post_stay(self.provider_client, 'add_task', booking, {
            'pet': self.pet.pk, 'kind': 'Meal',
            'due_at': timezone.localtime(timezone.now()+timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M')})
        task = booking.tasks.get(kind='Meal')
        task.due_at = timezone.now()-timedelta(seconds=1)
        task.save(update_fields=['due_at'])
        response = self.provider_client.post(reverse('task_complete', args=[task.pk]), follow=True)
        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.completed_by, self.provider_user)
        self.post_stay(self.provider_client, 'send_message', booking, {'text': 'Milo had a lovely walk.'})
        self.assertContains(self.owner_client.get(reverse('stay', args=[booking.pk])), 'Milo had a lovely walk.')
        self.post_stay(self.provider_client, 'checkout', booking, {
            'condition': 'Comfortable and ready to go home', 'belongings': 'Lead and bed returned'})
        self.assertEqual(booking.status, 'active')
        self.post_stay(self.owner_client, 'checkout', booking)
        self.assertEqual(booking.status, 'completed')
        self.assertTrue(all(slot.reserved == 0 for slot in CapacityDay.objects.all()))
        ratings = {name: 5 for name in ('cleanliness', 'communication', 'care_quality',
            'update_reliability', 'description_accuracy', 'handling', 'overall')}
        self.post_stay(self.owner_client, 'review', booking,
            {**ratings, 'text': 'A comfortable stay with clear updates.', 'matched_listing': 'on'})
        self.assertTrue(Review.objects.filter(booking=booking, ratings__overall=5).exists())
        self.assertContains(self.provider_client.get(reverse('bookings')), 'Journey Boarding')

    def test_unrelated_user_and_parent_cannot_operate_other_stays(self):
        booking = self.book()
        self.assertEqual(self.outsider_client.get(reverse('stay', args=[booking.pk])).status_code, 403)
        for client in (self.owner_client, self.outsider_client):
            self.assertEqual(client.post(reverse('confirm_stay', args=[booking.pk])).status_code, 403)
        for route in ('handover', 'checkout', 'record_care', 'add_task'):
            data = {'pet': self.pet.pk, 'kind': 'Walk', 'notes': 'Not permitted',
                'due_at': timezone.localtime(timezone.now()+timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M')}
            self.assertEqual(self.outsider_client.post(reverse(route, args=[booking.pk]), data).status_code, 403)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'reserved')
        self.assertFalse(booking.events.exists())
        self.assertFalse(booking.tasks.exists())
