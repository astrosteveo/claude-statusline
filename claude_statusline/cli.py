"""Command-line entry points.

With no arguments the engine reads a payload on stdin and prints the bar,
which is what Claude Code runs once a second. Everything else is a
subcommand for people (and for the design skill) to inspect, check and
preview layouts without a live session.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

from . import __version__
from .config import (CFG, CONFIG_SEARCH, DEBUG_ENV, DEFAULTS, DUMP_ENV, apply_config,
                     config_path, load_config, usable_width)
from .fit import LEVELS
from .gitinfo import _cache_dir
from .layout import LEGACY_FEATURES, build_layout, list_presets, load_preset
from .render import current_layout, fallback, render, render_lines
from .segments import REGISTRY
from .util import deep_merge
from .width import display_width

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")

HELP = f"""claude-statusline {__version__} — a status line engine for Claude Code

usage: statusline.py                      render the payload on stdin (what Claude Code runs)
       statusline.py <command> [options]

commands
  segments [name] [--json|--markdown]
                                  the catalog: every segment, its options, fields and colours
  presets [--json]                the bundled layouts
  validate [path] [--json]        check a config file; exit 1 on errors
  preview [--config P] [--preset N] [--width W,W] [--sample S] [--plain] [--json]
                                  render a layout at several widths with a sample payload
  render [--width W] [--sample S] render one payload (stdin, or a sample) at one width
  migrate [path] [--write]        rewrite a pre-2.0 config ([features]) into segment options
  doctor                          resolved config, layout, width, cache state
  ruler                           calibration rulers for layout.right_margin
  dump-config                     the effective configuration as TOML
  version

samples: {', '.join(sorted(f[:-5] for f in os.listdir(SAMPLE_DIR) if f.endswith('.json')))}
Old flag spellings (--doctor, --ruler, --demo, --dump-config) still work.
"""

_SGR = re.compile(r"\033\[[0-9;]*[@-~]")
_OSC = re.compile(r"\033\]8;;.*?(?:\033\\|\a)")
_REL = re.compile(r"^([+-])((?:\d+[smhd])+)$")
_UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def plain(text: str) -> str:
    return _SGR.sub("", _OSC.sub("", text))


# --- samples -----------------------------------------------------------------
def sample_names():
    return sorted(f[:-5] for f in os.listdir(SAMPLE_DIR) if f.endswith(".json"))


def _relative(value, now):
    m = _REL.match(value)
    if not m:
        return value
    secs = sum(int(n) * _UNIT[u] for n, u in re.findall(r"(\d+)([smhd])", m.group(2)))
    return now + secs if m.group(1) == "+" else now - secs


def _resolve_times(obj, now):
    if isinstance(obj, dict):
        return {k: (_relative(v, now) if k in ("resets_at", "resetsAt") and isinstance(v, str)
                    else _resolve_times(v, now)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_times(v, now) for v in obj]
    return obj


def load_sample(name: str, now=None) -> dict:
    """A bundled sample by name, or any JSON file by path. Reset times written
    as "+1h43m" are resolved relative to `now`, so bars always look live."""
    path = name if os.path.exists(name) else os.path.join(SAMPLE_DIR, f"{name}.json")
    with open(path) as fh:
        data = json.load(fh)
    return _resolve_times(data, time.time() if now is None else now)


# --- commands ----------------------------------------------------------------
def cmd_ruler(cols=None) -> str:
    """Two rulers for calibrating layout.right_margin.

    Row 1 counts columns from the left; row 2 counts *down* to the right edge,
    so the last digit you can actually see is the number of columns the host
    clipped. Add that to right_margin.
    """
    if cols is None:
        try:
            cols = int(os.environ.get("COLUMNS") or 0)
        except ValueError:
            cols = 0
        cols = cols or CFG["layout"]["fallback_columns"]
    forward = "".join(
        str((i // 10) % 10) if i % 10 == 0 else ("+" if i % 5 == 0 else "·")
        for i in range(cols)
    )
    backward = "".join(str((cols - 1 - i) % 10) for i in range(cols))
    return forward + "\n" + backward


def cmd_doctor(cols=None) -> str:
    path = config_path()
    try:
        env_cols = int(os.environ.get("COLUMNS") or 0)
    except ValueError:
        env_cols = 0
    layout = current_layout()
    lines = [
        f"claude-statusline {__version__}",
        f"  python          {sys.version.split()[0]}",
        f"  config          {path or '(defaults; none found)'}",
        f"  searched        {', '.join(CONFIG_SEARCH)}",
        f"  preset          {layout.preset}"
        + ("" if not CFG.get("line") else "  (lines declared in config)"),
        f"  lines           {len(layout.lines)}: "
        + " / ".join(", ".join(s.name for s in ln.left + ln.right) for ln in layout.lines),
        f"  COLUMNS         {env_cols or '(unset)'}"
        f"  →  fallback {CFG['layout']['fallback_columns']}",
        f"  right_margin    {CFG['layout']['right_margin']}",
        f"  usable width    {usable_width(cols)}",
        f"  bar             width={CFG['bar']['width']} "
        f"partial={CFG['bar']['partial']}",
        f"  git             enabled={CFG['git']['enabled']} "
        f"ttl={CFG['git']['cache_ttl']}s",
        f"  cache dir       {_cache_dir()}",
        f"  payload dump    {os.environ.get(DUMP_ENV) or '(off; set ' + DUMP_ENV + ')'}",
    ]
    try:
        entries = [f for f in os.listdir(_cache_dir()) if f.startswith("git-")]
        lines.append(f"  cached repos    {len(entries)}")
    except Exception:
        pass
    if layout.problems:
        lines.append(f"  layout          {len(layout.errors)} error(s), "
                     f"{len(layout.warnings)} warning(s) — run `validate`")
        for p in layout.problems[:6]:
            lines.append(f"    {p}")
        if len(layout.problems) > 6:
            lines.append(f"    … {len(layout.problems) - 6} more")
    else:
        lines.append("  layout          clean")
    return "\n".join(lines)


def _toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    return json.dumps(str(v), ensure_ascii=False)


def to_toml(cfg: dict, header: str | None = None) -> str:
    """Serialise a config-shaped dict: scalars, [[line]], [segment.x], [sections]."""
    out = [header] if header else []
    for key, val in cfg.items():
        if not isinstance(val, (dict, list)):
            out.append(f"{key} = {_toml_value(val)}")
    for section, body in cfg.items():
        if section == "line" and isinstance(body, list):
            for entry in body:
                out.append("\n[[line]]")
                for key, val in entry.items():
                    out.append(f"{key} = {_toml_value(val)}")
        elif section == "segment" and isinstance(body, dict):
            for name, table in body.items():
                out.append(f"\n[segment.{name}]")
                for key, val in table.items():
                    out.append(f"{key} = {_toml_value(val)}")
        elif isinstance(body, dict):
            out.append(f"\n[{section}]")
            for key, val in body.items():
                out.append(f"{key} = {_toml_value(val)}")
    return "\n".join(out).lstrip("\n") + "\n"


def cmd_dump_config() -> str:
    return to_toml(CFG, f"# claude-statusline {__version__} — effective configuration")


def _segment_info(seg) -> dict:
    return {
        "name": seg.name,
        "doc": seg.doc,
        "priority": seg.priority,
        "format": seg.format,
        "options": {k: {"type": o.type.__name__, "default": o.default, "doc": o.doc}
                    for k, o in seg.all_options().items() if k not in ("format", "priority")},
        "fields": dict(seg.fields),
        "colors": dict(seg.colors),
    }


def catalog_markdown() -> str:
    """The catalog as a reference page for the design skill."""
    out = ["# Segment catalog", "",
           "Generated by `statusline.py segments --markdown`; regenerate with `make catalog`.",
           "Every segment also accepts `format` (template) and `priority` (int).", ""]
    out.append("| segment | priority | what it shows |")
    out.append("|---------|----------|---------------|")
    segs = sorted(REGISTRY.values(), key=lambda s: -s.priority)
    for s in segs:
        out.append(f"| `{s.name}` | {s.priority} | {s.doc} |")
    for s in segs:
        info = _segment_info(s)
        out += ["", f"## {s.name}", "", s.doc, "", f"Default format: `{s.format}`"]
        if info["options"]:
            out += ["", "| option | type | default | meaning |", "|--------|------|---------|---------|"]
            for k, o in info["options"].items():
                out.append(f"| `{k}` | {o['type']} | `{_toml_value(o['default'])}` | {o['doc']} |")
        out += ["", "| field | holds |", "|-------|-------|"]
        for k, doc in s.fields.items():
            out.append(f"| `{{{k}}}` | {doc} |")
        if s.colors:
            out += ["", "| colour | when |", "|--------|------|"]
            for k, doc in s.colors.items():
                out.append(f"| `<{k}>` | {doc} |")
    return "\n".join(out) + "\n"


def cmd_segments(name=None, as_json=False, as_markdown=False) -> str:
    if as_markdown:
        return catalog_markdown()
    if name:
        seg = REGISTRY.get(name)
        if seg is None:
            return f"unknown segment {name!r}; try one of: {', '.join(sorted(REGISTRY))}"
        info = _segment_info(seg)
        if as_json:
            return json.dumps(info, indent=2, ensure_ascii=False)
        out = [f"{seg.name}  (priority {seg.priority})", f"  {seg.doc}", "",
               "  format", f"    {seg.format}"]
        if info["options"]:
            out += ["", "  options"]
            for k, o in info["options"].items():
                out.append(f"    {k:<18}{o['type']:<6}default {_toml_value(o['default'])}")
                out.append(f"    {'':<18}{o['doc']}")
        out += ["", "  fields"]
        for k, doc in seg.fields.items():
            out.append(f"    {{{k}}}".ljust(22) + doc)
        if "url" not in seg.fields and any("url" in f for f in seg.fields):
            pass
        if seg.colors:
            out += ["", "  colours"]
            for k, doc in seg.colors.items():
                out.append(f"    <{k}>".ljust(22) + doc)
        return "\n".join(out)
    segs = sorted(REGISTRY.values(), key=lambda s: -s.priority)
    if as_json:
        return json.dumps([_segment_info(s) for s in segs], indent=2, ensure_ascii=False)
    width = max(len(s.name) for s in segs)
    out = [f"{'segment'.ljust(width)}  prio  description"]
    for s in segs:
        out.append(f"{s.name.ljust(width)}  {s.priority:>4}  {s.doc}")
    out.append("")
    out.append("statusline.py segments <name> for options, fields and colours")
    return "\n".join(out)


def cmd_presets(as_json=False) -> str:
    items = []
    for name in list_presets():
        raw = load_preset(name) or {}
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets", f"{name}.toml")
        with open(path) as fh:
            first = fh.readline().strip().lstrip("# ").strip()
        lines = [{"left": ln.get("left", []), "right": ln.get("right", []), "gap": ln.get("gap", 2)}
                 for ln in raw.get("line", [])]
        items.append({"name": name, "summary": first, "lines": lines,
                      "segment": raw.get("segment", {})})
    if as_json:
        return json.dumps(items, indent=2, ensure_ascii=False)
    out = []
    for it in items:
        out.append(it["summary"])
        for ln in it["lines"]:
            right = f"    ⇥ {', '.join(ln['right'])}" if ln["right"] else ""
            out.append(f"    {', '.join(ln['left'])}{right}")
        out.append("")
    return "\n".join(out).rstrip("\n")


def _read_toml(path):
    import tomllib
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def check_config(raw: dict):
    """Top-level shape problems build_layout does not cover: unknown sections/keys."""
    from .layout import Problem
    out = []
    fixed_keys = ("layout", "bar", "thresholds", "git", "glyphs")
    for section, body in raw.items():
        if section not in DEFAULTS and section != "features":
            out.append(Problem("error", section, "unknown section"))
        elif isinstance(DEFAULTS.get(section), dict) and not isinstance(body, dict):
            out.append(Problem("error", section, "must be a table"))
        elif section in fixed_keys:
            for key in body:
                if key not in DEFAULTS[section]:
                    out.append(Problem("error", f"{section}.{key}", "unknown key"))
    return out


def cmd_validate(path=None, as_json=False):
    path = path or config_path()
    if not path:
        msg = "no config file found; defaults render the classic preset"
        return (json.dumps({"path": None, "ok": True, "problems": [], "note": msg}) if as_json
                else msg), 0
    try:
        raw = _read_toml(path)
    except Exception as exc:
        problems = [{"level": "error", "path": "", "message": f"not valid TOML: {exc}"}]
        text = (json.dumps({"path": path, "ok": False, "problems": problems}) if as_json
                else f"error: {path}: not valid TOML: {exc}")
        return text, 1
    layout = build_layout(deep_merge(DEFAULTS, raw))
    problems = check_config(raw) + layout.problems
    errors = [p for p in problems if p.level == "error"]
    if as_json:
        return json.dumps({
            "path": path, "ok": not errors, "preset": layout.preset,
            "lines": [[s.name for s in ln.left] + ["⇥"] + [s.name for s in ln.right]
                      for ln in layout.lines],
            "problems": [{"level": p.level, "path": p.path, "message": p.message} for p in problems],
        }, indent=2, ensure_ascii=False), (1 if errors else 0)
    out = [f"{path}"]
    out += [f"  {p}" for p in problems]
    n_seg = sum(len(ln.left) + len(ln.right) for ln in layout.lines)
    verdict = "ok" if not errors else f"{len(errors)} error(s)"
    out.append(f"  {verdict}: preset {layout.preset}, {len(layout.lines)} line(s), {n_seg} segment(s)"
               + (f", {len(problems) - len(errors)} warning(s)" if len(problems) > len(errors) else ""))
    return "\n".join(out), (1 if errors else 0)


def cmd_preview(config=None, preset=None, widths=(100, 140, 200), sample="busy",
                as_plain=False, as_json=False, now=None):
    if config:
        apply_config(load_config(config))
    if preset:
        apply_config(deep_merge(CFG, {"preset": preset, "line": []}))
    now = time.time() if now is None else now
    try:
        data = load_sample(sample, now)
    except Exception as exc:
        return f"cannot load sample {sample!r}: {exc}", 2
    layout = current_layout()
    report = {"preset": layout.preset, "sample": sample,
              "problems": [str(p) for p in layout.problems], "widths": []}
    for cols in widths:
        fits = render_lines(data, cols=cols, now=now)
        entry = {"columns": cols, "usable": usable_width(cols), "lines": []}
        for fit in fits:
            if fit is None:
                entry["lines"].append(None)
                continue
            entry["lines"].append({"text": fit.text, "plain": plain(fit.text),
                                   "width": fit.width, "level": LEVELS[fit.level],
                                   "dropped": fit.dropped, "overflow": fit.overflow})
        report["widths"].append(entry)
    if as_json:
        return json.dumps(report, indent=2, ensure_ascii=False), 0

    out = [f"preset {layout.preset} · sample {sample}"]
    out += [f"  {p}" for p in layout.problems]
    for entry in report["widths"]:
        usable = entry["usable"]
        label = f" {entry['columns']} columns, {usable} usable "
        out.append("")
        out.append(("─" * 2 + label + "─" * max(0, usable - 2 - len(label)))[:usable] + "┤")
        notes = []
        for i, ln in enumerate(entry["lines"], 1):
            if ln is None:
                notes.append(f"line {i}: empty, omitted")
                continue
            out.append(ln["plain"] if as_plain else ln["text"])
            bits = []
            if ln["level"] != "full":
                bits.append(f"level {ln['level']}")
            if ln["dropped"]:
                bits.append("dropped " + ", ".join(ln["dropped"]))
            if ln["overflow"]:
                bits.append(f"OVERFLOWS by {ln['overflow']}")
            if bits:
                notes.append(f"line {i}: " + "; ".join(bits))
        for note in notes:
            out.append(f"  ↳ {note}")
    return "\n".join(out), 0


def migrate_config(raw: dict):
    """Fold a pre-2.0 [features] table into segment options. Returns (new, changes)."""
    new = {k: v for k, v in raw.items() if k != "features"}
    feats = raw.get("features")
    changes = []
    if not isinstance(feats, dict):
        return new, changes
    seg = new.setdefault("segment", {})
    remove = set()

    def opt(name, key, value):
        schema = REGISTRY[name].all_options()[key]
        if type(value) is not schema.type and not (schema.type is float and isinstance(value, int)):
            changes.append(f"dropped features setting for segment.{name}.{key}: bad value {value!r}")
            return
        if value == schema.default:
            changes.append(f"segment.{name}.{key} left at its default ({_toml_value(value)})")
            return
        seg.setdefault(name, {})[key] = value
        changes.append(f"segment.{name}.{key} = {_toml_value(value)}")

    table = {
        "pace": lambda v: (opt("limit_5h", "pace", v), opt("limit_7d", "pace", v)),
        "pace_min_elapsed": lambda v: (opt("limit_5h", "pace_min_elapsed", v),
                                       opt("limit_7d", "pace_min_elapsed", v)),
        "reset_clock": lambda v: (opt("limit_5h", "clock", v), opt("limit_7d", "clock", v)),
        "last_commit": lambda v: opt("git", "last_commit", v),
        "last_commit_nudge_min": lambda v: opt("git", "nudge_min", v),
        "context_tokens": lambda v: opt("context", "tokens", v),
        "context_size": lambda v: opt("context", "size", v),
        "prompt_cache_min_ratio": lambda v: opt("cache", "min_ratio", v),
        "repo_links": lambda v: (opt("git", "links", v), opt("pr", "links", v)),
        "fast_mode": lambda v: opt("model", "fast", v),
        "heartbeat_color": lambda v: opt("heartbeat", "color", v),
        "heartbeat_period": lambda v: opt("heartbeat", "period", v),
        "prompt_cache": lambda v: remove.add("cache") if v is False else None,
        "model_window": lambda v: remove.add("limit_7d_model") if v is False else None,
        "heartbeat": lambda v: remove.add("heartbeat") if v is False else None,
    }
    for key, value in feats.items():
        fn = table.get(key)
        if fn is None:
            changes.append(f"dropped features.{key} (unknown)")
            continue
        fn(value)
    if remove:
        lines = new.get("line") or (load_preset(new.get("preset", "classic")) or {}).get("line") or []
        new_lines = []
        for ln in lines:
            entry = {k: v for k, v in ln.items()}
            for side in ("left", "right"):
                if side in entry:
                    entry[side] = [n for n in entry[side] if n not in remove]
            new_lines.append(entry)
        new["line"] = new_lines
        changes.append("removed from lines: " + ", ".join(sorted(remove)))
        for name in remove:
            if seg.pop(name, None) is not None:
                changes.append(f"dropped [segment.{name}] (not on any line)")
    if not seg:
        new.pop("segment", None)
    # Keep the canonical order: scalars, lines, segments, then style sections.
    ordered = {}
    for key in ("preset", "line", "segment"):
        if key in new:
            ordered[key] = new[key]
    for key, val in new.items():
        ordered.setdefault(key, val)
    return ordered, changes


def cmd_migrate(path=None, write=False):
    path = path or config_path()
    if not path:
        return "no config file found; nothing to migrate", 0
    try:
        raw = _read_toml(path)
    except Exception as exc:
        return f"error: {path}: not valid TOML: {exc}", 1
    if "features" not in raw:
        return f"{path}: no [features] table; already current", 0
    new, changes = migrate_config(raw)
    text = to_toml(new, f"# claude-statusline configuration (migrated from {os.path.basename(path)})")
    summary = "\n".join(f"  {c}" for c in changes) or "  (no changes)"
    if write:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = f"{path}.bak-{stamp}"
        n = 1
        while os.path.exists(backup):
            backup = f"{path}.bak-{stamp}-{n}"
            n += 1
        os.replace(path, backup)
        with open(path, "w") as fh:
            fh.write(text)
        return f"migrated {path}\n  backup: {backup}\n{summary}", 0
    return f"# migration of {path} — rerun with --write to apply\n{summary}\n\n{text}", 0


# --- entry -------------------------------------------------------------------
_LEGACY_FLAGS = {"--doctor": ["doctor"], "--ruler": ["ruler"], "--dump-config": ["dump-config"],
                 "--version": ["version"], "--demo": ["render", "--sample", "busy"],
                 "-h": ["help"], "--help": ["help"]}


def _read_payload():
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}
    return raw, (data if isinstance(data, dict) else {})


def _render_stdin() -> int:
    raw, data = _read_payload()
    dump = os.environ.get(DUMP_ENV)
    if dump and raw:
        try:
            with open(os.path.expanduser(dump), "w") as fh:
                fh.write(raw)
        except Exception:
            pass
    try:
        sys.stdout.write(render(data))
    except Exception:
        # A status line that degrades beats one that vanishes.
        if os.environ.get(DEBUG_ENV):
            import traceback
            traceback.print_exc(file=sys.stderr)
        sys.stdout.write(fallback(data))
    return 0


def _widths(text):
    out = []
    for tok in str(text).split(","):
        tok = tok.strip()
        if tok:
            out.append(max(20, int(tok)))
    return tuple(out) or (100, 140, 200)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    apply_config(load_config())
    if not argv:
        return _render_stdin()
    if argv[0] in _LEGACY_FLAGS:
        argv = _LEGACY_FLAGS[argv[0]] + argv[1:]

    import argparse
    ap = argparse.ArgumentParser(prog="statusline.py", add_help=False)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("help")
    sub.add_parser("version")
    sub.add_parser("doctor")
    sub.add_parser("ruler")
    sub.add_parser("dump-config")
    p = sub.add_parser("segments"); p.add_argument("name", nargs="?"); p.add_argument("--json", action="store_true")
    p.add_argument("--markdown", action="store_true")
    p = sub.add_parser("presets"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("validate"); p.add_argument("path", nargs="?"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("preview")
    p.add_argument("--config"); p.add_argument("--preset"); p.add_argument("--width", default="100,140,200")
    p.add_argument("--sample", default="busy"); p.add_argument("--plain", action="store_true")
    p.add_argument("--json", action="store_true"); p.add_argument("--now", type=float)
    p = sub.add_parser("render")
    p.add_argument("--width", type=int); p.add_argument("--sample"); p.add_argument("--now", type=float)
    p.add_argument("--config"); p.add_argument("--preset")
    p = sub.add_parser("migrate"); p.add_argument("path", nargs="?"); p.add_argument("--write", action="store_true")

    try:
        args = ap.parse_args(argv)
    except SystemExit:
        print(f"unknown command: {' '.join(argv)}\n\n{HELP}", file=sys.stderr)
        return 2

    if args.cmd == "help":
        print(HELP)
    elif args.cmd == "version":
        print(f"claude-statusline {__version__}")
    elif args.cmd == "doctor":
        print(cmd_doctor())
    elif args.cmd == "ruler":
        print(cmd_ruler())
    elif args.cmd == "dump-config":
        sys.stdout.write(cmd_dump_config())
    elif args.cmd == "segments":
        sys.stdout.write(cmd_segments(args.name, args.json, args.markdown))
        if not args.markdown:
            print()
    elif args.cmd == "presets":
        print(cmd_presets(args.json))
    elif args.cmd == "validate":
        text, code = cmd_validate(args.path, args.json)
        print(text)
        return code
    elif args.cmd == "preview":
        try:
            widths = _widths(args.width)
        except ValueError:
            print(f"bad --width {args.width!r}; use e.g. 100,140,200", file=sys.stderr)
            return 2
        text, code = cmd_preview(args.config, args.preset, widths, args.sample,
                                 args.plain, args.json, args.now)
        print(text)
        return code
    elif args.cmd == "render":
        if args.config:
            apply_config(load_config(args.config))
        if args.preset:
            apply_config(deep_merge(CFG, {"preset": args.preset, "line": []}))
        if args.sample:
            try:
                data = load_sample(args.sample, args.now)
            except Exception as exc:
                print(f"cannot load sample {args.sample!r}: {exc}", file=sys.stderr)
                return 2
        else:
            _, data = _read_payload()
        try:
            print(render(data, cols=args.width, now=args.now))
        except Exception:
            if os.environ.get(DEBUG_ENV):
                import traceback
                traceback.print_exc(file=sys.stderr)
            print(fallback(data))
    elif args.cmd == "migrate":
        text, code = cmd_migrate(args.path, args.write)
        print(text)
        return code
    return 0
