# P1 API and recording contract

Every route uses the P0 anonymous workspace header `X-Aitiolin-Session`. The seed header `X-Aitiolin-Seed` must agree with the P1 specification. Existing P0 ownership/expiry/reservation safeguards apply; all data processing is server-side. P1 makes no provider requests.

| Route | Request | Result |
|---|---|---|
| GET `/api/p1/schema/` | `graph_id`, optional treatment name | Column types/levels, saved DAG, data-source label, suggested treatment parents, `state_id`. |
| POST `/api/p1/estimate/` | `graph_id`, exact reviewed `state_id`, `specification` | Explicit P1 result plus `p0_run_id`, `p0_analysis_key`; successful run stored in P0 RunRecord. |
| GET `/api/p1/history/` | `graph_id` | Up to 50 named P1 runs for the active graph, newest first. |
| POST `/api/p1/compare/` | Two distinct owned `run_ids` | Specification/graph differences; effect delta only if scale/data/sample/target match. |
| POST `/api/p1/bundles/preview/` | Multipart `graph_id`, `bundle` file | Validation/replay preview and `approval_digest`; creates no graph. |
| POST `/api/p1/bundles/restore/` | Same fields plus `confirmed=true`, digest | NEW owned graph, roles, raw/cleaned copies, reviewed configuration to restore; no estimate. |
| POST `/api/p1/examples/randomized/load/` | `{}` | Synthetic campaign graph/data, generating risk difference 0.08. |
| POST `/api/p1/examples/poor-overlap/load/` | `{}` | Synthetic positivity failure graph/data. |

The five method identifiers in this path are `linear_regression`, `logistic_regression`, `propensity_score_weighting`, `propensity_score_matching`, `descriptive_difference`. They identify the P1 implementation, NOT DoWhy's `backdoor.*` classes.

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

A successful result provides effect and scale, uncertainty status/method, identification under the supplied graph, reviewed specification, sample exclusions, encoding, diagnostics and warnings. P1 recording stores this full specification under `p1.specification`, module version, snapshots, data hashes, environment and timestamps. Existing P0 JSON/ZIP export preserves it. No legacy refuter run is silently associated with the P1 key.

A state mismatch produces HTTP 409 (`p1_stale_state`) and requires fresh review. Input/identification/estimator failures return explicit HTTP 400 errors, not substitute estimates. Missing dependencies and existing P0 ownership/retention errors remain distinguishable. Package-integrity hashes do not replace code review, and bundle hashes do not establish authenticity.
