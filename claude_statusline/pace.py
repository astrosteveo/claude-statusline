"""Burn-rate projections for the rate-limit windows.

`average` needs nothing but the payload: usage so far divided by the fraction
of the window gone. It answers "will I run out at this overall pace?" but
only drifts down slowly after a slowdown.

`recent` measures the rate over the last stretch of the window instead, so it
reacts to a change of pace within that stretch. Each render only sees the
host's snapshot, so the samples it needs live on disk beside the git cache:
one small file per window, keyed by the window's reset time so a new window
starts a clean history.
"""
from __future__ import annotations

import json
import os

from .gitinfo import _cache_dir

MODES = ("average", "recent")

# One sample per this fraction of the lookback, whether or not usage moved:
# an idle stretch has to be on record for the rate to see it. With the anchor
# that keeps the file at a hundred-odd rows.
SAMPLES_PER_LOOKBACK = 100


def history_path(slot: str) -> str:
    return os.path.join(_cache_dir(), f"pace-{slot}.json")


def _read(path: str, key):
    try:
        with open(path) as fh:
            blob = json.load(fh)
    except Exception:
        return []
    if blob.get("key") != key:
        return []
    samples = blob.get("samples")
    return [tuple(s) for s in samples if isinstance(s, list) and len(s) == 2] if isinstance(samples, list) else []


def _write(path: str, key, samples) -> None:
    try:
        tmp = f"{path}.{os.getpid()}"
        with open(tmp, "w") as fh:
            json.dump({"key": key, "samples": [list(s) for s in samples]}, fh)
        os.replace(tmp, path)          # atomic; concurrent sessions are safe
    except Exception:
        pass


def _record(samples, now, pct, lookback):
    """Fold the current reading into the history. Returns (samples, changed)."""
    if samples and pct < samples[-1][1]:
        samples = []                   # the host moved backwards: start over
    if not samples:
        return [(now, pct)], True
    if now - samples[-1][0] < lookback / SAMPLES_PER_LOOKBACK:
        return samples, False
    samples.append((now, pct))
    # Keep one sample from before the lookback as the anchor and drop the rest.
    cutoff = now - lookback
    first_inside = next((i for i, s in enumerate(samples) if s[0] > cutoff), len(samples))
    return samples[max(0, first_inside - 1):], True


def _pct_at(samples, t):
    """Usage at time `t`, interpolated between the neighbouring samples."""
    before = after = None
    for s in samples:
        if s[0] <= t:
            before = s
        else:
            after = s
            break
    if before is None:
        return None
    if after is None or before[0] == after[0]:
        return before[1]
    frac = (t - before[0]) / (after[0] - before[0])
    return before[1] + (after[1] - before[1]) * frac


def recent_rate(slot, key, pct, now, lookback):
    """Percentage points per second over the last `lookback` seconds, or None
    until that much history exists."""
    if lookback <= 0:
        return None
    path = history_path(slot)
    samples, changed = _record(_read(path, key), now, pct, lookback)
    if changed:
        _write(path, key, samples)
    then = _pct_at(samples + [(now, pct)], now - lookback)
    if then is None:
        return None
    return max(0.0, pct - then) / lookback


def project(ctx, slot, pct, resets_at, window_len, opts):
    """Usage at the reset if the pace holds, or None when there is nothing
    sound to extrapolate from."""
    left = resets_at - ctx.now
    elapsed = (window_len - left) / window_len
    if not 0.0 < elapsed <= 1.0:
        return None
    average = pct / elapsed if elapsed >= opts["pace_min_elapsed"] else None
    if opts["pace_mode"] != "recent":
        return average
    lookback = opts["pace_lookback"] * window_len
    rate = ctx.memo(("pace", slot), lambda: recent_rate(slot, resets_at, pct, ctx.now, lookback))
    if rate is None:
        return average
    return pct + rate * left
