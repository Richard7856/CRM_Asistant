"""
Seed script — Knowledge Base documents for DigitalMind agency demo.

Creates 4 documents with realistic chunked content:
  1. Guía de Marca (dept: Contenido) — brand tone/voice for Copywriter
  2. Template de Propuesta Comercial (dept: Clientes) — structure for Analista de Propuestas
  3. Manual de Procesos Internos (org-level) — available to all agents
  4. Catálogo de Servicios y Precios (org-level) — pricing for all agents

The tsvector trigger auto-populates search_vector on each chunk insert.
Run: python seed_knowledge.py
Re-run safe: skips if knowledge documents already exist.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select, func

from app.auth.models import Organization, User
from app.core.database import async_session_factory, engine, Base
from app.departments.models import Department
from app.knowledge.models import KnowledgeDocument, KnowledgeChunk

# Import all models so relationships resolve
from app.agents.models import Agent  # noqa: F401
from app.tasks.models import Task  # noqa: F401
from app.activities.models import ActivityLog  # noqa: F401
from app.metrics.models import PerformanceMetric  # noqa: F401
from app.interactions.models import AgentInteraction  # noqa: F401
from app.improvements.models import ImprovementPoint  # noqa: F401
from app.prompts.models import PromptVersion, PromptTemplate  # noqa: F401

# Rough estimate — used to populate token_count without a tokenizer
TOKENS_PER_WORD = 1.3


# ---------------------------------------------------------------------------
# Document content — each doc is a list of chunks (logical sections)
# ---------------------------------------------------------------------------

GUIA_DE_MARCA = {
    "title": "Guía de Marca — DigitalMind",
    "description": (
        "Lineamientos de tono, voz, vocabulario y estilo visual de la agencia. "
        "Obligatorio para toda pieza de contenido que salga al público."
    ),
    "file_type": "md",
    "dept_slug": "contenido",  # dept-level — Copywriter e Investigador
    "chunks": [
        # Chunk 0: Identidad de marca
        (
            "# Identidad de Marca — DigitalMind\n\n"
            "DigitalMind es una agencia de automatización inteligente. Ayudamos a empresas "
            "a escalar sus operaciones usando agentes de IA que trabajan como un equipo humano: "
            "con roles claros, supervisión, y métricas de rendimiento.\n\n"
            "## Propuesta de valor\n"
            "No vendemos tecnología — vendemos equipos que nunca duermen, nunca renuncian, "
            "y mejoran cada semana. Nuestros agentes de IA son empleados digitales que se "
            "integran a la estructura organizacional del cliente.\n\n"
            "## Diferenciador clave\n"
            "Otros venden chatbots. Nosotros vendemos una fuerza laboral digital con "
            "organigramas, KPIs, y supervisores que coordinan el trabajo."
        ),
        # Chunk 1: Tono y voz
        (
            "# Tono y Voz\n\n"
            "## Tono general\n"
            "Profesional pero humano. Sabemos de tecnología avanzada pero hablamos en el "
            "idioma del negocio, no del ingeniero. Confianza sin arrogancia.\n\n"
            "## Reglas de tono por canal\n"
            "- **LinkedIn**: Autoridad técnica con insights prácticos. Datos concretos, "
            "no generalidades. Máximo 1,300 caracteres. Cierra con pregunta o invitación a comentar.\n"
            "- **Instagram**: Cercano, visual-first. Frases cortas y directas. "
            "Hashtags: máximo 8, relevantes al sector (no genéricos). Stories para behind-the-scenes.\n"
            "- **Email marketing**: Claro y orientado a acción. Subject line < 50 caracteres. "
            "Un solo CTA por email. Personalización con nombre cuando sea posible.\n"
            "- **Blog**: Educativo y profundo. Mínimo 800 palabras. Siempre incluir datos o "
            "ejemplos reales. Headers cada 200-300 palabras. Cerrar con CTA hacia demo o consulta.\n"
            "- **Propuestas comerciales**: Formal pero no corporativo. Liderar con el problema "
            "del cliente, no con nuestras capacidades. Números concretos siempre."
        ),
        # Chunk 2: Vocabulario obligatorio y prohibido
        (
            "# Vocabulario\n\n"
            "## Palabras que SÍ usamos\n"
            "- 'Agentes de IA' (nunca 'bots' ni 'chatbots')\n"
            "- 'Equipo digital' o 'fuerza laboral digital'\n"
            "- 'Automatización inteligente' (no solo 'automatización')\n"
            "- 'Escalar operaciones' (verbo preferido para growth)\n"
            "- 'Supervisión' y 'coordinación' (para describir el sistema multi-agente)\n"
            "- 'Métricas de rendimiento', 'KPIs'\n"
            "- 'Integración' (para conexiones con sistemas existentes)\n\n"
            "## Palabras PROHIBIDAS\n"
            "- 'Bot' / 'chatbot' / 'robot' → reemplazar por 'agente'\n"
            "- 'Inteligencia artificial mágica' o 'el futuro es hoy' → clichés prohibidos\n"
            "- 'Reemplazar humanos' → NUNCA. Decir 'potenciar equipos' o 'liberar tiempo'\n"
            "- 'Barato' / 'económico' → decir 'eficiente en costos' o 'optimizado'\n"
            "- 'Fácil' / 'simple' → decir 'accesible' o 'intuitivo'\n"
            "- Anglicismos innecesarios cuando hay equivalente claro en español"
        ),
        # Chunk 3: Estilo visual y formato
        (
            "# Estilo Visual y Formato\n\n"
            "## Colores de marca\n"
            "- Primario: #2563EB (azul eléctrico — confianza y tecnología)\n"
            "- Secundario: #7C3AED (violeta — innovación)\n"
            "- Acento: #10B981 (verde — crecimiento y resultados)\n"
            "- Neutros: #1F2937 (texto), #F9FAFB (fondo), #E5E7EB (bordes)\n\n"
            "## Tipografía\n"
            "- Títulos: Inter Bold\n"
            "- Cuerpo: Inter Regular, 16px mínimo\n"
            "- Código/datos: JetBrains Mono\n\n"
            "## Formato de entregables\n"
            "- Blog posts: título H1, subtítulos H2, bullet points para listas\n"
            "- Social media: imagen cuadrada 1080x1080 para feed, 1080x1920 para stories\n"
            "- Propuestas: PDF con portada, tabla de contenidos, máximo 10 páginas\n"
            "- Emails: ancho máximo 600px, botón CTA con color primario"
        ),
    ],
}

TEMPLATE_PROPUESTA = {
    "title": "Template — Propuesta Comercial Estándar",
    "description": (
        "Estructura base para propuestas comerciales de DigitalMind. "
        "El Analista de Propuestas debe usar esta estructura como punto de partida."
    ),
    "file_type": "md",
    "dept_slug": "clientes",  # dept-level — Account Manager y Analista
    "chunks": [
        # Chunk 0: Estructura general
        (
            "# Template de Propuesta Comercial — DigitalMind\n\n"
            "## Estructura obligatoria\n"
            "Toda propuesta comercial debe seguir esta estructura en este orden:\n\n"
            "1. **Portada** — Logo, nombre del cliente, fecha, versión\n"
            "2. **Resumen ejecutivo** (máx. 200 palabras) — El problema del cliente en "
            "sus propias palabras, y cómo lo resolvemos en 3 oraciones\n"
            "3. **Diagnóstico** — Situación actual del cliente, pain points identificados, "
            "impacto en su negocio (con números si están disponibles)\n"
            "4. **Solución propuesta** — Qué agentes/servicios proponemos, cómo funcionan, "
            "qué integración requieren con sus sistemas actuales\n"
            "5. **Alcance y entregables** — Lista detallada de lo que incluye y lo que NO incluye\n"
            "6. **Timeline** — Fases con fechas estimadas. Mínimo 3 fases: setup, piloto, producción\n"
            "7. **Inversión** — Tabla de precios clara. Siempre mostrar ROI estimado\n"
            "8. **Próximos pasos** — 3 acciones concretas con responsable y fecha\n"
            "9. **Anexos** — Casos de éxito, especificaciones técnicas si aplican"
        ),
        # Chunk 1: Reglas de redacción
        (
            "# Reglas de Redacción para Propuestas\n\n"
            "## Principio #1: Liderar con el cliente, no con nosotros\n"
            "La primera página completa debe hablar del cliente: su problema, su contexto, "
            "su oportunidad. DigitalMind aparece a partir de la solución propuesta.\n\n"
            "## Principio #2: Números concretos\n"
            "- Cada beneficio debe tener un estimado cuantificable\n"
            "- Ejemplo correcto: 'Reducción del 40% en tiempo de respuesta a clientes'\n"
            "- Ejemplo incorrecto: 'Mejora significativa en tiempos de respuesta'\n\n"
            "## Principio #3: Lenguaje del negocio\n"
            "- No usar jerga técnica (API, webhook, modelo, tokens) en el cuerpo principal\n"
            "- Términos técnicos van en los anexos, no en la narrativa\n"
            "- El CFO debe poder entender la propuesta sin ayuda del CTO\n\n"
            "## Principio #4: Timeline realista\n"
            "- Siempre agregar 20% de buffer al timeline interno\n"
            "- Fase de piloto obligatoria (mínimo 2 semanas) antes de producción\n"
            "- No prometer fechas exactas de entrega — usar 'semana de' o 'sprint de'"
        ),
        # Chunk 2: Tabla de precios modelo
        (
            "# Modelo de Precios — Referencia Interna\n\n"
            "## Paquetes estándar (referencia, ajustar por caso)\n\n"
            "### Starter — $2,500/mes\n"
            "- 3 agentes de IA (1 supervisor + 2 operativos)\n"
            "- 1 departamento configurado\n"
            "- Dashboard de métricas básico\n"
            "- Soporte por email (48h respuesta)\n"
            "- Hasta 500 tareas/mes\n\n"
            "### Professional — $5,000/mes\n"
            "- 8 agentes de IA (3 supervisores + 5 operativos)\n"
            "- 3 departamentos configurados\n"
            "- Dashboard completo + reportes semanales automáticos\n"
            "- Knowledge Base con documentos del cliente\n"
            "- Integraciones: CRM, email, Slack\n"
            "- Soporte prioritario (24h respuesta)\n"
            "- Hasta 2,000 tareas/mes\n\n"
            "### Enterprise — desde $12,000/mes\n"
            "- Agentes ilimitados\n"
            "- Departamentos ilimitados con jerarquía personalizada\n"
            "- MCP tools personalizados\n"
            "- SLA 99.9% uptime\n"
            "- Account Manager dedicado\n"
            "- Onboarding y training incluido\n"
            "- Integración con cualquier sistema vía API/webhook\n\n"
            "**Nota:** Para propuestas, NO mostrar precios de lista directamente. "
            "Calcular precio basado en necesidades reales del cliente y presentar como inversión "
            "con ROI estimado. Los paquetes son referencia interna."
        ),
    ],
}

MANUAL_PROCESOS = {
    "title": "Manual de Procesos Internos — DigitalMind",
    "description": (
        "Procesos operativos estándar de la agencia. "
        "Disponible para todos los agentes de todas las áreas."
    ),
    "file_type": "md",
    "dept_slug": None,  # org-level — all agents
    "chunks": [
        # Chunk 0: Flujo de trabajo estándar
        (
            "# Flujo de Trabajo Estándar\n\n"
            "## Ciclo de vida de una solicitud de cliente\n"
            "1. **Recepción** — El Account Manager recibe la solicitud por email, WhatsApp o formulario web\n"
            "2. **Clasificación** — Se clasifica por tipo (contenido, propuesta, soporte, estrategia) "
            "y urgencia (crítica, alta, media, baja)\n"
            "3. **Asignación** — Se asigna al departamento y supervisor correspondiente\n"
            "4. **Delegación** — El supervisor descompone la tarea y delega a sus agentes operativos\n"
            "5. **Ejecución** — Los agentes ejecutan sus subtareas en paralelo cuando es posible\n"
            "6. **Revisión** — El supervisor revisa y agrega los resultados en un entregable coherente\n"
            "7. **Entrega** — Se envía al cliente con resumen ejecutivo\n"
            "8. **Seguimiento** — A las 48h se confirma satisfacción y se registran mejoras\n\n"
            "## Tiempos de respuesta esperados\n"
            "- Urgencia Crítica: < 2 horas\n"
            "- Urgencia Alta: < 8 horas (mismo día laboral)\n"
            "- Urgencia Media: < 24 horas\n"
            "- Urgencia Baja: < 48 horas"
        ),
        # Chunk 1: Escalamiento y calidad
        (
            "# Proceso de Escalamiento\n\n"
            "## Cuándo escalar\n"
            "Un agente debe escalar a su supervisor cuando:\n"
            "- La tarea requiere acceso a información que no tiene\n"
            "- El resultado tiene una confianza menor al 80%\n"
            "- El cliente solicita algo fuera del alcance del servicio contratado\n"
            "- Han pasado más de 2 intentos sin resultado satisfactorio\n"
            "- La tarea involucra temas legales, financieros sensibles, o datos personales\n\n"
            "## Control de calidad\n"
            "Todo entregable que sale al cliente debe cumplir:\n"
            "- Ortografía y gramática revisadas\n"
            "- Datos verificados con fuente citada\n"
            "- Formato alineado con la guía de marca\n"
            "- Resumen ejecutivo incluido\n"
            "- CTA o próximo paso claro\n\n"
            "## Registro de actividad\n"
            "Cada acción relevante queda registrada en el sistema con: "
            "agente responsable, timestamp, tipo de acción, y resultado. "
            "Esto alimenta las métricas de rendimiento y permite auditoría."
        ),
        # Chunk 2: SLAs y métricas
        (
            "# SLAs y Métricas Operativas\n\n"
            "## SLAs internos (compromisos entre equipos)\n"
            "- Tiempo de clasificación de solicitud: < 15 minutos\n"
            "- Tiempo de primera delegación (supervisor): < 30 minutos después de recibir\n"
            "- Disponibilidad de agentes internos: 99% (24/7)\n"
            "- Disponibilidad de agentes externos: 95% (depende de plataforma)\n\n"
            "## Métricas clave por departamento\n"
            "### Contenido\n"
            "- Piezas producidas por semana (target: 15)\n"
            "- Tasa de aprobación en primera revisión (target: >80%)\n"
            "- Engagement rate promedio en social media (target: >3%)\n\n"
            "### Clientes\n"
            "- Tiempo medio de respuesta a solicitudes (target: <4h)\n"
            "- Tasa de conversión de propuestas (target: >30%)\n"
            "- CSAT score (target: >4.5/5)\n\n"
            "### Estrategia\n"
            "- Planes ejecutados según timeline (target: >85%)\n"
            "- ROI medido en iniciativas completadas\n"
            "- Reportes de datos entregados a tiempo (target: >95%)"
        ),
    ],
}

CATALOGO_SERVICIOS = {
    "title": "Catálogo de Servicios — DigitalMind",
    "description": (
        "Servicios ofrecidos por la agencia con descripción, casos de uso y tecnologías. "
        "Referencia para todos los agentes al responder consultas de clientes."
    ),
    "file_type": "md",
    "dept_slug": None,  # org-level — all agents
    "chunks": [
        # Chunk 0: Servicios core
        (
            "# Servicios Core de DigitalMind\n\n"
            "## 1. Equipos de Agentes de IA\n"
            "Diseñamos e implementamos equipos de agentes de IA que operan como una extensión "
            "del equipo humano del cliente. Cada agente tiene un rol definido, supervisor, "
            "y métricas de rendimiento.\n\n"
            "**Casos de uso:**\n"
            "- Atención al cliente 24/7 con escalamiento automático\n"
            "- Generación de contenido para marketing (blog, social, email)\n"
            "- Análisis de datos y reportes automáticos\n"
            "- Soporte técnico nivel 1 con resolución automatizada\n"
            "- Gestión de propuestas comerciales\n\n"
            "**Tecnología:** Claude API (Anthropic) para agentes internos, "
            "integraciones webhook para agentes externos (n8n, plataformas propias del cliente).\n\n"
            "## 2. Knowledge Base Empresarial\n"
            "Sistema de documentación interna que alimenta a los agentes con información "
            "específica del negocio del cliente: manuales, políticas, precios, procesos.\n\n"
            "**Beneficio:** Los agentes no solo responden con IA genérica — responden "
            "con el conocimiento específico de la empresa."
        ),
        # Chunk 1: Servicios complementarios
        (
            "# Servicios Complementarios\n\n"
            "## 3. Automatización de Workflows\n"
            "Diseño e implementación de flujos de trabajo automatizados que conectan "
            "los agentes de IA con los sistemas existentes del cliente.\n\n"
            "**Integraciones disponibles:**\n"
            "- CRM (HubSpot, Salesforce, Pipedrive)\n"
            "- Email (Gmail, Outlook, SendGrid)\n"
            "- Mensajería (WhatsApp Business, Slack, Teams)\n"
            "- Gestión de proyectos (Asana, Monday, Trello)\n"
            "- Herramientas de diseño (Canva, Figma)\n"
            "- Redes sociales (Meta Business, LinkedIn)\n"
            "- Bases de datos y APIs personalizadas\n\n"
            "## 4. Consultoría en IA Aplicada\n"
            "Evaluamos qué procesos del negocio del cliente pueden beneficiarse "
            "de agentes de IA y diseñamos la estrategia de implementación.\n\n"
            "**Incluye:**\n"
            "- Auditoría de procesos actuales\n"
            "- Mapa de oportunidades de automatización\n"
            "- Business case con ROI estimado\n"
            "- Roadmap de implementación por fases\n"
            "- Acompañamiento durante las primeras 4 semanas post-implementación"
        ),
        # Chunk 2: Diferenciadores y garantías
        (
            "# Diferenciadores Competitivos\n\n"
            "## ¿Por qué DigitalMind y no otros?\n\n"
            "1. **Estructura organizacional de agentes** — No vendemos bots sueltos. "
            "Creamos equipos con supervisores, departamentos, y jerarquía. "
            "El cliente ve un organigrama de su equipo digital.\n\n"
            "2. **Métricas en tiempo real** — Dashboard con KPIs de cada agente: "
            "tareas completadas, tasa de éxito, tiempo de respuesta, costo por tarea. "
            "Los agentes rinden cuentas como un empleado.\n\n"
            "3. **Knowledge Base integrado** — Los agentes aprenden del negocio del cliente. "
            "No respuestas genéricas, sino respuestas con contexto empresarial.\n\n"
            "4. **Prompt engineering medido** — Cada versión del prompt de un agente tiene "
            "una puntuación de rendimiento. Optimizamos continuamente.\n\n"
            "5. **Herramientas externas vía MCP** — Los agentes pueden usar herramientas "
            "reales: publicar en redes, generar diseños, consultar CRMs, enviar emails. "
            "No solo hablan — actúan.\n\n"
            "## Garantía\n"
            "Fase de piloto obligatoria. Si al finalizar el piloto los KPIs acordados "
            "no se cumplen, el cliente puede cancelar sin costo. Sin contratos largos "
            "ni penalidades de salida."
        ),
    ],
}

ALL_DOCUMENTS = [GUIA_DE_MARCA, TEMPLATE_PROPUESTA, MANUAL_PROCESOS, CATALOGO_SERVICIOS]


async def seed_knowledge():
    async with async_session_factory() as session:
        # Check if DigitalMind KB docs already exist (by title match)
        dm_check = await session.execute(
            select(func.count(KnowledgeDocument.id)).where(
                KnowledgeDocument.title.ilike("%DigitalMind%")
            )
        )
        if dm_check.scalar() and dm_check.scalar() > 0:
            print("DigitalMind knowledge docs already seeded. Skipping.")
            return

        # Clean up any old/stale KB docs (e.g. from previous demo scenarios)
        old_docs = await session.execute(select(KnowledgeDocument))
        old_list = old_docs.scalars().all()
        if old_list:
            print(f"Removing {len(old_list)} old KB documents (previous demo scenario)...")
            for old_doc in old_list:
                await session.delete(old_doc)  # cascade deletes chunks
            await session.flush()

        # Get org and user
        org_result = await session.execute(select(Organization).limit(1))
        org = org_result.scalar_one_or_none()
        if org is None:
            print("ERROR: No organization found. Run seed.py first.")
            return

        user_result = await session.execute(select(User.id).limit(1))
        user_row = user_result.first()
        if user_row is None:
            print("ERROR: No user found. Run auth setup first.")
            return

        org_id = org.id
        user_id = user_row[0]

        # Load departments for dept-level scoping
        dept_result = await session.execute(
            select(Department).where(Department.organization_id == org_id)
        )
        departments = {d.slug: d for d in dept_result.scalars().all()}

        print(f"Seeding knowledge base for org: {org.name}")
        print(f"  Departments available: {list(departments.keys())}")

        total_chunks = 0

        for doc_data in ALL_DOCUMENTS:
            dept_slug = doc_data["dept_slug"]
            dept_id = departments[dept_slug].id if dept_slug else None
            scope_label = f"dept:{dept_slug}" if dept_slug else "org-level"

            doc = KnowledgeDocument(
                organization_id=org_id,
                department_id=dept_id,
                title=doc_data["title"],
                description=doc_data["description"],
                file_type=doc_data["file_type"],
                created_by_user_id=user_id,
            )
            session.add(doc)
            await session.flush()  # get doc.id for chunks

            for idx, content in enumerate(doc_data["chunks"]):
                word_count = len(content.split())
                est_tokens = int(word_count * TOKENS_PER_WORD)

                chunk = KnowledgeChunk(
                    document_id=doc.id,
                    organization_id=org_id,
                    department_id=dept_id,
                    chunk_index=idx,
                    content=content,
                    token_count=est_tokens,
                )
                session.add(chunk)
                total_chunks += 1

            print(f"  [{scope_label}] {doc_data['title']} — {len(doc_data['chunks'])} chunks")

        await session.commit()

        print(f"\nKnowledge base seeded!")
        print(f"  Documents: {len(ALL_DOCUMENTS)}")
        print(f"  Total chunks: {total_chunks}")
        print(f"  Dept-level: 2 (contenido, clientes)")
        print(f"  Org-level: 2 (procesos internos, catálogo servicios)")


if __name__ == "__main__":
    asyncio.run(seed_knowledge())
