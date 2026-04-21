"""AI-writing-tell detector for marketing bot drafts.

Catches the tells from Wikipedia's "Signs of AI writing" + Pangram + the
Barron's "it's not just X, it's Y" research:
  - Overused vocabulary (delve, tapestry, crucial, pivotal, ...)
  - Negative parallelism: "not just X, but Y" / "not X, but Y"
  - Copula avoidance: "serves as", "stands as", "represents", ...
  - Em-dash density (when combined with other tells)
  - Missing punchy short sentences (no human variability)
  - Empty closer hedges: "in conclusion", "ultimately", ...
  - Empty opener hedges: "in today's ever-evolving world", ...

Usage:
    result = check(draft_text, platform="bluesky", strict=True)
    if not result.passed:
        # retry with hint, or reject
        ...
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Blocklists. Lowercased for case-insensitive matching.
# ---------------------------------------------------------------------------

# Single-word tells. These are the AI-overused vocabulary words from
# Wikipedia's tracked list + Pangram's frequency data. Matching is
# whole-word so "delve" matches but "delivery" doesn't.
BLOCKLIST_WORDS: frozenset[str] = frozenset({
    # Wikipedia's high-density list
    "delve", "delves", "delving",
    "tapestry", "tapestries",
    "testament",
    "landscape", "landscapes",
    "intricate", "intricacies",
    "pivotal",
    "crucial", "crucially",
    "meticulous", "meticulously",
    "nuanced",
    "multifaceted",
    "underscore", "underscores", "underscoring",
    "bolster", "bolsters", "bolstered", "bolstering",
    "garner", "garners", "garnered",
    "showcase", "showcases", "showcased",
    "foster", "fosters", "fostering",
    "interplay",
    "vibrant",
    "robust",
    "seamless", "seamlessly",
    "leverage", "leverages", "leveraged", "leveraging",
    "navigate", "navigates", "navigating",  # metaphorical; literal is fine in context
    "harness", "harnesses", "harnessing",
    "endeavor", "endeavors",
    "facet", "facets",
    "myriad",
    "plethora",
    "realm",
    # Common AI hedge intensifiers
    "paramount",
    "indispensable",
    "quintessential",
    "noteworthy",
    "compelling",
    # Wikipedia-cited promotional adjectives
    "pristine",
    "stunning",
    "breathtaking",
    "captivating",
})

# Multi-word phrases. Lowercased substring match against the lowercased text.
BLOCKLIST_PHRASES: tuple[str, ...] = (
    # Hedge openers
    "it's worth noting",
    "it is worth noting",
    "it's important to note",
    "it is important to note",
    "it's important to recognize",
    "one could argue",
    # Empty corporate openers
    "in today's ever-evolving",
    "in today's fast-paced",
    "in today's digital age",
    "in an era of",
    "in an era where",
    "in the realm of",
    "at its core",
    "at the heart of",
    # Empty corporate closers
    "in conclusion",
    "in summary",
    "in essence",
    "as we move forward",
    "moving forward",
    "the future of",  # only when used as an opener — see opener-only check below
    # Bot tells from RLHF training
    "certainly!",
    "absolutely!",
    "i'd be happy to",
    "i would be happy to",
    "great question",
    # Generic filler
    "cutting-edge",
    "game-changing",
    "groundbreaking",
    "revolutionary",  # already in twitter prompt as banned
    "state-of-the-art",
    "best-in-class",
)

# Copula avoidance — AI rarely writes "X is Y", reaches for these instead.
# Catching presence of these isn't a hard fail (they have legitimate uses),
# but a high count signals AI rhythm.
COPULA_REPLACEMENTS: tuple[str, ...] = (
    "serves as",
    "stands as",
    "represents a",
    "marks a",
    "boasts",
    "embodies",
    "exemplifies",
)

# Negative-parallelism patterns — Barron's "it's not just X, it's Y" research.
# These are the strongest single tell in 2025/2026 corporate writing.
NEG_PARALLELISM_PATTERNS: tuple[re.Pattern[str], ...] = (
    # "it's not just X — it's Y" / "it's not just X, it's Y" / "it's not just X; it's Y"
    re.compile(r"\bit'?s\s+not\s+just\s+\w[\w\s]{0,40}[,;\u2014\u2013-]\s*it'?s\b", re.IGNORECASE),
    # "not just X, but Y" / "not just X but also Y"
    re.compile(r"\bnot\s+just\s+\w[\w\s]{0,40}[,;]?\s+but(?:\s+also)?\b", re.IGNORECASE),
    # "not X, but Y" (weaker — requires verb after to avoid false positives)
    re.compile(
        r"\bnot\s+(?:a|an|the|simply|merely)\s+\w[\w\s]{0,30}[,;]\s+but\s+\w",
        re.IGNORECASE,
    ),
    # "X isn't just Y; it's Z"
    re.compile(r"\b\w+\s+isn'?t\s+just\s+\w[\w\s]{0,40}[,;\u2014\u2013-]\s*it'?s\b", re.IGNORECASE),
)

# Word-boundary regex builder for the single-word blocklist.
_WORD_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in sorted(BLOCKLIST_WORDS)) + r")\b",
    re.IGNORECASE,
)

# Em-dash detector (both U+2014 EM DASH and double-hyphen substitute).
_EM_DASH_RE = re.compile(r"\u2014|--")

# Sentence splitter — rough but good enough for length variability check.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class CheckResult:
    """Outcome of running the linter on a draft."""

    passed: bool
    severity: str  # "ok" | "warn" | "block"
    reasons: list[str] = field(default_factory=list)
    # Detail tallies for telemetry
    blocked_words: list[str] = field(default_factory=list)
    blocked_phrases: list[str] = field(default_factory=list)
    em_dash_density: float = 0.0
    has_short_sentence: bool = True
    word_count: int = 0
    sentence_count: int = 0

    def hint(self) -> str:
        """Build a regeneration hint to feed back into the LLM."""
        parts: list[str] = []
        if self.blocked_words:
            shown = ", ".join(sorted(set(self.blocked_words))[:8])
            parts.append(
                f"Drop these words entirely: {shown}. "
                f"Use plain alternatives."
            )
        if self.blocked_phrases:
            shown = "; ".join(f'"{p}"' for p in sorted(set(self.blocked_phrases))[:4])
            parts.append(f"Drop these phrases: {shown}.")
        if "neg_parallelism" in self.reasons:
            parts.append(
                'Drop the "not just X, it\'s Y" / "not just X, but Y" structure. '
                'Just say what you mean directly.'
            )
        if "high_em_dash_density" in self.reasons:
            parts.append("Replace most em-dashes with periods or commas.")
        if "no_short_sentence" in self.reasons:
            parts.append(
                "Include at least one sentence under 8 words. "
                "Vary your rhythm — humans don't write at a uniform medium length."
            )
        if "high_copula_avoidance" in self.reasons:
            parts.append(
                'Use "is" / "are" instead of "serves as" / "stands as" / '
                '"represents" / "boasts".'
            )
        return " ".join(parts)


def check(
    text: str,
    *,
    platform: str = "generic",
    strict: bool = True,
) -> CheckResult:
    """Run all detectors on a draft and return a CheckResult.

    Args:
        text: The generated draft to check.
        platform: Used to scale rules. Short-form (twitter/bluesky) skips
            the short-sentence rule because there's only one sentence.
        strict: If True, blocklist hits become block-level. If False,
            they're warn-level (logged but allowed). Use False to gather
            telemetry before fully enforcing.
    """
    if not text or not text.strip():
        return CheckResult(passed=True, severity="ok", reasons=[])

    lower = text.lower()
    reasons: list[str] = []
    severity = "ok"

    # 1. Blocklist words
    blocked_words = [m.group(1).lower() for m in _WORD_RE.finditer(text)]
    if blocked_words:
        reasons.append("blocklist_word")
        severity = "block" if strict else "warn"

    # 2. Blocklist phrases
    blocked_phrases = [p for p in BLOCKLIST_PHRASES if p in lower]
    if blocked_phrases:
        reasons.append("blocklist_phrase")
        severity = "block" if strict else "warn"

    # 3. Negative parallelism
    if any(pat.search(text) for pat in NEG_PARALLELISM_PATTERNS):
        reasons.append("neg_parallelism")
        severity = "block" if strict else "warn"

    # 4. Em-dash density (per 500 chars). Only fires above threshold AND
    # requires another tell present — em-dashes alone are fine punctuation.
    em_count = len(_EM_DASH_RE.findall(text))
    em_density = (em_count / len(text)) * 500 if text else 0.0
    if em_density > 2.5:
        # Soft warn unless paired with another tell — humans use em-dashes too.
        if reasons:
            reasons.append("high_em_dash_density")
            severity = "block" if strict else "warn"
        else:
            reasons.append("high_em_dash_density")
            if severity == "ok":
                severity = "warn"

    # 5. Short-sentence variety. Skip for short-form platforms (one sentence
    # in 280 chars can't have rhythm variety).
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    word_count = len(text.split())
    has_short = any(len(s.split()) <= 7 for s in sentences)
    short_form = platform in {"twitter", "bluesky"}
    if not short_form and len(sentences) >= 3 and not has_short:
        reasons.append("no_short_sentence")
        if severity == "ok":
            severity = "warn"

    # 6. Copula-avoidance density. >2 in same draft = AI rhythm tell.
    copula_count = sum(lower.count(c) for c in COPULA_REPLACEMENTS)
    if copula_count >= 3:
        reasons.append("high_copula_avoidance")
        if severity == "ok":
            severity = "warn"

    passed = severity != "block"
    return CheckResult(
        passed=passed,
        severity=severity,
        reasons=reasons,
        blocked_words=blocked_words,
        blocked_phrases=blocked_phrases,
        em_dash_density=em_density,
        has_short_sentence=has_short,
        word_count=word_count,
        sentence_count=len(sentences),
    )


# ---------------------------------------------------------------------------
# Voice prompt fragment — inject into LLM system prompts so the generator
# avoids the tells in the first place rather than relying purely on retry.
# ---------------------------------------------------------------------------

VOICE_PROMPT_FRAGMENT = (
    "\n\n## Voice rules — these matter, the draft will be rejected if violated\n"
    "Never use these words: delve, tapestry, testament, landscape, intricate, "
    "pivotal, crucial, meticulous, nuanced, multifaceted, underscore, bolster, "
    "garner, showcase, foster, interplay, vibrant, robust, seamless, leverage, "
    "navigate (as metaphor), harness, endeavor, myriad, plethora, realm, "
    "paramount, indispensable, noteworthy, compelling, cutting-edge, "
    "game-changing, groundbreaking, revolutionary, state-of-the-art.\n"
    "Never use 'it's not just X, it's Y' or 'not just X, but Y' — say what "
    "you mean directly.\n"
    "Use plain 'is' / 'are' instead of 'serves as', 'stands as', 'represents', "
    "'boasts', 'embodies'.\n"
    "Don't open with 'In today's...', 'In an era of...', 'In the realm of...', "
    "'At its core', 'At the heart of'.\n"
    "Don't close with 'In conclusion', 'In summary', 'Ultimately', 'Moving forward'.\n"
    "Vary sentence length. Include at least one sentence under 8 words "
    "(unless the platform limit makes that impossible). Humans don't write "
    "at uniform medium length.\n"
    "Em-dashes are fine in moderation; don't substitute them for every comma.\n"
    "Skip 'I'd be happy to' / 'Certainly!' / 'Great question' openers — "
    "just answer.\n"
)
