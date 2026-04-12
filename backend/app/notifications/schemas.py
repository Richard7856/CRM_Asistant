from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.notifications.models import NotificationType


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID | None = None
    title: str
    body: str | None = None
    notification_type: NotificationType
    is_read: bool
    action_url: str | None = None
    metadata_: dict = {}
    created_at: datetime


class NotificationMarkRead(BaseModel):
    is_read: bool = True


class UnreadCountResponse(BaseModel):
    unread_count: int
