# Reviewed-comparison API and recording contract

Every route uses the anonymous workspace header `X-Aitiolin-Session`. The seed header `X-Aitiolin-Seed` must agree with the comparison specification. The workspace ownership/expiry/reservation safeguards apply; all data processing is server-side. These routes make no provider requests.

| Route | Request | Result |
|---|---|---|
| GET `/api/analysis/schema/` | `graph_id`, optional treatment name | Column types/levels, saved DAG, data-source label, suggested treatment parents, `state_id`. |
| POST `/api/analysis/estimate/` | `graph_id`, exact reviewed `state_id`, `specification` | Explicit comparison result plus `run_id`, `analysis_key`; a successful run is stored as a workspace RunRecord. |
| GET `/api/analysis/history/` | `graph_id` | Up to 50 named comparison runs for the active graph, newest first. |
| POST `/api/analysis/compare/` | Two distinct owned `run_ids` | Specification/graph differences; effect delta only if scale/data/sample/target match. |
| POST `/api/analysis/bundles/preview/` | Multipart `graph_id`, `bundle` file | Validation/replay preview and `approval_digest`; creates no graph. |
| POST `/api/analysis/bundles/restore/` | Same fields plus `confirmed=true`, digest | NEW owned graph, roles, raw/cleaned copies, reviewed configuration to restore; no estimate. |
| POST `/api/analysis/examples/randomized/load/` | `{}` | Synthetic campaign graph/data, generating risk difference 0.08. |
| POST `/api/analysis/examples/poor-overlap/load/` | `{}` | Synthetic positivity failure graph/data. |

The five method identifiers in this path are `linear_regression`, `logistic_regression`, `propensity_score_weighting`, `propensity_score_matching`, `descriptive_difference`. They identify the implementation in `causal_app/analysis/engine.py`, NOT DoWhy's `backdoor.*` classes.

Example request specification:

```json
{
  "name": "Churn — reviewed contract comparison",
  "treatment": "Contract",
  "outcome": "Churn",
  "treatment_kind": "categorical",
  "outcome_kind": "binary",
  "control_value": "Month-to-month",
  "treatment_value": "One year",
  "event_value": "Yes",
  "estimand": "ATE",
  "method": "logistic_regression",
  "covariates": [{"name": "tenure", "kind": "numeric"},
                 {"name": "gender", "kind": "nominal", "reference": "Female"}],
  "interactions": [],
  "missing": "error",
  "uncertainty": "auto",
  "confidence": 0.95,
  "bootstrap_reps": 200,
  "seed": 42,
  "units": "probability",
  "reviewed": true,
  "independent_units": true
}
```

This is a syntax illustration, not endorsement of snapshot tenure as a valid confounder. Its timing is an important limitation of the Churn dataset.

A successful result provides effect and scale, uncertainty status/method, identification under the supplied graph, reviewed specification, sample exclusions, encoding, diagnostics and warnings. Recording stores this full specification under `p1.specification` (a stable key inside exported bundles), module version, snapshots, data hashes, environment and timestamps. The workspace JSON/ZIP export preserves it. No legacy refuter run is silently associated with the analysis key of the comparison.

A state mismatch produces HTTP 409 (`stale_state`) and requires fresh review. Input/identification/estimator failures return explicit HTTP 400 errors, not substitute estimates. Missing dependencies and workspace ownership/retention errors remain distinguishable. Bundle hashes verify consistency; they do not establish authenticity.
