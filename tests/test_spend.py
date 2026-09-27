"""Spend today: the ledger of every session's cost per local day, and the segment that shows it."""
import os
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from claude_statusline import ledger as L  # noqa: E402
from claude_statusline.context import Context  # noqa: E402
from claude_statusline.layout import compile_config  # noqa: E402
from claude_statusline.render import render_lines  # noqa: E402

NOON = time.mktime((2026, 9, 26, 12, 0, 0, 0, 0, -1))
MIDNIGHT = time.mktime((2026, 9, 27, 0, 0, 0, 0, 0, -1))


def ledger_at(*readings):
    """Fold readings of (session, cost, duration ms, time) in order, as the bar would."""
    led = L.fresh(L.day_of(readings[0][3]))
    for sid, cost, ms, now in readings:
        L.roll(led, L.day_of(now))
        L.note(led, sid, cost, ms, now)
    return led


class LedgerTests(unittest.TestCase):
    def test_sessions_add_up(self):
        led = ledger_at(("a", 0.5, 60_000, NOON), ("a", 4.0, 900_000, NOON + 900),
                        ("b", 0.1, 30_000, NOON + 60), ("b", 2.5, 600_000, NOON + 700))
        self.assertAlmostEqual(L.totals(led, NOON + 1000)["today"], 6.5)
        # this session's live cost counts before the bar next writes it
        self.assertAlmostEqual(L.totals(led, NOON + 1001, "b", 3.0, 700_000)["today"], 7.0)

    def test_a_resumed_session_counts_from_when_it_was_seen(self):
        led = ledger_at(("old", 40.0, 9_000_000, NOON), ("old", 42.0, 9_100_000, NOON + 500))
        self.assertAlmostEqual(L.totals(led, NOON + 600)["today"], 2.0)

    def test_midnight_splits_a_session(self):
        led = ledger_at(("a", 0.0, 1_000, NOON), ("a", 10.0, 600_000, MIDNIGHT - 60),
                        ("a", 13.0, 700_000, MIDNIGHT + 60))
        t = L.totals(led, MIDNIGHT + 120)
        self.assertAlmostEqual(t["today"], 3.0)
        self.assertAlmostEqual(t["week"], 13.0)
        self.assertEqual(led["days"][L.day_of(NOON)], 10.0)
        # a ledger nobody wrote since yesterday still reads right today
        stale = ledger_at(("a", 0.0, 1_000, NOON), ("a", 10.0, 600_000, NOON + 60))
        t = L.totals(stale, MIDNIGHT + 60, "a", 11.0, 700_000)
        self.assertAlmostEqual(t["today"], 1.0)
        self.assertAlmostEqual(t["week"], 11.0)

    def test_the_month_and_its_edges(self):
        first = time.mktime((2026, 10, 1, 9, 0, 0, 0, 0, -1))
        led = ledger_at(("a", 0.0, 1_000, NOON), ("a", 5.0, 100_000, NOON + 10), ("b", 0.0, 1_000, first),
                        ("b", 1.0, 100_000, first + 10))
        t = L.totals(led, first + 20)
        self.assertAlmostEqual(t["month"], 1.0)                 # September's spend is not October's
        self.assertAlmostEqual(t["week"], 6.0)

    def test_writes_are_throttled_and_safe_together(self):
        os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp(prefix="sl-state-")
        self.assertTrue(L.due(None, "a", 1.0, NOON))
        led = L.update("a", 1.0, 10_000, NOON)
        self.assertFalse(L.due(led, "a", 1.5, NOON + 5))
        self.assertTrue(L.due(led, "a", 1.5, NOON + L.WRITE_EVERY))
        self.assertTrue(L.due(led, "a", 1.5, MIDNIGHT + 1))
        threads = [threading.Thread(target=L.update, args=(f"s{i}", float(i), 10_000, NOON + i)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(L.read()["sessions"]), 21)
        self.assertAlmostEqual(L.totals(L.read(), NOON + 30)["today"], 1.0 + sum(range(20)))


class SegmentTests(unittest.TestCase):
    def line(self, data, cols=200, **opts):
        comp = compile_config({"line": [{"left": ["spend"]}], "style": "minimal", "icons": "unicode",
                               "segment": {"spend": opts}})
        ctx = Context(data, comp, cols=cols, now=NOON, env={"COLORTERM": "truecolor"}, live=False)
        fits = render_lines(data, comp, ctx=ctx)
        return fits[0].text.plain() if fits[0] else None

    def test_shows(self):
        data = {"_spend": {"today": 61.2, "week": 212.4, "month": 488.9}}
        self.assertEqual(self.line(data), "Σ today $61.20 · month $489")
        self.assertIn("· week $212", self.line(data, week=True))
        self.assertIn("61%", self.line(data, budget=100.0))
        narrow = self.line(data, cols=30, budget=100.0)
        self.assertIn("$61.20", narrow)
        self.assertNotIn("61%", narrow)                               # the percentage goes first
        self.assertNotIn("month", narrow)
        self.assertIsNone(self.line({}))

    def test_previews_never_write(self):
        os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp(prefix="sl-state-")
        self.line({"session_id": "x", "cost": {"total_cost_usd": 3.0, "total_duration_ms": 5_000}})
        self.assertFalse(os.path.exists(L.path()))


if __name__ == "__main__":
    unittest.main()
