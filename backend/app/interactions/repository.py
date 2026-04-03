import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.core.pagination import PaginationParams
from app.departments.models import Department
from app.interactions.models import AgentInteraction, InteractionChannel


class InteractionRepository:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id

    def _scoped(self):
        return select(AgentInteraction).where(AgentInteraction.organization_id == self.org_id)

    async def list_all(
        self,
        pagination: PaginationParams,
        *,
        agent_id: uuid.UUID | None = None,
        channel: InteractionChannel | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> tuple[list[AgentInteraction], int]:
        query = self._scoped()
        count_base = select(func.count()).select_from(AgentInteraction).where(
            AgentInteraction.organization_id == self.org_id
        )

        if agent_id is not None:
            condition = (AgentInteraction.from_agent_id == agent_id) | (
                AgentInteraction.to_agent_id == agent_id
            )
            query = query.where(condition)
            count_base = count_base.where(condition)
        if channel is not None:
            query = query.where(AgentInteraction.channel == channel)
            count_base = count_base.where(AgentInteraction.channel == channel)
        if date_from is not None:
            query = query.where(AgentInteraction.occurred_at >= date_from)
            count_base = count_base.where(AgentInteraction.occurred_at >= date_from)
        if date_to is not None:
            query = query.where(AgentInteraction.occurred_at <= date_to)
            count_base = count_base.where(AgentInteraction.occurred_at <= date_to)

        total = (await self.db.execute(count_base)).scalar_one()

        result = await self.db.execute(
            query.order_by(AgentInteraction.occurred_at.desc())
            .offset(pagination.offset)
            .limit(pagination.size)
        )
        return list(result.scalars().all()), total

    async def create(self, interaction: AgentInteraction) -> AgentInteraction:
        self.db.add(interaction)
        await self.db.flush()
        await self.db.refresh(interaction)
        return interaction

    async def get_edge_weights(self) -> list[tuple[uuid.UUID, uuid.UUID, int]]:
        result = await self.db.execute(
            select(
                AgentInteraction.from_agent_id,
                AgentInteraction.to_agent_id,
                func.count().label("weight"),
            )
            .where(AgentInteraction.organization_id == self.org_id)
            .group_by(
                AgentInteraction.from_agent_id,
                AgentInteraction.to_agent_id,
            )
        )
        return list(result.all())

    async def get_agents_with_departments(
        self, agent_ids: set[uuid.UUID]
    ) -> list[tuple[uuid.UUID, str, str | None]]:
        if not agent_ids:
            return []
        result = await self.db.execute(
            select(Agent.id, Agent.name, Department.name)
            .outerjoin(Department, Agent.department_id == Department.id)
            .where(Agent.id.in_(agent_ids), Agent.organization_id == self.org_id)
        )
        return list(result.all())
