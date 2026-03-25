from __future__ import annotations

import logging
import math
import re as _re
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

_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=3600, s-maxage=86400",
    "Access-Control-Allow-Origin": "*",
    "Cross-Origin-Resource-Policy": "cross-origin",
}

# ---------------------------------------------------------------------------
# Font metrics — Verdana 11px approximate char widths (integer tenths)
# Measured from shields.io's Verdana width table.
# ---------------------------------------------------------------------------

_VERDANA_WIDTHS: dict[str, float] = {
    " ": 3.58, "!": 3.94, '"': 5.06, "#": 7.78, "$": 6.36, "%": 8.89,
    "&": 7.52, "'": 2.81, "(": 4.33, ")": 4.33, "*": 6.36, "+": 7.78,
    ",": 3.58, "-": 4.33, ".": 3.58, "/": 4.58, "0": 6.36, "1": 6.36,
    "2": 6.36, "3": 6.36, "4": 6.36, "5": 6.36, "6": 6.36, "7": 6.36,
    "8": 6.36, "9": 6.36, ":": 4.33, ";": 4.33, "<": 7.78, "=": 7.78,
    ">": 7.78, "?": 5.56, "@": 10.0, "A": 7.17, "B": 6.89, "C": 6.67,
    "D": 7.72, "E": 6.22, "F": 5.67, "G": 7.72, "H": 7.72, "I": 4.33,
    "J": 4.67, "K": 7.0, "L": 5.83, "M": 8.83, "N": 7.61, "O": 7.78,
    "P": 6.06, "Q": 7.78, "R": 6.89, "S": 6.67, "T": 6.11, "U": 7.39,
    "V": 7.17, "W": 10.17, "X": 6.33, "Y": 6.11, "Z": 6.56,
    "a": 5.94, "b": 6.39, "c": 5.17, "d": 6.39, "e": 5.94, "f": 3.83,
    "g": 6.39, "h": 6.50, "i": 2.94, "j": 3.61, "k": 6.0, "l": 2.94,
    "m": 9.78, "n": 6.50, "o": 6.28, "p": 6.39, "q": 6.39, "r": 4.50,
    "s": 5.0, "t": 4.17, "u": 6.50, "v": 5.72, "w": 8.22, "x": 5.44,
    "y": 5.72, "z": 5.0,
}
_DEFAULT_CHAR_WIDTH = 6.5


def _text_width(text: str) -> float:
    """Measure text width in pixels using Verdana 11px metrics."""
    return sum(_VERDANA_WIDTHS.get(ch, _DEFAULT_CHAR_WIDTH) for ch in text)


# ---------------------------------------------------------------------------
# Brand colors from design-system/tokens.json trust-tiers
# ---------------------------------------------------------------------------

_BRAND_TEAL = "#0D9488"
_BRAND_TEAL_BRIGHT = "#2DD4BF"


def _trust_tier_color(score: float) -> str:
    """Return a hex color based on trust score tier.

    Uses AgentGraph brand palette from design tokens.
    """
    if score >= 0.8:
        return _BRAND_TEAL_BRIGHT  # tier-3 — bright teal, highly trusted
    if score >= 0.6:
        return _BRAND_TEAL  # tier-2 — primary teal, trusted
    if score >= 0.3:
        return "#F59E0B"  # tier-1 — amber, emerging
    return "#6C7086"  # tier-0 — muted gray, unverified


def _trust_tier_label(score: float) -> str:
    """Return a human-readable trust tier label."""
    if score >= 0.8:
        return "Trusted"
    if score >= 0.6:
        return "Verified"
    if score >= 0.3:
        return "Emerging"
    return "New"


def _status_text(has_operator: bool, is_provisional: bool) -> str:
    if is_provisional:
        return "unclaimed"
    if has_operator:
        return "verified"
    return "unverified"


# ---------------------------------------------------------------------------
# SVG icon paths — tiny shield + checkmark, viewBox 0 0 10 12
# ---------------------------------------------------------------------------

# Small shield outline (10x12) — clean vector, no emoji
_SHIELD_PATH = (
    "M5 0L0 2.2v3.5c0 2.9 2.1 5.6 5 6.3 2.9-.7 5-3.4 5-6.3V2.2L5 0z"
)

# Checkmark (fits inside the shield)
_CHECK_PATH = "M3.5 7.5L2 6l-.7.7L3.5 8.9l5-5L7.8 3.2z"

# X mark (fits inside the shield)
_X_PATH = "M7.5 3.2L6.8 2.5 5 4.3 3.2 2.5l-.7.7L4.3 5 2.5 6.8l.7.7L5 5.7l1.8 1.8.7-.7L5.7 5z"


# ---------------------------------------------------------------------------
# Theme colors
# ---------------------------------------------------------------------------

def _theme_colors(theme: str) -> dict:
    if theme == "dark":
        return {
            "label_bg": _BRAND_TEAL,
            "label_text": "#fff",
            "mid_bg": "#2d2d2d",
            "mid_text": "#e0e0e0",
            "value_text": "#fff",
            "shadow_fill": "#000",
        }
    # light (default)
    return {
        "label_bg": _BRAND_TEAL,
        "label_text": "#fff",
        "mid_bg": "#555",
        "mid_text": "#fff",
        "value_text": "#fff",
        "shadow_fill": "#010101",
    }


# ---------------------------------------------------------------------------
# Compact badge (default) — 20px, shields.io compatible
# [shield AgentGraph | 0.85 verified]
# ---------------------------------------------------------------------------

def _render_compact_svg(
    score: float,
    has_operator: bool,
    is_provisional: bool,
    theme: str,
) -> str:
    tc = _theme_colors(theme)
    color = _trust_tier_color(score)
    status = _status_text(has_operator, is_provisional)
    score_text = f"{score:.2f}"
    value_label = f"{score_text} {status}"

    # Icon (shield) occupies 14px (10 icon + 4 pad)
    icon_width = 14
    label_text = "AgentGraph"
    label_text_w = _text_width(label_text)
    label_width = math.ceil(icon_width + label_text_w + 10)  # 5px pad each side

    value_text_w = _text_width(value_label)
    value_width = math.ceil(value_text_w + 10)

    total_width = label_width + value_width
    # Text centers
    label_text_x = icon_width + 3 + label_text_w / 2
    value_text_x = label_width + value_width / 2
    height = 20
    rx = 3
    font = "Verdana,Geneva,DejaVu Sans,sans-serif"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{height}" role="img" aria-label="AgentGraph Trust: {score_text}">
  <title>AgentGraph Trust: {score_text} ({status})</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r"><rect width="{total_width}" height="{height}" rx="{rx}" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="{height}" fill="{tc['label_bg']}"/>
    <rect x="{label_width}" width="{value_width}" height="{height}" fill="{color}"/>
    <rect width="{total_width}" height="{height}" fill="url(#s)"/>
  </g>
  <g transform="translate(4,4)" fill="#fff" fill-opacity=".9">
    <path d="{_SHIELD_PATH}"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="{font}" font-size="11">
    <text x="{label_text_x}" y="15" fill="{tc['shadow_fill']}" fill-opacity=".3">{label_text}</text>
    <text x="{label_text_x}" y="14">{label_text}</text>
  </g>
  <g fill="{tc['value_text']}" text-anchor="middle" font-family="{font}" font-size="11">
    <text x="{value_text_x}" y="15" fill="{tc['shadow_fill']}" fill-opacity=".3">{value_label}</text>
    <text x="{value_text_x}" y="14">{value_label}</text>
  </g>
</svg>"""


# ---------------------------------------------------------------------------
# Detailed badge — 20px, three segments with entity name
# [shield AgentGraph | WelcomeBot | 0.85 check]
# ---------------------------------------------------------------------------

def _render_detailed_svg(
    score: float,
    has_operator: bool,
    is_provisional: bool,
    entity_name: str,
    theme: str,
) -> str:
    tc = _theme_colors(theme)
    color = _trust_tier_color(score)
    score_text = f"{score:.2f}"

    if len(entity_name) > 20:
        entity_name = entity_name[:19] + "\u2026"

    # Left: shield icon + "AgentGraph"
    icon_width = 14
    left_label = "AgentGraph"
    left_text_w = _text_width(left_label)
    left_width = math.ceil(icon_width + left_text_w + 10)
    left_text_x = icon_width + 3 + left_text_w / 2

    # Middle: entity name
    mid_text_w = _text_width(entity_name)
    mid_width = math.ceil(mid_text_w + 10)
    mid_text_x = left_width + mid_width / 2

    # Right: score + check/x icon
    right_label = score_text
    right_text_w = _text_width(right_label)
    # Add space for inline check icon (10px)
    right_width = math.ceil(right_text_w + 22)
    right_text_x = left_width + mid_width + (right_width - 10) / 2
    # Check icon position — after score text
    check_x = left_width + mid_width + right_width - 14

    total_width = left_width + mid_width + right_width
    height = 20
    rx = 3
    font = "Verdana,Geneva,DejaVu Sans,sans-serif"

    is_verified = has_operator and not is_provisional
    check_icon = _CHECK_PATH if is_verified else _X_PATH
    check_color = "#fff"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{height}" role="img" aria-label="AgentGraph: {entity_name} {score_text}">
  <title>AgentGraph: {entity_name} — {score_text}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r"><rect width="{total_width}" height="{height}" rx="{rx}" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="{left_width}" height="{height}" fill="{tc['label_bg']}"/>
    <rect x="{left_width}" width="{mid_width}" height="{height}" fill="{tc['mid_bg']}"/>
    <rect x="{left_width + mid_width}" width="{right_width}" height="{height}" fill="{color}"/>
    <rect width="{total_width}" height="{height}" fill="url(#s)"/>
  </g>
  <g transform="translate(4,4)" fill="#fff" fill-opacity=".9">
    <path d="{_SHIELD_PATH}"/>
  </g>
  <g fill="{tc['label_text']}" text-anchor="middle" font-family="{font}" font-size="11">
    <text x="{left_text_x}" y="15" fill="{tc['shadow_fill']}" fill-opacity=".3">{left_label}</text>
    <text x="{left_text_x}" y="14">{left_label}</text>
  </g>
  <g fill="{tc['mid_text']}" text-anchor="middle" font-family="{font}" font-size="11">
    <text x="{mid_text_x}" y="15" fill="{tc['shadow_fill']}" fill-opacity=".3">{entity_name}</text>
    <text x="{mid_text_x}" y="14">{entity_name}</text>
  </g>
  <g fill="{tc['value_text']}" text-anchor="middle" font-family="{font}" font-size="11">
    <text x="{right_text_x}" y="15" fill="{tc['shadow_fill']}" fill-opacity=".3">{right_label}</text>
    <text x="{right_text_x}" y="14">{right_label}</text>
  </g>
  <g transform="translate({check_x},4)" fill="{check_color}">
    <path d="{check_icon}"/>
  </g>
</svg>"""


# ---------------------------------------------------------------------------
# Minimal badge — 20px, single pill with score only
# [0.85]
# ---------------------------------------------------------------------------

def _render_minimal_svg(
    score: float,
    has_operator: bool,
    is_provisional: bool,
    theme: str,
) -> str:
    color = _trust_tier_color(score)
    score_text = f"{score:.2f}"
    tc = _theme_colors(theme)

    text_w = _text_width(score_text)
    # Shield icon (small, 8px) + score
    icon_size = 10
    pill_width = math.ceil(icon_size + text_w + 14)
    text_x = icon_size + 4 + text_w / 2
    height = 20
    rx = 3
    font = "Verdana,Geneva,DejaVu Sans,sans-serif"

    is_verified = has_operator and not is_provisional
    icon_path = _SHIELD_PATH

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{pill_width}" height="{height}" role="img" aria-label="Trust: {score_text}">
  <title>AgentGraph Trust: {score_text}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r"><rect width="{pill_width}" height="{height}" rx="{rx}" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="{pill_width}" height="{height}" fill="{color}"/>
    <rect width="{pill_width}" height="{height}" fill="url(#s)"/>
  </g>
  <g transform="translate(3,4)" fill="#fff" fill-opacity="{'.9' if is_verified else '.5'}">
    <path d="{icon_path}"/>
  </g>
  <g fill="{tc['value_text']}" text-anchor="middle" font-family="{font}" font-size="11">
    <text x="{text_x}" y="15" fill="{tc['shadow_fill']}" fill-opacity=".3">{score_text}</text>
    <text x="{text_x}" y="14">{score_text}</text>
  </g>
</svg>"""


# ---------------------------------------------------------------------------
# Flat-square badge — 20px, no rounded corners, no gradient
# [shield AgentGraph | 0.85 verified]
# ---------------------------------------------------------------------------

def _render_flat_square_svg(
    score: float,
    has_operator: bool,
    is_provisional: bool,
    theme: str,
) -> str:
    tc = _theme_colors(theme)
    color = _trust_tier_color(score)
    status = _status_text(has_operator, is_provisional)
    score_text = f"{score:.2f}"
    value_label = f"{score_text} {status}"

    icon_width = 14
    label_text = "AgentGraph"
    label_text_w = _text_width(label_text)
    label_width = math.ceil(icon_width + label_text_w + 10)

    value_text_w = _text_width(value_label)
    value_width = math.ceil(value_text_w + 10)

    total_width = label_width + value_width
    label_text_x = icon_width + 3 + label_text_w / 2
    value_text_x = label_width + value_width / 2
    height = 20
    font = "Verdana,Geneva,DejaVu Sans,sans-serif"

    # Flat-square: no gradient, no rounded corners, no shadow
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{height}" role="img" aria-label="AgentGraph Trust: {score_text}">
  <title>AgentGraph Trust: {score_text} ({status})</title>
  <g>
    <rect width="{label_width}" height="{height}" fill="{tc['label_bg']}"/>
    <rect x="{label_width}" width="{value_width}" height="{height}" fill="{color}"/>
  </g>
  <g transform="translate(4,4)" fill="#fff" fill-opacity=".9">
    <path d="{_SHIELD_PATH}"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="{font}" font-size="11">
    <text x="{label_text_x}" y="14">{label_text}</text>
  </g>
  <g fill="{tc['value_text']}" text-anchor="middle" font-family="{font}" font-size="11">
    <text x="{value_text_x}" y="14">{value_label}</text>
  </g>
</svg>"""


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def _apply_scale(svg: str, scale: float) -> str:
    """Scale an SVG badge by adjusting width/height and adding viewBox."""
    m = _re.search(r'width="([\d.]+)" height="([\d.]+)"', svg)
    if not m:
        return svg
    orig_w, orig_h = float(m.group(1)), float(m.group(2))
    new_w = round(orig_w * scale, 1)
    new_h = round(orig_h * scale, 1)
    # Replace first occurrence (the svg element's dimensions)
    svg = svg.replace(
        f'width="{m.group(1)}" height="{m.group(2)}"',
        f'width="{new_w}" height="{new_h}"'
        f' viewBox="0 0 {m.group(1)} {m.group(2)}"',
        1,
    )
    return svg


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
    if style == "flat-square":
        return _render_flat_square_svg(
            score, has_operator, is_provisional, theme,
        )
    # compact (default)
    return _render_compact_svg(score, has_operator, is_provisional, theme)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

_STYLE_OPTIONS = Literal["compact", "detailed", "minimal", "flat-square"]


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
    style: _STYLE_OPTIONS = Query(
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

    badge_url = f"https://agentgraph.co/api/v1/badges/trust/{entity_id}.svg"
    params: list[str] = []
    if style != "compact":
        params.append(f"style={style}")
    if theme != "light":
        params.append(f"theme={theme}")
    # Always add scale=1.5 for README snippets (bigger badge)
    params.append("scale=1.5")
    badge_url += "?" + "&".join(params)

    profile_url = f"https://agentgraph.co/profile/{entity_id}"
    alt = "AgentGraph Trust Score"

    blurb = (
        '<sub>Verified on <a href="https://agentgraph.co">'
        "AgentGraph</a>"
        " \u2014 trust infrastructure for AI agents."
        f' <a href="{profile_url}">View profile</a></sub>'
    )

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
        snippet = (
            f'<a href="{profile_url}">\n'
            f'  <img src="{badge_url}" alt="{alt}" />\n'
            f"</a>\n\n{blurb}"
        )

    return Response(
        content=snippet,
        media_type="text/plain",
        headers=dict(_CACHE_HEADERS),
    )


@router.api_route(
    "/badges/trust/{entity_id}.svg",
    methods=["GET", "HEAD"],
    dependencies=[Depends(rate_limit_reads)],
    responses={
        200: {"content": {"image/svg+xml": {}}, "description": "SVG trust badge"},
        404: {"description": "Entity not found"},
    },
)
async def get_trust_badge_svg(
    entity_id: uuid.UUID,
    style: _STYLE_OPTIONS = Query(
        "compact", description="Badge visual style",
    ),
    theme: Literal["light", "dark"] = Query(
        "light", description="Badge color theme",
    ),
    scale: float = Query(
        1.0, ge=1.0, le=3.0,
        description="Scale factor (1.0-3.0) for larger badges",
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

    # Apply scale by wrapping in viewBox if scale > 1
    if scale > 1.0:
        svg = _apply_scale(svg, scale)

    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers=dict(_CACHE_HEADERS),
    )
