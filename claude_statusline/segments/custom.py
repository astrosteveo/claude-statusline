"""Your own command's output (commands.py keeps it off the refresh path)."""
from __future__ import annotations

from ..fit import LEAN, NARROW
from ..text import Text
from ..util import dig, num
from . import Opt, Segment, register


@register
class Command(Segment):
    name = "command"
    doc = ("The first line of your own command's output, run in the background at most every `every` "
           "seconds and stopped after `timeout`; the bar only reads what it printed last. Place several with "
           "`type = \"command\"`. `[commands] enabled = false` turns them all off.")
    priority = 35
    tone = "subtext"
    format = "{text}"
    options = {
        "command": Opt(str, "", "The shell command (run with /bin/sh -c in the session's directory)."),
        "every": Opt(float, 30.0, "Seconds between runs (at least 2)."),
        "timeout": Opt(float, 2.0, "Seconds a run may take before it is killed (at most 10)."),
        "per": Opt(str, "project", "project: a separate output for each directory · global: one for all",
                   choices=("project", "global")),
        "max": Opt(int, 40, "Longest output shown; longer ends in …"),
        "stale": Opt(float, 600.0, "Hide output older than this many seconds (a command that stopped working)."),
    }
    fields_doc = {"text": "the first line it printed, with its colours", "plain": "the same without colours",
                  "age": "seconds since it ran", "exit": "its exit status", "took": "seconds it ran for"}

    def fields(self, ctx, opts, level):
        command = (opts.get("command") or "").strip()
        from .. import commands
        if not command or not commands.enabled(ctx.comp):
            return None
        every = max(commands.MIN_EVERY, num(opts["every"], 30.0))
        timeout = max(0.1, min(commands.MAX_TIMEOUT, num(opts["timeout"], 2.0)))
        key = commands.key_of(command, ctx.cwd, opts["per"])
        entry = commands.read(key)
        stale = entry is None or ctx.now - num(entry.get("at"), 0) >= every
        if stale:
            env = {"STATUSLINE_CWD": ctx.cwd,
                   "STATUSLINE_PROJECT_DIR": str(dig(ctx.data, "workspace", "project_dir") or ctx.cwd),
                   "STATUSLINE_MODEL": str(dig(ctx.data, "model", "display_name") or ""),
                   "STATUSLINE_SESSION_ID": str(ctx.data.get("session_id") or "")}
            if ctx.live:
                commands.request(key, command, ctx.cwd, timeout, env)
            elif ctx.sync_git and entry is None:        # a preview: run it once, bounded by the timeout
                entry = commands.run(key, command, ctx.cwd, timeout, env)
        if entry is None or not entry.get("spans"):
            return None
        age = ctx.now - num(entry.get("at"), 0)
        if age > max(opts["stale"], every * 2):
            return None
        cap = opts["max"] if level < LEAN else (max(8, opts["max"] // 2) if level < NARROW else 12)
        text = Text([(t, (fg, bg, attrs, None)) for t, fg, bg, attrs in entry["spans"]]).clip(max(4, cap))
        return {"text": text, "plain": text.plain(), "age": f"{age:.0f}", "exit": str(entry.get("exit")),
                "took": f"{num(entry.get('took'), 0):.2f}"}
