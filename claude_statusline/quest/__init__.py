"""Claude Quest: an RPG that plays itself while you work with Claude Code.

Hooks turn what Claude does into XP, loot, quests and boss fights; the save
lives in ~/.claude/quest (or $CLAUDE_QUEST_HOME) and the status line draws
the hero, the boss, the quests and the pet from the snapshot the game writes
beside it. Switch it on or off with `statusline.py quest enable|disable`.
"""
import os


def home() -> str:
    return os.path.expanduser(os.environ.get("CLAUDE_QUEST_HOME") or "~/.claude/quest")


def state_path() -> str:
    return os.path.join(home(), "state.json")


def lock_path() -> str:
    return os.path.join(home(), ".lock")


# Where things were when this module loaded; code that runs later asks the functions.
HOME = home()
STATE = state_path()
LOCK = lock_path()
