"""Turn a payload into lines."""
from __future__ import annotations

from . import config
from .ansi import c
from .config import CFG, GLYPHS
from .context import Context
from .fit import fit_line
from .layout import build_layout
from .segments import REGISTRY
from .util import compact_path, dig

_layout = None
_layout_gen = -1


def current_layout():
    """The layout for the active config, rebuilt only when the config changes."""
    global _layout, _layout_gen
    if _layout is None or _layout_gen != config.GENERATION:
        _layout = build_layout()
        _layout_gen = config.GENERATION
    return _layout


def render_lines(data, cols=None, now=None):
    """Fit every line; returns the Fit objects (empty lines included as None)."""
    ctx = Context(data, cols, now)
    sep = c("dim", CFG["layout"]["separator"])
    fits = []
    for line in current_layout().lines:
        fit = fit_line([s.place(ctx) for s in line.left],
                       [s.place(ctx) for s in line.right], ctx.avail, sep, line.gap)
        fits.append(fit if fit.text else None)
    return fits


def render(data, cols=None, now=None) -> str:
    return "\n".join(f.text for f in render_lines(data, cols, now) if f is not None)


def render_segment(name, data=None, cols=None, now=None, level=0, **opts) -> str:
    """Render one catalog segment with its defaults (plus `opts`), for demos and tests."""
    seg = REGISTRY[name]
    resolved = {k: o.default for k, o in seg.all_options().items()}
    resolved.update(opts)
    return seg.render(Context(data or {}, cols, now), resolved, level)


def fallback(data) -> str:
    """Last resort when render() raises: never leave the bar blank."""
    try:
        model = (dig(data, "model", "display_name")
                 or dig(data, "model", "id") or "claude")
        cwd = (dig(data, "workspace", "current_dir")
               or data.get("cwd") or ".")
        return f"{GLYPHS['model']} {model}  {GLYPHS['dir']} {compact_path(str(cwd))}"
    except Exception:
        return "claude"
