# CausalGUI

Full-stack causal graph builder with:

- Django REST API (`causalproject/`)
- Vue 3 + Vite frontend (`causal-frontend/`)

Features: interactive graph canvas, AI-assisted edge drafting (OpenAI), statistical edge verification, identification analysis (admissibility checklist, backdoor paths, adjustment sets), robustness dashboard (estimator comparison, refutations, sensitivity), and time-series causal analysis.

This is the canonical setup and operations runbook for the app. For repository-level overview, see `../README.md`.

## Prerequisites

- Python 3.10+
- Node.js 20+ (LTS recommended)

## Backend Setup (Django)

```bash
cd causalproject
..\..\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# .env already exists - set your key:
# edit .env and fill in OPENAI_API_KEY=sk-proj-...
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

If you prefer an isolated backend-only environment, create and activate `causalproject/.venv` instead.

Backend runs at `http://127.0.0.1:8000`.

### Environment Variables

Configured in `causalproject/.env`:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CORS_ALLOWED_ORIGINS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `OPENAI_API_KEY` (optional, enables AI edge suggestions)
- `OPENAI_MODEL` (optional, default: `gpt-4o-mini`)

## Frontend Setup (Vue)

```bash
cd causal-frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173` and proxies `/api` to Django.

From the repository root, you can also run frontend commands through root scripts:

```bash
npm run dev
npm run lint
npm run test
npm run build
```

## Development Commands

### Backend

```bash
cd causalproject
python manage.py migrate
python manage.py test
```

### Frontend

```bash
cd causal-frontend
npm run lint
npm run test
npm run build
```

## API Endpoints

| Method | URL | Description |
|--------|-----|-------------|
| POST | `/api/upload_csv/` | Upload dataset CSV, create graph + variables |
| GET | `/api/graph_details/<id>/` | Return graph nodes, edges, positions |
| POST | `/api/save_graph/` | Persist nodes, edges, and node positions |
| POST | `/api/assess_query/` | Identification analysis: admissibility checklist, backdoor paths, adjustment sets |
| POST | `/api/causal_inference/` | Run DoWhy causal estimation |
| POST | `/api/robustness_dashboard/` | Estimator comparison, refutations, sensitivity, robustness score |
| POST | `/api/openai/suggest_edges/` | LLM edge suggestions from variable names only |
| POST | `/api/openai/draft_graph/` | LLM draft + statistical verification against uploaded dataset |
| POST | `/api/time_series_analysis/` | Rolling-window temporal causal analysis, edge stability |

## Notes

- Uploaded datasets and generated graph images are written under `causalproject/media/`.
- Workspace Python interpreter is configured in `.vscode/settings.json` to use `.venv` at repository root.
- `python-dotenv` is used to load `.env`; it is listed in `requirements.txt`.
- The robustness dashboard runs three estimators by default (`linear_regression`, `propensity_score_matching`, `propensity_score_weighting`). `doubly_robust_estimator` is excluded by default due to memory usage in dev.

## Current Interaction Flow

1. Upload CSV from the Dataset sidebar.
2. Drag variables onto the canvas as nodes.
3. Create directed edges by dragging from a node handle to another node (or right-drag as fallback).
4. Use **Graph Copilot** to ask the LLM for edge suggestions. Review each suggestion in the Copilot panel (accept / lock-accept / skip).
5. Use the **Identification** panel to check DAG validity, admissibility, backdoor paths, and minimal adjustment sets.
6. Choose treatment/outcome in Controls and click **Estimate Effect**.
7. Open the **Robustness Dashboard** to compare estimators, inspect refutations, and see the robustness score.
8. Use **Time Series** mode to run rolling-window stability analysis across temporal windows.

Important behavior:

- Uploading a CSV does **not** auto-add nodes/edges to the canvas.
- The `Reset` button clears canvas and analysis results, while keeping the uploaded dataset/variables loaded.
- Node positions are persisted with the saved graph and restored on reload.
- Multi-select is supported with box selection, and the Canvas Details panel shows the current selection state.
- **Graph Copilot** requires `OPENAI_API_KEY` in `.env` and a dataset-linked graph. It calls `draft_graph` when a graph exists, otherwise falls back to `suggest_edges`.
- The Copilot panel shows per-edge confidence, verifier breakdown (LLM prior, marginal/partial correlation, pair coverage, temporal precedence), and a recommended action (accept / review / reject).
- The Identification panel shows DAG cycle status, admissibility checklist, adjustment sets, IV/frontdoor candidates, open/blocked backdoor paths, and sample/variation diagnostics.
- The Robustness Dashboard shows estimator comparison, refuter results (placebo treatment, dummy outcome, random common cause, data subsample), linear sensitivity sweep, and an overall robustness score.
- Time Series mode requires a time column and at least one entity column; it runs per-window lag analysis and returns per-edge stability scores across windows.

## VS Code Shell Quickstart

Use two integrated terminals:

Terminal 1 (backend):

```powershell
Set-Location "C:\Users\agros\Programming\Python\CausalitySection\CausalGUI\causalproject"
..\..\.venv\Scripts\Activate.ps1
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

Terminal 2 (frontend):

```powershell
Set-Location "C:\Users\agros\Programming\Python\CausalitySection\CausalGUI\causal-frontend"
npm run dev
```

Frontend: `http://localhost:5173`.
Backend: `http://127.0.0.1:8000`.

## Data Preprocessing (Backend)

Before analysis, the backend applies column-wise preprocessing:

- Boolean-like values (`true/false`, `yes/no`, `1/0`) are converted to numeric.
- Numeric-like strings are coerced to numeric.
- Datetime-like values are converted to epoch seconds.
- Remaining text/categorical columns are encoded to category codes.
- `inf/-inf` values are replaced and missing numeric values are imputed (median fallback, else `0.0`).

This reduces failures from mixed column types and missing values during causal estimation.

## Troubleshooting

- `POST /api/openai/draft_graph/ 400`:
	- Confirm `OPENAI_API_KEY` is set in `causalproject/.env` and the backend was restarted after editing.
	- Confirm a CSV has been uploaded (the graph must have a linked data file).
	- Confirm at least two variables are present in the graph.
	- Check the response body: `{"error": "..."}` will identify the exact failure.
- `ECONNRESET` on `/api/robustness_dashboard/`:
	- The Django dev server process was killed by memory pressure. Reduce the number of requested estimators or lower `num_simulations` in `services.py`.
	- Avoid requesting `backdoor.doubly_robust_estimator` on large datasets.
- Cannot draw edges on the canvas:
	- Ensure at least two nodes are present on the canvas. Edge drawing only works between existing nodes.
	- Try the right-drag fallback: right-click and drag from source node to target node.
	- Clear selection state first (click empty canvas area), then retry edge drawing.
	- If a browser/context-menu still appears, keep the right mouse button held and drag before release.
	- Verify the frontend is running from latest code: `cd causal-frontend`, then `npm run lint && npm test && npm run dev`.
	- Hard refresh the browser tab (Ctrl+F5) after pulling updates.
- `POST /api/assess_query/ 404` while selecting variables:
	- Ensure edges are saved (the frontend now persists edges before assessment).
	- Confirm Django server is running and frontend proxy points to `127.0.0.1:8000`.
- `Found unknown categories ... during transform`:
	- Backend now falls back to safer estimation paths automatically.
- `exog contains inf or nans`:
	- Addressed by preprocessing/imputation; restart Django after pulling latest changes.
