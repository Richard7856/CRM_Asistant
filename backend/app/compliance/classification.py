"""
Data classification registry + tenant erasure plan — the backbone of P0.7.

ONE source of truth, three jobs:

1. CLASSIFY every tenant table as PII / OPERATIONAL / METADATA. The export
   manifest uses this to tell a customer exactly what kind of data they're
   getting back, and the future LLM sensitivity router (L2) will use it to
   decide what must never leave a private instance.

2. ORDER the deletion of a tenant's rows. ~15 tables point at organizations.id
   WITHOUT `ON DELETE CASCADE`, so a naive `DELETE FROM organizations` fails on
   the first foreign-key violation. We delete FK-holders first, let the existing
   CASCADE children fall with their parents, and drop the organization row last.

3. ENUMERATE the tenant-scoped tables so a coverage test fails loudly the day
   someone adds a new table with organization_id and forgets to wire it into
   erasure/export.

WHY an explicit plan instead of schema-wide ON DELETE CASCADE (decided with
Richard, 2026-06-12): erasing a tenant is rare and irreversible, so it must be
deliberate and auditable — we count every row before it dies to build the
erasure certificate. A blanket CASCADE would turn any accidental org delete
into a silent total wipe.
"""

import enum


class DataClass(str, enum.Enum):
    """Sensitivity tier of a table's contents. Drives export labeling + future L2 routing."""

    PII = "pii"                  # identifies a person: email, full name, free text authored by users
    OPERATIONAL = "operational"  # business data: tasks, agent configs, metrics, knowledge
    METADATA = "metadata"        # system bookkeeping with no standalone personal data


# ─── Tenant tables: every table carrying organization_id ──────────────────────
# Maps table name → its top sensitivity class. The export manifest and the
# /classification endpoint surface this verbatim. A test asserts this dict covers
# exactly the set of tables that have an organization_id column — no more, no less.
TENANT_TABLE_CLASSIFICATION: dict[str, DataClass] = {
    "users": DataClass.PII,                  # email, full_name
    "agents": DataClass.OPERATIONAL,         # config; name/description rarely PII
    "departments": DataClass.OPERATIONAL,
    "tasks": DataClass.OPERATIONAL,          # title/description can embed customer data
    "activity_logs": DataClass.OPERATIONAL,  # summary/details JSONB may embed payloads
    "performance_metrics": DataClass.METADATA,
    "agent_interactions": DataClass.OPERATIONAL,  # payload JSONB from external endpoints
    "improvement_points": DataClass.OPERATIONAL,
    "notifications": DataClass.OPERATIONAL,  # title/body
    "credentials": DataClass.PII,            # secret_value (encrypted), notes
    "knowledge_documents": DataClass.PII,    # uploaded docs: contracts, customer records
    "knowledge_chunks": DataClass.PII,       # chunked content of the above
    "audit_log": DataClass.PII,              # context JSONB may hold IP / user-agent
    "autonomy_policies": DataClass.OPERATIONAL,
    "approval_requests": DataClass.PII,      # action_input JSONB = exact user input
    "retention_policies": DataClass.METADATA,  # per-tenant retention config (P0.7b)
}

# Columns that are PII at the field level — used to label exports and, later, to
# tell L2 which columns must stay on a private LLM. Not exhaustive of every JSONB
# blob (those are classified at the table level above), just the typed columns.
PII_COLUMNS: dict[str, list[str]] = {
    "users": ["email", "full_name", "password_hash"],
    "credentials": ["secret_value", "secret_preview", "notes"],
    "knowledge_documents": ["title", "description"],
    "knowledge_chunks": ["content"],
    "audit_log": ["context"],
    "approval_requests": ["action_input", "shadow_simulated_output"],
}


# ─── Erasure plan ─────────────────────────────────────────────────────────────
# Phase A — null out FK references that would otherwise block ordered deletion:
# self-references and the agents↔departments cycle (departments.head_agent_id is
# added with use_alter precisely because of this cycle). Listed as
# (table_name, {column: None}).
ERASURE_NULL_BREAKERS: list[tuple[str, dict[str, None]]] = [
    ("agents", {"supervisor_id": None, "created_by_agent_id": None}),
    ("departments", {"head_agent_id": None, "parent_id": None}),
    ("tasks", {"parent_task_id": None}),
]

# Phase B — delete tenant rows in dependency order (FK-holders first). Children
# declared with ON DELETE CASCADE are NOT listed here because they fall with their
# parent automatically; the comment on each line notes what cascades:
ERASURE_DELETE_ORDER: list[str] = [
    "audit_log",            # → users, agents, organizations
    "approval_requests",    # → agents, tasks, users
    "autonomy_policies",    # → users
    "retention_policies",   # → users (P0.7b)
    "activity_logs",        # → agents, tasks
    "agent_interactions",   # → agents, tasks
    "performance_metrics",  # → agents
    "improvement_points",   # → agents
    "notifications",        # → agents
    "credentials",          # cascades credential_access_log
    "knowledge_documents",  # cascades knowledge_chunks
    "tasks",                # → agents, departments (self-ref nulled in phase A)
    "agents",               # cascades agent_definitions, agent_integrations, api_keys,
                            #   prompt_versions, department_agent_permissions
    "users",               # delete before departments (users.department_id → departments)
    "departments",          # cascades department_tool_permissions; org row deleted last
]

# Tables intentionally NEVER touched by tenant erasure:
# - roles / permissions / role_permissions: GLOBAL seed data shared across tenants
# - prompt_templates: GLOBAL catalog (no organization_id, no agent_id)
# - token_blacklist: no organization_id; purged by user_id during erasure (see repo)
# - erasure_certificates: the durable proof, must survive the org's deletion
# - alembic_version: migration bookkeeping
GLOBAL_TABLES: frozenset[str] = frozenset(
    {
        "roles",
        "permissions",
        "role_permissions",
        "prompt_templates",
        "token_blacklist",
        "erasure_certificates",
        "alembic_version",
    }
)


def tenant_table_names() -> frozenset[str]:
    """The set of tables that hold tenant data (have an organization_id column)."""
    return frozenset(TENANT_TABLE_CLASSIFICATION.keys())
