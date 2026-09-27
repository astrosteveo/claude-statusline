"""Turn a payload into the status line."""
from __future__ import annotations

import os

from . import decor, segments
from .context import Context
from .fit import Fit, Placed, fit_line
from .icons import icon_for
from .template import render as render_template
from .text import Text


def render_spec(spec, ctx, level):
    """One placed segment at one detail level, as an RSeg (or None)."""
    seg = segments.get(spec["type"])
    if seg is None:
        return None
    if spec["quest"] and not ctx.quest_cfg.get("enabled"):
        return None
    opts = spec["opts"]
    f = seg.fields(ctx, opts, level)
    if f is None:
        return None
    tree = spec["tpl"]
    if f.get("_missing"):
        tree = spec["missing"]
        if not tree:
            return None
    icon = spec["icon"]
    if icon is None:
        icon = icon_for(spec["type"], ctx.iconset, ctx.comp.get("glyphs"))
    f["icon"] = f["glyph"] = icon
    dyn = seg.colors(ctx, opts, f)
    colors = ctx.pal
    if dyn:
        colors = dict(colors)
        for k, v in dyn.items():
            colors[k] = ctx.color(v) if isinstance(v, str) else v
    body = render_template(tree, f, colors)
    if not body:
        return None
    tone = ctx.color(opts.get("color") or seg.tone_at(ctx, opts, f) or spec["tone"])
    return decor.RSeg(spec["name"], "" if spec["own_icon"] else icon, body, tone, spec["bare"])


def _placed(specs, ctx):
    return [Placed(s["name"], s["prio"], (lambda s: lambda level: render_spec(s, ctx, level))(s))
            for s in specs]


def render_lines(data, comp, cols=None, now=None, env=None, sync_git=False, ctx=None):
    """The fitted lines (Fit objects); empty lines come back as None."""
    ctx = ctx or Context(data, comp, cols=cols, now=now, env=env, sync_git=sync_git)
    lines = comp["lines"]
    pins = [None] * len(lines)
    game = ctx.quest_cfg.get("enabled") and ctx.quest_cfg.get("placement") == "game"
    if game:
        return _game_lines(ctx, lines)
    if ctx.live and ctx.quest_cfg.get("enabled") and ctx.quest_cfg.get("avatar") not in ("off", False):
        try:
            from .segments.quest import avatar_pins
            pins = avatar_pins(ctx, len(lines)) or pins
        except Exception:
            if os.environ.get("CLAUDE_STATUSLINE_DEBUG"):
                raise
    ctx.avatar_active = any(pins)

    def group(segs, side):
        return decor.group(segs, ctx, side)

    fits = []
    for line, pin in zip(lines, pins):
        avail = ctx.avail
        if pin is not None:
            avail = max(10, avail - pin.width - 1)
        fit = fit_line(_placed(line["left"], ctx), _placed(line["right"], ctx), avail,
                       line.get("gap", 2), group, decor.compose)
        if pin is not None:
            text = fit.text
            pad = max(1, avail - text.width + 1)
            fit.text = Text(text.spans + [(" " * pad, (None, None, 0, None))] + pin.spans)
            fit.width = fit.text.width
        fits.append(fit if fit.text else None)
    return fits


def _game_lines(ctx, lines):
    """Game mode: the ticker line as usual, then the scene with a gauge beside each row."""
    from .gamemode import scene_rows

    def group(segs, side):
        return decor.group(segs, ctx, side)

    scene = [ln for ln in lines if ln.get("scene") is not None]
    hud_w = ctx.quest_cfg.get("game_hud_width", "auto")
    if hud_w == "auto":
        # As wide as the widest gauge in full, rounded up so a percentage gaining
        # a digit doesn't resize the scene (and re-draw the kitty picture).
        widest = max((fit_line(_placed(ln["right"], ctx), [], ctx.avail, 0, group, decor.compose).text.width
                      for ln in scene if ln["right"]), default=0)
        hud_w = -(-widest // 4) * 4
    hud_w = max(0, min(int(hud_w), ctx.avail // 3))
    has_hud = hud_w > 0 and any(ln["right"] for ln in scene)
    width = max(10, ctx.avail - (hud_w + 1 if has_hud else 0))
    rows = scene_rows(ctx, width, len(scene)) if scene else []
    fits = []
    for line in lines:
        if line.get("scene") is None:
            fit = fit_line(_placed(line["left"], ctx), _placed(line["right"], ctx), ctx.avail,
                           line.get("gap", 2), group, decor.compose)
            fits.append(fit if fit.text else None)
            continue
        text = rows[line["scene"]]
        if has_hud:
            hud = fit_line([], _placed(line["right"], ctx), hud_w, 0, group, decor.compose)
            pad = hud_w - hud.text.width
            text = Text(text.spans + [(" " * (1 + max(0, pad)), (None, None, 0, None))] + hud.text.spans)
        fit = Fit(text, 0, [], ctx.avail)
        fits.append(fit)
    return fits


def render(data, comp, cols=None, now=None, env=None, sync_git=False, live=None) -> str:
    ctx = Context(data, comp, cols=cols, now=now, env=env, sync_git=sync_git, live=live)
    return "\n".join(_anchor(f.text.ansi(ctx.mode), ctx.mode)
                     for f in render_lines(data, comp, ctx=ctx) if f is not None)


def _anchor(line, mode):
    """Claude Code trims each line, so a line with an empty left group would lose
    the padding that pushes its right group (and the pinned pet) to the edge.
    A leading reset, or a blank braille cell without colour, is not whitespace."""
    if not line.startswith(" "):
        return line
    return ("⠀" + line[1:]) if mode == "none" else "\033[0m" + line


def fallback(data) -> str:
    """Last resort when rendering raised: never leave the bar blank."""
    try:
        from .util import dig, home_path
        model = dig(data, "model", "display_name") or dig(data, "model", "id") or "Claude"
        cwd = dig(data, "workspace", "current_dir") or data.get("cwd") or "."
        return f"✶ {model}  ▸ {home_path(str(cwd))}"
    except Exception:
        return "✶ Claude"
