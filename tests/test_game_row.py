"""Game mode's top row: the session details beside the quest ticker, and the gauges beside the scene."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="quest-row-")
os.environ["CLAUDE_QUEST_HOME"] = HOME

from claude_statusline import decor, samples  # noqa: E402
from claude_statusline.config import read_toml  # noqa: E402
from claude_statusline.context import Context  # noqa: E402
from claude_statusline.decor import LOOKS  # noqa: E402
from claude_statusline.fit import GLANCE, NARROW, TEXT  # noqa: E402
from claude_statusline.layout import compile_config  # noqa: E402
from claude_statusline.render import _top_row, render_lines, render_spec  # noqa: E402
from claude_statusline.width import char_width  # noqa: E402

NOW = 1_800_000_000
ENV = {"COLORTERM": "truecolor"}
PAD = (None, None, 0, None)
NEWS = "🐙 The Legacy Behemoth rises from widget-factory's backlog: 11 TODOs and FIXMEs. Commits that remove them strike it."
BUSY = {"boss": {"icon": "🐍", "name": "Flaky Test Hydra", "hp": 3, "max_hp": 5, "kind": "test",
                 "project": "widget-factory"},
        "raids": {"widget-factory": {"name": "Backlog Kraken", "hp": 7, "max_hp": 11, "defeated": False}},
        "dungeons": [{"project": "widget-factory", "number": 42, "name": "Crypt of the Nitpick", "rooms": 3,
                      "traps": 1, "failing": 2}],
        "buffs": [{"icon": "☕", "name": "Flask of Cold Brew +2", "until": NOW + 900}]}
STATES = {"calm": ({}, {}),
          "eventful": ({"last_event": {"text": NEWS, "at": NOW - 3, "kind": "raid"}}, BUSY)}


def setUpModule():
    os.environ["CLAUDE_QUEST_HOME"] = HOME           # other test modules point it elsewhere


def save(state=None, **view):
    base = {"level": 38, "title": "Master", "rank": "Master", "xp_in": 3190, "xp_need": 3750,
            "class_icon": "🧙", "class": "Shell Sorcerer", "gold": 13096, "bag": 125, "stage": "drake",
            "gear_sig": "abc", "buffs": [], "boss": None, "daily_done": 3, "daily_total": 3, "streak": 3,
            "weekly": [{"title": "Proving Grounds", "progress": 19, "goal": 22, "done": False}]}
    base.update(view)
    data = {"xp": 70000, "view": base, "last_activity": NOW - 30}
    data.update(state or {})
    with open(os.path.join(HOME, "state.json"), "w") as fh:
        json.dump(data, fh)


def game(extra=None, **quest):
    raw = {"quest": {"enabled": True, "placement": "game", **quest}}
    raw.update(extra or {})
    return raw


def top(raw, data, cols, env=ENV, comp=None):
    comp = comp or compile_config(raw)
    ctx = Context(data, comp, cols=cols, now=NOW, env=env, live=False, sync_git=True)
    fit = _top_row(ctx, comp["lines"][0], lambda segs, side: decor.group(segs, ctx, side))
    return ctx, fit


def cells(text):
    """Each terminal cell as (character, style); the second half of a wide one is (None, style)."""
    out = []
    for t, st in text.spans:
        for ch in t:
            w = char_width(ch)
            if w == 0 and out:
                out[-1] = (out[-1][0] + ch, out[-1][1])
                continue
            out.append((ch, st))
            if w == 2:
                out.append((None, st))
    return out


class TopRowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = {n: samples.load(n, NOW) for n in ("quiet", "busy", "hot")}

    def test_game_sections_identical_with_and_without_details(self):
        """Every cell the game sections draw is the same with the details on the row as without,
        at 40 to 300 columns, in every style and icon set, with every sample and Quest state."""
        combos = [(style, icons) for style in LOOKS for icons in ("nerd", "unicode", "emoji", "none")]
        shown = 0
        for state_name, (state, view) in STATES.items():
            save(state, **view)
            for k, (style, icons) in enumerate(combos):
                look = {"style": style, "icons": icons, "theme": "midnight"}
                without, with_ = compile_config(game(look, game_details=[])), compile_config(game(look))
                for cols in range(40 + (k * 7) % 29, 301, 29):
                    for name, data in self.data.items():
                        ctx, alone = top(None, data, cols, comp=without)
                        _, both = top(None, data, cols, comp=with_)
                        where = (state_name, style, icons, cols, name)
                        self.assertLessEqual(both.text.width, ctx.avail, where)
                        self.assertEqual(both.overflow, alone.overflow, where)
                        a, b = cells(alone.text), cells(both.text)
                        for i, cell in enumerate(a):
                            if cell != (" ", PAD):
                                self.assertEqual(b[i] if i < len(b) else None, cell, (where, i, alone.text.plain()))
                        shown += both.details is not None and bool(both.details.text)
        self.assertGreater(shown, 500)                   # the details did show, mostly

    def test_news_takes_the_room_first(self):
        save({"last_event": {"text": NEWS, "at": NOW - 3, "kind": "raid"}})
        raw = game({"style": "minimal", "icons": "unicode"})
        _, fit = top(raw, self.data["busy"], 300)
        self.assertIn(NEWS.split(":")[0], fit.text.plain())
        self.assertIn("strike it.", fit.text.plain())             # the whole text, not the 48-cell cap
        self.assertGreater(fit.grown.get("quest_event", 0), 0)
        _, fit = top(raw, self.data["busy"], 120)
        self.assertIn("…", fit.text.plain())                      # short of room: capped
        self.assertNotIn("strike it.", fit.text.plain())
        save()
        _, calm = top(raw, self.data["busy"], 300)
        self.assertEqual(calm.grown, {})

    def test_auto_details_follow_your_lines(self):
        def names(raw):
            comp = compile_config(raw)
            self.assertEqual([p for p in comp["problems"] if p[0] == "error"], [])
            return [s["name"] for s in comp["lines"][0]["details"]]
        raw = game({"line": [{"left": ["dir", "git", "quest", "context"], "right": ["limit_5h", "clock"]},
                             {"left": ["cost", "model", "limit_7d_model"]}]})
        self.assertEqual(names(raw), ["model", "dir", "git", "clock", "cost", "limit_7d_model"])
        self.assertEqual(names(game()), ["model", "dir", "git", "pr", "worktree", "cache", "cost", "env",
                                         "session", "agent", "output_style", "limit_7d_model",
                                         "limit_spend"])                                # the classic preset
        self.assertEqual(names(game(game_details=["cost", "git"])), ["cost", "git"])
        self.assertEqual(names(game(game_details=[])), [])
        raw = game({"line": [{"left": ["context", "git"]}]}, game_hud=["git"])
        self.assertEqual(names(raw), ["model", "context"])        # what the gauges show stays off the row
        comp = compile_config(game(game_details="everything"))
        self.assertIn(("error", "quest.game_details"), {p[:2] for p in comp["problems"]})
        comp = compile_config(game(game_details=["modle"]))
        self.assertIn("did you mean 'model'", " ".join(p[2] for p in comp["problems"]))

    def test_the_users_config_at_220_columns(self):
        save()
        raw, err = read_toml(os.path.join(HERE, "fixtures", "game-user.toml"))
        self.assertIsNone(err)
        _, fit = top(raw, self.data["busy"], 220, env={"COLORTERM": "truecolor", "TERM": "xterm-kitty"})
        text = fit.text.plain()
        for want in ("Opus 5", "high", "widget-factory", "feat/parser", "#1234", "$24.73", "Lv 38", "13,096"):
            self.assertIn(want, text)

    def test_details_give_way_lowest_priority_first(self):
        save({"last_event": {"text": NEWS, "at": NOW - 3, "kind": "raid"}}, **BUSY)
        raw = game({"style": "capsules", "icons": "nerd"})
        comp = compile_config(raw)
        prio = {s["name"]: s["prio"] for s in comp["lines"][0]["details"]}
        seen_levels = set()
        for cols in range(60, 301, 3):
            _, fit = top(raw, self.data["busy"], cols)
            d = fit.details
            if d is None:
                continue
            for name, level in d.levels.items():
                seen_levels.add(level)
                if level > 0:        # nothing less important is still on the row
                    self.assertFalse([n for n, lv in d.levels.items() if prio[n] < prio[name]], (cols, d.levels))
            for gone in d.dropped:
                self.assertFalse([n for n in d.levels if prio[n] < prio[gone]], (cols, d.levels, d.dropped))
        self.assertIn(0, seen_levels)
        self.assertTrue(seen_levels - {0})

    def test_glance_is_the_icon_alone(self):
        comp = compile_config(game({"style": "capsules", "icons": "nerd", "line": [{"left": ["git", "cost"]}]}))
        ctx = Context(self.data["busy"], comp, cols=200, now=NOW, env=ENV, live=False, sync_git=True)
        git, cost = [s for s in comp["lines"][0]["details"] if s["name"] in ("git", "cost")]
        g = render_spec(git, ctx, GLANCE)
        self.assertTrue(g.glance)
        self.assertEqual(g.body.plain(), "")
        self.assertEqual(decor.group([g], ctx).width, 3)            # cap, icon, cap
        c = render_spec(cost, ctx, GLANCE)                          # no state in its colour: keeps its text
        self.assertFalse(c.glance)
        self.assertIn("$24.73", c.body.plain())
        for style in LOOKS:
            ctx.style = style
            self.assertLessEqual(decor.group([g], ctx).width, 4, style)          # powerline adds its arrow
        comp = compile_config(game({"icons": "none", "line": [{"left": ["git"]}]}))
        ctx = Context(self.data["busy"], comp, cols=200, now=NOW, env=ENV, live=False, sync_git=True)
        self.assertFalse(render_spec(comp["lines"][0]["details"][1], ctx, GLANCE).glance)   # no icon, no glance


class GaugeTests(unittest.TestCase):
    def rows(self, cols, now=NOW, **quest):
        save()
        data = samples.load("busy", now)
        comp = compile_config(game({"style": "capsules", "icons": "nerd"}, **quest))
        ctx = Context(data, comp, cols=cols, now=now, env=ENV, live=False)
        return ctx, render_lines(data, comp, ctx=ctx)

    def test_wide_terminals_get_the_rich_look(self):
        ctx, fits = self.rows(220)
        text = [f.text.plain() for f in fits[1:]]
        self.assertIn("28% 279k", text[0])
        self.assertIn("↻1h43m", text[1].replace("\U000f0450", "↻"))
        self.assertIn("→", text[1])
        ctx, fits = self.rows(120)
        text = [f.text.plain() for f in fits[1:]]
        self.assertIn("ctx 28%", text[0])                                       # version 3's compact look
        self.assertNotIn("279k", text[0])
        self.assertNotIn("1h43m", text[1])

    def test_the_column_does_not_follow_the_values(self):
        from claude_statusline.render import _hud
        widths = set()
        for minutes in (0, 45, 100):                                 # the 5h reset: 1h43m, 58m, 3m
            ctx, fits = self.rows(220, NOW + minutes * 60)
            scene = [ln for ln in ctx.comp["lines"] if ln.get("scene") is not None]
            hud_w, gauges = _hud(ctx, scene, lambda segs, side: decor.group(segs, ctx, side))
            widths.add(hud_w)
            self.assertTrue(all(g.width == hud_w for g in gauges.values()))
            for f in fits[1:]:
                self.assertEqual(f.text.width, ctx.avail)
        self.assertEqual(len(widths), 1)

    def test_any_segment_can_be_a_gauge(self):
        comp = compile_config(game(game_hud=["cost", "git", "context"]))
        self.assertEqual([p for p in comp["problems"] if p[0] == "error"], [])
        ctx, fits = self.rows(160, game_hud=["cost", "git", "context"])
        self.assertIn("$24.73", fits[1].text.plain())
        self.assertIn("feat/parser", fits[2].text.plain())

    def test_a_zero_width_bar_stays_hidden(self):
        comp = compile_config({"line": [{"left": ["context"]}], "segment": {"context": {"width": 0}}})
        ctx = Context(samples.load("busy", NOW), comp, cols=200, now=NOW, env=ENV, live=False)
        self.assertEqual(ctx.bar_width({"width": 0}, NARROW), 0)
        self.assertEqual(ctx.bar_width({"width": 0}, TEXT), 0)
        self.assertEqual(ctx.bar_width({"width": 10}, NARROW), 5)


if __name__ == "__main__":
    unittest.main()
