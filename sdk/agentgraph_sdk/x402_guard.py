"""x402 verify-then-pay guard — refuse to pay an endpoint graded critical/high.

This is the core "score before money moves" bet made tangible: an x402 client that,
*before* paying, asks AgentGraph for the endpoint's signed safety verdict, verifies
that verdict offline (Ed25519/JWS, no trust in the server), and refuses to pay if the
endpoint carries a critical/high finding.

Design notes
------------
* **Live query + offline verify.** The verdict is fetched live from AgentGraph at
  pay-time (so the gate sees the current posture and AgentGraph stays the issuer/
  aggregator), then signature-verified client-side via ``agentgraph_sdk.verify`` — the
  endpoint can't forge a clean verdict, and you don't have to trust our server's word.
* **Composes as a PRE_PAYMENT_GUARD screen.** The deny rule here is identical to the
  reference safety screen + conformance vectors in
  ``docs/conformance/x402-safety-screen-v0/`` (deny on critical/high; admit-with-reason
  when un-attested).
* **fail policy is the host's choice.** ``require_safety=False`` (default) admits an
  un-attested endpoint with a reason (never silent); ``require_safety=True`` refuses it.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

_BLOCKING = ("critical", "high")


class PaymentRefused(Exception):
    """Raised when the safety verdict says do not pay this endpoint."""

    def __init__(self, endpoint: str, verdict: dict[str, Any]):
        self.endpoint = endpoint
        self.verdict = verdict
        super().__init__(f"refused to pay {endpoint}: {verdict.get('reason', 'denied')}")


def _findings(att: dict) -> dict:
    return ((att or {}).get("attestation", {}) or {}).get("payload", {}).get("findings", {}) or {}


def evaluate(attestation: dict | None) -> dict[str, Any]:
    """Pure deny rule — mirrors docs/conformance/x402-safety-screen-v0/safety_screen.py."""
    if not attestation:
        return {"verdict": "admit", "reason": "no_safety_attestation"}
    f = _findings(attestation)
    blocking = {s: int(f.get(s, 0) or 0) for s in _BLOCKING}
    if sum(blocking.values()) > 0:
        entities = sorted(s for s, n in blocking.items() if n > 0)
        parts = ", ".join(f"{blocking[s]} {s}" for s in entities)
        grade = (attestation.get("attestation", {}) or {}).get("payload", {}).get("grade")
        reason = f"endpoint graded {grade}: {parts} finding(s)" if grade else f"{parts} finding(s)"
        return {"verdict": "deny", "reason": reason, "entities": entities}
    return {"verdict": "admit"}


class X402SafetyGuard:
    """Verify-then-pay guard for an x402 client.

    Example::

        guard = X402SafetyGuard(client)                 # AgentGraphClient
        result = await guard.guarded_pay(endpoint_url, pay_fn=do_x402_payment)

    ``do_x402_payment`` is your existing payment coroutine; it only runs if the
    endpoint is admitted. On a deny, :class:`PaymentRefused` is raised and no payment
    is attempted.
    """

    def __init__(
        self,
        client: Any = None,
        *,
        require_safety: bool = False,
        fetch_attestation: Callable[[str], Awaitable[dict | None]] | None = None,
        verify_signature: bool = True,
    ) -> None:
        self._client = client
        self._require_safety = require_safety
        self._verify_signature = verify_signature
        # Injectable fetcher (live query). Default: ask AgentGraph for the endpoint's
        # signed safety attestation. Override in tests or to point at a cache.
        self._fetch = fetch_attestation or self._default_fetch

    async def _default_fetch(self, endpoint_url: str) -> dict | None:
        if self._client is None:
            raise ValueError(
                "X402SafetyGuard needs an AgentGraphClient or a fetch_attestation callable"
            )
        # live verdict query — AgentGraph remains the issuer/aggregator
        return await self._client._request(
            "GET", "/x402/attestation", params={"endpoint": endpoint_url}
        )

    async def check(self, endpoint_url: str) -> dict[str, Any]:
        """Return the safety verdict for ``endpoint_url``; raise PaymentRefused on deny.

        Verifies the attestation signature client-side before trusting the verdict.
        """
        attestation = await self._fetch(endpoint_url)

        if attestation and self._verify_signature and self._client is not None:
            res = await self._client.verify_envelope(attestation)
            if not res:
                refused = {"verdict": "deny", "reason": "attestation_signature_invalid"}
                raise PaymentRefused(endpoint_url, refused)

        verdict = evaluate(attestation)

        if verdict["verdict"] == "deny":
            raise PaymentRefused(endpoint_url, verdict)
        if verdict.get("reason") == "no_safety_attestation" and self._require_safety:
            refused = {"verdict": "deny", "reason": "no_safety_attestation_and_required"}
            raise PaymentRefused(endpoint_url, refused)
        return verdict

    async def guarded_pay(
        self, endpoint_url: str, pay_fn: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Check safety, then run ``pay_fn`` only if admitted."""
        await self.check(endpoint_url)
        return await pay_fn()


__all__ = ["X402SafetyGuard", "PaymentRefused", "evaluate"]
