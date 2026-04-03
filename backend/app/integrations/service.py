import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.activities.models import ActivityLog, LogLevel
from app.agents.models import Agent, AgentIntegration, AgentStatus
from app.core.events import Event, event_bus
from app.core.exceptions import BadRequestError, NotFoundError
from app.integrations.adapters import AdapterRegistry
from app.integrations.adapters.base import NormalizedEvent
from app.tasks.models import Task, TaskStatus

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Return a timezone-aware UTC datetime for API responses."""
    return datetime.now(timezone.utc)


def _utcnow_naive() -> datetime:
    """Return a naive UTC datetime for DB writes (TIMESTAMP WITHOUT TIME ZONE)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class IntegrationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_agent_with_integration(self, agent_id: uuid.UUID) -> tuple[Agent, AgentIntegration]:
        """Load an agent and its integration, raising if not found."""
        result = await self.db.execute(
            select(Agent)
            .options(selectinload(Agent.integration))
            .where(Agent.id == agent_id)
        )
        agent = result.scalar_one_or_none()
        if agent is None:
            raise NotFoundError(detail=f"Agent {agent_id} not found")
        if agent.integration is None:
            raise BadRequestError(detail=f"Agent {agent_id} has no external integration configured")
        if not agent.integration.is_active:
            raise BadRequestError(detail=f"Integration for agent {agent_id} is inactive")
        return agent, agent.integration

    async def _log_activity(
        self,
        agent_id: uuid.UUID,
        action: str,
        level: LogLevel = LogLevel.INFO,
        summary: str | None = None,
        details: dict | None = None,
        task_id: uuid.UUID | None = None,
    ) -> ActivityLog:
        activity = ActivityLog(
            agent_id=agent_id,
            task_id=task_id,
            action=action,
            level=level,
            summary=summary,
            details=details or {},
        )
        self.db.add(activity)
        await self.db.flush()
        return activity

    # ------------------------------------------------------------------
    # Task dispatch
    # ------------------------------------------------------------------

    async def dispatch_task(self, agent_id: uuid.UUID, task_data: dict) -> dict:
        """Dispatch a task to an external agent via its platform adapter."""
        agent, integration = await self._get_agent_with_integration(agent_id)

        adapter = AdapterRegistry.get(integration.platform or "generic")
        result = await adapter.send_task(
            endpoint_url=integration.endpoint_url or "",
            task_data=task_data,
            config=integration.config or {},
        )

        # Log activity
        level = LogLevel.INFO if result.success else LogLevel.ERROR
        await self._log_activity(
            agent_id=agent_id,
            action="integration.task_dispatched",
            level=level,
            summary=result.message,
            details={
                "platform": integration.platform,
                "success": result.success,
                "external_id": result.external_id,
                "task_data_keys": list(task_data.keys()),
            },
        )

        return {
            "success": result.success,
            "message": result.message,
            "agent_id": agent_id,
            "external_id": result.external_id,
            "response_data": result.response_data,
            "dispatched_at": _utcnow(),
        }

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def check_agent_health(self, agent_id: uuid.UUID) -> dict:
        """Health check a single agent's integration."""
        agent, integration = await self._get_agent_with_integration(agent_id)

        adapter = AdapterRegistry.get(integration.platform or "generic")
        health = await adapter.check_health(
            endpoint_url=integration.endpoint_url or "",
            config=integration.config or {},
        )

        # Update agent status based on health
        if health.healthy and agent.status == AgentStatus.ERROR:
            agent.status = AgentStatus.IDLE
        elif not health.healthy and agent.status not in (AgentStatus.OFFLINE, AgentStatus.MAINTENANCE):
            agent.status = AgentStatus.ERROR

        await self.db.flush()

        return {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "platform": integration.platform,
            "healthy": health.healthy,
            "message": health.message,
            "latency_ms": health.latency_ms,
            "checked_at": _utcnow(),
        }

    async def check_all_integrations_health(self) -> dict:
        """Batch health check all active integrations."""
        result = await self.db.execute(
            select(Agent)
            .options(selectinload(Agent.integration))
            .join(AgentIntegration)
            .where(AgentIntegration.is_active.is_(True))
        )
        agents = result.scalars().all()

        results = []
        healthy_count = 0

        for agent in agents:
            if not agent.integration:
                continue
            try:
                health_result = await self.check_agent_health(agent.id)
                results.append(health_result)
                if health_result["healthy"]:
                    healthy_count += 1
            except Exception as e:
                logger.error("Health check failed for agent %s: %s", agent.id, e)
                results.append({
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "platform": agent.integration.platform,
                    "healthy": False,
                    "message": f"Health check error: {e}",
                    "latency_ms": None,
                    "checked_at": _utcnow(),
                })

        return {
            "total": len(results),
            "healthy": healthy_count,
            "unhealthy": len(results) - healthy_count,
            "results": results,
            "checked_at": _utcnow(),
        }

    # ------------------------------------------------------------------
    # Webhook processing
    # ------------------------------------------------------------------

    async def process_webhook(self, platform: str, payload: dict) -> dict:
        """
        Handle an inbound webhook from an external platform.

        When the webhook reports task completion/failure, updates the
        corresponding task record (status, result, timestamps).
        """
        adapter = AdapterRegistry.get(platform)
        event: NormalizedEvent = await adapter.normalize_inbound(payload)

        # Try to find the agent
        agent_id = None
        if event.agent_id:
            try:
                agent_uuid = uuid.UUID(event.agent_id)
                result = await self.db.execute(
                    select(Agent).where(Agent.id == agent_uuid)
                )
                agent = result.scalar_one_or_none()
                if agent:
                    agent_id = agent.id

                    # Update heartbeat
                    agent.last_heartbeat_at = _utcnow_naive()

                    # Update status based on event type
                    if event.event_type == "error" and agent.status != AgentStatus.MAINTENANCE:
                        agent.status = AgentStatus.ERROR
                    elif event.event_type in ("activity.completed", "task.completed"):
                        agent.status = AgentStatus.IDLE
                    elif event.event_type == "heartbeat":
                        if agent.status == AgentStatus.ERROR:
                            agent.status = AgentStatus.IDLE
            except (ValueError, Exception) as e:
                logger.warning("Could not resolve agent_id %s: %s", event.agent_id, e)

        # Update the linked task if webhook carries task result
        task_uuid = None
        if event.task_id:
            try:
                task_uuid = uuid.UUID(event.task_id)
            except ValueError:
                pass

        if task_uuid:
            await self._update_task_from_webhook(task_uuid, event, platform)

        # Log activity if we have an agent
        activity_id = None
        if agent_id:
            level = LogLevel.ERROR if event.event_type == "error" else LogLevel.INFO

            activity = await self._log_activity(
                agent_id=agent_id,
                action=event.action or f"webhook.{platform}.{event.event_type}",
                level=level,
                summary=f"Webhook from {platform}: {event.event_type}",
                details={
                    "platform": platform,
                    "event_type": event.event_type,
                    "result": event.result,
                    "metrics": event.metrics,
                },
                task_id=task_uuid,
            )
            activity_id = activity.id

        await self.db.flush()

        return {
            "success": True,
            "event_type": event.event_type,
            "agent_id": event.agent_id,
            "message": f"Webhook processed for {platform}",
            "activity_id": activity_id,
        }

    async def _update_task_from_webhook(
        self, task_id: uuid.UUID, event: NormalizedEvent, platform: str
    ) -> None:
        """Update a task based on webhook event (completion, failure, progress)."""
        result = await self.db.execute(
            select(Task).where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()
        if task is None:
            logger.warning("Webhook referenced task %s but it doesn't exist", task_id)
            return

        now = _utcnow_naive()

        if event.event_type in ("activity.completed", "task.completed"):
            task.status = TaskStatus.COMPLETED
            task.completed_at = now
            task.result = {
                "output": event.result if isinstance(event.result, str) else str(event.result or ""),
                "platform": platform,
                "metrics": event.metrics or {},
                "source": "webhook",
            }
            logger.info("Task %s marked completed via %s webhook", task_id, platform)
            await event_bus.publish(Event(type="task.completed", data={
                "task_id": str(task_id), "title": task.title,
                "platform": platform, "source": "webhook",
            }))

        elif event.event_type == "error":
            task.status = TaskStatus.FAILED
            task.completed_at = now
            task.result = {
                "error": event.result if isinstance(event.result, str) else str(event.result or "Unknown error"),
                "error_type": "ExternalAgentError",
                "platform": platform,
                "source": "webhook",
            }
            logger.info("Task %s marked failed via %s webhook", task_id, platform)
            await event_bus.publish(Event(type="task.failed", data={
                "task_id": str(task_id), "title": task.title,
                "platform": platform, "source": "webhook",
            }))

        elif event.event_type == "task.status_changed":
            # Progress update — keep in_progress but store intermediate result
            if event.result:
                existing = task.result or {}
                existing["latest_update"] = event.result
                existing["updated_via"] = "webhook"
                task.result = existing

        await self.db.flush()

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    async def sync_agent(self, agent_id: uuid.UUID) -> dict:
        """Sync external agent state."""
        agent, integration = await self._get_agent_with_integration(agent_id)

        adapter = AdapterRegistry.get(integration.platform or "generic")
        state = await adapter.sync_agent_state(
            endpoint_url=integration.endpoint_url or "",
            config=integration.config or {},
        )

        # Update agent status
        status_map = {
            "active": AgentStatus.ACTIVE,
            "idle": AgentStatus.IDLE,
            "busy": AgentStatus.BUSY,
            "error": AgentStatus.ERROR,
            "offline": AgentStatus.OFFLINE,
        }
        new_status = status_map.get(state.status)
        if new_status and agent.status != AgentStatus.MAINTENANCE:
            agent.status = new_status

        # Update last sync timestamp
        integration.last_sync_at = _utcnow_naive()
        agent.last_heartbeat_at = _utcnow_naive()

        await self.db.flush()

        # Log sync activity
        await self._log_activity(
            agent_id=agent_id,
            action="integration.synced",
            summary=f"Synced with {integration.platform}: status={state.status}",
            details={
                "platform": integration.platform,
                "status": state.status,
                "current_task": state.current_task,
                "metadata": state.metadata,
            },
        )

        return {
            "agent_id": agent_id,
            "platform": integration.platform,
            "status": state.status,
            "current_task": state.current_task,
            "metadata": state.metadata,
            "synced_at": _utcnow(),
        }
