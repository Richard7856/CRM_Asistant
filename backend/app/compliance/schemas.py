"""Pydantic schemas for the compliance API (P0.7)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.compliance.models import ErasureMethod, ErasureSubjectType


class EraseTenantRequest(BaseModel):
    """
    Body for erase-tenant. The confirmation must equal the caller's own org slug
    — a deliberate friction step so a fat-fingered request can't wipe a tenant.
    The org is always the caller's own (taken from the JWT); you cannot erase
    another organization.
    """

    confirmation: str = Field(
        ...,
        description="Debe coincidir EXACTAMENTE con el slug de tu organización para confirmar el borrado irreversible.",
    )


class ErasureCertificateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str
    organization_slug: str
    subject_type: ErasureSubjectType
    subject_user_id: uuid.UUID | None
    method: ErasureMethod
    requested_by_user_id: uuid.UUID | None
    requested_by_email: str | None
    row_counts: dict[str, int]
    total_rows_erased: int
    content_hash: str
    issued_at: datetime


class ClassificationEntry(BaseModel):
    table: str
    classification: str
    pii_columns: list[str]


class DataClassificationResponse(BaseModel):
    """Transparency endpoint: what data we hold and how it's classified."""

    tables: list[ClassificationEntry]
    note: str = (
        "Clasificación de datos por tabla (PII / operacional / metadata). "
        "Base para el derecho de acceso y para el ruteo por sensibilidad del LLM."
    )
