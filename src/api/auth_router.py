from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth_service import (
    authenticate_human,
    create_access_token,
    create_refresh_token,
    create_verification_token,
    decode_token,
    get_entity_by_email,
    get_entity_by_id,
    register_human,
    verify_email_token,
)
from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_auth
from src.api.schemas import (
    EntityResponse,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from src.audit import log_action
from src.config import settings
from src.database import get_db
from src.models import Entity

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_auth)],
)
async def register(
    body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    existing = await get_entity_by_email(db, body.email)
    if existing is not None:
        # Don't reveal whether email exists — same message either way
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registration failed",
        )

    entity = await register_human(db, body.email, body.password, body.display_name)
    verification_token = await create_verification_token(db, entity.id)

    await log_action(
        db,
        action="auth.register",
        entity_id=entity.id,
        ip_address=request.client.host if request.client else None,
    )

    return MessageResponse(
        message=f"Registration successful. Verification token: {verification_token}",
    )


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit_auth)])
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    entity = await authenticate_human(db, body.email, body.password)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    await log_action(
        db,
        action="auth.login",
        entity_id=entity.id,
        ip_address=request.client.host if request.client else None,
    )

    access_token = create_access_token(entity.id, entity.type.value)
    refresh_token = create_refresh_token(entity.id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("kind") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    entity = await get_entity_by_id(db, payload["sub"])
    if entity is None or not entity.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    access_token = create_access_token(entity.id, entity.type.value)
    refresh_token = create_refresh_token(entity.id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=EntityResponse)
async def get_me(current_entity: Entity = Depends(get_current_entity)):
    return current_entity


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    """Verify email address using the token from registration."""
    entity = await verify_email_token(db, token)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )
    return MessageResponse(message="Email verified successfully")


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit_auth)],
)
async def resend_verification(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Resend email verification token."""
    if current_entity.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already verified",
        )

    token = await create_verification_token(db, current_entity.id)
    return MessageResponse(
        message=f"Verification token: {token}",
    )
