"""
Test infrastructure for CRM Agents.

Strategy:
- Separate test database (`crm_agents_test`) — never touches dev/prod data.
- Schema created once per test session with `Base.metadata.create_all`.
- Each test runs inside a transaction that gets rolled back — guarantees isolation
  without paying the cost of TRUNCATE/DROP between tests.
- The HTTP client receives the same session via FastAPI dependency override,
  so handler-level changes are visible to the test and rolled back together.

Fixtures:
- `test_engine` (session) — async engine + schema lifecycle
- `db` (function) — per-test session inside a rolled-back transaction
- `client` (function) — AsyncClient with `get_db` overridden to use `db`
- `test_org` (function) — fresh Organization with unique slug
- `test_user` (function) — fresh User (OWNER) belonging to test_org
- `auth_headers` (function) — Bearer token headers for test_user
"""

import uuid
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.agents.models import (
    Agent,
    AgentDefinition,
    AgentIntegration,
    AgentOrigin,
    AgentStatus,
    IntegrationType,
)
from app.auth.models import Organization, User, UserRole
from app.auth.service import create_access_token, hash_password
from app.core.database import Base, get_db
from app.core.middleware import reset_rate_limit_state
from app.main import app
from app.tasks.models import Task, TaskStatus

# Import ALL models so they register with Base.metadata before create_all runs.
# Keep this list in sync with alembic/env.py.
from app.agents.models import (  # noqa: F401
    Agent, AgentDefinition, AgentIntegration, ApiKey,
    Permission, Role, RolePermission,
)
from app.departments.models import Department  # noqa: F401
from app.tasks.models import Task  # noqa: F401
from app.activities.models import ActivityLog  # noqa: F401
from app.metrics.models import PerformanceMetric  # noqa: F401
from app.interactions.models import AgentInteraction  # noqa: F401
from app.improvements.models import ImprovementPoint  # noqa: F401
from app.prompts.models import PromptVersion, PromptTemplate  # noqa: F401
from app.auth.models import TokenBlacklist  # noqa: F401
from app.knowledge.models import KnowledgeDocument, KnowledgeChunk  # noqa: F401
from app.credentials.models import Credential  # noqa: F401
from app.notifications.models import Notification  # noqa: F401


# Test database — separate from dev so a destructive test can never harm seed data.
TEST_DATABASE_URL = (
    "postgresql+asyncpg://richardfigueroa@localhost:5432/crm_agents_test"
)


@pytest.fixture(autouse=True)
def _clean_rate_limit_state():
    """
    Reset the in-memory rate limiter before every test. Without this, tests
    leak request counts to each other (the middleware lives at module scope).
    Specific tests still get a clean slate to verify rate-limit behavior end-to-end.
    """
    reset_rate_limit_state()
    yield
    reset_rate_limit_state()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine():
    """
    Session-scoped engine. Drops + recreates schema once per test session.
    NullPool avoids connection-state pollution between tests.
    `loop_scope="session"` keeps this on the same event loop across all tests.
    """
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool, echo=False)
    # Drop the entire schema (handles FKs with use_alter that drop_all can't manage)
    # then recreate from current SQLAlchemy metadata. Faster than running migrations
    # and guarantees the test DB matches our model definitions exactly.
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Per-test session wrapped in a transaction that rolls back on teardown.
    Any commits inside handler code are absorbed by the outer transaction.
    """
    async with test_engine.connect() as conn:
        trans = await conn.begin()
        session_maker = async_sessionmaker(bind=conn, expire_on_commit=False)
        session = session_maker()
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest_asyncio.fixture
async def client(db) -> AsyncGenerator[AsyncClient, None]:
    """
    HTTP client with the FastAPI `get_db` dependency overridden to use the
    per-test session. This way, data created via API calls is visible inside
    the test and gets rolled back at teardown.
    """

    async def override_get_db():
        # Yield without committing — the test's outer transaction owns commit/rollback.
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_org(db) -> Organization:
    """Fresh Organization with a unique slug — no collisions across tests."""
    org = Organization(
        name="Test Organization",
        slug=f"test-org-{uuid.uuid4().hex[:12]}",
    )
    db.add(org)
    await db.flush()
    await db.refresh(org)
    return org


@pytest_asyncio.fixture
async def test_user(db, test_org) -> User:
    """Fresh User (OWNER role) belonging to test_org. Password is 'Test1234'."""
    user = User(
        email=f"user-{uuid.uuid4().hex[:8]}@test.io",
        password_hash=hash_password("Test1234"),
        full_name="Test User",
        role=UserRole.OWNER,
        organization_id=test_org.id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user, test_org) -> dict[str, str]:
    """Bearer token headers for test_user — drop into any authenticated request."""
    token, _ = create_access_token(test_user.id, test_org.id, test_user.role.value)
    return {"Authorization": f"Bearer {token}"}


# ─── Second org fixtures (for tenant isolation tests) ─────────────────────────
# These let us create resources in TWO different orgs in the same test, then
# verify that org A's user cannot see/modify/delete org B's data.


@pytest_asyncio.fixture
async def second_org(db) -> Organization:
    """A second Organization, fully separate from test_org."""
    org = Organization(
        name="Second Test Organization",
        slug=f"test-org-2-{uuid.uuid4().hex[:12]}",
    )
    db.add(org)
    await db.flush()
    await db.refresh(org)
    return org


@pytest_asyncio.fixture
async def second_user(db, second_org) -> User:
    """User belonging to second_org. Password is 'Test1234'."""
    user = User(
        email=f"user2-{uuid.uuid4().hex[:8]}@test.io",
        password_hash=hash_password("Test1234"),
        full_name="Second Org User",
        role=UserRole.OWNER,
        organization_id=second_org.id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def second_auth_headers(second_user, second_org) -> dict[str, str]:
    """Bearer token for second_user — used to make requests AS the second org."""
    token, _ = create_access_token(
        second_user.id, second_org.id, second_user.role.value
    )
    return {"Authorization": f"Bearer {token}"}


# ─── Agent fixtures (for task execution tests) ────────────────────────────────


@pytest_asyncio.fixture
async def internal_agent(db, test_org) -> Agent:
    """An internal Claude-backed agent in test_org with a minimal definition."""
    suffix = uuid.uuid4().hex[:8]
    agent = Agent(
        name=f"Internal Agent {suffix}",
        slug=f"internal-{suffix}",
        origin=AgentOrigin.INTERNAL,
        status=AgentStatus.ACTIVE,
        organization_id=test_org.id,
    )
    db.add(agent)
    await db.flush()

    definition = AgentDefinition(
        agent_id=agent.id,
        system_prompt="Eres un asistente de prueba. Responde brevemente.",
        model_provider="anthropic",
        model_name="claude-sonnet-4-5",
        temperature=0.7,
        max_tokens=1024,
        tools=[],
    )
    db.add(definition)
    await db.flush()
    await db.refresh(agent, attribute_names=["definition"])
    return agent


@pytest_asyncio.fixture
async def external_agent(db, test_org) -> Agent:
    """An external webhook-backed agent in test_org."""
    suffix = uuid.uuid4().hex[:8]
    agent = Agent(
        name=f"External Agent {suffix}",
        slug=f"external-{suffix}",
        origin=AgentOrigin.EXTERNAL,
        status=AgentStatus.ACTIVE,
        organization_id=test_org.id,
    )
    db.add(agent)
    await db.flush()

    integration = AgentIntegration(
        agent_id=agent.id,
        integration_type=IntegrationType.WEBHOOK,
        platform="n8n",
        endpoint_url="https://n8n.test.io/webhook/fake",
    )
    db.add(integration)
    await db.flush()
    await db.refresh(agent, attribute_names=["integration"])
    return agent


# ─── Claude API mock ──────────────────────────────────────────────────────────
# We never want to hit the real Claude API in tests:
# (1) it costs money on every CI run, (2) it's slow (10-60s), (3) responses
# are non-deterministic. The fake_claude fixture patches `_get_client()` in the
# agent_executor so internal task execution returns a canned response instantly.


def _make_fake_claude_message(text: str = "Respuesta de prueba", input_tokens: int = 100, output_tokens: int = 50):
    """
    Build an object that quacks like an `anthropic.types.Message` for the parts
    of the response the executor reads (.content, .stop_reason, .usage, .model).
    """
    text_block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(
        content=[text_block],
        stop_reason="end_turn",
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
        model="claude-sonnet-4-5",
        id=f"msg_test_{uuid.uuid4().hex[:8]}",
        role="assistant",
        type="message",
    )


@pytest_asyncio.fixture
async def fake_claude(monkeypatch):
    """
    Patches `_get_client()` in agent_executor with a mock whose
    `messages.create()` returns a deterministic Message-shaped response.

    Default response: text="Respuesta de prueba", end_turn, 100/50 tokens.
    Tests that need different responses can mutate `client.messages.create`
    via the returned mock.
    """
    fake_message = _make_fake_claude_message()

    fake_client = AsyncMock()
    fake_client.messages.create = AsyncMock(return_value=fake_message)

    # Replace `_get_client` so any module that calls it gets our fake
    monkeypatch.setattr(
        "app.workers.agent_executor._get_client",
        lambda: fake_client,
    )
    yield fake_client
