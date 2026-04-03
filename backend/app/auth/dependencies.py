"""
FastAPI dependencies for authentication and authorization.
Inject get_current_user into any route that needs auth.
"""

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRole
from app.auth.service import decode_token, get_user_by_id
from app.core.database import get_db

# Bearer token extractor — looks for "Authorization: Bearer <token>"
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Decode JWT from Authorization header and return the authenticated User.
    Raises 401 on missing/invalid token, 403 on inactive user.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticacion requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere un access token",
        )

    user_id = uuid.UUID(payload["sub"])
    user = await get_user_by_id(user_id, db)

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario desactivado")

    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Like get_current_user but returns None instead of 401 — for public endpoints."""
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


async def get_org_id(user: User = Depends(get_current_user)) -> uuid.UUID:
    """Extract organization_id from the authenticated user — use in services."""
    return user.organization_id


def require_role(*allowed_roles: UserRole):
    """
    Dependency factory — restricts a route to specific user roles.
    Usage: Depends(require_role(UserRole.OWNER, UserRole.ADMIN))
    """

    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere rol: {', '.join(r.value for r in allowed_roles)}",
            )
        return user

    return _check
