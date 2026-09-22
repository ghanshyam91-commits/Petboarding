from datetime import timedelta
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from care.demo import DEMO_GROUP, DEMO_CITY, DEMO_USERS
from care.models import (Jurisdiction, ComplianceRule, Pet, HealthRecord, Provider,
                         Credential, Booking, CareEvent, CareTask, Message, Notification, Review)
from care.services.stays import reserve


class Command(BaseCommand):
    help = 'Create fictional, read-only public demo accounts when explicitly enabled.'

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.ENABLE_DEMO_LOGIN:
            raise CommandError('Set ENABLE_DEMO_LOGIN=true to enable this demonstration.')
        group, _ = Group.objects.get_or_create(name=DEMO_GROUP)
        Group.objects.select_for_update().get(pk=group.pk)
        existing = User.objects.filter(username__in=DEMO_USERS.values())
        if existing.exists():
            if existing.count() != 2 or existing.exclude(groups=group).exists():
                raise CommandError('Demo usernames conflict with existing accounts; no data changed.')
            self.stdout.write('Public demo already exists; no records changed.')
            return
        parent = User.objects.create_user(DEMO_USERS['parent'], first_name='Alex')
        provider = User.objects.create_user(DEMO_USERS['provider'], first_name='Maya', last_name='(Demo caregiver)')
        parent.groups.add(group)
        provider.groups.add(group)
        # These accounts have unusable passwords and no staff/admin privileges.
        city, created = Jurisdiction.objects.get_or_create(city=DEMO_CITY,
            defaults={'state': 'Fictional demonstration only'})
        if not created:
            raise CommandError('Demo jurisdiction already exists; refusing to alter existing records.')
        ComplianceRule.objects.create(jurisdiction=city, version=1, reviewed=True,
            required_credentials=['identity', 'premises', 'training'], required_vaccines=['rabies'])
        today = timezone.localdate()
        pets = []
        for name, species, breed, weight in [('Milo', 'dog', 'Golden Retriever', 24), ('Luna', 'cat', 'Domestic Shorthair', 4)]:
            pet = Pet.objects.create(owner=parent, name=name, species=species, breed=breed,
                weight=weight, compatible_dogs=True, compatible_cats=True,
                routine=[{'kind': 'Breakfast', 'time': '08:00'}, {'kind': 'Playtime', 'time': '17:00'}],
                emergency={'contact': 'Fictional sample — no emergency contact', 'treatment_authorized': False})
            HealthRecord.objects.create(pet=pet, kind='rabies', status='verified',
                expires=today + timedelta(days=365), verified_by=provider, verified_at=timezone.now())
            pets.append(pet)
        facilities = []
        for name, area, price in [('Green House · Demo', 'Whitefield', 140000),
                                  ('Little Sanctuary · Demo', 'Indiranagar', 180000),
                                  ('Quiet Tails · Demo', 'Sarjapur', 120000)]:
            facility = Provider.objects.create(owner=provider, name=name, jurisdiction=city,
                kind='facility', locality=area, species=['dog', 'cat'], capacity=12,
                medication_competent=True, overnight_supervision=True, ac=True,
                nightly_paise=price, care_description='Fictional sample boarding with calm rest areas and individual care routines.')
            for category in ['identity', 'premises', 'training']:
                Credential.objects.create(provider=facility, category=category, status='verified',
                    expires=today + timedelta(days=365), verified_by=provider,
                    verified_at=timezone.now(), issuing_authority='DEMO — not a real verification')
            facilities.append(facility)
        active = reserve(parent, facilities[0].pk, [pets[0].pk], today, today + timedelta(days=3))
        active.status = 'active'
        active.save(update_fields=['status'])
        reserve(parent, facilities[1].pk, [pets[1].pk], today + timedelta(days=7), today + timedelta(days=9))
        completed = Booking.objects.create(owner=parent, provider=facilities[2],
            starts=today-timedelta(days=10), ends=today-timedelta(days=8), status='completed',
            quote={'nights': 2, 'base_paise': 240000, 'additional_paise': 0, 'fees_paise': 0, 'total_paise': 240000})
        completed.pets.add(pets[0])
        Review.objects.create(booking=completed, ratings={'care': 5}, text='Sample review: thoughtful care and regular updates.', matched_listing=True)
        for kind, notes in [('Breakfast enjoyed', 'Milo finished his usual portion. Fresh water refilled.'),
                            ('Morning walk', 'A relaxed garden walk with plenty of sniffing stops.'),
                            ('Rest and wellbeing', 'Settled comfortably in the quiet rest area.'),
                            ('Playtime', 'Enjoyed a short supervised game with his favourite ball.')]:
            CareEvent.objects.create(booking=active, pet=pets[0], actor=provider, kind=kind, notes=notes)
        for kind, hours in [('Evening walk', 2), ('Dinner', 3), ('Wellbeing check', 4)]:
            CareTask.objects.create(booking=active, pet=pets[0], kind=kind, due_at=timezone.now()+timedelta(hours=hours))
        for sender, message in [(parent, 'Sample message: Milo loves a quiet spot after his walk.'),
                                (provider, 'Sample update: He has settled in well and enjoyed breakfast.')]:
            Message.objects.create(booking=active, sender=sender, text=message)
        Notification.objects.create(user=parent, booking=active,
            message='Demo update: Milo has settled in and his care timeline is ready.', status='demo')
        self.stdout.write('Created two read-only demo accounts, two pets, three facilities and three stays.')
