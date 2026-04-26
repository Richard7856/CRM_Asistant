"""Pydantic schemas for auth endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.auth.models import UserRole


# ─── Request schemas ───

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    org_name: str = Field(min_length=1, max_length=120, description="Organization name — created on first signup")

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Enforce NIST 800-63B basics — no special char requirement (security theater)."""
        if not any(c.isupper() for c in v):
            raise ValueError("La contrasena debe tener al menos una mayuscula")
        if not any(c.islower() for c in v):
            raise ValueError("La contrasena debe tener al menos una minuscula")
        if not any(c.isdigit() for c in v):
            raise ValueError("La contrasena debe tener al menos un numero")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None  # optionally blacklist the refresh token too


# ─── Response schemas ───

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class MessageResponse(BaseModel):
    message: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    organization_id: uuid.UUID
    organization_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
