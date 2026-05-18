"""Tests for URN parser — pure logic, no chain calls."""
from __future__ import annotations

import pytest

from agentgraph_bridge_erc8004.models import ERC8004Registry
from agentgraph_bridge_erc8004.urn_resolver import (
    ParsedURN,
    URNParseError,
    parse_erc8004_urn,
)


class TestParseValid:
    def test_identity_registry(self):
        result = parse_erc8004_urn("urn:erc8004:identity:42")
        assert result == ParsedURN(
            registry=ERC8004Registry.IDENTITY, entry_id=42,
        )

    def test_reputation_registry(self):
        result = parse_erc8004_urn("urn:erc8004:reputation:0")
        assert result == ParsedURN(
            registry=ERC8004Registry.REPUTATION, entry_id=0,
        )

    def test_validation_registry(self):
        result = parse_erc8004_urn("urn:erc8004:validation:999999")
        assert result == ParsedURN(
            registry=ERC8004Registry.VALIDATION, entry_id=999999,
        )

    def test_round_trip(self):
        urn = "urn:erc8004:reputation:7"
        assert parse_erc8004_urn(urn).to_urn() == urn


class TestParseInvalid:
    def test_wrong_scheme(self):
        with pytest.raises(URNParseError, match="Malformed"):
            parse_erc8004_urn("urn:concordia:attestation:42")

    def test_unknown_registry(self):
        with pytest.raises(URNParseError, match="Malformed"):
            parse_erc8004_urn("urn:erc8004:unknown:42")

    def test_negative_entry_id(self):
        with pytest.raises(URNParseError, match="Malformed"):
            parse_erc8004_urn("urn:erc8004:identity:-1")

    def test_leading_zero(self):
        # "0" is valid, but "01" is not
        with pytest.raises(URNParseError, match="Malformed"):
            parse_erc8004_urn("urn:erc8004:identity:01")

    def test_non_numeric_entry_id(self):
        with pytest.raises(URNParseError, match="Malformed"):
            parse_erc8004_urn("urn:erc8004:identity:abc")

    def test_extra_segments(self):
        with pytest.raises(URNParseError, match="Malformed"):
            parse_erc8004_urn("urn:erc8004:identity:42:extra")

    def test_empty_string(self):
        with pytest.raises(URNParseError, match="Malformed"):
            parse_erc8004_urn("")

    def test_non_string_input(self):
        with pytest.raises(URNParseError, match="must be str"):
            parse_erc8004_urn(42)  # type: ignore[arg-type]
