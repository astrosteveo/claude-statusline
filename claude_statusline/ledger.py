"""What today cost, across sessions: a small ledger the bar keeps itself.

The payload carries each session's running cost. The bar notes it per
session and per local day in `$XDG_STATE_HOME/claude-statusline/spend.bin`
(it has to outlive a reboot, so not the runtime directory). A session counts
toward a day only what it spent that day: the first time the bar sees it on
a day, its cost then is its baseline, unless the session had only just
begun. Writes happen at most every WRITE_EVERY seconds per session, under a
lock; a refresh otherwise only reads the file.

It is exact for the sessions this bar drew and blind to the rest
(`claude -p`, other machines, sessions with another status line).
"""
from __future__ import annotations

import os
import time

VERSION = 1
WRITE_EVERY = 30.0
NEW_SESSION_MS = 120_000       # a session younger than this counts from zero, not from its first sighting
KEEP_DAYS = 400
FORGET_SESSION = 3 * 86400


def path():
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "claude-statusline", "spend.bin")


def day_of(ts):
    t = time.localtime(ts)
    return f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"


def fresh(day):
    return {"v": VERSION, "day": day, "sessions": {}, "days": {}}


def read():
    import marshal
    try:
        with open(path(), "rb") as fh:
            led = marshal.loads(fh.read())
    except (OSError, ValueError, EOFError, TypeError):
        return None
    return led if isinstance(led, dict) and led.get("v") == VERSION else None


def roll(led, day):
    """Close the ledger's day if `day` is a new one. Sessions carry their cost over as the new baseline."""
    if led["day"] == day:
        return led
    total = sum(max(0.0, last - base) for base, last, _ in led["sessions"].values())
    if total:
        led["days"][led["day"]] = round(led["days"].get(led["day"], 0.0) + total, 6)
    led["days"] = dict(sorted(led["days"].items())[-KEEP_DAYS:])
    led["sessions"] = {sid: [last, last, seen] for sid, (base, last, seen) in led["sessions"].items()}
    led["day"] = day
    return led


def note(led, sid, cost, duration_ms, now):
    """Fold one reading into the ledger (in place)."""
    entry = led["sessions"].get(sid)
    if entry is None:
        base = 0.0 if duration_ms is not None and duration_ms < NEW_SESSION_MS else cost
        led["sessions"][sid] = [base, cost, now]
    else:
        if cost < entry[1]:                 # a cost that went down: the session restarted from zero under its
            entry[0] -= entry[1]            # old id; keep what it already spent today by lowering the baseline
        entry[1], entry[2] = cost, now
    led["sessions"] = {k: v for k, v in led["sessions"].items() if now - v[2] < FORGET_SESSION}


def totals(led, now, sid=None, cost=None, duration_ms=None):
    """{"today", "week", "month"} in dollars (the week is the last seven days), with this
    session's live cost folded in."""
    today = day_of(now)
    sessions = dict(led["sessions"]) if led else {}
    days = dict(led["days"]) if led else {}
    if led and led.get("day") != today:
        closed = sum(max(0.0, last - base) for base, last, _ in led["sessions"].values())
        if closed:
            days[led["day"]] = days.get(led["day"], 0.0) + closed
        sessions = {k: [last, last, seen] for k, (base, last, seen) in led["sessions"].items()}
    if sid is not None and cost is not None:
        entry = sessions.get(sid)
        if entry is None:
            base = 0.0 if duration_ms is not None and duration_ms < NEW_SESSION_MS else cost
            entry = [base, cost, 0]
        base = entry[0] - entry[1] if cost < entry[1] else entry[0]
        sessions[sid] = [base, cost, 0]
    now_total = sum(max(0.0, last - base) for base, last, _ in sessions.values())
    week = {day_of(now - i * 86400) for i in range(1, 7)}
    month = today[:7]
    return {"today": now_total,
            "week": now_total + sum(v for k, v in days.items() if k in week),
            "month": now_total + sum(v for k, v in days.items() if k.startswith(month) and k != today)}


def update(sid, cost, duration_ms, now):
    """Record a reading if it is due; the ledger as it now stands (or None)."""
    import fcntl
    import marshal
    dest = path()
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest + ".lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            led = read() or fresh(day_of(now))
            roll(led, day_of(now))
            note(led, sid, cost, duration_ms, now)
            tmp = f"{dest}.{os.getpid()}"
            with open(tmp, "wb") as fh:
                fh.write(marshal.dumps(led))
            os.replace(tmp, dest)
            return led
    except OSError:
        return None


def due(led, sid, cost, now):
    """Whether this reading should be written: new session, new day, or a change WRITE_EVERY old."""
    if led is None or led.get("day") != day_of(now):
        return True
    entry = led["sessions"].get(sid)
    if entry is None:
        return True
    return cost != entry[1] and now - entry[2] >= WRITE_EVERY
