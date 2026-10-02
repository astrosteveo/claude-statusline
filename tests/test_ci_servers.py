"""The CI and servers panels: what their refreshers make of gh and ss, and how a stack shares its rows."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from claude_statusline import ci, samples  # noqa: E402
from claude_statusline.context import Context  # noqa: E402
from claude_statusline.layout import compile_config  # noqa: E402
from claude_statusline.render import render_lines  # noqa: E402
from claude_statusline.servers import parse_ss  # noqa: E402

NOW = 1_790_400_000
GH = [
    {"databaseId": 3, "workflowName": "Tests", "displayTitle": "Fix it", "status": "in_progress", "conclusion": "",
     "headSha": "abc", "event": "push", "createdAt": "2026-10-02T04:31:34Z", "startedAt": "2026-10-02T04:31:34Z",
     "updatedAt": "2026-10-02T04:32:28Z", "url": "https://github.com/o/r/actions/runs/3"},
    {"databaseId": 2, "workflowName": "Tests", "displayTitle": "Older", "status": "completed",
     "conclusion": "failure", "headSha": "old", "event": "push", "createdAt": "2026-10-01T04:31:34Z",
     "startedAt": "2026-10-01T04:31:34Z", "updatedAt": "2026-10-01T04:40:00Z", "url": ""},
    {"databaseId": 1, "workflowName": "Lint", "displayTitle": "Fix it", "status": "completed", "conclusion": "success",
     "headSha": "abc", "event": "push", "createdAt": "2026-10-02T04:31:34Z", "startedAt": "0001-01-01T00:00:00Z",
     "updatedAt": "2026-10-02T04:33:00Z", "url": ""},
]


class CiTests(unittest.TestCase):
    def test_latest_run_per_workflow(self):
        runs = ci.runs_of(GH)
        self.assertEqual([(r[0], r[1], r[3]) for r in runs], [(3, "Tests", "in_progress"), (1, "Lint", "completed")])
        self.assertEqual(runs[0][6], 1790915494)
        self.assertEqual(runs[1][6], 1790915494)             # an unset start falls back to the creation time

    def test_a_pop_up_only_for_a_run_seen_running_on_our_commit(self):
        before = ci.runs_of(GH)
        done = [dict(GH[0], status="completed", conclusion="success")] + GH[1:]
        after = ci.runs_of(done)
        self.assertEqual([r[0] for r in ci.finished(before, after, {"abc"})], [3])
        self.assertEqual(ci.finished(before, after, {"someone-else"}), [])
        self.assertEqual(ci.finished([], after, {"abc"}), [])       # never announce what was not seen running
        self.assertEqual(ci.finished(after, after, {"abc"}), [])


class ServersTests(unittest.TestCase):
    def test_parse_ss(self):
        text = ('LISTEN 0 511 *:5173 *:* users:(("node",pid=42,fd=20),("node",pid=43,fd=20))\n'
                'LISTEN 0 128 [::1]:8000 [::]:* users:(("python",pid=7,fd=3))\n'
                'LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\n')
        self.assertEqual(parse_ss(text), [(5173, "node", 42), (5173, "node", 43), (8000, "python", 7)])


class StackTests(unittest.TestCase):
    def rows(self, n, drop=()):
        comp = compile_config({"preset": "dev", "panels": {"rows": n}})
        data = samples.load("busy", NOW)
        for k in drop:
            data["_panels"][k] = [] if k != "ci" else None
        ctx = Context(data, comp, cols=100, now=NOW, env={"COLORTERM": "truecolor"}, live=False)
        out = [f.text.plain() for f, ln in zip(render_lines(data, comp, ctx=ctx), comp["lines"]) if "panel" in ln]
        return ctx, out

    def test_every_height_fits(self):
        for n in range(1, 17):
            ctx, rows = self.rows(n)
            self.assertEqual(len(rows), n)
            self.assertTrue(all(len(r) <= ctx.avail for r in rows))

    def test_all_four_at_twelve_rows(self):
        text = "\n".join(self.rows(12)[1])
        for word in ("Branches 5", "CI", "✗ Tests", ":5173 vite", "Stash 1"):
            self.assertIn(word, text)

    def test_quiet_panels_stay_out(self):
        text = "\n".join(self.rows(12, drop=("ci", "servers"))[1])
        self.assertNotIn("CI", text)
        self.assertNotIn("Servers", text)


if __name__ == "__main__":
    unittest.main()
