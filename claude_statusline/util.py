"""Small tolerant helpers: payload digging, number coercion, formatting."""
from __future__ import annotations

import os
import subprocess
from datetime import datetime


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, val in (over or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def dig(obj, *path, default=None):
    for key in path:
        if not isinstance(obj, dict) or key not in obj:
            return default
        obj = obj[key]
    return obj if obj is not None else default


def num(value, default=None):
    """Coerce to float, tolerating the junk a host might hand us."""
    if value is None or isinstance(value, bool):
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out or out in (float("inf"), float("-inf")):
        return default                             # reject NaN and infinities
    return out


def short_num(n) -> str:
    n = num(n)
    if n is None:
        return "?"
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


def dur(seconds) -> str:
    seconds = max(0, int(num(seconds, 0)))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d{h}h"
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m"

def home_path(path: str) -> str:
    home = os.path.expanduser("~")
    if path == home:
        return "~"
    if path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def compact_path(path: str, keep: int = 3) -> str:
    disp = home_path(path)
    parts = disp.split(os.sep)
    if len(parts) <= keep + 1:
        return disp
    return os.sep.join(["…"] + parts[-keep:])


def to_epoch(value):
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            ts = float(value)
            return ts / 1000.0 if ts > 1e11 else ts
        text = str(value).strip().replace("Z", "+00:00")
        return datetime.fromisoformat(text).timestamp()
    except Exception:
        return None


def run(args, cwd=None, timeout=1.5):
    try:
        p = subprocess.run(args, cwd=cwd, timeout=timeout,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return p.stdout.decode("utf-8", "replace") if p.returncode == 0 else None
    except Exception:
        return None
