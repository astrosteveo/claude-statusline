"""Command segments: output cached off the refresh path, bounded runs, colours kept, an off switch."""
import os
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from claude_statusline import commands as C  # noqa: E402
from claude_statusline.context import Context  # noqa: E402
from claude_statusline.layout import compile_config  # noqa: E402
from claude_statusline.render import render_lines  # noqa: E402


def raw(command, **opts):
    return {"line": [{"left": ["mine"]}], "style": "minimal", "icons": "none",
            "segment": {"mine": {"type": "command", "command": command, **opts}}}


class CommandTests(unittest.TestCase):
    def setUp(self):
        os.environ["XDG_RUNTIME_DIR"] = self.dir = tempfile.mkdtemp(prefix="sl-cmd-")
        os.environ.pop("CLAUDE_STATUSLINE_NO_COMMANDS", None)

    def render(self, cfg, live=False, sync=True):
        comp = compile_config(cfg)
        ctx = Context({"cwd": self.dir}, comp, cols=120, env={}, live=live, sync_git=sync)
        f = render_lines({"cwd": self.dir}, comp, ctx=ctx)[0]
        return f.text if f else None

    def test_output_keeps_colours_and_loses_the_rest(self):
        spans = C.spans_of("\x1b[1;38;5;208mhot\x1b[0m\tplain \x1b]8;;http://x\x1b\\link\x1b]8;;\x1b\\\x07\x1b[2Kend")
        self.assertEqual("".join(t for t, *_ in spans), "hot plain linkend")
        self.assertEqual(spans[0][1][3], 208)
        self.assertEqual(spans[0][3], 1)                       # bold
        self.assertEqual(C.spans_of("\x1b[38;2;1;2;3mrgb")[0][1], (1, 2, 3, -1))
        self.assertEqual(len("".join(t for t, *_ in C.spans_of("x" * 5000))), C.MAX_CHARS)

    def test_a_preview_runs_it_once(self):
        text = self.render(raw("printf '\\033[31mred\\033[0m and first\\nsecond\\n'"))
        self.assertEqual(text.plain(), "red and first")
        self.assertEqual(text.spans[0][1][0][:3], (205, 0, 0))

    def test_a_refresh_never_waits(self):
        cfg = raw("sleep 1; echo done", every=2)
        t = time.time()
        self.assertIsNone(self.render(cfg, live=True, sync=False))        # nothing yet, a runner started
        self.assertLess(time.time() - t, 0.5)
        self.assertIsNone(self.render(cfg, live=True, sync=False))        # the lock: still one runner
        locks = [f for f in os.listdir(os.path.join(self.dir, "claude-statusline")) if f.endswith(".lock")]
        self.assertEqual(len(locks), 1)
        for _ in range(60):
            text = self.render(cfg, live=True, sync=False)
            if text is not None:
                break
            time.sleep(0.1)
        self.assertEqual(text.plain(), "done")

    def test_a_slow_command_is_killed(self):
        t = time.time()
        entry = C.run("k1", "echo early; sleep 30 & sleep 30", self.dir, 0.5)
        self.assertLess(time.time() - t, 5)
        self.assertEqual(entry["exit"], "timeout")
        self.assertEqual(entry["plain"], "early")

    def test_the_off_switch(self):
        cfg = dict(raw("echo hi"), commands={"enabled": False})
        self.assertIsNone(self.render(cfg))
        self.assertIsNone(self.render(cfg, live=True, sync=False))
        runtime = os.path.join(self.dir, "claude-statusline")
        self.assertFalse(os.path.isdir(runtime) and any(f.startswith("cmd-") for f in os.listdir(runtime)))
        os.environ["CLAUDE_STATUSLINE_NO_COMMANDS"] = "1"
        try:
            self.assertIsNone(self.render(raw("echo hi")))
        finally:
            del os.environ["CLAUDE_STATUSLINE_NO_COMMANDS"]

    def test_old_output_goes(self):
        cfg = raw("echo hi", every=5, stale=60)
        self.assertEqual(self.render(cfg).plain(), "hi")
        key = C.key_of("echo hi", self.dir, "project")
        entry = C.read(key)
        entry["at"] -= 3600
        import marshal
        with open(C.paths(key)[0], "wb") as fh:
            fh.write(marshal.dumps(entry))
        self.assertIsNone(self.render(cfg, live=False, sync=False))

    def test_problems(self):
        probs = {(p[0], p[1]) for p in compile_config(raw("", every=0.5, timeout=60))["problems"]}
        self.assertEqual(probs, {("error", "segment.mine.command"), ("warning", "segment.mine.every"),
                                 ("warning", "segment.mine.timeout")})


if __name__ == "__main__":
    unittest.main()
