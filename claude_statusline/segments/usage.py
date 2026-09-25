"""The context window and the rate-limit windows."""
from __future__ import annotations

from ..fit import LEAN, LESS, TEXT
from ..util import dig, dur, num, short_num, to_epoch
from . import Opt, Segment, register

FIVE_HOUR = 5 * 3600
SEVEN_DAY = 7 * 86400

BAR_OPTS = {
    "width": Opt(int, -1, "Bar cells; -1 means [bar].width."),
    "style": Opt(str, "", "Bar style for this segment; empty means [bar].style."),
    "fill": Opt(str, "", "Bar fill for this segment; empty means [bar].fill."),
}


@register
class ContextWindow(Segment):
    name = "context"
    doc = "How full the context window is: a bar, the percentage, and the tokens."
    priority = 70
    tone = "green"
    format = ("[<subtext>{label}</subtext> ][{bar} ][<level><bold>{pct}%</bold></level>]"
              "[ <muted>{detail}</muted>]")
    options = {
        "label": Opt(str, "ctx", "Label before the bar; empty for none."),
        **BAR_OPTS,
        "tokens": Opt(bool, True, "Show the tokens used beside the percentage."),
        "size": Opt(bool, True, "...and the window's size, as 279k/1.0M."),
        "remaining": Opt(bool, False, "Show what is left instead of what is used."),
    }
    fields_doc = {"label": "the label", "bar": "the bar", "pct": "whole percentage",
                  "tokens": "tokens used", "size": "window size", "left": "tokens left",
                  "detail": "tokens, or tokens/size"}
    colors_doc = {"level": "green / yellow / orange / red by [thresholds]"}

    def fields(self, ctx, opts, level):
        data = ctx.data
        cw = data.get("context_window") if isinstance(data.get("context_window"), dict) else {}
        pct = num(cw.get("used_percentage"))
        tok = num(cw.get("used_tokens"))
        if tok is None:
            tok = num(cw.get("total_input_tokens"))
        if tok is None and isinstance(cw.get("current_usage"), dict):
            cu = cw["current_usage"]
            parts = [num(cu.get(k)) for k in ("input_tokens", "cache_creation_input_tokens",
                                              "cache_read_input_tokens")]
            tok = sum(p for p in parts if p) or None
        size = num(cw.get("context_window_size"))
        if pct is None and tok and size:
            pct = 100.0 * tok / size
        if pct is None:
            if data.get("exceeds_200k_tokens"):
                return {"label": opts["label"], "bar": "", "pct": "", "detail": ">200k",
                        "tokens": ">200k", "size": "", "left": "", "_pct": 100.0}
            return None
        pct = max(0.0, min(100.0, pct))
        shown = 100.0 - pct if opts["remaining"] else pct
        detail = ""
        if tok and opts["tokens"] and level < LEAN:
            used = short_num(tok)
            detail = used + (f"/{short_num(size)}" if size and opts["size"] and level < LESS else "")
        return {"label": opts["label"] if level < TEXT else "",
                "bar": ctx.bar(shown, ctx.bar_width(opts, level), opts["style"], opts["fill"],
                               tone=ctx.level_role(pct)),
                "pct": f"{shown:.0f}", "tokens": short_num(tok) if tok else "",
                "size": short_num(size) if size else "",
                "left": short_num(size - tok) if size and tok else "", "detail": detail, "_pct": pct}

    def colors(self, ctx, opts, f):
        return {"level": ctx.level_role(f["_pct"])}

    def tone_at(self, ctx, opts, f):
        return ctx.level_role(f["_pct"])


@register
class Tokens(Segment):
    name = "tokens"
    doc = "Tokens this session: sent to the model and received from it."
    priority = 32
    tone = "cyan"
    format = "<subtext>{input}</subtext><muted> in · </muted><subtext>{output}</subtext><muted> out</muted>"
    fields_doc = {"input": "input tokens", "output": "output tokens"}

    def fields(self, ctx, opts, level):
        cw = ctx.data.get("context_window") if isinstance(ctx.data.get("context_window"), dict) else {}
        i, o = num(cw.get("total_input_tokens")), num(cw.get("total_output_tokens"))
        if i is None and o is None:
            return None
        return {"input": short_num(i or 0), "output": short_num(o or 0)}


class Limit(Segment):
    """What the rate-limit bars share."""
    slot = ""
    window_len = 0
    label = ""
    tone = "green"
    format = ("[<subtext>{label}</subtext> ][{bar} ]<level><bold>{pct}%</bold></level>"
              "[ <pacecolor>{pace}</pacecolor>][ <muted>{reset}[·{clock}]</muted>]")
    options = {
        "label": Opt(str, None, "Label before the bar; empty for none."),
        **BAR_OPTS,
        "pace": Opt(bool, True, "Project where usage will be when the window resets (⇢)."),
        "pace_mode": Opt(str, "recent", "recent: the rate over the last stretch of the window; "
                                        "average: usage so far over the window gone.",
                         choices=("recent", "average")),
        "pace_min_elapsed": Opt(float, 0.10, "Don't extrapolate an average from under this much of the window."),
        "pace_lookback": Opt(float, 0.10, "The stretch `recent` measures, as a fraction of the window."),
        "reset": Opt(bool, True, "Show the time until the window resets (↻)."),
        "clock": Opt(bool, True, "...and the time of day it resets."),
        "missing": Opt(str, "<muted>{label} —</muted>", "Shown when the host sends no such window; "
                                                          "empty hides the segment."),
    }
    fields_doc = {"label": "the window's label", "bar": "the bar", "pct": "whole percentage",
                  "pace": "⇢ projected usage at reset", "reset": "↻ time until reset",
                  "clock": "time of day of the reset", "left": "percentage left"}
    colors_doc = {"level": "green / yellow / orange / red by [thresholds]",
                  "pacecolor": "red when the projection passes 100%, orange past 85%, else muted"}

    def all_options(self):
        out = super().all_options()
        out["label"] = Opt(str, self.label, "Label before the bar; empty for none.")
        return out

    def window(self, ctx):
        return ctx.windows().get(self.slot)

    def fields(self, ctx, opts, level):
        win = self.window(ctx)
        label = opts["label"] if opts.get("label") is not None else self.label
        if not win:
            return {"label": label, "_missing": True}
        pct = num(win.get("pct"), 0.0)
        f = {"label": label if level < TEXT else label, "pct": f"{pct:.0f}", "left": f"{100 - pct:.0f}",
             "bar": ctx.bar(pct, ctx.bar_width(opts, level), opts["style"], opts["fill"],
                            tone=ctx.level_role(pct)),
             "pace": "", "reset": "", "clock": "", "_pct": pct, "_pace": "muted", "_missing": False}
        ts = to_epoch(win.get("resets_at"))
        if ts is None:
            return f
        left = ts - ctx.now
        if opts["pace"] and level < LEAN and pct < 99 and self.window_len:
            from ..pace import project
            # Previews project from the average: only the live bar keeps a history.
            popts = opts if ctx.live else dict(opts, pace_mode="average")
            proj = ctx.memo(("pace", self.slot),
                            lambda: project(ctx.now, self.slot, pct, ts, self.window_len, popts))
            if proj is not None:
                f["pace"] = f"{ctx.mark('pace')}{min(proj, 999):.0f}%"
                f["_pace"] = "red" if proj >= 100 else ("orange" if proj >= 85 else "muted")
        if opts["reset"] and left > 0:
            f["reset"] = f"{ctx.mark('reset')}{dur(left)}"
            if opts["clock"] and level < LESS and left < 3 * 86400:
                from datetime import datetime
                f["clock"] = datetime.fromtimestamp(ts).strftime("%H:%M")
        return f

    def colors(self, ctx, opts, f):
        if f.get("_missing"):
            return {}
        return {"level": ctx.level_role(f["_pct"]), "pacecolor": f["_pace"]}

    def tone_at(self, ctx, opts, f):
        return "muted" if f.get("_missing") else ctx.level_role(f["_pct"])


@register
class FiveHour(Limit):
    name = "limit_5h"
    doc = "The five-hour rate-limit window, with a pace projection and the reset countdown."
    priority = 80
    slot = "5h"
    window_len = FIVE_HOUR
    label = "5h"


@register
class SevenDay(Limit):
    name = "limit_7d"
    doc = "The seven-day rate-limit window."
    priority = 75
    slot = "7d"
    window_len = SEVEN_DAY
    label = "7d"


@register
class SevenDayModel(Limit):
    name = "limit_7d_model"
    doc = "The per-model weekly window, shown only when it differs from the overall one."
    priority = 55
    slot = "7d_model"
    window_len = SEVEN_DAY
    label = "7d"
    options = {**Limit.options,
               "pace": Opt(bool, False, "Project where usage will be when the window resets (⇢)."),
               "clock": Opt(bool, False, "...and the time of day it resets."),
               "missing": Opt(str, "", "Shown when absent; empty hides it.")}

    def fields(self, ctx, opts, level):
        wins = ctx.windows()
        win = wins.get("7d_model")
        if not win or win is wins.get("7d") or level >= TEXT:
            return None
        f = super().fields(ctx, opts, level)
        if not f.get("_missing"):
            f["label"] = f"{f['label']}·{win.get('label') or 'model'}"
        return f


@register
class SpendLimit(Limit):
    name = "limit_spend"
    doc = "The spend limit, for accounts behind a gateway that meters spend."
    priority = 72
    slot = "spend"
    window_len = 0
    label = "spend"
    tone = "gold"
    options = {**Limit.options, "missing": Opt(str, "", "Shown when absent; empty hides it.")}
