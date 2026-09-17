# Changelog

## Consolidation — 2026-09-17

Structure only; no behaviour change. All five comparison estimators and the legacy estimator return
bit-identical results on the Churn sample before and after.

- Merge the separate `p0` and `p1` Django apps into `causal_app` as `causal_app/workspace/` (sessions,
  privacy, exports) and `causal_app/analysis/` (reviewed comparisons). Frontend code moves to
  `src/workspace/` and `src/analysis/`; components become `WorkspacePanel`, `PrivacyReview`, `AnalysisPanel`.
- Routes move to `/api/workspace/…` and `/api/analysis/…`. Commands become `purge_sessions` and
  `recover_locks`. Settings become `WORKSPACE_*`; the old `P0_*` environment names are still read.
- Recreate the workspace tables under `causal_app` (migration `0010_workspace_models`), which also drops
  the old `p0_*` tables. They only ever held 24-hour session data. Run `python manage.py migrate`.
- Keep the identifiers stored inside exported bundles (`aitiolin.run.v1`, `aitiolin.p1.v1`, the `p1` key,
  `p1_estimate`) so existing exports stay restorable.
- Remove the one-off `scripts/integrate_p1_sources.py`, `p0-source.json` and the installer sections of the docs.

## P1 integration — 2026-09-17

P1 module version: `0.1.0-p1.1`. The existing application version is unchanged;
this is a source integration, not a published release or deployment.

- Add the collapsed Reviewed comparison panel without replacing the existing canvas or agent workflow.
- Make treatment/control values, binary outcome events, target populations, adjustment,
  nominal reference categories, interactions and missing-data handling explicit.
- Add regression and logistic standardized contrasts, propensity weighting and matching,
  plus a separately labelled descriptive comparison. Report appropriate uncertainty
  or an explicit unavailable state, with overlap, balance and effective-sample diagnostics.
- Record named P1 runs in the existing private P0 workspace/export infrastructure.
- Validate P1 JSON/ZIP bundles and restore into a new owned graph after raw/cleaned
  data-hash verification; never import executable code or treat old estimates as new runs.
- Add synthetic randomized-campaign and poor-overlap teaching datasets, methods documentation,
  real-estimator API tests and the read-only P1 backend/frontend CI workflow.
- Wire P1 routes and include its source in the analysis fingerprint.
- Remove silent legacy estimator substitution and unadjusted difference-in-means fallback.
- Correct the delivered numerical test's malformed list-comprehension bracket before integration.

P1 supports independent observations only. Matching intervals, clustered/panel inference,
IV/front-door extensions and heterogeneous-effect models are not added. P1 settings do
not silently change the legacy estimator/agent/robustness configuration.

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
- Verify sample integrity over LF-normalised bytes so Windows checkouts can load the guided examples.
- Name the analysis seed in its validation error; the client omits a cleared seed instead of sending
  an empty header. Stop re-issuing identical identification queries from the estimate flow.
- Fail clearly (410) when a tracked dataset file is missing; purge every expired session in one pass;
  take the process-wide RNG lock only for analysis routes; cap unexpired sessions with
  `P0_MAX_ACTIVE_WORKSPACES`.

This is a prototype patch, not a security certification, causal-method validation or production release.
