"""Live activity: the tools running, the subagents at work, the task list, the turn and the
permission mode, from the file the activity hooks keep (activity.py). Without the hooks these
show nothing."""
from __future__ import annotations

from ..fit import LEAN, LESS, NARROW, TEXT
from ..text import Text
from ..util import num
from ..width import clip
from . import Opt, Segment, register

RECENT_SECONDS = 60.0


def activity(ctx):
    """The session's activity, or None. Sample payloads carry their own under `_activity`,
    with times as seconds before now."""
    def get():
        fake = ctx.data.get("_activity")
        if isinstance(fake, dict):
            return _from_sample(fake, ctx.now)
        from ..activity import STALE, shown
        s = shown(ctx.data.get("session_id"))
        if s is None or ctx.now - num(s.get("at"), 0) > STALE:
            return None
        return s
    return ctx.memo("activity", get)


def _from_sample(d, now):
    from ..activity import fresh

    def t(v):
        v = num(v, 0.0)
        return now + v if v < 0 else v
    s = fresh()
    s["at"] = now
    s["turn"], s["stop"] = t(d.get("turn")), t(d.get("stop"))
    s["failed"] = str(d.get("failed") or "")
    if d.get("ask"):
        s["ask"] = [t(d["ask"][0]), str(d["ask"][1]), "permission", ""]
    s["cwd"] = str(d.get("cwd") or "")
    s["edited"] = {p: t(w) for p, w in (d.get("edited") or {}).items()}
    s["checks"] = {k: v[:5] + [t(v[5]), str(v[6] if len(v) > 6 else "")] for k, v in (d.get("checks") or {}).items()}
    s["mode"] = str(d.get("mode") or "")
    for i, (name, tgt, start, agent) in enumerate(d.get("tools") or []):
        s["tools"][f"t{i}"] = [name, tgt, t(start), agent]
    s["recent"] = [[n, tg, t(end), ok, ag] for n, tg, end, ok, ag in d.get("recent") or []]
    for i, (kind, start, desc, tool, tgt) in enumerate(d.get("agents") or []):
        s["agents"][f"a{i}"] = [kind, t(start), desc, tool, tgt]
    s["tasks"] = {str(i): [subject, status] for i, (subject, status) in enumerate(d.get("tasks") or [])}
    if d.get("compacting"):
        s["compact"] = [now - 5, 0.0, "auto"]
    s["compactions"] = int(num(d.get("compactions"), 0))
    return s


def elapsed(seconds):
    """4s, 52s, 1m04s, 12m, 1h05m."""
    s = max(0, int(seconds))
    if s < 60:
        return f"{s}s"
    if s < 600:
        return f"{s // 60}m{s % 60:02d}s"
    if s < 3600:
        return f"{s // 60}m"
    return f"{s // 3600}h{s % 3600 // 60:02d}m"


class LiveSegment(Segment):
    def data(self, ctx):
        return activity(ctx)


@register
class Tools(LiveSegment):
    name = "tools"
    doc = ("The tools Claude is running now, with what they work on and for how long, then the ones "
           "just finished this turn (live activity).")
    priority = 48
    tone = "cyan"
    format = "[<bold>{tool}</bold>][ <subtext>{target}</subtext>][ <muted>{elapsed}</muted>][ <muted>{more}</muted>][ {done}]"
    options = {"recent": Opt(int, 3, "Finished tools shown after the running one, grouped by name."),
               "target": Opt(int, 32, "Longest target shown (a command, a file, a pattern).")}
    fields_doc = {"tool": "the tool running now (the longest-running, if several)", "target": "what it works on",
                  "elapsed": "how long it has run", "more": "+n other tools running",
                  "done": "tools finished this turn: ✓ Read ×3 · Edit", "running": "how many are running"}

    def fields(self, ctx, opts, level):
        s = self.data(ctx)
        if not s:
            return None
        from ..activity import TOOL_EXPIRES
        running = sorted((v for v in s["tools"].values() if not v[3] and ctx.now - v[2] < TOOL_EXPIRES),
                         key=lambda v: v[2])             # the longest-running first: it is what holds things up
        in_turn = s["turn"] and s["turn"] > s["stop"]
        since = s["turn"] if in_turn else ctx.now - RECENT_SECONDS
        done = [r for r in s["recent"] if not r[4] and r[2] >= since] if in_turn or not s["stop"] else []
        if not running and not done:
            return None
        f = {"tool": "", "target": "", "elapsed": "", "more": "", "done": "", "running": str(len(running))}
        if running:
            name, tgt, start = running[0][:3]
            from ..activity import tool_label
            f["tool"] = tool_label(name)
            cap = {0: opts["target"], 1: max(8, opts["target"] * 3 // 4)}.get(level, 16)
            f["target"] = clip(" ".join(tgt.split()), cap) if tgt and level < NARROW else ""
            if ctx.now - start >= 2:
                f["elapsed"] = elapsed(ctx.now - start)
            if len(running) > 1 and level < TEXT:
                f["more"] = f"+{len(running) - 1}"
        groups = []
        for name, _, _, ok, _ in reversed(done):
            for g in groups:
                if g[0] == name:
                    g[1] += 1
                    g[2] = g[2] and ok
                    break
            else:
                groups.append([name, 1, ok])
        show = max(0, opts["recent"]) if level < LESS else (1 if level < LEAN else 0)
        if not running:
            show = max(show, 1) if level < TEXT else 0
        if groups[:show]:
            from ..activity import tool_label
            t = Text()
            ok_c, bad_c, dim = ctx.color("green"), ctx.color("red"), ctx.color("muted")
            for i, (name, n, ok) in enumerate(groups[:show]):
                if i:
                    t.add(" · ", (dim, None, 0, None))
                t.add(ctx.mark("ok") if ok else ctx.mark("fail"), (ok_c if ok else bad_c, None, 0, None))
                t.add(" " + tool_label(name) + (f" ×{n}" if n > 1 else ""), (ctx.color("subtext"), None, 0, None))
            f["done"] = t
        if not f["tool"] and not f["done"]:
            return None
        return f


@register
class Agents(LiveSegment):
    name = "agents"
    doc = "The subagents at work: their kind, what they were asked, and for how long (live activity)."
    priority = 47
    tone = "purple"
    format = "{agents}"
    options = {"desc": Opt(int, 24, "Longest task description shown for each.")}
    fields_doc = {"agents": "each subagent: kind, task, time", "count": "how many are running",
                  "kinds": "their kinds, comma-separated"}

    def fields(self, ctx, opts, level):
        s = self.data(ctx)
        running = sorted((s or {}).get("agents", {}).values(), key=lambda a: a[1])
        if not running:
            return None
        t = Text()
        dim, sub, bold = ctx.color("muted"), ctx.color("subtext"), ctx.color("purple")
        if level >= NARROW:
            t.add(f"{len(running)} agent{'s' if len(running) != 1 else ''}", (bold, None, 0, None))
        else:
            for i, (kind, start, desc, _, _) in enumerate(running[:3 if level < LEAN else 4]):
                if i:
                    t.add(" · ", (dim, None, 0, None))
                t.add(kind, (bold, None, 1, None))
                if desc and level < LESS:
                    t.add(" " + clip(desc, max(6, opts["desc"])), (sub, None, 0, None))
                if level < LEAN:
                    t.add(" " + elapsed(ctx.now - start), (dim, None, 0, None))
            if len(running) > (3 if level < LEAN else 4):
                t.add(f" +{len(running) - (3 if level < LEAN else 4)}", (dim, None, 0, None))
        return {"agents": t, "count": str(len(running)), "kinds": ", ".join(a[0] for a in running)}


@register
class Tasks(LiveSegment):
    name = "tasks"
    doc = ("The task list Claude keeps (TaskCreate or TodoWrite, where the model has them): the task in "
           "hand and how many are done (live activity).")
    priority = 44
    tone = "green"
    format = "[<text>{current}</text> ]<bold>{done}/{total}</bold>"
    options = {"max": Opt(int, 32, "Longest task title shown.")}
    fields_doc = {"current": "the task in progress (or the next one)", "done": "tasks completed",
                  "total": "tasks in the list"}

    def fields(self, ctx, opts, level):
        s = self.data(ctx)
        tasks = list(((s or {}).get("tasks") or {}).values())
        if not tasks:
            return None
        done = sum(1 for _, st in tasks if st == "completed")
        if done == len(tasks) and s and s.get("stop", 0) > s.get("turn", 0) and \
                ctx.now - s["stop"] > 300:
            return None                     # a finished list fades once the turn is long over
        current = next((t for t, st in tasks if st == "in_progress"), None) or \
            next((t for t, st in tasks if st == "pending"), "")
        cap = opts["max"] if level < LEAN else (16 if level < NARROW else 0)
        return {"current": clip(current, cap) if cap and current else "", "done": str(done),
                "total": str(len(tasks))}


@register
class Turn(LiveSegment):
    name = "turn"
    doc = ("How long Claude has been working on your last message, or how long it has waited for you "
           "since it finished; a question it needs you to answer, compaction and a failed turn too "
           "(live activity).")
    priority = 52
    tone = "accent"
    format = "<turnc>{state}</turnc>[ <subtext>{ask}</subtext>][ <muted>{time}</muted>]"
    options = {"waiting": Opt(bool, True, "Show how long Claude has waited for you."),
               "wait_max": Opt(float, 12.0, "Hours after which the wait is no longer shown."),
               "ask": Opt(int, 40, "Longest question shown after `needs you`; 0 for none.")}
    fields_doc = {"state": "working, needs you, waiting, compacting, or why a turn stopped",
                  "ask": "what Claude asks you: the tool it wants to run, or its question",
                  "time": "how long, in that state", "compactions": "compactions this session"}
    colors_doc = {"turnc": "accent working, red when it needs you, muted waiting, yellow compacting, "
                           "red after a failure"}

    def fields(self, ctx, opts, level):
        s = self.data(ctx)
        if not s:
            return None
        now = ctx.now
        c_start, c_end = s["compact"][0], s["compact"][1]
        base = {"compactions": str(s.get("compactions", 0)), "ask": ""}
        asked, question = s["ask"][0], s["ask"][1]
        if asked and now - asked < 3600:
            cap = opts["ask"] if level < LESS else (min(opts["ask"], 20) if level < NARROW else 0)
            return dict(base, state="needs you", ask=clip(" ".join(question.split()), cap) if cap > 0 else "",
                        time=elapsed(now - asked) if level < LEAN else "", _role="red")
        if c_start and not c_end and now - c_start < 600:
            return dict(base, state="compacting", time=elapsed(now - c_start) if level < NARROW else "",
                        _role="yellow")
        if s["turn"] and s["turn"] > s["stop"]:
            return dict(base, state="working", time=elapsed(now - s["turn"]), _role="accent")
        if s["failed"] and now - s["stop"] < 1800:
            why = {"rate_limit": "rate limited", "overloaded": "overloaded", "max_output_tokens": "out of tokens",
                   "server_error": "server error", "authentication_failed": "signed out",
                   "billing_error": "billing"}.get(s["failed"], s["failed"].replace("_", " "))
            return dict(base, state=f"stopped: {why}" if level < NARROW else "stopped", time="", _role="red")
        if s["stop"] and opts["waiting"] and now - s["stop"] < opts["wait_max"] * 3600:
            return dict(base, state="waiting", time=elapsed(now - s["stop"]), _role="muted")
        return None

    def colors(self, ctx, opts, f):
        return {"turnc": f["_role"]}

    def tone_at(self, ctx, opts, f):
        return f["_role"]


MODES = {"plan": ("plan", "blue"), "acceptEdits": ("accept edits", "yellow"), "auto": ("auto", "teal"),
         "dontAsk": ("don't ask", "orange"), "bypassPermissions": ("bypass", "red")}


@register
class Mode(LiveSegment):
    name = "mode"
    doc = ("The permission mode when it is not the default: plan, accept edits, auto, don't ask or bypass "
           "(live activity; the hooks see it change on the next event).")
    priority = 66
    tone = "yellow"
    glance = True
    format = "<modec><bold>{mode}</bold></modec>"
    fields_doc = {"mode": "the mode's name", "raw": "the mode as Claude Code names it"}
    colors_doc = {"modec": "blue plan, yellow accept edits, teal auto, orange don't ask, red bypass"}

    def fields(self, ctx, opts, level):
        s = self.data(ctx)
        raw = (s or {}).get("mode") or ""
        if raw not in MODES:
            return None
        return {"mode": MODES[raw][0], "raw": raw, "_role": MODES[raw][1]}

    def colors(self, ctx, opts, f):
        return {"modec": f["_role"]}

    def tone_at(self, ctx, opts, f):
        return f["_role"]
