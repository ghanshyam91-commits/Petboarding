from datetime import timedelta
from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from care.demo import DEMO_GROUP
from care.models import Booking, ComplianceRule, Credential, HealthRecord, Jurisdiction, Pet, Provider


@override_settings(ENABLE_DEMO_LOGIN=True)
class ProviderPreviewTests(TestCase):
    def setUp(self):
        self.parent=User.objects.create_user('preview-parent')
        self.operator=User.objects.create_user('preview-operator')
        self.city=Jurisdiction.objects.create(city='Bengaluru',state='Karnataka')
        ComplianceRule.objects.create(jurisdiction=self.city,version=1,reviewed=True,required_credentials=['identity'],required_vaccines=['rabies'])
        self.provider=Provider.objects.create(owner=self.operator,jurisdiction=self.city,name='Preview stay',kind='facility',species=['dog'],capacity=4,nightly_paise=120000)
        self.pet=Pet.objects.create(owner=self.parent,name='Uno',species='dog')
        self.end=timezone.localdate()+timedelta(days=2)
        Credential.objects.create(provider=self.provider,category='identity',status='verified',expires=self.end,verified_at=timezone.now(),verified_by=self.operator)
        HealthRecord.objects.create(pet=self.pet,kind='rabies',status='verified',expires=self.end,verified_at=timezone.now(),verified_by=self.operator)
        self.client.force_login(self.parent)
        self.url=reverse('provider_preview',args=[self.provider.pk])
        self.params={'city':'Bengaluru','starts':timezone.localdate().isoformat(),'ends':self.end.isoformat(),'pets':[self.pet.pk]}

    def test_quote_before_any_reservation(self):
        response=self.client.get(self.url,self.params)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['estimate']['total_paise'],240000)
        self.assertContains(response,'Total estimate')
        self.assertContains(response,'Reserve this stay')
        self.assertEqual(Booking.objects.count(),0)

    def test_details_without_dates_never_reserve(self):
        response=self.client.get(self.url)
        self.assertContains(response,'Preview stay')
        self.assertContains(response,'Choose pets and dates')
        self.assertNotContains(response,'Reserve this stay')
        self.assertEqual(Booking.objects.count(),0)

    def test_invalid_health_explains_block_without_book_button(self):
        self.pet.records.update(status='pending')
        response=self.client.get(self.url,self.params)
        self.assertContains(response,'verified rabies must remain valid through checkout')
        self.assertNotContains(response,'Reserve this stay')

    def test_pet_ownership_and_past_dates_validated(self):
        other=User.objects.create_user('preview-other')
        pet=Pet.objects.create(owner=other,name='Other',species='dog')
        for params in [{**self.params,'pets':[pet.pk]}, {**self.params,'starts':(timezone.localdate()-timedelta(days=1)).isoformat()}]:
            response=self.client.get(self.url,params)
            self.assertFalse(response.context['eligible'])
            self.assertNotContains(response,'Reserve this stay')

    def test_demo_provider_isolation_both_directions(self):
        group=Group.objects.create(name=DEMO_GROUP)
        self.operator.groups.add(group)
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.operator.groups.clear();self.parent.groups.add(group)
        self.assertEqual(self.client.get(self.url).status_code,404)
