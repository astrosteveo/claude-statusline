"""Cost, time, lines changed and the prompt cache."""
from __future__ import annotations

from ..config import CFG, GLYPHS
from ..util import dur, num, short_num
from . import Opt, Segment, register


def _cost_fields(data):
    cost = data.get("cost")
    cost = cost if isinstance(cost, dict) else {}
    usd = num(cost.get("total_cost_usd"))
    ms = num(cost.get("total_duration_ms"))
    added = num(cost.get("total_lines_added"), 0)
    removed = num(cost.get("total_lines_removed"), 0)
    return {
        "usd": f"{usd:.2f}" if usd is not None else "",
        "duration": dur(ms / 1000.0) if ms else "",
        "added": f"{added:.0f}" if (added or removed) else "",
        "removed": f"{removed:.0f}" if (added or removed) else "",
    }


@register
class Cost(Segment):
    name = "cost"
    doc = "Session cost, wall time and lines changed, together."
    priority = 60
    format = ("<gold>[${usd}]</gold>[ <gray>{duration}</gray>]"
              "[ <green>+{added}</green><dim>/</dim><red>-{removed}</red>]")
    fields = {"usd": "cost in dollars, two decimals", "duration": "wall time",
              "added": "lines added", "removed": "lines removed"}

    def fields_at(self, ctx, opts, level):
        f = _cost_fields(ctx.data)
        return f if any(f.values()) else None


@register
class Duration(Segment):
    name = "duration"
    doc = "Session wall time on its own."
    priority = 58
    format = "<gray>{duration}</gray>"
    fields = {"duration": "wall time"}

    def fields_at(self, ctx, opts, level):
        f = _cost_fields(ctx.data)
        return f if f["duration"] else None


@register
class Diff(Segment):
    name = "diff"
    doc = "Lines added and removed on their own."
    priority = 57
    format = "<green>+{added}</green><dim>/</dim><red>-{removed}</red>"
    fields = {"added": "lines added", "removed": "lines removed"}

    def fields_at(self, ctx, opts, level):
        f = _cost_fields(ctx.data)
        return f if f["added"] else None


@register
class Cache(Segment):
    name = "cache"
    doc = "The prompt cache, shown only when it is costing money."
    priority = 65
    format = "<cachestate>{glyph} {detail}</cachestate>"
    options = {"min_ratio": Opt(float, 0.90, "Warn when the hit ratio falls below this.")}
    fields = {"glyph": "the cache glyph", "detail": "'cold <tokens>' or '<ratio>%'",
              "ratio": "hit ratio as a percentage", "tokens": "tokens to recache if cold"}
    colors = {"cachestate": "orange when cold, yellow when the ratio is low"}

    def fields_at(self, ctx, opts, level):
        node = ctx.data.get("prompt_cache")
        if not isinstance(node, dict):
            return None
        ratio = num(node.get("hit_ratio"))
        tokens = short_num(node.get("recache_tokens_if_cold") or 0)
        pct = f"{ratio * 100:.0f}" if ratio is not None else ""
        if node.get("warm") is False:
            return {"glyph": GLYPHS["cache"], "detail": f"cold {tokens}", "ratio": pct,
                    "tokens": tokens, "_state": "orange"}
        if ratio is not None and ratio < opts["min_ratio"]:
            return {"glyph": GLYPHS["cache"], "detail": f"{pct}%", "ratio": pct,
                    "tokens": tokens, "_state": "yellow"}
        return None

    def colors_at(self, ctx, opts, fields):
        return {"cachestate": CFG["colors"][fields["_state"]]}
