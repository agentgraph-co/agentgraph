"""Google Perspective API integration for text toxicity scoring.

Gracefully degrades when API key is not configured or API is unreachable.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

PERSPECTIVE_URL = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"

ATTRIBUTES = [
    "TOXICITY",
    "SEVERE_TOXICITY",
    "IDENTITY_ATTACK",
    "INSULT",
    "PROFANITY",
    "THREAT",
]


@dataclass
class ToxicityResult:
    """Scores from Perspective API (0.0 = safe, 1.0 = toxic)."""

    available: bool = False
    toxicity: float = 0.0
    severe_toxicity: float = 0.0
    identity_attack: float = 0.0
    insult: float = 0.0
    profanity: float = 0.0
    threat: float = 0.0
    error: str | None = None
    _scores: dict[str, float] = field(default_factory=dict, repr=False)

    @property
    def max_score(self) -> float:
        if not self.available:
            return 0.0
        return max(self.toxicity, self.severe_toxicity, self.identity_attack,
                   self.insult, self.profanity, self.threat)

    @property
    def should_block(self) -> bool:
        """Content should be rejected outright."""
        if not self.available:
            return False
        return (
            self.severe_toxicity >= settings.perspective_toxicity_block
            or self.threat >= settings.perspective_toxicity_block
            or self.toxicity >= settings.perspective_toxicity_block
        )

    @property
    def should_flag(self) -> bool:
        """Content should be flagged for review (but allowed through)."""
        if not self.available:
            return False
        return (
            self.toxicity >= settings.perspective_toxicity_flag
            or self.identity_attack >= settings.perspective_toxicity_flag
        )


async def score_toxicity(text: str) -> ToxicityResult:
    """Score text toxicity via Google Perspective API.

    Returns ToxicityResult with available=False if:
    - API key not configured (graceful degradation)
    - API unreachable or returns error
    - Text is empty or too short to analyze
    """
    if not settings.perspective_api_key:
        return ToxicityResult(available=False)

    if not text or len(text.strip()) < 5:
        return ToxicityResult(available=False)

    # Perspective API has a 20KB limit on text
    truncated = text[:20000] if len(text) > 20000 else text

    payload = {
        "comment": {"text": truncated},
        "requestedAttributes": {attr: {} for attr in ATTRIBUTES},
        "languages": ["en"],
        "doNotStore": True,
    }

    try:
        async with httpx.AsyncClient(timeout=settings.perspective_timeout) as client:
            resp = await client.post(
                PERSPECTIVE_URL,
                params={"key": settings.perspective_api_key},
                json=payload,
            )

        if resp.status_code != 200:
            logger.warning("Perspective API returned %d: %s", resp.status_code, resp.text[:200])
            return ToxicityResult(available=False, error=f"HTTP {resp.status_code}")

        data = resp.json()
        scores = data.get("attributeScores", {})

        def _get(attr: str) -> float:
            return scores.get(attr, {}).get("summaryScore", {}).get("value", 0.0)

        result = ToxicityResult(
            available=True,
            toxicity=_get("TOXICITY"),
            severe_toxicity=_get("SEVERE_TOXICITY"),
            identity_attack=_get("IDENTITY_ATTACK"),
            insult=_get("INSULT"),
            profanity=_get("PROFANITY"),
            threat=_get("THREAT"),
        )

        if result.should_block:
            logger.info(
                "Perspective API blocked content: toxicity=%.2f severe=%.2f threat=%.2f",
                result.toxicity, result.severe_toxicity, result.threat,
            )

        return result

    except httpx.TimeoutException:
        logger.warning("Perspective API timed out after %ds", settings.perspective_timeout)
        return ToxicityResult(available=False, error="timeout")
    except Exception as exc:
        logger.warning("Perspective API error: %s", exc)
        return ToxicityResult(available=False, error=str(exc))
