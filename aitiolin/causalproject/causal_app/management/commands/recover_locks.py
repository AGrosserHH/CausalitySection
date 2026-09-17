"""Explicit crash recovery. Never run while any web worker can still process requests."""
from django.core.management.base import BaseCommand, CommandError
from causal_app.workspace.models import Workspace


class Command(BaseCommand):
    help = "Clear abandoned workspace reservations ONLY after all application workers have stopped."
    def add_arguments(self, parser):
        parser.add_argument("--workers-stopped", action="store_true",
                            help="Affirm that every application worker has been stopped.")
    def handle(self, *args, **options):
        if not options["workers_stopped"]:
            raise CommandError("Stop all application workers and pass --workers-stopped. Do not recover locks while a request may still write data.")
        count = Workspace.objects.filter(busy=True).update(busy=False)
        self.stdout.write(f"Cleared {count} abandoned reservations. Deletion locks remain intact.")
