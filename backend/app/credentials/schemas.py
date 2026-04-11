"""
Pydantic schemas for Credential CRUD.

Key design: `secret_value` is write-only (accepted in Create/Update),
never included in Response. The response only shows `secret_preview` (masked).
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.credentials.models import CredentialType


class CredentialCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    credential_type: CredentialType = CredentialType.API_KEY
    secret_value: str = Field(..., min_length=1, description="The actual secret — only accepted on create/update")
    service_name: str = Field(..., min_length=1, max_length=100)
    agent_id: uuid.UUID | None = None
    notes: str | None = None


class CredentialUpdate(BaseModel):
    name: str | None = None
    credential_type: CredentialType | None = None
    secret_value: str | None = Field(None, description="If provided, replaces the stored secret")
    service_name: str | None = None
    agent_id: uuid.UUID | None = None
    is_active: bool | None = None
    notes: str | None = None


class CredentialResponse(BaseModel):
    """API response — never includes the full secret."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    credential_type: CredentialType
    service_name: str
    agent_id: uuid.UUID | None
    agent_name: str | None = None
    is_active: bool
    secret_preview: str
    notes: str | None
    organization_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
