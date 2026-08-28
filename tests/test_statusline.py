#!/usr/bin/env python3
"""Test suite for claude-statusline. Stdlib only: python3 -m unittest discover tests"""
import json
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(HERE, "fixtures")
SCRIPT = os.path.join(ROOT, "statusline.py")

sys.path.insert(0, ROOT)
import statusline as S  # noqa: E402

WIDTHS = (200, 174, 160, 120, 100, 80, 60, 40)
_SGR = re.compile(r"\033\[[0-9;]*[@-~]")
_OSC = re.compile(r"\033\]8;;.*?(?:\033\\|\a)")


def strip(s):
    return _SGR.sub("", _OSC.sub("", s))


def fixtures():
    for name in sorted(os.listdir(FIXTURES)):
        if name.endswith(".json"):
            with open(os.path.join(FIXTURES, name)) as fh:
                yield name, json.load(fh)


class WidthTests(unittest.TestCase):
    def test_ascii(self):
        self.assertEqual(S.display_width("hello"), 5)

    def test_sgr_is_invisible(self):
        self.assertEqual(S.display_width("\033[38;5;114mabc\033[0m"), 3)

    def test_osc8_hyperlink_is_invisible(self):
        self.assertEqual(S.display_width(S.link("https://example.com", "abc")), 3)

    def test_osc8_bel_terminated(self):
        self.assertEqual(S.display_width("\033]8;;http://x\aabc\033]8;;\a"), 3)

    def test_cjk_is_wide(self):
        self.assertEqual(S.display_width("中文"), 4)

    def test_emoji_presentation_is_wide(self):
        self.assertEqual(S.display_width("\U0001F680"), 2)   # rocket

    def test_combining_marks_are_zero(self):
        self.assertEqual(S.display_width("é"), 1)

    def test_zero_width_joiner(self):
        self.assertEqual(S.display_width("a​b"), 2)

    def test_vs16_promotes_to_wide(self):
        self.assertEqual(S.display_width("⏱️"), 2)

    def test_configured_wide_glyph_override(self):
        cfg = S._deep_merge(S.DEFAULTS, {"layout": {"wide_glyphs": ["⏱"]}})
        S.apply_config(cfg)
        try:
            self.assertEqual(S.display_width("⏱"), 2)
        finally:
            S.apply_config(S._deep_merge(S.DEFAULTS, {}))

    def test_bar_glyphs_are_single_cell(self):
        """The whole right-anchoring scheme depends on this."""
        for ch in "█░" + S._EIGHTHS + S._SHADES:
            self.assertEqual(S.cell_width(ch), 1, f"{ch!r} is not 1 cell")


class BarTests(unittest.TestCase):
    def setUp(self):
        S.apply_config(S._deep_merge(S.DEFAULTS, {}))

    def test_zero_is_empty(self):
        self.assertEqual(strip(S.make_bar(0, 10)), "░" * 10)

    def test_full_is_full(self):
        self.assertEqual(strip(S.make_bar(100, 10)), "█" * 10)

    def test_width_is_exact_at_every_percent(self):
        for width in (1, 4, 6, 12, 20):
            for pct in range(0, 101):
                self.assertEqual(S.display_width(S.make_bar(pct, width)), width,
                                 f"pct={pct} width={width}")

    def test_small_nonzero_shows_a_sliver(self):
        """A 2% bar must not look identical to 0%."""
        self.assertNotEqual(strip(S.make_bar(2, 12)), strip(S.make_bar(0, 12)))

    def test_shade_style_never_breaks_the_track(self):
        """Regression: eighth-blocks left the rest of their cell unshaded, so
        the ░ track had a visible notch at the fill boundary."""
        S.apply_config(S._deep_merge(S.DEFAULTS,
                                     {"bar": {"partial_style": "shade"}}))
        allowed = set("█░▒▓")
        for width in (6, 12, 20):
            for pct in range(0, 101):
                glyphs = set(strip(S.make_bar(pct, width)))
                self.assertTrue(glyphs <= allowed,
                                f"pct={pct} width={width} used {glyphs - allowed}")

    def test_every_style_is_width_exact(self):
        for style in ("shade", "eighth", "off"):
            S.apply_config(S._deep_merge(S.DEFAULTS,
                                         {"bar": {"partial_style": style}}))
            for width in (1, 6, 12, 20):
                for pct in range(0, 101):
                    self.assertEqual(S.display_width(S.make_bar(pct, width)),
                                     width, f"{style} pct={pct} width={width}")

    def test_eighth_style_still_available(self):
        S.apply_config(S._deep_merge(S.DEFAULTS,
                                     {"bar": {"partial_style": "eighth"}}))
        self.assertTrue(set(strip(S.make_bar(6, 12))) & set(S._EIGHTHS))

    def test_off_style_rounds_to_whole_cells(self):
        S.apply_config(S._deep_merge(S.DEFAULTS,
                                     {"bar": {"partial_style": "off"}}))
        self.assertTrue(set(strip(S.make_bar(37, 12))) <= set("█░"))

    def test_off_style_still_shows_a_sliver(self):
        S.apply_config(S._deep_merge(S.DEFAULTS,
                                     {"bar": {"partial_style": "off"}}))
        self.assertNotEqual(strip(S.make_bar(2, 12)), strip(S.make_bar(0, 12)))

    def test_monotonic(self):
        prev = -1.0
        for pct in range(0, 101):
            filled = sum(1 for ch in strip(S.make_bar(pct, 20))
                         if ch != "░")
            self.assertGreaterEqual(filled, prev)
            prev = filled

    def test_out_of_range_is_clamped(self):
        self.assertEqual(S.display_width(S.make_bar(-50, 8)), 8)
        self.assertEqual(S.display_width(S.make_bar(9999, 8)), 8)

    def test_zero_width_renders_nothing(self):
        self.assertEqual(S.make_bar(50, 0), "")


class RenderTests(unittest.TestCase):
    def setUp(self):
        S.apply_config(S._deep_merge(S.DEFAULTS, {}))

    def test_never_exceeds_budget(self):
        """The core invariant: no line may overflow the usable width."""
        for name, data in fixtures():
            for cols in WIDTHS:
                out = S.render(data, cols=cols)
                budget = S.usable_width(cols)
                for i, line in enumerate(out.split("\n"), 1):
                    self.assertLessEqual(
                        S.display_width(line), budget,
                        f"{name} @ {cols} cols: line {i} overflows "
                        f"({S.display_width(line)} > {budget})")

    def test_always_two_lines(self):
        for name, data in fixtures():
            self.assertEqual(len(S.render(data, cols=120).split("\n")), 2, name)

    def test_limits_are_right_anchored(self):
        """Line 2 should consume nearly all its budget, not float left."""
        with open(os.path.join(FIXTURES, "full.json")) as fh:
            data = json.load(fh)
        for cols in (174, 120, 100):
            line2 = S.render(data, cols=cols).split("\n")[1]
            budget = S.usable_width(cols)
            self.assertGreaterEqual(S.display_width(line2), budget - 2,
                                    f"@{cols}: line 2 is not flush right")

    def test_no_trailing_whitespace_on_line2(self):
        for name, data in fixtures():
            line2 = S.render(data, cols=140).split("\n")[1]
            self.assertEqual(strip(line2), strip(line2).rstrip(), name)

    def test_hostile_input_still_renders(self):
        with open(os.path.join(FIXTURES, "hostile.json")) as fh:
            data = json.load(fh)
        self.assertEqual(len(S.render(data, cols=120).split("\n")), 2)

    def test_context_bar_precedes_limits(self):
        with open(os.path.join(FIXTURES, "full.json")) as fh:
            data = json.load(fh)
        line2 = strip(S.render(data, cols=174).split("\n")[1])
        self.assertLess(line2.index("ctx"), line2.index("5h"))
        self.assertLess(line2.index("5h"), line2.index("7d"))

    def test_context_moved_off_line1(self):
        with open(os.path.join(FIXTURES, "full.json")) as fh:
            data = json.load(fh)
        self.assertNotIn("ctx", strip(S.render(data, cols=174).split("\n")[0]))


class WindowTests(unittest.TestCase):
    def test_snake_case(self):
        w = S.find_windows({"rate_limits": {"five_hour": {"used_percentage": 5},
                                            "seven_day": {"used_percentage": 9}}})
        self.assertEqual(w["5h"]["pct"], 5)
        self.assertEqual(w["7d"]["pct"], 9)

    def test_camel_case(self):
        w = S.find_windows({"rateLimits": {"fiveHour": {"usedPercentage": 5},
                                           "sevenDay": {"usedPercentage": 9}}})
        self.assertEqual(w["5h"]["pct"], 5)

    def test_list_shape(self):
        """Regression: this branch was unreachable in the original script."""
        w = S.find_windows({"rate_limits": [
            {"window": "five_hour", "used_percentage": 50},
            {"window": "seven_day", "used_percentage": 12}]})
        self.assertEqual(w["5h"]["pct"], 50)
        self.assertEqual(w["7d"]["pct"], 12)

    def test_per_model_window_labelled(self):
        w = S.find_windows({"rate_limits": {
            "seven_day": {"used_percentage": 9},
            "seven_day_opus": {"used_percentage": 40}}})
        self.assertEqual(w["7d_model"]["label"], "opus")

    def test_model_window_falls_back_to_7d(self):
        w = S.find_windows({"rate_limits": {"seven_day_opus": {"used_percentage": 40}}})
        self.assertEqual(w["7d"]["pct"], 40)

    def test_missing_limits(self):
        self.assertEqual(S.find_windows({}), {})


class ConfigTests(unittest.TestCase):
    def tearDown(self):
        S.apply_config(S._deep_merge(S.DEFAULTS, {}))

    def test_example_matches_defaults(self):
        """Guards against config drift between the example and the code."""
        import tomllib
        with open(os.path.join(ROOT, "statusline.example.toml"), "rb") as fh:
            cfg = tomllib.load(fh)
        for section, body in cfg.items():
            self.assertIn(section, S.DEFAULTS, f"unknown section [{section}]")
            for key in body:
                self.assertIn(key, S.DEFAULTS[section],
                              f"unknown key {section}.{key}")
        for section, body in S.DEFAULTS.items():
            for key in body:
                self.assertIn(key, cfg.get(section, {}),
                              f"{section}.{key} is undocumented in the example")

    def test_broken_config_falls_back(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as fh:
            fh.write("this is not [valid toml")
            path = fh.name
        try:
            self.assertEqual(S.load_config(path)["bar"]["width"],
                             S.DEFAULTS["bar"]["width"])
        finally:
            os.unlink(path)

    def test_partial_config_merges(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as fh:
            fh.write("[bar]\nwidth = 30\n")
            path = fh.name
        try:
            cfg = S.load_config(path)
            self.assertEqual(cfg["bar"]["width"], 30)
            self.assertEqual(cfg["bar"]["full"], S.DEFAULTS["bar"]["full"])
            self.assertIn("colors", cfg)
        finally:
            os.unlink(path)

    def test_right_margin_changes_usable_width(self):
        S.apply_config(S._deep_merge(S.DEFAULTS, {"layout": {"right_margin": 0}}))
        self.assertEqual(S.usable_width(100), 100)
        S.apply_config(S._deep_merge(S.DEFAULTS, {"layout": {"right_margin": 9}}))
        self.assertEqual(S.usable_width(100), 91)


class HelperTests(unittest.TestCase):
    def test_num_rejects_junk(self):
        self.assertIsNone(S.num("abc"))
        self.assertIsNone(S.num(None))
        self.assertIsNone(S.num({}))
        self.assertIsNone(S.num(float("nan")))
        self.assertEqual(S.num("3.5"), 3.5)

    def test_num_rejects_bool(self):
        self.assertIsNone(S.num(True))

    def test_short_num(self):
        self.assertEqual(S.short_num(999), "999")
        self.assertEqual(S.short_num(1500), "2k")
        self.assertEqual(S.short_num(1_500_000), "1.5M")

    def test_dur(self):
        self.assertEqual(S.dur(90), "1m")
        self.assertEqual(S.dur(3700), "1h01m")
        self.assertEqual(S.dur(200000), "2d7h")
        self.assertEqual(S.dur(-5), "0m")

    def test_to_epoch_variants(self):
        self.assertEqual(S.to_epoch(1700000000), 1700000000)
        self.assertEqual(S.to_epoch(1700000000000), 1700000000)  # millis
        self.assertIsNotNone(S.to_epoch("2024-01-01T00:00:00Z"))
        self.assertIsNone(S.to_epoch("garbage"))

    def test_compact_path(self):
        self.assertEqual(S.compact_path("/a/b/c/d/e/f", keep=2), "…/e/f")


class CliTests(unittest.TestCase):
    """End-to-end: the process must exit 0 and print something, always."""

    def _run(self, args=(), stdin="", cols="120"):
        env = {**os.environ, "COLUMNS": cols, "CLAUDE_STATUSLINE_CONFIG": "/nonexistent"}
        return subprocess.run([sys.executable, SCRIPT, *args], input=stdin,
                              capture_output=True, text=True, env=env, timeout=30)

    def test_exit_zero_on_every_fixture(self):
        for name, data in fixtures():
            p = self._run(stdin=json.dumps(data))
            self.assertEqual(p.returncode, 0, f"{name}: {p.stderr}")
            self.assertTrue(p.stdout.strip(), name)

    def test_exit_zero_on_garbage(self):
        for junk in ("", "   ", "not json", "[]", "null", "123",
                     '{"broken": ', '{"model": {"display_name": {}}}'):
            p = self._run(stdin=junk)
            self.assertEqual(p.returncode, 0, f"{junk!r}: {p.stderr}")
            self.assertTrue(p.stdout.strip(), f"{junk!r} produced no output")

    def test_flags(self):
        for flag in ("--version", "--doctor", "--ruler", "--dump-config",
                     "--demo", "--help"):
            p = self._run([flag])
            self.assertEqual(p.returncode, 0, f"{flag}: {p.stderr}")
            self.assertTrue(p.stdout.strip(), flag)

    def test_unknown_flag_exits_nonzero(self):
        self.assertEqual(self._run(["--nope"]).returncode, 2)

    def test_dump_config_roundtrips_as_toml(self):
        import tomllib
        p = self._run(["--dump-config"])
        tomllib.loads(p.stdout)          # must parse

    def test_ruler_width(self):
        p = self._run(["--ruler"], cols="80")
        for line in p.stdout.rstrip("\n").split("\n"):
            self.assertEqual(len(line), 80)


if __name__ == "__main__":
    unittest.main(verbosity=2)
