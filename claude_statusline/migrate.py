"""Bring configs from earlier versions up to date.

v3 still reads v2 files as they are; `migrate` tidies them: v1's
[features] becomes segment options, bar glyph overrides become bar styles,
colours and glyphs equal to v2's defaults go (the theme supplies them now),
and hand-placed kitty avatar rows give way to automatic placement.
"""
from __future__ import annotations

import re

# v2 formats began with the icon: "<model>{glyph} {name}</model>". v3 styles
# place icons themselves (as coloured blocks in the chip looks), so the
# placeholder goes and the style takes over.
_LEADING_GLYPH = re.compile(r"^((?:<[A-Za-z_]+>)*)\{glyph\} ?")

V2_COLORS = {"reset": "0", "dim": "38;5;240", "gray": "38;5;245", "model": "38;5;141", "dir": "38;5;39",
             "cyan": "38;5;80", "green": "38;5;114", "yellow": "38;5;221", "orange": "38;5;208",
             "red": "38;5;203", "gold": "38;5;179", "purple": "38;5;176", "bold": "1"}
V2_GLYPHS = {"model": "◆", "dir": "▸", "git": "⎇", "reset": "↻", "stash": "⚑", "ahead": "↑",
             "behind": "↓", "pace": "⇢", "clock": "⏱", "pr": "⇄", "host": "⌂", "env": "⬢",
             "fast": "⚡", "cache": "⌗", "heartbeat_frames": "⠋⠙⠹⠸⠼⠴⠦⠧"}
V2_LAYOUT = {"separator": " │ "}

FEATURES = {
    "pace": [("limit_5h", "pace"), ("limit_7d", "pace")],
    "pace_min_elapsed": [("limit_5h", "pace_min_elapsed"), ("limit_7d", "pace_min_elapsed")],
    "reset_clock": [("limit_5h", "clock"), ("limit_7d", "clock")],
    "last_commit": [("git", "last_commit")],
    "last_commit_nudge_min": [("git", "nudge_min")],
    "context_tokens": [("context", "tokens")],
    "context_size": [("context", "size")],
    "prompt_cache_min_ratio": [("cache", "min_ratio")],
    "repo_links": [("git", "links"), ("pr", "links")],
    "fast_mode": [("model", "fast")],
    "heartbeat_color": [("heartbeat", "color")],
    "heartbeat_period": [("heartbeat", "period")],
}
REMOVE_IF_FALSE = {"prompt_cache": "cache", "model_window": "limit_7d_model", "heartbeat": "heartbeat"}


def migrate(raw: dict):
    """(new config dict, [what changed])."""
    new = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
           for k, v in raw.items()}
    changes = []
    segs = {k: dict(v) for k, v in (new.get("segment") or {}).items() if isinstance(v, dict)}
    remove = set()

    feats = new.pop("features", None)
    if isinstance(feats, dict):
        for key, val in feats.items():
            if key in FEATURES:
                for name, opt in FEATURES[key]:
                    segs.setdefault(name, {})[opt] = val
                    changes.append(f"features.{key} -> segment.{name}.{opt} = {val!r}")
            elif key in REMOVE_IF_FALSE:
                if val is False:
                    remove.add(REMOVE_IF_FALSE[key])
                    changes.append(f"features.{key} = false -> {REMOVE_IF_FALSE[key]} left off the lines")
            else:
                changes.append(f"dropped features.{key} (no longer meaningful)")

    bar = new.get("bar")
    if isinstance(bar, dict):
        style = bar.get("style")
        if bar.get("empty") in ("░",) and style in (None, "block"):
            bar["style"] = "shade"
            changes.append("bar.empty = \"░\" -> bar.style = \"shade\"")
        elif style in ("block", "thin"):
            bar["style"] = {"block": "smooth", "thin": "line"}[style]
            changes.append(f"bar.style {style!r} -> {bar['style']!r}")
        for key in ("full", "empty", "partial", "partial_style"):
            if key in bar:
                bar.pop(key)
                changes.append(f"dropped bar.{key} (bar styles carry their own glyphs)")
        if bar.get("track") == "dim":
            bar.pop("track")
            changes.append("dropped bar.track = \"dim\" (the theme's track colour is the default now)")
        if not bar:
            new.pop("bar")

    colors = new.get("colors")
    if isinstance(colors, dict):
        same = [k for k, v in colors.items() if V2_COLORS.get(k) == v]
        for k in same:
            colors.pop(k)
        if same:
            changes.append(f"dropped {len(same)} colour(s) equal to v2's defaults; the theme supplies them")
        if not colors:
            new.pop("colors")

    glyphs = new.get("glyphs")
    if isinstance(glyphs, dict):
        same = [k for k, v in glyphs.items() if V2_GLYPHS.get(k) == v]
        for k in same:
            glyphs.pop(k)
        if same:
            changes.append(f"dropped {len(same)} glyph(s) equal to v2's defaults; the icon set supplies them")
        if not glyphs:
            new.pop("glyphs")

    layout = new.get("layout")
    if isinstance(layout, dict):
        for k, v in V2_LAYOUT.items():
            if layout.get(k) == v:
                layout.pop(k)
                changes.append(f"dropped layout.{k} = {v!r} (the style decides separators now)")
        if not layout:
            new.pop("layout")

    lines = new.get("line")
    avatar_rows = {n for n, t in segs.items() if t.get("type") == "avatar"}
    if isinstance(lines, list):
        quest_types = {"quest", "quest_boss", "quest_daily", "quest_buffs", "quest_streak", "quest_event",
                       "quest_gold", "quest_pet", "pet", "avatar", "quest_dungeon", "quest_raid"}
        uses_quest = False
        out = []
        for ln in lines:
            if not isinstance(ln, dict):
                out.append(ln)
                continue
            ln = dict(ln)
            for side in ("left", "right"):
                names = ln.get(side)
                if isinstance(names, list):
                    kept = []
                    for n in names:
                        t = segs.get(n, {}).get("type", n)
                        if t in quest_types:
                            uses_quest = True
                        if n in avatar_rows or n in remove:
                            continue
                        if t == "pet":
                            n = "quest_pet"
                        kept.append(n)
                    ln[side] = kept
            if ln.get("left") or ln.get("right"):
                out.append(ln)
        if avatar_rows:
            changes.append(f"removed hand-placed avatar rows ({', '.join(sorted(avatar_rows))}); "
                           f"[quest] avatar = \"auto\" places the picture at the right edge by itself")
            for n in avatar_rows:
                segs.pop(n, None)
        if remove:
            changes.append("removed from lines: " + ", ".join(sorted(remove)))
        new["line"] = out
        if uses_quest:
            q = new.setdefault("quest", {})
            if "enabled" not in q:
                q["enabled"] = True
                changes.append("quest segments are placed -> [quest] enabled = true")
            if avatar_rows and "avatar" not in q:
                q["avatar"] = "auto"
    for n, table in segs.items():
        fmt = table.get("format")
        if isinstance(fmt, str) and _LEADING_GLYPH.match(fmt):
            table["format"] = _LEADING_GLYPH.sub(r"\1", fmt, count=1)
            changes.append(f"segment.{n}.format: the icon is placed by the style now")
    for n in list(segs):
        if segs[n].get("type") == "pet":
            segs[n]["type"] = "quest_pet"
            changes.append(f"segment.{n}.type \"pet\" -> \"quest_pet\"")
    if segs:
        new["segment"] = segs
    else:
        new.pop("segment", None)
    return new, changes
