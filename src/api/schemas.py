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


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


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


# --- Agent request/response schemas ---


class CreateAgentRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=100)
    capabilities: list[str] = Field(default_factory=list, max_length=50)
    autonomy_level: int | None = Field(None, ge=1, le=5)
    bio_markdown: str = Field("", max_length=5000)


class UpdateAgentRequest(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=100)
    capabilities: list[str] | None = Field(None, max_length=50)
    autonomy_level: int | None = Field(None, ge=1, le=5)
    bio_markdown: str | None = Field(None, max_length=5000)


class AgentResponse(BaseModel):
    id: uuid.UUID
    type: str
    display_name: str
    bio_markdown: str
    did_web: str
    capabilities: list[str]
    autonomy_level: int | None
    operator_id: uuid.UUID | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RegisterAgentRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=100)
    capabilities: list[str] = Field(default_factory=list, max_length=50)
    autonomy_level: int | None = Field(None, ge=1, le=5)
    bio_markdown: str = Field("", max_length=5000)
    operator_email: str | None = Field(
        None,
        description="Optional operator email to link. Must be a registered human.",
    )


class AgentCreatedResponse(BaseModel):
    agent: AgentResponse
    api_key: str  # plaintext, shown once


class ApiKeyRotatedResponse(BaseModel):
    api_key: str  # plaintext, shown once
    message: str
