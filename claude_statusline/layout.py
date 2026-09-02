"""The layout schema: lines of segments, resolved against a preset and validated.

    preset = "classic"                 # supplies the lines when none are declared

    [[line]]
    left  = ["model", "dir", "git"]    # flows from the left edge
    right = ["heartbeat"]              # pushed against the right edge
    gap   = 1                          # minimum columns between the groups

    [segment.dir]                      # options for a catalog segment...
    depth = 2
    priority = 95

    [segment.greeting]                 # ...or a named instance of one
    type = "text"
    text = "hello"

Nothing here raises. Problems are collected with a path, and rendering skips
whatever it could not understand, so a typo in the config never blanks the bar.
"""
from __future__ import annotations

import os

from .config import CFG
from .fit import Placed
from .segments import REGISTRY
from .template import Template, TemplateError
from .util import deep_merge

PRESET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets")
LEGACY_FEATURES = {
    "pace": "segment.limit_5h.pace / segment.limit_7d.pace",
    "pace_min_elapsed": "segment.limit_5h.pace_min_elapsed",
    "reset_clock": "segment.limit_5h.clock / segment.limit_7d.clock",
    "last_commit": "segment.git.last_commit",
    "last_commit_nudge_min": "segment.git.nudge_min",
    "context_tokens": "segment.context.tokens",
    "context_size": "segment.context.size",
    "prompt_cache": "leave `cache` out of the line to hide it",
    "prompt_cache_min_ratio": "segment.cache.min_ratio",
    "model_window": "leave `limit_7d_model` out of the line to hide it",
    "repo_links": "segment.git.links / segment.pr.links",
    "fast_mode": "segment.model.fast",
    "heartbeat": "leave `heartbeat` out of the line to hide it",
    "heartbeat_color": "segment.heartbeat.color",
    "heartbeat_period": "segment.heartbeat.period",
}


class Problem:
    __slots__ = ("level", "path", "message")

    def __init__(self, level, path, message):
        self.level = level        # "error" | "warning"
        self.path = path
        self.message = message

    def __str__(self):
        return f"{self.level}: {self.path}: {self.message}"


class SegmentSpec:
    __slots__ = ("name", "type", "segment", "opts")

    def __init__(self, name, type_, segment, opts):
        self.name = name          # the name used in the line
        self.type = type_         # catalog key
        self.segment = segment    # Segment instance from the catalog
        self.opts = opts          # fully resolved options

    def place(self, ctx) -> Placed:
        seg, opts = self.segment, self.opts
        return Placed(self.name, opts["priority"],
                      lambda level: seg.render(ctx, opts, level))


class LineSpec:
    __slots__ = ("left", "right", "gap")

    def __init__(self, left, right, gap):
        self.left = left
        self.right = right
        self.gap = gap


class Layout:
    def __init__(self, lines, problems, preset):
        self.lines = lines
        self.problems = problems
        self.preset = preset

    @property
    def errors(self):
        return [p for p in self.problems if p.level == "error"]

    @property
    def warnings(self):
        return [p for p in self.problems if p.level == "warning"]

    def segment_names(self):
        return [s.name for line in self.lines for s in line.left + line.right]


def list_presets():
    try:
        return sorted(f[:-5] for f in os.listdir(PRESET_DIR) if f.endswith(".toml"))
    except OSError:
        return []


def load_preset(name):
    """The preset's raw tables, or None."""
    if not name or not isinstance(name, str) or "/" in name or name.startswith("."):
        return None
    path = os.path.join(PRESET_DIR, f"{name}.toml")
    try:
        import tomllib
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except Exception:
        return None


def _coerce(value, opt, path, problems):
    """Type-check one option value; return the value to use."""
    want = opt.type
    if want is bool:
        if isinstance(value, bool):
            return value
    elif want is int:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
    elif want is float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    elif want is str:
        if isinstance(value, str):
            return value
    problems.append(Problem("error", path,
                            f"expected {want.__name__}, got {type(value).__name__} {value!r}"))
    return opt.default


def _resolve_segment(name, tables, problems, seen):
    """Turn a name from a line into a SegmentSpec, or None."""
    table = tables.get(name)
    if not isinstance(table, dict):
        table = {}
        if name in tables:
            problems.append(Problem("error", f"segment.{name}", "must be a table"))
    type_ = table.get("type", name)
    seg = REGISTRY.get(type_) if isinstance(type_, str) else None
    if seg is None:
        hint = _closest(str(type_), REGISTRY)
        where = f"segment.{name}.type" if "type" in table else f"line.{name}"
        problems.append(Problem("error", where,
                                f"unknown segment {type_!r}" + (f" (did you mean {hint!r}?)" if hint else "")))
        return None
    if type_ != name and name in REGISTRY and name not in seen:
        problems.append(Problem("warning", f"segment.{name}",
                                f"named after catalog segment {name!r} but has type {type_!r}"))
    schema = seg.all_options()
    opts = {key: opt.default for key, opt in schema.items()}
    for key, value in table.items():
        if key == "type":
            continue
        if key not in schema:
            hint = _closest(key, schema)
            problems.append(Problem("error", f"segment.{name}.{key}",
                                    f"unknown option" + (f" (did you mean {hint!r}?)" if hint else "")))
            continue
        opts[key] = _coerce(value, schema[key], f"segment.{name}.{key}", problems)
    for key in ("format", "missing"):
        if key in opts and isinstance(opts[key], str) and opts[key]:
            try:
                tpl = Template(opts[key])
            except TemplateError as exc:
                problems.append(Problem("error", f"segment.{name}.{key}", str(exc)))
                opts[key] = schema[key].default
                continue
            for field in sorted(tpl.fields - set(seg.fields) - {"url"}):
                problems.append(Problem("warning", f"segment.{name}.{key}",
                                        f"{{{field}}} is not a field of {type_!r}"))
            known = set(CFG["colors"]) | set(seg.colors)
            for color in sorted(tpl.colors - known):
                problems.append(Problem("warning", f"segment.{name}.{key}",
                                        f"<{color}> is not a colour"))
    seen.add(name)
    return SegmentSpec(name, type_, seg, opts)


def _closest(word, candidates):
    """Cheap did-you-mean: shared prefix or one edit away."""
    best, score = None, 0
    for cand in candidates:
        common = os.path.commonprefix([word, cand])
        s = len(common) * 2
        if abs(len(word) - len(cand)) <= 1:
            s += sum(1 for a, b in zip(word, cand) if a == b)
        if s > score and s >= max(3, len(word)):
            best, score = cand, s
    return best


def build_layout(cfg=None) -> Layout:
    cfg = CFG if cfg is None else cfg
    problems = []

    preset_name = cfg.get("preset", "classic")
    preset = load_preset(preset_name)
    if preset is None:
        problems.append(Problem("error", "preset",
                                f"unknown preset {preset_name!r}; using 'classic'"))
        preset_name = "classic"
        preset = load_preset("classic") or {}

    lines_raw = cfg.get("line")
    if not isinstance(lines_raw, list):
        problems.append(Problem("error", "line", "must be an array of tables ([[line]])"))
        lines_raw = []
    if not lines_raw:
        lines_raw = preset.get("line") or []

    tables = deep_merge(preset.get("segment") or {}, cfg.get("segment") or {})
    if not isinstance(cfg.get("segment", {}), dict):
        problems.append(Problem("error", "segment", "must be a table"))
        tables = preset.get("segment") or {}

    features = cfg.get("features")
    if isinstance(features, dict):
        for key in features:
            problems.append(Problem("warning", f"features.{key}",
                                    f"no longer read; use {LEGACY_FEATURES.get(key, 'the segment options')}"))

    seen = set()
    lines = []
    for idx, raw in enumerate(lines_raw):
        path = f"line[{idx}]"
        if not isinstance(raw, dict):
            problems.append(Problem("error", path, "must be a table"))
            continue
        for key in raw:
            if key not in ("left", "right", "gap"):
                problems.append(Problem("error", f"{path}.{key}", "unknown key (left, right, gap)"))
        groups = []
        for side in ("left", "right"):
            names = raw.get(side, [])
            if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
                problems.append(Problem("error", f"{path}.{side}", "must be a list of segment names"))
                names = []
            specs = []
            for name in names:
                spec = _resolve_segment(name, tables, problems, seen)
                if spec is not None:
                    specs.append(spec)
            groups.append(specs)
        gap = raw.get("gap", 2)
        if not isinstance(gap, int) or isinstance(gap, bool) or gap < 0:
            problems.append(Problem("error", f"{path}.gap", "must be a non-negative integer"))
            gap = 2
        if groups[0] or groups[1]:
            lines.append(LineSpec(groups[0], groups[1], gap))
        else:
            problems.append(Problem("warning", path, "empty line"))

    for name in tables:
        if name not in seen and isinstance(tables[name], dict):
            if name in REGISTRY or "type" in tables[name]:
                problems.append(Problem("warning", f"segment.{name}",
                                        "configured but not placed on any line"))
            else:
                problems.append(Problem("error", f"segment.{name}", "unknown segment"))

    return Layout(lines, problems, preset_name)
