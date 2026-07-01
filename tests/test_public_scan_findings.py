"""Public scan API now returns individual findings (severity-sorted, capped, no snippet)."""
from src.api.public_scan_router import _build_scan_payload, _scan_result_to_dict
from src.scanner.scan import Finding, ScanResult


def _result_with(findings):
    r = ScanResult(repo="o/r", stars=0, description="", framework="")
    r.findings = findings
    r.trust_score = 50
    return r


def test_items_present_and_shaped():
    r = _result_with([
        Finding("prompt_injection", "Instruction override", "high", "skill.md", 3, "x"),
    ])
    d = _scan_result_to_dict(r)
    items = d["findings"]["items"]
    assert len(items) == 1
    it = items[0]
    assert it["category"] == "prompt_injection"
    assert it["severity"] == "high"
    assert it["file_path"] == "skill.md"
    assert it["line_number"] == 3
    assert "snippet" not in it  # never leak raw matched content


def test_items_severity_sorted():
    r = _result_with([
        Finding("fs_access", "b", "medium", "f", 1, ""),
        Finding("secret", "a", "critical", "f", 2, ""),
        Finding("unsafe_exec", "c", "high", "f", 3, ""),
    ])
    sev = [i["severity"] for i in _scan_result_to_dict(r)["findings"]["items"]]
    assert sev == ["critical", "high", "medium"]


def test_items_capped_at_100():
    r = _result_with([Finding("fs_access", "x", "medium", "f", i, "") for i in range(250)])
    assert len(_scan_result_to_dict(r)["findings"]["items"]) == 100


def test_items_signed_into_attestation():
    r = _result_with([Finding("toxic_flow", "trifecta", "high", "tool.py", 5, "")])
    d = _scan_result_to_dict(r)
    payload = _build_scan_payload("o/r", d)
    signed_items = payload["scan"]["findings"]["items"]
    assert signed_items and signed_items[0]["name"] == "trifecta"
