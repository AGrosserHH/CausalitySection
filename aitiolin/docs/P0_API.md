# P0 API and recording contract

All API calls, including the original `/api/` routes, require a random 64-character lowercase hexadecimal bearer token in `X-Aitiolin-Session`. The browser generates it using `crypto.getRandomValues`; only its SHA-256 digest is stored as the workspace key. Send no token in URLs. The app's API client attaches it to same-origin `/api/` paths only.

`X-Aitiolin-Seed` is an optional unsigned 32-bit integer; the default is 42. External LLM requests are disabled unless `X-Aitiolin-LLM-Mode: review` is explicitly set. This is a prototype session mechanism, not an account/login system or public multi-tenant authorization platform.

## Additional routes

| Method | Route | Behavior |
|---|---|---|
| GET | `/api/p0/session/` | Session expiry, storage descriptions and provider availability. |
| PATCH | `/api/p0/session/` | `{"retention_hours": 1}`; accepted options: 1, 6, 24, within the configured maximum session lifetime. |
| DELETE | `/api/p0/session/data/` | Deletes owned records and tracked files. Busy sessions return 409; incomplete file deletion returns 500 and remains retryable. |
| GET | `/api/p0/samples/` | Allowlisted sample titles, questions, roles, sources and caveats. |
| POST | `/api/p0/samples/churn/load/` | Copies the bundled Churn CSV, creates an owned graph with a preset DAG and role IDs. No cleaning or LLM request. |
| POST | `/api/p0/samples/worldbank/load/` | Same for the 2019 World Bank snapshot in original units. |
| GET | `/api/p0/graphs/{graph_id}/runs/` | Most recent 50 stage records for an owned graph. |
| GET | `/api/p0/runs/{uuid}/bundle/?file_format=zip` | Export stored records and matching earlier stages as a ZIP. |
| GET | `/api/p0/runs/{uuid}/bundle/?file_format=json` | Equivalent structured JSON export. |
| GET | `/api/p0/graphs/{graph_id}/image/` | Owned graph image, fetched with the session header and displayed from a blob URL. |

Use `file_format`, not `format`: the latter is reserved by Django REST Framework's renderer negotiation.

## LLM review flow

1. A user requests an LLM-assisted graph/model action with reviewed mode enabled.
2. The endpoint builds the outgoing completion payload, but the provider call is intercepted before transmission.
3. The response is HTTP 409 with code `llm_review_required`, a preview of the exact completion payload, its SHA-256, the destination/provider notice and a short-lived approval token.
4. The browser displays the preview. Canceling makes no completion request.
5. Approval resubmits the same action with `X-Aitiolin-LLM-Approval`. The server recomputes the outgoing payload hash and checks the operation, owner, expiry and unused permit. A changed request requires another review. A permit is consumed before the provider call, including when the provider then returns an error.

The patch omits the statistical profile from the model prompt and does not attach uploaded rows. Names, manually supplied context and graph descriptions can still be sensitive. The exact completion payload is shown, but it is not stored in the database by P0; the permit stores a hash. The provider client uses a fixed OpenAI API base URL, a 30-second timeout, no SDK retries and `store=false`. This does not promise zero provider retention.

The Causality Agent's local heuristic branch remains available with reviewed mode off. Direct Graph Copilot requests return an explanatory error while external mode is off. Schema/model suggestions are hypotheses, not confirmed causal structure.

## Recording

Recorded operations are identification/assessment, inference, estimate-plan refresh, robustness, competing-model comparison, time-series, what-if and root-cause calls. Successful and returned-error responses retain an HTTP status; failed values are not silently recorded as successful evidence.

Each record includes:

```text
id, operation, analysis_key
snapshot:
  dag: active nodes, edges, locks, evidence, saved canvas positions
  available_variables: full dataset-column inventory, separate from the DAG
  data: sample provenance, source/effective data SHA-256 hashes and sizes
  cleaning: cumulative accepted cleaning requests/results
  current_cleaning_plan
  code_sha256
query: treatment/outcome names, intended target and treatment contrast
configuration: submitted supported estimator/time-series settings
defaults_policy
seed: requested seed, controlled RNGs and uncontrolled/nondeterministic caveats
started_at, finished_at, status, http_status
environment: app/Python/dependency versions and source/lockfile metadata
result: endpoint response without row previews, filesystem paths or explicit secret fields
```

The recorded query normalizes the inspected DoWhy 0.14 defaults to ATE and a 0→1 treatment contrast, matching the existing UI's ATE request. This is the requested/intended query, not proof that an IV estimator identifies a population ATE, or that an emergency descriptive fallback respected the requested contrast. Inspect the returned method, estimand and limitations. Omitted method parameters retain source/library defaults; they are not all independently expanded into a full trained-model serialization.

The analysis association key hashes the active graph structure, data hashes, cleaning history, query, source fingerprint and seed. Positions and estimator selection are excluded so diagnostics and alternative estimators for the same question can be reviewed together. A changed graph/data/query/seed produces another key. The dashboard only presents a competing-model table alongside a robustness run when those provenance keys match.

## Bundle

```text
aitiolin-run-{uuid}.zip
  run.json
  dag.json
  cleaning.json
  README.txt
  checksums.json
```

`run.json` includes the selected immutable stage and matching preceding stages. It does not fetch subsequent stages or recompute an estimate. A bundle downloaded immediately after estimation will not contain checks that were run later; select the latest completed stage to include them.

Input files, row previews, prompts and explicit secret fields are excluded. There is deliberately no `include_data=true` route. This is data minimization, not anonymization: variable names, cleaning parameters, error messages, graph annotations and aggregate results may disclose information.

The bundle is not a one-click replay engine. Re-running requires matching data and dependencies, and some library-specific random generators or LLM behavior are not controlled. Raw-source and processed-file hashes allow the operator to check the correct local inputs.

## Files, expiry and concurrency

Django FileField writes are tracked in the workspace, including successive cleaned copies. The existing generated-graph filename is also tracked. No public Django media-serving route remains. A reverse proxy must not expose the same media directory independently.

An atomic per-workspace reservation prevents overlapping requests and deletion-vs-write races. The browser queues its API calls. Python/NumPy legacy random state is serialized within each worker and restored after requests. A crashed worker can leave a reservation set: the explicit lock-recovery command is only for use after all application workers are stopped.

Session expiry blocks API access. Scheduled purge performs physical file/row deletion and skips busy sessions. Deletion is scoped to managed session records/files, never the bundled example originals. Pre-P0 graphs remain unowned; no automatic ownership adoption or legacy cleanup is performed.

## Manual checks before merging

Start the updated app, load both samples without a provider key, run and compare actual estimates, change a graph and confirm old diagnostics are not treated as matching, inspect ZIP/JSON exports, test privacy cancellation/approval with non-sensitive sample metadata, and delete a session while verifying another independent browser session remains unaffected. Run the automated Django and Vue suites first. Review logs and proxy configuration separately before any non-local hosting.
