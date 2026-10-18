"""Light bulb design studio: ten candidate designs, each drawn as SVG at any brightness.

Run `python scripts/bulb_designs.py` to render the gallery (HTML + PNG) at 50% brightness on the
dark theme. Brightness b is 0..1; every design takes it as its only dial, so the chosen design
can later be shown at ten levels, one per 10% of ideas.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

W, H = 120, 160

BULB = (
    "M60 10 C34 10 18 30 18 54 C18 72 27 84 37 96 C41 101 42 106 42 112 "
    "L78 112 C78 106 79 101 83 96 C93 84 102 72 102 54 C102 30 86 10 60 10 Z"
)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mix(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> str:
    return "#%02x%02x%02x" % tuple(int(round(lerp(x, y, t))) for x, y in zip(c1, c2))


DIM = (96, 58, 18)
WARM = (255, 178, 52)
HOT = (255, 238, 186)


def glow_colour(b: float) -> str:
    """Dim ember -> amber -> warm white as brightness rises."""
    if b < 0.6:
        return mix(DIM, WARM, b / 0.6)
    return mix(WARM, HOT, (b - 0.6) / 0.4)


def wave(y: float, amp: float, x0: float, x1: float, periods: float, phase: float = 0.0) -> str:
    pts = []
    n = 48
    for i in range(n + 1):
        t = i / n
        x = lerp(x0, x1, t)
        yy = y + amp * math.sin(2 * math.pi * periods * t + phase)
        pts.append(f"{x:.1f} {yy:.1f}")
    return "M" + " L".join(pts)


def glow_filter(fid: str, std: float) -> str:
    return (
        f'<filter id="{fid}" x="-60%" y="-60%" width="220%" height="220%">'
        f'<feGaussianBlur stdDeviation="{std:.2f}" result="g"/>'
        f'<feMerge><feMergeNode in="g"/><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge>'
        "</filter>"
    )


def halo(uid: str, b: float, r: float = 74, cy: float = 54) -> str:
    c = glow_colour(min(1.0, b + 0.15))
    return (
        f'<defs><radialGradient id="{uid}h" cx="50%" cy="50%" r="50%">'
        f'<stop offset="0" stop-color="{c}" stop-opacity="{0.05 + 0.5 * b:.2f}"/>'
        f'<stop offset="1" stop-color="{c}" stop-opacity="0"/></radialGradient></defs>'
        f'<circle cx="60" cy="{cy}" r="{r}" fill="url(#{uid}h)"/>'
    )


def wrap(inner: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W*2}" height="{H*2}" style="overflow:visible">{inner}</svg>'


def neon_base(col: str, sw: float = 3.0) -> str:
    return (
        f'<g fill="none" stroke="{col}" stroke-width="{sw}" stroke-linecap="round">'
        '<path d="M44 119 H76"/><path d="M44 128 H76"/><path d="M45 137 H75"/>'
        '<path d="M50 146 H70"/></g>'
    )


# 1 -- Neon outline, four waves (closest to reference 4, "idea" scribble swapped for waves)
def d1(b: float) -> str:
    u, col = "d1", glow_colour(b)
    waves = "".join(
        f'<path d="{wave(y, 3.2, 38, 82, 2.5, ph)}"/>'
        for y, ph in ((38, 0), (47, 1.2), (56, 2.4), (65, 3.6))
    )
    return wrap(
        halo(u, b)
        + f"<defs>{glow_filter(u + 'g', 1.2 + 2.6 * b)}</defs>"
        + f'<g filter="url(#{u}g)" fill="none" stroke="{col}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">'
        + f'<path d="{BULB}"/>'
        + f'<g stroke-width="2.2">{waves}</g>'
        + neon_base(col)
        + "</g>"
    )


# 2 -- Neon outline, support wires and a zig-zag filament
def d2(b: float) -> str:
    u, col = "d2", glow_colour(b)
    zig = "M42 58 L48 44 L54 58 L60 44 L66 58 L72 44 L78 58"
    return wrap(
        halo(u, b)
        + f"<defs>{glow_filter(u + 'g', 1.2 + 2.6 * b)}</defs>"
        + f'<g filter="url(#{u}g)" fill="none" stroke="{col}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">'
        + f'<path d="{BULB}"/>'
        + f'<path d="M50 112 V80 L42 58 M70 112 V80 L78 58" stroke-width="2"/>'
        + f'<path d="{zig}" stroke-width="2.4"/>'
        + neon_base(col)
        + "</g>"
    )


def brass(uid: str) -> str:
    return (
        f'<linearGradient id="{uid}b" x1="0" x2="1">'
        '<stop offset="0" stop-color="#4d3611"/><stop offset=".3" stop-color="#d1a54c"/>'
        '<stop offset=".55" stop-color="#8d6a24"/><stop offset="1" stop-color="#3f2c0d"/></linearGradient>'
    )


def edison_base(uid: str) -> str:
    ridges = "".join(
        f'<path d="M43 {y} Q60 {y + 5} 77 {y}" fill="none" stroke="#2b1d08" stroke-width="1.6" opacity=".75"/>'
        for y in (119, 127, 135)
    )
    return (
        f'<path d="M42 112 H78 V138 Q78 144 70 146 H50 Q42 144 42 138 Z" fill="url(#{uid}b)"/>'
        + ridges
        + '<path d="M50 147 H70 L66 152 H54 Z" fill="#241a09"/>'
    )


def glass(uid: str, b: float) -> str:
    c = glow_colour(b)
    return (
        f'<radialGradient id="{uid}s" cx="50%" cy="40%" r="60%">'
        f'<stop offset="0" stop-color="{c}" stop-opacity="{0.05 + 0.28 * b:.2f}"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0.03"/></radialGradient>'
    )


def glass_shapes(uid: str) -> str:
    return (
        f'<path d="{BULB}" fill="url(#{uid}s)" stroke="#f3e3bd" stroke-opacity=".38" stroke-width="1.6"/>'
        '<path d="M28 44 C28 30 40 18 52 16" fill="none" stroke="#fff" stroke-opacity=".5" stroke-width="2.4" stroke-linecap="round"/>'
        '<path d="M30 60 C30 55 31 51 32 48" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="2" stroke-linecap="round"/>'
        '<ellipse cx="60" cy="13.5" rx="6" ry="2" fill="#fff" opacity=".28"/>'
    )


# 3 -- Edison realistic: glass, brass cap, coiled tungsten filament (reference 2)
def d3(b: float) -> str:
    u, col = "d3", glow_colour(b)
    pts = []
    for i in range(0, 241):
        t = i / 240 * 6 * math.pi
        x = 38 + 44 * i / 240 + 6.5 * math.cos(t)
        y = 54 + 9 * math.sin(t)
        pts.append(f"{x:.1f} {y:.1f}")
    coil = "M" + " L".join(pts)
    return wrap(
        halo(u, b)
        + f"<defs>{brass(u)}{glass(u, b)}{glow_filter(u + 'g', 1.0 + 2.2 * b)}</defs>"
        + glass_shapes(u)
        + f'<path d="M52 112 V86 L38 56 M68 112 V86 L82 56" fill="none" stroke="#c9b48a" stroke-opacity=".7" stroke-width="1.4"/>'
        + f'<g filter="url(#{u}g)"><path d="{coil}" fill="none" stroke="{col}" stroke-width="2.2" stroke-linejoin="round"/></g>'
        + f'<path d="{coil}" fill="none" stroke="{glow_colour(min(1, b + .35))}" stroke-width=".9" opacity="{0.4 + 0.6 * b:.2f}"/>'
        + edison_base(u)
    )


# 4 -- Edison cage: four tall loops and a cross-bar, like the vintage squirrel-cage lamp
def d4(b: float) -> str:
    u, col = "d4", glow_colour(b)
    loops = "".join(
        f'<ellipse cx="{x}" cy="50" rx="4.2" ry="21" transform="rotate({r} {x} 50)"/>'
        for x, r in ((42, -6), (53, -2), (65, 2), (77, 6))
    )
    return wrap(
        halo(u, b)
        + f"<defs>{brass(u)}{glass(u, b)}{glow_filter(u + 'g', 1.0 + 2.2 * b)}</defs>"
        + glass_shapes(u)
        + '<path d="M54 112 V78 M66 112 V78" stroke="#c9b48a" stroke-opacity=".7" stroke-width="1.4" fill="none"/>'
        + f'<g filter="url(#{u}g)" fill="none" stroke="{col}" stroke-width="1.9">{loops}'
        + f'<path d="M38 40 H82 M40 60 H80" stroke-width="1.4"/><path d="M48 78 L42 62 M72 78 L78 62" stroke-width="1.4"/></g>'
        + edison_base(u)
    )


# 5 -- Amber halo, tangled filament (reference 3)
def d5(b: float) -> str:
    u = "d5"
    c = glow_colour(b)
    tangle = (
        "M44 74 C40 52 50 36 56 56 C60 70 46 76 54 52 C58 40 66 38 64 58 "
        "C63 74 76 70 70 50 C68 42 80 40 78 60 C77 70 72 76 66 66"
    )
    return wrap(
        f'<defs><radialGradient id="{u}a" cx="50%" cy="45%" r="55%">'
        f'<stop offset="0" stop-color="#ff9a2e" stop-opacity="{0.18 + 0.6 * b:.2f}"/>'
        '<stop offset="1" stop-color="#ff9a2e" stop-opacity="0"/></radialGradient>'
        f"{glass(u, b)}{glow_filter(u + 'g', 1.2 + 3 * b)}{brass(u)}</defs>"
        f'<circle cx="60" cy="56" r="78" fill="url(#{u}a)"/>'
        + f'<path d="{BULB}" fill="url(#{u}s)" stroke="#ffd9a0" stroke-opacity=".45" stroke-width="1.3"/>'
        + '<path d="M26 50 C26 34 38 20 50 16" fill="none" stroke="#fff" stroke-opacity=".4" stroke-width="2.4" stroke-linecap="round"/>'
        + f'<g filter="url(#{u}g)" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        + f'<path d="{tangle}"/><path d="M54 112 V86 L48 74 M66 112 V86 L66 66" stroke-width="1.4"/></g>'
        + f'<path d="{tangle}" fill="none" stroke="{glow_colour(min(1, b + .35))}" stroke-width=".8" opacity="{0.4 + 0.6 * b:.2f}"/>'
        + edison_base(u)
    )


# 6 -- Neon tube: thick soft tube plus a bright core line, looping cursive scribble inside
def d6(b: float) -> str:
    u, col = "d6", glow_colour(b)
    core = glow_colour(min(1, b + 0.3))
    scribble = (
        "M38 52 C38 36 52 36 52 50 C52 62 40 66 44 56 "
        "C48 46 62 40 62 54 C62 66 50 70 54 60 "
        "C58 50 74 44 74 56 C74 68 62 72 66 62 C68 56 80 54 82 48"
    )
    return wrap(
        halo(u, b)
        + f"<defs>{glow_filter(u + 'g', 1.6 + 3 * b)}</defs>"
        + f'<g filter="url(#{u}g)" fill="none" stroke-linecap="round" stroke-linejoin="round">'
        + f'<path d="{BULB}" stroke="{col}" stroke-width="6" opacity=".55"/>'
        + f'<path d="{BULB}" stroke="{core}" stroke-width="1.8"/>'
        + f'<path d="{scribble}" stroke="{col}" stroke-width="4" opacity=".55"/><path d="{scribble}" stroke="{core}" stroke-width="1.6"/>'
        + f'<g stroke="{col}" stroke-width="3"><path d="M44 119 H76"/><path d="M44 128 H76"/><path d="M45 137 H75"/><path d="M50 146 H70"/></g>'
        + "</g>"
    )



# 6b -- the chosen look: neon tube outline and base, horizontal coil (as in 3), grey support wires
def d6b(b: float, theme: str = "dark") -> str:
    u, col = "d6b", glow_colour(b)
    core = glow_colour(min(1, b + 0.3))
    wire = "#9a9a9a" if theme == "dark" else "#6f6f6f"
    pts = []
    for i in range(0, 241):
        t = i / 240 * 6 * math.pi
        x = 38 + 44 * i / 240 + 6.5 * math.cos(t)
        y = 54 + 9 * math.sin(t)
        pts.append(f"{x:.1f} {y:.1f}")
    coil = "M" + " L".join(pts)
    # Two thin wires rise from the base, bend out to each end of the coil, and a short cross-wire holds the stem.
    wires = "M52 112 V90 L44.5 56 M68 112 V90 L88.5 56"
    return wrap(
        halo(u, b)
        + f"<defs>{glow_filter(u + 'g', 1.6 + 3 * b)}</defs>"
        + f'<path d="{wires}" fill="none" stroke="{wire}" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>'
        + f'<circle cx="52" cy="90" r="1.6" fill="{wire}"/><circle cx="68" cy="90" r="1.6" fill="{wire}"/>'
        + f'<g filter="url(#{u}g)" fill="none" stroke-linecap="round" stroke-linejoin="round">'
        + f'<path d="{BULB}" stroke="{col}" stroke-width="6" opacity=".55"/>'
        + f'<path d="{BULB}" stroke="{core}" stroke-width="1.8"/>'
        + f'<path d="{coil}" stroke="{col}" stroke-width="3.4" opacity=".55"/><path d="{coil}" stroke="{core}" stroke-width="1.4"/>'
        + f'<g stroke="{col}" stroke-width="3"><path d="M44 119 H76"/><path d="M44 128 H76"/><path d="M45 137 H75"/><path d="M50 146 H70"/></g>'
        + "</g>"
    )

# 7 -- Technical cutaway: thin line art, glass stem, compact coil on two posts
def d7(b: float) -> str:
    u, col = "d7", glow_colour(b)
    pts = []
    for i in range(0, 121):
        t = i / 120 * 8 * math.pi
        pts.append(f"{46 + 28 * i / 120:.1f} {50 + 5.5 * math.sin(t):.1f}")
    coil = "M" + " L".join(pts)
    return wrap(
        halo(u, b, r=60)
        + f"<defs>{glow_filter(u + 'g', 1.0 + 2.4 * b)}</defs>"
        + f'<path d="{BULB}" fill="none" stroke="#e9dcc0" stroke-opacity=".55" stroke-width="1.2"/>'
        + '<path d="M52 112 V96 C52 90 56 88 56 84 H64 C64 88 68 90 68 96 V112" fill="none" stroke="#e9dcc0" stroke-opacity=".5" stroke-width="1.2"/>'
        + '<path d="M56 84 V58 M64 84 V58" stroke="#e9dcc0" stroke-opacity=".6" stroke-width="1.2"/>'
        + f'<path d="M46 50 L56 58 M74 50 L64 58 M46 50 V36 M74 50 V36" fill="none" stroke="#e9dcc0" stroke-opacity=".6" stroke-width="1.2"/>'
        + f'<g filter="url(#{u}g)"><path d="{coil}" fill="none" stroke="{col}" stroke-width="2" stroke-linejoin="round"/></g>'
        + '<g fill="none" stroke="#e9dcc0" stroke-opacity=".6" stroke-width="1.2"><path d="M44 112 H76 V146 H44 Z"/>'
        + '<path d="M44 121 H76 M44 130 H76 M44 139 H76"/></g>'
    )


# 8 -- Flat solid: gold fill, glass shine, steel cap (reference 5, lit side)
def d8(b: float) -> str:
    u = "d8"
    top = mix((120, 84, 34), (255, 226, 92), b)
    bot = mix((96, 56, 18), (255, 170, 40), b)
    line = mix((70, 40, 14), (140, 78, 12), b)
    return wrap(
        halo(u, b)
        + f'<defs><linearGradient id="{u}f" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bot}"/></linearGradient>'
        '<linearGradient id="d8c" x1="0" x2="1"><stop offset="0" stop-color="#4a5a74"/><stop offset=".45" stop-color="#9db0cc"/>'
        '<stop offset="1" stop-color="#3d4a63"/></linearGradient></defs>'
        + f'<path d="{BULB}" fill="url(#{u}f)" stroke="{line}" stroke-width="2.4" stroke-linejoin="round"/>'
        + '<path d="M30 40 C32 28 42 20 52 18 C42 26 36 36 34 50 Z" fill="#fff" opacity=".55"/>'
        + '<path d="M88 40 C86 32 82 26 76 22 C82 30 84 38 85 46 Z" fill="#fff" opacity=".4"/>'
        + f'<g fill="none" stroke="{line}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        + '<path d="M50 112 V92 L44 66 M70 112 V92 L76 66"/><path d="M44 66 L50 76 L56 62 L62 76 L68 62 L74 76 L76 66"/></g>'
        + '<path d="M42 112 H78 V138 Q78 144 70 146 H50 Q42 144 42 138 Z" fill="url(#d8c)" stroke="#2c3750" stroke-width="2"/>'
        + '<path d="M43 121 H77 M43 130 H77" stroke="#2c3750" stroke-width="2"/><path d="M52 147 H68 L65 152 H55 Z" fill="#2c3750"/>'
    )


# 9 -- Neon outline, ember-to-gold wave gradient and rays around the crown
def d9(b: float) -> str:
    u, col = "d9", glow_colour(b)
    rays = "".join(
        f'<path d="M{60 + 50 * math.cos(math.radians(a)):.1f} {54 - 50 * math.sin(math.radians(a)):.1f} '
        f'L{60 + (50 + 8 + 10 * b) * math.cos(math.radians(a)):.1f} {54 - (50 + 8 + 10 * b) * math.sin(math.radians(a)):.1f}"/>'
        for a in (20, 50, 80, 100, 130, 160)
    )
    waves = "".join(
        f'<path d="{wave(y, 3.4, 37, 83, 2, ph)}"/>' for y, ph in ((40, 0), (52, 1.5), (64, 3.0))
    )
    return wrap(
        halo(u, b)
        + f'<defs>{glow_filter(u + "g", 1.2 + 2.6 * b)}'
        f'<linearGradient id="{u}w" x1="0" x2="1"><stop offset="0" stop-color="{mix((190, 60, 40), (255, 90, 54), b)}"/>'
        f'<stop offset="1" stop-color="{mix((190, 120, 40), (255, 200, 70), b)}"/></linearGradient></defs>'
        + f'<g filter="url(#{u}g)" fill="none" stroke-linecap="round" stroke-linejoin="round">'
        + f'<path d="{BULB}" stroke="{col}" stroke-width="3"/>'
        + f'<g stroke="url(#{u}w)" stroke-width="2.6">{waves}</g>'
        + f'<g stroke="{col}" stroke-width="2" opacity="{0.35 + 0.65 * b:.2f}">{rays}</g>'
        + neon_base(col)
        + "</g>"
    )


# 10 -- Glass with reflections, one arched filament and a hot core, standing on a soft reflection
def d10(b: float) -> str:
    u, col = "d10", glow_colour(b)
    core = glow_colour(min(1, b + 0.35))
    return wrap(
        halo(u, b)
        + f"<defs>{brass(u)}{glass(u, b)}{glow_filter(u + 'g', 1.4 + 3 * b)}</defs>"
        + '<ellipse cx="60" cy="156" rx="26" ry="3.2" fill="#fff" opacity=".07"/>'
        + glass_shapes(u)
        + '<path d="M96 52 C96 66 90 76 84 86" fill="none" stroke="#fff" stroke-opacity=".28" stroke-width="2" stroke-linecap="round"/>'
        + '<path d="M52 112 V84 L44 62 M68 112 V84 L76 62" fill="none" stroke="#c9b48a" stroke-opacity=".7" stroke-width="1.4"/>'
        + f'<g filter="url(#{u}g)"><path d="M44 62 C44 30 76 30 76 62" fill="none" stroke="{col}" stroke-width="2.6" stroke-linecap="round"/></g>'
        + f'<path d="M44 62 C44 30 76 30 76 62" fill="none" stroke="{core}" stroke-width="1" opacity="{0.45 + 0.55 * b:.2f}"/>'
        + f'<circle cx="60" cy="38.5" r="{2 + 2.5 * b:.1f}" fill="{core}" opacity="{0.4 + 0.6 * b:.2f}" filter="url(#{u}g)"/>'
        + edison_base(u)
    )


DESIGNS = [
    ("1", "Neon outline, four waves", d1),
    ("2", "Neon outline, zig-zag filament", d2),
    ("3", "Edison realistic, coiled filament", d3),
    ("4", "Edison cage, tall loops", d4),
    ("5", "Amber halo, tangled filament", d5),
    ("6", "Neon tube, looping scribble", d6),
    ("7", "Technical cutaway, thin line art", d7),
    ("8", "Flat solid gold, glass shine", d8),
    ("9", "Neon, red-to-gold waves and rays", d9),
    ("10", "Glass reflections, arched filament", d10),
]


def gallery(b: float = 0.5, theme: str = "dark") -> str:
    bg = "#14110d" if theme == "dark" else "#fbf7ee"
    fg = "#e8dcc5" if theme == "dark" else "#3a2f1e"
    cells = "".join(
        f'<figure><div class="art">{fn(b)}</div><figcaption><b>{num}</b> {label}</figcaption></figure>'
        for num, label, fn in DESIGNS
    )
    return (
        f'<!doctype html><meta charset="utf-8"><style>body{{margin:0;background:{bg};color:{fg};font:15px system-ui,sans-serif;padding:28px}}'
        'h1{font-size:20px;margin:0 0 18px}.grid{display:grid;grid-template-columns:repeat(5,1fr);gap:18px}'
        f'figure{{margin:0;background:{"#1c1812" if theme == "dark" else "#fff"};border:1px solid {"#2d261c" if theme == "dark" else "#e6dcc6"};border-radius:14px;padding:14px;text-align:center}}'
        '.art svg{width:100%;height:auto;max-width:240px}figcaption{margin-top:8px}</style>'
        f"<h1>Light bulb designs at {int(b * 100)}% brightness, {theme} theme</h1><div class=\"grid\">{cells}</div>"
    )


def levels_sheet(theme: str = "dark") -> str:
    bg = "#14110d" if theme == "dark" else "#fbf7ee"
    fg = "#e8dcc5" if theme == "dark" else "#3a2f1e"
    cells = "".join(
        f'<figure><div class="art">{d6b((n - 0.5) / 10, theme)}</div><figcaption>{n}</figcaption></figure>' for n in range(1, 11)
    )
    return (
        f'<!doctype html><meta charset="utf-8"><style>body{{margin:0;background:{bg};color:{fg};font:15px system-ui;padding:24px}}'
        '.grid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}figure{margin:0;text-align:center}'
        '.art svg{width:100%;height:auto;max-width:200px}</style>'
        f'<div class="grid">{cells}</div>'
    )


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-0/bulbs")
    out.mkdir(parents=True, exist_ok=True)
    (out / "gallery.html").write_text(gallery(0.5, "dark"))
    for num, _label, fn in DESIGNS:
        (out / f"bulb-{num}.svg").write_text(fn(0.5))
    (out / "bulb-6b.svg").write_text(d6b(0.5))
    (out / "levels-dark.html").write_text(levels_sheet("dark"))
    print("wrote", out)
