import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.models import (
    Agent,
    AgentOrigin,
    AgentStatus,
    Role,
)
from app.core.pagination import PaginationParams


class AgentRepository:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    def _base_agent_query(self):
        """Return a select with eager-loaded role and department, scoped to org."""
        return (
            select(Agent)
            .where(Agent.organization_id == self.org_id)
            .options(
                selectinload(Agent.role),
                selectinload(Agent.department),
                selectinload(Agent.supervisor),
            )
        )

    async def get_by_id(self, agent_id: uuid.UUID) -> Agent | None:
        result = await self.db.execute(
            self._base_agent_query().where(Agent.id == agent_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Agent | None:
        result = await self.db.execute(
            self._base_agent_query().where(Agent.slug == slug)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        pagination: PaginationParams,
        *,
        department_id: uuid.UUID | None = None,
        status: AgentStatus | None = None,
        origin: AgentOrigin | None = None,
        role_id: uuid.UUID | None = None,
    ) -> tuple[list[Agent], int]:
        base = select(Agent).where(Agent.organization_id == self.org_id)

        if department_id is not None:
            base = base.where(Agent.department_id == department_id)
        if status is not None:
            base = base.where(Agent.status == status)
        if origin is not None:
            base = base.where(Agent.origin == origin)
        if role_id is not None:
            base = base.where(Agent.role_id == role_id)

        # Total count
        count_result = await self.db.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = count_result.scalar_one()

        # Paginated results with eager loads
        filtered = base.options(
            selectinload(Agent.role),
            selectinload(Agent.department),
            selectinload(Agent.supervisor),
        ).order_by(Agent.name).offset(pagination.offset).limit(pagination.size)

        result = await self.db.execute(filtered)
        agents = list(result.scalars().all())
        return agents, total

    async def create(self, agent: Agent) -> Agent:
        self.db.add(agent)
        await self.db.flush()
        await self.db.refresh(agent, attribute_names=["role", "department", "supervisor"])
        return agent

    async def update(self, agent: Agent, data: dict) -> Agent:
        for key, value in data.items():
            setattr(agent, key, value)
        await self.db.flush()
        await self.db.refresh(agent, attribute_names=["role", "department", "supervisor"])
        return agent

    async def delete(self, agent: Agent) -> Agent:
        """Soft-delete: set status to OFFLINE."""
        agent.status = AgentStatus.OFFLINE
        await self.db.flush()
        await self.db.refresh(agent)
        return agent

    async def get_subordinates(self, agent_id: uuid.UUID) -> list[Agent]:
        result = await self.db.execute(
            self._base_agent_query().where(Agent.supervisor_id == agent_id).order_by(Agent.name)
        )
        return list(result.scalars().all())

    async def slug_exists(self, slug: str) -> bool:
        result = await self.db.execute(
            select(func.count()).select_from(Agent).where(Agent.slug == slug)
        )
        return result.scalar_one() > 0

    # ------------------------------------------------------------------
    # Roles (global — not org-scoped)
    # ------------------------------------------------------------------

    async def get_role_by_id(self, role_id: uuid.UUID) -> Role | None:
        result = await self.db.execute(
            select(Role).where(Role.id == role_id)
        )
        return result.scalar_one_or_none()

    async def list_roles(self) -> list[Role]:
        result = await self.db.execute(select(Role).order_by(Role.name))
        return list(result.scalars().all())

    async def create_role(self, role: Role) -> Role:
        self.db.add(role)
        await self.db.flush()
        await self.db.refresh(role)
        return role
