"""Demo: an x402 agent that refuses to pay an unsafe endpoint.

    python3 x402_refuse_to_pay.py

Shows the core "score before money moves" bet: the agent asks AgentGraph for each
endpoint's signed safety verdict and only pays the ones graded clean. Uses stub
verdicts so it runs offline; in production drop in an AgentGraphClient and the guard
fetches + signature-verifies live.
"""
from __future__ import annotations

import asyncio

from agentgraph_sdk.x402_guard import PaymentRefused, X402SafetyGuard

# Stand-in for AgentGraph's live verdict service (one signed attestation per endpoint).
_VERDICTS = {
    "https://clean-api.example/x402": {
        "attestation": {"payload": {"grade": "A", "findings": {"critical": 0, "high": 0, "medium": 1}}}
    },
    "https://leaky-api.example/x402": {
        "attestation": {"payload": {"grade": "F", "findings": {"critical": 1, "high": 2, "medium": 0}}}
    },
    "https://unknown-api.example/x402": None,  # never scanned
}


async def main() -> None:
    async def fetch(url):
        return _VERDICTS.get(url)

    guard = X402SafetyGuard(fetch_attestation=fetch, verify_signature=False)

    for url in _VERDICTS:
        async def pay():
            return f"💸 paid {url}"

        try:
            print(await guard.guarded_pay(url, pay))
        except PaymentRefused as e:
            print(f"🛑 {e}")


if __name__ == "__main__":
    asyncio.run(main())
