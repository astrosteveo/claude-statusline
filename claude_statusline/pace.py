"""Burn-rate projections for the rate-limit windows.

`average` needs nothing but the payload: usage so far divided by the
fraction of the window gone. It answers "will I run out at this overall
pace?" but only drifts down slowly after a slowdown.

`recent` measures the rate over the last stretch of the window instead, so
it follows a change of pace within that stretch. A render only sees the
host's snapshot, so the samples live in the runtime directory: one small
file per window, keyed by the reset time so a new window starts clean.
Until a lookback's worth of history exists, `recent` shows the average.
"""
from __future__ import annotations

import marshal
import os

from .config import runtime_dir

MODES = ("average", "recent")
SAMPLES_PER_LOOKBACK = 100


def _path(slot):
    return os.path.join(runtime_dir(), f"pace-{slot}.bin")


def _read(path, key):
    try:
        with open(path, "rb") as fh:
            blob = marshal.loads(fh.read())
    except Exception:
        return []
    if not isinstance(blob, dict) or blob.get("key") != key:
        return []
    samples = blob.get("samples")
    return [tuple(s) for s in samples if isinstance(s, (list, tuple)) and len(s) == 2] \
        if isinstance(samples, list) else []


def _write(path, key, samples):
    try:
        tmp = f"{path}.{os.getpid()}"
        with open(tmp, "wb") as fh:
            marshal.dump({"key": key, "samples": [list(s) for s in samples]}, fh)
        os.replace(tmp, path)
    except OSError:
        pass


def record(samples, now, pct, lookback):
    """Fold a reading into the history. Returns (samples, changed)."""
    if samples and pct < samples[-1][1]:
        samples = []                       # the host moved backwards: start over
    if not samples:
        return [(now, pct)], True
    if now - samples[-1][0] < lookback / SAMPLES_PER_LOOKBACK:
        return samples, False
    samples = samples + [(now, pct)]
    cutoff = now - lookback
    first_inside = next((i for i, s in enumerate(samples) if s[0] > cutoff), len(samples))
    return samples[max(0, first_inside - 1):], True


def pct_at(samples, t):
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
    return before[1] + (after[1] - before[1]) * (t - before[0]) / (after[0] - before[0])


def recent_rate(slot, key, pct, now, lookback):
    """Percentage points per second over the last `lookback` seconds, or None."""
    if lookback <= 0:
        return None
    path = _path(slot)
    samples, changed = record(_read(path, key), now, pct, lookback)
    if changed:
        _write(path, key, samples)
    then = pct_at(samples + [(now, pct)], now - lookback)
    if then is None:
        return None
    return max(0.0, pct - then) / lookback


def project(now, slot, pct, resets_at, window_len, opts, memo=None):
    """Usage at the reset if the pace holds, or None when there is nothing
    sound to extrapolate from."""
    left = resets_at - now
    elapsed = (window_len - left) / window_len
    if not 0.0 < elapsed <= 1.0:
        return None
    average = pct / elapsed if elapsed >= opts.get("pace_min_elapsed", 0.1) else None
    if opts.get("pace_mode", "recent") != "recent":
        return average
    lookback = opts.get("pace_lookback", 0.1) * window_len
    rate = recent_rate(slot, resets_at, pct, now, lookback)
    if rate is None:
        return average
    return pct + rate * left
