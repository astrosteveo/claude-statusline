"""PR dungeons: opening a pull request with `gh pr create` opens a dungeon.

Every push to the project while it is open is another room (a round of
review fixes); every `gh pr checks` run that reports failures springs a
trap. `gh pr merge` clears it, paying more the deeper it went; `gh pr close`
abandons it. A dungeon nobody merges collapses after two weeks.
"""
import random
import re

COLLAPSE_AFTER = 14 * 24 * 3600
KEEP = 10
ICON = "🏰"
PLACES = ["Crypt", "Keep", "Catacombs", "Vault", "Labyrinth", "Sunken Hall", "Spire", "Undercroft"]
EPITHETS = ["Merge Conflicts", "the Nitpick", "Endless Review", "the Red X", "Stale Branches",
            "the Flaky Check", "a Thousand Comments", "the Rebase"]

_GH_PR = re.compile(r"^gh\s+pr\s+(create|merge|close|checks)\b(.*)")
# Only plain arguments may follow merge, close and checks, so `gh pr merge` quoted inside
# some other text (a heredoc, a test) is not taken for the real thing. `create` is
# trusted only when its output holds the new pull request's URL.
_ARGS = re.compile(r"""(?:\s+(?:[\w#./:=@+-]+|"[^"]*"|'[^']*'))*\s*""")
_URL = re.compile(r"https?://\S+/pull/(\d+)")
_NUMBER = re.compile(r"(?:^|\s)#?(\d+)(?=\s|$)")
_FAIL_LINE = re.compile(r"^\S.*\t(?:fail|failure)\t|^X\s", re.M | re.I)


def commands(segments):
    """(verb, rest of the line) for every `gh pr` command among a shell line's segments."""
    for seg in segments:
        m = _GH_PR.match(seg)
        if m and (m.group(1) == "create" or _ARGS.fullmatch(m.group(2))):
            yield m.group(1), m.group(2)


def url_number(text):
    """The number in a pull request URL in text, or None."""
    m = _URL.search(text or "")
    return int(m.group(1)) if m else None


def number_in(args):
    """The PR a merge, close or checks command names, by URL or number, or None."""
    n = url_number(args)
    if n is not None:
        return n
    m = _NUMBER.search(args or "")
    return int(m.group(1)) if m else None


def failing_checks(output):
    """Checks `gh pr checks` reported as failing."""
    return len(_FAIL_LINE.findall(output or ""))


def key(project, number):
    return f"{project}#{number}"


def open_(project, number, now, rng=None):
    rng = rng or random.Random()
    return {"project": project, "number": number, "opened": now, "rooms": 1, "traps": 0,
            "name": f"{rng.choice(PLACES)} of {rng.choice(EPITHETS)}"}


def find(dungeons, project, number=None):
    """The dungeon a merge or close in this project means: by number, else the newest there."""
    if number is not None:
        return dungeons.get(key(project, number))
    here = [d for d in dungeons.values() if d["project"] == project]
    return max(here, key=lambda d: d["opened"]) if here else None


def rewards(d, level):
    """(xp, gold, loot fortune) for clearing a dungeon."""
    rooms, traps = d["rooms"], d["traps"]
    return (100 + 40 * rooms + 25 * traps + 5 * level, 40 + 15 * rooms + 10 * traps,
            0.5 + 0.2 * min(rooms + traps, 10))
