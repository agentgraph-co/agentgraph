"""SSO endpoints — SAML and OIDC enterprise authentication."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.config import settings
from src.database import get_db
from src.enterprise.sso import (
    OIDCHandler,
    SAMLHandler,
    create_sso_tokens,
    find_or_create_sso_entity,
)
from src.models import (
    Entity,
    Organization,
    OrganizationMembership,
    OrgRole,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sso", tags=["sso"])

_saml_handler = SAMLHandler()
_oidc_handler = OIDCHandler()


# --- Schemas ---


class SAMLLoginRequest(BaseModel):
    org_id: uuid.UUID


class SAMLCallbackRequest(BaseModel):
    saml_response: str = Field(..., min_length=1)
    org_id: uuid.UUID


class OIDCCallbackParams(BaseModel):
    code: str = Field(..., min_length=1)
    state: str = Field(..., min_length=1)
    org_id: uuid.UUID


class SSOConfigUpdate(BaseModel):
    provider: str = Field(..., pattern="^(saml|oidc)$")
    enabled: bool = True
    # SAML fields
    idp_sso_url: str | None = None
    idp_entity_id: str | None = None
    idp_certificate: str | None = None
    # OIDC fields
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    client_id: str | None = None
    client_secret: str | None = None


# --- Helpers ---


async def _get_org_or_404(db: AsyncSession, org_id: uuid.UUID) -> Organization:
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


async def _check_org_admin(
    db: AsyncSession, org_id: uuid.UUID, entity_id: uuid.UUID,
) -> None:
    """Verify entity is an owner or admin of the org."""
    membership = await db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.entity_id == entity_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="Not a member of this organization")
    if membership.role not in (OrgRole.OWNER, OrgRole.ADMIN):
        raise HTTPException(status_code=403, detail="Insufficient role")


def _get_sso_config(org: Organization) -> dict:
    """Extract SSO config from organization settings."""
    org_settings = org.settings or {}
    return org_settings.get("sso", {})


def _require_sso_enabled() -> None:
    """Guard: reject all SSO requests when the feature is disabled."""
    if not settings.sso_enabled:
        raise HTTPException(
            status_code=503,
            detail="SSO is not enabled on this instance",
        )


# --- SAML Endpoints ---


@router.post("/saml/login")
async def saml_login(
    body: SAMLLoginRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_writes),
) -> dict:
    """Initiate SAML SSO login for an organization.

    Returns a redirect URL to the IdP for authentication.
    """
    _require_sso_enabled()
    org = await _get_org_or_404(db, body.org_id)
    sso_config = _get_sso_config(org)
    if sso_config.get("provider") != "saml" or not sso_config.get("enabled", False):
        raise HTTPException(status_code=400, detail="SAML SSO not configured for this organization")
    return _saml_handler.initiate_login(body.org_id, sso_config)


@router.post("/saml/callback")
async def saml_callback(
    body: SAMLCallbackRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_writes),
) -> dict:
    """SAML Assertion Consumer Service endpoint.

    Validates the SAML assertion and returns JWT tokens.
    """
    _require_sso_enabled()
    org = await _get_org_or_404(db, body.org_id)
    sso_config = _get_sso_config(org)
    if sso_config.get("provider") != "saml" or not sso_config.get("enabled", False):
        raise HTTPException(status_code=400, detail="SAML SSO not configured for this organization")

    parsed = _saml_handler.parse_callback(body.saml_response, sso_config)
    if parsed is None:
        raise HTTPException(status_code=401, detail="Invalid SAML assertion")

    try:
        entity = await find_or_create_sso_entity(
            db=db,
            org_id=body.org_id,
            provider="saml",
            provider_user_id=parsed["name_id"],
            email=parsed["email"],
            display_name=parsed["display_name"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return create_sso_tokens(entity)


@router.get("/saml/metadata/{org_id}", response_class=PlainTextResponse)
async def saml_metadata(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_reads),
) -> str:
    """Return SP metadata XML for the organization.

    Used by IdP administrators to configure the SAML integration.
    """
    _require_sso_enabled()
    await _get_org_or_404(db, org_id)
    return _saml_handler.generate_metadata(org_id)


# --- OIDC Endpoints ---


@router.get("/oidc/login/{org_id}")
async def oidc_login(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_reads),
) -> dict:
    """Initiate OIDC SSO login for an organization.

    Returns a redirect URL to the OIDC provider for authentication.
    """
    _require_sso_enabled()
    org = await _get_org_or_404(db, org_id)
    sso_config = _get_sso_config(org)
    if sso_config.get("provider") != "oidc" or not sso_config.get("enabled", False):
        raise HTTPException(status_code=400, detail="OIDC SSO not configured for this organization")
    result = _oidc_handler.initiate_login(org_id, sso_config)
    # Store state for validation in callback
    from src import cache
    await cache.set(f"oidc_state:{result['state']}", str(org_id), ttl=600)  # 10 min expiry
    return result


@router.get("/oidc/callback")
async def oidc_callback(
    code: str,
    state: str,
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_reads),
) -> dict:
    """OIDC callback endpoint.

    Exchanges the authorization code for user info and returns JWT tokens.
    """
    _require_sso_enabled()
    # Validate OIDC state to prevent CSRF
    from src import cache
    stored_org = await cache.get(f"oidc_state:{state}")
    if stored_org is None or stored_org != str(org_id):
        raise HTTPException(status_code=400, detail="Invalid or expired OIDC state")
    await cache.invalidate(f"oidc_state:{state}")  # One-time use

    org = await _get_org_or_404(db, org_id)
    sso_config = _get_sso_config(org)
    if sso_config.get("provider") != "oidc" or not sso_config.get("enabled", False):
        raise HTTPException(status_code=400, detail="OIDC SSO not configured for this organization")

    userinfo = _oidc_handler.exchange_code(code, sso_config)
    if userinfo is None:
        raise HTTPException(status_code=401, detail="Invalid OIDC authorization code")

    try:
        entity = await find_or_create_sso_entity(
            db=db,
            org_id=org_id,
            provider="oidc",
            provider_user_id=userinfo["sub"],
            email=userinfo["email"],
            display_name=userinfo["display_name"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return create_sso_tokens(entity)


# --- SSO Config CRUD (on /organizations prefix) ---

# These are registered under /sso but reference org_id in path.
# An alternative would be to add them to org_router, but the task
# spec places them here.


@router.get("/config/{org_id}")
async def get_sso_config(
    org_id: uuid.UUID,
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_reads),
) -> dict:
    """Get SSO configuration for an organization. Org admin only."""
    _require_sso_enabled()
    org = await _get_org_or_404(db, org_id)
    await _check_org_admin(db, org_id, entity.id)
    sso_config = _get_sso_config(org)
    # Redact sensitive fields
    safe_config = dict(sso_config)
    if "client_secret" in safe_config:
        safe_config["client_secret"] = "***"
    if "idp_certificate" in safe_config:
        safe_config["idp_certificate"] = "***"
    return {"org_id": str(org_id), "sso": safe_config}


@router.put("/config/{org_id}")
async def set_sso_config(
    org_id: uuid.UUID,
    body: SSOConfigUpdate,
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_writes),
) -> dict:
    """Set SSO configuration for an organization. Org admin only."""
    _require_sso_enabled()
    org = await _get_org_or_404(db, org_id)
    await _check_org_admin(db, org_id, entity.id)

    sso_data: dict = {
        "provider": body.provider,
        "enabled": body.enabled,
    }
    if body.provider == "saml":
        if body.idp_sso_url:
            sso_data["idp_sso_url"] = body.idp_sso_url
        if body.idp_entity_id:
            sso_data["idp_entity_id"] = body.idp_entity_id
        if body.idp_certificate:
            sso_data["idp_certificate"] = body.idp_certificate
    elif body.provider == "oidc":
        if body.authorization_endpoint:
            sso_data["authorization_endpoint"] = body.authorization_endpoint
        if body.token_endpoint:
            sso_data["token_endpoint"] = body.token_endpoint
        if body.client_id:
            sso_data["client_id"] = body.client_id
        if body.client_secret:
            sso_data["client_secret"] = body.client_secret

    org_settings = dict(org.settings or {})
    org_settings["sso"] = sso_data
    org.settings = org_settings
    await db.flush()
    await db.refresh(org)

    return {"org_id": str(org_id), "sso": sso_data}
