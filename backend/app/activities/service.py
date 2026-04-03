import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.activities.models import ActivityLog, LogLevel
from app.activities.repository import ActivityRepository
from app.activities.schemas import ActivityCreate, ActivityResponse, ActivitySummary
from app.core.pagination import PaginationParams


class ActivityService:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id
        self.repo = ActivityRepository(db, org_id)

    async def create_activity(self, data: ActivityCreate) -> ActivityResponse:
        activity = ActivityLog(
            agent_id=data.agent_id,
            task_id=data.task_id,
            action=data.action,
            level=data.level,
            summary=data.summary,
            details=data.details or {},
            organization_id=self.org_id,
        )
        activity = await self.repo.create(activity)
        return ActivityResponse.model_validate(activity)

    async def list_activities(
        self,
        pagination: PaginationParams,
        *,
        agent_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        level: LogLevel | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> tuple[list[ActivityResponse], int]:
        activities, total = await self.repo.list_all(
            pagination,
            agent_id=agent_id,
            task_id=task_id,
            level=level,
            date_from=date_from,
            date_to=date_to,
        )
        return [ActivityResponse.model_validate(a) for a in activities], total

    async def get_summary(self) -> list[ActivitySummary]:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        rows = await self.repo.summary_by_level(since)
        return [ActivitySummary(level=level, count=count) for level, count in rows]
