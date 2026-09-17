"""One-use, session-bound approval for the exact outgoing completion payload."""
from datetime import timedelta
from django.utils import timezone
from django.core.exceptions import ValidationError
from .core import digest, json_ready
from .models import LLMPermit
from .runtime import current_request
from .service import WorkspaceError


class ConsentRequired(Exception):
    def __init__(self, preview):
        super().__init__("Review the outgoing LLM request before sending it.")
        self.preview = preview


def reviewed_completion(client, **kwargs):
    request = current_request.get()
    if request is None or not hasattr(request, "workspace"):
        raise WorkspaceError("LLM calls require a private workspace and explicit payload review.", 403)
    if request.headers.get("X-Aitiolin-LLM-Mode", "off") != "review":
        raise WorkspaceError("LLM access is disabled. Enable reviewed LLM requests in the privacy panel.", 403)
    kwargs["store"] = False
    outgoing = json_ready(kwargs)
    payload_hash = digest(outgoing)
    token = request.headers.get("X-Aitiolin-LLM-Approval", "")
    permit = None
    if token:
        try:
            permit = LLMPermit.objects.filter(pk=token, workspace=request.workspace,
                operation=request.workspace_operation, payload_hash=payload_hash, used=False,
                expires_at__gt=timezone.now()).first()
        except (ValueError, TypeError, ValidationError):
            permit = None
    if permit and LLMPermit.objects.filter(pk=permit.pk, used=False).update(used=True):
        return client.chat.completions.create(**kwargs)
    LLMPermit.objects.filter(workspace=request.workspace, expires_at__lte=timezone.now()).delete()
    permit = LLMPermit.objects.create(workspace=request.workspace, operation=request.workspace_operation,
        payload_hash=payload_hash, expires_at=timezone.now() + timedelta(minutes=2))
    raise ConsentRequired({"approval_token": str(permit.pk), "payload_sha256": payload_hash,
        "provider": "OpenAI API", "payload": outgoing, "expires_in_seconds": 120,
        "policy": "Variable names and supplied modeling context only; the app does not attach dataset rows or profiling statistics. Context and variable names may themselves be sensitive.",
        "provider_notice": "store=false is requested. Provider processing, security logs and retention are governed by your provider account terms; this is not a zero-retention guarantee."})
