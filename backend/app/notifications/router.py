import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_org_id
from app.core.database import get_db
from app.notifications.schemas import NotificationMarkRead, NotificationResponse, UnreadCountResponse
from app.notifications.service import NotificationService

router = APIRouter()


@router.get("/", response_model=list[NotificationResponse])
async def list_notifications(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
):
    """List recent notifications, unread first."""
    service = NotificationService(db, org_id)
    return await service.list_notifications(limit)


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
):
    """Get count of unread notifications for the bell badge."""
    service = NotificationService(db, org_id)
    return await service.get_unread_count()


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
):
    """Mark a single notification as read."""
    service = NotificationService(db, org_id)
    result = await service.mark_read(notification_id)
    await db.commit()
    return result


@router.post("/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
):
    """Mark all unread notifications as read."""
    service = NotificationService(db, org_id)
    count = await service.mark_all_read()
    await db.commit()
    return {"marked_read": count}
