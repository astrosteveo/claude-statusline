"""Progress bars with sub-cell resolution.

Three choices are independent:

    style   the glyphs: smooth, shade, line, slim, dots, pips, braille, ascii
    fill    how the filled part is coloured: "level" (one colour by
            threshold), "gradient" (each cell by the usage it stands for),
            "tone" (the segment's colour), a colour role or #hex, or a comma
            list of them blended along the bar
    track   the colour of the empty part

The host reports whole percentages, so a bar needs 101 distinct states;
at eight steps a cell, 13 cells is the narrowest that shows them all.

The smooth style paints cells with background colour rather than glyphs, so
the bar is one continuous shape at any line height, and its boundary cell is
an eighth-block in the fill colour on the track colour. Every glyph is one
cell wide; the fitter depends on it.
"""
from __future__ import annotations

from .color import mix
from .text import BOLD, KEEP, Text

EIGHTHS = "▏▎▍▌▋▊▉"
SHADES = "░▒▓"

STYLES = {
    "smooth": {"doc": "solid blocks, eighth-cell precision", "full": "█", "empty": " ", "ramp": ""},
    "shade": {"doc": "solid fill on a textured ░ track", "full": "█", "empty": "░", "ramp": "▒▓"},
    "line": {"doc": "a heavy rule over a light one", "full": "━", "empty": "─", "ramp": "╸"},
    "slim": {"doc": "half-height blocks, a sleeker bar", "full": "▄", "empty": "▄", "ramp": "▖"},
    "dots": {"doc": "filled and hollow circles", "full": "●", "empty": "○", "ramp": "◐"},
    "pips": {"doc": "slanted pips, whole cells", "full": "▰", "empty": "▱", "ramp": ""},
    "braille": {"doc": "fine braille dots", "full": "⣿", "empty": "⣀", "ramp": "⡇"},
    "ascii": {"doc": "plain ASCII, for any font", "full": "#", "empty": "-", "ramp": "",
              "caps": ("[", "]")},
}
ALIASES = {"block": "smooth", "thin": "line", "blocks": "smooth"}
FILLS = ("level", "gradient", "tone")


def style_name(name) -> str:
    name = ALIASES.get(name, name)
    return name if name in STYLES else "smooth"


def level_role(pct, thresholds) -> str:
    """The colour role for a usage percentage: green, yellow, orange, red."""
    if pct is None:
        return "muted"
    if pct >= thresholds.get("red", 90):
        return "red"
    if pct >= thresholds.get("orange", 75):
        return "orange"
    if pct >= thresholds.get("yellow", 50):
        return "yellow"
    return "green"


def _gradient(pal, thresholds, at: float):
    """The colour a usage of `at` percent stands for, blended between stops."""
    stops = [(0.0, pal["green"]), (float(thresholds.get("yellow", 50)), pal["yellow"]),
             (float(thresholds.get("orange", 75)), pal["orange"]),
             (float(thresholds.get("red", 90)), pal["red"]), (100.0, pal["red"])]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if at <= b:
            if ca is None or cb is None or b <= a:
                return cb or ca
            return mix(ca, cb, (at - a) / (b - a))
    return pal["red"]


def cell_colors(fill: str, pct: float, cells: int, pal, thresholds, tone=None):
    """The fill colour of each cell, left to right."""
    if cells <= 0:
        return []
    if fill == "level" or not fill:
        return [pal.get(level_role(pct, thresholds))] * cells
    if fill == "gradient":
        return [_gradient(pal, thresholds, 100.0 * (i + 0.5) / cells) for i in range(cells)]
    if fill == "tone":
        return [tone or pal.get(level_role(pct, thresholds))] * cells
    from .color import parse
    keys = [k.strip() for k in fill.split(",") if k.strip()]
    stops = [pal[k] if k in pal else parse(k) for k in keys]
    stops = [c for c in stops if c is not None]
    if not stops:
        return [pal.get(level_role(pct, thresholds))] * cells
    if len(stops) == 1:
        return stops * cells
    out = []
    for i in range(cells):
        pos = (i + 0.5) / cells * (len(stops) - 1)
        j = min(len(stops) - 2, int(pos))
        out.append(mix(stops[j], stops[j + 1], pos - j))
    return out


def make_bar(pct, width, *, pal, thresholds, style="smooth", fill="level", track="subtle",
             tone=None, now=None, pulse=False, ink=None, mono=False, min_sliver=True,
             caps=None) -> Text:
    """A `width`-cell bar for `pct` percent.

    `ink` = (fill, track) forces two colours (a bar drawn on a coloured chip).
    `mono` draws with glyphs only, for terminals with colour off.
    """
    if width <= 0:
        return Text()
    try:
        pct = max(0.0, min(100.0, float(pct)))
    except (TypeError, ValueError):
        pct = 0.0
    name = style_name(style)
    spec = STYLES[name]
    if mono and name == "smooth":
        name, spec = "shade", STYLES["shade"]
    full_ch, empty_ch, ramp = spec["full"], spec["empty"], spec["ramp"]

    if ink:
        colors = [ink[0]] * width
        track_c = ink[1]
    else:
        colors = cell_colors(fill, pct, width, pal, thresholds, tone)
        track_c = pal.get(track) if isinstance(track, str) else track
        if track_c is None and isinstance(track, str):
            from .color import parse
            track_c = parse(track)
    hot = pulse and now is not None and pct >= thresholds.get("red", 90) and int(now) % 2 == 1
    if hot and not ink:
        light = pal.get("_light") or pal.get("text")
        if light is not None:
            colors = [mix(c, light, 0.35) if c is not None else c for c in colors]

    cells = pct / 100.0 * width
    full = int(cells)
    frac = cells - full
    sliver = full == 0 and pct > 0 and min_sliver

    part = ""
    if full < width:
        if name == "smooth":
            eighths = int(frac * 8)
            if eighths == 0 and sliver:
                eighths = 1
            if eighths:
                part = EIGHTHS[eighths - 1]
        elif ramp:
            steps = len(ramp) + 1
            k = int(frac * steps)
            if k == 0 and sliver:
                k = 1
            if k:
                part = ramp[min(len(ramp), k) - 1]
        else:
            filled = int(round(cells))
            if filled == 0 and sliver:
                filled = 1
            full = min(width, filled)

    out = Text()
    lcap, rcap = caps if caps is not None else spec.get("caps", ("", ""))
    if lcap:
        out.add(lcap, (track_c, None, 0, None))
    attrs = BOLD if hot and name != "smooth" else 0
    if name == "smooth" and not mono:
        # Background-painted cells: one continuous shape at any line height.
        for i in range(full):
            out.add(" ", (None, colors[i], 0, None))
        if part:
            out.add(part, (colors[full], track_c, 0, None))
        rest = width - full - (1 if part else 0)
        if rest > 0:
            out.add(" " * rest, (None, track_c, 0, None))
    else:
        run, run_c = [], None
        for i in range(full):
            if colors[i] != run_c and run:
                out.add("".join(run), (run_c, None, attrs, None))
                run = []
            run_c = colors[i]
            run.append(full_ch)
        if run:
            out.add("".join(run), (run_c, None, attrs, None))
        if part:
            out.add(part, (colors[full], None, attrs, None))
        rest = width - full - (1 if part else 0)
        if rest > 0:
            out.add(empty_ch * rest, (track_c, None, 0, None))
    if rcap:
        out.add(rcap, (track_c, None, 0, None))
    return _merge(out)


def _merge(t: Text) -> Text:
    spans = []
    for text, st in ((x, (s[0], s[1], s[2] | KEEP, s[3])) for x, s in t.spans):
        if spans and spans[-1][1] == st:
            spans[-1] = (spans[-1][0] + text, st)
        else:
            spans.append((text, st))
    return Text(spans)


def glyphs() -> str:
    """Every glyph a bar can draw; tests hold each to one cell."""
    out = set(EIGHTHS + SHADES)
    for spec in STYLES.values():
        out.update(spec["full"] + spec["empty"] + spec["ramp"])
        out.update("".join(spec.get("caps", ("", ""))))
    return "".join(sorted(out))
