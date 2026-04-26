"""
Auth service — handles user registration, login, and JWT lifecycle.
Passwords hashed with bcrypt via passlib. Tokens signed with HS256 via python-jose.
"""

import re
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.auth.models import Organization, TokenBlacklist, User, UserRole
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _slugify(name: str) -> str:
    """Convert org name to a URL-safe slug."""
    slug = re.sub(r"[^\w\s-]", "", name.lower().strip())
    return re.sub(r"[\s_]+", "-", slug)[:60]


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: uuid.UUID, org_id: uuid.UUID, role: str) -> tuple[str, str]:
    """Returns (token, jti) — jti is the unique ID used for blacklisting."""
    jti = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "org": str(org_id),
        "role": role,
        "exp": expires,
        "type": "access",
        "jti": jti,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, jti


def create_refresh_token(user_id: uuid.UUID) -> tuple[str, str]:
    """Returns (token, jti) — jti is the unique ID used for blacklisting."""
    jti = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": str(user_id),
        "exp": expires,
        "type": "refresh",
        "jti": jti,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, jti


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises JWTError on invalid/expired tokens."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


async def register_user(
    email: str,
    password: str,
    full_name: str,
    org_name: str,
    db: AsyncSession,
) -> tuple[User, Organization]:
    """
    Register a new user. Creates an Organization if needed.
    The first user of an org gets the OWNER role.
    """
    # Check duplicate email
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise ValueError("El email ya esta registrado")

    # Find or create organization
    slug = _slugify(org_name)
    result = await db.execute(select(Organization).where(Organization.slug == slug))
    org = result.scalar_one_or_none()

    if org is None:
        org = Organization(name=org_name, slug=slug)
        db.add(org)
        await db.flush()  # get org.id
        role = UserRole.OWNER
    else:
        role = UserRole.MEMBER

    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
        organization_id=org.id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    await db.refresh(org)

    return user, org


async def authenticate_user(
    email: str, password: str, db: AsyncSession
) -> User | None:
    """Verify credentials. Returns User if valid, None otherwise."""
    result = await db.execute(
        select(User)
        .options(selectinload(User.organization))
        .where(User.email == email)
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user


async def get_user_by_id(user_id: uuid.UUID, db: AsyncSession) -> User | None:
    result = await db.execute(
        select(User)
        .options(selectinload(User.organization))
        .where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def refresh_tokens(refresh_token: str, db: AsyncSession) -> tuple[str, str]:
    """
    Validate a refresh token and return a new access + refresh pair.
    Implements rotation: the old refresh token is blacklisted after use.
    """
    try:
        payload = decode_token(refresh_token)
    except JWTError:
        raise ValueError("Refresh token invalido o expirado")

    if payload.get("type") != "refresh":
        raise ValueError("Token no es de tipo refresh")

    # Check if old refresh token was already used (rotation protection)
    old_jti = payload.get("jti")
    if old_jti and await is_token_blacklisted(old_jti, db):
        raise ValueError("Refresh token ya fue utilizado")

    user_id = uuid.UUID(payload["sub"])
    user = await get_user_by_id(user_id, db)
    if user is None or not user.is_active:
        raise ValueError("Usuario no encontrado o inactivo")

    # Issue new pair
    access, _ = create_access_token(user.id, user.organization_id, user.role.value)
    refresh, _ = create_refresh_token(user.id)

    # Blacklist old refresh token so it can't be reused
    if old_jti:
        expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        await blacklist_token(old_jti, "refresh", user_id, expires_at, db)

    return access, refresh


# ─── Token blacklist ───


async def blacklist_token(
    jti: str,
    token_type: str,
    user_id: uuid.UUID,
    expires_at: datetime,
    db: AsyncSession,
) -> None:
    """Add a token JTI to the blacklist. Idempotent — ignores duplicates."""
    stmt = (
        pg_insert(TokenBlacklist)
        .values(
            jti=jti,
            token_type=token_type,
            user_id=user_id,
            expires_at=expires_at,
        )
        .on_conflict_do_nothing(index_elements=["jti"])
    )
    await db.execute(stmt)


async def is_token_blacklisted(jti: str, db: AsyncSession) -> bool:
    """Check if a token JTI has been revoked."""
    result = await db.execute(
        select(TokenBlacklist.id).where(TokenBlacklist.jti == jti).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def cleanup_expired_blacklist(db: AsyncSession) -> int:
    """Remove blacklist entries for tokens that have already expired. Returns count deleted."""
    from sqlalchemy import delete

    result = await db.execute(
        delete(TokenBlacklist).where(
            TokenBlacklist.expires_at < datetime.now(timezone.utc)
        )
    )
    return result.rowcount
