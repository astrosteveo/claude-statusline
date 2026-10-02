"""Model, directory, session and the small static segments."""
from __future__ import annotations

from ..fit import LEAN, LESS, NARROW
from ..util import dig, home_path, split_path
from . import Opt, Segment, register



def strip_qualifier(name: str) -> str:
    """"Opus 5 (1M context)" -> "Opus 5"; the host folds the context size into the name."""
    text = name.rstrip()
    if text.endswith(")"):
        start = text.rfind("(")
        if start > 0 and "(" not in text[start + 1:-1] and ")" not in text[start + 1:-1]:
            return text[:start].rstrip() or name
    return name


@register
class Model(Segment):
    name = "model"
    doc = "The model, its effort level, and the fast-mode flag."
    priority = 100
    tone = "model"
    format = "<model><bold>{name}</bold></model>[ <yellow>{fast}</yellow>][<muted> · {effort}</muted>]"
    options = {
        "fast": Opt(bool, True, "Show the fast-mode mark when fast mode is on."),
        "full_name": Opt(bool, False, "Keep the qualifier the host adds, e.g. (1M context)."),
    }
    fields_doc = {"name": "the model name (without the qualifier unless full_name)",
                  "full": "the display name as the host sends it", "short": "the name without its qualifier",
                  "id": "the model id", "fast": "the fast-mode mark, or empty",
                  "effort": "effort level, 'think', or empty"}

    def fields(self, ctx, opts, level):
        data = ctx.data
        full = str(dig(data, "model", "display_name") or dig(data, "model", "id") or "Claude")
        short = strip_qualifier(full)
        effort = dig(data, "effort", "level")
        effort = str(effort) if effort else ("think" if dig(data, "thinking", "enabled") else "")
        return {"name": full if opts["full_name"] and level < LEAN else short,
                "full": full, "short": short, "id": str(dig(data, "model", "id") or ""),
                "fast": ctx.mark("fast") if data.get("fast_mode") and opts["fast"] else "",
                "effort": effort if level < NARROW else ""}


@register
class Dir(Segment):
    name = "dir"
    doc = "The working directory: parents abbreviated, the folder you are in picked out."
    priority = 90
    tone = "dir"
    format = "<muted>{parent}</muted><dir><bold>{base}</bold></dir>"
    options = {
        "mode": Opt(str, "fish", "fish (~/P/project), compact (…/a/b/project), full, base, or project "
                                 "(relative to the project root)",
                    choices=("fish", "compact", "full", "base", "project")),
        "depth": Opt(int, 1, "Trailing components kept whole (fish, compact)."),
    }
    fields_doc = {"path": "the whole display path", "parent": "everything before the last component",
                  "base": "the last component", "full": "the full path with ~ for home",
                  "project": "the project's folder name"}

    def fields(self, ctx, opts, level):
        cwd = ctx.cwd
        mode = opts["mode"]
        project_dir = dig(ctx.data, "workspace", "project_dir")
        project = ""
        if isinstance(project_dir, str) and project_dir:
            project = project_dir.rstrip("/").rsplit("/", 1)[-1]
        if mode == "project" and project and (cwd == project_dir or cwd.startswith(project_dir.rstrip("/") + "/")):
            rel = cwd[len(project_dir.rstrip("/")):].strip("/")
            parent, base = (project + "/" + rel.rsplit("/", 1)[0] + "/", rel.rsplit("/", 1)[-1]) \
                if "/" in rel else ((project + "/", rel) if rel else ("", project))
        else:
            if mode == "project":
                mode = "fish"
            if level >= LEAN and mode in ("full", "compact"):
                mode = "fish"
            parent, base = split_path(cwd, max(1, opts["depth"]), mode, ctx.home)
        if level >= NARROW:
            parent = ""
        return {"path": parent + base, "parent": parent, "base": base,
                "full": home_path(cwd, ctx.home), "project": project}


@register
class Session(Segment):
    name = "session"
    doc = "The session name, once one is set (/rename)."
    priority = 40
    tone = "pink"
    format = "<subtext>{name}</subtext>"
    options = {"max": Opt(int, 32, "Longest name shown; longer ones end in …")}
    fields_doc = {"name": "the session name"}

    def fields(self, ctx, opts, level):
        from ..width import clip
        name = ctx.data.get("session_name")
        if not name:
            return None
        cap = opts["max"] if level < LEAN else max(8, opts["max"] // 2)
        return {"name": clip(str(name), max(4, cap))}


@register
class OutputStyle(Segment):
    name = "output_style"
    doc = "The output style, unless it is the default."
    priority = 30
    tone = "purple"
    format = "<muted>{style}</muted>"
    fields_doc = {"style": "the output style's name"}

    def fields(self, ctx, opts, level):
        style = dig(ctx.data, "output_style", "name")
        return {"style": str(style)} if style and str(style).lower() != "default" else None


@register
class TextSeg(Segment):
    name = "text"
    doc = "Your own label. Set `text` (and colour it in `format`); several can be placed with `type`."
    priority = 10
    tone = "subtext"
    format = "<subtext>{text}</subtext>"
    options = {"text": Opt(str, "", "The text to show.")}
    fields_doc = {"text": "the configured text"}

    def fields(self, ctx, opts, level):
        return {"text": opts["text"]} if opts["text"] else None


@register
class Cycle(Segment):
    name = "cycle"
    doc = ("A slot that shows one of several segments and moves to the next when you click it "
           "(ctrl+shift+click in kitty; needs `statusline.py clicks enable`). Name it, list them in `of`, "
           "and place the name: [segment.limits] type = \"cycle\", of = [\"limit_5h\", \"limit_7d\"].")
    priority = 50
    tone = "text"
    options = {"of": Opt(list, [], "The segments it moves through, in order; the first shows until you click.")}

    def fields(self, ctx, opts, level):
        return None                     # render.py draws the member that is showing


@register
class Clock(Segment):
    name = "clock"
    doc = "The time of day."
    priority = 20
    tone = "subtext"
    format = "<subtext>{time}</subtext>"
    options = {"strftime": Opt(str, "%H:%M", "strftime pattern for {time}.")}
    fields_doc = {"time": "the formatted time", "date": "ISO date", "weekday": "Mon, Tue…"}

    def fields(self, ctx, opts, level):
        import time
        t = time.localtime(ctx.now)             # not datetime: importing it costs more than the bar
        try:
            text = time.strftime(opts["strftime"], t)
        except Exception:
            text = time.strftime("%H:%M", t)
        return {"time": text, "date": time.strftime("%Y-%m-%d", t), "weekday": time.strftime("%a", t)}


@register
class Version(Segment):
    name = "version"
    doc = "The Claude Code version."
    priority = 15
    tone = "muted"
    format = "<muted>v{version}</muted>"
    fields_doc = {"version": "the version string"}

    def fields(self, ctx, opts, level):
        v = ctx.data.get("version")
        return {"version": str(v)} if v else None


@register
class Vim(Segment):
    name = "vim"
    doc = "The vim mode, when vim keybindings are on (pair with hideVimModeIndicator)."
    priority = 35
    tone = "green"
    glance = True
    format = "<vimmode><bold>{mode}</bold></vimmode>"
    fields_doc = {"mode": "NORMAL, INSERT, VISUAL or VISUAL LINE"}
    colors_doc = {"vimmode": "green in INSERT, yellow in VISUAL, blue in NORMAL"}

    def fields(self, ctx, opts, level):
        mode = dig(ctx.data, "vim", "mode")
        return {"mode": str(mode)} if mode else None

    def _role(self, f):
        mode = f["mode"]
        return "green" if mode == "INSERT" else ("yellow" if mode.startswith("VISUAL") else "blue")

    def colors(self, ctx, opts, f):
        return {"vimmode": self._role(f)}

    def tone_at(self, ctx, opts, f):
        return self._role(f)


@register
class Agent(Segment):
    name = "agent"
    doc = "The agent, when Claude Code runs with --agent."
    priority = 38
    tone = "purple"
    format = "<purple>{name}</purple>"
    fields_doc = {"name": "the agent's name"}

    def fields(self, ctx, opts, level):
        name = dig(ctx.data, "agent", "name")
        return {"name": str(name)} if name else None
