"""Command-line entry points."""
from __future__ import annotations

import json
import os
import sys
import time

from . import __version__
from .config import CFG, CONFIG_SEARCH, DEBUG_ENV, DUMP_ENV, apply_config, config_path, load_config
from .gitinfo import _cache_dir
from .config import usable_width
from .render import fallback, render

HELP = """Claude Code status line.

Reads the status JSON on stdin and prints the bar. Configure via TOML
(see --dump-config); no third-party dependencies, stdlib only.

    --doctor        report resolved config, detected width, cache state
    --ruler         print calibration rulers (see README: right_margin)
    --demo          render a bundled sample payload
    --dump-config   print the effective config as TOML
    --version       print version
"""


SAMPLE = {
    "model": {"display_name": "Opus 5 (1M context)", "id": "claude-opus-5[1m]"},
    "effort": {"level": "high"},
    "session_name": "demo session",
    "workspace": {"current_dir": os.path.expanduser("~/Projects/demo"),
                  "repo": {"host": "github.com", "owner": "octocat",
                           "name": "demo"}},
    "cost": {"total_cost_usd": 12.5, "total_duration_ms": 3_600_000,
             "total_lines_added": 420, "total_lines_removed": 69},
    "context_window": {"used_percentage": 38, "total_input_tokens": 380_000,
                       "context_window_size": 1_000_000},
    "prompt_cache": {"warm": True, "hit_ratio": 0.98},
    "rate_limits": {
        "five_hour": {"used_percentage": 62,
                      "resets_at": time.time() + 2 * 3600},
        "seven_day": {"used_percentage": 24,
                      "resets_at": time.time() + 4 * 86400},
    },
}


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
    lines = [
        f"claude-statusline {__version__}",
        f"  python          {sys.version.split()[0]}",
        f"  config          {path or '(defaults; none found)'}",
        f"  searched        {', '.join(CONFIG_SEARCH)}",
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
    return "\n".join(lines)


def _toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    return json.dumps(str(v), ensure_ascii=False)


def cmd_dump_config() -> str:
    out = [f"# claude-statusline {__version__} — effective configuration"]
    for key, val in CFG.items():
        if not isinstance(val, (dict, list)):
            out.append(f"{key} = {_toml_value(val)}")
    for section, body in CFG.items():
        if section == "line":
            for entry in body:
                out.append("\n[[line]]")
                for key, val in entry.items():
                    out.append(f"{key} = {_toml_value(val)}")
        elif section == "segment":
            for name, table in body.items():
                out.append(f"\n[segment.{name}]")
                for key, val in table.items():
                    out.append(f"{key} = {_toml_value(val)}")
        elif isinstance(body, dict):
            out.append(f"\n[{section}]")
            for key, val in body.items():
                out.append(f"{key} = {_toml_value(val)}")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    apply_config(load_config())

    if argv:
        flag = argv[0]
        if flag == "--version":
            print(f"claude-statusline {__version__}")
            return 0
        if flag == "--doctor":
            print(cmd_doctor())
            return 0
        if flag == "--ruler":
            print(cmd_ruler())
            return 0
        if flag == "--dump-config":
            print(cmd_dump_config())
            return 0
        if flag == "--demo":
            print(render(SAMPLE))
            return 0
        if flag in ("-h", "--help"):
            print(HELP)
            return 0
        print(f"unknown flag: {flag}\n\n{HELP}", file=sys.stderr)
        return 2

    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}

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
