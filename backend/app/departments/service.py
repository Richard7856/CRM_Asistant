import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.pagination import PaginationParams
from app.departments.models import Department
from app.departments.repository import DepartmentRepository
from app.departments.schemas import (
    DepartmentCreate,
    DepartmentResponse,
    DepartmentTreeNode,
    DepartmentUpdate,
)


def _generate_slug(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


class DepartmentService:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id
        self.repo = DepartmentRepository(db, org_id)

    async def create_department(self, data: DepartmentCreate) -> DepartmentResponse:
        existing = await self.repo.get_by_name(data.name)
        if existing:
            raise ConflictError(detail=f"Department with name '{data.name}' already exists")

        if data.parent_id:
            parent = await self.repo.get_by_id(data.parent_id)
            if not parent:
                raise BadRequestError(detail="Parent department not found")

        slug = _generate_slug(data.name)

        existing_slug = await self.repo.get_by_slug(slug)
        if existing_slug:
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"

        department = Department(
            name=data.name,
            slug=slug,
            description=data.description,
            parent_id=data.parent_id,
            organization_id=self.org_id,
        )
        department = await self.repo.create(department)
        agent_count = await self.repo.count_agents(department.id)
        response = DepartmentResponse.model_validate(department)
        response.agent_count = agent_count
        return response

    async def update_department(
        self, department_id: uuid.UUID, data: DepartmentUpdate
    ) -> DepartmentResponse:
        department = await self.repo.get_by_id(department_id)
        if not department:
            raise NotFoundError(detail="Department not found")

        update_data: dict = data.model_dump(exclude_unset=True)

        if "name" in update_data and update_data["name"] != department.name:
            existing = await self.repo.get_by_name(update_data["name"])
            if existing:
                raise ConflictError(
                    detail=f"Department with name '{update_data['name']}' already exists"
                )
            slug = _generate_slug(update_data["name"])
            existing_slug = await self.repo.get_by_slug(slug)
            if existing_slug and existing_slug.id != department.id:
                slug = f"{slug}-{uuid.uuid4().hex[:6]}"
            update_data["slug"] = slug

        if "parent_id" in update_data and update_data["parent_id"]:
            if update_data["parent_id"] == department_id:
                raise BadRequestError(detail="Department cannot be its own parent")
            parent = await self.repo.get_by_id(update_data["parent_id"])
            if not parent:
                raise BadRequestError(detail="Parent department not found")

        if "head_agent_id" in update_data and update_data["head_agent_id"]:
            from sqlalchemy import select
            result = await self.db.execute(
                select(Agent).where(Agent.id == update_data["head_agent_id"])
            )
            agent = result.scalar_one_or_none()
            if not agent:
                raise BadRequestError(detail="Head agent not found")

        department = await self.repo.update(department, update_data)
        agent_count = await self.repo.count_agents(department.id)
        response = DepartmentResponse.model_validate(department)
        response.agent_count = agent_count
        return response

    async def get_department(self, department_id: uuid.UUID) -> DepartmentResponse:
        department = await self.repo.get_by_id(department_id)
        if not department:
            raise NotFoundError(detail="Department not found")
        agent_count = await self.repo.count_agents(department.id)
        response = DepartmentResponse.model_validate(department)
        response.agent_count = agent_count
        return response

    async def list_departments(
        self, pagination: PaginationParams
    ) -> tuple[list[DepartmentResponse], int]:
        departments, total = await self.repo.list_all(pagination)
        responses = []
        for dept in departments:
            count = await self.repo.count_agents(dept.id)
            response = DepartmentResponse.model_validate(dept)
            response.agent_count = count
            responses.append(response)
        return responses, total

    async def get_department_tree(self) -> list[DepartmentTreeNode]:
        all_departments = await self.repo.get_tree()

        dept_map: dict[uuid.UUID, DepartmentTreeNode] = {}
        for dept in all_departments:
            count = await self.repo.count_agents(dept.id)
            node = DepartmentTreeNode.model_validate(dept)
            node.agent_count = count
            node.children = []
            dept_map[dept.id] = node

        roots: list[DepartmentTreeNode] = []
        for node in dept_map.values():
            if node.parent_id and node.parent_id in dept_map:
                dept_map[node.parent_id].children.append(node)
            else:
                roots.append(node)

        return roots

    async def get_agents_in_department(self, department_id: uuid.UUID) -> list:
        department = await self.repo.get_by_id(department_id)
        if not department:
            raise NotFoundError(detail="Department not found")
        return await self.repo.get_agents_in_department(department_id)
