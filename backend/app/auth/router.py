"""
Auth router — register, login, refresh, logout, and user profile endpoints.
Public routes (no auth required): register, login, refresh, health.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.auth.service import (
    authenticate_user,
    blacklist_token,
    create_access_token,
    create_refresh_token,
    decode_token,
    refresh_tokens,
    register_user,
)
from app.config import settings
from app.core.database import get_db

_bearer = HTTPBearer()

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Create a new user and organization. Returns JWT tokens."""
    try:
        user, org = await register_user(
            email=body.email,
            password=body.password,
            full_name=body.full_name,
            org_name=body.org_name,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    access, _ = create_access_token(user.id, org.id, user.role.value)
    refresh, _ = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with email + password. Returns JWT tokens."""
    user = await authenticate_user(body.email, body.password, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales invalidas",
        )

    access, _ = create_access_token(user.id, user.organization_id, user.role.value)
    refresh, _ = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a refresh token for a new access + refresh token pair."""
    try:
        access, new_refresh = await refresh_tokens(body.refresh_token, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    return TokenResponse(
        access_token=access,
        refresh_token=new_refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        organization_id=user.organization_id,
        organization_name=user.organization.name if user.organization else None,
        created_at=user.created_at,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    body: LogoutRequest | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Revoke the current access token (and optionally the refresh token).
    Both tokens are added to the blacklist so they can't be reused.
    """
    # Blacklist the access token from the Authorization header
    try:
        access_payload = decode_token(credentials.credentials)
        access_jti = access_payload.get("jti")
        if access_jti:
            expires_at = datetime.fromtimestamp(access_payload["exp"], tz=timezone.utc)
            await blacklist_token(access_jti, "access", user.id, expires_at, db)
    except JWTError:
        pass  # Token was already validated by get_current_user

    # Optionally blacklist the refresh token too
    if body and body.refresh_token:
        try:
            refresh_payload = decode_token(body.refresh_token)
            # Verify the refresh token belongs to this user
            if refresh_payload.get("sub") == str(user.id) and refresh_payload.get("type") == "refresh":
                refresh_jti = refresh_payload.get("jti")
                if refresh_jti:
                    expires_at = datetime.fromtimestamp(refresh_payload["exp"], tz=timezone.utc)
                    await blacklist_token(refresh_jti, "refresh", user.id, expires_at, db)
        except JWTError:
            pass  # Expired/invalid refresh token — nothing to blacklist

    return MessageResponse(message="Sesion cerrada exitosamente")
