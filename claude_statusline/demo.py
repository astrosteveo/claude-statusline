"""A scripted session, played in your terminal: `statusline.py demo`.

The script is data. Each scene says, for any moment `t` into it, which config
the bar uses, what the payload holds (the model, git, costs, the live
activity, the Quest save), how wide the terminal is, the conversation above
the bar, and a caption. Everything on the bar comes from `render()`, as it
would in Claude Code. The trailer (tools/trailer) plays the same scenes into
video frames, so the two never drift apart.
"""
from __future__ import annotations

import os
import time

# 2026-10-30, 19:40 local time: the Hallowed Harvest, at dusk.
BASE = time.mktime((2026, 10, 30, 19, 40, 0, 0, 0, -1))
DAY = time.mktime((2026, 10, 30, 14, 0, 0, 0, 0, -1))
LOOK = {"theme": "midnight", "style": "capsules", "icons": "nerd"}


class Frame:
    """What one moment of the demo shows."""
    __slots__ = ("raw", "data", "cols", "talk", "caption", "now", "note")

    def __init__(self, raw, data, cols, talk, caption, now, note=""):
        self.raw, self.data, self.cols, self.talk, self.caption, self.now, self.note = \
            raw, data, cols, talk, caption, now, note


# --- the payload and the save --------------------------------------------------------------
def payload(now, **over):
    """A busy session on a current model, times relative to `now`."""
    data = {
        "session_id": "demo", "model": {"id": "claude-opus-5-5", "display_name": "Opus 5.5"},
        "effort": {"level": "high"}, "thinking": {"enabled": True}, "version": "2.1.283",
        "cwd": "/home/u/Projects/widget-factory", "_home": "/home/u",
        "workspace": {"current_dir": "/home/u/Projects/widget-factory", "project_dir": "/home/u/Projects/widget-factory",
                      "repo": {"host": "github.com", "owner": "octocat", "name": "widget-factory"}},
        "cost": {"total_cost_usd": 18.42, "total_duration_ms": 2_950_000, "total_api_duration_ms": 1_100_000,
                 "total_lines_added": 412, "total_lines_removed": 96},
        "context_window": {"used_percentage": 34, "total_input_tokens": 341_000, "context_window_size": 1_000_000},
        "prompt_cache": {"warm": True, "hit_ratio": 0.98, "ttl": "1h", "expires_at": now + 3000},
        "rate_limits": {"five_hour": {"used_percentage": 41, "resets_at": now + 2 * 3600 + 13 * 60},
                        "seven_day": {"used_percentage": 23, "resets_at": now + 4 * 86400}},
        "_git": {"branch": "fix/parser", "ahead": 1, "staged": 0, "dirty": 2, "untracked": 1,
                 "upstream": "origin/fix/parser"},
        "_spend": {"today": 42.8, "week": 188.1, "month": 402.5},
        "_commands": {"oncall-now --short": "\x1b[32m●\x1b[0m on call: priya"},
    }
    for k, v in over.items():
        data[k] = v
    return data


def save(now, **view):
    """A Claude Quest save as the bar reads it."""
    base = {"level": 38, "title": "Master", "rank": "Master", "xp_in": 3190, "xp_need": 3750,
            "class": "Shell Sorcerer", "class_icon": "🧙", "gold": 13096, "bag": 125, "stage": "drake",
            "form": "ember", "gear_sig": "demo", "buffs": [], "boss": None, "daily_done": 2, "daily_total": 3,
            "weekly": [{"title": "Proving Grounds", "progress": 19, "goal": 22, "done": False}],
            "streak": 12, "dungeons": [], "raids": {}, "party": [], "season": None, "goblin": None}
    state = {"xp": 70000, "last_activity": now - 5, "last_tool": now - 2, "last_prompt": now - 40}
    for k in ("last_event", "last_tool", "last_stop", "last_prompt", "last_activity"):
        if k in view:
            state[k] = view.pop(k)
    base.update(view)
    state["view"] = base
    return state


def event(now, text, kind, ago=1):
    return {"text": text, "kind": kind, "at": now - ago}


TALK = [
    ("you", "The parser test is flaky again. Find out why, fix it, and open a PR."),
    ("claude", "I'll read the parser and the failing test, then run the suite."),
    ("tool", "Read  src/parser.py"),
    ("tool", "Read  tests/test_parser.py"),
    ("tool", "Bash  pytest tests/test_parser.py -q"),
    ("out", "2 failed, 41 passed in 1.84s"),
    ("claude", "Both failures read the tokenizer's cache after another test has filled it. The cache"),
    ("claude", "outlives each test, so the order they run in decides the result."),
]


# --- the scenes ---------------------------------------------------------------------------------
class Scene:
    def __init__(self, name, seconds, build):
        self.name, self.seconds, self.build = name, seconds, build


def _session(t):
    now = DAY + t
    act = {"turn": -94, "tools": [["Bash", "pytest tests/test_parser.py -q", -3 - t, ""]],
           "recent": [["Read", "parser.py", -60, True, ""], ["Read", "lexer.py", -58, True, ""],
                      ["Edit", "parser.py", -20, True, ""]],
           "agents": [], "mode": "acceptEdits"}
    return Frame(dict(LOOK, preset="classic", activity={"enabled": True}),
                 payload(now, _activity=act), 200, TALK, "The bar under a Claude Code session.", now)


def _narrow(t):
    now = DAY + 30 + t
    cols = int(200 - (200 - 60) * min(1.0, t / 5.0))
    return Frame(dict(LOOK, preset="classic"), payload(now), cols, TALK,
                 "Narrow the window: detail goes first, and nothing clips.", now, f"{cols} columns")


LOOKS = [("midnight", "capsules"), ("catppuccin", "powerline"), ("tokyo-night", "pills"), ("gruvbox", "slant"),
         ("nord", "chips"), ("rose-pine", "classic"), ("dracula", "powerline"), ("claude", "capsules")]


def _looks(t):
    now = DAY + 60 + t
    theme, style = LOOKS[min(len(LOOKS) - 1, int(t / 1.0))]
    return Frame({"theme": theme, "style": style, "icons": "nerd", "preset": "classic"}, payload(now), 170, TALK,
                 "19 themes and 8 styles, all drawn from the same segments.", now, f"{theme} · {style}")


GAME = dict(LOOK, quest={"enabled": True, "placement": "game", "game_rows": 4},
            line=[{"left": ["model", "dir", "git", "pr", "cost", "spend"]},
                  {"left": ["context"], "right": ["limit_5h", "limit_7d"]}])


def _game(t):
    """The pet works, a failing test summons a boss, a fix wins, loot and a level-up."""
    now = BASE + t
    talk = list(TALK)
    if t < 4:
        q = save(now, last_tool=now - 1)
        cap = "Game mode: the bar becomes the game. The pet works while tools run."
    elif t < 9:
        q = save(now, last_tool=now - 1, last_event=event(now, "🐍 A wild Flaky Test Hydra appears in "
                                                            "widget-factory! 2 HP. Get the tests passing.", "boss",
                                                     ago=t - 4),
                 boss={"icon": "🐍", "name": "Flaky Test Hydra", "hp": 2, "max_hp": 2, "kind": "test",
                       "project": "widget-factory"})
        cap = "Failing tests summon a boss. Fix them to win."
    elif t < 13:
        q = save(now, last_tool=now - 1, last_event=event(now, "⚔️ You defeated the Flaky Test Hydra! +143 XP, "
                                                              "+34 gold", "victory", ago=t - 9))
        talk = talk + [("tool", "Edit  parser.py"), ("tool", "Bash  pytest tests/test_parser.py -q"),
                       ("out", "43 passed in 1.71s")]
        cap = "A clean run wins the fight."
    elif t < 17:
        q = save(now, level=39, xp_in=120, xp_need=3850, last_tool=now - 30,
                 last_event=event(now, "⬆️ LEVEL UP! You are now level 39, Master. (+780 gold)", "levelup",
                                  ago=t - 13))
        cap = "A level-up, and the pet celebrates."
    else:
        q = save(now, level=39, xp_in=460, xp_need=3850, last_tool=now - 1,
                 dungeons=[{"project": "widget-factory", "number": 214, "name": "Crypt of the Nitpick",
                            "rooms": 3, "traps": 0, "failing": 0}],
                 raids={"widget-factory": {"name": "Backlog Kraken", "hp": 9, "max_hp": 14, "defeated": False}},
                 last_event=event(now, "🏰 PR #214 opens the Crypt of the Nitpick in widget-factory.", "dungeon",
                                  ago=t - 17))
        talk = talk + [("tool", "Bash  gh pr create --fill"), ("out", "https://github.com/octocat/widget-factory/pull/214")]
        cap = "A pull request is a dungeon; TODOs rise as a tech-debt raid."
    data = payload(now, _quest=q, pr={"number": 214, "review_state": "pending"} if t >= 17 else None)
    if t < 17:
        data.pop("pr")
    return Frame(GAME, data, 200, talk, cap, now)


def _top_row(t):
    now = BASE + 40 + t
    q = save(now, last_tool=now - 60, last_stop=now - 20, last_prompt=now - 90)
    return Frame(GAME, payload(now, _quest=q), int(220 - 60 * max(0.0, (t - 3) / 3)), TALK,
                 "New in 4: your model, git and cost share the game's top row, and give way first.", now)


def _party(t):
    now = BASE + 60 + t
    party = [{"type": "Explore", "role": "scout"}, {"type": "Plan", "role": "strategist"},
             {"type": "general-purpose", "role": "adventurer"}][:1 + min(2, int(t / 1.5))]
    q = save(now, last_tool=now - 1, party=party,
             last_event=event(now, f"🧭 A{'n' if party[-1]['role'][0] in 'aeiou' else ''} {party[-1]['role']} joins your "
                                   f"party ({party[-1]['type']}). "
                                   f"{len(party)} at work.", "party", ago=0.5))
    act = {"turn": -150, "tools": [], "agents": [[m["type"], -40 + 8 * i, "", "Grep", ""] for i, m in enumerate(party)]}
    return Frame(GAME, payload(now, _quest=q, _activity=act), 200, TALK,
                 "Subagents join your party while they work.", now)


def _harvest(t):
    now = BASE + 90 + t
    boss = {"icon": "🐍", "name": "Headless Heisenbug", "hp": 3, "max_hp": 3, "kind": "test",
            "project": "widget-factory"}
    q = save(now, last_tool=now - 1, season="halloween", goblin=now + 400 if t > 2.5 else None, boss=boss,
             last_event=event(now, "💰 A treasure goblin scurries past! Commit in the next ten minutes to catch it.",
                              "goblin", ago=t - 2.5) if t > 2.5 else
             event(now, "🎃 The Hallowed Harvest has begun: haunted bosses and seasonal loot.", "season"))
    return Frame(GAME, payload(now, _quest=q), 200, TALK,
                 "Late October brings haunted bosses. A treasure goblin can turn up any day.", now)


def _live(t):
    now = DAY + 400 + t
    act = {"turn": -(130 + t), "tools": [["Bash", "npm run build", -12 - t, ""]],
           "recent": [["Edit", "App.tsx", -30, True, ""], ["Edit", "App.tsx", -25, True, ""],
                      ["Read", "routes.ts", -40, True, ""]],
           "agents": [["Explore", -70 - t, "Find every caller of parse()", "Grep", "parse("]],
           "mode": "acceptEdits"}
    raw = dict(LOOK, activity={"enabled": True},
               line=[{"left": ["model", "dir", "git", "cost", "spend", "oncall"]},
                     {"left": ["context"], "right": ["cache", "limit_5h", "limit_7d"]}],
               segment={"oncall": {"type": "command", "command": "oncall-now --short"}})
    data = payload(now, _activity=act)
    data["prompt_cache"] = {"warm": True, "hit_ratio": 0.98, "ttl": "5m", "expires_at": now + 125 - t}
    return Frame(raw, data, 200, TALK,
                 "Live activity, today's spend, your own commands, and a cache countdown.", now)


SCENES = [Scene("session", 6.0, _session), Scene("narrow", 7.0, _narrow), Scene("looks", 8.0, _looks),
          Scene("game", 21.0, _game), Scene("top row", 7.0, _top_row), Scene("party", 6.0, _party),
          Scene("harvest", 7.0, _harvest), Scene("live", 7.0, _live)]


def total():
    return sum(s.seconds for s in SCENES)


def at(t):
    """(scene, Frame) at `t` seconds into the whole script."""
    for s in SCENES:
        if t < s.seconds:
            return s, s.build(t)
        t -= s.seconds
    last = SCENES[-1]
    return last, last.build(last.seconds - 0.01)


# --- drawing -------------------------------------------------------------------------------------
_COMPILED: dict = {}


def bar(frame, env=None):
    """The fitted bar for a frame: a list of Text, and the Context."""
    import json
    from .context import Context
    from .layout import compile_config
    from .render import render_lines
    key = json.dumps(frame.raw, sort_keys=True)
    comp = _COMPILED.get(key)
    if comp is None:
        comp = _COMPILED[key] = compile_config(frame.raw)
    env = env if env is not None else {"COLORTERM": "truecolor", "TERM": "xterm-kitty"}
    ctx = Context(frame.data, comp, cols=frame.cols, now=frame.now, env=env, live=False, sync_git=True)
    return [f.text for f in render_lines(frame.data, comp, ctx=ctx) if f is not None], ctx


def talk_lines(frame, pal):
    """The conversation above the bar, as Text, in the theme's colours."""
    from .text import BOLD, Text
    out = []
    for who, line in frame.talk:
        if who == "you":
            out.append(Text().add("› ", (pal.get("accent"), None, BOLD, None)).add(line, (pal.get("text"), None, 0, None)))
        elif who == "claude":
            out.append(Text().add("  " + line, (pal.get("text"), None, 0, None)))
        elif who == "tool":
            name, _, rest = line.partition("  ")
            out.append(Text().add("  · ", (pal.get("muted"), None, 0, None)).add(name, (pal.get("blue"), None, BOLD, None))
                       .add("  " + rest, (pal.get("subtext"), None, 0, None)))
        else:
            out.append(Text().add("    " + line, (pal.get("muted"), None, 0, None)))
        out.append(Text())
    return out


def run(argv=None) -> int:
    """Play the script in this terminal: q quits, space pauses, ← → skip scenes."""
    import sys
    argv = list(argv or [])
    speed = 1.0
    if "--speed" in argv:
        try:
            speed = max(0.1, float(argv[argv.index("--speed") + 1]))
        except (IndexError, ValueError):
            pass
    try:
        interactive = sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        interactive = False
    if not interactive:
        print("The demo needs a terminal: run `python3 ~/.claude/statusline.py demo` in one.")
        return 2
    from .color import detect_mode
    from .text import BOLD, Text
    from .tui.term import Terminal
    mode = detect_mode()
    if mode == "none":
        mode = "256"
    t, paused, last = 0.0, False, time.time()
    starts = []
    acc = 0.0
    for s in SCENES:
        starts.append(acc)
        acc += s.seconds
    with Terminal(mouse=False) as term:
        while True:
            W, H = term.size()
            now = time.time()
            if not paused:
                t = (t + (now - last) * speed) % total()
            last = now
            scene, frame = at(t)
            frame.cols = min(frame.cols, W)
            lines, ctx = bar(frame)
            pal = ctx.pal
            rows = [Text().add(" " + frame.caption, (pal.get("text"), None, BOLD, None))
                    .add(("   " + frame.note) if frame.note else "", (pal.get("muted"), None, 0, None)), Text()]
            rows += talk_lines(frame, pal)
            room = max(0, H - len(rows) - len(lines) - 1)
            rows = rows[:max(2, H - len(lines) - 1)] + [Text()] * room + lines
            hint = Text().add(" q quit · space pause · ← → scene", (pal.get("subtle"), None, 0, None))
            rows = rows[:H - 1] + [hint]
            term.frame([r.ansi(mode) for r in rows])
            for k in term.keys(timeout=0.2):
                if k in ("q", "esc", "ctrl-c"):
                    return 0
                if k == " ":
                    paused = not paused
                i = SCENES.index(scene)
                if k in ("right", "l"):
                    t = starts[(i + 1) % len(SCENES)]
                elif k in ("left", "h"):
                    t = starts[(i - 1) % len(SCENES)]
