"""Read agent records from the real ERC-8004 Identity Registry (mainnet v2.0.0).

CRITICAL MODEL CORRECTION (2026-05-27): the original `registry_reader.py`
(Day 2) was built against an *inferred* ABI (`getEntry(uint256) -> (submitter,
subjectDid, data, timestamp, exists)`) that assumed CTEF attestation bytes were
embedded directly in the registry. The REAL deployed contract is different:

The Identity Registry is an **ERC-721 contract** ("AgentIdentity" / "AGENT",
getVersion 2.0.0). An agent is an NFT:
  - agent_id        = tokenId (uint256)
  - owner           = ownerOf(tokenId)
  - agent_wallet    = getAgentWallet(tokenId)  -- the agent's operating address
  - registration    = tokenURI(tokenId)        -- URI to an OFF-CHAIN registration file
  - metadata        = getMetadata(tokenId, key) -- arbitrary on-chain key/value (bytes)

There is NO embedded CTEF envelope in the registry. The registration file the
tokenURI points at is where an agent's DID / capabilities / (optionally) a CTEF
attestation live. So the bridge's consumption model is:

  registry (pointer layer)  ->  tokenURI  ->  off-chain registration file
       ->  CTEF attestation (if present)

This module reads the on-chain pointer layer into an `AgentRecord`. Resolving
the registration file + extracting any CTEF attestation is the
attestation_normalizer's job (Day-3 normalizer needs rework for this model —
it currently expects embedded bytes; see ACTIVATION_NOTES.md).

ABI: abi/erc8004_v2/IdentityRegistry.json (pulled from
github.com/erc-8004/erc-8004-contracts, validated against the live mainnet
contract — name/symbol/getVersion match).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from agentgraph_bridge_erc8004.config import ERC8004Config

if TYPE_CHECKING:
    from web3 import Web3
    from web3.contract import Contract

_ABI_DIR = Path(__file__).parent / "abi" / "erc8004_v2"


class IdentityReadError(RuntimeError):
    """Raised when an Identity Registry read fails (RPC down, token not minted, revert)."""


@dataclass(frozen=True)
class AgentRecord:
    """An agent's on-chain identity record from the ERC-8004 Identity Registry.

    This is the pointer layer. `registration_uri` (tokenURI) points to the
    off-chain registration file that carries the agent's DID, capabilities,
    and any CTEF attestation — resolving that file is a separate step.
    """

    agent_id: int                  # ERC-721 tokenId
    owner: str                     # ownerOf(tokenId)
    agent_wallet: str | None    # getAgentWallet(tokenId) — agent's operating address
    registration_uri: str          # tokenURI(tokenId) — off-chain registration file
    source_urn: str                # urn:erc8004:identity:<agent_id>


def _load_abi(name: str) -> list[dict]:
    with open(_ABI_DIR / f"{name}.json") as f:
        return json.load(f)


class IdentityRegistryReader:
    """Read-only client for the real ERC-8004 Identity Registry (ERC-721 model).

    Construct with a configured Web3 + ERC8004Config. Web3 is injected so tests
    pass a MagicMock; production passes Web3(HTTPProvider(rpc_url)).
    """

    def __init__(self, web3: Web3, config: ERC8004Config) -> None:
        self._w3 = web3
        self._cfg = config
        from web3 import Web3  # local import — only when reader is used

        self._contract: Contract = web3.eth.contract(
            address=Web3.to_checksum_address(config.identity_registry_address),
            abi=_load_abi("IdentityRegistry"),
        )

    def read_agent(self, agent_id: int) -> AgentRecord:
        """Read one agent's on-chain identity record by tokenId.

        Raises IdentityReadError if the token isn't minted or the RPC fails.
        ERC-721 ownerOf reverts for non-existent tokens — we surface that as
        a clean "agent not found".
        """
        if agent_id < 0:
            raise IdentityReadError(f"agent_id must be non-negative, got {agent_id}")

        urn = f"urn:erc8004:identity:{agent_id}"
        c = self._contract.functions
        try:
            owner = c.ownerOf(agent_id).call()
        except Exception as exc:
            raise IdentityReadError(
                f"{urn}: ownerOf reverted (token likely not minted): "
                f"{type(exc).__name__}: {exc}",
            ) from exc

        # tokenURI + agentWallet are best-effort; a minted token always has a
        # URI, but agentWallet may be unset (returns zero address).
        try:
            registration_uri = c.tokenURI(agent_id).call()
        except Exception as exc:
            raise IdentityReadError(f"{urn}: tokenURI failed: {exc}") from exc

        agent_wallet: str | None = None
        try:
            w = c.getAgentWallet(agent_id).call()
            if w and int(w, 16) != 0:
                agent_wallet = w
        except Exception:
            agent_wallet = None  # unset wallet is non-fatal

        return AgentRecord(
            agent_id=agent_id,
            owner=owner,
            agent_wallet=agent_wallet,
            registration_uri=registration_uri,
            source_urn=urn,
        )

    def get_metadata(self, agent_id: int, key: str) -> bytes | None:
        """Read an arbitrary on-chain metadata value for an agent (getMetadata).

        Returns None if the key is unset. This is where an agent MAY publish a
        CTEF attestation reference or DID directly on-chain (vs in the off-chain
        registration file).
        """
        try:
            raw = self._contract.functions.getMetadata(agent_id, key).call()
            return bytes(raw) if raw else None
        except Exception:
            return None

    def is_reachable(self) -> bool:
        """Health check: contract responds + reports the expected name."""
        try:
            return self._contract.functions.name().call() == "AgentIdentity"
        except Exception:
            return False


def make_identity_reader_from_env() -> IdentityRegistryReader:
    """Build a ready-to-use Identity Registry reader from env vars."""
    from web3 import HTTPProvider, Web3

    from agentgraph_bridge_erc8004.config import load_config_from_env

    cfg = load_config_from_env()
    w3 = Web3(HTTPProvider(cfg.rpc_url, request_kwargs={"timeout": cfg.request_timeout_seconds}))
    return IdentityRegistryReader(w3, cfg)


__all__ = [
    "AgentRecord",
    "IdentityReadError",
    "IdentityRegistryReader",
    "make_identity_reader_from_env",
]
