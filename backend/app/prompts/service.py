import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.models import Agent, AgentDefinition
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.pagination import PaginatedResponse, PaginationParams
from app.prompts.models import PromptTemplate, PromptVersion
from app.prompts.repository import PromptRepository
from app.prompts.schemas import (
    PromptCompareResponse,
    PromptDiff,
    PromptTemplateCreate,
    PromptTemplateResponse,
    PromptTemplateUpdate,
    PromptVersionCreate,
    PromptVersionResponse,
)


class PromptService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = PromptRepository(db)

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

    async def _get_agent_or_404(self, agent_id: uuid.UUID) -> Agent:
        result = await self.db.execute(
            select(Agent)
            .options(selectinload(Agent.definition))
            .where(Agent.id == agent_id)
        )
        agent = result.scalar_one_or_none()
        if agent is None:
            raise NotFoundError(detail=f"Agent {agent_id} not found")
        return agent

    async def _get_definition_or_404(self, agent_id: uuid.UUID) -> AgentDefinition:
        result = await self.db.execute(
            select(AgentDefinition).where(AgentDefinition.agent_id == agent_id)
        )
        defn = result.scalar_one_or_none()
        if defn is None:
            raise NotFoundError(detail=f"AgentDefinition for agent {agent_id} not found")
        return defn

    # ------------------------------------------------------------------
    # Prompt Versions
    # ------------------------------------------------------------------

    async def list_versions(
        self, agent_id: uuid.UUID, pagination: PaginationParams
    ) -> PaginatedResponse:
        await self._get_agent_or_404(agent_id)
        versions, total = await self.repo.list_versions(agent_id, pagination)
        items = [PromptVersionResponse.model_validate(v) for v in versions]
        return PaginatedResponse.create(items=items, total=total, params=pagination)

    async def create_version(
        self, agent_id: uuid.UUID, data: PromptVersionCreate
    ) -> PromptVersionResponse:
        await self._get_agent_or_404(agent_id)
        next_version = await self.repo.get_next_version_number(agent_id)

        version = PromptVersion(
            agent_id=agent_id,
            version=next_version,
            system_prompt=data.system_prompt,
            model_provider=data.model_provider,
            model_name=data.model_name,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
            tools=data.tools,
            change_notes=data.change_notes,
            created_by=data.created_by,
            is_active=False,
        )
        version = await self.repo.create_version(version)
        return PromptVersionResponse.model_validate(version)

    async def activate_version(
        self, agent_id: uuid.UUID, version_number: int
    ) -> PromptVersionResponse:
        agent = await self._get_agent_or_404(agent_id)
        version = await self.repo.get_version(agent_id, version_number)
        if version is None:
            raise NotFoundError(
                detail=f"Version {version_number} not found for agent {agent_id}"
            )

        version = await self.repo.activate_version(agent_id, version_number)

        # Update the AgentDefinition with the activated version's data
        defn = await self._get_definition_or_404(agent_id)
        defn.system_prompt = version.system_prompt
        defn.model_provider = version.model_provider
        defn.model_name = version.model_name
        defn.temperature = version.temperature
        defn.max_tokens = version.max_tokens
        defn.tools = version.tools
        defn.version = version.version
        await self.db.flush()

        return PromptVersionResponse.model_validate(version)

    async def compare_versions(
        self, agent_id: uuid.UUID, v1: int, v2: int
    ) -> PromptCompareResponse:
        await self._get_agent_or_404(agent_id)

        version_a = await self.repo.get_version(agent_id, v1)
        if version_a is None:
            raise NotFoundError(detail=f"Version {v1} not found for agent {agent_id}")

        version_b = await self.repo.get_version(agent_id, v2)
        if version_b is None:
            raise NotFoundError(detail=f"Version {v2} not found for agent {agent_id}")

        compare_fields = [
            "system_prompt",
            "model_provider",
            "model_name",
            "temperature",
            "max_tokens",
            "tools",
        ]

        diffs = []
        for field in compare_fields:
            old_val = getattr(version_a, field)
            new_val = getattr(version_b, field)
            if str(old_val) != str(new_val):
                diffs.append(
                    PromptDiff(
                        field=field,
                        old_value=str(old_val) if old_val is not None else None,
                        new_value=str(new_val) if new_val is not None else None,
                    )
                )

        return PromptCompareResponse(version_a=v1, version_b=v2, diffs=diffs)

    async def apply_template(
        self, agent_id: uuid.UUID, template_id: uuid.UUID
    ) -> PromptVersionResponse:
        await self._get_agent_or_404(agent_id)

        template = await self.repo.get_template(template_id)
        if template is None:
            raise NotFoundError(detail=f"Template {template_id} not found")

        next_version = await self.repo.get_next_version_number(agent_id)

        version = PromptVersion(
            agent_id=agent_id,
            version=next_version,
            system_prompt=template.system_prompt,
            model_provider=template.model_provider,
            model_name=template.model_name,
            temperature=float(template.temperature),
            max_tokens=template.max_tokens,
            tools=template.tools,
            change_notes=f"Applied template: {template.name}",
            created_by="system",
            is_active=False,
        )
        version = await self.repo.create_version(version)

        # Increment template usage count
        await self.repo.increment_template_usage(template_id)

        return PromptVersionResponse.model_validate(version)

    async def create_initial_version(self, agent_id: uuid.UUID) -> PromptVersionResponse:
        """Read current AgentDefinition and create version 1 from it."""
        defn = await self._get_definition_or_404(agent_id)

        # Check if version 1 already exists
        existing = await self.repo.get_version(agent_id, 1)
        if existing is not None:
            return PromptVersionResponse.model_validate(existing)

        version = PromptVersion(
            agent_id=agent_id,
            version=1,
            system_prompt=defn.system_prompt or "",
            model_provider=defn.model_provider,
            model_name=defn.model_name,
            temperature=float(defn.temperature),
            max_tokens=defn.max_tokens,
            tools=defn.tools,
            change_notes="Initial version from agent definition",
            created_by="system",
            is_active=True,
        )
        version = await self.repo.create_version(version)
        return PromptVersionResponse.model_validate(version)

    # ------------------------------------------------------------------
    # Prompt Templates
    # ------------------------------------------------------------------

    async def list_templates(
        self,
        pagination: PaginationParams,
        category: str | None = None,
        search: str | None = None,
    ) -> PaginatedResponse:
        templates, total = await self.repo.list_templates(pagination, category, search)
        items = [PromptTemplateResponse.model_validate(t) for t in templates]
        return PaginatedResponse.create(items=items, total=total, params=pagination)

    async def get_template(self, template_id: uuid.UUID) -> PromptTemplateResponse:
        template = await self.repo.get_template(template_id)
        if template is None:
            raise NotFoundError(detail=f"Template {template_id} not found")
        return PromptTemplateResponse.model_validate(template)

    async def create_template(
        self, data: PromptTemplateCreate
    ) -> PromptTemplateResponse:
        slug = await self._unique_slug(data.name)

        template = PromptTemplate(
            name=data.name,
            slug=slug,
            description=data.description,
            category=data.category,
            system_prompt=data.system_prompt,
            model_provider=data.model_provider,
            model_name=data.model_name,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
            tools=data.tools,
            tags=data.tags,
        )
        template = await self.repo.create_template(template)
        return PromptTemplateResponse.model_validate(template)

    async def update_template(
        self, template_id: uuid.UUID, data: PromptTemplateUpdate
    ) -> PromptTemplateResponse:
        template = await self.repo.get_template(template_id)
        if template is None:
            raise NotFoundError(detail=f"Template {template_id} not found")

        update_data = data.model_dump(exclude_unset=True)

        # If name changed, regenerate slug
        if "name" in update_data and update_data["name"] is not None:
            update_data["slug"] = await self._unique_slug(update_data["name"])

        template = await self.repo.update_template(template, update_data)
        return PromptTemplateResponse.model_validate(template)

    async def delete_template(self, template_id: uuid.UUID) -> None:
        template = await self.repo.get_template(template_id)
        if template is None:
            raise NotFoundError(detail=f"Template {template_id} not found")
        await self.repo.delete_template(template)
