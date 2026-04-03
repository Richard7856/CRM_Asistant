import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import PaginatedResponse, PaginationParams
from app.departments.schemas import (
    DepartmentCreate,
    DepartmentResponse,
    DepartmentTreeNode,
    DepartmentUpdate,
)
from app.auth.dependencies import get_org_id
from app.departments.service import DepartmentService

router = APIRouter()


def _get_service(
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
) -> DepartmentService:
    return DepartmentService(db, org_id)


@router.get("/", response_model=PaginatedResponse)
async def list_departments(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    service: DepartmentService = Depends(_get_service),
):
    pagination = PaginationParams(page=page, size=size)
    items, total = await service.list_departments(pagination)
    return PaginatedResponse.create(items=[i.model_dump() for i in items], total=total, params=pagination)


@router.post("/", response_model=DepartmentResponse, status_code=201)
async def create_department(
    data: DepartmentCreate,
    service: DepartmentService = Depends(_get_service),
):
    return await service.create_department(data)


@router.get("/tree", response_model=list[DepartmentTreeNode])
async def get_department_tree(
    service: DepartmentService = Depends(_get_service),
):
    return await service.get_department_tree()


@router.get("/{department_id}", response_model=DepartmentResponse)
async def get_department(
    department_id: uuid.UUID,
    service: DepartmentService = Depends(_get_service),
):
    return await service.get_department(department_id)


@router.patch("/{department_id}", response_model=DepartmentResponse)
async def update_department(
    department_id: uuid.UUID,
    data: DepartmentUpdate,
    service: DepartmentService = Depends(_get_service),
):
    return await service.update_department(department_id, data)


@router.get("/{department_id}/agents")
async def get_agents_in_department(
    department_id: uuid.UUID,
    service: DepartmentService = Depends(_get_service),
):
    return await service.get_agents_in_department(department_id)
