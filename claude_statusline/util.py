"""Small tolerant helpers: payload digging, number coercion, formatting."""
from __future__ import annotations

import os


def dig(obj, *path, default=None):
    for key in path:
        if not isinstance(obj, dict) or key not in obj:
            return default
        obj = obj[key]
    return obj if obj is not None else default


def num(value, default=None):
    """A finite float from whatever the host sent, or `default`."""
    if value is None or isinstance(value, bool):
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out or out in (float("inf"), float("-inf")):
        return default
    return out


def short_num(n) -> str:
    """12, 1.2k, 34k, 1.2M."""
    n = num(n)
    if n is None:
        return "?"
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1_000:.0f}k"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def dur(seconds, fine=False) -> str:
    """3d4h, 1h05m, 12m (or 45s with `fine`)."""
    seconds = max(0, int(num(seconds, 0)))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        return f"{d}d{h}h"
    if h:
        return f"{h}h{m:02d}m"
    if fine and not m:
        return f"{s}s"
    return f"{m}m"


def money(usd) -> str:
    usd = num(usd)
    if usd is None:
        return ""
    if usd >= 1000:
        return f"{usd / 1000:.1f}k"
    if usd >= 100:
        return f"{usd:.0f}"
    return f"{usd:.2f}"


def home_path(path: str, home=None) -> str:
    home = (home or os.path.expanduser("~")).rstrip(os.sep)
    if path == home:
        return "~"
    if path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def split_path(path: str, depth: int = 3, mode: str = "fish", home=None):
    """(parent, base) for display. Modes:

    fish     every parent component shortened to its first letter: ~/P/w/
    compact  the last `depth` components, …/ in front of the rest
    full     the whole path, ~ for home
    base     the last component only
    """
    disp = home_path(path, home).rstrip(os.sep) or os.sep
    if disp in ("~", os.sep):
        return "", disp
    parts = disp.split(os.sep)
    base = parts[-1]
    parents = parts[:-1]
    if mode == "base":
        return "", base
    if mode == "full":
        return os.sep.join(parents) + os.sep, base
    if mode == "fish":
        cut = len(parents) - max(0, depth - 1)       # parents after `cut` stay whole
        short = [p if i >= cut or p in ("~", "") else (p[:2] if p.startswith(".") else p[:1])
                 for i, p in enumerate(parents)]
        return os.sep.join(short) + os.sep, base
    keep = max(1, depth)
    if len(parts) <= keep + 1:
        return (os.sep.join(parents) + os.sep) if parents else "", base
    return "…" + os.sep + os.sep.join(parts[-keep:-1]) + (os.sep if keep > 1 else ""), base


def to_epoch(value):
    """Seconds since the epoch from epoch seconds, epoch ms, or ISO-8601."""
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float)):
            ts = float(value)
            return ts / 1000.0 if ts > 1e11 else ts
        text = str(value).strip()
        if text.replace(".", "", 1).isdigit():
            ts = float(text)
            return ts / 1000.0 if ts > 1e11 else ts
        from datetime import datetime
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None
