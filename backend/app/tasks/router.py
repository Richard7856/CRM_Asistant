import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import PaginatedResponse, PaginationParams
from app.tasks.models import TaskPriority, TaskStatus
from app.tasks.schemas import TaskAssign, TaskCreate, TaskResponse, TaskUpdate
from app.auth.dependencies import get_org_id
from app.tasks.service import TaskService
from app.workers.agent_executor import execute_task

router = APIRouter()


def _get_service(
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
) -> TaskService:
    return TaskService(db, org_id)


@router.get("/", response_model=PaginatedResponse)
async def list_tasks(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    status: TaskStatus | None = Query(default=None),
    priority: TaskPriority | None = Query(default=None),
    assigned_to: uuid.UUID | None = Query(default=None),
    department_id: uuid.UUID | None = Query(default=None),
    service: TaskService = Depends(_get_service),
):
    pagination = PaginationParams(page=page, size=size)
    items, total = await service.list_tasks(
        pagination,
        status=status,
        priority=priority,
        assigned_to=assigned_to,
        department_id=department_id,
    )
    return PaginatedResponse.create(
        items=[i.model_dump() for i in items], total=total, params=pagination
    )


@router.post("/", response_model=TaskResponse, status_code=201)
async def create_task(
    data: TaskCreate,
    service: TaskService = Depends(_get_service),
):
    return await service.create_task(data)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    service: TaskService = Depends(_get_service),
):
    return await service.get_task(task_id)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: uuid.UUID,
    data: TaskUpdate,
    service: TaskService = Depends(_get_service),
):
    return await service.update_task(task_id, data)


@router.post("/{task_id}/assign", response_model=TaskResponse)
async def assign_task(
    task_id: uuid.UUID,
    data: TaskAssign,
    service: TaskService = Depends(_get_service),
):
    return await service.assign_task(task_id, data.agent_id)


@router.post("/{task_id}/execute", response_model=TaskResponse)
async def execute_task_endpoint(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Execute a task using its assigned agent's LLM config (Claude API)."""
    task = await execute_task(task_id, db)
    return TaskResponse.model_validate(task)


@router.get("/{task_id}/subtasks", response_model=list[TaskResponse])
async def get_subtasks(
    task_id: uuid.UUID,
    service: TaskService = Depends(_get_service),
):
    return await service.get_subtasks(task_id)
