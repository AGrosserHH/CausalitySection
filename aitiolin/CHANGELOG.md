# Changelog

## 0.1.0-prototype.1 — 2026-09-15

- Add allowlisted Churn and World Bank sample loading, fixed educational DAG presets and a short guide.
- Record immutable analysis-stage snapshots with dataset hashes, cleaning history, configuration,
  seed information, installed versions and evidence. Export JSON/ZIP without raw CSV rows.
- Add anonymous, tab-scoped bearer sessions and graph ownership checks to all existing API routes.
- Add one-use approval for the exact LLM payload; omit statistical profiles from model prompts.
- Make model assistance local/heuristic by default until reviewed provider requests are enabled.
- Add server-data deletion, expiry and a scheduled cleanup command. Disable public media URLs.
- Show refutations, estimator differences and a sensitivity curve before the optional composite score.
- Add backend integration tests, dependency-free helper tests, frontend tests and GitHub CI.
- Add a version source of truth, draft prerelease workflow and targeted terminology checks.

This is a prototype patch, not a security certification, causal-method validation or production release.
