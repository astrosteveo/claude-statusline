"""Looks: how a line of rendered segments is dressed.

Each segment arrives as an icon, a body (styled text) and a tone (the
colour it stands for). A look decides the rest:

    minimal    coloured icons, bodies, generous spacing
    classic    the same with │ between segments
    dots       the same with · between segments
    chips      soft chips: an icon block in the tone, the body on a surface
               colour, square half-block edges. Any font.
    capsules   the same with rounded ends (Nerd Font)
    pills      each segment one rounded pill in its tone (Nerd Font)
    powerline  segments in their tones, joined by arrows (Nerd Font)
    slant      the same, joined by slants (Nerd Font)

`bare` segments (the heartbeat) are drawn as plain text in every look.
A `glance` segment (game mode's session details at their leanest) is its
icon alone, in its tone: a coloured icon, a small chip, a pill or a block.
"""
from __future__ import annotations

from .color import mix
from .text import Text, join

PL_RIGHT, PL_RIGHT_THIN, PL_LEFT, PL_LEFT_THIN = "", "", "", ""
ROUND_LEFT, ROUND_RIGHT = "", ""
SLANT_LEFT_END, SLANT_RIGHT_START = "", ""
HALF_LEFT, HALF_RIGHT = "▐", "▌"      # ▐ opens a chip, ▌ closes it

LOOKS = {
    "minimal": "Coloured icons and text, generous spacing.",
    "classic": "Coloured text with │ between segments.",
    "dots": "Coloured text with · between segments.",
    "chips": "Soft chips: coloured icon blocks on a surface, square edges. Any font.",
    "capsules": "Soft chips with rounded ends. Needs a Nerd Font.",
    "pills": "Each segment a rounded pill in its own colour. Needs a Nerd Font.",
    "powerline": "Segments in their colours joined by arrows. Needs a Nerd Font.",
    "slant": "Segments in their colours joined by slants. Needs a Nerd Font.",
}


class RSeg:
    """A segment rendered for one detail level."""
    __slots__ = ("name", "icon", "body", "tone", "bare", "glance")

    def __init__(self, name, icon, body, tone, bare=False, glance=False):
        self.name = name
        self.icon = icon
        self.body = body
        self.tone = tone
        self.bare = bare
        self.glance = glance


def _st(fg=None, bg=None, attrs=0):
    return (fg, bg, attrs, None)


# --- text looks ----------------------------------------------------------------
def _plain_seg(s: RSeg, ctx) -> Text:
    if s.glance:
        return Text.of(s.icon, _st(s.tone))
    if s.bare or not s.icon:
        return s.body
    out = Text().add(s.icon, _st(s.tone))
    out.add(" ")
    return out.extend(s.body)


def _separated(segs, ctx, sep: str) -> Text:
    sep_t = Text.of(sep, _st(ctx.color("subtle") if sep.strip() in ("│", "|") else ctx.color("muted")))
    return join([_plain_seg(s, ctx) for s in segs], sep_t)


# --- chip looks ------------------------------------------------------------------
def _soft(segs, ctx, rounded: bool) -> Text:
    surface = ctx.color("surface")
    left_cap, right_cap = (ROUND_LEFT, ROUND_RIGHT) if rounded else (HALF_LEFT, HALF_RIGHT)
    parts = []
    for s in segs:
        if s.bare:
            parts.append(s.body)
            continue
        out = Text()
        tone = s.tone or ctx.color("accent")
        if s.glance:
            parts.append(_glance_chip(s, ctx, tone, left_cap, right_cap))
            continue
        if s.icon:
            ink = ctx.chip_ink(tone)
            out.add(left_cap, _st(tone))
            out.add(s.icon, _st(ink, tone))
            out.add(" ", _st(None, tone))
            out.add(" ", _st(None, surface))
        else:
            out.add(left_cap, _st(surface))
        body = s.body.under(surface).tint(ctx.color("text"))
        out.extend(body)
        out.add(" ", _st(None, surface))
        out.add(right_cap, _st(surface))
        parts.append(out)
    return join(parts, Text.of(" "))


def _glance_chip(s: RSeg, ctx, tone, left_cap, right_cap) -> Text:
    """The icon alone on a chip of its tone."""
    return Text().add(left_cap, _st(tone)).add(s.icon, _st(ctx.chip_ink(tone), tone)).add(right_cap, _st(tone))


def _vivid_block(s: RSeg, ctx, bg) -> Text:
    ink = ctx.chip_ink(bg)
    if s.glance:
        return Text().add(" ", _st(None, bg)).add(s.icon, _st(ink, bg)).add(" ", _st(None, bg))
    out = Text().add(" ", _st(None, bg))
    if s.icon:
        out.add(s.icon, _st(ink, bg))
        out.add(" ", _st(None, bg))
    out.extend(s.body.ink(ink).under(bg))
    out.add(" ", _st(None, bg))
    return out


def _pills(segs, ctx) -> Text:
    parts = []
    for s in segs:
        if s.bare:
            parts.append(s.body)
            continue
        bg = s.tone or ctx.color("accent")
        if s.glance:
            parts.append(_glance_chip(s, ctx, bg, ROUND_LEFT, ROUND_RIGHT))
            continue
        out = Text().add(ROUND_LEFT, _st(bg))
        block = _vivid_block(s, ctx, bg)
        block.spans[0] = ("", block.spans[0][1])             # the cap already pads the left
        out.extend(block)
        out.spans[-1] = ("", out.spans[-1][1])
        out.add(ROUND_RIGHT, _st(bg))
        parts.append(out)
    return join(parts, Text.of(" "))


def _arrows(segs, ctx, side: str, slant: bool) -> Text:
    """Powerline (or slanted) runs; bare segments break the run."""
    out = Text()
    run = []

    def flush():
        if not run:
            return
        bgs = [s.tone or ctx.color("accent") for s in run]
        if side == "right":
            out.add(SLANT_RIGHT_START if slant else PL_LEFT, _st(bgs[0]))
        for i, s in enumerate(run):
            out.extend(_vivid_block(s, ctx, bgs[i]))
            nxt = bgs[i + 1] if i + 1 < len(run) else None
            if side == "left":
                if nxt is None:
                    out.add(SLANT_LEFT_END if slant else PL_RIGHT, _st(bgs[i]))
                elif nxt == bgs[i]:
                    out.add(PL_RIGHT_THIN, _st(mix(ctx.chip_ink(bgs[i]), bgs[i], 0.45), bgs[i]))
                else:
                    out.add(SLANT_LEFT_END if slant else PL_RIGHT, _st(bgs[i], nxt))
            elif nxt is not None:
                if nxt == bgs[i]:
                    out.add(PL_LEFT_THIN, _st(mix(ctx.chip_ink(bgs[i]), bgs[i], 0.45), bgs[i]))
                else:
                    out.add(SLANT_RIGHT_START if slant else PL_LEFT, _st(nxt, bgs[i]))
        run.clear()

    for s in segs:
        if s.bare:
            flush()
            if out:
                out.add(" ")
            out.extend(s.body)
            continue
        if out and not run and out.plain()[-1:] != " ":
            out.add(" ")
        run.append(s)
    flush()
    return out


def group(segs, ctx, side="left") -> Text:
    """One side of a line in the context's look."""
    segs = [s for s in segs if s.body or s.glance]
    if not segs:
        return Text()
    look = ctx.style
    if look == "minimal":
        return _separated(segs, ctx, "  ")
    if look == "classic":
        return _separated(segs, ctx, ctx.comp["layout"].get("separator") or " │ ")
    if look == "dots":
        return _separated(segs, ctx, ctx.comp["layout"].get("separator") or " · ")
    if look == "chips":
        return _soft(segs, ctx, rounded=False)
    if look == "capsules":
        return _soft(segs, ctx, rounded=True)
    if look == "pills":
        return _pills(segs, ctx)
    if look in ("powerline", "slant"):
        return _arrows(segs, ctx, side, slant=look == "slant")
    return _separated(segs, ctx, "  ")


def compose(left: Text, right: Text, avail: int, gap: int) -> Text:
    """The two groups on one line, the right one pushed to the edge."""
    if not right:
        return left
    if not left:
        return Text([(" " * max(0, avail - right.width), (None, None, 0, None))] + right.spans)
    pad = max(gap, avail - left.width - right.width)
    return Text(left.spans + [(" " * pad, (None, None, 0, None))] + right.spans)
