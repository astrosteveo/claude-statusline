"""Claude Quest on the bar: the segments render from the save's snapshot, and the pet behaves."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="quest-bar-")
os.environ["CLAUDE_QUEST_HOME"] = HOME

from claude_statusline.context import Context  # noqa: E402
from claude_statusline.layout import compile_config  # noqa: E402
from claude_statusline.render import render_lines  # noqa: E402
from claude_statusline.segments import quest as Q  # noqa: E402

NOW = 1_800_000_000
ENV = {"COLORTERM": "truecolor"}


def setUpModule():
    os.environ["CLAUDE_QUEST_HOME"] = HOME           # other test modules point it elsewhere


def save(state=None, **view):
    base = {"level": 21, "title": "Veteran", "rank": "Veteran", "xp_in": 500, "xp_need": 2050,
            "class_icon": "🧙", "class": "Shell Sorcerer", "gold": 1234, "bag": 4, "stage": "lizard",
            "gear_sig": "abc", "buffs": [], "boss": None, "daily_done": 1, "daily_total": 3, "streak": 5,
            "weekly": [{"title": "Proving Grounds", "progress": 19, "goal": 22, "done": False}]}
    base.update(view)
    data = {"xp": 20500, "view": base, "last_activity": NOW - 30}
    data.update(state or {})
    with open(os.path.join(HOME, "state.json"), "w") as fh:
        json.dump(data, fh)


def one(name, enabled=True, level=None, cols=200, **opts):
    raw = {"line": [{"left": [name]}], "style": "minimal", "icons": "unicode",
           "quest": {"enabled": enabled}, "segment": {name: opts} if opts else {}}
    comp = compile_config(raw)
    ctx = Context({}, comp, cols=cols, now=NOW, env=ENV, live=False)
    fits = render_lines({}, comp, ctx=ctx)
    return fits[0].text.plain() if fits and fits[0] else ""


class SegmentTests(unittest.TestCase):
    def test_hero(self):
        save()
        out = one("quest")
        for part in ("† Lv 21", "Veteran", "🧙", "500/2,050"):
            self.assertIn(part, out)

    def test_hidden_unless_enabled(self):
        save()
        for name in ("quest", "quest_daily", "quest_gold", "quest_streak"):
            self.assertEqual(one(name, enabled=False), "", name)

    def test_old_save_without_a_snapshot(self):
        with open(os.path.join(HOME, "state.json"), "w") as fh:
            json.dump({"xp": 20500, "school": {"shell": 3}}, fh)
        self.assertIn("Lv 21", one("quest"))

    def test_boss(self):
        save(boss={"icon": "🐍", "name": "Flaky Test Hydra", "hp": 2, "max_hp": 5})
        self.assertEqual(one("quest_boss"), "Ω Flaky Test Hydra ♥♥♡♡♡")
        save(boss={"icon": "🗿", "name": "Linker Lich", "hp": 11, "max_hp": 12})
        self.assertEqual(one("quest_boss"), "Ω Linker Lich ♥ 11/12")
        save()
        self.assertEqual(one("quest_boss"), "")

    def test_daily_gold_streak_buffs(self):
        save(buffs=[{"icon": "☕", "name": "Cold Brew", "until": NOW + 600},
                    {"icon": "⚡", "name": "Energy", "until": NOW - 1}])
        self.assertEqual(one("quest_daily"), "✓ 1/3 · week 19/22")
        self.assertEqual(one("quest_gold"), "◎ 1,234 · 4 items")
        self.assertEqual(one("quest_streak"), "◆ 5d")
        self.assertEqual(one("quest_buffs"), "▲ ☕10m")
        save(streak=1)
        self.assertEqual(one("quest_streak"), "")

    def test_event_fades(self):
        save({"last_event": {"text": "⬆️ LEVEL UP! You are now level 22", "at": NOW - 5, "kind": "levelup"}})
        self.assertIn("LEVEL UP", one("quest_event"))
        save({"last_event": {"text": "old news", "at": NOW - 600, "kind": "loot"}})
        self.assertEqual(one("quest_event"), "")

    def test_text_pet(self):
        save({"last_tool": NOW - 2})
        out = one("quest_pet")
        self.assertTrue(any(s in out for s in ("(o>", "<o)")))
        save({"last_activity": NOW - 3600})
        self.assertIn("z", one("quest_pet"))

    def test_quest_line_fits(self):
        save(boss={"icon": "🐍", "name": "Off-by-One Ogre", "hp": 1, "max_hp": 3},
             buffs=[{"icon": "☕", "until": NOW + 900}])
        for style in ("minimal", "capsules", "powerline"):
            comp = compile_config({"style": style, "quest": {"enabled": True}})
            for cols in (60, 100, 160, 220):
                ctx = Context({}, comp, cols=cols, now=NOW, env=ENV, live=False)
                for f in render_lines({}, comp, ctx=ctx):
                    if f:
                        self.assertLessEqual(f.text.width, ctx.avail)


class AvatarTests(unittest.TestCase):
    def act(self, **state):
        return Q.pick_action(state, NOW)

    def test_reactions_come_first(self):
        self.assertEqual(self.act(last_event={"at": NOW - 2, "kind": "victory"}), "victory")
        self.assertEqual(self.act(last_event={"at": NOW - 2, "kind": "boss"}), "battle")
        self.assertEqual(self.act(last_event={"at": NOW - 2, "text": "⬆️ LEVEL UP"}), "levelup")

    def test_work_battle_turn_sleep(self):
        self.assertEqual(self.act(last_tool=NOW - 3, last_activity=NOW), "work")
        self.assertEqual(self.act(last_tool=NOW - 3, last_activity=NOW, view={"boss": {"hp": 2}}), "battle")
        self.assertEqual(self.act(last_stop=NOW - 5, last_prompt=NOW - 50, last_activity=NOW - 5), "yourturn")
        self.assertEqual(self.act(last_activity=NOW - 3600), "sleep")
        self.assertEqual(self.act(last_prompt=NOW - 1, last_activity=NOW), "perk")

    def test_idle_rotation_uses_known_actions(self):
        seen = {Q.pick_action({"last_activity": NOW}, NOW + i * 8, ["stand", "look"]) for i in range(40)}
        self.assertEqual(seen, {"stand", "look"})

    def test_placeholder_row(self):
        row = Q.placeholder_row(1, 8, 205)
        text, style = row.spans[0]
        self.assertEqual(row.width, 8)
        self.assertEqual(text[0], Q.PLACEHOLDER)
        self.assertEqual(text[1], Q.DIACRITICS[1])
        self.assertEqual(style[0][3], 205)                          # the image id rides in the colour
        self.assertEqual(row.ansi("truecolor").count("38;5;205"), 1)

    def test_previews_never_touch_terminals(self):
        save()
        comp = compile_config({"quest": {"enabled": True, "avatar": "on"}})
        ctx = Context({}, comp, cols=160, now=NOW, env=ENV, live=False)
        render_lines({}, comp, ctx=ctx)
        self.assertFalse(ctx.avatar_active)


if __name__ == "__main__":
    unittest.main()
