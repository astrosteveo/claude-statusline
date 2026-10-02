"""GitHub Actions for this branch, for the CI panel, without ever making the bar wait.

A detached process runs `gh run list` and writes a cache in the runtime
directory, the same stale-while-revalidate as gitstatus.py. It asks again
every 15 seconds while a run is queued or running and every minute
otherwise; a commit or a push changes the cache key, so it asks at once.
Offline, the last answer stays and is marked stale. Only github.com remotes
are asked, and only when `gh` is installed.

When a run on this branch's commit (or its upstream's) finishes, the
refresher that sees it finish sends one desktop pop-up ([panels] notify).
It never announces runs it did not see running.
"""
from __future__ import annotations

import os
import time

from .gitstatus import _load, _paths, _save, read_head, spawn_refresh, unlock

ACTIVE_TTL = 15.0
IDLE_TTL = 60.0
GH_TIMEOUT = 10.0          # under gitstatus.LOCK_STALE, so a slow network never starts a second refresher
RUNS = 20
FIELDS = "databaseId,workflowName,displayTitle,status,conclusion,headSha,event,createdAt,startedAt,updatedAt,url"


def ci_key(gitdir, common, branch):
    parts = [branch or ""]
    for path in (os.path.join(gitdir, "logs", "HEAD"),
                 os.path.join(common, "logs", "refs", "remotes", "origin", branch or "-")):
        try:
            parts.append(str(os.stat(path).st_mtime_ns))
        except OSError:
            parts.append("-")
    return "|".join(parts)


def data(root, gitdir, common, cfg, sync=False, spawn=True):
    """{"runs": [...], "branch", "stale"}, {"pending": True} before the first answer, or None
    where there is nothing to ask (detached HEAD, no GitHub remote, no gh)."""
    branch, _ = read_head(gitdir)
    if not branch:
        return None
    cache, lock = _paths(root, "ci")
    blob = _load(cache)
    key = ci_key(gitdir, common, branch)
    out = blob.get("data") if isinstance(blob, dict) else None
    fresh = False
    if out is not None and blob.get("key") == key:
        active = any(r[3] != "completed" for r in out.get("runs") or [])
        fresh = time.time() - float(blob.get("ts") or 0) <= (ACTIVE_TTL if active else IDLE_TTL)
    if not fresh:
        if sync:                        # previews and tests: no pop-ups
            out = refresh(root, gitdir, common, branch)
        elif spawn:
            notify = "1" if cfg.get("notify", True) else "0"
            spawn_refresh("ci", lock, [root, gitdir, common, branch, notify, lock])
    if out is None:
        return {"pending": True}
    if out.get("skip"):
        return None
    return out


def _refresh_main(args):
    root, gitdir, common, branch, notify, lock = args
    try:
        refresh(root, gitdir, common, branch, notify == "1")
    finally:
        unlock(lock)


def _git(args, root):
    from .gitstatus import _run
    return _run(["git", "--no-optional-locks", *args], root, 2.0)


def _epoch(iso):
    """2026-10-02T04:31:34Z -> seconds since the epoch (0 when unset)."""
    if not iso or iso.startswith("0001"):
        return 0
    import calendar
    try:
        return calendar.timegm(time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return 0


def on_github(root):
    url = (_git(["remote", "get-url", "origin"], root) or "").strip()
    return "github.com" in url


def ask_gh(root, branch):
    """The runs for `branch` from gh, newest first, or None when gh could not answer."""
    import json
    import subprocess
    try:
        p = subprocess.run(["gh", "run", "list", "--branch", branch, "-L", str(RUNS), "--json", FIELDS],
                           cwd=root, timeout=GH_TIMEOUT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    try:
        raw = json.loads(p.stdout or b"[]")
    except ValueError:
        return None
    return raw if isinstance(raw, list) else None


def runs_of(raw):
    """The latest run of each workflow, as tuples: (id, workflow, title, status, conclusion,
    head sha, started, updated, url, event)."""
    seen, out = set(), []
    for r in raw:
        if not isinstance(r, dict) or r.get("workflowName") in seen:
            continue
        seen.add(r.get("workflowName"))
        out.append((r.get("databaseId") or 0, str(r.get("workflowName") or "?"), str(r.get("displayTitle") or ""),
                    str(r.get("status") or ""), str(r.get("conclusion") or ""), str(r.get("headSha") or ""),
                    _epoch(r.get("startedAt")) or _epoch(r.get("createdAt")), _epoch(r.get("updatedAt")),
                    str(r.get("url") or ""), str(r.get("event") or "")))
    return out


def finished(before, after, shas):
    """Runs on one of `shas` that were queued or running in `before` and are done in `after`."""
    was = {r[0]: r[3] for r in before}
    return [r for r in after if r[3] == "completed" and was.get(r[0]) not in (None, "completed") and r[5] in shas]


def refresh(root, gitdir, common, branch, notify=False):
    cache, _ = _paths(root, "ci")
    key = ci_key(gitdir, common, branch)
    old = _load(cache)
    old = old.get("data") if isinstance(old, dict) else None
    import shutil
    if not shutil.which("gh") or not on_github(root):
        info = {"skip": True}
    else:
        raw = ask_gh(root, branch)
        if raw is None:
            info = dict(old or {"runs": []}, stale=True)
        else:
            info = {"runs": runs_of(raw), "branch": branch, "stale": False}
            if notify and old and old.get("runs") and not old.get("skip"):
                shas = {s.strip() for s in ((_git(["rev-parse", "HEAD"], root) or "") + "\n" +
                                            (_git(["rev-parse", "@{u}"], root) or "")).split() if s.strip()}
                for r in finished(old["runs"], info["runs"], shas):
                    pop_up(r)
    _save(cache, {"key": key, "ts": time.time(), "data": info})
    return info


def pop_up(run):
    import shutil
    from .gitstatus import spawn_detached
    if not shutil.which("notify-send"):
        return
    ok = run[4] == "success"
    word = {"success": "passed", "failure": "failed", "cancelled": "was cancelled",
            "timed_out": "timed out"}.get(run[4], run[4] or "finished")
    spawn_detached(["notify-send", "-a", "claude-statusline", "-i", "dialog-information" if ok else "dialog-error",
                    f"{run[1]} {word}", run[2]])


# ---- rerunning a failed run from the panel --------------------------------------------------
# A link anything in the terminal can print must not spend CI minutes, so a rerun takes two
# clicks. `rerun/ask/<cache tag>/<run>` only remembers the run, and only one that the cache holds
# as failed; the panel then shows `rerun? yes · no`, and the yes link carries a fresh random
# token that only the bar has seen. The question lapses after CONFIRM seconds.
CONFIRM = 120.0
RERUNNABLE = ("failure", "timed_out", "cancelled", "startup_failure")


def pending_path(sid):
    from .config import runtime_dir
    return os.path.join(runtime_dir(), f"rerun-{sid}.json")


def pending(sid, now):
    """The rerun this session is asking about ({"run", "token", "at", "name"}), or None."""
    import json
    try:
        with open(pending_path(sid)) as fh:
            p = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(p, dict) or now - float(p.get("at") or 0) > CONFIRM:
        return None
    return p


def cache_tag(root):
    return os.path.basename(_paths(root, "ci")[0])[3:-4]


def _cached_run(tag, run):
    from .config import runtime_dir
    if not (tag.isalnum() and run.isdigit()):
        return None
    blob = _load(os.path.join(runtime_dir(), f"ci-{tag}.bin"))
    runs = ((blob or {}).get("data") or {}).get("runs") or [] if isinstance(blob, dict) else []
    return next((r for r in runs if str(r[0]) == run and r[3] == "completed" and r[4] in RERUNNABLE), None)


def rerun_click(sid, args, now):
    """What a rerun link does: ask, yes or no. Returns what it did; ValueError when it may not."""
    import json
    import secrets
    step = args[0]
    path = pending_path(sid)
    if step == "ask":
        r = _cached_run(args[1], args[2])
        if r is None:
            raise ValueError("no such failed run")
        p = {"run": r[0], "name": r[1], "url": r[8], "tag": args[1], "token": secrets.token_hex(8), "at": now}
        tmp = f"{path}.{os.getpid()}"
        with open(tmp, "w") as fh:
            json.dump(p, fh)
        os.replace(tmp, path)
        return f"rerun {r[1]}?"
    p = pending(sid, now)
    try:
        os.unlink(path)
    except OSError:
        pass
    if step == "no":
        return "kept the run as it is"
    if step != "yes" or not p or not secrets.compare_digest(str(p.get("token")), args[1]):
        raise ValueError("that rerun button has lapsed")
    from .reviews import owner_name
    where = owner_name((p.get("url") or "").split("/actions/")[0])
    if not where or _cached_run(p["tag"], str(p["run"])) is None:
        raise ValueError("that run is no longer a failed one")
    from .gitstatus import spawn_detached
    import shutil
    gh = shutil.which("gh")
    if not gh:
        raise ValueError("gh is not installed")
    spawn_detached([gh, "run", "rerun", str(p["run"]), "--failed", "--repo", "/".join(where)])
    from .config import runtime_dir
    cache = os.path.join(runtime_dir(), f"ci-{p['tag']}.bin")
    blob = _load(cache)
    if isinstance(blob, dict):
        blob["ts"] = 0                  # ask again on the next refresh: the run is queued now
        _save(cache, blob)
    return f"rerunning the failed jobs of {p['name']}"
