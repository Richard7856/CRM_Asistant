"""
Seed script to populate the database with initial data.
Run: python seed.py
"""

import asyncio
import sys
from pathlib import Path
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select

from app.agents.models import Agent, AgentDefinition, AgentOrigin, AgentStatus, Role, RoleLevel
from app.core.database import async_session_factory, engine, Base
from app.departments.models import Department
from app.tasks.models import Task  # noqa: F401 - needed for relationship resolution
from app.activities.models import ActivityLog  # noqa: F401
from app.metrics.models import PerformanceMetric  # noqa: F401
from app.interactions.models import AgentInteraction  # noqa: F401
from app.improvements.models import ImprovementPoint  # noqa: F401


async def seed():
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        # Check if already seeded
        existing = await session.execute(select(Role).limit(1))
        if existing.scalar():
            print("Database already seeded. Skipping.")
            return

        # --- Roles ---
        roles = {
            "admin": Role(id=uuid.uuid4(), name="Admin", level=RoleLevel.ADMIN, description="Administrador del sistema"),
            "manager": Role(id=uuid.uuid4(), name="Manager", level=RoleLevel.MANAGER, description="Gerente de area"),
            "supervisor": Role(id=uuid.uuid4(), name="Supervisor", level=RoleLevel.SUPERVISOR, description="Supervisor de equipo"),
            "agent": Role(id=uuid.uuid4(), name="Agent", level=RoleLevel.AGENT, description="Agente operativo"),
        }
        for role in roles.values():
            session.add(role)

        # --- Departments ---
        departments = {
            "marketing": Department(id=uuid.uuid4(), name="Marketing", slug="marketing", description="Estrategia y contenido de marketing"),
            "ventas": Department(id=uuid.uuid4(), name="Ventas", slug="ventas", description="Equipo de ventas y prospeccion"),
            "soporte": Department(id=uuid.uuid4(), name="Soporte", slug="soporte", description="Atencion al cliente y soporte tecnico"),
            "operaciones": Department(id=uuid.uuid4(), name="Operaciones", slug="operaciones", description="Operaciones y automatizacion"),
            "analytics": Department(id=uuid.uuid4(), name="Analytics", slug="analytics", description="Analisis de datos e insights"),
        }
        for dept in departments.values():
            session.add(dept)

        await session.flush()

        # --- Sample Agents ---
        # Marketing supervisor
        marketing_sup = Agent(
            id=uuid.uuid4(),
            name="Marketing Lead",
            slug="marketing-lead",
            description="Supervisor del equipo de marketing. Coordina campanas y contenido.",
            origin=AgentOrigin.INTERNAL,
            status=AgentStatus.ACTIVE,
            role_id=roles["supervisor"].id,
            department_id=departments["marketing"].id,
            capabilities=["content_generation", "campaign_planning", "seo_analysis"],
        )
        session.add(marketing_sup)

        # Marketing agent
        content_agent = Agent(
            id=uuid.uuid4(),
            name="Content Creator",
            slug="content-creator",
            description="Genera contenido para blog, redes sociales y email marketing.",
            origin=AgentOrigin.INTERNAL,
            status=AgentStatus.ACTIVE,
            role_id=roles["agent"].id,
            department_id=departments["marketing"].id,
            supervisor_id=marketing_sup.id,
            capabilities=["text_generation", "copywriting", "social_media"],
        )
        session.add(content_agent)

        # Sales supervisor
        sales_sup = Agent(
            id=uuid.uuid4(),
            name="Sales Manager",
            slug="sales-manager",
            description="Gestiona el pipeline de ventas y supervisa agentes de prospeccion.",
            origin=AgentOrigin.INTERNAL,
            status=AgentStatus.ACTIVE,
            role_id=roles["supervisor"].id,
            department_id=departments["ventas"].id,
            capabilities=["lead_scoring", "pipeline_management", "reporting"],
        )
        session.add(sales_sup)

        # Sales agent (external via n8n)
        prospector = Agent(
            id=uuid.uuid4(),
            name="Prospector Bot",
            slug="prospector-bot",
            description="Busca y califica leads automaticamente via n8n workflows.",
            origin=AgentOrigin.EXTERNAL,
            status=AgentStatus.IDLE,
            role_id=roles["agent"].id,
            department_id=departments["ventas"].id,
            supervisor_id=sales_sup.id,
            capabilities=["lead_generation", "email_outreach", "data_enrichment"],
        )
        session.add(prospector)

        # Support agent
        support_agent = Agent(
            id=uuid.uuid4(),
            name="Support Assistant",
            slug="support-assistant",
            description="Responde tickets de soporte y escala problemas complejos.",
            origin=AgentOrigin.INTERNAL,
            status=AgentStatus.ACTIVE,
            role_id=roles["agent"].id,
            department_id=departments["soporte"].id,
            capabilities=["ticket_response", "knowledge_base_search", "escalation"],
        )
        session.add(support_agent)

        # Analytics agent
        analytics_agent = Agent(
            id=uuid.uuid4(),
            name="Data Analyst",
            slug="data-analyst",
            description="Analiza datos de rendimiento y genera reportes.",
            origin=AgentOrigin.INTERNAL,
            status=AgentStatus.ACTIVE,
            role_id=roles["agent"].id,
            department_id=departments["analytics"].id,
            capabilities=["data_analysis", "report_generation", "visualization"],
        )
        session.add(analytics_agent)

        await session.flush()

        # --- Agent Definitions (for internal agents) ---
        for agent in [marketing_sup, content_agent, sales_sup, support_agent, analytics_agent]:
            defn = AgentDefinition(
                agent_id=agent.id,
                system_prompt=f"You are {agent.name}. {agent.description}",
                model_provider="anthropic",
                model_name="claude-sonnet-4-20250514",
                temperature=0.7,
                max_tokens=4096,
                tools=[],
            )
            session.add(defn)

        # Set department heads
        departments["marketing"].head_agent_id = marketing_sup.id
        departments["ventas"].head_agent_id = sales_sup.id

        await session.commit()
        print("Database seeded successfully!")
        print(f"  - {len(roles)} roles")
        print(f"  - {len(departments)} departments")
        print(f"  - 6 agents (5 internal, 1 external)")


if __name__ == "__main__":
    asyncio.run(seed())
