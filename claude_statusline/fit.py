"""Fit a line of segments into the columns available.

Every segment can render at five detail levels, richest first:

    0 full     everything it knows
    1 less     tertiary detail gone (the reset clock, stash counts)
    2 lean     secondary detail gone (the pace projection, token counts)
    3 narrow   bars at half width, names shortened
    4 text     no bars at all

The engine steps every segment on the line down together, so bars stay the
same width as each other. Only when the leanest rendering still overflows
does it drop the lowest-priority segment and start again from the top. The
result keeps the most segments, and among those, the richest rendering.
"""
from __future__ import annotations

LEVELS = ("full", "less", "lean", "narrow", "text")
FULL, LESS, LEAN, NARROW, TEXT = range(len(LEVELS))


class Placed:
    """A segment placed on a line: a priority and a render(level) callable."""
    __slots__ = ("name", "prio", "render", "_memo")

    def __init__(self, name, prio, render):
        self.name = name
        self.prio = prio
        self.render = render
        self._memo = {}

    def at(self, level):
        memo = self._memo
        if level not in memo:
            try:
                memo[level] = self.render(level)
            except Exception:
                import os
                if os.environ.get("CLAUDE_STATUSLINE_DEBUG"):
                    raise
                memo[level] = None
        return memo[level]


class Fit:
    __slots__ = ("text", "level", "dropped", "width", "avail", "overflow")

    def __init__(self, text, level, dropped, avail, overflow=0):
        self.text = text
        self.level = level
        self.dropped = dropped
        self.width = text.width
        self.avail = avail
        self.overflow = overflow


def fit_line(left, right, avail, gap, group, compose) -> Fit:
    """`left`/`right` are lists of Placed; `group(segs, side)` dresses one side,
    `compose(l, r, avail, gap)` joins them."""
    keep_l, keep_r = list(left), list(right)
    dropped = []
    while True:
        last = None
        for level in range(len(LEVELS)):
            lt = group([s for s in (p.at(level) for p in keep_l) if s is not None], "left")
            rt = group([s for s in (p.at(level) for p in keep_r) if s is not None], "right")
            need = lt.width + rt.width + (gap if lt and rt else 0)
            if need <= avail:
                return Fit(compose(lt, rt, avail, gap), level, dropped, avail)
            last = (lt, rt, need)
        present = [p for p in keep_l + keep_r if p.at(FULL) is not None]
        if len(present) <= 1:
            lt, rt, need = last
            text = compose(lt, rt, avail, gap).clip(avail)
            return Fit(text, TEXT, dropped, avail, overflow=need - avail)
        victim = min(present, key=lambda p: p.prio)
        dropped.append(victim.name)
        if victim in keep_l:
            keep_l.remove(victim)
        else:
            keep_r.remove(victim)
