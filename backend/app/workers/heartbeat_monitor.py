"""
Heartbeat monitor worker.
Checks agent heartbeats and updates status for stale agents.
Run periodically (e.g., every 60 seconds via scheduler or cron).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.agents.models import Agent, AgentOrigin, AgentStatus
from app.core.database import async_session_factory
from app.core.events import Event, event_bus

logger = logging.getLogger(__name__)

# Thresholds
ERROR_THRESHOLD_MULTIPLIER = 3
OFFLINE_THRESHOLD_MULTIPLIER = 10
DEFAULT_HEARTBEAT_INTERVAL = 60  # seconds


async def check_heartbeats():
    """Check all external agents for stale heartbeats."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Agent).where(
                Agent.origin == AgentOrigin.EXTERNAL,
                Agent.status.not_in([AgentStatus.OFFLINE, AgentStatus.MAINTENANCE]),
            )
        )
        agents = result.scalars().all()

        now = datetime.now(timezone.utc)

        for agent in agents:
            if not agent.last_heartbeat_at:
                continue

            elapsed = (now - agent.last_heartbeat_at.replace(tzinfo=timezone.utc)).total_seconds()
            interval = DEFAULT_HEARTBEAT_INTERVAL

            if elapsed > interval * OFFLINE_THRESHOLD_MULTIPLIER:
                new_status = AgentStatus.OFFLINE
            elif elapsed > interval * ERROR_THRESHOLD_MULTIPLIER:
                new_status = AgentStatus.ERROR
            else:
                continue

            if agent.status != new_status:
                logger.warning(
                    "Agent %s (%s) heartbeat stale (%.0fs). Status: %s -> %s",
                    agent.name, agent.id, elapsed, agent.status, new_status,
                )
                await session.execute(
                    update(Agent)
                    .where(Agent.id == agent.id)
                    .values(status=new_status)
                )
                # Notify all SSE subscribers so the frontend updates in real time
                await event_bus.publish(Event(
                    type="agent.status_changed",
                    data={
                        "agent_id": str(agent.id),
                        "agent_name": agent.name,
                        "old_status": agent.status.value,
                        "new_status": new_status.value,
                        "reason": "heartbeat_stale",
                        "elapsed_seconds": round(elapsed),
                    },
                ))

        await session.commit()


async def run_monitor(interval: int = 60):
    """Run heartbeat monitor in a loop."""
    logger.info("Starting heartbeat monitor (interval=%ds)", interval)
    while True:
        try:
            await check_heartbeats()
        except Exception:
            logger.exception("Heartbeat monitor error")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(run_monitor())
