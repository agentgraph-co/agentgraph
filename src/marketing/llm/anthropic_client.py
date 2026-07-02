"""Thin async wrapper around the Anthropic Messages API using httpx."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

from src.marketing.config import marketing_settings

logger = logging.getLogger(__name__)

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
# Granular timeouts: fail the CONNECT fast (so a transient blip retries quickly)
# but keep a long READ — Sonnet blog posts genuinely take a while to generate.
_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
_MAX_ATTEMPTS = 3
# Transient network faults worth retrying (ConnectTimeout is the Sentry case).
_RETRYABLE_NET = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
)
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""

    text: str
    model: str
    tokens_in: int
    tokens_out: int
    error: str | None = None


async def generate(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> LLMResponse:
    """Call the Anthropic Messages API.

    Returns an LLMResponse with text and token counts.
    On failure, returns an LLMResponse with error set.
    """
    api_key = marketing_settings.anthropic_api_key
    if not api_key:
        return LLMResponse(
            text="", model=model or "", tokens_in=0, tokens_out=0,
            error="ANTHROPIC_API_KEY not configured",
        )

    resolved_model = model or marketing_settings.anthropic_haiku_model

    messages = [{"role": "user", "content": prompt}]
    body: dict = {
        "model": resolved_model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    # Opus 4.7+ rejects temperature/top_p/top_k with a 400 error — omit for those models.
    # See https://platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-7
    if not resolved_model.startswith("claude-opus-4-7"):
        body["temperature"] = temperature
    if system:
        body["system"] = system

    headers = {
        "x-api-key": api_key,
        "anthropic-version": _API_VERSION,
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            for attempt in range(1, _MAX_ATTEMPTS + 1):
                try:
                    resp = await client.post(_API_URL, json=body, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    text = "".join(
                        block.get("text", "")
                        for block in data.get("content", [])
                        if block.get("type") == "text"
                    )
                    usage = data.get("usage", {})
                    return LLMResponse(
                        text=text.strip(),
                        model=resolved_model,
                        tokens_in=usage.get("input_tokens", 0),
                        tokens_out=usage.get("output_tokens", 0),
                    )
                except _RETRYABLE_NET as exc:
                    # Transient network fault (e.g. ConnectTimeout). Retry with backoff;
                    # only escalate to a real error once all attempts are exhausted, so a
                    # recovered blip doesn't page Sentry.
                    if attempt < _MAX_ATTEMPTS:
                        backoff = 2.0 ** (attempt - 1)  # 1s, 2s
                        logger.warning(
                            "Anthropic transient %s (attempt %d/%d) — retrying in %.0fs",
                            type(exc).__name__, attempt, _MAX_ATTEMPTS, backoff,
                        )
                        await asyncio.sleep(backoff)
                        continue
                    logger.warning(
                        "Anthropic API unreachable after %d attempts: %s",
                        _MAX_ATTEMPTS, type(exc).__name__,
                    )
                    return LLMResponse(
                        text="", model=resolved_model, tokens_in=0, tokens_out=0,
                        error=f"network: {type(exc).__name__}",
                    )
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    if status in _RETRYABLE_STATUS and attempt < _MAX_ATTEMPTS:
                        backoff = 2.0 ** (attempt - 1)
                        logger.warning(
                            "Anthropic HTTP %s (attempt %d/%d) — retrying in %.0fs",
                            status, attempt, _MAX_ATTEMPTS, backoff,
                        )
                        await asyncio.sleep(backoff)
                        continue
                    logger.warning("Anthropic API error %s: %s", status, exc.response.text[:200])
                    return LLMResponse(
                        text="", model=resolved_model, tokens_in=0, tokens_out=0,
                        error=f"HTTP {status}",
                    )
    except Exception as exc:
        logger.exception("Anthropic API call failed (unexpected)")
        return LLMResponse(
            text="", model=resolved_model, tokens_in=0, tokens_out=0,
            error=str(exc),
        )
    # Unreachable in practice — every path above returns — but satisfies type checkers.
    return LLMResponse(
        text="", model=resolved_model, tokens_in=0, tokens_out=0,
        error="no response",
    )
