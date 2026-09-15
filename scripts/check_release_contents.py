#!/usr/bin/env python3
"""Refuse private runtime artefacts in tracked source; intentional sample CSVs remain allowed."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode("utf-8").split("\0")
failures = []
for item in filter(None, tracked):
    path = Path(item)
    if (path.name == ".env" or path.name.startswith(".env.") and path.name != ".env.example"
        or path.suffix in {".sqlite3", ".sqlite", ".log", ".pyc"}
        or "media" in path.parts and "causalproject" in path.parts
        or "node_modules" in path.parts or "__pycache__" in path.parts):
        failures.append(item)
if failures:
    print("Remove private/generated runtime artefacts from tracked files:\n" + "\n".join(failures), file=sys.stderr)
    raise SystemExit(1)
print("Tracked runtime-artifact check passed. This is not a full secret scanner.")
