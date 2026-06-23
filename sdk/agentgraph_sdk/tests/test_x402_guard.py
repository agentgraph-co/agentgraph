"""Tests for the x402 verify-then-pay safety guard."""
from __future__ import annotations

import hashlib
import json
import os

import pytest
import rfc8785

from agentgraph_sdk.x402_guard import PaymentRefused, X402SafetyGuard, evaluate


def _att(grade: str, crit: int, high: int, med: int = 0) -> dict:
    return {
        "attestation": {
            "payload": {
                "grade": grade,
                "findings": {"critical": crit, "high": high, "medium": med,
                             "total": crit + high + med},
            }
        }
    }


def _fetch(value):
    async def f(_url):
        return value
    return f


@pytest.mark.asyncio
async def test_refuses_to_pay_critical():
    paid = []

    async def pay():
        paid.append(True)

    guard = X402SafetyGuard(fetch_attestation=_fetch(_att("F", 2, 0)), verify_signature=False)
    with pytest.raises(PaymentRefused):
        await guard.guarded_pay("https://api.example.com/x402", pay)
    assert paid == []  # pay_fn never ran


@pytest.mark.asyncio
async def test_refuses_to_pay_high():
    guard = X402SafetyGuard(fetch_attestation=_fetch(_att("D", 0, 3)), verify_signature=False)
    with pytest.raises(PaymentRefused):
        await guard.check("https://api.example.com/x402")


@pytest.mark.asyncio
async def test_admits_clean_endpoint():
    paid = []

    async def pay():
        paid.append(True)
        return "PAID"

    guard = X402SafetyGuard(fetch_attestation=_fetch(_att("A", 0, 0, 1)), verify_signature=False)
    result = await guard.guarded_pay("https://api.example.com/x402", pay)
    assert result == "PAID"
    assert paid == [True]


@pytest.mark.asyncio
async def test_unattested_admits_by_default_but_records_reason():
    guard = X402SafetyGuard(fetch_attestation=_fetch(None), verify_signature=False)
    verdict = await guard.check("https://api.example.com/x402")
    assert verdict == {"verdict": "admit", "reason": "no_safety_attestation"}


@pytest.mark.asyncio
async def test_unattested_refused_when_required():
    guard = X402SafetyGuard(fetch_attestation=_fetch(None), require_safety=True, verify_signature=False)
    with pytest.raises(PaymentRefused):
        await guard.check("https://api.example.com/x402")


def test_evaluate_matches_published_conformance_vectors():
    """The guard's deny rule must stay byte-identical to the published vectors."""
    fixture_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..", "docs", "conformance", "x402-safety-screen-v0",
        "safety_screen_v0.json",
    )
    fixture = json.load(open(os.path.normpath(fixture_path)))
    for vec in fixture["vectors"]:
        verdict = evaluate(vec["input"].get("safety_attestation"))
        sha = hashlib.sha256(rfc8785.dumps(verdict)).hexdigest()
        assert sha == vec["verdict_sha256"], f"{vec['name']} diverged from published vector"
