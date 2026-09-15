from django.core.management.base import BaseCommand
from django.utils import timezone
from p0.models import Workspace
from p0.service import WorkspaceError, delete_workspace, reserve, release


class Command(BaseCommand):
    help = "Remove expired prototype sessions and their tracked files. Schedule this command regularly."
    def handle(self, *args, **options):
        deleted = skipped = 0
        # Materialise first: SQLite gives no isolation between a chunked read and the deletes
        # below, so iterating the live cursor can skip expired rows.
        for workspace in list(Workspace.objects.filter(expires_at__lte=timezone.now())):
            reserved = False
            try:
                reserve(workspace)
                reserved = True
                delete_workspace(workspace)
                deleted += 1
            except WorkspaceError:
                skipped += 1
            finally:
                if reserved:
                    release(workspace)
        self.stdout.write(f"Deleted: {deleted}; busy or incomplete: {skipped}")
