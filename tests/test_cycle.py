"""Cycle slots and panel pages: what shows, the link a click follows, and what the click writes."""
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from claude_statusline import menu, samples  # noqa: E402
from claude_statusline.context import Context  # noqa: E402
from claude_statusline.layout import compile_config  # noqa: E402
from claude_statusline.render import render_lines  # noqa: E402

NOW = 1_790_400_000
LIMITS = {"segment": {"limits": {"type": "cycle", "of": ["limit_5h", "limit_7d"]}},
          "line": [{"left": ["model"], "right": ["limits"]}]}


def first_line(raw, view=None, sid="s1"):
    comp = compile_config(raw)
    data = samples.load("busy", NOW)
    data["session_id"] = sid
    if view is not None:
        data["_view"] = view
    ctx = Context(data, comp, cols=160, now=NOW, env={"COLORTERM": "truecolor"}, live=False)
    return render_lines(data, comp, ctx=ctx)[0].text


class CycleTests(unittest.TestCase):
    def test_compiles_and_counts_its_members_as_placed(self):
        comp = compile_config(dict(LIMITS, segment={"limits": LIMITS["segment"]["limits"],
                                                     "limit_7d": {"clock": False}}))
        self.assertEqual(comp["problems"], [])
        spec = comp["lines"][0]["right"][0]
        self.assertEqual([m["name"] for m in spec["cycle"]], ["limit_5h", "limit_7d"])
        self.assertEqual(spec["slot"], "limits")

    def test_it_survives_as_long_as_its_strongest_member(self):
        spec = compile_config(LIMITS)["lines"][0]["right"][0]
        self.assertEqual(spec["prio"], 80)                       # limit_5h's
        own = dict(LIMITS, segment={"limits": dict(LIMITS["segment"]["limits"], priority=5)})
        self.assertEqual(compile_config(own)["lines"][0]["right"][0]["prio"], 5)

    def test_bad_cycles(self):
        comp = compile_config({"segment": {"one": {"type": "cycle", "of": ["clock"]},
                                           "loop": {"type": "cycle", "of": ["loop", "clock"]}},
                               "line": [{"left": ["one", "loop"]}]})
        self.assertEqual([p[1] for p in comp["problems"] if p[0] == "error"], ["segment.one.of", "segment.loop.of"])
        self.assertEqual([s["name"] for s in comp["lines"][0]["left"]], ["clock", "clock"])

    def test_a_click_moves_it_on_and_round(self):
        shown = [first_line(LIMITS, {"limits": n}).plain() for n in (0, 1, 2)]
        self.assertIn("5h", shown[0])
        self.assertIn("7d", shown[1])
        self.assertNotIn("5h", shown[1])
        self.assertEqual(shown[0], shown[2])

    def test_its_text_is_the_link(self):
        links = {s[3] for _, s in first_line(LIMITS, {}).spans if s[3]}
        self.assertEqual(links, {"claude-statusline://s1/cycle/limits"})

    def test_no_link_without_clicks(self):
        self.assertFalse(any(s[3] for _, s in first_line(LIMITS).spans))

    def test_activity_inside_a_cycle_needs_no_line_of_its_own(self):
        comp = compile_config({"activity": {"enabled": True},
                               "segment": {"now": {"type": "cycle", "of": ["turn", "clock"]}},
                               "line": [{"left": ["model", "now"]}]})
        self.assertEqual(len(comp["lines"]), 1)

    def test_dev_preset_cycles(self):
        comp = compile_config({"preset": "dev"})
        self.assertEqual(comp["problems"], [])
        self.assertEqual([s.get("slot") for s in comp["lines"][0]["right"]], ["usage", "limits"])


class ClickTests(unittest.TestCase):
    def test_a_cycle_click_writes_the_view_and_opens_no_menu(self):
        d = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": d}):
            for _ in range(3):
                menu.handle("claude-statusline://s1/cycle/limits")
            self.assertEqual(menu._read_views("s1"), {"limits": 3})
            self.assertFalse(os.path.exists(menu.state_path("s1")))

    def test_odd_slots_are_refused(self):
        for url in ("claude-statusline://s1/cycle", "claude-statusline://s1/cycle/a/b",
                    "claude-statusline://s1/cycle/a%20b"):
            with self.assertRaises(ValueError):
                menu.parse(url)


class PageTests(unittest.TestCase):
    def rows(self, view):
        comp = compile_config({"preset": "dev", "panels": {"rows": 4, "show": ["files"]}})
        data = samples.load("busy", NOW)
        data["session_id"] = "s1"
        data["_view"] = view
        ctx = Context(data, comp, cols=100, now=NOW, env={"COLORTERM": "truecolor"}, live=False)
        return [f.text.plain() for f, ln in zip(render_lines(data, comp, ctx=ctx), comp["lines"]) if "panel" in ln]

    def test_pages_turn_and_wrap(self):
        p1, p2, p4 = self.rows({}), self.rows({"panel-files": 1}), self.rows({"panel-files": 3})
        self.assertIn("page 1/3 ›", p1[-1])
        self.assertIn("page 2/3 ›", p2[-1])
        self.assertNotEqual(p1[1:3], p2[1:3])
        self.assertEqual(p1, p4)
        self.assertEqual(len(p1), 4)


if __name__ == "__main__":
    unittest.main()
