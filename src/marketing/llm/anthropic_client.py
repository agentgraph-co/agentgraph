"""Thin async wrapper around the Anthropic Messages API using httpx."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from src.marketing.config import marketing_settings

logger = logging.getLogger(__name__)

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
_TIMEOUT = 120.0  # Sonnet blog posts need longer


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
        "temperature": temperature,
    }
    if system:
        body["system"] = system

    headers = {
        "x-api-key": api_key,
        "anthropic-version": _API_VERSION,
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(_API_URL, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")

        usage = data.get("usage", {})
        return LLMResponse(
            text=text.strip(),
            model=resolved_model,
            tokens_in=usage.get("input_tokens", 0),
            tokens_out=usage.get("output_tokens", 0),
        )
    except httpx.HTTPStatusError as exc:
        logger.warning("Anthropic API error %s: %s", exc.response.status_code, exc.response.text)
        return LLMResponse(
            text="", model=resolved_model, tokens_in=0, tokens_out=0,
            error=f"HTTP {exc.response.status_code}",
        )
    except Exception as exc:
        logger.exception("Anthropic API call failed")
        return LLMResponse(
            text="", model=resolved_model, tokens_in=0, tokens_out=0,
            error=str(exc),
        )
