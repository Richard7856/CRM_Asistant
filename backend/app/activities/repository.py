import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activities.models import ActivityLog, LogLevel
from app.core.pagination import PaginationParams


class ActivityRepository:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id

    def _scoped(self):
        return select(ActivityLog).where(ActivityLog.organization_id == self.org_id)

    async def list_all(
        self,
        pagination: PaginationParams,
        *,
        agent_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        level: LogLevel | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> tuple[list[ActivityLog], int]:
        query = self._scoped()
        count_base = select(func.count()).select_from(ActivityLog).where(
            ActivityLog.organization_id == self.org_id
        )

        if agent_id is not None:
            query = query.where(ActivityLog.agent_id == agent_id)
            count_base = count_base.where(ActivityLog.agent_id == agent_id)
        if task_id is not None:
            query = query.where(ActivityLog.task_id == task_id)
            count_base = count_base.where(ActivityLog.task_id == task_id)
        if level is not None:
            query = query.where(ActivityLog.level == level)
            count_base = count_base.where(ActivityLog.level == level)
        if date_from is not None:
            query = query.where(ActivityLog.occurred_at >= date_from)
            count_base = count_base.where(ActivityLog.occurred_at >= date_from)
        if date_to is not None:
            query = query.where(ActivityLog.occurred_at <= date_to)
            count_base = count_base.where(ActivityLog.occurred_at <= date_to)

        total = (await self.db.execute(count_base)).scalar_one()

        result = await self.db.execute(
            query.order_by(ActivityLog.occurred_at.desc())
            .offset(pagination.offset)
            .limit(pagination.size)
        )
        return list(result.scalars().all()), total

    async def create(self, activity: ActivityLog) -> ActivityLog:
        self.db.add(activity)
        await self.db.flush()
        await self.db.refresh(activity)
        return activity

    async def summary_by_level(self, since: datetime) -> list[tuple[LogLevel, int]]:
        result = await self.db.execute(
            select(ActivityLog.level, func.count())
            .where(ActivityLog.occurred_at >= since, ActivityLog.organization_id == self.org_id)
            .group_by(ActivityLog.level)
        )
        return list(result.all())
