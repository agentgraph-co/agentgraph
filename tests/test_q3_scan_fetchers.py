"""URL-parse smoke tests for the Q3 2026 scan-corpus expansion fetchers.

Covers the three new source-import fetchers added for the Q3 scan expansion
per `docs/internal/execution-plan-rebalance.md` week of Jun 22 (#111):

- Smithery — third-party MCP server registry
- PulseMCP — third-party MCP server directory
- crates.io — Rust agent packages

Full HTTP-mocked fetch tests follow when the batch-scan integration lands;
this file proves the URL parsers work and the modules import cleanly.
"""
from __future__ import annotations

import pytest

from src.source_import.crates_fetcher import parse_crates_url
from src.source_import.errors import SourceParseError
from src.source_import.pulsemcp_fetcher import parse_pulsemcp_url
from src.source_import.smithery_fetcher import parse_smithery_url


class TestParseSmitheryUrl:
    def test_simple_server(self):
        assert parse_smithery_url("https://smithery.ai/server/some-server") == "some-server"

    def test_namespaced_server(self):
        # Smithery allows owner/server paths
        assert (
            parse_smithery_url("https://smithery.ai/server/owner/my-server")
            == "owner/my-server"
        )

    def test_with_trailing_slash(self):
        assert parse_smithery_url("https://smithery.ai/server/x/") == "x"

    def test_http_scheme(self):
        assert parse_smithery_url("http://smithery.ai/server/x") == "x"

    def test_invalid(self):
        with pytest.raises(SourceParseError):
            parse_smithery_url("https://example.com/server/x")


class TestParsePulseMcpUrl:
    def test_with_www(self):
        assert (
            parse_pulsemcp_url("https://www.pulsemcp.com/servers/example-server")
            == "example-server"
        )

    def test_without_www(self):
        assert parse_pulsemcp_url("https://pulsemcp.com/servers/x") == "x"

    def test_with_query_string(self):
        assert (
            parse_pulsemcp_url("https://www.pulsemcp.com/servers/x?ref=hn") == "x"
        )

    def test_invalid(self):
        with pytest.raises(SourceParseError):
            parse_pulsemcp_url("https://pulsemcp.com/other-path/x")


class TestParseCratesUrl:
    def test_simple_crate(self):
        assert parse_crates_url("https://crates.io/crates/serde_jcs") == "serde_jcs"

    def test_with_version(self):
        # crates.io URLs may carry a version suffix
        assert parse_crates_url("https://crates.io/crates/tokio/1.40.0") == "tokio"

    def test_with_hyphen(self):
        assert parse_crates_url("https://crates.io/crates/my-crate") == "my-crate"

    def test_invalid(self):
        with pytest.raises(SourceParseError):
            parse_crates_url("https://crates.io/users/someone")
