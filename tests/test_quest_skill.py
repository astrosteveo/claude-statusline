"""The claude-quest skill, /quest's routing of requests, and the best-gear search."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
QUEST_HOME = tempfile.mkdtemp(prefix="quest-skill-")

from claude_statusline.quest import cli, skill  # noqa: E402
from claude_statusline.quest import state as store  # noqa: E402
from claude_statusline.quest.game import Game  # noqa: E402


def setUpModule():
    os.environ["CLAUDE_QUEST_HOME"] = QUEST_HOME
    os.environ["CLAUDE_QUEST_QUIET"] = "1"


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


class SkillTests(unittest.TestCase):
    def test_plugin_copy_is_in_step(self):
        with open(os.path.join(ROOT, "skills", "claude-quest", "SKILL.md")) as fh:
            self.assertEqual(fh.read(), skill.text(skill.PLUGIN_CMD),
                             "regenerate skills/claude-quest/SKILL.md from claude_statusline/quest/skill.py")

    def test_every_command_it_names_exists(self):
        for word in ("bag", "inspect", "best", "equip", "unequip", "use", "sell", "forge", "shop", "buy", "quests",
                     "reroll", "boss", "dungeons", "raid", "pet", "titles", "title", "achievements", "log", "guide"):
            self.assertIn(f"$Q {word}" if word in ("bag", "inspect", "best", "shop", "quests", "boss") else word,
                          skill.TEXT)
            self.assertIn(word, cli.COMMANDS)


class RouteTests(unittest.TestCase):
    def test_a_game_command_runs(self):
        code, out = run("route", "guide")
        self.assertEqual(code, 0)
        self.assertNotIn("REQUEST:", out)

    def test_words_become_a_request_with_the_sheet(self):
        code, out = run("route", "equip", "my", "best", "gear")    # a command that fails on words
        self.assertTrue(out.startswith("REQUEST: equip my best gear"))
        code, out = run("route", "equip", "nothing")                # a short one shows the game's answer
        self.assertNotIn("REQUEST:", out)
        code, out = run("route", "what", "should", "I", "buy?")
        self.assertTrue(out.startswith("REQUEST: what should I buy?"))
        self.assertIn("CLAUDE QUEST", out)


class BestTests(unittest.TestCase):
    def setUp(self):
        with store.Locked() as s:
            s.clear()
            s.update(store.fresh())
            g = Game(s)
            g.tick()
            for item in ("paper_hat", "wizard_hat", "dotfiles_robe", "excalibash", "blade_green_ci"):
                g.grant(item, "a test", found=False)
            s["counters"]["shell"] = 5000
            g.equip("Paper Hat from the Standup")
            g.finish()

    def test_finds_and_wears_the_shell_set(self):
        code, out = run("best")
        self.assertIn("← change", out)
        run("best", "equip")
        with store.Locked() as s:
            worn = {slot: next(e["id"] for e in s["bag"] if e["uid"] == uid) for slot, uid in s["equipped"].items()}
        self.assertEqual(worn, {"head": "wizard_hat", "back": "dotfiles_robe", "hand": "excalibash"})
        code, out = run("best")
        self.assertIn("already wearing your best gear", out)


class ToolTests(unittest.TestCase):
    """The MCP server: the protocol, and each tool on a save of its own."""

    def setUp(self):
        BestTests.setUp(self)

    def rpc(self, *msgs):
        from claude_statusline.quest import mcp
        out = io.StringIO()
        mcp.serve(io.StringIO("".join(json.dumps(m) + "\n" for m in msgs)), out)
        return [json.loads(line) for line in out.getvalue().splitlines()]

    def tool(self, name, **args):
        r = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}})
        res = r[0]["result"]
        return json.loads(res["content"][0]["text"]), res["isError"]

    def test_handshake_and_list(self):
        r = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                     {"jsonrpc": "2.0", "method": "notifications/initialized"},
                     {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                     {"jsonrpc": "2.0", "id": 3, "method": "nope"})
        self.assertEqual([m["id"] for m in r], [1, 2, 3])
        self.assertEqual(r[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual({t["name"] for t in r[1]["result"]["tools"]},
                         {"quest_status", "quest_bag", "quest_shop", "quest_best_gear", "quest_act"})
        self.assertIn("error", r[2])

    def test_reads(self):
        st, err = self.tool("quest_status")
        self.assertFalse(err)
        self.assertEqual(st["worn"]["head"]["id"], "paper_hat")
        bag, _ = self.tool("quest_bag", kind="gear")
        self.assertIn("wizard_hat", [i["id"] for i in bag["items"]])
        shop, _ = self.tool("quest_shop")
        self.assertEqual(len(shop["stock"]), 5)

    def test_best_gear_then_act(self):
        best, _ = self.tool("quest_best_gear", equip=True)
        self.assertTrue(best["equipped"])
        self.assertGreater(best["xp_gain_percent"], 0)
        st, _ = self.tool("quest_status")
        self.assertEqual(st["worn"]["hand"]["id"], "excalibash")
        out, err = self.tool("quest_act", action="equip", target="blade_green_ci")
        self.assertFalse(err)
        self.assertTrue(out["messages"])
        out, err = self.tool("quest_act", action="buy", target="99")
        self.assertTrue(err)
        self.assertIn("error", out)


if __name__ == "__main__":
    unittest.main()
