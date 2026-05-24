"""
Audit log service — single entry point for recording events.

Any code that needs to log an audit event imports `log_audit_event` from here.
The helper hashes input/output with SHA-256 before persisting — we never store
the raw content, only the digest. This protects PII while still letting auditors
verify "did this exact value pass through the system on day X".

Plus AuditService for queries (list with filters, export to CSV).
"""

import csv
import hashlib
import io
import json
import uuid
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEventType, AuditLog, AuditResult


def _hash_payload(payload: Any) -> str:
    """
    SHA-256 hex digest (64 chars) of a payload.
    - dict/list/etc: stable JSON serialization first
    - bytes: hashed directly
    - other: str() representation
    Used for forensics: prove "this exact content was processed" without storing it.
    """
    if payload is None:
        return ""
    if isinstance(payload, bytes):
        data = payload
    elif isinstance(payload, (dict, list, tuple)):
        # sort_keys for deterministic hashes across runs / Python versions
        data = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    else:
        data = str(payload).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


async def log_audit_event(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_type: AuditEventType,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_agent_id: uuid.UUID | None = None,
    result: AuditResult = AuditResult.SUCCESS,
    input_payload: Any = None,
    output_payload: Any = None,
    autonomy_level: int | None = None,
    approved_by_user_id: uuid.UUID | None = None,
    context: dict | None = None,
) -> AuditLog:
    """
    Record an audit event. Hashes input/output before storing.

    Returns the persisted AuditLog row (flushed but not committed — caller is
    responsible for transaction boundaries).
    """
    entry = AuditLog(
        organization_id=organization_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_user_id=actor_user_id,
        actor_agent_id=actor_agent_id,
        result=result,
        input_hash=_hash_payload(input_payload) if input_payload is not None else None,
        output_hash=_hash_payload(output_payload) if output_payload is not None else None,
        autonomy_level=autonomy_level,
        approved_by_user_id=approved_by_user_id,
        context=context or {},
    )
    db.add(entry)
    await db.flush()
    return entry


class AuditService:
    """Query side: list events with filters, export to CSV. Read-only."""

    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id

    async def list_events(
        self,
        page: int = 1,
        size: int = 50,
        event_type: AuditEventType | None = None,
        resource_type: str | None = None,
        resource_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
        actor_agent_id: uuid.UUID | None = None,
        result: AuditResult | None = None,
        from_ts: Any = None,  # datetime
        to_ts: Any = None,
    ) -> tuple[list[AuditLog], int]:
        filters = [AuditLog.organization_id == self.org_id]
        if event_type is not None:
            filters.append(AuditLog.event_type == event_type)
        if resource_type is not None:
            filters.append(AuditLog.resource_type == resource_type)
        if resource_id is not None:
            filters.append(AuditLog.resource_id == resource_id)
        if actor_user_id is not None:
            filters.append(AuditLog.actor_user_id == actor_user_id)
        if actor_agent_id is not None:
            filters.append(AuditLog.actor_agent_id == actor_agent_id)
        if result is not None:
            filters.append(AuditLog.result == result)
        if from_ts is not None:
            filters.append(AuditLog.occurred_at >= from_ts)
        if to_ts is not None:
            filters.append(AuditLog.occurred_at <= to_ts)

        where = and_(*filters)

        # Count
        count_stmt = select(AuditLog).where(where)
        count_result = await self.db.execute(count_stmt)
        total = len(count_result.scalars().all())

        # Page
        offset = (page - 1) * size
        stmt = (
            select(AuditLog)
            .where(where)
            .order_by(AuditLog.occurred_at.desc())
            .offset(offset)
            .limit(size)
        )
        result_rows = await self.db.execute(stmt)
        return list(result_rows.scalars().all()), total

    async def export_csv(
        self,
        event_type: AuditEventType | None = None,
        resource_type: str | None = None,
        resource_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
        actor_agent_id: uuid.UUID | None = None,
        from_ts: Any = None,
        to_ts: Any = None,
        limit: int = 10000,
    ) -> str:
        """
        Returns a CSV string with up to `limit` rows matching the filters.
        Caps at 10k rows to avoid runaway exports. For larger exports we'll
        need streaming + retention policy first (P0.7).
        """
        filters = [AuditLog.organization_id == self.org_id]
        if event_type is not None:
            filters.append(AuditLog.event_type == event_type)
        if resource_type is not None:
            filters.append(AuditLog.resource_type == resource_type)
        if resource_id is not None:
            filters.append(AuditLog.resource_id == resource_id)
        if actor_user_id is not None:
            filters.append(AuditLog.actor_user_id == actor_user_id)
        if actor_agent_id is not None:
            filters.append(AuditLog.actor_agent_id == actor_agent_id)
        if from_ts is not None:
            filters.append(AuditLog.occurred_at >= from_ts)
        if to_ts is not None:
            filters.append(AuditLog.occurred_at <= to_ts)

        stmt = (
            select(AuditLog)
            .where(and_(*filters))
            .order_by(AuditLog.occurred_at.desc())
            .limit(limit)
        )
        result_rows = await self.db.execute(stmt)
        rows = list(result_rows.scalars().all())

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "id", "occurred_at", "event_type", "result",
            "resource_type", "resource_id",
            "actor_user_id", "actor_agent_id",
            "input_hash", "output_hash",
            "autonomy_level", "approved_by_user_id",
            "context_json",
        ])
        for r in rows:
            writer.writerow([
                str(r.id),
                r.occurred_at.isoformat() if r.occurred_at else "",
                r.event_type.value,
                r.result.value,
                r.resource_type or "",
                str(r.resource_id) if r.resource_id else "",
                str(r.actor_user_id) if r.actor_user_id else "",
                str(r.actor_agent_id) if r.actor_agent_id else "",
                r.input_hash or "",
                r.output_hash or "",
                r.autonomy_level if r.autonomy_level is not None else "",
                str(r.approved_by_user_id) if r.approved_by_user_id else "",
                json.dumps(r.context, sort_keys=True, default=str) if r.context else "",
            ])
        return buf.getvalue()
