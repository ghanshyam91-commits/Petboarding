from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import path
from config.urls import urlpatterns as application_patterns
from django.utils import timezone

from care import account_flows
from care.models import CapacityDay, Credential, Jurisdiction, Provider, StaffMembership
from care.demo import DEMO_CITY

# Exercise real middleware and shared templates while the routes are integrated.
urlpatterns = [
    path('signup/', account_flows.signup, name='signup'),
    path('account/', account_flows.account, name='account'),
] + application_patterns


@override_settings(SECURE_SSL_REDIRECT=False, ROOT_URLCONF=__name__)
class AccountFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user('listing_owner', email='owner@example.test')
        cls.other = User.objects.create_user('another_parent')
        cls.city = Jurisdiction.objects.create(city='Bengaluru', state='Karnataka')
        cls.demo_city = Jurisdiction.objects.create(city=DEMO_CITY, state='Demo')
        cls.provider = Provider.objects.create(owner=cls.owner, name='Original space',
            jurisdiction=cls.city, kind='facility', locality='Indiranagar',
            species=['dog'], capacity=5, nightly_paise=150000)

    def listing_data(self, **changes):
        values = {'name':'Kind Care', 'jurisdiction':self.city.pk, 'kind':'facility',
                  'locality':'Indiranagar', 'species':['dog','cat'], 'capacity':5,
                  'nightly_rupees':'1499.50', 'care_description':'Quiet rooms and supervised walks'}
        values.update(changes)
        return values

    def test_signup_creates_only_parent_and_logs_in(self):
        response = self.client.post('/signup/', {'username':'new_parent','first_name':'Alex',
            'email':'Alex@example.test','password1':'PetCare-unique-840!','password2':'PetCare-unique-840!',
            'is_staff':'true','is_superuser':'true'})
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username='new_parent')
        self.assertEqual(user.email, 'alex@example.test')
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_signup_validates_email_and_password(self):
        form = account_flows.SignupForm({'username':'bad_parent','first_name':'Alex',
            'email':'OWNER@example.test','password1':'short','password2':'short'})
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)
        self.assertIn('password2', form.errors)

    def test_new_listing_is_suspended_and_species_constrained(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post('/account/', self.listing_data()).status_code, 302)
        listing = Provider.objects.get(name='Kind Care')
        self.assertEqual(listing.owner, self.owner)
        self.assertTrue(listing.suspended)
        self.assertEqual(listing.nightly_paise,149950)
        self.assertEqual(listing.species,['dog','cat'])
        self.assertFalse(listing.credentials.exists())
        self.assertFalse(account_flows.ProviderListingForm(self.listing_data(species=['snake'])).is_valid())
        self.assertFalse(account_flows.ProviderListingForm(self.listing_data(jurisdiction=self.demo_city.pk)).is_valid())

    def test_other_owner_and_frontdesk_cannot_edit(self):
        StaffMembership.objects.create(provider=self.provider,user=self.other,role='frontdesk')
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f'/account/?provider={self.provider.pk}').status_code,404)
        self.assertEqual(self.client.post('/account/',self.listing_data(provider_id=self.provider.pk)).status_code,404)
        self.provider.refresh_from_db()
        self.assertEqual(self.provider.name,'Original space')
        self.assertFalse(self.provider.suspended)

    def test_capacity_cannot_drop_below_reserved_and_edit_requires_review(self):
        CapacityDay.objects.create(provider=self.provider,day=timezone.localdate(),reserved=4)
        credential = Credential.objects.create(provider=self.provider,category='identity',
            status='verified',expires=timezone.localdate()+timedelta(days=30),verified_by=self.owner,
            verified_at=timezone.now())
        self.client.force_login(self.owner)
        response=self.client.post('/account/',self.listing_data(provider_id=self.provider.pk,capacity=3))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Capacity cannot be lower')
        self.provider.refresh_from_db()
        self.assertEqual(self.provider.capacity,5)
        self.assertFalse(self.provider.suspended)
        response=self.client.post('/account/',self.listing_data(provider_id=self.provider.pk,capacity=4))
        self.assertEqual(response.status_code,302)
        self.provider.refresh_from_db()
        self.assertTrue(self.provider.suspended)
        self.assertEqual(self.provider.capacity,4)
        credential.refresh_from_db()
        self.assertEqual(credential.status,'verified')
