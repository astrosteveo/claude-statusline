"""Subcommands. Everything here is off the render path, so it can take its time."""
from __future__ import annotations

import os
import sys
import time

from . import __version__

HELP = """\
claude-statusline {version} — a fast, themeable status line for Claude Code, with Claude Quest

  statusline.py                   print the bar for the payload on stdin (what Claude Code runs)
  statusline.py configure         the interactive configurator (also: run it with no arguments in a terminal)

look and try
  preview [options]               the bar at several widths      --width 80,120,160 --sample busy|quiet|hot|live
  themes | styles | icons | bars  galleries of every choice, drawn with your layout
  segments [name]                 the catalog: every segment, its options, fields and colours
  presets                         the ready-made layouts
      preview/render/themes/styles also take --theme T --style S --icons I --preset P --config PATH --plain

change
  set <key> <value>               e.g. set theme nord · set style capsules · set segment.dir.mode base
  get <key> | unset <key>         read or remove one setting
  activity enable | disable       live activity on or off (background hooks; tools, agents, turn…)
  quest enable | disable | status Claude Quest on or off (hooks, the /quest command, the quest line)
  quest <command>                 play: sheet, bag, equip, use, shop, quests, boss, pet… (quest help)

check
  validate [path]                 every problem in a config, with suggestions; exit 1 on errors
  doctor                          what is installed, detected and in force
  ruler                           calibrate layout.right_margin
  bench                           how long a refresh takes
  migrate [path] [--write]        bring an older config up to date
  render [--width W] [--sample S] one rendering of stdin or a sample
  version
"""


# --- helpers -------------------------------------------------------------------
def _tty():
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _opts(argv, flags=(), values=()):
    """A tiny parser: (positional, {flag: True}, {name: value})."""
    pos, fl, vals = [], {}, {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            name, eq, val = a[2:].partition("=")
            if name in values:
                if not eq:
                    i += 1
                    val = argv[i] if i < len(argv) else ""
                vals[name] = val
            elif name in flags:
                fl[name] = True
            else:
                raise SystemExit(f"unknown option --{name}")
        else:
            pos.append(a)
        i += 1
    return pos, fl, vals


LOOK_VALUES = ("theme", "style", "icons", "preset", "config", "sample", "width", "now", "color")


def _raw_config(vals):
    from .config import config_path, read_toml
    path = os.path.expanduser(vals["config"]) if vals.get("config") else config_path()
    raw, err = read_toml(path)
    raw = dict(raw)
    for k in ("theme", "style", "icons", "color"):
        if vals.get(k):
            raw[k] = vals[k]
    if vals.get("preset"):
        raw["preset"] = vals["preset"]
        raw.pop("line", None)
    return raw, path, err


def _compiled(vals):
    from .layout import compile_config
    raw, path, err = _raw_config(vals)
    return compile_config(raw, path=path, read_error=err)


def _mode(plain):
    if plain:
        return "none"
    from .color import detect_mode
    return detect_mode()


def _render_lines(comp, data, cols, now, env=None):
    from . import width
    from .context import Context
    from .render import render_lines
    width.WIDE.update(comp["layout"].get("wide_glyphs") or ())
    env = dict(os.environ if env is None else env)
    ctx = Context(data, comp, cols=cols, now=now, env=env, sync_git=True)
    return ctx, render_lines(data, comp, ctx=ctx)


def _widths(text, default):
    out = []
    for tok in str(text or "").split(","):
        tok = tok.strip()
        if tok:
            out.append(max(20, int(tok)))
    return out or default


def _term_cols(default=120):
    try:
        return int(os.environ.get("COLUMNS") or 0) or os.get_terminal_size().columns
    except (OSError, ValueError):
        return default


def _paint(text, role, mode, comp=None, bold=False):
    """A string in a theme colour, for command output."""
    from .text import BOLD, Text
    from .themes import palette
    pal = comp["palette"] if comp else palette("claude")
    return Text.of(text, (pal.get(role), None, BOLD if bold else 0, None)).ansi(mode)


def _sample(vals, now):
    from . import samples
    return samples.load(vals.get("sample") or "busy", now)


# --- commands ------------------------------------------------------------------
def cmd_preview(argv):
    _, fl, vals = _opts(argv, ("plain", "json"), LOOK_VALUES)
    comp = _compiled(vals)
    now = float(vals["now"]) if vals.get("now") else time.time()
    try:
        data = _sample(vals, now)
    except Exception as exc:
        print(f"cannot load sample {vals.get('sample')!r}: {exc}", file=sys.stderr)
        return 2
    cols = _term_cols()
    widths = _widths(vals.get("width"), sorted({80, 120, max(80, cols)}))
    mode = _mode(fl.get("plain"))
    report = []
    from .fit import DETAIL_LEVELS, LEVELS
    for w in widths:
        ctx, fits = _render_lines(comp, data, w, now)
        report.append((w, ctx, fits))
    if fl.get("json"):
        import json

        def line(f):
            out = {"text": f.text.ansi(ctx.mode), "plain": f.text.plain(), "width": f.width,
                   "level": LEVELS[f.level], "dropped": f.dropped, "overflow": f.overflow}
            if f.grown:
                out["grown"] = f.grown
            if f.details is not None:
                out["details"] = {"levels": {n: DETAIL_LEVELS[lv] for n, lv in f.details.levels.items()},
                                  "dropped": f.details.dropped}
            return out
        print(json.dumps({"problems": [list(p) for p in comp["problems"]], "widths": [
            {"columns": w, "usable": ctx.avail, "style": ctx.style, "icons": ctx.iconset,
             "lines": [None if f is None else line(f) for f in fits]} for w, ctx, fits in report]},
            indent=2, ensure_ascii=False))
        return 0
    head = (f"preset {comp['preset']} · theme {comp['theme']} · style {report[0][1].style} · "
            f"icons {report[0][1].iconset} · sample {vals.get('sample') or 'busy'}")
    print(_paint(head, "subtext", mode, comp))
    for p in comp["problems"]:
        print(_paint(f"  {p[0]}: {p[1]}: {p[2]}", "yellow" if p[0] == "warning" else "red", mode, comp))
    for w, ctx, fits in report:
        label = f" {w} columns, {ctx.avail} usable "
        print()
        print(_paint(("─" * 2 + label + "─" * max(0, ctx.avail - 2 - len(label)))[:ctx.avail] + "┤", "subtle", mode, comp))
        notes = []
        for i, f in enumerate(fits, 1):
            if f is None:
                notes.append(f"line {i}: empty, left out")
                continue
            print(f.text.ansi(mode) if mode != "none" else f.text.plain())
            notes += fit_notes(i, f)
        for n in notes:
            print(_paint(f"  ↳ {n}", "muted", mode, comp))
    return 0


def fit_notes(i, f):
    """What gave way on one fitted line, for `preview`."""
    from .fit import DETAIL_LEVELS, LEVELS
    game = f.details is not None
    bits = []
    if f.level:
        bits.append(f"{'game at ' if game else 'level '}{LEVELS[f.level]}")
    if f.dropped:
        bits.append(("game dropped " if game else "dropped ") + ", ".join(f.dropped))
    for name, cols in f.grown.items():
        bits.append(f"{name} took {cols} spare columns")
    if f.overflow:
        bits.append(f"OVERFLOWS by {f.overflow}")
    out = [f"line {i}: " + "; ".join(bits)] if bits else []
    if game:
        d = f.details
        lean = [f"{n} at {DETAIL_LEVELS[lv]}" for n, lv in d.levels.items() if lv]
        dbits = ([", ".join(lean)] if lean else []) + (["dropped " + ", ".join(d.dropped)] if d.dropped else [])
        if not d.levels and not d.dropped:
            dbits = ["none to show"]
        out.append(f"line {i} details: " + ("; ".join(dbits) if dbits else "all in full"))
    return out


def cmd_render(argv):
    _, fl, vals = _opts(argv, ("plain",), LOOK_VALUES)
    comp = _compiled(vals)
    now = float(vals["now"]) if vals.get("now") else time.time()
    if vals.get("sample"):
        data = _sample(vals, now)
    else:
        from .fastjson import loads
        try:
            data = loads(sys.stdin.read() or "{}")
        except ValueError:
            data = {}
    cols = int(vals["width"]) if vals.get("width") else None
    ctx, fits = _render_lines(comp, data if isinstance(data, dict) else {}, cols, now)
    mode = "none" if fl.get("plain") else ctx.mode
    print("\n".join((f.text.ansi(mode) if mode != "none" else f.text.plain()) for f in fits if f))
    return 0


def _gallery(argv, key, choices, describe):
    _, fl, vals = _opts(argv, ("plain",), LOOK_VALUES)
    now = float(vals["now"]) if vals.get("now") else time.time()
    data = _sample(vals, now)
    cols = int(vals["width"]) if vals.get("width") else _term_cols()
    mode = _mode(fl.get("plain"))
    base = _compiled(vals)
    current = base.get(key)
    for choice in choices:
        comp = _compiled(dict(vals, **{key: choice}))
        ctx, fits = _render_lines(comp, data, cols, now)
        mark = "●" if choice == current else " "
        print(_paint(f"{mark} {choice}", "accent", mode, comp, bold=True) + "  " +
              _paint(describe(choice), "muted", mode, comp))
        for f in fits:
            if f is not None:
                print(f.text.ansi(mode) if mode != "none" else f.text.plain())
        print()
    print(_paint(f"statusline.py set {key} <name>   to choose one", "subtext", mode, base))
    return 0


def cmd_themes(argv):
    from .themes import THEMES, describe
    if "--list" in argv:
        for name in THEMES:
            print(f"{name:<18}{describe(name)}")
        return 0
    return _gallery(argv, "theme", list(THEMES), describe)


def cmd_styles(argv):
    from .decor import LOOKS
    return _gallery(argv, "style", list(LOOKS), lambda s: LOOKS[s])


def cmd_icons(argv):
    from .icons import ICONS, SETS
    mode = _mode("--plain" in argv)
    comp = _compiled({})
    names = [n for n in ICONS["unicode"] if n not in ("text", "heartbeat")]
    print(_paint(f"{'segment':<16}" + "".join(f"{s:<9}" for s in SETS[:3]), "subtext", mode, comp, bold=True))
    for n in names:
        print(f"{n:<16}" + "".join(f"{ICONS[s].get(n, '') or '·':<9}" for s in SETS[:3]))
    print(_paint("\nstatusline.py set icons nerd|unicode|emoji|none   ·   per segment: "
                 "set segment.git.icon \"\"", "subtext", mode, comp))
    return 0


def cmd_bars(argv):
    _, fl, vals = _opts(argv, ("plain",), ("width", "theme"))
    from .bar import STYLES, make_bar
    comp = _compiled(vals)
    mode = _mode(fl.get("plain"))
    width = int(vals["width"]) if vals.get("width") else comp["bar"]["width"]
    pcts = (3, 28, 50, 62, 81, 97)
    print(_paint(f"bar styles at width {width}; columns are " + ", ".join(f"{p}%" for p in pcts), "subtext", mode, comp))
    for name, spec in STYLES.items():
        print()
        print(_paint(f"{name:<9}", "accent", mode, comp, bold=True) + _paint(spec["doc"], "muted", mode, comp))
        for fill in ("level", "gradient", "cyan,purple"):
            row = []
            for p in pcts:
                t = make_bar(p, width, pal=comp["palette"], thresholds=comp["thresholds"], style=name, fill=fill,
                             track=comp["bar"]["track"], mono=mode == "none")
                row.append(t.ansi(mode) if mode != "none" else t.plain())
            print(f"  {fill:<12}" + "  ".join(row))
    print(_paint("\nset bar.style <name> · set bar.fill level|gradient|tone|<role>|<role,role> · "
                 "set bar.width 10", "subtext", mode, comp))
    return 0


def segment_info(seg):
    return {"name": seg.name, "doc": seg.doc, "priority": seg.priority, "tone": seg.tone, "format": seg.format,
            "quest": seg.quest,
            "options": {k: {"type": o.type.__name__, "default": o.default, "doc": o.doc,
                            **({"choices": list(o.choices)} if o.choices else {})}
                        for k, o in seg.all_options().items() if k not in ("format", "priority", "icon", "color")},
            "fields": dict(seg.fields_doc), "colors": dict(seg.colors_doc)}


def catalog_markdown():
    from .segments import load_all
    from .tomlw import value
    reg = load_all()
    segs = sorted(reg.values(), key=lambda s: (s.quest, -s.priority, s.name))
    segs = [s for s in segs if s.name != "pet"]
    out = ["# Segment catalog", "",
           "Generated by `statusline.py segments --markdown`; regenerate with `make catalog`.",
           "Every segment also takes `format` (its body template), `priority`, `icon` (\"\" hides it) "
           "and `color` (the theme role its icon and chip wear).", "",
           "| segment | priority | what it shows |", "|---------|----------|---------------|"]
    for s in segs:
        out.append(f"| `{s.name}` | {s.priority} | {s.doc}{' (Claude Quest)' if s.quest else ''} |")
    for s in segs:
        info = segment_info(s)
        out += ["", f"## {s.name}", "", s.doc, "", f"Tone: `{s.tone}`. Default format: `{s.format}`"]
        if info["options"]:
            out += ["", "| option | type | default | meaning |", "|--------|------|---------|---------|"]
            for k, o in info["options"].items():
                extra = f" One of: {', '.join(o['choices'])}." if o.get("choices") else ""
                out.append(f"| `{k}` | {o['type']} | `{value(o['default'])}` | {o['doc']}{extra} |")
        out += ["", "| field | holds |", "|-------|-------|"]
        for k, doc in s.fields_doc.items():
            out.append(f"| `{{{k}}}` | {doc} |")
        if s.colors_doc:
            out += ["", "| colour | when |", "|--------|------|"]
            for k, doc in s.colors_doc.items():
                out.append(f"| `<{k}>` | {doc} |")
    return "\n".join(out) + "\n"


def cmd_segments(argv):
    pos, fl, _ = _opts(argv, ("json", "markdown"))
    from .segments import load_all
    reg = load_all()
    if fl.get("markdown"):
        sys.stdout.write(catalog_markdown())
        return 0
    import json
    if pos:
        seg = reg.get(pos[0])
        if seg is None:
            from .layout import closest
            hint = closest(pos[0], reg)
            print(f"unknown segment {pos[0]!r}" + (f"; did you mean {hint!r}?" if hint else ""))
            return 1
        info = segment_info(seg)
        if fl.get("json"):
            print(json.dumps(info, indent=2, ensure_ascii=False))
            return 0
        from .tomlw import value
        out = [f"{seg.name}  (priority {seg.priority}, tone {seg.tone}{', Claude Quest' if seg.quest else ''})",
               f"  {seg.doc}", "", "  format", f"    {seg.format}"]
        if info["options"]:
            out += ["", "  options"]
            for k, o in info["options"].items():
                out.append(f"    {k:<18}{o['type']:<6}default {value(o['default'])}")
                out.append(f"    {'':<18}{o['doc']}" + (f" ({', '.join(o['choices'])})" if o.get("choices") else ""))
        out += ["", "  fields"] + [f"    {{{k}}}".ljust(22) + d for k, d in seg.fields_doc.items()]
        if seg.colors_doc:
            out += ["", "  colours"] + [f"    <{k}>".ljust(22) + d for k, d in seg.colors_doc.items()]
        out += ["", f"  set segment.{seg.name}.<option> <value>"]
        print("\n".join(out))
        return 0
    segs = sorted((s for s in reg.values() if s.name != "pet"), key=lambda s: (s.quest, -s.priority))
    if fl.get("json"):
        print(json.dumps([segment_info(s) for s in segs], indent=2, ensure_ascii=False))
        return 0
    w = max(len(s.name) for s in segs)
    print(f"{'segment'.ljust(w)}  prio  what it shows")
    quest_started = False
    for s in segs:
        if s.quest and not quest_started:
            print(f"\n{'Claude Quest'.ljust(w)}  (shown when [quest] enabled = true)")
            quest_started = True
        print(f"{s.name.ljust(w)}  {s.priority:>4}  {s.doc}")
    print("\nstatusline.py segments <name>   for options, fields and colours")
    return 0


def cmd_presets(argv):
    from .layout import list_presets, load_preset, preset_summary
    for name in list_presets():
        raw = load_preset(name) or {}
        print(preset_summary(name))
        for ln in raw.get("line", []):
            right = f"   ⇥ {', '.join(ln.get('right', []))}" if ln.get("right") else ""
            print(f"    {', '.join(ln.get('left', []))}{right}")
        print()
    print("statusline.py set preset <name>   (a [[line]] in your config overrides the preset's lines)")
    return 0


def cmd_validate(argv):
    pos, fl, _ = _opts(argv, ("json",))
    from .config import config_path, read_toml
    from .layout import compile_config
    path = os.path.expanduser(pos[0]) if pos else config_path()
    if not path:
        print("no config file; the defaults are in force (statusline.py configure to make one)")
        return 0
    raw, err = read_toml(path)
    comp = compile_config(raw, path=path, read_error=err)
    errors = [p for p in comp["problems"] if p[0] == "error"]
    if fl.get("json"):
        import json
        print(json.dumps({"path": path, "ok": not errors, "problems": [
            {"level": p[0], "path": p[1], "message": p[2]} for p in comp["problems"]],
            "lines": [[s["name"] for s in ln["left"]] + ["⇥"] + [s["name"] for s in ln["right"]]
                      for ln in comp["lines"]],
            **({"game_details": [s["name"] for ln in comp["lines"] if ln.get("details") is not None
                                 for s in ln["details"]]} if any(ln.get("details") is not None
                                                                 for ln in comp["lines"]) else {})},
            indent=2, ensure_ascii=False))
        return 1 if errors else 0
    print(path)
    for p in comp["problems"]:
        print(f"  {p[0]}: {p[1]}: {p[2]}" if p[1] else f"  {p[0]}: {p[2]}")
    n = sum(len(ln["left"]) + len(ln["right"]) + len(ln.get("details") or []) for ln in comp["lines"])
    warn = len(comp["problems"]) - len(errors)
    print(f"  {'ok' if not errors else f'{len(errors)} error(s)'}: {len(comp['lines'])} line(s), {n} segment(s)"
          + (f", {warn} warning(s)" if warn else ""))
    return 1 if errors else 0


def describe_lines(comp):
    """The lines in force, as one row of text; game mode's by what they hold."""
    lines = comp["lines"]
    top = next((ln for ln in lines if ln.get("details") is not None), None)
    if top is None:
        return " / ".join(", ".join(s["name"] for s in ln["left"] + ln["right"]) for ln in lines)
    gauges = [s["name"] for ln in lines if ln.get("scene") is not None for s in ln["right"]]
    rows = sum(1 for ln in lines if ln.get("scene") is not None)
    details = ", ".join(s["name"] for s in top["details"]) or "none"
    how = "auto" if comp["quest"].get("game_details", "auto") == "auto" else "set"
    return (f"game mode: the quest ticker with details ({how}) {details}; "
            f"{rows} rows of scene with gauges {', '.join(gauges) or 'none'}")


def describe_command(spec, comp):
    from . import commands
    opts = spec["opts"]
    if not commands.enabled(comp):
        return "off ([commands] enabled = false or CLAUDE_STATUSLINE_NO_COMMANDS)"
    entry = commands.read(commands.key_of(opts.get("command") or "", os.getcwd(), opts.get("per")))
    if entry is None:
        return f"not run yet here · every {opts['every']:g}s, timeout {opts['timeout']:g}s"
    status = "ok" if entry.get("exit") == 0 else f"exit {entry.get('exit')}" + (
        f" ({entry['error']})" if entry.get("error") else "")
    return (f"ran {time.time() - entry['at']:.0f}s ago in {entry.get('took', 0):.2f}s, {status} · "
            f"every {opts['every']:g}s, timeout {opts['timeout']:g}s")


def cmd_doctor(argv):
    from . import settings as st
    from .config import CONFIG_SEARCH, compiled, config_path, runtime_dir
    from .context import nerd_terminal, resolve_look
    comp = compiled()
    style, icons, mode = resolve_look(comp, os.environ)
    path = config_path()
    try:
        cfg = st.load()
        line = cfg.get("statusLine")
    except st.SettingsError as exc:
        cfg, line = {}, f"(unreadable: {exc})"
    cmd = line.get("command") if isinstance(line, dict) else line
    rows = [
        ("engine", f"claude-statusline {__version__} at {os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}"),
        ("python", sys.version.split()[0]),
        ("statusLine", cmd or "(not set: run install.sh)"),
        ("config", path or f"(none; defaults) searched {', '.join(CONFIG_SEARCH)}"),
        ("preset", comp["preset"] + ("  (lines declared in config)" if comp.get("declared") else "")),
        ("look", f"theme {comp['theme']} · style {comp['style']}→{style} · icons {comp['icons']}→{icons} · "
                 f"colour {comp['color']}→{mode}"),
        ("terminal", f"TERM={os.environ.get('TERM', '')} COLORTERM={os.environ.get('COLORTERM', '')}"
                     f"{'  (bundles Nerd Font symbols)' if nerd_terminal(os.environ) else ''}"),
        ("lines", describe_lines(comp)),
        ("width", f"COLUMNS={os.environ.get('COLUMNS') or '(unset)'} right_margin={comp['layout']['right_margin']}"),
        ("quest", ("on" if comp["quest"].get("enabled") else "off")
         + (" · hooks registered" if st.quest_hooks_present(cfg) else " · hooks not registered")),
        ("activity", ("on" if comp["activity"].get("enabled") else "off")
         + (" · hooks registered" if st.activity_hooks_present(cfg) else " · hooks not registered")),
        ("runtime", runtime_dir()),
    ]
    for spec in [s for ln in comp["lines"] for s in ln["left"] + ln["right"] + (ln.get("details") or [])
                 if s["type"] == "command"]:
        rows.append((f"command", f"{spec['name']}: {describe_command(spec, comp)}"))
    for k, v in rows:
        print(f"  {k:<11} {v}")
    if comp["problems"]:
        print(f"  {'problems':<11} {len(comp['problems'])} (statusline.py validate)")
        for p in comp["problems"][:8]:
            print(f"    {p[0]}: {p[1]}: {p[2]}")
    else:
        print(f"  {'problems':<11} none")
    return 0


def cmd_ruler(argv):
    cols = _term_cols(200)
    print("".join(str((i // 10) % 10) if i % 10 == 0 else ("+" if i % 5 == 0 else "·") for i in range(cols)))
    print("".join(str((cols - 1 - i) % 10) for i in range(cols)))
    return 0


def _parse_value(text):
    import tomllib
    try:
        return tomllib.loads(f"v = {text}")["v"]
    except Exception:
        return text


def cmd_set(argv, unset=False):
    pos, fl, vals = _opts(argv, ("force",), ("config",))
    if len(pos) < (1 if unset else 2):
        print("usage: statusline.py set <key> <value>   (e.g. set theme nord, set segment.dir.depth 2)")
        return 2
    from .config import read_toml, write_path
    from .layout import compile_config
    from .tomlw import set_key
    path = os.path.expanduser(vals["config"]) if vals.get("config") else write_path()
    key_ = pos[0]
    val = None if unset else _parse_value(" ".join(pos[1:]))
    try:
        with open(path) as fh:
            text = fh.read()
    except FileNotFoundError:
        text = ""
    new = set_key(text, key_, val)
    import tomllib
    try:
        raw_new = tomllib.loads(new)
    except Exception as exc:
        print(f"refusing: the edit would leave {path} unreadable ({exc})")
        return 1
    before = {(p[1], p[2]) for p in compile_config(read_toml(path)[0] if text else {})["problems"]}
    after = compile_config(raw_new)["problems"]
    fresh = [p for p in after if (p[1], p[2]) not in before and p[0] == "error"]
    if fresh and not fl.get("force"):
        for p in fresh:
            print(f"  error: {p[1]}: {p[2]}")
        print("not written (use --force to write anyway)")
        return 1
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as fh:
        fh.write(new if new.endswith("\n") else new + "\n")
    os.replace(tmp, path)
    from .tomlw import value
    print(f"{'removed' if unset else 'set'} {key_}{'' if unset else ' = ' + value(val)} in {path}")
    return 0


def cmd_get(argv):
    pos, _, _ = _opts(argv)
    if not pos:
        print("usage: statusline.py get <key>")
        return 2
    from .config import DEFAULTS, config_path, deep_merge, read_toml
    raw, _ = read_toml(config_path())
    cur = deep_merge(DEFAULTS, raw)
    for part in pos[0].split("."):
        if not isinstance(cur, dict) or part not in cur:
            print(f"{pos[0]} is not set")
            return 1
        cur = cur[part]
    from .tomlw import value
    print(value(cur))
    return 0


def cmd_bench(argv):
    import subprocess
    from . import samples
    import json
    data = samples.load("busy")
    payload = json.dumps(data).encode()
    entry = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "statusline.py")
    runs = 30
    for label, cmd in (("python3 -S statusline.py", ["python3", "-S", entry]),
                       ("python3 statusline.py", ["python3", entry])):
        ts = []
        for _ in range(runs):
            t = time.perf_counter()
            subprocess.run(cmd, input=payload, stdout=subprocess.DEVNULL, env=dict(os.environ, COLUMNS="160"))
            ts.append(time.perf_counter() - t)
        ts.sort()
        print(f"  {label:<26} median {ts[runs // 2] * 1000:5.1f} ms   best {ts[0] * 1000:5.1f} ms")
    ts = []
    for _ in range(runs):
        t = time.perf_counter()
        subprocess.run(["python3", "-S", "-c", "pass"])
        ts.append(time.perf_counter() - t)
    ts.sort()
    print(f"  {'(python3 -S doing nothing)':<26} median {ts[runs // 2] * 1000:5.1f} ms")
    return 0


def cmd_migrate(argv):
    pos, fl, _ = _opts(argv, ("write",))
    from .config import config_path, read_toml
    from .migrate import migrate
    path = os.path.expanduser(pos[0]) if pos else config_path()
    if not path:
        print("no config file; nothing to migrate")
        return 0
    raw, err = read_toml(path)
    if err:
        print(f"{path}: {err}")
        return 1
    new, changes = migrate(raw)
    if not changes:
        print(f"{path}: already current")
        return 0
    from .tomlw import dumps
    text = dumps(new, header=f"# claude-statusline {__version__} configuration (migrated)")
    summary = "\n".join(f"  {c}" for c in changes)
    if fl.get("write"):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = f"{path}.bak-{stamp}"
        import shutil
        shutil.copy2(path, backup)
        with open(path, "w") as fh:
            fh.write(text)
        print(f"migrated {path}\n  backup: {backup}\n{summary}")
        return 0
    print(f"# migration of {path}; rerun with --write to apply\n{summary}\n\n{text}")
    return 0


def cmd_configure(argv):
    try:
        interactive = sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        interactive = False
    if not interactive:
        print("The configurator needs a terminal: run `python3 ~/.claude/statusline.py configure` in one.\n"
              "From here, try: statusline.py themes · styles · preview · set <key> <value>")
        return 2
    from .tui.app import run
    return run(argv)


COMMANDS = {
    "help": lambda a: (print(HELP.format(version=__version__)), 0)[1],
    "version": lambda a: (print(f"claude-statusline {__version__}"), 0)[1],
    "configure": cmd_configure, "config": cmd_configure,
    "preview": cmd_preview, "render": cmd_render,
    "themes": cmd_themes, "styles": cmd_styles, "icons": cmd_icons, "bars": cmd_bars,
    "segments": cmd_segments, "presets": cmd_presets,
    "validate": cmd_validate, "doctor": cmd_doctor, "ruler": cmd_ruler, "bench": cmd_bench,
    "set": cmd_set, "unset": lambda a: cmd_set(a, unset=True), "get": cmd_get,
    "migrate": cmd_migrate,
}
ALIASES = {"-h": "help", "--help": "help", "--version": "version", "-V": "version", "--doctor": "doctor",
           "--ruler": "ruler", "--demo": "preview"}


def run(argv) -> int:
    cmd, rest = argv[0], argv[1:]
    cmd = ALIASES.get(cmd, cmd)
    if cmd == "quest":
        from .quest.main import main as quest_main
        return quest_main(rest) or 0
    if cmd == "activity":
        from .activity import main as activity_main
        return activity_main(rest) or 0
    fn = COMMANDS.get(cmd)
    if fn is None:
        from .layout import closest
        hint = closest(cmd, COMMANDS)
        print(f"unknown command {cmd!r}" + (f"; did you mean {hint!r}?" if hint else "") + "\n", file=sys.stderr)
        print(HELP.format(version=__version__), file=sys.stderr)
        return 2
    try:
        return fn(rest) or 0
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 2
        raise
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 0
