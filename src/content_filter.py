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


# --- HTML Sanitization ---

# Allowed tags for user-generated content (safe subset for Markdown rendering)
_ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "code", "dd", "del", "dl", "dt",
    "em", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "ins",
    "li", "ol", "p", "pre", "s", "strong", "sub", "sup", "table", "tbody",
    "td", "th", "thead", "tr", "ul",
}

# Allowed attributes per tag
_ALLOWED_ATTRIBUTES: dict[str, set[str]] = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}

# Only allow safe URL schemes
_ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


def sanitize_html(text: str) -> str:
    """Strip dangerous HTML from user-generated text.

    Uses nh3 (Rust-based ammonia bindings) for robust, spec-compliant
    HTML sanitization that cannot be bypassed by encoding tricks.

    For plain-text fields (titles, display names, etc.) that pass through
    here, we strip ALL tags and return unescaped text. For markdown/rich
    fields that may contain safe HTML, allowed tags are preserved.
    """
    if not text:
        return text

    import nh3

    return nh3.clean(
        text,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        url_schemes=_ALLOWED_URL_SCHEMES,
        strip_comments=True,
    )


def sanitize_text(text: str) -> str:
    """Strip ALL HTML tags from text, returning safe plain text.

    Use this for plain-text fields (titles, display names, summaries)
    that should never contain markup.
    """
    if not text:
        return text

    import html

    import nh3

    # Strip all HTML tags
    cleaned = nh3.clean(text, tags=set())
    # Decode entities back to plain text characters (e.g. &amp; → &)
    return html.unescape(cleaned)
