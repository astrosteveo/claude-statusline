"""Bundled sample payloads for previews, and the live one the bar last saw."""
from __future__ import annotations

import os
import re
import time

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")
_REL = re.compile(r"^([+-])((?:\d+[smhd])+)$")
_UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def names():
    out = sorted(f[:-5] for f in os.listdir(DIR) if f.endswith(".json"))
    return (["live"] if live_path() else []) + out


def live_path():
    from .config import runtime_dir
    path = os.path.join(runtime_dir(), "last-payload.json")
    return path if os.path.exists(path) else None


def _relative(value, now):
    m = _REL.match(value)
    if not m:
        return value
    secs = sum(int(n) * _UNIT[u] for n, u in re.findall(r"(\d+)([smhd])", m.group(2)))
    return now + secs if m.group(1) == "+" else now - secs


def _resolve(obj, now):
    if isinstance(obj, dict):
        return {k: (_relative(v, now) if k in ("resets_at", "resetsAt") and isinstance(v, str)
                    else _resolve(v, now)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve(v, now) for v in obj]
    return obj


def load(name, now=None) -> dict:
    """A sample by name ('busy', 'live', ...) or any JSON file by path.
    Reset times written as "+1h43m" resolve against `now` so bars look live."""
    import json
    if name == "live":
        path = live_path()
        if not path:
            raise FileNotFoundError("no live payload yet: the bar saves one once it has run")
    else:
        path = name if os.path.exists(name) else os.path.join(DIR, f"{name}.json")
    with open(path) as fh:
        data = json.load(fh)
    return _resolve(data, time.time() if now is None else now)
