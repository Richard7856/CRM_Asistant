# Deploy Check

Pre-deploy verification — ensure everything compiles, no sensitive files exposed, frontend builds clean.

## Steps

1. **Check for sensitive files in git staging** — Run `git status` and verify NO `.env`, `credentials`, API keys, or `node_modules` are staged. If found, warn immediately and do NOT proceed.

2. **Verify all Python files parse** — For every `.py` file in `backend/app/`, verify syntax with `ast.parse()`. Report any that fail.

3. **Verify backend imports** — Using the venv Python (`.venv/bin/python`), run `from app.main import app` to ensure the full import chain works. This catches missing dependencies and circular imports.

4. **Check for TODO/FIXME markers** — Grep for `TODO`, `FIXME`, `XXX`, `HACK` across `backend/app/` and `frontend/src/`. List them so the user can decide if any are blockers.

5. **Frontend type check** — From `frontend/`, run `npx tsc --noEmit` to verify TypeScript compiles without errors. Report any type errors.

6. **Frontend build** — Run `npm run build` from `frontend/`. This catches any build-time errors (missing imports, JSX issues, Vite config problems).

7. **Check git diff summary** — Show a `git diff --stat HEAD` so the user sees exactly what's about to be pushed.

8. **Report** — Summary table: each check (Python syntax, imports, sensitive files, TS types, build) with pass/fail. If all pass, tell the user it's safe to commit and push.
