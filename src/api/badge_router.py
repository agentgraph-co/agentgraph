from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.rate_limit import rate_limit_reads
from src.database import get_db
from src.models import Entity, TrustScore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["trust-badges"])

_CACHE_HEADERS = {"Cache-Control": "public, max-age=3600, s-maxage=86400"}


def _trust_tier_color(score: float) -> str:
    """Return a hex color based on trust score tier."""
    if score >= 0.8:
        return "#2196F3"  # blue — highly trusted
    if score >= 0.6:
        return "#4CAF50"  # green — trusted
    if score >= 0.3:
        return "#FFC107"  # yellow — moderate
    return "#F44336"  # red — low trust


def _status_text(
    has_operator: bool,
    is_provisional: bool,
) -> str:
    """Return verification status label."""
    if is_provisional:
        return "Unclaimed"
    if has_operator:
        return "Verified"
    return "Unverified"


# ---------------------------------------------------------------------------
# Theme colors
# ---------------------------------------------------------------------------

def _theme_colors(theme: str) -> dict:
    """Return label background, label text, and value text colors for a theme."""
    if theme == "dark":
        return {
            "label_bg": "#2d2d2d",
            "label_text": "#e0e0e0",
            "mid_bg": "#3a3a3a",
            "value_text": "#fff",
            "shadow_fill": "#000",
        }
    # light (default)
    return {
        "label_bg": "#555",
        "label_text": "#fff",
        "mid_bg": "#666",
        "value_text": "#fff",
        "shadow_fill": "#010101",
    }


# ---------------------------------------------------------------------------
# Compact badge (default — matches original design)
# ---------------------------------------------------------------------------

def _render_compact_svg(
    score: float,
    has_operator: bool,
    is_provisional: bool,
    theme: str,
) -> str:
    """Two-tone pill: [AgentGraph Trust | 0.75 Verified]. Height 32px."""
    tc = _theme_colors(theme)
    label = "AgentGraph Trust"
    score_text = f"{score:.2f}"
    sub_text = _status_text(has_operator, is_provisional)
    color = _trust_tier_color(score)

    label_width = len(label) * 6.5 + 12
    value_width = max(len(score_text), len(sub_text)) * 6.5 + 12
    total_width = label_width + value_width
    label_center = label_width / 2
    value_center = label_width + value_width / 2

    font = "Verdana,Geneva,DejaVu Sans,sans-serif"
    shadow = f'fill="{tc["shadow_fill"]}" fill-opacity=".3"'

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' width="{total_width}" height="32"'
        f' role="img" aria-label="{label}: {score_text}">',
        f"  <title>{label}: {score_text} ({sub_text})</title>",
        '  <linearGradient id="s" x2="0" y2="100%">',
        '    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>',
        '    <stop offset="1" stop-opacity=".1"/>',
        "  </linearGradient>",
        '  <clipPath id="r">',
        f'    <rect width="{total_width}" height="32"'
        f' rx="4" fill="#fff"/>',
        "  </clipPath>",
        '  <g clip-path="url(#r)">',
        f'    <rect width="{label_width}" height="32"'
        f' fill="{tc["label_bg"]}"/>',
        f'    <rect x="{label_width}" width="{value_width}"'
        f' height="32" fill="{color}"/>',
        f'    <rect width="{total_width}" height="32"'
        f' fill="url(#s)"/>',
        "  </g>",
        f'  <g fill="{tc["label_text"]}" text-anchor="middle"'
        f' font-family="{font}" font-size="11">',
        f'    <text x="{label_center}" y="14"'
        f" {shadow}>{label}</text>",
        f'    <text x="{label_center}" y="13">'
        f"{label}</text>",
        "  </g>",
        f'  <g fill="{tc["value_text"]}" text-anchor="middle"'
        f' font-family="{font}" font-size="11">',
        f'    <text x="{value_center}" y="14"'
        f" {shadow}>{score_text}</text>",
        f'    <text x="{value_center}" y="13">'
        f"{score_text}</text>",
        f'    <text x="{value_center}" y="26"'
        f" font-size=\"8\" {shadow}>{sub_text}</text>",
        f'    <text x="{value_center}" y="25"'
        f' font-size="8">{sub_text}</text>',
        "  </g>",
        "</svg>",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Detailed badge
# ---------------------------------------------------------------------------

def _render_detailed_svg(
    score: float,
    has_operator: bool,
    is_provisional: bool,
    entity_name: str,
    theme: str,
) -> str:
    """Three-segment pill: [shield AgentGraph | entity_name | 0.75 check].
    Height 24px."""
    tc = _theme_colors(theme)
    score_text = f"{score:.2f}"
    color = _trust_tier_color(score)

    # Truncate entity name at 20 chars
    if len(entity_name) > 20:
        entity_name = entity_name[:19] + "\u2026"

    check = "\u2713" if has_operator and not is_provisional else "\u2717"

    left_label = "\U0001f6e1 AgentGraph"
    # Shield emoji occupies roughly 2 char widths in rendering
    left_width = (len("AgentGraph") + 3) * 6.5 + 12
    mid_width = len(entity_name) * 6.5 + 12
    right_text = f"{score_text} {check}"
    right_width = len(right_text) * 6.5 + 12
    total_width = left_width + mid_width + right_width

    left_center = left_width / 2
    mid_center = left_width + mid_width / 2
    right_center = left_width + mid_width + right_width / 2

    font = "Verdana,Geneva,DejaVu Sans,sans-serif"
    shadow = f'fill="{tc["shadow_fill"]}" fill-opacity=".3"'

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' width="{total_width}" height="24"'
        f' role="img" aria-label="AgentGraph: {entity_name} {score_text}">',
        f"  <title>AgentGraph: {entity_name} — {score_text}</title>",
        '  <linearGradient id="s" x2="0" y2="100%">',
        '    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>',
        '    <stop offset="1" stop-opacity=".1"/>',
        "  </linearGradient>",
        '  <clipPath id="r">',
        f'    <rect width="{total_width}" height="24"'
        f' rx="3" fill="#fff"/>',
        "  </clipPath>",
        '  <g clip-path="url(#r)">',
        f'    <rect width="{left_width}" height="24"'
        f' fill="{tc["label_bg"]}"/>',
        f'    <rect x="{left_width}" width="{mid_width}"'
        f' height="24" fill="{tc["mid_bg"]}"/>',
        f'    <rect x="{left_width + mid_width}" width="{right_width}"'
        f' height="24" fill="{color}"/>',
        f'    <rect width="{total_width}" height="24"'
        f' fill="url(#s)"/>',
        "  </g>",
        f'  <g text-anchor="middle"'
        f' font-family="{font}" font-size="11">',
        # Left segment
        f'    <text fill="{tc["label_text"]}" x="{left_center}" y="16"'
        f" {shadow}>{left_label}</text>",
        f'    <text fill="{tc["label_text"]}" x="{left_center}" y="15">'
        f"{left_label}</text>",
        # Middle segment
        f'    <text fill="{tc["label_text"]}" x="{mid_center}" y="16"'
        f" {shadow}>{entity_name}</text>",
        f'    <text fill="{tc["label_text"]}" x="{mid_center}" y="15">'
        f"{entity_name}</text>",
        # Right segment
        f'    <text fill="{tc["value_text"]}" x="{right_center}" y="16"'
        f" {shadow}>{right_text}</text>",
        f'    <text fill="{tc["value_text"]}" x="{right_center}" y="15">'
        f"{right_text}</text>",
        "  </g>",
        "</svg>",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Minimal badge
# ---------------------------------------------------------------------------

def _render_minimal_svg(
    score: float,
    has_operator: bool,
    is_provisional: bool,
    theme: str,
) -> str:
    """Single small pill: [check 0.75]. Height 20px."""
    score_text = f"{score:.2f}"
    color = _trust_tier_color(score)
    check = "\u2713" if has_operator and not is_provisional else "\u2717"
    text = f"{check} {score_text}"

    pill_width = len(text) * 7 + 16
    center = pill_width / 2

    font = "Verdana,Geneva,DejaVu Sans,sans-serif"
    tc = _theme_colors(theme)
    shadow = f'fill="{tc["shadow_fill"]}" fill-opacity=".3"'

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' width="{pill_width}" height="20"'
        f' role="img" aria-label="Trust: {score_text}">',
        f"  <title>AgentGraph Trust: {score_text}</title>",
        '  <linearGradient id="s" x2="0" y2="100%">',
        '    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>',
        '    <stop offset="1" stop-opacity=".1"/>',
        "  </linearGradient>",
        '  <clipPath id="r">',
        f'    <rect width="{pill_width}" height="20"'
        f' rx="3" fill="#fff"/>',
        "  </clipPath>",
        '  <g clip-path="url(#r)">',
        f'    <rect width="{pill_width}" height="20" fill="{color}"/>',
        f'    <rect width="{pill_width}" height="20" fill="url(#s)"/>',
        "  </g>",
        f'  <g fill="{tc["value_text"]}" text-anchor="middle"'
        f' font-family="{font}" font-size="11">',
        f'    <text x="{center}" y="14" {shadow}>{text}</text>',
        f'    <text x="{center}" y="13">{text}</text>',
        "  </g>",
        "</svg>",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def _render_badge_svg(
    score: float,
    has_operator: bool,
    is_provisional: bool = False,
    style: str = "compact",
    theme: str = "light",
    entity_name: str = "",
) -> str:
    """Render an SVG trust badge in the requested style and theme."""
    if style == "detailed":
        return _render_detailed_svg(
            score, has_operator, is_provisional, entity_name, theme,
        )
    if style == "minimal":
        return _render_minimal_svg(score, has_operator, is_provisional, theme)
    # compact (default)
    return _render_compact_svg(score, has_operator, is_provisional, theme)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/badges/readme/{entity_id}",
    dependencies=[Depends(rate_limit_reads)],
    responses={
        200: {"content": {"text/plain": {}}, "description": "Badge embed snippet"},
        404: {"description": "Entity not found"},
    },
)
async def get_readme_badge(
    entity_id: uuid.UUID,
    fmt: Literal["markdown", "html", "rst"] = Query(
        "markdown", alias="format",
        description="Snippet format: markdown, html, or rst",
    ),
    style: Literal["compact", "detailed", "minimal"] = Query(
        "compact", description="Badge visual style",
    ),
    theme: Literal["light", "dark"] = Query(
        "light", description="Badge color theme",
    ),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return a copy-paste snippet for embedding a trust badge in a README."""
    entity = await db.get(Entity, entity_id)
    if entity is None or not entity.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    slug = (
        entity.display_name.lower().replace(" ", "-")
        if entity.display_name
        else str(entity_id)
    )

    # Build badge URL with optional query params
    badge_url = f"https://agentgraph.co/api/v1/badges/trust/{entity_id}.svg"
    params: list[str] = []
    if style != "compact":
        params.append(f"style={style}")
    if theme != "light":
        params.append(f"theme={theme}")
    if params:
        badge_url += "?" + "&".join(params)

    profile_url = f"https://agentgraph.co/profiles/{slug}"
    alt = "AgentGraph Trust Score"

    if fmt == "html":
        snippet = (
            f'<a href="{profile_url}">'
            f'<img src="{badge_url}" alt="{alt}" />'
            f"</a>"
        )
    elif fmt == "rst":
        snippet = (
            f".. image:: {badge_url}\n"
            f"   :target: {profile_url}\n"
            f"   :alt: {alt}"
        )
    else:
        # markdown (default)
        snippet = f"[![{alt}]({badge_url})]({profile_url})"

    return Response(
        content=snippet,
        media_type="text/plain",
        headers=dict(_CACHE_HEADERS),
    )


@router.get(
    "/badges/trust/{entity_id}.svg",
    dependencies=[Depends(rate_limit_reads)],
    responses={
        200: {"content": {"image/svg+xml": {}}, "description": "SVG trust badge"},
        404: {"description": "Entity not found"},
    },
)
async def get_trust_badge_svg(
    entity_id: uuid.UUID,
    style: Literal["compact", "detailed", "minimal"] = Query(
        "compact", description="Badge visual style",
    ),
    theme: Literal["light", "dark"] = Query(
        "light", description="Badge color theme",
    ),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return an embeddable SVG badge showing an entity's trust score and
    verification status. No authentication required — badges are public."""

    entity = await db.get(Entity, entity_id)
    if entity is None or not entity.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    trust = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == entity_id)
    )
    score = trust.score if trust else 0.0
    has_operator = entity.operator_id is not None
    is_provisional = getattr(entity, "is_provisional", False) or False

    svg = _render_badge_svg(
        score=score,
        has_operator=has_operator,
        is_provisional=is_provisional,
        style=style,
        theme=theme,
        entity_name=entity.display_name or str(entity_id),
    )

    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers=dict(_CACHE_HEADERS),
    )
