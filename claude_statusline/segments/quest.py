"""Claude Quest on the bar: the hero, the boss, quests, buffs, the latest
event, the streak, and the pet (as text anywhere, or as an animated picture
in kitty).

Everything reads the snapshot the game writes into its save
(`state["view"]`), so the bar never needs the game's rules. All motion comes
from the clock, like the heartbeat: the pet walks only while the bar is
being refreshed. None of these show anything unless `[quest] enabled`.
"""
from __future__ import annotations

import os

from ..fit import LEAN, LESS, NARROW, TEXT
from ..text import Text
from ..util import num
from ..width import clip
from . import Opt, Segment, register

STAGES = [
    (1, "egg", ["(_)", "(_)"]),
    (5, "hatchling", ["(o>", "(o>"]),
    (15, "lizard", ["~=(o>", "~-(o>"]),
    (30, "drake", ["~^(O>", "~v(O>"]),
    (50, "wyrm", ["~~^(@>", "~~v(@>"]),
]
MIRROR = str.maketrans("<>()[]{}/\\", "><)(][}{\\/")
TITLES = [(1, "Wandering Prompter"), (5, "Apprentice"), (10, "Journeyman"), (15, "Adept"),
          (20, "Veteran"), (30, "Master"), (40, "Grandmaster"), (50, "Archmage"), (75, "Mythic"),
          (100, "Ascended")]
CLASS_ICONS = {"shell": "🧙", "edit": "🔨", "read": "📜", "agent": "🔮", "web": "🏹"}
EVENT_TONE = {"levelup": "gold", "victory": "gold", "boss": "red", "hit": "red", "quest": "green",
              "achievement": "purple", "loot": "cyan", "chest": "gold", "eat": "pink", "strut": "pink",
              "use": "purple", "escape": "muted"}


def load_state(ctx):
    """The save as a dict, or None."""
    def read():
        from ..quest import state_path
        try:
            with open(state_path(), "rb") as fh:
                raw = fh.read()
            from ..fastjson import loads
            data = loads(raw)
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None
    return ctx.memo("quest-state", read)


def _level(xp):
    import math
    return int(math.sqrt(max(0, xp) / 50)) + 1


def view_of(state):
    """The game's snapshot, or one derived from a save too old to carry it."""
    view = state.get("view")
    if isinstance(view, dict) and "level" in view:
        return view
    xp = num(state.get("xp"), 0)
    lvl = _level(xp)
    lo, hi = 50 * (lvl - 1) ** 2, 50 * lvl ** 2
    school = state.get("school") or {}
    return {"level": lvl, "title": [t for need, t in TITLES if lvl >= need][-1],
            "xp_in": xp - lo, "xp_need": hi - lo,
            "class_icon": CLASS_ICONS.get(max(school, key=school.get), "") if school else "",
            "gold": num(state.get("gold"), 0), "bag": len(state.get("bag") or []),
            "stage": [s for s in STAGES if lvl >= s[0]][-1][1], "gear_sig": "", "buffs": [],
            "boss": None, "daily_done": 0, "daily_total": 0, "streak": 0}


class QuestSegment(Segment):
    quest = True

    def view(self, ctx):
        state = load_state(ctx)
        return (state, view_of(state)) if state else (None, None)


@register
class Hero(QuestSegment):
    name = "quest"
    doc = "Your Claude Quest hero: level, title, class, and progress to the next level."
    priority = 42
    tone = "gold"
    format = ("<gold><bold>Lv {level}</bold></gold>[ <purple>{title}</purple>][ {class_icon}]"
              "[ {bar}][ <muted>{xp}/{need}</muted>]")
    options = {
        "width": Opt(int, 10, "XP bar cells; 0 hides the bar."),
        "fill": Opt(str, "cyan,purple", "XP bar fill: colour roles blended along it, or level/gradient."),
        "style": Opt(str, "", "Bar style; empty means [bar].style."),
    }
    fields_doc = {"level": "hero level", "title": "your title (or rank)", "rank": "rank for the level",
                  "class_icon": "your class's emoji", "class": "your class", "bar": "XP progress bar",
                  "xp": "XP into this level", "need": "XP this level takes", "pct": "percent to next level",
                  "gold": "gold carried", "bag": "items carried"}

    def fields(self, ctx, opts, level):
        state, v = self.view(ctx)
        if not v:
            return None
        need = max(1, num(v.get("xp_need"), 1))
        into = max(0, num(v.get("xp_in"), 0))
        pct = min(100.0, 100.0 * into / need)
        width = opts["width"] if level < NARROW else max(4, opts["width"] // 2)
        bar = ctx.bar(pct, width if level < TEXT else 0, opts["style"], opts["fill"], tone="gold") \
            if opts["width"] > 0 else ""
        return {"level": str(v.get("level", 1)), "title": str(v.get("title") or "") if level < LEAN else "",
                "rank": str(v.get("rank") or ""), "class_icon": str(v.get("class_icon") or ""),
                "class": str(v.get("class") or ""), "bar": bar,
                "xp": f"{int(into):,}" if level < LESS else "", "need": f"{int(need):,}",
                "pct": f"{pct:.0f}", "gold": f"{int(num(v.get('gold'), 0)):,}", "bag": str(v.get("bag") or 0)}


@register
class Gold(QuestSegment):
    name = "quest_gold"
    doc = "Claude Quest gold, and the items in your bag."
    priority = 30
    tone = "gold"
    format = "<gold><bold>{gold}</bold></gold>[<muted> · {bag} items</muted>]"
    fields_doc = {"gold": "gold carried", "bag": "items in the bag"}

    def fields(self, ctx, opts, level):
        _, v = self.view(ctx)
        if not v:
            return None
        bag = int(num(v.get("bag"), 0))
        return {"gold": f"{int(num(v.get('gold'), 0)):,}", "bag": str(bag) if bag and level < LEAN else ""}


@register
class Boss(QuestSegment):
    name = "quest_boss"
    doc = "The boss you are fighting: a failing test, build or lint run, with its HP as hearts."
    priority = 60
    tone = "red"
    format = "[<red><bold>{name}</bold></red> ]{hearts}"
    fields_doc = {"name": "the boss's name (dropped when narrow)", "hearts": "HP as hearts, or hp/max",
                  "hp": "HP left", "max_hp": "full HP", "emoji": "the boss's emoji",
                  "project": "where it lurks"}

    def fields(self, ctx, opts, level):
        _, v = self.view(ctx)
        b = (v or {}).get("boss")
        if not b:
            return None
        hp, top = int(num(b.get("hp"), 0)), int(num(b.get("max_hp"), 0))
        red, dim = ctx.color("red"), ctx.color("subtle")
        heart, empty = ctx.mark("heart"), ctx.mark("heart_empty")
        if top <= 8:
            hearts = Text().add(heart * hp, (red, None, 0, None)).add(empty * max(0, top - hp), (dim, None, 0, None))
        else:
            hearts = Text().add(heart, (red, None, 0, None)).add(f" {hp}/{top}", (ctx.color("subtext"), None, 0, None))
        return {"name": str(b.get("name") or "") if level < LEAN else "", "hearts": hearts,
                "hp": str(hp), "max_hp": str(top), "emoji": str(b.get("icon") or ""),
                "project": str(b.get("project") or "")}


@register
class Daily(QuestSegment):
    name = "quest_daily"
    doc = "Today's quests done out of three, and the weekly quest's progress."
    priority = 36
    tone = "green"
    format = "<questc><bold>{done}/{total}</bold></questc>[<muted> · week {weekly}</muted>]"
    options = {"weekly": Opt(bool, True, "Show the weekly quest's progress too.")}
    fields_doc = {"done": "quests done today", "total": "quests today", "weekly": "weekly progress, n/goal"}
    colors_doc = {"questc": "green once all are done, subtext before"}

    def fields(self, ctx, opts, level):
        _, v = self.view(ctx)
        if not v:
            return None
        total = int(num(v.get("daily_total"), 0))
        if not total:
            return None
        done = int(num(v.get("daily_done"), 0))
        weekly = ""
        wk = [w for w in (v.get("weekly") or []) if isinstance(w, dict)]
        if opts["weekly"] and wk and level < LEAN and not wk[0].get("done"):
            weekly = f"{wk[0].get('progress', 0)}/{wk[0].get('goal', 0)}"
        return {"done": str(done), "total": str(total), "weekly": weekly, "_all": done >= total}

    def colors(self, ctx, opts, f):
        return {"questc": "green" if f["_all"] else "subtext"}

    def tone_at(self, ctx, opts, f):
        return "green" if f["_all"] else "yellow"


@register
class Buffs(QuestSegment):
    name = "quest_buffs"
    doc = "Buffs in effect, each with the minutes it has left."
    priority = 44
    tone = "purple"
    format = "{buffs}"
    fields_doc = {"buffs": "icon and minutes left for each buff"}

    def fields(self, ctx, opts, level):
        _, v = self.view(ctx)
        if not v:
            return None
        live = [b for b in v.get("buffs") or [] if isinstance(b, dict) and num(b.get("until"), 0) > ctx.now]
        if not live:
            return None
        parts = []
        for b in live:
            mins = max(1, round((num(b["until"], 0) - ctx.now) / 60))
            parts.append(str(b.get("icon", "✨")) + (f"{mins}m" if level < NARROW else ""))
        return {"buffs": " ".join(parts)}


@register
class Streak(QuestSegment):
    name = "quest_streak"
    doc = "Days in a row you have played (from two days on)."
    priority = 26
    tone = "orange"
    format = "<orange><bold>{streak}</bold></orange><muted>d</muted>"
    fields_doc = {"streak": "days in a row"}

    def fields(self, ctx, opts, level):
        _, v = self.view(ctx)
        n = int(num((v or {}).get("streak"), 0))
        return {"streak": str(n)} if n >= 2 else None


@register
class Event(QuestSegment):
    name = "quest_event"
    doc = "The latest thing that happened (loot, a level-up, a quest done), for a little while."
    priority = 50
    tone = "gold"
    format = "<eventc>{text}</eventc>"
    options = {"max": Opt(int, 48, "Longest text shown; longer ends in …")}
    fields_doc = {"text": "what happened", "kind": "levelup, loot, quest, victory, boss, achievement…"}
    colors_doc = {"eventc": "by kind: gold level-ups and victories, cyan loot, green quests, red bosses"}

    def fields(self, ctx, opts, level):
        state, _ = self.view(ctx)
        ev = (state or {}).get("last_event")
        if not isinstance(ev, dict):
            return None
        keep = float(ctx.quest_cfg.get("event_seconds", 30.0))
        if ctx.now - num(ev.get("at"), 0) > keep:
            return None
        text = " ".join(str(ev.get("text") or "").split())
        if not text:
            return None
        cap = opts["max"] if level < LEAN else max(16, opts["max"] // 2)
        return {"text": clip(text, cap), "kind": str(ev.get("kind") or "")}

    def colors(self, ctx, opts, f):
        return {"eventc": EVENT_TONE.get(f["kind"], "text")}

    def tone_at(self, ctx, opts, f):
        return EVENT_TONE.get(f["kind"])


def _mood(state, now, excited_s, sleepy_s):
    event = state.get("last_event") or {}
    if now - num(event.get("at"), 0) < excited_s:
        return "excited"
    if now - num(state.get("last_tool"), 0) < 15:
        return "working"
    if now - num(state.get("last_activity"), 0) > sleepy_s:
        return "sleepy"
    return "idle"


@register
class Pet(QuestSegment):
    name = "quest_pet"
    doc = ("Your companion as a little text sprite strolling across a yard. It evolves with your level, "
           "hurries while tools run, cheers at loot and level-ups, and dozes when you step away. "
           "Hidden while the kitty picture of it is on screen.")
    priority = 24
    tone = "green"
    format = "<petc>{yard}</petc>"
    options = {
        "yard": Opt(int, 24, "Columns the pet roams; halves when the line is narrow."),
        "excited": Opt(float, 20.0, "Seconds the pet celebrates after an event."),
        "sleepy": Opt(float, 600.0, "Idle seconds before it falls asleep."),
    }
    fields_doc = {"yard": "the pet at its spot in the yard", "sprite": "the pet alone",
                  "mood": "excited, working, idle or sleepy", "stage": "egg … wyrm"}
    colors_doc = {"petc": "green; gold while excited, muted asleep"}

    def fields(self, ctx, opts, level):
        if getattr(ctx, "avatar_active", False):
            return None
        state, v = self.view(ctx)
        if not v:
            return None
        lvl = int(num(v.get("level"), 1))
        _, stage, frames = [s for s in STAGES if lvl >= s[0]][-1]
        now = ctx.now
        mood = _mood(state, now, opts["excited"], opts["sleepy"])
        tick = int(now)
        yard = max(0, int(opts["yard"]))
        if level >= NARROW:
            yard //= 2
        if level >= TEXT:
            yard = 0
        sprite = frames[tick % len(frames)]
        room = max(0, yard - len(sprite))
        speed = {"working": 2, "excited": 0, "idle": 1, "sleepy": 0}[mood]
        span = 2 * room or 1
        step = (tick * speed) % span if speed else room // 2
        pos, facing_left = (step, False) if step <= room else (span - step, True)
        if mood == "excited":
            sprite = ("\\" + frames[0] + "/") if tick % 2 else ("*" + frames[0] + "*")
            pos = max(0, pos - 1)
        elif mood == "sleepy":
            sprite = frames[0].replace("o", "-").replace("O", "-").replace("@", "-")
        if facing_left:
            sprite = sprite[::-1].translate(MIRROR)
        if mood == "sleepy":
            sprite += " " + "zZz"[:1 + tick % 3]
        pos = min(pos, max(0, yard - len(sprite)))
        yard_text = (" " * pos + sprite).ljust(yard) if yard else sprite
        return {"yard": yard_text, "sprite": sprite, "mood": mood, "stage": stage}

    def colors(self, ctx, opts, f):
        return {"petc": {"excited": "gold", "sleepy": "muted"}.get(f["mood"], "green")}


@register
class PetV2(Pet):
    name = "pet"
    doc = "The text pet under its earlier name; same as quest_pet."


# ---- the kitty picture of the pet --------------------------------------------
#
# The pet is drawn by kitty's Unicode placeholders: the bar prints ordinary
# text cells whose foreground colour names an image kitty already holds.
# Each of the pet's actions is uploaded once as its own looping animation, so
# switching action is just a different colour, and nothing but text ever
# goes through Claude Code.

DIACRITICS = [chr(c) for c in (
    0x0305, 0x030D, 0x030E, 0x0310, 0x0312, 0x033D, 0x033E, 0x033F, 0x0346, 0x034A,
    0x034B, 0x034C, 0x0350, 0x0351, 0x0352, 0x0357, 0x035B, 0x0363, 0x0364, 0x0365)]
PLACEHOLDER = "\U0010EEEE"
IMAGE_BASE = 200
ACTIONS = ["stand", "walk", "look", "lookaround", "hop", "sleep", "work", "perk", "yourturn",
           "levelup", "achievement", "loot", "battle", "victory", "quest", "eat", "strut"]
IDLE_WEIGHTS = [("stand", 5), ("look", 3), ("lookaround", 2), ("walk", 2),
                ("hop", 1), ("sleep", 1), ("strut", 1)]
REACTIONS = {"levelup": "levelup", "achievement": "achievement", "loot": "loot", "chest": "loot",
             "quest": "quest", "victory": "victory", "boss": "battle", "hit": "battle",
             "eat": "eat", "strut": "strut", "use": "strut", "escape": "lookaround"}
TIMING = {"react": 8.0, "your_turn": 90.0, "idle_every": 8.0, "sleepy": 600.0, "refresh": 1800.0}


def _runtime(name):
    from ..config import runtime_dir
    return os.path.join(runtime_dir(), name)


def kitty_terminals(ctx):
    """{pty: pid} for every claude process drawing in a kitty window.

    A session hosted by the Claude Code daemon is only relayed to the kitty
    window that shows it, so its own pty is the wrong place for images.
    Kitty keeps images per window and the placeholder cells are plain text
    that survives any relay, so the frames go to every kitty window running
    claude. The /proc scan is cached for a few seconds.
    """
    def scan():
        import time
        import marshal
        cache = _runtime("kitty-terminals.bin")
        try:
            with open(cache, "rb") as fh:
                blob = marshal.load(fh)
            if time.time() - blob["at"] < 15:
                return blob["terminals"]
        except Exception:
            pass
        found = {}
        if not os.path.isdir("/proc"):
            return found
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open(f"/proc/{entry}/cmdline", "rb") as fh:
                    argv0 = os.path.basename(fh.read().split(b"\0", 1)[0].decode(errors="ignore"))
                if argv0 != "claude" and not argv0[:1].isdigit():
                    continue
                tty = os.readlink(f"/proc/{entry}/fd/1")
                if not tty.startswith("/dev/pts/"):
                    continue
                with open(f"/proc/{entry}/environ", "rb") as fh:
                    if b"KITTY_WINDOW_ID=" not in fh.read():
                        continue
                found.setdefault(tty, int(entry))
            except (OSError, ValueError):
                continue
        try:
            tmp = f"{cache}.{os.getpid()}"
            with open(tmp, "wb") as fh:
                marshal.dump({"at": time.time(), "terminals": found}, fh)
            os.replace(tmp, cache)
        except OSError:
            pass
        return found
    return ctx.memo("kitty-terminals", scan)


def _art_version():
    """Changes whenever the drawing code changes, so the frames are re-sent."""
    folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "quest", "art")
    try:
        return int(max(os.stat(os.path.join(folder, f)).st_mtime
                       for f in ("avatar.py", "sprites.py", "gear.py")))
    except (OSError, ValueError):
        return None


def _ensure_uploaded(ctx, look, terminals, cols, rows):
    """Start the uploader for each kitty window lacking frames for this look."""
    import time
    version = _art_version()
    if version is None:
        return False
    key = f"{look}:{cols}x{rows}:{IMAGE_BASE}:{version}"
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for tty, pid in terminals.items():
        stamp_file = _runtime(f"avatar-{pid}")
        try:
            with open(stamp_file) as fh:
                old_key, stamp = fh.read().rsplit("|", 1)
            if old_key == key and time.time() - float(stamp) < TIMING["refresh"]:
                continue
        except (OSError, ValueError):
            pass
        try:
            with open(stamp_file, "w") as fh:
                fh.write(f"{key}|{time.time()}")
        except OSError:
            continue
        import shutil
        python = shutil.which("python3") or "python3"
        code = ("import sys; sys.path.insert(0, sys.argv[1]); "
                "from claude_statusline.quest.art.avatar import main; sys.exit(main(sys.argv[2:]))")
        from ..gitstatus import spawn_detached
        spawn_detached([python, "-c", code, root, "--tty", tty, "--base", str(IMAGE_BASE),
                        "--cols", str(cols), "--rows", str(rows)])
    return True


def _event_kind(event):
    kind = event.get("kind")
    if kind:
        return kind
    text = str(event.get("text", ""))
    if text.startswith("⬆"):
        return "levelup"
    return "loot" if "Loot" in text else "achievement"


def pick_action(state, now, known=ACTIONS, timing=TIMING):
    """What the pet is doing right now: reactions first, then an idle rotation."""
    event = state.get("last_event") or {}

    def since(key):
        return now - num(state.get(key), 0)
    boss = (state.get("view") or {}).get("boss") or state.get("boss")
    if now - num(event.get("at"), 0) < timing["react"]:
        act = REACTIONS.get(_event_kind(event))
        if act in known:
            return act
    if since("last_prompt") < 4:
        return "perk"
    if since("last_tool") < 12:
        return "battle" if boss and "battle" in known else "work"
    if since("last_activity") > timing["sleepy"]:
        return "sleep"
    last_stop = num(state.get("last_stop"), 0)
    if (last_stop > max(num(state.get("last_prompt"), 0), num(state.get("last_tool"), 0))
            and now - last_stop < timing["your_turn"]):
        return "yourturn"
    weights = [(a, w) for a, w in IDLE_WEIGHTS if a in known]
    if boss and "battle" in known:
        weights.append(("battle", 4))
    if not weights:
        return known[0] if known else "stand"
    pick = _unit(int(now // timing["idle_every"])) * sum(w for _, w in weights)
    for act, w in weights:
        pick -= w
        if pick < 0:
            return act
    return weights[-1][0]


def _unit(n: int) -> float:
    """A well-mixed number in [0, 1) from an integer (murmur3's finaliser);
    `random` would cost more to import than the whole refresh."""
    x = (n * 0x9E3779B1) & 0xFFFFFFFF
    x ^= x >> 16
    x = (x * 0x85EBCA6B) & 0xFFFFFFFF
    x ^= x >> 13
    x = (x * 0xC2B2AE35) & 0xFFFFFFFF
    x ^= x >> 16
    return x / 4294967296.0


def _manifest_actions():
    path = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
                        "claude-statusline", "avatar", "manifest.json")
    try:
        from ..fastjson import loads
        with open(path, "rb") as fh:
            data = loads(fh.read())
        if isinstance(data.get("actions"), list):
            return data["actions"]
    except (OSError, ValueError, AttributeError):
        pass
    return ACTIONS


def placeholder_row(row: int, cols: int, image_id: int) -> Text:
    """One row of placeholder cells. Only the first names its row and column;
    kitty infers the rest, and hosts that count combining marks see less."""
    cells = PLACEHOLDER + DIACRITICS[row] + DIACRITICS[0] + PLACEHOLDER * (cols - 1)
    return Text([(cells, ((0, 0, 0, image_id), None, 0, None))])


def avatar_pins(ctx, n_lines):
    """Placeholder rows for the first lines, or None when there is no picture to show."""
    cfg = ctx.quest_cfg
    if ctx.mode not in ("truecolor", "256") or n_lines <= 0:
        return None
    if cfg.get("avatar") in ("off", False):
        return None
    terminals = kitty_terminals(ctx)
    if not terminals:
        return None
    state = load_state(ctx)
    if not state:
        return None
    rows = min(3, n_lines, len(DIACRITICS))
    cols = max(2, min(int(cfg.get("avatar_cols", 8)), len(DIACRITICS)))
    v = view_of(state)
    if not _ensure_uploaded(ctx, f"{v.get('stage')}:{v.get('gear_sig', '')}", terminals, cols, rows):
        return None
    known = _manifest_actions()
    action = pick_action(state, ctx.now, known)
    image_id = IMAGE_BASE + (known.index(action) if action in known else 0)
    return [placeholder_row(r, cols, image_id) if r < rows else None for r in range(n_lines)]


@register
class Avatar(QuestSegment):
    name = "avatar"
    doc = ("One row of the kitty picture of your pet, for placing it by hand ([quest] placement = "
           "\"manual\"). With the default placement the picture is placed for you at the right edge.")
    priority = 100
    tone = "text"
    bare = True
    format = "{cells}"
    options = {"row": Opt(int, 0, "Which row of the picture this instance draws."),
               "rows": Opt(int, 3, "Rows the picture spans."),
               "cols": Opt(int, 8, "Columns the picture spans.")}
    fields_doc = {"cells": "the placeholder cells for this row", "action": "what the pet is doing"}

    def fields(self, ctx, opts, level):
        if ctx.mode not in ("truecolor", "256") or not ctx.live:
            return None
        terminals = kitty_terminals(ctx)
        state = load_state(ctx)
        if not terminals or not state:
            return None
        row, cols, rows = int(opts["row"]), int(opts["cols"]), int(opts["rows"])
        if not (0 <= row < min(rows, len(DIACRITICS))) or not 2 <= cols <= len(DIACRITICS):
            return None
        v = view_of(state)
        if not _ensure_uploaded(ctx, f"{v.get('stage')}:{v.get('gear_sig', '')}", terminals, cols, rows):
            return None
        known = _manifest_actions()
        action = pick_action(state, ctx.now, known)
        return {"cells": placeholder_row(row, cols, IMAGE_BASE + (known.index(action) if action in known else 0)),
                "action": action}
