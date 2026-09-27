"""The interactive configurator.

    statusline.py configure

A live preview of your bar sits on top and changes as you move through the
choices below it: themes, styles and icons; the lines and what is on them;
each segment's options; the bars; Claude Quest; and the finer settings. The
configurator itself wears the theme you are looking at. Nothing is written
until you save; saving writes your config (keeping a backup of the old one)
and the bar picks it up within a second.
"""
from __future__ import annotations

import copy
import os
import time

from .. import samples
from ..color import detect_mode, mix
from ..config import DEFAULTS, PLACEMENTS, read_toml, write_path
from ..decor import LOOKS
from ..icons import HEARTBEAT_FRAMES, ICONS
from ..layout import compile_config, list_presets, load_preset, preset_summary
from ..text import BOLD, ITALIC, REVERSE, Text
from ..themes import ROLES, THEMES, describe as theme_desc
from ..width import width as cells

TABS = ["Look", "Layout", "Segments", "Bars", "Quest", "More"]
STYLE_CHOICES = ["auto"] + list(LOOKS)
ICON_CHOICES = ["auto", "nerd", "unicode", "emoji", "none"]
ICON_DESC = {"auto": "Nerd Font icons where the terminal bundles them, else Unicode",
             "nerd": "Nerd Font icons (kitty, WezTerm, Ghostty, or a Nerd Font)",
             "unicode": "symbols every font has", "emoji": "colour emoji, two cells each",
             "none": "no icons, text only"}
STYLE_DESC = dict(LOOKS, auto="capsules with a Nerd Font terminal, chips otherwise")
COLOR_ROLES = ["", "accent", "blue", "cyan", "teal", "green", "yellow", "orange", "red", "pink", "purple",
               "gold", "text", "subtext", "muted"]
BAR_STYLES = ["smooth", "shade", "line", "slim", "dots", "pips", "braille", "ascii"]
FILLS = ["level", "gradient", "tone", "cyan,purple", "blue,pink", "green,yellow,red", "accent"]


# --- config access -------------------------------------------------------------
def dig(d, path, default=None):
    for p in path:
        if not isinstance(d, dict) or p not in d:
            return default
        d = d[p]
    return d


def put(d, path, value):
    for p in path[:-1]:
        if not isinstance(d.get(p), dict):
            d[p] = {}
        d = d[p]
    d[path[-1]] = value


def drop(d, path):
    trail = []
    for p in path[:-1]:
        if not isinstance(d.get(p), dict):
            return
        trail.append((d, p))
        d = d[p]
    d.pop(path[-1], None)
    for parent, key in reversed(trail):             # remove tables left empty
        if parent[key] == {}:
            parent.pop(key)


class Field:
    """One editable setting on a form."""

    def __init__(self, label, path, kind, doc="", choices=None, default=None, step=1, lo=None, hi=None,
                 getter=None, setter=None):
        self.label = label
        self.path = path
        self.kind = kind          # bool choice int float str info action
        self.doc = doc
        self.choices = choices or []
        self.default = default
        self.step = step
        self.lo = lo
        self.hi = hi
        self.getter = getter      # for settings that are not a single key
        self.setter = setter


class App:
    def __init__(self, path=None):
        self.path = path or write_path()
        raw, err = read_toml(self.path) if os.path.exists(self.path) else ({}, None)
        self.load_error = err
        self.raw = copy.deepcopy(raw)
        self.saved = copy.deepcopy(raw)
        self.tab = 0
        self.mode = detect_mode()
        if self.mode == "none":
            self.mode = "256"
        self.samples = samples.names()
        self.sample = "live" if "live" in self.samples else "busy"
        self.widths = [0, 120, 100, 80]
        self.width_i = 0
        self.msg = ("", "muted", 0.0)
        self.help = False
        self.picker = None        # {"items": [...], "i": 0, "filter": ""}
        self.confirm = None       # {"text": ..., "keys": {key: fn}}
        self.edit = None          # {"field": Field, "buf": str, "pos": int}
        self.hits = []            # (y, x0, x1, fn) for mouse clicks
        # per-page state
        self.look_col = 0
        self.layout_line = 0
        self.layout_pos = 0
        self.layout_focus = 1     # 0 preset row, 1 lines, 2 game mode's rows
        self.game_i = 0           # 0 the top row's details, 1 the gauges
        self.preset_cursor = None
        self.seg_i = 0
        self.seg_focus = 0        # 0 list, 1 options
        self.form_i = {}          # tab name -> row
        self.data_cache = {}
        self.quit = False
        self.recompile()
        if err:
            self.say(f"{self.path}: {err} — saving will replace it", "red", 8)

    # -- state ---------------------------------------------------------------
    def recompile(self):
        self.comp = compile_config(self.raw, path=self.path)
        self.pal = self.comp["palette"]

    def changed(self):
        self.recompile()

    def dirty(self):
        return self.raw != self.saved

    def say(self, text, role="green", secs=4.0):
        self.msg = (text, role, time.time() + secs)

    def get(self, path, default=None):
        val = dig(self.raw, path)
        if val is not None:
            return val
        d = dig(DEFAULTS, path)
        return d if d is not None else default

    def set(self, path, value):
        if value is None:
            drop(self.raw, path)
        else:
            put(self.raw, path, value)
        self.changed()

    # -- colours ---------------------------------------------------------------
    def c(self, role):
        c = self.pal.get(role)
        if c is None and role == "text":
            return None
        return c

    def T(self, text, role="text", bold=False, bg=None, italic=False, reverse=False):
        attrs = (BOLD if bold else 0) | (ITALIC if italic else 0) | (REVERSE if reverse else 0)
        return Text.of(text, (self.c(role) if isinstance(role, str) else role,
                              self.c(bg) if isinstance(bg, str) else bg, attrs, None))

    # -- data for the preview --------------------------------------------------------
    def payload(self):
        key = (self.sample, int(time.time() // 5))
        if key not in self.data_cache:
            try:
                self.data_cache = {key: samples.load(self.sample)}
            except Exception:
                self.sample = "busy"
                self.data_cache = {key: samples.load("busy")}
        return self.data_cache[key]

    def preview(self, inner):
        from ..context import Context
        from ..render import render_lines
        from .. import width as width_mod
        width_mod.WIDE.update(self.comp["layout"].get("wide_glyphs") or ())
        target = self.widths[self.width_i] or inner
        target = min(target, inner)
        margin = self.comp["layout"].get("right_margin", 5)
        data = self.payload()
        ctx = Context(data, self.comp, cols=target + margin, env=dict(os.environ), sync_git=True, live=False)
        try:
            fits = render_lines(data, self.comp, ctx=ctx)
        except Exception as exc:
            return [self.T(f"preview failed: {exc}", "red")], target, ctx
        return [f.text for f in fits if f is not None], target, ctx

    # -- drawing helpers ---------------------------------------------------------
    def pad(self, t: Text, w: int, bg=None) -> Text:
        t = t.clip(w)
        short = w - t.width
        if short > 0:
            t = Text(t.spans + [(" " * short, (None, self.c(bg) if isinstance(bg, str) else bg, 0, None))])
        return t.under(self.c(bg)) if bg else t

    def row(self, *parts) -> Text:
        out = Text()
        for p in parts:
            out.extend(p if isinstance(p, Text) else self.T(str(p)))
        return out

    def hit(self, y, x0, x1, fn):
        self.hits.append((y, x0, x1, fn))

    def draw(self, W, H):
        self.hits = []
        if W < 60 or H < 16:
            note = self.T(f"The configurator needs at least 60×16; this terminal is {W}×{H}.", "yellow")
            return [self.pad(note, W)] + [Text()] * (H - 1)
        rows = []
        # title bar
        title = self.row(self.T(" ✶ ", "accent", bold=True), self.T("claude-statusline", "text", bold=True),
                         self.T("  configure", "muted"))
        status = self.T("● unsaved  ", "yellow") if self.dirty() else self.T("saved  ", "muted")
        right = self.row(status, self.T("? help ", "subtext"))
        rows.append(self.pad(self.row(title, " " * max(1, W - title.width - right.width), right), W))
        # preview box
        inner = W - 4
        lines, target, ctx = self.preview(inner)
        label = f" preview · {self.sample} · {target} columns · {ctx.style} · {ctx.iconset} "
        top = self.row(self.T(" ╭─", "subtle"), self.T(label, "muted"),
                       self.T("─" * max(0, W - 5 - cells(label)) + "╮", "subtle"))
        rows.append(self.pad(top, W))
        for t in (lines or [self.T("(nothing to show)", "muted")]):
            rows.append(self.row(self.T(" │ ", "subtle"), self.pad(t, inner), self.T("│", "subtle")))
        rows.append(self.pad(self.T(" ╰" + "─" * (W - 4) + "╯", "subtle"), W))
        # tabs
        tabs = Text().add(" ")
        x = 1
        for i, name in enumerate(TABS):
            label = f" {name} "
            if i == self.tab:
                tabs.extend(self.T(label, "base", bold=True, bg="accent"))
            else:
                tabs.extend(self.T(label, "subtext"))
            self.hit(len(rows), x, x + cells(label), (lambda i: lambda: self.goto(i))(i))
            x += cells(label)
            tabs.add(" ")
            x += 1
        rows.append(self.pad(tabs, W))
        rows.append(self.pad(self.T(" " + "─" * (W - 2), "subtle"), W))
        body_h = H - len(rows) - 2
        page = getattr(self, "page_" + TABS[self.tab].lower())
        body = page(W, body_h, len(rows))
        body = (body + [Text()] * body_h)[:body_h]
        rows.extend(self.pad(b, W) for b in body)
        # message and key hints
        text, role, until = self.msg
        rows.append(self.pad(self.T(" " + text, role) if text and time.time() < until else Text(), W))
        rows.append(self.pad(self.hints(), W))
        if self.help:
            rows = self.overlay_box(rows, W, H, "keys", self.help_lines())
        elif self.picker:
            rows = self.overlay_box(rows, W, H, self.picker.get("title", "add"), self.picker_lines())
        elif self.confirm:
            rows = self.overlay_box(rows, W, H, "confirm", [self.T(t, "text") for t in self.confirm["text"]])
        return rows

    def hints(self):
        if self.edit:
            pairs = [("enter", "keep"), ("esc", "cancel"), ("←→", "move")]
        elif self.picker:
            pairs = [("↑↓", "choose"), ("enter", "add"), ("type", "filter"), ("esc", "cancel")]
        else:
            pairs = self.page_hints() + [("tab", "next page"), ("p", "sample"), ("w", "width"),
                                         ("s", "save"), ("q", "quit")]
        out = Text().add(" ")
        for k, v in pairs:
            out.extend(self.T(k, "accent", bold=True)).extend(self.T(f" {v}   ", "muted"))
        return out

    def page_hints(self):
        name = TABS[self.tab]
        if name == "Look":
            return [("↑↓", "choose"), ("←→", "column")]
        if name == "Layout":
            return [("←→↑↓", "move"), ("< >", "shift"), ("[ ]", "line"), ("a", "add"), ("x", "remove"),
                    ("n", "new line")]
        if name == "Segments":
            return [("↑↓", "choose"), ("←→", "change"), ("enter", "edit"), ("del", "default")]
        return [("↑↓", "choose"), ("←→", "change"), ("enter", "edit"), ("del", "default")]

    def overlay_box(self, rows, W, H, title, lines):
        bw = min(W - 6, max(40, max((l.width for l in lines), default=0) + 6))
        bh = min(H - 4, len(lines) + 2)
        x0 = (W - bw) // 2
        y0 = max(1, (H - bh) // 2)
        surface = "surface"
        box = [self.row(self.T("╭─ ", "accent", bg=surface), self.T(title + " ", "text", bold=True, bg=surface),
                        self.T("─" * max(0, bw - 5 - cells(title)) + "╮", "accent", bg=surface))]
        for ln in lines[:bh - 2]:
            box.append(self.row(self.T("│ ", "accent", bg=surface), self.pad(ln, bw - 4, surface),
                                self.T(" │", "accent", bg=surface)))
        box.append(self.T("╰" + "─" * (bw - 2) + "╯", "accent", bg=surface))
        out = list(rows)
        for i, b in enumerate(box):
            y = y0 + i
            if y >= len(out):
                break
            base = out[y].clip(x0, ellipsis="") if out[y].width > x0 else out[y]
            rest = self._slice(out[y], x0 + bw)
            out[y] = self.row(self.pad(base, x0), b, rest)
        return out

    def _slice(self, t: Text, start: int) -> Text:
        """The part of `t` from cell `start` on."""
        out, pos = Text(), 0
        for text, st in t.spans:
            for ch in text:
                w = cells(ch)
                if pos >= start:
                    out.add(ch, st)
                pos += w
        return out

    def help_lines(self):
        pairs = [
            ("tab / shift-tab", "next / previous page (or click a tab)"),
            ("1 … 6", "jump to a page"),
            ("↑ ↓ ← →", "move and change values"),
            ("enter", "edit the value under the cursor"),
            ("delete", "put a setting back to its default"),
            ("p", "cycle the preview's sample: live data, busy, quiet, hot"),
            ("w", "cycle the preview's width"),
            ("s / ctrl-s", "save (the bar updates within a second)"),
            ("q / esc", "quit (asks first if there are unsaved changes)"),
            ("", ""),
            ("Layout page", "< > shift a segment · [ ] move it to another line"),
            ("", "a add · x remove · n new line · D delete line · enter on the preset row"),
        ]
        return [self.row(self.T(f"{k:<17}", "accent", bold=True), self.T(v, "text")) for k, v in pairs]

    # -- lists ----------------------------------------------------------------------
    def list_row(self, selected, focused, text: Text, width):
        if selected:
            bar = self.T("▌", "accent" if focused else "muted")
            return self.row(bar, self.pad(text, width - 1, "surface" if focused else None))
        return self.row(" ", self.pad(text, width - 1))

    def swatch(self, theme):
        from ..themes import palette
        pal = palette(theme)
        out = Text()
        for role in ("accent", "blue", "cyan", "green", "yellow", "orange", "red", "pink"):
            out.add("●", (pal.get(role), None, 0, None))
        return out

    # -- page: look -------------------------------------------------------------------
    def look_columns(self):
        return [("theme", list(THEMES), lambda n: self.row(self.swatch(n), " ", self.T(n, "text")),
                 theme_desc),
                ("style", STYLE_CHOICES, lambda n: self.T(n, "text"), lambda n: STYLE_DESC.get(n, "")),
                ("icons", ICON_CHOICES, lambda n: self.row(self.T(n, "text"), self.T(
                    "  " + " ".join(ICONS.get(n, {}).get(k, "") for k in ("model", "dir", "git", "context"))
                    if n in ICONS else "", "subtext")), lambda n: ICON_DESC.get(n, ""))]

    def page_look(self, W, H, y0):
        cols = self.look_columns()
        widths = [30, 22, W - 30 - 22 - 4]
        out = [Text() for _ in range(H)]
        x = 1
        for ci, (key, items, show, desc) in enumerate(cols):
            w = widths[ci]
            cur = self.get([key])
            focused = ci == self.look_col
            head = self.T(key.upper(), "accent" if focused else "muted", bold=True)
            out[0] = self.row(out[0], self.pad(Text().add(" ").extend(head), w + 1))
            for i, name in enumerate(items[:H - 3]):
                sel = name == cur
                label = self.row(self.T("● " if sel else "  ", "accent"), show(name))
                cell = self.list_row(sel, focused, label, w)
                out[i + 1] = self.row(self.pad(out[i + 1], sum(widths[:ci]) + ci), cell, " ")
                self.hit(y0 + i + 1, x, x + w, (lambda k, n, c: lambda: (setattr(self, "look_col", c),
                                                                         self.set([k], n)))(key, name, ci))
            x += w + 1
        key, items, _, desc = cols[self.look_col]
        cur = self.get([key])
        out[H - 1] = self.row(self.T(" " + key + ": ", "muted"), self.T(desc(cur), "subtext", italic=True))
        return out

    def keys_look(self, k):
        key, items, _, _ = self.look_columns()[self.look_col]
        cur = self.get([key])
        i = items.index(cur) if cur in items else 0
        if k in ("up", "k", "wheel-up"):
            self.set([key], items[(i - 1) % len(items)])
        elif k in ("down", "j", "wheel-down"):
            self.set([key], items[(i + 1) % len(items)])
        elif k in ("left", "h"):
            self.look_col = (self.look_col - 1) % 3
        elif k in ("right", "l"):
            self.look_col = (self.look_col + 1) % 3
        else:
            return False
        return True

    # -- page: layout -----------------------------------------------------------------
    def lines(self):
        """The lines as editable lists (the preset's until you change them)."""
        if isinstance(self.raw.get("line"), list) and self.raw["line"]:
            return self.raw["line"]
        preset = load_preset(self.get(["preset"])) or load_preset("classic") or {}
        return preset.get("line") or []

    def own_lines(self):
        if not (isinstance(self.raw.get("line"), list) and self.raw["line"]):
            self.raw["line"] = copy.deepcopy(self.lines())
            for ln in self.raw["line"]:
                ln.setdefault("left", [])
                ln.setdefault("right", [])
        return self.raw["line"]

    def flat(self, ln):
        return [("left", i, n) for i, n in enumerate(ln.get("left", []))] + \
               [("right", i, n) for i, n in enumerate(ln.get("right", []))]

    def page_layout(self, W, H, y0):
        out = []
        presets = list_presets()
        cur = self.get(["preset"])
        own = isinstance(self.raw.get("line"), list) and bool(self.raw["line"])
        head = self.row(self.T(" PRESET  ", "accent" if self.layout_focus == 0 else "muted", bold=True))
        x = head.width
        for name in presets:
            chosen = name == cur and not own
            cursor = own and name == self.preset_cursor and self.layout_focus == 0
            label = f" {name} "
            if chosen:
                head.extend(self.T(label, "base", bold=True, bg="accent"))
            elif cursor:
                head.extend(self.T(label, "accent", bold=True, bg="surface"))
            else:
                head.extend(self.T(label, "text" if self.layout_focus == 0 else "subtext"))
            self.hit(y0, x, x + cells(label), (lambda n: lambda: self.apply_preset(n))(name))
            x += cells(label)
            head.add(" ")
            x += 1
        if own:
            head.extend(self.T("  (your own lines; enter on a preset replaces them)", "muted", italic=True))
        out.append(head)
        out.append(self.T("   " + preset_summary(cur), "muted", italic=True) if not own else Text())
        out.append(Text())
        lines = self.lines()
        for li, ln in enumerate(lines):
            focused = self.layout_focus == 1 and li == self.layout_line
            row = self.row(self.T(f" line {li + 1} ", "accent" if focused else "muted", bold=focused))
            flat = self.flat(ln)
            if not ln.get("right"):
                flat_marks = flat + [("divider", 0, "")]
            else:
                flat_marks = flat
            j = 0
            for side, idx, name in flat:
                if side == "right" and (j == 0 or flat[j - 1][0] == "left"):
                    row.extend(self.T(" ⇥ ", "subtle"))
                sel = focused and j == self.layout_pos
                label = f" {name} "
                if sel:
                    row.extend(self.T(label, "base", bold=True, bg="accent"))
                else:
                    seg_tone = self.seg_tone(name)
                    row.extend(self.T(label, seg_tone, bg="surface"))
                row.add(" ")
                j += 1
            if not ln.get("right"):
                row.extend(self.T(" ⇥ ", "subtle"))
            if not flat:
                row.extend(self.T("(empty — press a to add a segment)", "muted", italic=True))
            out.append(row)
            out.append(Text())
        if self.comp["quest"].get("enabled") and self.comp["quest"].get("placement") == "line" \
                and any(ln.get("auto") for ln in self.comp["lines"]):
            out.append(self.T(" + the Claude Quest line (Quest page)", "muted", italic=True))
        if self.game_on():
            out.append(self.T(" GAME MODE  the bar is the game; these lines give its top row its details",
                              "gold", bold=True))
            for gi, (label, key, names, explicit) in enumerate(self.game_rows()):
                focused = self.layout_focus == 2 and gi == self.game_i
                row = self.row(self.T(f" {label:<8}", "accent" if focused else "muted", bold=focused))
                for j, name in enumerate(names):
                    label_t = f" {name} "
                    if focused and j == self.layout_pos:
                        row.extend(self.T(label_t, "base", bold=True, bg="accent"))
                    else:
                        row.extend(self.T(label_t, self.seg_tone(name), bg="surface"))
                    row.add(" ")
                if not names:
                    row.extend(self.T("(none — press a to add one)", "muted", italic=True))
                if key == "game_details":
                    row.extend(self.T("  set by you (r: back to auto)" if explicit else
                                      "  auto: the model, then your lines", "muted", italic=True))
                out.append(row)
        return out

    # -- game mode's rows ------------------------------------------------------------
    def game_on(self):
        q = self.comp["quest"]
        return bool(q.get("enabled")) and q.get("placement") == "game"

    def game_rows(self):
        """(label, quest key, names, set explicitly?) for the top row's details and the gauges."""
        own = dig(self.raw, ["quest", "game_details"])
        if isinstance(own, list):
            details = list(own)
        else:
            top = next((ln for ln in self.comp["lines"] if ln.get("details") is not None), None)
            details = [s["name"] for s in top["details"]] if top else []
        hud = self.get(["quest", "game_hud"])
        return [("top row", "game_details", details, isinstance(own, list)),
                ("gauges", "game_hud", list(hud) if isinstance(hud, list) else [], True)]

    def keys_game(self, k):
        label, key, names, _ = self.game_rows()[self.game_i]
        self.layout_pos = max(0, min(self.layout_pos, max(0, len(names) - 1)))
        if k in ("left", "h"):
            self.layout_pos = max(0, self.layout_pos - 1)
        elif k in ("right", "l"):
            self.layout_pos = min(max(0, len(names) - 1), self.layout_pos + 1)
        elif k in ("up", "k"):
            if self.game_i:
                self.game_i, self.layout_pos = self.game_i - 1, 0
            else:
                self.layout_focus = 1 if self.lines() else 0
        elif k in ("down", "j"):
            self.game_i, self.layout_pos = min(1, self.game_i + 1), 0
        elif k in ("<", ",", "shift-left", ">", ".", "shift-right") and names:
            d = -1 if k in ("<", ",", "shift-left") else 1
            i = self.layout_pos
            if 0 <= i + d < len(names):
                names[i], names[i + d] = names[i + d], names[i]
                self.layout_pos += d
                self.set(["quest", key], names)
        elif k in ("x", "delete", "backspace") and names:
            gone = names.pop(self.layout_pos)
            self.set(["quest", key], names)
            self.say(f"removed {gone} from the {label}", "yellow")
        elif k in ("a", "+", "insert"):
            self.open_picker()
            self.picker["target"] = key
        elif k == "r" and key == "game_details":
            self.set(["quest", "game_details"], None)
            self.say("top row back to auto: the model, then your lines", "green")
        else:
            return False
        return True

    def seg_tone(self, name):
        from .. import segments
        table = dig(self.raw, ["segment", name]) or {}
        seg = segments.get(table.get("type", name) if isinstance(table, dict) else name)
        return seg.tone if seg and seg.tone in self.pal else "text"

    def apply_preset(self, name):
        self.raw.pop("line", None)
        self.set(["preset"], name)
        self.layout_line = self.layout_pos = 0
        self.say(f"preset {name}: {preset_summary(name)}", "green")

    def keys_layout(self, k):
        presets = list_presets()
        if self.layout_focus == 2:
            return self.keys_game(k)
        if self.layout_focus == 0:
            own = bool(isinstance(self.raw.get("line"), list) and self.raw["line"])
            cur = (self.preset_cursor or self.get(["preset"])) if own else self.get(["preset"])
            i = presets.index(cur) if cur in presets else 0
            if k in ("left", "h", "right", "l"):
                new = presets[(i + (-1 if k in ("left", "h") else 1)) % len(presets)]
                if own:
                    self.preset_cursor = new
                    self.say(f"enter puts preset {new} in place of your own lines", "yellow")
                else:
                    self.set(["preset"], new)
            elif k == "enter":
                self.apply_preset(cur)
                self.preset_cursor = None
            elif k in ("down", "j"):
                self.layout_focus = 1 if self.lines() or not self.game_on() else 2
            else:
                return False
            return True
        lines = self.lines()
        if not lines:
            if k == "n":
                self.own_lines().append({"left": [], "right": []})
                self.changed()
                return True
            if k in ("up", "k"):
                self.layout_focus = 0
                return True
            return False
        self.layout_line = max(0, min(self.layout_line, len(lines) - 1))
        ln = lines[self.layout_line]
        flat = self.flat(ln)
        self.layout_pos = max(0, min(self.layout_pos, max(0, len(flat) - 1)))
        if k in ("left", "h"):
            self.layout_pos = max(0, self.layout_pos - 1)
        elif k in ("right", "l"):
            self.layout_pos = min(max(0, len(flat) - 1), self.layout_pos + 1)
        elif k in ("up", "k"):
            if self.layout_line == 0:
                self.layout_focus = 0
            else:
                self.layout_line -= 1
        elif k in ("down", "j"):
            if self.layout_line == len(lines) - 1 and self.game_on():
                self.layout_focus, self.game_i, self.layout_pos = 2, 0, 0
            self.layout_line = min(len(lines) - 1, self.layout_line + 1)
        elif k in ("<", ",", "shift-left", ">", ".", "shift-right") and flat:
            self.shift(-1 if k in ("<", ",", "shift-left") else 1)
        elif k in ("[", "shift-up", "]", "shift-down") and flat:
            self.move_line(-1 if k in ("[", "shift-up") else 1)
        elif k in ("x", "delete", "backspace") and flat:
            lines = self.own_lines()
            side, idx, name = self.flat(lines[self.layout_line])[self.layout_pos]
            lines[self.layout_line][side].pop(idx)
            self.changed()
            self.say(f"removed {name}", "yellow")
        elif k in ("a", "+", "insert"):
            self.open_picker()
        elif k == "n":
            self.own_lines().insert(self.layout_line + 1, {"left": [], "right": []})
            self.layout_line += 1
            self.layout_pos = 0
            self.changed()
        elif k == "D":
            lines = self.own_lines()
            gone = lines.pop(self.layout_line)
            if not lines:
                lines.append({"left": [], "right": []})
            self.layout_line = max(0, self.layout_line - 1)
            self.changed()
            self.say(f"deleted line with {len(gone.get('left', [])) + len(gone.get('right', []))} segment(s)", "yellow")
        else:
            return False
        return True

    def shift(self, d):
        lines = self.own_lines()
        ln = lines[self.layout_line]
        flat = self.flat(ln)
        side, idx, name = flat[self.layout_pos]
        group = ln[side]
        if 0 <= idx + d < len(group):
            group[idx], group[idx + d] = group[idx + d], group[idx]
            self.layout_pos += d
        elif d > 0 and side == "left":
            group.pop(idx)
            ln["right"].insert(0, name)
        elif d < 0 and side == "right":
            group.pop(idx)
            ln["left"].append(name)
        self.changed()

    def move_line(self, d):
        lines = self.own_lines()
        target = self.layout_line + d
        if target < 0:
            return
        if target >= len(lines):
            lines.append({"left": [], "right": []})
        side, idx, name = self.flat(lines[self.layout_line])[self.layout_pos]
        lines[self.layout_line][side].pop(idx)
        dest = lines[target].setdefault(side, [])
        dest.append(name)
        self.layout_line = target
        flat = self.flat(lines[target])
        self.layout_pos = next(j for j, (sd, ix, nm) in enumerate(flat) if sd == side and ix == len(dest) - 1)
        self.changed()

    def open_picker(self):
        from .. import segments
        reg = segments.load_all()
        placed = {n for ln in self.lines() for side in ("left", "right") for n in ln.get(side, [])}
        items = []
        for seg in sorted(reg.values(), key=lambda s: (s.quest, -s.priority)):
            if seg.name in ("pet", "avatar"):
                continue
            items.append({"name": seg.name, "doc": seg.doc, "placed": seg.name in placed, "quest": seg.quest})
        items.append({"name": "+ text label", "doc": "your own words, as a new text segment", "placed": False,
                      "quest": False, "label": True})
        self.picker = {"items": items, "i": 0, "filter": "", "title": "add a segment"}

    def picker_items(self):
        f = self.picker["filter"].lower()
        return [it for it in self.picker["items"] if f in it["name"].lower() or f in it["doc"].lower()]

    def picker_lines(self):
        items = self.picker_items()
        i = min(self.picker["i"], max(0, len(items) - 1))
        top = max(0, i - 12)
        out = [self.row(self.T("filter: ", "muted"), self.T(self.picker["filter"] or "type to narrow", "text"
                                                            if self.picker["filter"] else "muted"))]
        for j, it in enumerate(items[top:top + 14], top):
            name = self.T(f"{it['name']:<15}", "accent" if j == i else "text", bold=j == i)
            tag = self.T(" placed " if it["placed"] else (" quest  " if it["quest"] else "        "), "muted")
            doc = self.T(it["doc"][:70], "subtext")
            out.append(self.row(self.T("▶ " if j == i else "  ", "accent"), name, tag, doc))
        return out

    def keys_picker(self, k):
        items = self.picker_items()
        if k == "esc":
            self.picker = None
        elif k in ("up", "wheel-up"):
            self.picker["i"] = max(0, self.picker["i"] - 1)
        elif k in ("down", "wheel-down"):
            self.picker["i"] = min(max(0, len(items) - 1), self.picker["i"] + 1)
        elif k == "backspace":
            self.picker["filter"] = self.picker["filter"][:-1]
            self.picker["i"] = 0
        elif k == "enter" and items:
            it = items[min(self.picker["i"], len(items) - 1)]
            target = self.picker.get("target")
            self.picker = None
            name = it["name"]
            if it.get("label"):
                n = 1
                while dig(self.raw, ["segment", f"label{n}"]) is not None:
                    n += 1
                name = f"label{n}"
                put(self.raw, ["segment", name], {"type": "text", "text": "hello"})
            if target:
                names = next(r[2] for r in self.game_rows() if r[1] == target)
                names.insert(min(self.layout_pos + 1, len(names)), name)
                self.set(["quest", target], names)
                self.say(f"added {name} to game mode's {'top row' if target == 'game_details' else 'gauges'}")
                return True
            lines = self.own_lines()
            if not lines:
                lines.append({"left": [], "right": []})
            ln = lines[self.layout_line]
            flat = self.flat(ln)
            if flat:
                side, idx, _ = flat[min(self.layout_pos, len(flat) - 1)]
                ln[side].insert(idx + 1, name)
                self.layout_pos += 1
            else:
                ln.setdefault("left", []).append(name)
                self.layout_pos = 0
            self.changed()
            if it.get("quest") and not self.comp["quest"].get("enabled"):
                self.say(f"added {name} — it shows once Claude Quest is on (Quest page)", "yellow", 6)
            elif it.get("label"):
                self.say(f"added {name}: set its text on the Segments page", "green", 6)
            else:
                self.say(f"added {name}", "green")
        elif len(k.name) == 1 and k.name.isprintable():
            self.picker["filter"] += k.name
            self.picker["i"] = 0
        return True

    # -- forms --------------------------------------------------------------------------
    def value_of(self, f: Field):
        if f.getter:
            return f.getter()
        return self.get(f.path, f.default)

    def store(self, f: Field, value):
        if f.setter:
            f.setter(value)
            self.changed()
        else:
            self.set(f.path, value)

    def show_value(self, f: Field, focused):
        v = self.value_of(f)
        explicit = f.getter is not None or dig(self.raw, f.path) is not None
        if f.kind == "bool":
            return self.row(self.T("◉ on " if v else "○ off", "green" if v else "muted", bold=bool(v)))
        if f.kind == "choice":
            label = "default" if v in (None, "") else str(v)
            return self.row(self.T("‹ " if focused else "  ", "muted"),
                            self.T(label, "text" if explicit else "subtext", bold=explicit),
                            self.T(" ›" if focused else "", "muted"))
        if f.kind in ("int", "float"):
            return self.row(self.T("‹ " if focused else "  ", "muted"),
                            self.T(str(v), "text" if explicit else "subtext", bold=explicit),
                            self.T(" ›" if focused else "", "muted"))
        if f.kind == "str":
            if v in (None, ""):
                return self.T("(default)" if f.default in (None, "") else f"{f.default}", "muted", italic=True)
            return self.T(str(v), "text" if explicit else "subtext")
        if f.kind == "info":
            return v if isinstance(v, Text) else self.T(str(v or ""), "subtext")
        if f.kind == "action":
            return self.T("⏎ " + (f.doc or ""), "accent")
        return self.T(str(v))

    def draw_form(self, fields, key, W, H, y0, x0=0, label_w=18):
        i = self.form_i.get(key, 0)
        i = max(0, min(i, len(fields) - 1)) if fields else 0
        self.form_i[key] = i
        out = []
        top = max(0, i - (H - 3))
        for j, f in enumerate(fields[top:top + H - 2], top):
            sel = j == i and (key != "seg" or self.seg_focus == 1)
            if self.edit and self.edit["field"] is f:
                buf, pos = self.edit["buf"], self.edit["pos"]
                val = self.row(self.T(buf[:pos], "text"), self.T(buf[pos:pos + 1] or " ", "text", reverse=True),
                               self.T(buf[pos + 1:], "text"))
            else:
                val = self.show_value(f, sel)
            label = self.T(f"{f.label:<{label_w}}", "accent" if sel else "subtext", bold=sel)
            body = self.row(label, self.pad(val, 30), self.T("  " + (f.doc if f.kind != "action" else ""), "muted"))
            out.append(self.list_row(sel, True, body, W - x0 - 1))
            self.hit(y0 + len(out) - 1, x0, W, (lambda j: lambda: self.form_i.__setitem__(key, j))(j))
        return out

    def keys_form(self, fields, key, k):
        if not fields:
            return False
        i = self.form_i.get(key, 0)
        f = fields[min(i, len(fields) - 1)]
        if k in ("up", "k", "wheel-up"):
            self.form_i[key] = (i - 1) % len(fields)
        elif k in ("down", "j", "wheel-down"):
            self.form_i[key] = (i + 1) % len(fields)
        elif k in ("left", "right", "h", "l"):
            self.nudge(f, -1 if k in ("left", "h") else 1)
        elif k in ("enter", " "):
            if f.kind == "bool":
                self.store(f, not self.value_of(f))
            elif f.kind == "choice":
                self.nudge(f, 1)
            elif f.kind in ("int", "float", "str"):
                cur = self.value_of(f)
                buf = "" if cur is None else str(cur)
                self.edit = {"field": f, "buf": buf, "pos": len(buf)}
            elif f.kind == "action" and callable(f.default):
                f.default()
        elif k in ("delete", "backspace"):
            if f.kind not in ("info", "action") and not f.setter:
                self.set(f.path, None)
                self.say(f"{f.label} back to its default", "muted")
        else:
            return False
        return True

    def nudge(self, f: Field, d):
        v = self.value_of(f)
        if f.kind == "bool":
            self.store(f, not v)
        elif f.kind == "choice" and f.choices:
            i = f.choices.index(v) if v in f.choices else (f.choices.index("") if "" in f.choices else -1)
            nv = f.choices[(i + d) % len(f.choices)]
            if f.setter:
                self.store(f, nv)
            else:
                self.set(f.path, None if nv == "" else nv)
        elif f.kind == "int":
            nv = int(v or 0) + d * f.step
            if f.lo is not None:
                nv = max(f.lo, nv)
            if f.hi is not None:
                nv = min(f.hi, nv)
            self.set(f.path, nv)
        elif f.kind == "float":
            nv = round(float(v or 0) + d * f.step, 3)
            if f.lo is not None:
                nv = max(f.lo, nv)
            self.set(f.path, nv)

    def keys_edit(self, k):
        e = self.edit
        buf, pos = e["buf"], e["pos"]
        if k == "esc":
            self.edit = None
        elif k == "enter":
            f = e["field"]
            self.edit = None
            if f.kind == "int":
                try:
                    self.set(f.path, int(buf))
                except ValueError:
                    self.say(f"{buf!r} is not a whole number", "red")
            elif f.kind == "float":
                try:
                    self.set(f.path, float(buf))
                except ValueError:
                    self.say(f"{buf!r} is not a number", "red")
            else:
                if f.path[-1] == "format" and buf:
                    from ..template import TemplateError, compile_template
                    try:
                        compile_template(buf)
                    except TemplateError as exc:
                        self.say(f"not saved: {exc}", "red", 6)
                        self.edit = {"field": f, "buf": buf, "pos": pos}
                        return True
                self.set(f.path, buf if (buf or f.path[-1] == "icon") else None)
        elif k == "backspace":
            if pos:
                e["buf"], e["pos"] = buf[:pos - 1] + buf[pos:], pos - 1
        elif k == "delete":
            e["buf"] = buf[:pos] + buf[pos + 1:]
        elif k == "left":
            e["pos"] = max(0, pos - 1)
        elif k == "right":
            e["pos"] = min(len(buf), pos + 1)
        elif k in ("home", "ctrl-a"):
            e["pos"] = 0
        elif k in ("end", "ctrl-e"):
            e["pos"] = len(buf)
        elif k == "ctrl-u":
            e["buf"], e["pos"] = "", 0
        elif k.char and k.char.isprintable():
            e["buf"], e["pos"] = buf[:pos] + k.char + buf[pos:], pos + 1
        return True

    # -- page: segments ---------------------------------------------------------------------
    def placed_names(self):
        seen = []
        for ln in self.comp["lines"]:
            for s in ln["left"] + ln["right"] + (ln.get("details") or []):
                if s["name"] not in seen:
                    seen.append(s["name"])
        return seen

    def segment_fields(self, name):
        from .. import segments
        table = dig(self.raw, ["segment", name]) or {}
        type_ = table.get("type", name) if isinstance(table, dict) else name
        seg = segments.get(type_)
        if seg is None:
            return []
        p = ["segment", name]
        fields = [Field("format", p + ["format"], "str", "the body template", default=seg.format),
                  Field("icon", p + ["icon"], "str", "empty hides it; default from the icon set"),
                  Field("color", p + ["color"], "choice", "the icon's and chip's colour",
                        choices=COLOR_ROLES),
                  Field("priority", p + ["priority"], "int", "higher survives narrow terminals",
                        default=seg.priority, step=5)]
        for key, o in seg.options.items():
            kind = {bool: "bool", int: "int", float: "float"}.get(o.type, "str")
            choices = list(o.choices) if o.choices else None
            if key == "style" and "fill" in seg.options:
                kind, choices = "choice", [""] + BAR_STYLES
            elif key == "fill":
                kind, choices = "choice", [""] + FILLS
            elif key == "frames":
                kind, choices = "choice", list(HEARTBEAT_FRAMES)
            elif key == "color" and seg.name == "heartbeat":
                kind, choices = "choice", COLOR_ROLES[1:]
            if choices:
                kind = "choice"
            step = 0.05 if kind == "float" and isinstance(o.default, float) and o.default < 2 else (
                5.0 if kind == "float" else 1)
            fields.append(Field(key, p + [key], kind, o.doc, choices=choices, default=o.default, step=step))
        return fields

    def page_segments(self, W, H, y0):
        names = self.placed_names()
        if not names:
            return [self.T(" nothing is placed yet — add segments on the Layout page", "muted")]
        self.seg_i = max(0, min(self.seg_i, len(names) - 1))
        lw = 20
        left = []
        for i, n in enumerate(names[:H]):
            sel = i == self.seg_i
            left.append(self.list_row(sel, self.seg_focus == 0, self.T(n, self.seg_tone(n), bold=sel), lw))
            self.hit(y0 + i, 0, lw, (lambda i: lambda: (setattr(self, "seg_i", i), setattr(self, "seg_focus", 0)))(i))
        name = names[self.seg_i]
        from .. import segments
        table = dig(self.raw, ["segment", name]) or {}
        seg = segments.get(table.get("type", name) if isinstance(table, dict) else name)
        head = self.row(self.T(" " + name, "accent", bold=True),
                        self.T(f"  {seg.doc}" if seg else "", "muted", italic=True))
        right = [head] + self.draw_form(self.segment_fields(name), "seg", W - lw - 2, H - 1, y0 + 1, lw + 1,
                                        label_w=14)
        out = []
        for i in range(H):
            l = left[i] if i < len(left) else Text()
            r = right[i] if i < len(right) else Text()
            out.append(self.row(self.pad(l, lw), self.T("│", "subtle"), r))
        return out

    def keys_segments(self, k):
        names = self.placed_names()
        if not names:
            return False
        if self.seg_focus == 0:
            if k in ("up", "k", "wheel-up"):
                self.seg_i = (self.seg_i - 1) % len(names)
            elif k in ("down", "j", "wheel-down"):
                self.seg_i = (self.seg_i + 1) % len(names)
            elif k in ("right", "l", "enter"):
                self.seg_focus = 1
            else:
                return False
            return True
        fields = self.segment_fields(names[self.seg_i])
        if k in ("left", "h") and self.form_i.get("seg", 0) < len(fields) and \
                fields[self.form_i.get("seg", 0)].kind not in ("bool", "choice", "int", "float"):
            self.seg_focus = 0
            return True
        if k == "esc":
            self.seg_focus = 0
            return True
        return self.keys_form(fields, "seg", k)

    # -- page: bars ---------------------------------------------------------------------------
    def bar_fields(self):
        return [Field("style", ["bar", "style"], "choice", "the glyphs", choices=BAR_STYLES),
                Field("width", ["bar", "width"], "int", "cells; 13 shows every percentage", lo=3, hi=40),
                Field("fill", ["bar", "fill"], "choice", "how the filled part is coloured", choices=FILLS),
                Field("track", ["bar", "track"], "choice", "the empty part's colour",
                      choices=["subtle", "muted", "surface", "overlay"]),
                Field("pulse", ["bar", "pulse"], "bool", "past the red threshold, flash on odd seconds"),
                Field("min_sliver", ["bar", "min_sliver"], "bool", "any usage above 0 shows a sliver")]

    def page_bars(self, W, H, y0):
        out = self.draw_form(self.bar_fields(), "bars", W, 8, y0)
        out.append(Text())
        from ..context import Context
        ctx = Context({}, self.comp, cols=W, env=dict(os.environ), live=False)
        row = Text().add("   ")
        for pct in (4, 28, 50, 62, 81, 97):
            row.extend(ctx.bar(pct, self.comp["bar"]["width"], tone=ctx.level_role(pct)))
            row.extend(self.T(f" {pct}%   ", "muted"))
        out.append(row)
        out.append(Text())
        out.append(self.T("   Bar segments (context, limits, the quest hero) can override style, fill and width "
                          "on the Segments page.", "muted", italic=True))
        return out

    def keys_bars(self, k):
        return self.keys_form(self.bar_fields(), "bars", k)

    # -- page: quest ----------------------------------------------------------------------------
    def quest_fields(self):
        return [Field("enabled", ["quest", "enabled"], "bool",
                      "saving registers the hooks (or removes them)"),
                Field("placement", ["quest", "placement"], "choice", "line: its own line · inline: "
                      "the hero on line 1 · manual: where you put quest segments · game: the whole bar "
                      "becomes the game", choices=list(PLACEMENTS)),
                Field("game_rows", ["quest", "game_rows"], "int", "game mode: rows of scene", lo=1, hi=8),
                Field("game_details", [], "choice", "game mode's top row: auto (the model, then your lines), "
                      "none, or your own list (Layout page)", choices=["auto", "none", "custom"],
                      getter=self.details_mode, setter=self.set_details_mode),
                Field("game_hud_width", ["quest", "game_hud_width"], "choice",
                      "game mode: columns for the gauges beside the scene", choices=["auto", 0, 12, 16, 20, 24, 28]),
                Field("avatar", ["quest", "avatar"], "choice", "the animated pet picture, in kitty",
                      choices=["auto", "on", "off"]),
                Field("avatar_cols", ["quest", "avatar_cols"], "int", "the picture's width in cells", lo=4, hi=20),
                Field("event_seconds", ["quest", "event_seconds"], "float",
                      "how long news (loot, level-ups) stays", step=5.0, lo=0.0)]

    def details_mode(self):
        own = dig(self.raw, ["quest", "game_details"])
        return "auto" if not isinstance(own, list) else ("none" if not own else "custom")

    def set_details_mode(self, mode):
        if mode == "auto":
            drop(self.raw, ["quest", "game_details"])
        elif mode == "none":
            put(self.raw, ["quest", "game_details"], [])
        else:
            put(self.raw, ["quest", "game_details"], self.game_rows()[0][2] or ["model"])
            self.say("your own top row: change it on the Layout page", "green")

    def page_quest(self, W, H, y0):
        out = [self.row(self.T(" ⚔ Claude Quest", "gold", bold=True),
                        self.T("  an RPG that plays itself while you work: XP for every tool, loot as "
                               "replies land, bosses from failing tests", "muted", italic=True)), Text()]
        out += self.draw_form(self.quest_fields(), "quest", W, 10, y0 + 2)
        out.append(Text())
        from ..quest import state_path
        if os.path.exists(state_path()):
            try:
                from ..fastjson import loads
                with open(state_path(), "rb") as fh:
                    v = (loads(fh.read()) or {}).get("view") or {}
                out.append(self.row(self.T("   your hero  ", "subtext"),
                                    self.T(f"Lv {v.get('level')} {v.get('title', '')}", "gold", bold=True),
                                    self.T(f"  {v.get('class') or ''} {v.get('class_icon') or ''}   "
                                           f"{v.get('gold', 0):,} gold · {v.get('bag', 0)} items · "
                                           f"{v.get('stage_name') or ''}", "subtext")))
            except Exception:
                out.append(self.T("   your save could not be read", "yellow"))
        else:
            out.append(self.T("   no save yet: your hero starts with your next prompt once this is on", "muted"))
        from ..context import nerd_terminal
        kitty = "KITTY_WINDOW_ID" in os.environ or os.environ.get("TERM") == "xterm-kitty"
        out.append(self.row(self.T("   kitty        ", "subtext"),
                            self.T("detected — the pet can be drawn as a picture" if kitty else
                                   "not detected — the pet is drawn as text", "text" if kitty else "muted")))
        out.append(self.T("   play: /quest in Claude Code, or claude-quest in a terminal (sheet, bag, shop…)",
                          "muted", italic=True))
        return out

    def keys_quest(self, k):
        return self.keys_form(self.quest_fields(), "quest", k)

    # -- page: more -----------------------------------------------------------------------------
    def more_fields(self):
        return [Field("live activity", ["activity", "enabled"], "bool",
                      "tools, subagents and the turn, from background hooks (saving registers them)"),
                Field("activity place", ["activity", "placement"], "choice",
                      "auto: its segments get a line of their own · manual: where you put them",
                      choices=["auto", "manual"]),
                Field("colour depth", ["color"], "choice", "auto follows COLORTERM",
                      choices=["auto", "truecolor", "256", "16", "none"]),
                Field("right margin", ["layout", "right_margin"], "int",
                      "columns the host keeps at the edge (statusline.py ruler)", lo=0, hi=20),
                Field("gap", ["layout", "gap"], "int", "least space between left and right", lo=0, hi=20),
                Field("separator", ["layout", "separator"], "str", "for the classic and dots styles"),
                Field("warn at", ["thresholds", "yellow"], "int", "percent where bars turn yellow", step=5, lo=0,
                      hi=100),
                Field("alert at", ["thresholds", "orange"], "int", "…orange", step=5, lo=0, hi=100),
                Field("critical at", ["thresholds", "red"], "int", "…red", step=5, lo=0, hi=100),
                Field("git", ["git", "enabled"], "bool", "read git state (cached, in the background)"),
                Field("git refresh", ["git", "cache_ttl"], "float", "seconds between git reads", step=0.5,
                      lo=0.5),
                Field("heartbeat", [], "bool", "a tick at the end of line 1 that moves on every refresh",
                      getter=self.heartbeat_on, setter=self.set_heartbeat),
                Field("tick frames", ["segment", "heartbeat", "frames"], "choice", "the heartbeat's frames",
                      choices=list(HEARTBEAT_FRAMES), default="dots"),
                Field("clock", ["segment", "clock", "strftime"], "str", "strftime for the clock segment",
                      default="%H:%M"),
                Field("dir style", ["segment", "dir", "mode"], "choice", "how the directory is shortened",
                      choices=["fish", "compact", "full", "base", "project"], default="fish")]

    def heartbeat_on(self):
        return any("heartbeat" in (ln.get(side) or []) for ln in self.lines() for side in ("left", "right"))

    def set_heartbeat(self, on):
        lines = self.own_lines()
        for ln in lines:
            for side in ("left", "right"):
                if "heartbeat" in (ln.get(side) or []):
                    ln[side] = [n for n in ln[side] if n != "heartbeat"]
        if on:
            if not lines:
                lines.append({"left": [], "right": []})
            lines[0].setdefault("right", []).append("heartbeat")

    def page_more(self, W, H, y0):
        out = self.draw_form(self.more_fields(), "more", W, H - 2, y0)
        out.append(Text())
        out.append(self.T(f"   config: {self.path}", "muted"))
        return out

    def keys_more(self, k):
        return self.keys_form(self.more_fields(), "more", k)

    # -- saving ---------------------------------------------------------------------------------
    def save(self):
        from ..tomlw import dumps
        from .. import __version__
        quest_before = bool(dig(self.saved, ["quest", "enabled"]))
        quest_after = bool(dig(self.raw, ["quest", "enabled"]))
        live_before = bool(dig(self.saved, ["activity", "enabled"]))
        live_after = bool(dig(self.raw, ["activity", "enabled"]))
        text = dumps(self.raw, header=f"# claude-statusline {__version__} — written by `statusline.py configure`.\n"
                                      f"# Every key is optional; see `statusline.py help`.\n")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if os.path.exists(self.path) and not getattr(self, "_backed_up", False):
            import shutil
            stamp = time.strftime("%Y%m%d-%H%M%S")
            shutil.copy2(self.path, f"{self.path}.bak-{stamp}")
            self._backed_up = True
        tmp = f"{self.path}.{os.getpid()}.tmp"
        with open(tmp, "w") as fh:
            fh.write(text)
        os.replace(tmp, self.path)
        self.saved = copy.deepcopy(self.raw)
        note = ""
        if quest_after != quest_before:
            from ..quest import setup
            log = []
            try:
                (setup.enable if quest_after else setup.disable)(log=log.append)
                note = " · Claude Quest " + ("on: hooks registered" if quest_after else "off: hooks removed")
            except Exception as exc:
                note = f" · Claude Quest: {exc}"
            self.saved = copy.deepcopy(self.raw)
        if live_after != live_before:
            from .. import activity
            log = []
            try:
                (activity.enable if live_after else activity.disable)(log=log.append)
                note += " · live activity " + ("on: hooks registered" if live_after else "off: hooks removed")
            except Exception as exc:
                note += f" · live activity: {exc}"
            self.saved = copy.deepcopy(self.raw)
        self.say(f"saved {self.path}{note} — your bar updates within a second", "green", 6)

    def ask_quit(self):
        if not self.dirty():
            self.quit = True
            return
        self.confirm = {"text": ["You have unsaved changes.", "",
                                 "s  save and quit", "q  quit without saving", "esc  keep editing"],
                        "keys": {"s": lambda: (self.save(), setattr(self, "quit", True)),
                                 "y": lambda: (self.save(), setattr(self, "quit", True)),
                                 "q": lambda: setattr(self, "quit", True),
                                 "n": lambda: setattr(self, "quit", True)}}

    # -- input -------------------------------------------------------------------------------------
    def goto(self, i):
        self.tab = i % len(TABS)
        self.edit = None

    def on_key(self, k):
        if k == "ctrl-c":
            self.ask_quit() if not self.confirm else setattr(self, "quit", True)
            return
        if self.confirm:
            fn = self.confirm["keys"].get(k.name)
            self.confirm = None
            if fn:
                fn()
            return
        if self.help:
            self.help = False
            return
        if k == "click":
            for y, x0, x1, fn in self.hits:
                if y == k.y and x0 <= k.x < x1:
                    fn()
                    return
            return
        if self.edit:
            self.keys_edit(k)
            return
        if self.picker:
            self.keys_picker(k)
            return
        page = TABS[self.tab].lower()
        if getattr(self, "keys_" + page)(k):
            return
        if k in ("tab",):
            self.goto(self.tab + 1)
        elif k == "shift-tab":
            self.goto(self.tab - 1)
        elif k.name in "123456" and len(k.name) == 1:
            self.goto(int(k.name) - 1)
        elif k in ("s", "ctrl-s"):
            self.save()
        elif k in ("q", "esc"):
            self.ask_quit()
        elif k == "?":
            self.help = True
        elif k == "p":
            self.samples = samples.names()
            i = self.samples.index(self.sample) if self.sample in self.samples else 0
            self.sample = self.samples[(i + 1) % len(self.samples)]
            self.data_cache = {}
            self.say(f"preview sample: {self.sample}", "muted")
        elif k == "w":
            self.width_i = (self.width_i + 1) % len(self.widths)
            self.say("preview width: " + (str(self.widths[self.width_i]) if self.widths[self.width_i] else "full"),
                     "muted")

    def to_ansi(self, rows):
        return [r.ansi(self.mode) for r in rows]


def run(argv=None):
    from .term import Terminal
    app = App()
    with Terminal() as term:
        while not app.quit:
            W, H = term.size()
            term.frame(app.to_ansi(app.draw(W, H)))
            for k in term.keys(timeout=1.0):
                app.on_key(k)
                if app.quit:
                    break
    if app.dirty():
        print("Left without saving.")
    else:
        print(f"Config: {app.path}")
    return 0
