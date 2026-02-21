from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth_service import (
    authenticate_human,
    blacklist_token,
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    create_verification_token,
    decode_token,
    get_entity_by_email,
    get_entity_by_id,
    hash_password,
    register_human,
    verify_email_token,
    verify_password_reset_token,
)
from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_auth, rate_limit_reads, rate_limit_writes
from src.api.schemas import (
    ChangeEmailRequest,
    EntityResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from src.audit import log_action
from src.config import settings
from src.database import get_db
from src.models import AnalyticsEvent, Entity

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
    session_id: str | None = Query(None, max_length=64),
):
    # Content filter on display_name
    from src.content_filter import check_content, sanitize_html

    filter_result = check_content(body.display_name)
    if not filter_result.is_clean:
        raise HTTPException(
            status_code=400,
            detail=f"Display name rejected: {', '.join(filter_result.flags)}",
        )
    body.display_name = sanitize_html(body.display_name)

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

    # Record conversion analytics event linking session to new entity
    if session_id:
        db.add(AnalyticsEvent(
            event_type="register_complete",
            session_id=session_id,
            page="/register",
            entity_id=entity.id,
            ip_address=request.client.host if request.client else None,
        ))
        await db.flush()

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


@router.post(
    "/refresh", response_model=TokenResponse,
    dependencies=[Depends(rate_limit_auth)],
)
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


@router.get(
    "/me", response_model=EntityResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_me(current_entity: Entity = Depends(get_current_entity)):
    return current_entity


@router.post(
    "/verify-email", response_model=MessageResponse,
    dependencies=[Depends(rate_limit_auth)],
)
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


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit_auth)],
)
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Request a password reset token.

    Always returns success to prevent email enumeration.
    In production, the token would be emailed rather than returned.
    """
    entity = await get_entity_by_email(db, body.email)
    if entity is None or not entity.is_active:
        # Don't reveal whether account exists
        return MessageResponse(
            message="If an account with that email exists, a reset token has been generated.",
        )

    token = await create_password_reset_token(db, entity.id)

    await log_action(
        db,
        action="auth.password_reset_requested",
        entity_id=entity.id,
        ip_address=request.client.host if request.client else None,
    )

    return MessageResponse(
        message=f"Password reset token: {token}",
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit_auth)],
)
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Reset password using a valid reset token."""
    entity = await verify_password_reset_token(db, body.token)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    entity.password_hash = hash_password(body.new_password)
    await db.flush()

    await log_action(
        db,
        action="auth.password_reset",
        entity_id=entity.id,
        ip_address=request.client.host if request.client else None,
    )

    return MessageResponse(message="Password reset successful. Please log in.")


@router.post(
    "/change-email",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit_auth)],
)
async def change_email(
    body: ChangeEmailRequest,
    request: Request,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Change email address. Requires current password. Sends verification."""
    # Verify current password
    authed = await authenticate_human(
        db, current_entity.email, body.current_password,
    )
    if authed is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid current password",
        )

    # Check new email not taken
    existing = await get_entity_by_email(db, body.new_email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already in use",
        )

    # Update email and reset verification
    current_entity.email = body.new_email
    current_entity.email_verified = False
    await db.flush()

    # Create verification token for new email
    verification_token = await create_verification_token(db, current_entity.id)

    await log_action(
        db,
        action="auth.email_changed",
        entity_id=current_entity.id,
        details={"new_email": body.new_email},
        ip_address=request.client.host if request.client else None,
    )

    return MessageResponse(
        message=f"Email changed. Verification token: {verification_token}",
    )


@router.post(
    "/logout", response_model=MessageResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def logout(
    request: Request,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Logout and revoke the current access token."""
    from src.api.auth_service import decode_token as _decode

    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "")
    payload = _decode(token)

    if payload and payload.get("jti"):
        from datetime import datetime, timezone

        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        await blacklist_token(db, payload["jti"], current_entity.id, exp)

    await log_action(
        db,
        action="auth.logout",
        entity_id=current_entity.id,
        ip_address=request.client.host if request.client else None,
    )

    return MessageResponse(message="Logged out successfully")
