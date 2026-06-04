from django.core.management.base import BaseCommand

from catalog.views import purge_stale_requests


class Command(BaseCommand):
    help = "Delete fulfilled/closed movie requests older than the retention window."

    def handle(self, *args, **options):
        deleted, _ = purge_stale_requests()
        self.stdout.write(self.style.SUCCESS(f"Purged {deleted} stale movie request(s)."))
