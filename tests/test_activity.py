"""Live activity: hook events folded into a per-session file, and the segments that draw it."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import tomllib
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
RUNTIME = tempfile.mkdtemp(prefix="sl-live-")

from claude_statusline import activity as A, samples, settings  # noqa: E402
from claude_statusline.context import Context  # noqa: E402
from claude_statusline.decor import LOOKS  # noqa: E402
from claude_statusline.layout import compile_config  # noqa: E402
from claude_statusline.render import render_lines, render_spec  # noqa: E402

NOW = 1_800_000_000.0
ENV = {"COLORTERM": "truecolor"}


def ev(name, **kw):
    return dict({"hook_event_name": name, "session_id": "s1", "permission_mode": "default"}, **kw)


def tool(name, tid, phase="PreToolUse", agent=None, **ti):
    e = ev(phase, tool_name=name, tool_use_id=tid, tool_input=ti)
    if agent:
        e["agent_id"] = agent
    return e


def run_events(events, start=NOW):
    s = A.fresh()
    for i, e in enumerate(events):
        A.apply(s, e, start + i)
    return s


class ApplyTests(unittest.TestCase):
    def test_a_tool_runs_then_finishes(self):
        s = run_events([ev("UserPromptSubmit"), tool("Bash", "t1", command="npm test\nmore")])
        self.assertEqual(s["tools"]["t1"][:2], ["Bash", "npm test"])
        A.apply(s, tool("Bash", "t1", "PostToolUse"), NOW + 5)
        self.assertEqual(s["tools"], {})
        self.assertEqual(s["recent"][-1][:4], ["Bash", "npm test", NOW + 5, True])
        A.apply(s, tool("Bash", "t2", "PostToolUseFailure"), NOW + 6)
        self.assertFalse(s["recent"][-1][3])

    def test_an_end_that_arrives_first_wins(self):
        s = run_events([tool("Read", "t1", "PostToolUse", file_path="/a/b.py"), tool("Read", "t1", file_path="/a/b.py")])
        self.assertEqual(s["tools"], {})                         # the late start is ignored
        self.assertEqual(s["recent"][-1][1], "b.py")

    def test_targets(self):
        self.assertEqual(A.target("Edit", {"file_path": "/x/y/render.py"}), "render.py")
        self.assertEqual(A.target("Grep", {"pattern": "fit_"}), "fit_")
        self.assertEqual(A.target("WebFetch", {"url": "https://docs.example.com/a/b"}), "docs.example.com")
        self.assertEqual(A.target("mcp__github__create_issue", {}), "github")
        self.assertEqual(A.tool_label("mcp__github__create_issue"), "create_issue")
        self.assertEqual(A.target("Nope", None), "")

    def test_subagents_and_their_tools(self):
        s = run_events([ev("UserPromptSubmit"),
                        tool("Agent", "a1", description="Find the parser", subagent_type="Explore"),
                        ev("SubagentStart", agent_id="ag1", agent_type="Explore"),
                        tool("Grep", "g1", agent="ag1", pattern="parse"),
                        ev("Stop")])
        self.assertEqual(s["agents"]["ag1"][0], "Explore")
        self.assertEqual(s["agents"]["ag1"][2], "Find the parser")          # the Agent call's description
        self.assertEqual(s["agents"]["ag1"][3:], ["Grep", "parse"])
        self.assertIn("g1", s["tools"])                               # the main thread's stop leaves it running
        A.apply(s, ev("SubagentStop", agent_id="ag1", agent_type="Explore"), NOW + 10)
        self.assertEqual(s["agents"], {})
        self.assertNotIn("g1", s["tools"])

    def test_turns_compaction_mode_and_failure(self):
        s = run_events([ev("UserPromptSubmit", permission_mode="plan"), ev("PreCompact", trigger="auto", permission_mode="plan")])
        self.assertEqual(s["mode"], "plan")
        self.assertTrue(s["compact"][0] and not s["compact"][1])
        A.apply(s, ev("PostCompact", trigger="auto"), NOW + 5)
        self.assertEqual(s["compactions"], 1)
        A.apply(s, ev("StopFailure", error_type="rate_limit"), NOW + 6)
        self.assertEqual((s["turn"], s["failed"]), (0.0, "rate_limit"))
        A.apply(s, ev("UserPromptSubmit"), NOW + 7)
        self.assertEqual(s["failed"], "")

    def test_tasks_from_every_source(self):
        s = run_events([ev("TaskCreated", task_id="1", task_subject="Write tests"),
                        ev("TaskCreated", task_id="2", task_subject="Fix parser"),
                        tool("TaskUpdate", "u1", "PostToolUse", taskId="2", status="in_progress"),
                        ev("TaskCompleted", task_id="1", task_subject="Write tests")])
        self.assertEqual(s["tasks"], {"1": ["Write tests", "completed"], "2": ["Fix parser", "in_progress"]})
        todo = tool("TodoWrite", "w1", "PostToolUse", todos=[{"content": "a", "status": "completed"},
                                                              {"content": "b", "status": "pending"}])
        A.apply(s, todo, NOW + 9)
        self.assertEqual(list(s["tasks"].values()), [["a", "completed"], ["b", "pending"]])

    def test_things_that_never_end_expire(self):
        s = run_events([tool("Bash", "t1"), ev("SubagentStart", agent_id="x", agent_type="Plan")])
        A.apply(s, ev("Notification"), NOW + A.AGENT_EXPIRES + 1)
        self.assertEqual((s["tools"], s["agents"]), ({}, {}))
        self.assertFalse(A.apply(s, ev("SessionEnd"), NOW + 2))


class RecordedTests(unittest.TestCase):
    """A real session's events (claude -p, one Read, a Bash, an Explore subagent), replayed."""

    def events(self):
        with open(os.path.join(HERE, "fixtures", "activity-session.jsonl")) as fh:
            return [json.loads(line) for line in fh]

    def test_replay(self):
        events = self.events()
        names = [e["hook_event_name"] for e in events]
        s = A.fresh()
        seen = []
        for i, e in enumerate(events[:-1]):
            A.apply(s, e, NOW + i)
            seen.append((e["hook_event_name"], len(s["tools"]), len(s["agents"])))
        self.assertIn(("SubagentStart", 2, 1), seen)            # the Bash and the Agent call still running
        stop = names.index("Stop")
        self.assertEqual(seen[stop][2], 1)                      # the subagent works on after the reply
        self.assertEqual(s["agents"], {})                       # ... and is gone once it stops
        self.assertEqual(s["tools"], {})
        self.assertEqual(s["mode"], "bypassPermissions")
        self.assertFalse(A.apply(s, events[-1], NOW + 99))      # SessionEnd


class FileTests(unittest.TestCase):
    def setUp(self):
        os.environ["XDG_RUNTIME_DIR"] = RUNTIME

    def test_concurrent_hooks_lose_nothing(self):
        sid = "race"
        events = [dict(tool("Read", f"t{i}", file_path=f"/f{i}"), session_id=sid) for i in range(30)]
        threads = [threading.Thread(target=A.record, args=(e, NOW + i)) for i, e in enumerate(events)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(A.load(sid)["tools"]), 30)
        A.record(ev("SessionEnd", session_id=sid), NOW + 50)
        self.assertIsNone(A.load(sid))
        self.assertFalse(os.path.exists(A.path(sid)))

    def test_session_ids_cannot_escape_the_directory(self):
        self.assertEqual(os.path.dirname(A.path("../../etc/x")), os.path.dirname(A.path("s")))


class SegmentTests(unittest.TestCase):
    LIVE = {"turn": -72, "mode": "bypassPermissions",
            "tools": [["Bash", "npm test -- --watch=false --coverage", -40, ""], ["Read", "x.py", -1, ""]],
            "recent": [["Read", "a", -30, True, ""], ["Read", "b", -20, True, ""], ["Edit", "c", -15, True, ""],
                       ["Bash", "d", -14, False, ""]],
            "agents": [["Explore", -80, "Find the parser entry points", "Grep", "fit_"],
                       ["Plan", -20, "Design the cache", "", ""]],
            "tasks": [["Write the tests", "completed"], ["Fix the parser", "in_progress"], ["Docs", "pending"]]}

    def one(self, name, live, level=0):
        comp = compile_config({"line": [{"left": [name]}], "style": "minimal", "icons": "unicode"})
        data = {"_activity": live}
        ctx = Context(data, comp, cols=200, now=NOW, env=ENV, live=False)
        seg = render_spec(comp["lines"][0]["left"][0], ctx, level)
        return seg.body.plain() if seg else None

    def test_each_segment(self):
        self.assertEqual(self.one("tools", self.LIVE), "Bash npm test -- --watch=false --cov… 40s +1 ✗ Bash · ✓ Edit · ✓ Read ×2")
        self.assertEqual(self.one("tools", self.LIVE, 3), "Bash 40s +1")
        self.assertEqual(self.one("agents", self.LIVE), "Explore Find the parser entry p… 1m20s · Plan Design the cache 20s")
        self.assertEqual(self.one("agents", self.LIVE, 3), "2 agents")
        self.assertEqual(self.one("tasks", self.LIVE), "Fix the parser 1/3")
        self.assertEqual(self.one("turn", self.LIVE), "working 1m12s")
        self.assertEqual(self.one("mode", self.LIVE), "bypass")
        self.assertEqual(self.one("turn", {"stop": -700}), "waiting 11m")
        self.assertEqual(self.one("turn", {"stop": -5, "failed": "rate_limit"}), "stopped: rate limited")
        self.assertEqual(self.one("turn", {"turn": -5, "compacting": True}), "compacting 5s")
        self.assertIsNone(self.one("mode", {"mode": "default"}))
        self.assertIsNone(self.one("tools", {"stop": -5, "recent": [["Read", "a", -30, True, ""]]}))

    def test_nothing_without_the_hooks(self):
        comp = compile_config({"line": [{"left": A_SEGMENTS}]})
        ctx = Context({"session_id": "no-such"}, comp, cols=200, now=NOW, env=ENV, live=False)
        self.assertEqual(render_lines({"session_id": "no-such"}, comp, ctx=ctx), [None])

    def test_placement(self):
        auto = compile_config({"activity": {"enabled": True}})
        self.assertEqual(len(auto["lines"]), len(compile_config({})["lines"]) + 1)
        self.assertEqual([s["name"] for s in auto["lines"][-1]["left"] + auto["lines"][-1]["right"]], A_SEGMENTS)
        own = compile_config({"activity": {"enabled": True}, "line": [{"left": ["model", "tools"]}]})
        self.assertEqual([s["name"] for s in own["lines"][0]["left"]], ["model", "tools"])
        manual = compile_config({"activity": {"enabled": True, "placement": "manual"}})
        self.assertEqual(manual["lines"], compile_config({})["lines"])
        game = compile_config({"activity": {"enabled": True}, "quest": {"enabled": True, "placement": "game"}})
        self.assertIn("tools", [s["name"] for s in game["lines"][0]["details"]])
        self.assertIn("activity.placement", [p[1] for p in compile_config(
            {"activity": {"placement": "everywhere"}})["problems"]])

    def test_fits_everywhere(self):
        data = dict(samples.load("busy", NOW), _activity=self.LIVE)
        for style in LOOKS:
            for icons in ("nerd", "unicode", "emoji", "none"):
                comp = compile_config({"activity": {"enabled": True}, "style": style, "icons": icons})
                for cols in (40, 70, 100, 140, 200):
                    ctx = Context(data, comp, cols=cols, now=NOW, env=ENV, live=False)
                    for f in render_lines(data, comp, ctx=ctx):
                        if f:
                            self.assertLessEqual(f.text.width, ctx.avail, (style, icons, cols))


A_SEGMENTS = ["turn", "tools", "agents", "tasks", "mode"]


class SwitchTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="sl-live-home-")
        self.claude = os.path.join(self.home, ".claude")
        os.makedirs(self.claude)
        with open(os.path.join(self.claude, "settings.json"), "w") as fh:
            json.dump({"hooks": {"PostToolUse": [{"matcher": "*", "hooks": [{"type": "command",
                                                                            "command": "my-own-hook"}]}]}}, fh)
        with open(os.path.join(self.claude, "statusline.py"), "w") as fh:
            fh.write("# stand-in\n")
        self.env = dict(os.environ, HOME=self.home, CLAUDE_CONFIG_DIR=self.claude,
                        XDG_CONFIG_HOME=os.path.join(self.home, ".config"), XDG_RUNTIME_DIR=self.home,
                        CLAUDE_STATUSLINE_CONFIG="")

    def run_(self, *args, stdin=None):
        p = subprocess.run([sys.executable, "-S", os.path.join(ROOT, "statusline.py"), *args], capture_output=True,
                           text=True, env=self.env, input=stdin)
        return p.returncode, p.stdout, p.stderr

    def test_enable_hook_disable(self):
        code, out, err = self.run_("activity", "enable")
        self.assertEqual(code, 0, err)
        with open(os.path.join(self.claude, "settings.json")) as fh:
            s = json.load(fh)
        ours = [h for ev in s["hooks"].values() for e in ev for h in e["hooks"] if "activity hook" in h["command"]]
        self.assertEqual(len(ours), len(A.EVENTS))
        self.assertTrue(all(h["async"] for h in ours))
        self.assertTrue(settings.activity_hooks_present(s))
        self.assertIn("my-own-hook", json.dumps(s))
        with open(os.path.join(self.home, ".config", "claude-statusline", "config.toml"), "rb") as fh:
            self.assertTrue(tomllib.load(fh)["activity"]["enabled"])
        event = json.dumps(tool("Bash", "t1", command="make test"))
        code, out, err = self.run_("activity", "hook", stdin=event)
        self.assertEqual((code, out), (0, ""), err)
        runtime = os.path.join(self.home, "claude-statusline")
        self.assertTrue(any(f.startswith("activity-s1") for f in os.listdir(runtime)))
        code, out, _ = self.run_("doctor")
        self.assertIn("hooks registered", out.split("activity", 1)[1])
        code, out, err = self.run_("activity", "disable")
        self.assertEqual(code, 0, err)
        with open(os.path.join(self.claude, "settings.json")) as fh:
            self.assertNotIn("activity hook", fh.read())
        self.assertFalse(any(f.startswith("activity-") for f in os.listdir(runtime)))
        self.run_("activity", "hook", stdin=event)                   # off means off
        self.assertFalse(any(f.startswith("activity-") for f in os.listdir(runtime)))


if __name__ == "__main__":
    unittest.main()
