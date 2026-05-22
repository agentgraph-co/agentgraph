"""ERC-8004 bridge — production code for AgentGraph composite trust score
to consume ERC-8004 registry entries as primitives via URN-shaped references.

ERC-8004 ("Trustless Agents", Ethereum mainnet 2026-01-29) ships three on-chain
registries: Identity, Reputation, Validation. This bridge reads entries from
those registries, normalizes the CTEF-formatted payload, verifies both the
Ethereum-layer signature (registry-side) and the Ed25519 signature on the
embedded CTEF attestation, and feeds the normalized attestation into
AgentGraph's composite trust score `EXTERNAL: 0.35` weight.

Architecture (per docs/standards/v0.3.2-layering-figure.md):
- ERC-8004 is a Layer 2 primitive over an alternate execution substrate
  (Ethereum / L2), not a Layer 1' addition
- CTEF supplies the embedded claim_type attestation that travels inside
  the registry entry's `data` field
- Both ERC-8004 entry signature and CTEF Ed25519 signature must verify
  before the attestation is admitted to the composite score
- URN scheme: `urn:erc8004:{identity,reputation,validation}:<entry_id>`

MVP scope (Day 1 of 3-day plan per docs/internal/monday-may18-scope.md):
- models.py + urn_resolver.py + config.py shipped
- registry_reader.py + attestation_normalizer.py + score_ingest.py are skeleton

Day 2-3: wire web3.py against mainnet RPC, add per-vector mainnet snapshot
fixtures, integrate normalized attestations into src/trust/score.py.
"""
from __future__ import annotations

from agentgraph_bridge_erc8004.attestation_normalizer import (
    NormalizationError,
    normalize,
)
from agentgraph_bridge_erc8004.models import (
    ERC8004Entry,
    ERC8004Registry,
    NormalizedAttestation,
)
from agentgraph_bridge_erc8004.registry_reader import (
    ERC8004RegistryReader,
    RegistryReadError,
    make_reader_from_env,
)
from agentgraph_bridge_erc8004.score_ingest import (
    blend_with_community_signals,
    score,
    score_breakdown,
)
from agentgraph_bridge_erc8004.urn_resolver import (
    ParsedURN,
    URNParseError,
    parse_erc8004_urn,
)

__all__ = [
    "ERC8004Entry",
    "ERC8004Registry",
    "ERC8004RegistryReader",
    "NormalizationError",
    "NormalizedAttestation",
    "ParsedURN",
    "RegistryReadError",
    "URNParseError",
    "blend_with_community_signals",
    "make_reader_from_env",
    "normalize",
    "parse_erc8004_urn",
    "score",
    "score_breakdown",
]

__version__ = "0.2.0"  # Day 3 ships normalizer + score_ingest
