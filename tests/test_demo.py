"""The demo: every moment of the script renders within the width budget, with the real engine."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from claude_statusline import demo  # noqa: E402


class DemoTests(unittest.TestCase):
    def test_every_step_fits(self):
        t, seen = 0.0, set()
        while t < demo.total():
            scene, frame = demo.at(t)
            lines, ctx = demo.bar(frame)
            self.assertTrue(lines, (scene.name, t))
            for line in lines:
                self.assertLessEqual(line.width, ctx.avail, (scene.name, t, line.plain()))
            self.assertTrue(frame.caption and not frame.caption[0].islower(), scene.name)
            seen.add(scene.name)
            t += 0.5
        self.assertEqual(seen, {s.name for s in demo.SCENES})

    def test_the_story_is_on_the_bar(self):
        def text(t):
            return "\n".join(line.plain() for line in demo.bar(demo.at(t)[1])[0])
        start = {}
        acc = 0.0
        for s in demo.SCENES:
            start[s.name] = acc
            acc += s.seconds
        self.assertIn("Opus 5.5", text(start["session"] + 1))
        self.assertIn("pytest", text(start["session"] + 1))                   # live activity
        self.assertIn("Flaky Test Hydra", text(start["game"] + 5))
        self.assertIn("LEVEL UP", text(start["game"] + 14))
        self.assertIn("#214", text(start["game"] + 18))
        self.assertIn("Headless Heisenbug", text(start["harvest"] + 1))
        self.assertIn("on call: priya", text(start["live"] + 1))

    def test_needs_a_terminal(self):
        import subprocess
        p = subprocess.run([sys.executable, "-S", os.path.join(os.path.dirname(HERE), "statusline.py"), "demo"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(p.returncode, 2)
        self.assertIn("needs a terminal", p.stdout)


if __name__ == "__main__":
    unittest.main()
