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

Game mode's session details go one level further:

    5 glance   a segment whose icon colour carries its state (git, the PR,
               a gauge) is just that icon; the others keep their text

and are fitted one at a time rather than together (`fit_details`): the
lowest-priority detail gives up its detail a level at a time, down to its
icon, then drops, before the next one gives up anything. So the model keeps
its effort longest, and a detail is never trimmed while a less important
one is still on the row.

A segment may be elastic (the quest news): it is fitted at its shortest,
and once the line fits, any columns left over go to it, so a long text shows
in full when there is room and is cut short only when there is not.
"""
from __future__ import annotations

LEVELS = ("full", "less", "lean", "narrow", "text")
FULL, LESS, LEAN, NARROW, TEXT = range(len(LEVELS))
GLANCE = len(LEVELS)
DETAIL_LEVELS = LEVELS + ("glance",)


class Placed:
    """A segment placed on a line: a priority and a render(level, room) callable."""
    __slots__ = ("name", "prio", "render", "elastic", "_memo")

    def __init__(self, name, prio, render, elastic=False):
        self.name = name
        self.prio = prio
        self.render = render
        self.elastic = elastic
        self._memo = {}

    def at(self, level, room=0):
        memo = self._memo
        key = (level, room)
        if key not in memo:
            try:
                memo[key] = self.render(level, room) if room else self.render(level)
            except Exception:
                import os
                if os.environ.get("CLAUDE_STATUSLINE_DEBUG"):
                    raise
                memo[key] = None
        return memo[key]


class Fit:
    __slots__ = ("text", "level", "dropped", "width", "avail", "overflow", "parts", "grown", "details",
                 "levels")

    def __init__(self, text, level, dropped, avail, overflow=0, parts=None):
        self.text = text
        self.level = level
        self.dropped = dropped
        self.width = text.width
        self.avail = avail
        self.overflow = overflow
        self.parts = parts          # (left group, right group) as fitted
        self.grown = {}             # elastic segment -> columns it took from the spare room
        self.details = None         # game mode's top row: how its session details fitted
        self.levels = {}            # fit_details: segment -> the level it was drawn at


def fit_line(left, right, avail, gap, group, compose, top=TEXT, keep_last=True) -> Fit:
    """`left`/`right` are lists of Placed; `group(segs, side)` dresses one side,
    `compose(l, r, avail, gap)` joins them. Levels run from full to `top`.
    With `keep_last` false, a line whose last segment cannot fit comes back
    empty instead of cut short."""
    keep_l, keep_r = list(left), list(right)
    dropped = []
    while True:
        last = None
        for level in range(top + 1):
            segs_l = [p.at(_lv(p, level)) for p in keep_l]
            segs_r = [p.at(_lv(p, level)) for p in keep_r]
            lt = group([s for s in segs_l if s is not None], "left")
            rt = group([s for s in segs_r if s is not None], "right")
            need = lt.width + rt.width + (gap if lt and rt else 0)
            if need <= avail:
                fit = Fit(compose(lt, rt, avail, gap), level, dropped, avail, parts=(lt, rt))
                if need < avail and any(p.elastic for p in keep_l + keep_r):
                    _grow(fit, keep_l, keep_r, segs_l, segs_r, level, need, gap, group, compose)
                return fit
            last = (lt, rt, need)
        present = [p for p in keep_l + keep_r if p.at(FULL) is not None]
        if len(present) <= 1:
            if not keep_last:
                if present:
                    dropped.append(present[0].name)
                return Fit(group([], "left"), top, dropped, avail)
            lt, rt, need = last
            text = compose(lt, rt, avail, gap).clip(avail)
            return Fit(text, top, dropped, avail, overflow=need - avail, parts=(lt, rt))
        victim = min(present, key=lambda p: p.prio)
        dropped.append(victim.name)
        if victim in keep_l:
            keep_l.remove(victim)
        else:
            keep_r.remove(victim)


def _lv(p, level):
    """An elastic segment is fitted at its shortest (and grows afterwards), so a long
    text never costs its neighbours their detail."""
    return max(level, LEAN) if p.elastic else level


def _grow(fit, keep_l, keep_r, segs_l, segs_r, level, need, gap, group, compose):
    """Give the columns the line did not need to its elastic segments, in order."""
    avail = fit.avail
    for side, keep, segs in (("left", keep_l, segs_l), ("right", keep_r, segs_r)):
        for i, p in enumerate(keep):
            spare = avail - need
            if spare <= 0 or not p.elastic or segs[i] is None:
                continue
            bigger = p.at(_lv(p, level), spare)
            if bigger is None:
                continue
            trial = list(segs)
            trial[i] = bigger
            lt = group([s for s in (trial if side == "left" else segs_l) if s is not None], "left")
            rt = group([s for s in (trial if side == "right" else segs_r) if s is not None], "right")
            now = lt.width + rt.width + (gap if lt and rt else 0)
            if need < now <= avail:
                fit.grown[p.name] = now - need
                segs[i] = bigger
                need = now
                fit.text = compose(lt, rt, avail, gap)
                fit.width = fit.text.width
                fit.parts = (lt, rt)


def fit_details(placed, room, group) -> Fit:
    """Session details into `room` columns without clipping (see the module doc).
    Widths add up segment by segment, so the search renders a segment at a
    level at most once; the arrangement is measured whole before it is
    accepted."""
    widths = {}
    # Most important first: once those already fill the room at full detail, every detail below
    # them would be dropped before any of them gives way, so the rest are never even drawn.
    present, used = [], 0
    for p in sorted(placed, key=lambda p: (-p.prio, placed.index(p))):
        if used >= room:
            break
        s = p.at(FULL)
        if s is not None:
            present.append(p)
            used += group([s], "left").width + 1
    present.sort(key=placed.index)
    order = sorted(present, key=lambda p: (p.prio, -placed.index(p)))
    levels = {p.name: FULL for p in present}

    def w(p, level):
        key = (p.name, level)
        if key not in widths:
            s = p.at(level)
            widths[key] = group([s], "left").width if s is not None else 0
        return widths[key]
    join = 0
    if len(present) >= 2:
        a, b = present[0].at(FULL), present[1].at(FULL)
        join = group([a, b], "left").width - w(present[0], FULL) - w(present[1], FULL)
    kept = list(present)
    dropped = []

    def attempt():
        shown = [p for p in kept if p.at(levels[p.name]) is not None]
        if sum(w(p, levels[p.name]) for p in shown) + join * max(0, len(shown) - 1) > room:
            return None
        text = group([p.at(levels[p.name]) for p in shown], "left")
        return text if text.width <= room else None
    text = attempt()
    for p in order:
        if text is not None:
            break
        for level in range(LESS, GLANCE + 1):
            if w(p, level) < w(p, levels[p.name]):
                levels[p.name] = level
                text = attempt()
                if text is not None:
                    break
        if text is None:
            kept.remove(p)
            dropped.append(p.name)
            del levels[p.name]
            text = attempt()
    return _details_fit(text if text is not None else group([], "left"), levels, dropped, room)


def _details_fit(text, levels, dropped, room):
    fit = Fit(text, max(levels.values(), default=FULL), dropped, room)
    fit.levels = levels
    return fit
