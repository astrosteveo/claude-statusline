"""Model, directory, session and the small static segments."""
from __future__ import annotations

from datetime import datetime

from ..config import CFG, GLYPHS
from ..util import compact_path, dig, home_path
from . import Opt, Segment, register


@register
class Model(Segment):
    name = "model"
    doc = "Model name, effort level, and the fast-mode flag."
    priority = 100
    format = "<model>{glyph} {name}</model><yellow>{fast}</yellow><dim>[ · {effort}]</dim>"
    options = {"fast": Opt(bool, True, "Show the fast-mode glyph when fast mode is on.")}
    fields = {"glyph": "the model glyph", "name": "display name or id",
              "fast": "fast-mode glyph, or empty", "effort": "effort level, 'think', or empty"}

    def fields_at(self, ctx, opts, level):
        data = ctx.data
        name = (dig(data, "model", "display_name") or dig(data, "model", "id") or "claude")
        fast = GLYPHS["fast"] if data.get("fast_mode") and opts["fast"] else ""
        effort = dig(data, "effort", "level")
        if effort:
            effort = str(effort)
        elif dig(data, "thinking", "enabled"):
            effort = "think"
        else:
            effort = ""
        return {"glyph": GLYPHS["model"], "name": str(name), "fast": fast, "effort": effort}


@register
class Dir(Segment):
    name = "dir"
    doc = "Working directory, compacted to its last few components."
    priority = 90
    format = "<dir>{glyph} {path}</dir>"
    options = {"depth": Opt(int, 3, "Trailing path components to keep.")}
    fields = {"glyph": "the directory glyph", "path": "compacted path",
              "full": "the whole path with ~ for home", "base": "last component only"}

    def fields_at(self, ctx, opts, level):
        full = home_path(ctx.cwd)
        return {"glyph": GLYPHS["dir"], "path": compact_path(ctx.cwd, max(1, opts["depth"])),
                "full": full, "base": full.rstrip("/").rsplit("/", 1)[-1] or full}


@register
class Session(Segment):
    name = "session"
    doc = "The session name, when one has been set."
    priority = 40
    format = "<gray>{name}</gray>"
    fields = {"name": "session name"}

    def fields_at(self, ctx, opts, level):
        name = ctx.data.get("session_name")
        return {"name": str(name)} if name else None


@register
class OutputStyle(Segment):
    name = "output_style"
    doc = "The active output style, unless it is the default."
    priority = 30
    format = "<dim>{style}</dim>"
    fields = {"style": "output style name"}

    def fields_at(self, ctx, opts, level):
        style = dig(ctx.data, "output_style", "name")
        return {"style": str(style)} if style and style != "default" else None


@register
class Text(Segment):
    name = "text"
    doc = "A fixed label. Set `text`, and colour it in `format`."
    priority = 10
    format = "<dim>{text}</dim>"
    options = {"text": Opt(str, "", "The text to show.")}
    fields = {"text": "the configured text"}

    def fields_at(self, ctx, opts, level):
        return {"text": opts["text"]} if opts["text"] else None


@register
class Clock(Segment):
    name = "clock"
    doc = "Wall-clock time."
    priority = 20
    format = "<dim>{time}</dim>"
    options = {"strftime": Opt(str, "%H:%M", "strftime pattern for `time`.")}
    fields = {"time": "formatted local time", "date": "ISO date"}

    def fields_at(self, ctx, opts, level):
        dt = datetime.fromtimestamp(ctx.now)
        try:
            text = dt.strftime(opts["strftime"])
        except Exception:
            text = dt.strftime("%H:%M")
        return {"time": text, "date": dt.strftime("%Y-%m-%d")}


@register
class Version(Segment):
    name = "version"
    doc = "The Claude Code version the host reports."
    priority = 15
    format = "<dim>v{version}</dim>"
    fields = {"version": "host version string"}

    def fields_at(self, ctx, opts, level):
        v = ctx.data.get("version")
        return {"version": str(v)} if v else None


@register
class Vim(Segment):
    name = "vim"
    doc = "Vim mode, when vim keybindings are on. Pair with hideVimModeIndicator in settings."
    priority = 35
    format = "<vimmode>-- {mode} --</vimmode>"
    fields = {"mode": "NORMAL, INSERT, VISUAL or VISUAL LINE"}
    colors = {"vimmode": "green in INSERT, yellow in VISUAL, gray otherwise"}

    def fields_at(self, ctx, opts, level):
        mode = dig(ctx.data, "vim", "mode")
        return {"mode": str(mode)} if mode else None

    def colors_at(self, ctx, opts, fields):
        mode = fields["mode"]
        tone = "green" if mode == "INSERT" else ("yellow" if mode.startswith("VISUAL") else "gray")
        return {"vimmode": CFG["colors"][tone]}


@register
class Agent(Segment):
    name = "agent"
    doc = "The agent name when Claude Code runs with --agent."
    priority = 38
    format = "<purple>@{name}</purple>"
    fields = {"name": "agent name"}

    def fields_at(self, ctx, opts, level):
        name = dig(ctx.data, "agent", "name")
        return {"name": str(name)} if name else None
