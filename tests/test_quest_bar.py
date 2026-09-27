"""Claude Quest on the bar: the segments render from the save's snapshot, and the pet behaves."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="quest-bar-")
os.environ["CLAUDE_QUEST_HOME"] = HOME

from claude_statusline.context import Context  # noqa: E402
from claude_statusline.layout import compile_config  # noqa: E402
from claude_statusline.render import render_lines  # noqa: E402
from claude_statusline.segments import quest as Q  # noqa: E402

NOW = 1_800_000_000
ENV = {"COLORTERM": "truecolor"}


def setUpModule():
    os.environ["CLAUDE_QUEST_HOME"] = HOME           # other test modules point it elsewhere


def save(state=None, **view):
    base = {"level": 21, "title": "Veteran", "rank": "Veteran", "xp_in": 500, "xp_need": 2050,
            "class_icon": "🧙", "class": "Shell Sorcerer", "gold": 1234, "bag": 4, "stage": "lizard",
            "gear_sig": "abc", "buffs": [], "boss": None, "daily_done": 1, "daily_total": 3, "streak": 5,
            "weekly": [{"title": "Proving Grounds", "progress": 19, "goal": 22, "done": False}]}
    base.update(view)
    data = {"xp": 20500, "view": base, "last_activity": NOW - 30}
    data.update(state or {})
    with open(os.path.join(HOME, "state.json"), "w") as fh:
        json.dump(data, fh)


def one(name, enabled=True, level=None, cols=200, data=None, **opts):
    raw = {"line": [{"left": [name]}], "style": "minimal", "icons": "unicode",
           "quest": {"enabled": enabled}, "segment": {name: opts} if opts else {}}
    comp = compile_config(raw)
    data = data or {}
    ctx = Context(data, comp, cols=cols, now=NOW, env=ENV, live=False)
    fits = render_lines(data, comp, ctx=ctx)
    return fits[0].text.plain() if fits and fits[0] else ""


class SegmentTests(unittest.TestCase):
    def test_hero(self):
        save()
        out = one("quest")
        for part in ("† Lv 21", "Veteran", "🧙", "500/2,050"):
            self.assertIn(part, out)

    def test_hidden_unless_enabled(self):
        save()
        for name in ("quest", "quest_daily", "quest_gold", "quest_streak"):
            self.assertEqual(one(name, enabled=False), "", name)

    def test_old_save_without_a_snapshot(self):
        with open(os.path.join(HOME, "state.json"), "w") as fh:
            json.dump({"xp": 20500, "school": {"shell": 3}}, fh)
        self.assertIn("Lv 21", one("quest"))

    def test_boss(self):
        save(boss={"icon": "🐍", "name": "Flaky Test Hydra", "hp": 2, "max_hp": 5})
        self.assertEqual(one("quest_boss"), "Ω Flaky Test Hydra ♥♥♡♡♡")
        save(boss={"icon": "🗿", "name": "Linker Lich", "hp": 11, "max_hp": 12})
        self.assertEqual(one("quest_boss"), "Ω Linker Lich ♥ 11/12")
        save()
        self.assertEqual(one("quest_boss"), "")

    def test_dungeon_and_raid_follow_the_project(self):
        here = {"cwd": "/home/me/proj"}
        save(dungeons=[{"project": "other", "number": 9, "name": "Keep of the Rebase", "rooms": 2,
                        "traps": 0, "failing": 0},
                       {"project": "proj", "number": 42, "name": "Crypt of the Nitpick", "rooms": 3,
                        "traps": 1, "failing": 2}],
             raids={"proj": {"name": "Backlog Kraken", "hp": 7, "max_hp": 10, "defeated": False},
                    "done": {"name": "Legacy Behemoth", "hp": 0, "max_hp": 4, "defeated": True}})
        self.assertEqual(one("quest_dungeon", data=here), "Π #42 Crypt of the Nitpick room 3 ✗ 2")
        out = one("quest_raid", data=here, width=0)
        self.assertEqual(out, "Ψ Backlog Kraken 7/10")
        self.assertIn("Backlog Kraken", one("quest_raid", data=here))
        self.assertEqual(one("quest_dungeon", data={"cwd": "/home/me/elsewhere"}), "")
        self.assertEqual(one("quest_raid", data={"cwd": "/x/done"}), "")

    def test_daily_gold_streak_buffs(self):
        save(buffs=[{"icon": "☕", "name": "Cold Brew", "until": NOW + 600},
                    {"icon": "⚡", "name": "Energy", "until": NOW - 1}])
        self.assertEqual(one("quest_daily"), "✓ 1/3 · week 19/22")
        self.assertEqual(one("quest_gold"), "◎ 1,234 · 4 items")
        self.assertEqual(one("quest_streak"), "◆ 5d")
        self.assertEqual(one("quest_buffs"), "▲ ☕10m")
        save(streak=1)
        self.assertEqual(one("quest_streak"), "")

    def test_event_fades(self):
        save({"last_event": {"text": "⬆️ LEVEL UP! You are now level 22", "at": NOW - 5, "kind": "levelup"}})
        self.assertIn("LEVEL UP", one("quest_event"))
        save({"last_event": {"text": "old news", "at": NOW - 600, "kind": "loot"}})
        self.assertEqual(one("quest_event"), "")

    def test_text_pet(self):
        save({"last_tool": NOW - 2})
        out = one("quest_pet")
        self.assertTrue(any(s in out for s in ("(o>", "<o)")))
        save({"last_activity": NOW - 3600})
        self.assertIn("z", one("quest_pet"))

    def test_quest_line_fits(self):
        save(boss={"icon": "🐍", "name": "Off-by-One Ogre", "hp": 1, "max_hp": 3},
             buffs=[{"icon": "☕", "until": NOW + 900}])
        for style in ("minimal", "capsules", "powerline"):
            comp = compile_config({"style": style, "quest": {"enabled": True}})
            for cols in (60, 100, 160, 220):
                ctx = Context({}, comp, cols=cols, now=NOW, env=ENV, live=False)
                for f in render_lines({}, comp, ctx=ctx):
                    if f:
                        self.assertLessEqual(f.text.width, ctx.avail)


class AvatarTests(unittest.TestCase):
    def act(self, **state):
        return Q.pick_action(state, NOW)

    def test_reactions_come_first(self):
        self.assertEqual(self.act(last_event={"at": NOW - 2, "kind": "victory"}), "victory")
        self.assertEqual(self.act(last_event={"at": NOW - 2, "kind": "boss"}), "battle")
        self.assertEqual(self.act(last_event={"at": NOW - 2, "text": "⬆️ LEVEL UP"}), "levelup")

    def test_work_battle_turn_sleep(self):
        self.assertEqual(self.act(last_tool=NOW - 3, last_activity=NOW), "work")
        self.assertEqual(self.act(last_tool=NOW - 3, last_activity=NOW, view={"boss": {"hp": 2}}), "battle")
        self.assertEqual(self.act(last_stop=NOW - 5, last_prompt=NOW - 50, last_activity=NOW - 5), "yourturn")
        self.assertEqual(self.act(last_activity=NOW - 3600), "sleep")
        self.assertEqual(self.act(last_prompt=NOW - 1, last_activity=NOW), "perk")

    def test_idle_rotation_uses_known_actions(self):
        seen = {Q.pick_action({"last_activity": NOW}, NOW + i * 8, ["stand", "look"]) for i in range(40)}
        self.assertEqual(seen, {"stand", "look"})

    def test_placeholder_row(self):
        row = Q.placeholder_row(1, 8, 205)
        text, style = row.spans[0]
        self.assertEqual(row.width, 8)
        self.assertEqual(text[0], Q.PLACEHOLDER)
        self.assertEqual(text[1], Q.DIACRITICS[1])
        self.assertEqual(style[0][3], 205)                          # the image id rides in the colour
        self.assertEqual(row.ansi("truecolor").count("38;5;205"), 1)

    def test_previews_never_touch_terminals(self):
        save()
        comp = compile_config({"quest": {"enabled": True, "avatar": "on"}})
        ctx = Context({}, comp, cols=160, now=NOW, env=ENV, live=False)
        render_lines({}, comp, ctx=ctx)
        self.assertFalse(ctx.avatar_active)


if __name__ == "__main__":
    unittest.main()


class GameModeTests(unittest.TestCase):
    RAW = {"style": "minimal", "icons": "unicode", "quest": {"enabled": True, "placement": "game"}}

    def lines(self, raw=None, cols=120, now=NOW, data=None):
        comp = compile_config(raw or self.RAW)
        self.assertEqual([p for p in comp["problems"] if p[0] == "error"], [])
        data = data or {"cwd": "/home/me/proj", "context_window": {"used_percentage": 42},
                        "rate_limits": {"five_hour": {"used_percentage": 12}, "seven_day": {"used_percentage": 31}}}
        ctx = Context(data, comp, cols=cols, now=now, env=ENV, live=False)
        return ctx, render_lines(data, comp, ctx=ctx)

    def test_layout(self):
        save(boss={"icon": "🐍", "name": "Flaky Test Hydra", "hp": 2, "max_hp": 5, "kind": "test"},
             raids={"proj": {"name": "Backlog Kraken", "hp": 7, "max_hp": 10, "defeated": False}},
             dungeons=[{"project": "proj", "number": 42, "name": "Crypt", "rooms": 3, "traps": 0}])
        for cols in (40, 80, 120, 200):
            ctx, fits = self.lines(cols=cols)
            self.assertEqual(len(fits), 4)
            for f in fits:
                self.assertIsNotNone(f)
                self.assertLessEqual(f.text.width, ctx.avail, (cols, f.text.plain()))
            for f in fits[1:]:
                self.assertEqual(f.text.width, ctx.avail, (cols, f.text.plain()))
        ctx, fits = self.lines()
        text = [f.text.plain() for f in fits]
        self.assertIn("Lv 21", text[0])
        self.assertTrue(text[1].rstrip().endswith("42%"), text[1])
        self.assertTrue(text[2].rstrip().endswith("12%"), text[2])
        self.assertTrue(text[3].rstrip().endswith("31%"), text[3])
        self.assertIn("∫§∫", text[3])                      # the boss stands on the ground
        self.assertIn("▟Π▙", text[2])                      # the dungeon's castle

    def test_rows_hud_and_problems(self):
        save()
        raw = dict(self.RAW, quest={"enabled": True, "placement": "game", "game_rows": 2,
                                    "game_hud": ["context"], "game_hud_width": 0})
        ctx, fits = self.lines(raw)
        self.assertEqual(len(fits), 3)
        self.assertNotIn("42%", fits[1].text.plain())       # no room kept for gauges
        comp = compile_config(dict(self.RAW, quest={"enabled": True, "placement": "game", "game_rows": 0}))
        self.assertIn("quest.game_rows", [p[1] for p in comp["problems"]])

    def test_auto_hud_width_fits_the_gauges(self):
        save()
        for style in ("minimal", "capsules", "powerline"):
            ctx, fits = self.lines(dict(self.RAW, style=style, icons="nerd"))
            self.assertIn("42%", fits[1].text.plain())
            self.assertIn("ctx", fits[1].text.plain(), style)

    def test_hud_keeps_its_look_and_your_options(self):
        comp = compile_config(dict(self.RAW, segment={"context": {"width": 9, "label": "mem",
                                                                  "format": "{bar} {tokens} of {size}"}}))
        spec = next(ln for ln in comp["lines"] if ln.get("scene") == 0)["right"][0]
        self.assertEqual(spec["opts"]["width"], 0)
        self.assertEqual(spec["opts"]["label"], "mem")

    def test_situations(self):
        from claude_statusline import gamemode as G
        now = NOW
        self.assertEqual(G.situation({"last_activity": now - 5000}, now, None), "sleep")
        self.assertEqual(G.situation({"last_tool": now - 2, "last_activity": now}, now, None), "work")
        self.assertEqual(G.situation({"last_tool": now - 2, "last_activity": now}, now, "test"), "battle")
        self.assertEqual(G.situation({"last_event": {"at": now - 1, "kind": "loot"}, "last_activity": now},
                                     now, None), "celebrate")
        self.assertEqual(G.situation({"last_stop": now - 10, "last_tool": now - 60, "last_activity": now},
                                     now, None), "yourturn")
        self.assertEqual(G.situation({"last_activity": now - 100, "last_stop": now - 500}, now, None), "idle")

    def test_each_scene_has_its_own_image_ids(self):
        from claude_statusline import gamemode as G
        a, b = G.slot_of("lizard:x:test:0:0:day:150x3:1"), G.slot_of("lizard:x:test:0:1:day:150x3:1")
        self.assertNotEqual(a, b)                          # the same window, another project: no fight
        self.assertEqual(a, G.slot_of("lizard:x:test:0:0:day:150x3:1"))
        top = G.SCENE_BASE + len(G.SITUATIONS) * G.SLOTS - 1
        self.assertLess(top, Q.IMAGE_BASE)                 # clear of the avatar's ids, within 8 bits

    def test_the_text_world_moves(self):
        save()
        frames = {tuple(f.text.plain() for f in self.lines(now=NOW + t)[1][1:]) for t in range(4)}
        self.assertGreater(len(frames), 1)

    def test_scene_frames_stay_inside_the_picture(self):
        try:
            from claude_statusline.quest.art import scene
        except ImportError:
            self.skipTest("no cairo")
        import struct
        old = os.environ.get("XDG_CACHE_HOME")
        os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="scene-cache-")
        try:
            import importlib
            from claude_statusline.quest.art import avatar
            importlib.reload(avatar)
            importlib.reload(scene)
            scene.LOOK = ("drake", {"form": "storm"})
            scene.PARTY = 3
            w, h = 400, 63
            for sit in scene.SITUATIONS:
                bg, patches, gap = scene.frames_for(sit, w, h, "night", "lint", True, True)
                self.assertTrue(patches and gap > 0, sit)
                with open(bg, "rb") as fh:
                    self.assertEqual(struct.unpack(">II", fh.read()[16:24]), (w, h))
                for x, path in patches:
                    with open(path, "rb") as fh:
                        pw, ph = struct.unpack(">II", fh.read()[16:24])
                    self.assertTrue(0 <= x and x + pw <= w and ph == h, (sit, x, pw))
            # Drawn again (another window's uploader, say), each file is replaced, never rewritten
            # in place: kitty may be reading the old one, and a file shrinking under it kills kitty.
            before = {p: os.stat(p).st_ino for p in [bg] + [p for _, p in patches]}
            os.remove(os.path.join(os.path.dirname(bg), "index.json"))
            with open(bg, "rb") as held:
                old_bytes = held.read()
                scene.frames_for(sit, w, h, "night", "lint", True, True)
                held.seek(0)
                self.assertEqual(held.read(), old_bytes)
            for p, ino in before.items():
                self.assertNotEqual(os.stat(p).st_ino, ino, p)
            self.assertFalse([f for f in os.listdir(os.path.dirname(bg)) if f.endswith(".tmp")])
            r, wfd = os.pipe()
            scene.upload(wfd, 231, bg, patches[:2], gap, 40, 3)
            os.close(wfd)
            sent = os.read(r, 1 << 20)
            self.assertIn(b"a=f,i=231,f=100,x=", sent)
            self.assertIn(b"c=1,z=", sent)
            self.assertNotIn(b"m=1", sent)                  # never chunked: kitty reads the files
            self.assertIn(b",t=f;", sent)
            self.assertIn(b"a=a,i=231,r=1,z=-1", sent)
        finally:
            if old is None:
                os.environ.pop("XDG_CACHE_HOME", None)
            else:
                os.environ["XDG_CACHE_HOME"] = old


class PartySceneTests(unittest.TestCase):
    def test_the_text_world_draws_the_party(self):
        save(party=[{"type": "Explore", "role": "scout"}, {"type": "Plan", "role": "strategist"}],
             state={"last_tool": NOW - 2, "last_activity": NOW})
        comp = compile_config({"style": "minimal", "icons": "unicode", "quest": {"enabled": True, "placement": "game"}})
        ctx = Context({}, comp, cols=120, now=NOW, env=ENV, live=False)
        ground = render_lines({}, comp, ctx=ctx)[-1].text.plain()
        self.assertTrue("o>" in ground or "<o" in ground, ground)
        self.assertTrue("ô>" in ground or "<ô" in ground, ground)
        save()
        ground = render_lines({}, comp, ctx=Context({}, comp, cols=120, now=NOW, env=ENV, live=False))[-1].text.plain()
        self.assertNotIn("ô", ground)

    def test_the_scene_switches_only_to_a_complete_picture(self):
        from claude_statusline import gamemode as G, gitstatus
        runtime = tempfile.mkdtemp(prefix="scene-ready-")
        old_rt, old_spawn = os.environ.get("XDG_RUNTIME_DIR"), gitstatus.spawn_detached
        os.environ["XDG_RUNTIME_DIR"] = runtime
        spawned = []
        gitstatus.spawn_detached = lambda argv: spawned.append(argv) or True
        try:
            ctx = Context({}, compile_config({}), cols=120, now=NOW, env=ENV, live=True)
            terms = {"/dev/pts/9": 4242}
            self.assertIsNone(G._ensure_scene(ctx, terms, 100, 3, "drake:x:-:0:0:day:0", []))   # nothing ready
            argv = spawned[-1]
            ready, key = argv[argv.index("--ready") + 1], argv[argv.index("--key") + 1]
            with open(ready, "w") as fh:
                fh.write(key)                                      # the uploader finished
            first = G._ensure_scene(ctx, terms, 100, 3, "drake:x:-:0:0:day:0", [])
            self.assertEqual(first[1], 100)
            second = G._ensure_scene(ctx, terms, 100, 3, "drake:x:-:0:0:day:2", [])  # the party grows
            self.assertEqual(second, first)                         # the old picture until the new one is in
            self.assertEqual(len(spawned), 2)
        finally:
            gitstatus.spawn_detached = old_spawn
            if old_rt is None:
                os.environ.pop("XDG_RUNTIME_DIR", None)
            else:
                os.environ["XDG_RUNTIME_DIR"] = old_rt
