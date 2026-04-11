"""
Credential service — business logic for credential management.

Handles masking (secret_preview), validation, and response conversion.
The secret_value is never returned in API responses — only the masked preview.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

# SQLAlchemy relationship resolution — Agent has cascading relationships to most models.
# Import all ORM models so the mapper can fully configure. Same pattern as alembic/env.py.
from app.agents.models import Agent  # noqa: F401
from app.auth.models import Organization, User  # noqa: F401
from app.departments.models import Department  # noqa: F401
from app.tasks.models import Task  # noqa: F401
from app.activities.models import ActivityLog  # noqa: F401
from app.metrics.models import PerformanceMetric  # noqa: F401
from app.interactions.models import AgentInteraction  # noqa: F401
from app.improvements.models import ImprovementPoint  # noqa: F401
from app.core.exceptions import NotFoundError
from app.credentials.models import Credential
from app.credentials.repository import CredentialRepository
from app.credentials.schemas import (
    CredentialCreate,
    CredentialResponse,
    CredentialUpdate,
)


def _mask_secret(secret: str) -> str:
    """Generate a masked preview: show last 4 chars, rest as asterisks."""
    if len(secret) <= 4:
        return "****"
    return "****" + secret[-4:]


def _to_response(cred: Credential) -> CredentialResponse:
    """Convert ORM model to response schema, including agent_name if loaded."""
    return CredentialResponse(
        id=cred.id,
        name=cred.name,
        credential_type=cred.credential_type,
        service_name=cred.service_name,
        agent_id=cred.agent_id,
        agent_name=cred.agent.name if cred.agent else None,
        is_active=cred.is_active,
        secret_preview=cred.secret_preview,
        notes=cred.notes,
        organization_id=cred.organization_id,
        created_at=cred.created_at,
        updated_at=cred.updated_at,
    )


class CredentialService:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id
        self.repo = CredentialRepository(db, org_id)

    async def create_credential(self, data: CredentialCreate) -> CredentialResponse:
        credential = Credential(
            name=data.name,
            credential_type=data.credential_type,
            secret_value=data.secret_value,
            service_name=data.service_name,
            agent_id=data.agent_id,
            notes=data.notes,
            secret_preview=_mask_secret(data.secret_value),
            organization_id=self.org_id,
        )
        await self.repo.create(credential)
        # Re-fetch with agent relationship loaded to populate agent_name
        created = await self.repo.get_by_id(credential.id)
        assert created is not None  # just flushed — must exist
        return _to_response(created)

    async def update_credential(
        self, cred_id: uuid.UUID, data: CredentialUpdate
    ) -> CredentialResponse:
        credential = await self.repo.get_by_id(cred_id)
        if not credential:
            raise NotFoundError(f"Credential {cred_id} not found")

        # Apply updates only for provided fields
        if data.name is not None:
            credential.name = data.name
        if data.credential_type is not None:
            credential.credential_type = data.credential_type
        if data.service_name is not None:
            credential.service_name = data.service_name
        if data.agent_id is not None:
            credential.agent_id = data.agent_id
        if data.is_active is not None:
            credential.is_active = data.is_active
        if data.notes is not None:
            credential.notes = data.notes
        # Secret update — re-mask preview
        if data.secret_value is not None:
            credential.secret_value = data.secret_value
            credential.secret_preview = _mask_secret(data.secret_value)

        await self.repo.update(credential)
        # Re-fetch with relationships loaded
        updated = await self.repo.get_by_id(credential.id)
        assert updated is not None  # just flushed — must exist
        return _to_response(updated)

    async def get_credential(self, cred_id: uuid.UUID) -> CredentialResponse:
        credential = await self.repo.get_by_id(cred_id)
        if not credential:
            raise NotFoundError(f"Credential {cred_id} not found")
        return _to_response(credential)

    async def list_credentials(
        self,
        page: int = 1,
        size: int = 20,
        service_name: str | None = None,
        agent_id: uuid.UUID | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[CredentialResponse], int]:
        items, total = await self.repo.list_all(
            page=page, size=size,
            service_name=service_name,
            agent_id=agent_id,
            is_active=is_active,
        )
        return [_to_response(c) for c in items], total

    async def list_agent_credentials(
        self, agent_id: uuid.UUID
    ) -> list[CredentialResponse]:
        """Get credentials available to an agent (agent-specific + shared org-level)."""
        items = await self.repo.list_by_agent(agent_id)
        return [_to_response(c) for c in items]

    async def delete_credential(self, cred_id: uuid.UUID) -> None:
        credential = await self.repo.get_by_id(cred_id)
        if not credential:
            raise NotFoundError(f"Credential {cred_id} not found")
        await self.repo.delete(credential)
