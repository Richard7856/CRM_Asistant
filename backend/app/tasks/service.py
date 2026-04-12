import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.pagination import PaginationParams
from app.departments.models import Department
from app.tasks.models import Task, TaskPriority, TaskStatus
from app.tasks.repository import TaskRepository
from app.tasks.schemas import TaskCreate, TaskResponse, TaskUpdate

logger = logging.getLogger(__name__)


class TaskService:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id
        self.repo = TaskRepository(db, org_id)

    @staticmethod
    def _to_response(task: Task) -> TaskResponse:
        """Convert Task ORM model to response, including joined agent name."""
        resp = TaskResponse.model_validate(task)
        # Populate names from eagerly-loaded relationships
        if hasattr(task, "assignee") and task.assignee is not None:
            resp.assignee_name = task.assignee.name
        if hasattr(task, "department") and task.department is not None:
            resp.department_name = task.department.name
        return resp

    async def _resolve_assignee(self, data: TaskCreate) -> uuid.UUID | None:
        """Auto-assign to department supervisor when department_id is set but assigned_to is not.

        This routes tasks to the department head (supervisor) first,
        who can then delegate to subordinates via the supervisor delegator.
        """
        if data.assigned_to:
            return data.assigned_to

        if not data.department_id:
            return None

        result = await self.db.execute(
            select(Department.head_agent_id).where(
                Department.id == data.department_id,
                Department.organization_id == self.org_id,
            )
        )
        head_agent_id = result.scalar_one_or_none()

        if head_agent_id:
            logger.info(
                "Auto-assigned task to dept supervisor %s (dept %s)",
                head_agent_id, data.department_id,
            )

        return head_agent_id

    async def create_task(self, data: TaskCreate) -> TaskResponse:
        assigned_to = await self._resolve_assignee(data)

        task = Task(
            title=data.title,
            description=data.description,
            priority=data.priority,
            assigned_to=assigned_to,
            department_id=data.department_id,
            parent_task_id=data.parent_task_id,
            due_at=data.due_at,
            status=TaskStatus.ASSIGNED if assigned_to else TaskStatus.PENDING,
            organization_id=self.org_id,
        )
        task = await self.repo.create(task)
        return TaskResponse.model_validate(task)

    async def get_task(self, task_id: uuid.UUID) -> TaskResponse:
        task = await self.repo.get_by_id(task_id)
        if not task:
            raise NotFoundError(detail="Task not found")
        return TaskResponse.model_validate(task)

    async def update_task(self, task_id: uuid.UUID, data: TaskUpdate) -> TaskResponse:
        task = await self.repo.get_by_id(task_id)
        if not task:
            raise NotFoundError(detail="Task not found")

        update_data = data.model_dump(exclude_unset=True)

        if "status" in update_data:
            new_status = update_data["status"]
            if new_status == TaskStatus.IN_PROGRESS and not task.started_at:
                update_data["started_at"] = datetime.now(timezone.utc)
            elif new_status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                update_data["completed_at"] = datetime.now(timezone.utc)

        task = await self.repo.update(task, update_data)
        return TaskResponse.model_validate(task)

    async def list_tasks(
        self,
        pagination: PaginationParams,
        *,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assigned_to: uuid.UUID | None = None,
        department_id: uuid.UUID | None = None,
    ) -> tuple[list[TaskResponse], int]:
        tasks, total = await self.repo.list_all(
            pagination,
            status=status,
            priority=priority,
            assigned_to=assigned_to,
            department_id=department_id,
        )
        return [self._to_response(t) for t in tasks], total

    async def assign_task(self, task_id: uuid.UUID, agent_id: uuid.UUID) -> TaskResponse:
        task = await self.repo.get_by_id(task_id)
        if not task:
            raise NotFoundError(detail="Task not found")

        update_data: dict = {"assigned_to": agent_id}
        if task.status == TaskStatus.PENDING:
            update_data["status"] = TaskStatus.ASSIGNED

        task = await self.repo.update(task, update_data)
        return TaskResponse.model_validate(task)

    async def get_subtasks(self, task_id: uuid.UUID) -> list[TaskResponse]:
        task = await self.repo.get_by_id(task_id)
        if not task:
            raise NotFoundError(detail="Task not found")
        subtasks = await self.repo.get_subtasks(task_id)
        return [TaskResponse.model_validate(t) for t in subtasks]
