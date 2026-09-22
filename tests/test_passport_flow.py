from datetime import timedelta
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import include, path, reverse
from django.utils import timezone
from care import passport_flows
from care.models import AuditEntry, HealthEvidence, HealthRecord, Pet

urlpatterns=[
    path('pets/<int:pk>/edit/',passport_flows.pet_edit,name='pet_edit'),
    path('pets/<int:pk>/health/',passport_flows.health_submit,name='health_submit'),
    path('health/<int:pk>/document/',passport_flows.health_document,name='health_document'),
    path('health/<int:pk>/review/',passport_flows.health_review,name='health_review'),
    path('',include('config.urls')),
]

@override_settings(ROOT_URLCONF=__name__)
class PassportFlowTests(TestCase):
    def setUp(self):
        self.owner=User.objects.create_user('passport-parent')
        self.other=User.objects.create_user('passport-other')
        self.reviewer=User.objects.create_user('passport-reviewer',is_staff=True)
        self.pet=Pet.objects.create(owner=self.owner,name='Uno',species='dog')
        self.client.force_login(self.owner)

    def upload(self,**extra):
        data={'kind':'Rabies','expires':(timezone.localdate()+timedelta(days=365)).isoformat(),
              'document':SimpleUploadedFile('rabies.pdf',b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n',content_type='application/pdf'),**extra}
        return self.client.post(reverse('health_submit',args=[self.pet.pk]),data)

    def test_owner_submits_staff_verifies_and_document_stays_private(self):
        self.assertEqual(self.upload(status='verified',verified_by=self.owner.pk).status_code,302)
        record=HealthRecord.objects.get()
        self.assertEqual(record.status,'pending');self.assertIsNone(record.verified_by)
        self.assertEqual(record.kind,'rabies')
        url=reverse('health_document',args=[record.pk])
        response=self.client.get(url)
        self.assertEqual(response.status_code,200)
        self.assertIn('attachment',response['Content-Disposition'])
        self.assertEqual(response['Cache-Control'],'private, no-store')
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code,403)
        self.assertEqual(self.client.get(reverse('health_review',args=[record.pk])).status_code,403)
        self.client.force_login(self.reviewer)
        self.assertEqual(self.client.get(url).status_code,200)
        response=self.client.post(reverse('health_review',args=[record.pk]),{'decision':'verified','note':'Pet and expiry match the vaccination record.'})
        self.assertEqual(response.status_code,302)
        record.refresh_from_db()
        self.assertEqual(record.status,'verified');self.assertEqual(record.verified_by,self.reviewer)
        self.assertIsNotNone(record.verified_at)
        self.assertTrue(AuditEntry.objects.filter(action='health_evidence_verified',object_id=record.pk).exists())
        self.client.post(reverse('health_review',args=[record.pk]),{'decision':'rejected','note':'Duplicate change'})
        record.refresh_from_db();self.assertEqual(record.status,'verified')

    def test_owner_cannot_edit_or_submit_for_another_pet(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('pet_edit',args=[self.pet.pk])).status_code,404)
        self.assertEqual(self.upload().status_code,404)
        self.assertEqual(HealthRecord.objects.count(),0)

    def test_invalid_and_oversized_evidence_is_rejected(self):
        for content in [b'<script>alert(1)</script>',b'%PDF-'+b'A'*(2*1024*1024)+b'%%EOF']:
            response=self.upload(document=SimpleUploadedFile('fake.pdf',content,content_type='application/pdf'))
            self.assertEqual(response.status_code,200)
        self.assertEqual(HealthRecord.objects.count(),0)
        self.assertEqual(HealthEvidence.objects.count(),0)

    def test_staff_cannot_verify_own_pet(self):
        self.owner.is_staff=True;self.owner.save()
        self.upload();record=HealthRecord.objects.get()
        response=self.client.post(reverse('health_review',args=[record.pk]),{'decision':'verified','note':'Own record'})
        self.assertEqual(response.status_code,403)
        record.refresh_from_db();self.assertEqual(record.status,'pending')

    def test_rejected_evidence_cannot_pass_verification_gate(self):
        self.upload();record=HealthRecord.objects.get()
        self.client.force_login(self.reviewer)
        self.client.post(reverse('health_review',args=[record.pk]),{'decision':'rejected','note':'Pet identity does not match.'})
        record.refresh_from_db();self.assertEqual(record.status,'rejected');self.assertIsNone(record.verified_by)

    def test_passport_edit_validates_routine_and_contacts(self):
        url=reverse('pet_edit',args=[self.pet.pk])
        data={'name':'Uno','species':'dog','weight':'15','routine_1_kind':'Breakfast','routine_1_time':'08:00',
              'emergency_name':'Parent','emergency_phone':'+91 99999 12345','care_notes':'Sensitive stomach'}
        self.assertEqual(self.client.post(url,data).status_code,302)
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.routine,[{'kind':'Breakfast','time':'08:00'}])
        self.assertEqual(self.pet.emergency['emergency_phone'],'+91 99999 12345')
        self.assertEqual(self.pet.health['care_notes'],'Sensitive stomach')
        bad={**data,'routine_1_time':'','emergency_phone':'not a phone','weight':'-1'}
        self.assertEqual(self.client.post(url,bad).status_code,200)
        self.pet.refresh_from_db();self.assertEqual(self.pet.weight,15)
