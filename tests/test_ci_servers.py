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
    def rows(self, n, drop=(), cols=100):
        comp = compile_config({"preset": "dev", "panels": {"rows": n}})
        data = samples.load("busy", NOW)
        for k in drop:
            data["_panels"][k] = [] if k != "ci" else None
        ctx = Context(data, comp, cols=cols, now=NOW, env={"COLORTERM": "truecolor"}, live=False)
        out = [f.text.plain() for f, ln in zip(render_lines(data, comp, ctx=ctx), comp["lines"]) if "panel" in ln]
        return ctx, out

    def test_every_height_fits(self):
        for n in range(1, 17):
            ctx, rows = self.rows(n)
            self.assertEqual(len(rows), n)
            self.assertTrue(all(len(r) <= ctx.avail for r in rows))

    def test_all_four_at_twelve_rows(self):
        text = "\n".join(self.rows(12)[1])
        for word in ("Branches 5", "CI", "✗ Tests", "Stash 1", "✗ tests 2 failed"):
            self.assertIn(word, text)
        wide = "\n".join(self.rows(12, cols=180)[1])
        for word in ("Sessions 3", "Reviews", ":5173 vite"):                  # the fourth column, given room
            self.assertIn(word, wide)

    def test_quiet_panels_stay_out(self):
        text = "\n".join(self.rows(12, drop=("ci", "servers"))[1])
        self.assertNotIn("CI", text)
        self.assertNotIn("Servers", text)


class ActivityPanelTests(unittest.TestCase):
    """The panels that draw on live activity and on the other sessions."""

    def text(self, show, rows=10, cols=140, drop=()):
        comp = compile_config({"preset": "dev", "panels": {"rows": rows, "show": show}})
        data = samples.load("busy", NOW)
        for k in drop:
            data["_activity"].pop(k, None)
        ctx = Context(data, comp, cols=cols, now=NOW, env={"COLORTERM": "truecolor"}, live=False)
        out = [f.text.plain() for f, ln in zip(render_lines(data, comp, ctx=ctx), comp["lines"]) if "panel" in ln]
        return "\n".join(out)

    def test_claude_edits_are_marked(self):
        text = self.text(["files"])
        self.assertIn("Changes 6 ✻2", text)
        self.assertIn("M ✻src/parser/lexer.py", text)
        self.assertIn(" M src/parser/grammar.py", text)
        self.assertNotIn("✻", self.text(["files"], drop=("edited",)))

    def test_checks(self):
        text = self.text(["checks"])
        self.assertIn("✗ tests 2 failed · 46 passed", text)
        self.assertIn("TestNested::test_quotes_inside_lists", text)
        self.assertIn("test_parser.py:88", text)
        self.assertIn("✓ lint", text)
        self.assertNotIn("Checks", self.text(["files", "checks"], drop=("checks",)))

    def test_sessions(self):
        text = self.text(["sessions"])
        self.assertIn("Sessions 3", text)
        self.assertIn("1 needs you", text)
        lines = [ln for ln in text.split("\n") if ln.strip("⠀ ")]
        self.assertTrue(lines[1].startswith("! api-gateway needs you Bash terraform apply"))
        self.assertTrue(lines[2].startswith("● docs-site"))


class SessionsTests(unittest.TestCase):
    def test_others_skips_itself_the_ended_and_the_stale(self):
        import tempfile
        from claude_statusline import activity as A, sessions
        os.environ["XDG_RUNTIME_DIR"] = tempfile.mkdtemp(prefix="sl-sess-")
        t = 1_800_000_000.0

        def send(sid, name, at, **kw):
            A.record(dict({"hook_event_name": name, "session_id": sid, "cwd": f"/p/{sid}"}, **kw), at)

        send("me", "UserPromptSubmit", t)
        send("busy", "UserPromptSubmit", t - 60)
        send("busy", "PreToolUse", t - 30, tool_name="Bash", tool_use_id="x", tool_input={"command": "make"})
        send("idle", "Stop", t - 600)
        send("asks", "PermissionRequest", t - 5, tool_name="Write", tool_use_id="y", tool_input={"file_path": "/a/b.md"})
        send("gone", "SessionEnd", t - 10)
        send("old", "Stop", t - sessions.MAX_AGE - 10)
        self.assertEqual(sessions.others("me", t), [["asks", "ask", t - 5, "Write b.md"],
                                                    ["busy", "work", t - 60, "Bash make"],
                                                    ["idle", "wait", t - 600, ""]])


class ReviewsTests(unittest.TestCase):
    def test_parse(self):
        from claude_statusline import reviews
        raw = {"search": {"nodes": [
                   {"number": 5, "title": "Old", "url": "u5", "updatedAt": "2026-10-01T00:00:00Z", "isDraft": False,
                    "author": {"login": "a"}, "repository": {"nameWithOwner": "o/x"}},
                   {"number": 9, "title": "New", "url": "u9", "updatedAt": "2026-10-02T00:00:00Z", "isDraft": True,
                    "author": None, "repository": {"nameWithOwner": "o/y"}}, {}]},
               "repository": {"pullRequests": {"nodes": [
                   {"number": 3, "title": "Mine", "url": "u3", "reviewDecision": "CHANGES_REQUESTED",
                    "reviewThreads": {"nodes": [
                        {"isResolved": True, "path": "a.py", "line": 1, "comments": {"nodes": []}},
                        {"isResolved": False, "isOutdated": False, "path": "b.py", "line": 7,
                         "comments": {"nodes": [{"author": {"login": "m"}, "body": "Fix\n  this", "url": "c"}]}}]}}]}}}
        got = reviews.parse(raw)
        self.assertEqual([r[:3] for r in got["asked"]], [["o/y", 9, "New"], ["o/x", 5, "Old"]])
        self.assertEqual(got["mine"][:4], [3, "Mine", "u3", "CHANGES_REQUESTED"])
        self.assertEqual(got["mine"][4], [["b.py", 7, "m", "Fix this", "c", False]])
        self.assertEqual(reviews.parse({"repository": None}), {"mine": None, "asked": []})
        self.assertEqual(reviews.owner_name("git@github.com:o/r.git"), ("o", "r"))
        self.assertIsNone(reviews.owner_name("https://gitlab.com/o/r"))

    def test_panel(self):
        comp = compile_config({"preset": "dev", "panels": {"rows": 8, "show": [["reviews"]]}})
        data = samples.load("busy", NOW)
        ctx = Context(data, comp, cols=120, now=NOW, env={}, live=False)
        text = "\n".join(f.text.plain() for f, ln in zip(render_lines(data, comp, ctx=ctx), comp["lines"])
                         if "panel" in ln)
        for part in ("Reviews", "2 for you", "#1234 changes requested · 2 open", "mona This drops",
                     "lexer.py:42", "api-gateway#87 Rate-limit"):
            self.assertIn(part, text)


class RerunTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from claude_statusline import gitstatus
        os.environ["XDG_RUNTIME_DIR"] = tempfile.mkdtemp(prefix="sl-rerun-")
        self.root = "/home/u/Projects/widget-factory"
        cache, _ = gitstatus._paths(self.root, "ci")
        runs = ci.runs_of([dict(GH[1], databaseId=7, url="https://github.com/o/r/actions/runs/7"), GH[0]])
        gitstatus._save(cache, {"key": "k", "ts": NOW, "data": {"runs": runs, "branch": "b", "stale": False}})
        self.tag = ci.cache_tag(self.root)
        self.spawned = []
        self.real = gitstatus.spawn_detached
        gitstatus.spawn_detached = self.spawned.append

    def tearDown(self):
        from claude_statusline import gitstatus
        gitstatus.spawn_detached = self.real

    def test_two_clicks_and_a_token(self):
        from claude_statusline import menu
        self.assertRaises(ValueError, menu.handle, f"claude-statusline://s1/rerun/ask/{self.tag}/3", NOW)  # running
        self.assertRaises(ValueError, menu.handle, f"claude-statusline://s1/rerun/ask/{self.tag}/99", NOW)
        self.assertRaises(ValueError, menu.handle, "claude-statusline://s1/rerun/now/x/7", NOW)
        self.assertEqual(menu.handle(f"claude-statusline://s1/rerun/ask/{self.tag}/7", NOW), "rerun Tests?")
        self.assertEqual(self.spawned, [])                                  # asking runs nothing
        token = ci.pending("s1", NOW)["token"]
        self.assertRaises(ValueError, menu.handle, "claude-statusline://s1/rerun/yes/guess/-", NOW)
        self.assertIsNone(ci.pending("s1", NOW))                             # a wrong guess spends the question
        menu.handle(f"claude-statusline://s1/rerun/ask/{self.tag}/7", NOW)
        token = ci.pending("s1", NOW)["token"]
        self.assertRaises(ValueError, menu.handle, f"claude-statusline://s1/rerun/yes/{token}/-", NOW + 500)
        menu.handle(f"claude-statusline://s1/rerun/ask/{self.tag}/7", NOW)
        token = ci.pending("s1", NOW)["token"]
        self.assertIn("rerunning", menu.handle(f"claude-statusline://s1/rerun/yes/{token}/-", NOW + 1))
        self.assertEqual(self.spawned[0][1:], ["run", "rerun", "7", "--failed", "--repo", "o/r"])

    def test_the_panel_shows_the_buttons(self):
        comp = compile_config({"preset": "dev", "panels": {"rows": 8, "show": [["ci"]]}})
        data = samples.load("busy", NOW)
        data["_view"] = {}
        ctx = Context(data, comp, cols=100, now=NOW, env={}, live=False)
        text = "\n".join(f.text.plain() for f, ln in zip(render_lines(data, comp, ctx=ctx), comp["lines"])
                         if "panel" in ln)
        self.assertIn("✗ Tests", text)
        self.assertIn("↻ rerun", text)
        data["_rerun"] = {"run": data["_panels"]["ci"]["runs"][0][0], "token": "abc"}
        ctx = Context(data, comp, cols=100, now=NOW, env={}, live=False)
        text = "\n".join(f.text.plain() for f, ln in zip(render_lines(data, comp, ctx=ctx), comp["lines"])
                         if "panel" in ln)
        self.assertIn("rerun? yes no", text)


if __name__ == "__main__":
    unittest.main()
