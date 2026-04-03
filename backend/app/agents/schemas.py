from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.agents.models import (
    AgentOrigin,
    AgentStatus,
    IntegrationType,
    RoleLevel,
)


# ---------------------------------------------------------------------------
# Role schemas
# ---------------------------------------------------------------------------


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    level: RoleLevel
    description: str | None = None


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    level: RoleLevel
    description: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Agent create / update schemas
# ---------------------------------------------------------------------------


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    origin: AgentOrigin
    role_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    supervisor_id: uuid.UUID | None = None
    capabilities: list[str] | None = None
    avatar_url: str | None = Field(default=None, max_length=500)


class AgentCreateInternal(AgentCreate):
    """Payload for creating an internal (LLM-backed) agent."""

    origin: AgentOrigin = AgentOrigin.INTERNAL
    system_prompt: str | None = None
    model_provider: str | None = Field(default=None, max_length=50)
    model_name: str | None = Field(default=None, max_length=100)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)
    tools: list[dict] | None = None


class AgentRegisterExternal(AgentCreate):
    """Payload for registering an external agent with an integration."""

    origin: AgentOrigin = AgentOrigin.EXTERNAL
    integration_type: IntegrationType
    platform: str | None = Field(default=None, max_length=50)
    endpoint_url: str | None = Field(default=None, max_length=500)
    polling_interval_seconds: int = Field(default=60, ge=1)
    integration_config: dict | None = None


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: AgentStatus | None = None
    role_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    supervisor_id: uuid.UUID | None = None
    capabilities: list[str] | None = None
    avatar_url: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# Agent response schemas
# ---------------------------------------------------------------------------


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    origin: AgentOrigin
    status: AgentStatus
    role_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    supervisor_id: uuid.UUID | None = None
    avatar_url: str | None = None
    capabilities: list | dict | None = None
    metadata_: dict | None = Field(default=None, alias="metadata_")
    created_at: datetime
    updated_at: datetime
    last_heartbeat_at: datetime | None = None

    # Resolved names (populated by service layer)
    role_name: str | None = None
    department_name: str | None = None
    supervisor_name: str | None = None


class IntegrationDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    integration_type: IntegrationType
    platform: str | None = None
    endpoint_url: str | None = None
    polling_interval_seconds: int
    config: dict | None = None
    is_active: bool
    last_sync_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DefinitionDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    system_prompt: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    temperature: float
    max_tokens: int
    tools: list | dict | None = None
    knowledge_base: dict | None = None
    config: dict | None = None
    version: int
    created_at: datetime
    updated_at: datetime


class AgentDetailResponse(AgentResponse):
    integration: IntegrationDetail | None = None
    definition: DefinitionDetail | None = None


class ApiKeyOut(BaseModel):
    """Returned once when an API key is created (raw key is never stored)."""

    id: uuid.UUID
    key_prefix: str
    raw_key: str
    label: str | None = None
    scopes: list[str]
    expires_at: datetime | None = None
