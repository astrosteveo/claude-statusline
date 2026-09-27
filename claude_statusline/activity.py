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
          "TaskCreated", "TaskCompleted", "SessionEnd")
TOOL_EVENTS = ("PreToolUse", "PostToolUse", "PostToolUseFailure")
VERSION = 1
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
            "tasks": {}, "mode": "", "calls": 0}


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


# --- folding one event in ----------------------------------------------------------------
def apply(s, event, now):
    """Fold one hook event into the state `s` (changed in place). False to delete the file."""
    name = event.get("hook_event_name")
    mode = event.get("permission_mode")
    if isinstance(mode, str) and mode:
        s["mode"] = mode
    agent = str(event.get("agent_id") or "")
    if name in TOOL_EVENTS:
        tid = str(event.get("tool_use_id") or "")
        tool = str(event.get("tool_name") or "?")
        if name == "PreToolUse":
            if tid and tid not in s["ended"]:
                s["tools"][tid] = [tool, target(tool, event.get("tool_input")), now, agent]
                s["calls"] += 1
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
    elif name == "SessionEnd":
        return False
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


def record(event, now=None):
    """Fold `event` into its session's file, under the session's lock."""
    import fcntl
    import marshal
    sid = event.get("session_id")
    if not sid:
        return
    now = time.time() if now is None else now
    dest = path(sid)
    with open(dest + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        s = load(sid)
        if s is None or now - float(s.get("at") or 0) > STALE:
            s = fresh()
        keep = apply(s, event, now)
        if not keep:
            for p in (dest, dest + ".lock"):
                try:
                    os.unlink(p)
                except OSError:
                    pass
            return
        tmp = f"{dest}.{os.getpid()}"
        with open(tmp, "wb") as fh:
            fh.write(marshal.dumps(s))
        os.replace(tmp, dest)


def enabled() -> bool:
    try:
        from .config import compiled
        return bool(compiled()["activity"].get("enabled"))
    except Exception:
        return False


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
            record(event, now)
            if event.get("hook_event_name") == "SessionStart":
                sweep()
    except Exception:
        if os.environ.get("CLAUDE_STATUSLINE_DEBUG"):
            raise
    return 0


def sweep(max_age=STALE):
    """Remove the files of sessions that ended without saying so."""
    from .config import runtime_dir
    now = time.time()
    try:
        names = os.listdir(runtime_dir())
    except OSError:
        return
    for n in names:
        if n.startswith("activity-"):
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
    sweep(0)
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
