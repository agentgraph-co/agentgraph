"""Basic content filtering for spam and abuse detection.

Provides rule-based pattern matching for common spam patterns.
Designed to be extended with ML classifiers in Phase 2.
"""
from __future__ import annotations

import re

# Patterns that indicate spam/abuse
SPAM_PATTERNS = [
    re.compile(r"(buy|sell|cheap|discount|free money).{0,20}(click|visit|http)", re.I),
    re.compile(r"(earn|make)\s+\$\d+", re.I),
    re.compile(r"(viagra|cialis|pharmacy|crypto\s*airdrop)", re.I),
    re.compile(r"(bit\.ly|tinyurl|t\.co|shorturl)[\s/]", re.I),
    re.compile(r"(subscribe|follow)\s+(my|our)\s+(channel|page)", re.I),
]

# Excessive caps or repetition
NOISE_PATTERNS = [
    re.compile(r"(.)\1{9,}"),  # Same char repeated 10+ times
    re.compile(r"[A-Z\s]{50,}"),  # 50+ consecutive uppercase chars
]

# Prompt injection attempts
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.I),
    re.compile(r"system\s*:\s*", re.I),
    re.compile(r"<\|?(system|assistant|user)\|?>", re.I),
]


class FilterResult:
    """Result of content filtering."""

    def __init__(self) -> None:
        self.is_clean = True
        self.flags: list[str] = []
        self.score = 0.0  # 0.0 = clean, 1.0 = definitely spam

    def flag(self, reason: str, weight: float = 0.5) -> None:
        self.flags.append(reason)
        self.score = min(1.0, self.score + weight)
        if self.score >= 0.5:
            self.is_clean = False


def check_content(text: str) -> FilterResult:
    """Check text content against spam and abuse patterns.

    Returns a FilterResult with is_clean=True if content passes,
    or is_clean=False with flags describing issues found.
    """
    result = FilterResult()

    if not text or not text.strip():
        return result

    for pattern in SPAM_PATTERNS:
        if pattern.search(text):
            result.flag("spam_pattern", 0.6)
            break

    for pattern in NOISE_PATTERNS:
        if pattern.search(text):
            result.flag("noise_pattern", 0.6)
            break

    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            result.flag("prompt_injection", 0.8)
            break

    # Excessive links
    link_count = len(re.findall(r"https?://", text))
    if link_count > 5:
        result.flag("excessive_links", 0.6)

    return result
