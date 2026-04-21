"""Tests for the AI-writing-tell linter (src/marketing/content/ai_tells.py).

Validates that obvious AI-written drafts get flagged and clean human-style
drafts pass cleanly.
"""
from __future__ import annotations

from src.marketing.content.ai_tells import (
    BLOCKLIST_PHRASES,
    BLOCKLIST_WORDS,
    VOICE_PROMPT_FRAGMENT,
    check,
)


# --- Negative cases (should be blocked) ----------------------------------


def test_blocklist_word_blocks_draft():
    """A draft containing 'delve' should be blocked."""
    text = "Let's delve into how agent identity works in production."
    r = check(text, platform="bluesky", strict=True)
    assert not r.passed
    assert "blocklist_word" in r.reasons
    assert "delve" in r.blocked_words


def test_multiple_tell_words_caught():
    """Tapestry + meticulous + crucial — full house."""
    text = (
        "AgentGraph is a tapestry of meticulous trust signals — "
        "a crucial layer for the agent landscape."
    )
    r = check(text, platform="github_discussions", strict=True)
    assert not r.passed
    assert {"tapestry", "meticulous", "crucial", "landscape"}.issubset(
        set(r.blocked_words),
    )


def test_neg_parallelism_its_not_just_blocked():
    """The signature 2025/26 corporate AI tell."""
    text = "It's not just a trust score, it's a verifiable attestation."
    r = check(text, platform="twitter", strict=True)
    assert not r.passed
    assert "neg_parallelism" in r.reasons


def test_neg_parallelism_not_just_but_also_blocked():
    text = "These systems are not just executing tasks, but also adapting."
    r = check(text, platform="linkedin", strict=True)
    assert not r.passed
    assert "neg_parallelism" in r.reasons


def test_blocklist_phrase_in_today_blocked():
    text = (
        "In today's ever-evolving agent ecosystem, identity matters more "
        "than ever before."
    )
    r = check(text, platform="devto", strict=True)
    assert not r.passed
    assert "blocklist_phrase" in r.reasons


def test_blocklist_phrase_in_conclusion_blocked():
    text = (
        "We shipped the gateway and verified end-to-end. The latency held. "
        "Tests passed. In conclusion, the rollout went smoothly."
    )
    r = check(text, platform="devto", strict=True)
    assert not r.passed
    assert "blocklist_phrase" in r.reasons


# --- Positive cases (should pass) ----------------------------------------


def test_clean_draft_passes():
    """A short technical draft with no tells should pass."""
    text = (
        "Shipped /gateway/re-verify today. 30s TTL, no-store, fail-closed "
        "on missing attestation. Smoke-tested in prod, 5.9ms latency."
    )
    r = check(text, platform="bluesky", strict=True)
    assert r.passed, f"reasons: {r.reasons}, blocked: {r.blocked_words}"


def test_short_form_skips_short_sentence_rule():
    """Twitter and Bluesky shouldn't trip 'no_short_sentence'."""
    text = "Trust scoring for AI agents now lives behind a single endpoint."
    r = check(text, platform="twitter", strict=True)
    assert r.passed
    assert "no_short_sentence" not in r.reasons


def test_long_form_with_short_sentence_passes():
    text = (
        "We rebuilt the verify endpoint. It now signs every verdict with "
        "EdDSA. Latency dropped from 40ms to 6ms after we stopped fetching "
        "the cert chain on every call. Worth it."
    )
    r = check(text, platform="github_discussions", strict=True)
    assert r.passed, f"reasons: {r.reasons}"


def test_long_form_without_short_sentence_warns():
    """Long-form draft with all medium-length sentences flags rhythm tell."""
    text = (
        "We have implemented a new verification endpoint for all agents. "
        "The endpoint signs every single verdict using the EdDSA algorithm. "
        "Latency has improved significantly across our entire fleet of services."
    )
    r = check(text, platform="github_discussions", strict=True)
    # Has no blocklist hits, should still warn on rhythm
    assert "no_short_sentence" in r.reasons
    assert r.severity in {"warn", "block"}


def test_empty_text_passes():
    r = check("", platform="twitter", strict=True)
    assert r.passed


def test_hint_includes_specific_words():
    text = "We meticulously delve into the tapestry of trust signals."
    r = check(text, platform="linkedin", strict=True)
    assert not r.passed
    hint = r.hint()
    assert "delve" in hint or "tapestry" in hint or "meticulously" in hint


def test_voice_prompt_fragment_mentions_key_words():
    """Sanity: the prompt fragment names the worst tell-words."""
    assert "delve" in VOICE_PROMPT_FRAGMENT
    assert "tapestry" in VOICE_PROMPT_FRAGMENT
    assert "not just" in VOICE_PROMPT_FRAGMENT


def test_blocklists_are_lowercase():
    """All entries lowercased for case-insensitive matching."""
    assert all(w == w.lower() for w in BLOCKLIST_WORDS)
    assert all(p == p.lower() for p in BLOCKLIST_PHRASES)


def test_em_dash_density_alone_does_not_block():
    """Em-dashes alone — even several — shouldn't block. They're real punctuation."""
    text = "I shipped — finally — the verify endpoint — and it works."
    r = check(text, platform="twitter", strict=True)
    # Should warn maybe, but not block (no other tells present)
    assert r.passed or r.severity == "warn"


def test_copula_avoidance_density_warns():
    """Three 'serves as'/'represents'/'stands as' in one draft = AI rhythm."""
    text = (
        "AgentGraph serves as a trust layer. The gateway represents a verifier. "
        "The score serves as the input to enforcement decisions."
    )
    r = check(text, platform="github_discussions", strict=True)
    assert "high_copula_avoidance" in r.reasons


def test_strict_false_warns_instead_of_blocking():
    """Soft mode never blocks, only warns — useful for telemetry phase."""
    text = "Let's delve into the multifaceted tapestry."
    r = check(text, platform="bluesky", strict=False)
    assert r.passed  # soft mode passes
    assert r.severity == "warn"
    assert "blocklist_word" in r.reasons
