"""Turn a payload into the status line."""
from __future__ import annotations

import os

from . import decor, segments
from .context import Context
from .fit import GLANCE, NARROW, TEXT, Fit, Placed, fit_details, fit_line
from .icons import icon_for
from .template import render as render_template
from .text import Text

PAD = (None, None, 0, None)


def render_spec(spec, ctx, level, room=0, seen=None):
    """One placed segment at one detail level, as an RSeg (or None). `room` is
    extra columns an elastic segment may take; at `glance` a segment whose
    icon carries its state is drawn as that icon alone. `seen` holds the
    (fields, rendering) pairs of levels already drawn: a level whose fields
    are the same reuses the rendering instead of drawing it again."""
    seg = segments.get(spec["type"])
    if seg is None:
        return None
    if spec["quest"] and not ctx.quest_cfg.get("enabled"):
        return None
    glance = level >= GLANCE
    if glance:
        level = TEXT
    opts = spec["opts"]
    if room:
        opts = dict(opts, _room=room)
    f = seg.fields(ctx, opts, level)
    if f is None:
        return None
    tree = spec["tpl"]
    missing = f.get("_missing")
    if missing:
        tree = spec["missing"]
        if not tree:
            return None
    icon = spec["icon"]
    if icon is None:
        icon = icon_for(spec["type"], ctx.iconset, ctx.comp.get("glyphs"))
    f["icon"] = f["glyph"] = icon
    if glance and seg.glance and icon and not spec["own_icon"] and not missing:
        tone = ctx.color(opts.get("color") or seg.tone_at(ctx, opts, f) or spec["tone"])
        return decor.RSeg(spec["name"], icon, Text(), tone, spec["bare"], glance=True)
    if seen:
        for old, out in seen:
            if old == f:
                return out
    dyn = seg.colors(ctx, opts, f)
    colors = ctx.pal
    if dyn:
        colors = dict(colors)
        for k, v in dyn.items():
            colors[k] = ctx.color(v) if isinstance(v, str) else v
    body = render_template(tree, f, colors)
    out = None
    if body:
        tone = ctx.color(opts.get("color") or seg.tone_at(ctx, opts, f) or spec["tone"])
        out = decor.RSeg(spec["name"], "" if spec["own_icon"] else icon, body, tone, spec["bare"])
    if seen is not None:
        seen.append((f, out))
    return out


def _placed(specs, ctx):
    def make(spec):
        seen = []
        return lambda level, room=0: render_spec(spec, ctx, level, room, seen)
    return [Placed(s["name"], s["prio"], make(s), s.get("elastic", False)) for s in specs]


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
            fit.text = Text(text.spans + [(" " * pad, PAD)] + pin.spans)
            fit.width = fit.text.width
        fits.append(fit if fit.text else None)
    return fits


def _game_lines(ctx, lines):
    """Game mode: the ticker line with the session details beside it, then the
    scene with a gauge beside each row."""
    from .gamemode import scene_rows

    def group(segs, side):
        return decor.group(segs, ctx, side)

    scene = [ln for ln in lines if ln.get("scene") is not None]
    from . import menu
    open_menu = menu.state(ctx) if scene else None
    if open_menu is not None:        # the settings menu takes the scene's rows, gauges and all
        hud = None
        rows = menu.rows(ctx, ctx.avail, len(scene), open_menu)
    else:
        width, hud_w, hud = scene_geometry(ctx, lines, group)
        rows = scene_rows(ctx, width, len(scene)) if scene else []
        news_w = news_width(ctx, len(scene))
        if news_w:
            from .gamemode import news_rows
            rows = [Text(r.spans + [(" ", PAD)] + n.spans)
                    for r, n in zip(rows, news_rows(ctx, news_w, len(scene)))]
    fits = []
    for line in lines:
        if line.get("scene") is None:
            fit = _top_row(ctx, line, group)
            fits.append(fit if fit.text else None)
            continue
        text = rows[line["scene"]]
        if hud:
            gauge = hud.get(line["scene"]) or Text()
            pad = hud_w - gauge.width
            text = Text(text.spans + [(" " * (1 + max(0, pad)), PAD)] + gauge.spans)
        fits.append(Fit(text, 0, [], ctx.avail))
    return fits


def scene_geometry(ctx, lines, group=None):
    """(scene width in columns, gauge column width, {row: gauge}) for game mode's scene rows."""
    group = group or (lambda segs, side: decor.group(segs, ctx, side))
    scene = [ln for ln in lines if ln.get("scene") is not None]
    hud_w, hud = _hud(ctx, scene, group)
    news_w = news_width(ctx, len(scene))
    return max(10, ctx.avail - (hud_w + 1 if hud else 0) - (news_w + 1 if news_w else 0)), hud_w, hud


def news_width(ctx, rows):
    """Columns for the news beside the scene. They follow the terminal's width alone, never the
    news, so the scene's picture keeps its size (a new size means drawing it again)."""
    setting = ctx.quest_cfg.get("game_news", "auto")
    if setting == "off" or not rows:
        return 0
    if setting == "auto":
        if rows < 3 or ctx.avail < 120:
            return 0
        return min(64, ctx.avail * 28 // 100 // 4 * 4)
    return max(0, min(int(setting), ctx.avail // 2))


def _top_row(ctx, line, group):
    """The quest ticker, fitted exactly as if it were alone, then the session
    details in whatever room it leaves, right-aligned against the ticker's
    right group. The details give up detail, then drop; they never clip, and
    nothing they do changes the ticker."""
    gap = line.get("gap", 2)
    fit = fit_line(_placed(line["left"], ctx), _placed(line["right"], ctx), ctx.avail, gap, group,
                   decor.compose)
    details = line.get("details") or []
    if not details or fit.overflow or fit.parts is None:
        return fit
    lt, rt = fit.parts
    apart = gap + 2              # between the details and the streak and gold, so the game's end stands out
    room = ctx.avail - lt.width - rt.width - (gap if lt else 0) - (apart if rt else 0)
    dfit = fit_details(_placed(details, ctx), max(0, room), group)
    fit.details = dfit
    dt = dfit.text
    if not dt:
        return fit
    if not lt and not rt:
        fit.text = dt
    else:
        pad = ctx.avail - lt.width - dt.width - rt.width - (apart if rt else 0)
        fit.text = Text(lt.spans + [(" " * pad, PAD)] + dt.spans + ([(" " * apart, PAD)] + rt.spans if rt else []))
    fit.width = fit.text.width
    return fit


def _hud(ctx, scene, group):
    """(column width, {scene row: gauge Text}) for the gauges beside the scene.

    A gauge has a compact look (version 3's `ctx 28%`) and a rich one (a
    small bar, the pace, the reset, the tokens). On a wide terminal the column
    grows with the terminal (never with the values, so a countdown ticking
    does not resize the scene and re-draw its kitty picture) and the gauges
    take the richest level at which every one of them fits it."""
    rows = [ln for ln in scene if ln["right"]]
    if not rows:
        return 0, {}
    compact = {ln["scene"]: _placed(ln["right"], ctx)[0] for ln in rows}
    rich = {ln["scene"]: _placed(ln.get("rich") or ln["right"], ctx)[0] for ln in rows}

    def one(p, level):
        s = p.at(level)
        return group([s], "right") if s is not None else Text()

    setting = ctx.quest_cfg.get("game_hud_width", "auto")
    widest = max((one(p, 0).width for p in compact.values()), default=0)
    compact_w = -(-widest // 4) * 4           # rounded up, so a digit more doesn't resize the scene
    if setting == "auto":
        hud_w = compact_w
        if ctx.avail >= 160:
            hud_w = max(compact_w, min(40, ctx.avail * 17 // 100 // 4 * 4))
    else:
        hud_w = int(setting)
    hud_w = max(0, min(hud_w, ctx.avail // 3))
    if hud_w <= 0:
        return 0, {}
    if hud_w > compact_w:
        for level in range(NARROW + 1):
            texts = {i: one(p, level) for i, p in rich.items()}
            if all(t.width <= hud_w for t in texts.values()):
                # Left-aligned, so the icons, labels, bars and percentages line up.
                return hud_w, {i: Text(t.spans + [(" " * (hud_w - t.width), PAD)]) for i, t in texts.items()}
    return hud_w, {i: fit_line([], [p], hud_w, 0, group, decor.compose).text for i, p in compact.items()}


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
