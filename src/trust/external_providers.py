"""External trust provider integration — consume signed attestations from WG partners.

Queries external providers (RNWY, MoltBridge, AgentID, etc.) for signed
trust attestations and incorporates them into AgentGraph's composite score.

Each provider publishes JWKS at /.well-known/jwks.json and returns
signed JWS attestations. We verify signatures before incorporating data.

This is the aggregation layer — we consume multiple providers' signals
and produce a single composite trust score with enforcement decisions.
"""
from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass, field

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

logger = logging.getLogger(__name__)

# In-memory JWKS cache: provider_id -> (jwks_dict, fetch_timestamp)
_jwks_cache: dict[str, tuple[dict, float]] = {}
_JWKS_TTL = 3600  # 1 hour

# Provider registry — known trust attestation providers
PROVIDERS: list[dict] = [
    {
        "id": "rnwy",
        "name": "RNWY",
        "type": "behavioral_trust",
        "endpoint": "https://rnwy.com/api/trust-check",
        "jwks": "https://rnwy.com/.well-known/jwks.json",
        "description": "Behavioral trust scoring across ERC-8004 agents",
        "params": {"chain": "base"},  # default chain
    },
    {
        "id": "moltbridge",
        "name": "MoltBridge",
        "type": "interaction_trust",
        "endpoint": "https://api.moltbridge.ai/api/v1/attestations",
        "jwks": "https://api.moltbridge.ai/.well-known/jwks.json",
        "description": "Interaction-based attestation graph",
    },
    {
        "id": "agentid",
        "name": "AgentID",
        "type": "identity_verification",
        "endpoint": "https://getagentid.dev/api/v1/agents/verify",
        "jwks": "https://getagentid.dev/.well-known/jwks.json",
        "description": "Agent identity verification and behavioral risk",
    },
]


def _b64url_decode(s: str) -> bytes:
    """Decode base64url without padding (RFC 7515 §2)."""
    s = s.replace("-", "+").replace("_", "/")
    # Add padding
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.b64decode(s)


async def _fetch_jwks(
    provider_id: str,
    jwks_url: str,
    timeout: float = 10.0,
) -> dict | None:
    """Fetch and cache a provider's JWKS.

    Checks Redis cache first (1hr TTL), then in-memory cache, then
    fetches from the provider's jwks_url.  Returns the JWKS dict or
    None on failure.
    """
    cache_key = f"jwks:{provider_id}"

    # 1. Try Redis cache
    try:
        from src import cache as ag_cache

        cached = await ag_cache.get(cache_key)
        if cached is not None:
            return cached
    except Exception:
        pass

    # 2. Try in-memory cache
    if provider_id in _jwks_cache:
        jwks_data, ts = _jwks_cache[provider_id]
        if time.monotonic() - ts < _JWKS_TTL:
            return jwks_data

    # 3. Fetch from provider
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(jwks_url)
            if resp.status_code != 200:
                logger.warning(
                    "Failed to fetch JWKS from %s: HTTP %d",
                    jwks_url,
                    resp.status_code,
                )
                return None
            jwks_data = resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch JWKS from %s: %s", jwks_url, exc)
        return None

    # Store in both caches
    _jwks_cache[provider_id] = (jwks_data, time.monotonic())
    try:
        from src import cache as ag_cache

        await ag_cache.set(cache_key, jwks_data, ttl=_JWKS_TTL)
    except Exception:
        pass

    return jwks_data


def _find_ed25519_key(jwks: dict, kid: str | None = None) -> Ed25519PublicKey | None:
    """Extract an Ed25519 public key from a JWKS dict.

    If *kid* is provided, looks for a matching key; otherwise returns
    the first Ed25519 key found.
    """
    keys = jwks.get("keys", [])
    for key in keys:
        if key.get("kty") != "OKP" or key.get("crv") != "Ed25519":
            continue
        if kid is not None and key.get("kid") != kid:
            continue
        x_bytes = _b64url_decode(key["x"])
        if len(x_bytes) != 32:
            continue
        return Ed25519PublicKey.from_public_bytes(x_bytes)
    return None


def _verify_jws(jws_compact: str, public_key: Ed25519PublicKey) -> bool:
    """Verify a compact JWS (header.payload.signature) with Ed25519.

    Returns True if the signature is valid, False otherwise.
    """
    parts = jws_compact.split(".")
    if len(parts) != 3:
        return False

    header_b64, payload_b64, sig_b64 = parts

    # Verify algorithm from header
    try:
        header = json.loads(_b64url_decode(header_b64))
    except Exception:
        return False

    if header.get("alg") not in ("EdDSA", "Ed25519"):
        logger.warning("Unsupported JWS algorithm: %s", header.get("alg"))
        return False

    # Signing input is "header.payload" (ASCII)
    signing_input = (header_b64 + "." + payload_b64).encode("ascii")
    signature = _b64url_decode(sig_b64)

    try:
        public_key.verify(signature, signing_input)
        return True
    except Exception:
        return False


async def verify_attestation_jws(
    provider: dict,
    raw_jws: str | None,
) -> bool:
    """Verify the JWS signature on an external attestation.

    Fetches the provider's JWKS, finds the matching Ed25519 key,
    and verifies the signature.  Returns True if verification
    succeeds, False otherwise (graceful degradation).
    """
    if not raw_jws:
        return False

    jwks_url = provider.get("jwks")
    if not jwks_url:
        logger.warning("No JWKS URL for provider %s", provider["id"])
        return False

    jwks = await _fetch_jwks(provider["id"], jwks_url)
    if jwks is None:
        return False

    # Extract kid from JWS header if present
    kid = None
    try:
        header_b64 = raw_jws.split(".")[0]
        header = json.loads(_b64url_decode(header_b64))
        kid = header.get("kid")
    except Exception:
        pass

    public_key = _find_ed25519_key(jwks, kid)
    if public_key is None:
        logger.warning(
            "No matching Ed25519 key in JWKS for provider %s (kid=%s)",
            provider["id"],
            kid,
        )
        return False

    if _verify_jws(raw_jws, public_key):
        logger.info("JWS signature verified for provider %s", provider["id"])
        return True
    else:
        logger.warning("JWS signature verification FAILED for provider %s", provider["id"])
        return False


@dataclass
class ExternalAttestation:
    """A trust attestation from an external provider."""

    provider_id: str
    provider_name: str
    attestation_type: str
    score: float | None = None  # 0.0-1.0 if the provider returns a score
    tier: str | None = None
    evidence: dict = field(default_factory=dict)
    verified: bool = False  # True if JWS signature verified
    raw_jws: str | None = None
    error: str | None = None


async def query_provider(
    provider: dict,
    identifier: str,
    timeout: float = 10.0,
) -> ExternalAttestation:
    """Query a single external provider for a trust attestation.

    Args:
        provider: Provider config from PROVIDERS list
        identifier: Entity identifier (repo URL, wallet, agent ID)
        timeout: Request timeout in seconds

    Returns:
        ExternalAttestation with the provider's response or error
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Build request based on provider
            if provider["id"] == "rnwy":
                # RNWY uses GET with chain + id params
                resp = await client.get(
                    provider["endpoint"],
                    params={
                        "chain": provider.get("params", {}).get("chain", "base"),
                        "id": identifier,
                    },
                )
            elif provider["id"] == "moltbridge":
                # MoltBridge — query attestation edges
                resp = await client.get(
                    f"{provider['endpoint']}/{identifier}",
                )
            elif provider["id"] == "agentid":
                # AgentID uses POST with agent_id
                resp = await client.post(
                    provider["endpoint"],
                    json={"agent_id": identifier},
                )
            else:
                resp = await client.get(
                    provider["endpoint"],
                    params={"id": identifier},
                )

            if resp.status_code != 200:
                return ExternalAttestation(
                    provider_id=provider["id"],
                    provider_name=provider["name"],
                    attestation_type=provider["type"],
                    error=f"HTTP {resp.status_code}",
                )

            data = resp.json()

            # Extract score based on provider format
            score = None
            tier = None
            if provider["id"] == "rnwy":
                # RNWY returns score + tier in signed payload
                signed = data.get("signed", data)
                score = signed.get("score")
                tier = signed.get("tier")
                if score is not None:
                    score = score / 100.0  # RNWY scores are 0-100
            elif provider["id"] == "agentid":
                tier = data.get("trust_level")
                if data.get("verified"):
                    score = 0.7  # Verified = baseline trust

            raw_jws = data.get("jws") or data.get("sig")
            verified = await verify_attestation_jws(provider, raw_jws)

            return ExternalAttestation(
                provider_id=provider["id"],
                provider_name=provider["name"],
                attestation_type=provider["type"],
                score=score,
                tier=tier,
                evidence=data,
                verified=verified,
                raw_jws=raw_jws,
            )

    except httpx.TimeoutException:
        return ExternalAttestation(
            provider_id=provider["id"],
            provider_name=provider["name"],
            attestation_type=provider["type"],
            error="timeout",
        )
    except Exception as e:
        return ExternalAttestation(
            provider_id=provider["id"],
            provider_name=provider["name"],
            attestation_type=provider["type"],
            error=str(e),
        )


async def resolve_provider_id(
    entity_id: str,
    provider_id: str,
) -> str | None:
    """Look up the provider-specific ID for an entity.

    Returns the provider's identifier (e.g. RNWY agent ID, MoltBridge DID)
    or None if no mapping exists.
    """
    try:
        from sqlalchemy import select

        from src.database import async_session
        from src.models import ProviderIdMapping

        async with async_session() as db:
            mapping = await db.scalar(
                select(ProviderIdMapping.provider_entity_id).where(
                    ProviderIdMapping.entity_id == entity_id,
                    ProviderIdMapping.provider == provider_id,
                )
            )
            return mapping
    except Exception:
        return None


async def query_all_providers(
    identifier: str,
    provider_ids: list[str] | None = None,
    entity_id: str | None = None,
) -> list[ExternalAttestation]:
    """Query multiple providers in parallel for trust attestations.

    Args:
        identifier: Entity identifier
        provider_ids: Optional list of specific providers to query.
                     If None, queries all registered providers.

    Returns:
        List of ExternalAttestations (including errors/timeouts)
    """
    import asyncio

    providers = PROVIDERS
    if provider_ids:
        providers = [p for p in PROVIDERS if p["id"] in provider_ids]

    tasks = [query_provider(p, identifier) for p in providers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    attestations = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning("Provider query failed: %s", r)
        elif isinstance(r, ExternalAttestation):
            attestations.append(r)

    return attestations


def aggregate_external_scores(
    attestations: list[ExternalAttestation],
) -> float:
    """Aggregate external provider scores into a single 0.0-1.0 signal.

    Crypto-verified attestations weight higher than unverified.
    Scores from multiple providers are averaged with verification weighting.
    """
    if not attestations:
        return 0.0

    total = 0.0
    weight_sum = 0.0

    for att in attestations:
        if att.score is not None and att.error is None:
            w = 1.0 if att.verified else 0.7  # Crypto-verified weighs more
            total += att.score * w
            weight_sum += w

    return total / weight_sum if weight_sum > 0 else 0.0
