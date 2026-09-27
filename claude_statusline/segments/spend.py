"""Cost, time, lines changed, burn rate and the prompt cache."""
from __future__ import annotations

from ..fit import LEAN, LESS, NARROW, TEXT
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


CAUSES = {"tools_changed": "tools changed", "system_prompt_changed": "system prompt changed",
          "ttl_expired_5m": "expired after 5m", "ttl_expired_1h": "expired after 1h",
          "likely_server_side": "server side", "model_changed": "model changed"}


@register
class Cache(Segment):
    name = "cache"
    doc = ("The prompt cache, shown while it is costing you (cold, or missing too often, with the likely "
           "cause) and in the last minutes before a warm cache goes cold.")
    priority = 65
    tone = "orange"
    glance = True
    format = "<cachestate>{detail}</cachestate>[<muted> · {cause}</muted>]"
    options = {"min_ratio": Opt(float, 0.90, "Warn when the hit ratio drops below this."),
               "always": Opt(bool, False, "Show the hit ratio even when all is well."),
               "countdown": Opt(float, 5.0, "Minutes before a warm cache goes cold to start counting down "
                                            "(at most half its TTL); 0 turns the countdown off.")}
    fields_doc = {"detail": "'cold 310k', 'hit 62%', 'cools 2m14s' or the hit ratio", "ratio": "hit ratio, percent",
                  "tokens": "tokens to re-cache when cold", "ttl": "the cache's TTL",
                  "left": "time until a warm cache goes cold", "cause": "the likely cause of the last miss"}
    colors_doc = {"cachestate": "orange when cold, yellow when the ratio is low or under a minute is left, "
                                "teal counting down, muted otherwise"}

    def fields(self, ctx, opts, level):
        node = ctx.data.get("prompt_cache")
        if not isinstance(node, dict):
            return None
        ratio = num(node.get("hit_ratio"))
        tokens = node.get("miss_recache_tokens", node.get("recache_tokens_if_cold"))
        tokens = short_num(tokens) if num(tokens) else ""
        pct = f"{ratio * 100:.0f}%" if ratio is not None else ""
        miss = node.get("last_miss_cause")
        causes = miss.get("causes") if isinstance(miss, dict) else None
        cause = ", ".join(CAUSES.get(c, str(c).replace("_", " ")) for c in causes[:2]) \
            if isinstance(causes, list) and causes and level < LEAN else ""
        base = {"ratio": pct, "tokens": tokens, "ttl": str(node.get("ttl") or ""), "left": "", "cause": ""}
        if node.get("warm") is False:
            return dict(base, detail="cold" + (f" {tokens}" if tokens and level < LEAN else ""), cause=cause,
                        _state="orange")
        if ratio is not None and ratio < opts["min_ratio"]:
            return dict(base, detail=f"hit {pct}", cause=cause, _state="yellow")
        expires = num(node.get("expires_at"))
        if expires and opts["countdown"] > 0:
            left = expires - ctx.now
            ttl = {"5m": 300, "1h": 3600}.get(str(node.get("ttl")), 3600)
            if 0 < left <= min(opts["countdown"] * 60, ttl / 2):
                from .live import elapsed
                return dict(base, detail=f"cools {elapsed(left)}", left=elapsed(left),
                            _state="yellow" if left < 60 else "teal")
        if opts["always"] and pct:
            return dict(base, detail=pct, _state="muted")
        return None

    def colors(self, ctx, opts, f):
        return {"cachestate": f["_state"]}

    def tone_at(self, ctx, opts, f):
        return f["_state"]


@register
class Spend(Segment):
    name = "spend"
    doc = ("What today cost across every session this bar has drawn (local days), with the week and "
           "the month, and an optional daily budget drawn as a bar.")
    priority = 56
    tone = "gold"
    format = ("[<subtext>{label}</subtext> ]<spendc><bold>${today}</bold></spendc>[ {bar}][ <muted>{pct}%</muted>]"
              "[<muted> · week ${week}</muted>][<muted> · month ${month}</muted>]")
    options = {
        "label": Opt(str, "today", "Label before the amount; empty for none."),
        "budget": Opt(float, 0.0, "A daily budget in dollars; 0 for none. Shows a bar and turns the amount "
                                  "yellow, orange and red as it fills."),
        "week": Opt(bool, False, "Also show the last seven days."),
        "month": Opt(bool, True, "Also show the month so far."),
        "width": Opt(int, 8, "Budget bar cells; 0 hides the bar."),
    }
    fields_doc = {"label": "the label", "today": "dollars today", "week": "dollars over the last seven days",
                  "month": "dollars this month", "bar": "today against the budget", "pct": "percent of the budget",
                  "budget": "the daily budget"}
    colors_doc = {"spendc": "gold, or by [thresholds] against the budget"}

    def fields(self, ctx, opts, level):
        t = spend_totals(ctx)
        if t is None:
            return None
        budget = max(0.0, num(opts["budget"], 0.0))
        pct = 100.0 * t["today"] / budget if budget else None
        width = 0 if not budget or level >= TEXT or opts["width"] <= 0 else \
            (opts["width"] if level < NARROW else max(3, opts["width"] // 2))
        return {"label": opts["label"] if level < NARROW else "", "today": money(t["today"]),
                "week": money(t["week"]) if opts["week"] and level < LESS else "",
                "month": money(t["month"]) if opts["month"] and level < LESS else "",
                "bar": ctx.bar(min(100.0, pct), width, tone=ctx.level_role(pct)) if width and pct is not None else "",
                "pct": f"{pct:.0f}" if pct is not None and level < LEAN else "",
                "budget": money(budget) if budget else "", "_pct": pct}

    def colors(self, ctx, opts, f):
        return {"spendc": ctx.level_role(f["_pct"]) if f["_pct"] is not None else "gold"}

    def tone_at(self, ctx, opts, f):
        return ctx.level_role(f["_pct"]) if f["_pct"] is not None else None


def spend_totals(ctx):
    """Today's, the week's and the month's spend, or None when the payload has no cost."""
    def get():
        fake = ctx.data.get("_spend")
        if isinstance(fake, dict):
            return {k: num(fake.get(k), 0.0) for k in ("today", "week", "month")}
        usd, ms, _, _, _ = _cost(ctx.data)
        sid = ctx.data.get("session_id")
        if usd is None or not sid:
            return None
        from .. import ledger
        led = ledger.read()
        if ctx.live and ledger.due(led, str(sid), usd, ctx.now):
            led = ledger.update(str(sid), usd, ms, ctx.now) or led
        return ledger.totals(led, ctx.now, str(sid), usd, ms)
    return ctx.memo("spend", get)
