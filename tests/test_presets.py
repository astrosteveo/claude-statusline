"""Presets that carry settings ([quest], [bar]…), and `use` switching to one."""
import os
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from claude_statusline.cli import apply_preset  # noqa: E402
from claude_statusline.layout import compile_config, list_presets  # noqa: E402


class PresetSectionTests(unittest.TestCase):
    def test_arcade_is_the_full_game(self):
        self.assertIn("arcade", list_presets())
        comp = compile_config({"preset": "arcade"})
        self.assertEqual(comp["problems"], [])
        q = comp["quest"]
        self.assertEqual((q["enabled"], q["placement"], q["game_rows"], len(q["game_hud"])), (True, "game", 8, 8))
        self.assertEqual(len(comp["lines"]), 9)

    def test_your_own_keys_win(self):
        comp = compile_config({"preset": "arcade", "quest": {"game_rows": 4}, "bar": {"style": "dots"}})
        self.assertEqual(comp["quest"]["game_rows"], 4)
        self.assertEqual(comp["bar"]["style"], "dots")

    def test_other_presets_change_nothing_else(self):
        self.assertEqual(compile_config({"preset": "classic"})["quest"]["placement"], "line")


class UseTests(unittest.TestCase):
    def test_takes_out_what_would_hide_the_preset(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "config.toml")
        with open(path, "w") as fh:
            fh.write('# mine\npreset = "dashboard"\ntheme = "nord"\n\n[[line]]\nleft = ["model"]\n\n'
                     '[quest]\nenabled = true\ngame_rows = 3\nnotify = false\n')
        with mock.patch.dict(os.environ, {"CLAUDE_STATUSLINE_CONFIG": path}):
            _, removed, backup = apply_preset("arcade", path)
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
        self.assertEqual(raw["preset"], "arcade")
        self.assertEqual(raw["theme"], "nord")
        self.assertNotIn("line", raw)
        self.assertEqual(raw["quest"], {"notify": False})          # what the preset does not set stays
        self.assertIn("quest.game_rows", removed)
        self.assertTrue(os.path.exists(backup))
        with self.assertRaises(ValueError):
            apply_preset("nope", path)


if __name__ == "__main__":
    unittest.main()
