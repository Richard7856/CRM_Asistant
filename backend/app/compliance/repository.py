"""
Compliance repository — the raw data work for erasure and export.

Operates on SQLAlchemy *core* tables (Base.metadata.tables[name]) rather than ORM
models so the erasure/export plan can be driven by the table-name lists in
classification.py without importing every model here. Table names come from our
own metadata, never from user input, so building statements from them is safe.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.classification import (
    ERASURE_DELETE_ORDER,
    ERASURE_NULL_BREAKERS,
    tenant_table_names,
)
from app.core.database import Base


def _json_safe(value: Any) -> Any:
    """Convert a DB value into something json.dumps / Pydantic can serialize."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return value


def _serialize_row(mapping: Any) -> dict[str, Any]:
    return {key: _json_safe(val) for key, val in dict(mapping).items()}


class ComplianceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _table(self, name: str):
        return Base.metadata.tables[name]

    # ─── Counting ─────────────────────────────────────────────────────────────
    async def count_tenant_rows(self, org_id: uuid.UUID) -> dict[str, int]:
        """
        Rows per tenant table for this org. Taken BEFORE deletion to build the
        erasure certificate, and again AFTER to verify everything reached zero.
        """
        counts: dict[str, int] = {}
        for name in sorted(tenant_table_names()):
            table = self._table(name)
            stmt = (
                select(func.count())
                .select_from(table)
                .where(table.c.organization_id == org_id)
            )
            counts[name] = int((await self.db.execute(stmt)).scalar_one())
        return counts

    # ─── Export (right of access / portability) ───────────────────────────────
    async def fetch_tenant_export(self, org_id: uuid.UUID) -> dict[str, list[dict]]:
        """Every tenant row for this org, table by table, serialized to dicts."""
        bundle: dict[str, list[dict]] = {}
        for name in sorted(tenant_table_names()):
            table = self._table(name)
            stmt = select(table).where(table.c.organization_id == org_id)
            rows = (await self.db.execute(stmt)).mappings().all()
            bundle[name] = [_serialize_row(r) for r in rows]
        return bundle

    async def fetch_user_rows(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict[str, list[dict]]:
        """
        A single user's identifiable footprint: their own row plus the records
        that reference them as author/actor. Scoped to org_id so an admin can't
        reach a user in another tenant.
        """
        out: dict[str, list[dict]] = {}

        users = self._table("users")
        user_rows = (
            await self.db.execute(
                select(users).where(
                    users.c.id == user_id, users.c.organization_id == org_id
                )
            )
        ).mappings().all()
        out["users"] = [_serialize_row(r) for r in user_rows]

        # Records authored by / attributed to this user, by referencing column.
        references = [
            ("knowledge_documents", "created_by_user_id"),
            ("audit_log", "actor_user_id"),
            ("autonomy_policies", "created_by_user_id"),
            ("approval_requests", "approved_by_user_id"),
        ]
        for table_name, column in references:
            table = self._table(table_name)
            stmt = select(table).where(
                table.c.organization_id == org_id,
                getattr(table.c, column) == user_id,
            )
            rows = (await self.db.execute(stmt)).mappings().all()
            out[f"{table_name}.{column}"] = [_serialize_row(r) for r in rows]
        return out

    async def get_org_user_ids(self, org_id: uuid.UUID) -> list[uuid.UUID]:
        users = self._table("users")
        rows = (
            await self.db.execute(select(users.c.id).where(users.c.organization_id == org_id))
        ).scalars().all()
        return list(rows)

    # ─── Erasure ──────────────────────────────────────────────────────────────
    async def execute_tenant_erasure(self, org_id: uuid.UUID) -> None:
        """
        Physically delete every row belonging to org_id, in dependency order, then
        the organization itself. CASCADE children fall with their parents. Runs
        inside the caller's transaction — the service commits only after the
        certificate is written, so a failure rolls back the whole thing.
        """
        # Phase A — break self-references and the agents↔departments cycle.
        for table_name, null_values in ERASURE_NULL_BREAKERS:
            table = self._table(table_name)
            await self.db.execute(
                update(table)
                .where(table.c.organization_id == org_id)
                .values(**null_values)
            )

        # token_blacklist has no organization_id — purge by this org's user ids
        # before the users themselves disappear.
        user_ids = await self.get_org_user_ids(org_id)
        if user_ids:
            tb = self._table("token_blacklist")
            await self.db.execute(delete(tb).where(tb.c.user_id.in_(user_ids)))

        # Phase B — ordered deletes (FK-holders first).
        for table_name in ERASURE_DELETE_ORDER:
            table = self._table(table_name)
            await self.db.execute(
                delete(table).where(table.c.organization_id == org_id)
            )

        # Finally the organization row itself.
        orgs = self._table("organizations")
        await self.db.execute(delete(orgs).where(orgs.c.id == org_id))

    async def anonymize_user(self, org_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """
        Scrub a single user's PII in place while keeping their operational records
        intact (a knowledge doc they uploaded belongs to the org, not to them, and
        knowledge_documents.created_by_user_id is NOT NULL). After this the person
        is no longer identifiable — the LFPDPPP-compliant alternative to deletion
        when hard-delete would destroy legitimately retained business records.
        """
        users = self._table("users")
        await self.db.execute(
            update(users)
            .where(users.c.id == user_id, users.c.organization_id == org_id)
            .values(
                email=f"erased-{user_id}@anonymized.local",
                full_name="Usuario eliminado",
                password_hash="!erased",  # bcrypt never produces this → login impossible
                is_active=False,
            )
        )
