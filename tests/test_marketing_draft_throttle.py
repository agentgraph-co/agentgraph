"""Regression: draft (human_review) platforms must record cadence, else every proactive
tick regenerates a fresh LinkedIn draft (the "9 drafts in one day" bug)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.marketing import orchestrator


def _content():
    return SimpleNamespace(
        error=None, text="draft body", topic="security_scanner",
        content_hash="hash1", llm_model="haiku", llm_tokens_in=1, llm_tokens_out=1,
        llm_cost_usd=0.0, utm_params={}, image_path=None,
    )


@pytest.mark.asyncio
async def test_draft_platform_records_cadence(monkeypatch):
    # Force exactly one linkedin platform down the human_review draft branch.
    monkeypatch.setattr(orchestrator, "_get_adapters", lambda: {"linkedin": MagicMock()})
    monkeypatch.setattr(
        orchestrator, "get_platform_intervals",
        AsyncMock(return_value={"linkedin": 86400}),
    )
    monkeypatch.setattr(
        orchestrator, "_post_planned_campaign_posts",
        AsyncMock(return_value={"posted": [], "skipped": [], "errors": []}),
    )
    monkeypatch.setattr(orchestrator, "_is_platform_scheduled_today", lambda p: p == "linkedin")
    monkeypatch.setattr(orchestrator, "should_post", AsyncMock(return_value=True))
    monkeypatch.setattr(orchestrator, "get_recent_topics", AsyncMock(return_value=[]))
    monkeypatch.setattr(orchestrator, "generate_proactive", AsyncMock(return_value=_content()))
    monkeypatch.setattr(orchestrator, "_is_duplicate", AsyncMock(return_value=False))
    monkeypatch.setattr(orchestrator, "enqueue_draft", AsyncMock())
    monkeypatch.setattr("src.marketing.llm.cost_tracker.get_daily_spend", AsyncMock(return_value=0.0))

    rec_post = AsyncMock()
    rec_topic = AsyncMock()
    monkeypatch.setattr(orchestrator, "record_post", rec_post)
    monkeypatch.setattr(orchestrator, "record_topic", rec_topic)

    result = await orchestrator.run_proactive_cycle(MagicMock())

    # A draft was queued AND cadence was recorded (so the next tick throttles).
    assert {"platform": "linkedin", "topic": "security_scanner"} in result["drafts"]
    rec_post.assert_awaited_once_with("linkedin")
    rec_topic.assert_awaited_once_with("linkedin", "security_scanner")
