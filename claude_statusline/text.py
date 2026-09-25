"""Styled text: runs of plain text, each with a style, serialised to ANSI last.

Keeping text and style apart until the end is what lets the engine measure
widths exactly (no escape parsing), lay backgrounds under whole segments,
and recolour a segment for a different look without re-rendering it.

A style is a tuple `(fg, bg, attrs, link)`: colours from `color.parse`
(or None for the terminal default), an attribute bitmask, and an OSC-8
hyperlink target (or None).
"""
from __future__ import annotations

from .color import sgr
from .width import char_width, width

BOLD, FAINT, ITALIC, UNDERLINE, STRIKE, BLINK, REVERSE = 1, 2, 4, 8, 16, 32, 64
KEEP = 128      # not an SGR attribute: marks runs a look must not recolour (bars)
_ATTR_CODES = ((BOLD, "1"), (FAINT, "2"), (ITALIC, "3"), (UNDERLINE, "4"),
               (BLINK, "5"), (REVERSE, "7"), (STRIKE, "9"))
ATTR_NAMES = {"bold": BOLD, "b": BOLD, "faint": FAINT, "italic": ITALIC, "i": ITALIC,
              "underline": UNDERLINE, "u": UNDERLINE, "strike": STRIKE, "s": STRIKE,
              "blink": BLINK, "reverse": REVERSE}

PLAIN = (None, None, 0, None)


def style(fg=None, bg=None, attrs=0, link=None):
    return (fg, bg, attrs, link)


class Text:
    """A sequence of (text, style) runs."""
    __slots__ = ("spans",)

    def __init__(self, spans=None):
        self.spans = spans if spans is not None else []

    @classmethod
    def of(cls, text, st=PLAIN):
        return cls([(text, st)] if text else [])

    def add(self, text, st=PLAIN):
        if text:
            self.spans.append((text, st))
        return self

    def extend(self, other):
        if other is not None:
            self.spans.extend(other.spans)
        return self

    def copy(self):
        return Text(list(self.spans))

    def __bool__(self):
        return any(t for t, _ in self.spans)

    def __repr__(self):
        return f"Text({self.plain()!r})"

    @property
    def width(self):
        return sum(width(t) for t, _ in self.spans)

    def plain(self):
        return "".join(t for t, _ in self.spans)

    # -- restyling ---------------------------------------------------------
    def under(self, bg):
        """Lay `bg` under every run that has no background of its own."""
        if bg is None:
            return self
        return Text([(t, (s[0], bg, s[2], s[3]) if s[1] is None else s) for t, s in self.spans])

    def ink(self, fg, keep_attrs=True):
        """Every run in `fg`, whatever colour it had (backgrounds and KEEP runs kept)."""
        return Text([(t, s if s[2] & KEEP else (fg, s[1], s[2] if keep_attrs else 0, s[3]))
                     for t, s in self.spans])

    def tint(self, fg):
        """`fg` for runs that have no colour of their own (KEEP runs excepted)."""
        return Text([(t, (fg, s[1], s[2], s[3]) if s[0] is None and not s[2] & KEEP else s)
                     for t, s in self.spans])

    def link(self, url):
        if not url:
            return self
        return Text([(t, (s[0], s[1], s[2], s[3] or url)) for t, s in self.spans])

    # -- geometry ----------------------------------------------------------
    def clip(self, cells, ellipsis="…"):
        """At most `cells` wide, ending in `ellipsis` (in the last run's style) if cut."""
        if self.width <= cells:
            return self
        if cells <= 0:
            return Text()
        room = cells - width(ellipsis)
        out, used, last = [], 0, PLAIN
        for t, s in self.spans:
            w = width(t)
            if used + w <= room:
                out.append((t, s))
                used += w
                last = s
                continue
            keep = []
            for ch in t:
                cw = char_width(ch)
                if used + cw > room:
                    break
                keep.append(ch)
                used += cw
            if keep:
                out.append(("".join(keep).rstrip(), s))
            last = s
            break
        if room >= 0:
            out.append((ellipsis, (last[0], last[1], last[2], None)))
        return Text(out)

    def ansi(self, mode="truecolor"):
        return to_ansi(self.spans, mode)


_PARAMS: dict = {}


def _params(st, mode):
    key = (st[0], st[1], st[2], mode)
    out = _PARAMS.get(key)
    if out is None:
        parts = [code for bit, code in _ATTR_CODES if st[2] & bit]
        if mode != "none":
            fg = sgr(st[0], mode)
            bg = sgr(st[1], mode, background=True)
            if fg:
                parts.append(fg)
            if bg:
                parts.append(bg)
        out = _PARAMS[key] = ";".join(parts)
    return out


_OSC_CLOSE = "\033]8;;\033\\"


def to_ansi(spans, mode="truecolor") -> str:
    """Serialise runs, emitting an escape only where the style changes."""
    out = []
    cur_params = ""
    cur_link = None
    for text, st in spans:
        if not text:
            continue
        link = st[3]
        if link != cur_link:
            if cur_link:
                out.append(_OSC_CLOSE)
            if link:
                out.append(f"\033]8;;{link}\033\\")
            cur_link = link
        params = _params(st, mode)
        if params != cur_params:
            out.append(f"\033[0;{params}m" if params else "\033[0m")
            cur_params = params
        out.append(text)
    if cur_link:
        out.append(_OSC_CLOSE)
    if cur_params:
        out.append("\033[0m")
    return "".join(out)


def join(parts, sep=None):
    """Concatenate Texts, with `sep` (a Text) between non-empty ones."""
    out = Text()
    first = True
    for p in parts:
        if not p:
            continue
        if not first and sep is not None:
            out.extend(sep)
        out.extend(p)
        first = False
    return out
