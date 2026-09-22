from django.core.management.base import BaseCommand
from care.services.stays import escalate_overdue


class Command(BaseCommand):
    help = "Escalate overdue critical care. Run every minute with a scheduler."

    def handle(self, *args, **options):
        self.stdout.write(f"Escalated {escalate_overdue()} critical tasks.")
