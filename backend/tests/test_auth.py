"""
Auth flow integration tests — covers everything implemented in Phase 5A.

Test classes:
- TestRegister:          new user/org creation
- TestPasswordStrength:  validation rules from RegisterRequest
- TestLogin:             credential authentication
- TestRefreshRotation:   refresh token rotation + blacklist
- TestLogout:            token revocation
- TestRateLimiting:      sliding-window protection on auth endpoints
- TestSecurityHeaders:   middleware that hardens responses

Each test runs against a fresh DB transaction (rolled back at teardown) and
a fresh rate-limit state (cleared autouse). No test depends on another.
"""

import base64
import json
import uuid

import pytest
from sqlalchemy import select

from app.auth.models import TokenBlacklist, User
from app.auth.service import create_access_token, create_refresh_token


def _decode_jwt_payload(token: str) -> dict:
    """Decode the payload of a JWT without verifying signature (for tests only)."""
    payload_b64 = token.split(".")[1]
    # JWT base64 strings sometimes lack padding — pad to multiple of 4
    payload_b64 += "=" * (4 - len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64))


# ─────────────────────────────────────────────────────────────────────────────
# TestRegister
# ─────────────────────────────────────────────────────────────────────────────


class TestRegister:
    async def test_register_creates_user_and_org(self, client, db):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "alice@example.com",
                "password": "Strong123",
                "full_name": "Alice Tester",
                "org_name": "Alice Org",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert "access_token" in body and "refresh_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 30 * 60  # 30 minutes in seconds

        # Verify user was actually persisted
        result = await db.execute(select(User).where(User.email == "alice@example.com"))
        user = result.scalar_one()
        assert user.full_name == "Alice Tester"
        assert user.role.value == "owner"  # first user of an org → OWNER

    async def test_register_tokens_have_jti(self, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "bob@example.com",
                "password": "Strong123",
                "full_name": "Bob",
                "org_name": "Bob Org",
            },
        )
        body = response.json()
        access_payload = _decode_jwt_payload(body["access_token"])
        refresh_payload = _decode_jwt_payload(body["refresh_token"])
        # JTI is the linchpin of Phase 5A's blacklist mechanism — verify it's present
        assert "jti" in access_payload
        assert "jti" in refresh_payload
        # And they should be different UUIDs
        assert access_payload["jti"] != refresh_payload["jti"]

    async def test_register_duplicate_email_returns_409(self, client, test_user):
        # test_user fixture already created a user — try to register with same email
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": test_user.email,
                "password": "Strong123",
                "full_name": "Impostor",
                "org_name": "Impostor Org",
            },
        )
        assert response.status_code == 409
        assert "ya esta registrado" in response.json()["detail"]

    async def test_register_invalid_email_returns_422(self, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "not-an-email",
                "password": "Strong123",
                "full_name": "X",
                "org_name": "X Org",
            },
        )
        assert response.status_code == 422

    async def test_register_short_password_returns_422(self, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "short@example.com",
                "password": "Sh0rt",  # 5 chars — under the 8-char minimum
                "full_name": "X",
                "org_name": "X Org",
            },
        )
        assert response.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# TestPasswordStrength
# ─────────────────────────────────────────────────────────────────────────────


class TestPasswordStrength:
    """NIST 800-63B basics: uppercase + lowercase + digit. No special-char dance."""

    @pytest.mark.parametrize(
        "password,missing",
        [
            ("alllowercase1", "mayuscula"),
            ("ALLUPPERCASE1", "minuscula"),
            ("NoDigitsHere", "numero"),
        ],
    )
    async def test_weak_passwords_rejected(self, client, password, missing):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"weak-{uuid.uuid4().hex[:6]}@example.com",
                "password": password,
                "full_name": "X",
                "org_name": f"Org-{uuid.uuid4().hex[:6]}",
            },
        )
        assert response.status_code == 422
        # Pydantic wraps the validator error — verify our message is in there
        body = response.json()
        assert any(missing in str(err) for err in body["detail"])

    async def test_strong_password_accepted(self, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "strong@example.com",
                "password": "StrongP4ss",  # has all three categories
                "full_name": "Strong User",
                "org_name": "Strong Org",
            },
        )
        assert response.status_code == 201


# ─────────────────────────────────────────────────────────────────────────────
# TestLogin
# ─────────────────────────────────────────────────────────────────────────────


class TestLogin:
    async def test_login_with_valid_credentials_returns_tokens(self, client, test_user):
        # test_user fixture sets password to "Test1234"
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "Test1234"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert "refresh_token" in body

    async def test_login_tokens_have_jti(self, client, test_user):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "Test1234"},
        )
        body = response.json()
        assert "jti" in _decode_jwt_payload(body["access_token"])
        assert "jti" in _decode_jwt_payload(body["refresh_token"])

    async def test_login_with_wrong_password_returns_401(self, client, test_user):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "WrongPass1"},
        )
        assert response.status_code == 401
        assert "Credenciales invalidas" in response.json()["detail"]

    async def test_login_with_unknown_email_returns_401(self, client):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@nowhere.io", "password": "Whatever1"},
        )
        # Same generic error as wrong password — don't leak which one is wrong
        assert response.status_code == 401
        assert "Credenciales invalidas" in response.json()["detail"]

    async def test_inactive_user_cannot_login(self, client, test_user, db):
        # Deactivate the user
        test_user.is_active = False
        await db.flush()

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "Test1234"},
        )
        # authenticate_user returns None for inactive users → same 401
        assert response.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# TestRefreshRotation
# ─────────────────────────────────────────────────────────────────────────────


class TestRefreshRotation:
    """The crown jewel of Phase 5A — verify a refresh token can't be reused."""

    async def test_refresh_returns_new_pair(self, client, test_user, test_org):
        refresh_token, _ = create_refresh_token(test_user.id)
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        body = response.json()
        # Both new tokens must be present and not equal to the old refresh
        assert body["refresh_token"] != refresh_token
        assert "access_token" in body

    async def test_refresh_rejects_old_token_after_rotation(
        self, client, test_user, test_org
    ):
        refresh_token, _ = create_refresh_token(test_user.id)
        # Use the refresh token once → succeeds
        first = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert first.status_code == 200

        # Reuse the SAME old token → must fail (it's now blacklisted)
        second = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert second.status_code == 401
        assert "ya fue utilizado" in second.json()["detail"]

    async def test_refresh_blacklists_old_jti(self, client, test_user, db):
        refresh_token, old_jti = create_refresh_token(test_user.id)
        await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        # The old JTI must be in the blacklist now
        result = await db.execute(
            select(TokenBlacklist).where(TokenBlacklist.jti == old_jti)
        )
        entry = result.scalar_one()
        assert entry.token_type == "refresh"
        assert entry.user_id == test_user.id

    async def test_refresh_with_access_token_fails(self, client, test_user, test_org):
        # Pass an access token where a refresh is expected — should reject
        access_token, _ = create_access_token(
            test_user.id, test_org.id, test_user.role.value
        )
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": access_token},
        )
        assert response.status_code == 401
        assert "no es de tipo refresh" in response.json()["detail"]

    async def test_refresh_with_garbage_token_fails(self, client):
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "this.is.not.a.jwt"},
        )
        assert response.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# TestLogout
# ─────────────────────────────────────────────────────────────────────────────


class TestLogout:
    async def test_logout_blacklists_access_token(
        self, client, test_user, test_org, auth_headers, db
    ):
        access_token = auth_headers["Authorization"].split()[1]
        access_jti = _decode_jwt_payload(access_token)["jti"]

        response = await client.post("/api/v1/auth/logout", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["message"] == "Sesion cerrada exitosamente"

        # The access token's JTI must now be in the blacklist
        result = await db.execute(
            select(TokenBlacklist).where(TokenBlacklist.jti == access_jti)
        )
        assert result.scalar_one().token_type == "access"

    async def test_logout_blacklists_refresh_token_when_provided(
        self, client, test_user, auth_headers, db
    ):
        refresh_token, refresh_jti = create_refresh_token(test_user.id)
        await client.post(
            "/api/v1/auth/logout",
            headers=auth_headers,
            json={"refresh_token": refresh_token},
        )

        result = await db.execute(
            select(TokenBlacklist).where(TokenBlacklist.jti == refresh_jti)
        )
        assert result.scalar_one().token_type == "refresh"

    async def test_logout_without_auth_returns_401(self, client):
        response = await client.post("/api/v1/auth/logout")
        assert response.status_code == 401

    async def test_access_after_logout_is_revoked(self, client, auth_headers):
        # Logout invalidates the access token
        logout = await client.post("/api/v1/auth/logout", headers=auth_headers)
        assert logout.status_code == 200

        # Same token used again → 401 with "revoked" message
        followup = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert followup.status_code == 401
        assert "revocado" in followup.json()["detail"]

    async def test_logout_is_idempotent(self, client, auth_headers):
        """Calling logout twice with the same token should not crash."""
        first = await client.post("/api/v1/auth/logout", headers=auth_headers)
        assert first.status_code == 200

        # Second call: token is already blacklisted, get_current_user rejects it
        # before reaching the logout handler — this should be 401, not 500
        second = await client.post("/api/v1/auth/logout", headers=auth_headers)
        assert second.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# TestRateLimiting
# ─────────────────────────────────────────────────────────────────────────────


class TestRateLimiting:
    """
    The autouse `_clean_rate_limit_state` fixture in conftest.py guarantees each
    test starts from zero — so we can test the exact threshold behavior.
    """

    async def test_login_blocks_after_5_attempts_per_minute(self, client):
        payload = {"email": "ghost@nowhere.io", "password": "Whatever1"}
        # First 5 attempts: each returns 401 (bad credentials, but rate limiter
        # lets them through — 401 ≠ 429)
        for i in range(5):
            response = await client.post("/api/v1/auth/login", json=payload)
            assert response.status_code == 401, f"Request {i + 1} unexpectedly blocked"

        # 6th attempt within the window: must be rate-limited
        response = await client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 429
        assert "Demasiadas solicitudes" in response.json()["detail"]

    async def test_register_blocks_after_3_attempts_per_minute(self, client):
        for i in range(3):
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"new-{i}@example.com",
                    "password": "Strong123",
                    "full_name": "X",
                    "org_name": f"Org{i}",
                },
            )
            # 201 (created) or 422 (validation) both count toward rate limit
            assert response.status_code in (201, 422)

        # 4th attempt: blocked
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "blocked@example.com",
                "password": "Strong123",
                "full_name": "X",
                "org_name": "Blocked Org",
            },
        )
        assert response.status_code == 429

    async def test_rate_limit_response_includes_retry_after_header(self, client):
        payload = {"email": "x@y.io", "password": "Whatever1"}
        # Burn through the limit
        for _ in range(5):
            await client.post("/api/v1/auth/login", json=payload)

        response = await client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 429
        # Retry-After tells the client how many seconds to wait
        assert "Retry-After" in response.headers
        assert int(response.headers["Retry-After"]) > 0
        assert response.headers["X-RateLimit-Limit"] == "5"
        assert response.headers["X-RateLimit-Remaining"] == "0"

    async def test_successful_request_includes_rate_limit_headers(self, client, test_user):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "Test1234"},
        )
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "5"
        # 5 - 1 (this request) = 4 remaining
        assert response.headers["X-RateLimit-Remaining"] == "4"

    async def test_non_auth_endpoints_not_rate_limited(self, client):
        # /health is not in RATE_LIMITS — should never get 429 no matter how many hits
        for _ in range(20):
            response = await client.get("/health")
            assert response.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# TestSecurityHeaders
# ─────────────────────────────────────────────────────────────────────────────


class TestSecurityHeaders:
    async def test_response_has_clickjacking_protection(self, client):
        response = await client.get("/health")
        assert response.headers["X-Frame-Options"] == "DENY"

    async def test_response_has_content_type_protection(self, client):
        response = await client.get("/health")
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    async def test_response_has_referrer_policy(self, client):
        response = await client.get("/health")
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
