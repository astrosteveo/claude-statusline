#!/usr/bin/env python3
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from claude_statusline.fit import FULL, LEVELS, TEXT, Placed, compose, fit_line  # noqa: E402


def const(name, prio, text):
    return Placed(name, prio, lambda level: text)


def ladder(name, prio, *texts):
    """Renderings per level; the last repeats for deeper levels."""
    return Placed(name, prio, lambda level: texts[min(level, len(texts) - 1)])


class ComposeTests(unittest.TestCase):
    def test_left_only(self):
        self.assertEqual(compose(["a", "b"], [], 20, "|", 2), "a|b")

    def test_right_only_is_anchored(self):
        self.assertEqual(compose([], ["ab"], 10, "|", 2), "        ab")

    def test_both_groups_padded_to_edge(self):
        self.assertEqual(compose(["ab"], ["cd"], 10, "|", 2), "ab      cd")

    def test_minimum_gap_survives_overflow(self):
        self.assertEqual(compose(["abcdef"], ["ghijkl"], 10, "|", 2), "abcdef  ghijkl")

    def test_empty_parts_are_skipped(self):
        self.assertEqual(compose(["a", "", "b"], ["", "c"], 20, "|", 2), "a|b" + " " * 16 + "c")


class FitTests(unittest.TestCase):
    def test_everything_fits_at_full(self):
        f = fit_line([const("a", 1, "aaa")], [const("b", 2, "bb")], 10, "|")
        self.assertEqual(f.text, "aaa     bb")
        self.assertEqual(f.level, FULL)
        self.assertEqual(f.dropped, [])

    def test_levels_step_in_lockstep_before_any_drop(self):
        a = ladder("a", 10, "aaaaaa", "aaaa", "aa")
        b = ladder("b", 5, "bbbbbb", "bbbb", "bb")
        f = fit_line([a, b], [], 9, "|")
        self.assertEqual(f.text, "aaaa|bbbb")
        self.assertEqual(f.level, 1)
        self.assertEqual(f.dropped, [])

    def test_lowest_priority_drops_only_after_leanest_level(self):
        a = ladder("a", 10, "aaaaaa", "aaaa")
        b = ladder("b", 5, "bbbbbb", "bbbb")
        c = const("c", 1, "cccc")
        f = fit_line([a, b, c], [], 9, "|")
        self.assertEqual(f.dropped, ["c"])
        self.assertEqual(f.text, "aaaa|bbbb")

    def test_after_a_drop_the_richest_fitting_level_wins(self):
        a = ladder("a", 10, "aaaaaa", "aaa")
        c = const("c", 1, "cccccccc")
        f = fit_line([a, c], [], 7, "|")
        self.assertEqual(f.dropped, ["c"])
        self.assertEqual(f.level, FULL)
        self.assertEqual(f.text, "aaaaaa")

    def test_segments_absent_at_full_are_never_dropped(self):
        a = const("a", 10, "aaaaaaaaaa")
        gone = const("gone", 0, "")
        f = fit_line([a, gone], [], 5, "|")
        self.assertEqual(f.dropped, [])
        self.assertEqual(f.text, "aaaaaaaaaa")   # last one standing may overflow

    def test_last_segment_stays_even_when_it_overflows(self):
        f = fit_line([const("a", 1, "x" * 30)], [const("b", 2, "y" * 30)], 10, "|")
        self.assertEqual(f.dropped, ["a"])
        self.assertTrue(f.text.endswith("y" * 30))
        self.assertGreater(f.overflow, 0)

    def test_segment_may_vanish_at_a_level(self):
        a = ladder("a", 10, "aaaa", "aa")
        opt = ladder("opt", 5, "oooo", "")
        f = fit_line([a, opt], [], 4, "|")
        self.assertEqual(f.text, "aa")
        self.assertEqual(f.level, 1)
        self.assertEqual(f.dropped, [])

    def test_render_exception_counts_as_absent(self):
        def boom(level):
            raise RuntimeError("no")
        f = fit_line([Placed("x", 1, boom), const("a", 2, "ok")], [], 10, "|")
        self.assertEqual(f.text, "ok")

    def test_ties_drop_leftmost_first(self):
        f = fit_line([const("a", 1, "aaaa"), const("b", 1, "bbbb")], [], 4, "|")
        self.assertEqual(f.dropped, ["a"])

    def test_deepest_level_is_text(self):
        self.assertEqual(LEVELS[TEXT], "text")
        self.assertEqual(len(LEVELS), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
