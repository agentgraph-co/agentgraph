"""Linked accounts API — external account linking and reputation sync."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity, get_db
from src.config import settings
from src.models import LinkedAccount

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/linked-accounts", tags=["linked-accounts"])


class ClaimRequest(BaseModel):
    provider: str
    username: str


# --- GitHub OAuth flow ---


def _github_state(entity_id: str) -> str:
    """Generate HMAC-signed state param to prevent CSRF."""
    raw = f"github:{entity_id}"
    sig = hmac.new(
        settings.jwt_secret.encode(), raw.encode(), hashlib.sha256
    ).hexdigest()[:32]
    return f"{entity_id}:{sig}"


def _verify_github_state(state: str) -> str | None:
    """Verify state param, return entity_id or None."""
    parts = state.split(":", 1)
    if len(parts) != 2:
        return None
    entity_id, sig = parts
    expected = _github_state(entity_id)
    if not hmac.compare_digest(state, expected):
        return None
    return entity_id


@router.get("/github/connect")
async def github_connect(
    request: Request,
    entity=Depends(get_current_entity),
):
    """Return GitHub OAuth consent URL (frontend navigates to it)."""
    if not settings.github_client_id:
        raise HTTPException(400, "GitHub OAuth not configured")

    from src.api.github_oauth import get_github_auth_url

    # Use the single registered callback URL (auth router) — the state
    # param carries "link:" prefix so the callback routes back to us.
    base = settings.base_url.rstrip("/")
    redirect_uri = f"{base}/api/v1/auth/github/callback"
    state = _github_state(str(entity.id))
    url = get_github_auth_url(redirect_uri, state, scope="read:user")
    return {"url": url}


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str = "",
    state: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Handle GitHub OAuth callback for account linking."""
    entity_id = _verify_github_state(state)
    if not entity_id:
        return RedirectResponse(
            f"{settings.base_url}/settings?linked=github&status=error&reason=invalid_state",
            status_code=302,
        )

    from src.api.github_oauth import exchange_github_code

    # Must match the redirect_uri used in the consent URL
    base = settings.base_url.rstrip("/")
    redirect_uri = f"{base}/api/v1/auth/github/callback"
    user_data = await exchange_github_code(code, redirect_uri)

    if not user_data:
        return RedirectResponse(
            f"{settings.base_url}/settings?linked=github&status=error&reason=exchange_failed",
            status_code=302,
        )

    from src.crypto import encrypt_token

    access_token = user_data.pop("_access_token", "")
    github_id = str(user_data.get("id", ""))
    github_login = user_data.get("login", "")

    # Upsert linked account
    existing = await db.scalar(
        select(LinkedAccount).where(
            LinkedAccount.entity_id == uuid.UUID(entity_id),
            LinkedAccount.provider == "github",
        )
    )

    if existing:
        existing.provider_user_id = github_id
        existing.provider_username = github_login
        existing.verification_status = "verified_oauth"
        existing.access_token = encrypt_token(access_token) if access_token else None
        existing.profile_data = user_data
        existing.last_synced_at = datetime.now(timezone.utc)
    else:
        la = LinkedAccount(
            id=uuid.uuid4(),
            entity_id=uuid.UUID(entity_id),
            provider="github",
            provider_user_id=github_id,
            provider_username=github_login,
            verification_status="verified_oauth",
            access_token=encrypt_token(access_token) if access_token else None,
            profile_data=user_data,
            last_synced_at=datetime.now(timezone.utc),
        )
        db.add(la)

    await db.flush()

    # Kick off background sync for reputation data
    linked = existing or la
    asyncio.ensure_future(_background_sync(linked.id, entity_id))

    return RedirectResponse(
        f"{settings.base_url}/settings?linked=github&status=success",
        status_code=302,
    )


async def _background_sync(linked_account_id: uuid.UUID, entity_id: str) -> None:
    """Background task to sync external reputation data."""
    try:
        from src.database import async_session
        from src.external_reputation import sync_provider_data

        async with async_session() as db:
            async with db.begin():
                la = await db.get(LinkedAccount, linked_account_id)
                if la:
                    await sync_provider_data(db, la)

        # Trigger trust recompute
        async with async_session() as db:
            async with db.begin():
                from src.trust.score import compute_trust_score

                await compute_trust_score(db, uuid.UUID(entity_id))
    except Exception:
        logger.exception("Background sync failed for %s", linked_account_id)


# --- Username claim flow ---


@router.post("/claim")
async def claim_account(
    body: ClaimRequest,
    entity=Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Claim an external account by username. Returns verification challenge."""
    provider = body.provider.lower()
    if provider not in ("github", "npm", "pypi", "huggingface"):
        raise HTTPException(400, f"Unsupported provider: {provider}")

    # Check for existing link
    existing = await db.scalar(
        select(LinkedAccount).where(
            LinkedAccount.entity_id == entity.id,
            LinkedAccount.provider == provider,
        )
    )
    if existing:
        raise HTTPException(409, f"{provider} account already linked")

    challenge_token = f"agentgraph-verify:{entity.id}"

    la = LinkedAccount(
        id=uuid.uuid4(),
        entity_id=entity.id,
        provider=provider,
        provider_user_id=body.username,
        provider_username=body.username,
        verification_status="unverified_claim",
    )
    db.add(la)
    await db.flush()

    # Pull public data immediately
    asyncio.ensure_future(_background_sync(la.id, str(entity.id)))

    return {
        "status": "claimed",
        "provider": provider,
        "username": body.username,
        "verification_challenge": challenge_token,
        "instructions": _verification_instructions(provider, challenge_token),
    }


def _verification_instructions(provider: str, token: str) -> str:
    """Return human-readable verification instructions."""
    verify_ep = f"POST /api/v1/linked-accounts/{provider}/verify"
    if provider == "github":
        return (
            f'Add "{token}" to your GitHub bio at github.com/settings/profile, '
            f"then call {verify_ep}."
        )
    if provider == "npm":
        return (
            f'Add "{token}" to your npm package description in package.json, '
            f"publish, then call {verify_ep}."
        )
    if provider == "pypi":
        return (
            f'Add "{token}" to your PyPI package summary or description, '
            f"publish a new release, then call {verify_ep}."
        )
    if provider == "huggingface":
        return (
            f'Add "{token}" to your model card README.md on HuggingFace, '
            f"then call {verify_ep}."
        )
    return f'Add "{token}" to your profile, then call {verify_ep}.'


@router.post("/{provider}/verify")
async def verify_account(
    provider: str,
    entity=Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Check if verification challenge was completed."""
    la = await db.scalar(
        select(LinkedAccount).where(
            LinkedAccount.entity_id == entity.id,
            LinkedAccount.provider == provider,
        )
    )
    if not la:
        raise HTTPException(404, f"No {provider} account linked")

    if la.verification_status in ("verified_oauth", "verified_challenge"):
        return {"status": "already_verified", "verification_status": la.verification_status}

    challenge_token = f"agentgraph-verify:{entity.id}"
    verified = False

    if provider == "github":
        verified = await _check_github_bio(la.provider_username, challenge_token)
    elif provider == "npm":
        verified = await _check_npm_description(la.provider_username, challenge_token)
    elif provider == "pypi":
        verified = await _check_pypi_description(la.provider_username, challenge_token)
    elif provider == "huggingface":
        verified = await _check_huggingface_card(la.provider_username, challenge_token)

    if verified:
        la.verification_status = "verified_challenge"
        await db.flush()

        # Recompute trust score
        asyncio.ensure_future(_background_sync(la.id, str(entity.id)))

        return {"status": "verified", "verification_status": "verified_challenge"}

    return {
        "status": "pending",
        "verification_status": la.verification_status,
        "message": (
            f"Challenge token not found. Add '{challenge_token}'"
            f" to your {provider} profile."
        ),
    }


async def _check_github_bio(username: str | None, token: str) -> bool:
    """Check if GitHub user bio contains the verification token."""
    if not username:
        return False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://api.github.com/users/{username}",
                headers={"Accept": "application/vnd.github+json"},
            )
            if resp.status_code == 200:
                bio = resp.json().get("bio", "") or ""
                return token in bio
    except Exception:
        logger.exception("GitHub bio check failed")
    return False


async def _check_npm_description(package_name: str | None, token: str) -> bool:
    """Check if npm package description contains the verification token."""
    if not package_name:
        return False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://registry.npmjs.org/{package_name}",
            )
            if resp.status_code == 200:
                desc = resp.json().get("description", "") or ""
                return token in desc
    except Exception:
        logger.exception("npm description check failed")
    return False


async def _check_pypi_description(package_name: str | None, token: str) -> bool:
    """Check if PyPI package description contains the verification token."""
    if not package_name:
        return False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://pypi.org/pypi/{package_name}/json",
            )
            if resp.status_code == 200:
                info = resp.json().get("info", {})
                summary = info.get("summary", "") or ""
                description = info.get("description", "") or ""
                return token in summary or token in description
    except Exception:
        logger.exception("PyPI description check failed")
    return False


async def _check_huggingface_card(model_id: str | None, token: str) -> bool:
    """Check if HuggingFace model card contains the verification token."""
    if not model_id:
        return False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://huggingface.co/api/models/{model_id}",
            )
            if resp.status_code == 200:
                data = resp.json()
                # Check model card content and description
                card_data = data.get("cardData", {}) or {}
                description = card_data.get("description", "") or ""
                # Also check README-style card text
                card_resp = await client.get(
                    f"https://huggingface.co/{model_id}/raw/main/README.md",
                )
                readme = card_resp.text if card_resp.status_code == 200 else ""
                return token in description or token in readme
    except Exception:
        logger.exception("HuggingFace card check failed")
    return False


# --- List / Delete / Sync ---


@router.get("")
async def list_linked_accounts(
    entity=Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """List current user's linked accounts (tokens excluded)."""
    result = await db.execute(
        select(LinkedAccount).where(LinkedAccount.entity_id == entity.id)
    )
    accounts = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "provider": a.provider,
            "provider_username": a.provider_username,
            "verification_status": a.verification_status,
            "reputation_score": a.reputation_score,
            "reputation_data": a.reputation_data,
            "last_synced_at": a.last_synced_at.isoformat() if a.last_synced_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in accounts
    ]


@router.delete("/{provider}")
async def unlink_account(
    provider: str,
    entity=Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Unlink an external account."""
    la = await db.scalar(
        select(LinkedAccount).where(
            LinkedAccount.entity_id == entity.id,
            LinkedAccount.provider == provider,
        )
    )
    if not la:
        raise HTTPException(404, f"No {provider} account linked")

    await db.delete(la)
    await db.flush()

    # Recompute trust score without external rep
    asyncio.ensure_future(_recompute_trust(str(entity.id)))

    return {"status": "unlinked", "provider": provider}


async def _recompute_trust(entity_id: str) -> None:
    """Recompute trust score after unlinking."""
    try:
        from src.database import async_session
        from src.trust.score import compute_trust_score

        async with async_session() as db:
            async with db.begin():
                await compute_trust_score(db, uuid.UUID(entity_id))
    except Exception:
        logger.exception("Trust recompute failed after unlink")


@router.post("/{provider}/sync")
async def sync_account(
    provider: str,
    entity=Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Manual re-sync trigger for a linked account."""
    la = await db.scalar(
        select(LinkedAccount).where(
            LinkedAccount.entity_id == entity.id,
            LinkedAccount.provider == provider,
        )
    )
    if not la:
        raise HTTPException(404, f"No {provider} account linked")

    from src.external_reputation import sync_provider_data

    await sync_provider_data(db, la)
    await db.flush()
    await db.refresh(la)

    return {
        "status": "synced",
        "provider": provider,
        "reputation_score": la.reputation_score,
        "last_synced_at": la.last_synced_at.isoformat() if la.last_synced_at else None,
    }
