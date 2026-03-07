# CausalGUI

Full-stack causal graph builder with:

- Django REST API (`causalproject/`)
- Vue 3 + Vite frontend (`causal-frontend/`)

## Prerequisites

- Python 3.10+
- Node.js 20+ (LTS recommended)

## Backend Setup (Django)

```bash
cd causalproject
..\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py runserver
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

## Development Commands

### Backend

```bash
cd causalproject
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
