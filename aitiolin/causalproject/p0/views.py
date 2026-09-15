from __future__ import annotations
import csv
import hashlib
import io
import json
import uuid
from datetime import timedelta
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser

from causal_app.models import CausalEdge, CausalGraph, Variable
from .core import LIMITATIONS, contained_path, json_ready, make_bundle
from .guard import reply, request_payload
from .models import Artifact, GraphOwnership, RunRecord, Workspace
from .service import WorkspaceError, delete_workspace, owned_graph, remember_file


def manifest():
    root = Path(settings.BASE_DIR).parent
    document = json.loads((root / "examples/manifest.json").read_text(encoding="utf-8"))
    return document["samples"]


def parse_csv(content):
    if len(content) > int(getattr(settings, "P0_MAX_UPLOAD_BYTES", 10 * 1024 * 1024)):
        raise WorkspaceError("CSV exceeds the configured size limit.", 413)
    try:
        text = content.decode("utf-8-sig")
        header = next(csv.reader(io.StringIO(text)))
        if not 2 <= len(header) <= 250 or len(set(header)) != len(header):
            raise WorkspaceError("CSV needs 2–250 uniquely named columns.")
        if any(not name.strip() or len(name) > 100 for name in header):
            raise WorkspaceError("Column names must be non-empty and at most 100 characters.")
        frame = pd.read_csv(io.StringIO(text), nrows=100001)
    except (UnicodeDecodeError, StopIteration, pd.errors.ParserError, pd.errors.EmptyDataError):
        raise WorkspaceError("Upload a well-formed UTF-8 CSV.") from None
    if frame.empty or len(frame) > 100000:
        raise WorkspaceError("CSV must contain 1–100,000 observations.")
    return frame


def create_graph(request, content, title, sample=None):
    frame = parse_csv(content)
    workspace = request.p0_workspace
    if workspace.graphs.count() >= int(getattr(settings, "P0_MAX_GRAPHS", 10)):
        raise WorkspaceError("Session dataset limit reached. Delete session data before loading more.", 429)
    storage, storage_name = None, None
    try:
        with transaction.atomic():
            graph = CausalGraph.objects.create(name=title[:100])
            request.p0_graph = graph
            GraphOwnership.objects.create(graph=graph, workspace=workspace,
                                          sample_id=(sample or {}).get("id", ""))
            graph.data_file.save(f"p0/{uuid.uuid4().hex}.csv", ContentFile(content), save=True)
            storage, storage_name = graph.data_file.storage, graph.data_file.name
            remember_file(workspace, graph, storage_name)
            Variable.objects.bulk_create([Variable(graph=graph, name=str(name)) for name in frame.columns])
            variables_by_name = {v.name: v for v in graph.variables.all()}
            if sample:
                required = {name for pair in sample["edges"] for name in pair}
                if not required.issubset(variables_by_name):
                    raise WorkspaceError("The sample schema no longer matches its manifest.", 409)
                for source, target in sample["edges"]:
                    CausalEdge.objects.create(graph=graph, source=variables_by_name[source],
                                             target=variables_by_name[target], directed=True)
                graph.node_positions = {name: {"x": 120 + i % 3 * 220, "y": 100 + i // 3 * 180}
                                        for i, name in enumerate(sorted(required))}
                graph.save(update_fields=["node_positions"])
            payload = {"graph_id": graph.pk, "graph_name": graph.name,
                "variables": [{"id": v.pk, "name": v.name} for v in graph.variables.order_by("id")],
                "preview": json_ready(frame.head(3).to_dict(orient="records"))}
            if sample:
                payload["sample"] = {k: v for k, v in sample.items() if k not in ("file", "git_blob_sha1")}
                payload["treatment_id"] = variables_by_name[sample["treatment"]].pk
                payload["outcome_id"] = variables_by_name[sample["outcome"]].pk
                payload["method_name"] = sample["method_name"]
        return payload
    except Exception:
        if storage is not None and storage_name:
            storage.delete(storage_name)
        raise


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def upload(request):
    file = request.FILES.get("file")
    if file is None or not file.name.lower().endswith(".csv"):
        raise WorkspaceError("Provide a CSV file in the file field.")
    if file.size > int(getattr(settings, "P0_MAX_UPLOAD_BYTES", 10 * 1024 * 1024)):
        raise WorkspaceError("CSV exceeds the size limit.", 413)
    # Guard context tracks the underlying HttpRequest; DRF delegates attributes to it.
    raw = request._request
    return reply(create_graph(raw, file.read(), "Uploaded dataset"))


@api_view(["GET"])
def variables(request):
    names = Variable.objects.filter(graph__p0_owner__workspace=request.p0_workspace).values_list("name", flat=True).distinct()
    return reply(list(names))


@api_view(["GET"])
def samples(request):
    return reply({"samples": [{k: v for k, v in item.items() if k not in ("file", "git_blob_sha1", "edges")}
                               for item in manifest()]})


@api_view(["POST"])
def load_sample(request, sample_id):
    sample = next((s for s in manifest() if s["id"] == sample_id), None)
    if sample is None:
        raise WorkspaceError("Unknown sample.", 404)
    path = contained_path(Path(settings.BASE_DIR).parent, sample["file"])
    if not path.is_file():
        raise WorkspaceError("Sample file is not installed on this server.", 503)
    # The manifest stores git blob SHAs, which git computes over LF-normalised content.
    # A Windows checkout has CRLF in the working tree, so normalise before hashing and
    # store the normalised bytes, keeping loaded samples identical across platforms.
    content = path.read_bytes().replace(b"\r\n", b"\n")
    blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
    if blob != sample["git_blob_sha1"]:
        raise WorkspaceError("Sample has changed; review and update its manifest before use.", 409)
    return reply(create_graph(request._request, content, sample["title"], sample))


@api_view(["GET", "PATCH"])
def session_info(request):
    workspace = request.p0_workspace
    if request.method == "PATCH":
        hours = request.data.get("retention_hours")
        if isinstance(hours, bool) or hours not in (1, 6, 24):
            raise WorkspaceError("Choose a retention period of 1, 6 or 24 hours.")
        maximum = workspace.created_at + timedelta(hours=max(1, min(72, int(getattr(settings, "P0_RETENTION_HOURS", 24)))))
        workspace.expires_at = min(timezone.now() + timedelta(hours=hours), maximum)
        workspace.save(update_fields=["expires_at"])
    return reply({"expires_at": workspace.expires_at.isoformat(),
        "llm_available": bool(settings.OPENAI_API_KEY),
        "saved_graphs": workspace.graphs.count(), "saved_runs": workspace.runs.count(),
        "data_flow": {
            "browser": "The session bearer token is held in this tab's sessionStorage. The graph and visible results are in browser memory; saved graph state is stored by the server.",
            "server": "CSV uploads, cleaned copies, graph state, recorded analysis results and temporary LLM approval hashes are stored by the Django server. Local only when that server runs on your own computer.",
            "llm": "Off by default. Reviewed calls send variable names and supplied model context; the app does not attach dataset rows or profiling statistics. Names and supplied context can still contain sensitive information. Every outgoing payload must be previewed and approved.",
            "retention": "Access expires at the displayed time. Physical removal requires the scheduled purge_p0_sessions command; closing the tab alone does not delete server files.",
            "deletion_limits": "Deletion does not remove downloaded exports, host access logs/backups, or information already sent to a provider.",
        }})


@api_view(["DELETE"])
def delete_session(request):
    return reply(delete_workspace(request.p0_workspace))


@api_view(["GET"])
def runs(request, graph_id):
    graph = owned_graph(request.p0_workspace, graph_id)
    records = RunRecord.objects.filter(workspace=request.p0_workspace, graph=graph).order_by("-created_at")[:50]
    return reply({"runs": [{"id": str(r.pk), "operation": r.operation,
                            "created_at": r.created_at.isoformat(), "analysis_key": r.analysis_key,
                            "status": r.payload.get("status", "unknown")} for r in records]})


@api_view(["GET"])
def bundle(request, run_id):
    if request.query_params.get("file_format", "zip") not in {"zip", "json"}:
        raise WorkspaceError("file_format must be zip or json.")
    record = RunRecord.objects.filter(pk=run_id, workspace=request.p0_workspace).first()
    if record is None:
        raise WorkspaceError("Run not found in this session.", 404)
    compatible = RunRecord.objects.filter(workspace=request.p0_workspace, graph=record.graph,
        analysis_key=record.analysis_key, created_at__lte=record.created_at).order_by("created_at")
    stages = [{"id": str(r.pk), "operation": r.operation, **r.payload} for r in compatible]
    root = {"id": str(record.pk), "operation": record.operation, "analysis_key": record.analysis_key,
            **record.payload}
    if request.query_params.get("file_format", "zip") == "json":
        from .core import canonical_bytes, redact, SCHEMA_VERSION
        body = canonical_bytes(redact({**root, "stages": stages, "schema_version": SCHEMA_VERSION,
                                      "raw_data_included": False, "limitations": LIMITATIONS}))
        response = HttpResponse(body, content_type="application/json")
        suffix = "json"
    else:
        response = HttpResponse(make_bundle(root, stages), content_type="application/zip")
        suffix = "zip"
    response["Content-Disposition"] = f'attachment; filename="aitiolin-run-{record.pk}.{suffix}"'
    return response


@api_view(["GET"])
def graph_image(request, graph_id):
    graph = owned_graph(request.p0_workspace, graph_id)
    artifact = Artifact.objects.filter(workspace=request.p0_workspace, graph=graph,
                                       storage_name__startswith="causal_graphs/").order_by("-id").first()
    if not artifact:
        raise WorkspaceError("Image not found.", 404)
    path = contained_path(Path(settings.MEDIA_ROOT), artifact.storage_name)
    if not path.is_file() or path.suffix.lower() != ".png":
        raise WorkspaceError("Image not found.", 404)
    return FileResponse(path.open("rb"), content_type="image/png")
