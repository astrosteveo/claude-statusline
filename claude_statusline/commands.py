"""Your own commands on the bar, kept off the refresh path.

A `type = "command"` segment shows the first line of a command's output. The
bar never runs the command itself: it reads the last output from a cache in
the runtime directory, and when that is older than the segment's `every`, it
starts one detached runner (a lock keeps it to one) and draws the old output
meanwhile, the way git's state is kept. The runner gives the command
`timeout` seconds, then kills its whole process group. It keeps the first
line, turns SGR colours into styled runs and drops every other control
sequence, so a refresh reads one marshal file and parses nothing.

`[commands] enabled = false`, or CLAUDE_STATUSLINE_NO_COMMANDS=1 in the
environment, hides every command segment and starts nothing. Commands come
only from your own config file.
"""
from __future__ import annotations

import os
import sys
import time

MIN_EVERY = 2.0
MAX_TIMEOUT = 10.0
MAX_BYTES = 4096
MAX_CHARS = 200


def enabled(comp) -> bool:
    return bool((comp.get("commands") or {}).get("enabled", True)) and \
        not os.environ.get("CLAUDE_STATUSLINE_NO_COMMANDS")


def key_of(command, cwd, per):
    import zlib
    text = command + ("\0" + cwd if per == "project" else "")
    return "%08x" % zlib.crc32(text.encode("utf-8", "replace"))


def paths(key):
    from .config import runtime_dir
    base = os.path.join(runtime_dir(), f"cmd-{key}")
    return base + ".bin", base + ".lock"


def read(key):
    import marshal
    try:
        with open(paths(key)[0], "rb") as fh:
            blob = marshal.loads(fh.read())
    except (OSError, ValueError, EOFError, TypeError):
        return None
    return blob if isinstance(blob, dict) else None


def request(key, command, cwd, timeout, env):
    """Start a detached runner unless one is already running for this command."""
    _, lock = paths(key)
    now = time.time()
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        try:
            if now - os.stat(lock).st_mtime < timeout + 5:
                return False
            os.unlink(lock)
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except OSError:
            return False
    except OSError:
        return False
    os.close(fd)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = ("import sys; sys.path.insert(0, sys.argv[1]); "
            "from claude_statusline.commands import runner_main; runner_main(sys.argv[2:])")
    from .gitstatus import spawn_detached
    argv = [sys.executable or "python3", "-S", "-c", code, root, key, command, cwd, str(timeout)]
    for k, v in env.items():
        argv.append(f"{k}={v}")
    return spawn_detached(argv)


def runner_main(args):
    key, command, cwd, timeout = args[:4]
    env = dict(a.split("=", 1) for a in args[4:] if "=" in a)
    try:
        run(key, command, cwd, float(timeout), env)
    finally:
        try:
            os.unlink(paths(key)[1])
        except OSError:
            pass


def run(key, command, cwd, timeout, env=None):
    """Run the command now (bounded by `timeout`), store its output, and return the entry."""
    import marshal
    import signal
    import subprocess
    timeout = max(0.1, min(MAX_TIMEOUT, timeout))
    started = time.time()
    entry = {"at": started, "took": 0.0, "exit": None, "spans": [], "plain": "", "error": ""}
    try:
        p = subprocess.Popen(["/bin/sh", "-c", command], cwd=cwd if os.path.isdir(cwd or "") else None,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             start_new_session=True, env=dict(os.environ, **(env or {})))
        try:
            out, err = p.communicate(timeout=timeout)
            entry["exit"] = p.returncode
            entry["error"] = err.decode("utf-8", "replace").strip().split("\n")[-1][:200] if p.returncode else ""
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
            out, _ = p.communicate()
            entry["exit"] = "timeout"
            entry["error"] = f"took longer than {timeout:g}s"
        text = out[:MAX_BYTES].decode("utf-8", "replace")
        line = next((ln for ln in text.split("\n") if ln.strip() and strip(ln).strip()), "")
        entry["spans"] = spans_of(line)
        entry["plain"] = "".join(t for t, *_ in entry["spans"])
    except OSError as exc:
        entry["exit"] = "error"
        entry["error"] = str(exc)[:200]
    entry["took"] = time.time() - started
    dest, _ = paths(key)
    try:
        tmp = f"{dest}.{os.getpid()}"
        with open(tmp, "wb") as fh:
            fh.write(marshal.dumps(entry))
        os.replace(tmp, dest)
    except OSError:
        pass
    return entry


def strip(text):
    return "".join(t for t, *_ in spans_of(text))


def spans_of(line):
    """[(text, fg, bg, attrs)] from one line of terminal output: SGR colours and bold, faint,
    italic and underline kept; every other escape and control character dropped; tabs as a space."""
    from .color import index_rgb
    out = []
    fg = bg = None
    attrs = 0
    buf = []
    count = 0
    i, n = 0, len(line)

    def flush():
        if buf:
            out.append(("".join(buf), fg, bg, attrs))
            buf.clear()
    while i < n and count < MAX_CHARS:
        ch = line[i]
        if ch == "\x1b":
            if line.startswith("\x1b[", i):
                j = i + 2
                while j < n and not ("@" <= line[j] <= "~"):
                    j += 1
                if j < n and line[j] == "m":
                    flush()
                    fg, bg, attrs = _sgr(line[i + 2:j], fg, bg, attrs, index_rgb)
                i = j + 1
            elif line.startswith("\x1b]", i):
                end = line.find("\x1b\\", i)
                bel = line.find("\x07", i)
                stop = min(x for x in (end + 2 if end != -1 else n, bel + 1 if bel != -1 else n))
                i = stop
            else:
                i += 2
            continue
        if ch == "\t":
            ch = " "
        if ch < " " or ch == "\x7f" or 0x80 <= ord(ch) < 0xA0:
            i += 1
            continue
        buf.append(ch)
        count += 1
        i += 1
    flush()
    return out


def _sgr(params, fg, bg, attrs, index_rgb):
    codes = [int(p) if p.isdigit() else 0 for p in params.split(";")] if params else [0]
    k = 0
    while k < len(codes):
        c = codes[k]
        if c == 0:
            fg = bg = None
            attrs = 0
        elif c in (1, 2, 3, 4):
            attrs |= {1: 1, 2: 2, 3: 4, 4: 8}[c]
        elif c == 22:
            attrs &= ~3
        elif c == 23:
            attrs &= ~4
        elif c == 24:
            attrs &= ~8
        elif 30 <= c <= 37 or 90 <= c <= 97:
            idx = c - 30 if c < 90 else c - 82
            fg = (*index_rgb(idx), idx)
        elif 40 <= c <= 47 or 100 <= c <= 107:
            idx = c - 40 if c < 100 else c - 92
            bg = (*index_rgb(idx), idx)
        elif c == 39:
            fg = None
        elif c == 49:
            bg = None
        elif c in (38, 48) and k + 1 < len(codes):
            color = None
            if codes[k + 1] == 5 and k + 2 < len(codes):
                n = max(0, min(255, codes[k + 2]))
                color = (*index_rgb(n), n)
                k += 2
            elif codes[k + 1] == 2 and k + 4 < len(codes):
                color = tuple(max(0, min(255, x)) for x in codes[k + 2:k + 5]) + (-1,)
                k += 4
            if c == 38:
                fg = color
            else:
                bg = color
        k += 1
    return fg, bg, attrs
