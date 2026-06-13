"""
Compliance service (P0.7) — orchestrates the data-subject rights.

Transaction model: every method runs inside the request's session (get_db), which
commits on success and rolls back on any exception. So if erasure verification
fails, or writing the certificate fails, NOTHING is deleted — the whole operation
is atomic.
"""

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEventType
from app.audit.service import log_audit_event
from app.auth.models import Organization, User
from app.compliance.classification import (
    PII_COLUMNS,
    TENANT_TABLE_CLASSIFICATION,
)
from app.compliance.models import (
    ErasureCertificate,
    ErasureMethod,
    ErasureSubjectType,
)
from app.compliance.repository import ComplianceRepository
from app.core.exceptions import BadRequestError, NotFoundError


class ComplianceService:
    def __init__(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
    ) -> None:
        self.db = db
        self.org_id = org_id
        self.actor_user_id = actor_user_id
        self.repo = ComplianceRepository(db)

    async def _load_org(self) -> Organization:
        org = (
            await self.db.execute(
                select(Organization).where(Organization.id == self.org_id)
            )
        ).scalar_one_or_none()
        if org is None:
            raise NotFoundError("Organización no encontrada")
        return org

    # ─── Transparency ─────────────────────────────────────────────────────────
    def get_classification(self) -> list[dict]:
        """The data classification registry, table by table."""
        return [
            {
                "table": table,
                "classification": data_class.value,
                "pii_columns": PII_COLUMNS.get(table, []),
            }
            for table, data_class in sorted(TENANT_TABLE_CLASSIFICATION.items())
        ]

    # ─── Export (right of access / portability) ───────────────────────────────
    async def export_tenant(self) -> dict:
        org = await self._load_org()
        data = await self.repo.fetch_tenant_export(self.org_id)
        await log_audit_event(
            self.db,
            organization_id=self.org_id,
            event_type=AuditEventType.DATA_EXPORTED,
            resource_type="organization",
            resource_id=self.org_id,
            actor_user_id=self.actor_user_id,
            context={"scope": "tenant", "tables": len(data)},
        )
        return {
            "manifest": {
                "organization_id": str(org.id),
                "organization_name": org.name,
                "scope": "tenant",
                "classification": self.get_classification(),
            },
            "data": data,
        }

    async def export_user(self, user_id: uuid.UUID) -> dict:
        user = (
            await self.db.execute(
                select(User).where(
                    User.id == user_id, User.organization_id == self.org_id
                )
            )
        ).scalar_one_or_none()
        if user is None:
            raise NotFoundError("Usuario no encontrado en esta organización")

        data = await self.repo.fetch_user_rows(self.org_id, user_id)
        await log_audit_event(
            self.db,
            organization_id=self.org_id,
            event_type=AuditEventType.DATA_EXPORTED,
            resource_type="user",
            resource_id=user_id,
            actor_user_id=self.actor_user_id,
            context={"scope": "user"},
        )
        return {
            "manifest": {
                "organization_id": str(self.org_id),
                "user_id": str(user_id),
                "scope": "user",
            },
            "data": data,
        }

    # ─── Right to be forgotten ────────────────────────────────────────────────
    async def erase_tenant(self, confirmation: str, requester: User) -> ErasureCertificate:
        """
        Irreversibly delete the caller's own organization and all its data, then
        issue a certificate. The certificate is written in the SAME transaction as
        the deletion, so they commit together or not at all.
        """
        org = await self._load_org()

        # Friction step: the caller must echo their org slug exactly.
        if confirmation != org.slug:
            raise BadRequestError(
                "La confirmación no coincide con el slug de la organización. "
                "Borrado cancelado."
            )

        # Snapshot the authorizer BEFORE their user row is deleted.
        requested_by_user_id = requester.id
        requested_by_email = requester.email
        org_name, org_slug = org.name, org.slug

        # Count before deleting — this is the auditable record.
        row_counts = await self.repo.count_tenant_rows(self.org_id)

        await self.repo.execute_tenant_erasure(self.org_id)

        # Verify the deletion actually emptied every tenant table. If anything
        # survived, abort — the exception rolls back the whole transaction so no
        # partial wipe is left behind.
        remaining = await self.repo.count_tenant_rows(self.org_id)
        leftovers = {t: n for t, n in remaining.items() if n > 0}
        if leftovers:
            raise RuntimeError(
                f"Erasure verification failed — rows survived in {leftovers}. "
                "Transaction rolled back; nothing was deleted."
            )

        certificate = self._build_certificate(
            organization_id=self.org_id,
            organization_name=org_name,
            organization_slug=org_slug,
            subject_type=ErasureSubjectType.TENANT,
            subject_user_id=None,
            method=ErasureMethod.ORDERED_DELETE,
            requested_by_user_id=requested_by_user_id,
            requested_by_email=requested_by_email,
            row_counts=row_counts,
        )
        self.db.add(certificate)
        await self.db.flush()
        await self.db.refresh(certificate)
        return certificate

    async def erase_user(self, user_id: uuid.UUID, requester: User) -> ErasureCertificate:
        """Anonymize a single user in place and issue a certificate."""
        org = await self._load_org()
        user = (
            await self.db.execute(
                select(User).where(
                    User.id == user_id, User.organization_id == self.org_id
                )
            )
        ).scalar_one_or_none()
        if user is None:
            raise NotFoundError("Usuario no encontrado en esta organización")

        await self.repo.anonymize_user(self.org_id, user_id)

        # The org survives → this erasure IS auditable in audit_log.
        await log_audit_event(
            self.db,
            organization_id=self.org_id,
            event_type=AuditEventType.USER_ERASED,
            resource_type="user",
            resource_id=user_id,
            actor_user_id=requester.id,
            context={"method": ErasureMethod.ANONYMIZE.value},
        )

        certificate = self._build_certificate(
            organization_id=self.org_id,
            organization_name=org.name,
            organization_slug=org.slug,
            subject_type=ErasureSubjectType.USER,
            subject_user_id=user_id,
            method=ErasureMethod.ANONYMIZE,
            requested_by_user_id=requester.id,
            requested_by_email=requester.email,
            row_counts={"users_anonymized": 1},
        )
        self.db.add(certificate)
        await self.db.flush()
        await self.db.refresh(certificate)
        return certificate

    # ─── Certificate construction ─────────────────────────────────────────────
    @staticmethod
    def _build_certificate(
        *,
        organization_id: uuid.UUID,
        organization_name: str,
        organization_slug: str,
        subject_type: ErasureSubjectType,
        subject_user_id: uuid.UUID | None,
        method: ErasureMethod,
        requested_by_user_id: uuid.UUID | None,
        requested_by_email: str | None,
        row_counts: dict[str, int],
    ) -> ErasureCertificate:
        total = sum(row_counts.values())
        # Hash over the stable payload so the counts/metadata are tamper-evident.
        payload = {
            "organization_id": str(organization_id),
            "organization_slug": organization_slug,
            "subject_type": subject_type.value,
            "subject_user_id": str(subject_user_id) if subject_user_id else None,
            "method": method.value,
            "requested_by_user_id": (
                str(requested_by_user_id) if requested_by_user_id else None
            ),
            "row_counts": row_counts,
            "total_rows_erased": total,
        }
        content_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()

        return ErasureCertificate(
            organization_id=organization_id,
            organization_name=organization_name,
            organization_slug=organization_slug,
            subject_type=subject_type,
            subject_user_id=subject_user_id,
            method=method,
            requested_by_user_id=requested_by_user_id,
            requested_by_email=requested_by_email,
            row_counts=row_counts,
            total_rows_erased=total,
            content_hash=content_hash,
        )
