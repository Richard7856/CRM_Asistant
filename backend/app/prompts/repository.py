import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PaginationParams
from app.prompts.models import PromptTemplate, PromptVersion


class PromptRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Prompt Versions
    # ------------------------------------------------------------------

    async def list_versions(
        self,
        agent_id: uuid.UUID,
        pagination: PaginationParams,
    ) -> tuple[list[PromptVersion], int]:
        base = select(PromptVersion).where(PromptVersion.agent_id == agent_id)

        count_result = await self.db.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = count_result.scalar_one()

        query = (
            base.order_by(PromptVersion.version.desc())
            .offset(pagination.offset)
            .limit(pagination.size)
        )
        result = await self.db.execute(query)
        versions = list(result.scalars().all())
        return versions, total

    async def get_version(
        self, agent_id: uuid.UUID, version_number: int
    ) -> PromptVersion | None:
        result = await self.db.execute(
            select(PromptVersion).where(
                PromptVersion.agent_id == agent_id,
                PromptVersion.version == version_number,
            )
        )
        return result.scalar_one_or_none()

    async def get_active_version(self, agent_id: uuid.UUID) -> PromptVersion | None:
        result = await self.db.execute(
            select(PromptVersion).where(
                PromptVersion.agent_id == agent_id,
                PromptVersion.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create_version(self, version: PromptVersion) -> PromptVersion:
        self.db.add(version)
        await self.db.flush()
        await self.db.refresh(version)
        return version

    async def activate_version(
        self, agent_id: uuid.UUID, version_number: int
    ) -> PromptVersion | None:
        # Deactivate all versions for this agent
        await self.db.execute(
            update(PromptVersion)
            .where(PromptVersion.agent_id == agent_id)
            .values(is_active=False)
        )
        # Activate the specified version
        await self.db.execute(
            update(PromptVersion)
            .where(
                PromptVersion.agent_id == agent_id,
                PromptVersion.version == version_number,
            )
            .values(is_active=True)
        )
        await self.db.flush()
        return await self.get_version(agent_id, version_number)

    async def get_next_version_number(self, agent_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.coalesce(func.max(PromptVersion.version), 0)).where(
                PromptVersion.agent_id == agent_id
            )
        )
        return result.scalar_one() + 1

    # ------------------------------------------------------------------
    # Prompt Templates
    # ------------------------------------------------------------------

    async def list_templates(
        self,
        pagination: PaginationParams,
        category: str | None = None,
        search: str | None = None,
    ) -> tuple[list[PromptTemplate], int]:
        base = select(PromptTemplate)

        if category:
            base = base.where(PromptTemplate.category == category)
        if search:
            pattern = f"%{search}%"
            base = base.where(
                PromptTemplate.name.ilike(pattern)
                | PromptTemplate.description.ilike(pattern)
            )

        count_result = await self.db.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = count_result.scalar_one()

        query = (
            base.order_by(PromptTemplate.name)
            .offset(pagination.offset)
            .limit(pagination.size)
        )
        result = await self.db.execute(query)
        templates = list(result.scalars().all())
        return templates, total

    async def get_template(self, template_id: uuid.UUID) -> PromptTemplate | None:
        result = await self.db.execute(
            select(PromptTemplate).where(PromptTemplate.id == template_id)
        )
        return result.scalar_one_or_none()

    async def create_template(self, template: PromptTemplate) -> PromptTemplate:
        self.db.add(template)
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def update_template(
        self, template: PromptTemplate, data: dict
    ) -> PromptTemplate:
        for key, value in data.items():
            setattr(template, key, value)
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def delete_template(self, template: PromptTemplate) -> None:
        await self.db.delete(template)
        await self.db.flush()

    async def increment_template_usage(self, template_id: uuid.UUID) -> None:
        await self.db.execute(
            update(PromptTemplate)
            .where(PromptTemplate.id == template_id)
            .values(usage_count=PromptTemplate.usage_count + 1)
        )
        await self.db.flush()

    async def slug_exists(self, slug: str) -> bool:
        result = await self.db.execute(
            select(func.count()).select_from(PromptTemplate).where(
                PromptTemplate.slug == slug
            )
        )
        return result.scalar_one() > 0
