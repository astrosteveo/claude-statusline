"""Usage bars with sub-cell resolution and a continuous track."""
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


# Two families of partial-fill glyph, and they do not mix.
#
#   shade   ░▒▓  vary *density* and ink the whole cell, so a partial cell keeps
#                the same texture as the ░ track running through it.
#   eighth  ▏▎▍  vary *width*, painting a sliver at the left of the cell and
#                leaving the rest as bare background — precise, but it punches
#                a visible hole in a shaded track. Only sensible when the track
#                is blank (empty = " ").
_EIGHTHS = "▏▎▍▌▋▊▉"          # 1/8 .. 7/8, left-aligned
_SHADES = "░▒▓"               # ~25%, ~50%, ~75% density, full cell

_SHADE_TRACK = ("░", "▒", "▓")   # textured track
_SOLID_TRACK = ("█",)            # fully-inked track
_BLANK_TRACK = (" ", "")         # bare terminal background


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
    """Pick a boundary-cell family whose remainder matches the track.

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


def make_bar(pct, width=None) -> str:
    """Usage bar with optional sub-cell resolution."""
    bcfg = CFG["bar"]
    width = bcfg["width"] if width is None else width
    if width <= 0:
        return ""
    pct = max(0.0, min(100.0, num(pct, 0)))
    color = pct_color(pct)
    full_ch, empty_ch = bcfg["full"], bcfg["empty"]
    style = bcfg.get("partial_style", "auto")
    if not bcfg.get("partial", True):
        style = "off"
    style, need_bg = _partial_plan(style, empty_ch)

    cells = pct / 100.0 * width
    full = int(cells)
    frac = cells - full
    sliver = full == 0 and pct > 0 and bcfg.get("min_sliver", True)
    part = ""

    if style == "off":
        filled = int(round(cells))
        if filled == 0 and sliver:
            filled = 1
        return (c(color, full_ch * filled)
                + c("dim", empty_ch * max(0, width - filled)))

    if full < width:
        if style == "eighth":
            eighths = int(frac * 8)
            if eighths == 0 and sliver:
                eighths = 1
            if eighths:
                part = _EIGHTHS[eighths - 1]
        else:                                   # shade
            # Drop any shade that collides with the track glyph, so a partial
            # cell is distinguishable by shape alone and not only by colour.
            ramp = [ch for ch in _SHADES if ch != empty_ch] or [full_ch]
            if frac >= 1.0 / (2 * len(ramp)) or sliver:
                part = ramp[min(len(ramp) - 1, int(frac * len(ramp)))]

    empty = width - full - (1 if part else 0)
    out = c(color, full_ch * full)
    if part:
        bg = _as_bg(CFG["colors"]["dim"]) if need_bg else None
        if bg:
            # Paint the cell's unfilled remainder in the track colour so the
            # bar stays continuous across the boundary.
            out += f"\033[{CFG['colors'][color]};{bg}m{part}{C['reset']}"
        else:
            out += c(color, part)
    return out + c("dim", empty_ch * max(0, empty))
