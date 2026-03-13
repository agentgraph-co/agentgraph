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


# ─── Human Avatars ─── Geometric patterns: circles, waves, diamonds

def _human_geometric(idx: int) -> str:
    """Abstract geometric pattern avatar."""
    pal = PALETTES[idx % len(PALETTES)]
    seed = f"human-geo-{idx}"
    bg_angle = _hash_int(seed + "angle", 360)
    shapes = []

    variant = idx % 6
    if variant == 0:
        # Concentric circles
        for i in range(4, 0, -1):
            r = i * 30
            opacity = 0.2 + (5 - i) * 0.15
            shapes.append(f'<circle cx="128" cy="128" r="{r}" fill="{pal[i % 3]}" opacity="{opacity:.1f}"/>')
    elif variant == 1:
        # Diamond grid
        for row in range(4):
            for col in range(4):
                x = 32 + col * 64
                y = 32 + row * 64
                if (row + col) % 2 == 0:
                    shapes.append(
                        f'<rect x="{x-16}" y="{y-16}" width="32" height="32" rx="4" '
                        f'fill="{pal[(row+col) % 3]}" opacity="0.6" '
                        f'transform="rotate(45 {x} {y})"/>'
                    )
    elif variant == 2:
        # Horizontal stripes
        for i in range(8):
            y = i * 32
            shapes.append(
                f'<rect x="0" y="{y}" width="256" height="16" '
                f'fill="{pal[i % 3]}" opacity="{0.3 + (i % 3) * 0.2:.1f}"/>'
            )
    elif variant == 3:
        # Dots grid
        for row in range(5):
            for col in range(5):
                x = 28 + col * 50
                y = 28 + row * 50
                r = 8 + ((row * 5 + col) % 4) * 4
                shapes.append(
                    f'<circle cx="{x}" cy="{y}" r="{r}" '
                    f'fill="{pal[(row + col) % 3]}" opacity="0.5"/>'
                )
    elif variant == 4:
        # Triangles
        for i in range(6):
            x = _hash_int(seed + f"tx{i}", 200) + 28
            y = _hash_int(seed + f"ty{i}", 200) + 28
            size = 30 + _hash_int(seed + f"ts{i}", 40)
            shapes.append(
                f'<polygon points="{x},{y-size} {x-size},{y+size} {x+size},{y+size}" '
                f'fill="{pal[i % 3]}" opacity="0.5"/>'
            )
    else:
        # Rings
        for i in range(5):
            cx = _hash_int(seed + f"rx{i}", 180) + 38
            cy = _hash_int(seed + f"ry{i}", 180) + 38
            r = 20 + _hash_int(seed + f"rr{i}", 35)
            shapes.append(
                f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
                f'stroke="{pal[i % 3]}" stroke-width="4" opacity="0.6"/>'
            )

    grad = _gradient("bg", pal[0], pal[2], bg_angle)
    return (
        f'<svg width="256" height="256" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">'
        f'<defs>{grad}</defs>'
        f'<rect width="256" height="256" rx="128" fill="url(#bg)" opacity="0.15"/>'
        f'{"".join(shapes)}'
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

    # Generate 36 human avatars (6 patterns x 12 palettes / 2)
    for i in range(36):
        svg = _human_geometric(i)
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
