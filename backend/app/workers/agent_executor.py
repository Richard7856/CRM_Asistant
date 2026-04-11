"""
Agent Execution Engine — the core of the CRM Agents MVP.

Unified dispatcher: detects agent origin and routes accordingly.
- Internal agents: calls Claude API with the agent's system prompt + model config
- External agents: dispatches via platform adapter (n8n, CrewAI, LangChain, etc.)

Pipeline: assigned → in_progress → completed/failed
Each step creates an ActivityLog entry for full visibility.
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# Retry config for Claude API calls.
# Retries on overload (529), rate limit (429), and transient server errors (500+).
# Backoff: 1s → 2s → 4s — total max wait ~7s before giving up.
_MAX_RETRIES = 3
_BASE_BACKOFF_SECONDS = 1.0
_API_TIMEOUT_SECONDS = 90  # hard cap — if Claude hasn't responded in 90s, fail the task

from app.activities.models import ActivityLog, LogLevel
from app.agents.models import Agent, AgentOrigin, AgentStatus
from app.config import settings
from app.core.events import Event, event_bus
from app.tasks.models import Task, TaskStatus

logger = logging.getLogger(__name__)

# Anthropic client — initialized lazily so tests don't need a real key
_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def _emit(event_type: str, data: dict) -> None:
    """Publish an event to SSE subscribers."""
    await event_bus.publish(Event(type=event_type, data=data))


async def _log_activity(
    db: AsyncSession,
    agent_id: uuid.UUID,
    task_id: uuid.UUID,
    action: str,
    level: LogLevel,
    summary: str,
    details: dict | None = None,
    organization_id: uuid.UUID | None = None,
) -> None:
    """Helper to create an activity log entry.
    organization_id is required by the DB NOT NULL constraint — always pass agent.organization_id.
    """
    log = ActivityLog(
        agent_id=agent_id,
        task_id=task_id,
        action=action,
        level=level,
        summary=summary,
        details=details or {},
        organization_id=organization_id,
    )
    db.add(log)
    await db.flush()


async def _retrieve_rag_context(
    agent: "Agent",
    query: str,
    db: AsyncSession,
    top_k: int = 5,
) -> tuple[str | None, int]:
    """
    Retrieve relevant knowledge chunks for the agent's task using full-text search.
    Returns (formatted_context_string | None, chunks_found_count).

    Fail-open: if retrieval fails for any reason, returns (None, 0) so
    task execution continues with the original system prompt.

    Searches org-level KB + dept-level KB for the agent's department.
    """
    try:
        from app.knowledge.repository import KnowledgeRepository
        repo = KnowledgeRepository(db, agent.organization_id)
        results = await repo.search(
            query=query,
            department_id=agent.department_id,
            limit=top_k,
        )
        if not results:
            return None, 0

        sections = []
        for chunk, rank in results:
            sections.append(f"[Relevancia: {rank:.3f}]\n{chunk.content}")

        context = "\n\n---\n\n".join(sections)
        return context, len(results)
    except Exception as exc:
        logger.warning("RAG retrieval failed (non-fatal): %s", exc)
        return None, 0


async def execute_task(task_id: uuid.UUID, db: AsyncSession) -> Task:
    """
    Execute a task using its assigned agent.

    Detects agent origin and routes to the right execution path:
    - INTERNAL → Claude API call with system prompt + task description
    - EXTERNAL → dispatch via platform adapter (webhook/API)
    """

    # 1. Load task
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise ValueError(f"Task {task_id} not found")

    if task.assigned_to is None:
        raise ValueError(f"Task {task_id} has no assigned agent")

    # Load agent with definition + integration (need both to decide route)
    agent_result = await db.execute(
        select(Agent)
        .options(
            selectinload(Agent.definition),
            selectinload(Agent.integration),
        )
        .where(Agent.id == task.assigned_to)
    )
    agent = agent_result.scalar_one_or_none()
    if agent is None:
        raise ValueError(f"Agent {task.assigned_to} not found")

    # Route based on agent origin
    if agent.origin == AgentOrigin.INTERNAL:
        await _execute_internal(task, agent, db)
    else:
        await _execute_external(task, agent, db)

    await db.commit()
    await db.refresh(task)
    return task


async def execute_task_background(task_id: uuid.UUID) -> None:
    """
    Execute a task in a background coroutine with its own DB session.

    Called via asyncio.create_task() from the router so the HTTP request
    returns immediately (202). The result reaches the frontend through
    the SSE EventBus — no polling needed.

    Each background execution opens and closes its own session to avoid
    sharing the request's session (which closes when the endpoint returns).
    """
    from app.core.database import async_session_factory

    async with async_session_factory() as db:
        try:
            await execute_task(task_id, db)
        except Exception as exc:
            # execute_task already logs errors and emits SSE events internally,
            # but if something fails BEFORE it gets to the agent routing
            # (e.g. task not found, no agent assigned) we catch it here
            # so the background task doesn't crash silently.
            logger.error("Background execution failed for task %s: %s", task_id, exc)
            await _emit("task.failed", {
                "task_id": str(task_id),
                "error": str(exc)[:200],
            })


# ------------------------------------------------------------------
# Internal agent execution (Claude API)
# ------------------------------------------------------------------


async def _call_claude_with_retry(
    client: anthropic.AsyncAnthropic,
    **kwargs,
) -> anthropic.types.Message:
    """
    Call Claude API with retry + timeout protection.

    Retries on transient errors (overload 529, rate limit 429, server 500+).
    Non-retryable errors (400 bad request, 401 auth) fail immediately.
    Hard timeout of 90s per attempt — if Claude hangs, we don't hang with it.
    """
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            return await asyncio.wait_for(
                client.messages.create(**kwargs),
                timeout=_API_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            last_exc = TimeoutError(
                f"Claude API did not respond within {_API_TIMEOUT_SECONDS}s (attempt {attempt + 1}/{_MAX_RETRIES})"
            )
            logger.warning("Claude API timeout on attempt %d/%d", attempt + 1, _MAX_RETRIES)
        except anthropic.RateLimitError as exc:
            last_exc = exc
            logger.warning("Claude API rate limited (429) on attempt %d/%d", attempt + 1, _MAX_RETRIES)
        except anthropic.InternalServerError as exc:
            # Covers 500 and 529 (overloaded)
            last_exc = exc
            logger.warning("Claude API server error on attempt %d/%d: %s", attempt + 1, _MAX_RETRIES, exc)
        except anthropic.APIError as exc:
            # Non-retryable API errors (400, 401, 403) — fail immediately
            raise

        # Exponential backoff: 1s, 2s, 4s
        if attempt < _MAX_RETRIES - 1:
            backoff = _BASE_BACKOFF_SECONDS * (2 ** attempt)
            logger.info("Retrying Claude API in %.1fs...", backoff)
            await asyncio.sleep(backoff)

    raise last_exc or RuntimeError("Claude API failed after all retries")


async def _execute_internal(task: Task, agent: Agent, db: AsyncSession) -> None:
    """Execute task via Claude API using the agent's definition."""
    definition = agent.definition
    if definition is None:
        raise ValueError(f"Agent {agent.name} has no definition (no system prompt configured)")

    # Mark task as in_progress, agent as busy
    task.status = TaskStatus.IN_PROGRESS
    task.started_at = datetime.utcnow()
    agent.status = AgentStatus.BUSY
    await db.flush()

    await _log_activity(
        db, agent.id, task.id,
        action="task_started",
        level=LogLevel.INFO,
        summary=f"Iniciando tarea: {task.title}",
        details={"model": definition.model_name, "temperature": float(definition.temperature)},
        organization_id=agent.organization_id,
    )

    await _emit("task.started", {
        "task_id": str(task.id), "title": task.title,
        "agent_id": str(agent.id), "agent_name": agent.name,
    })

    start_time = time.time()
    try:
        client = _get_client()

        # Build the user message from the task
        user_message = f"## Tarea: {task.title}\n\n"
        if task.description:
            user_message += task.description

        model = definition.model_name or "claude-sonnet-4-20250514"
        max_tokens = definition.max_tokens or 4096
        temperature = float(definition.temperature) if definition.temperature is not None else 0.7

        # RAG: retrieve relevant knowledge chunks and inject into system prompt
        rag_query = f"{task.title} {task.description or ''}".strip()
        rag_context, rag_chunks_found = await _retrieve_rag_context(agent, rag_query, db)

        system_prompt = definition.system_prompt or "Eres un agente de IA asistente."
        if rag_context:
            system_prompt = (
                system_prompt
                + "\n\n<knowledge_base>\n"
                + "La siguiente información de la base de conocimiento de la empresa es relevante para esta tarea. "
                + "Úsala como contexto al responder:\n\n"
                + rag_context
                + "\n</knowledge_base>"
            )
            logger.info(
                "RAG: injected %d knowledge chunks for task %s (agent %s)",
                rag_chunks_found, task.id, agent.name,
            )

        response = await _call_claude_with_retry(
            client,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        elapsed_ms = int((time.time() - start_time) * 1000)

        # Extract the text response
        output_text = ""
        for block in response.content:
            if block.type == "text":
                output_text += block.text

        # Store result, mark completed
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.utcnow()
        task.result = {
            "output": output_text,
            "model": response.model,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            "elapsed_ms": elapsed_ms,
            "stop_reason": response.stop_reason,
        }

        agent.status = AgentStatus.ACTIVE
        agent.last_heartbeat_at = datetime.utcnow()
        await db.flush()

        await _log_activity(
            db, agent.id, task.id,
            action="task_completed",
            level=LogLevel.INFO,
            summary=f"Tarea completada en {elapsed_ms}ms — {response.usage.input_tokens + response.usage.output_tokens} tokens",
            details={
                "elapsed_ms": elapsed_ms,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "model": response.model,
                "stop_reason": response.stop_reason,
                "rag_chunks_retrieved": rag_chunks_found,
            },
            organization_id=agent.organization_id,
        )

        await _emit("task.completed", {
            "task_id": str(task.id), "title": task.title,
            "agent_id": str(agent.id), "agent_name": agent.name,
            "elapsed_ms": elapsed_ms,
            "tokens": response.usage.input_tokens + response.usage.output_tokens,
        })

        logger.info(
            "Task %s completed by agent %s in %dms (%d tokens)",
            task.id, agent.name, elapsed_ms,
            response.usage.input_tokens + response.usage.output_tokens,
        )

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        _mark_task_failed(task, agent, str(e), type(e).__name__, elapsed_ms)
        await db.flush()

        await _emit("task.failed", {
            "task_id": str(task.id), "title": task.title,
            "agent_id": str(agent.id), "agent_name": agent.name,
            "error": str(e)[:200],
        })

        await _log_activity(
            db, agent.id, task.id,
            action="task_failed",
            level=LogLevel.ERROR,
            summary=f"Error ejecutando tarea: {str(e)[:200]}",
            details={"error": str(e), "error_type": type(e).__name__, "elapsed_ms": elapsed_ms},
            organization_id=agent.organization_id,
        )
        logger.error("Task %s failed for agent %s: %s", task.id, agent.name, e)


# ------------------------------------------------------------------
# External agent execution (platform adapter dispatch)
# ------------------------------------------------------------------


async def _execute_external(task: Task, agent: Agent, db: AsyncSession) -> None:
    """Dispatch task to an external agent via its platform adapter."""
    from app.integrations.adapters import AdapterRegistry

    integration = agent.integration
    if integration is None:
        raise ValueError(f"Agent {agent.name} has no external integration configured")
    if not integration.is_active:
        raise ValueError(f"Integration for agent {agent.name} is inactive")

    # Mark task as in_progress, agent as busy
    task.status = TaskStatus.IN_PROGRESS
    task.started_at = datetime.utcnow()
    agent.status = AgentStatus.BUSY
    await db.flush()

    platform = integration.platform or "generic"

    await _log_activity(
        db, agent.id, task.id,
        action="task_dispatched",
        level=LogLevel.INFO,
        summary=f"Despachando tarea a agente externo ({platform}): {task.title}",
        details={"platform": platform, "endpoint": integration.endpoint_url},
        organization_id=agent.organization_id,
    )

    await _emit("task.dispatched", {
        "task_id": str(task.id), "title": task.title,
        "agent_id": str(agent.id), "agent_name": agent.name,
        "platform": platform,
    })

    start_time = time.time()
    try:
        adapter = AdapterRegistry.get(platform)

        # Build task payload for the external agent
        task_data = {
            "task_id": str(task.id),
            "title": task.title,
            "description": task.description or "",
            "priority": task.priority.value if task.priority else "medium",
            # Callback URL so external agent can report results back
            "callback_url": f"/api/v1/integrations/webhook/{platform}",
        }

        result = await adapter.send_task(
            endpoint_url=integration.endpoint_url or "",
            task_data=task_data,
            config=integration.config or {},
        )

        elapsed_ms = int((time.time() - start_time) * 1000)

        if result.success:
            # Task dispatched — stays in_progress until webhook callback arrives
            # Store dispatch metadata so we can correlate the webhook response
            task.result = {
                "dispatch_status": "sent",
                "platform": platform,
                "external_id": result.external_id,
                "message": result.message,
                "elapsed_ms": elapsed_ms,
                "response_data": result.response_data,
            }
            agent.last_heartbeat_at = datetime.utcnow()
            await db.flush()

            await _log_activity(
                db, agent.id, task.id,
                action="task_dispatch_success",
                level=LogLevel.INFO,
                summary=f"Tarea enviada a {platform} en {elapsed_ms}ms — esperando resultado",
                details={
                    "external_id": result.external_id,
                    "elapsed_ms": elapsed_ms,
                    "platform": platform,
                },
                organization_id=agent.organization_id,
            )
            logger.info(
                "Task %s dispatched to external agent %s (%s) in %dms",
                task.id, agent.name, platform, elapsed_ms,
            )
        else:
            # Dispatch itself failed — mark task as failed
            _mark_task_failed(task, agent, result.message, "DispatchError", elapsed_ms)
            task.result["platform"] = platform
            await db.flush()

            await _log_activity(
                db, agent.id, task.id,
                action="task_dispatch_failed",
                level=LogLevel.ERROR,
                summary=f"Error despachando a {platform}: {result.message[:200]}",
                details={
                    "error": result.message,
                    "elapsed_ms": elapsed_ms,
                    "platform": platform,
                },
                organization_id=agent.organization_id,
            )
            logger.error("Task %s dispatch failed for agent %s: %s", task.id, agent.name, result.message)

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        _mark_task_failed(task, agent, str(e), type(e).__name__, elapsed_ms)
        await db.flush()

        await _log_activity(
            db, agent.id, task.id,
            action="task_dispatch_failed",
            level=LogLevel.ERROR,
            summary=f"Error despachando tarea: {str(e)[:200]}",
            details={"error": str(e), "error_type": type(e).__name__, "elapsed_ms": elapsed_ms},
            organization_id=agent.organization_id,
        )
        logger.error("Task %s dispatch error for agent %s: %s", task.id, agent.name, e)


# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------


def _mark_task_failed(
    task: Task, agent: Agent, error_msg: str, error_type: str, elapsed_ms: int
) -> None:
    """Set task to failed and agent to error state."""
    task.status = TaskStatus.FAILED
    task.completed_at = datetime.utcnow()
    task.result = {
        "error": error_msg,
        "error_type": error_type,
        "elapsed_ms": elapsed_ms,
    }
    agent.status = AgentStatus.ERROR
