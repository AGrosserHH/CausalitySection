# Causality Section

This repository contains experiments and a working prototype GUI for causal inference workflows.

## Project Layout

- `CausalGUI/` - full-stack app (Django API + Vue frontend)
- `CausalModels/` - notebooks and modeling experiments

## Start Here

- App setup, backend/frontend runbook, and API feature notes: `CausalGUI/README.md`
- Notebook-focused dependencies and experiments: `CausalModels/requirements.txt`

Recent UX and backend behavior updates (node position persistence, canvas controls, and troubleshooting) are documented in `CausalGUI/README.md`.

## Root Shortcuts

From repository root, these scripts proxy to the frontend workspace:

```bash
npm run dev
npm run lint
npm run test
npm run build
```

For backend tests from root:

```bash
cd CausalGUI/causalproject
..\..\.venv\Scripts\python.exe manage.py test
```

For backend runtime from root:

```bash
cd CausalGUI/causalproject
..\..\.venv\Scripts\python.exe manage.py migrate
..\..\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```
