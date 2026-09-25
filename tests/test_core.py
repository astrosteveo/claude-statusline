"""Widths, colours, styled text, templates and bars: the primitives the bar is built from."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_statusline import bar, color, width  # noqa: E402
from claude_statusline.template import TemplateError, compile_template, render  # noqa: E402
from claude_statusline.text import BOLD, KEEP, PLAIN, Text, to_ansi  # noqa: E402
from claude_statusline.themes import THEMES, palette  # noqa: E402

PAL = palette("claude")
TH = {"yellow": 50, "orange": 75, "red": 90}


class WidthTests(unittest.TestCase):
    """Widths must match Claude Code's string-width, or right edges drift."""

    def test_ascii_and_controls(self):
        self.assertEqual(width.width("hello"), 5)
        self.assertEqual(width.width("a\tb"), 2)
        self.assertEqual(width.width(""), 0)

    def test_wide(self):
        self.assertEqual(width.width("日本"), 4)
        self.assertEqual(width.width("🧙"), 2)
        self.assertEqual(width.width("🪙12"), 4)
        self.assertEqual(width.width("⚡"), 2)

    def test_emoji_sequences(self):
        self.assertEqual(width.width("⚔"), 1)          # text presentation by default
        self.assertEqual(width.width("⚔️"), 2)         # VS16 promotes it
        self.assertEqual(width.width("⬆️"), 2)
        self.assertEqual(width.width("👍🏽"), 2)        # skin tone joins the emoji
        self.assertEqual(width.width("👨‍👩‍👧"), 2)      # ZWJ family is one glyph
        self.assertEqual(width.width("🇬🇧"), 2)        # a flag is a pair of regional indicators
        self.assertEqual(width.width("1️⃣"), 2)          # keycap

    def test_zero_width(self):
        self.assertEqual(width.width("é"), 1)     # combining accent
        self.assertEqual(width.width("a​b"), 2)    # zero-width space
        # kitty placeholder: one cell each, the diacritics add nothing
        self.assertEqual(width.width("\U0010EEEE̅̅" + "\U0010EEEE" * 7), 8)

    def test_nerd_font_and_blocks(self):
        for ch in "\U000f0674█▌▐░▒▓━─●○▰▱⣿⡇":
            self.assertEqual(width.width(ch), 1, repr(ch))

    def test_wide_glyphs_setting(self):
        width.WIDE.add("⎇")
        width._CHAR.clear()
        width._STR.clear()
        try:
            self.assertEqual(width.width("⎇ main"), 7)
        finally:
            width.WIDE.discard("⎇")
            width._CHAR.clear()
            width._STR.clear()

    def test_strip_and_clip(self):
        s = "\033[1;38;5;141mOpus\033[0m \033]8;;https://x\033\\link\033]8;;\033\\"
        self.assertEqual(width.strip_ansi(s), "Opus link")
        self.assertEqual(width.ansi_width(s), 9)
        self.assertEqual(width.clip("abcdefgh", 5), "abcd…")
        self.assertEqual(width.clip("日本語", 4), "日…")
        self.assertEqual(width.clip("abc", 5), "abc")


class ColorTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(color.parse("#ff8000"), (255, 128, 0, -1))
        self.assertEqual(color.parse("#f80"), (255, 136, 0, -1))
        self.assertEqual(color.parse("38;5;141")[3], 141)
        self.assertEqual(color.parse("38;2;1;2;3"), (1, 2, 3, -1))
        self.assertEqual(color.parse(208)[3], 208)
        self.assertEqual(color.parse("31")[3], 1)
        for bad in ("nope", "#12345", None, True, "38;5;999", []):
            self.assertIsNone(color.parse(bad), bad)

    def test_modes(self):
        c = color.parse("#d97757")
        self.assertEqual(color.sgr(c, "truecolor"), "38;2;217;119;87")
        self.assertTrue(color.sgr(c, "256").startswith("38;5;"))
        self.assertIn(color.sgr(c, "16"), [str(30 + i) for i in range(8)] + [str(90 + i) for i in range(8)])
        self.assertEqual(color.sgr(c, "none"), "")
        self.assertEqual(color.sgr(c, "truecolor", background=True), "48;2;217;119;87")
        # an index the user chose is kept as an index, even in truecolor
        self.assertEqual(color.sgr(color.parse(141), "truecolor"), "38;5;141")

    def test_detect(self):
        self.assertEqual(color.detect_mode({"COLORTERM": "truecolor"}), "truecolor")
        self.assertEqual(color.detect_mode({"TERM": "xterm-256color"}), "256")
        self.assertEqual(color.detect_mode({"NO_COLOR": "1", "COLORTERM": "truecolor"}), "none")
        self.assertEqual(color.detect_mode({"TERM": "linux"}), "16")
        self.assertEqual(color.detect_mode({"CLAUDE_STATUSLINE_COLOR": "256", "COLORTERM": "truecolor"}), "256")

    def test_nearest256(self):
        self.assertEqual(color._nearest256(0, 0, 0), 16)
        self.assertEqual(color._nearest256(255, 255, 255), 231)
        self.assertEqual(color._nearest256(128, 128, 128), 244)

    def test_themes_are_complete(self):
        for name in THEMES:
            pal = palette(name)
            for role in ("accent", "green", "yellow", "orange", "red", "surface", "subtle", "muted"):
                self.assertIsNotNone(pal.get(role), f"{name}.{role}")
            self.assertIn("model", pal)
            self.assertIn("dim", pal)

    def test_overrides(self):
        pal = palette("nord", {"accent": "#010203", "dir": "38;5;39"})
        self.assertEqual(pal["accent"][:3], (1, 2, 3))
        self.assertEqual(pal["model"][:3], (1, 2, 3))      # the alias follows its role
        self.assertEqual(pal["dir"][3], 39)
        self.assertEqual(palette("nope")["accent"], palette("claude")["accent"])


class TextTests(unittest.TestCase):
    def test_serialise_only_on_change(self):
        red = color.parse("#ff0000")
        t = Text().add("a", (red, None, 0, None)).add("b", (red, None, 0, None)).add("c")
        self.assertEqual(t.ansi(), "\033[0;38;2;255;0;0mab\033[0mc")
        self.assertEqual(Text.of("plain").ansi(), "plain")

    def test_links(self):
        t = Text().add("x", (None, None, 0, "https://a")).add("y")
        self.assertEqual(t.ansi(), "\033]8;;https://a\033\\x\033]8;;\033\\y")

    def test_restyle(self):
        blue = color.parse("#0000ff")
        t = Text().add("a").add("b", (None, blue, KEEP, None))
        self.assertEqual(t.under(blue).spans[0][1][1], blue)
        inked = t.ink(blue)
        self.assertEqual(inked.spans[0][1][0], blue)
        self.assertIsNone(inked.spans[1][1][0])           # KEEP runs are left alone
        self.assertNotIn("128", t.ansi())                 # KEEP is not an SGR code

    def test_clip_keeps_styles(self):
        t = Text().add("hello ", (None, None, BOLD, None)).add("world")
        c = t.clip(8)
        self.assertEqual(c.plain(), "hello w…")
        self.assertEqual(c.width, 8)
        self.assertEqual(c.spans[0][1][2], BOLD)


class TemplateTests(unittest.TestCase):
    def r(self, src, **fields):
        return render(compile_template(src), fields, dict(PAL)).plain()

    def test_fields_and_groups(self):
        self.assertEqual(self.r("{a}[ · {b}]", a="x", b="y"), "x · y")
        self.assertEqual(self.r("{a}[ · {b}]", a="x", b=""), "x")
        self.assertEqual(self.r("[{a}] mid [{b}]", a="", b=""), "mid")

    def test_empty_group_takes_one_space(self):
        self.assertEqual(self.r("{a} [{b}] {c}", a="1", b="", c="3"), "1 3")
        self.assertEqual(self.r("{a}[ {b}][ {c}]", a="1", b="", c="3"), "1 3")

    def test_empty_template_is_absent(self):
        self.assertEqual(render(compile_template("[{a}]"), {"a": ""}, PAL).width, 0)

    def test_colours_attributes_links(self):
        t = render(compile_template("<accent><bold>{a}</bold></accent> <#ff0000>{b}</> <link>go</link>"),
                   {"a": "A", "b": "B", "url": "https://x"}, PAL)
        spans = dict((txt, st) for txt, st in t.spans)
        self.assertEqual(spans["A"][0], PAL["accent"])
        self.assertTrue(spans["A"][2] & BOLD)
        self.assertEqual(spans["B"][0][:3], (255, 0, 0))
        self.assertEqual(spans["go"][3], "https://x")

    def test_padding(self):
        self.assertEqual(self.r("[{p:>3}]%", p="7"), "  7%")
        self.assertEqual(self.r("{p:<3}|", p="7"), "7  |")
        self.assertEqual(self.r("{p:^5}|", p="ab"), " ab  |")

    def test_styled_values_keep_their_colours(self):
        green = PAL["green"]
        val = Text.of("██", (green, None, 0, None))
        t = render(compile_template("<red>[{bar}]</red>"), {"bar": val}, PAL)
        self.assertEqual(t.spans[0][1][0], green)

    def test_escapes(self):
        self.assertEqual(self.r("\\{x\\} \\[y\\] \\<z\\>"), "{x} [y] <z>")

    def test_errors(self):
        for bad in ("{a", "a}", "[a", "a]", "<red>x", "x</red>", "{a b}", "<bad name>x</>", "{a:q}"):
            with self.assertRaises(TemplateError, msg=bad):
                compile_template(bad)


class BarTests(unittest.TestCase):
    def bar(self, pct, w=13, **kw):
        kw.setdefault("pal", PAL)
        kw.setdefault("thresholds", TH)
        return bar.make_bar(pct, w, **kw)

    def test_every_style_is_exactly_its_width(self):
        for style in bar.STYLES:
            for pct in (0, 1, 7, 33, 50, 99, 100, -5, 250, "junk", None):
                t = self.bar(pct, 13, style=style)
                caps = 2 if style == "ascii" else 0
                self.assertEqual(t.width, 13 + caps, (style, pct))

    def test_glyphs_are_one_cell(self):
        for ch in bar.glyphs():
            self.assertEqual(width.width(ch), 1, repr(ch))

    def test_thirteen_cells_show_every_percentage(self):
        seen = set()
        for pct in range(101):
            t = self.bar(pct, 13, style="smooth")
            seen.add(tuple((txt, st[0], st[1]) for txt, st in t.spans))
        self.assertEqual(len(seen), 101)

    def test_sliver(self):
        t = self.bar(0.5, 13, style="smooth")
        self.assertIn("▏", t.plain())
        self.assertNotIn("▏", self.bar(0.5, 13, style="smooth", min_sliver=False).plain())
        self.assertNotIn("▏", self.bar(0, 13, style="smooth").plain())

    def test_fills(self):
        lvl = bar.cell_colors("level", 95, 4, PAL, TH)
        self.assertEqual(set(lvl), {PAL["red"]})
        grad = bar.cell_colors("gradient", 50, 10, PAL, TH)
        self.assertNotEqual(grad[0], grad[-1])
        self.assertEqual(bar.cell_colors("cyan", 10, 3, PAL, TH), [PAL["cyan"]] * 3)
        blend = bar.cell_colors("cyan,purple", 10, 5, PAL, TH)
        self.assertEqual(len(set(blend)), 5)

    def test_ink_and_mono(self):
        dark, mid = PAL["base"], PAL["surface"]
        t = self.bar(50, 10, ink=(dark, mid))
        colours = {st[1] for _, st in t.spans if st[1] is not None}
        self.assertTrue(colours <= {dark, mid})
        mono = self.bar(50, 10, mono=True)
        self.assertTrue(all(st[1] is None for _, st in mono.spans))
        self.assertIn("█", mono.plain())

    def test_level_role(self):
        self.assertEqual(bar.level_role(10, TH), "green")
        self.assertEqual(bar.level_role(60, TH), "yellow")
        self.assertEqual(bar.level_role(80, TH), "orange")
        self.assertEqual(bar.level_role(95, TH), "red")


if __name__ == "__main__":
    unittest.main()
