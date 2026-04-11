"""
Seed script — DigitalMind agency demo data.

Creates the organizational structure for the demo:
3 departments, 8 agents (3 supervisors + 4 internal + 1 external),
with specialized system prompts for each role.

Run: python seed.py
Re-run safe: skips if data already exists (checks for roles).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select

from app.agents.models import (
    Agent,
    AgentDefinition,
    AgentIntegration,
    AgentOrigin,
    AgentStatus,
    IntegrationType,
    Role,
    RoleLevel,
)
from app.auth.models import Organization
from app.core.database import async_session_factory, engine, Base
from app.departments.models import Department

# Import all models so Base.metadata.create_all picks them up
from app.tasks.models import Task  # noqa: F401
from app.activities.models import ActivityLog  # noqa: F401
from app.metrics.models import PerformanceMetric  # noqa: F401
from app.interactions.models import AgentInteraction  # noqa: F401
from app.improvements.models import ImprovementPoint  # noqa: F401
from app.prompts.models import PromptVersion, PromptTemplate  # noqa: F401
from app.knowledge.models import KnowledgeDocument, KnowledgeChunk  # noqa: F401


# ---------------------------------------------------------------------------
# System prompts — each agent gets a specialized persona and instructions
# ---------------------------------------------------------------------------

PROMPTS = {
    "director-contenido": (
        "Eres el Director de Contenido de la agencia DigitalMind. "
        "Tu rol es recibir briefs de contenido, descomponerlos en piezas ejecutables, "
        "y coordinar al equipo de contenido (Copywriter e Investigador). "
        "Cuando recibes una tarea compleja, analiza qué piezas necesitas y delega. "
        "Cuando recibes resultados de tu equipo, agrégalos en un entregable coherente "
        "con una narrativa clara. Siempre incluye un resumen ejecutivo al inicio."
    ),
    "copywriter": (
        "Eres Copywriter senior en la agencia DigitalMind. "
        "Escribes textos persuasivos y creativos para blog, LinkedIn, Instagram, "
        "email marketing y páginas web. Siempre adaptas el tono al canal: "
        "profesional en LinkedIn, cercano en Instagram, claro en email. "
        "Si tienes acceso a la guía de marca en el knowledge base, SIEMPRE "
        "respeta el tono y vocabulario definido ahí. "
        "Entrega el copy listo para publicar con título, cuerpo, y CTA."
    ),
    "investigador": (
        "Eres Investigador de contenido en la agencia DigitalMind. "
        "Tu trabajo es buscar datos, estadísticas, tendencias y fuentes "
        "que respalden las piezas de contenido del equipo. "
        "Siempre estructura tu investigación con: contexto del tema, "
        "3-5 datos clave con fuentes, tendencias relevantes, y recomendaciones "
        "para el ángulo del contenido. Sé conciso y factual."
    ),
    "account-manager": (
        "Eres Account Manager en la agencia DigitalMind. "
        "Gestionas las solicitudes de clientes: clasificas el tipo de solicitud, "
        "evalúas urgencia, y delegas al especialista correcto de tu equipo. "
        "Para propuestas comerciales, delega al Analista de Propuestas. "
        "Para problemas técnicos, delega a Soporte Técnico. "
        "Siempre responde al cliente con un resumen ejecutivo claro."
    ),
    "analista-propuestas": (
        "Eres Analista de Propuestas en la agencia DigitalMind. "
        "Generas propuestas comerciales profesionales basándote en las necesidades "
        "del cliente. Incluye: resumen del problema, solución propuesta, "
        "alcance del proyecto, timeline estimado, y próximos pasos. "
        "Si tienes templates en el knowledge base, úsalos como estructura base. "
        "El tono debe ser profesional pero no corporativo — somos una agencia ágil."
    ),
    "soporte-tecnico": (
        "Eres agente de Soporte Técnico en la agencia DigitalMind. "
        "Respondes tickets de clientes sobre problemas técnicos con sus "
        "plataformas digitales, integraciones, y herramientas. "
        "Siempre: (1) confirma el problema, (2) diagnostica la causa probable, "
        "(3) ofrece solución paso a paso, (4) sugiere prevención futura."
    ),
    "strategist": (
        "Eres el Strategist principal de la agencia DigitalMind. "
        "Recibes objetivos de negocio de alto nivel y los traduces en planes "
        "ejecutables con métricas claras. Cuando necesitas datos, delega "
        "al Data Analyst. Tu output siempre incluye: objetivo, estrategia, "
        "tácticas específicas, KPIs de éxito, y timeline."
    ),
    "data-analyst": (
        "Eres Data Analyst en la agencia DigitalMind. "
        "Analizas métricas de performance, generando insights accionables. "
        "Siempre estructura tus análisis con: resumen ejecutivo, "
        "métricas clave (con números), tendencias identificadas, "
        "anomalías o alertas, y recomendaciones. Usa lenguaje claro — "
        "tus reportes los lee gente no técnica."
    ),
}


async def seed():
    # Ensure all tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        # Check if already seeded
        existing = await session.execute(select(Role).limit(1))
        if existing.scalar():
            print("Database already seeded. Skipping.")
            print("To re-seed, drop the existing data first.")
            return

        # Find the existing organization (created during initial setup / migration)
        org_result = await session.execute(select(Organization).limit(1))
        org = org_result.scalar_one_or_none()
        if org is None:
            print("ERROR: No organization found. Run the auth setup first.")
            return

        org_id = org.id
        print(f"Using organization: {org.name} ({org_id})")

        # ─── Roles ───
        roles = {
            "admin": Role(name="Admin", level=RoleLevel.ADMIN, description="Administrador del sistema"),
            "manager": Role(name="Manager", level=RoleLevel.MANAGER, description="Gerente de area"),
            "supervisor": Role(name="Supervisor", level=RoleLevel.SUPERVISOR, description="Supervisor de equipo — puede delegar tareas"),
            "agent": Role(name="Agent", level=RoleLevel.AGENT, description="Agente operativo — ejecuta tareas asignadas"),
        }
        for role in roles.values():
            session.add(role)
        await session.flush()

        # ─── Departments ───
        departments = {
            "contenido": Department(
                name="Contenido",
                slug="contenido",
                description="Creación de contenido: blog, redes sociales, email marketing. "
                "El Director planifica y delega; Copywriter e Investigador ejecutan.",
                organization_id=org_id,
            ),
            "clientes": Department(
                name="Clientes",
                slug="clientes",
                description="Gestión de clientes: propuestas comerciales, soporte técnico. "
                "El Account Manager clasifica y delega solicitudes.",
                organization_id=org_id,
            ),
            "estrategia": Department(
                name="Estrategia",
                slug="estrategia",
                description="Planificación estratégica y análisis de datos. "
                "El Strategist define planes; Data Analyst genera insights.",
                organization_id=org_id,
            ),
        }
        for dept in departments.values():
            session.add(dept)
        await session.flush()

        # ─── Agents ───
        # Contenido department
        director_contenido = Agent(
            name="Director de Contenido",
            slug="director-contenido",
            description="Supervisor del equipo de contenido. Recibe briefs, descompone en piezas, "
            "delega a Copywriter e Investigador, y agrega los resultados en un entregable final.",
            origin=AgentOrigin.INTERNAL,
            status=AgentStatus.ACTIVE,
            role_id=roles["supervisor"].id,
            department_id=departments["contenido"].id,
            organization_id=org_id,
            capabilities=["content_planning", "editorial_direction", "team_coordination", "quality_review"],
        )
        session.add(director_contenido)

        copywriter = Agent(
            name="Copywriter",
            slug="copywriter",
            description="Escribe textos persuasivos para blog, LinkedIn, Instagram, email. "
            "Adapta tono al canal. Respeta guía de marca del knowledge base.",
            origin=AgentOrigin.INTERNAL,
            status=AgentStatus.ACTIVE,
            role_id=roles["agent"].id,
            department_id=departments["contenido"].id,
            supervisor_id=None,  # set after flush
            organization_id=org_id,
            capabilities=["copywriting", "social_media", "email_marketing", "blog_writing"],
        )
        session.add(copywriter)

        investigador = Agent(
            name="Investigador",
            slug="investigador",
            description="Busca datos, estadísticas y tendencias para respaldar las piezas de contenido. "
            "Estructura investigación con datos clave, fuentes y recomendaciones.",
            origin=AgentOrigin.INTERNAL,
            status=AgentStatus.ACTIVE,
            role_id=roles["agent"].id,
            department_id=departments["contenido"].id,
            supervisor_id=None,  # set after flush
            organization_id=org_id,
            capabilities=["research", "data_gathering", "trend_analysis", "source_verification"],
        )
        session.add(investigador)

        # Clientes department
        account_manager = Agent(
            name="Account Manager",
            slug="account-manager",
            description="Gestiona solicitudes de clientes. Clasifica tipo y urgencia, "
            "delega a Analista de Propuestas o Soporte Técnico según el caso.",
            origin=AgentOrigin.INTERNAL,
            status=AgentStatus.ACTIVE,
            role_id=roles["supervisor"].id,
            department_id=departments["clientes"].id,
            organization_id=org_id,
            capabilities=["client_management", "request_classification", "team_coordination", "reporting"],
        )
        session.add(account_manager)

        analista_propuestas = Agent(
            name="Analista de Propuestas",
            slug="analista-propuestas",
            description="Genera propuestas comerciales profesionales. Incluye problema, solución, "
            "alcance, timeline y próximos pasos. Usa templates del knowledge base.",
            origin=AgentOrigin.INTERNAL,
            status=AgentStatus.ACTIVE,
            role_id=roles["agent"].id,
            department_id=departments["clientes"].id,
            supervisor_id=None,  # set after flush
            organization_id=org_id,
            capabilities=["proposal_writing", "pricing_analysis", "client_communication"],
        )
        session.add(analista_propuestas)

        soporte_tecnico = Agent(
            name="Soporte Técnico",
            slug="soporte-tecnico",
            description="Responde tickets de clientes sobre problemas técnicos. "
            "Diagnostica, ofrece solución paso a paso, y sugiere prevención.",
            origin=AgentOrigin.EXTERNAL,
            status=AgentStatus.IDLE,
            role_id=roles["agent"].id,
            department_id=departments["clientes"].id,
            supervisor_id=None,  # set after flush
            organization_id=org_id,
            capabilities=["technical_support", "troubleshooting", "ticket_management"],
        )
        session.add(soporte_tecnico)

        # Estrategia department
        strategist = Agent(
            name="Strategist",
            slug="strategist",
            description="Traduce objetivos de negocio en planes ejecutables con métricas claras. "
            "Delega análisis de datos al Data Analyst cuando necesita insights.",
            origin=AgentOrigin.INTERNAL,
            status=AgentStatus.ACTIVE,
            role_id=roles["supervisor"].id,
            department_id=departments["estrategia"].id,
            organization_id=org_id,
            capabilities=["strategic_planning", "kpi_definition", "market_analysis", "team_coordination"],
        )
        session.add(strategist)

        data_analyst = Agent(
            name="Data Analyst",
            slug="data-analyst",
            description="Analiza métricas de performance y genera insights accionables. "
            "Reportes con resumen ejecutivo, métricas, tendencias y recomendaciones.",
            origin=AgentOrigin.INTERNAL,
            status=AgentStatus.ACTIVE,
            role_id=roles["agent"].id,
            department_id=departments["estrategia"].id,
            supervisor_id=None,  # set after flush
            organization_id=org_id,
            capabilities=["data_analysis", "report_generation", "visualization", "forecasting"],
        )
        session.add(data_analyst)

        await session.flush()

        # ─── Set supervisor relationships (need IDs from flush) ───
        copywriter.supervisor_id = director_contenido.id
        investigador.supervisor_id = director_contenido.id
        analista_propuestas.supervisor_id = account_manager.id
        soporte_tecnico.supervisor_id = account_manager.id
        data_analyst.supervisor_id = strategist.id

        # ─── Set department heads ───
        departments["contenido"].head_agent_id = director_contenido.id
        departments["clientes"].head_agent_id = account_manager.id
        departments["estrategia"].head_agent_id = strategist.id

        await session.flush()

        # ─── Agent Definitions (system prompts for internal agents) ───
        internal_agents = [
            director_contenido, copywriter, investigador,
            account_manager, analista_propuestas,
            strategist, data_analyst,
        ]
        for agent in internal_agents:
            defn = AgentDefinition(
                agent_id=agent.id,
                system_prompt=PROMPTS[agent.slug],
                model_provider="anthropic",
                model_name="claude-sonnet-4-20250514",
                temperature=0.7,
                max_tokens=4096,
                tools=[],
            )
            session.add(defn)

        # ─── External agent integration (Soporte Técnico via webhook) ───
        integration = AgentIntegration(
            agent_id=soporte_tecnico.id,
            integration_type=IntegrationType.WEBHOOK,
            platform="custom",
            endpoint_url="https://support.digitalmind.example/webhook",
            polling_interval_seconds=60,
            config={"headers": {"X-Source": "crm-agents"}},
            is_active=False,  # demo placeholder — no real endpoint
        )
        session.add(integration)

        await session.commit()

        # ─── Summary ───
        print("\nDatabase seeded successfully!")
        print(f"  Organization: {org.name}")
        print(f"  Roles: {len(roles)}")
        print(f"  Departments: {len(departments)} (all with head_agent)")
        print(f"  Agents: {len(internal_agents) + 1} (7 internal, 1 external)")
        print("\n  Contenido:")
        print(f"    Supervisor: {director_contenido.name}")
        print(f"    Agents: {copywriter.name}, {investigador.name}")
        print("  Clientes:")
        print(f"    Supervisor: {account_manager.name}")
        print(f"    Agents: {analista_propuestas.name}, {soporte_tecnico.name} (external)")
        print("  Estrategia:")
        print(f"    Supervisor: {strategist.name}")
        print(f"    Agents: {data_analyst.name}")


if __name__ == "__main__":
    asyncio.run(seed())
