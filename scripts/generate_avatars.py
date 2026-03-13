"""Generate a library of SVG avatars for humans and agents."""
from __future__ import annotations

import hashlib
import math
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "web", "public", "avatars", "library")

# Color palettes — warm, cool, nature, sunset, ocean, forest, berry, earth
PALETTES = [
    ("#6366F1", "#8B5CF6", "#A78BFA"),  # Indigo/violet
    ("#06B6D4", "#0EA5E9", "#38BDF8"),  # Cyan/sky
    ("#10B981", "#34D399", "#6EE7B7"),  # Emerald
    ("#F59E0B", "#FBBF24", "#FCD34D"),  # Amber
    ("#EF4444", "#F87171", "#FCA5A5"),  # Red
    ("#EC4899", "#F472B6", "#F9A8D4"),  # Pink
    ("#8B5CF6", "#A78BFA", "#C4B5FD"),  # Purple
    ("#14B8A6", "#2DD4BF", "#5EEAD4"),  # Teal
    ("#F97316", "#FB923C", "#FDBA74"),  # Orange
    ("#3B82F6", "#60A5FA", "#93C5FD"),  # Blue
    ("#84CC16", "#A3E635", "#BEF264"),  # Lime
    ("#D946EF", "#E879F9", "#F0ABFC"),  # Fuchsia
]


def _gradient(id_: str, c1: str, c2: str, angle: int = 45) -> str:
    rad = math.radians(angle)
    x1 = round(50 - 50 * math.cos(rad))
    y1 = round(50 - 50 * math.sin(rad))
    x2 = round(50 + 50 * math.cos(rad))
    y2 = round(50 + 50 * math.sin(rad))
    return (
        f'<linearGradient id="{id_}" x1="{x1}%" y1="{y1}%" x2="{x2}%" y2="{y2}%">'
        f'<stop offset="0%" stop-color="{c1}"/>'
        f'<stop offset="100%" stop-color="{c2}"/>'
        f'</linearGradient>'
    )


def _hash_int(seed: str, mod: int) -> int:
    return int(hashlib.md5(seed.encode()).hexdigest()[:8], 16) % mod


# ─── Human Avatars ─── Bold colored icons on pastel backgrounds
# Uses 24x24 icon paths (standard viewBox) scaled to center of 256x256

# (name, bg_light, icon_color, 24x24_path_d)
# Each icon is drawn in a 24x24 viewBox, we scale+center it in the 256 SVG.
HUMAN_ICONS = [
    # ── Animals ──
    ("cat", "#EEF2FF", "#6366f1",
     "M12 2c-1 0-2.5.7-3 2L7 2C6 2 5.5 3 6 4l1.5 3C6 8 5 9.5 5 11.5 5 15 8 18 12 18s7-3 7-6.5c0-2-1-3.5-2.5-4.5L18 4c.5-1 0-2-1-2l-2 2c-.5-1.3-2-2-3-2zm-2.5 9a1.5 1.5 0 110-3 1.5 1.5 0 010 3zm5 0a1.5 1.5 0 110-3 1.5 1.5 0 010 3zM10 15h4"),
    ("dog", "#EEF2FF", "#818cf8",
     "M12 2C9 2 7 4.5 7 7v1H5.5C4.7 8 4 8.7 4 9.5v3C4 13.3 4.7 14 5.5 14H7v2c0 3 2.2 6 5 6s5-3 5-6v-2h1.5c.8 0 1.5-.7 1.5-1.5v-3c0-.8-.7-1.5-1.5-1.5H17V7c0-2.5-2-5-5-5zm-2 8a1 1 0 110-2 1 1 0 010 2zm4 0a1 1 0 110-2 1 1 0 010 2zm-4 4h4l-2 2z"),
    ("fox", "#EEF2FF", "#a78bfa",
     "M18 3l-3 5h-2V5L12 2 11 5v3H9L6 3C5.2 3 5 4 5.4 4.6L8 10c-1.5 1.5-2 3.5-2 5.5C6 19 9 22 12 22s6-3 6-6.5c0-2-0.5-4-2-5.5l2.6-5.4C19 4 18.8 3 18 3zM10 13a1 1 0 110-2 1 1 0 010 2zm4 0a1 1 0 110-2 1 1 0 010 2zm-2 4l-1.5-2h3z"),
    ("owl", "#FFF7ED", "#f59e0b",
     "M12 2C8.5 2 5 5 5 9v4c0 4 3 9 7 9s7-5 7-9V9c0-4-3.5-7-7-7zm0 2c.5 0 1 .1 1.5.3L12 6l-1.5-1.7c.5-.2 1-.3 1.5-.3zM8.5 10a2.5 2.5 0 110 5 2.5 2.5 0 010-5zm7 0a2.5 2.5 0 110 5 2.5 2.5 0 010-5zM8.5 12a.5.5 0 100 1 .5.5 0 000-1zm7 0a.5.5 0 100 1 .5.5 0 000-1zM12 17l-1 1.5h2z"),
    ("bear", "#FEF2F2", "#ef4444",
     "M8 4a3 3 0 00-2 5.2V11c0 4.4 2.7 9 6 9s6-4.6 6-9V9.2A3 3 0 0016 4a3 3 0 00-2.8 2H10.8A3 3 0 008 4zm2 7a1.5 1.5 0 110 3 1.5 1.5 0 010-3zm4 0a1.5 1.5 0 110 3 1.5 1.5 0 010-3zm-2 5c-1 0-1.8.5-2 1h4c-.2-.5-1-1-2-1z"),
    ("penguin", "#F0FDF4", "#10b981",
     "M12 2C9.5 2 8 4 8 6v1c-1.5 1-3 3-3 6 0 4 2.5 6 4 7v1h6v-1c1.5-1 4-3 4-7 0-3-1.5-5-3-6V6c0-2-1.5-4-4-4zm0 2c1 0 2 1 2 2H10c0-1 1-2 2-2zm-2 7a1.5 1.5 0 110 3 1.5 1.5 0 010-3zm4 0a1.5 1.5 0 110 3 1.5 1.5 0 010-3z"),
    # ── Nature ──
    ("mountain", "#ECFDF5", "#059669",
     "M13 3.5L7.5 13l2 0-5.5 7.5h16L14.5 13l2 0zM17 10l4 10.5h-6z"),
    ("tree", "#F0FDF4", "#16a34a",
     "M12 2L5 10h3l-3 5h3l-3 5h14l-3-5h3l-3-5h3zm-1 18h2v2h-2z"),
    ("star", "#FFFBEB", "#d97706",
     "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"),
    ("moon", "#EFF6FF", "#2563eb",
     "M12 3a9 9 0 109 9c0-.5 0-1-.06-1.5A5 5 0 0113.5 3.06 9.06 9.06 0 0012 3z"),
    ("flower", "#FDF2F8", "#db2777",
     "M12 22c1 0 2-1 2-2h-4c0 1 1 2 2 2zm0-20C10 2 9 3 9 4c0 .4.1.7.3 1A5 5 0 007 10c0 2.5 1 4.5 2.5 5.5l-.5 2.5h6l-.5-2.5C16 14.5 17 12.5 17 10a5 5 0 00-2.3-5c.2-.3.3-.6.3-1 0-1-1-2-3-2zm-3 9a1 1 0 112 0 1 1 0 01-2 0zm4 0a1 1 0 112 0 1 1 0 01-2 0z"),
    ("sun", "#FEF3C7", "#b45309",
     "M12 7a5 5 0 100 10 5 5 0 000-10zM2 13h2v-2H2zm18 0h2v-2h-2zM11 2v2h2V2zm0 18v2h2v-2zM5.99 4.58l-1.41 1.41 1.41 1.42 1.42-1.42zm12.02 12.02l-1.41 1.41 1.41 1.42 1.42-1.42zM4.58 18.01l1.41 1.41 1.42-1.41-1.42-1.42zm12.02-12.02l1.41 1.41 1.42-1.41-1.42-1.42z"),
    # ── Characters ──
    ("astronaut", "#F5F3FF", "#7c3aed",
     "M12 2a5 5 0 00-5 5v2a5 5 0 003 4.58V15H8v5a2 2 0 002 2h4a2 2 0 002-2v-5h-2v-1.42A5 5 0 0017 9V7a5 5 0 00-5-5zm0 2a3 3 0 013 3v2a3 3 0 01-6 0V7a3 3 0 013-3zM9 8h6v1a3 3 0 01-6 0z"),
    ("ninja", "#FEF2F2", "#dc2626",
     "M12 2C8 2 5 5 5 9c0 2 .8 3.8 2 5v2l-2 4h14l-2-4v-2c1.2-1.2 2-3 2-5 0-4-3-7-7-7zm-4 7h8v2H8zm4 7l-2-3h4z"),
    ("wizard", "#F5F3FF", "#6d28d9",
     "M12 2L7 12h3v3H7l5 7 5-7h-3v-3h3zm-2 20h4v-1h-4z"),
    ("robot", "#E0F2FE", "#0284c7",
     "M12 2a1 1 0 00-1 1v1H7a3 3 0 00-3 3v8a3 3 0 003 3h1v2a2 2 0 002 2h4a2 2 0 002-2v-2h1a3 3 0 003-3V7a3 3 0 00-3-3h-4V3a1 1 0 00-1-1zM9 9a1.5 1.5 0 110 3 1.5 1.5 0 010-3zm6 0a1.5 1.5 0 110 3 1.5 1.5 0 010-3zm-5 6h4l-2 2z"),
    ("pirate", "#FFF7ED", "#c2410c",
     "M15 2l-1 3H10L9 2 7 3l1.5 3C6.5 7 5 9 5 12c0 4 3 8 7 8s7-4 7-8c0-3-1.5-5-3.5-6L17 3zM10 11a1.5 1.5 0 110 3 1.5 1.5 0 010-3zm4 .5a2 2 0 11-1 1l2-1.5zM9 16h6c-.5 1.5-1.5 2-3 2s-2.5-.5-3-2z"),
    ("superhero", "#EFF6FF", "#1d4ed8",
     "M12 2L9 5v2H7a2 2 0 00-2 2v5l3 4v2a2 2 0 002 2h4a2 2 0 002-2v-2l3-4V9a2 2 0 00-2-2h-2V5zm0 2l1.5 2h-3zM9 10.5a1.5 1.5 0 113 0 1.5 1.5 0 01-3 0zm3 2.5l2 3h-4z"),
    # ── Food ──
    ("pizza", "#FEF2F2", "#e11d48",
     "M12 2L3 20h18zm0 4l5.5 12h-11zm-1 5a1 1 0 112 0 1 1 0 01-2 0zm-2 3a1 1 0 112 0 1 1 0 01-2 0zm5 0a1 1 0 112 0 1 1 0 01-2 0z"),
    ("cupcake", "#FDF2F8", "#c026d3",
     "M8 13v5a4 4 0 008 0v-5zM7 12h10c.5 0 1-.5 1-1-1-3-3-5-6-5s-5 2-6 5c0 .5.5 1 1 1zm3-8c0-.5.4-1 1-1h2c.6 0 1 .5 1 1v1h-4z"),
    ("coffee", "#FEF9C3", "#a16207",
     "M6 7h8a1 1 0 011 1v7a4 4 0 01-4 4H9a4 4 0 01-4-4V8a1 1 0 011-1zm10 2h1a3 3 0 010 6h-1zM8 3v2m2-3v3m2-2v2"),
    ("taco", "#FFF7ED", "#ea580c",
     "M4 16c0 3 3.5 6 8 6s8-3 8-6l-1-4c-.5-2-2-4-4-5l-1-4h-4l-1 4c-2 1-3.5 3-4 5zm4-2a1 1 0 112 0 1 1 0 01-2 0zm3 0a1 1 0 112 0 1 1 0 01-2 0zm3 0a1 1 0 112 0 1 1 0 01-2 0z"),
    ("icecream", "#FCE7F3", "#be185d",
     "M12 2a5 5 0 00-5 5c0 2 1 3.5 2.5 4.5L8 22h8l-1.5-10.5C16 10.5 17 9 17 7a5 5 0 00-5-5zm0 2a3 3 0 013 3c0 1.2-.7 2.2-1.7 2.7L12 16l-1.3-6.3A3 3 0 019 7a3 3 0 013-3z"),
    ("sushi", "#F0FDF4", "#15803d",
     "M4 12c0-3 3.5-6 8-6s8 3 8 6-3.5 6-8 6-8-3-8-6zm3 0c0 1.5 2 3 5 3s5-1.5 5-3-2-3-5-3-5 1.5-5 3zm3-1a1 1 0 112 0 1 1 0 01-2 0zm3 1a1 1 0 112 0 1 1 0 01-2 0z"),
    # ── Hobby ──
    ("headphones", "#F5F3FF", "#7c3aed",
     "M12 3C7 3 3 7 3 12v4a3 3 0 003 3h1a2 2 0 002-2v-4a2 2 0 00-2-2H6c0-3.3 2.7-6 6-6s6 2.7 6 6h-1a2 2 0 00-2 2v4a2 2 0 002 2h1a3 3 0 003-3v-4c0-5-4-9-9-9z"),
    ("gamepad", "#EEF2FF", "#4f46e5",
     "M6 9a4 4 0 00-4 4v0a4 4 0 004 4h12a4 4 0 004-4v0a4 4 0 00-4-4zm2 2v2h-2v-2zm0 2v2h-2v-2zm-2-2h-2v2h2zM15 11a1 1 0 110 2 1 1 0 010-2zm2 2a1 1 0 110 2 1 1 0 010-2z"),
    ("music", "#FDF4FF", "#a21caf",
     "M12 3v12.26A4 4 0 008 13a4 4 0 000 8 4 4 0 004-4V7h4V3zm0 14a2 2 0 11-4 0 2 2 0 014 0z"),
    ("camera", "#ECFEFF", "#0891b2",
     "M9 3l-1.5 2H4a2 2 0 00-2 2v11a2 2 0 002 2h16a2 2 0 002-2V7a2 2 0 00-2-2h-3.5L15 3zm3 5a5 5 0 110 10 5 5 0 010-10zm0 2a3 3 0 100 6 3 3 0 000-6z"),
    ("rocket", "#FEF2F2", "#dc2626",
     "M12 2c-3 4-5 8-5 13h3v5h4v-5h3c0-5-2-9-5-13zm0 4c1 2 2 4.5 2.5 7h-5C10 10.5 11 8 12 6z"),
    ("lightning", "#FEF9C3", "#ca8a04",
     "M13 2L5 13h5l-2 9 9-12h-5z"),
    # ── Abstract ──
    ("globe", "#E0F2FE", "#0369a1",
     "M12 2a10 10 0 100 20 10 10 0 000-20zm0 2c1.1 0 2.5 1.8 3.2 5H8.8C9.5 5.8 10.9 4 12 4zM8.2 11h7.6c.1.6.2 1.3.2 2s-.1 1.4-.2 2H8.2c-.1-.6-.2-1.3-.2-2s.1-1.4.2-2zM12 20c-1.1 0-2.5-1.8-3.2-5h6.4c-.7 3.2-2.1 5-3.2 5z"),
    ("heart", "#FDF2F8", "#be185d",
     "M12 21.35l-1.45-1.32C5.4 15.36 2 12.27 2 8.5 2 5.41 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.08C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.41 22 8.5c0 3.77-3.4 6.86-8.55 11.53z"),
    ("diamond", "#F5F3FF", "#7c3aed",
     "M12 2L2 9l10 13L22 9zm0 3.5L18 9l-6 8.5L6 9z"),
    ("flame", "#FFF7ED", "#ea580c",
     "M12 2c-3 5-7 8-7 12a7 7 0 0014 0c0-4-4-7-7-12zm0 6c1.5 2.5 3 4 3 6a3 3 0 01-6 0c0-2 1.5-3.5 3-6z"),
    ("leaf", "#F0FDF4", "#16a34a",
     "M17 8C8 10 5.9 16.17 3.82 21.34l1.89.66.95-2.3c.48.17.98.3 1.34.3C19 20 22 3 22 3c-1 2-8 2.25-13 3.25S2 11.5 2 13.5s1.5 3.5 4 5C7 15 9 12 12 10c-4 6-2 8-2 8l.5.5C15 16 17 8 17 8z"),
    ("sparkle", "#FFFBEB", "#d97706",
     "M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8z"),
]


def _human_icon(idx: int) -> str:
    """Generate a human avatar with a bold colored icon on a pastel background."""
    name, bg_color, icon_color, path_d = HUMAN_ICONS[idx % len(HUMAN_ICONS)]
    # The path is in a 24x24 viewBox. We scale it to fit nicely in 256x256.
    # Scale factor: 7x, centered with translate to (44, 44) for a 168x168 icon area
    return (
        f'<svg width="256" height="256" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="256" height="256" rx="32" fill="{bg_color}"/>'
        f'<g transform="translate(44,44) scale(7)">'
        f'<path d="{path_d}" fill="{icon_color}" fill-rule="evenodd"/>'
        f'</g>'
        f'</svg>'
    )


# ─── Agent Avatars ─── Circuit/tech patterns: nodes, connections, hexagons

def _agent_circuit(idx: int) -> str:
    """Circuit/tech pattern avatar for agents."""
    pal = PALETTES[idx % len(PALETTES)]
    seed = f"agent-circuit-{idx}"
    shapes = []

    variant = idx % 6
    if variant == 0:
        # Hex grid
        for row in range(4):
            for col in range(4):
                x = 40 + col * 55 + (row % 2) * 27
                y = 35 + row * 48
                size = 22
                points = []
                for i in range(6):
                    angle = math.radians(60 * i - 30)
                    px = x + size * math.cos(angle)
                    py = y + size * math.sin(angle)
                    points.append(f"{px:.0f},{py:.0f}")
                shapes.append(
                    f'<polygon points="{" ".join(points)}" fill="none" '
                    f'stroke="{pal[(row+col) % 3]}" stroke-width="2" opacity="0.7"/>'
                )
    elif variant == 1:
        # Node network
        nodes = []
        for i in range(8):
            x = _hash_int(seed + f"nx{i}", 200) + 28
            y = _hash_int(seed + f"ny{i}", 200) + 28
            nodes.append((x, y))
            shapes.append(f'<circle cx="{x}" cy="{y}" r="6" fill="{pal[i % 3]}"/>')
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                dist = math.sqrt((nodes[i][0]-nodes[j][0])**2 + (nodes[i][1]-nodes[j][1])**2)
                if dist < 120:
                    shapes.insert(0,
                        f'<line x1="{nodes[i][0]}" y1="{nodes[i][1]}" '
                        f'x2="{nodes[j][0]}" y2="{nodes[j][1]}" '
                        f'stroke="{pal[1]}" stroke-width="1.5" opacity="0.3"/>'
                    )
    elif variant == 2:
        # Concentric hexagons
        for i in range(5, 0, -1):
            size = i * 22
            points = []
            for j in range(6):
                angle = math.radians(60 * j - 30)
                px = 128 + size * math.cos(angle)
                py = 128 + size * math.sin(angle)
                points.append(f"{px:.0f},{py:.0f}")
            shapes.append(
                f'<polygon points="{" ".join(points)}" fill="none" '
                f'stroke="{pal[i % 3]}" stroke-width="2" opacity="{0.3 + i * 0.12:.1f}"/>'
            )
    elif variant == 3:
        # Circuit traces
        for i in range(6):
            x1 = _hash_int(seed + f"cx1{i}", 256)
            y1 = _hash_int(seed + f"cy1{i}", 256)
            x2 = _hash_int(seed + f"cx2{i}", 256)
            y2 = _hash_int(seed + f"cy2{i}", 256)
            mid_x = (x1 + x2) // 2
            shapes.append(
                f'<path d="M{x1},{y1} L{mid_x},{y1} L{mid_x},{y2} L{x2},{y2}" '
                f'fill="none" stroke="{pal[i % 3]}" stroke-width="2.5" opacity="0.5" '
                f'stroke-linecap="round"/>'
            )
            shapes.append(f'<circle cx="{x1}" cy="{y1}" r="4" fill="{pal[i % 3]}" opacity="0.7"/>')
            shapes.append(f'<circle cx="{x2}" cy="{y2}" r="4" fill="{pal[i % 3]}" opacity="0.7"/>')
    elif variant == 4:
        # Stacked chevrons
        for i in range(7):
            y = 20 + i * 32
            shapes.append(
                f'<path d="M28,{y+16} L128,{y} L228,{y+16}" fill="none" '
                f'stroke="{pal[i % 3]}" stroke-width="3" opacity="{0.3 + i * 0.08:.1f}" '
                f'stroke-linecap="round"/>'
            )
    else:
        # Data blocks
        for row in range(6):
            x = 16
            for col in range(8):
                w = 12 + _hash_int(seed + f"bw{row}{col}", 20)
                h = 24
                if _hash_int(seed + f"bv{row}{col}", 3) > 0:
                    shapes.append(
                        f'<rect x="{x}" y="{16 + row * 38}" width="{w}" height="{h}" rx="3" '
                        f'fill="{pal[_hash_int(seed + f"bc{row}{col}", 3)]}" opacity="0.4"/>'
                    )
                x += w + 4
                if x > 240:
                    break

    # Hexagonal clip for agent avatars
    hex_points = " ".join(
        f"{128 + 128 * math.cos(math.radians(60 * i - 90)):.0f},"
        f"{128 + 128 * math.sin(math.radians(60 * i - 90)):.0f}"
        for i in range(6)
    )
    grad = _gradient("bg", pal[0], pal[2], 135)
    return (
        f'<svg width="256" height="256" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">'
        f'<defs>{grad}'
        f'<clipPath id="hex"><polygon points="{hex_points}"/></clipPath>'
        f'</defs>'
        f'<g clip-path="url(#hex)">'
        f'<rect width="256" height="256" fill="url(#bg)" opacity="0.15"/>'
        f'{"".join(shapes)}'
        f'</g>'
        f'</svg>'
    )


def main() -> None:
    os.makedirs(os.path.join(OUTPUT_DIR, "human"), exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "agent"), exist_ok=True)

    # Generate 36 human avatars
    for i in range(36):
        svg = _human_icon(i)
        path = os.path.join(OUTPUT_DIR, "human", f"h{i:02d}.svg")
        with open(path, "w") as f:
            f.write(svg)

    # Generate 36 agent avatars
    for i in range(36):
        svg = _agent_circuit(i)
        path = os.path.join(OUTPUT_DIR, "agent", f"a{i:02d}.svg")
        with open(path, "w") as f:
            f.write(svg)

    print(f"Generated 72 avatars in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
