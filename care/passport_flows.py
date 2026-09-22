import hashlib
import re
from datetime import date
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from .forms import PetForm
from .models import AuditEntry, HealthEvidence, HealthRecord, Pet


class PassportForm(PetForm):
    microchip = forms.CharField(max_length=80, required=False)
    care_notes = forms.CharField(label='Health and care notes', widget=forms.Textarea, required=False, max_length=2000)
    emergency_name = forms.CharField(label='Emergency contact name', max_length=100, required=False)
    emergency_phone = forms.CharField(label='Emergency phone', max_length=30, required=False)
    vet_name = forms.CharField(label='Veterinarian / clinic', max_length=120, required=False)
    vet_phone = forms.CharField(label='Veterinarian phone', max_length=30, required=False)
    routine_1_kind = forms.CharField(label='Daily care task 1', max_length=50, required=False)
    routine_1_time = forms.TimeField(label='Task 1 time', widget=forms.TimeInput(attrs={'type':'time'}), required=False)
    routine_2_kind = forms.CharField(label='Daily care task 2', max_length=50, required=False)
    routine_2_time = forms.TimeField(label='Task 2 time', widget=forms.TimeInput(attrs={'type':'time'}), required=False)
    routine_3_kind = forms.CharField(label='Daily care task 3', max_length=50, required=False)
    routine_3_time = forms.TimeField(label='Task 3 time', widget=forms.TimeInput(attrs={'type':'time'}), required=False)

    class Meta(PetForm.Meta):
        fields = PetForm.Meta.fields + ['microchip']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pet = self.instance
        if pet.pk:
            self.initial['care_notes'] = pet.health.get('care_notes', '')
            for field in ['emergency_name','emergency_phone','vet_name','vet_phone']:
                self.initial[field] = pet.emergency.get(field, '')
            for i, item in enumerate(pet.routine[:3], 1):
                self.initial[f'routine_{i}_kind'] = item.get('kind', '')
                self.initial[f'routine_{i}_time'] = item.get('time', '')

    def clean(self):
        data = super().clean()
        if data.get('weight') is not None and data['weight'] <= 0:
            self.add_error('weight','Enter a weight greater than zero.')
        if data.get('birth_date') and data['birth_date'] > timezone.localdate():
            self.add_error('birth_date','Birth date cannot be in the future.')
        for field in ['emergency_phone','vet_phone']:
            value=data.get(field,'')
            if value and (not re.fullmatch(r'[+\d ()-]+',value) or not 7 <= len(re.sub(r'\D','',value)) <= 15):
                self.add_error(field,'Enter a phone number with 7–15 digits.')
        for name, phone in [('emergency_name','emergency_phone'),('vet_name','vet_phone')]:
            if bool(data.get(name)) != bool(data.get(phone)):
                self.add_error(name,'Add both a name and phone number, or leave both blank.')
        for i in range(1,4):
            if bool(data.get(f'routine_{i}_kind')) != bool(data.get(f'routine_{i}_time')):
                self.add_error(f'routine_{i}_kind','Add both the task and its daily time.')
        return data

    def save(self, commit=True):
        pet=super().save(commit=False)
        pet.health={**pet.health, 'care_notes':self.cleaned_data['care_notes']}
        pet.emergency={**pet.emergency, **{field:self.cleaned_data[field] for field in ['emergency_name','emergency_phone','vet_name','vet_phone']}}
        # Keep additional existing routine entries; active bookings retain their snapshot.
        routine=[]
        for i in range(1,4):
            if self.cleaned_data.get(f'routine_{i}_kind'):
                old=pet.routine[i-1] if len(pet.routine)>=i else {}
                routine.append({**old,'kind':self.cleaned_data[f'routine_{i}_kind'],'time':self.cleaned_data[f'routine_{i}_time'].strftime('%H:%M')})
        pet.routine=routine+pet.routine[3:]
        if commit:pet.save()
        return pet


class HealthSubmissionForm(forms.Form):
    kind=forms.CharField(label='Vaccination or record name', max_length=80, help_text='For example: rabies')
    expires=forms.DateField(label='Valid until', widget=forms.DateInput(attrs={'type':'date'}))
    document=forms.FileField(label='Vaccination evidence', help_text='PDF, JPEG or PNG. Maximum 2 MB.')

    def clean_kind(self):
        return self.cleaned_data['kind'].strip().lower()

    def clean_expires(self):
        value=self.cleaned_data['expires']
        if value < timezone.localdate():raise forms.ValidationError('Submit a record that has not expired.')
        return value

    def clean_document(self):
        upload=self.cleaned_data['document']
        if upload.size>2*1024*1024:raise forms.ValidationError('The document must be 2 MB or smaller.')
        content=upload.read(2*1024*1024+1)
        if len(content)>2*1024*1024:raise forms.ValidationError('The document must be 2 MB or smaller.')
        if content.startswith(b'%PDF-') and b'%%EOF' in content[-1024:]:
            mime,extension='application/pdf','pdf'
        elif content.startswith(b'\x89PNG\r\n\x1a\n') and content.endswith(b'IEND\xaeB`\x82'):
            mime,extension='image/png','png'
        elif content.startswith(b'\xff\xd8\xff') and content.endswith(b'\xff\xd9'):
            mime,extension='image/jpeg','jpg'
        else:raise forms.ValidationError('Choose a valid PDF, JPEG or PNG document.')
        return {'content':content,'content_type':mime,'extension':extension,'sha256':hashlib.sha256(content).hexdigest()}


@login_required
@require_http_methods(['GET','POST'])
def pet_edit(request,pk):
    pet=get_object_or_404(Pet,pk=pk,owner=request.user)
    form=PassportForm(request.POST or None,instance=pet)
    if request.method=='POST' and form.is_valid():
        form.save()
        messages.success(request,'Care passport updated. Existing stay care plans remain unchanged.')
        return redirect('profile')
    return render(request,'care/pet_edit.html',{'form':form,'pet':pet,'nav':'Profile'})


@login_required
@require_http_methods(['GET','POST'])
def health_submit(request,pk):
    pet=get_object_or_404(Pet,pk=pk,owner=request.user)
    form=HealthSubmissionForm(request.POST or None,request.FILES or None)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            record=HealthRecord.objects.create(pet=pet,kind=form.cleaned_data['kind'],expires=form.cleaned_data['expires'],status='pending')
            HealthEvidence.objects.create(record=record,uploaded_by=request.user,**form.cleaned_data['document'])
            AuditEntry.objects.create(actor=request.user,action='health_evidence_submitted',object_type='healthrecord',object_id=record.pk)
        messages.success(request,'Health evidence submitted for review. It becomes eligible only after verification.')
        return redirect('profile')
    return render(request,'care/health_submit.html',{'form':form,'pet':pet,'nav':'Profile'})


@login_required
@require_http_methods(['GET'])
def health_document(request,pk):
    evidence=get_object_or_404(HealthEvidence.objects.select_related('record__pet'),record_id=pk)
    if evidence.record.pet.owner_id!=request.user.pk and not request.user.is_staff:raise PermissionDenied
    response=HttpResponse(bytes(evidence.content),content_type=evidence.content_type)
    response['Content-Disposition']=f'attachment; filename="health-record-{pk}.{evidence.extension}"'
    response['Cache-Control']='private, no-store'
    response['X-Content-Type-Options']='nosniff'
    return response


class HealthReviewForm(forms.Form):
    decision=forms.ChoiceField(choices=[('verified','Verify evidence'),('rejected','Reject evidence')])
    note=forms.CharField(label='Review notes',widget=forms.Textarea,max_length=2000,required=True)


def health_review_queue():
    return HealthRecord.objects.filter(status='pending',evidence__isnull=False).select_related('pet','evidence').order_by('pk')


@login_required
@require_http_methods(['GET','POST'])
def health_review(request,pk):
    if not request.user.is_staff:raise PermissionDenied
    record=get_object_or_404(HealthRecord.objects.select_related('pet','evidence'),pk=pk,evidence__isnull=False)
    if record.pet.owner_id==request.user.pk:raise PermissionDenied('A different reviewer must assess your pet’s health evidence.')
    form=HealthReviewForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            record=HealthRecord.objects.select_for_update().get(pk=pk)
            if record.status!='pending':
                messages.info(request,'This evidence has already been reviewed.')
                return redirect('health_review',pk=pk)
            if form.cleaned_data['decision']=='verified' and (not record.expires or record.expires<timezone.localdate()):
                form.add_error('decision','Expired evidence cannot be verified.')
            else:
                record.status=form.cleaned_data['decision']
                record.verified_by=request.user if record.status=='verified' else None
                record.verified_at=timezone.now() if record.status=='verified' else None
                record.save(update_fields=['status','verified_by','verified_at'])
                HealthEvidence.objects.filter(record=record).update(reviewer_note=form.cleaned_data['note'])
                AuditEntry.objects.create(actor=request.user,action='health_evidence_'+record.status,object_type='healthrecord',object_id=pk,detail={'note':form.cleaned_data['note']})
                messages.success(request,'Health evidence review saved.')
                return redirect('health_review',pk=pk)
    return render(request,'care/health_review.html',{'record':record,'form':form,'nav':'Trust'})
