"""Tests for Perspective API toxicity scoring."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.toxicity import ToxicityResult, score_toxicity


def test_toxicity_result_should_block():
    """High severe_toxicity or threat triggers block."""
    r = ToxicityResult(available=True, severe_toxicity=0.90, threat=0.50)
    assert r.should_block is True

    r2 = ToxicityResult(available=True, threat=0.90)
    assert r2.should_block is True

    r3 = ToxicityResult(available=True, toxicity=0.90)
    assert r3.should_block is True


def test_toxicity_result_should_not_block_below_threshold():
    r = ToxicityResult(available=True, toxicity=0.60, severe_toxicity=0.30)
    assert r.should_block is False


def test_toxicity_result_should_flag():
    r = ToxicityResult(available=True, toxicity=0.75)
    assert r.should_flag is True
    assert r.should_block is False


def test_toxicity_result_unavailable_never_blocks():
    r = ToxicityResult(available=False, toxicity=0.99, severe_toxicity=0.99)
    assert r.should_block is False
    assert r.should_flag is False


def test_toxicity_result_max_score():
    r = ToxicityResult(available=True, toxicity=0.3, insult=0.8, profanity=0.5)
    assert r.max_score == 0.8


def test_toxicity_result_max_score_unavailable():
    r = ToxicityResult(available=False)
    assert r.max_score == 0.0


@pytest.mark.asyncio
async def test_score_toxicity_no_api_key():
    """Without API key, returns unavailable (graceful degradation)."""
    with patch("src.toxicity.settings") as mock_settings:
        mock_settings.perspective_api_key = None
        result = await score_toxicity("some text")
    assert result.available is False
    assert result.should_block is False


@pytest.mark.asyncio
async def test_score_toxicity_empty_text():
    """Empty or very short text returns unavailable."""
    with patch("src.toxicity.settings") as mock_settings:
        mock_settings.perspective_api_key = "fake-key"
        result = await score_toxicity("")
    assert result.available is False

    with patch("src.toxicity.settings") as mock_settings:
        mock_settings.perspective_api_key = "fake-key"
        result2 = await score_toxicity("hi")
    assert result2.available is False


@pytest.mark.asyncio
async def test_score_toxicity_api_success():
    """Successful API call parses scores correctly."""
    from unittest.mock import MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "attributeScores": {
            "TOXICITY": {"summaryScore": {"value": 0.85}},
            "SEVERE_TOXICITY": {"summaryScore": {"value": 0.20}},
            "IDENTITY_ATTACK": {"summaryScore": {"value": 0.10}},
            "INSULT": {"summaryScore": {"value": 0.45}},
            "PROFANITY": {"summaryScore": {"value": 0.30}},
            "THREAT": {"summaryScore": {"value": 0.05}},
        }
    }

    with patch("src.toxicity.settings") as mock_settings, \
         patch("src.toxicity.httpx.AsyncClient") as mock_client_cls:
        mock_settings.perspective_api_key = "fake-key"
        mock_settings.perspective_timeout = 5
        mock_settings.perspective_toxicity_block = 0.85
        mock_settings.perspective_toxicity_flag = 0.70

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = await score_toxicity("you are terrible and should go away")

    assert result.available is True
    assert result.toxicity == 0.85
    assert result.severe_toxicity == 0.20
    assert result.threat == 0.05
    assert result.should_block is True  # toxicity >= 0.85


@pytest.mark.asyncio
async def test_score_toxicity_api_error():
    """API returning non-200 degrades gracefully."""
    from unittest.mock import MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.text = "rate limited"

    with patch("src.toxicity.settings") as mock_settings, \
         patch("src.toxicity.httpx.AsyncClient") as mock_client_cls:
        mock_settings.perspective_api_key = "fake-key"
        mock_settings.perspective_timeout = 5

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = await score_toxicity("some text here")

    assert result.available is False
    assert result.error == "HTTP 429"
    assert result.should_block is False


@pytest.mark.asyncio
async def test_score_toxicity_timeout():
    """Timeout degrades gracefully."""
    import httpx as real_httpx

    with patch("src.toxicity.settings") as mock_settings, \
         patch("src.toxicity.httpx.AsyncClient") as mock_client_cls:
        mock_settings.perspective_api_key = "fake-key"
        mock_settings.perspective_timeout = 5

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.side_effect = real_httpx.TimeoutException("timed out")
        mock_client_cls.return_value = mock_client

        result = await score_toxicity("some text here")

    assert result.available is False
    assert result.error == "timeout"
    assert result.should_block is False
