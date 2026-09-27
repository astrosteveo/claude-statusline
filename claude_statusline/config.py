"""Defaults, config discovery, and the compiled-config cache.

The config is TOML, but parsing TOML and validating a layout costs more than
drawing the bar, so the engine compiles the config once (layout.py) and keeps
the result in a marshal file in the runtime directory. Every refresh after
that is a stat of the config file, a stat of the engine's own sources, and
one read: the cache is rebuilt whenever either changes.
"""
from __future__ import annotations

import marshal
import os

from . import __version__

CONFIG_ENV = "CLAUDE_STATUSLINE_CONFIG"
DEBUG_ENV = "CLAUDE_STATUSLINE_DEBUG"
NOCACHE_ENV = "CLAUDE_STATUSLINE_NOCACHE"

CONFIG_SEARCH = (
    "~/.config/claude-statusline/config.toml",
    "~/.claude/statusline.toml",
)
DEFAULT_PATH = CONFIG_SEARCH[0]

PKG = os.path.dirname(os.path.abspath(__file__))

STYLES = ("auto", "minimal", "classic", "dots", "powerline", "slant", "pills", "capsules", "chips")
ICONSETS = ("auto", "nerd", "unicode", "emoji", "none")
PLACEMENTS = ("line", "inline", "manual", "game")

DEFAULTS = {
    "preset": "classic",
    "theme": "claude",
    "style": "auto",
    "icons": "auto",
    "color": "auto",
    "line": [],
    "segment": {},
    "layout": {
        # Columns the host keeps at the right edge before it cuts a line.
        # Claude Code's fullscreen TUI takes about 4 beyond the COLUMNS it
        # reports; one more keeps clear of the wrap. `ruler` calibrates it.
        "right_margin": 5,
        "gap": 2,
        "fallback_columns": 200,
        # Glyphs your font draws two cells wide though Unicode says one.
        "wide_glyphs": [],
        # The separator of the classic and dots styles; "" for the style's own.
        "separator": "",
    },
    "bar": {
        # 13 cells x 8 steps = 104 >= the 101 whole percentages the host
        # sends, so every value renders distinctly.
        "width": 13,
        "style": "smooth",
        "fill": "level",
        "track": "subtle",
        "pulse": False,
        "min_sliver": True,
        "cap_left": "",
        "cap_right": "",
    },
    "thresholds": {"yellow": 50, "orange": 75, "red": 90},
    "git": {
        "enabled": True,
        "cache_ttl": 2.0,
        "timeout": 2.0,
        "slow_threshold": 0.35,
        "slow_backoff": 10.0,
    },
    "glyphs": {},
    "colors": {},
    # Command segments: false hides them all and runs nothing.
    "commands": {"enabled": True},
    # Live activity: hooks that tell the bar what Claude is doing (statusline.py activity enable).
    "activity": {
        "enabled": False,
        # auto: the activity segments get a line of their own unless you place them yourself.
        "placement": "auto",
    },
    "quest": {
        "enabled": False,
        # line: a line of its own at the bottom; inline: the hero badge on
        # line 1; manual: only where you place quest segments yourself;
        # game: the whole bar becomes the game, an animated scene with a
        # few gauges beside it.
        "placement": "line",
        # Game mode: rows of scene under the quest ticker, the gauges beside
        # it (one per row), and the columns kept for them ("auto": as many
        # as the widest gauge takes, 0: no gauges).
        "game_rows": 3,
        "game_hud": ["context", "limit_5h", "limit_7d"],
        "game_hud_width": "auto",
        # The session details on game mode's top row: "auto" (the model, then
        # your lines' segments, less what the gauges show) or a list.
        "game_details": "auto",
        # The pet as an animated picture in kitty; "auto" draws it when
        # Claude Code runs in kitty.
        "avatar": "auto",
        "avatar_cols": 8,
        # Seconds the latest event (loot, level-up, quest) stays on the bar.
        "event_seconds": 30.0,
        # Subagents at work walk with your pet in game mode's scene.
        "party": True,
        # Seasonal events (the Hallowed Harvest, late October): bosses, loot, the scene.
        "seasons": True,
    },
}

# Keys v2 read that v3 ignores, with what replaced them.
RETIRED = {
    "bar.full": "bar styles carry their own glyphs; pick one with bar.style",
    "bar.empty": "bar styles carry their own glyphs; pick one with bar.style",
    "bar.partial": "every bar style has its own sub-cell precision",
    "bar.partial_style": "every bar style has its own sub-cell precision",
}


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, val in (over or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def config_path():
    """The config file in use, or None when there is none."""
    explicit = os.environ.get(CONFIG_ENV)
    if explicit:
        path = os.path.expanduser(explicit)
        return path if os.path.exists(path) else None
    for cand in CONFIG_SEARCH:
        path = os.path.expanduser(cand)
        if os.path.exists(path):
            return path
    return None


def write_path():
    """Where a new config should be written."""
    explicit = os.environ.get(CONFIG_ENV)
    return os.path.expanduser(explicit) if explicit else (config_path() or os.path.expanduser(DEFAULT_PATH))


def read_toml(path):
    """(dict, error message or None). Never raises."""
    if not path:
        return {}, None
    try:
        import tomllib
        with open(path, "rb") as fh:
            return tomllib.load(fh), None
    except FileNotFoundError:
        return {}, None
    except Exception as exc:                   # a broken file must not blank the bar
        return {}, f"not valid TOML: {exc}"


def runtime_dir() -> str:
    base = os.environ.get("XDG_RUNTIME_DIR")
    if not base or not os.path.isdir(base):
        base = os.path.join("/tmp", f"claude-statusline-{os.getuid()}") if hasattr(os, "getuid") else "/tmp"
        path = base
    else:
        path = os.path.join(base, "claude-statusline")
    try:
        os.makedirs(path, mode=0o700, exist_ok=True)
    except OSError:
        pass
    return path


def _code_stamp() -> int:
    """Changes whenever the engine's sources or presets change."""
    newest = 0
    for sub in ("", "segments", "presets"):
        try:
            with os.scandir(os.path.join(PKG, sub) if sub else PKG) as it:
                for entry in it:
                    if entry.name.endswith((".py", ".toml")):
                        m = entry.stat().st_mtime_ns
                        if m > newest:
                            newest = m
        except OSError:
            pass
    return newest


def _crc(text: str) -> str:
    import zlib
    return "%08x" % zlib.crc32(text.encode("utf-8", "replace"))


def compiled(path=None, use_cache=True) -> dict:
    """The compiled config for `path` (default: the one in use)."""
    path = config_path() if path is None else path
    try:
        st = os.stat(path) if path else None
    except OSError:
        st = None
    key = [__version__, path or "", st.st_mtime_ns if st else 0, st.st_size if st else 0, _code_stamp()]
    use_cache = use_cache and not os.environ.get(NOCACHE_ENV)
    cache = os.path.join(runtime_dir(), f"compiled-{_crc(path or '-')}.bin")
    if use_cache:
        try:
            with open(cache, "rb") as fh:
                blob = marshal.loads(fh.read())
            if blob.get("key") == key:
                return blob["compiled"]
        except Exception:
            pass
    from .layout import compile_config
    raw, err = read_toml(path)
    comp = compile_config(raw, path=path, read_error=err)
    if use_cache:
        try:
            tmp = f"{cache}.{os.getpid()}"
            with open(tmp, "wb") as fh:
                marshal.dump({"key": key, "compiled": comp}, fh)
            os.replace(tmp, cache)
        except Exception:
            pass
    return comp
