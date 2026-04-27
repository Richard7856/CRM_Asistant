"""
Smoke tests — verify the test infrastructure itself works.

If these fail, nothing else in the test suite will work either.
Each one validates a specific layer of the conftest.py setup.
"""

from sqlalchemy import select

from app.auth.models import User


class TestInfraSmoke:
    """Sanity checks for the test infrastructure."""

    async def test_db_fixture_works(self, db):
        """The db fixture provides a usable AsyncSession."""
        result = await db.execute(select(1))
        assert result.scalar() == 1

    async def test_test_org_is_persisted(self, db, test_org):
        """test_org fixture creates a real Organization visible in the session."""
        assert test_org.id is not None
        assert test_org.slug.startswith("test-org-")

    async def test_test_user_is_persisted(self, db, test_user, test_org):
        """test_user fixture creates a User linked to test_org."""
        assert test_user.id is not None
        assert test_user.organization_id == test_org.id
        # Verify it's actually in the DB (not just in-memory)
        result = await db.execute(select(User).where(User.id == test_user.id))
        fetched = result.scalar_one()
        assert fetched.email == test_user.email

    async def test_client_hits_public_endpoint(self, client):
        """HTTP client can hit unauthenticated endpoints."""
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    async def test_auth_headers_unlock_protected_endpoint(self, client, auth_headers, test_user):
        """JWT in auth_headers fixture grants access to protected /auth/me."""
        response = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["email"] == test_user.email

    async def test_request_without_auth_is_rejected(self, client):
        """Protected endpoint returns 401 without bearer token."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401

    async def test_isolation_between_tests(self, db):
        """
        After this test, the DB should be empty again.
        We rely on the next run of test_db_fixture_works to confirm rollback worked,
        but we can at least verify no data leaked from previous tests into this one.
        """
        result = await db.execute(select(User))
        # Should be empty — previous test's test_user was rolled back
        users = result.scalars().all()
        assert len(users) == 0, f"Expected empty users table, found {len(users)}"
