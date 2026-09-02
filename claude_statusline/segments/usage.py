"""Context window and rate-limit bars."""
from __future__ import annotations

from datetime import datetime

from ..bar import make_bar, pct_color
from ..config import CFG, FIVE_HOUR, GLYPHS, SEVEN_DAY
from ..fit import LEAN, LESS, NARROW, TEXT
from ..template import compile_template
from ..util import dig, dur, num, short_num, to_epoch
from . import Opt, Segment, register


def _bar_width(opts, level):
    base = opts["width"]
    base = CFG["bar"]["width"] if base is None or base < 0 else base
    if level >= TEXT:
        return 0
    if level >= NARROW:
        return max(4, base // 2)
    return base


@register
class ContextWindow(Segment):
    name = "context"
    doc = "Context-window usage as a bar, percentage and token count."
    priority = 70
    format = "<gray>{label}</gray>[ {bar}] <level>{pct}%</level>[ <dim>({detail})</dim>]"
    options = {
        "label": Opt(str, "ctx", "Label before the bar."),
        "width": Opt(int, -1, "Bar cells; -1 means [bar].width."),
        "tokens": Opt(bool, True, "Show the token count beside the percentage."),
        "size": Opt(bool, True, "...and the window size, e.g. (380k/1.0M)."),
    }
    fields = {"label": "the label", "bar": "the bar", "pct": "whole-number percentage",
              "tokens": "tokens used, short form", "size": "window size, short form",
              "detail": "tokens, or tokens/size"}
    colors = {"level": "green / yellow / orange / red by [thresholds]"}

    def fields_at(self, ctx, opts, level):
        data = ctx.data
        pct = num(dig(data, "context_window", "used_percentage"))
        tok = num(dig(data, "context_window", "used_tokens"))
        if tok is None:
            tok = num(dig(data, "context_window", "total_input_tokens"))
        size = num(dig(data, "context_window", "context_window_size"))
        if pct is None and tok and size:
            pct = 100.0 * tok / size
        if pct is None:
            if tok:
                return {"label": opts["label"], "bar": "", "pct": "", "tokens": short_num(tok),
                        "size": "", "detail": short_num(tok), "_pct": None}
            if data.get("exceeds_200k_tokens"):
                return {"label": opts["label"], "bar": "", "pct": "", "tokens": ">200k",
                        "size": "", "detail": ">200k", "_pct": None}
            return None
        width = _bar_width(opts, level)
        tokens = short_num(tok) if tok else ""
        size_s = short_num(size) if size else ""
        detail = ""
        if tokens and width > 0 and opts["tokens"]:
            detail = tokens + (f"/{size_s}" if size_s and opts["size"] else "")
        return {"label": opts["label"], "bar": make_bar(pct, width), "pct": f"{pct:.0f}",
                "tokens": tokens, "size": size_s, "detail": detail, "_pct": pct}

    def colors_at(self, ctx, opts, fields):
        pct = fields["_pct"]
        return {"level": CFG["colors"][pct_color(pct) if pct is not None else "gray"]}

    def render(self, ctx, opts, level):
        fields = self.fields_at(ctx, opts, level)
        if fields is None:
            return ""
        if fields["_pct"] is None:
            # No percentage to draw: fall back to the plain token readout.
            colors = dict(CFG["colors"])
            tone = "orange" if fields["detail"] == ">200k" else "gray"
            return compile_template("<tone>{label} {detail}</tone>").render(
                fields, {**colors, "tone": colors[tone]})
        return super().render(ctx, opts, level)


class Limit(Segment):
    """Shared shape of the rate-limit bars."""
    slot = ""
    window_len = 0
    label = ""
    format = ("<gray>{label}</gray>[ {bar}] <level>{pct}%</level>"
              "[ <pacecolor>{pace}</pacecolor>][ <dim>{reset}[·{clock}]</dim>]")
    options = {
        "width": Opt(int, -1, "Bar cells; -1 means [bar].width."),
        "pace": Opt(bool, True, "Project end-of-window usage from the burn rate."),
        "pace_min_elapsed": Opt(float, 0.10, "Do not extrapolate from under this fraction of the window."),
        "clock": Opt(bool, True, "Append the wall-clock time of the reset."),
        "missing": Opt(str, "<dim>{label} —</dim>", "Template used when the host sends no such window; empty hides it."),
    }
    fields = {"label": "the window label", "bar": "the bar", "pct": "whole-number percentage",
              "pace": "⇢ projected usage at reset", "reset": "↻ time until reset",
              "clock": "wall-clock time of the reset"}
    colors = {"level": "green / yellow / orange / red by [thresholds]",
              "pacecolor": "red when the projection exceeds 100%, orange past 85%, else dim"}

    def window(self, ctx):
        return ctx.windows().get(self.slot)

    def fields_at(self, ctx, opts, level):
        win = self.window(ctx)
        if not win:
            return {"label": self.label, "_missing": True}
        pct = num(win.get("pct"), 0.0)
        width = _bar_width(opts, level)
        f = {"label": self.label, "bar": make_bar(pct, width), "pct": f"{pct:.0f}",
             "pace": "", "reset": "", "clock": "", "_pct": pct, "_pacecolor": "dim",
             "_missing": False}
        ts = to_epoch(win.get("resets_at"))
        if ts is None:
            return f
        left = ts - ctx.now
        if opts["pace"] and level < LEAN and pct < 99 and self.window_len:
            elapsed = (self.window_len - left) / self.window_len
            if opts["pace_min_elapsed"] <= elapsed <= 1.0:
                proj = pct / elapsed
                f["pace"] = f"{GLYPHS['pace']}{min(proj, 999):.0f}%"
                f["_pacecolor"] = "red" if proj >= 100 else ("orange" if proj >= 85 else "dim")
        f["reset"] = f"{GLYPHS['reset']}{dur(left)}"
        if opts["clock"] and level < LESS and left < 3 * 86400:
            f["clock"] = datetime.fromtimestamp(ts).strftime("%H:%M")
        return f

    def colors_at(self, ctx, opts, fields):
        return {"level": CFG["colors"][pct_color(fields["_pct"])],
                "pacecolor": CFG["colors"][fields["_pacecolor"]]}

    def render(self, ctx, opts, level):
        fields = self.fields_at(ctx, opts, level)
        if fields is None:
            return ""
        if fields["_missing"]:
            if not opts["missing"]:
                return ""
            return compile_template(opts["missing"]).render(fields, dict(CFG["colors"]))
        colors = dict(CFG["colors"])
        colors.update(self.colors_at(ctx, opts, fields))
        return compile_template(opts["format"]).render(fields, colors)


@register
class FiveHour(Limit):
    name = "limit_5h"
    doc = "The five-hour rate-limit window."
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
    doc = "The per-model weekly window, only when it differs from the overall one."
    priority = 55
    slot = "7d_model"
    window_len = SEVEN_DAY
    label = "7d"
    options = {**Limit.options,
               "pace": Opt(bool, False, "Project end-of-window usage from the burn rate."),
               "clock": Opt(bool, False, "Append the wall-clock time of the reset."),
               "missing": Opt(str, "", "Template when absent; empty hides it.")}

    def fields_at(self, ctx, opts, level):
        wins = ctx.windows()
        win = wins.get("7d_model")
        if not win or win is wins.get("7d") or level >= TEXT:
            return None
        f = super().fields_at(ctx, opts, level)
        f["label"] = f"7d·{win.get('label') or 'model'}"
        return f
