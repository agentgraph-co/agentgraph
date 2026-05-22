"""Tests for ERC-8004 registry reader.

Unit tests use mocked Web3 — no network I/O. The full integration path
(real Alchemy RPC + EIP-8004 mainnet contracts) is covered by Day 3's
`test_smoke_mainnet.py` once final addresses + ABI lock.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from agentgraph_bridge_erc8004.config import ERC8004Config, ERC8004_TEST_ADDRESSES
from agentgraph_bridge_erc8004.models import ERC8004Registry
from agentgraph_bridge_erc8004.registry_reader import (
    ERC8004RegistryReader,
    RegistryReadError,
)

# Sample raw entry shape as returned by `getEntry(entryId)`:
#   (submitter, subjectDid, data, timestamp, exists)
_SAMPLE_ENTRY = (
    "0x" + "ab" * 20,  # submitter
    "did:web:agent.example.com",  # subjectDid
    b'{"claim_type":"identity","payload":{"sub":"did:web:agent.example.com"}}',  # data
    1747977600,  # timestamp (2026-05-22T...)
    True,  # exists
)

_SAMPLE_TX = "0x" + "cd" * 32


def _mock_config() -> ERC8004Config:
    return ERC8004Config(
        rpc_url="http://localhost:8545",
        identity_registry_address=ERC8004_TEST_ADDRESSES["identity"],
        reputation_registry_address=ERC8004_TEST_ADDRESSES["reputation"],
        validation_registry_address=ERC8004_TEST_ADDRESSES["validation"],
    )


def _mock_web3_with_entry(entry_tuple, tx_log=None):
    """Build a MagicMock Web3 that returns `entry_tuple` from getEntry()
    and `tx_log` (or empty) from EntrySubmitted event lookup."""
    w3 = MagicMock()
    w3.eth.chain_id = 1  # mainnet

    # contract.functions.getEntry(entryId).call() returns the tuple
    contract = MagicMock()
    contract.functions.getEntry.return_value.call.return_value = entry_tuple
    contract.functions.entryCount.return_value.call.return_value = 42

    # contract.events.EntrySubmitted.get_logs() returns event logs
    if tx_log is None:
        contract.events.EntrySubmitted.get_logs.return_value = []
    else:
        contract.events.EntrySubmitted.get_logs.return_value = [tx_log]

    w3.eth.contract.return_value = contract
    return w3, contract


class TestReadByURN:
    def test_identity_registry(self):
        log = {
            "blockNumber": 25_000_000,
            "transactionHash": MagicMock(hex=lambda: "cd" * 32),
        }
        w3, _ = _mock_web3_with_entry(_SAMPLE_ENTRY, tx_log=log)
        reader = ERC8004RegistryReader(w3, _mock_config())

        entry = reader.read_entry("urn:erc8004:identity:42")

        assert entry.registry == ERC8004Registry.IDENTITY
        assert entry.entry_id == 42
        assert entry.subject_did == "did:web:agent.example.com"
        assert entry.data == _SAMPLE_ENTRY[2]
        assert entry.block_number == 25_000_000
        assert entry.tx_hash == _SAMPLE_TX
        # 1747977600 = 2025-05-23 05:20:00 UTC (matches the unix ts in _SAMPLE_ENTRY)
        assert entry.block_timestamp == datetime.fromtimestamp(1747977600, tz=timezone.utc)

    def test_reputation_registry(self):
        w3, _ = _mock_web3_with_entry(_SAMPLE_ENTRY)
        reader = ERC8004RegistryReader(w3, _mock_config())
        entry = reader.read_entry("urn:erc8004:reputation:7")
        assert entry.registry == ERC8004Registry.REPUTATION
        assert entry.entry_id == 7

    def test_validation_registry(self):
        w3, _ = _mock_web3_with_entry(_SAMPLE_ENTRY)
        reader = ERC8004RegistryReader(w3, _mock_config())
        entry = reader.read_entry("urn:erc8004:validation:99")
        assert entry.registry == ERC8004Registry.VALIDATION
        assert entry.entry_id == 99


class TestReadByID:
    def test_basic(self):
        w3, _ = _mock_web3_with_entry(_SAMPLE_ENTRY)
        reader = ERC8004RegistryReader(w3, _mock_config())
        entry = reader.read_entry_by_id(ERC8004Registry.IDENTITY, 42)
        assert entry.entry_id == 42
        assert entry.submitter == "0x" + "ab" * 20

    def test_negative_id_rejected(self):
        w3, _ = _mock_web3_with_entry(_SAMPLE_ENTRY)
        reader = ERC8004RegistryReader(w3, _mock_config())
        with pytest.raises(RegistryReadError, match="non-negative"):
            reader.read_entry_by_id(ERC8004Registry.IDENTITY, -1)

    def test_subject_did_empty_becomes_none(self):
        empty_did_entry = (
            "0x" + "ab" * 20, "", b"data", 1747977600, True,
        )
        w3, _ = _mock_web3_with_entry(empty_did_entry)
        reader = ERC8004RegistryReader(w3, _mock_config())
        entry = reader.read_entry_by_id(ERC8004Registry.IDENTITY, 1)
        assert entry.subject_did is None


class TestEntryNotFound:
    def test_exists_false_raises(self):
        not_found_entry = (
            "0x" + "00" * 20, "", b"", 0, False,
        )
        w3, _ = _mock_web3_with_entry(not_found_entry)
        reader = ERC8004RegistryReader(w3, _mock_config())
        with pytest.raises(RegistryReadError, match="not found"):
            reader.read_entry("urn:erc8004:identity:999")


class TestRPCFailure:
    def test_contract_call_exception_wraps(self):
        w3 = MagicMock()
        w3.eth.chain_id = 1
        contract = MagicMock()
        contract.functions.getEntry.return_value.call.side_effect = ConnectionError("RPC down")
        w3.eth.contract.return_value = contract

        reader = ERC8004RegistryReader(w3, _mock_config())
        with pytest.raises(RegistryReadError, match="Registry read failed"):
            reader.read_entry("urn:erc8004:identity:42")


class TestEntryCount:
    def test_returns_count(self):
        w3, _ = _mock_web3_with_entry(_SAMPLE_ENTRY)
        reader = ERC8004RegistryReader(w3, _mock_config())
        assert reader.entry_count(ERC8004Registry.IDENTITY) == 42

    def test_failure_wraps(self):
        w3 = MagicMock()
        w3.eth.chain_id = 1
        contract = MagicMock()
        contract.functions.entryCount.return_value.call.side_effect = ConnectionError("RPC down")
        w3.eth.contract.return_value = contract

        reader = ERC8004RegistryReader(w3, _mock_config())
        with pytest.raises(RegistryReadError, match="entry_count"):
            reader.entry_count(ERC8004Registry.IDENTITY)


class TestIsReachable:
    def test_reachable_mainnet(self):
        w3, _ = _mock_web3_with_entry(_SAMPLE_ENTRY)
        reader = ERC8004RegistryReader(w3, _mock_config())
        assert reader.is_reachable() is True

    def test_chain_id_mismatch(self):
        w3 = MagicMock()
        w3.eth.chain_id = 5  # Goerli, not mainnet
        w3.eth.contract.return_value = MagicMock()
        reader = ERC8004RegistryReader(w3, _mock_config())
        assert reader.is_reachable() is False

    def test_rpc_unreachable(self):
        w3 = MagicMock()
        # accessing chain_id raises
        type(w3.eth).chain_id = property(lambda _: (_ for _ in ()).throw(ConnectionError()))
        w3.eth.contract.return_value = MagicMock()
        reader = ERC8004RegistryReader(w3, _mock_config())
        assert reader.is_reachable() is False


@pytest.mark.skipif(
    not os.environ.get("ETH_RPC_URL"),
    reason="ETH_RPC_URL not set — skipping live mainnet smoke test",
)
class TestLiveMainnetSmoke:
    """Integration smoke test against the real RPC endpoint.

    Skipped by default. Runs when ETH_RPC_URL is set in env (which it
    is in both dev + prod). Confirms the RPC actually responds and
    the chain ID matches expected mainnet (1).

    Does NOT test contract reads — those need real EIP-8004 contract
    addresses which are placeholders until Day 3.
    """

    def test_rpc_responds_with_mainnet_chain_id(self):
        from web3 import HTTPProvider, Web3

        from agentgraph_bridge_erc8004.config import load_config_from_env
        cfg = load_config_from_env()
        w3 = Web3(HTTPProvider(cfg.rpc_url, request_kwargs={"timeout": 10}))

        assert int(w3.eth.chain_id) == 1, "Expected Ethereum mainnet (chain_id=1)"
        # Confirm the RPC is producing fresh blocks
        block = int(w3.eth.block_number)
        assert block > 25_000_000, f"Block number {block} seems stale"
