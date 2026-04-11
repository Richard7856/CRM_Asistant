# Test Backend

Run a full backend smoke test: verify imports, start uvicorn, test key endpoints, then shut down.

## Steps

1. **Verify Python imports compile** — Run `python3 -c "import ast; ast.parse(open('app/main.py').read())"` from the backend directory using the venv Python (`.venv/bin/python`). If this fails, there's a syntax error — fix it before proceeding.

2. **Check PostgreSQL is running** — Run `pg_isready -h localhost -p 5432`. If not running, tell the user to start it.

3. **Start uvicorn in background** — From `backend/`, activate venv and run `uvicorn app.main:app --host 127.0.0.1 --port 8000` in background. Wait 4 seconds for startup.

4. **Test health endpoint** — `GET /health` should return 200 with `{"status":"healthy"}`.

5. **Test login** — `POST /api/v1/auth/login` with `{"email":"richard@crmagents.io","password":"admin123"}`. Should return 200 with an access_token.

6. **Test a protected endpoint** — Using the token from step 5, `GET /api/v1/agents/?size=1`. Should return 200 with agent data.

7. **Test task execute returns 202** — If there's an existing task with an assigned agent, `POST /api/v1/tasks/{id}/execute`. Should return 202 (Accepted), NOT 200.

8. **Kill the server** — `kill $(lsof -t -i:8000)` or similar.

9. **Report results** — Show a summary table of each test (endpoint, expected status, actual status, pass/fail).

If any test fails, diagnose the error and suggest a fix. Do NOT commit if tests fail.
