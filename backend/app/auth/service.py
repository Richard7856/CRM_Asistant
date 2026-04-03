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

from app.auth.models import Organization, User, UserRole
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


def create_access_token(user_id: uuid.UUID, org_id: uuid.UUID, role: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "org": str(org_id),
        "role": role,
        "exp": expires,
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: uuid.UUID) -> str:
    expires = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": str(user_id),
        "exp": expires,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


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
    """Validate a refresh token and return a new access + refresh token pair."""
    try:
        payload = decode_token(refresh_token)
    except JWTError:
        raise ValueError("Refresh token invalido o expirado")

    if payload.get("type") != "refresh":
        raise ValueError("Token no es de tipo refresh")

    user_id = uuid.UUID(payload["sub"])
    user = await get_user_by_id(user_id, db)
    if user is None or not user.is_active:
        raise ValueError("Usuario no encontrado o inactivo")

    access = create_access_token(user.id, user.organization_id, user.role.value)
    refresh = create_refresh_token(user.id)
    return access, refresh
