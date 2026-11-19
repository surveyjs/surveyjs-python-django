"""Demo only: python manage.py prune_sandboxes removes the visitor sandboxes (and relay snapshots) unused for 24
hours. In demo mode the app runs the same function hourly (config/lifespan.py); a host with cron may run this
instead."""

from django.core.management.base import BaseCommand

from demo.sandbox import prune


class Command(BaseCommand):
    help = "Remove the demo's visitor sandboxes unused for 24 hours."

    def handle(self, *args, **options):
        removed = prune()
        self.stdout.write(f"Removed {removed} visitor sandbox{'es' if removed != 1 else ''} unused for 24 hours.")
