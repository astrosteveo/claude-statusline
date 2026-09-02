"""Everything a segment may look at while rendering one refresh."""
from __future__ import annotations

import os
import time

from .config import usable_width
from .gitinfo import git_info
from .payload import find_windows
from .util import dig


class Context:
    def __init__(self, data, cols=None, now=None):
        self.data = data if isinstance(data, dict) else {}
        self.cwd = (dig(self.data, "workspace", "current_dir")
                    or self.data.get("cwd") or os.getcwd())
        if not isinstance(self.cwd, str):
            self.cwd = os.getcwd()
        self.worktree = dig(self.data, "workspace", "git_worktree")
        self.now = time.time() if now is None else float(now)
        self.avail = usable_width(cols)
        self._memo = {}

    def memo(self, key, compute):
        if key not in self._memo:
            self._memo[key] = compute()
        return self._memo[key]

    def git(self, last_commit=True):
        return self.memo(("git", bool(last_commit)),
                         lambda: git_info(self.cwd, last_commit))

    def windows(self):
        return self.memo("windows", lambda: find_windows(self.data))
