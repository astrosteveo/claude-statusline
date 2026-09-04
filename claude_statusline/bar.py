"""Usage bars: named styles, fills, caps, sub-cell resolution and a
continuous track.

A bar is `width` cells of fill glyph, a boundary cell with sub-cell
resolution, and the rest as track. Three things are chosen independently:

    style   the glyph set: block, shade, thin, dots, pips, ascii (STYLES)
    fill    how the filled cells are coloured: one colour by threshold
            ("level"), a colour per cell by its own position ("gradient"),
            a fixed [colors] key, or a comma-separated list of keys spread
            evenly along the bar
    track   the [colors] key for the empty cells and the caps

Every glyph is one terminal cell; the fitter depends on it.
"""
from __future__ import annotations

from .ansi import c
from .config import CFG, C
from .util import num


def pct_color(pct) -> str:
    t = CFG["thresholds"]
    pct = num(pct, 0)
    if pct >= t["red"]:
        return "red"
    if pct >= t["orange"]:
        return "orange"
    if pct >= t["yellow"]:
        return "yellow"
    return "green"


# --- glyph families -----------------------------------------------------------
#
# Two families of partial-fill glyph for the block styles, and they do not mix.
#
#   shade   ░▒▓  vary *density* and ink the whole cell, so a partial cell keeps
#                the same texture as the ░ track running through it.
#   eighth  ▏▎▍  vary *width*, painting a sliver at the left of the cell and
#                leaving the rest as bare background — precise, but it punches
#                a visible hole in a shaded track. Only sensible when the track
#                is blank (empty = " ") or solid (the remainder is painted).
_EIGHTHS = "▏▎▍▌▋▊▉"          # 1/8 .. 7/8, left-aligned
_SHADES = "░▒▓"               # ~25%, ~50%, ~75% density, full cell

_SHADE_TRACK = ("░", "▒", "▓")   # textured track
_SOLID_TRACK = ("█",)            # fully-inked track
_BLANK_TRACK = (" ", "")         # bare terminal background

# Named styles. `ramp` is the style's own partial-cell glyphs, ascending; the
# block styles leave it empty and pick a family from the track instead.
STYLES = {
    "block": {"full": "█", "empty": "█", "ramp": "", "cap_left": "", "cap_right": "",
              "doc": "solid fill on a solid track, eighth-cell resolution (the default)"},
    "shade": {"full": "█", "empty": "░", "ramp": "", "cap_left": "", "cap_right": "",
              "doc": "solid fill on a textured ░ track, shaded boundary cell"},
    "thin":  {"full": "━", "empty": "─", "ramp": "╸", "cap_left": "", "cap_right": "",
              "doc": "a heavy rule over a light one, half-cell resolution"},
    "dots":  {"full": "●", "empty": "○", "ramp": "◐", "cap_left": "", "cap_right": "",
              "doc": "filled and hollow circles, half-cell resolution"},
    "pips":  {"full": "▰", "empty": "▱", "ramp": "", "cap_left": "", "cap_right": "",
              "doc": "slanted pips, whole cells only"},
    "ascii": {"full": "#", "empty": "-", "ramp": "", "cap_left": "[", "cap_right": "]",
              "doc": "plain ASCII in brackets, for fonts without block glyphs"},
}
FILLS = ("level", "gradient")     # plus any [colors] key, or a comma-separated list of them


def style_glyphs() -> str:
    """Every glyph a style can emit; tests hold each to one cell."""
    out = set(_EIGHTHS + _SHADES)
    for spec in STYLES.values():
        for key in ("full", "empty", "ramp", "cap_left", "cap_right"):
            out.update(spec[key])
    return "".join(sorted(out))


def _as_bg(spec: str):
    """Turn a foreground SGR spec into its background equivalent."""
    if spec.startswith("38;"):
        return "48;" + spec[3:]
    if spec.isdigit() and 30 <= int(spec) <= 37:
        return str(int(spec) + 10)
    if spec.isdigit() and 90 <= int(spec) <= 97:
        return str(int(spec) + 10)
    return None


def _partial_plan(style: str, empty_ch: str):
    """Pick a boundary-cell family for a block style whose remainder matches
    the track.

    An eighth-block inks only the left fraction of its cell, so the rest must
    be painted to match the track or it reads as a hole. That works when the
    track is solid (paint the cell background) or blank (paint nothing), but a
    textured ░ track cannot be reproduced by a solid background — there, the
    shade family is the only family that stays continuous.
    """
    if style == "auto":
        style = "shade" if empty_ch in _SHADE_TRACK else "eighth"
    if style == "eighth":
        return "eighth", empty_ch in _SOLID_TRACK
    return style, False


# --- resolution -------------------------------------------------------------
def resolve(style=None, fill=None) -> dict:
    """The effective bar settings for one call.

    [bar].style names the glyph set; [bar].full / empty override its glyphs
    when set ("" means "from the style"). Those overrides belong to the
    configured style: a segment that asks for a different style gets that
    style's own glyphs, untouched. Caps frame every bar, whatever its style.
    """
    bcfg = CFG["bar"]
    configured = bcfg.get("style") or "block"
    name = style or configured
    if name not in STYLES:
        name = "block"
    spec = STYLES[name]
    own = name == configured

    def glyph(key, scoped=True):
        val = bcfg.get(key)
        if isinstance(val, str) and val != "" and (own or not scoped):
            return val
        return spec[key]

    return {
        "style": name,
        "full": glyph("full"),
        "empty": glyph("empty"),
        "ramp": spec["ramp"],
        "cap_left": glyph("cap_left", scoped=False),
        "cap_right": glyph("cap_right", scoped=False),
        "fill": fill or bcfg.get("fill") or "level",
        "track": bcfg.get("track") or "dim",
        "partial": bcfg.get("partial", True),
        "partial_style": bcfg.get("partial_style", "auto"),
        "min_sliver": bcfg.get("min_sliver", True),
        "pulse": bool(bcfg.get("pulse", False)),
    }


def check(cfg=None):
    """Problems with the [bar] section and its values; (path, message) pairs."""
    bcfg = (cfg or CFG)["bar"]
    colors = (cfg or CFG)["colors"]
    out = []
    style = bcfg.get("style", "block")
    if style not in STYLES:
        out.append(("bar.style", f"unknown style {style!r}; one of {', '.join(STYLES)}"))
    ps = bcfg.get("partial_style", "auto")
    if ps not in ("auto", "eighth", "shade", "off"):
        out.append(("bar.partial_style", f"unknown partial_style {ps!r}; auto, eighth, shade or off"))
    out += [("bar.fill", m) for m in check_fill(bcfg.get("fill", "level"), colors)]
    track = bcfg.get("track", "dim")
    if track not in colors:
        out.append(("bar.track", f"unknown colour {track!r}; add it under [colors]"))
    for key in ("full", "empty", "cap_left", "cap_right"):
        val = bcfg.get(key, "")
        if isinstance(val, str) and len(val) > 1:
            out.append((f"bar.{key}", "must be a single glyph"))
    return out


def check_fill(fill, colors) -> list:
    """Messages about a fill spec: level, gradient, or [colors] keys."""
    if not isinstance(fill, str) or not fill:
        return ["fill must be a string"]
    if fill in FILLS:
        return []
    bad = [k for k in (x.strip() for x in fill.split(",")) if k not in colors]
    if bad:
        return [f"unknown colour(s) {', '.join(repr(b) for b in bad)}; "
                f"use level, gradient, or keys from [colors]"]
    return []


# --- colouring -----------------------------------------------------------------
def _cell_colors(fill: str, pct: float, width: int) -> list:
    """The [colors] key for each cell of the fill, left to right."""
    if fill == "level":
        return [pct_color(pct)] * width
    if fill == "gradient":
        # Each cell takes the colour of the usage it represents, so a full bar
        # walks green → yellow → orange → red and a low one stays green.
        return [pct_color(100.0 * (i + 1) / width) for i in range(width)]
    keys = [k.strip() for k in fill.split(",") if k.strip()]
    keys = [k for k in keys if k in CFG["colors"]] or [pct_color(pct)]
    if len(keys) == 1:
        return keys * width
    # Spread the listed colours evenly along the bar.
    return [keys[min(len(keys) - 1, i * len(keys) // max(1, width))] for i in range(width)]


def _sgr(color: str, bold=False, bg=None) -> str:
    params = CFG["colors"].get(color, "")
    if bold:
        params = f"1;{params}" if params else "1"
    if bg:
        params = f"{params};{bg}" if params else bg
    return f"\033[{params}m" if params else ""


def _paint(cells: list, bold=False) -> str:
    """Join (colour, text) runs, merging neighbours of the same colour."""
    out = []
    cur, buf = None, []
    for color, text in cells:
        if not text:
            continue
        if color != cur and buf:
            out.append(f"{_sgr(cur, bold)}{''.join(buf)}{C['reset']}")
            buf = []
        cur = color
        buf.append(text)
    if buf:
        out.append(f"{_sgr(cur, bold)}{''.join(buf)}{C['reset']}")
    return "".join(out)


# --- the bar ------------------------------------------------------------------
def make_bar(pct, width=None, style=None, fill=None, now=None) -> str:
    """Usage bar with optional sub-cell resolution.

    `style` and `fill` override [bar] for one call (segments pass their own
    options through). `now` drives the pulse effect; without it the bar is
    static.
    """
    bar = resolve(style, fill)
    width = CFG["bar"]["width"] if width is None else width
    if width <= 0:
        return ""
    pct = max(0.0, min(100.0, num(pct, 0)))
    full_ch, empty_ch = bar["full"], bar["empty"]
    track = bar["track"]
    caps = (c(track, bar["cap_left"]), c(track, bar["cap_right"]))
    colors = _cell_colors(bar["fill"], pct, width)
    bold = (bar["pulse"] and now is not None and pct >= CFG["thresholds"]["red"]
            and int(now) % 2 == 1)

    cells = pct / 100.0 * width
    full = int(cells)
    frac = cells - full
    sliver = full == 0 and pct > 0 and bar["min_sliver"]

    ps = bar["partial_style"] if bar["partial"] else "off"
    part, need_bg = "", False
    if ps != "off" and full < width:
        if full_ch == "█":
            # Block styles: choose the family that stays continuous on this track.
            family, need_bg = _partial_plan(ps, empty_ch)
            if family == "eighth":
                eighths = int(frac * 8)
                if eighths == 0 and sliver:
                    eighths = 1
                if eighths:
                    part = _EIGHTHS[eighths - 1]
            else:
                # Drop any shade that collides with the track glyph, so a partial
                # cell is distinguishable by shape alone and not only by colour.
                ramp = [ch for ch in _SHADES if ch != empty_ch] or [full_ch]
                if frac >= 1.0 / (2 * len(ramp)) or sliver:
                    part = ramp[min(len(ramp) - 1, int(frac * len(ramp)))]
        elif bar["ramp"]:
            ramp = bar["ramp"]
            if frac >= 1.0 / (2 * len(ramp)) or sliver:
                part = ramp[min(len(ramp) - 1, int(frac * len(ramp)))]
    if ps == "off" or (not part and not bar["ramp"] and full_ch != "█"):
        # Whole cells only: round, and keep a sliver visible.
        filled = int(round(cells))
        if filled == 0 and sliver:
            filled = 1
        full, part = min(width, filled), ""

    empty = width - full - (1 if part else 0)
    painted = _paint([(colors[i], full_ch) for i in range(full)], bold)
    if part:
        color = colors[full]
        bg = _as_bg(CFG["colors"].get(track, "")) if need_bg else None
        # Paint the cell's unfilled remainder in the track colour so the bar
        # stays continuous across the boundary.
        painted += f"{_sgr(color, bold, bg)}{part}{C['reset']}"
    painted += c(track, empty_ch * max(0, empty))
    return caps[0] + painted + caps[1]
