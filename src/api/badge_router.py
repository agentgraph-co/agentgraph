from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.rate_limit import rate_limit_reads
from src.database import get_db
from src.models import Entity, TrustScore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["trust-badges"])


def _trust_tier_color(score: float) -> str:
    """Return a hex color based on trust score tier."""
    if score >= 0.8:
        return "#2196F3"  # blue — highly trusted
    if score >= 0.6:
        return "#4CAF50"  # green — trusted
    if score >= 0.3:
        return "#FFC107"  # yellow — moderate
    return "#F44336"  # red — low trust


def _render_badge_svg(
    score: float,
    has_operator: bool,
) -> str:
    """Render a shields.io-style two-tone pill badge as SVG."""
    label = "AgentGraph Trust"
    score_text = f"{score:.2f}"
    sub_text = "Verified" if has_operator else "Unverified"

    color = _trust_tier_color(score)

    # Approximate character widths for the badge sizing
    label_width = len(label) * 6.5 + 12
    value_width = max(len(score_text), len(sub_text)) * 6.5 + 12
    total_width = label_width + value_width
    label_center = label_width / 2
    value_center = label_width + value_width / 2

    font = "Verdana,Geneva,DejaVu Sans,sans-serif"
    shadow = 'fill="#010101" fill-opacity=".3"'

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
        f' fill="#555"/>',
        f'    <rect x="{label_width}" width="{value_width}"'
        f' height="32" fill="{color}"/>',
        f'    <rect width="{total_width}" height="32"'
        f' fill="url(#s)"/>',
        "  </g>",
        f'  <g fill="#fff" text-anchor="middle"'
        f' font-family="{font}" font-size="11">',
        f'    <text x="{label_center}" y="14"'
        f" {shadow}>{label}</text>",
        f'    <text x="{label_center}" y="13">'
        f"{label}</text>",
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

    svg = _render_badge_svg(score, has_operator)

    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "public, max-age=300",
        },
    )
