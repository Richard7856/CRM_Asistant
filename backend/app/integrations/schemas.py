from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Inbound webhook
# ---------------------------------------------------------------------------


class WebhookPayload(BaseModel):
    """Generic inbound webhook payload from any external platform."""
    agent_id: str | None = None
    event_type: str | None = None
    task_id: str | None = None
    action: str | None = None
    status: str | None = None
    result: Any = None
    metrics: dict | None = None
    timestamp: str | None = None
    # Platform-specific extra fields are captured here
    extra: dict | None = Field(default=None, description="Platform-specific extra data")


# ---------------------------------------------------------------------------
# Task dispatch
# ---------------------------------------------------------------------------


class TaskDispatchRequest(BaseModel):
    """Request to dispatch a task to an external agent."""
    task_type: str = Field(..., description="Type of task to execute")
    input_data: dict = Field(default_factory=dict, description="Input data for the task")
    priority: str = Field(default="normal", description="Task priority: low, normal, high")
    callback_url: str | None = Field(default=None, description="URL to receive completion callback")
    config_overrides: dict | None = Field(default=None, description="Platform-specific config overrides")


class TaskDispatchResponse(BaseModel):
    """Response after dispatching a task."""
    success: bool
    message: str
    agent_id: uuid.UUID
    external_id: str | None = None
    response_data: dict | None = None
    dispatched_at: datetime


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class IntegrationHealthResponse(BaseModel):
    """Health check result for a single integration."""
    agent_id: uuid.UUID
    agent_name: str
    platform: str | None
    healthy: bool
    message: str
    latency_ms: int | None = None
    checked_at: datetime


class BulkHealthResponse(BaseModel):
    """Bulk health check results."""
    total: int
    healthy: int
    unhealthy: int
    results: list[IntegrationHealthResponse]
    checked_at: datetime


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


class IntegrationSyncResponse(BaseModel):
    """Result of syncing an external agent's state."""
    agent_id: uuid.UUID
    platform: str | None
    status: str
    current_task: str | None = None
    metadata: dict = Field(default_factory=dict)
    synced_at: datetime


# ---------------------------------------------------------------------------
# Platform info
# ---------------------------------------------------------------------------


class PlatformConfigField(BaseModel):
    """Describes a config field for a platform."""
    name: str
    type: str = "string"
    required: bool = False
    description: str = ""


class PlatformInfo(BaseModel):
    """Info about a supported platform."""
    name: str
    description: str
    config_fields: list[PlatformConfigField] = []


# ---------------------------------------------------------------------------
# Webhook event (processed)
# ---------------------------------------------------------------------------


class WebhookEventResponse(BaseModel):
    """Response after processing an inbound webhook."""
    success: bool
    event_type: str
    agent_id: str | None = None
    message: str
    activity_id: uuid.UUID | None = None
