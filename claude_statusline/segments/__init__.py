"""The segment catalog.

A segment is a small class: a default format (its body), a default
priority, a tone (the theme role its icon and chip wear), typed options, and
`fields(ctx, opts, level)` returning the values its format may reference, or
None when it has nothing to show. The engine does everything else: icons,
looks, colours, fitting, dropping.

Detail levels, richest first (see fit.py): 0 full, 1 less, 2 lean,
3 narrow (bars at half width), 4 text (no bars). A segment gives something
up at each level if it has something to give; the engine steps every
segment on a line down together.

Modules load lazily: rendering imports only the modules whose segments are
placed, so the catalog can grow without slowing the bar down.
"""
from __future__ import annotations

import importlib

# Segment type -> module that defines it.
CATALOG = {
    "model": "core", "dir": "core", "session": "core", "output_style": "core", "text": "core",
    "clock": "core", "version": "core", "vim": "core", "agent": "core",
    "git": "vcs", "pr": "vcs", "worktree": "vcs",
    "context": "usage", "tokens": "usage", "limit_5h": "usage", "limit_7d": "usage",
    "limit_7d_model": "usage", "limit_spend": "usage",
    "cost": "spend", "duration": "spend", "diff": "spend", "cache": "spend", "burn": "spend", "spend": "spend",
    "env": "env", "host": "env", "heartbeat": "env",
    "command": "custom", "tools": "live", "agents": "live", "tasks": "live", "turn": "live", "mode": "live",
    "quest": "quest", "quest_boss": "quest", "quest_daily": "quest", "quest_buffs": "quest",
    "quest_streak": "quest", "quest_event": "quest", "quest_gold": "quest", "quest_pet": "quest",
    "avatar": "quest", "pet": "quest", "quest_dungeon": "quest", "quest_raid": "quest",
    "quest_settings": "quest",
}
# Types from v2 configs that are spelt differently now.
RENAMED = {}


class Opt:
    __slots__ = ("type", "default", "doc", "choices")

    def __init__(self, type_, default, doc, choices=None):
        self.type = type_
        self.default = default
        self.doc = doc
        self.choices = choices


# Options every segment takes, handled by the engine.
COMMON = {
    "format": Opt(str, None, "The body template (see the schema reference)."),
    "priority": Opt(int, None, "Higher survives longer when the line is too narrow."),
    "icon": Opt(str, None, "The segment's icon; empty hides it. Default: from the icon set."),
    "color": Opt(str, None, "Theme role (or #hex) for the icon and chip. Default: the segment's tone."),
}


class Segment:
    name = ""
    doc = ""
    priority = 50
    tone = "text"          # theme role for icon and chip
    format = ""
    options: dict = {}
    fields_doc: dict = {}  # field -> what it holds
    colors_doc: dict = {}  # dynamic colour -> when it applies
    bare = False           # drawn without chip or icon in every look
    quest = False          # part of Claude Quest: hidden unless quest is enabled
    glance = False         # its icon's colour carries its state, so the icon alone says something
    elastic = False        # takes the columns a fitted line has left over (fit.py)

    def all_options(self) -> dict:
        out = {}
        for key, opt in COMMON.items():
            default = {"format": self.format, "priority": self.priority,
                       "icon": None, "color": None}[key]
            out[key] = Opt(opt.type, default, opt.doc)
        out.update(self.options)
        return out

    def fields(self, ctx, opts, level):
        raise NotImplementedError

    def colors(self, ctx, opts, f) -> dict:
        """Dynamic colours for this rendering: name -> theme role or colour."""
        return {}

    def tone_at(self, ctx, opts, f):
        """The tone for this rendering (e.g. the usage level); None keeps the default."""
        return None


REGISTRY: dict = {}


def register(cls):
    REGISTRY[cls.name] = cls()
    return cls


def get(name: str):
    seg = REGISTRY.get(name)
    if seg is None:
        mod = CATALOG.get(name)
        if mod is None:
            return None
        importlib.import_module(f"{__name__}.{mod}")
        seg = REGISTRY.get(name)
    return seg


def load_all():
    for mod in sorted(set(CATALOG.values())):
        importlib.import_module(f"{__name__}.{mod}")
    return REGISTRY
