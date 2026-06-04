from django.core.management.base import BaseCommand

from parties.services import prune_parties


class Command(BaseCommand):
    help = "End abandoned active parties and delete long-ended ones."

    def add_arguments(self, parser):
        parser.add_argument("--stale-hours", type=int, default=None,
                            help="End active parties idle for this many hours (default: settings.PARTY_STALE_HOURS or 8).")
        parser.add_argument("--keep-days", type=int, default=None,
                            help="Delete parties ended more than this many days ago (default: settings.PARTY_KEEP_DAYS or 7).")

    def handle(self, *args, **options):
        ended, deleted = prune_parties(
            stale_hours=options["stale_hours"], keep_days=options["keep_days"]
        )
        self.stdout.write(self.style.SUCCESS(
            f"Ended {ended} abandoned part(ies); deleted {deleted} old ended part(ies)."
        ))
