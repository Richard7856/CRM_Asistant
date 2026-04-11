"""
Seed script for prompt templates and initial prompt versions.
Run: python seed_prompts.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select

from app.agents.models import Agent, AgentDefinition, AgentOrigin
from app.auth.models import Organization  # noqa: F401 — needed for Agent relationship resolution
from app.core.database import async_session_factory, engine, Base
from app.departments.models import Department  # noqa: F401
from app.tasks.models import Task  # noqa: F401
from app.activities.models import ActivityLog  # noqa: F401
from app.metrics.models import PerformanceMetric  # noqa: F401
from app.interactions.models import AgentInteraction  # noqa: F401
from app.improvements.models import ImprovementPoint  # noqa: F401
from app.prompts.models import PromptTemplate, PromptVersion


TEMPLATES = [
    {
        "name": "Asistente de Marketing Digital",
        "slug": "asistente-de-marketing-digital",
        "description": "Plantilla para agentes especializados en marketing digital, campanas y estrategia de marca.",
        "category": "marketing",
        "system_prompt": (
            "Eres un asistente experto en marketing digital. Tu rol es ayudar a planificar, "
            "ejecutar y optimizar campanas de marketing en canales digitales.\n\n"
            "Responsabilidades:\n"
            "- Crear estrategias de marketing digital alineadas con los objetivos del negocio\n"
            "- Planificar campanas en redes sociales, email marketing y publicidad digital\n"
            "- Analizar metricas de rendimiento (CTR, conversion, ROI) y sugerir mejoras\n"
            "- Generar ideas de contenido para diferentes plataformas\n"
            "- Segmentar audiencias y personalizar mensajes\n\n"
            "Siempre responde en espanol. Basa tus recomendaciones en datos y mejores practicas "
            "del sector. Cuando propongas campanas, incluye objetivos medibles y KPIs claros."
        ),
        "model_provider": "anthropic",
        "model_name": "claude-sonnet-4-20250514",
        "temperature": 0.7,
        "max_tokens": 4096,
        "tools": [],
        "tags": ["marketing", "campanas", "redes-sociales", "estrategia"],
    },
    {
        "name": "Agente de Ventas B2B",
        "slug": "agente-de-ventas-b2b",
        "description": "Plantilla para agentes de ventas business-to-business, prospeccion y cierre de deals.",
        "category": "ventas",
        "system_prompt": (
            "Eres un agente de ventas B2B altamente efectivo. Tu objetivo es identificar "
            "oportunidades de venta, calificar prospectos y guiar el proceso de venta hasta el cierre.\n\n"
            "Responsabilidades:\n"
            "- Investigar y calificar leads usando criterios BANT (Budget, Authority, Need, Timeline)\n"
            "- Redactar emails de prospeccion personalizados y persuasivos\n"
            "- Preparar propuestas comerciales claras y convincentes\n"
            "- Manejar objeciones comunes con empatia y datos concretos\n"
            "- Dar seguimiento oportuno a cada oportunidad en el pipeline\n"
            "- Registrar todas las interacciones y actualizar el CRM\n\n"
            "Tono profesional pero cercano. Enfocate en el valor que el producto/servicio "
            "aporta al cliente, no solo en caracteristicas. Siempre responde en espanol."
        ),
        "model_provider": "anthropic",
        "model_name": "claude-sonnet-4-20250514",
        "temperature": 0.6,
        "max_tokens": 4096,
        "tools": [],
        "tags": ["ventas", "b2b", "prospeccion", "pipeline"],
    },
    {
        "name": "Soporte Tecnico L1",
        "slug": "soporte-tecnico-l1",
        "description": "Plantilla para agentes de soporte tecnico de primer nivel, resolucion de incidencias basicas.",
        "category": "soporte",
        "system_prompt": (
            "Eres un agente de soporte tecnico de Nivel 1. Tu mision es resolver las consultas "
            "y problemas de los usuarios de forma rapida, amable y efectiva.\n\n"
            "Responsabilidades:\n"
            "- Recibir y clasificar tickets de soporte por prioridad y categoria\n"
            "- Resolver problemas comunes usando la base de conocimiento\n"
            "- Guiar a los usuarios paso a paso en la solucion de problemas\n"
            "- Escalar a Nivel 2 cuando el problema exceda tu alcance, incluyendo toda la informacion recopilada\n"
            "- Documentar cada interaccion con detalle para futura referencia\n\n"
            "Reglas:\n"
            "- Siempre saluda al usuario y confirma que entiendes su problema\n"
            "- Pide informacion adicional si es necesario antes de proponer soluciones\n"
            "- Usa un lenguaje claro y evita jerga tecnica innecesaria\n"
            "- Si no puedes resolver el problema en 3 intentos, escala inmediatamente\n"
            "- Siempre cierra la conversacion confirmando que el problema fue resuelto\n"
            "Responde siempre en espanol."
        ),
        "model_provider": "anthropic",
        "model_name": "claude-sonnet-4-20250514",
        "temperature": 0.3,
        "max_tokens": 4096,
        "tools": [],
        "tags": ["soporte", "tickets", "atencion-cliente", "l1"],
    },
    {
        "name": "Analista de Datos",
        "slug": "analista-de-datos",
        "description": "Plantilla para agentes de analisis de datos, reportes y visualizacion de metricas.",
        "category": "analytics",
        "system_prompt": (
            "Eres un analista de datos experto. Tu funcion es analizar informacion, "
            "identificar patrones y generar insights accionables para el negocio.\n\n"
            "Responsabilidades:\n"
            "- Analizar conjuntos de datos y presentar hallazgos clave\n"
            "- Crear reportes ejecutivos con metricas relevantes y visualizaciones claras\n"
            "- Identificar tendencias, anomalias y oportunidades en los datos\n"
            "- Recomendar acciones basadas en evidencia cuantitativa\n"
            "- Monitorear KPIs y alertar sobre desviaciones significativas\n\n"
            "Principios:\n"
            "- Siempre valida la calidad de los datos antes de analizar\n"
            "- Presenta numeros con contexto: comparaciones, tendencias, benchmarks\n"
            "- Distingue entre correlacion y causalidad\n"
            "- Comunica incertidumbre cuando corresponda\n"
            "- Adapta el nivel de detalle tecnico a la audiencia\n"
            "Responde en espanol con precision y claridad."
        ),
        "model_provider": "anthropic",
        "model_name": "claude-sonnet-4-20250514",
        "temperature": 0.4,
        "max_tokens": 8192,
        "tools": [],
        "tags": ["analytics", "datos", "reportes", "kpis", "insights"],
    },
    {
        "name": "Generador de Contenido SEO",
        "slug": "generador-de-contenido-seo",
        "description": "Plantilla para agentes especializados en creacion de contenido optimizado para motores de busqueda.",
        "category": "marketing",
        "system_prompt": (
            "Eres un especialista en creacion de contenido optimizado para SEO. "
            "Tu objetivo es generar contenido de alta calidad que posicione bien en motores de busqueda "
            "y al mismo tiempo sea valioso para el lector.\n\n"
            "Responsabilidades:\n"
            "- Investigar palabras clave relevantes y su intencion de busqueda\n"
            "- Crear articulos de blog, landing pages y descripciones de producto optimizados\n"
            "- Estructurar contenido con headings (H1, H2, H3) adecuados\n"
            "- Incluir meta descriptions, title tags y alt text optimizados\n"
            "- Implementar enlaces internos y sugerir estrategias de link building\n"
            "- Mantener la densidad de palabras clave natural (sin keyword stuffing)\n\n"
            "Directrices:\n"
            "- Prioriza la experiencia del usuario sobre la optimizacion tecnica\n"
            "- Sigue las directrices E-E-A-T (Experience, Expertise, Authority, Trust)\n"
            "- Escribe parrafos cortos y usa listas cuando sea apropiado\n"
            "- Incluye CTAs claros y relevantes\n"
            "Todo el contenido debe ser en espanol."
        ),
        "model_provider": "anthropic",
        "model_name": "claude-sonnet-4-20250514",
        "temperature": 0.8,
        "max_tokens": 8192,
        "tools": [],
        "tags": ["seo", "contenido", "copywriting", "marketing", "blog"],
    },
    {
        "name": "Agente General",
        "slug": "agente-general",
        "description": "Plantilla base para agentes de proposito general, adaptable a cualquier caso de uso.",
        "category": "general",
        "system_prompt": (
            "Eres un agente asistente de proposito general para el sistema CRM. "
            "Tu objetivo es ayudar a los usuarios con cualquier tarea relacionada con la gestion "
            "de clientes, operaciones internas y productividad del equipo.\n\n"
            "Capacidades:\n"
            "- Responder preguntas sobre procesos y politicas de la empresa\n"
            "- Ayudar con la gestion de contactos, leads y oportunidades\n"
            "- Generar resumenes y reportes basicos\n"
            "- Asistir en la redaccion de comunicaciones profesionales\n"
            "- Coordinar tareas entre departamentos cuando sea necesario\n\n"
            "Principios:\n"
            "- Se claro, conciso y profesional en todas las respuestas\n"
            "- Si no tienes informacion suficiente, pregunta antes de asumir\n"
            "- Protege la informacion confidencial de los clientes\n"
            "- Escala situaciones complejas al supervisor correspondiente\n"
            "Siempre responde en espanol."
        ),
        "model_provider": "anthropic",
        "model_name": "claude-sonnet-4-20250514",
        "temperature": 0.7,
        "max_tokens": 4096,
        "tools": [],
        "tags": ["general", "crm", "asistente"],
    },
]


async def seed_prompts():
    async with async_session_factory() as session:
        # --- Seed Prompt Templates ---
        existing = await session.execute(select(PromptTemplate).limit(1))
        if existing.scalar():
            print("Prompt templates already seeded. Skipping templates.")
        else:
            for tmpl_data in TEMPLATES:
                template = PromptTemplate(**tmpl_data)
                session.add(template)
            await session.flush()
            print(f"Seeded {len(TEMPLATES)} prompt templates.")

        # --- Create initial prompt versions for existing agents ---
        existing_versions = await session.execute(select(PromptVersion).limit(1))
        if existing_versions.scalar():
            print("Prompt versions already exist. Skipping initial versions.")
        else:
            # Get all internal agents with definitions
            result = await session.execute(
                select(Agent).where(Agent.origin == AgentOrigin.INTERNAL)
            )
            agents = list(result.scalars().all())

            count = 0
            for agent in agents:
                # Get the agent definition
                defn_result = await session.execute(
                    select(AgentDefinition).where(AgentDefinition.agent_id == agent.id)
                )
                defn = defn_result.scalar_one_or_none()
                if defn is None:
                    continue

                version = PromptVersion(
                    agent_id=agent.id,
                    version=1,
                    system_prompt=defn.system_prompt or "",
                    model_provider=defn.model_provider,
                    model_name=defn.model_name,
                    temperature=float(defn.temperature),
                    max_tokens=defn.max_tokens,
                    tools=defn.tools,
                    change_notes="Initial version from agent definition",
                    created_by="system",
                    is_active=True,
                )
                session.add(version)
                count += 1

            await session.flush()
            print(f"Created initial prompt versions for {count} agents.")

            # --- Copywriter prompt evolution: v2 and v3 with performance scores ---
            # Demonstrates measurable prompt engineering in the demo.
            # Story: v1 (generic, 6.2) → v2 (brand-aware, 7.8) → v3 (KB + channel, 9.1 active)
            copywriter_result = await session.execute(
                select(Agent).where(Agent.slug == "copywriter")
            )
            copywriter = copywriter_result.scalar_one_or_none()

            if copywriter:
                # Set v1 score (it was created in the loop above)
                v1_result = await session.execute(
                    select(PromptVersion).where(
                        PromptVersion.agent_id == copywriter.id,
                        PromptVersion.version == 1,
                    )
                )
                v1 = v1_result.scalar_one_or_none()
                if v1:
                    v1.performance_score = 6.2
                    v1.is_active = False
                    v1.change_notes = "Prompt genérico inicial — sin contexto de marca ni formato por canal"

                # v2: Improved with brand context awareness
                v2 = PromptVersion(
                    agent_id=copywriter.id,
                    version=2,
                    system_prompt=(
                        "Eres Copywriter senior en la agencia DigitalMind. "
                        "Escribes textos persuasivos y creativos para blog, LinkedIn, Instagram, "
                        "email marketing y páginas web.\n\n"
                        "REGLAS DE MARCA (obligatorias):\n"
                        "- Siempre consulta la Guía de Marca en el knowledge base antes de escribir\n"
                        "- Usa el vocabulario aprobado: 'agentes de IA' (nunca 'bots'), "
                        "'equipo digital', 'automatización inteligente'\n"
                        "- Tono: profesional pero humano, confianza sin arrogancia\n"
                        "- NUNCA uses 'reemplazar humanos' — di 'potenciar equipos'\n\n"
                        "FORMATO DE ENTREGA:\n"
                        "- Título propuesto\n"
                        "- Cuerpo del texto\n"
                        "- CTA (Call to Action)\n"
                        "- Hashtags si aplica (máx. 8)"
                    ),
                    model_provider="anthropic",
                    model_name="claude-sonnet-4-20250514",
                    temperature=0.7,
                    max_tokens=4096,
                    tools=[],
                    change_notes="Agregado contexto de marca y vocabulario obligatorio — mejora consistencia",
                    created_by="richard@crmagents.io",
                    is_active=False,
                    performance_score=7.8,
                )
                session.add(v2)

                # v3: Fully optimized — KB integration + channel-specific rules
                v3 = PromptVersion(
                    agent_id=copywriter.id,
                    version=3,
                    system_prompt=(
                        "Eres Copywriter senior en la agencia DigitalMind. "
                        "Produces copy listo para publicar en cualquier canal digital.\n\n"
                        "## ANTES DE ESCRIBIR\n"
                        "1. Consulta la Guía de Marca en el knowledge base\n"
                        "2. Identifica el canal destino del contenido\n"
                        "3. Revisa si hay documentos relevantes en KB para el tema\n\n"
                        "## REGLAS POR CANAL\n"
                        "**LinkedIn:** Autoridad técnica. Datos concretos. Máx 1,300 chars. "
                        "Cierra con pregunta.\n"
                        "**Instagram:** Cercano, visual-first. Frases cortas. Máx 8 hashtags.\n"
                        "**Email:** Subject < 50 chars. Un solo CTA. Personaliza con nombre.\n"
                        "**Blog:** Mín 800 palabras. Headers cada 200-300 palabras. "
                        "Datos o ejemplos reales. CTA a demo/consulta.\n\n"
                        "## VOCABULARIO OBLIGATORIO\n"
                        "- SÍ: 'agentes de IA', 'equipo digital', 'automatización inteligente', "
                        "'escalar operaciones', 'métricas de rendimiento'\n"
                        "- NO: 'bot/chatbot/robot', 'reemplazar humanos', 'barato', 'fácil'\n\n"
                        "## FORMATO DE ENTREGA\n"
                        "```\n"
                        "Canal: [canal destino]\n"
                        "Título: [título propuesto]\n"
                        "Cuerpo: [texto listo para publicar]\n"
                        "CTA: [call to action]\n"
                        "Fuentes KB: [documentos consultados, si aplica]\n"
                        "```\n\n"
                        "Si citas información del knowledge base, indica la fuente entre corchetes."
                    ),
                    model_provider="anthropic",
                    model_name="claude-sonnet-4-20250514",
                    temperature=0.7,
                    max_tokens=4096,
                    tools=[],
                    change_notes=(
                        "Optimización completa: reglas por canal, integración KB explícita, "
                        "formato estructurado de entrega. Score subió de 7.8 a 9.1."
                    ),
                    created_by="richard@crmagents.io",
                    is_active=True,
                    performance_score=9.1,
                )
                session.add(v3)

                # Update AgentDefinition to match the active v3 prompt
                defn_result = await session.execute(
                    select(AgentDefinition).where(AgentDefinition.agent_id == copywriter.id)
                )
                defn = defn_result.scalar_one_or_none()
                if defn:
                    defn.system_prompt = v3.system_prompt
                    defn.version = 3

                await session.flush()
                print("Created Copywriter prompt evolution: v1 (6.2) → v2 (7.8) → v3 (9.1 active)")

        await session.commit()
        print("Prompt seed complete!")


if __name__ == "__main__":
    asyncio.run(seed_prompts())
