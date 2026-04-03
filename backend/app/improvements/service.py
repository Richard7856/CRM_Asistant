import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.pagination import PaginationParams
from app.improvements.models import ImprovementPoint, ImprovementStatus
from app.improvements.repository import ImprovementRepository
from app.improvements.schemas import ImprovementCreate, ImprovementResponse, ImprovementUpdate
from app.tasks.models import TaskPriority


class ImprovementService:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id
        self.repo = ImprovementRepository(db, org_id)

    async def create_improvement(self, data: ImprovementCreate) -> ImprovementResponse:
        improvement = ImprovementPoint(
            agent_id=data.agent_id,
            identified_by=data.identified_by,
            category=data.category,
            title=data.title,
            description=data.description,
            evidence=data.evidence or {},
            priority=data.priority,
            organization_id=self.org_id,
        )
        improvement = await self.repo.create(improvement)
        return ImprovementResponse.model_validate(improvement)

    async def update_improvement(
        self, improvement_id: uuid.UUID, data: ImprovementUpdate
    ) -> ImprovementResponse:
        improvement = await self.repo.get_by_id(improvement_id)
        if not improvement:
            raise NotFoundError(detail="Improvement point not found")

        update_data = data.model_dump(exclude_unset=True)
        improvement = await self.repo.update(improvement, update_data)
        return ImprovementResponse.model_validate(improvement)

    async def list_improvements(
        self,
        pagination: PaginationParams,
        *,
        agent_id: uuid.UUID | None = None,
        status: ImprovementStatus | None = None,
        category: str | None = None,
        priority: TaskPriority | None = None,
    ) -> tuple[list[ImprovementResponse], int]:
        improvements, total = await self.repo.list_all(
            pagination,
            agent_id=agent_id,
            status=status,
            category=category,
            priority=priority,
        )
        return [ImprovementResponse.model_validate(i) for i in improvements], total
