import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PaginationParams
from app.improvements.models import ImprovementPoint, ImprovementStatus
from app.tasks.models import TaskPriority


class ImprovementRepository:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id

    def _scoped(self):
        return select(ImprovementPoint).where(ImprovementPoint.organization_id == self.org_id)

    async def get_by_id(self, improvement_id: uuid.UUID) -> ImprovementPoint | None:
        result = await self.db.execute(
            self._scoped().where(ImprovementPoint.id == improvement_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        pagination: PaginationParams,
        *,
        agent_id: uuid.UUID | None = None,
        status: ImprovementStatus | None = None,
        category: str | None = None,
        priority: TaskPriority | None = None,
    ) -> tuple[list[ImprovementPoint], int]:
        query = self._scoped()
        count_base = select(func.count()).select_from(ImprovementPoint).where(
            ImprovementPoint.organization_id == self.org_id
        )

        if agent_id is not None:
            query = query.where(ImprovementPoint.agent_id == agent_id)
            count_base = count_base.where(ImprovementPoint.agent_id == agent_id)
        if status is not None:
            query = query.where(ImprovementPoint.status == status)
            count_base = count_base.where(ImprovementPoint.status == status)
        if category is not None:
            query = query.where(ImprovementPoint.category == category)
            count_base = count_base.where(ImprovementPoint.category == category)
        if priority is not None:
            query = query.where(ImprovementPoint.priority == priority)
            count_base = count_base.where(ImprovementPoint.priority == priority)

        total = (await self.db.execute(count_base)).scalar_one()

        result = await self.db.execute(
            query.order_by(ImprovementPoint.created_at.desc())
            .offset(pagination.offset)
            .limit(pagination.size)
        )
        return list(result.scalars().all()), total

    async def create(self, improvement: ImprovementPoint) -> ImprovementPoint:
        self.db.add(improvement)
        await self.db.flush()
        await self.db.refresh(improvement)
        return improvement

    async def update(self, improvement: ImprovementPoint, data: dict) -> ImprovementPoint:
        for key, value in data.items():
            setattr(improvement, key, value)
        await self.db.flush()
        await self.db.refresh(improvement)
        return improvement
