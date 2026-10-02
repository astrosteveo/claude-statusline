"""Git state, without ever making the bar wait for git.

The branch comes straight from HEAD on every refresh (one small file read).
The counts come from `git status`, which can take anything from 5 ms to
seconds, so it runs in a detached background process that writes its answer
to a cache in the runtime directory; the bar draws whatever the cache holds
and asks for a new one when it goes stale. Stale-while-revalidate: at most a
refresh or two behind, never slow.

A cache entry is keyed on the mtimes of index, HEAD and the merge/rebase
markers, so a commit or checkout invalidates it at once; the TTL bounds how
stale worktree edits can get. A repository whose status is slow is polled
less often (`slow_threshold`, `slow_backoff`).
"""
from __future__ import annotations

import marshal
import os
import sys
import time

from .config import runtime_dir

LOCK_STALE = 15.0


def find_repo(cwd):
    """(worktree root, gitdir, common gitdir) for `cwd`, or None."""
    path = os.path.abspath(cwd or ".")
    while True:
        dotgit = os.path.join(path, ".git")
        if os.path.isdir(dotgit):
            return path, dotgit, dotgit
        if os.path.isfile(dotgit):
            try:
                with open(dotgit) as fh:
                    line = fh.readline().strip()
            except OSError:
                return None
            if line.startswith("gitdir:"):
                gitdir = line[7:].strip()
                if not os.path.isabs(gitdir):
                    gitdir = os.path.normpath(os.path.join(path, gitdir))
                common = gitdir
                try:
                    with open(os.path.join(gitdir, "commondir")) as fh:
                        rel = fh.read().strip()
                    common = os.path.normpath(os.path.join(gitdir, rel))
                except OSError:
                    pass
                return path, gitdir, common
            return None
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent


def read_head(gitdir):
    """(branch or None, short sha or None) straight from HEAD."""
    try:
        with open(os.path.join(gitdir, "HEAD")) as fh:
            head = fh.read().strip()
    except OSError:
        return None, None
    if head.startswith("ref:"):
        ref = head[4:].strip()
        return (ref[11:] if ref.startswith("refs/heads/") else ref), None
    return None, head[:7] or None


def repo_key(gitdir) -> str:
    parts = []
    for name in ("index", "HEAD", "MERGE_HEAD", "rebase-merge", "rebase-apply"):
        try:
            parts.append(str(os.stat(os.path.join(gitdir, name)).st_mtime_ns))
        except OSError:
            parts.append("-")
    return "|".join(parts)


def _paths(root, kind="git"):
    """(cache, lock) for `root`: `kind` keeps the status and the git panels apart."""
    import zlib
    tag = "%08x" % zlib.crc32(root.encode("utf-8", "replace"))
    base = os.path.join(runtime_dir(), f"{kind}-{tag}")
    return base + ".bin", base + ".lock"


def _load(path):
    try:
        with open(path, "rb") as fh:
            return marshal.loads(fh.read())
    except Exception:
        return None


def _save(path, blob):
    try:
        tmp = f"{path}.{os.getpid()}"
        with open(tmp, "wb") as fh:
            marshal.dump(blob, fh)
        os.replace(tmp, path)
    except OSError:
        pass


def spawn_refresh(module, lock, args):
    """Run `module`'s _refresh_main(args) in a detached process, unless a live lock says one
    already runs. The refresh unlinks the lock when it is done."""
    now = time.time()
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        try:
            if now - os.stat(lock).st_mtime < LOCK_STALE:
                return
            os.unlink(lock)
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except OSError:
            return
    except OSError:
        return
    os.close(fd)
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = ("import sys; sys.path.insert(0, sys.argv[1]); "
            f"from claude_statusline.{module} import _refresh_main; _refresh_main(sys.argv[2:])")
    spawn_detached([sys.executable, "-S", "-c", code, parent, *map(str, args)])


def unlock(lock):
    try:
        os.unlink(lock)
    except OSError:
        pass


def status(cwd, cfg, sync=False, last_commit=True):
    """Git state for `cwd` (dict), or None outside a repository."""
    if not cfg.get("enabled", True):
        return None
    repo = find_repo(cwd)
    if repo is None:
        return None
    root, gitdir, common = repo
    branch, sha = read_head(gitdir)
    cache, lock = _paths(root)
    blob = _load(cache)
    key = repo_key(gitdir)
    data = blob.get("data") if isinstance(blob, dict) else None
    fresh = False
    if data is not None and blob.get("key") == key and blob.get("lc", True) >= last_commit:
        ttl = float(cfg.get("cache_ttl", 2.0))
        took = float(blob.get("took") or 0.0)
        if took > float(cfg.get("slow_threshold", 0.35)):
            ttl = max(ttl, took * float(cfg.get("slow_backoff", 10.0)))
        fresh = time.time() - float(blob.get("ts") or 0) <= ttl
    if not fresh:
        if sync:
            data = refresh(root, gitdir, common, last_commit, float(cfg.get("timeout", 2.0)))
        else:
            spawn_refresh("gitstatus", lock, [root, gitdir, common, "1" if last_commit else "0",
                                              float(cfg.get("timeout", 2.0)), lock])
    out = dict(data) if data else {"branch": None, "sha": None, "upstream": None, "ahead": 0,
                                   "behind": 0, "staged": 0, "dirty": 0, "untracked": 0,
                                   "conflict": 0, "stash": 0, "state": None, "last_commit": None,
                                   "pending": True}
    out["root"] = root
    out["branch"] = branch
    out["sha"] = sha if branch is None else out.get("sha")
    out["state"] = _state(gitdir) or None
    return out


def _state(gitdir):
    def has(*p):
        return os.path.exists(os.path.join(gitdir, *p))
    if has("rebase-merge") or has("rebase-apply"):
        return "REBASE"
    if has("MERGE_HEAD"):
        return "MERGE"
    if has("CHERRY_PICK_HEAD"):
        return "CHERRY-PICK"
    if has("REVERT_HEAD"):
        return "REVERT"
    if has("BISECT_LOG"):
        return "BISECT"
    return ""


def spawn_detached(argv):
    """Start `argv` in its own session with no stdio, and do not wait for it."""
    devnull = os.devnull
    try:
        actions = [(os.POSIX_SPAWN_OPEN, 0, devnull, os.O_RDONLY, 0),
                   (os.POSIX_SPAWN_OPEN, 1, devnull, os.O_WRONLY, 0),
                   (os.POSIX_SPAWN_OPEN, 2, devnull, os.O_WRONLY, 0)]
        os.posix_spawn(argv[0], argv, dict(os.environ), file_actions=actions, setsid=True)
        return True
    except (AttributeError, NotImplementedError, OSError, TypeError):
        pass
    try:
        import subprocess
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
        return True
    except Exception:
        return False


def _refresh_main(args):
    root, gitdir, common, lc, timeout, lock = args
    try:
        refresh(root, gitdir, common, lc == "1", float(timeout))
    finally:
        unlock(lock)


def _run(args, cwd, timeout):
    import subprocess
    try:
        p = subprocess.run(args, cwd=cwd, timeout=timeout, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0",
                                                               LC_ALL="C"))
        return p.stdout.decode("utf-8", "replace") if p.returncode == 0 else None
    except Exception:
        return None


def refresh(root, gitdir, common, last_commit=True, timeout=2.0):
    """Run git, write the cache, and return the data."""
    key = repo_key(gitdir)
    started = time.time()
    info = {"branch": None, "sha": None, "upstream": None, "ahead": 0, "behind": 0, "staged": 0,
            "dirty": 0, "untracked": 0, "conflict": 0, "stash": 0, "state": None,
            "last_commit": None}
    out = _run(["git", "--no-optional-locks", "status", "--porcelain=v2", "--branch",
                "--untracked-files=normal"], root, max(timeout, 2.0))
    if out is not None:
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
                    if tok.startswith("+") and tok[1:].isdigit():
                        info["ahead"] = int(tok[1:])
                    elif tok.startswith("-") and tok[1:].isdigit():
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
        with open(os.path.join(common, "logs", "refs", "stash"), "rb") as fh:
            info["stash"] = sum(1 for _ in fh)
    except OSError:
        pass
    if last_commit and (info["staged"] or info["dirty"] or info["conflict"]):
        ct = _run(["git", "--no-optional-locks", "log", "-1", "--format=%ct"], root, timeout)
        if ct and ct.strip().isdigit():
            info["last_commit"] = int(ct.strip())
    took = time.time() - started
    _save(_paths(root)[0], {"key": key, "ts": time.time(), "took": took, "lc": bool(last_commit),
                             "data": info})
    return info
