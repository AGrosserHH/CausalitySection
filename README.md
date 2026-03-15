# Causality Section

This repository contains experiments and a working prototype GUI for causal inference workflows.

## Project Layout

- `CausalGUI/` - full-stack app (Django REST API + Vue 3 frontend)
- `CausalModels/` - Jupyter notebooks and modeling experiments

## Start Here

- Full setup, runbook, and feature reference: `CausalGUI/README.md`
- Notebook-focused dependencies and experiments: `CausalModels/requirements.txt`

The app includes an AI copilot for graph drafting (OpenAI), identification analysis, robustness dashboard, and time-series mode. All features are documented in `CausalGUI/README.md`.

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

## OpenAI Setup

Set your API key in `CausalGUI/causalproject/.env` before starting the backend:

```
OPENAI_API_KEY=sk-proj-...
```

The file already exists with documentation inline. The `.env` is git-ignored.
