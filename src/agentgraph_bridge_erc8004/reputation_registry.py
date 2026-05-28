"""Read feedback/reputation signals from the real ERC-8004 Reputation Registry.

Companion to identity_registry.py. Where the Identity Registry answers "who is
this agent" (ERC-721 token + off-chain registration file), the Reputation
Registry answers "what feedback has this agent accumulated" — the numeric
trust signal AgentGraph's composite score actually wants.

Real mainnet interface (validated against the deployed contract):
  - getSummary(agentId, clients[], tag1, tag2) -> (count uint64, aggregate int128, recent uint8)
  - readAllFeedback(agentId, clients[], tag1, tag2, includeRevoked)
       -> (clients[], indices[], scores int128[], ...)
  - getClients(agentId) -> address[]   (who has left feedback)
  - getLastIndex(agentId, client) -> uint64

ABI: abi/erc8004_v2/ReputationRegistry.json (from erc-8004-contracts).
Address verified live: 0x8004BAa17C55a88189AE136b182e5fdA19dE9b63.

NOTE: feedback scores are signed int128 (the spec allows negative feedback).
The mapping to AgentGraph's 0-1 external-reputation slot is handled in
score_ingest (a future step in the activation); this module is the read layer.
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


class ReputationReadError(RuntimeError):
    """Raised when a Reputation Registry read fails."""


@dataclass(frozen=True)
class ReputationSummary:
    """Aggregate feedback for an agent from the Reputation Registry.

    `aggregate_score` is the signed int128 sum/aggregate per the contract;
    `feedback_count` is how many feedback entries are aggregated. The
    normalization to a 0-1 trust contribution happens downstream in
    score_ingest, not here.
    """

    agent_id: int
    feedback_count: int        # number of feedback entries in the summary
    aggregate_score: int       # signed int128 aggregate (may be negative)
    recent_indicator: int      # uint8 recency/decay indicator per contract
    distinct_clients: int      # how many distinct addresses left feedback
    source_urn: str            # urn:erc8004:reputation:<agent_id>


def _load_abi(name: str) -> list[dict]:
    with open(_ABI_DIR / f"{name}.json") as f:
        return json.load(f)


class ReputationRegistryReader:
    """Read-only client for the real ERC-8004 Reputation Registry.

    Web3 injected for test-friendliness, same pattern as IdentityRegistryReader.
    """

    def __init__(self, web3: "Web3", config: ERC8004Config) -> None:
        self._w3 = web3
        self._cfg = config
        from web3 import Web3

        self._contract: "Contract" = web3.eth.contract(
            address=Web3.to_checksum_address(config.reputation_registry_address),
            abi=_load_abi("ReputationRegistry"),
        )

    def read_summary(self, agent_id: int) -> ReputationSummary:
        """Read aggregate feedback for an agent.

        Uses getClients to enumerate feedback-leavers, then getSummary across
        all of them with empty tag filters (tag1="", tag2="" = no filter).
        Returns a zero-summary (no feedback) rather than raising when an agent
        simply has no feedback yet — that's a valid state, not an error.
        """
        if agent_id < 0:
            raise ReputationReadError(f"agent_id must be non-negative, got {agent_id}")

        urn = f"urn:erc8004:reputation:{agent_id}"
        c = self._contract.functions

        try:
            clients = c.getClients(agent_id).call()
        except Exception as exc:
            raise ReputationReadError(
                f"{urn}: getClients failed: {type(exc).__name__}: {exc}",
            ) from exc

        if not clients:
            return ReputationSummary(
                agent_id=agent_id,
                feedback_count=0,
                aggregate_score=0,
                recent_indicator=0,
                distinct_clients=0,
                source_urn=urn,
            )

        try:
            # getSummary(agentId, clients[], tag1, tag2) -> (count, aggregate, recent)
            count, aggregate, recent = c.getSummary(agent_id, clients, "", "").call()
        except Exception as exc:
            raise ReputationReadError(
                f"{urn}: getSummary failed: {type(exc).__name__}: {exc}",
            ) from exc

        return ReputationSummary(
            agent_id=agent_id,
            feedback_count=int(count),
            aggregate_score=int(aggregate),
            recent_indicator=int(recent),
            distinct_clients=len(clients),
            source_urn=urn,
        )

    def is_reachable(self) -> bool:
        """Health check: contract responds + reports a version."""
        try:
            return bool(self._contract.functions.getVersion().call())
        except Exception:
            return False


def make_reputation_reader_from_env() -> ReputationRegistryReader:
    """Build a ready-to-use Reputation Registry reader from env vars."""
    from web3 import HTTPProvider, Web3

    from agentgraph_bridge_erc8004.config import load_config_from_env

    cfg = load_config_from_env()
    w3 = Web3(HTTPProvider(cfg.rpc_url, request_kwargs={"timeout": cfg.request_timeout_seconds}))
    return ReputationRegistryReader(w3, cfg)


__all__ = [
    "ReputationReadError",
    "ReputationRegistryReader",
    "ReputationSummary",
    "make_reputation_reader_from_env",
]
