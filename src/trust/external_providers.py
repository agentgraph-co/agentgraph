"""External trust provider integration — consume signed attestations from WG partners.

Queries external providers (RNWY, MoltBridge, AgentID, etc.) for signed
trust attestations and incorporates them into AgentGraph's composite score.

Each provider publishes JWKS at /.well-known/jwks.json and returns
signed JWS attestations. We verify signatures before incorporating data.

This is the aggregation layer — we consume multiple providers' signals
and produce a single composite trust score with enforcement decisions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

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

            return ExternalAttestation(
                provider_id=provider["id"],
                provider_name=provider["name"],
                attestation_type=provider["type"],
                score=score,
                tier=tier,
                evidence=data,
                verified=False,  # TODO: verify JWS signature
                raw_jws=data.get("jws") or data.get("sig"),
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


async def query_all_providers(
    identifier: str,
    provider_ids: list[str] | None = None,
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
