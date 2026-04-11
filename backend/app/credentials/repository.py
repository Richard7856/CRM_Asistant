"""
Credential repository — database operations for credential CRUD.
All queries scoped to organization_id for multi-tenant isolation.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.credentials.models import Credential


class CredentialRepository:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id

    def _scoped(self):
        """Base query scoped to this org — every query starts here."""
        return select(Credential).where(Credential.organization_id == self.org_id)

    async def get_by_id(self, cred_id: uuid.UUID) -> Credential | None:
        result = await self.db.execute(
            self._scoped()
            .options(selectinload(Credential.agent))
            .where(Credential.id == cred_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        page: int = 1,
        size: int = 20,
        service_name: str | None = None,
        agent_id: uuid.UUID | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[Credential], int]:
        """List credentials with optional filters, paginated."""
        base = self._scoped()

        if service_name:
            base = base.where(Credential.service_name == service_name)
        if agent_id is not None:
            base = base.where(Credential.agent_id == agent_id)
        if is_active is not None:
            base = base.where(Credential.is_active == is_active)

        # Count total matching records
        count_stmt = select(func.count()).select_from(base.subquery())
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar_one()

        # Fetch paginated results with agent relationship
        items_result = await self.db.execute(
            base.options(selectinload(Credential.agent))
            .order_by(Credential.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        items = list(items_result.scalars().all())
        return items, total

    async def list_by_agent(self, agent_id: uuid.UUID) -> list[Credential]:
        """Get all active credentials available to an agent (agent-specific + unscoped)."""
        result = await self.db.execute(
            self._scoped()
            .options(selectinload(Credential.agent))
            .where(
                Credential.is_active.is_(True),
                # Agent-specific OR shared (no agent_id)
                (Credential.agent_id == agent_id) | (Credential.agent_id.is_(None)),
            )
            .order_by(Credential.service_name)
        )
        return list(result.scalars().all())

    async def create(self, credential: Credential) -> Credential:
        self.db.add(credential)
        await self.db.flush()
        return credential

    async def update(self, credential: Credential) -> Credential:
        await self.db.flush()
        return credential

    async def delete(self, credential: Credential) -> None:
        await self.db.delete(credential)
        await self.db.flush()
