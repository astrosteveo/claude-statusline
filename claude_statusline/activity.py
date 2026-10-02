"""Live activity: what Claude is doing right now, kept by hooks for the bar.

`statusline.py activity enable` registers command hooks with `async: true`,
so no tool call waits for them. Each event runs `statusline.py activity
hook`, which folds it into a small marshal file per session in the runtime
directory, under a lock, replacing the file atomically. A refresh reads that
file once and the `tools`, `agents`, `tasks`, `turn` and `mode` segments draw
from it.

Async hooks can finish out of order (a quick tool's end before its start),
so an end leaves a short-lived mark and a start that arrives after its own
end is ignored. Anything that never ends expires on its own.
"""
from __future__ import annotations

import os
import time

EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure",
          "SubagentStart", "SubagentStop", "Stop", "StopFailure", "PreCompact", "PostCompact",
          "TaskCreated", "TaskCompleted", "SessionEnd", "Notification", "PermissionRequest")
TOOL_EVENTS = ("PreToolUse", "PostToolUse", "PostToolUseFailure")
# Notifications that mean Claude is stuck until you answer (idle_prompt only says it is waiting).
ASKS = ("permission_prompt", "elicitation_dialog", "elicitation_url_dialog", "agent_needs_input")
ASK_TOOLS = ("AskUserQuestion", "ExitPlanMode")      # tools that wait for you to answer
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
VERSION = 2
EDITED = 300                  # files Claude edited, remembered for the changes panel
KEEP_ENDED = 120.0            # seconds an end mark waits for a start that arrives late
TOOL_EXPIRES = 1800.0         # a tool with no end is forgotten after this long
AGENT_EXPIRES = 4 * 3600.0
RECENT = 12
STALE = 12 * 3600.0           # a file this old belongs to a session long gone


def path(session_id):
    from .config import runtime_dir
    sid = "".join(ch for ch in str(session_id) if ch.isalnum() or ch in "-_")[:64] or "none"
    return os.path.join(runtime_dir(), f"activity-{sid}.bin")


def fresh():
    return {"v": VERSION, "at": 0.0, "turn": 0.0, "stop": 0.0, "failed": "", "tools": {}, "ended": {},
            "recent": [], "agents": {}, "pending": [], "compact": [0.0, 0.0, ""], "compactions": 0,
            "tasks": {}, "mode": "", "calls": 0, "closed": 0.0,
            "cwd": "", "ask": [0.0, "", "", ""], "edited": {}, "checks": {}}


# --- what a tool call is about ---------------------------------------------------------
def _base(p):
    p = str(p or "").replace("\\", "/").rstrip("/")
    return p.rsplit("/", 1)[-1]


def target(name, tool_input):
    """A few words on what a tool call works on: a file, a command, a pattern."""
    ti = tool_input if isinstance(tool_input, dict) else {}
    if name in ("Bash", "PowerShell", "Monitor"):
        cmd = str(ti.get("command") or "").strip().split("\n", 1)[0]
        return cmd
    if name in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit"):
        return _base(ti.get("file_path") or ti.get("notebook_path"))
    if name in ("Grep", "Glob"):
        return str(ti.get("pattern") or "")
    if name == "WebFetch":
        url = str(ti.get("url") or "")
        return url.split("://", 1)[-1].split("/", 1)[0]
    if name == "WebSearch":
        return str(ti.get("query") or "")
    if name == "Agent":
        return str(ti.get("description") or ti.get("subagent_type") or "")
    if name == "Skill":
        return str(ti.get("skill") or ti.get("name") or "")
    if name.startswith("mcp__"):
        parts = name.split("__")
        return parts[1] if len(parts) > 2 else ""
    return ""


def tool_label(name):
    """`mcp__github__create_issue` -> `create_issue`."""
    if name.startswith("mcp__"):
        return name.split("__")[-1]
    return name


def _question(tool, tool_input):
    """What a tool that waits on you asks: the first question, or the plan to approve."""
    ti = tool_input if isinstance(tool_input, dict) else {}
    if tool == "ExitPlanMode":
        return "approve the plan"
    qs = ti.get("questions")
    q = qs[0] if isinstance(qs, list) and qs and isinstance(qs[0], dict) else {}
    return " ".join(str(q.get("question") or ti.get("question") or "a question").split())[:200]


def _answered(ask, name, tid, agent):
    """Whether `name` means the question in `ask` has been answered. A question about a tool call
    lasts until that call ends; one with no call until the main thread uses a tool. A new prompt,
    the end of the turn or of the session answers either. Subagents working on answer nothing."""
    if name in ("UserPromptSubmit", "Stop", "StopFailure", "SessionEnd"):
        return True
    if ask[3]:
        return name in ("PostToolUse", "PostToolUseFailure") and tid == ask[3]
    return name in TOOL_EVENTS and not agent


# --- folding one event in ----------------------------------------------------------------
def apply(s, event, now):
    """Fold one hook event into the state `s` (changed in place). False to delete the file."""
    name = event.get("hook_event_name")
    if s.get("closed") and name != "SessionStart":
        return True                        # async events that arrive after the session ended change nothing
    s["closed"] = 0.0
    cwd = event.get("cwd")
    if isinstance(cwd, str) and cwd:
        s["cwd"] = cwd
    tid = str(event.get("tool_use_id") or "")
    agent = str(event.get("agent_id") or "")
    if s["ask"][0] and _answered(s["ask"], name, tid, agent):
        s["ask"] = [0.0, "", "", ""]
    mode = event.get("permission_mode")
    if isinstance(mode, str) and mode:
        s["mode"] = mode
    if name in TOOL_EVENTS:
        tool = str(event.get("tool_name") or "?")
        if name == "PreToolUse":
            if tid and tid not in s["ended"]:
                s["tools"][tid] = [tool, target(tool, event.get("tool_input")), now, agent]
                s["calls"] += 1
                if tool in ASK_TOOLS and not agent:
                    s["ask"] = [now, _question(tool, event.get("tool_input")), "question", tid]
            if tool == "Agent":
                ti = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
                s["pending"].append([str(ti.get("subagent_type") or "general-purpose"),
                                     str(ti.get("description") or ""), now])
                s["pending"] = s["pending"][-8:]
        else:
            started = s["tools"].pop(tid, None)
            if tid:
                s["ended"][tid] = now
            ok = name == "PostToolUse"
            s["recent"].append([tool, started[1] if started else target(tool, event.get("tool_input")),
                                now, ok, agent])
            s["recent"] = s["recent"][-RECENT:]
            _task_tool(s, tool, event.get("tool_input"), event.get("tool_response"))
            ti = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
            if ok and tool in EDIT_TOOLS:
                fp = ti.get("file_path") or ti.get("notebook_path")
                if isinstance(fp, str) and fp:
                    s["edited"].pop(fp, None)
                    s["edited"][fp] = now
                    if len(s["edited"]) > EDITED:
                        s["edited"] = dict(list(s["edited"].items())[-EDITED:])
            resp = event.get("tool_response")
            if tool == "Bash" and not (isinstance(resp, dict) and resp.get("interrupted")):
                from .checks import failed, output_of, summary
                found = summary(ti.get("command"), output_of(event), failed(event))
                if found:
                    s["checks"][found[0]] = found[1:] + [now, s["cwd"]]
        if agent in s["agents"]:
            a = s["agents"][agent]
            a[3], a[4] = tool, target(tool, event.get("tool_input"))
    elif name == "UserPromptSubmit":
        s["turn"] = now
        s["failed"] = ""
    elif name == "Stop":
        s["stop"] = now
        s["turn"] = 0.0
        s["tools"] = {k: v for k, v in s["tools"].items() if v[3]}      # the main thread is done
    elif name == "StopFailure":
        s["stop"] = now
        s["turn"] = 0.0
        s["failed"] = str(event.get("error_type") or "error")
        s["tools"] = {k: v for k, v in s["tools"].items() if v[3]}
    elif name == "SubagentStart":
        kind = str(event.get("agent_type") or "agent")
        desc = ""
        for i, (ptype, pdesc, _) in enumerate(s["pending"]):
            if ptype == kind:
                desc = pdesc
                del s["pending"][i]
                break
        if agent:
            s["agents"][agent] = [kind, now, desc, "", ""]
    elif name == "SubagentStop":
        s["agents"].pop(agent, None)
        s["tools"] = {k: v for k, v in s["tools"].items() if v[3] != agent}
    elif name == "PreCompact":
        s["compact"] = [now, 0.0, str(event.get("trigger") or "")]
    elif name == "PostCompact":
        s["compact"] = [s["compact"][0] or now, now, str(event.get("trigger") or s["compact"][2])]
        s["compactions"] += 1
    elif name in ("TaskCreated", "TaskCompleted"):
        tid = str(event.get("task_id") or "")
        if tid:
            done = name == "TaskCompleted"
            s["tasks"][tid] = [str(event.get("task_subject") or ""), "completed" if done else
                               (s["tasks"].get(tid, [0, "pending"])[1])]
    elif name == "Notification":
        kind = str(event.get("notification_type") or "")
        if kind in ASKS and not s["ask"][0]:
            s["ask"] = [now, str(event.get("message") or "")[:200], kind, ""]
    elif name == "PermissionRequest":
        if tid not in s["ended"]:          # an async hook can land after the tool it asked about ran
            tool = str(event.get("tool_name") or "?")
            what = target(tool, event.get("tool_input"))
            s["ask"] = [now, f"{tool_label(tool)} {what}".strip(), "permission", tid]
    elif name == "SessionEnd":
        s["closed"] = now
        s["tools"], s["agents"] = {}, {}
    _prune(s, now)
    s["at"] = now
    return True


def _task_tool(s, tool, tool_input, response):
    """The task list, from the tools that keep it (TaskCreate, TaskUpdate, TodoWrite)."""
    ti = tool_input if isinstance(tool_input, dict) else {}
    if tool == "TodoWrite" and isinstance(ti.get("todos"), list):
        s["tasks"] = {str(i): [str(t.get("content") or ""), str(t.get("status") or "pending")]
                      for i, t in enumerate(ti["todos"]) if isinstance(t, dict)}
    elif tool == "TaskUpdate":
        tid = str(ti.get("taskId") or ti.get("task_id") or "")
        status = ti.get("status")
        if tid and isinstance(status, str):
            if status == "deleted":
                s["tasks"].pop(tid, None)
            else:
                entry = s["tasks"].setdefault(tid, [str(ti.get("subject") or ""), "pending"])
                entry[1] = status
    elif tool == "TaskCreate":
        tid = ""
        if isinstance(response, dict):
            task = response.get("task") if isinstance(response.get("task"), dict) else response
            tid = str(task.get("id") or task.get("taskId") or "")
        if tid:
            s["tasks"].setdefault(tid, [str(ti.get("subject") or ""), "pending"])


def _prune(s, now):
    s["ended"] = {k: t for k, t in s["ended"].items() if now - t < KEEP_ENDED}
    s["tools"] = {k: v for k, v in s["tools"].items() if now - v[2] < TOOL_EXPIRES}
    s["agents"] = {k: v for k, v in s["agents"].items() if now - v[1] < AGENT_EXPIRES}
    s["pending"] = [p for p in s["pending"] if now - p[2] < 600]
    if len(s["tasks"]) > 50:
        s["tasks"] = dict(list(s["tasks"].items())[-50:])


# --- files --------------------------------------------------------------------------------
def load(session_id):
    """The session's activity, or None (no hooks, no session, or long gone)."""
    if not session_id:
        return None
    import marshal
    try:
        with open(path(session_id), "rb") as fh:
            s = marshal.loads(fh.read())
    except (OSError, ValueError, EOFError, TypeError):
        return None
    if not isinstance(s, dict) or s.get("v") != VERSION:
        return None
    return s


def shown(session_id):
    """The session's activity for the bar: None once the session has ended."""
    s = load(session_id)
    return None if s is None or s.get("closed") else s


def record(event, now=None):
    """Fold `event` into its session's file, under the session's lock. Returns (state before
    the event's turn and ask, state after) for the pop-ups."""
    import fcntl
    import marshal
    sid = event.get("session_id")
    if not sid:
        return None
    now = time.time() if now is None else now
    dest = path(sid)
    with open(dest + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        s = load(sid)
        if s is None or now - float(s.get("at") or 0) > STALE:
            s = fresh()
        before = (s["turn"], s["ask"][0])
        apply(s, event, now)
        tmp = f"{dest}.{os.getpid()}"
        with open(tmp, "wb") as fh:
            fh.write(marshal.dumps(s))
        os.replace(tmp, dest)
    return before, s


def _cfg() -> dict:
    try:
        from .config import compiled
        return compiled()["activity"]
    except Exception:
        return {}


def enabled() -> bool:
    return bool(_cfg().get("enabled"))


# --- pop-ups ----------------------------------------------------------------------------------
def project_of(s):
    return _base(s.get("cwd")) or "Claude"


def pop_ups(event, before, s, now, cfg):
    """What to do after an event: [("ask", seconds)] to check back on a question, or
    [("done", title, body)] for a long turn that just ended."""
    if not cfg.get("notify", True):
        return []
    name = event.get("hook_event_name")
    if s["ask"][0] and s["ask"][0] != before[1]:
        return [("ask", max(0.0, float(cfg.get("notify_ask", 20.0))))]
    if name in ("Stop", "StopFailure") and before[0]:
        took = now - before[0]
        if took >= float(cfg.get("notify_after", 120.0)):
            what = "stopped" if name == "StopFailure" else "finished"
            return [("done", f"Claude {what} · {project_of(s)}", f"after {_took(took)}")]
    return []


def _took(sec):
    sec = int(sec)
    return f"{sec // 60}m{sec % 60:02d}s" if sec < 3600 else f"{sec // 3600}h{sec % 3600 // 60:02d}m"


def notify(title, body, urgent=False):
    import shutil
    from .gitstatus import spawn_detached
    if shutil.which("notify-send"):
        spawn_detached(["notify-send", "-a", "Claude Code", "-u", "critical" if urgent else "normal",
                        "-i", "dialog-question" if urgent else "dialog-information", title, body])


def _nudge_main(args):
    """A detached check, a little after a question: still unanswered, so say so on the desktop."""
    sid, asked, wait = args[0], float(args[1]), float(args[2])
    time.sleep(wait)
    s = load(sid)
    if not s or s.get("closed") or s["ask"][0] != asked:
        return
    notify(f"Claude needs you · {project_of(s)}", s["ask"][1] or "waiting for an answer", urgent=True)


def hook_main() -> int:
    """The hook: one event on stdin. Never fails a session, never prints."""
    import sys
    try:
        now = time.time()
        raw = sys.stdin.buffer.read()
        if not raw.strip() or not enabled():
            return 0
        from .fastjson import loads
        event = loads(raw)
        if isinstance(event, dict):
            done = record(event, now)
            if event.get("hook_event_name") == "SessionStart":
                sweep()
            if done:
                for act in pop_ups(event, *done, now, _cfg()):
                    if act[0] == "done":
                        notify(act[1], act[2])
                    else:
                        _spawn_nudge(str(event.get("session_id")), done[1]["ask"][0], act[1])
    except Exception:
        if os.environ.get("CLAUDE_STATUSLINE_DEBUG"):
            raise
    return 0


def _spawn_nudge(sid, asked, wait):
    import sys
    from .gitstatus import spawn_detached
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = ("import sys; sys.path.insert(0, sys.argv[1]); "
            "from claude_statusline.activity import _nudge_main; _nudge_main(sys.argv[2:])")
    spawn_detached([sys.executable, "-S", "-c", code, parent, sid, repr(asked), str(wait)])


def sweep(max_age=STALE, locks=False):
    """Remove the files of sessions long gone. Locks go too only when the hooks are off
    (`disable`), since a hook running now may hold one."""
    from .config import runtime_dir
    now = time.time()
    try:
        names = os.listdir(runtime_dir())
    except OSError:
        return
    for n in names:
        if (n.startswith("activity-") and (locks or not n.endswith(".lock"))) or n.startswith("turns-"):
            p = os.path.join(runtime_dir(), n)
            try:
                if now - os.stat(p).st_mtime > max_age:
                    os.unlink(p)
            except OSError:
                pass


# --- switching it on and off ------------------------------------------------------------------
def set_config_enabled(on: bool) -> str:
    from .config import write_path
    from .tomlw import set_key
    path = write_path()
    try:
        with open(path) as fh:
            text = fh.read()
    except FileNotFoundError:
        text = ""
    new = set_key(text, "activity.enabled", bool(on))
    if new != text:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w") as fh:
            fh.write(new if new.endswith("\n") else new + "\n")
        os.replace(tmp, path)
    return path


def enable(log=print) -> int:
    from . import settings as st
    try:
        data = st.load()
    except st.SettingsError as exc:
        log(f"  {exc}")
        return 1
    before = st.strip_activity_hooks(data)
    st.add_activity_hooks(data)
    backup = st.save(data)
    log(f"  hooks: {len(EVENTS)} registered in {st.SETTINGS}, running in the background"
        + (f" (replaced {before})" if before else "") + (f"; backup {os.path.basename(backup)}" if backup else ""))
    log(f"  config: [activity] enabled = true in {set_config_enabled(True)}")
    log("  segments: turn, tools, agents, tasks and mode get a line of their own unless you place "
        "them ([activity] placement = \"manual\")")
    log("  sessions started before now pick the hooks up when they restart")
    return 0


def disable(log=print) -> int:
    from . import settings as st
    try:
        data = st.load()
    except st.SettingsError as exc:
        log(f"  {exc}")
        return 1
    removed = st.strip_activity_hooks(data)
    if removed:
        backup = st.save(data)
        log(f"  hooks: removed {removed} from {st.SETTINGS}" + (f"; backup {os.path.basename(backup)}" if backup else ""))
    else:
        log("  hooks: none registered")
    log(f"  config: [activity] enabled = false in {set_config_enabled(False)}")
    sweep(0, locks=True)
    return 0


def status(log=print) -> int:
    from . import settings as st
    from .config import compiled
    on = bool(compiled()["activity"].get("enabled"))
    try:
        hooks = st.activity_hooks_present(st.load())
    except st.SettingsError:
        hooks = False
    log(f"  live activity  {'on' if on else 'off'}" + ("" if on == hooks else
        f"  (hooks {'present' if hooks else 'missing'}: run `statusline.py activity {'enable' if on else 'disable'}`)"))
    log(f"  hooks          {'registered' if hooks else 'not registered'} in {st.SETTINGS}")
    return 0


def main(argv) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "hook":
        return hook_main()
    fn = {"enable": enable, "disable": disable, "status": status}.get(cmd)
    if fn is None:
        print("usage: statusline.py activity enable | disable | status")
        return 2
    return fn()
