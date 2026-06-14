"""Keyword matching for the AI Agent News feed."""
from __future__ import annotations

import re

# Phrases to match (case-insensitive, word-boundary aware)
KEYWORDS: list[str] = [
    "ai agent",
    "ai agents",
    "mcp server",
    "mcp servers",
    "agent trust",
    "autonomous agent",
    "tool use",
    "agentic",
    "agent identity",
    "verifiable credential",
    "agent framework",
    "langchain agent",
    "crewai",
    "autogen",
    "agent orchestration",
    "agentgraph",
    "agent protocol",
    "multi-agent",
    "multiagent",
    "agent-to-agent",
    "agent swarm",
    "function calling",
    "tool calling",
    "agent memory",
    "agent planning",
    "model context protocol",
]

# Pre-compile a single regex for fast matching
_PATTERN = re.compile(
    "|".join(re.escape(kw) for kw in KEYWORDS),
    re.IGNORECASE,
)


def matches_keywords(text: str) -> list[str]:
    """Return list of matched keywords in text. Empty if no match.

    Guards against non-string input — Bluesky records without a text field
    (reposts, some embeds) surface ``text`` as None, which crashed the Jetstream
    subscriber on ``_PATTERN.finditer`` (expected string or bytes-like object).
    """
    if not isinstance(text, str):
        return []
    return list({m.group().lower() for m in _PATTERN.finditer(text)})
