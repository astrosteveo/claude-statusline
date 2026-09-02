#!/usr/bin/env python3
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from claude_statusline.template import Template, TemplateError  # noqa: E402

COLORS = {"red": "31", "dim": "38;5;240", "reset": "0"}


def r(src, **fields):
    return Template(src).render(fields, COLORS)


class TemplateTests(unittest.TestCase):
    def test_plain_field(self):
        self.assertEqual(r("hi {name}", name="bob"), "hi bob")

    def test_missing_field_is_empty(self):
        self.assertEqual(r("a{x}b"), "ab")

    def test_colour_span_matches_legacy_bytes(self):
        self.assertEqual(r("<red>{x}</red>", x="7"), "\033[31m7\033[0m")

    def test_empty_span_emits_nothing(self):
        self.assertEqual(r("<red>{x}</red>"), "")
        self.assertEqual(r("<red>{x}</red>a", ), "a")

    def test_short_close(self):
        self.assertEqual(r("<red>x</>"), "\033[31mx\033[0m")

    def test_adjacent_same_colour_merges_into_one_run(self):
        self.assertEqual(r("<red>{a} {b}</red>", a="1", b="2"), "\033[31m1 2\033[0m")

    def test_nested_spans(self):
        self.assertEqual(r("<red>a<dim>b</dim>c</red>"),
                         "\033[31ma\033[0m\033[31m\033[38;5;240mb\033[0m\033[31mc\033[0m")

    def test_unknown_colour_is_plain(self):
        self.assertEqual(r("<nope>x</nope>"), "x")

    def test_group_renders_when_fields_present(self):
        self.assertEqual(r("{a}[ · {b}]", a="x", b="y"), "x · y")

    def test_empty_group_eats_preceding_space(self):
        self.assertEqual(r("{a} [{b}] {c}", a="x", c="z"), "x z")

    def test_empty_group_eats_following_space_when_no_preceding(self):
        self.assertEqual(r("[{b}] {c}", c="z"), "z")

    def test_group_needs_every_field(self):
        self.assertEqual(r("[{a}/{b}]", a="1"), "")
        self.assertEqual(r("[{a}/{b}]", a="1", b="2"), "1/2")

    def test_group_without_fields_always_renders(self):
        self.assertEqual(r("[lit]"), "lit")

    def test_nested_group(self):
        self.assertEqual(r("[{a}[ ({b})]]", a="x"), "x")
        self.assertEqual(r("[{a}[ ({b})]]", a="x", b="y"), "x (y)")

    def test_ends_are_trimmed(self):
        self.assertEqual(r("  {a}  ", a="x"), "x")
        self.assertEqual(r("[{a}] {b}", b="y"), "y")

    def test_value_whitespace_is_kept(self):
        self.assertEqual(r("|{a}|", a="   "), "|   |")

    def test_raw_value_is_not_wrapped(self):
        bar = "\033[32m##\033[0m\033[90m..\033[0m"
        out = r("<red>{bar}</red>", bar=bar)
        self.assertEqual(out, bar)

    def test_raw_inside_span_keeps_surrounding_colour(self):
        bar = "\033[32m#\033[0m"
        self.assertEqual(r("<red>a{bar}b</red>", bar=bar),
                         "\033[31ma\033[0m" + bar + "\033[31mb\033[0m")

    def test_link_uses_url_field(self):
        self.assertEqual(r("<link><red>{n}</red></link>", n="x", url="http://u"),
                         "\033]8;;http://u\033\\\033[31mx\033[0m\033]8;;\033\\")

    def test_link_without_url_is_plain(self):
        self.assertEqual(r("<link>{n}</link>", n="x"), "x")

    def test_escapes(self):
        self.assertEqual(r(r"\{a\} \[b\] \<c\>"), "{a} [b] <c>")

    def test_reports_fields_and_colours(self):
        t = Template("<red>{a}</red>[ <dim>{b}</dim>]")
        self.assertEqual(t.fields, {"a", "b"})
        self.assertEqual(t.colors, {"red", "dim"})

    def test_syntax_errors(self):
        for bad in ("{a", "a}", "[a", "a]", "<red>a", "<red>a</dim>", "a</>", "{a b}", "<>a</>"):
            with self.assertRaises(TemplateError, msg=bad):
                Template(bad)

    def test_all_empty_is_empty(self):
        self.assertEqual(r("<red>{a}</red>[ {b}]"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
