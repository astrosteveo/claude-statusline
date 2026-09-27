"""The tech-debt raid: a weekly boss per project whose HP is its debt markers.

Each commit counts the TODO, FIXME, XXX and HACK markers in the project's
tracked files. The first count of the week summons the raid boss; later
commits that bring the count below its lowest so far damage it (adding
markers back heals it, but removing them again pays nothing twice), and a
count of zero defeats it. A new week brings a new raid.
"""
import subprocess

ICON = "🐙"
NAMES = ["Tech Debt Leviathan", "Backlog Kraken", "Legacy Behemoth", "Deprecation Hydra",
         "Spaghetti Colossus", "Workaround Wyrm"]
MARKERS = r"\b(TODO|FIXME|XXX|HACK)\b"


def count_debt(cwd, timeout=3.0):
    """Debt markers in the tracked files of the repository holding cwd, or None."""
    if not cwd:
        return None
    try:
        out = subprocess.run(["git", "-C", cwd, "grep", "-I", "-c", "-E", MARKERS, "--", ":/"],
                             capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode == 1 and not out.stdout:
        return 0                                 # git grep: no matches
    if out.returncode != 0:
        return None
    total = 0
    for line in out.stdout.splitlines():
        try:
            total += int(line.rsplit(":", 1)[1])
        except (IndexError, ValueError):
            pass
    return total


def summon(project, week, debt, rng):
    return {"project": project, "week": week, "name": rng.choice(NAMES), "hp": debt,
            "max_hp": debt, "low": debt, "defeated": False}


def rewards(r, level):
    """(xp, gold, loot fortune) for bringing a raid boss to zero."""
    return 200 + 10 * min(r["max_hp"], 200) + 5 * level, 50 + 5 * min(r["max_hp"], 200), 1.0
