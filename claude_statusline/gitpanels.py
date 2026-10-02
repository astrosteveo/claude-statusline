"""What the git panels show, without ever making the bar wait for git.

The same stale-while-revalidate as gitstatus.py: a detached process runs git
and writes a cache in the runtime directory, and the bar draws whatever the
cache holds. One refresh reads everything the panels need: the changed
files with their line counts, the commit graph, the branches and the
stashes. Each call is bounded (a commit count, a branch count) so a big
repository costs no more than a small one.

The cache key adds the reflogs and packed refs to gitstatus's key, so a
commit, a fetch or a stash shows at once rather than when the TTL runs out.
A rebase or merge in progress is read straight from its files on every
refresh, since it changes step by step.
"""
from __future__ import annotations

import os
import time

from .gitstatus import _load, _paths, _run, _save, find_repo, repo_key, spawn_refresh, unlock

BRANCHES = 30
STASHES = 10
SEP = "\x1f"


def panel_key(gitdir, common):
    parts = [repo_key(gitdir)]
    for base, name in ((gitdir, os.path.join("logs", "HEAD")), (common, "packed-refs"),
                       (common, "FETCH_HEAD"), (common, os.path.join("logs", "refs", "stash"))):
        try:
            parts.append(str(os.stat(os.path.join(base, name)).st_mtime_ns))
        except OSError:
            parts.append("-")
    return "|".join(parts)


def data(cwd, cfg, git_cfg, sync=False, spawn=True):
    """What the panels show for `cwd` (dict), or None outside a repository.
    Before the first refresh lands it holds {"pending": True}."""
    repo = find_repo(cwd)
    if repo is None:
        return None
    root, gitdir, common = repo
    cache, lock = _paths(root, "panels")
    blob = _load(cache)
    key = panel_key(gitdir, common)
    out = blob.get("data") if isinstance(blob, dict) else None
    commits = int(cfg.get("commits", 40))
    fresh = False
    if out is not None and blob.get("key") == key and blob.get("n") == commits:
        ttl = float(cfg.get("cache_ttl", 3.0))
        took = float(blob.get("took") or 0.0)
        if took > float(git_cfg.get("slow_threshold", 0.35)):
            ttl = max(ttl, took * float(git_cfg.get("slow_backoff", 10.0)))
        fresh = time.time() - float(blob.get("ts") or 0) <= ttl
    timeout = float(git_cfg.get("timeout", 2.0))
    if not fresh:
        if sync:
            out = refresh(root, gitdir, common, commits, timeout)
        elif spawn:
            spawn_refresh("gitpanels", lock, [root, gitdir, common, commits, timeout, lock])
    out = dict(out) if out else {"pending": True}
    out["root"], out["gitdir"], out["common"] = root, gitdir, common
    out["progress"] = progress(gitdir)
    return out


def _refresh_main(args):
    root, gitdir, common, commits, timeout, lock = args
    try:
        refresh(root, gitdir, common, int(commits), float(timeout))
    finally:
        unlock(lock)


def _git(args, root, timeout):
    return _run(["git", "--no-optional-locks", *args], root, timeout)


def refresh(root, gitdir, common, commits=40, timeout=2.0):
    """Run git, write the cache, and return the data."""
    key = panel_key(gitdir, common)
    started = time.time()
    info = {"files": changed_files(root, timeout), "graph": graph(root, commits, timeout),
            "branches": branches(root, timeout), "stashes": stashes(root, common, timeout)}
    took = time.time() - started
    _save(_paths(root, "panels")[0], {"key": key, "ts": time.time(), "took": took, "n": commits, "data": info})
    return info


def changed_files(root, timeout):
    """[(XY status, path, added, removed)]: added/removed are None for binary or untracked files."""
    out = _git(["status", "--porcelain=v1", "-z", "--no-renames", "--untracked-files=normal"], root, timeout)
    if out is None:
        return []
    files = []
    for entry in out.split("\0"):
        if len(entry) > 3:
            files.append([entry[:2], entry[3:], None, None])
    if not files:
        return []
    counts = {}
    num = _git(["diff", "--numstat", "-z", "--no-renames", "HEAD"], root, timeout)
    for entry in (num or "").split("\0"):
        parts = entry.split("\t", 2)
        if len(parts) == 3:
            a, r, path = parts
            counts[path] = (int(a) if a.isdigit() else None, int(r) if r.isdigit() else None)
    for f in files:
        f[2], f[3] = counts.get(f[1], (None, None))
    return [tuple(f) for f in files]


def graph(root, commits, timeout):
    """[(graph prefix, full sha or "", refs, commit time, subject)]: a row with no sha is a connector."""
    fmt = "%x1e" + "%x1f".join(["%H", "%D", "%ct", "%s"])
    out = _git(["log", "--graph", "--date-order", f"-n{commits}", f"--format={fmt}", "HEAD", "--branches"],
               root, timeout)
    if out is None:
        return []
    rows = []
    for line in out.split("\n"):
        prefix, mark, rest = line.partition("\x1e")
        if not mark:
            if not prefix.strip():
                continue
            rows.append((prefix.rstrip(), "", "", 0, ""))
            continue
        parts = rest.split(SEP, 3)
        if len(parts) < 4:
            continue
        sha, refs, ct, subject = parts
        rows.append((prefix, sha, refs, int(ct) if ct.isdigit() else 0, subject))
    return rows


def default_branch(root, timeout):
    out = _git(["symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"], root, timeout)
    if out and out.strip():
        return out.strip().split("/", 1)[-1]
    for name in ("main", "master", "trunk"):
        if _git(["rev-parse", "-q", "--verify", f"refs/heads/{name}"], root, timeout) is not None:
            return name
    return None


def branches(root, timeout):
    """[(current, name, upstream, track, commit time, merged into the default branch)], newest first."""
    fmt = "%1f".join(["%(HEAD)", "%(refname:short)", "%(upstream:short)", "%(upstream:track,nobracket)",
                      "%(committerdate:unix)"])
    out = _git(["for-each-ref", "--sort=-committerdate", f"--count={BRANCHES}", f"--format={fmt}",
                "refs/heads"], root, timeout)
    if out is None:
        return []
    default = default_branch(root, timeout)
    merged = set()
    if default:
        m = _git(["for-each-ref", f"--merged=refs/heads/{default}", "--format=%(refname:short)", "refs/heads"],
                 root, timeout)
        merged = set((m or "").split())
    rows = []
    for line in out.split("\n"):
        parts = line.split(SEP)
        if len(parts) != 5:
            continue
        head, name, upstream, track, ct = parts
        rows.append((head == "*", name, upstream, track, int(ct) if ct.isdigit() else 0,
                     name in merged and name != default and head != "*"))
    return rows


def stashes(root, common, timeout):
    """[(index, commit time, message)], newest first."""
    if not os.path.exists(os.path.join(common, "logs", "refs", "stash")):
        return []
    out = _git(["stash", "list", f"-n{STASHES}", "--format=%gd%x1f%ct%x1f%gs"], root, timeout)
    rows = []
    for line in (out or "").split("\n"):
        parts = line.split(SEP, 2)
        if len(parts) != 3:
            continue
        ref, ct, msg = parts
        idx = ref[ref.find("{") + 1:ref.find("}")] if "{" in ref else ref
        rows.append((idx, int(ct) if ct.isdigit() else 0, msg))
    return rows


def _read(*parts):
    try:
        with open(os.path.join(*parts)) as fh:
            return fh.read().strip()
    except OSError:
        return ""


def progress(gitdir):
    """A rebase, merge, cherry-pick, revert or bisect in progress, as a dict, or None."""
    def short(ref):
        return ref[11:] if ref.startswith("refs/heads/") else ref[:7]
    rm = os.path.join(gitdir, "rebase-merge")
    if os.path.isdir(rm):
        return {"op": "rebasing", "branch": short(_read(rm, "head-name")), "onto": _read(rm, "onto")[:7],
                "step": _read(rm, "msgnum"), "total": _read(rm, "end")}
    ra = os.path.join(gitdir, "rebase-apply")
    if os.path.isdir(ra):
        op = "applying" if os.path.exists(os.path.join(ra, "applying")) else "rebasing"
        return {"op": op, "branch": short(_read(ra, "head-name")), "onto": _read(ra, "onto")[:7],
                "step": _read(ra, "next"), "total": _read(ra, "last")}
    for name, op in (("MERGE_HEAD", "merging"), ("CHERRY_PICK_HEAD", "cherry-picking"),
                     ("REVERT_HEAD", "reverting")):
        sha = _read(gitdir, name)
        if sha:
            msg = _read(gitdir, "MERGE_MSG").splitlines()
            return {"op": op, "branch": "", "onto": sha[:7], "step": "", "total": "",
                    "message": msg[0] if msg else ""}
    if os.path.exists(os.path.join(gitdir, "BISECT_LOG")):
        return {"op": "bisecting", "branch": "", "onto": "", "step": "", "total": ""}
    return None
