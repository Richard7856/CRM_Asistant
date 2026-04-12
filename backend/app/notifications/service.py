import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, event_bus
from app.core.exceptions import NotFoundError
from app.notifications.models import Notification, NotificationType
from app.notifications.repository import NotificationRepository
from app.notifications.schemas import NotificationResponse, UnreadCountResponse


class NotificationService:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id
        self.repo = NotificationRepository(db, org_id)

    async def create_notification(
        self,
        title: str,
        notification_type: NotificationType,
        body: str | None = None,
        agent_id: uuid.UUID | None = None,
        action_url: str | None = None,
        metadata: dict | None = None,
    ) -> NotificationResponse:
        """Create a notification and emit SSE event."""
        notification = Notification(
            organization_id=self.org_id,
            agent_id=agent_id,
            title=title,
            body=body,
            notification_type=notification_type,
            action_url=action_url,
            metadata_=metadata or {},
        )
        notification = await self.repo.create(notification)

        # Emit SSE so the frontend can update the bell icon immediately
        await event_bus.publish(Event(
            type="notification.created",
            data={
                "notification_id": str(notification.id),
                "title": title,
                "type": notification_type.value,
                "agent_id": str(agent_id) if agent_id else None,
            },
        ))

        return NotificationResponse.model_validate(notification)

    async def list_notifications(self, limit: int = 50) -> list[NotificationResponse]:
        notifications = await self.repo.list_recent(limit)
        return [NotificationResponse.model_validate(n) for n in notifications]

    async def get_unread_count(self) -> UnreadCountResponse:
        count = await self.repo.count_unread()
        return UnreadCountResponse(unread_count=count)

    async def mark_read(self, notification_id: uuid.UUID) -> NotificationResponse:
        notification = await self.repo.mark_read(notification_id)
        if notification is None:
            raise NotFoundError(detail="Notification not found")
        return NotificationResponse.model_validate(notification)

    async def mark_all_read(self) -> int:
        """Mark all unread notifications as read. Returns count updated."""
        return await self.repo.mark_all_read()
