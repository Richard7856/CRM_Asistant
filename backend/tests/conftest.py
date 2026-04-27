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

from app.auth.models import Organization, User, UserRole
from app.auth.service import create_access_token, hash_password
from app.core.database import Base, get_db
from app.core.middleware import reset_rate_limit_state
from app.main import app

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
