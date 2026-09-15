from django.core.files.storage import FileSystemStorage
from .runtime import current_request


class PrivateStorage(FileSystemStorage):
    """Track every Django FileField write, including intermediate cleaned copies."""
    def _save(self, name, content):
        saved = super()._save(name, content)
        request = current_request.get()
        if request is not None and getattr(request, "p0_graph", None) is not None:
            try:
                from .service import remember_file
                remember_file(request.p0_workspace, request.p0_graph, saved)
            except Exception:
                super().delete(saved)
                raise
        return saved
