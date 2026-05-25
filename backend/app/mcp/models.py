"""
MCP Router scope storage.

Two tables that together answer the question:
"What agents and tools can a user from department X invoke through the Router?"

Both tables are scoped per-department (not per-user) — the unit of scope is
the department. Users inherit the scope of their department.

OWNER/ADMIN don't need entries here — they bypass scope checks via role
(they have org-wide access).

The Router queries these tables on EVERY request (no cache) so that
revoking a permission has effect within milliseconds.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, PrimaryKeyConstraint, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DepartmentAgentPermission(Base):
    """A department is allowed to invoke a specific agent through the Router."""

    __tablename__ = "department_agent_permissions"

    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        PrimaryKeyConstraint("department_id", "agent_id"),
    )

    department = relationship("Department", foreign_keys=[department_id])
    agent = relationship("Agent", foreign_keys=[agent_id])


class DepartmentToolPermission(Base):
    """A department is allowed to invoke a specific tool through the Router.

    Tool names are strings (matching the @register_tool registry — see
    app/workers/tool_registry.py). E.g. "create_agent", "assign_task".
    """

    __tablename__ = "department_tool_permissions"

    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=False,
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        PrimaryKeyConstraint("department_id", "tool_name"),
    )

    department = relationship("Department", foreign_keys=[department_id])
