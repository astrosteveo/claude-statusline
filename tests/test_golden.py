#!/usr/bin/env python3
"""Golden output of the default layout.

The bar today is the acceptance test for the engine tomorrow: every fixture is
rendered at every width with time, timezone, git and the environment pinned,
and the result must match byte for byte. Regenerate deliberately with
UPDATE_GOLDENS=1 when a change to the default layout is intended.
"""
import json
import os
import sys
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(HERE, "fixtures")
GOLDEN = os.path.join(HERE, "goldens", "classic.json")

sys.path.insert(0, ROOT)
import claude_statusline as S  # noqa: E402

WIDTHS = (200, 174, 160, 120, 100, 80, 60, 40)

# Inside the 5h window of full.json (65% elapsed) and 11% into its 7d window,
# so pace projections and the reset clock both render.
NOW = 1_787_950_000.0

# Git reads the live repository and the environment reads the live shell, so
# neither can be golden. Everything else about the default layout can.
PINNED_CONFIG = {"git": {"enabled": False}}
PINNED_ENV = {"TZ": "UTC", "HOME": "/home/u"}
UNPINNABLE_ENV = ("VIRTUAL_ENV", "CONDA_DEFAULT_ENV", "SSH_CONNECTION")


def fixtures():
    for name in sorted(os.listdir(FIXTURES)):
        if name.endswith(".json"):
            with open(os.path.join(FIXTURES, name)) as fh:
                yield name[:-5], json.load(fh)


def render_all():
    out = {}
    with mock.patch.dict(os.environ, PINNED_ENV):
        for var in UNPINNABLE_ENV:
            os.environ.pop(var, None)
        time.tzset()
        S.apply_config(S.deep_merge(S.DEFAULTS, PINNED_CONFIG))
        try:
            with mock.patch("claude_statusline.segments.time.time", return_value=NOW):
                for name, data in fixtures():
                    for cols in WIDTHS:
                        out[f"{name}@{cols}"] = S.render(data, cols=cols, now=NOW)
        finally:
            S.apply_config(S.deep_merge(S.DEFAULTS, {}))
    time.tzset()
    return out


class GoldenTests(unittest.TestCase):
    def test_default_layout_matches_golden(self):
        got = render_all()
        if os.environ.get("UPDATE_GOLDENS"):
            os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
            with open(GOLDEN, "w") as fh:
                json.dump(got, fh, indent=1, ensure_ascii=False, sort_keys=True)
                fh.write("\n")
            self.skipTest(f"goldens rewritten: {GOLDEN}")
        with open(GOLDEN) as fh:
            want = json.load(fh)
        self.assertEqual(sorted(got), sorted(want), "fixture/width set changed")
        for key in sorted(want):
            self.assertEqual(got[key], want[key],
                             f"{key} drifted from golden:\n"
                             f"want: {want[key]!r}\n got: {got[key]!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
