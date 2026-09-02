"""Git state, cached on disk so a once-a-second refresh stays cheap."""
from __future__ import annotations

import hashlib
import json
import os
import time

from .config import CFG
from .util import num, run


def _cache_dir() -> str:
    base = os.environ.get("XDG_RUNTIME_DIR") or os.environ.get("TMPDIR")
    if not base or not os.path.isdir(base):
        # tempfile drags in shutil/fnmatch/re (~5 ms); only pay that off-path.
        if os.path.isdir("/tmp"):
            base = "/tmp"
        else:
            import tempfile
            base = tempfile.gettempdir()
    path = os.path.join(base, "claude-statusline")
    os.makedirs(path, exist_ok=True)
    return path


def _cache_file(root: str) -> str:
    tag = hashlib.sha1(root.encode("utf-8", "replace")).hexdigest()[:16]
    return os.path.join(_cache_dir(), f"git-{tag}.json")


def _repo_key(gitdir: str) -> str:
    """Cheap fingerprint that changes on commit / checkout / stage / merge.

    Worktree edits do not move these mtimes, so the TTL remains the real
    freshness bound; this key exists to invalidate *early* on ref changes.
    """
    parts = []
    for name in ("index", "HEAD", "MERGE_HEAD", "rebase-merge", "rebase-apply"):
        try:
            parts.append(f"{name}:{os.stat(os.path.join(gitdir, name)).st_mtime_ns}")
        except OSError:
            parts.append(f"{name}:-")
    return "|".join(parts)


def _cache_read(path: str, key: str):
    try:
        with open(path) as fh:
            blob = json.load(fh)
    except Exception:
        return None
    if blob.get("key") != key:
        return None
    gcfg = CFG["git"]
    ttl = gcfg["cache_ttl"]
    took = num(blob.get("took"), 0.0)
    if took > gcfg["slow_threshold"]:
        # Expensive repo: back off hard rather than stall every refresh.
        ttl = max(ttl, took * gcfg["slow_backoff"])
    if time.time() - num(blob.get("ts"), 0.0) > ttl:
        return None
    return blob.get("data")


def _cache_write(path: str, key: str, data, took: float) -> None:
    try:
        tmp = f"{path}.{os.getpid()}"
        with open(tmp, "w") as fh:
            json.dump({"key": key, "ts": time.time(), "took": took,
                       "data": data}, fh)
        os.replace(tmp, path)          # atomic; concurrent refreshes are safe
    except Exception:
        pass


# --------------------------------------------------------------------- git ---
def git_info(cwd: str):
    if not CFG["git"]["enabled"]:
        return None
    timeout = CFG["git"]["timeout"]
    top = run(["git", "rev-parse", "--path-format=absolute",
               "--show-toplevel", "--git-dir"], cwd=cwd, timeout=timeout)
    if not top:
        return None
    lines = top.strip().splitlines()
    if len(lines) < 2:
        return None
    root, gitdir = lines[0], lines[1]

    cache, key = _cache_file(root), _repo_key(gitdir)
    hit = _cache_read(cache, key)
    if hit is not None:
        return hit

    info = {"root": root, "gitdir": gitdir, "branch": None, "upstream": None,
            "ahead": 0, "behind": 0, "staged": 0, "dirty": 0, "untracked": 0,
            "conflict": 0, "stash": 0, "state": None, "sha": None,
            "last_commit": None}

    started = time.time()
    out = run(["git", "--no-optional-locks", "status", "--porcelain=v2",
               "--branch", "--untracked-files=normal"], cwd=cwd,
              timeout=max(timeout, 2.0))
    if out is None:
        return info
    for line in out.splitlines():
        if line.startswith("# branch.head "):
            head = line[14:].strip()
            info["branch"] = None if head == "(detached)" else head
        elif line.startswith("# branch.oid "):
            info["sha"] = line[13:].strip()[:7]
        elif line.startswith("# branch.upstream "):
            info["upstream"] = line[18:].strip()
        elif line.startswith("# branch.ab "):
            for tok in line[12:].split():
                if tok.startswith("+"):
                    info["ahead"] = int(tok[1:])
                elif tok.startswith("-"):
                    info["behind"] = int(tok[1:])
        elif line.startswith("u "):
            info["conflict"] += 1
        elif line.startswith("? "):
            info["untracked"] += 1
        elif line[:2] in ("1 ", "2 "):
            xy = line[2:4]
            if xy[0] != ".":
                info["staged"] += 1
            if xy[1] != ".":
                info["dirty"] += 1

    try:
        with open(os.path.join(gitdir, "logs", "refs", "stash")) as fh:
            info["stash"] = sum(1 for _ in fh)
    except Exception:
        pass

    def exists(*p):
        return os.path.exists(os.path.join(gitdir, *p))

    if exists("rebase-merge") or exists("rebase-apply"):
        info["state"] = "REBASE"
    elif exists("MERGE_HEAD"):
        info["state"] = "MERGE"
    elif exists("CHERRY_PICK_HEAD"):
        info["state"] = "CHERRY-PICK"
    elif exists("REVERT_HEAD"):
        info["state"] = "REVERT"
    elif exists("BISECT_LOG"):
        info["state"] = "BISECT"

    dirty = info["staged"] or info["dirty"] or info["conflict"]
    if CFG["features"]["last_commit"] and dirty:
        ct = run(["git", "--no-optional-locks", "log", "-1", "--format=%ct"],
                 cwd=cwd, timeout=timeout)
        if ct and ct.strip().isdigit():
            info["last_commit"] = int(ct.strip())

    _cache_write(cache, key, info, time.time() - started)
    return info
