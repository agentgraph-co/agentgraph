"""Configuration for ERC-8004 bridge — RPC endpoint + contract addresses.

The three ERC-8004 registry contracts went live on Ethereum mainnet
2026-01-29 per EIP-8004. Production deployment loads addresses from
env vars; tests use the mocked addresses from `ERC8004_TEST_ADDRESSES`.

TODO Day 2 of MVP: replace placeholder addresses with actual mainnet
deployment addresses from https://eips.ethereum.org/EIPS/eip-8004
once verified.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ERC8004Config:
    """Configuration for ERC-8004 bridge — RPC endpoint + contract addresses."""

    rpc_url: str
    identity_registry_address: str
    reputation_registry_address: str
    validation_registry_address: str
    chain_id: int = 1  # 1 = Ethereum mainnet; override for testnets
    request_timeout_seconds: int = 15
    freshness_ttl_seconds: int = 24 * 60 * 60  # 24h default TTL for attestations


# Real EIP-8004 mainnet deployment addresses, verified live via eth_getCode
# 2026-05-27 (Identity name()="AgentIdentity" symbol()="AGENT" getVersion()="2.0.0").
# Source: github.com/erc-8004/erc-8004-contracts (mainnet, chain_id=1).
# ERC-8004 went live on Ethereum mainnet 2026-01-29.
#
# NOTE: Validation Registry is NOT yet deployed on mainnet (testnets only) —
# left as placeholder zero until it ships. Identity + Reputation are live.
ERC8004_MAINNET_ADDRESSES = {
    "identity": "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
    "reputation": "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63",
    "validation": "0x0000000000000000000000000000000000000000",  # not on mainnet yet
}

# Back-compat alias (older imports referenced PLACEHOLDER); now points at real.
ERC8004_PLACEHOLDER_ADDRESSES = ERC8004_MAINNET_ADDRESSES

# Test addresses — use anvil/foundry mock chain in tests
ERC8004_TEST_ADDRESSES = {
    "identity": "0x" + "01" * 20,
    "reputation": "0x" + "02" * 20,
    "validation": "0x" + "03" * 20,
}


def load_config_from_env() -> ERC8004Config:
    """Build config from env vars.

    Required env vars:
    - ETH_RPC_URL — Ethereum mainnet RPC endpoint (Alchemy, Quicknode, etc.)
    - ERC8004_IDENTITY_ADDRESS
    - ERC8004_REPUTATION_ADDRESS
    - ERC8004_VALIDATION_ADDRESS

    Optional:
    - ETH_CHAIN_ID (default: 1)
    - ERC8004_REQUEST_TIMEOUT_SECONDS (default: 15)
    - ERC8004_FRESHNESS_TTL_SECONDS (default: 86400)
    """
    rpc_url = os.environ.get("ETH_RPC_URL")
    if not rpc_url:
        raise RuntimeError("ETH_RPC_URL env var not set")

    return ERC8004Config(
        rpc_url=rpc_url,
        identity_registry_address=os.environ.get(
            "ERC8004_IDENTITY_ADDRESS",
            ERC8004_PLACEHOLDER_ADDRESSES["identity"],
        ),
        reputation_registry_address=os.environ.get(
            "ERC8004_REPUTATION_ADDRESS",
            ERC8004_PLACEHOLDER_ADDRESSES["reputation"],
        ),
        validation_registry_address=os.environ.get(
            "ERC8004_VALIDATION_ADDRESS",
            ERC8004_PLACEHOLDER_ADDRESSES["validation"],
        ),
        chain_id=int(os.environ.get("ETH_CHAIN_ID", "1")),
        request_timeout_seconds=int(
            os.environ.get("ERC8004_REQUEST_TIMEOUT_SECONDS", "15"),
        ),
        freshness_ttl_seconds=int(
            os.environ.get("ERC8004_FRESHNESS_TTL_SECONDS", str(24 * 60 * 60)),
        ),
    )
