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


# ─── Human Avatars ─── Recognizable silhouettes and icons

# 6 color palettes for the 6 groups
HUMAN_PALETTES = [
    ("#6366f1", "#818cf8", "#c7d2fe"),  # Indigo — animals
    ("#10b981", "#34d399", "#a7f3d0"),  # Emerald — nature/objects
    ("#f59e0b", "#fbbf24", "#fde68a"),  # Amber — characters
    ("#f43f5e", "#fb7185", "#fecdd3"),  # Rose — food/fun
    ("#06b6d4", "#22d3ee", "#a5f3fc"),  # Cyan — abstract
    ("#a855f7", "#c084fc", "#e9d5ff"),  # Purple — (extra cycle)
]

# SVG path data for each icon, designed for a 256x256 viewBox.
# Each value is the SVG content (paths, circles, etc.) to draw in white/light color.

HUMAN_ICONS: list[tuple[str, str]] = [
    # ── Group 0: Animal silhouettes (Indigo) ──
    ("cat",
     '<path d="M128 200c-35 0-60-20-60-50 0-25 15-40 25-50l-15-60 30 25 20-10 20 10 30-25-15 60c10 10 25 25 25 50 0 30-25 50-60 50z" fill="white" opacity="0.9"/>'
     '<circle cx="108" cy="130" r="8" fill="white" opacity="0.5"/>'
     '<circle cx="148" cy="130" r="8" fill="white" opacity="0.5"/>'
     '<ellipse cx="128" cy="148" rx="6" ry="4" fill="white" opacity="0.5"/>'
     '<path d="M118 160q10 8 20 0" fill="none" stroke="white" stroke-width="2.5" opacity="0.5"/>'),
    ("dog",
     '<path d="M128 205c-40 0-65-25-65-55 0-20 10-35 20-45l-8-15c-5-10 0-22 8-28l15 20 30-15 30 15 15-20c8 6 13 18 8 28l-8 15c10 10 20 25 20 45 0 30-25 55-65 55z" fill="white" opacity="0.9"/>'
     '<circle cx="105" cy="125" r="9" fill="white" opacity="0.5"/>'
     '<circle cx="151" cy="125" r="9" fill="white" opacity="0.5"/>'
     '<ellipse cx="128" cy="150" rx="10" ry="7" fill="white" opacity="0.5"/>'
     '<path d="M120 165q8 6 16 0" fill="none" stroke="white" stroke-width="2" opacity="0.5"/>'),
    ("fox",
     '<path d="M128 205c-38 0-58-22-58-48 0-22 12-38 22-48L72 60l28 30 28-20 28 20 28-30-20 49c10 10 22 26 22 48 0 26-20 48-58 48z" fill="white" opacity="0.9"/>'
     '<circle cx="108" cy="130" r="7" fill="white" opacity="0.5"/>'
     '<circle cx="148" cy="130" r="7" fill="white" opacity="0.5"/>'
     '<path d="M128 152l-6 8h12z" fill="white" opacity="0.5"/>'),
    ("owl",
     '<ellipse cx="128" cy="140" rx="55" ry="65" fill="white" opacity="0.9"/>'
     '<path d="M73 105l-15-40 30 20z" fill="white" opacity="0.9"/>'
     '<path d="M183 105l15-40-30 20z" fill="white" opacity="0.9"/>'
     '<circle cx="108" cy="125" r="22" fill="white" opacity="0.4"/>'
     '<circle cx="148" cy="125" r="22" fill="white" opacity="0.4"/>'
     '<circle cx="108" cy="125" r="10" fill="white" opacity="0.6"/>'
     '<circle cx="148" cy="125" r="10" fill="white" opacity="0.6"/>'
     '<path d="M122 155l6 10 6-10" fill="white" opacity="0.5"/>'),
    ("bear",
     '<circle cx="88" cy="80" r="22" fill="white" opacity="0.85"/>'
     '<circle cx="168" cy="80" r="22" fill="white" opacity="0.85"/>'
     '<ellipse cx="128" cy="145" rx="60" ry="62" fill="white" opacity="0.9"/>'
     '<circle cx="108" cy="128" r="8" fill="white" opacity="0.4"/>'
     '<circle cx="148" cy="128" r="8" fill="white" opacity="0.4"/>'
     '<ellipse cx="128" cy="155" rx="15" ry="10" fill="white" opacity="0.4"/>'
     '<circle cx="128" cy="150" r="5" fill="white" opacity="0.5"/>'),
    ("penguin",
     '<ellipse cx="128" cy="148" rx="48" ry="65" fill="white" opacity="0.9"/>'
     '<ellipse cx="128" cy="148" rx="30" ry="55" fill="white" opacity="0.5"/>'
     '<circle cx="128" cy="95" r="32" fill="white" opacity="0.9"/>'
     '<circle cx="116" cy="90" r="5" fill="white" opacity="0.4"/>'
     '<circle cx="140" cy="90" r="5" fill="white" opacity="0.4"/>'
     '<path d="M122 102l6 8 6-8" fill="white" opacity="0.6"/>'
     '<path d="M80 130q-10 20 5 45" fill="none" stroke="white" stroke-width="6" stroke-linecap="round" opacity="0.7"/>'
     '<path d="M176 130q10 20-5 45" fill="none" stroke="white" stroke-width="6" stroke-linecap="round" opacity="0.7"/>'),

    # ── Group 1: Nature/Object icons (Emerald) ──
    ("mountain",
     '<path d="M20 200L90 70l30 40 38-60 78 150z" fill="white" opacity="0.9"/>'
     '<path d="M158 50l-25 40 10 12 15-20 15 20 10-12z" fill="white" opacity="0.6"/>'),
    ("tree",
     '<rect x="118" y="160" width="20" height="50" rx="4" fill="white" opacity="0.7"/>'
     '<path d="M128 40l-50 55h25l-20 35h25l-15 30h70l-15-30h25l-20-35h25z" fill="white" opacity="0.9"/>'),
    ("star",
     '<path d="M128 35l22 50 55 5-42 35 14 53-49-30-49 30 14-53-42-35 55-5z" fill="white" opacity="0.9"/>'),
    ("moon",
     '<path d="M148 50a75 75 0 1 0 0 156 85 85 0 0 1 0-156z" fill="white" opacity="0.9"/>'
     '<circle cx="155" cy="85" r="4" fill="white" opacity="0.4"/>'
     '<circle cx="180" cy="110" r="3" fill="white" opacity="0.3"/>'
     '<circle cx="170" cy="145" r="5" fill="white" opacity="0.35"/>'),
    ("flower",
     '<circle cx="128" cy="128" r="18" fill="white" opacity="0.9"/>'
     '<ellipse cx="128" cy="85" rx="18" ry="25" fill="white" opacity="0.65"/>'
     '<ellipse cx="128" cy="171" rx="18" ry="25" fill="white" opacity="0.65"/>'
     '<ellipse cx="85" cy="128" rx="25" ry="18" fill="white" opacity="0.65"/>'
     '<ellipse cx="171" cy="128" rx="25" ry="18" fill="white" opacity="0.65"/>'
     '<ellipse cx="98" cy="98" rx="20" ry="18" fill="white" opacity="0.55" transform="rotate(-45 98 98)"/>'
     '<ellipse cx="158" cy="98" rx="20" ry="18" fill="white" opacity="0.55" transform="rotate(45 158 98)"/>'
     '<ellipse cx="98" cy="158" rx="20" ry="18" fill="white" opacity="0.55" transform="rotate(45 98 158)"/>'
     '<ellipse cx="158" cy="158" rx="20" ry="18" fill="white" opacity="0.55" transform="rotate(-45 158 158)"/>'),
    ("sun",
     '<circle cx="128" cy="128" r="35" fill="white" opacity="0.9"/>'
     '<line x1="128" y1="55" x2="128" y2="75" stroke="white" stroke-width="6" stroke-linecap="round" opacity="0.7"/>'
     '<line x1="128" y1="181" x2="128" y2="201" stroke="white" stroke-width="6" stroke-linecap="round" opacity="0.7"/>'
     '<line x1="55" y1="128" x2="75" y2="128" stroke="white" stroke-width="6" stroke-linecap="round" opacity="0.7"/>'
     '<line x1="181" y1="128" x2="201" y2="128" stroke="white" stroke-width="6" stroke-linecap="round" opacity="0.7"/>'
     '<line x1="76" y1="76" x2="90" y2="90" stroke="white" stroke-width="6" stroke-linecap="round" opacity="0.6"/>'
     '<line x1="166" y1="76" x2="180" y2="90" stroke="white" stroke-width="6" stroke-linecap="round" opacity="0.6"/>'  # noqa: E501
     '<line x1="76" y1="180" x2="90" y2="166" stroke="white" stroke-width="6" stroke-linecap="round" opacity="0.6"/>'
     '<line x1="166" y1="180" x2="180" y2="166" stroke="white" stroke-width="6" stroke-linecap="round" opacity="0.6"/>'),

    # ── Group 2: Character silhouettes (Amber) ──
    ("astronaut",
     '<circle cx="128" cy="100" r="45" fill="white" opacity="0.9"/>'
     '<rect x="83" y="95" width="90" height="50" rx="22" fill="white" opacity="0.5"/>'
     '<rect x="95" y="145" width="66" height="60" rx="10" fill="white" opacity="0.85"/>'
     '<circle cx="108" cy="95" r="5" fill="white" opacity="0.3"/>'
     '<circle cx="148" cy="95" r="5" fill="white" opacity="0.3"/>'
     '<rect x="75" y="155" width="20" height="35" rx="8" fill="white" opacity="0.7"/>'
     '<rect x="161" y="155" width="20" height="35" rx="8" fill="white" opacity="0.7"/>'),
    ("ninja",
     '<circle cx="128" cy="100" r="40" fill="white" opacity="0.9"/>'
     '<rect x="85" y="88" width="86" height="18" rx="4" fill="white" opacity="0.4"/>'
     '<circle cx="112" cy="97" r="5" fill="white" opacity="0.6"/>'
     '<circle cx="144" cy="97" r="5" fill="white" opacity="0.6"/>'
     '<path d="M100 140l28 65 28-65z" fill="white" opacity="0.85"/>'
     '<path d="M80 95l-25-15" stroke="white" stroke-width="5" stroke-linecap="round" opacity="0.6"/>'
     '<path d="M176 95l25-15" stroke="white" stroke-width="5" stroke-linecap="round" opacity="0.6"/>'),
    ("wizard",
     '<path d="M128 30l-35 80h70z" fill="white" opacity="0.9"/>'
     '<rect x="85" y="108" width="86" height="8" rx="3" fill="white" opacity="0.7"/>'
     '<circle cx="128" cy="140" r="32" fill="white" opacity="0.85"/>'
     '<circle cx="118" cy="135" r="4" fill="white" opacity="0.4"/>'
     '<circle cx="138" cy="135" r="4" fill="white" opacity="0.4"/>'
     '<path d="M100 170l28 40 28-40z" fill="white" opacity="0.75"/>'
     '<circle cx="128" cy="65" r="6" fill="white" opacity="0.6"/>'),
    ("robot-face",
     '<rect x="78" y="70" width="100" height="90" rx="16" fill="white" opacity="0.9"/>'
     '<rect x="68" y="100" width="12" height="25" rx="5" fill="white" opacity="0.7"/>'
     '<rect x="176" y="100" width="12" height="25" rx="5" fill="white" opacity="0.7"/>'
     '<rect x="100" y="95" width="22" height="18" rx="4" fill="white" opacity="0.4"/>'
     '<rect x="134" y="95" width="22" height="18" rx="4" fill="white" opacity="0.4"/>'
     '<rect x="108" y="132" width="40" height="8" rx="3" fill="white" opacity="0.4"/>'
     '<rect x="118" y="55" width="20" height="18" rx="6" fill="white" opacity="0.7"/>'
     '<rect x="88" y="170" width="80" height="30" rx="8" fill="white" opacity="0.75"/>'),
    ("pirate",
     '<circle cx="128" cy="120" r="40" fill="white" opacity="0.9"/>'
     '<path d="M75 80q53-50 106 0" fill="white" opacity="0.7"/>'
     '<rect x="75" y="75" width="106" height="10" rx="3" fill="white" opacity="0.6"/>'
     '<circle cx="145" cy="115" r="12" fill="white" opacity="0.35"/>'
     '<line x1="133" y1="103" x2="157" y2="127" stroke="white" stroke-width="3" opacity="0.4"/>'
     '<circle cx="112" cy="115" r="5" fill="white" opacity="0.5"/>'
     '<path d="M112 138q16 12 32 0" fill="none" stroke="white" stroke-width="2.5" opacity="0.5"/>'
     '<path d="M100 165l28 40 28-40z" fill="white" opacity="0.8"/>'),
    ("superhero",
     '<circle cx="128" cy="85" r="32" fill="white" opacity="0.9"/>'
     '<path d="M85 115h86l10 90H75z" fill="white" opacity="0.85"/>'
     '<path d="M75 130l-35 25 40-5z" fill="white" opacity="0.7"/>'
     '<path d="M181 130l35 25-40-5z" fill="white" opacity="0.7"/>'
     '<path d="M100 85l28-25 28 25" fill="white" opacity="0.5"/>'
     '<path d="M118 155l10 12 10-12z" fill="white" opacity="0.45"/>'),

    # ── Group 3: Food/Fun (Rose) ──
    ("pizza",
     '<path d="M128 55l-65 150h130z" fill="white" opacity="0.9"/>'
     '<circle cx="115" cy="140" r="10" fill="white" opacity="0.45"/>'
     '<circle cx="145" cy="155" r="9" fill="white" opacity="0.45"/>'
     '<circle cx="125" cy="170" r="8" fill="white" opacity="0.4"/>'
     '<path d="M63 205q65-15 130 0" fill="none" stroke="white" stroke-width="5" opacity="0.6"/>'),
    ("cupcake",
     '<path d="M88 130q0-45 40-45t40 45z" fill="white" opacity="0.9"/>'
     '<path d="M78 130q10 8 20-2t20 4 20-4 20 2" fill="white" opacity="0.7"/>'
     '<rect x="85" y="140" width="86" height="55" rx="8" fill="white" opacity="0.8"/>'
     '<rect x="90" y="195" width="76" height="10" rx="4" fill="white" opacity="0.6"/>'
     '<circle cx="128" cy="100" r="6" fill="white" opacity="0.5"/>'),
    ("coffee",
     '<rect x="78" y="80" width="90" height="110" rx="12" fill="white" opacity="0.9"/>'
     '<path d="M168 110q30 0 30 30t-30 30" fill="none" stroke="white" stroke-width="6" opacity="0.7"/>'
     '<rect x="75" y="195" width="96" height="10" rx="4" fill="white" opacity="0.6"/>'
     '<path d="M105 55q8-15 16 0t16 0" fill="none" stroke="white" stroke-width="4" stroke-linecap="round" opacity="0.5"/>'),
    ("taco",
     '<path d="M45 165q83-110 166 0" fill="white" opacity="0.9"/>'
     '<path d="M45 165q83 30 166 0" fill="white" opacity="0.7"/>'
     '<circle cx="100" cy="140" r="8" fill="white" opacity="0.4"/>'
     '<circle cx="128" cy="130" r="7" fill="white" opacity="0.4"/>'
     '<circle cx="156" cy="140" r="8" fill="white" opacity="0.4"/>'
     '<path d="M80 155q48-10 96 0" fill="none" stroke="white" stroke-width="3" opacity="0.4"/>'),
    ("ice-cream",
     '<circle cx="128" cy="90" r="40" fill="white" opacity="0.9"/>'
     '<circle cx="100" cy="85" r="25" fill="white" opacity="0.75"/>'
     '<circle cx="156" cy="85" r="25" fill="white" opacity="0.75"/>'
     '<path d="M95 115l33 90 33-90z" fill="white" opacity="0.8"/>'
     '<path d="M95 115q33 15 66 0" fill="white" opacity="0.5"/>'),
    ("sushi",
     '<ellipse cx="128" cy="145" rx="65" ry="40" fill="white" opacity="0.9"/>'
     '<ellipse cx="128" cy="130" rx="55" ry="30" fill="white" opacity="0.7"/>'
     '<ellipse cx="128" cy="120" rx="35" ry="20" fill="white" opacity="0.5"/>'
     '<rect x="118" y="95" width="20" height="55" rx="6" fill="white" opacity="0.6"/>'
     '<rect x="85" y="140" width="86" height="10" rx="3" fill="white" opacity="0.4"/>'),

    # ── Group 4: Abstract but appealing (Cyan) ──
    ("gradient-circle",
     '<circle cx="128" cy="128" r="70" fill="white" opacity="0.9"/>'
     '<circle cx="128" cy="128" r="55" fill="white" opacity="0.25"/>'
     '<circle cx="128" cy="128" r="40" fill="white" opacity="0.25"/>'
     '<circle cx="128" cy="128" r="25" fill="white" opacity="0.2"/>'),
    ("rainbow-arc",
     '<path d="M40 180A88 88 0 0 1 216 180" fill="none" stroke="white" stroke-width="10" opacity="0.9"/>'
     '<path d="M55 180A73 73 0 0 1 201 180" fill="none" stroke="white" stroke-width="8" opacity="0.7"/>'
     '<path d="M70 180A58 58 0 0 1 186 180" fill="none" stroke="white" stroke-width="7" opacity="0.5"/>'
     '<path d="M85 180A43 43 0 0 1 171 180" fill="none" stroke="white" stroke-width="6" opacity="0.35"/>'),
    ("yin-yang",
     '<circle cx="128" cy="128" r="70" fill="white" opacity="0.9"/>'
     '<path d="M128 58a70 70 0 0 1 0 140a35 35 0 0 1 0-70a35 35 0 0 0 0-70z" fill="white" opacity="0.35"/>'
     '<circle cx="128" cy="93" r="10" fill="white" opacity="0.6"/>'
     '<circle cx="128" cy="163" r="10" fill="white" opacity="0.4"/>'),
    ("mandala",
     '<circle cx="128" cy="128" r="12" fill="white" opacity="0.9"/>'
     '<circle cx="128" cy="128" r="30" fill="none" stroke="white" stroke-width="2.5" opacity="0.7"/>'
     '<circle cx="128" cy="128" r="50" fill="none" stroke="white" stroke-width="2" opacity="0.55"/>'
     '<circle cx="128" cy="128" r="70" fill="none" stroke="white" stroke-width="1.5" opacity="0.4"/>'
     + ''.join(
         f'<ellipse cx="128" cy="128" rx="10" ry="50" fill="white" opacity="0.2" transform="rotate({a} 128 128)"/>'
         for a in range(0, 180, 30)
     )
     + ''.join(
         f'<circle cx="{128 + int(50 * math.cos(math.radians(a)))}" cy="{128 + int(50 * math.sin(math.radians(a)))}" r="5" fill="white" opacity="0.6"/>'
         for a in range(0, 360, 45)
     )),
    ("spiral",
     '<path d="M128 128'
     + ''.join(
         f'A{8+i*4} {8+i*4} 0 0 {1 if i % 2 == 0 else 0} '
         f'{128 + int((8+i*4) * math.cos(math.radians(i * 180)))} '
         f'{128 + int((8+i*4) * math.sin(math.radians(i * 180)))}'
         for i in range(1, 10)
     )
     + '" fill="none" stroke="white" stroke-width="5" stroke-linecap="round" opacity="0.9"/>'
     + ''.join(
         f'<circle cx="{128 + int((8+i*4) * math.cos(math.radians(i * 180)))}" '
         f'cy="{128 + int((8+i*4) * math.sin(math.radians(i * 180)))}" r="3" fill="white" opacity="0.5"/>'
         for i in range(1, 10, 2)
     )),
    ("gem",
     '<path d="M88 95h80l-40 100z" fill="white" opacity="0.9"/>'
     '<path d="M88 95l40-40 40 40z" fill="white" opacity="0.7"/>'
     '<path d="M128 55l-40 40 40 100 40-100z" fill="white" opacity="0.2"/>'
     '<line x1="128" y1="55" x2="128" y2="195" stroke="white" stroke-width="1.5" opacity="0.4"/>'
     '<line x1="88" y1="95" x2="128" y2="195" stroke="white" stroke-width="1" opacity="0.3"/>'
     '<line x1="168" y1="95" x2="128" y2="195" stroke="white" stroke-width="1" opacity="0.3"/>'),

    # ── Group 5: Sports/Hobby (Purple) ──
    ("headphones",
     '<path d="M68 140a60 60 0 0 1 120 0" fill="none" stroke="white" stroke-width="8" stroke-linecap="round" opacity="0.9"/>'
     '<rect x="58" y="135" width="22" height="40" rx="10" fill="white" opacity="0.85"/>'
     '<rect x="176" y="135" width="22" height="40" rx="10" fill="white" opacity="0.85"/>'
     '<rect x="62" y="140" width="14" height="30" rx="6" fill="white" opacity="0.4"/>'
     '<rect x="180" y="140" width="14" height="30" rx="6" fill="white" opacity="0.4"/>'),
    ("gamepad",
     '<rect x="58" y="95" width="140" height="75" rx="30" fill="white" opacity="0.9"/>'
     '<circle cx="102" cy="128" r="6" fill="white" opacity="0.4"/>'
     '<rect x="95" y="110" width="14" height="4" rx="2" fill="white" opacity="0.4"/>'
     '<rect x="100" y="105" width="4" height="14" rx="2" fill="white" opacity="0.4"/>'
     '<circle cx="158" cy="120" r="5" fill="white" opacity="0.4"/>'
     '<circle cx="170" cy="128" r="5" fill="white" opacity="0.4"/>'
     '<circle cx="158" cy="136" r="5" fill="white" opacity="0.4"/>'
     '<circle cx="146" cy="128" r="5" fill="white" opacity="0.4"/>'),
    ("music-note",
     '<circle cx="100" cy="175" r="22" fill="white" opacity="0.85"/>'
     '<rect x="118" y="65" width="8" height="115" rx="3" fill="white" opacity="0.9"/>'
     '<path d="M126 65l40-15v30l-40 12z" fill="white" opacity="0.7"/>'),
    ("camera",
     '<rect x="65" y="90" width="126" height="90" rx="14" fill="white" opacity="0.9"/>'
     '<circle cx="128" cy="138" r="30" fill="white" opacity="0.35"/>'
     '<circle cx="128" cy="138" r="20" fill="white" opacity="0.35"/>'
     '<rect x="105" y="75" width="46" height="20" rx="6" fill="white" opacity="0.7"/>'
     '<circle cx="170" cy="105" r="6" fill="white" opacity="0.4"/>'),
    ("rocket",
     '<path d="M128 50c-20 30-25 70-25 100h50c0-30-5-70-25-100z" fill="white" opacity="0.9"/>'
     '<path d="M103 140l-18 30h18z" fill="white" opacity="0.7"/>'
     '<path d="M153 140l18 30h-18z" fill="white" opacity="0.7"/>'
     '<circle cx="128" cy="120" r="10" fill="white" opacity="0.35"/>'
     '<path d="M118 175l10 20 10-20z" fill="white" opacity="0.6"/>'),
    ("lightning",
     '<path d="M145 50l-50 85h35l-15 75 55-95h-35z" fill="white" opacity="0.9"/>'),
]


def _human_icon(idx: int) -> str:
    """Generate a human avatar with a recognizable silhouette/icon on a gradient background."""
    group = idx // 6          # 0-5: which color palette group
    design = idx % 6          # 0-5: which design within the group
    icon_idx = group * 6 + design

    # Wrap palette index for safety
    pal = HUMAN_PALETTES[group % len(HUMAN_PALETTES)]
    _name, icon_svg = HUMAN_ICONS[icon_idx % len(HUMAN_ICONS)]

    grad = _gradient("bg", pal[0], pal[1], 135)
    return (
        f'<svg width="256" height="256" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">'
        f'<defs>{grad}</defs>'
        f'<rect width="256" height="256" rx="32" fill="url(#bg)"/>'
        f'{icon_svg}'
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

    # Generate 36 human avatars (6 groups x 6 designs)
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
