"""The pieces of the bar. Each returns a string, or None to render nothing."""
from __future__ import annotations

import os
import time
from datetime import datetime

from .ansi import c, link
from .bar import make_bar, pct_color
from .config import CFG, GLYPHS
from .gitinfo import git_info
from .payload import repo_url
from .util import compact_path, dig, dur, num, short_num, to_epoch


def git_segment(data, cwd: str, worktree=None):
    g = git_info(cwd)
    if not g:
        return None
    name = g["branch"] or (f"@{g['sha']}" if g["sha"] else "?")
    clean = not (g["staged"] or g["dirty"] or g["untracked"] or g["conflict"])
    label = c("green" if clean else "orange", name)

    base = repo_url(data)
    if base and g["branch"]:
        label = link(f"{base}/tree/{g['branch']}", label)
    parts = [c("dim", GLYPHS["git"] + " ") + label]

    if g["state"]:
        parts.append(c("red", g["state"]))
    if g["ahead"]:
        parts.append(c("cyan", f"{GLYPHS['ahead']}{g['ahead']}"))
    if g["behind"]:
        parts.append(c("cyan", f"{GLYPHS['behind']}{g['behind']}"))
    elif not g["upstream"] and g["branch"]:
        parts.append(c("dim", "∅"))
    if g["staged"]:
        parts.append(c("green", f"+{g['staged']}"))
    if g["dirty"]:
        parts.append(c("yellow", f"~{g['dirty']}"))
    if g["untracked"]:
        parts.append(c("gray", f"?{g['untracked']}"))
    if g["conflict"]:
        parts.append(c("red", f"!{g['conflict']}"))
    if g["stash"]:
        parts.append(c("gray", f"{GLYPHS['stash']}{g['stash']}"))

    if g["last_commit"]:
        age = time.time() - g["last_commit"]
        if age >= CFG["features"]["last_commit_nudge_min"] * 60:
            col = "gray" if age < 7200 else ("yellow" if age < 14400 else "orange")
            parts.append(c(col, f"{GLYPHS['clock']}{dur(age)}"))
    if worktree:
        parts.append(c("dim", "wt"))
    return " ".join(parts)

PR_STATE_COLOR = {"open": "green", "draft": "gray", "merged": "purple",
                  "closed": "red", "mr": "green"}


def pr_segment(data):
    node = data.get("github") or data.get("gitlab") or data.get("pull_request")
    if not isinstance(node, dict):
        return None

    def hunt(n, depth=0):
        if depth > 3 or not isinstance(n, dict):
            return None
        num_ = n.get("number") or n.get("pr_number") or n.get("prNumber") or n.get("id")
        if isinstance(num_, int):
            return n
        for v in n.values():
            if isinstance(v, dict):
                got = hunt(v, depth + 1)
                if got:
                    return got
        return None

    pr = hunt(node)
    if not pr:
        return None
    number = pr.get("number") or pr.get("pr_number") or pr.get("prNumber") or pr.get("id")
    state = str(pr.get("state") or pr.get("status") or "open").lower()
    if pr.get("draft") or pr.get("is_draft"):
        state = "draft"
    sigil = "!" if "gitlab" in data else "#"
    label = f"{GLYPHS['pr']} {sigil}{number}"
    checks = str(pr.get("checks") or pr.get("check_status") or "").lower()
    if checks in ("failure", "failing", "error"):
        label += " ✗"
    elif checks in ("success", "passing"):
        label += " ✓"
    elif checks in ("pending", "running"):
        label += " ●"

    url = pr.get("url") or pr.get("html_url")
    if not url:
        base = repo_url(data)
        if base:
            url = f"{base}/pull/{number}"
    return link(url, c(PR_STATE_COLOR.get(state, "cyan"), label))

def limit_segment(label, win, window_len, width=None, pace=None, clock=None):
    feats = CFG["features"]
    width = CFG["bar"]["width"] if width is None else width
    pace = feats["pace"] if pace is None else pace
    clock = feats["reset_clock"] if clock is None else clock

    if not win:
        return c("dim", f"{label} —")
    pct = num(win.get("pct"), 0.0)
    out = c("gray", label)
    if width > 0:
        out += " " + make_bar(pct, width)
    out += " " + c(pct_color(pct), f"{pct:.0f}%")

    ts = to_epoch(win.get("resets_at"))
    if ts is None:
        return out
    left = ts - time.time()

    if pace and pct < 99 and window_len:
        elapsed = (window_len - left) / window_len
        if feats["pace_min_elapsed"] <= elapsed <= 1.0:
            proj = pct / elapsed
            col = "red" if proj >= 100 else ("orange" if proj >= 85 else "dim")
            out += " " + c(col, f"{GLYPHS['pace']}{min(proj, 999):.0f}%")

    tail = f"{GLYPHS['reset']}{dur(left)}"
    if clock and left < 3 * 86400:
        tail += datetime.fromtimestamp(ts).strftime("·%H:%M")
    return out + " " + c("dim", tail)

def ctx_segment(data, width=None):
    """Context-window usage, rendered like the rate-limit bars."""
    feats = CFG["features"]
    width = CFG["bar"]["width"] if width is None else width
    pct = num(dig(data, "context_window", "used_percentage"))
    tok = num(dig(data, "context_window", "used_tokens"))
    if tok is None:
        tok = num(dig(data, "context_window", "total_input_tokens"))
    size = num(dig(data, "context_window", "context_window_size"))

    if pct is None and tok and size:
        pct = 100.0 * tok / size
    if pct is None:
        if tok:
            return c("gray", f"ctx {short_num(tok)}")
        if data.get("exceeds_200k_tokens"):
            return c("orange", "ctx >200k")
        return None

    out = c("gray", "ctx")
    if width > 0:
        out += " " + make_bar(pct, width)
    out += " " + c(pct_color(pct), f"{pct:.0f}%")
    if tok and width > 0 and feats["context_tokens"]:
        detail = short_num(tok)
        if size and feats["context_size"]:
            detail += f"/{short_num(size)}"
        out += " " + c("dim", f"({detail})")
    return out


def cache_segment(data):
    """Surface the prompt cache only when it is costing money."""
    feats = CFG["features"]
    if not feats["prompt_cache"]:
        return None
    node = data.get("prompt_cache")
    if not isinstance(node, dict):
        return None
    ratio = num(node.get("hit_ratio"))
    warm = node.get("warm")
    if warm is False:
        cold = short_num(node.get("recache_tokens_if_cold") or 0)
        return c("orange", f"{GLYPHS['cache']} cold {cold}")
    if ratio is not None and ratio < feats["prompt_cache_min_ratio"]:
        return c("yellow", f"{GLYPHS['cache']} {ratio * 100:.0f}%")
    return None


def heartbeat(now=None) -> str:
    """A tick that advances every refresh, proving the bar is still live.

    Each refresh is a separate process, so there is no counter to increment;
    the frame comes from the wall clock instead. That makes it self
    synchronising and, more usefully, means a stalled status line freezes on
    whatever frame it last drew.
    """
    feats = CFG["features"]
    if not feats.get("heartbeat", True):
        return ""
    frames = CFG["glyphs"].get("heartbeat_frames") or ""
    if not frames:
        return ""
    period = num(feats.get("heartbeat_period"), 1.0) or 1.0
    now = time.time() if now is None else now
    idx = int(now / period) % len(frames)
    return c(feats.get("heartbeat_color", "dim"), frames[idx])

def build_line1(data, cwd, worktree):
    seg = []

    def add(priority, text):
        if text:
            seg.append((priority, text))

    model = (dig(data, "model", "display_name")
             or dig(data, "model", "id") or "claude")
    txt = c("model", f"{GLYPHS['model']} {model}")
    if data.get("fast_mode") and CFG["features"]["fast_mode"]:
        txt += c("yellow", GLYPHS["fast"])
    effort = dig(data, "effort", "level")
    if effort:
        txt += c("dim", f" · {effort}")
    elif dig(data, "thinking", "enabled"):
        txt += c("dim", " · think")
    add(100, txt)

    add(90, c("dir", f"{GLYPHS['dir']} {compact_path(cwd)}"))
    add(85, git_segment(data, cwd, worktree))
    add(70, pr_segment(data))
    add(65, cache_segment(data))

    cost = data.get("cost")
    cost = cost if isinstance(cost, dict) else {}
    tail = []
    usd = num(cost.get("total_cost_usd"))
    if usd is not None:
        tail.append(c("gold", f"${usd:.2f}"))
    ms = num(cost.get("total_duration_ms"))
    if ms:
        tail.append(c("gray", dur(ms / 1000.0)))
    added = num(cost.get("total_lines_added"), 0)
    removed = num(cost.get("total_lines_removed"), 0)
    if added or removed:
        tail.append(c("green", f"+{added:.0f}") + c("dim", "/")
                    + c("red", f"-{removed:.0f}"))
    add(60, " ".join(tail) if tail else None)

    env_bits = []
    venv = os.environ.get("VIRTUAL_ENV") or os.environ.get("CONDA_DEFAULT_ENV")
    if venv:
        env_bits.append(f"{GLYPHS['env']} {os.path.basename(venv)}")
    if os.environ.get("SSH_CONNECTION") or os.path.exists("/.dockerenv"):
        env_bits.append(f"{GLYPHS['host']} {os.uname().nodename}")
    add(50, c("cyan", " ".join(env_bits)) if env_bits else None)

    name = data.get("session_name")
    add(40, c("gray", name) if name else None)

    style = dig(data, "output_style", "name")
    add(30, c("dim", style) if style and style != "default" else None)
    return seg
