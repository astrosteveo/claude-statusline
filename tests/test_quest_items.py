"""Every Claude Quest item is well formed, and every piece of art draws."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_statusline.quest import items  # noqa: E402

HAT_KINDS = {"pumpkin", "paper", "beanie", "headphones", "goggles", "crown", "helm", "wizard", "halo"}
HAND_KINDS = {"sword", "duck", "pointer", "stick", "wand", "staff", "hammer"}
BACK_KINDS = {"cape", "wings", "backpack"}
FEET_KINDS = {"boots", "sneakers", "socks"}
USE_KEYS = {"buff", "minutes", "icon", "xp", "gamble", "treat", "guarantee", "streak", "crate",
            "reroll", "banish"}
FX_KEYS = set(items.FX_TEXT)


class ItemDatabaseTests(unittest.TestCase):
    def test_gear_is_drawable(self):
        kinds = {"head": HAT_KINDS, "hand": HAND_KINDS, "back": BACK_KINDS, "feet": FEET_KINDS,
                 "charm": {"amulet"}}
        for item in items.ITEMS.values():
            if item["kind"] != "gear":
                continue
            self.assertIn(item["slot"], items.SLOTS, item["id"])
            self.assertIn(item["visual"]["kind"], kinds[item["slot"]], item["id"])
            self.assertTrue(set(item["fx"]) <= FX_KEYS, item["id"])

    def test_consumables_do_something(self):
        for item in items.ITEMS.values():
            if item["kind"] == "consumable":
                self.assertTrue(set(item["use"]) <= USE_KEYS, item["id"])
                self.assertTrue(items.use_lines(item["use"]), item["id"])

    def test_every_rarity_can_drop(self):
        for rarity in items.RARITIES:
            self.assertTrue(items.droppable(rarity), rarity)

    def test_sets(self):
        for set_id, spec in items.SETS.items():
            slots = [items.ITEMS[p]["slot"] for p in spec["pieces"]]
            self.assertEqual(len(slots), len(set(slots)), f"{set_id} needs one piece per slot")
            for piece in spec["pieces"]:
                self.assertEqual(items.ITEMS[piece].get("set"), set_id)
            self.assertIn(len(spec["pieces"]), spec["bonus"])

    def test_names_resolve(self):
        for item in items.ITEMS.values():
            self.assertEqual(items.by_name(item["name"]), item["id"])
        self.assertEqual(items.by_name("the Sacred `--force-with-lease`"), "force_with_lease")
        self.assertEqual(items.by_name("a Half-Eaten Cookie (session)"), "cookie")


class ArtSmokeTests(unittest.TestCase):
    def test_every_action_renders(self):
        try:
            from claude_statusline.quest.art import avatar
        except ImportError as e:  # no cairo
            self.skipTest(str(e))
        for stage in ("egg", "hatchling", "lizard", "drake", "wyrm"):
            for gear in ({}, avatar.SAMPLE_GEAR):
                for action in avatar.ACTIONS:
                    avatar.render(stage, action, 3, 88, 81, gear)

    def test_every_gear_visual_renders(self):
        try:
            from claude_statusline.quest.art import avatar
        except ImportError as e:
            self.skipTest(str(e))
        for item in items.ITEMS.values():
            if item["kind"] == "gear":
                gear = {item["slot"]: item["visual"]}
                avatar.render("lizard", "look", 0, 88, 81, gear)
                avatar.render("lizard", "stand", 0, 88, 81, gear)
                avatar.render("hatchling", "battle", 0, 88, 81, gear)


if __name__ == "__main__":
    unittest.main()
