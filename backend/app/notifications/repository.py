import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import Notification


class NotificationRepository:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id

    def _scoped(self):
        return select(Notification).where(Notification.organization_id == self.org_id)

    async def create(self, notification: Notification) -> Notification:
        self.db.add(notification)
        await self.db.flush()
        await self.db.refresh(notification)
        return notification

    async def get_by_id(self, notification_id: uuid.UUID) -> Notification | None:
        result = await self.db.execute(
            self._scoped().where(Notification.id == notification_id)
        )
        return result.scalar_one_or_none()

    async def list_recent(self, limit: int = 50) -> list[Notification]:
        """List most recent notifications, unread first."""
        result = await self.db.execute(
            self._scoped()
            .order_by(Notification.is_read.asc(), Notification.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_unread(self) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.organization_id == self.org_id,
                Notification.is_read == False,  # noqa: E712
            )
        )
        return result.scalar_one()

    async def mark_read(self, notification_id: uuid.UUID) -> Notification | None:
        notification = await self.get_by_id(notification_id)
        if notification:
            notification.is_read = True
            await self.db.flush()
            await self.db.refresh(notification)
        return notification

    async def mark_all_read(self) -> int:
        """Mark all unread notifications as read. Returns count of updated rows."""
        result = await self.db.execute(
            update(Notification)
            .where(
                Notification.organization_id == self.org_id,
                Notification.is_read == False,  # noqa: E712
            )
            .values(is_read=True)
        )
        await self.db.flush()
        return result.rowcount
