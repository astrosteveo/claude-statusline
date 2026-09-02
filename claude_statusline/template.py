"""Format strings for segments.

A template is ordinary text with four constructs:

    {field}             a value the segment supplies
    [ ... ]             an optional group: rendered only when every field
                        inside it is non-empty. An empty group also swallows
                        one adjacent space, so " · {effort}" leaves no gap
                        behind when there is no effort level.
    <name> ... </name>  a colour span; `name` is a key from [colors] or a
                        colour the segment computes (documented per segment).
                        </> closes the innermost span.
    <link> ... </link>  an OSC-8 hyperlink to the segment's `url` field, or
                        plain text when there is none.

Backslash escapes a literal { } [ ] < > or backslash.

Segments may hand over values that already carry escape sequences (a bar, for
instance); those are emitted untouched and never merged into a colour span.
"""
from __future__ import annotations

from .width import display_width

RESET = "\033[0m"


class TemplateError(ValueError):
    pass


# --- AST ---------------------------------------------------------------------
class _Text:
    __slots__ = ("text",)

    def __init__(self, text):
        self.text = text


class _Field:
    __slots__ = ("name",)

    def __init__(self, name):
        self.name = name


class _Group:
    __slots__ = ("children",)

    def __init__(self, children):
        self.children = children


class _Span:
    __slots__ = ("color", "children")

    def __init__(self, color, children):
        self.color = color
        self.children = children


class _Link:
    __slots__ = ("children",)

    def __init__(self, children):
        self.children = children


_SPECIAL = "{}[]<>\\"


def _ident(name: str, what: str, pos: int) -> str:
    name = name.strip()
    if not name or not all(ch.isalnum() or ch == "_" for ch in name):
        raise TemplateError(f"bad {what} name {name!r} at column {pos}")
    return name


class _Parser:
    def __init__(self, src: str):
        self.s = src
        self.i = 0

    def parse(self):
        nodes = self.seq(closers=())
        return nodes

    def seq(self, closers, opener=None):
        """Parse until one of `closers` (']' or a closing tag) is consumed."""
        nodes = []
        buf = []
        s, n = self.s, len(self.s)

        def flush():
            if buf:
                nodes.append(_Text("".join(buf)))
                buf.clear()

        while self.i < n:
            ch = s[self.i]
            if ch == "\\":
                if self.i + 1 < n:
                    buf.append(s[self.i + 1])
                    self.i += 2
                else:
                    buf.append("\\")
                    self.i += 1
            elif ch == "{":
                end = s.find("}", self.i)
                if end == -1:
                    raise TemplateError(f"unclosed '{{' at column {self.i}")
                flush()
                nodes.append(_Field(_ident(s[self.i + 1:end], "field", self.i)))
                self.i = end + 1
            elif ch == "}":
                raise TemplateError(f"unmatched '}}' at column {self.i}")
            elif ch == "[":
                flush()
                start = self.i
                self.i += 1
                children = self.seq(closers=("]",), opener=f"unclosed '[' at column {start}")
                nodes.append(_Group(children))
            elif ch == "]":
                if "]" in closers:
                    flush()
                    self.i += 1
                    self.closed = "]"
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
                        if closer == "]":
                            continue
                        if name == "" or name == closer:
                            flush()
                            self.closed = closer
                            return nodes
                    raise TemplateError(f"unmatched '</{name}>' at column {start}")
                flush()
                name = _ident(tag, "tag", start)
                children = self.seq(closers=(name,), opener=f"unclosed '<{name}>' at column {start}")
                nodes.append(_Link(children) if name == "link" else _Span(name, children))
            elif ch == ">":
                raise TemplateError(f"unmatched '>' at column {self.i}")
            else:
                buf.append(ch)
                self.i += 1
        if closers:
            raise TemplateError(opener or "unexpected end of template")
        flush()
        self.closed = None
        return nodes


# --- rendering ---------------------------------------------------------------
class _Piece:
    """A run of output with its colour stack and link, before serialisation."""
    __slots__ = ("text", "colors", "url", "kind")

    def __init__(self, text, colors, url, kind):
        self.text = text          # str
        self.colors = colors      # tuple of colour names, outermost first
        self.url = url            # str or None
        self.kind = kind          # "lit" | "val" | "raw" | "gap"


class Template:
    def __init__(self, source: str):
        self.source = source
        self.nodes = _Parser(source).parse()
        self.fields: set[str] = set()
        self.colors: set[str] = set()
        self._walk(self.nodes)

    def _walk(self, nodes):
        for node in nodes:
            if isinstance(node, _Field):
                self.fields.add(node.name)
            elif isinstance(node, _Span):
                self.colors.add(node.color)
                self._walk(node.children)
            elif isinstance(node, (_Group, _Link)):
                self._walk(node.children)

    # -- pieces
    def _emit(self, nodes, fields, colors, url, out) -> bool:
        """Append pieces for `nodes`; return False if a field inside was empty."""
        ok = True
        for node in nodes:
            if isinstance(node, _Text):
                out.append(_Piece(node.text, colors, url, "lit"))
            elif isinstance(node, _Field):
                val = fields.get(node.name)
                val = "" if val is None else str(val)
                if val == "":
                    ok = False
                else:
                    kind = "raw" if "\033" in val else "val"
                    out.append(_Piece(val, colors, url, kind))
            elif isinstance(node, _Group):
                inner = []
                if self._emit(node.children, fields, colors, url, inner) and inner:
                    out.extend(inner)
                else:
                    out.append(_Piece("", colors, url, "gap"))
            elif isinstance(node, _Span):
                ok &= self._emit(node.children, fields, colors + (node.color,), url, out)
            elif isinstance(node, _Link):
                target = fields.get("url") or None
                ok &= self._emit(node.children, fields, colors, target or url, out)
        return ok

    @staticmethod
    def _swallow_gaps(pieces):
        """An empty group must not leave a double space behind.

        When the text on both sides of the gap is a space (or the gap sits at
        an end of the segment), one of those spaces goes: the following one
        by preference. When only one side has a space it is a separator the
        neighbours still need, so it stays.
        """
        out = []
        n = len(pieces)
        for idx, piece in enumerate(pieces):
            if piece.kind != "gap":
                out.append(piece)
                continue
            prev = out[-1] if out else None
            nxt = idx + 1
            while nxt < n and pieces[nxt].kind == "gap":
                nxt += 1
            follow = pieces[nxt] if nxt < n else None
            before_ok = prev is None or (prev.kind == "lit" and prev.text.endswith(" "))
            after_ok = follow is None or (follow.kind == "lit" and follow.text.startswith(" "))
            if not (before_ok and after_ok):
                continue
            if follow is not None and follow.kind == "lit" and follow.text.startswith(" "):
                pieces[nxt] = _Piece(follow.text[1:], follow.colors, follow.url, "lit")
            elif prev is not None and prev.kind == "lit" and prev.text.endswith(" "):
                out[-1] = _Piece(prev.text[:-1], prev.colors, prev.url, "lit")
        return out

    @staticmethod
    def _trim(pieces):
        """Strip literal whitespace from the ends of the segment."""
        while pieces and pieces[0].kind == "lit":
            t = pieces[0].text.lstrip(" ")
            if t:
                pieces[0] = _Piece(t, pieces[0].colors, pieces[0].url, "lit")
                break
            pieces.pop(0)
        while pieces and pieces[-1].kind == "lit":
            t = pieces[-1].text.rstrip(" ")
            if t:
                pieces[-1] = _Piece(t, pieces[-1].colors, pieces[-1].url, "lit")
                break
            pieces.pop()
        return pieces

    @staticmethod
    def _serialise(pieces, colors) -> str:
        out = []
        i = 0
        n = len(pieces)
        while i < n:
            p = pieces[i]
            if p.kind == "raw":
                out.append(_wrap_link(p.url, p.text))
                i += 1
                continue
            # Merge a run of same-styled, non-raw pieces.
            j = i
            text = []
            while j < n and pieces[j].kind != "raw" \
                    and pieces[j].colors == p.colors and pieces[j].url == p.url:
                text.append(pieces[j].text)
                j += 1
            run = "".join(text)
            i = j
            if not run:
                continue
            sgr = "".join(f"\033[{colors[name]}m" for name in p.colors if colors.get(name))
            if sgr:
                run = f"{sgr}{run}{RESET}"
            out.append(_wrap_link(p.url, run))
        return "".join(out)

    def render(self, fields: dict, colors: dict) -> str:
        """Render with `fields` (name -> str) and `colors` (name -> SGR params).

        Returns "" when nothing visible came out, so callers can treat an
        all-empty segment as absent.
        """
        pieces = []
        self._emit(self.nodes, fields, (), None, pieces)
        pieces = self._trim(self._swallow_gaps(pieces))
        text = self._serialise(pieces, colors)
        return text if display_width(text) else ""


def _wrap_link(url, text):
    if not url or not text:
        return text
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


_CACHE: dict[str, Template] = {}


def compile_template(source: str) -> Template:
    tpl = _CACHE.get(source)
    if tpl is None:
        tpl = _CACHE[source] = Template(source)
    return tpl
