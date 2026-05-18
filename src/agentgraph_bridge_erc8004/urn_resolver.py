"""URN parsing for ERC-8004 cross-protocol references.

Per Concordia v0.5.1 §11.5.7, ERC-8004 entries are addressable via three
URN schemes:
- `urn:erc8004:identity:<entry_id>` — Identity Registry entry
- `urn:erc8004:reputation:<entry_id>` — Reputation Registry entry
- `urn:erc8004:validation:<entry_id>` — Validation Registry entry

The URN scheme is the cross-protocol pointer shape AgentGraph's composite
trust score uses to consume ERC-8004 attestations without any translation
layer — the substrate stays at JCS canonicalization; the cross-protocol
semantics live in the URN scheme itself.

This module is the pure-logic URN parser. No on-chain RPC, no signature
verification — just string parsing + validation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from agentgraph_bridge_erc8004.models import ERC8004Registry


class URNParseError(ValueError):
    """Raised when an ERC-8004 URN doesn't parse correctly."""


@dataclass(frozen=True)
class ParsedURN:
    """Result of parsing a `urn:erc8004:{registry}:<entry_id>` URN.

    `entry_id` is the on-chain integer index; `registry` is one of the
    three ERC-8004 registry enum values.
    """

    registry: ERC8004Registry
    entry_id: int

    def to_urn(self) -> str:
        """Reconstruct canonical URN string from parsed components."""
        return f"urn:erc8004:{self.registry.value}:{self.entry_id}"


# urn:erc8004:{registry}:{entry_id}
# - registry must be one of identity, reputation, validation
# - entry_id must be a non-negative integer (no leading zeros except "0")
_URN_PATTERN = re.compile(
    r"^urn:erc8004:(?P<registry>identity|reputation|validation):(?P<entry_id>0|[1-9]\d*)$"
)


def parse_erc8004_urn(urn: str) -> ParsedURN:
    """Parse an `urn:erc8004:{registry}:<entry_id>` URN into typed components.

    Raises URNParseError on any malformed input:
    - Wrong scheme (not `urn:erc8004:`)
    - Unknown registry (not in {identity, reputation, validation})
    - Invalid entry_id (negative, leading zeros, non-numeric)
    - Extra path segments

    Example:
        >>> parse_erc8004_urn("urn:erc8004:reputation:42")
        ParsedURN(registry=ERC8004Registry.REPUTATION, entry_id=42)
    """
    if not isinstance(urn, str):
        raise URNParseError(f"URN must be str, got {type(urn).__name__}")

    match = _URN_PATTERN.match(urn)
    if not match:
        raise URNParseError(
            f"Malformed ERC-8004 URN: {urn!r} (expected "
            f"urn:erc8004:{{identity|reputation|validation}}:<entry_id>)",
        )

    return ParsedURN(
        registry=ERC8004Registry(match.group("registry")),
        entry_id=int(match.group("entry_id")),
    )
