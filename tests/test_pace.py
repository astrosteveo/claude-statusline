#!/usr/bin/env python3
"""The burn-rate projection: the stateless average and the on-disk recent rate."""
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import claude_statusline as S  # noqa: E402
from claude_statusline import pace  # noqa: E402
from claude_statusline.cli import check_config  # noqa: E402

_SGR = re.compile(r"\033\[[0-9;]*[@-~]")
FIVE_H = 5 * 3600
RESET = 2_000_000_000.0          # the window ends here; NOW is measured back from it


def strip(s):
    return _SGR.sub("", s)


class PaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()
        S.apply_config(S.deep_merge(S.DEFAULTS, {}))

    def configure(self, **limit):
        S.apply_config(S.deep_merge(S.DEFAULTS, {
            "line": [{"left": ["limit_5h"]}],
            "segment": {"limit_5h": {"format": "{pct}%[ {pace}]", "clock": False, **limit}}}))

    def render(self, pct, elapsed_frac):
        now = RESET - FIVE_H * (1 - elapsed_frac)
        data = {"rate_limits": {"five_hour": {"used_percentage": pct, "resets_at": RESET}}}
        return strip(S.render(data, cols=80, now=now))

    # --- average ---------------------------------------------------------
    def test_average_divides_usage_by_the_window_gone(self):
        self.configure()
        self.assertEqual(self.render(42, 0.525), "42% ⇢80%")

    def test_average_waits_for_min_elapsed(self):
        self.configure()
        self.assertEqual(self.render(5, 0.05), "5%")
        self.assertEqual(self.render(5, 0.10), "5% ⇢50%")

    def test_average_never_touches_disk(self):
        self.configure()
        self.render(42, 0.5)
        self.assertFalse(os.path.exists(pace.history_path("5h")))

    # --- recent ----------------------------------------------------------
    def test_recent_falls_back_to_average_until_the_history_spans_the_lookback(self):
        self.configure(pace_mode="recent")
        self.assertEqual(self.render(42, 0.525), "42% ⇢80%")      # first sample
        self.assertEqual(self.render(43, 0.55), "43% ⇢78%")       # 7.5 min later: still short of 30 min
        self.assertEqual(self.render(44, 0.60), "44% ⇢73%")       # 22.5 min: still short

    def test_recent_follows_a_slowdown(self):
        self.configure(pace_mode="recent")
        self.render(42, 0.525)
        self.render(43, 0.55)
        # 30 min of history: 2 points over a tenth of the window, with 0.375
        # of it left, so 44 + 2 * 3.75 = 51.5. The average would say 70.
        self.assertEqual(self.render(44, 0.625), "44% ⇢52%")
        # Then nothing for 30 minutes: the rate over the lookback is 0.
        self.assertEqual(self.render(44, 0.725), "44% ⇢44%")

    def test_recent_follows_a_speedup(self):
        self.configure(pace_mode="recent")
        self.render(10, 0.30)
        self.render(10, 0.40)
        # 10 points in the last 30 min with 2.5 h left: 20 + 10 * 5 = 70,
        # where the average would say 40.
        self.assertEqual(self.render(20, 0.50), "20% ⇢70%")

    def test_recent_starts_over_on_a_new_window(self):
        self.configure(pace_mode="recent")
        self.render(42, 0.525)
        self.render(44, 0.625)
        self.assertEqual(self.render(44, 0.625), "44% ⇢52%")
        later = {"rate_limits": {"five_hour": {"used_percentage": 3, "resets_at": RESET + FIVE_H}}}
        out = strip(S.render(later, cols=80, now=RESET + FIVE_H * 0.2))
        self.assertEqual(out, "3% ⇢15%")                          # the average again
        with open(pace.history_path("5h")) as fh:
            blob = fh.read()
        self.assertIn(str(int(RESET + FIVE_H)), blob)
        self.assertNotIn("42", blob)

    def test_recent_is_per_window_slot(self):
        S.apply_config(S.deep_merge(S.DEFAULTS, {
            "line": [{"left": ["limit_5h", "limit_7d"]}],
            "segment": {"limit_5h": {"pace_mode": "recent"}, "limit_7d": {"pace_mode": "recent"}}}))
        data = {"rate_limits": {"five_hour": {"used_percentage": 42, "resets_at": RESET},
                                "seven_day": {"used_percentage": 20, "resets_at": RESET + 6 * 86400}}}
        S.render(data, cols=200, now=RESET - FIVE_H / 2)
        self.assertTrue(os.path.exists(pace.history_path("5h")))
        self.assertTrue(os.path.exists(pace.history_path("7d")))

    def test_history_stays_small(self):
        lookback = 1800.0
        samples = []
        for i in range(5000):
            samples, _ = pace._record(samples, float(i), float(i) / 10, lookback)
        self.assertLessEqual(len(samples), pace.SAMPLES_PER_LOOKBACK + 2)
        self.assertLess(samples[0][0], 5000 - lookback)              # the anchor precedes the lookback

    def test_unreadable_history_is_ignored(self):
        self.configure(pace_mode="recent")
        with open(pace.history_path("5h"), "w") as fh:
            fh.write("{not json")
        self.assertEqual(self.render(42, 0.525), "42% ⇢80%")

    def test_unknown_mode_is_a_config_problem(self):
        probs = check_config({"segment": {"limit_5h": {"pace_mode": "psychic"}}})
        self.assertEqual([p.path for p in probs], ["segment.limit_5h.pace_mode"])
        self.assertEqual(check_config({"segment": {"limit_5h": {"pace_mode": "recent"}}}), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
