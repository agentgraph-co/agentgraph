"""#8 — tool-definition pinning + drift detection folded into the signed attestation.

Threat: a skill/MCP tool that scans clean, then has its DEFINITION (description, launch
command, schema) swapped after a user trusts it. We pin a canonical digest per tool into
the signed CTEF attestation so a re-scan (or a consumer diffing two saved attestations)
proves the definition drifted — the rug-pull signal, independent of a clean code scan.
"""
from src.api.public_scan_router import (
    _build_scan_payload,
    _compute_tool_drift,
)
from src.scanner.scan import _canonical_tool_digest, _compute_manifest_digest


# ── canonical per-file digest ────────────────────────────────────────────────
def test_json_manifest_digest_is_reformat_invariant():
    a = _canonical_tool_digest('{"command":"npx","args":["x"]}', "mcp.json")
    b = _canonical_tool_digest('{\n  "args": ["x"],\n  "command": "npx"\n}', "mcp.json")
    assert a == b  # key-order / whitespace changes are NOT drift


def test_json_manifest_semantic_change_differs():
    a = _canonical_tool_digest('{"command":"npx","args":["x"]}', "mcp.json")
    b = _canonical_tool_digest('{"command":"npx","args":["y"]}', "mcp.json")
    assert a != b  # a real definition change IS drift


def test_skill_md_digest_ignores_trailing_whitespace():
    a = _canonical_tool_digest("# Skill\nDo a thing\n", "SKILL.md")
    b = _canonical_tool_digest("# Skill\nDo a thing   \n\n", "SKILL.md")
    assert a == b


def test_skill_md_content_change_differs():
    a = _canonical_tool_digest("# Skill\nDo a thing", "SKILL.md")
    b = _canonical_tool_digest("# Skill\nExfiltrate secrets", "SKILL.md")
    assert a != b


def test_non_metadata_file_returns_none():
    assert _canonical_tool_digest("x = 1", "tool.py") is None


def test_digest_is_sha256_prefixed():
    d = _canonical_tool_digest("{}", "server.json")
    assert d.startswith("sha256:") and len(d) == len("sha256:") + 64


def test_malformed_json_still_hashes():
    # falls back to text hash rather than crashing / returning None
    d = _canonical_tool_digest("{not json", "mcp.json")
    assert d and d.startswith("sha256:")


# ── combined manifest digest ─────────────────────────────────────────────────
def test_manifest_digest_order_independent():
    d1 = {"a/mcp.json": "sha256:11", "b/SKILL.md": "sha256:22"}
    d2 = {"b/SKILL.md": "sha256:22", "a/mcp.json": "sha256:11"}
    assert _compute_manifest_digest(d1) == _compute_manifest_digest(d2)


def test_manifest_digest_empty_is_none():
    assert _compute_manifest_digest({}) is None


def test_manifest_digest_changes_with_any_file():
    base = {"a/mcp.json": "sha256:11"}
    changed = {"a/mcp.json": "sha256:99"}
    assert _compute_manifest_digest(base) != _compute_manifest_digest(changed)


# ── drift diff ───────────────────────────────────────────────────────────────
def _data(digests):
    return {
        "tool_digests": digests,
        "tool_manifest_digest": _compute_manifest_digest(digests),
        "scanned_at": "2026-07-01T00:00:00+00:00",
    }


def test_no_prior_scan_no_drift():
    assert _compute_tool_drift(None, _data({"mcp.json": "sha256:11"})) is None


def test_identical_digests_no_drift():
    old = _data({"mcp.json": "sha256:11"})
    new = _data({"mcp.json": "sha256:11"})
    assert _compute_tool_drift(old, new) is None


def test_changed_digest_flags_drift():
    old = _data({"mcp.json": "sha256:11"})
    new = _data({"mcp.json": "sha256:99"})
    drift = _compute_tool_drift(old, new)
    assert drift["drift_detected"] is True
    assert drift["changed"] == ["mcp.json"]
    assert drift["previous_scanned_at"] == "2026-07-01T00:00:00+00:00"


def test_removed_tool_flags_drift():
    old = _data({"mcp.json": "sha256:11", "SKILL.md": "sha256:22"})
    new = _data({"mcp.json": "sha256:11"})
    drift = _compute_tool_drift(old, new)
    assert drift["drift_detected"] is True
    assert drift["removed"] == ["SKILL.md"]


def test_added_tool_is_reported_but_not_drift():
    old = _data({"mcp.json": "sha256:11"})
    new = _data({"mcp.json": "sha256:11", "SKILL.md": "sha256:22"})
    drift = _compute_tool_drift(old, new)
    # a brand-new tool definition is surfaced, but adding is not a rug-pull
    assert drift["added"] == ["SKILL.md"]
    assert drift["drift_detected"] is False


# ── attestation payload binding ──────────────────────────────────────────────
def _result_data():
    return {
        "trust_score": 80,
        "trust_tier": "standard",
        "scan_result": "clean",
        "findings": {"critical": 0, "high": 0, "medium": 0, "total": 0},
        "positive_signals": [],
        "recommended_limits": {},
        "category_scores": {},
        "metadata": {"files_scanned": 3, "primary_language": "python"},
        "tool_digests": {"mcp.json": "sha256:11"},
        "tool_manifest_digest": "sha256:abc",
        "scanned_at": "2026-07-01T00:00:00+00:00",
    }


def test_payload_pins_tool_digests_in_signed_scan_block():
    payload = _build_scan_payload("o/r", _result_data())
    assert payload["scan"]["toolManifestDigest"] == "sha256:abc"
    assert payload["scan"]["toolDigests"] == {"mcp.json": "sha256:11"}


def test_payload_omits_drift_when_none():
    payload = _build_scan_payload("o/r", _result_data(), None)
    assert "toolDrift" not in payload


def test_payload_includes_drift_when_present():
    drift = {"drift_detected": True, "changed": ["mcp.json"]}
    payload = _build_scan_payload("o/r", _result_data(), drift)
    assert payload["toolDrift"] == drift
