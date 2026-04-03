"""
Integration health checker worker.
Periodically checks health of all external agent integrations
and updates agent status based on results.
Run every 5 minutes via scheduler or standalone.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.agents.models import Agent, AgentIntegration, AgentStatus
from app.core.database import async_session_factory
from app.integrations.adapters import AdapterRegistry

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 300  # 5 minutes


async def check_integration_health():
    """Check health of all active external integrations."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Agent)
            .options(selectinload(Agent.integration))
            .join(AgentIntegration)
            .where(
                AgentIntegration.is_active.is_(True),
                Agent.status.not_in([AgentStatus.MAINTENANCE]),
            )
        )
        agents = result.scalars().all()

        healthy_count = 0
        unhealthy_count = 0

        for agent in agents:
            if not agent.integration or not agent.integration.endpoint_url:
                continue

            platform = agent.integration.platform or "generic"
            adapter = AdapterRegistry.get(platform)

            try:
                health = await adapter.check_health(
                    endpoint_url=agent.integration.endpoint_url,
                    config=agent.integration.config or {},
                )

                if health.healthy:
                    healthy_count += 1
                    # Recover from error status
                    if agent.status == AgentStatus.ERROR:
                        logger.info(
                            "Agent %s (%s) recovered: %s",
                            agent.name, agent.id, health.message,
                        )
                        await session.execute(
                            update(Agent)
                            .where(Agent.id == agent.id)
                            .values(
                                status=AgentStatus.IDLE,
                                last_heartbeat_at=datetime.now(timezone.utc),
                            )
                        )
                else:
                    unhealthy_count += 1
                    if agent.status not in (AgentStatus.ERROR, AgentStatus.OFFLINE):
                        logger.warning(
                            "Agent %s (%s) unhealthy: %s",
                            agent.name, agent.id, health.message,
                        )
                        await session.execute(
                            update(Agent)
                            .where(Agent.id == agent.id)
                            .values(status=AgentStatus.ERROR)
                        )

            except Exception as e:
                unhealthy_count += 1
                logger.error(
                    "Health check error for agent %s (%s): %s",
                    agent.name, agent.id, e,
                )
                if agent.status not in (AgentStatus.ERROR, AgentStatus.OFFLINE):
                    await session.execute(
                        update(Agent)
                        .where(Agent.id == agent.id)
                        .values(status=AgentStatus.ERROR)
                    )

        await session.commit()
        logger.info(
            "Integration health check complete: %d healthy, %d unhealthy",
            healthy_count, unhealthy_count,
        )


async def run_health_checker(interval: int = CHECK_INTERVAL):
    """Run integration health checker in a loop."""
    logger.info("Starting integration health checker (interval=%ds)", interval)
    while True:
        try:
            await check_integration_health()
        except Exception:
            logger.exception("Integration health checker error")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(run_health_checker())
