from pathlib import Path
import json
import re

root = Path(__file__).resolve().parents[1] / "aitiolin"
version = (root / "VERSION").read_text().strip()
if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version):
    raise SystemExit("Invalid VERSION.")
for file in ("package.json", "package-lock.json"):
    data = json.loads((root / "causal-frontend" / file).read_text())
    if data["version"] != version: raise SystemExit(f"Version mismatch in {file}")
if f"## {version}" not in (root / "CHANGELOG.md").read_text():
    raise SystemExit("Current version lacks a changelog entry.")
print(f"Version metadata aligned: {version}")
