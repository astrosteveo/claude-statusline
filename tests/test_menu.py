"""Game mode's settings menu: the links, what a click does, the drawing, the gear, the link opener."""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from claude_statusline import menu, samples  # noqa: E402
from claude_statusline.config import runtime_dir  # noqa: E402
from claude_statusline.context import Context  # noqa: E402
from claude_statusline.layout import compile_config  # noqa: E402
from claude_statusline.render import render_lines  # noqa: E402
from claude_statusline.themes import THEMES  # noqa: E402

NOW = 1_800_000_000
ENV = {"COLORTERM": "truecolor", "TERM": "xterm-kitty"}
SID = "0f3c2a9e-1b2d-4c5e-8f70-123456789abc"
CONFIG = """# my config
theme = "nord"   # cool colours
style = "capsules"

[quest]
enabled = true
placement = "game"
game_rows = 3
"""


def game(rows=3, **quest):
    return compile_config({"quest": {"enabled": True, "placement": "game", "game_rows": rows, **quest}})


def links(texts):
    return [st[3] for t in texts for _, st in t.spans if st[3]]


class Sandbox(unittest.TestCase):
    """A config, runtime folder and data folder of its own, so nothing touches the real ones."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="menu-")
        self.config = os.path.join(self.dir, "config.toml")
        with open(self.config, "w") as fh:
            fh.write(CONFIG)
        for sub in ("run", "data", "conf", "quest"):
            os.makedirs(os.path.join(self.dir, sub))
        env = mock.patch.dict(os.environ, {
            "CLAUDE_STATUSLINE_CONFIG": self.config, "CLAUDE_STATUSLINE_NOCACHE": "1",
            "XDG_RUNTIME_DIR": os.path.join(self.dir, "run"), "XDG_DATA_HOME": os.path.join(self.dir, "data"),
            "XDG_CONFIG_HOME": os.path.join(self.dir, "conf"), "CLAUDE_QUEST_HOME": os.path.join(self.dir, "quest")})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(shutil.rmtree, self.dir, True)

    def text(self):
        with open(self.config) as fh:
            return fh.read()

    def ctx(self, comp=None, live=True, **data):
        payload = {"session_id": SID, **data}
        return Context(payload, comp or game(), cols=160, now=NOW, env=ENV, live=live)


class ParseTests(unittest.TestCase):
    def test_accepts_the_menus_links(self):
        for path, want in (("open", ("open", [])), ("close", ("close", [])), ("back", ("back", [])),
                           ("page/2", ("page", ["2"])), ("pick/theme", ("pick", ["theme"])),
                           ("step/rows/up", ("step", ["rows", "up"])), ("set/theme/rose-pine", ("set", ["theme", "rose-pine"]))):
            self.assertEqual(menu.parse(f"claude-statusline://{SID}/{path}"), (SID, *want))

    def test_refuses_anything_else(self):
        for url in ("https://example.com/open", f"claude-statusline://{SID}/", f"claude-statusline://{SID}/explode",
                    f"claude-statusline://{SID}/open/now", f"claude-statusline://{SID}/step/theme",
                    f"claude-statusline://{SID}/step/preset/up", f"claude-statusline://{SID}/pick/party",
                    f"claude-statusline://{SID}/page/x", f"claude-statusline://{SID}/page/100",
                    f"claude-statusline://{SID}/open?x=1", f"claude-statusline://{SID}/open#x",
                    "claude-statusline://../open", "claude-statusline://a.b/open", "claude-statusline://a:1/open",
                    f"claude-statusline://{SID}/set/theme/..%2f..", f"claude-statusline://{SID}/set/theme/$(id)",
                    "claude-statusline:///open", "not a link"):
            with self.assertRaises(ValueError, msg=url):
                menu.parse(url)


class ClickTests(Sandbox):
    def click(self, path, now=NOW):
        return menu.handle(f"claude-statusline://{SID}/{path}", now=now)

    def test_open_and_close(self):
        self.assertIsNone(menu.read_state(self.ctx()))
        self.click("open")
        self.assertEqual(menu.read_state(self.ctx())["page"], 0)
        self.click("close")
        self.assertIsNone(menu.read_state(self.ctx()))

    def test_only_the_clicked_session_opens(self):
        self.click("open")
        other = Context({"session_id": "another-session"}, game(), cols=160, now=NOW, env=ENV, live=True)
        self.assertIsNone(menu.read_state(other))

    def test_closes_itself_when_idle(self):
        self.click("open", now=NOW - menu.IDLE - 1)
        self.assertIsNone(menu.read_state(self.ctx()))

    def test_step_writes_the_next_choice_and_keeps_comments(self):
        names = list(THEMES)
        want = names[(names.index("nord") + 1) % len(names)]
        self.assertEqual(self.click("step/theme/up"), f"theme = {want}")
        self.assertIn(f'theme = "{want}"  # cool colours', self.text())
        self.assertIn("# my config", self.text())
        self.click("step/theme/down")
        self.assertIn('theme = "nord"', self.text())

    def test_step_wraps_around(self):
        first, last = list(THEMES)[0], list(THEMES)[-1]
        self.click(f"set/theme/{first}")
        self.click("step/theme/down")
        self.assertIn(f'theme = "{last}"', self.text())

    def test_a_list_picks_then_returns_to_the_settings(self):
        self.click("open")
        self.click("pick/theme")
        self.assertEqual(menu.read_state(self.ctx())["pick"], "theme")
        self.click("set/theme/dracula")
        self.assertIn('theme = "dracula"', self.text())
        self.assertNotIn("pick", menu.read_state(self.ctx()))

    def test_rows_stay_within_bounds(self):
        self.click("step/rows/down")
        self.assertIn("game_rows = 2", self.text())
        for _ in range(4):
            self.click("step/rows/down")
        self.assertIn("game_rows = 1", self.text())
        for _ in range(10):
            self.click("step/rows/up")
        self.assertIn("game_rows = 8", self.text())

    def test_switches_add_their_key(self):
        self.click("step/party/up")
        self.assertIn("party = false", self.text())
        self.click("step/party/up")
        self.assertIn("party = true", self.text())
        self.click("step/picture/up")
        self.assertIn('avatar = "on"', self.text())
        self.click("step/bars/up")
        self.assertIn("[bar]", self.text())

    def test_refuses_a_value_that_is_not_a_choice(self):
        before = self.text()
        with self.assertRaises(ValueError):
            self.click("set/theme/evil")
        self.assertEqual(self.text(), before)

    def test_click_logs_what_it_did(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(menu.click(f"claude-statusline://{SID}/open"), 0)
            self.assertEqual(menu.click("claude-statusline://x/rm"), 1)
        with open(os.path.join(runtime_dir(), "clicks.log")) as fh:
            log = fh.read()
        self.assertIn("opened the menu", log)
        self.assertIn("refused", log)


class DrawTests(Sandbox):
    def ctx(self, comp, cols, state):
        data = samples.load("busy", NOW)
        data["session_id"] = SID
        data["_menu"] = state
        return Context(data, comp, cols=cols, now=NOW, env=ENV, live=False)

    def test_fits_every_height_and_width(self):
        states = [{"page": 0}, {"page": 1}] + [{"pick": p, "ppage": 1} for p in menu.PICKERS]
        for rows in range(1, 9):
            comp = game(rows)
            for cols in (60, 120, 200):
                for st in states:
                    ctx = self.ctx(comp, cols, st)
                    out = menu.rows(ctx, ctx.avail, rows, st)
                    where = (rows, cols, st)
                    self.assertEqual(len(out), rows, where)
                    for t in out:
                        self.assertLessEqual(t.width, ctx.avail, where)
                    for url in links(out):
                        self.assertEqual(menu.parse(url)[0], SID, where)

    def test_every_setting_is_reachable(self):
        comp = game(8)
        ctx = self.ctx(comp, 220, {"page": 0})
        urls = links(menu.rows(ctx, ctx.avail, 8, {"page": 0}))
        for item in menu.ITEMS:
            self.assertTrue(any(f"/{item[0]}/" in u for u in urls), item[0])
        self.assertTrue(any(u.endswith("/close") for u in urls))

    def test_pages_when_the_rows_run_out(self):
        comp = game(2)
        ctx = self.ctx(comp, 80, {"page": 0})
        first = menu.rows(ctx, ctx.avail, 2, {"page": 0})
        self.assertIn("1/", first[0].plain())
        last = menu.rows(ctx, ctx.avail, 2, {"page": 99})
        self.assertNotEqual(first[1].plain(), last[1].plain())

    def test_the_list_marks_the_current_choice(self):
        comp = compile_config({"theme": "nord", "quest": {"enabled": True, "placement": "game", "game_rows": 8}})
        ctx = self.ctx(comp, 200, {"pick": "theme"})
        out = menu.rows(ctx, ctx.avail, 8, {"pick": "theme"})
        self.assertIn("● nord", "".join(t.plain() for t in out))
        self.assertTrue(any(u.endswith("/back") for u in links(out)))

    def test_takes_the_scenes_place(self):
        comp = game(3)
        data = samples.load("busy", NOW)
        data["_menu"] = {"page": 0}
        ctx = Context(data, comp, cols=160, now=NOW, env=ENV, live=False)
        fits = render_lines(data, comp, ctx=ctx)
        self.assertEqual(len(fits), 4)
        self.assertIn("Settings", fits[1].text.plain())
        self.assertIn("Theme", fits[2].text.plain())


class GearTests(Sandbox):
    def install(self):
        path = menu.desktop_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").close()

    def test_shows_once_the_opener_is_registered(self):
        self.assertIsNone(menu.gear(self.ctx()))
        self.install()
        glyph, url, is_open = menu.gear(self.ctx())
        self.assertEqual(url, f"claude-statusline://{SID}/open")
        self.assertFalse(is_open)

    def test_closes_the_open_menu(self):
        self.install()
        menu.handle(f"claude-statusline://{SID}/open", now=NOW)
        _, url, is_open = menu.gear(self.ctx())
        self.assertTrue(url.endswith("/close"))
        self.assertTrue(is_open)

    def test_hidden_where_a_click_could_not_work(self):
        self.install()
        self.assertIsNone(menu.gear(self.ctx(live=False)))
        self.assertIsNone(menu.gear(Context({}, game(), cols=160, now=NOW, env=ENV, live=True)))
        self.assertIsNone(menu.gear(Context({"session_id": "../etc"}, game(), cols=160, now=NOW, env=ENV, live=True)))
        line = compile_config({"quest": {"enabled": True, "placement": "line"}})
        self.assertIsNone(menu.gear(self.ctx(line)))

    def test_previews_have_no_gear(self):
        self.install()
        data = dict(samples.load("busy", NOW), session_id=SID)
        ctx = Context(data, game(3), cols=200, now=NOW, env=ENV, live=False)
        fits = render_lines(data, game(3), ctx=ctx)
        self.assertNotIn(menu.GEAR["nerd"], fits[0].text.plain())

    def test_rides_the_ticker(self):
        comp = game(3)
        self.assertIn("quest_settings", [s["type"] for s in comp["lines"][0]["right"]])


class OpenerTests(Sandbox):
    def setUp(self):
        super().setUp()
        bin_dir = os.path.join(self.dir, "bin")
        os.makedirs(bin_dir)
        with open(os.path.join(bin_dir, "xdg-mime"), "w") as fh:     # writes what the real one would
            fh.write('#!/bin/sh\nprintf "[Default Applications]\\nx-scheme-handler/claude-statusline=%s\\n" "$2" '
                     '>> "$XDG_CONFIG_HOME/mimeapps.list"\n')
        os.chmod(os.path.join(bin_dir, "xdg-mime"), 0o755)
        env = mock.patch.dict(os.environ, {"PATH": bin_dir})
        env.start()
        self.addCleanup(env.stop)
        self.mime = os.path.join(self.dir, "conf", "mimeapps.list")

    def test_enable_then_disable(self):
        if sys.platform == "darwin":
            self.skipTest("Linux only")
        quiet = [].append
        self.assertEqual(menu.enable("/opt/my statusline.py", log=quiet), 0)
        with open(menu.desktop_path()) as fh:
            entry = fh.read()
        self.assertIn('-S "/opt/my statusline.py" click %u', entry)
        self.assertIn("MimeType=x-scheme-handler/claude-statusline;", entry)
        with open(self.mime) as fh:
            self.assertIn("claude-statusline-click.desktop", fh.read())
        self.assertTrue(menu.installed())
        self.assertEqual(menu.disable(log=quiet), 0)
        self.assertFalse(menu.installed())
        with open(self.mime) as fh:
            text = fh.read()
        self.assertNotIn("claude-statusline", text)
        self.assertIn("[Default Applications]", text)


class RuntimeDirTests(unittest.TestCase):
    def test_finds_the_usual_folder_without_the_variable(self):
        usual = f"/run/user/{os.getuid()}"
        if not os.path.isdir(usual) or not os.access(usual, os.W_OK):
            self.skipTest(f"no {usual}")
        env = {k: v for k, v in os.environ.items() if k != "XDG_RUNTIME_DIR"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(runtime_dir(), os.path.join(usual, "claude-statusline"))


if __name__ == "__main__":
    unittest.main()
