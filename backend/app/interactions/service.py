import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PaginationParams
from app.interactions.models import AgentInteraction, InteractionChannel
from app.interactions.repository import InteractionRepository
from app.interactions.schemas import (
    GraphData,
    GraphEdge,
    GraphNode,
    InteractionCreate,
    InteractionResponse,
)


class InteractionService:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id
        self.repo = InteractionRepository(db, org_id)

    async def create_interaction(self, data: InteractionCreate) -> InteractionResponse:
        interaction = AgentInteraction(
            from_agent_id=data.from_agent_id,
            to_agent_id=data.to_agent_id,
            channel=data.channel,
            task_id=data.task_id,
            payload_summary=data.payload_summary,
            payload=data.payload,
            latency_ms=data.latency_ms,
            success=data.success,
            organization_id=self.org_id,
        )
        interaction = await self.repo.create(interaction)
        return InteractionResponse.model_validate(interaction)

    async def list_interactions(
        self,
        pagination: PaginationParams,
        *,
        agent_id: uuid.UUID | None = None,
        channel: InteractionChannel | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> tuple[list[InteractionResponse], int]:
        interactions, total = await self.repo.list_all(
            pagination,
            agent_id=agent_id,
            channel=channel,
            date_from=date_from,
            date_to=date_to,
        )
        return [InteractionResponse.model_validate(i) for i in interactions], total

    async def get_graph(self) -> GraphData:
        edges_raw = await self.repo.get_edge_weights()

        agent_ids: set[uuid.UUID] = set()
        for from_id, to_id, _ in edges_raw:
            agent_ids.add(from_id)
            agent_ids.add(to_id)

        agents_data = await self.repo.get_agents_with_departments(agent_ids)

        nodes = [
            GraphNode(id=aid, name=name, department=dept)
            for aid, name, dept in agents_data
        ]
        edges = [
            GraphEdge(source=from_id, target=to_id, weight=weight)
            for from_id, to_id, weight in edges_raw
        ]

        return GraphData(nodes=nodes, edges=edges)
