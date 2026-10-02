"""Every Claude Code session on this machine, from agentboard, for the fleet map.

A detached process asks a running `agentboard web` for its snapshot. When none
answers it starts one in the background (at most once a minute;
CLAUDE_STATUSLINE_AGENTBOARD=off stops that) and runs `agentboard -once -json`
meanwhile, about a second of CPU, so at most every 15 seconds. It keeps one
small cache for the whole machine, so every session's bar shares one refresh
and never waits on agentboard. Without agentboard the map says how to get it.

The bar saves the payload Claude Code gives it to `last-payload.json`, which
agentboard reads for each model's context window and the account's limits.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime

from .gitstatus import _load, _save, spawn_detached, spawn_refresh, unlock

TTL = 3.0
CLI_TTL = 15.0                  # `agentboard -once -json` reads every transcript: about a second of CPU
DEFAULT_URL = "http://127.0.0.1:7777"
URL = os.environ.get("AGENTBOARD_URL", DEFAULT_URL)
# The page keeps its token per host, and agentboard's own link says localhost.
PAGE_URL = "http://localhost:7777" if URL == DEFAULT_URL else URL
START_EVERY = 60.0              # seconds between tries to start `agentboard web`
PAYLOAD_EVERY = 5.0             # seconds between saves of the payload
TICKS = 400                     # tool calls kept per session for the timeline
ORDER = {"needs": 0, "turn": 1, "working": 2, "settled": 3}


def _paths():
    from .config import runtime_dir
    base = os.path.join(runtime_dir(), "fleet")
    return base + ".bin", base + ".lock"


def payload_path():
    from .config import runtime_dir
    return os.path.join(runtime_dir(), "last-payload.json")


def data(sync=False, spawn=True):
    """{"rows": [...], "at", "src": "web" or "cli", "window"} or {"missing": True} when there is
    no agentboard; None before the first answer. Each row is a dict (see `rows`)."""
    cache, lock = _paths()
    blob = _load(cache)
    out = blob.get("data") if isinstance(blob, dict) else None
    ttl = TTL if isinstance(out, dict) and out.get("src") == "web" else CLI_TTL
    if out is None or time.time() - float(blob.get("ts") or 0) > ttl:
        if sync:
            out = refresh()
        elif spawn:
            spawn_refresh("fleet", lock, [lock])
    return out


def _refresh_main(args):
    try:
        refresh(start=True)
    finally:
        unlock(args[0])


def refresh(start=False):
    snap, src = _from_server(), "web"
    if snap is None:
        if start:
            _start_server()
        snap, src = _from_cli(), "cli"
    out = {"missing": True} if snap is None else \
        {"rows": rows(snap), "at": time.time(), "src": src,
         "window": float(snap.get("windowMs") or 3_600_000) / 1000}
    _save(_paths()[0], {"ts": time.time(), "data": out})
    return out


def _exe():
    exe = shutil.which("agentboard") or os.path.expanduser("~/.local/bin/agentboard")
    return exe if os.access(exe, os.X_OK) else None


def _from_server():
    from urllib.request import urlopen
    try:
        with urlopen(URL + "/api/snapshot", timeout=0.5) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _from_cli():
    exe = _exe()
    if not exe:
        return None
    try:
        p = subprocess.run([exe, "-once", "-json", "-statusline-payload", payload_path()],
                           capture_output=True, timeout=10)
        return json.loads(p.stdout) if p.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _start_server():
    """Start `agentboard web` on the default address, at most once a minute across every session."""
    if os.environ.get("CLAUDE_STATUSLINE_AGENTBOARD") == "off" or URL != DEFAULT_URL:
        return False
    exe = _exe()
    if not exe:
        return False
    from .config import runtime_dir
    stamp = os.path.join(runtime_dir(), "agentboard-start")
    try:
        if time.time() - os.stat(stamp).st_mtime < START_EVERY:
            return False
    except OSError:
        pass
    try:
        with open(stamp, "w"):
            pass
    except OSError:
        return False
    return spawn_detached([exe, "web", "-statusline-payload", payload_path()])


def save_payload(payload, now=None):
    """Keep the payload where agentboard reads it (mode 0600: it holds paths and cost)."""
    path = payload_path()
    now = time.time() if now is None else now
    try:
        if now - os.stat(path).st_mtime < PAYLOAD_EVERY:
            return
    except OSError:
        pass
    tmp = f"{path}.{os.getpid()}"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump({k: v for k, v in payload.items() if not k.startswith("_")}, fh)
        os.replace(tmp, path)
    except (OSError, TypeError, ValueError):
        try:
            os.unlink(tmp)
        except OSError:
            pass


def focus(key):
    """Ask agentboard to bring the session's kitty window or tmux pane forward. Its answer,
    or ValueError with agentboard's reason."""
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen
    try:
        with open(os.path.expanduser("~/.config/agentboard/token")) as fh:
            token = fh.read().strip()
    except OSError:
        raise ValueError("agentboard has no token yet; run `agentboard web` once") from None
    req = Request(f"{URL}/api/sessions/{key}/focus", data=b"{}", method="POST",
                  headers={"X-Agentboard": "1", "X-Agentboard-Token": token, "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=4) as r:
            return json.loads(r.read()).get("message") or "focused"
    except HTTPError as exc:
        try:
            body = json.loads(exc.read())
        except ValueError:
            body = {}
        raise ValueError(body.get("message") or body.get("error") or f"agentboard said {exc.code}") from None
    except OSError:
        raise ValueError("agentboard web isn't running") from None


def _ts(s):
    """An agentboard time (RFC 3339, up to 9 digits of fraction) as Unix seconds, or 0."""
    if not isinstance(s, str) or not s:
        return 0.0
    s = re.sub(r"(\.\d{6})\d+", r"\1", s.replace("Z", "+00:00"))
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return 0.0


def _one_line(s):
    return " ".join(str(s or "").split())


def _row(r, ticks):
    repo = r.get("repo")
    project = repo.get("name") if isinstance(repo, dict) and repo.get("name") else \
        os.path.basename((r.get("cwd") or "").rstrip("/")) or "?"
    section = r.get("section") if r.get("section") in ORDER else "settled"
    ask = r.get("ask") if isinstance(r.get("ask"), dict) else {}
    what = ask.get("text") if section == "needs" and ask.get("text") else r.get("activity") or r.get("label")
    win = r.get("window") if isinstance(r.get("window"), dict) else {}
    where = "bg" if r.get("kind") == "background" else \
        f"{win['kind']} {win.get('id', '')}".strip() if win.get("kind") else "app" \
        if r.get("entrypoint") == "claude-desktop" else "cli"
    key = r.get("key") or r.get("sessionId") or ""
    mine = ticks.get(key) or []
    pct = r.get("contextPct")
    return {
        "key": key,
        "sids": [r.get("sessionId") or ""],
        "parent": r.get("forkOf") if isinstance(r.get("forkOf"), dict) else None,
        "project": project,
        "section": section,
        "failed": r.get("state") == "failed",
        "title": _one_line(r.get("title") or r.get("name")) or "untitled",
        "what": _one_line(what),
        "since": _ts(r.get("sectionSince") or r.get("lastActive")),
        "where": where,
        "window": bool(win.get("kind")),
        "fork": bool(r.get("forkOf")),
        "count": 1,
        "flags": [f for f in r.get("flags") or [] if isinstance(f, str)],
        "fresh": r.get("lastPrompt") is None and section == "settled",
        "agents": [_one_line(a.get("label") or a.get("type")) for a in r.get("subagents") or []
                   if isinstance(a, dict)],
        "ctx": int(pct) if isinstance(pct, (int, float)) and not isinstance(pct, bool) else None,
        "tokens": int(r.get("contextTokens") or 0),
        "model": r.get("model") or "",
        "ticks": [t for t, _ in mine][-TICKS:],
        "flare": list(mine[-1]) if mine else None,
    }


def _merge(group):
    """Forks of one session in one section as one row: the original if it is there, with a count."""
    head = dict(next((r for r in group if not r["fork"]), group[0]))
    if len(group) > 1:
        head["count"] = len(group)
        head["sids"] = [s for r in group for s in r["sids"]]
        head["since"] = max(r["since"] for r in group)
        head["agents"] = [a for r in group for a in r["agents"]]
        head["flags"] = sorted({f for r in group for f in r["flags"]})
        head["ticks"] = sorted(t for r in group for t in r["ticks"])[-TICKS:]
        flares = [r["flare"] for r in group if r["flare"]]
        head["flare"] = max(flares, key=lambda f: f[0]) if flares else None
    return head


def rows(snap):
    """The snapshot's sessions, trimmed to what the map draws, forks merged, in queue order: what
    needs you first, failed background jobs after the sessions that ask something."""
    ticks = {}
    for e in snap.get("events") or []:
        if isinstance(e, dict) and e.get("kind") == "tool" and e.get("session"):
            ticks.setdefault(e["session"], []).append((_ts(e.get("at")), str(e.get("tool") or "")))
    for v in ticks.values():
        v.sort()
    all_ = [_row(r, ticks) for r in snap.get("rows") or [] if isinstance(r, dict)]
    keys = {r["key"] for r in all_}
    titled = {(r["project"], r["title"]): r["key"] for r in all_ if not r["parent"]}
    groups = {}
    for row in all_:                              # a fork joins its original, found by key or else by title
        p = row.pop("parent") or {}
        root = p.get("key") if p.get("key") in keys else \
            titled.get((row["project"], _one_line(p.get("title")))) or p.get("key") or row["key"]
        groups.setdefault((root, row["section"]), []).append(row)
    out = [_merge(g) for g in groups.values()]
    out.sort(key=lambda r: (ORDER[r["section"]], r["failed"], -r["since"]))
    return out
