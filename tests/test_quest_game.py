"""The Claude Quest game: bosses, progression, quests, items, streaks, saves, hooks."""
import json
import os
import random
import sys
import tempfile
import unittest
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["CLAUDE_QUEST_QUIET"] = "1"
QUEST_HOME = os.environ["CLAUDE_QUEST_HOME"] = tempfile.mkdtemp(prefix="quest-test-")


def setUpModule():
    os.environ["CLAUDE_QUEST_HOME"] = QUEST_HOME     # other test modules point it elsewhere

from claude_statusline.quest import boss, effects, items, quests, rules, state, view  # noqa: E402
from claude_statusline.quest.game import Game, GameError, git_subcommands, streak_of  # noqa: E402

NOON = datetime(2026, 9, 25, 12, 0).timestamp()


def new_state(**over):
    s = state.migrate({"xp": 50_000, "created": "2026-01-01T00:00:00"})
    s.update(over)
    return s


def game(s=None, now=NOON, seed=1):
    g = Game(s or new_state(), now=now, rng=random.Random(seed))
    g.tick()
    return g


def bash(cmd, *, failed=False, out="", cwd="/home/me/proj"):
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": cwd, "session_id": "s"}
    if failed:
        ev["error"] = f"Exit code 1\n{out}"
    else:
        ev["tool_response"] = {"stdout": out, "stderr": "", "interrupted": False}
    return ev


class ClassifyTests(unittest.TestCase):
    def test_runners(self):
        cases = {
            "pytest -q": "test", "python -m pytest tests": "test", "npm test": "test",
            "npm run test -- --watch=false": "test", "cd app && pnpm vitest run": "test",
            "cd app && npx vitest run": "test", "cargo test": "test", "go test ./...": "test",
            "FOO=1 uv run pytest": "test", "make test": "test", "tsc --noEmit": "build",
            "npm run build": "build", "cargo build --release": "build", "make": "build",
            "eslint src": "lint", "ruff check .": "lint", "cargo clippy": "lint",
            "grep -rn pytest .": None, "echo npm test": None, "git commit -m 'fix tests'": None,
            "ls && pytest -x | tail -5": "test",
        }
        for cmd, want in cases.items():
            self.assertEqual(boss.classify(cmd), want, cmd)

    def test_failure_counts(self):
        self.assertEqual(boss.count_failures("===== 2 failed, 3 passed in 0.2s ====="), 2)
        self.assertEqual(boss.count_failures("Tests:       4 failed, 10 passed, 14 total"), 4)
        self.assertEqual(boss.count_failures("FAILED (failures=2, errors=1)"), 3)
        self.assertEqual(boss.count_failures("Found 7 errors in 3 files."), 7)
        self.assertEqual(boss.count_failures("test result: FAILED. 8 passed; 1 failed; 0 ignored"), 1)
        self.assertEqual(boss.count_failures("--- FAIL: TestA\n--- FAIL: TestB\nFAIL\tpkg"), 3)
        self.assertEqual(boss.count_failures("10 passed, 0 failed"), 0)
        self.assertIsNone(boss.count_failures("all good"))

    def test_git_subcommands(self):
        self.assertEqual(list(git_subcommands("git add -A && git commit -m x")), ["add", "commit"])
        self.assertEqual(list(git_subcommands("git -C repo push origin main")), ["push"])
        self.assertEqual(list(git_subcommands("echo git commit")), [])


class BossTests(unittest.TestCase):
    def test_fight(self):
        g = game()
        g.tool(bash("pytest", failed=True, out="3 failed, 5 passed"), failed=True)
        b = g.s["boss"]
        self.assertEqual((b["hp"], b["max_hp"], b["kind"], b["project"]), (3, 3, "test", "proj"))
        g.tool(bash("pytest", failed=True, out="1 failed, 7 passed"), failed=True)
        self.assertEqual(g.s["boss"]["hp"], 1)
        bag = len(g.s["bag"])
        g.tool(bash("pytest", out="8 passed"))
        self.assertIsNone(g.s["boss"])
        self.assertEqual(g.s["counters"]["bosses"], 1)
        self.assertGreater(len(g.s["bag"]), bag)          # guaranteed drop
        self.assertIn("first_boss", g.s["achievements"])
        self.assertNotIn("clean_kill", g.s["achievements"])

    def test_clean_kill_and_piped_failures(self):
        g = game()
        g.tool(bash("pytest | tail -3", out="2 failed, 1 passed"))  # exit 0, but failing
        self.assertIsNotNone(g.s["boss"])
        g.tool(bash("pytest", out="3 passed"))
        self.assertIsNone(g.s["boss"])
        self.assertIn("clean_kill", g.s["achievements"])

    def test_other_project_does_not_count(self):
        g = game()
        g.tool(bash("pytest", failed=True, out="2 failed"), failed=True)
        g.tool(bash("pytest", out="ok", cwd="/elsewhere/other"))
        self.assertIsNotNone(g.s["boss"])

    def test_escape(self):
        s = new_state()
        g = game(s)
        g.tool(bash("tsc", failed=True, out="Found 2 errors"), failed=True)
        g2 = game(s, now=NOON + 25 * 3600)
        self.assertIsNone(g2.s["boss"])

    def test_banish(self):
        g = game()
        g.tool(bash("cargo build", failed=True, out="error: could not compile due to 4 previous errors"),
               failed=True)
        g.grant("self_fixing_bug", "test")
        g.use("bug that fixed")
        self.assertIsNone(g.s["boss"])
        self.assertEqual(g.s["counters"]["bosses"], 1)


class ProgressionTests(unittest.TestCase):
    def test_xp_multipliers(self):
        s = new_state()
        g = game(s)
        e = g.grant("excalibash", "test")
        g.equip("excalibash")
        before = s["xp"]
        g.gain_xp(100, school="shell")
        self.assertEqual(s["xp"] - before, 125)
        g.gain_xp(100, school="read")
        self.assertEqual(s["xp"] - before, 225)
        self.assertTrue(e)

    def test_set_bonus_and_title(self):
        g = game()
        for i in ("wizard_hat", "dotfiles_robe", "excalibash"):
            g.grant(i, "test")
            g.equip(items.ITEMS[i]["name"])
        self.assertIn("Archwizard of the Shell", g.s["titles"])
        self.assertAlmostEqual(g.fx["xp_shell"], 0.2 + 0.1 + 0.25 + 0.1 + 0.3)

    def test_level_up_pays_gold(self):
        s = new_state(xp=rules.xp_for_level(10) - 1)
        g = game(s)
        g.gain_xp(5)
        self.assertEqual(g.level(), 10)
        self.assertEqual(s["gold"], 200)
        self.assertIn("lvl10", s["achievements"])

    def test_commit_rewards(self):
        g = game()
        before = g.s["xp"]
        g.tool(bash("git add . && git commit -m 'feat'"))
        self.assertEqual(g.s["counters"]["commits"], 1)
        self.assertEqual(g.s["xp"] - before, rules.XP_BY_TOOL["Bash"] + rules.COMMIT_XP)
        g.tool(bash("git commit -m 'nothing'", failed=True, out="nothing to commit"), failed=True)
        self.assertEqual(g.s["counters"]["commits"], 1)


class QuestTests(unittest.TestCase):
    def test_daily_rollover_and_completion(self):
        s = new_state()
        g = game(s)
        self.assertEqual(len(s["daily"]["quests"]), 3)
        q = s["daily"]["quests"][0]
        gold = s["gold"]
        g.bump(q["counter"], q["goal"])
        self.assertTrue(q["done"])
        self.assertGreater(s["gold"], gold)
        self.assertEqual(s["counters"]["quests_done"], 1)
        # a new day brings new quests
        g2 = game(s, now=NOON + 86400)
        self.assertNotEqual(s["daily"]["date"], "2026-09-25")
        self.assertTrue(all(not q["done"] for q in s["daily"]["quests"]))
        self.assertTrue(g2)

    def test_reroll_once(self):
        g = game()
        old = g.s["daily"]["quests"][1]["id"]
        g.reroll(1)
        self.assertNotEqual(g.s["daily"]["quests"][1]["id"], old)
        with self.assertRaises(GameError):
            g.reroll(1)


class ItemTests(unittest.TestCase):
    def test_buff_stacks_duration(self):
        g = game()
        g.grant("cold_brew", "t")
        g.grant("cold_brew", "t")
        g.use("cold brew")
        g.use("cold brew")
        self.assertEqual(len(g.s["buffs"]), 1)
        self.assertEqual(round((g.s["buffs"][0]["until"] - NOON) / 60), 60)
        self.assertAlmostEqual(g.fx["xp"], 1.0)
        later = game(g.s, now=NOON + 3601)
        self.assertEqual(later.s["buffs"], [])

    def test_guarantee(self):
        g = game()
        g.grant("first_try_regex", "t")
        g.use("regex")
        item = g.roll_loot(1.0)
        self.assertGreaterEqual(items.rarity_rank(items.ITEMS[item["id"]]["rarity"]), 2)

    def test_sell_and_forge(self):
        g = game()
        for _ in range(6):
            g.grant("bent_semicolon", "t")
        g.sell("dupes")
        self.assertEqual(sum(1 for e in g.s["bag"] if e["id"] == "bent_semicolon"), 1)
        self.assertEqual(g.s["gold"], 50)
        for i in ("paper_hat", "beanie", "cookie", "stale_cache"):
            g.grant(i, "t")
        new = g.forge("common")
        self.assertEqual(new["rarity"], "uncommon")
        self.assertEqual(sum(1 for e in g.s["bag"] if items.ITEMS[e["id"]]["rarity"] == "common"), 0)

    def test_forge_skips_worn_gear(self):
        g = game()
        for i in ("paper_hat", "beanie", "cookie", "stale_cache", "rubber_duck"):
            g.grant(i, "t")
        g.equip("duck")
        with self.assertRaises(GameError):
            g.forge("common")

    def test_shop(self):
        s = new_state(gold=1000)
        g = game(s)
        stock = g.shop_stock()
        self.assertEqual(len(stock), 5)
        self.assertEqual(stock, game(s).shop_stock())  # same all day
        item = g.buy("1")
        self.assertTrue(g.owns(item["id"]))
        with self.assertRaises(GameError):
            g.buy("1")

    def test_find(self):
        g = game()
        g.grant("rubber_duck", "t")
        g.grant("regex_wand", "t")
        self.assertEqual(g.find("duck")[0]["id"], "rubber_duck")
        with self.assertRaises(GameError):
            g.find("zzz")
        self.assertEqual(g.find("1")[0]["id"], "regex_wand")  # uncommon sorts first


class StreakTests(unittest.TestCase):
    def test_streak_and_restore(self):
        s = new_state(days=["2026-09-20", "2026-09-21", "2026-09-22"])
        g = game(s)
        g.record_day()
        self.assertEqual(g.streak(), 1)
        self.assertEqual(s["broken_streak"]["length"], 3)
        g.grant("reflog_scroll", "t")
        g.use("reflog")
        self.assertEqual(g.streak(), 6)

    def test_streak_counts_yesterday(self):
        from datetime import date
        self.assertEqual(streak_of(["2026-09-23", "2026-09-24"], date(2026, 9, 25)), 2)


class MigrationTests(unittest.TestCase):
    def test_v1_loot(self):
        old = {"xp": 100, "commits": 4, "agents": 2,
               "loot": [{"item": "a Rubber Duck (squeaks)", "rarity": "common", "at": "x"},
                        {"item": "the Sacred `--force-with-lease`", "rarity": "legendary", "at": "y"},
                        {"item": "Boots of Fast-Forward Merge", "rarity": "uncommon", "at": "z"}]}
        s = state.migrate(old)
        self.assertEqual([e["id"] for e in s["bag"]], ["rubber_duck", "force_with_lease", "ff_boots"])
        self.assertEqual(s["counters"]["commits"], 4)
        self.assertNotIn("loot", s)
        self.assertEqual(state.migrate(s)["bag"], s["bag"])

    def test_view(self):
        g = game()
        g.grant("halo", "t")
        g.equip("halo")
        v = view.build(g.s, NOON)
        self.assertEqual(v["gear"]["head"]["kind"], "halo")
        json.dumps(v)


class HookTests(unittest.TestCase):
    def test_roundtrip(self):
        from claude_statusline.quest import hooks
        msg = hooks.handle({"hook_event_name": "SessionStart", "source": "startup", "session_id": "x"})
        self.assertIn("CLAUDE QUEST", msg)
        hooks.handle(bash("pytest", failed=True, out="2 failed") | {"hook_event_name": "PostToolUseFailure"})
        saved = state.load_readonly()
        self.assertEqual(saved["boss"]["hp"], 2)
        self.assertEqual(saved["view"]["boss"]["hp"], 2)


if __name__ == "__main__":
    unittest.main()
