"""AgentGraph endpoint-safety screen — a PRE_PAYMENT_GUARD plugin reference.

Implements the converging x402 pre-payment guard interface discussed in
x402-foundation/x402#2533:

    declares: list[str]
    screen(input, ctx) -> {"verdict": "admit"|"deny", "reason"?: str, "entities"?: list[str]}

This is the *safety* screen (sibling to evidai's authorization plugin and the
payload PII screen): it refuses to pay an x402 endpoint that AgentGraph has graded
critical/high. It is **deny-only** and **mutation-free** — it reads the supplied
safety attestation and decides; it changes nothing a downstream screen sees. That
purity is what makes the verdict byte-reproducible offline (see safety_screen_v0.json).

The screen is pure over its input: the AgentGraph CTEF safety attestation for the
endpoint is passed in as `input["safety_attestation"]` (fetched by the host before
the guard runs, exactly like a payload screen receives the payload). No network here.
"""
from __future__ import annotations

from typing import Any

NAME = "agentgraph.safety"
VERSION = "v0"

# keys_off_raw: the only fields this screen reads. It never touches the payment
# body or the raw payload — so it cannot launder a decision into the signed bytes.
DECLARES = ["resource_url", "safety_attestation"]

# Finding severities that block a payment.
_BLOCKING = ("critical", "high")


def _findings(att: dict) -> dict:
    return ((att or {}).get("attestation", {}) or {}).get("payload", {}).get("findings", {}) or {}


def screen(input: dict, ctx: dict | None = None) -> dict[str, Any]:
    """Return an admit/deny verdict for paying this x402 endpoint.

    `input["safety_attestation"]` is an AgentGraph CTEF attestation (the signed
    verdict over the endpoint). Its signature/binding is verified by the host
    *before* this screen runs (see agentgraph_sdk.verify); this screen decides on
    the already-trusted verdict, so it stays pure and offline-reproducible.

    Contract on a missing attestation: **admit with a reason** (never silently).
    The host's policy (e.g. a `require_safety` flag) decides whether an
    un-attested endpoint is acceptable — same philosophy as SafeAgent's
    `require_attestation`. The screen itself does not block the whole ecosystem.
    """
    att = input.get("safety_attestation")
    if not att:
        return {"verdict": "admit", "reason": "no_safety_attestation"}

    findings = _findings(att)
    blocking = {sev: int(findings.get(sev, 0) or 0) for sev in _BLOCKING}
    total_blocking = sum(blocking.values())

    if total_blocking > 0:
        # entities: the severity buckets that triggered the deny, sorted for determinism.
        entities = sorted(sev for sev, n in blocking.items() if n > 0)
        parts = ", ".join(f"{blocking[sev]} {sev}" for sev in entities)
        grade = (att.get("attestation", {}) or {}).get("payload", {}).get("grade")
        reason = f"endpoint graded {grade}: {parts} finding(s)" if grade else f"{parts} finding(s)"
        return {"verdict": "deny", "reason": reason, "entities": entities}

    return {"verdict": "admit"}


class SafetyScreen:
    """Object form of the screen for hosts that register plugin instances."""

    name = NAME
    version = VERSION
    declares = DECLARES

    def screen(self, input: dict, ctx: dict | None = None) -> dict[str, Any]:
        return screen(input, ctx)
