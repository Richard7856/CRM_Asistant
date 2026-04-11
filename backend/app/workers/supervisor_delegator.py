"""
Supervisor Delegator — Claude as planner for multi-agent task decomposition.

When a task is assigned to a supervisor agent, this module:
1. Asks Claude to analyze the task and decide which subordinates should handle it
2. Creates subtasks for each subordinate
3. Executes subtasks in parallel
4. Asks the supervisor to aggregate results into a final deliverable

The supervisor never executes the task directly — it coordinates.
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.activities.models import ActivityLog, LogLevel
from app.agents.models import Agent, AgentStatus
from app.auth.models import Organization  # noqa: F401 — needed for Agent relationship resolution
from app.core.events import Event, event_bus
from app.tasks.models import Task, TaskStatus
from app.workers.agent_executor import (
    _call_claude_with_retry,
    _emit,
    _get_client,
    _log_activity,
    _mark_task_failed,
    _retrieve_rag_context,
    execute_task,
)

logger = logging.getLogger(__name__)


# Tool definition for Claude to delegate subtasks
DELEGATE_TOOL = {
    "name": "delegate_subtasks",
    "description": (
        "Delega subtareas a los agentes subordinados disponibles. "
        "Cada subtarea se asigna a un agente específico por su slug. "
        "Puedes crear múltiples subtareas para diferentes agentes, "
        "o múltiples subtareas para el mismo agente si necesitas varias piezas."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "plan_summary": {
                "type": "string",
                "description": "Resumen breve del plan de delegación (1-2 oraciones)",
            },
            "subtasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "agent_slug": {
                            "type": "string",
                            "description": "Slug del agente subordinado que ejecutará esta subtarea",
                        },
                        "title": {
                            "type": "string",
                            "description": "Título conciso de la subtarea",
                        },
                        "description": {
                            "type": "string",
                            "description": (
                                "Instrucciones detalladas para el agente. "
                                "Incluye contexto, requisitos específicos, y formato esperado."
                            ),
                        },
                    },
                    "required": ["agent_slug", "title", "description"],
                },
                "minItems": 1,
            },
        },
        "required": ["plan_summary", "subtasks"],
    },
}


async def delegate_task_background(task_id: uuid.UUID) -> None:
    """Background wrapper for delegate_task — mirrors execute_task_background pattern."""
    from app.core.database import async_session_factory

    async with async_session_factory() as db:
        try:
            await delegate_task(task_id, db)
        except Exception as exc:
            logger.error("Background delegation failed for task %s: %s", task_id, exc)
            await _emit("task.failed", {
                "task_id": str(task_id),
                "error": str(exc)[:200],
            })


async def delegate_task(task_id: uuid.UUID, db: AsyncSession) -> Task:
    """
    Supervisor delegation flow:
    1. Load supervisor + subordinates
    2. Ask Claude to plan delegation (tool_use)
    3. Create and execute subtasks
    4. Aggregate results via supervisor
    """
    # Load task
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise ValueError(f"Task {task_id} not found")

    # Load supervisor with definition and subordinates
    agent_result = await db.execute(
        select(Agent)
        .options(
            selectinload(Agent.definition),
            selectinload(Agent.subordinates).selectinload(Agent.definition),
        )
        .where(Agent.id == task.assigned_to)
    )
    supervisor = agent_result.scalar_one_or_none()
    if supervisor is None:
        raise ValueError(f"Supervisor agent {task.assigned_to} not found")

    if not supervisor.subordinates:
        # No subordinates — fall back to direct execution
        logger.info("Supervisor %s has no subordinates, executing directly", supervisor.name)
        return await execute_task(task_id, db)

    definition = supervisor.definition
    if definition is None:
        raise ValueError(f"Supervisor {supervisor.name} has no definition")

    # Mark parent task in progress
    task.status = TaskStatus.IN_PROGRESS
    task.started_at = datetime.utcnow()
    supervisor.status = AgentStatus.BUSY
    await db.flush()

    await _log_activity(
        db, supervisor.id, task.id,
        action="delegation_started",
        level=LogLevel.INFO,
        summary=f"Supervisor planificando delegación: {task.title}",
        details={"subordinates": [s.slug for s in supervisor.subordinates]},
        organization_id=supervisor.organization_id,
    )

    await _emit("task.delegation_started", {
        "task_id": str(task.id), "title": task.title,
        "supervisor_id": str(supervisor.id), "supervisor_name": supervisor.name,
        "subordinate_count": len(supervisor.subordinates),
    })

    start_time = time.time()

    try:
        # ── Phase 1: Ask Claude to plan the delegation ──
        subtask_specs = await _plan_delegation(task, supervisor, db)

        # ── Phase 2: Create and execute subtasks ──
        subtask_results = await _execute_subtasks(
            task, supervisor, subtask_specs, db,
        )

        # ── Phase 3: Aggregate results ──
        final_output = await _aggregate_results(
            task, supervisor, subtask_results, db,
        )

        elapsed_ms = int((time.time() - start_time) * 1000)

        # Mark parent task completed with aggregated result
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.utcnow()
        task.result = final_output
        task.result["elapsed_ms"] = elapsed_ms
        task.result["delegation"] = {
            "subtasks_created": len(subtask_specs),
            "subtasks_completed": sum(
                1 for r in subtask_results if r.get("status") == "completed"
            ),
            "subtasks_failed": sum(
                1 for r in subtask_results if r.get("status") == "failed"
            ),
        }

        supervisor.status = AgentStatus.ACTIVE
        supervisor.last_heartbeat_at = datetime.utcnow()
        await db.flush()

        await _log_activity(
            db, supervisor.id, task.id,
            action="delegation_completed",
            level=LogLevel.INFO,
            summary=f"Delegación completada en {elapsed_ms}ms — {len(subtask_specs)} subtareas",
            details=task.result["delegation"],
            organization_id=supervisor.organization_id,
        )

        await _emit("task.completed", {
            "task_id": str(task.id), "title": task.title,
            "agent_id": str(supervisor.id), "agent_name": supervisor.name,
            "elapsed_ms": elapsed_ms,
            "delegation": task.result["delegation"],
        })

        logger.info(
            "Delegation for task %s completed by %s in %dms (%d subtasks)",
            task.id, supervisor.name, elapsed_ms, len(subtask_specs),
        )

        await db.commit()
        await db.refresh(task)
        return task

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        _mark_task_failed(task, supervisor, str(e), type(e).__name__, elapsed_ms)
        await db.flush()

        await _emit("task.failed", {
            "task_id": str(task.id), "title": task.title,
            "agent_id": str(supervisor.id), "agent_name": supervisor.name,
            "error": str(e)[:200],
        })

        await _log_activity(
            db, supervisor.id, task.id,
            action="delegation_failed",
            level=LogLevel.ERROR,
            summary=f"Error en delegación: {str(e)[:200]}",
            details={"error": str(e), "error_type": type(e).__name__, "elapsed_ms": elapsed_ms},
            organization_id=supervisor.organization_id,
        )

        await db.commit()
        await db.refresh(task)
        return task


async def _plan_delegation(
    task: Task,
    supervisor: Agent,
    db: AsyncSession,
) -> list[dict]:
    """
    Phase 1: Ask Claude (as the supervisor) to analyze the task and decide
    which subordinates should handle which parts.

    Uses tool_use so Claude returns structured JSON — no parsing gymnastics.
    """
    # Build subordinate descriptions for Claude
    subordinate_info = []
    for sub in supervisor.subordinates:
        caps = ", ".join(sub.capabilities or [])
        subordinate_info.append(
            f"- **{sub.name}** (slug: `{sub.slug}`): {sub.description or 'Sin descripción'}. "
            f"Capacidades: {caps or 'generales'}."
        )
    subordinates_text = "\n".join(subordinate_info)

    # RAG context for the supervisor
    rag_query = f"{task.title} {task.description or ''}".strip()
    rag_context, rag_chunks, _rag_sources = await _retrieve_rag_context(supervisor, rag_query, db)

    system_prompt = supervisor.definition.system_prompt or ""
    if rag_context:
        system_prompt += (
            "\n\n<knowledge_base>\n"
            "Información relevante de la base de conocimiento:\n\n"
            + rag_context
            + "\n</knowledge_base>"
        )

    user_message = (
        f"## Tarea recibida: {task.title}\n\n"
        f"{task.description or 'Sin descripción adicional.'}\n\n"
        f"## Tu equipo disponible\n{subordinates_text}\n\n"
        "Analiza la tarea y usa la herramienta `delegate_subtasks` para asignar "
        "subtareas a los miembros de tu equipo. Cada subtarea debe tener instrucciones "
        "claras y específicas para el agente que la ejecutará."
    )

    client = _get_client()
    model = supervisor.definition.model_name or "claude-sonnet-4-20250514"

    response = await _call_claude_with_retry(
        client,
        model=model,
        max_tokens=4096,
        temperature=0.3,  # low temperature for planning — we want consistent decisions
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        tools=[DELEGATE_TOOL],
        tool_choice={"type": "tool", "name": "delegate_subtasks"},
    )

    # Extract the tool call result
    for block in response.content:
        if block.type == "tool_use" and block.name == "delegate_subtasks":
            tool_input = block.input
            plan_summary = tool_input.get("plan_summary", "")
            subtasks = tool_input.get("subtasks", [])

            logger.info(
                "Supervisor %s planned %d subtasks: %s",
                supervisor.name, len(subtasks), plan_summary,
            )

            await _log_activity(
                db, supervisor.id, task.id,
                action="delegation_planned",
                level=LogLevel.INFO,
                summary=f"Plan: {plan_summary}",
                details={
                    "subtask_count": len(subtasks),
                    "agents_involved": list({s["agent_slug"] for s in subtasks}),
                    "rag_chunks_used": rag_chunks,
                },
                organization_id=supervisor.organization_id,
            )

            # Validate agent slugs exist in subordinates
            valid_slugs = {s.slug for s in supervisor.subordinates}
            validated = []
            for spec in subtasks:
                if spec["agent_slug"] in valid_slugs:
                    validated.append(spec)
                else:
                    logger.warning(
                        "Supervisor %s tried to delegate to unknown agent '%s' — skipping",
                        supervisor.name, spec["agent_slug"],
                    )

            if not validated:
                raise ValueError(
                    f"Supervisor planned {len(subtasks)} subtasks but none matched valid subordinates: {valid_slugs}"
                )

            return validated

    raise ValueError("Supervisor did not use the delegate_subtasks tool")


async def _execute_subtasks(
    parent_task: Task,
    supervisor: Agent,
    subtask_specs: list[dict],
    db: AsyncSession,
) -> list[dict]:
    """
    Phase 2: Create subtask records and execute them.

    Subtasks run sequentially (they share the DB session).
    Each gets its own Task record linked to the parent via parent_task_id.
    """
    # Build slug → agent lookup
    slug_to_agent = {s.slug: s for s in supervisor.subordinates}

    subtask_results = []

    for spec in subtask_specs:
        agent = slug_to_agent[spec["agent_slug"]]

        # Create subtask record in DB
        subtask = Task(
            title=spec["title"],
            description=spec["description"],
            priority=parent_task.priority,
            assigned_to=agent.id,
            department_id=parent_task.department_id,
            parent_task_id=parent_task.id,
            status=TaskStatus.ASSIGNED,
            organization_id=parent_task.organization_id,
        )
        db.add(subtask)
        await db.flush()

        await _emit("task.subtask_created", {
            "parent_task_id": str(parent_task.id),
            "subtask_id": str(subtask.id),
            "title": subtask.title,
            "agent_id": str(agent.id),
            "agent_name": agent.name,
        })

        # Execute the subtask — reuses the normal agent executor
        try:
            executed = await execute_task(subtask.id, db)

            subtask_results.append({
                "subtask_id": str(executed.id),
                "agent_name": agent.name,
                "agent_slug": agent.slug,
                "title": spec["title"],
                "status": "completed" if executed.status == TaskStatus.COMPLETED else "failed",
                "output": executed.result.get("output", "") if executed.result else "",
                "kb_sources": executed.result.get("kb_sources", []) if executed.result else [],
            })

        except Exception as exc:
            logger.error("Subtask %s failed: %s", subtask.id, exc)
            subtask_results.append({
                "subtask_id": str(subtask.id),
                "agent_name": agent.name,
                "agent_slug": agent.slug,
                "title": spec["title"],
                "status": "failed",
                "output": "",
                "error": str(exc)[:200],
            })

    return subtask_results


async def _aggregate_results(
    parent_task: Task,
    supervisor: Agent,
    subtask_results: list[dict],
    db: AsyncSession,
) -> dict:
    """
    Phase 3: Ask the supervisor to synthesize subtask outputs into a final deliverable.

    The supervisor gets the original task + all subtask results,
    and produces a coherent aggregated output.
    """
    # Build summary of subtask results for the supervisor
    results_text = []
    for r in subtask_results:
        status_emoji = "COMPLETADO" if r["status"] == "completed" else "FALLIDO"
        results_text.append(
            f"### Subtarea: {r['title']} ({r['agent_name']}) — {status_emoji}\n"
            f"{r['output'] or r.get('error', 'Sin resultado')}"
        )
    results_combined = "\n\n---\n\n".join(results_text)

    completed_count = sum(1 for r in subtask_results if r["status"] == "completed")
    failed_count = sum(1 for r in subtask_results if r["status"] == "failed")

    user_message = (
        f"## Tarea original: {parent_task.title}\n\n"
        f"{parent_task.description or ''}\n\n"
        f"## Resultados de tu equipo ({completed_count} completados, {failed_count} fallidos)\n\n"
        f"{results_combined}\n\n"
        "---\n\n"
        "Ahora, como supervisor, agrega estos resultados en un entregable final coherente. "
        "Incluye un resumen ejecutivo al inicio. "
        "Si alguna subtarea falló, indica qué falta y cómo se podría completar."
    )

    client = _get_client()
    model = supervisor.definition.model_name or "claude-sonnet-4-20250514"

    response = await _call_claude_with_retry(
        client,
        model=model,
        max_tokens=supervisor.definition.max_tokens or 4096,
        temperature=float(supervisor.definition.temperature or 0.7),
        system=supervisor.definition.system_prompt or "",
        messages=[{"role": "user", "content": user_message}],
    )

    aggregated_text = ""
    for block in response.content:
        if block.type == "text":
            aggregated_text += block.text

    # Collect all KB sources from subtasks
    all_kb_sources = []
    for r in subtask_results:
        all_kb_sources.extend(r.get("kb_sources", []))

    return {
        "output": aggregated_text,
        "model": response.model,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
        "stop_reason": response.stop_reason,
        "subtask_outputs": [
            {"agent": r["agent_name"], "title": r["title"], "status": r["status"]}
            for r in subtask_results
        ],
        "kb_sources": all_kb_sources,
    }
