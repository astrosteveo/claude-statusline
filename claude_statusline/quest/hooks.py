"""Claude Code hook entry point: one JSON event on stdin, maybe a systemMessage out.

Registered for SessionStart, UserPromptSubmit, PostToolUse, PostToolUseFailure,
Stop, SubagentStart, SubagentStop and PostCompact by `statusline.py quest enable`. It must never break a session, so
any error is swallowed and the hook exits 0. When Claude Quest is switched
off in the status line config, the hook does nothing at all.

What the game says goes to the save's news. In game mode that is all: the bar
shows it, and nothing is printed into the conversation. With the game on a
line of its own (or inline), the bar has no room for it, so it is also sent
as a systemMessage, after a banner when a session starts.
"""
import os
import sys

SOUNDS = "/usr/share/sounds/freedesktop/stereo"
EVENTS = ("SessionStart", "UserPromptSubmit", "PostToolUse", "PostToolUseFailure", "Stop", "SubagentStart",
          "SubagentStop", "PostCompact")


def _quest_cfg() -> dict:
    try:
        from ..config import compiled
        return compiled()["quest"]
    except Exception:
        return {}


def enabled() -> bool:
    """Whether the status line config has Claude Quest switched on."""
    return bool(os.environ.get("CLAUDE_QUEST_FORCE")) or bool(_quest_cfg().get("enabled"))


def game_mode() -> bool:
    return _quest_cfg().get("placement") == "game"


def _spawn(argv):
    from ..gitstatus import spawn_detached
    import shutil
    if shutil.which(argv[0]):
        spawn_detached(argv)


def deliver(toasts):
    """Desktop notifications and a sound, after the save is safely written ([quest] notify)."""
    if os.environ.get("CLAUDE_QUEST_QUIET") or not toasts or _quest_cfg().get("notify") is False:
        return
    sounds = []
    for title, body, sound in toasts:
        _spawn(["notify-send", "-a", "Claude Quest", "-i", "starred", title, body])
        if sound and sound not in sounds:
            sounds.append(sound)
    for sound in sounds[:1]:
        path = os.path.join(SOUNDS, f"{sound}.oga")
        if os.path.exists(path):
            _spawn(["pw-play", path])


def handle(event):
    name = event.get("hook_event_name")
    if name not in EVENTS:
        return None
    from . import state as store
    from .game import Game
    banner = None
    chat = not game_mode()
    with store.Locked() as state:
        g = Game(state)
        g.tick()
        if name == "SessionStart":
            g.session_start()
        elif name == "UserPromptSubmit":
            g.prompt(event.get("prompt", ""))
        elif name in ("PostToolUse", "PostToolUseFailure"):
            g.tool(event, failed=name == "PostToolUseFailure")
        elif name == "Stop":
            g.stop()
        elif name == "SubagentStart":
            g.party_join(str(event.get("agent_id") or ""), str(event.get("agent_type") or ""))
        elif name == "SubagentStop":
            g.party_leave(str(event.get("agent_id") or ""))
        elif name == "PostCompact":
            g.compacted(str(event.get("trigger") or ""))
        g.finish()
        store.add_news(state, g.msgs, g.now)
        if chat and name == "SessionStart" and event.get("source", "startup") in ("startup", "resume"):
            from . import ui, view
            banner = ui.banner(view.build(state, g.now), g.streak())
    deliver(g.toasts)
    if name == "SessionStart" and os.environ.get("KITTY_WINDOW_ID"):
        try:
            from .art import field_launcher
            field_launcher.autostart()
        except Exception:
            pass
    msgs = ([banner] if banner else []) + (g.msgs if chat else [])
    return "\n".join(msgs) if msgs else None


def run():
    try:
        raw = sys.stdin.read()
        if not enabled():
            return 0
        from ..fastjson import loads
        event = loads(raw) if raw.strip() else {}
        message = handle(event) if isinstance(event, dict) else None
    except Exception:
        if os.environ.get("CLAUDE_QUEST_DEBUG"):
            raise
        return 0
    if message:
        import json
        print(json.dumps({"systemMessage": message, "suppressOutput": True}))
    return 0
