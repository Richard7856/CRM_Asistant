import hashlib
import re
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import (
    Agent,
    AgentDefinition,
    AgentIntegration,
    AgentOrigin,
    AgentStatus,
    ApiKey,
    Role,
)
from app.agents.repository import AgentRepository
from app.agents.schemas import (
    AgentCreateInternal,
    AgentDetailResponse,
    AgentRegisterExternal,
    AgentResponse,
    AgentUpdate,
    ApiKeyOut,
    DefinitionDetail,
    IntegrationDetail,
    RoleCreate,
    RoleResponse,
)
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.pagination import PaginatedResponse, PaginationParams
from app.departments.models import Department


class AgentService:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id
        self.repo = AgentRepository(db, org_id)

    # ------------------------------------------------------------------
    # Slug helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _slugify(name: str) -> str:
        slug = name.lower().strip()
        slug = slug.replace(" ", "-")
        slug = re.sub(r"[^a-z0-9\-]", "", slug)
        slug = re.sub(r"-+", "-", slug).strip("-")
        return slug

    async def _unique_slug(self, name: str) -> str:
        base = self._slugify(name)
        slug = base
        counter = 1
        while await self.repo.slug_exists(slug):
            slug = f"{base}-{counter}"
            counter += 1
        return slug

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    async def _validate_role(self, role_id: uuid.UUID) -> Role:
        role = await self.repo.get_role_by_id(role_id)
        if role is None:
            raise NotFoundError(detail=f"Role {role_id} not found")
        return role

    async def _validate_department(self, department_id: uuid.UUID) -> Department:
        from sqlalchemy import select

        result = await self.db.execute(
            select(Department).where(Department.id == department_id)
        )
        dept = result.scalar_one_or_none()
        if dept is None:
            raise NotFoundError(detail=f"Department {department_id} not found")
        return dept

    async def _validate_supervisor(self, supervisor_id: uuid.UUID) -> Agent:
        agent = await self.repo.get_by_id(supervisor_id)
        if agent is None:
            raise NotFoundError(detail=f"Supervisor agent {supervisor_id} not found")
        return agent

    # ------------------------------------------------------------------
    # API key helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_api_key() -> tuple[str, str, str]:
        """Return (raw_key, key_prefix, key_hash)."""
        raw_key = secrets.token_urlsafe(32)
        key_prefix = raw_key[:8]
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        return raw_key, key_prefix, key_hash

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _agent_to_response(agent: Agent) -> AgentResponse:
        return AgentResponse(
            id=agent.id,
            name=agent.name,
            slug=agent.slug,
            description=agent.description,
            origin=agent.origin,
            status=agent.status,
            role_id=agent.role_id,
            department_id=agent.department_id,
            supervisor_id=agent.supervisor_id,
            avatar_url=agent.avatar_url,
            capabilities=agent.capabilities,
            metadata_=agent.metadata_,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
            last_heartbeat_at=agent.last_heartbeat_at,
            role_name=agent.role.name if agent.role else None,
            department_name=agent.department.name if agent.department else None,
            supervisor_name=agent.supervisor.name if agent.supervisor else None,
        )

    @staticmethod
    def _agent_to_detail(agent: Agent) -> AgentDetailResponse:
        integration = None
        definition = None
        if agent.origin == AgentOrigin.EXTERNAL and agent.integration:
            integration = IntegrationDetail.model_validate(agent.integration)
        if agent.origin == AgentOrigin.INTERNAL and agent.definition:
            definition = DefinitionDetail.model_validate(agent.definition)

        return AgentDetailResponse(
            id=agent.id,
            name=agent.name,
            slug=agent.slug,
            description=agent.description,
            origin=agent.origin,
            status=agent.status,
            role_id=agent.role_id,
            department_id=agent.department_id,
            supervisor_id=agent.supervisor_id,
            avatar_url=agent.avatar_url,
            capabilities=agent.capabilities,
            metadata_=agent.metadata_,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
            last_heartbeat_at=agent.last_heartbeat_at,
            role_name=agent.role.name if agent.role else None,
            department_name=agent.department.name if agent.department else None,
            supervisor_name=agent.supervisor.name if agent.supervisor else None,
            integration=integration,
            definition=definition,
        )

    # ------------------------------------------------------------------
    # Agent CRUD
    # ------------------------------------------------------------------

    async def create_internal_agent(self, payload: AgentCreateInternal) -> AgentDetailResponse:
        if payload.role_id:
            await self._validate_role(payload.role_id)
        if payload.department_id:
            await self._validate_department(payload.department_id)
        if payload.supervisor_id:
            await self._validate_supervisor(payload.supervisor_id)

        slug = await self._unique_slug(payload.name)

        agent = Agent(
            name=payload.name,
            slug=slug,
            description=payload.description,
            origin=AgentOrigin.INTERNAL,
            status=AgentStatus.IDLE,
            role_id=payload.role_id,
            department_id=payload.department_id,
            supervisor_id=payload.supervisor_id,
            avatar_url=payload.avatar_url,
            capabilities=payload.capabilities or [],
            organization_id=self.org_id,
        )
        self.db.add(agent)
        await self.db.flush()

        definition = AgentDefinition(
            agent_id=agent.id,
            system_prompt=payload.system_prompt,
            model_provider=payload.model_provider,
            model_name=payload.model_name,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            tools=payload.tools or [],
        )
        self.db.add(definition)
        await self.db.flush()

        # Reload with relationships eagerly loaded
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        result = await self.db.execute(
            select(Agent)
            .options(
                selectinload(Agent.role),
                selectinload(Agent.department),
                selectinload(Agent.supervisor),
                selectinload(Agent.integration),
                selectinload(Agent.definition),
            )
            .where(Agent.id == agent.id)
        )
        agent = result.scalar_one()
        return self._agent_to_detail(agent)

    async def register_external_agent(
        self, payload: AgentRegisterExternal
    ) -> tuple[AgentDetailResponse, ApiKeyOut]:
        if payload.role_id:
            await self._validate_role(payload.role_id)
        if payload.department_id:
            await self._validate_department(payload.department_id)
        if payload.supervisor_id:
            await self._validate_supervisor(payload.supervisor_id)

        slug = await self._unique_slug(payload.name)

        agent = Agent(
            name=payload.name,
            slug=slug,
            description=payload.description,
            origin=AgentOrigin.EXTERNAL,
            status=AgentStatus.IDLE,
            role_id=payload.role_id,
            department_id=payload.department_id,
            supervisor_id=payload.supervisor_id,
            avatar_url=payload.avatar_url,
            capabilities=payload.capabilities or [],
            organization_id=self.org_id,
        )
        self.db.add(agent)
        await self.db.flush()

        integration = AgentIntegration(
            agent_id=agent.id,
            integration_type=payload.integration_type,
            platform=payload.platform,
            endpoint_url=payload.endpoint_url,
            polling_interval_seconds=payload.polling_interval_seconds,
            config=payload.integration_config or {},
        )
        self.db.add(integration)

        # Generate API key
        raw_key, key_prefix, key_hash = self._generate_api_key()
        api_key = ApiKey(
            agent_id=agent.id,
            key_prefix=key_prefix,
            key_hash=key_hash,
            label="default",
            scopes=["agent:report", "agent:heartbeat"],
        )
        self.db.add(api_key)
        await self.db.flush()

        agent = await self.repo.get_by_id(agent.id)
        agent_detail = self._agent_to_detail(agent)

        api_key_out = ApiKeyOut(
            id=api_key.id,
            key_prefix=key_prefix,
            raw_key=raw_key,
            label=api_key.label,
            scopes=api_key.scopes,
            expires_at=api_key.expires_at,
        )
        return agent_detail, api_key_out

    async def update_agent(self, agent_id: uuid.UUID, payload: AgentUpdate) -> AgentResponse:
        agent = await self.repo.get_by_id(agent_id)
        if agent is None:
            raise NotFoundError(detail=f"Agent {agent_id} not found")

        data = payload.model_dump(exclude_unset=True)

        if "role_id" in data and data["role_id"] is not None:
            await self._validate_role(data["role_id"])
        if "department_id" in data and data["department_id"] is not None:
            await self._validate_department(data["department_id"])
        if "supervisor_id" in data and data["supervisor_id"] is not None:
            await self._validate_supervisor(data["supervisor_id"])

        agent = await self.repo.update(agent, data)
        return self._agent_to_response(agent)

    async def get_agent(self, agent_id: uuid.UUID) -> AgentDetailResponse:
        agent = await self.repo.get_by_id(agent_id)
        if agent is None:
            raise NotFoundError(detail=f"Agent {agent_id} not found")

        # Eager-load integration / definition for detail response
        from sqlalchemy.orm import selectinload
        from sqlalchemy import select

        result = await self.db.execute(
            select(Agent)
            .options(
                selectinload(Agent.role),
                selectinload(Agent.department),
                selectinload(Agent.supervisor),
                selectinload(Agent.integration),
                selectinload(Agent.definition),
            )
            .where(Agent.id == agent_id)
        )
        agent = result.scalar_one()
        return self._agent_to_detail(agent)

    async def list_agents(
        self,
        pagination: PaginationParams,
        *,
        department_id: uuid.UUID | None = None,
        status: AgentStatus | None = None,
        origin: AgentOrigin | None = None,
        role_id: uuid.UUID | None = None,
    ) -> PaginatedResponse:
        agents, total = await self.repo.list_all(
            pagination,
            department_id=department_id,
            status=status,
            origin=origin,
            role_id=role_id,
        )
        items = [self._agent_to_response(a) for a in agents]
        return PaginatedResponse.create(items=items, total=total, params=pagination)

    async def get_subordinates(self, agent_id: uuid.UUID) -> list[AgentResponse]:
        agent = await self.repo.get_by_id(agent_id)
        if agent is None:
            raise NotFoundError(detail=f"Agent {agent_id} not found")
        subordinates = await self.repo.get_subordinates(agent_id)
        return [self._agent_to_response(s) for s in subordinates]

    async def deactivate_agent(self, agent_id: uuid.UUID) -> AgentResponse:
        agent = await self.repo.get_by_id(agent_id)
        if agent is None:
            raise NotFoundError(detail=f"Agent {agent_id} not found")
        agent = await self.repo.delete(agent)
        return self._agent_to_response(agent)

    async def record_heartbeat(self, agent_id: uuid.UUID) -> AgentResponse:
        agent = await self.repo.get_by_id(agent_id)
        if agent is None:
            raise NotFoundError(detail=f"Agent {agent_id} not found")
        agent = await self.repo.update(
            agent, {"last_heartbeat_at": datetime.now(timezone.utc)}
        )
        return self._agent_to_response(agent)

    # ------------------------------------------------------------------
    # Roles
    # ------------------------------------------------------------------

    async def create_role(self, payload: RoleCreate) -> RoleResponse:
        role = Role(
            name=payload.name,
            level=payload.level,
            description=payload.description,
        )
        role = await self.repo.create_role(role)
        return RoleResponse.model_validate(role)

    async def list_roles(self) -> list[RoleResponse]:
        roles = await self.repo.list_roles()
        return [RoleResponse.model_validate(r) for r in roles]
