"""The save file: where it lives, how old saves are upgraded, and safe writes.

Hooks fire in parallel (Claude runs tools concurrently), so every change
happens under an exclusive flock and is written atomically. Saves from every
earlier version of Claude Quest load and are upgraded in place.
"""
import json
import os
from datetime import datetime

from . import home, items, lock_path, state_path

STATS_CACHE = os.path.expanduser("~/.claude/stats-cache.json")
VERSION = 2
LOG_KEEP = 200

COUNTERS = ["commits", "pushes", "tests", "edits", "reads", "prompts", "agents", "bosses",
            "items_found", "items_used", "shell", "web", "thanks", "quests_done",
            "xp_gained", "gold_earned", "forged", "bought", "sold", "dungeons", "raids", "compactions"]


def legacy_xp():
    """Tool calls from before the game existed count as XP, so nobody starts at zero."""
    try:
        with open(STATS_CACHE) as fh:
            data = json.load(fh)
        return sum(d.get("toolCallCount", 0) for d in data.get("dailyActivity", []))
    except (OSError, ValueError, AttributeError, TypeError):
        return 0


def fresh():
    xp = legacy_xp()
    return migrate({"xp": xp, "legacy_xp": xp,
                    "created": datetime.now().isoformat(timespec="seconds")})


def migrate(s):
    """Bring any save up to the current shape. Idempotent."""
    s.setdefault("xp", 0)
    s.setdefault("legacy_xp", 0)
    s.setdefault("created", datetime.now().isoformat(timespec="seconds"))
    s.setdefault("gold", 0)
    s.setdefault("school", {})
    s.setdefault("achievements", {})
    s.setdefault("bag", [])
    s.setdefault("next_uid", 1)
    s.setdefault("equipped", {})
    s.setdefault("buffs", [])
    s.setdefault("charges", {})
    s.setdefault("pet", {"name": None, "bond": 0})
    s.setdefault("title", None)
    s.setdefault("titles", [])
    s.setdefault("days", [])
    s.setdefault("daily", {})
    s.setdefault("weekly", {})
    s.setdefault("shop", {})
    s.setdefault("boss", None)
    s.setdefault("dungeons", {})
    s.setdefault("raids", {})
    s.setdefault("party", {})
    s.setdefault("log", [])
    s.setdefault("sessions", {})
    counters = s.setdefault("counters", {})
    for key in COUNTERS:
        counters.setdefault(key, 0)

    if s.get("version", 1) < 2:
        s["pet"]["bond"] = max(s["pet"].get("bond", 0), len(s["days"]))
        counters["commits"] = max(counters["commits"], s.pop("commits", 0))
        counters["agents"] = max(counters["agents"], s.pop("agents", 0))
        for entry in s.pop("loot", []):
            item_id = items.by_name(entry.get("item", ""))
            if item_id:
                s["bag"].append({"uid": s["next_uid"], "id": item_id, "at": entry.get("at", "")})
                s["next_uid"] += 1
                counters["items_found"] += 1
    s["version"] = VERSION
    return s


def load_readonly():
    try:
        with open(state_path()) as fh:
            return migrate(json.load(fh))
    except (OSError, ValueError):
        return fresh()


class Locked:
    """`with Locked() as state:` — read, change, and write back atomically."""

    def __enter__(self):
        import fcntl
        os.makedirs(home(), exist_ok=True)
        self.path = state_path()
        self.fd = open(lock_path(), "w")
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        try:
            with open(self.path) as fh:
                self.state = migrate(json.load(fh))
        except (FileNotFoundError, ValueError):
            self.state = fresh()
        return self.state

    def __exit__(self, exc_type, *_):
        import fcntl
        try:
            if exc_type is None:
                from . import view
                self.state["view"] = view.build(self.state)
                self.state["log"] = self.state["log"][-LOG_KEEP:]
                tmp = f"{self.path}.{os.getpid()}.tmp"
                with open(tmp, "w") as fh:
                    json.dump(self.state, fh, indent=1, ensure_ascii=False)
                os.replace(tmp, self.path)
        finally:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            self.fd.close()
