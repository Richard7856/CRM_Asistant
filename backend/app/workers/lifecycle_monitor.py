"""
Lifecycle Monitor — detects idle agents and notifies human operators.

Runs every 24 hours as a background asyncio task (same pattern as
metrics_calculator, heartbeat_monitor, and integration_health_checker).

Detection criteria:
- Agent completed last task >7 days ago, OR
- Agent was created >3 days ago and has 0 completed tasks

Extra attention to agents created autonomously (created_by_agent_id IS NOT NULL) —
these get flagged faster since they weren't created by a human decision.

IMPORTANT: This worker NEVER deactivates agents automatically.
It only creates notifications suggesting the human take action.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, or_, and_

from app.agents.models import Agent, AgentStatus
from app.core.database import async_session_factory
from app.core.events import Event, event_bus
from app.notifications.models import Notification, NotificationType

logger = logging.getLogger(__name__)

# Thresholds for idle detection
_IDLE_DAYS_SINCE_LAST_TASK = 7
_IDLE_DAYS_NEVER_COMPLETED = 3


async def run_lifecycle_monitor(interval_seconds: int = 86400) -> None:
    """
    Background worker loop — runs check_idle_agents() on an interval.

    Default interval is 24 hours. First check runs after a short delay
    to let the server fully start up.
    """
    await asyncio.sleep(30)  # let the server boot
    logger.info("Lifecycle monitor started (interval: %ds)", interval_seconds)

    while True:
        try:
            await check_idle_agents()
        except asyncio.CancelledError:
            logger.info("Lifecycle monitor shutting down")
            raise
        except Exception as exc:
            logger.error("Lifecycle monitor error: %s", exc, exc_info=True)

        await asyncio.sleep(interval_seconds)


async def check_idle_agents() -> int:
    """
    Scan for idle agents and create notifications for each one found.

    Returns the number of idle agents detected.
    """
    async with async_session_factory() as db:
        now = datetime.utcnow()
        idle_since_task = now - timedelta(days=_IDLE_DAYS_SINCE_LAST_TASK)
        idle_since_creation = now - timedelta(days=_IDLE_DAYS_NEVER_COMPLETED)

        # Find agents that are idle:
        # 1. Last task completed > 7 days ago
        # 2. Created > 3 days ago and never completed a task
        # Exclude already-offline agents (already flagged or deactivated)
        result = await db.execute(
            select(Agent).where(
                Agent.status != AgentStatus.OFFLINE,
                Agent.status != AgentStatus.MAINTENANCE,
                or_(
                    # Case 1: Has completed tasks but none recently
                    and_(
                        Agent.last_task_completed_at.isnot(None),
                        Agent.last_task_completed_at < idle_since_task,
                    ),
                    # Case 2: Never completed a task and not brand new
                    and_(
                        Agent.total_tasks_completed == 0,
                        Agent.created_at < idle_since_creation,
                    ),
                ),
            )
        )
        idle_agents = list(result.scalars().all())

        if not idle_agents:
            logger.info("Lifecycle check: no idle agents found")
            return 0

        logger.info("Lifecycle check: found %d idle agents", len(idle_agents))

        for agent in idle_agents:
            # Check if we already have an unread notification for this agent
            existing = await db.execute(
                select(Notification).where(
                    Notification.agent_id == agent.id,
                    Notification.notification_type == NotificationType.AGENT_IDLE,
                    Notification.is_read == False,  # noqa: E712
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue  # already notified, don't spam

            # Build context-aware notification
            days_idle = _calculate_idle_days(agent, now)
            was_autonomous = agent.created_by_agent_id is not None

            title = f"Agente inactivo: {agent.name}"
            if was_autonomous:
                title = f"Agente autónomo inactivo: {agent.name}"

            body_parts = [f"**{agent.name}** lleva {days_idle} días sin completar tareas."]
            if agent.total_tasks_completed == 0:
                body_parts.append("No ha completado ninguna tarea desde su creación.")
            else:
                body_parts.append(f"Total de tareas completadas: {agent.total_tasks_completed}.")
            if was_autonomous:
                body_parts.append("Este agente fue creado autónomamente por otro agente.")
                if agent.creation_reason:
                    body_parts.append(f"Razón de creación: {agent.creation_reason}")
            body_parts.append("Considera desactivarlo si ya no es necesario.")

            notification = Notification(
                organization_id=agent.organization_id,
                agent_id=agent.id,
                title=title,
                body=" ".join(body_parts),
                notification_type=NotificationType.AGENT_IDLE,
                action_url=f"/agents/{agent.id}",
                metadata_={
                    "days_idle": days_idle,
                    "total_tasks_completed": agent.total_tasks_completed,
                    "was_autonomous": was_autonomous,
                    "created_by_agent_id": str(agent.created_by_agent_id) if agent.created_by_agent_id else None,
                },
            )
            db.add(notification)

            await event_bus.publish(Event(
                type="agent.idle_detected",
                data={
                    "agent_id": str(agent.id),
                    "agent_name": agent.name,
                    "days_idle": days_idle,
                    "was_autonomous": was_autonomous,
                },
            ))

            logger.info(
                "Idle agent detected: %s (days idle: %d, autonomous: %s)",
                agent.name, days_idle, was_autonomous,
            )

        await db.commit()
        return len(idle_agents)


def _calculate_idle_days(agent: Agent, now: datetime) -> int:
    """Calculate how many days the agent has been idle."""
    if agent.last_task_completed_at:
        return (now - agent.last_task_completed_at).days
    # Never completed a task — count from creation
    return (now - agent.created_at).days
