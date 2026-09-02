"""Fit the segments to the terminal and emit the lines."""
from __future__ import annotations

import os

from .ansi import c
from .config import CFG, FIVE_HOUR, GLYPHS, SEVEN_DAY
from .payload import find_windows
from .segments import build_line1, ctx_segment, heartbeat, limit_segment
from .util import compact_path, dig
from .width import display_width


def assemble_line1(seg, avail, sep):
    """Drop the lowest-priority segments until the row fits."""
    order = sorted(range(len(seg)), key=lambda i: seg[i][0])
    kept = list(range(len(seg)))
    while True:
        line = sep.join(seg[i][1] for i in sorted(kept))
        if display_width(line) <= avail or len(kept) <= 1:
            return line
        for i in order:
            if i in kept:
                kept.remove(i)
                break


# Progressively cheaper renderings; the first that fits the row wins.
def _levels(base_width):
    narrow = max(4, base_width // 2)
    return (
        (True, base_width, True, True),
        (True, base_width, True, False),
        (True, base_width, False, False),
        (True, narrow, False, False),
        (True, 0, False, False),
        (False, 0, False, False),
    )


def assemble_line2(data, avail, sep):
    wins = find_windows(data)
    feats = CFG["features"]
    left = right = ""
    gap = min_gap = 0

    for show_ctx, width, pace, clock in _levels(CFG["bar"]["width"]):
        left = (ctx_segment(data, width) or "") if show_ctx else ""
        right = (limit_segment("5h", wins.get("5h"), FIVE_HOUR, width, pace, clock)
                 + sep
                 + limit_segment("7d", wins.get("7d"), SEVEN_DAY, width, pace, clock))
        model_win = wins.get("7d_model")
        if (feats["model_window"] and model_win
                and model_win is not wins.get("7d") and width):
            tag = model_win.get("label") or "model"
            right += sep + limit_segment(f"7d·{tag}", model_win, SEVEN_DAY,
                                         width, False, False)
        if not wins:
            right += sep + c("dim", "limits n/a")
        min_gap = 2 if left else 0
        gap = avail - display_width(left) - display_width(right)
        if gap >= min_gap:
            break
    return left + " " * max(min_gap, gap) + right


def usable_width(cols=None) -> int:
    lay = CFG["layout"]
    if cols is None:
        try:
            cols = int(os.environ.get("COLUMNS") or 0)
        except ValueError:
            cols = 0
        cols = cols or lay["fallback_columns"]
    return max(20, cols - max(0, lay["right_margin"]))


def render(data, cols=None, now=None) -> str:
    if not isinstance(data, dict):
        data = {}
    cwd = (dig(data, "workspace", "current_dir")
           or data.get("cwd") or os.getcwd())
    worktree = dig(data, "workspace", "git_worktree")
    avail = usable_width(cols)
    sep = c("dim", CFG["layout"]["separator"])

    beat = heartbeat(now)
    beat_w = display_width(beat)
    # Reserve the tick plus one column of gap, but give up on it rather than
    # crowd out real information on a very narrow terminal.
    reserve = beat_w + 1 if beat_w and avail - beat_w - 1 >= 20 else 0

    line1 = assemble_line1(build_line1(data, cwd, worktree),
                           avail - reserve, sep)
    if reserve:
        pad = avail - display_width(line1) - beat_w
        line1 += " " * max(1, pad) + beat
    line2 = assemble_line2(data, avail, sep)
    return line1 + "\n" + line2


def fallback(data) -> str:
    """Last resort when render() raises: never leave the bar blank."""
    try:
        model = (dig(data, "model", "display_name")
                 or dig(data, "model", "id") or "claude")
        cwd = (dig(data, "workspace", "current_dir")
               or data.get("cwd") or os.getcwd())
        return f"{GLYPHS['model']} {model}  {GLYPHS['dir']} {compact_path(cwd)}"
    except Exception:
        return "claude"
