"""claude-statusline: a declarative status line engine for Claude Code."""
from __future__ import annotations

__version__ = "2.0.0.dev0"

from .config import CFG, DEFAULTS, apply_config, config_path, deep_merge, load_config, usable_width  # noqa: E402,F401
from .width import cell_width, display_width  # noqa: E402,F401
from .ansi import c, link  # noqa: E402,F401
from .util import compact_path, dur, num, short_num, to_epoch  # noqa: E402,F401
from .bar import make_bar, pct_color  # noqa: E402,F401
from .payload import find_windows  # noqa: E402,F401
from .layout import build_layout  # noqa: E402,F401
from .render import fallback, render, render_lines, render_segment  # noqa: E402,F401
from .cli import main  # noqa: E402,F401



