"""Your other Claude Code sessions on this machine, for the sessions panel.

Every session with the activity hooks keeps a small file in the runtime
directory (activity.py). This reads them all, leaves out this session and
sessions that have ended or gone quiet for `MAX_AGE`, and says what each is
doing: it needs you, it is working, or it is waiting for you. It runs no
process; a refresh pays one directory listing and a small read per session.
"""
from __future__ import annotations

import os

MAX_AGE = 6 * 3600.0
MAX = 12


def others(own_sid, now, max_age=MAX_AGE):
    """[[project, state, since, what]] for the other live sessions, those that need you first, then
    those working, then those waiting; the most recent first within each. State is ask, work or wait."""
    from .activity import load, project_of, tool_label
    from .config import runtime_dir
    try:
        names = os.listdir(runtime_dir())
    except OSError:
        return []
    own = f"activity-{own_sid}.bin" if own_sid else None
    out = []
    for n in names:
        if not n.startswith("activity-") or not n.endswith(".bin") or n == own:
            continue
        s = load(n[len("activity-"):-len(".bin")])
        if not s or s.get("closed") or now - float(s.get("at") or 0) > max_age:
            continue
        if s["ask"][0]:
            out.append([project_of(s), "ask", s["ask"][0], s["ask"][1]])
        elif s["turn"] and s["turn"] > s["stop"]:
            running = sorted((v for v in s["tools"].values() if not v[3]), key=lambda v: v[2])
            what = f"{tool_label(running[0][0])} {running[0][1]}".strip() if running else ""
            out.append([project_of(s), "work", s["turn"], what])
        elif s["stop"]:
            out.append([project_of(s), "wait", s["stop"], ""])
    rank = {"ask": 0, "work": 1, "wait": 2}
    out.sort(key=lambda r: (rank[r[1]], -r[2]))
    return out[:MAX]
