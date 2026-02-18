from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.content_filter import sanitize_html
from src.database import get_db
from src.main import app


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"

USER = {
    "email": "xss_user@example.com",
    "password": "Str0ngP@ss",
    "display_name": "XSSUser",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup(client: AsyncClient) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=USER)
    resp = await client.post(
        LOGIN_URL, json={"email": USER["email"], "password": USER["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


# --- Unit tests for sanitize_html ---


def test_sanitize_script_tag():
    """Script tags and their content are removed."""
    assert "<script>" not in sanitize_html("<script>alert('xss')</script>")
    assert "alert" not in sanitize_html("<script>alert('xss')</script>")


def test_sanitize_event_handlers():
    """Event handler attributes are removed."""
    result = sanitize_html('<img src="x" onerror="alert(1)">')
    assert "onerror" not in result


def test_sanitize_javascript_uri():
    """javascript: URIs are neutralized."""
    result = sanitize_html('<a href="javascript:alert(1)">click</a>')
    assert "javascript:" not in result


def test_sanitize_iframe():
    """iframe tags are removed."""
    result = sanitize_html('<iframe src="evil.com"></iframe>')
    assert "<iframe" not in result


def test_sanitize_style_tag():
    """style tags and content are removed."""
    result = sanitize_html(
        "<style>body { background: url('javascript:alert(1)') }</style>text"
    )
    assert "<style>" not in result
    assert "text" in result


def test_sanitize_html_comments():
    """HTML comments are removed."""
    result = sanitize_html("before <!-- hidden --> after")
    assert "hidden" not in result
    assert "before" in result
    assert "after" in result


def test_sanitize_preserves_plain_text():
    """Plain text content is preserved."""
    text = "Hello, this is a normal post with **markdown** and _italic_."
    assert sanitize_html(text) == text


def test_sanitize_preserves_markdown():
    """Markdown formatting is preserved."""
    text = "# Heading\n\n- list item\n- another\n\n```code```"
    assert sanitize_html(text) == text


def test_sanitize_svg_tag():
    """SVG tags are removed (can contain scripts)."""
    result = sanitize_html(
        '<svg onload="alert(1)"><circle r="10"/></svg>'
    )
    assert "<svg" not in result


def test_sanitize_data_uri():
    """data: URIs are neutralized."""
    result = sanitize_html('<a href="data:text/html,<script>alert(1)</script>">')
    assert "data:" not in result


def test_sanitize_empty_and_none():
    """Empty and None inputs are handled safely."""
    assert sanitize_html("") == ""
    assert sanitize_html(None) is None


# --- Integration: posts are sanitized ---


@pytest.mark.asyncio
async def test_post_content_sanitized(client: AsyncClient, db):
    """Post creation strips dangerous HTML from content."""
    token, _ = await _setup(client)

    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": 'Hello <script>alert("xss")</script> world'},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    assert "<script>" not in resp.json()["content"]
    assert "Hello" in resp.json()["content"]
    assert "world" in resp.json()["content"]


@pytest.mark.asyncio
async def test_bio_sanitized(client: AsyncClient, db):
    """Profile bio update strips dangerous HTML."""
    token, entity_id = await _setup(client)

    resp = await client.patch(
        f"/api/v1/profiles/{entity_id}",
        json={"bio_markdown": 'My bio <iframe src="evil.com"></iframe> is here'},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert "<iframe" not in resp.json()["bio_markdown"]
    assert "My bio" in resp.json()["bio_markdown"]
