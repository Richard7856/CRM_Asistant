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


# ─── Retention (P0.7b) ────────────────────────────────────────────────────────


class RetentionPolicyUpsert(BaseModel):
    """Create or update a retention policy for one eligible table."""

    table_name: str = Field(..., description="Tabla a purgar. Debe estar en la allowlist de retención.")
    retention_days: int = Field(..., ge=1, description="Días a conservar; filas más viejas se borran.")
    is_enabled: bool = Field(default=True, description="Si false, la política existe pero no purga.")


class RetentionPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    table_name: str
    retention_days: int
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class RetentionEligibleResponse(BaseModel):
    """What tables can have a retention policy + recommended windows."""

    eligible: list[dict]  # [{table, timestamp_column, recommended_days}]
    note: str = (
        "Retención opt-in: sin política, la tabla se conserva indefinidamente. "
        "Solo logs operativos son elegibles — los datos core salen por erase-tenant."
    )
