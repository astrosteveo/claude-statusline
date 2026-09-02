"""Defaults, config discovery and the mutable engine state."""
from __future__ import annotations

import os
import sys


CONFIG_ENV = "CLAUDE_STATUSLINE_CONFIG"
DUMP_ENV = "CLAUDE_STATUSLINE_DUMP"      # set to a path to capture raw payloads
DEBUG_ENV = "CLAUDE_STATUSLINE_DEBUG"    # set to surface tracebacks on stderr

CONFIG_SEARCH = (
    "~/.config/claude-statusline/config.toml",
    "~/.claude/statusline.toml",
)

FIVE_HOUR = 5 * 3600
SEVEN_DAY = 7 * 86400

# ---------------------------------------------------------------- defaults ---
DEFAULTS = {
    "layout": {
        # Columns the host TUI reserves at the right edge. Claude Code's
        # fullscreen TUI consumes ~4 beyond the COLUMNS it reports (frame and
        # padding) and then truncates with an ellipsis; 4 reserved + 1 wrap
        # gap = 5. Run `--ruler` to calibrate for your terminal.
        "right_margin": 5,
        "separator": " │ ",
        "fallback_columns": 200,
        # Glyphs your font renders double-width even though Unicode calls them
        # narrow. Purely cosmetic elsewhere, but they push the line over budget.
        "wide_glyphs": [],
    },
    "bar": {
        # 13 cells x 8 sub-steps = 104 >= the 101 integer percentages the host
        # sends, so every distinct input renders distinctly. Narrower collides;
        # wider adds columns without adding information.
        "width": 13,
        "partial": True,          # sub-cell resolution for the boundary cell
        "partial_style": "auto",  # "auto" | "eighth" (▏▎▍) | "shade" (░▒▓) | "off"
        "min_sliver": True,       # any usage > 0 shows at least a sliver
        "full": "█",
        "empty": "█",
    },
    "thresholds": {"yellow": 50, "orange": 75, "red": 90},
    "features": {
        "pace": True,
        "pace_min_elapsed": 0.10,
        "reset_clock": True,
        "last_commit": True,
        "last_commit_nudge_min": 45,
        "context_tokens": True,
        "context_size": True,
        "prompt_cache": True,
        "prompt_cache_min_ratio": 0.90,
        "model_window": True,
        "repo_links": True,
        "fast_mode": True,
        # A liveness tick docked to the right of line 1. The frame is derived
        # from the wall clock rather than a counter, because each refresh is a
        # brand new process with no memory of the last one — so if refreshing
        # stops, the frame simply stops moving, which is the whole signal.
        "heartbeat": True,
        "heartbeat_color": "dim",
        "heartbeat_period": 1.0,   # seconds per frame
    },
    "git": {
        "enabled": True,
        "timeout": 2.0,
        "cache_ttl": 2.0,       # seconds a cached git read stays fresh
        "slow_threshold": 0.35, # a read slower than this triggers backoff
        "slow_backoff": 10.0,   # ttl = max(cache_ttl, duration * slow_backoff)
    },
    "glyphs": {
        "model": "◆", "dir": "▸", "git": "⎇", "reset": "↻",
        "stash": "⚑", "ahead": "↑", "behind": "↓",
        "pace": "⇢", "clock": "⏱", "pr": "⇄", "host": "⌂",
        "env": "⬢", "fast": "⚡", "cache": "⌗",
        # One character per frame, cycled in order.
        "heartbeat_frames": "⠋⠙⠹⠸⠼⠴⠦⠧",
    },
    "colors": {
        "reset": "0", "dim": "38;5;240", "gray": "38;5;245",
        "model": "38;5;141", "dir": "38;5;39", "cyan": "38;5;80",
        "green": "38;5;114", "yellow": "38;5;221", "orange": "38;5;208",
        "red": "38;5;203", "gold": "38;5;179", "purple": "38;5;176",
        "bold": "1",
    },
}

# Mutable module state, rebound by apply_config().
CFG: dict = {}
C: dict = {}
GLYPHS: dict = {}
WIDE: set = set()


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, val in (over or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def config_path() -> str | None:
    """First existing config file, or None."""
    explicit = os.environ.get(CONFIG_ENV)
    if explicit:
        path = os.path.expanduser(explicit)
        return path if os.path.exists(path) else None
    for cand in CONFIG_SEARCH:
        path = os.path.expanduser(cand)
        if os.path.exists(path):
            return path
    return None


def load_config(path: str | None = None) -> dict:
    """DEFAULTS merged with the user's TOML. Never raises."""
    path = path if path is not None else config_path()
    if not path:
        return deep_merge(DEFAULTS, {})
    try:
        import tomllib
        with open(path, "rb") as fh:
            return deep_merge(DEFAULTS, tomllib.load(fh))
    except Exception:
        # A broken config must not take the status line down with it.
        if os.environ.get(DEBUG_ENV):
            import traceback
            traceback.print_exc(file=sys.stderr)
        return deep_merge(DEFAULTS, {})

def apply_config(cfg: dict) -> None:
    """Rebind the engine state in place, so `from .config import CFG` stays live."""
    CFG.clear()
    CFG.update(cfg)
    C.clear()
    C.update({k: f"\033[{v}m" for k, v in cfg["colors"].items()})
    GLYPHS.clear()
    GLYPHS.update(cfg["glyphs"])
    WIDE.clear()
    WIDE.update(cfg["layout"].get("wide_glyphs") or ())


apply_config(deep_merge(DEFAULTS, {}))
