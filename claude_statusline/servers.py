"""The dev servers this project runs, for the servers panel. Linux only.

A detached process reads `ss -ltnp` and keeps the listening sockets whose
process works inside this repository (/proc/<pid>/cwd), so a server Claude
started in the background shows, and one from another project does not.
Claude Code's own socket is left out. Ports Docker publishes belong to
Docker's proxy, not to a process here, so they do not show.
"""
from __future__ import annotations

import os
import time

from .gitstatus import _load, _paths, _save, spawn_refresh, unlock

TTL = 5.0
SKIP = {"claude"}


def data(root, sync=False, spawn=True):
    """[(port, name, started)], newest first (empty before the first answer), or None off Linux."""
    if not os.path.isdir("/proc"):
        return None
    cache, lock = _paths(root, "servers")
    blob = _load(cache)
    out = blob.get("data") if isinstance(blob, dict) else None
    if out is None or time.time() - float(blob.get("ts") or 0) > TTL:
        if sync:
            out = refresh(root)
        elif spawn:
            spawn_refresh("servers", lock, [root, lock])
    return out or []


def _refresh_main(args):
    root, lock = args
    try:
        refresh(root)
    finally:
        unlock(lock)


def parse_ss(text):
    """`ss -ltnpH` -> [(port, process name, pid)], one per (port, pid)."""
    out, seen = [], set()
    for line in text.split("\n"):
        cols = line.split()
        if len(cols) < 6 or "users:((" not in line:
            continue
        port = cols[3].rsplit(":", 1)[-1]
        if not port.isdigit():
            continue
        users = line[line.index("users:((") + 8:]
        for proc in users.split("),("):
            parts = proc.split(",")
            name = parts[0].strip('"()')
            pid = next((p[4:] for p in parts if p.startswith("pid=")), "")
            if pid.isdigit() and (int(port), int(pid)) not in seen:
                seen.add((int(port), int(pid)))
                out.append((int(port), name, int(pid)))
    return out


def _started(pid, boot, tick):
    try:
        with open(f"/proc/{pid}/stat") as fh:
            stat = fh.read()
        return boot + int(stat[stat.rindex(")") + 2:].split()[19]) / tick
    except (OSError, ValueError, IndexError):
        return 0


def _label(pid, name):
    """What the process is, briefly: `vite`, `next dev`, `uvicorn app:api`, else its name."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            argv = [a.decode("utf-8", "replace") for a in fh.read().split(b"\0") if a]
    except OSError:
        return name
    words = [os.path.basename(a) for a in argv if not a.startswith("-")]
    while words and words[0] in ("node", "python", "python3", "bun", "deno", "npx", "uv", "uvx", "env", "sh"):
        words = words[1:]
    if words and words[0] in ("npm", "pnpm", "yarn") and len(words) > 1:
        words = words[1:]
    if not words:
        return name
    second = words[1] if len(words) > 1 and words[1][:1].isalpha() and "/" not in words[1] else ""
    return f"{words[0]} {second}".strip()


def refresh(root):
    import subprocess
    try:
        p = subprocess.run(["ss", "-ltnpH"], timeout=3, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        text = p.stdout.decode("utf-8", "replace") if p.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        text = ""
    boot = 0.0
    try:
        with open("/proc/stat") as fh:
            boot = float(next(line.split()[1] for line in fh if line.startswith("btime")))
    except (OSError, StopIteration, ValueError):
        pass
    tick = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
    real = os.path.realpath(root)
    out, ports = [], set()
    for port, name, pid in parse_ss(text):
        if name in SKIP or port in ports:
            continue
        try:
            cwd = os.path.realpath(os.readlink(f"/proc/{pid}/cwd"))
        except OSError:
            continue
        if cwd != real and not cwd.startswith(real + os.sep):
            continue
        ports.add(port)
        out.append((port, _label(pid, name), _started(pid, boot, tick)))
    out.sort(key=lambda s: -s[2])
    _save(_paths(root, "servers")[0], {"ts": time.time(), "data": out})
    return out
