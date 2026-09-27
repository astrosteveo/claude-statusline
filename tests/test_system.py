"""Everything that touches files: TOML edits, settings.json, git, the CLI, migration, Quest on/off."""
import json
import os
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from claude_statusline import gitstatus, settings, tomlw  # noqa: E402
from claude_statusline.migrate import migrate  # noqa: E402

ENTRY = os.path.join(ROOT, "statusline.py")


def run(*args, env=None, stdin=None):
    e = dict(os.environ, **(env or {}))
    p = subprocess.run([sys.executable, "-S", ENTRY, *args], capture_output=True, text=True, env=e, input=stdin)
    return p.returncode, p.stdout, p.stderr


class TomlTests(unittest.TestCase):
    TEXT = """# my config
theme = "nord"   # cold

[bar]
width = 10       # keep

[[line]]
left = ["model"]

[segment.dir]
depth = 2
"""

    def test_set_preserves_everything_else(self):
        out = tomlw.set_key(self.TEXT, "theme", "dracula")
        self.assertIn('theme = "dracula"  # cold', out)
        self.assertIn("# my config", out)
        out = tomlw.set_key(out, "bar.width", 13)
        self.assertIn("width = 13  # keep", out)
        out = tomlw.set_key(out, "segment.dir.mode", "base")
        out = tomlw.set_key(out, "quest.enabled", True)
        out = tomlw.set_key(out, "style", "pills")
        data = tomllib.loads(out)
        self.assertEqual(data["theme"], "dracula")
        self.assertEqual(data["style"], "pills")
        self.assertEqual(data["segment"]["dir"], {"depth": 2, "mode": "base"})
        self.assertEqual(data["quest"], {"enabled": True})
        self.assertEqual(data["line"], [{"left": ["model"]}])

    def test_unset(self):
        out = tomlw.set_key(self.TEXT, "segment.dir.depth", None)
        self.assertNotIn("depth", out)
        self.assertEqual(tomlw.set_key("", "a.b", None), "")

    def test_empty_file(self):
        self.assertEqual(tomllib.loads(tomlw.set_key("", "quest.enabled", True)), {"quest": {"enabled": True}})
        self.assertEqual(tomllib.loads(tomlw.set_key("", "theme", "x")), {"theme": "x"})

    def test_dumps_roundtrip(self):
        cfg = {"theme": "nord", "style": "chips", "line": [{"left": ["a", "b"], "right": ["c"], "gap": 1}],
               "segment": {"x": {"type": "text", "text": 'q"uote # hash', "n": 1.5}},
               "bar": {"width": 9, "pulse": True}, "quest": {"enabled": False}, "colors": {"accent": "#ffffff"}}
        self.assertEqual(tomllib.loads(tomlw.dumps(cfg, header="# hi")), cfg)


class SettingsTests(unittest.TestCase):
    def test_quest_hooks_replace_legacy_ones(self):
        data = {"hooks": {
            "PostToolUse": [{"matcher": "*", "hooks": [
                {"type": "command", "command": "python3 ~/.claude/quest/quest.py hook", "timeout": 5},
                {"type": "command", "command": "my-own-hook"}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "python3 ~/.claude/quest/quest.py hook"}]}]}}
        self.assertEqual(settings.strip_quest_hooks(data), 2)
        self.assertEqual(data["hooks"]["PostToolUse"][0]["hooks"], [{"type": "command", "command": "my-own-hook"}])
        self.assertNotIn("Stop", data["hooks"])
        settings.add_quest_hooks(data)
        self.assertTrue(settings.quest_hooks_present(data))
        self.assertEqual(settings.strip_quest_hooks(data), len(settings.HOOK_EVENTS))
        self.assertFalse(settings.quest_hooks_present(data))
        self.assertEqual(data["hooks"]["PostToolUse"][0]["hooks"][0]["command"], "my-own-hook")


class QuestSwitchTests(unittest.TestCase):
    """quest enable / disable in a throwaway home."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="sl-home-")
        claude = os.path.join(self.home, ".claude")
        os.makedirs(claude)
        with open(os.path.join(claude, "settings.json"), "w") as fh:
            json.dump({"theme": "dark", "hooks": {"Stop": [{"hooks": [
                {"type": "command", "command": "python3 ~/.claude/quest/quest.py hook"}]}]}}, fh)
        with open(os.path.join(claude, "statusline.py"), "w") as fh:
            fh.write("# stand-in\n")
        self.env = {"HOME": self.home, "CLAUDE_CONFIG_DIR": claude, "XDG_CONFIG_HOME": os.path.join(self.home, ".config"),
                    "XDG_RUNTIME_DIR": self.home, "CLAUDE_QUEST_HOME": os.path.join(claude, "quest"),
                    "CLAUDE_STATUSLINE_CONFIG": ""}
        self.claude = claude

    def settings(self):
        with open(os.path.join(self.claude, "settings.json")) as fh:
            return json.load(fh)

    def test_enable_then_disable(self):
        code, out, err = run("quest", "enable", env=self.env)
        self.assertEqual(code, 0, err)
        s = self.settings()
        self.assertEqual(s["theme"], "dark")
        cmds = [h["command"] for ev in s["hooks"].values() for e in ev for h in e["hooks"]]
        self.assertEqual(len(cmds), len(settings.HOOK_EVENTS))
        self.assertTrue(all("statusline.py quest hook" in c for c in cmds))
        self.assertTrue(os.path.exists(os.path.join(self.claude, "commands", "quest.md")))
        cfg = os.path.join(self.home, ".config", "claude-statusline", "config.toml")
        with open(cfg, "rb") as fh:
            self.assertTrue(tomllib.load(fh)["quest"]["enabled"])
        self.assertTrue(any(f.startswith("settings.json.bak-") for f in os.listdir(self.claude)))

        # the hook plays the game only while it is on
        event = json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "thanks!", "session_id": "s"})
        code, out, err = run("quest", "hook", env=dict(self.env, CLAUDE_QUEST_QUIET="1"), stdin=event)
        self.assertEqual(code, 0, err)
        save = os.path.join(self.claude, "quest", "state.json")
        self.assertTrue(os.path.exists(save))

        code, out, err = run("quest", "disable", env=self.env)
        self.assertEqual(code, 0, err)
        self.assertNotIn("hooks", self.settings())
        self.assertFalse(os.path.exists(os.path.join(self.claude, "commands", "quest.md")))
        with open(cfg, "rb") as fh:
            self.assertFalse(tomllib.load(fh)["quest"]["enabled"])
        self.assertTrue(os.path.exists(save))                          # the save is kept
        mtime = os.stat(save).st_mtime
        time.sleep(0.02)
        run("quest", "hook", env=dict(self.env, CLAUDE_QUEST_QUIET="1"), stdin=event)
        self.assertEqual(os.stat(save).st_mtime, mtime)                 # off means off

    def test_bad_settings_are_left_alone(self):
        path = os.path.join(self.claude, "settings.json")
        with open(path, "w") as fh:
            fh.write("{ not json")
        code, out, _ = run("quest", "enable", env=self.env)
        self.assertEqual(code, 1)
        self.assertIn("not valid JSON", out)
        with open(path) as fh:
            self.assertEqual(fh.read(), "{ not json")


class GitTests(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="sl-git-")
        g = ["git", "-C", self.repo, "-c", "user.email=a@b", "-c", "user.name=t"]
        subprocess.run(g[:3] + ["init", "-q", "-b", "trunk"], check=True)
        with open(os.path.join(self.repo, "a.txt"), "w") as fh:
            fh.write("a\n")
        subprocess.run(g + ["add", "a.txt"], check=True)
        subprocess.run(g + ["commit", "-q", "-m", "one"], check=True)
        with open(os.path.join(self.repo, "a.txt"), "a") as fh:
            fh.write("b\n")
        with open(os.path.join(self.repo, "new.txt"), "w") as fh:
            fh.write("n\n")
        os.makedirs(os.path.join(self.repo, "sub", "deep"))
        os.environ["XDG_RUNTIME_DIR"] = self.repo

    def tearDown(self):
        os.environ.pop("XDG_RUNTIME_DIR", None)

    def test_find_and_head(self):
        root, gitdir, common = gitstatus.find_repo(os.path.join(self.repo, "sub", "deep"))
        self.assertEqual(os.path.realpath(root), os.path.realpath(self.repo))
        self.assertEqual(gitstatus.read_head(gitdir), ("trunk", None))
        self.assertIsNone(gitstatus.find_repo("/"))

    def test_sync_status_and_cache(self):
        cfg = {"enabled": True, "cache_ttl": 60.0}
        g = gitstatus.status(self.repo, cfg, sync=True)
        self.assertEqual((g["branch"], g["dirty"], g["untracked"], g["staged"]), ("trunk", 1, 1, 0))
        self.assertIsNone(g["upstream"])
        again = gitstatus.status(self.repo, cfg, sync=False)          # fresh cache: no refresh needed
        self.assertEqual(again["dirty"], 1)
        self.assertFalse(again.get("pending"))

    def test_async_first_render_shows_the_branch(self):
        g = gitstatus.status(self.repo, {"enabled": True, "cache_ttl": 2.0}, sync=False)
        self.assertEqual(g["branch"], "trunk")
        self.assertTrue(g.get("pending"))
        deadline = time.time() + 5
        while time.time() < deadline:                                  # the background refresh lands
            g = gitstatus.status(self.repo, {"enabled": True, "cache_ttl": 60.0}, sync=False)
            if not g.get("pending"):
                break
            time.sleep(0.05)
        self.assertEqual(g["dirty"], 1)

    def test_worktree(self):
        wt = os.path.join(tempfile.mkdtemp(), "wt")
        subprocess.run(["git", "-C", self.repo, "worktree", "add", "-q", "-b", "side", wt], check=True)
        root, gitdir, common = gitstatus.find_repo(wt)
        self.assertEqual(gitstatus.read_head(gitdir)[0], "side")
        self.assertNotEqual(gitdir, common)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="sl-cli-")
        self.cfg = os.path.join(self.dir, "config.toml")
        self.env = {"CLAUDE_STATUSLINE_CONFIG": self.cfg, "XDG_RUNTIME_DIR": self.dir, "COLUMNS": "120",
                    "CLAUDE_QUEST_HOME": os.path.join(self.dir, "quest")}

    def test_render_stdin(self):
        payload = json.dumps({"model": {"display_name": "Opus 5"}, "cwd": "/tmp"})
        code, out, err = run(env=self.env, stdin=payload)
        self.assertEqual(code, 0)
        self.assertIn("Opus 5", out)
        code, out, _ = run(env=self.env, stdin="this is not json")
        self.assertEqual(code, 0)
        self.assertTrue(out.strip())                                   # never blank

    def test_set_get_unset_validate(self):
        self.assertEqual(run("set", "theme", "nord", env=self.env)[0], 0)
        self.assertEqual(run("set", "segment.dir.depth", "2", env=self.env)[0], 0)
        self.assertEqual(run("get", "theme", env=self.env)[1].strip(), '"nord"')
        self.assertEqual(run("get", "segment.dir.depth", env=self.env)[1].strip(), "2")
        code, out, _ = run("set", "theme", "nrod", env=self.env)
        self.assertEqual(code, 1)
        self.assertIn("did you mean 'nord'", out)
        self.assertEqual(run("unset", "segment.dir.depth", env=self.env)[0], 0)
        code, out, _ = run("validate", env=self.env)
        self.assertEqual(code, 0, out)
        with open(self.cfg, "a") as fh:
            fh.write('\n[segment.bogus]\nx = 1\n')
        self.assertEqual(run("validate", env=self.env)[0], 1)

    def test_galleries_and_catalog(self):
        for args in (["preview", "--width", "80,120", "--plain"], ["themes", "--plain"], ["styles", "--plain"],
                     ["icons"], ["bars", "--plain"], ["segments"], ["segments", "git"], ["presets"],
                     ["doctor"], ["version"], ["help"], ["ruler"], ["preview", "--json"]):
            code, out, err = run(*args, env=self.env)
            self.assertEqual(code, 0, (args, err))
            self.assertTrue(out.strip(), args)
        code, out, _ = run("nosuch", env=self.env)
        self.assertEqual(code, 2)

    def test_catalog_in_sync(self):
        with open(os.path.join(ROOT, "skills", "design", "reference", "catalog.md")) as fh:
            on_disk = fh.read()
        self.assertEqual(run("segments", "--markdown", env=self.env)[1], on_disk,
                         "run `make catalog` to regenerate the skill's catalog")


class HotPathTests(unittest.TestCase):
    """A refresh must not import modules that cost more than drawing the bar."""

    HEAVY = ("json", "re", "random", "subprocess", "tomllib", "argparse", "hashlib", "shutil")

    def test_refresh_imports(self):
        d = tempfile.mkdtemp(prefix="sl-hot-")
        cfg = os.path.join(d, "config.toml")
        with open(cfg, "w") as fh:
            fh.write('style = "capsules"\n[quest]\nenabled = true\n[[line]]\n'
                     'left = ["model", "dir", "git", "pr", "cache", "cost", "burn", "tokens", "env", "session"]\n'
                     'right = ["heartbeat", "clock"]\n[[line]]\nleft = ["context"]\n'
                     'right = ["limit_5h", "limit_7d", "limit_7d_model", "limit_spend"]\n')
        qhome = os.path.join(d, "quest")
        os.makedirs(qhome)
        with open(os.path.join(qhome, "state.json"), "w") as fh:
            json.dump({"xp": 5000, "view": {"level": 11, "xp_in": 10, "xp_need": 100, "boss": {"name": "x", "hp": 1,
                                                                                            "max_hp": 2}}}, fh)
        env = {"CLAUDE_STATUSLINE_CONFIG": cfg, "XDG_RUNTIME_DIR": d, "CLAUDE_QUEST_HOME": qhome, "COLUMNS": "150"}
        with open(os.path.join(ROOT, "claude_statusline", "samples", "hot.json")) as fh:
            payload = fh.read()
        run(env=env, stdin=payload)                                    # compile and cache the config
        p = subprocess.run([sys.executable, "-S", "-X", "importtime", ENTRY], input=payload, capture_output=True,
                           text=True, env=dict(os.environ, **env))
        imported = {line.split("|")[-1].strip() for line in p.stderr.splitlines() if "|" in line}
        self.assertTrue(p.stdout.strip())
        for mod in self.HEAVY:
            self.assertNotIn(mod, imported, f"{mod} is imported on every refresh")


class MigrateTests(unittest.TestCase):
    def test_v2_config_with_avatar_rows(self):
        raw = {"line": [{"left": ["model"], "right": ["heartbeat", "avatar0"]},
                        {"left": ["quest_daily"], "right": ["quest", "avatar1"]}],
               "segment": {"avatar0": {"type": "avatar", "row": 0}, "avatar1": {"type": "avatar", "row": 1},
                           "dir": {"depth": 2}},
               "bar": {"width": 16, "empty": "█", "style": "block"},
               "colors": {"dim": "38;5;240", "accent": "#ff0000"}, "glyphs": {"model": "◆", "git": "G"},
               "features": {"pace": False, "heartbeat": False}}
        new, changes = migrate(raw)
        self.assertEqual(new["line"][0]["right"], [])
        self.assertEqual(new["line"][1]["right"], ["quest"])
        self.assertNotIn("avatar0", new["segment"])
        self.assertEqual(new["quest"], {"enabled": True, "avatar": "auto"})
        self.assertEqual(new["bar"], {"width": 16, "style": "smooth"})
        self.assertEqual(new["colors"], {"accent": "#ff0000"})
        self.assertEqual(new["glyphs"], {"git": "G"})
        self.assertFalse(new["segment"]["limit_5h"]["pace"])
        self.assertNotIn("features", new)
        self.assertTrue(changes)
        from claude_statusline.layout import compile_config
        self.assertEqual([p for p in compile_config(new)["problems"] if p[0] == "error"], [])
        self.assertEqual(migrate(new)[1], [])                          # idempotent


if __name__ == "__main__":
    unittest.main()
