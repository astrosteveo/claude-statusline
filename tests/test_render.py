"""Configs compile, segments render, lines fit, and the bar never breaks."""
import os
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["CLAUDE_QUEST_HOME"] = tempfile.mkdtemp(prefix="quest-render-")

from claude_statusline import config, samples  # noqa: E402
from claude_statusline.context import Context, resolve_look  # noqa: E402
from claude_statusline.decor import LOOKS  # noqa: E402
from claude_statusline.fit import LEVELS  # noqa: E402
from claude_statusline.layout import compile_config, list_presets  # noqa: E402
from claude_statusline.render import fallback, render, render_lines  # noqa: E402
from claude_statusline.themes import THEMES  # noqa: E402

NOW = 1_790_400_000
ENV = {"COLORTERM": "truecolor", "TERM": "xterm-256color"}
HOSTILE = {"model": 5, "cwd": ["x"], "context_window": {"used_percentage": "NaN", "context_window_size": -3},
           "cost": "lots", "rate_limits": [{"window": "five_hour", "used_percentage": 250}, 7],
           "pr": {"number": True}, "session_name": {"a": 1}, "vim": {"mode": None}, "worktree": "yes",
           "effort": {"level": ["x"]}, "prompt_cache": {"warm": "maybe", "hit_ratio": "high"},
           "workspace": {"current_dir": 7, "repo": "r"}, "exceeds_200k_tokens": "yes"}


def lines_of(raw, data, cols=160, env=ENV):
    comp = compile_config(raw)
    ctx = Context(data, comp, cols=cols, now=NOW, env=env, live=False, sync_git=True)
    return ctx, [f for f in render_lines(data, comp, ctx=ctx)]


def plain(raw, data, cols=160, env=ENV):
    return [f.text.plain() if f else None for f in lines_of(raw, data, cols, env)[1]]


class CompileTests(unittest.TestCase):
    def problems(self, raw):
        return compile_config(raw)["problems"]

    def test_defaults_are_clean(self):
        self.assertEqual(self.problems({}), [])
        for p in list_presets():
            self.assertEqual(self.problems({"preset": p}), [], p)

    def test_did_you_mean(self):
        probs = self.problems({"line": [{"left": ["modle", "dir"]}]})
        self.assertEqual(len(probs), 1)
        self.assertIn("did you mean 'model'", probs[0][2])
        self.assertIn("did you mean 'depth'", self.problems({"segment": {"dir": {"dept": 2}}})[0][2])
        self.assertIn("did you mean", self.problems({"theme": "catppucin"})[0][2])

    def test_types_and_choices(self):
        probs = self.problems({"segment": {"dir": {"depth": "two", "mode": "sideways"}}})
        msgs = " ".join(p[2] for p in probs)
        self.assertIn("expected int", msgs)
        self.assertIn("not one of", msgs)
        self.assertTrue(any(p[1] == "bar.width" for p in self.problems({"bar": {"width": "wide"}})))
        self.assertTrue(any(p[1] == "style" for p in self.problems({"style": "gothic"})))

    def test_template_problems(self):
        probs = self.problems({"segment": {"model": {"format": "{name"}}})
        self.assertEqual(probs[0][0], "error")
        warn = self.problems({"segment": {"model": {"format": "<nope>{name}</nope> {nosuch}"}}})
        self.assertEqual({p[0] for p in warn}, {"warning"})
        self.assertEqual(len(warn), 2)

    def test_instances(self):
        raw = {"line": [{"left": ["hello", "bye"]}],
               "segment": {"hello": {"type": "text", "text": "hi"}, "bye": {"type": "text", "text": "bye"}}}
        comp = compile_config(raw)
        self.assertEqual(comp["problems"], [])
        self.assertEqual([s["type"] for s in comp["lines"][0]["left"]], ["text", "text"])
        self.assertEqual(plain(dict(raw, style="minimal"), {}), ["hi  bye"])

    def test_unplaced_and_unknown_tables(self):
        probs = self.problems({"segment": {"clock": {"strftime": "%H"}, "zzz": {"a": 1}}})
        self.assertEqual({(p[0], p[1]) for p in probs}, {("warning", "segment.clock"), ("error", "segment.zzz")})

    def test_bad_preset_falls_back(self):
        comp = compile_config({"preset": "nope"})
        self.assertEqual(comp["preset"], "classic")
        self.assertTrue(comp["lines"])

    def test_v2_keys(self):
        probs = self.problems({"bar": {"empty": "█", "partial_style": "auto"}, "features": {"pace": True}})
        self.assertEqual({p[0] for p in probs}, {"warning"})

    def test_quest_line_only_when_enabled(self):
        base = compile_config({})
        on = compile_config({"quest": {"enabled": True}})
        self.assertEqual(len(on["lines"]), len(base["lines"]) + 1)
        self.assertTrue(on["lines"][-1]["auto"])
        inline = compile_config({"quest": {"enabled": True, "placement": "inline"}})
        self.assertEqual(inline["lines"][0]["right"][0]["name"], "quest")
        manual = compile_config({"quest": {"enabled": True, "placement": "manual"}})
        self.assertEqual(len(manual["lines"]), len(base["lines"]))
        placed = compile_config({"quest": {"enabled": True}, "line": [{"left": ["model", "quest"]}]})
        self.assertEqual(len(placed["lines"]), 1)

    def test_compiled_is_cacheable(self):
        import marshal
        comp = compile_config({"quest": {"enabled": True}, "theme": "nord"})
        self.assertEqual(marshal.loads(marshal.dumps(comp)), comp)


class CacheTests(unittest.TestCase):
    def test_cache_follows_the_file(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "config.toml")
        with open(path, "w") as fh:
            fh.write('theme = "nord"\n')
        os.environ["XDG_RUNTIME_DIR"] = d
        try:
            self.assertEqual(config.compiled(path)["theme"], "nord")
            self.assertEqual(config.compiled(path)["theme"], "nord")          # from the cache
            time.sleep(0.01)
            with open(path, "w") as fh:
                fh.write('theme = "dracula"\n# longer\n')
            self.assertEqual(config.compiled(path)["theme"], "dracula")
            with open(path, "w") as fh:
                fh.write("theme = [broken\n")
            comp = config.compiled(path)
            self.assertEqual(comp["theme"], "claude")                         # defaults, never a crash
            self.assertIn("not valid TOML", comp["problems"][0][2])
        finally:
            os.environ.pop("XDG_RUNTIME_DIR", None)


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = {n: samples.load(n, NOW) for n in ("busy", "quiet", "hot")}
        cls.data["empty"] = {}
        cls.data["hostile"] = HOSTILE

    def test_width_invariant(self):
        """No line ever exceeds the usable width, in any look, at any width."""
        for preset in list_presets():
            for style in LOOKS:
                for icons in ("nerd", "unicode", "emoji", "none"):
                    raw = {"preset": preset, "style": style, "icons": icons, "theme": "midnight",
                           "quest": {"enabled": True}}
                    for name, data in self.data.items():
                        for cols in (30, 60, 80, 100, 140, 200):
                            ctx, fits = lines_of(raw, data, cols)
                            for f in fits:
                                if f is not None:
                                    self.assertLessEqual(f.text.width, ctx.avail,
                                                         (preset, style, icons, name, cols, f.text.plain()))

    def test_every_theme_and_colour_depth_renders(self):
        for theme in THEMES:
            for mode in ("truecolor", "256", "16", "none"):
                comp = compile_config({"theme": theme, "color": mode})
                out = render(self.data["busy"], comp, cols=160, now=NOW, env=ENV, live=False)
                self.assertIn("Opus 5", out)
                if mode == "none":
                    self.assertNotIn("\033[0;3", out)

    def test_right_only_line_survives_trimming(self):
        """Claude Code trims lines: one with an empty left group must not start with a space."""
        for mode in ("truecolor", "none"):
            comp = compile_config({"color": mode, "line": [{"right": ["model"]}]})
            out = render(self.data["busy"], comp, cols=80, now=NOW, env=ENV, live=False)
            self.assertFalse(out[:1].isspace(), repr(out))
            self.assertIn("Opus 5", out.strip())

    def test_busy_content(self):
        text = "\n".join(plain({"style": "minimal", "icons": "unicode"}, self.data["busy"], 200))
        for want in ("Opus 5", "high", "~/P/", "widget-factory", "feat/parser", "↑2", "+1", "~3", "?2",
                     "#1234", "$24.73", "59m", "+1006", "-21", "28%", "279k/1.0M", "62%", "→", "↻1h43m",
                     "24%", "refactor the parser"):
            self.assertIn(want, text)

    def test_degrades_before_dropping(self):
        ctx, fits = lines_of({"style": "minimal", "icons": "unicode"}, self.data["busy"], 100)
        self.assertGreater(fits[1].level, 0)
        self.assertEqual(fits[1].dropped, [])
        ctx, fits = lines_of({"style": "minimal", "icons": "unicode"}, self.data["busy"], 45)
        self.assertTrue(fits[0].dropped)
        self.assertIn("Opus", fits[0].text.plain())            # the highest priority survives
        self.assertEqual(LEVELS[0], "full")

    def test_missing_windows_and_empty_lines(self):
        raw = {"line": [{"left": ["model"]}, {"left": ["limit_7d_model", "session"]}]}
        _, fits = lines_of(raw, {"model": {"display_name": "Haiku"}})
        self.assertIsNotNone(fits[0])
        self.assertIsNone(fits[1])                             # nothing to show: the line is left out
        text = plain({"line": [{"left": ["limit_5h"]}], "style": "minimal", "icons": "none"}, {})
        self.assertEqual(text, ["5h —"])

    def test_hostile_payload(self):
        for style in LOOKS:
            out = render(HOSTILE, compile_config({"style": style}), cols=120, now=NOW, env=ENV, live=False)
            self.assertIsInstance(out, str)

    def test_fallback(self):
        self.assertIn("Opus", fallback({"model": {"display_name": "Opus"}, "cwd": "/tmp"}))
        self.assertEqual(fallback(None), "✶ Claude")

    def test_looks(self):
        data = self.data["busy"]
        for style, mark in (("classic", "│"), ("dots", "·"), ("powerline", ""), ("slant", ""),
                            ("capsules", ""), ("pills", ""), ("chips", "▌")):
            text = "\n".join(plain({"style": style, "icons": "nerd"}, data, 200))
            self.assertIn(mark, text, style)

    def test_auto_look(self):
        comp = compile_config({})
        self.assertEqual(resolve_look(comp, {"TERM": "xterm-kitty"})[:2], ("capsules", "nerd"))
        self.assertEqual(resolve_look(comp, {"TERM": "xterm-256color"})[:2], ("chips", "unicode"))
        self.assertEqual(resolve_look(compile_config({"style": "capsules"}), {"TERM": "xterm"})[0], "chips")
        self.assertEqual(resolve_look(compile_config({"style": "capsules", "icons": "unicode"}), {})[0],
                         "capsules")

    def test_segment_colour_and_icon_overrides(self):
        raw = {"line": [{"left": ["model"]}], "style": "minimal", "icons": "nerd",
               "segment": {"model": {"icon": "M", "color": "#ff0000"}}}
        ctx, fits = lines_of(raw, self.data["busy"])
        spans = fits[0].text.spans
        self.assertEqual(spans[0][0], "M")
        self.assertEqual(spans[0][1][0][:3], (255, 0, 0))
        raw["segment"]["model"]["icon"] = ""
        self.assertTrue(plain(raw, self.data["busy"])[0].startswith("Opus"))

    def test_v2_config_still_renders(self):
        """A v2 file: SGR colours, {glyph} in formats, avatar rows, bar glyph overrides."""
        raw = {
            "line": [{"left": ["model", "dir", "git"], "right": ["heartbeat", "avatar0"], "gap": 1},
                     {"left": ["context"], "right": ["limit_5h", "avatar1"]}],
            "segment": {"avatar0": {"type": "avatar", "row": 0}, "avatar1": {"type": "avatar", "row": 1},
                        "model": {"format": "<model>{glyph} {short}</model><dim>[ · {effort}]</dim>"},
                        "context": {"format": "{bar} <level>{pct}%</level> <dim>{tokens} of {size} tokens</dim>"},
                        "limit_5h": {"clock": False, "pace_mode": "recent"}},
            "bar": {"width": 16, "empty": "█"}, "colors": {"dim": "38;5;240", "model": "38;5;141"},
        }
        comp = compile_config(raw)
        self.assertEqual([p[0] for p in comp["problems"]], ["warning"])     # bar.empty is retired
        text = "\n".join(plain(dict(raw, style="classic", icons="unicode"), self.data["busy"], 200))
        self.assertIn("✶ Opus 5", text)                                       # {glyph} is the icon
        self.assertIn("279k of 1.0M tokens", text)


class SegmentTests(unittest.TestCase):
    def one(self, name, data, cols=200, **opts):
        raw = {"line": [{"left": [name]}], "style": "minimal", "icons": "unicode",
               "segment": {name: opts} if opts else {}}
        out = plain(raw, data, cols)
        return out[0] if out else None

    def test_model(self):
        d = {"model": {"display_name": "Opus 5 (1M context)"}, "effort": {"level": "xhigh"}, "fast_mode": True}
        self.assertEqual(self.one("model", d), "✶ Opus 5 ⚡ · xhigh")
        self.assertIn("(1M context)", self.one("model", d, full_name=True))
        self.assertEqual(self.one("model", {"model": {"id": "x"}, "thinking": {"enabled": True}}), "✶ x · think")

    def test_dir_modes(self):
        d = {"cwd": "/home/u/Projects/app/src", "_home": "/home/u"}
        self.assertEqual(self.one("dir", d), "▸ ~/P/a/src")
        self.assertEqual(self.one("dir", d, depth=2), "▸ ~/P/app/src")
        self.assertEqual(self.one("dir", d, mode="base"), "▸ src")
        self.assertEqual(self.one("dir", d, mode="full"), "▸ ~/Projects/app/src")
        self.assertEqual(self.one("dir", d, mode="compact", depth=2), "▸ …/app/src")
        d["workspace"] = {"current_dir": d["cwd"], "project_dir": "/home/u/Projects/app"}
        self.assertEqual(self.one("dir", d, mode="project"), "▸ app/src")

    def test_git_from_sample_state(self):
        d = {"_git": {"branch": "main", "ahead": 1, "behind": 2, "staged": 3, "dirty": 4, "untracked": 5,
                      "conflict": 1, "stash": 2, "state": "MERGE", "upstream": "origin/main"}}
        out = self.one("git", d)
        for part in ("main", "MERGE", "↑1↓2", "+3", "~4", "?5", "!1", "≡2"):
            self.assertIn(part, out)
        self.assertIn("∅", self.one("git", {"_git": {"branch": "wip"}}))

    def test_pr(self):
        self.assertEqual(self.one("pr", {"pr": {"number": 12, "review_state": "approved"}}), "⊕ #12 approved")
        self.assertEqual(self.one("pr", {"pr": {"number": 7, "kind": "mr"}}), "⊕ !7")
        self.assertIsNone(self.one("pr", {}))

    def test_limits(self):
        d = {"rate_limits": {"five_hour": {"used_percentage": 40, "resets_at": NOW + 3600}}}
        out = self.one("limit_5h", d)
        self.assertIn("40%", out)
        self.assertIn("↻1h00m", out)
        self.assertIn("→", out)                                    # 40% with 80% of the window gone
        self.assertNotIn("↻", self.one("limit_5h", d, reset=False))
        camel = {"rateLimits": {"fiveHour": {"usedPercentage": 12}}}
        self.assertIn("12%", self.one("limit_5h", camel))
        model = {"rate_limits": {"seven_day": {"used_percentage": 20}, "seven_day_opus": {"used_percentage": 70}}}
        self.assertIn("7d·opus", self.one("limit_7d_model", model))

    def test_context(self):
        d = {"context_window": {"used_percentage": 42, "total_input_tokens": 84000, "context_window_size": 200000}}
        self.assertIn("84k/200k", self.one("context", d))
        self.assertIn("58%", self.one("context", d, remaining=True))
        self.assertEqual(self.one("context", {"exceeds_200k_tokens": True}), "◔ ctx >200k")

    def test_cost_cache_burn(self):
        d = {"cost": {"total_cost_usd": 12.5, "total_duration_ms": 3_600_000}}
        self.assertIn("$12.50", self.one("cost", d))
        self.assertIn("$12.50/h", self.one("burn", d))
        self.assertIn("cold", self.one("cache", {"prompt_cache": {"warm": False, "miss_recache_tokens": 300000}}))
        self.assertIsNone(self.one("cache", {"prompt_cache": {"warm": True, "hit_ratio": 0.99}}))
        self.assertIn("hit 50%", self.one("cache", {"prompt_cache": {"warm": True, "hit_ratio": 0.5}}))

    def test_cache_countdown_and_cause(self):
        warm = {"warm": True, "hit_ratio": 0.99, "ttl": "5m", "expires_at": NOW + 134}
        self.assertEqual(self.one("cache", {"prompt_cache": warm}), "⊙ cools 2m14s")
        self.assertIsNone(self.one("cache", {"prompt_cache": dict(warm, expires_at=NOW + 200)}))  # over half the TTL
        self.assertIsNone(self.one("cache", {"prompt_cache": warm}, countdown=0.0))
        hour = dict(warm, ttl="1h", expires_at=NOW + 290)
        self.assertEqual(self.one("cache", {"prompt_cache": hour}), "⊙ cools 4m50s")
        missed = {"warm": True, "hit_ratio": 0.62, "last_miss_cause": {"causes": ["tools_changed", "odd_new_cause"]}}
        self.assertEqual(self.one("cache", {"prompt_cache": missed}), "⊙ hit 62% · tools changed, odd new cause")

    def test_heartbeat_moves_with_the_clock(self):
        comp = compile_config({"line": [{"left": ["heartbeat"]}]})
        frames = {render({}, comp, cols=80, now=NOW + i, env=ENV, live=False) for i in range(8)}
        self.assertEqual(len(frames), 8)

    def test_vim_and_agent(self):
        self.assertEqual(self.one("vim", {"vim": {"mode": "INSERT"}}), "INSERT")
        self.assertEqual(self.one("agent", {"agent": {"name": "reviewer"}}), "⍟ reviewer")


if __name__ == "__main__":
    unittest.main()
