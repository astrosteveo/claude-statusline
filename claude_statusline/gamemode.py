"""Game mode: the bar as a game. `[quest] placement = "game"`.

The top line is the quest ticker (hero, boss, raid, dungeon, quests, news).
Below it, the scene fills the width: in kitty, one animated picture per
situation (see quest/art/scene.py), switched by colour like the avatar;
elsewhere, a little text world that moves with each refresh. Beside each
row of scene sits one gauge from `game_hud` (context, 5h, 7d by default),
right-aligned in `game_hud_width` columns.
"""
from __future__ import annotations

import os
import time

from .text import Text
from .util import num

SITUATIONS = ["idle", "work", "battle", "celebrate", "sleep", "yourturn"]
# Kitty image ids: each distinct scene gets a slot of its own, ids SCENE_BASE + 6 * slot + situation,
# so sessions sharing a window (a background agent in another project, say) never overwrite each
# other's picture; overwriting it on every refresh is what made the scene flicker. The ids stay
# under 200 (the avatar's) and within 8 bits, which a 256-colour placeholder can name.
SCENE_BASE = 100
SLOTS = 16
CELEBRATE = {"levelup", "achievement", "loot", "chest", "quest", "victory", "eat", "strut", "use", "dungeon",
             "compact", "season"}
PARTY_MAX = 3
PARTY_LOOK = [("o>", "blue"), ("ô>", "pink"), ("ö>", "teal")]     # the companions in the text world
FIGHT = {"boss", "hit", "raid"}
STEP = 10                        # the picture's width snaps to this many columns, so resizing rarely re-draws it


def time_of_day(now):
    hour = time.localtime(now).tm_hour
    return "dawn" if 5 <= hour < 8 else "day" if 8 <= hour < 18 else "dusk" if 18 <= hour < 21 else "night"


def party_of(view, cfg=None):
    """How many companions walk with the pet (at most PARTY_MAX; none with `party` off)."""
    if cfg is not None and cfg.get("party") is False:
        return 0
    party = view.get("party")
    return min(PARTY_MAX, len(party)) if isinstance(party, list) else 0


def extras(view, now):
    """(season or None, is a treasure goblin about?) from the game's snapshot."""
    season = view.get("season")
    return (season if isinstance(season, str) else None), num(view.get("goblin"), 0) > now


def props(view, project):
    """(boss kind or None, raid here?, dungeon here?) from the game's snapshot."""
    b = view.get("boss")
    boss = str(b.get("kind") or "test") if isinstance(b, dict) else None
    raids = view.get("raids") if isinstance(view.get("raids"), dict) else {}
    r = raids.get(project)
    raid = isinstance(r, dict) and not r.get("defeated")
    dungeon = any(isinstance(d, dict) and d.get("project") == project for d in view.get("dungeons") or [])
    return boss, bool(raid), dungeon


def situation(state, now, foe, react=8.0, sleepy=600.0, your_turn=90.0):
    """What the scene shows right now."""
    event = state.get("last_event") or {}

    def since(key):
        return now - num(state.get(key), 0)
    if now - num(event.get("at"), 0) < react:
        kind = event.get("kind")
        if kind in CELEBRATE:
            return "celebrate"
        if kind in FIGHT and foe:
            return "battle"
    if since("last_tool") < 12 or since("last_prompt") < 4:
        return "battle" if foe else "work"
    if since("last_activity") > sleepy:
        return "sleep"
    last_stop = num(state.get("last_stop"), 0)
    if last_stop > max(num(state.get("last_prompt"), 0), num(state.get("last_tool"), 0)) and \
            now - last_stop < your_turn:
        return "yourturn"
    return "idle"


# ---- kitty ------------------------------------------------------------------------------

def _ancestors(depth=3):
    """Our parent and its parents: the claude drawing this bar is among them, so its
    window alone gets the picture (other sessions may be another width)."""
    out, pid = set(), os.getppid()
    for _ in range(depth):
        out.add(pid)
        try:
            with open(f"/proc/{pid}/stat") as fh:
                pid = int(fh.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return out


def slot_of(key):
    """A stable slot for a scene key (FNV-1a: `hashlib` costs too much to import here)."""
    h = 0x811C9DC5
    for b in key.encode():
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h % SLOTS


def _ensure_scene(ctx, terminals, cols, rows, look, args):
    """Start the scene uploader for each kitty window lacking this scene. Returns (image base,
    columns) of the picture this window can show now: this scene once its upload is complete,
    the last complete one while it is not, or None when there is none yet."""
    from .segments.quest import TIMING, _runtime
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quest", "art")
    try:            # changes whenever the drawing code does, so the scene is re-sent
        version = int(max(os.stat(os.path.join(folder, f)).st_mtime
                          for f in ("scene.py", "avatar.py", "sprites.py", "gear.py")))
    except (OSError, ValueError):
        return None
    key = f"{look}:{cols}x{rows}:{version}"
    slot = slot_of(key)
    base = SCENE_BASE + len(SITUATIONS) * slot
    mine = {tty: pid for tty, pid in terminals.items() if pid in _ancestors()}
    targets = mine or terminals
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for tty, pid in targets.items():
        stamp_file = _runtime(f"scene-{pid}-{slot}")
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
                "from claude_statusline.quest.art.scene import main; sys.exit(main(sys.argv[2:]))")
        from .gitstatus import spawn_detached
        spawn_detached([python, "-c", code, root, "--tty", tty, "--base", str(base),
                        "--cols", str(cols), "--rows", str(rows), "--ready", _runtime(f"scene-ready-{pid}-{slot}"),
                        "--key", key] + args)
    pid = next(iter(targets.values()))
    shown = _runtime(f"scene-shown-{pid}")
    try:
        with open(_runtime(f"scene-ready-{pid}-{slot}")) as fh:
            ready = fh.read() == key
    except OSError:
        ready = False
    if ready:
        try:
            with open(shown) as fh:
                same = fh.read() == f"{base}|{cols}|{rows}"
        except OSError:
            same = False
        if not same:
            try:
                with open(shown, "w") as fh:
                    fh.write(f"{base}|{cols}|{rows}")
            except OSError:
                pass
        return base, cols
    try:                        # kitty is still receiving this scene: keep showing the last one it has,
        with open(shown) as fh:  # unless it lives in the slot being overwritten right now
            old_base, old_cols, old_rows = (int(x) for x in fh.read().split("|"))
        if old_rows == rows and old_base != base:
            return old_base, old_cols
    except (OSError, ValueError):
        pass
    return None


def kitty_rows(ctx, state, view, width, rows, sit, boss, raid, dungeon):
    """Placeholder rows for the picture, or None when kitty can't show it."""
    from .segments.quest import DIACRITICS, kitty_terminals, placeholder_row
    if not ctx.live or ctx.mode not in ("truecolor", "256") or rows > len(DIACRITICS):
        return None
    terminals = kitty_terminals(ctx)
    if not terminals:
        return None
    cols = max(STEP, width // STEP * STEP)
    tod = time_of_day(ctx.now)
    party = party_of(view, ctx.quest_cfg)
    season, goblin = extras(view, ctx.now)
    look = (f"{view.get('stage')}:{view.get('gear_sig', '')}:{boss or '-'}:{int(raid)}:{int(dungeon)}:{tod}:"
            f"{party}:{season or '-'}:{int(goblin)}")
    args = ["--tod", tod, "--party", str(party)] + (["--boss", boss] if boss else []) + \
        (["--raid"] if raid else []) + (["--dungeon"] if dungeon else []) + \
        (["--season", season] if season else []) + (["--goblin"] if goblin else [])
    got = _ensure_scene(ctx, terminals, cols, rows, look, args)
    if not got:
        return None
    base, cols = got
    if cols > width:
        return None
    image = base + SITUATIONS.index(sit)
    pad = " " * (width - cols)
    return [Text(placeholder_row(r, cols, image).spans + ([(pad, (None, None, 0, None))] if pad else []))
            for r in range(rows)]


# ---- text -------------------------------------------------------------------------------

def _put(grid, row, col, text, role):
    if 0 <= row < len(grid):
        for i, ch in enumerate(text):
            if 0 <= col + i < len(grid[row]):
                grid[row][col + i] = (ch, role)


def text_rows(ctx, state, view, width, rows, sit, boss, raid, dungeon):
    """A small world drawn in characters: sky, ground, the pet and whatever it faces."""
    from .segments.quest import MIRROR, STAGES
    now = ctx.now
    tick = int(now)
    tod = time_of_day(now)
    night = tod in ("night", "dusk")
    grid = [[(" ", "muted") for _ in range(width)] for _ in range(rows)]
    ground = rows - 1
    for c in range(width):                                        # the ground, with a little grass
        grid[ground][c] = ("▁" if (c * 7) % 11 else "‿", "green")
    if rows >= 2:
        for c in range(0, width, 1):                              # stars, or a drifting cloud
            if night and (c * 37 + 11) % 23 == 0:
                _put(grid, 0, c, "·" if (c + tick // 3) % 5 else "*", "subtext")
        _put(grid, 0, 2, "◯" if not night else "◔", "gold" if not night else "text")
        if not night:
            cloud = (tick // 2) % (width + 6) - 6
            _put(grid, 0, cloud, "≈≈≈", "subtext")
    season, goblin = extras(view, now)
    if season == "halloween":                                     # pumpkins on the ground, bats in the sky
        for c in range(9, width - 8, 23):
            _put(grid, ground, c, "●", "orange")
        if rows >= 2:
            for i, c in enumerate(range(width // 5, width, max(12, width // 4))):
                _put(grid, 0, (c + tick * (1 + i % 2)) % max(1, width - 3), "^v^" if (tick + i) % 2 else "v^v", "purple")
    if goblin and width > 20:                                     # the treasure goblin, scurrying past
        c = width - 12 - (tick * 3) % max(1, width // 2)
        _put(grid, ground, c, "g$", "gold")
    if dungeon and width > 30:
        c = int(width * 0.62)
        if rows >= 2:
            _put(grid, ground - 1, c, "▟Π▙", "purple")
        _put(grid, ground, c, "█∩█", "purple")
    if raid:
        c = width - 7
        wave = "≋≈" if tick % 2 else "≈≋"
        _put(grid, ground, c, wave * 3 + "≈", "blue")
        if rows >= 2:
            _put(grid, ground - 1, c + 1, "Ψ ψ Ψ" if tick % 2 else "ψ Ψ ψ", "purple")
    if boss:
        c = int(width * 0.78)
        foe = {"test": "∫§∫", "build": "[▓]", "lint": "}Ω{"}.get(boss, "[▓]")
        _put(grid, ground, c, foe, "red")

    lvl = int(num(view.get("level"), 1))
    _, _, frames = [s for s in STAGES if lvl >= s[0]][-1]
    sprite = frames[tick % len(frames)]
    lo, hi = 4, max(6, int(width * (0.5 if (boss or raid) else 0.58)))
    span = max(1, hi - lo - len(sprite))
    if sit in ("idle", "work"):
        speed = 2 if sit == "work" else 1
        step = (tick * speed) % (2 * span)
        pos, left = (step, False) if step < span else (2 * span - step, True)
        col = lo + pos
        if left:
            sprite = sprite[::-1].translate(MIRROR)
        if sit == "work" and col > 1:
            _put(grid, ground, col - 1 if not left else col + len(sprite), "∙", "muted")
    elif sit == "battle":
        col = (int(width * 0.78) if boss else width - 7) - len(sprite) - (1 + tick % 2)
        if tick % 2 and rows >= 2:
            _put(grid, ground - 1, col + len(sprite), "*", "gold")
    elif sit == "celebrate":
        col = int(width * 0.3)
        sprite = ("\\" + frames[0] + "/") if tick % 2 else ("*" + frames[0] + "*")
        for i in range(6):
            _put(grid, max(0, ground - 1 - (i + tick) % max(1, rows - 1)), col - 4 + (i * 5 + tick) % 14,
                 "*·°"[i % 3], ["gold", "pink", "cyan"][i % 3])
    elif sit == "sleep":
        col = int(width * 0.24)
        sprite = frames[0].replace("o", "-").replace("O", "-").replace("@", "-")
        if rows >= 2:
            _put(grid, ground - 1, col + len(sprite), "zZz"[:1 + tick % 3], "muted")
    else:                                                        # yourturn
        col = int(width * 0.24)
        if rows >= 2 and tick % 4 < 2:
            _put(grid, ground - 1, col + len(sprite), "?", "text")
    _put(grid, ground, col, sprite, "gold" if sit == "celebrate" else "green")
    behind = sit in ("idle", "work") and left
    for i in range(party_of(view, ctx.quest_cfg)):                              # the party trails the pet
        mate, role = PARTY_LOOK[i]
        if behind:
            c = col + len(sprite) + 1 + 3 * i
            mate = mate[::-1].translate(MIRROR)
        else:
            c = col - 3 * (i + 1)
        row = ground - 1 if (sit == "celebrate" and (tick + i) % 2 and rows >= 2) else ground
        if sit == "sleep":
            mate = mate.replace("o", "-").replace("ô", "-").replace("ö", "-")
        _put(grid, row, c, mate, role)

    out = []
    for row in grid:
        t = Text()
        run, role = "", None
        for ch, r in row:
            if r != role and run:
                t.add(run, (ctx.color(role), None, 0, None))
                run = ""
            run, role = run + ch, r
        if run:
            t.add(run, (ctx.color(role), None, 0, None))
        out.append(t)
    return out


def scene_rows(ctx, width, rows):
    """The scene, `rows` Texts each `width` cells wide."""
    from .segments.quest import load_state, view_of
    state = load_state(ctx) or {}
    view = view_of(state) if state else {"level": 1}
    project = ctx.cwd.rstrip("/").rsplit("/", 1)[-1] or "?"
    boss, raid, dungeon = props(view, project)
    sit = situation(state, ctx.now, boss or raid)
    out = None
    if ctx.quest_cfg.get("avatar") not in ("off", False) and state:
        try:
            out = kitty_rows(ctx, state, view, width, rows, sit, boss, raid, dungeon)
        except Exception:
            if os.environ.get("CLAUDE_STATUSLINE_DEBUG"):
                raise
    return out or text_rows(ctx, state, view, width, rows, sit, boss, raid, dungeon)
