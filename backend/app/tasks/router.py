import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.pagination import PaginatedResponse, PaginationParams
from app.tasks.models import Task, TaskPriority, TaskStatus
from app.tasks.schemas import TaskAssign, TaskCreate, TaskResponse, TaskUpdate
from app.auth.dependencies import get_org_id
from app.tasks.service import TaskService
from app.workers.agent_executor import execute_task_background
from app.agents.models import Agent

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


@router.post("/{task_id}/execute", response_model=TaskResponse, status_code=202)
async def execute_task_endpoint(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Launch task execution in background — returns 202 immediately.

    The actual result arrives via SSE (event types: task.completed / task.failed).
    This lets the frontend fire 50 executions without blocking; each one
    runs as an independent asyncio coroutine with its own DB session.
    """
    # Validate task exists and has an assigned agent BEFORE launching background work.
    # This way the client gets a clear 404/400 immediately instead of a silent SSE error.
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    if task.assigned_to is None:
        raise HTTPException(status_code=400, detail="Task has no assigned agent")

    # Verify agent exists
    agent_result = await db.execute(
        select(Agent).where(Agent.id == task.assigned_to)
    )
    if agent_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=400, detail="Assigned agent not found")

    # Launch execution in background — does NOT block this response
    asyncio.create_task(
        execute_task_background(task_id),
        name=f"exec-task-{task_id}",
    )

    return TaskResponse.model_validate(task)


@router.get("/{task_id}/subtasks", response_model=list[TaskResponse])
async def get_subtasks(
    task_id: uuid.UUID,
    service: TaskService = Depends(_get_service),
):
    return await service.get_subtasks(task_id)
