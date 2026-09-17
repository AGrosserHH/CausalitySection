from __future__ import annotations

import importlib.metadata
import json
import platform
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from causal_app.models import CausalGraph
from .core import analysis_key, contained_path, digest, file_digest, json_ready, redact, token_digest
from .models import Artifact, GraphOwnership, LLMPermit, RunRecord, Workspace


class WorkspaceError(Exception):
    def __init__(self, message, status=400, code="invalid_request"):
        super().__init__(message)
        self.status, self.code = status, code


def workspace_for(request, create=True, permit_expired_delete=False):
    try:
        key = token_digest(request.headers.get("X-Aitiolin-Session", ""))
    except ValueError as exc:
        raise WorkspaceError(str(exc), 401, "session_required") from exc
    workspace = Workspace.objects.filter(pk=key).first()
    if workspace is None and create:
        # Any well-formed token can open a session, so bound how many unexpired ones may exist.
        limit = max(1, int(getattr(settings, "P0_MAX_ACTIVE_WORKSPACES", 500)))
        if Workspace.objects.filter(expires_at__gt=timezone.now()).count() >= limit:
            raise WorkspaceError("This server has reached its limit of active sessions. Wait for sessions "
                                 "to expire or run purge_p0_sessions.", 503, "session_limit")
        hours = max(1, min(int(getattr(settings, "P0_RETENTION_HOURS", 24)), 72))
        workspace, _ = Workspace.objects.get_or_create(
            token_hash=key, defaults={"expires_at": timezone.now() + timedelta(hours=hours)})
    if workspace is None:
        raise WorkspaceError("Session not found.", 404, "session_not_found")
    if not permit_expired_delete and (workspace.deleting or workspace.expires_at <= timezone.now()):
        raise WorkspaceError("Session expired or is being deleted. Delete its data or start a new session.",
                             410, "session_expired")
    return workspace


def owned_graph(workspace, graph_id):
    try:
        if isinstance(graph_id, bool):
            raise ValueError
        pk = int(graph_id)
    except (ValueError, TypeError):
        raise WorkspaceError("A valid graph_id is required.") from None
    ownership = GraphOwnership.objects.select_related("graph").filter(
        workspace=workspace, graph_id=pk).first()
    if ownership is None:
        # Do not reveal whether another session owns a guessed ID.
        raise WorkspaceError("Graph not found in this session.", 404, "graph_not_found")
    return ownership.graph


def reserve(workspace):
    if not Workspace.objects.filter(pk=workspace.pk, busy=False).update(busy=True):
        raise WorkspaceError("A session operation is still running. Try again after it finishes.",
                             409, "session_busy")


def release(workspace):
    Workspace.objects.filter(pk=workspace.pk).update(busy=False)


def remember_file(workspace, graph, name):
    if not name:
        return
    path = contained_path(Path(settings.MEDIA_ROOT), str(name))
    if path.is_file():
        Artifact.objects.get_or_create(workspace=workspace, graph=graph, storage_name=str(name))


def track_files(workspace, graph, response=None):
    graph.refresh_from_db()
    for field in (graph.data_file, graph.cleaned_file):
        if field and field.name:
            remember_file(workspace, graph, field.name)
    image = (response or {}).get("graph_image") if isinstance(response, dict) else None
    if isinstance(image, str) and image.startswith(settings.MEDIA_URL):
        remember_file(workspace, graph, image[len(settings.MEDIA_URL):])
    # Existing generate_graph_image uses this private, graph-specific filename.
    remember_file(workspace, graph, f"causal_graphs/causal_graph_{graph.pk}.png")


def code_fingerprint():
    root = Path(settings.BASE_DIR)
    hashes = {str(p.relative_to(root)): file_digest(p)
              for folder in (root / "causal_app", root / "p0", root / "p1", root / "causal_project")
              for p in sorted(folder.rglob("*.py")) if "__pycache__" not in p.parts}
    return digest(hashes)


def environment():
    app_dir = Path(settings.BASE_DIR).parent
    version_file = app_dir / "VERSION"
    result = {"python": platform.python_version(), "platform": platform.platform(),
              "app_version": version_file.read_text().strip() if version_file.exists() else "unknown",
              "dependencies": {}}
    source = app_dir / "p0-source.json"
    if source.exists():
        result["source"] = json.loads(source.read_text())
    for package in ("Django", "djangorestframework", "dowhy", "numpy", "pandas",
                    "networkx", "scipy", "scikit-learn", "statsmodels", "openai"):
        try:
            result["dependencies"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result["dependencies"][package] = "not installed"
    result["dependency_manifest"] = {
        path.name: file_digest(path) for path in (Path(settings.BASE_DIR) / "requirements.txt",
             app_dir / "causal-frontend/package-lock.json") if path.exists()}
    return result


def snapshot(graph):
    owner = graph.p0_owner
    available_variables = list(graph.variables.order_by("name").values_list("name", flat=True))
    edges = []
    for edge in graph.edges.select_related("source", "target").prefetch_related("evidences").all():
        edges.append({"source": edge.source.name, "target": edge.target.name,
                      "directed": edge.directed, "manual_lock": edge.manual_lock,
                      "evidence": [{"type": e.evidence_type, "status": e.status,
                                    "score": e.score, "details": redact(e.details)}
                                   for e in edge.evidences.all()]})
    active_names = set(graph.node_positions or {})
    active_names.update(e[endpoint] for e in edges for endpoint in ("source", "target"))
    nodes = [{"name": name, "position": (graph.node_positions or {}).get(name)}
             for name in sorted(active_names)]
    data = {"sample_id": owner.sample_id or None}
    if owner.sample_id:
        manifest_file = Path(settings.BASE_DIR).parent / "examples/manifest.json"
        if manifest_file.exists():
            samples = json.loads(manifest_file.read_text(encoding="utf-8")).get("samples", [])
            sample = next((s for s in samples if s["id"] == owner.sample_id), {})
            data["provenance"] = {k: sample[k] for k in ("id", "source", "git_blob_sha1", "warnings") if k in sample}
    for label, field in (("raw", graph.data_file), ("cleaned", graph.cleaned_file)):
        if field and field.name:
            path = contained_path(Path(settings.MEDIA_ROOT), field.name)
            if not path.is_file():
                # A database restored without its media directory, or manual cleanup, leaves a
                # dangling reference; fail clearly rather than 500 on every recorded operation.
                raise WorkspaceError(f"The {label} dataset file for this graph is no longer on the server. "
                                     "Re-upload the data or load a sample into a new graph.", 410, "data_file_missing")
            data[label] = {"sha256": file_digest(path), "bytes": path.stat().st_size}
    data["effective"] = "cleaned" if graph.cleaned_file else "raw"
    return json_ready({"dag": {"nodes": nodes, "edges": sorted(edges, key=lambda e: (e["source"], e["target"]))},
                       "data": data, "cleaning": owner.cleaning_history,
                       "current_cleaning_plan": graph.cleaning_plan, "available_variables": available_variables,
                       "code_sha256": code_fingerprint()})


def query_for(graph, payload):
    names = dict(graph.variables.values_list("id", "name"))
    def name(value):
        try:
            return names.get(int(value))
        except (ValueError, TypeError):
            return None
    return {"treatment": name(payload.get("treatment")), "outcome": name(payload.get("outcome")),
            "target_units": str(payload.get("estimand") or "ATE").upper(),
            "treatment_value": payload.get("treatment_value", 1),
            "control_value": payload.get("control_value", 0)}


def save_record(workspace, graph, operation, before, payload, response, seed, started_at, http_status=200):
    query = query_for(graph, payload)
    safe_config = {key: payload[key] for key in (
        "treatment", "outcome", "method_name", "estimators", "estimand", "num_simulations",
        "time_column", "entity_column", "window_count", "max_lag", "treatment_value", "control_value") if key in payload}
    record = RunRecord.objects.create(workspace=workspace, graph=graph, operation=operation,
        analysis_key=analysis_key(before, query, seed), payload={
            "snapshot": before, "query": query, "configuration": safe_config,
            "http_status": http_status, "status": "completed" if http_status < 400 else "error",
            "defaults_policy": "Omitted values use the recorded application/library version defaults.",
            "seed": {"requested": seed, "python_random": seed, "numpy_legacy": seed,
                     "library_specific_generators": "not all overridden; inspect versioned source",
                     "llm": "not deterministic"},
            "started_at": started_at.isoformat(), "finished_at": timezone.now().isoformat(),
            "environment": environment(), "result": redact(response),
        })
    return record


def delete_workspace(workspace):
    """Call only while holding the workspace reservation. Failure remains retryable."""
    Workspace.objects.filter(pk=workspace.pk).update(deleting=True)
    for owner in workspace.graphs.select_related("graph"):
        track_files(workspace, owner.graph)
    failures = 0
    for artifact in workspace.artifacts.all():
        try:
            contained_path(Path(settings.MEDIA_ROOT), artifact.storage_name).unlink(missing_ok=True)
        except (OSError, ValueError):
            failures += 1
    if failures:
        raise WorkspaceError("Some server files could not be removed. Session is locked; retry deletion or contact the operator.",
                             500, "deletion_incomplete")
    with transaction.atomic():
        ids = list(workspace.graphs.values_list("graph_id", flat=True))
        CausalGraph.objects.filter(pk__in=ids).delete()
        workspace.delete()
    return {"deleted": True,
            "scope": "Owned graphs, uploads, cleaned copies, generated graph images, run records and pending approvals.",
            "not_deleted": ["Downloaded exports", "Hosting access logs and backups", "Previously sent provider data"]}
