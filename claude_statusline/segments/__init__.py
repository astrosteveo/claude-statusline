"""The segment catalog.

A segment is a small class: a name, a default format string, a default
priority, typed options, and `fields_at(ctx, opts, level)` returning the
values its format may reference (or None when it has nothing to show). The
engine handles everything else: fitting, colours, links, dropping.
"""
from __future__ import annotations

from ..config import CFG
from ..template import compile_template


class Opt:
    __slots__ = ("type", "default", "doc")

    def __init__(self, type_, default, doc):
        self.type = type_
        self.default = default
        self.doc = doc


class Segment:
    name = ""
    doc = ""
    priority = 50
    format = ""
    options: dict = {}
    fields: dict = {}     # field name -> what it holds
    colors: dict = {}     # dynamic colour name -> when it applies

    def all_options(self) -> dict:
        return {
            "format": Opt(str, self.format, "Template; see the schema reference."),
            "priority": Opt(int, self.priority,
                            "Higher survives longer when the line is too narrow."),
            **self.options,
        }

    def fields_at(self, ctx, opts, level):
        raise NotImplementedError

    def colors_at(self, ctx, opts, fields) -> dict:
        return {}

    def render(self, ctx, opts, level) -> str:
        fields = self.fields_at(ctx, opts, level)
        if fields is None:
            return ""
        colors = dict(CFG["colors"])
        colors.update(self.colors_at(ctx, opts, fields))
        return compile_template(opts["format"]).render(fields, colors)


REGISTRY: dict[str, Segment] = {}


def register(cls):
    REGISTRY[cls.name] = cls()
    return cls


def get(name: str) -> Segment | None:
    return REGISTRY.get(name)


from . import core, env, spend, usage, vcs  # noqa: E402,F401  (populate REGISTRY)
