"""Colours: parsing, blending, and SGR for each terminal colour depth.

A colour is a tuple `(r, g, b, index)`. `index` is -1 for a colour given as
RGB, or the xterm-256 index when the user named one (`38;5;141`, `141`), in
which case that exact index is emitted so the terminal's own palette wins.

Modes: "truecolor" (38;2;r;g;b), "256" (nearest xterm index), "16" (nearest
basic ANSI colour) and "none".
"""
from __future__ import annotations

import os

MODES = ("auto", "truecolor", "256", "16", "none")

# xterm's defaults for the 16 base colours; terminals differ, which is why
# an explicit index is always emitted as an index.
_BASE16 = (
    (0, 0, 0), (205, 0, 0), (0, 205, 0), (205, 205, 0), (0, 0, 238), (205, 0, 205),
    (0, 205, 205), (229, 229, 229), (127, 127, 127), (255, 0, 0), (0, 255, 0),
    (255, 255, 0), (92, 92, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255),
)
_CUBE = (0, 95, 135, 175, 215, 255)


def index_rgb(n: int):
    if n < 16:
        return _BASE16[n]
    if n < 232:
        n -= 16
        return _CUBE[n // 36], _CUBE[(n // 6) % 6], _CUBE[n % 6]
    v = 8 + 10 * (n - 232)
    return v, v, v


def rgb(r, g, b):
    return (int(r), int(g), int(b), -1)


def parse(spec):
    """A colour from '#rrggbb', '#rgb', an xterm index, or an SGR parameter
    string ('38;5;141', '38;2;r;g;b', '31'). None when it is not a colour."""
    if isinstance(spec, bool):
        return None
    if isinstance(spec, int):
        return (*index_rgb(spec), spec) if 0 <= spec <= 255 else None
    if isinstance(spec, (tuple, list)) and len(spec) in (3, 4):
        try:
            r, g, b = (max(0, min(255, int(x))) for x in spec[:3])
            idx = int(spec[3]) if len(spec) == 4 else -1
            return (r, g, b, idx)
        except (TypeError, ValueError):
            return None
    if not isinstance(spec, str):
        return None
    s = spec.strip().lower()
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            try:
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), -1)
            except ValueError:
                return None
        return None
    if s.isdigit():
        n = int(s)
        if 30 <= n <= 37 or 90 <= n <= 97:     # a bare SGR foreground code
            idx = n - 30 if n < 90 else n - 82
            return (*index_rgb(idx), idx)
        return (*index_rgb(n), n) if n <= 255 else None
    parts = s.split(";")
    try:
        if len(parts) == 3 and parts[0] in ("38", "48") and parts[1] == "5":
            n = int(parts[2])
            return (*index_rgb(n), n) if 0 <= n <= 255 else None
        if len(parts) == 5 and parts[0] in ("38", "48") and parts[1] == "2":
            r, g, b = (max(0, min(255, int(x))) for x in parts[2:])
            return (r, g, b, -1)
    except ValueError:
        return None
    return None


def hex_of(c) -> str:
    return "#%02x%02x%02x" % (c[0], c[1], c[2])


def mix(a, b, t: float):
    """`a` moved a fraction `t` of the way to `b`, as RGB."""
    t = max(0.0, min(1.0, t))
    return (round(a[0] + (b[0] - a[0]) * t), round(a[1] + (b[1] - a[1]) * t),
            round(a[2] + (b[2] - a[2]) * t), -1)


def luminance(c) -> float:
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def contrast(a, b) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def readable_on(bg, dark, light):
    """Whichever of `dark` and `light` reads better on `bg`."""
    return dark if contrast(bg, dark) >= contrast(bg, light) else light


def _nearest256(r, g, b) -> int:
    def cube(v):
        return 0 if v < 48 else (1 if v < 115 else (v - 35) // 40)
    ci = cube(r), cube(g), cube(b)
    cr, cg, cb = _CUBE[ci[0]], _CUBE[ci[1]], _CUBE[ci[2]]
    cube_idx = 16 + 36 * ci[0] + 6 * ci[1] + ci[2]
    avg = (r + g + b) // 3
    gi = 23 if avg > 238 else max(0, (avg - 3) // 10)
    gv = 8 + 10 * gi
    d_cube = (cr - r) ** 2 + (cg - g) ** 2 + (cb - b) ** 2
    d_gray = (gv - r) ** 2 + (gv - g) ** 2 + (gv - b) ** 2
    return cube_idx if d_cube <= d_gray else 232 + gi


def _nearest16(r, g, b) -> int:
    best, dist = 7, 1 << 30
    for i, (br, bg_, bb) in enumerate(_BASE16):
        d = (br - r) ** 2 + (bg_ - g) ** 2 + (bb - b) ** 2
        if d < dist:
            best, dist = i, d
    return best


_SGR: dict = {}


def sgr(c, mode: str, background: bool = False) -> str:
    """SGR parameters that select colour `c` in `mode`, or '' for none."""
    if c is None or mode == "none":
        return ""
    key = (c, mode, background)
    out = _SGR.get(key)
    if out is not None:
        return out
    r, g, b, idx = c
    base = 48 if background else 38
    if mode == "16":
        n = idx if 0 <= idx < 16 else _nearest16(r, g, b) if idx < 0 else _nearest16(*index_rgb(idx))
        out = str((40 if background else 30) + n) if n < 8 else str((100 if background else 90) + n - 8)
    elif idx >= 0:
        out = f"{base};5;{idx}"
    elif mode == "256":
        out = f"{base};5;{_nearest256(r, g, b)}"
    else:
        out = f"{base};2;{r};{g};{b}"
    _SGR[key] = out
    return out


def detect_mode(env=None) -> str:
    """The colour depth the environment asks for."""
    env = os.environ if env is None else env
    if env.get("NO_COLOR"):
        return "none"
    forced = env.get("CLAUDE_STATUSLINE_COLOR", "").strip().lower()
    if forced in MODES and forced != "auto":
        return forced
    if env.get("COLORTERM", "").lower() in ("truecolor", "24bit"):
        return "truecolor"
    term = env.get("TERM", "")
    if term in ("xterm-kitty", "xterm-ghostty", "wezterm", "alacritty", "foot") or "direct" in term:
        return "truecolor"
    if term in ("linux", "vt100", "vt220", "ansi") or term.endswith("-16color"):
        return "16"
    return "256"
