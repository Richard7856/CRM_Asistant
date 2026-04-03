import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AgentOrigin(str, enum.Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class AgentStatus(str, enum.Enum):
    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


class RoleLevel(str, enum.Enum):
    AGENT = "agent"
    SUPERVISOR = "supervisor"
    MANAGER = "manager"
    ADMIN = "admin"


class IntegrationType(str, enum.Enum):
    WEBHOOK = "webhook"
    API_POLLING = "api_polling"
    WEBSOCKET = "websocket"
    SDK = "sdk"


# --- Roles & Permissions ---


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    level: Mapped[RoleLevel] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")
    agents = relationship("Agent", back_populates="role")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    codename: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    roles = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )

    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission", back_populates="roles")


# --- Agent ---


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[AgentOrigin] = mapped_column(nullable=False)
    status: Mapped[AgentStatus] = mapped_column(default=AgentStatus.IDLE)
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True, index=True
    )
    supervisor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), index=True
    )
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    capabilities: Mapped[dict] = mapped_column(JSONB, default=list)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column()

    # Relationships
    organization = relationship("Organization", foreign_keys=[organization_id])
    role = relationship("Role", back_populates="agents")
    department = relationship("Department", back_populates="agents", foreign_keys=[department_id])
    supervisor = relationship("Agent", remote_side="Agent.id", back_populates="subordinates")
    subordinates = relationship("Agent", back_populates="supervisor")
    integration = relationship(
        "AgentIntegration", back_populates="agent", uselist=False, cascade="all, delete-orphan"
    )
    definition = relationship(
        "AgentDefinition", back_populates="agent", uselist=False, cascade="all, delete-orphan"
    )
    tasks_assigned = relationship("Task", back_populates="assignee", foreign_keys="Task.assigned_to")
    activity_logs = relationship("ActivityLog", back_populates="agent")
    api_keys = relationship("ApiKey", back_populates="agent", cascade="all, delete-orphan")


# --- External Agent Integration ---


class AgentIntegration(Base):
    __tablename__ = "agent_integrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), unique=True
    )
    integration_type: Mapped[IntegrationType] = mapped_column(nullable=False)
    platform: Mapped[str | None] = mapped_column(String(50))
    endpoint_url: Mapped[str | None] = mapped_column(String(500))
    api_key_hash: Mapped[str | None] = mapped_column(String(256))
    webhook_secret: Mapped[str | None] = mapped_column(String(256))
    polling_interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    agent = relationship("Agent", back_populates="integration")


# --- Internal Agent Definition ---


class AgentDefinition(Base):
    __tablename__ = "agent_definitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), unique=True
    )
    system_prompt: Mapped[str | None] = mapped_column(Text)
    model_provider: Mapped[str | None] = mapped_column(String(50))
    model_name: Mapped[str | None] = mapped_column(String(100))
    temperature: Mapped[float] = mapped_column(Numeric(3, 2), default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    tools: Mapped[dict] = mapped_column(JSONB, default=list)
    knowledge_base: Mapped[dict] = mapped_column(JSONB, default=dict)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    agent = relationship("Agent", back_populates="definition")


# --- API Keys ---


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    label: Mapped[str | None] = mapped_column(String(100))
    scopes: Mapped[dict] = mapped_column(JSONB, default=lambda: ["report"])
    expires_at: Mapped[datetime | None] = mapped_column()
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    agent = relationship("Agent", back_populates="api_keys")
