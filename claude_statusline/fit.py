"""Fit a line of segments into the columns available.

Every segment offers a rendering at each detail level, richest first:

    0 full     everything the segment knows
    1 less     tertiary decoration gone (the reset clock, say)
    2 lean     secondary detail gone (the pace projection)
    3 narrow   bars at half width
    4 text     no bars at all

Segments that have nothing to give up simply repeat themselves. The engine
steps every segment on the line down together, so bars stay the same width
as each other, and only when the leanest rendering still overflows does it
drop the lowest-priority segment and try again from the top. The result is
the line that keeps the most segments, and among those, the richest.
"""
from __future__ import annotations

from .width import display_width

LEVELS = ("full", "less", "lean", "narrow", "text")
FULL, LESS, LEAN, NARROW, TEXT = range(len(LEVELS))


class Placed:
    """A segment placed on a line: a priority and a render(level) callable."""
    __slots__ = ("name", "priority", "render", "_memo")

    def __init__(self, name, priority, render):
        self.name = name
        self.priority = priority
        self.render = render
        self._memo = {}

    def at(self, level: int) -> str:
        if level not in self._memo:
            try:
                text = self.render(level)
            except Exception:
                text = ""
            self._memo[level] = text if isinstance(text, str) else ""
        return self._memo[level]


class Fit:
    __slots__ = ("text", "level", "dropped", "width", "avail")

    def __init__(self, text, level, dropped, width, avail):
        self.text = text
        self.level = level
        self.dropped = dropped      # names, in the order they went
        self.width = width
        self.avail = avail

    @property
    def overflow(self) -> int:
        return max(0, self.width - self.avail)


def compose(left, right, avail, sep, gap):
    """Join the two groups; the right one is pushed to the edge."""
    l = sep.join(p for p in left if p)
    r = sep.join(p for p in right if p)
    if not r:
        return l
    if not l:
        return " " * max(0, avail - display_width(r)) + r
    pad = avail - display_width(l) - display_width(r)
    return l + " " * max(gap, pad) + r


def fit_line(left, right, avail, sep, gap=2) -> Fit:
    """`left` and `right` are lists of Placed. Returns the fitted line."""
    keep_l = list(left)
    keep_r = list(right)
    dropped = []
    while True:
        last = ""
        for level in range(len(LEVELS)):
            line = compose([p.at(level) for p in keep_l],
                           [p.at(level) for p in keep_r], avail, sep, gap)
            width = display_width(line)
            if width <= avail:
                return Fit(line, level, dropped, width, avail)
            last = line
        present = [p for p in keep_l + keep_r if p.at(FULL)]
        if len(present) <= 1:
            return Fit(last, len(LEVELS) - 1, dropped, display_width(last), avail)
        victim = min(present, key=lambda p: p.priority)
        dropped.append(victim.name)
        if victim in keep_l:
            keep_l.remove(victim)
        else:
            keep_r.remove(victim)
