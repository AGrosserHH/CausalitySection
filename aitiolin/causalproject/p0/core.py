"""Dependency-free, tested security/provenance helpers. No network operations."""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import zipfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "aitiolin.run.v1"
PROTOTYPE_NOTICE = (
    "Experimental prototype for private learning and hypothesis exploration. "
    "Not validated for production, operational business decisions, medical or policy recommendations. "
    "Passing diagnostics does not establish that a causal graph or effect is correct."
)
LIMITATIONS = [
    PROTOTYPE_NOTICE,
    "Identification is conditional on the supplied causal assumptions, not verification of those assumptions.",
    "Observational estimates can be biased by unmeasured confounding, timing, selection or misspecification.",
    "Python and NumPy legacy RNGs are seeded; library-specific generators and LLM outputs may differ.",
    "No dataset rows are included. Re-running requires matching local input data and dependencies.",
    "Metadata, variable names, graph annotations and statistical outputs may still be sensitive.",
    "Existing preprocessing may assign ordinal codes to nominal categories. Review encoding and units.",
]
OMIT_KEYS = {
    "preview", "preview_rows", "raw_data", "raw_rows", "rows", "data_file", "cleaned_file",
    "dataset_path", "image_path", "graph_image", "context", "api_key", "authorization",
    "session_token", "approval_token", "prompt", "messages",
}


def json_ready(value: Any) -> Any:
    """Strict JSON: non-finite floats become null, not invalid NaN/Infinity tokens."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(v) for v in value]
    if hasattr(value, "tolist"):
        return json_ready(value.tolist())
    if hasattr(value, "item"):
        return json_ready(value.item())
    return str(value)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(json_ready(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def redact(value: Any) -> Any:
    """Conservative export filter, not an anonymisation claim."""
    if isinstance(value, dict):
        return {str(k): redact(v) for k, v in value.items()
                if str(k).lower() not in OMIT_KEYS and "secret" not in str(k).lower()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return json_ready(value)


def parse_seed(value: Any = 42) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"\d{1,10}", str(value)):
        raise ValueError("Seed must be an integer between 0 and 4294967295.")
    seed = int(value)
    if seed > 2**32 - 1:
        raise ValueError("Seed must be an integer between 0 and 4294967295.")
    return seed


def token_digest(token: str) -> str:
    if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{64}", token):
        raise ValueError("A 256-bit session token is required in X-Aitiolin-Session.")
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def contained_path(root: Path, relative: str) -> Path:
    """Reject absolute names, traversal and symlinks escaping the controlled root."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("Invalid relative path.")
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("Path must remain inside the configured directory.")
    result = (root.resolve() / rel).resolve()
    if not result.is_relative_to(root.resolve()) or result == root.resolve():
        raise ValueError("Path must remain inside the configured directory.")
    return result


def analysis_key(snapshot: dict, query: dict, seed: int) -> str:
    """Exclude positions and estimator choice; retain graph, data and treatment contrast."""
    dag = snapshot.get("dag", {})
    edges = sorted(dag.get("edges", []), key=lambda e: (e["source"], e["target"]))
    causal_edges = [{k: e[k] for k in ("source", "target", "directed") if k in e} for e in edges]
    return digest({"nodes": sorted(n["name"] for n in dag.get("nodes", [])),
                   "edges": causal_edges, "data": snapshot.get("data", {}),
                   "cleaning": snapshot.get("cleaning", []), "query": query,
                   "seed": seed, "code_sha256": snapshot.get("code_sha256")})


def make_bundle(run: dict, records: list[dict]) -> bytes:
    """Immutable snapshot ZIP. Never accepts files or a user-supplied archive path."""
    document = redact({**run, "schema_version": SCHEMA_VERSION, "stages": records,
                       "raw_data_included": False, "limitations": LIMITATIONS})
    files = {
        "run.json": canonical_bytes(document),
        "dag.json": canonical_bytes(document.get("snapshot", {}).get("dag", {})),
        "cleaning.json": canonical_bytes(document.get("snapshot", {}).get("cleaning", [])),
        "README.txt": ("aitiolin reproducibility record\n\n" + "\n".join(LIMITATIONS)
            + "\n\nResults are recorded, not rerun during export. Each stage retains its request, "
              "response and timestamp. The bundle is a provenance record, not a self-contained "
              "replay engine or proof of reproducibility.\n").encode(),
    }
    files["checksums.json"] = canonical_bytes({name: hashlib.sha256(content).hexdigest()
                                               for name, content in files.items()})
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, content)
    return target.getvalue()
