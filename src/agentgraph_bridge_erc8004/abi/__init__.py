"""ERC-8004 registry ABI fragments.

The ABI in `erc8004_registry.json` is a minimal, inferred shape based on
EIP-8004 semantics: `getEntry(uint256 entryId)` returning the canonical
fields needed to materialize an `ERC8004Entry` model + `entryCount()`
for bulk enumeration + `EntrySubmitted` event for change feeds.

Day 2 of the 3-day MVP uses this inferred ABI against placeholder
addresses. Day 3 swaps in the real EIP-8004 finalised ABI once the
canonical contract is verified on mainnet.

To override at runtime: set ERC8004_ABI_PATH env var to a JSON file
matching the same fragment shape.
"""
from __future__ import annotations

import json
from pathlib import Path

_ABI_PATH = Path(__file__).parent / "erc8004_registry.json"


def load_registry_abi() -> list[dict]:
    """Load the canonical ERC-8004 registry ABI fragments.

    Returns a list of ABI entries (functions + events). Use as the
    `abi=` argument when constructing `web3.eth.contract()`.
    """
    import os

    override = os.environ.get("ERC8004_ABI_PATH")
    path = Path(override) if override else _ABI_PATH

    with open(path) as f:
        return json.load(f)
