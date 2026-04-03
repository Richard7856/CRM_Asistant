import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.models import Agent
from app.core.pagination import PaginationParams
from app.departments.models import Department


class DepartmentRepository:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id

    def _scoped(self):
        return select(Department).where(Department.organization_id == self.org_id)

    async def get_by_id(self, department_id: uuid.UUID) -> Department | None:
        result = await self.db.execute(
            self._scoped().where(Department.id == department_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Department | None:
        result = await self.db.execute(
            self._scoped().where(Department.slug == slug)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Department | None:
        result = await self.db.execute(
            self._scoped().where(Department.name == name)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self, pagination: PaginationParams
    ) -> tuple[list[Department], int]:
        base = self._scoped()
        count_result = await self.db.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = count_result.scalar_one()

        result = await self.db.execute(
            base.order_by(Department.name)
            .offset(pagination.offset)
            .limit(pagination.size)
        )
        departments = list(result.scalars().all())
        return departments, total

    async def create(self, department: Department) -> Department:
        self.db.add(department)
        await self.db.flush()
        await self.db.refresh(department)
        return department

    async def update(self, department: Department, data: dict) -> Department:
        for key, value in data.items():
            setattr(department, key, value)
        await self.db.flush()
        await self.db.refresh(department)
        return department

    async def delete(self, department: Department) -> None:
        await self.db.delete(department)
        await self.db.flush()

    async def get_tree(self) -> list[Department]:
        result = await self.db.execute(
            self._scoped()
            .options(selectinload(Department.children))
            .order_by(Department.name)
        )
        return list(result.scalars().unique().all())

    async def get_agents_in_department(self, department_id: uuid.UUID) -> list[Agent]:
        result = await self.db.execute(
            select(Agent)
            .where(Agent.department_id == department_id, Agent.organization_id == self.org_id)
            .order_by(Agent.name)
        )
        return list(result.scalars().all())

    async def count_agents(self, department_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(Agent)
            .where(Agent.department_id == department_id, Agent.organization_id == self.org_id)
        )
        return result.scalar_one()
