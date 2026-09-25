"""Entry point. Kept tiny: the render path imports only what it draws.

    statusline.py            with a payload on stdin: print the bar
    statusline.py            in a terminal: open the configurator
    statusline.py <command>  everything else (see `help`)
"""
from __future__ import annotations

import os
import sys

CAPTURE_EVERY = 5.0      # seconds between saves of the live payload


def _capture(raw: bytes):
    """Keep the latest payload so the configurator can preview real data."""
    try:
        from .config import runtime_dir
        path = os.path.join(runtime_dir(), "last-payload.json")
        import time
        try:
            if time.time() - os.stat(path).st_mtime < CAPTURE_EVERY:
                return
        except OSError:
            pass
        tmp = f"{path}.{os.getpid()}"
        with open(tmp, "wb") as fh:
            fh.write(raw)
        os.replace(tmp, path)
    except Exception:
        pass


def render_stdin() -> int:
    try:
        raw = sys.stdin.buffer.read()
    except Exception:
        raw = b""
    data = {}
    try:
        from .fastjson import loads
        data = loads(raw) if raw.strip() else {}
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    try:
        from .config import compiled
        from .render import render
        from . import width
        comp = compiled()
        width.WIDE.update(comp["layout"].get("wide_glyphs") or ())
        out = render(data, comp)
    except Exception:
        if os.environ.get("CLAUDE_STATUSLINE_DEBUG"):
            import traceback
            traceback.print_exc(file=sys.stderr)
        from .render import fallback
        out = fallback(data)
    try:
        sys.stdout.write(out)
        sys.stdout.flush()
    except Exception:
        pass
    if raw and data:
        _capture(raw)
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if os.path.basename(sys.argv[0] or "").startswith("claude-quest"):
        from .quest.main import main as quest_main
        return quest_main(argv) or 0
    if not argv:
        try:
            interactive = sys.stdin.isatty() and sys.stdout.isatty()
        except Exception:
            interactive = False
        if not interactive:
            return render_stdin()
        argv = ["configure"]
    from .cli import run
    return run(argv)
