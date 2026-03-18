"""Async Ollama client for local LLM inference (Qwen 3.5 9B)."""
from __future__ import annotations

import logging

import httpx

from src.marketing.config import marketing_settings
from src.marketing.llm.anthropic_client import LLMResponse

logger = logging.getLogger(__name__)


async def generate(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> LLMResponse:
    """Call the local Ollama /api/chat endpoint.

    Uses the same LLMResponse dataclass for consistency.
    Cost is always $0 (local inference).
    """
    resolved_model = model or marketing_settings.ollama_model
    base_url = marketing_settings.ollama_url
    timeout = marketing_settings.ollama_timeout

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body = {
        "model": resolved_model,
        "messages": messages,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": temperature,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{base_url}/api/chat", json=body)
            resp.raise_for_status()
            data = resp.json()

        text = data.get("message", {}).get("content", "")
        # Ollama reports token counts in eval_count / prompt_eval_count
        tokens_in = data.get("prompt_eval_count", 0)
        tokens_out = data.get("eval_count", 0)

        return LLMResponse(
            text=text.strip(),
            model=resolved_model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
    except httpx.ConnectError:
        logger.warning("Ollama not reachable at %s", base_url)
        return LLMResponse(
            text="", model=resolved_model, tokens_in=0, tokens_out=0,
            error=f"Ollama not reachable at {base_url}",
        )
    except Exception as exc:
        logger.exception("Ollama call failed")
        return LLMResponse(
            text="", model=resolved_model, tokens_in=0, tokens_out=0,
            error=str(exc),
        )


async def is_available() -> bool:
    """Check if Ollama is running and the model is available."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{marketing_settings.ollama_url}/api/tags")
            if resp.status_code != 200:
                return False
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            return any(marketing_settings.ollama_model in m for m in models)
    except Exception:
        return False
