# CRM Agents — Project Instructions

## What this is
CRM for managing AI agents like employees — departments, roles, tasks, performance metrics, knowledge base. Multi-tenant, real-time via SSE.

## Stack
- **Backend:** Python 3.12 + FastAPI + SQLAlchemy async + PostgreSQL 16
- **Frontend:** React 19 + TypeScript + Vite 6 + Tailwind 4 + Zustand + React Query
- **LLM:** Claude API (anthropic SDK) for internal agent execution
- **DB:** PostgreSQL local (brew), user `richardfigueroa`, no password, database `crm_agents`

## How to run

### Backend
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm run dev  # port 5173
```

### Database
PostgreSQL must be running locally (`pg_isready` to check). Migrations via Alembic:
```bash
cd backend && source .venv/bin/activate
alembic upgrade head
```

## Critical: iCloud Drive quirks
This repo lives in iCloud Drive. Two known issues:
1. **Python .so binaries can corrupt** — if `import pydantic` hangs, reinstall with: `~/.local/bin/uv pip install --reinstall pydantic-core`
2. **`python -m http.server` fails** on paths with spaces — use `/tmp` as workaround for static file serving
3. **The venv uses Python 3.12 via uv** (not the system Python 3.9 or 3.13). The `uv` binary is at `~/.local/bin/uv`. There is no `pip` in the venv — always use `~/.local/bin/uv pip install`.

## Project structure (backend)
Each domain module follows the same pattern: `models.py` -> `repository.py` -> `service.py` -> `router.py` -> `schemas.py`

Modules: `agents`, `auth`, `departments`, `tasks`, `activities`, `metrics`, `interactions`, `improvements`, `integrations`, `prompts`, `events`, `knowledge`

Core: `core/database.py` (async engine + session factory), `core/events.py` (SSE EventBus), `core/middleware.py` (timing), `workers/` (background tasks)

## Project structure (frontend)
`src/features/` — one folder per domain (agents, tasks, dashboard, metrics, etc.)
`src/api/` — axios client + typed API functions
`src/components/` — shared UI (charts, layout, common)
`src/hooks/` — useEventStream (SSE), useDebounce
`src/store/` — Zustand auth store

## Architecture patterns

### Task execution is async
`POST /tasks/{id}/execute` returns **202 immediately**. Execution runs in background via `asyncio.create_task()` with its own DB session. Results arrive via SSE events (`task.completed` / `task.failed`). See `workers/agent_executor.py`.

### Multi-tenant
Every table has `organization_id`. Every query filters by `org_id` from the JWT. No row-level security in Postgres — isolation is enforced in the service layer.

### Agent duality
An agent is either `internal` (has `AgentDefinition` with system prompt + model config, executes via Claude API) or `external` (has `AgentIntegration` with endpoint URL, dispatches via webhook adapter).

### SSE EventBus
In-memory fan-out (`core/events.py`). Single process only. Each browser tab gets its own asyncio.Queue. Events: task lifecycle, agent status changes.

### RAG
PostgreSQL full-text search (tsvector + GIN). Two scopes: org-wide and per-department. Agent executor auto-injects matching KB chunks into system prompt before calling Claude.

### Background workers
3 asyncio tasks in the FastAPI lifespan (NOT Celery):
- `metrics_calculator` — hourly KPI aggregation
- `heartbeat_monitor` — 60s agent liveness check
- `integration_health_checker` — 5min external endpoint health

## Auth
JWT (python-jose) + bcrypt. Login: `POST /api/v1/auth/login` with `{email, password}`. Test user: `richard@crmagents.io`. Protected routes require `Authorization: Bearer <token>`.

## Coding conventions
- Comments explain WHY, never WHAT
- Functions: `verb_noun` (get_user, validate_token)
- Booleans: `is_`/`has_`/`can_` prefix
- All non-trivial decisions go in `DECISIONS.md`
- Commits: `type(scope): description` (feat, fix, refactor, docs)
- Spanish in user-facing content and log messages, English in code and comments

## Don't repeat these mistakes
- Never use system `python3` (3.9) for backend work — always activate the venv or use `.venv/bin/python`
- Never run `pip install` — use `~/.local/bin/uv pip install`
- Never serve static files from the iCloud path directly — copy to `/tmp` first
- The DB pool is `pool_size=10, max_overflow=20` (30 total). Each concurrent task uses ~2 connections. Monitor if running 50+ tasks.
