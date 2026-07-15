

# notifications/management/commands/seed_jobs.py
from django.core.management.base import BaseCommand
from notifications.services import submit_email_job

class Command(BaseCommand):
    def handle(self, *args, **options):
        for i in range(250):
            submit_email_job(recipient=f"neww{i}@example.com", subject="Order Confirmation")
        self.stdout.write(self.style.SUCCESS("Submitted 120 jobs"))