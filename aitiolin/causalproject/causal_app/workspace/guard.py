"""Wrap existing API views: session ownership, serialisation and run capture."""
import json
from contextlib import nullcontext
from functools import wraps
from django.conf import settings
from django.http import JsonResponse
from django.urls import URLPattern
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .core import parse_seed
from .llm import ConsentRequired
from .runtime import current_request, seeded
from .service import (WorkspaceError, owned_graph, query_for, release, reserve,
                      save_record, snapshot, track_files, workspace_for)

RECORDED = {"causal_inference", "assess_query", "assess_query_alias_hyphen",
            "assess_query_alias_no_slash", "assess_query_alias_hyphen_no_slash",
            "robustness_dashboard", "agent_compare_models", "agent_estimate_plan",
            "time_series_analysis", "what_if_analysis", "root_cause_analysis"}
# Record-keeping routes never touch the RNG. Seeding them would only make every session queue
# behind whichever analysis currently holds the process-wide RNG lock.
UNSEEDED = {"upload_csv", "variables", "save_graph", "graph_details"}


def reply(data, status=200):
    response = JsonResponse(data, safe=isinstance(data, dict), status=status,
                            json_dumps_params={"allow_nan": False})
    response.data = data  # Preserve DRF test-client response ergonomics for these wrapped views.
    response["Cache-Control"] = "no-store"
    return response


def request_payload(request):
    if request.content_type == "application/json":
        try:
            payload = json.loads(request.body or b"{}")
        except (ValueError, UnicodeDecodeError):
            raise WorkspaceError("Invalid JSON.") from None
        if not isinstance(payload, dict):
            raise WorkspaceError("Expected a JSON object.")
        return payload
    return request.POST.dict() if request.method != "GET" else request.GET.dict()


def guard(view, operation):
    @csrf_exempt
    @wraps(view)
    def secured(request, *args, **kwargs):
        if request.method == "OPTIONS":
            return view(request, *args, **kwargs)
        workspace, context_token, reserved = None, None, False
        graph, before = None, None
        try:
            is_delete = operation == "workspace_delete"
            workspace = workspace_for(request, permit_expired_delete=is_delete)
            reserve(workspace)
            reserved = True
            request.workspace = workspace
            request.workspace_operation = operation
            context_token = current_request.set(request)
            payload = request_payload(request)
            try:
                seed = parse_seed(request.headers.get("X-Aitiolin-Seed", 42))
            except ValueError:
                raise WorkspaceError("Analysis seed must be an integer between 0 and 4294967295 "
                                     "(X-Aitiolin-Seed header).", 400, "invalid_seed") from None
            request.workspace_seed = seed
            graph_id = kwargs.get("graph_id", payload.get("graph_id"))
            if graph_id not in (None, ""):
                graph = owned_graph(workspace, graph_id)
                request.workspace_graph = graph
                track_files(workspace, graph)
            if not operation.startswith("workspace_") and operation not in {"upload_csv", "variables", "openai_suggest_edges"} and graph is None:
                raise WorkspaceError("Upload or load a sample first; graph_id is required.")
            if operation.startswith("openai_") and request.headers.get("X-Aitiolin-LLM-Mode", "off") != "review":
                raise WorkspaceError("Enable reviewed LLM requests in the privacy panel before using Graph Copilot.", 403)
            if graph is not None and operation in RECORDED:
                before = snapshot(graph)
            started_at = timezone.now()
            rng = nullcontext() if operation.startswith("workspace_") or operation in UNSEEDED else seeded(seed)
            with rng:
                response = view(request, *args, **kwargs)
            data = getattr(response, "data", None)
            if graph is not None:
                track_files(workspace, graph, data)
                if isinstance(data, dict) and data.get("graph_image"):
                    data["graph_image"] = f"/api/workspace/graphs/{graph.pk}/image/"
                if operation == "agent_apply_cleaning" and response.status_code < 400:
                    owner = graph.ownership
                    from .core import redact
                    owner.cleaning_history = [*owner.cleaning_history,
                        {"at": timezone.now().isoformat(), "request": redact(payload), "result": redact(data)}]
                    owner.save(update_fields=["cleaning_history"])
            if before is not None:
                record = save_record(workspace, graph, operation, before, payload,
                                     data or {"http_status": response.status_code}, seed, started_at, response.status_code)
                if isinstance(data, dict):
                    data["run_id"] = str(record.pk)
                    data["analysis_key"] = record.analysis_key
                response["X-Aitiolin-Run"] = str(record.pk)
            response["Cache-Control"] = "no-store"
            return response
        except ConsentRequired as exc:
            return reply({"error": str(exc), "code": "llm_review_required", "review": exc.preview}, 409)
        except WorkspaceError as exc:
            return reply({"error": str(exc), "code": exc.code}, exc.status)
        except ValueError:
            return reply({"error": "Invalid request value.", "code": "invalid_request"}, 400)
        finally:
            if context_token is not None:
                current_request.reset(context_token)
            if reserved and workspace is not None:
                release(workspace)
    return secured


def protect_urlpatterns(patterns):
    from .views import upload, variables
    for pattern in patterns:
        if not isinstance(pattern, URLPattern):
            raise RuntimeError("Review newly nested API routes before enabling them.")
        callback = upload if pattern.name == "upload_csv" else variables if pattern.name == "variables" else pattern.callback
        pattern.callback = guard(callback, pattern.name)
    return patterns


class PrivateMediaMiddleware:
    """Uploads are never public URLs. Reverse proxies must follow the same rule."""
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        if request.path.startswith(settings.MEDIA_URL):
            return reply({"error": "Not found."}, 404)
        return self.get_response(request)
