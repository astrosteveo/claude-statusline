"""Claude Code hook entry point: one JSON event on stdin, maybe a systemMessage out.

Registered for SessionStart, UserPromptSubmit, PostToolUse, PostToolUseFailure
and Stop by `statusline.py quest enable`. It must never break a session, so
any error is swallowed and the hook exits 0. When Claude Quest is switched
off in the status line config, the hook does nothing at all.
"""
import os
import sys

SOUNDS = "/usr/share/sounds/freedesktop/stereo"
EVENTS = ("SessionStart", "UserPromptSubmit", "PostToolUse", "PostToolUseFailure", "Stop")


def enabled() -> bool:
    """Whether the status line config has Claude Quest switched on."""
    if os.environ.get("CLAUDE_QUEST_FORCE"):
        return True
    try:
        from ..config import compiled
        return bool(compiled()["quest"].get("enabled"))
    except Exception:
        return False


def _spawn(argv):
    from ..gitstatus import spawn_detached
    import shutil
    if shutil.which(argv[0]):
        spawn_detached(argv)


def deliver(toasts):
    """Desktop notifications and a sound, after the save is safely written."""
    if os.environ.get("CLAUDE_QUEST_QUIET") or not toasts:
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
        g.finish()
        if name == "SessionStart" and event.get("source", "startup") in ("startup", "resume"):
            from . import ui, view
            banner = ui.banner(view.build(state, g.now), g.streak())
    deliver(g.toasts)
    if name == "SessionStart" and os.environ.get("KITTY_WINDOW_ID"):
        try:
            from .art import field_launcher
            field_launcher.autostart()
        except Exception:
            pass
    msgs = ([banner] if banner else []) + g.msgs
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
