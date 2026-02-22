"""SSO handlers for SAML and OIDC enterprise authentication.

Placeholder/mock implementations structured so real libraries
(python3-saml, authlib) can be plugged in later.
"""
from __future__ import annotations

import base64
import json
import logging
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth_service import create_access_token, create_refresh_token, generate_did_web
from src.config import settings
from src.models import (
    Entity,
    EntityType,
    OrganizationMembership,
    OrgRole,
)

logger = logging.getLogger(__name__)


class SAMLHandler:
    """SAML 2.0 Service Provider handler.

    This is a mock implementation. In production, replace the callback
    parsing with python3-saml or similar.
    """

    def initiate_login(self, org_id: uuid.UUID, sso_config: dict) -> dict:
        """Generate a SAML AuthnRequest redirect URL.

        Returns dict with redirect_url and request_id.
        """
        idp_sso_url = sso_config.get("idp_sso_url", "https://idp.example.com/sso")
        request_id = f"_ag_{secrets.token_hex(16)}"
        # In production, this would be a real SAML AuthnRequest XML
        relay_state = str(org_id)
        redirect_url = (
            f"{idp_sso_url}?SAMLRequest={request_id}"
            f"&RelayState={relay_state}"
        )
        return {
            "redirect_url": redirect_url,
            "request_id": request_id,
        }

    def parse_callback(self, saml_response: str, sso_config: dict) -> dict | None:
        """Parse and validate a SAML assertion.

        In production, this would use python3-saml to validate the XML
        signature against the IdP certificate. For now, we accept a
        base64-encoded JSON mock assertion.

        Expected mock assertion format (base64-encoded JSON):
        {
            "name_id": "user@company.com",
            "attributes": {
                "email": "user@company.com",
                "display_name": "User Name"
            },
            "session_index": "..."
        }
        """
        logger.warning(
            "SECURITY: Using mock SAML assertion parser. "
            "Replace with python3-saml before production deployment."
        )
        try:
            decoded = base64.b64decode(saml_response).decode("utf-8")
            assertion = json.loads(decoded)
        except Exception:
            logger.warning("Failed to decode SAML assertion")
            return None

        name_id = assertion.get("name_id")
        if not name_id:
            logger.warning("SAML assertion missing name_id")
            return None

        attributes = assertion.get("attributes", {})
        return {
            "name_id": name_id,
            "email": attributes.get("email", name_id),
            "display_name": attributes.get("display_name", name_id.split("@")[0]),
            "session_index": assertion.get("session_index", ""),
        }

    def generate_metadata(self, org_id: uuid.UUID) -> str:
        """Generate SP metadata XML for IdP configuration.

        Returns an XML string with entity descriptor, ACS URL, etc.
        """
        entity_id = settings.sso_saml_entity_id
        callback_url = f"{settings.sso_callback_base_url}/api/v1/sso/saml/callback"
        return (
            '<?xml version="1.0"?>\n'
            '<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"'
            f' entityID="{entity_id}">\n'
            '  <md:SPSSODescriptor'
            ' protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">\n'
            '    <md:AssertionConsumerService'
            ' Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"'
            f' Location="{callback_url}"'
            ' index="0" isDefault="true"/>\n'
            '  </md:SPSSODescriptor>\n'
            '</md:EntityDescriptor>\n'
        )


class OIDCHandler:
    """OpenID Connect Relying Party handler.

    This is a mock implementation. In production, replace with authlib
    or another OIDC library.
    """

    def initiate_login(self, org_id: uuid.UUID, sso_config: dict) -> dict:
        """Generate an OIDC authorization URL.

        Returns dict with redirect_url, state, and nonce.
        """
        authorization_endpoint = sso_config.get(
            "authorization_endpoint",
            "https://idp.example.com/authorize",
        )
        client_id = sso_config.get("client_id", "agentgraph")
        redirect_uri = f"{settings.sso_callback_base_url}/api/v1/sso/oidc/callback"
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)

        redirect_url = (
            f"{authorization_endpoint}"
            f"?response_type=code"
            f"&client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&scope=openid+email+profile"
            f"&state={state}"
            f"&nonce={nonce}"
        )
        return {
            "redirect_url": redirect_url,
            "state": state,
            "nonce": nonce,
        }

    def exchange_code(self, code: str, sso_config: dict) -> dict | None:
        """Exchange an authorization code for user info.

        In production, this would call the token endpoint and then the
        userinfo endpoint. For now, we treat the code as a base64-encoded
        JSON mock token response.

        Expected mock code format (base64-encoded JSON):
        {
            "sub": "unique-user-id",
            "email": "user@company.com",
            "name": "User Name"
        }
        """
        logger.warning(
            "SECURITY: Using mock OIDC code exchange. "
            "Replace with authlib before production deployment."
        )
        try:
            decoded = base64.b64decode(code).decode("utf-8")
            userinfo = json.loads(decoded)
        except Exception:
            logger.warning("Failed to decode OIDC code")
            return None

        sub = userinfo.get("sub")
        if not sub:
            logger.warning("OIDC response missing sub claim")
            return None

        return {
            "sub": sub,
            "email": userinfo.get("email", ""),
            "display_name": userinfo.get("name", sub),
        }


async def find_or_create_sso_entity(
    db: AsyncSession,
    org_id: uuid.UUID,
    provider: str,
    provider_user_id: str,
    email: str,
    display_name: str,
) -> Entity:
    """Find an existing entity by SSO provider ID, or create a new one.

    The sso_provider_id is formatted as "{provider}:{provider_user_id}"
    to ensure uniqueness across providers.
    """
    sso_id = f"{provider}:{provider_user_id}"

    # Try to find by sso_provider_id first
    result = await db.execute(
        select(Entity).where(Entity.sso_provider_id == sso_id)
    )
    entity = result.scalar_one_or_none()
    if entity is not None:
        return entity

    # Try to find by email
    if email:
        result = await db.execute(
            select(Entity).where(Entity.email == email)
        )
        entity = result.scalar_one_or_none()
        if entity is not None:
            # Only link if email was already verified on this account,
            # to prevent SSO account takeover of unverified accounts
            if not entity.email_verified:
                logger.warning(
                    "SSO login attempted to link to unverified email account %s",
                    email,
                )
                raise ValueError("Cannot link SSO to unverified email account")
            # Link existing entity to SSO
            entity.sso_provider_id = sso_id
            await db.flush()
            await db.refresh(entity)
            return entity

    # Create a new entity
    entity_id = uuid.uuid4()
    entity = Entity(
        id=entity_id,
        type=EntityType.HUMAN,
        email=email or None,
        display_name=display_name,
        did_web=generate_did_web(entity_id),
        sso_provider_id=sso_id,
        organization_id=org_id,
        email_verified=True,  # Trust SSO provider's email verification
    )
    db.add(entity)
    await db.flush()

    # Add as member of the org if not already
    existing_membership = await db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.entity_id == entity.id,
        )
    )
    if existing_membership is None:
        membership = OrganizationMembership(
            organization_id=org_id,
            entity_id=entity.id,
            role=OrgRole.MEMBER,
        )
        db.add(membership)
        await db.flush()

    await db.refresh(entity)
    return entity


def create_sso_tokens(entity: Entity) -> dict:
    """Create JWT access + refresh tokens for an SSO-authenticated entity."""
    access = create_access_token(entity.id, entity.type.value)
    refresh = create_refresh_token(entity.id)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "entity_id": str(entity.id),
    }
