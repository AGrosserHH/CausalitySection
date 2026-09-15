#!/usr/bin/env python3
"""Check specific positive claims, not legitimate negative-use disclaimers."""
import re
from pathlib import Path

PATTERNS = [r"\bbefore rollout\b", r"\bproduction[- ]ready\b",
            r"\bguarantee[sd]?\s+(?:legal\s+|regulatory\s+)?compliance\b",
            r"\bproves? causation\b", r"\bprobability of causal correctness:\s*\d"]
NEGATED = re.compile(r"\b(?:not|never|no|cannot|doesn't|isn't|without)\b", re.I)


def violations(text):
    found = []
    for index, line in enumerate(text.splitlines(), 1):
        for pattern in PATTERNS:
            for match in re.finditer(pattern, line, re.I):
                # Restrict negation to the nearby clause before this actual match.
                prefix = re.split(r"[.;!?]", line[:match.start()])[-1][-100:]
                if not NEGATED.search(prefix): found.append((index, match.group()))
    return found


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    failed = []
    for base in (root / "aitiolin/causal-frontend/src", root / "aitiolin/website"):
        for path in base.rglob("*"):
            if path.suffix not in (".vue", ".html", ".js", ".mjs") or ".test." in path.name: continue
            for line, phrase in violations(path.read_text(encoding="utf-8")):
                failed.append(f"{path.relative_to(root)}:{line}: review {phrase!r}")
    print("\n".join(failed) if failed else "Prototype language checks passed.")
    raise SystemExit(bool(failed))
