"""Cost, time, lines changed, burn rate and the prompt cache."""
from __future__ import annotations

from ..fit import LEAN, LESS
from ..util import dur, money, num, short_num
from . import Opt, Segment, register


def _cost(data):
    cost = data.get("cost") if isinstance(data.get("cost"), dict) else {}
    return (num(cost.get("total_cost_usd")), num(cost.get("total_duration_ms")),
            num(cost.get("total_api_duration_ms")), num(cost.get("total_lines_added"), 0),
            num(cost.get("total_lines_removed"), 0))


@register
class Cost(Segment):
    name = "cost"
    doc = "What the session has cost, with its wall time and lines changed alongside."
    priority = 60
    tone = "gold"
    format = ("[<gold><bold>${usd}</bold></gold>][<muted> · </muted><subtext>{duration}</subtext>]"
              "[<muted> · </muted><green>+{added}</green><muted>/</muted><red>-{removed}</red>]")
    options = {"time": Opt(bool, True, "Include the wall time."),
               "lines": Opt(bool, True, "Include lines added and removed.")}
    fields_doc = {"usd": "dollars", "duration": "wall time", "added": "lines added",
                  "removed": "lines removed"}

    def fields(self, ctx, opts, level):
        usd, ms, _, added, removed = _cost(ctx.data)
        f = {"usd": money(usd) if usd is not None else "",
             "duration": dur(ms / 1000.0) if ms and opts["time"] and level < LEAN else "",
             "added": f"{added:.0f}" if (added or removed) and opts["lines"] and level < LESS else "",
             "removed": f"{removed:.0f}" if (added or removed) and opts["lines"] and level < LESS else ""}
        return f if any(f.values()) else None


@register
class Duration(Segment):
    name = "duration"
    doc = "The session's wall time, and how much of it was spent waiting on the API."
    priority = 58
    tone = "subtext"
    format = "<subtext>{duration}</subtext>[<muted> · api {api}</muted>]"
    options = {"api": Opt(bool, False, "Also show the time spent in API calls.")}
    fields_doc = {"duration": "wall time", "api": "API time"}

    def fields(self, ctx, opts, level):
        _, ms, api, _, _ = _cost(ctx.data)
        if not ms:
            return None
        return {"duration": dur(ms / 1000.0),
                "api": dur(api / 1000.0) if api and opts["api"] and level < LEAN else ""}


@register
class Diff(Segment):
    name = "diff"
    doc = "Lines added and removed this session."
    priority = 57
    tone = "green"
    format = "<green>+{added}</green><muted>/</muted><red>-{removed}</red>"
    fields_doc = {"added": "lines added", "removed": "lines removed"}

    def fields(self, ctx, opts, level):
        _, _, _, added, removed = _cost(ctx.data)
        if not (added or removed):
            return None
        return {"added": f"{added:.0f}", "removed": f"{removed:.0f}"}


@register
class Burn(Segment):
    name = "burn"
    doc = "The spend rate: dollars per hour of session so far."
    priority = 45
    tone = "orange"
    format = "<orange>${rate}</orange><muted>/h</muted>"
    options = {"min_minutes": Opt(float, 5.0, "Wait this long into a session before showing a rate.")}
    fields_doc = {"rate": "dollars per hour"}

    def fields(self, ctx, opts, level):
        usd, ms, _, _, _ = _cost(ctx.data)
        if not usd or not ms or ms < opts["min_minutes"] * 60000:
            return None
        return {"rate": money(usd / (ms / 3_600_000.0))}


@register
class Cache(Segment):
    name = "cache"
    doc = "The prompt cache, shown only while it is costing you: cold, or missing too often."
    priority = 65
    tone = "orange"
    format = "<cachestate>{detail}</cachestate>"
    options = {"min_ratio": Opt(float, 0.90, "Warn when the hit ratio drops below this."),
               "always": Opt(bool, False, "Show the hit ratio even when all is well.")}
    fields_doc = {"detail": "'cold 310k' or the hit ratio", "ratio": "hit ratio, percent",
                  "tokens": "tokens to re-cache when cold", "ttl": "the cache's TTL"}
    colors_doc = {"cachestate": "orange when cold, yellow when the ratio is low, muted otherwise"}

    def fields(self, ctx, opts, level):
        node = ctx.data.get("prompt_cache")
        if not isinstance(node, dict):
            return None
        ratio = num(node.get("hit_ratio"))
        tokens = node.get("miss_recache_tokens", node.get("recache_tokens_if_cold"))
        tokens = short_num(tokens) if num(tokens) else ""
        pct = f"{ratio * 100:.0f}%" if ratio is not None else ""
        base = {"ratio": pct, "tokens": tokens, "ttl": str(node.get("ttl") or "")}
        if node.get("warm") is False:
            return dict(base, detail="cold" + (f" {tokens}" if tokens and level < LEAN else ""), _state="orange")
        if ratio is not None and ratio < opts["min_ratio"]:
            return dict(base, detail=f"hit {pct}", _state="yellow")
        if opts["always"] and pct:
            return dict(base, detail=pct, _state="muted")
        return None

    def colors(self, ctx, opts, f):
        return {"cachestate": f["_state"]}

    def tone_at(self, ctx, opts, f):
        return f["_state"]
