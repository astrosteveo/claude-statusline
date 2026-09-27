"""Claude Code's settings.json: the statusLine entry and Claude Quest's hooks.

Every change is written atomically, and the file is backed up once before
the first change of a run. A file that is not valid JSON is never touched.
"""
from __future__ import annotations

import json
import os
import shutil
import time

CLAUDE_DIR = os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude")
SETTINGS = os.path.join(CLAUDE_DIR, "settings.json")
ENTRY = os.path.join(CLAUDE_DIR, "statusline.py")

HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "PostToolUse", "PostToolUseFailure", "Stop", "SubagentStart",
               "SubagentStop", "PostCompact")
# Commands earlier Claude Quest installs registered; replaced on enable, removed on disable.
LEGACY_HOOK_MARKS = ("claude/quest/quest.py", "claude-quest hook", "claude_quest")


class SettingsError(RuntimeError):
    pass


def entry_command(*args) -> str:
    """How settings.json should invoke the engine."""
    path = "~/.claude/statusline.py" if os.path.exists(ENTRY) else os.path.abspath(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "statusline.py"))
    return " ".join(["python3", "-S", path, *args])


def load(path=SETTINGS) -> dict:
    try:
        with open(path) as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    except ValueError as exc:
        raise SettingsError(f"{path} is not valid JSON ({exc}); not touching it") from None
    if not isinstance(data, dict):
        raise SettingsError(f"{path} is not a JSON object; not touching it")
    return data


def save(data: dict, path=SETTINGS, backup=True) -> str | None:
    """Write `data`; returns the backup's path when one was made."""
    made = None
    if backup and os.path.exists(path):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        made = f"{path}.bak-{stamp}"
        n = 1
        while os.path.exists(made):
            made = f"{path}.bak-{stamp}-{n}"
            n += 1
        shutil.copy2(path, made)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
    return made


def status_line_entry() -> dict:
    return {"type": "command", "command": entry_command(), "padding": 0, "refreshInterval": 1}


def _is_activity_hook(command: str) -> bool:
    command = command or ""
    return " activity hook" in command and "statusline.py" in command


def activity_hooks_present(data: dict) -> bool:
    from .activity import EVENTS
    hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
    want = entry_command("activity", "hook")
    return all(any(h.get("command") == want and h.get("async") for e in hooks.get(ev) or [] if isinstance(e, dict)
                   for h in e.get("hooks") or [] if isinstance(h, dict)) for ev in EVENTS)


def add_activity_hooks(data: dict):
    """The live-activity hooks: background (`async`), so no tool call waits for them."""
    from .activity import EVENTS, TOOL_EVENTS
    hooks = data.setdefault("hooks", {})
    command = entry_command("activity", "hook")
    for event in EVENTS:
        entry = {"hooks": [{"type": "command", "command": command, "async": True}]}
        if event in TOOL_EVENTS:
            entry = {"matcher": "*", **entry}
        hooks.setdefault(event, []).append(entry)


def strip_activity_hooks(data: dict) -> int:
    return _strip(data, _is_activity_hook)


def _is_quest_hook(command: str) -> bool:
    command = command or ""
    return (" quest hook" in command and "statusline.py" in command) or any(m in command for m in LEGACY_HOOK_MARKS)


def quest_hooks_missing(data: dict) -> list:
    """Events Claude Quest wants a hook on that settings.json lacks (an older `quest enable`)."""
    hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
    want = entry_command("quest", "hook")
    return [ev for ev in HOOK_EVENTS if not any(h.get("command") == want for e in hooks.get(ev) or []
                                                  if isinstance(e, dict) for h in e.get("hooks") or []
                                                  if isinstance(h, dict))]


def quest_hooks_present(data: dict) -> bool:
    hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
    want = entry_command("quest", "hook")
    return all(any(h.get("command") == want for e in hooks.get(ev) or [] if isinstance(e, dict)
                   for h in e.get("hooks") or [] if isinstance(h, dict)) for ev in HOOK_EVENTS)


def strip_quest_hooks(data: dict) -> int:
    """Remove every Claude Quest hook (this engine's and older installs'). Returns how many."""
    return _strip(data, _is_quest_hook)


def _strip(data: dict, ours) -> int:
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return 0
    removed = 0
    for event in list(hooks):
        entries = hooks.get(event)
        if not isinstance(entries, list):
            continue
        kept = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
                kept.append(entry)
                continue
            inner = [h for h in entry["hooks"] if not (isinstance(h, dict) and ours(h.get("command")))]
            removed += len(entry["hooks"]) - len(inner)
            if inner:
                kept.append(dict(entry, hooks=inner))
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        data.pop("hooks", None)
    return removed


def add_quest_hooks(data: dict):
    hooks = data.setdefault("hooks", {})
    command = entry_command("quest", "hook")
    for event in HOOK_EVENTS:
        entry = {"hooks": [{"type": "command", "command": command, "timeout": 5}]}
        if event.startswith("PostToolUse"):
            entry = {"matcher": "*", **entry}
        hooks.setdefault(event, []).append(entry)
