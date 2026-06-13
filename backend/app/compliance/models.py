"""
ErasureCertificate — the durable, tamper-evident proof that data was erased.

This is the one record that must OUTLIVE the data it describes. When a tenant
exercises the right to be forgotten we delete their organization row and every
table that references it — including their audit_log. The certificate is what
remains: proof, for our own compliance and for the (now departed) customer, that
the erasure happened, who authorized it, and how many rows died.

Design choices (P0.7):
- NO foreign key to organizations. The org is gone; the certificate stores the
  org id/name/slug as plain snapshots so it can stand alone.
- Append-only AND delete-proof at the DB level (trigger blocks UPDATE and DELETE).
  Stronger than audit_log, which allows DELETE for retention cleanup — a proof of
  erasure that could itself be erased would be worthless.
- Stores the authorizer's identity (requested_by_user_id/email) as an
  accountability record. Retaining who authorized a legal compliance action is a
  legitimate interest, distinct from the data-subject PII we removed.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ErasureSubjectType(str, enum.Enum):
    TENANT = "tenant"  # whole organization erased (ordered delete)
    USER = "user"      # single user anonymized in place


class ErasureMethod(str, enum.Enum):
    ORDERED_DELETE = "ordered_delete"  # rows physically removed
    ANONYMIZE = "anonymize"            # PII scrubbed, operational rows kept


class ErasureCertificate(Base):
    __tablename__ = "erasure_certificates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Snapshots of the erased org — NOT foreign keys (the org may no longer exist).
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    organization_name: Mapped[str] = mapped_column(String(120), nullable=False)
    organization_slug: Mapped[str] = mapped_column(String(60), nullable=False)

    subject_type: Mapped[ErasureSubjectType] = mapped_column(nullable=False)
    # Set only for USER erasure — the anonymized user's id (kept for traceability).
    subject_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    method: Mapped[ErasureMethod] = mapped_column(nullable=False)

    # Who authorized it — accountability record, not data-subject PII.
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    requested_by_email: Mapped[str | None] = mapped_column(String(255))

    # {table_name: rows_erased} — the auditable count taken before deletion.
    row_counts: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    total_rows_erased: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # SHA-256 over the canonical certificate payload — lets anyone verify the
    # counts/metadata weren't altered after issuance.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
