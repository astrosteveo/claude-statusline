"""Compile a config into what the renderer needs: lines of resolved segments.

    preset = "classic"                 # supplies the lines when none are declared
    theme  = "catppuccin"
    style  = "capsules"

    [[line]]
    left  = ["model", "dir", "git"]    # flows from the left edge
    right = ["heartbeat"]              # pushed against the right edge
    gap   = 1                          # minimum columns between the groups

    [segment.dir]                      # options for a catalog segment...
    depth = 2

    [segment.greeting]                 # ...or a named instance of one
    type = "text"
    text = "hello"

Nothing here raises. Problems are collected with the path they concern, and
whatever could not be understood is skipped, so a typo never blanks the bar.
The result is plain data (dicts, lists, tuples) so it can be cached.
"""
from __future__ import annotations

import os

from . import segments as catalog
from .bar import ALIASES as BAR_ALIASES, FILLS, STYLES as BAR_STYLES
from .color import MODES, parse as parse_color
from .config import DEFAULTS, ICONSETS, PKG, PLACEMENTS, RETIRED, STYLES, deep_merge
from .template import TemplateError, compile_template, fields_of, known_tag, tags_of
from .themes import THEMES, palette

PRESET_DIR = os.path.join(PKG, "presets")

LEGACY_FEATURES = {
    "pace": "segment.limit_5h.pace / segment.limit_7d.pace",
    "reset_clock": "segment.limit_5h.clock / segment.limit_7d.clock",
    "last_commit": "segment.git.last_commit",
    "context_tokens": "segment.context.tokens",
    "heartbeat": "leave `heartbeat` out of the line to hide it",
}

GAME_TICKER = {"left": ["quest", "quest_boss", "quest_raid", "quest_dungeon", "quest_daily", "quest_buffs",
                        "quest_event"],
               "right": ["quest_streak", "quest_gold"]}
# How a gauge looks beside the game scene.
GAME_HUD_LOOK = {"width": 0, "format": "[<subtext>{label}</subtext> ]<level><bold>{pct}%</bold></level>"}
# The scene is the picture in game mode, so the ticker keeps no bar but the hero's XP.
GAME_BARLESS = {"quest_raid": {"width": 0}}
QUEST_LINE = {"left": ["quest", "quest_daily", "quest_boss", "quest_raid", "quest_dungeon", "quest_buffs",
                       "quest_event"],
              "right": ["quest_pet", "quest_streak", "quest_gold"]}


def problem(level, where, message):
    return (level, where, message)


def list_presets():
    try:
        return sorted(f[:-5] for f in os.listdir(PRESET_DIR) if f.endswith(".toml"))
    except OSError:
        return []


def load_preset(name):
    if not isinstance(name, str) or not name or "/" in name or name.startswith("."):
        return None
    try:
        import tomllib
        with open(os.path.join(PRESET_DIR, f"{name}.toml"), "rb") as fh:
            return tomllib.load(fh)
    except Exception:
        return None


def preset_summary(name) -> str:
    try:
        with open(os.path.join(PRESET_DIR, f"{name}.toml")) as fh:
            return fh.readline().lstrip("# ").strip()
    except OSError:
        return ""


def closest(word, candidates):
    """Cheap did-you-mean: a shared prefix, or one edit away."""
    word = str(word)
    best, score = None, 0
    for cand in candidates:
        common = os.path.commonprefix([word, cand])
        s = len(common) * 2
        if abs(len(word) - len(cand)) <= 1:
            s += sum(1 for a, b in zip(word, cand) if a == b)
        if s > score and s >= max(3, len(word)):
            best, score = cand, s
    return best


def _hint(word, candidates):
    h = closest(word, candidates)
    return f" (did you mean {h!r}?)" if h else ""


def coerce(value, opt, where, problems):
    """Type-check one option value; returns the value to use."""
    want = opt.type
    ok = None
    if want is bool and isinstance(value, bool):
        ok = value
    elif want is int and isinstance(value, int) and not isinstance(value, bool):
        ok = value
    elif want is int and isinstance(value, float) and value.is_integer():
        ok = int(value)
    elif want is float and isinstance(value, (int, float)) and not isinstance(value, bool):
        ok = float(value)
    elif want is str and isinstance(value, str):
        ok = value
    if ok is None:
        problems.append(problem("error", where, f"expected {want.__name__}, got {type(value).__name__} {value!r}"))
        return opt.default
    if opt.choices and ok not in opt.choices:
        problems.append(problem("error", where, f"{ok!r} is not one of {', '.join(map(str, opt.choices))}"
                                + _hint(ok, opt.choices)))
        return opt.default
    return ok


def resolve_segment(name, tables, problems, pal, seen, where_line):
    """A name placed on a line -> a compiled spec dict, or None."""
    table = tables.get(name)
    if table is not None and not isinstance(table, dict):
        problems.append(problem("error", f"segment.{name}", "must be a table"))
        table = None
    table = table or {}
    type_ = table.get("type", name)
    seg = catalog.get(type_) if isinstance(type_, str) else None
    if seg is None:
        where = f"segment.{name}.type" if "type" in table else where_line
        problems.append(problem("error", where, f"unknown segment {type_!r}"
                                + _hint(type_, catalog.CATALOG)))
        return None
    if type_ != name and name in catalog.CATALOG and name not in seen:
        problems.append(problem("warning", f"segment.{name}",
                                f"named after the {name!r} segment but has type {type_!r}"))
    schema = seg.all_options()
    opts = {key: o.default for key, o in schema.items()}
    for key, value in table.items():
        if key == "type":
            continue
        if key not in schema:
            problems.append(problem("error", f"segment.{name}.{key}", "unknown option" + _hint(key, schema)))
            continue
        opts[key] = coerce(value, schema[key], f"segment.{name}.{key}", problems)
    colors = set(pal) | set(seg.colors_doc)
    trees = {}
    for key in ("format", "missing"):
        src = opts.get(key)
        if not isinstance(src, str) or (key == "missing" and not src):
            continue
        try:
            tree = compile_template(src)
        except TemplateError as exc:
            problems.append(problem("error", f"segment.{name}.{key}", str(exc)))
            src = schema[key].default
            tree = compile_template(src) if src else ()
        for field in sorted(fields_of(tree) - set(seg.fields_doc) - {"url", "icon", "glyph"}):
            problems.append(problem("warning", f"segment.{name}.{key}", f"{{{field}}} is not a field of {type_!r}"))
        for tag in sorted(tags_of(tree)):
            if tag != "link" and not known_tag(tag, colors):
                problems.append(problem("warning", f"segment.{name}.{key}", f"<{tag}> is not a colour"))
        trees[key] = tree
    tone = opts.get("color") or seg.tone
    if opts.get("color") and not (opts["color"] in pal or parse_color(opts["color"])):
        problems.append(problem("error", f"segment.{name}.color", f"unknown colour {opts['color']!r}"))
        tone = seg.tone
    # Bar options every bar segment shares.
    for key in ("style", "fill"):
        val = opts.get(key)
        if key in seg.options and isinstance(val, str) and val:
            if key == "style" and val not in BAR_STYLES and val not in BAR_ALIASES:
                problems.append(problem("error", f"segment.{name}.style",
                                        f"unknown bar style {val!r}" + _hint(val, BAR_STYLES)))
            if key == "fill":
                for m in check_fill(val, pal):
                    problems.append(problem("error", f"segment.{name}.fill", m))
    seen.add(name)
    tpl = trees.get("format", ())
    own_icon = bool(fields_of(tpl) & {"icon", "glyph"})
    return {"name": name, "type": type_, "mod": catalog.CATALOG[type_],
            "prio": opts.get("priority") if opts.get("priority") is not None else seg.priority,
            "opts": {k: v for k, v in opts.items() if k not in ("format", "missing")},
            "tpl": tpl, "missing": trees.get("missing"), "icon": opts.get("icon"),
            "tone": tone, "own_icon": own_icon, "bare": seg.bare, "quest": seg.quest}


def check_fill(fill, pal):
    if not isinstance(fill, str) or not fill:
        return ["fill must be a string"]
    if fill in FILLS:
        return []
    bad = [k for k in (x.strip() for x in fill.split(",")) if k and k not in pal and parse_color(k) is None]
    if bad:
        return [f"unknown colour(s) {', '.join(map(repr, bad))}; use level, gradient, tone, "
                f"theme roles or #hex"]
    return []


def _check_section(cfg_raw, problems):
    known = set(DEFAULTS) | {"features", "version"}
    for section, body in cfg_raw.items():
        if section not in known:
            problems.append(problem("error", section, "unknown setting" + _hint(section, DEFAULTS)))
            continue
        default = DEFAULTS.get(section)
        if isinstance(default, dict) and not isinstance(body, dict):
            problems.append(problem("error", section, "must be a table"))
            continue
        if section in ("layout", "bar", "thresholds", "git", "quest"):
            for key, val in body.items():
                where = f"{section}.{key}"
                if where in RETIRED:
                    problems.append(problem("warning", where, f"no longer used: {RETIRED[where]}"))
                elif key not in default:
                    problems.append(problem("error", where, "unknown key" + _hint(key, default)))
                elif where in ("quest.avatar", "quest.game_hud_width"):   # checked below
                    continue
                elif default[key] is not None and not isinstance(val, type(default[key])) and not (
                        isinstance(default[key], float) and isinstance(val, int) and not isinstance(val, bool)):
                    problems.append(problem("error", where, f"expected {type(default[key]).__name__}, "
                                                            f"got {type(val).__name__} {val!r}"))
    feats = cfg_raw.get("features")
    if isinstance(feats, dict):
        for key in feats:
            problems.append(problem("warning", f"features.{key}",
                                    f"no longer read; use {LEGACY_FEATURES.get(key, 'the segment options')} "
                                    f"(`statusline migrate` rewrites the file)"))


def _choice(cfg, key, choices, problems, default):
    val = cfg.get(key, default)
    if val not in choices:
        problems.append(problem("error", key, f"unknown {key} {val!r}; one of {', '.join(choices)}"
                                + _hint(val, choices)))
        return default
    return val


def compile_config(raw: dict, path=None, read_error=None) -> dict:
    problems = []
    if read_error:
        problems.append(problem("error", "", read_error))
    raw = raw if isinstance(raw, dict) else {}
    _check_section(raw, problems)
    safe = {k: v for k, v in raw.items() if not (isinstance(DEFAULTS.get(k), dict) and not isinstance(v, dict))}
    cfg = deep_merge(DEFAULTS, safe)

    theme = cfg.get("theme")
    if theme not in THEMES:
        problems.append(problem("error", "theme", f"unknown theme {theme!r}" + _hint(theme, THEMES)))
        theme = DEFAULTS["theme"]
    colors = cfg.get("colors") if isinstance(cfg.get("colors"), dict) else {}
    for key, val in colors.items():
        if key not in ("reset", "bold") and parse_color(val) is None:
            problems.append(problem("error", f"colors.{key}", f"not a colour: {val!r} (use #rrggbb, an "
                                                             f"xterm index, or 38;5;N)"))
    pal = palette(theme, colors)
    style = _choice(cfg, "style", STYLES, problems, "auto")
    icons = _choice(cfg, "icons", ICONSETS, problems, "auto")
    color = _choice(cfg, "color", MODES, problems, "auto")

    bar = dict(cfg["bar"])
    if bar.get("style") not in BAR_STYLES and bar.get("style") not in BAR_ALIASES:
        problems.append(problem("error", "bar.style", f"unknown bar style {bar.get('style')!r}; one of "
                                                      f"{', '.join(BAR_STYLES)}"))
        bar["style"] = "smooth"
    for m in check_fill(bar.get("fill"), pal):
        problems.append(problem("error", "bar.fill", m))
        bar["fill"] = "level"
    if bar.get("track") not in pal and parse_color(bar.get("track")) is None:
        problems.append(problem("error", "bar.track", f"unknown colour {bar.get('track')!r}"))
        bar["track"] = "subtle"
    for key in ("cap_left", "cap_right"):
        if not isinstance(bar.get(key), str) or len(bar.get(key)) > 1:
            problems.append(problem("error", f"bar.{key}", "must be a single glyph or empty"))
            bar[key] = ""

    preset_name = cfg.get("preset")
    preset = load_preset(preset_name)
    if preset is None:
        problems.append(problem("error", "preset", f"unknown preset {preset_name!r}; using 'classic'"
                                + _hint(preset_name, list_presets())))
        preset_name, preset = "classic", load_preset("classic") or {}

    lines_raw = raw.get("line", [])
    if not isinstance(lines_raw, list):
        problems.append(problem("error", "line", "must be an array of tables ([[line]])"))
        lines_raw = []
    declared = bool(lines_raw)
    if not lines_raw:
        lines_raw = preset.get("line") or []
    tables = deep_merge(preset.get("segment") or {}, cfg.get("segment") if isinstance(cfg.get("segment"), dict) else {})

    quest = dict(cfg["quest"])
    if quest.get("placement") not in PLACEMENTS:
        problems.append(problem("error", "quest.placement", f"one of {', '.join(PLACEMENTS)}"))
        quest["placement"] = "line"
    if quest.get("avatar") not in ("auto", "on", "off", True, False):
        problems.append(problem("error", "quest.avatar", "one of auto, on, off"))
        quest["avatar"] = "auto"

    game = bool(quest.get("enabled")) and quest["placement"] == "game"
    if game:
        rows = quest.get("game_rows")
        if not isinstance(rows, int) or isinstance(rows, bool) or not 1 <= rows <= 8:
            problems.append(problem("error", "quest.game_rows", "a whole number from 1 to 8"))
            quest["game_rows"] = rows = 3
        hud = quest.get("game_hud")
        if not isinstance(hud, list) or not all(isinstance(n, str) for n in hud):
            problems.append(problem("error", "quest.game_hud", "a list of segment names"))
            quest["game_hud"] = hud = list(DEFAULTS["quest"]["game_hud"])
        width = quest.get("game_hud_width")
        if width != "auto" and (not isinstance(width, int) or isinstance(width, bool) or not 0 <= width <= 60):
            problems.append(problem("error", "quest.game_hud_width", '"auto" or a whole number from 0 to 60'))
            quest["game_hud_width"] = "auto"
        if len(hud) > rows:
            problems.append(problem("warning", "quest.game_hud", f"only {rows} fit beside {rows} rows of scene"))
        # The game is the whole bar: the ticker, then the scene with a gauge on each row.
        lines_raw = [{"left": list(GAME_TICKER["left"]), "right": list(GAME_TICKER["right"]), "_auto": True}]
        lines_raw += [{"right": [hud[i]] if i < len(hud) else [], "_scene": i} for i in range(rows)]
        for n in hud[:rows]:
            # The gauges always wear the compact look (a format written for the full bar would
            # crowd the scene); every other option of yours still applies.
            if isinstance(tables.get(n, {}), dict):
                tables[n] = {**tables.get(n, {}), **GAME_HUD_LOOK}
        for n, look in GAME_BARLESS.items():
            if isinstance(tables.get(n, {}), dict):
                tables[n] = {**tables.get(n, {}), **look}

    lines_raw = [dict(ln) if isinstance(ln, dict) else ln for ln in lines_raw]
    placed = {n for ln in lines_raw if isinstance(ln, dict) for side in ("left", "right")
              for n in (ln.get(side) or []) if isinstance(n, str)}
    placed_types = {(tables.get(n) or {}).get("type", n) if isinstance(tables.get(n), dict) else n for n in placed}
    if quest.get("enabled") and not game:
        has_quest = any(t in catalog.CATALOG and catalog.CATALOG[t] == "quest" and t not in ("avatar",)
                        for t in placed_types)
        if quest["placement"] == "line" and not has_quest:
            lines_raw.append({"left": list(QUEST_LINE["left"]), "right": list(QUEST_LINE["right"]), "_auto": True})
        elif quest["placement"] == "inline" and not has_quest and lines_raw and isinstance(lines_raw[0], dict):
            first = dict(lines_raw[0])
            first["right"] = ["quest"] + list(first.get("right") or [])
            lines_raw[0] = first

    seen = set()
    lines = []
    for idx, ln in enumerate(lines_raw):
        where = f"line[{idx}]"
        if not isinstance(ln, dict):
            problems.append(problem("error", where, "must be a table"))
            continue
        for key in ln:
            if key not in ("left", "right", "gap", "_auto", "_scene"):
                problems.append(problem("error", f"{where}.{key}", "unknown key (left, right, gap)"))
        groups = []
        for side in ("left", "right"):
            names = ln.get(side, [])
            if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
                problems.append(problem("error", f"{where}.{side}", "must be a list of segment names"))
                names = []
            specs = []
            for n in names:
                spec = resolve_segment(n, tables, problems, pal, seen, f"{where}.{side}")
                if spec is not None:
                    specs.append(spec)
            groups.append(specs)
        gap = ln.get("gap", cfg["layout"].get("gap", 2))
        if not isinstance(gap, int) or isinstance(gap, bool) or gap < 0:
            problems.append(problem("error", f"{where}.gap", "must be a non-negative integer"))
            gap = 2
        if "_scene" in ln:
            lines.append({"left": [], "right": groups[1], "gap": 0, "auto": True, "scene": ln["_scene"]})
        elif groups[0] or groups[1]:
            lines.append({"left": groups[0], "right": groups[1], "gap": gap, "auto": bool(ln.get("_auto"))})
        else:
            problems.append(problem("warning", where, "empty line"))
    if len(lines) > 4 and not game:
        problems.append(problem("warning", "line", f"{len(lines)} lines; the bar takes that many rows "
                                                   f"from the conversation"))

    for n, table in tables.items():
        if n in seen or not isinstance(table, dict):
            continue
        type_ = table.get("type", n)
        if type_ in catalog.CATALOG:
            resolve_segment(n, tables, problems, pal, set(), f"segment.{n}")
            if n in (cfg.get("segment") or {}) and not game and \
                    not (catalog.CATALOG.get(type_) == "quest" and not quest.get("enabled")):
                problems.append(problem("warning", f"segment.{n}", "configured but not placed on any line"))
        else:
            problems.append(problem("error", f"segment.{n}", f"unknown segment{_hint(type_, catalog.CATALOG)}"))

    wide = cfg["layout"].get("wide_glyphs") or []
    if not isinstance(wide, list):
        problems.append(problem("error", "layout.wide_glyphs", "must be a list of glyphs"))
        wide = []

    return {
        "path": path, "problems": problems, "preset": preset_name, "declared": declared,
        "theme": theme, "style": style, "icons": icons, "color": color, "palette": pal,
        "layout": dict(cfg["layout"], wide_glyphs=[g for g in wide if isinstance(g, str)]),
        "bar": bar, "thresholds": dict(cfg["thresholds"]), "git": dict(cfg["git"]),
        "glyphs": dict(cfg["glyphs"]) if isinstance(cfg.get("glyphs"), dict) else {},
        "quest": quest, "lines": lines,
    }
