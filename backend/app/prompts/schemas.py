import uuid
from datetime import datetime

from pydantic import BaseModel


class PromptVersionResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    version: int
    system_prompt: str
    model_provider: str | None
    model_name: str | None
    temperature: float
    max_tokens: int
    tools: list
    change_notes: str | None
    created_by: str | None
    is_active: bool
    performance_score: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PromptVersionCreate(BaseModel):
    system_prompt: str
    model_provider: str | None = None
    model_name: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096
    tools: list = []
    change_notes: str | None = None
    created_by: str = "user"


class PromptTemplateResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    category: str
    system_prompt: str
    model_provider: str | None
    model_name: str | None
    temperature: float
    max_tokens: int
    tools: list
    tags: list
    usage_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PromptTemplateCreate(BaseModel):
    name: str
    description: str | None = None
    category: str
    system_prompt: str
    model_provider: str = "anthropic"
    model_name: str = "claude-sonnet-4-20250514"
    temperature: float = 0.7
    max_tokens: int = 4096
    tools: list = []
    tags: list = []


class PromptTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    system_prompt: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    tools: list | None = None
    tags: list | None = None


class PromptDiff(BaseModel):
    field: str
    old_value: str | None
    new_value: str | None


class PromptCompareResponse(BaseModel):
    version_a: int
    version_b: int
    diffs: list[PromptDiff]
