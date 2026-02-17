from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

# --- Auth request/response schemas ---


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=100)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class MessageResponse(BaseModel):
    message: str


# --- Entity response schemas ---


class EntityResponse(BaseModel):
    id: uuid.UUID
    type: str
    email: str | None = None
    display_name: str
    bio_markdown: str
    did_web: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
