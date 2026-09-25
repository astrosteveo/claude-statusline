"""Segment format strings.

A format is ordinary text with a few constructs:

    {field}           a value the segment supplies; {field:>4} pads it to 4
                      cells, right-aligned (< left, ^ centre), so numbers
                      that change length do not shake the line
    [ ... ]           an optional group: shown only when every field inside
                      it has a value. An empty group also takes one
                      neighbouring space with it, so " · {effort}" leaves no
                      double space behind
    <name> ... </name>
                      a colour or attribute span. `name` is a theme role
                      (accent, muted, green…), an alias (model, dim, gray…),
                      a colour the segment computes (documented per
                      segment), `#rrggbb`, `on_<role>` for a background, or
                      one of bold, italic, underline, strike, faint.
                      </> closes the innermost span
    <link> ... </link>
                      an OSC-8 hyperlink to the segment's `url` field

A backslash escapes { } [ ] < > or itself. Values that are already styled
(a bar, say) keep their own colours.

Templates compile to nested tuples so the compiled form can be cached with
the config and rendered without re-parsing.
"""
from __future__ import annotations

from .color import parse as parse_color
from .text import ATTR_NAMES, PLAIN, Text
from .width import width


class TemplateError(ValueError):
    pass


def _ident(name: str, what: str, pos: int) -> str:
    name = name.strip()
    ok = name and all(ch.isalnum() or ch == "_" for ch in name.lstrip("#"))
    if not ok or (name.startswith("#") and len(name) not in (4, 7)):
        raise TemplateError(f"bad {what} name {name!r} at column {pos}")
    return name


class _Parser:
    def __init__(self, src: str):
        self.s = src
        self.i = 0

    def seq(self, closers, opener=None):
        nodes, buf = [], []
        s, n = self.s, len(self.s)

        def flush():
            if buf:
                nodes.append(("t", "".join(buf)))
                buf.clear()

        while self.i < n:
            ch = s[self.i]
            if ch == "\\":
                buf.append(s[self.i + 1] if self.i + 1 < n else "\\")
                self.i += 2
            elif ch == "{":
                end = s.find("}", self.i)
                if end == -1:
                    raise TemplateError(f"unclosed '{{' at column {self.i}")
                flush()
                body = s[self.i + 1:end]
                name, _, spec = body.partition(":")
                align, cells = "", 0
                spec = spec.strip()
                if spec:
                    if spec[0] in "<>^":
                        align, spec = spec[0], spec[1:]
                    if not spec.isdigit():
                        raise TemplateError(f"bad format spec {body!r} at column {self.i}")
                    cells = int(spec)
                    align = align or "<"
                nodes.append(("f", _ident(name, "field", self.i), align, cells))
                self.i = end + 1
            elif ch == "}":
                raise TemplateError(f"unmatched '}}' at column {self.i}")
            elif ch == "[":
                flush()
                start = self.i
                self.i += 1
                nodes.append(("g", tuple(self.seq(("]",), f"unclosed '[' at column {start}"))))
            elif ch == "]":
                if "]" in closers:
                    flush()
                    self.i += 1
                    return nodes
                raise TemplateError(f"unmatched ']' at column {self.i}")
            elif ch == "<":
                end = s.find(">", self.i)
                if end == -1:
                    raise TemplateError(f"unclosed '<' at column {self.i}")
                tag = s[self.i + 1:end].strip()
                start = self.i
                self.i = end + 1
                if tag.startswith("/"):
                    name = tag[1:].strip()
                    for closer in closers:
                        if closer != "]" and (name == "" or name == closer):
                            flush()
                            return nodes
                    raise TemplateError(f"unmatched '</{name}>' at column {start}")
                flush()
                name = _ident(tag, "tag", start)
                kids = tuple(self.seq((name,), f"unclosed '<{name}>' at column {start}"))
                nodes.append(("l", kids) if name == "link" else ("c", name, kids))
            elif ch == ">":
                raise TemplateError(f"unmatched '>' at column {self.i}")
            else:
                buf.append(ch)
                self.i += 1
        if closers:
            raise TemplateError(opener or "unexpected end of template")
        flush()
        return nodes


def compile_template(source: str) -> tuple:
    """Parse a format string; raises TemplateError."""
    return tuple(_Parser(source).seq(()))


def fields_of(tree) -> set:
    out = set()
    for node in tree:
        kind = node[0]
        if kind == "f":
            out.add(node[1])
        elif kind == "g" or kind == "l":
            out |= fields_of(node[1])
        elif kind == "c":
            out |= fields_of(node[2])
    return out


def tags_of(tree) -> set:
    out = set()
    for node in tree:
        kind = node[0]
        if kind == "c":
            out.add(node[1])
            out |= tags_of(node[2])
        elif kind == "g" or kind == "l":
            out |= tags_of(node[1])
    return out


def known_tag(tag: str, colors) -> bool:
    if tag in ATTR_NAMES or tag in colors:
        return True
    if tag.startswith("#"):
        return parse_color(tag) is not None
    if tag.startswith("on_"):
        return tag[3:] in colors or parse_color("#" + tag[3:]) is not None
    return False


# --- rendering ---------------------------------------------------------------
# A piece is [kind, value, tags, url]: kind "lit" (template text), "val" (a
# plain field value), "raw" (a styled Text value) or "gap" (an empty group).

def _pad(val: str, align: str, cells: int) -> str:
    short = cells - width(val)
    if short <= 0:
        return val
    if align == ">":
        return " " * short + val
    if align == "^":
        return " " * (short // 2) + val + " " * (short - short // 2)
    return val + " " * short


def _emit(nodes, fields, tags, url, out) -> bool:
    ok = True
    for node in nodes:
        kind = node[0]
        if kind == "t":
            out.append(["lit", node[1], tags, url])
        elif kind == "f":
            val = fields.get(node[1])
            if isinstance(val, Text):
                if val:
                    out.append(["raw", val, tags, url])
                else:
                    ok = False
                continue
            val = "" if val is None or val is False else str(val)
            if val == "":
                ok = False
            else:
                if node[3]:
                    val = _pad(val, node[2], node[3])
                out.append(["val", val, tags, url])
        elif kind == "g":
            inner = []
            if _emit(node[1], fields, tags, url, inner) and inner:
                out.extend(inner)
            else:
                out.append(["gap", "", tags, url])
        elif kind == "c":
            ok &= _emit(node[2], fields, tags + (node[1],), url, out)
        elif kind == "l":
            target = fields.get("url") or None
            ok &= _emit(node[1], fields, tags, target or url, out)
    return ok


def _swallow_gaps(pieces):
    """An empty group must not leave a double space behind.

    When the text on both sides of the gap is a space (or the gap sits at an
    end of the segment), one of those spaces goes, the following one by
    preference. When only one side has a space it separates neighbours that
    are both still present, so it stays.
    """
    out = []
    n = len(pieces)
    for idx, piece in enumerate(pieces):
        if piece[0] != "gap":
            out.append(piece)
            continue
        prev = out[-1] if out else None
        nxt = idx + 1
        while nxt < n and pieces[nxt][0] == "gap":
            nxt += 1
        follow = pieces[nxt] if nxt < n else None
        before_ok = prev is None or (prev[0] == "lit" and prev[1].endswith(" "))
        after_ok = follow is None or (follow[0] == "lit" and follow[1].startswith(" "))
        if not (before_ok and after_ok):
            continue
        if follow is not None and follow[0] == "lit" and follow[1].startswith(" "):
            pieces[nxt] = ["lit", follow[1][1:], follow[2], follow[3]]
        elif prev is not None and prev[0] == "lit" and prev[1].endswith(" "):
            out[-1] = ["lit", prev[1][:-1], prev[2], prev[3]]
    return out


def _trim(pieces):
    while pieces and pieces[0][0] == "lit":
        t = pieces[0][1].lstrip(" ")
        if t:
            pieces[0] = ["lit", t, pieces[0][2], pieces[0][3]]
            break
        pieces.pop(0)
    while pieces and pieces[-1][0] == "lit":
        t = pieces[-1][1].rstrip(" ")
        if t:
            pieces[-1] = ["lit", t, pieces[-1][2], pieces[-1][3]]
            break
        pieces.pop()
    return pieces


def _style_for(tags, colors):
    fg = bg = None
    attrs = 0
    for tag in tags:
        bit = ATTR_NAMES.get(tag)
        if bit:
            attrs |= bit
        elif tag in colors:
            c = colors[tag]
            if c is not None:
                fg = c
        elif tag.startswith("#"):
            c = parse_color(tag)
            if c is not None:
                fg = c
        elif tag.startswith("on_"):
            c = colors.get(tag[3:]) or parse_color("#" + tag[3:])
            if c is not None:
                bg = c
    return (fg, bg, attrs, None)


def render(tree, fields: dict, colors: dict) -> Text:
    """Render a compiled template. An all-empty result is an empty Text, so
    callers can treat the segment as absent."""
    pieces = []
    _emit(tree, fields, (), None, pieces)
    pieces = _trim(_swallow_gaps(pieces))
    out = Text()
    spans = out.spans
    for kind, val, tags, url in pieces:
        if kind == "gap" or not val:
            continue
        if kind == "raw":
            base = _style_for(tags, colors) if tags else PLAIN
            for t, s in val.spans:
                fg = s[0] if s[0] is not None else base[0]
                bg = s[1] if s[1] is not None else base[1]
                spans.append((t, (fg, bg, s[2] | base[2], s[3] or url)))
            continue
        st = _style_for(tags, colors) if tags else PLAIN
        if url:
            st = (st[0], st[1], st[2], url)
        if spans and spans[-1][1] == st:
            spans[-1] = (spans[-1][0] + val, st)
        else:
            spans.append((val, st))
    return out if out.width else Text()


_COMPILED: dict = {}


def cached(source: str) -> tuple:
    tree = _COMPILED.get(source)
    if tree is None:
        tree = _COMPILED[source] = compile_template(source)
    return tree
