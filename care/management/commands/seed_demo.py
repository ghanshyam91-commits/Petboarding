import os
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from care.models import *
from care.services.stays import reserve
class Command(BaseCommand):
    help='Create explicitly fictional demonstration data. Local development only.'
    def handle(self,*args,**kwargs):
        if not settings.DEBUG: raise CommandError('Demo data is forbidden outside DEBUG mode.')
        password=os.environ.get('DEMO_PASSWORD')
        if not password or len(password)<12: raise CommandError('Set DEMO_PASSWORD to a password of at least 12 characters.')
        if User.objects.filter(username='parent_demo').exists(): raise CommandError('Demo data already exists.')
        parent=User.objects.create_user('parent_demo',password=password,first_name='Ghanshyam')
        provider=User.objects.create_user('provider_demo',password=password,first_name='Care team')
        reviewer=User.objects.create_user('trust_demo',password=password,is_staff=True)
        cities=['Bengaluru','Delhi NCR','Mumbai','Pune','Hyderabad','Chennai','Kolkata']
        for city in cities: Jurisdiction.objects.get_or_create(city=city,defaults={'state':'Demo — verify local authority'})
        city=Jurisdiction.objects.get(city='Bengaluru')
        ComplianceRule.objects.create(jurisdiction=city,version=1,reviewed=True,home_boarding_allowed=False,required_credentials=['identity','premises','training'],required_vaccines=['rabies'])
        pet=Pet.objects.create(owner=parent,name='Uno',species='dog',breed='Pomeranian',weight=15,compatible_dogs=False,compatible_cats=False,routine=[{'kind':'Breakfast','time':'08:00'},{'kind':'Evening walk','time':'18:00'}],emergency={'contact':'Demo only — configure real contact','treatment_authorized':False})
        HealthRecord.objects.create(pet=pet,kind='rabies',status='verified',expires=timezone.localdate()+timedelta(days=365),verified_by=reviewer,verified_at=timezone.now())
        for name,locality,price in [('The Green House · Demo','Whitefield',140000),('Little Sanctuary · Demo','Indiranagar',180000),('Quiet Tails · Demo','Sarjapur',120000)]:
            p=Provider.objects.create(owner=provider,name=name,jurisdiction=city,kind='facility',locality=locality,species=['dog','cat'],capacity=8,medication_competent=True,overnight_supervision=True,ac=True,nightly_paise=price,care_description='Fictional demo facility. Individual care routines, calm rest areas and attributed daily updates.')
            for category in ['identity','premises','training']:
                Credential.objects.create(provider=p,category=category,status='verified',expires=timezone.localdate()+timedelta(days=365),verified_by=reviewer,verified_at=timezone.now(),issuing_authority='DEMO — not a real verification')
        p=Provider.objects.first()
        b=reserve(parent,p.pk,[pet.pk],timezone.localdate(),timezone.localdate()+timedelta(days=3))
        b.status='active';b.save()
        for i,(kind,notes) in enumerate([('Breakfast completed','Finished the usual portion. Fresh water refilled.'),('Morning walk','A relaxed walk with plenty of sniffing stops.'),('Rest & wellbeing check','Settled comfortably in the quiet rest area.')]):
            CareEvent.objects.create(booking=b,pet=pet,actor=provider,kind=kind,notes=notes)
        for kind,hours,critical in [('Evening walk',2,False),('Dinner',3,False),('Wellbeing check',4,False)]:
            CareTask.objects.create(booking=b,pet=pet,kind=kind,due_at=timezone.now()+timedelta(hours=hours),critical=critical)
        self.stdout.write('Created parent_demo, provider_demo, trust_demo. All data is fictional. Use DEMO_PASSWORD to sign in.')
