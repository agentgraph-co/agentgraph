"""Generate agentgraph-scan-v1-structural fixtures for the interop PR.

Writes three fixtures to data/interop-fixtures/agentgraph/v1/ using the
published slot emitter. These are the structural-shape counterparts to
AgentID's v1 fixtures — same test agent, same canonicalization, same
subject DID. aeoess will then compose them into composed/v1/ envelopes.

Usage:
    python3 scripts/dev/generate_agentgraph_fixtures.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.attestation.composed_slot import (  # noqa: E402
    ScanInputs,
    build_agentgraph_slot,
    compute_evidence_hash,
)

# Shared test-agent constants — mirrors AgentID fixtures exactly so all
# three slots reference the same subject.
TEST_AGENT_ID = "agent_interop_test_001"
TEST_AGENT_DID = "did:web:getagentid.dev:agent:agent_interop_test_001"
TEST_SCANNED_AT = datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)
TEST_SCANNER_VERSION = "2026.04.1"

OUT_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "data" / "interop-fixtures" / "agentgraph" / "v1"
)


def _slot_fixture(
    *,
    scenario: str,
    description: str,
    trust_score: int,
    category_scores: dict[str, int],
    findings: dict[str, int],
    expected_gate_states: dict[str, str],
    composite_decision: str,
    failing_gates: list[str],
    reasoning: str,
    decisive_gate: str,
    source_url: str = "https://github.com/agentgraph-co/interop-test-agent",
    artifact_ref: str = "git:sha256:6c0f4fdeaa2f8b6ce0c3f0f5e8a4a9f1c7e6d5b8",
) -> dict:
    """Build a vector.schema.json-compliant fixture wrapping an AgentGraph slot."""
    # Pre-compute evidence hash over a stable payload
    evidence_payload = {
        "scanner": "agentgraph-trust-scanner",
        "scanner_version": TEST_SCANNER_VERSION,
        "trust_score": trust_score,
        "category_scores": category_scores,
        "findings": findings,
    }
    evidence_hash = compute_evidence_hash(evidence_payload)

    inputs = ScanInputs(
        entity_id=TEST_AGENT_ID,
        entity_did=TEST_AGENT_DID,
        source_url=source_url,
        source_type="github",
        framework=None,
        artifact_ref=artifact_ref,
        scanned_at=TEST_SCANNED_AT,
        scanner_version=TEST_SCANNER_VERSION,
        trust_score_0_to_100=trust_score,
        category_scores=category_scores,
        findings=findings,
        evidence_hash=evidence_hash,
        evidence_url=(
            f"https://agentgraph.co/api/v1/entities/{TEST_AGENT_ID}"
            "/attestation/composed-slot"
        ),
    )
    slot = build_agentgraph_slot(inputs)

    return {
        "scenario": scenario,
        "description": description,
        "subject": {
            "agent_id": TEST_AGENT_ID,
            "did": TEST_AGENT_DID,
        },
        "inputs": {
            "agentgraph_scan": slot,
        },
        "expected_result": {
            **expected_gate_states,
            "composite_decision": composite_decision,
            "failing_gates": failing_gates,
            "reasoning": reasoning,
            "decisive_gate": decisive_gate,
        },
        "metadata": {
            "signature_alg": "Ed25519",
            "canonicalization": "JCS (RFC 8785)",
            "schema_version": "1.0.1",
            "fixture_form": "structural",
            "contributors": ["kenneives"],
        },
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1) happy-path — all three gates pass → permit (grade A)
    happy = _slot_fixture(
        scenario="happy-path",
        description=(
            "Agent's linked repo has clean static analysis, no secrets, "
            "no vulnerable deps. All three AgentGraph gates pass. "
            "Composite (security dimension): permit."
        ),
        trust_score=88,
        category_scores={
            "code_quality": 90,
            "secrets": 100,
            "dependencies": 85,
        },
        findings={
            "static_analysis": 0,
            "secrets": 0,
            "dep_critical": 0,
            "dep_high": 0,
        },
        expected_gate_states={
            "security_gate": "passed",
            "identity_gate": "not_applicable",
            "delegation_gate": "not_applicable",
            "wallet_state_gate": "not_applicable",
            "revocation_gate": "not_applicable",
            "policy_gate": "not_applicable",
            "key_lifecycle_gate": "not_applicable",
        },
        composite_decision="permit",
        failing_gates=[],
        reasoning=(
            "AgentGraph scan issued within freshness window. "
            "static_analysis: grade A (0 issues). "
            "secret_scan: grade A+ (0 findings). "
            "dependency_audit: grade A (0 critical, 0 high). "
            "AND-composition across the three published gates: pass. "
            "Identity/delegation/wallet_state/revocation/policy/key_lifecycle "
            "are not_applicable to a security-scan-only vector."
        ),
        decisive_gate="all_passed",
    )

    # 2) critical-deps — dependency_audit fails on a CVSS 9+ dep
    critical_deps = _slot_fixture(
        scenario="critical-deps-fail",
        description=(
            "Agent's repo depends on a package with 2 critical CVEs. "
            "dependency_audit fails; other gates pass. Composite: deny."
        ),
        trust_score=34,
        category_scores={
            "code_quality": 80,
            "secrets": 100,
            "dependencies": 22,
        },
        findings={
            "static_analysis": 1,
            "secrets": 0,
            "dep_critical": 2,
            "dep_high": 4,
        },
        expected_gate_states={
            "security_gate": "failed",
            "identity_gate": "not_applicable",
            "delegation_gate": "not_applicable",
            "wallet_state_gate": "not_applicable",
            "revocation_gate": "not_applicable",
            "policy_gate": "not_applicable",
            "key_lifecycle_gate": "not_applicable",
        },
        composite_decision="deny",
        failing_gates=["security_gate"],
        reasoning=(
            "dependency_audit gate failed: 2 critical CVEs (CVSS >= 9.0) "
            "and 4 high-severity vulnerabilities in direct dependencies. "
            "AND-composition: a single failed gate denies regardless of the "
            "clean static_analysis and secret_scan results."
        ),
        decisive_gate="security",
    )

    # 3) secret-leaked — secret_scan fails on a committed API key
    secret_leaked = _slot_fixture(
        scenario="secret-leaked",
        description=(
            "Agent's repo has a hardcoded API key committed to main. "
            "secret_scan fails; other gates pass. Composite: deny."
        ),
        trust_score=28,
        category_scores={
            "code_quality": 85,
            "secrets": 15,
            "dependencies": 90,
        },
        findings={
            "static_analysis": 0,
            "secrets": 1,
            "dep_critical": 0,
            "dep_high": 0,
        },
        expected_gate_states={
            "security_gate": "failed",
            "identity_gate": "not_applicable",
            "delegation_gate": "not_applicable",
            "wallet_state_gate": "not_applicable",
            "revocation_gate": "not_applicable",
            "policy_gate": "not_applicable",
            "key_lifecycle_gate": "not_applicable",
        },
        composite_decision="deny",
        failing_gates=["security_gate"],
        reasoning=(
            "secret_scan gate failed: 1 high-entropy credential detected "
            "(matches OpenAI API key pattern, present at HEAD). "
            "AND-composition across the three published AgentGraph gates: "
            "deny — secret exposure is non-recoverable by other gates passing."
        ),
        decisive_gate="security",
    )

    fixtures = [
        ("happy-path.json", happy),
        ("critical-deps-fail.json", critical_deps),
        ("secret-leaked.json", secret_leaked),
    ]
    for fname, payload in fixtures:
        out_path = OUT_DIR / fname
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")
        print(f"wrote {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
