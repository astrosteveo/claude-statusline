"""Code review on GitHub, for the reviews panel, without ever making the bar wait.

One GraphQL query through `gh api` asks for two things: the open pull
requests waiting on your review, anywhere on GitHub, and this branch's own
pull request with its review decision and the comment threads still open.
A detached process asks and writes a cache in the runtime directory, the
same stale-while-revalidate as ci.py, at most every two minutes (at once
after a commit or a push). Offline, the last answer stays and is marked
stale. Only github.com remotes are asked, and only when `gh` is installed.
"""
from __future__ import annotations

import re
import time

from .ci import _epoch, _git
from .gitstatus import _load, _paths, _save, read_head, spawn_refresh, unlock

TTL = 120.0
GH_TIMEOUT = 10.0
ASKED = 20
THREADS = 50
BODY = 160
QUERY = """query($owner: String!, $name: String!, $branch: String!) {
  search(query: "is:pr is:open review-requested:@me archived:false", type: ISSUE, first: %d) {
    nodes { ... on PullRequest { number title url updatedAt isDraft author { login }
                                 repository { nameWithOwner } } }
  }
  repository(owner: $owner, name: $name) {
    pullRequests(headRefName: $branch, states: OPEN, first: 1) {
      nodes { number title url reviewDecision
              reviewThreads(first: %d) { nodes { isResolved isOutdated path line
                comments(first: 1) { nodes { author { login } body url } } } } }
    }
  }
}""" % (ASKED, THREADS)
_REMOTE = re.compile(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


def owner_name(url):
    """("o", "r") from a github.com remote URL, or None."""
    m = _REMOTE.search((url or "").strip())
    return (m.group(1), m.group(2)) if m else None


def key_of(gitdir, branch):
    import os
    try:
        return f"{branch}|{os.stat(os.path.join(gitdir, 'logs', 'HEAD')).st_mtime_ns}"
    except OSError:
        return f"{branch}|-"


def data(root, gitdir, sync=False, spawn=True):
    """{"mine": [...] or None, "asked": [...], "stale"}, {"pending": True} before the first answer,
    or None where there is nothing to ask."""
    branch, _ = read_head(gitdir)
    if not branch:
        return None
    cache, lock = _paths(root, "reviews")
    blob = _load(cache)
    out = blob.get("data") if isinstance(blob, dict) else None
    key = key_of(gitdir, branch)
    fresh = out is not None and blob.get("key") == key and time.time() - float(blob.get("ts") or 0) <= TTL
    if not fresh:
        if sync:
            out = refresh(root, gitdir, branch)
        elif spawn:
            spawn_refresh("reviews", lock, [root, gitdir, branch, lock])
    if out is None:
        return {"pending": True}
    if out.get("skip"):
        return None
    return out


def _refresh_main(args):
    root, gitdir, branch, lock = args
    try:
        refresh(root, gitdir, branch)
    finally:
        unlock(lock)


def ask_gh(root, owner, name, branch):
    import json
    import subprocess
    try:
        p = subprocess.run(["gh", "api", "graphql", "-f", f"query={QUERY}", "-f", f"owner={owner}",
                            "-f", f"name={name}", "-f", f"branch={branch}"],
                           cwd=root, timeout=GH_TIMEOUT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    try:
        raw = json.loads(p.stdout or b"{}")
    except ValueError:
        return None
    return raw.get("data") if isinstance(raw, dict) and isinstance(raw.get("data"), dict) else None


def _login(node):
    a = node.get("author") if isinstance(node, dict) else None
    return str(a.get("login") or "") if isinstance(a, dict) else ""


def _nodes(obj, *path):
    for p in path:
        obj = obj.get(p) if isinstance(obj, dict) else None
    return [n for n in obj if isinstance(n, dict)] if isinstance(obj, list) else []


def parse(raw):
    """{"mine": [number, title, url, decision, threads] or None, "asked": [[repo, number, title, url,
    author, updated, draft]]}; each thread [path, line, author, body, url]."""
    asked = [[str((n.get("repository") if isinstance(n.get("repository"), dict) else {}).get("nameWithOwner") or ""),
              int(n.get("number") or 0), str(n.get("title") or ""), str(n.get("url") or ""), _login(n),
              _epoch(n.get("updatedAt")), bool(n.get("isDraft"))]
             for n in _nodes(raw, "search", "nodes") if n.get("number")]
    asked.sort(key=lambda r: -r[5])
    mine = None
    prs = _nodes(raw, "repository", "pullRequests", "nodes")
    if prs:
        pr = prs[0]
        threads = []
        for t in _nodes(pr, "reviewThreads", "nodes"):
            if t.get("isResolved"):
                continue
            c = (_nodes(t, "comments", "nodes") or [{}])[0]
            body = " ".join(str(c.get("body") or "").split())[:BODY]
            threads.append([str(t.get("path") or ""), int(t.get("line") or 0), _login(c), body,
                            str(c.get("url") or ""), bool(t.get("isOutdated"))])
        mine = [int(pr.get("number") or 0), str(pr.get("title") or ""), str(pr.get("url") or ""),
                str(pr.get("reviewDecision") or ""), threads]
    return {"mine": mine, "asked": asked}


def refresh(root, gitdir, branch):
    import shutil
    cache, _ = _paths(root, "reviews")
    old = _load(cache)
    old = old.get("data") if isinstance(old, dict) else None
    where = owner_name(_git(["remote", "get-url", "origin"], root))
    if not shutil.which("gh") or not where:
        info = {"skip": True}
    else:
        raw = ask_gh(root, *where, branch)
        if raw is None:
            info = dict(old if old and not old.get("skip") else {"mine": None, "asked": []}, stale=True)
        else:
            info = dict(parse(raw), stale=False)
    _save(cache, {"key": key_of(gitdir, branch), "ts": time.time(), "data": info})
    return info
