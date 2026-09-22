from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest import skipUnless
from django.test import TransactionTestCase
from django.db import connection, close_old_connections, DatabaseError, transaction
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError
from care.models import *
from care.services.stays import reserve


@skipUnless(
    connection.vendor == "postgresql", "Requires PostgreSQL row locks and triggers"
)
class PostgreSQLGuarantees(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner")
        self.operator = User.objects.create_user("operator")
        j = Jurisdiction.objects.create(city="Test", state="Test")
        ComplianceRule.objects.create(jurisdiction=j, version=1, reviewed=True)
        self.p = Provider.objects.create(
            owner=self.operator,
            name="Test",
            jurisdiction=j,
            kind="facility",
            capacity=1,
            species=["dog"],
        )
        self.pet = Pet.objects.create(owner=self.owner, name="Uno", species="dog")
        self.start = timezone.localdate()
        self.end = self.start + timedelta(days=2)

    def test_two_concurrent_reservations_only_one_succeeds(self):
        def attempt(_):
            close_old_connections()
            try:
                reserve(
                    User.objects.get(pk=self.owner.pk),
                    self.p.pk,
                    [self.pet.pk],
                    self.start,
                    self.end,
                )
                return True
            except ValidationError:
                return False
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, [1, 2]))
        self.assertEqual(sum(results), 1)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(CapacityDay.objects.first().reserved, 1)

    def test_bulk_update_and_delete_are_blocked(self):
        e = AuditEntry.objects.create(
            actor=self.owner, action="test", object_type="test", object_id=1
        )
        with self.assertRaises(DatabaseError), transaction.atomic():
            AuditEntry.objects.filter(pk=e.pk).update(action="tampered")
        with self.assertRaises(DatabaseError), transaction.atomic():
            AuditEntry.objects.filter(pk=e.pk).delete()
