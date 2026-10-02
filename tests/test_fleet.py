"""The fleet map: what it keeps of agentboard's snapshot, and how it lays out the stars."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from claude_statusline import fleet, samples  # noqa: E402
from claude_statusline.context import Context  # noqa: E402
from claude_statusline.layout import compile_config  # noqa: E402
from claude_statusline.render import render_lines  # noqa: E402

NOW = 1_790_400_000                     # 2026-09-26T05:20:00Z
REPO = {"root": "/p/void-sector", "name": "void-sector", "statusAt": "2026-09-26T05:19:59.25088052-05:00"}
SNAP = {"rows": [
    {"key": "a", "sessionId": "a", "kind": "background", "repo": REPO, "cwd": "/p/void-sector/wt",
     "title": "Godot migration", "section": "needs", "sectionSince": "2026-09-26T05:10:00Z",
     "activity": "permission prompt", "ask": {"kind": "permission", "tool": "Bash", "text": "rm -rf build"}},
    {"key": "b", "sessionId": "b", "kind": "background", "repo": REPO, "cwd": "/p/void-sector",
     "title": "Godot migration", "forkOf": {"key": "a"}, "section": "settled",
     "sectionSince": "2026-09-26T04:20:00.123456789Z"},
    {"key": "c", "sessionId": "me", "kind": "interactive", "entrypoint": "cli", "cwd": "/p/scratch",
     "window": {"kind": "kitty", "id": "55"}, "title": "Fleet map", "section": "working",
     "sectionSince": "2026-09-26T00:19:00-05:00", "activity": "Bash: make test",
     "flags": ["tree"], "subagents": [{"id": "x", "label": "Build installer", "type": "general-purpose"}]},
    {"key": "d", "sessionId": "d", "kind": "interactive", "entrypoint": "claude-desktop", "cwd": "/p/notes/",
     "title": "Notes", "section": "turn", "sectionSince": "2026-09-26T05:00:00Z", "activity": "Which one?"},
]}


class RowsTests(unittest.TestCase):
    def test_keeps_what_the_map_draws_in_queue_order(self):
        rs = fleet.rows(SNAP)
        self.assertEqual([r["key"] for r in rs], ["a", "d", "c", "b"])
        a, d, c, b = rs
        self.assertEqual((a["project"], a["what"], a["where"]), ("void-sector", "rm -rf build", "bg"))
        self.assertEqual((c["project"], c["where"], c["agents"], c["flags"]),
                         ("scratch", "kitty 55", ["Build installer"], ["tree"]))
        self.assertEqual((d["project"], d["where"]), ("notes", "app"))
        self.assertTrue(b["fork"])
        self.assertEqual(c["since"], NOW - 60)              # an offset time
        self.assertAlmostEqual(b["since"], NOW - 3600 + 0.123456, places=5)   # nine digits of fraction


SNAP2 = {"windowMs": 3_600_000, "rows": SNAP["rows"] + [
    {"key": "f", "sessionId": "f", "kind": "background", "repo": REPO, "title": "Godot migration (2)",
     "forkOf": {"key": "gone", "title": "Godot migration"}, "section": "needs",
     "sectionSince": "2026-09-26T05:15:00Z", "activity": "failed", "state": "failed"},
    {"key": "g", "sessionId": "g", "kind": "background", "repo": REPO, "title": "Nightly build", "state": "failed",
     "section": "needs", "sectionSince": "2026-09-26T05:19:00Z", "activity": "failed", "contextPct": 92},
], "events": [
    {"session": "c", "kind": "tool", "tool": "Bash", "at": "2026-09-26T05:19:58Z", "text": "Bash: make"},
    {"session": "c", "kind": "tool", "tool": "Edit", "at": "2026-09-26T05:10:00Z", "text": "Edit: x"},
    {"session": "c", "kind": "prompt", "at": "2026-09-26T05:00:00Z", "text": "go"},
]}


class FleetFeatureTests(unittest.TestCase):
    def test_forks_merge_and_failed_jobs_wait_below_asks(self):
        rs = fleet.rows(SNAP2)
        self.assertEqual([r["key"] for r in rs], ["a", "g", "d", "c", "b"])
        a = rs[0]
        self.assertEqual((a["count"], a["sids"], a["since"]), (2, ["a", "f"], NOW - 300))   # joined by title
        self.assertTrue(rs[1]["failed"])
        c = next(r for r in rs if r["key"] == "c")
        self.assertEqual(c["ticks"], [NOW - 600, NOW - 2])                    # tool calls only
        self.assertEqual(c["flare"], [NOW - 2, "Bash"])

    def text(self, cols=140, rows=14, now=NOW, snap=SNAP2):
        comp = compile_config({"preset": "fleet", "panels": {"rows": rows}})
        data = samples.load("busy", NOW)
        data["session_id"] = "me"
        data["_panels"] = {"fleet": {"rows": fleet.rows(snap), "at": NOW, "src": "web", "window": 3600}}
        data["_view"] = {}                                                    # a sample: links as if clicks were on
        ctx = Context(data, comp, cols=cols, now=now, env={"COLORTERM": "truecolor"}, live=False)
        fits = render_lines(data, comp, ctx=ctx)
        out = [x.text for x, ln in zip(fits, comp["lines"]) if "panel" in ln]
        self.assertEqual(len(out), rows)
        self.assertTrue(all(t.width <= ctx.avail for t in out))
        return "\n".join(t.plain() for t in out), out

    def test_map_marks_counts_meters_motion_and_flares(self):
        text, _ = self.text()
        self.assertIn("Fleet 6 · 3 need you", text)                          # sessions, not rows
        self.assertIn("! Godot migration ×2", text)
        self.assertIn("✗ Nightly build", text)
        self.assertIn("▰▰▰▰ 92%", text)
        self.assertIn("⚡Bash", text)
        self.assertNotIn("⚡Bash", self.text(now=NOW + 30)[0])                 # the flare fades
        self.assertNotEqual(self.text(now=NOW + 1)[0], text)                  # the working glyph turns

    def test_timeline_fills_the_spare_rows(self):
        text, _ = self.text(cols=200, rows=14)
        self.assertIn("Activity 60m", text)
        lane = next(ln for ln in text.split("\n") if "Fleet map" in ln and ("▁" in ln or "█" in ln))
        self.assertTrue(lane.rstrip().endswith("█"))                          # the newest call, at the right

    def test_every_width_keeps_the_height(self):
        for cols in (60, 120, 200):
            for rows in (4, 10, 20):
                self.text(cols=cols, rows=rows)

    def test_links(self):
        _, out = self.text()
        links = {s[3] for t in out for _, s in t.spans if s and len(s) > 3 and s[3]}
        self.assertIn("claude-statusline://me/focus/c", links)                # a terminal session: its window
        self.assertIn("http://localhost:7777/#/queue/session/g/conversation", links)   # background: its page


class FocusClickTests(unittest.TestCase):
    def test_parse(self):
        from claude_statusline import menu
        self.assertEqual(menu.parse("claude-statusline://me/focus/abc-1")[1:], ("focus", ["abc-1"]))
        with self.assertRaises(ValueError):
            menu.parse("claude-statusline://me/focus/a;b")
        self.assertEqual(menu.parse("claude-statusline://me/attach/1fb37cf5")[1:], ("attach", ["1fb37cf5"]))
        with self.assertRaises(ValueError):
            menu.parse("claude-statusline://me/attach/a/b")


class _Done:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


class AttachTests(unittest.TestCase):
    def test_a_background_session_with_an_id_attaches(self):
        snap = {"rows": [dict(SNAP["rows"][0], id="1fb37cf5"), SNAP["rows"][3]]}
        a, d = fleet.rows(snap)
        self.assertEqual((a["bg"], d["bg"]), ("1fb37cf5", None))      # a desktop session can't be attached
        bad = fleet.rows({"rows": [dict(SNAP["rows"][0], id="a;b")]})[0]
        self.assertIsNone(bad["bg"])
        for state in ("done", "failed", "stopped"):                     # attaching would start it again
            self.assertIsNone(fleet.rows({"rows": [dict(SNAP["rows"][0], id="1fb37cf5", state=state)]})[0]["bg"])

    def test_links(self):
        rows = [dict(r, id="1fb37cf5") if r["key"] == "a" else r for r in SNAP2["rows"]]
        _, out = FleetFeatureTests.text(self, snap=dict(SNAP2, rows=rows))
        links = {s[3] for t in out for _, s in t.spans if s and len(s) > 3 and s[3]}
        self.assertIn("claude-statusline://me/attach/1fb37cf5", links)
        self.assertIn("claude-statusline://me/focus/c", links)
        self.assertIn("http://localhost:7777/#/queue/session/d/conversation", links)   # the desktop app: its page

    def test_opens_a_tab_in_the_focused_kitty(self):
        calls = []

        def run(argv):
            calls.append(argv)
            if argv[4] == "ls":
                return _Done(stdout='[{"is_focused": %s}]' % ("true" if argv[3] == "unix:/tmp/k-2" else "false"))
            return _Done()
        did = fleet.attach("1fb37cf5", run=run, sockets=["unix:/tmp/k-1", "unix:/tmp/k-2"])
        self.assertEqual(did, "attached 1fb37cf5 in a new kitty tab")
        launch = calls[-1]
        self.assertEqual(launch[2:5], ["--to", "unix:/tmp/k-2", "launch"])
        self.assertIn("--type=tab", launch)
        self.assertEqual(launch[-2:], ["attach", "1fb37cf5"])

    def test_says_why_it_could_not(self):
        with self.assertRaisesRegex(ValueError, "listen_on"):
            fleet.attach("1fb37cf5", run=lambda a: _Done(), sockets=[])
        with self.assertRaisesRegex(ValueError, "remote control is disabled"):
            fleet.attach("1fb37cf5", run=lambda a: _Done(returncode=1, stderr="Error: remote control\nis disabled"),
                         sockets=["unix:/tmp/k-1"])
        with self.assertRaises(ValueError):
            fleet.attach("-rf", run=lambda a: _Done(), sockets=["unix:/tmp/k-1"])

    def test_finds_kitty_sockets_as_kitty_names_them(self):
        d = tempfile.mkdtemp(prefix="sl-kitty-")
        conf = os.path.join(d, "kitty.conf")
        with open(conf, "w") as fh:
            fh.write(f"allow_remote_control socket-only\nlisten_on unix:{d}/kitty\n")
        open(os.path.join(d, "kitty-42"), "w").close()
        env = os.environ.pop("KITTY_LISTEN_ON", None)
        try:
            self.assertEqual(fleet._kitty_sockets(conf, pids=["42", "43"]), [f"unix:{d}/kitty-42"])
            os.environ["KITTY_LISTEN_ON"] = "unix:/tmp/kitty-7"
            self.assertEqual(fleet._kitty_sockets(conf, pids=["42"]), ["unix:/tmp/kitty-7"])
        finally:
            os.environ.pop("KITTY_LISTEN_ON", None)
            if env is not None:
                os.environ["KITTY_LISTEN_ON"] = env


class PayloadTests(unittest.TestCase):
    def test_saved_private_and_at_most_every_five_seconds(self):
        os.environ["XDG_RUNTIME_DIR"] = tempfile.mkdtemp(prefix="sl-pay-")
        fleet.save_payload({"session_id": "x", "_panels": {}}, now=100)
        path = fleet.payload_path()
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        import json
        with open(path) as fh:
            self.assertEqual(json.load(fh), {"session_id": "x"})
        os.utime(path, (200, 200))
        fleet.save_payload({"session_id": "y"}, now=202)
        with open(path) as fh:
            self.assertEqual(json.load(fh), {"session_id": "x"})


class MapTests(unittest.TestCase):
    def text(self, f, cols=140, rows=12):
        comp = compile_config({"preset": "fleet", "panels": {"rows": rows}})
        data = samples.load("busy", NOW)
        data["session_id"] = "me"
        data["_panels"] = {"fleet": f}
        ctx = Context(data, comp, cols=cols, now=NOW, env={"COLORTERM": "truecolor"}, live=False)
        out = [x.text.plain() for x, ln in zip(render_lines(data, comp, ctx=ctx), comp["lines"]) if "panel" in ln]
        self.assertEqual(len(out), rows)
        self.assertTrue(all(len(r) <= ctx.avail for r in out))
        return "\n".join(out)

    def test_stars_and_orbits(self):
        text = self.text({"rows": fleet.rows(SNAP), "at": NOW})
        self.assertIn("Fleet 4 · 1 need you · 1 your turn · 1 working", text)
        self.assertIn("★ void-sector 2", text)
        self.assertIn("├ ! Godot migration rm -rf build", text)
        self.assertIn("└ ◌ ⑂ Godot migration", text)        # never prompted
        self.assertIn(" Fleet map ◂ here ⚠tree Bash: make test", text)
        self.assertIn("◦ Build installer", text)
        self.assertNotIn("off the map", text)

    def test_narrow_and_short_says_what_is_left_out(self):
        text = self.text({"rows": fleet.rows(SNAP), "at": NOW}, cols=60, rows=6)
        self.assertIn("off the map", text)

    def test_before_the_first_answer_and_without_agentboard(self):
        self.assertIn("Asking agentboard", self.text(None))
        self.assertIn("agentboard isn't installed", self.text({"missing": True}))

    def test_draws_outside_a_repository(self):
        os.environ["XDG_RUNTIME_DIR"] = tempfile.mkdtemp(prefix="sl-fleet-")
        comp = compile_config({"preset": "fleet", "panels": {"rows": 4}})
        data = {"session_id": "me", "cwd": tempfile.mkdtemp(prefix="sl-nogit-"), "model": {"display_name": "Opus"}}
        data["workspace"] = {"current_dir": data["cwd"]}
        ctx = Context(data, comp, cols=100, now=NOW, env={}, live=False)
        out = [x.text.plain() for x, ln in zip(render_lines(data, comp, ctx=ctx), comp["lines"]) if "panel" in ln]
        self.assertIn("Asking agentboard", "\n".join(out))


if __name__ == "__main__":
    unittest.main()
