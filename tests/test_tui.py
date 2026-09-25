"""The configurator: keys parse, every page draws, edits change the config, saving writes it."""
import os
import pty
import select
import signal
import struct
import sys
import tempfile
import time
import tomllib
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
DIR = tempfile.mkdtemp(prefix="sl-tui-")
os.environ["CLAUDE_STATUSLINE_CONFIG"] = os.path.join(DIR, "config.toml")
os.environ["CLAUDE_QUEST_HOME"] = os.path.join(DIR, "quest")
os.environ["XDG_RUNTIME_DIR"] = DIR

from claude_statusline.tui.app import TABS, App  # noqa: E402
from claude_statusline.tui.term import Key, parse_keys  # noqa: E402


def keys(app, *names):
    for n in names:
        app.on_key(Key(n, n if len(n) == 1 else ""))


class KeyTests(unittest.TestCase):
    def test_parse(self):
        names = [k.name for k in parse_keys("a\x1b[A\x1b[B\x1b[1;2C\x1b[3~\x1b[Z\r\t\x7f\x13\x1b")]
        self.assertEqual(names, ["a", "up", "down", "shift-right", "delete", "shift-tab", "enter", "tab",
                                 "backspace", "ctrl-s", "esc"])
        click = parse_keys("\x1b[<0;10;5M")[0]
        self.assertEqual((click.name, click.x, click.y), ("click", 9, 4))
        self.assertEqual(parse_keys("\x1b[<64;1;1M")[0].name, "wheel-up")
        self.assertEqual(parse_keys("\x1bOA")[0].name, "up")


class AppTests(unittest.TestCase):
    def setUp(self):
        path = os.environ["CLAUDE_STATUSLINE_CONFIG"]
        if os.path.exists(path):
            os.remove(path)
        self.app = App()
        self.app.sample = "busy"

    def test_every_page_draws_at_every_size(self):
        for i in range(len(TABS)):
            self.app.goto(i)
            for w, h in ((60, 16), (100, 30), (200, 60), (40, 10)):
                rows = self.app.draw(w, h)
                self.assertEqual(len(rows), h, (TABS[i], w, h))
                for r in rows:
                    self.assertLessEqual(r.width, w, (TABS[i], w, h, r.plain()))

    def test_look_changes_apply_live(self):
        keys(self.app, "down")
        self.assertEqual(self.app.raw["theme"], "claude-light")
        keys(self.app, "right", "down", "down")
        self.assertEqual(self.app.raw["style"], "classic")
        self.assertTrue(self.app.dirty())
        self.assertEqual(self.app.comp["style"], "classic")

    def test_layout_editing(self):
        app = self.app
        app.goto(1)
        keys(app, "x")                                    # remove the first segment of line 1
        first = app.raw["line"][0]["left"]
        self.assertNotIn("model", first)
        keys(app, "a")
        self.assertIsNotNone(app.picker)
        for ch in "model":
            keys(app, ch)
        keys(app, "enter")
        self.assertIn("model", app.raw["line"][0]["left"])
        pos = app.layout_pos
        keys(app, ">")
        self.assertEqual(app.layout_pos, pos + 1)
        keys(app, "]")                                    # to line 2
        self.assertIn("model", app.raw["line"][1]["left"])
        keys(app, "n")
        self.assertEqual(len(app.raw["line"]), 3)
        keys(app, "D")
        self.assertEqual(len(app.raw["line"]), 2)
        self.assertEqual([p for p in app.comp["problems"] if p[0] == "error"], [])

    def test_preset_row(self):
        app = self.app
        app.goto(1)
        keys(app, "up", "right")
        self.assertEqual(app.raw["preset"], "compact")
        self.assertNotIn("line", app.raw)

    def test_segment_form(self):
        app = self.app
        app.goto(2)
        keys(app, "down")                                 # dir
        keys(app, "right")                                # into its options
        fields = app.segment_fields("dir")
        idx = [f.label for f in fields].index("mode")
        for _ in range(idx):
            keys(app, "down")
        keys(app, "right")
        self.assertEqual(app.raw["segment"]["dir"]["mode"], "compact")
        keys(app, "delete")
        self.assertNotIn("segment", app.raw)
        keys(app, "up", "up", "up", "enter")              # edit `icon` as text
        self.assertIsNotNone(app.edit)
        for ch in "D":
            keys(app, ch)
        keys(app, "enter")
        self.assertEqual(app.raw["segment"]["dir"]["icon"], "D")

    def test_bad_format_is_refused(self):
        app = self.app
        app.goto(2)
        keys(app, "right", "enter")                       # model's format
        app.edit["buf"] = "{name"
        app.edit["pos"] = 5
        keys(app, "enter")
        self.assertIsNotNone(app.edit)                    # still editing
        self.assertNotIn("segment", app.raw)
        keys(app, "esc")
        self.assertIsNone(app.edit)

    def test_save_and_quit(self):
        app = self.app
        keys(app, "down", "s")
        with open(app.path, "rb") as fh:
            self.assertEqual(tomllib.load(fh)["theme"], "claude-light")
        self.assertFalse(app.dirty())
        keys(app, "down", "q")
        self.assertIsNotNone(app.confirm)
        keys(app, "esc")
        self.assertFalse(app.quit)
        keys(app, "q", "q")
        self.assertTrue(app.quit)

    def test_help_and_samples(self):
        keys(self.app, "?")
        self.assertTrue(self.app.help)
        self.app.draw(120, 40)
        keys(self.app, "x")
        self.assertFalse(self.app.help)
        before = self.app.sample
        keys(self.app, "p")
        self.assertNotEqual(self.app.sample, before)


class PtyTests(unittest.TestCase):
    def test_runs_in_a_terminal_and_restores_it(self):
        pid, fd = pty.fork()
        if pid == 0:
            os.execvp(sys.executable, [sys.executable, os.path.join(ROOT, "statusline.py")])
        import fcntl
        import termios
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 110, 0, 0))
        os.kill(pid, signal.SIGWINCH)
        out = b""

        def pump(t):
            nonlocal out
            end = time.time() + t
            while time.time() < end:
                r, _, _ = select.select([fd], [], [], 0.05)
                if r:
                    try:
                        out += os.read(fd, 65536)
                    except OSError:
                        return
        pump(1.5)
        for k in (b"\t", b"\t", b"\x1b[B", b"2", b"?", b"x", b"q"):
            os.write(fd, k)
            pump(0.2)
        pump(0.5)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)
        self.assertIn(b"\x1b[?1049h", out)                # alternate screen on…
        self.assertIn(b"\x1b[?1049l", out)                # …and off again
        self.assertIn("claude-statusline".encode(), out)


if __name__ == "__main__":
    unittest.main()
