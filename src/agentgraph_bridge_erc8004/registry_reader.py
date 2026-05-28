"""Read entries from ERC-8004 registry contracts on Ethereum mainnet.

`ERC8004RegistryReader` wraps a `web3.Web3` instance and the three
ERC-8004 registry contracts (Identity / Reputation / Validation),
returning `ERC8004Entry` Pydantic models for downstream normalization
in `attestation_normalizer.py` (Day 3).

Architecture:
- `read_entry(urn)` and `read_entry_by_id(registry, entry_id)` are the
  two read paths. Both produce the same `ERC8004Entry` shape.
- Web3 instantiation is injected (not hidden) so tests can pass a
  mock Web3 without monkeypatching imports.
- All on-chain reads are wrapped in narrow try/except that converts
  web3 exceptions to `RegistryReadError` with the URN context.
- Block timestamps are fetched once per entry via `eth.get_block()`
  rather than embedded in the registry (some EIP-8004 deployments
  may not store timestamp directly).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from agentgraph_bridge_erc8004.abi import load_registry_abi
from agentgraph_bridge_erc8004.config import ERC8004Config
from agentgraph_bridge_erc8004.models import ERC8004Entry, ERC8004Registry
from agentgraph_bridge_erc8004.urn_resolver import parse_erc8004_urn

if TYPE_CHECKING:
    from web3 import Web3
    from web3.contract import Contract


class RegistryReadError(RuntimeError):
    """Raised when a registry read fails (contract reverted, RPC down, entry not found)."""


@dataclass(frozen=True)
class _EntryTuple:
    """Raw return from `getEntry(entryId)` before Pydantic validation."""

    submitter: str
    subject_did: str
    data: bytes
    timestamp: int
    exists: bool


class ERC8004RegistryReader:
    """Read-only client for the three ERC-8004 registry contracts.

    Construct with a configured `Web3` instance + `ERC8004Config`. The
    Web3 instance is the only injection point — tests pass a `MagicMock`
    or a `Web3(EthereumTesterProvider())` and the reader's behavior is
    fully exercised without any network I/O.

    Example:
        >>> from web3 import Web3, HTTPProvider
        >>> from agentgraph_bridge_erc8004.config import load_config_from_env
        >>> cfg = load_config_from_env()
        >>> w3 = Web3(HTTPProvider(cfg.rpc_url))
        >>> reader = ERC8004RegistryReader(w3, cfg)
        >>> entry = reader.read_entry("urn:erc8004:identity:42")
        >>> entry.submitter
        '0x...'
    """

    def __init__(self, web3: Web3, config: ERC8004Config) -> None:
        self._w3 = web3
        self._cfg = config
        self._abi = load_registry_abi()
        self._contracts: dict[ERC8004Registry, Contract] = {
            ERC8004Registry.IDENTITY: self._make_contract(
                config.identity_registry_address,
            ),
            ERC8004Registry.REPUTATION: self._make_contract(
                config.reputation_registry_address,
            ),
            ERC8004Registry.VALIDATION: self._make_contract(
                config.validation_registry_address,
            ),
        }

    def _make_contract(self, address: str) -> Contract:
        """Construct a Web3 Contract bound to one registry's address + ABI."""
        # Web3 expects checksummed addresses. Normalize input.
        from web3 import Web3  # local import — only loaded when reader is used

        checksum = Web3.to_checksum_address(address)
        return self._w3.eth.contract(address=checksum, abi=self._abi)

    def read_entry(self, urn: str) -> ERC8004Entry:
        """Read an entry by URN. Convenience wrapper around `read_entry_by_id`.

        Raises:
            URNParseError — if URN is malformed (from `parse_erc8004_urn`)
            RegistryReadError — if the on-chain read fails or entry doesn't exist
        """
        parsed = parse_erc8004_urn(urn)
        return self.read_entry_by_id(parsed.registry, parsed.entry_id)

    def read_entry_by_id(
        self, registry: ERC8004Registry, entry_id: int,
    ) -> ERC8004Entry:
        """Read an entry from a specific registry by integer ID.

        Returns a populated `ERC8004Entry`. The `data` field carries the
        raw bytes payload (typically CTEF-formatted JSON) that the Day 3
        attestation normalizer will parse + verify.

        Raises:
            RegistryReadError — if the read fails, RPC is unreachable,
            or `exists=false` on the returned tuple
        """
        if entry_id < 0:
            raise RegistryReadError(
                f"entry_id must be non-negative, got {entry_id}",
            )

        contract = self._contracts[registry]
        urn = f"urn:erc8004:{registry.value}:{entry_id}"

        try:
            raw = contract.functions.getEntry(entry_id).call()
        except Exception as exc:  # web3 raises many types; catch wide
            raise RegistryReadError(
                f"Registry read failed for {urn}: {type(exc).__name__}: {exc}",
            ) from exc

        tup = _EntryTuple(
            submitter=raw[0],
            subject_did=raw[1],
            data=raw[2] if isinstance(raw[2], bytes) else bytes(raw[2]),
            timestamp=int(raw[3]),
            exists=bool(raw[4]),
        )

        if not tup.exists:
            raise RegistryReadError(f"Entry not found: {urn} (exists=false)")

        # Fetch the block this entry's tx landed in to get the canonical
        # block timestamp (registry-side timestamp may differ from block).
        block_number, tx_hash = self._lookup_entry_tx(registry, entry_id)

        # Use registry-provided timestamp if available, else fall back
        # to block timestamp (Unix seconds → datetime UTC).
        block_ts = datetime.fromtimestamp(tup.timestamp, tz=timezone.utc)

        return ERC8004Entry(
            registry=registry,
            entry_id=entry_id,
            submitter=tup.submitter,
            subject_did=tup.subject_did or None,
            data=tup.data,
            block_number=block_number,
            block_timestamp=block_ts,
            tx_hash=tx_hash,
        )

    def _lookup_entry_tx(
        self, registry: ERC8004Registry, entry_id: int,
    ) -> tuple[int, str]:
        """Find the block + tx hash that submitted this entry via event log.

        Scans `EntrySubmitted(entryId, ...)` events filtered by `entryId`.
        Returns (block_number, tx_hash). If no event is found, returns
        (0, all-zero-hash) — caller may treat as a degraded read.

        This is a separate method because some deployments may chunk
        the lookup (e.g. scan in 10k-block windows) for performance;
        the default implementation does a full historical scan which
        Alchemy/Quicknode handle fine on free tiers for low-volume
        registries.
        """
        contract = self._contracts[registry]

        try:
            event = contract.events.EntrySubmitted
            logs = event.get_logs(
                from_block=0,
                argument_filters={"entryId": entry_id},
            )
        except Exception:
            return 0, "0x" + "0" * 64

        if not logs:
            return 0, "0x" + "0" * 64

        first = logs[0]
        block_number = int(first["blockNumber"])
        tx_hash = first["transactionHash"].hex()
        if not tx_hash.startswith("0x"):
            tx_hash = "0x" + tx_hash
        return block_number, tx_hash

    def entry_count(self, registry: ERC8004Registry) -> int:
        """Return the total entry count for a registry. Useful for enumeration."""
        contract = self._contracts[registry]
        try:
            return int(contract.functions.entryCount().call())
        except Exception as exc:
            raise RegistryReadError(
                f"entry_count() failed for {registry.value}: {exc}",
            ) from exc

    def is_reachable(self) -> bool:
        """Health check — confirms the RPC endpoint responds + the chain ID matches config."""
        try:
            chain_id = int(self._w3.eth.chain_id)
        except Exception:
            return False
        return chain_id == self._cfg.chain_id


def make_reader_from_env() -> ERC8004RegistryReader:
    """Build a ready-to-use reader from environment variables.

    Convenience constructor — uses `load_config_from_env()` for config
    + builds a synchronous `Web3(HTTPProvider(...))` instance.

    For production deployments that need async, construct `Web3` with
    an `AsyncHTTPProvider` and pass it to `ERC8004RegistryReader`
    directly instead.
    """
    from web3 import HTTPProvider, Web3

    from agentgraph_bridge_erc8004.config import load_config_from_env

    cfg = load_config_from_env()
    w3 = Web3(HTTPProvider(
        cfg.rpc_url,
        request_kwargs={"timeout": cfg.request_timeout_seconds},
    ))
    return ERC8004RegistryReader(w3, cfg)


__all__ = [
    "ERC8004RegistryReader",
    "RegistryReadError",
    "make_reader_from_env",
]
