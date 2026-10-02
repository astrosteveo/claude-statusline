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
               "right": ["quest_streak", "quest_gold", "quest_settings"]}
# How a gauge (a segment with a label and a percentage) looks beside the game scene:
# compact at first, and with a small bar, the pace and the reset when the column is wide.
GAME_HUD_LOOK = {"width": 0, "format": "[<subtext>{label}</subtext> ][<level><bold>{pct}%</bold></level>]"}
GAME_HUD_RICH = {"width": 8, "format": "[<subtext>{label:<3}</subtext> ][{bar} ]<level><bold>{pct:>3}%</bold></level>"
                                       "[ <muted>{detail}</muted>][ <pacecolor>{pace}</pacecolor>]"
                                       "[ <muted>{reset}[·{clock}]</muted>]"}
# The scene is the picture in game mode, so the ticker keeps no bar but the hero's XP.
GAME_BARLESS = {"quest_raid": {"width": 0}}
# Live activity gets a line of its own unless you place its segments yourself.
ACTIVITY_SEGMENTS = ["turn", "tools", "agents", "tasks", "mode"]
ACTIVITY_LINE = {"left": ["turn", "tools", "agents", "tasks"], "right": ["mode"]}
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


PRESET_SECTIONS = ("quest", "bar", "activity", "layout", "thresholds", "panels")


def preset_sections(preset) -> dict:
    """The settings sections a preset carries besides its lines and segments."""
    return {k: v for k, v in (preset or {}).items() if k in PRESET_SECTIONS and isinstance(v, dict)}


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
    if type_ == "command":
        if not (opts.get("command") or "").strip():
            problems.append(problem("error", f"segment.{name}.command", "a command segment needs a command"))
        if opts["every"] < 2:
            problems.append(problem("warning", f"segment.{name}.every", "at least 2 seconds; 2 is used"))
        if not 0 < opts["timeout"] <= 10:
            problems.append(problem("warning", f"segment.{name}.timeout", "from 0 to 10 seconds; clamped"))
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
            "tone": tone, "own_icon": own_icon, "bare": seg.bare, "quest": seg.quest,
            "elastic": seg.elastic}


def type_of(name, tables):
    table = tables.get(name)
    return table.get("type", name) if isinstance(table, dict) else name


def game_details(lines, tables, gauges):
    """The session details game mode puts on its top row when `game_details` is
    "auto": the model first, then every segment of `lines` in order, less quest
    segments and whatever the gauges beside the scene already show. As
    (name, where it came from) pairs."""
    shown = {type_of(g, tables) for g in gauges}
    found = []
    for i, ln in enumerate(lines):
        if not isinstance(ln, dict):
            continue
        for side in ("left", "right"):
            names = ln.get(side)
            for n in names if isinstance(names, list) else []:
                if isinstance(n, str) and n not in (f[0] for f in found):
                    found.append((n, f"line[{i}].{side}"))
    model = next((f for f in found if type_of(f[0], tables) == "model"), ("model", "quest.game_details"))
    out = [model]
    for n, where in found:
        t = type_of(n, tables)
        if t == "model" or t in shown or catalog.CATALOG.get(t) == "quest":
            continue
        out.append((n, where))
    return out


def _gauge_looks(name, tables):
    """(compact, rich) overrides for a segment beside the scene, or ({}, {}) for
    one that is not a gauge: those keep their own format."""
    seg = catalog.get(type_of(name, tables))
    if seg is None or not {"label", "pct"} <= set(seg.fields_doc) or "width" not in seg.options:
        return {}, {}
    rich = dict(GAME_HUD_RICH)
    fields = set(seg.fields_doc)
    for part, field in (("[ <muted>{detail}</muted>]", "detail"), ("[ <pacecolor>{pace}</pacecolor>]", "pace"),
                        ("[ <muted>{reset}[·{clock}]</muted>]", "reset")):
        if field not in fields:
            rich["format"] = rich["format"].replace(part, "")
    return GAME_HUD_LOOK, rich


def _barless(names, tables):
    """A copy of `tables` in which the bar segments among `names` draw no bar."""
    out = dict(tables)
    for n in names:
        table = tables.get(n, {})
        seg = catalog.get(type_of(n, tables))
        if isinstance(table, dict) and seg is not None and "width" in seg.options and not seg.quest:
            out[n] = {**table, "width": 0}
    return out


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
        if section in ("layout", "bar", "thresholds", "git", "quest", "activity", "commands"):
            for key, val in body.items():
                where = f"{section}.{key}"
                if where in RETIRED:
                    problems.append(problem("warning", where, f"no longer used: {RETIRED[where]}"))
                elif key not in default:
                    problems.append(problem("error", where, "unknown key" + _hint(key, default)))
                elif where in ("quest.avatar", "quest.game_hud_width", "quest.game_details", "quest.game_news"):   # checked below
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
    # A preset may set sections too ([quest], [bar]…): they sit between the defaults and your own keys.
    early = load_preset(safe.get("preset", DEFAULTS["preset"])) or {}
    cfg = deep_merge(deep_merge(DEFAULTS, preset_sections(early)), safe)

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

    activity = dict(cfg["activity"])
    if activity.get("placement") not in ("auto", "manual"):
        problems.append(problem("error", "activity.placement", "one of auto, manual"))
        activity["placement"] = "auto"
    if activity.get("enabled") and activity["placement"] == "auto" and lines_raw and \
            isinstance(lines_raw[-1], dict):
        placed_now = {n for ln in lines_raw if isinstance(ln, dict) for side in ("left", "right")
                      for n in (ln.get(side) or []) if isinstance(n, str)}
        if not {type_of(n, tables) for n in placed_now} & set(ACTIVITY_SEGMENTS):
            lines_raw = list(lines_raw) + [{"left": list(ACTIVITY_LINE["left"]),
                                           "right": list(ACTIVITY_LINE["right"]), "_auto": True}]

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
        news = quest.get("game_news", "auto")
        if news not in ("auto", "off") and (not isinstance(news, int) or isinstance(news, bool) or
                                            not 0 <= news <= 80):
            problems.append(problem("error", "quest.game_news", '"auto", "off" or a whole number from 0 to 80'))
            quest["game_news"] = "auto"
        if len(hud) > rows:
            problems.append(problem("warning", "quest.game_hud", f"only {rows} fit beside {rows} rows of scene"))
        details = quest.get("game_details", "auto")
        if details != "auto" and not (isinstance(details, list) and all(isinstance(n, str) for n in details)):
            problems.append(problem("error", "quest.game_details", '"auto" or a list of segment names'))
            quest["game_details"] = details = "auto"
        # Your own lines (or the preset's) give way to the game, but they name the session
        # details that share its top row.
        named = game_details(lines_raw, tables, hud[:rows]) if details == "auto" else \
            [(n, "quest.game_details") for n in details]
        dtables = _barless([n for n, _ in named], tables)
        # The gauges wear the gauge looks (a format written for the full bar would crowd the
        # scene); every other option of yours still applies.
        compact, rich = dict(tables), dict(tables)
        for n in hud[:rows]:
            if isinstance(tables.get(n, {}), dict):
                small, big = _gauge_looks(n, tables)
                compact[n] = {**tables.get(n, {}), **small}
                rich[n] = {**tables.get(n, {}), **big}
        for n, look in GAME_BARLESS.items():
            if isinstance(tables.get(n, {}), dict):
                tables[n] = {**tables.get(n, {}), **look}
        # The game is the whole bar: the ticker and the details, then the scene with a gauge on each row.
        lines_raw = [{"left": list(GAME_TICKER["left"]), "right": list(GAME_TICKER["right"]), "_auto": True,
                      "_details": named, "_dtables": dtables}]
        lines_raw += [{"right": [hud[i]] if i < len(hud) else [], "_scene": i, "_tables": compact, "_rich": rich}
                      for i in range(rows)]

    panels = dict(cfg["panels"])
    show = panels.get("show")
    if not isinstance(show, list) or not all(isinstance(n, str) for n in show):
        problems.append(problem("error", "panels.show", "a list of panel names"))
        show = []
    from .panels import PANELS
    for n in show:
        if n not in PANELS:
            problems.append(problem("error", "panels.show", f"unknown panel {n!r}; one of "
                                                            f"{', '.join(PANELS)}" + _hint(n, PANELS)))
    panels["show"] = show = [n for n in dict.fromkeys(show) if n in PANELS]
    prows = panels.get("rows")
    if not isinstance(prows, int) or isinstance(prows, bool) or not 1 <= prows <= 16:
        problems.append(problem("error", "panels.rows", "a whole number from 1 to 16"))
        panels["rows"] = prows = 6
    for key, low in (("cache_ttl", 0), ("commits", 1)):
        v = panels.get(key)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < low:
            problems.append(problem("error", f"panels.{key}", f"a number from {low} up"))
            panels[key] = DEFAULTS["panels"][key]
    panels["commits"] = int(panels["commits"])
    if show and game:
        problems.append(problem("warning", "panels.show", "game mode takes the whole bar; the panels are hidden"))

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
    if show and not game:
        # The panels come last, under your lines and the activity and quest lines.
        lines_raw += [{"_panel": i} for i in range(prows)]

    seen = set()
    lines = []
    for idx, ln in enumerate(lines_raw):
        where = f"line[{idx}]"
        if not isinstance(ln, dict):
            problems.append(problem("error", where, "must be a table"))
            continue
        for key in ln:
            if key not in ("left", "right", "gap", "_auto", "_scene", "_details", "_dtables", "_tables", "_rich",
                           "_panel"):
                problems.append(problem("error", f"{where}.{key}", "unknown key (left, right, gap)"))
        own = ln.get("_tables", tables)
        groups = []
        for side in ("left", "right"):
            names = ln.get(side, [])
            if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
                problems.append(problem("error", f"{where}.{side}", "must be a list of segment names"))
                names = []
            specs = []
            for n in names:
                spec = resolve_segment(n, own, problems, pal, seen, f"{where}.{side}")
                if spec is not None:
                    specs.append(spec)
            groups.append(specs)
        gap = ln.get("gap", cfg["layout"].get("gap", 2))
        if not isinstance(gap, int) or isinstance(gap, bool) or gap < 0:
            problems.append(problem("error", f"{where}.gap", "must be a non-negative integer"))
            gap = 2
        if "_panel" in ln:
            lines.append({"left": [], "right": [], "gap": 0, "auto": True, "panel": ln["_panel"]})
        elif "_scene" in ln:
            rich = [s for s in (resolve_segment(n, ln["_rich"], [], pal, set(), where) for n in ln["right"]) if s]
            lines.append({"left": [], "right": groups[1], "rich": rich, "gap": 0, "auto": True,
                          "scene": ln["_scene"]})
        elif "_details" in ln:
            details = []
            for n, whence in ln["_details"]:
                spec = resolve_segment(n, ln["_dtables"], problems, pal, seen, whence)
                if spec is None:
                    continue
                if spec["quest"]:
                    problems.append(problem("warning", whence, f"{n!r} is on the quest ticker already"))
                    continue
                details.append(spec)
            lines.append({"left": groups[0], "right": groups[1], "gap": gap, "auto": True, "details": details})
        elif groups[0] or groups[1]:
            lines.append({"left": groups[0], "right": groups[1], "gap": gap, "auto": bool(ln.get("_auto"))})
        else:
            problems.append(problem("warning", where, "empty line"))
    own_lines = [ln for ln in lines if "panel" not in ln]
    if len(own_lines) > 4 and not game:
        problems.append(problem("warning", "line", f"{len(own_lines)} lines; the bar takes that many rows "
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
        "quest": quest, "activity": activity, "commands": dict(cfg["commands"]), "panels": panels,
        "lines": lines,
    }
