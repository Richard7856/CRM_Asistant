import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.pagination import PaginationParams
from app.tasks.models import Task, TaskPriority, TaskStatus


class TaskRepository:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id

    def _scoped(self):
        return select(Task).where(Task.organization_id == self.org_id)

    async def get_by_id(self, task_id: uuid.UUID) -> Task | None:
        result = await self.db.execute(
            self._scoped()
            .options(selectinload(Task.assignee), selectinload(Task.department))
            .where(Task.id == task_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        pagination: PaginationParams,
        *,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assigned_to: uuid.UUID | None = None,
        department_id: uuid.UUID | None = None,
    ) -> tuple[list[Task], int]:
        query = self._scoped()
        count_base = select(func.count()).select_from(Task).where(Task.organization_id == self.org_id)

        if status is not None:
            query = query.where(Task.status == status)
            count_base = count_base.where(Task.status == status)
        if priority is not None:
            query = query.where(Task.priority == priority)
            count_base = count_base.where(Task.priority == priority)
        if assigned_to is not None:
            query = query.where(Task.assigned_to == assigned_to)
            count_base = count_base.where(Task.assigned_to == assigned_to)
        if department_id is not None:
            query = query.where(Task.department_id == department_id)
            count_base = count_base.where(Task.department_id == department_id)

        total = (await self.db.execute(count_base)).scalar_one()

        result = await self.db.execute(
            query.options(selectinload(Task.assignee), selectinload(Task.department))
            .order_by(Task.created_at.desc())
            .offset(pagination.offset)
            .limit(pagination.size)
        )
        return list(result.scalars().all()), total

    async def create(self, task: Task) -> Task:
        self.db.add(task)
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def update(self, task: Task, data: dict) -> Task:
        for key, value in data.items():
            setattr(task, key, value)
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def get_subtasks(self, parent_task_id: uuid.UUID) -> list[Task]:
        result = await self.db.execute(
            self._scoped()
            .where(Task.parent_task_id == parent_task_id)
            .order_by(Task.created_at.desc())
        )
        return list(result.scalars().all())
