# CausalGUI

Full-stack causal graph builder with:

- Django REST API (`causalproject/`)
- Vue 3 + Vite frontend (`causal-frontend/`)

This is the canonical setup and operations runbook for the app. For repository-level overview, see `../README.md`.

## Prerequisites

- Python 3.10+
- Node.js 20+ (LTS recommended)

## Backend Setup (Django)

```bash
cd causalproject
..\..\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
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

## Notes

- The top-level `requirement.txt` now delegates to backend requirements.
- Uploaded datasets and generated graph images are written under `causalproject/media/`.
- Workspace Python interpreter is configured in `.vscode/settings.json` to use `.venv` at repository root.
- AI edge suggestions are available at `POST /api/openai/suggest_edges/` when `OPENAI_API_KEY` is configured.

## Current Interaction Flow

1. Upload CSV from the Dataset sidebar.
2. Select variables from the sidebar and drag them onto the canvas as nodes.
3. Create directed edges by dragging from a node handle to another node.
4. If handle gestures are unreliable in your browser/session, right-drag from a source node to a target node as fallback.
5. Use the Controls panel for auto-layout, delete selected, undo/redo, and zoom/fit/center actions.
6. Choose treatment/outcome in Controls and run inference.

Important behavior:

- Uploading a CSV does **not** auto-add nodes/edges to the canvas.
- The `Reset` button clears canvas and analysis results, while keeping the uploaded dataset/variables loaded.
- Node positions are persisted with the saved graph and restored on reload.
- Multi-select is supported with box selection, and the Canvas Details panel shows the current selection state.

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
