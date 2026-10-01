"""Writing TOML: whole configs for the configurator, and single-key edits
that leave the rest of a hand-written file (comments included) alone."""
from __future__ import annotations

import json
import re

_BARE = re.compile(r"^[A-Za-z0-9_-]+$")


def key(k: str) -> str:
    return k if _BARE.match(k) else json.dumps(k, ensure_ascii=False)


def value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v) if v == v and v not in (float("inf"), float("-inf")) else "0.0"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{key(k)} = {value(x)}" for k, x in v.items()) + " }"
    return json.dumps("" if v is None else str(v), ensure_ascii=False)


ORDER = ("preset", "theme", "style", "icons", "color")
SECTION_ORDER = ("layout", "bar", "thresholds", "commands", "activity", "quest", "git", "glyphs", "colors")


def dumps(cfg: dict, header: str = "", comments: dict | None = None) -> str:
    """A config dict as TOML: scalars, [[line]]s, [segment.x]s, then sections."""
    comments = comments or {}
    out = [header.rstrip("\n")] if header else []
    scalars = [k for k in ORDER if k in cfg] + [k for k, v in cfg.items()
                                                 if k not in ORDER and not isinstance(v, (dict, list))]
    for k in scalars:
        line = f"{key(k)} = {value(cfg[k])}"
        if comments.get(k):
            line = f"{line:<28} # {comments[k]}"
        out.append(line)
    for entry in cfg.get("line") or []:
        out.append("")
        out.append("[[line]]")
        for k in ("left", "right", "gap"):
            if k in entry:
                out.append(f"{k} = {value(entry[k])}")
    for name, table in (cfg.get("segment") or {}).items():
        if not isinstance(table, dict) or not table:
            continue
        out.append("")
        out.append(f"[segment.{key(name)}]")
        for k, v in table.items():
            out.append(f"{key(k)} = {value(v)}")
    sections = [s for s in SECTION_ORDER if s in cfg] + [s for s, v in cfg.items() if isinstance(v, dict)
                                                          and s not in SECTION_ORDER and s != "segment"]
    for section in sections:
        body = cfg.get(section)
        if not isinstance(body, dict) or not body:
            continue
        out.append("")
        out.append(f"[{key(section)}]")
        for k, v in body.items():
            out.append(f"{key(k)} = {value(v)}")
    return "\n".join(out).strip("\n") + "\n"


_HEADER = re.compile(r"^\s*\[\s*([^\[\]]+?)\s*\]\s*(#.*)?$")
_ARRAY_HEADER = re.compile(r"^\s*\[\[")


def _parts(dotted: str):
    return [p.strip().strip('"') for p in dotted.split(".")]


def set_key(text: str, dotted: str, val) -> str:
    """`text` with `dotted` (e.g. "theme", "quest.enabled", "segment.dir.depth")
    set to `val`, touching nothing else. `val` None removes the key."""
    parts = _parts(dotted)
    table, name = parts[:-1], parts[-1]
    lines = text.split("\n") if text else []
    header_name = ".".join(table)
    start = end = None
    if not table:
        start = 0
        end = next((i for i, ln in enumerate(lines) if _HEADER.match(ln) or _ARRAY_HEADER.match(ln)), len(lines))
    else:
        for i, ln in enumerate(lines):
            m = _HEADER.match(ln)
            if m and not _ARRAY_HEADER.match(ln) and ".".join(_parts(m.group(1))) == header_name:
                start = i + 1
                end = next((j for j in range(i + 1, len(lines))
                            if _HEADER.match(lines[j]) or _ARRAY_HEADER.match(lines[j])), len(lines))
                break
    assign = re.compile(r"^(\s*)(" + re.escape(name) + r"|\"" + re.escape(name) + r"\")\s*=\s*(.*)$")
    if start is not None:
        for i in range(start, end):
            m = assign.match(lines[i])
            if m:
                if val is None:
                    del lines[i]
                    return "\n".join(lines)
                rest = m.group(3)
                comment = ""
                cpos = _comment_pos(rest)
                if cpos is not None:
                    comment = "  " + rest[cpos:].strip()
                lines[i] = f"{m.group(1)}{key(name)} = {value(val)}{comment}"
                return "\n".join(lines)
        if val is None:
            return text
        insert = end
        while insert > start and not lines[insert - 1].strip():
            insert -= 1
        lines.insert(insert, f"{key(name)} = {value(val)}")
        return "\n".join(lines)
    if val is None:
        return text
    body = "\n".join(lines).rstrip("\n")
    return (body + "\n\n" if body else "") + f"[{header_name}]\n{key(name)} = {value(val)}\n"


def edit(path: str, dotted: str, val):
    """(old text, new text, new parsed) for setting one key in the file at
    `path` (None removes it). Raises ValueError if the result would not parse."""
    import tomllib
    try:
        with open(path) as fh:
            text = fh.read()
    except FileNotFoundError:
        text = ""
    new = set_key(text, dotted, val)
    try:
        return text, new, tomllib.loads(new)
    except Exception as exc:
        raise ValueError(f"the edit would leave {path} unreadable ({exc})") from None


def write(path: str, text: str):
    """Replace the file at `path` with `text` in one step."""
    import os
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as fh:
        fh.write(text if text.endswith("\n") else text + "\n")
    os.replace(tmp, path)


def _comment_pos(rest: str):
    """Where a trailing # comment starts in a value, ignoring #s inside strings."""
    quote = None
    i = 0
    while i < len(rest):
        ch = rest[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            return i
        i += 1
    return None
