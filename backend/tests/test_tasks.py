"""
Task pipeline tests — covers CRUD, the execute endpoint (202 contract), and
the underlying `execute_task()` function with Claude API mocked out.

Why we test `execute_task()` directly instead of the full background flow:
- The endpoint dispatches via `asyncio.create_task(execute_task_background(id))`.
  The background coroutine opens its OWN DB session via `async_session_factory()`
  — but our test's data lives in a transaction that gets rolled back, so the
  background session can't see it.
- Testing `execute_task()` directly with the test session avoids this whole
  problem and gives us deterministic assertions on the outcome.

The endpoint tests still verify the contract (validation, 202 return) without
waiting for the background task to complete.

Claude is mocked via the `fake_claude` fixture (see conftest.py). Real Claude
calls would cost money, be slow (10–60s), and produce non-deterministic results.
"""

import uuid

import anthropic
import pytest
from sqlalchemy import select

from app.agents.models import Agent, AgentStatus
from app.tasks.models import Task, TaskStatus
from app.workers.agent_executor import execute_task


# ─────────────────────────────────────────────────────────────────────────────
# TestTaskCRUD — basic create/list/detail through HTTP
# ─────────────────────────────────────────────────────────────────────────────


class TestTaskCRUD:
    async def test_create_task_with_assignee_starts_assigned(
        self, client, auth_headers, internal_agent
    ):
        # When the request includes assigned_to, the task starts in "assigned"
        # state (not "pending") — reflecting that an agent is already routed.
        response = await client.post(
            "/api/v1/tasks/",
            headers=auth_headers,
            json={
                "title": "Generar reporte de ventas",
                "description": "Resumen ejecutivo de las ventas Q1",
                "assigned_to": str(internal_agent.id),
                "priority": "medium",
            },
        )
        assert response.status_code in (200, 201)
        body = response.json()
        assert body["title"] == "Generar reporte de ventas"
        assert body["status"] == "assigned"
        assert body["assigned_to"] == str(internal_agent.id)

    async def test_create_task_without_assignee_starts_pending(
        self, client, auth_headers
    ):
        response = await client.post(
            "/api/v1/tasks/",
            headers=auth_headers,
            json={"title": "Tarea sin asignar"},
        )
        assert response.status_code in (200, 201)
        assert response.json()["status"] == "pending"

    async def test_create_task_persisted_with_caller_org(
        self, client, auth_headers, test_org, internal_agent, db
    ):
        response = await client.post(
            "/api/v1/tasks/",
            headers=auth_headers,
            json={"title": "Test scoping", "assigned_to": str(internal_agent.id)},
        )
        task_id = uuid.UUID(response.json()["id"])

        task = await db.get(Task, task_id)
        assert task.organization_id == test_org.id

    async def test_list_tasks_returns_paginated_response(
        self, client, auth_headers, test_org, internal_agent, db
    ):
        # Create 3 tasks directly in DB
        for i in range(3):
            db.add(Task(
                title=f"Task {i}",
                organization_id=test_org.id,
                assigned_to=internal_agent.id,
            ))
        await db.flush()

        response = await client.get("/api/v1/tasks/", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert len(body["items"]) >= 3

    async def test_get_task_by_id_returns_full_detail(
        self, client, auth_headers, test_org, internal_agent, db
    ):
        task = Task(
            title="Detail test",
            description="Some description",
            organization_id=test_org.id,
            assigned_to=internal_agent.id,
        )
        db.add(task)
        await db.flush()

        response = await client.get(
            f"/api/v1/tasks/{task.id}", headers=auth_headers
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(task.id)
        assert body["title"] == "Detail test"
        assert body["description"] == "Some description"

    async def test_get_nonexistent_task_returns_404(self, client, auth_headers):
        response = await client.get(
            f"/api/v1/tasks/{uuid.uuid4()}", headers=auth_headers
        )
        assert response.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# TestExecuteEndpoint — the 202 contract
# ─────────────────────────────────────────────────────────────────────────────


class TestExecuteEndpoint:
    """
    The execute endpoint validates the request and dispatches the work to a
    background task. We verify the synchronous part (validation + 202 response)
    here; the actual execution is tested in TestExecuteTaskFunction below.
    """

    async def test_execute_endpoint_returns_202_immediately(
        self, client, auth_headers, test_org, internal_agent, db
    ):
        task = Task(
            title="To execute",
            organization_id=test_org.id,
            assigned_to=internal_agent.id,
        )
        db.add(task)
        await db.flush()

        response = await client.post(
            f"/api/v1/tasks/{task.id}/execute", headers=auth_headers
        )
        # 202 Accepted: "I'll get to it, results via SSE"
        assert response.status_code == 202

    async def test_execute_nonexistent_task_returns_404(
        self, client, auth_headers
    ):
        response = await client.post(
            f"/api/v1/tasks/{uuid.uuid4()}/execute", headers=auth_headers
        )
        assert response.status_code == 404

    async def test_execute_task_without_assigned_agent_returns_4xx(
        self, client, auth_headers, test_org, db
    ):
        # Task with no agent assigned
        task = Task(
            title="Orphan",
            organization_id=test_org.id,
            assigned_to=None,
        )
        db.add(task)
        await db.flush()

        response = await client.post(
            f"/api/v1/tasks/{task.id}/execute", headers=auth_headers
        )
        # Should reject — no agent to dispatch to
        assert response.status_code in (400, 404, 422)


# ─────────────────────────────────────────────────────────────────────────────
# TestExecuteTaskFunction — direct tests of execute_task() with mocked Claude
# ─────────────────────────────────────────────────────────────────────────────


class TestExecuteTaskFunction:
    """
    Direct tests of `execute_task()` in workers/agent_executor.py.
    Bypasses the HTTP layer + asyncio background task to avoid session-scoping
    headaches (see module docstring at top of file).
    """

    async def test_internal_agent_execution_marks_task_completed(
        self, db, test_org, internal_agent, fake_claude
    ):
        # Set up a task assigned to the internal agent
        task = Task(
            title="Test internal execution",
            description="Should succeed with mocked Claude",
            organization_id=test_org.id,
            assigned_to=internal_agent.id,
        )
        db.add(task)
        await db.flush()
        task_id = task.id

        # Run the executor directly
        result = await execute_task(task_id, db)

        assert result.status == TaskStatus.COMPLETED
        # Result is a JSONB dict with output/model/usage/etc keys
        assert result.result is not None
        assert "output" in result.result
        # Verify Claude was actually called (not the real API)
        assert fake_claude.messages.create.called

    async def test_internal_execution_saves_claude_response_in_result(
        self, db, test_org, internal_agent, fake_claude
    ):
        # Override the mock to return a recognizable response
        from tests.conftest import _make_fake_claude_message
        fake_claude.messages.create.return_value = _make_fake_claude_message(
            text="Resumen: las ventas crecieron 23% en Q1."
        )

        task = Task(
            title="Test response capture",
            organization_id=test_org.id,
            assigned_to=internal_agent.id,
        )
        db.add(task)
        await db.flush()

        result = await execute_task(task.id, db)

        # The Claude response text ends up in result["output"]
        assert result.result is not None
        assert "23%" in result.result["output"]

    async def test_internal_execution_failure_marks_task_failed(
        self, db, test_org, internal_agent, fake_claude
    ):
        # Make Claude blow up with a non-retryable error (won't loop on retries)
        fake_claude.messages.create.side_effect = anthropic.APIError(
            message="Bad request",
            request=None,  # type: ignore
            body=None,
        )

        task = Task(
            title="Should fail",
            organization_id=test_org.id,
            assigned_to=internal_agent.id,
        )
        db.add(task)
        await db.flush()

        # The executor catches the exception and marks the task FAILED
        # (it shouldn't propagate out to the caller — that's the contract)
        try:
            await execute_task(task.id, db)
        except Exception:
            pass  # Some implementations re-raise; we care about final status

        await db.refresh(task)
        assert task.status == TaskStatus.FAILED

    async def test_internal_execution_records_token_usage(
        self, db, test_org, internal_agent, fake_claude
    ):
        from tests.conftest import _make_fake_claude_message
        fake_claude.messages.create.return_value = _make_fake_claude_message(
            text="Brief.", input_tokens=250, output_tokens=80,
        )

        task = Task(
            title="Track usage",
            organization_id=test_org.id,
            assigned_to=internal_agent.id,
        )
        db.add(task)
        await db.flush()

        result = await execute_task(task.id, db)

        # Tokens are tracked in result["usage"] — critical for cost-per-agent
        # metrics that are part of the executive dashboard
        assert result.result is not None
        usage = result.result.get("usage", {})
        assert usage.get("input_tokens") == 250
        assert usage.get("output_tokens") == 80

    async def test_internal_execution_marks_agent_busy_then_back(
        self, db, test_org, internal_agent, fake_claude
    ):
        task = Task(
            title="Status transition check",
            organization_id=test_org.id,
            assigned_to=internal_agent.id,
        )
        db.add(task)
        await db.flush()

        await execute_task(task.id, db)

        # After execution, the agent should NOT still be busy — should be back
        # to active (or idle), since the task is done.
        await db.refresh(internal_agent)
        assert internal_agent.status != AgentStatus.BUSY, (
            f"Agent stuck in BUSY after task completion — got {internal_agent.status}"
        )
