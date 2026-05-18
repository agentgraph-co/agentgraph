"""Pydantic schemas for ERC-8004 registry entries and normalized attestations.

ERC-8004 registries (per EIP-8004):
- Identity Registry: links agent DID → on-chain address + identity metadata
- Reputation Registry: stores feedback entries (numeric score + signed payload)
- Validation Registry: stores verified-work attestations (proof of completed task)

Each entry carries a CTEF-formatted payload in its `data` field, signed
Ed25519 by the attestation issuer (which may differ from the entry submitter).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ERC8004Registry(str, Enum):
    """The three ERC-8004 on-chain registries."""

    IDENTITY = "identity"
    REPUTATION = "reputation"
    VALIDATION = "validation"


class ERC8004Entry(BaseModel):
    """Raw entry as returned from an ERC-8004 registry contract call.

    The `data` field carries an opaque payload — for AgentGraph integration,
    that payload is expected to be a CTEF-formatted attestation (JCS-canonical
    JSON with Ed25519 signature). Other consumers may use different payload
    formats; ERC-8004 itself does not constrain the payload shape.
    """

    registry: ERC8004Registry
    entry_id: int = Field(ge=0, description="Sequential entry index in the registry")
    submitter: str = Field(
        pattern=r"^0x[0-9a-fA-F]{40}$",
        description="Ethereum address that submitted the entry",
    )
    subject_did: Optional[str] = Field(
        default=None,
        description="DID this entry attests about (e.g. did:web:agent.example.com)",
    )
    data: bytes = Field(description="Raw entry payload bytes (typically CTEF JSON)")
    block_number: int = Field(ge=0)
    block_timestamp: datetime
    tx_hash: str = Field(pattern=r"^0x[0-9a-fA-F]{64}$")


class NormalizedAttestation(BaseModel):
    """ERC-8004 entry normalized into AgentGraph composite-trust-score input.

    Produced by `attestation_normalizer.normalize()` after:
    1. Reading the entry from the on-chain registry
    2. Parsing the `data` field as CTEF v0.3.1 envelope
    3. Verifying the CTEF Ed25519 signature (substrate-side)
    4. Verifying the entry submitter's Ethereum signature (registry-side)
    """

    source_urn: str = Field(description="urn:erc8004:{registry}:<entry_id> originating URN")
    claim_type: str = Field(description="CTEF claim_type — one of {identity, transport, authority, continuity}")
    claim_subtype: Optional[str] = Field(default=None)
    subject_did: str = Field(description="The DID this attestation is about")
    provider_did: str = Field(description="The DID of the attestation issuer (CTEF provider)")
    payload: dict[str, Any] = Field(description="Parsed CTEF envelope payload")
    signature_verified: bool = Field(
        description="True iff CTEF Ed25519 signature verified against provider's published JWKS",
    )
    registry_signature_verified: bool = Field(
        description="True iff ERC-8004 entry submitter signature verified on-chain",
    )
    issued_at: datetime
    expires_at: Optional[datetime] = Field(default=None)
    freshness_ttl_remaining_seconds: Optional[int] = Field(default=None)

    @property
    def is_admissible(self) -> bool:
        """Both signature layers must verify and attestation must not be expired."""
        return (
            self.signature_verified
            and self.registry_signature_verified
            and (self.expires_at is None or self.expires_at > datetime.utcnow())
        )
