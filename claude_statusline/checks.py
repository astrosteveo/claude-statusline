"""What a test, lint or build run said, cut down to what the checks panel shows.

The activity hook calls `summary` on every shell command Claude runs. A
command that is not a test, lint or build run (quest/boss.py decides) is
ignored. For the rest it keeps the counts and up to `NAMES` failures, each
with the file and line where the runner names one, and never the output
itself.

Names are read for pytest, unittest, jest, vitest, cargo and go test, and
for linters and compilers that print `path:line:` (ruff, mypy, eslint's
unix format, tsc, gcc). Other runners still get their counts.
"""
from __future__ import annotations

import re

NAMES = 10
CMD = 120

_PYTEST = re.compile(r"^(?:FAILED|ERROR) (\S+?\.py)::(\S+)", re.M)
_UNITTEST = re.compile(r"^(?:FAIL|ERROR): (\w+) \(([\w.]+)\)", re.M)
_PYFRAME = re.compile(r'File "([^"]+)", line (\d+), in (\w+)')
_JEST = re.compile(r"^\s*● (.+? › .+)$", re.M)
_VITEST = re.compile(r"^\s*(?:FAIL|×)\s+(\S+\.\w+) > (.+?)(?:\s+\d+ms)?$", re.M)
_CARGO = re.compile(r"^---- (\S+) stdout ----$", re.M)
_GO = re.compile(r"^\s*--- FAIL: (\S+)", re.M)
_GOFILE = re.compile(r"^\s+(\S+_test\.go):(\d+):", re.M)
_PATHLINE = re.compile(r"^([\w./@+-]+\.\w+)(?::(\d+)(?::\d+)?:|\((\d+),\d+\):)\s*(.*)$", re.M)

_PASSED = re.compile(r"(\d+) passed")                           # pytest, jest, vitest, cargo
_RAN = re.compile(r"^Ran (\d+) tests?", re.M)                    # unittest


def passed_count(kind, text):
    """Tests that passed, or None where the runner does not say."""
    if kind != "test":
        return None
    ran = _RAN.search(text)
    if ran:
        from .quest.boss import count_failures
        return max(0, int(ran.group(1)) - (count_failures(text) or 0))
    found = [int(m.group(1)) for m in _PASSED.finditer(text)]
    if found:
        return max(found)
    return None


def _module_path(dotted, test):
    """tests.test_x.Cls.test_y -> tests/test_x.py (a guess the frames may correct)."""
    parts = dotted.split(".")
    if parts and parts[-1] == test:
        parts = parts[:-1]
    while len(parts) > 1 and parts[-1][:1].isupper():
        parts = parts[:-1]
    return "/".join(parts) + ".py" if parts else ""


def failures(kind, text):
    """[[label, path, line]] for the failures `text` names, at most NAMES of them."""
    out = []

    def add(label, path="", line=0):
        if len(out) < NAMES and [label, path, line] not in out:
            out.append([label, path, int(line or 0)])

    if kind == "test":
        frames = {}
        for m in _PYFRAME.finditer(text):
            frames[m.group(3)] = (m.group(1), int(m.group(2)))
        for m in _PYTEST.finditer(text):
            name = m.group(2).split(" ")[0]
            path, line = m.group(1), 0
            for f in _PATHLINE.finditer(text):
                if f.group(1) == path and f.group(2):
                    line = int(f.group(2))
                    break
            add(name, path, line)
        for m in _UNITTEST.finditer(text):
            test, dotted = m.group(1), m.group(2)
            path, line = frames.get(test, (_module_path(dotted, test), 0))
            cls = [p for p in dotted.split(".") if p[:1].isupper()]
            add(f"{cls[-1]}.{test}" if cls else test, path, line)
        for m in _VITEST.finditer(text):
            add(m.group(2).replace(" > ", " › ").strip(), m.group(1))
        for m in _JEST.finditer(text):
            add(m.group(1).strip())
        for m in _CARGO.finditer(text):
            add(m.group(1))
        gofiles = [(m.group(1), int(m.group(2))) for m in _GOFILE.finditer(text)]
        for i, m in enumerate(_GO.finditer(text)):
            path, line = gofiles[i] if i < len(gofiles) else ("", 0)
            add(m.group(1), path, line)
    else:
        for m in _PATHLINE.finditer(text):
            msg = re.sub(r"\s+", " ", m.group(4)).strip()
            if msg:
                add(msg, m.group(1), m.group(2) or m.group(3))
    return out


def summary(command, out, failed):
    """[kind, command, ok, failures, passed, names] for a test, lint or build run, or None."""
    from .quest.boss import classify, count_failures
    kind = classify(command or "")
    if not kind:
        return None
    text = out or ""
    n = count_failures(text)
    names = failures(kind, text)
    if n is None:
        n = len(names) if names else (1 if failed else 0)
    ok = not failed and n == 0
    if ok:
        names = []
    elif n == 0:
        n = max(1, len(names))
    cmd = " ".join(str(command).split())
    return [kind, cmd[:CMD], ok, n, passed_count(kind, text), names]


def output_of(event):
    """A finished shell call's output: stdout and stderr, or the error a failure carries."""
    resp = event.get("tool_response")
    if event.get("hook_event_name") == "PostToolUseFailure":
        err = event.get("error")
        if isinstance(err, dict):
            err = err.get("message") or ""
        return str(err or "") + ("\n" + _resp_text(resp) if resp else "")
    return _resp_text(resp)


def failed(event):
    """Whether a finished shell call failed: the failure event, or a non-zero exit code."""
    if event.get("hook_event_name") == "PostToolUseFailure":
        return True
    resp = event.get("tool_response")
    code = resp.get("exit_code") if isinstance(resp, dict) else None
    return isinstance(code, int) and code != 0


def _resp_text(resp):
    if isinstance(resp, dict):
        return f"{resp.get('stdout') or ''}\n{resp.get('stderr') or ''}"
    return str(resp or "")
