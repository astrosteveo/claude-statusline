#!/usr/bin/env python3
"""Claude Code status line.

Line 1: model/effort, cwd, git state, PR, cost, env, session name.
Line 2: context bar on the left; 5h / 7d rate-limit bars with burn-rate
        projection and reset countdowns, anchored flush to the right edge.

Reads the status JSON on stdin. Configure via TOML (see --dump-config);
no third-party dependencies, stdlib only.

    --doctor        report resolved config, detected width, cache state
    --ruler         print calibration rulers (see README: right_margin)
    --demo          render a bundled sample payload
    --dump-config   print the effective config as TOML
    --version       print version
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import unicodedata
from datetime import datetime

__version__ = "1.0.0"

CONFIG_ENV = "CLAUDE_STATUSLINE_CONFIG"
DUMP_ENV = "CLAUDE_STATUSLINE_DUMP"      # set to a path to capture raw payloads
DEBUG_ENV = "CLAUDE_STATUSLINE_DEBUG"    # set to surface tracebacks on stderr

CONFIG_SEARCH = (
    "~/.config/claude-statusline/config.toml",
    "~/.claude/statusline.toml",
)

FIVE_HOUR = 5 * 3600
SEVEN_DAY = 7 * 86400

# ---------------------------------------------------------------- defaults ---
DEFAULTS = {
    "layout": {
        # Columns the host TUI reserves at the right edge. Claude Code's
        # fullscreen TUI consumes ~4 beyond the COLUMNS it reports (frame and
        # padding) and then truncates with an ellipsis; 4 reserved + 1 wrap
        # gap = 5. Run `--ruler` to calibrate for your terminal.
        "right_margin": 5,
        "separator": " │ ",
        "fallback_columns": 200,
        # Glyphs your font renders double-width even though Unicode calls them
        # narrow. Purely cosmetic elsewhere, but they push the line over budget.
        "wide_glyphs": [],
    },
    "bar": {
        "width": 12,
        "partial": True,     # sub-cell resolution via eighth-block glyphs
        "min_sliver": True,  # any usage > 0 shows at least a sliver
        "full": "█",
        "empty": "░",
    },
    "thresholds": {"yellow": 50, "orange": 75, "red": 90},
    "features": {
        "pace": True,
        "pace_min_elapsed": 0.10,
        "reset_clock": True,
        "last_commit": True,
        "last_commit_nudge_min": 45,
        "context_tokens": True,
        "context_size": True,
        "prompt_cache": True,
        "prompt_cache_min_ratio": 0.90,
        "model_window": True,
        "repo_links": True,
        "fast_mode": True,
    },
    "git": {
        "enabled": True,
        "timeout": 2.0,
        "cache_ttl": 2.0,       # seconds a cached git read stays fresh
        "slow_threshold": 0.35, # a read slower than this triggers backoff
        "slow_backoff": 10.0,   # ttl = max(cache_ttl, duration * slow_backoff)
    },
    "glyphs": {
        "model": "◆", "dir": "▸", "git": "⎇", "reset": "↻",
        "stash": "⚑", "ahead": "↑", "behind": "↓",
        "pace": "⇢", "clock": "⏱", "pr": "⇄", "host": "⌂",
        "env": "⬢", "fast": "⚡", "cache": "⌗",
    },
    "colors": {
        "reset": "0", "dim": "38;5;240", "gray": "38;5;245",
        "model": "38;5;141", "dir": "38;5;39", "cyan": "38;5;80",
        "green": "38;5;114", "yellow": "38;5;221", "orange": "38;5;208",
        "red": "38;5;203", "gold": "38;5;179", "purple": "38;5;176",
        "bold": "1",
    },
}

# Mutable module state, rebound by apply_config().
CFG: dict = {}
C: dict = {}
GLYPHS: dict = {}
WIDE: frozenset = frozenset()


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, val in (over or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def config_path() -> str | None:
    """First existing config file, or None."""
    explicit = os.environ.get(CONFIG_ENV)
    if explicit:
        path = os.path.expanduser(explicit)
        return path if os.path.exists(path) else None
    for cand in CONFIG_SEARCH:
        path = os.path.expanduser(cand)
        if os.path.exists(path):
            return path
    return None


def load_config(path: str | None = None) -> dict:
    """DEFAULTS merged with the user's TOML. Never raises."""
    path = path if path is not None else config_path()
    if not path:
        return _deep_merge(DEFAULTS, {})
    try:
        import tomllib
        with open(path, "rb") as fh:
            return _deep_merge(DEFAULTS, tomllib.load(fh))
    except Exception:
        # A broken config must not take the status line down with it.
        if os.environ.get(DEBUG_ENV):
            import traceback
            traceback.print_exc(file=sys.stderr)
        return _deep_merge(DEFAULTS, {})


def apply_config(cfg: dict) -> None:
    global CFG, C, GLYPHS, WIDE
    CFG = cfg
    C = {k: f"\033[{v}m" for k, v in cfg["colors"].items()}
    GLYPHS = cfg["glyphs"]
    WIDE = frozenset(cfg["layout"].get("wide_glyphs") or ())


apply_config(_deep_merge(DEFAULTS, {}))


# ------------------------------------------------------------------ output ---
def c(color: str, text) -> str:
    if text == "" or text is None:
        return ""
    return f"{C.get(color, '')}{text}{C['reset']}"


def link(url: str | None, text: str) -> str:
    if not url:
        return text
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


# ------------------------------------------------------------------- width ---
_ZERO_WIDTH = frozenset(
    {0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0xFEFF}
)

# Codepoints with Emoji_Presentation=Yes render two cells even though their
# East_Asian_Width is Neutral. Abridged to the ranges that actually occur in
# terminal UI text.
_EMOJI_WIDE = (
    (0x231A, 0x231B), (0x23E9, 0x23EC), (0x23F0, 0x23F0), (0x23F3, 0x23F3),
    (0x25FD, 0x25FE), (0x2614, 0x2615), (0x2648, 0x2653), (0x267F, 0x267F),
    (0x2693, 0x2693), (0x26A1, 0x26A1), (0x26AA, 0x26AB), (0x26BD, 0x26BE),
    (0x26C4, 0x26C5), (0x26CE, 0x26CE), (0x26D4, 0x26D4), (0x26EA, 0x26EA),
    (0x26F2, 0x26F3), (0x26F5, 0x26F5), (0x26FA, 0x26FA), (0x26FD, 0x26FD),
    (0x2705, 0x2705), (0x270A, 0x270B), (0x2728, 0x2728), (0x274C, 0x274C),
    (0x274E, 0x274E), (0x2753, 0x2755), (0x2757, 0x2757), (0x2795, 0x2797),
    (0x27B0, 0x27B0), (0x27BF, 0x27BF), (0x2B1B, 0x2B1C), (0x2B50, 0x2B50),
    (0x2B55, 0x2B55), (0x1F004, 0x1F004), (0x1F0CF, 0x1F0CF),
    (0x1F18E, 0x1F18E), (0x1F191, 0x1F19A), (0x1F1E6, 0x1F1FF),
    (0x1F201, 0x1F202), (0x1F21A, 0x1F21A), (0x1F22F, 0x1F22F),
    (0x1F232, 0x1F236), (0x1F238, 0x1F23A), (0x1F250, 0x1F251),
    (0x1F300, 0x1F320), (0x1F32D, 0x1F335), (0x1F337, 0x1F37C),
    (0x1F37E, 0x1F393), (0x1F3A0, 0x1F3CA), (0x1F3CF, 0x1F3D3),
    (0x1F3E0, 0x1F3F0), (0x1F3F4, 0x1F3F4), (0x1F3F8, 0x1F43E),
    (0x1F440, 0x1F440), (0x1F442, 0x1F4FC), (0x1F4FF, 0x1F53D),
    (0x1F54B, 0x1F54E), (0x1F550, 0x1F567), (0x1F5A4, 0x1F5A4),
    (0x1F5FB, 0x1F64F), (0x1F680, 0x1F6C5), (0x1F6CC, 0x1F6CC),
    (0x1F6D0, 0x1F6D2), (0x1F6D5, 0x1F6D7), (0x1F6EB, 0x1F6EC),
    (0x1F6F4, 0x1F6FC), (0x1F7E0, 0x1F7EB), (0x1F90C, 0x1F93A),
    (0x1F93C, 0x1F945), (0x1F947, 0x1F978), (0x1F97A, 0x1F9CB),
    (0x1F9CD, 0x1F9FF), (0x1FA70, 0x1FA74), (0x1FA78, 0x1FA7A),
    (0x1FA80, 0x1FA86), (0x1FA90, 0x1FAA8), (0x1FAB0, 0x1FAB6),
    (0x1FAC0, 0x1FAC2), (0x1FAD0, 0x1FAD6),
)


def _emoji_wide(cp: int) -> bool:
    lo, hi = 0, len(_EMOJI_WIDE) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        start, end = _EMOJI_WIDE[mid]
        if cp < start:
            hi = mid - 1
        elif cp > end:
            lo = mid + 1
        else:
            return True
    return False


def cell_width(ch: str) -> int:
    """Terminal cells one character occupies."""
    if ch in WIDE:
        return 2
    cp = ord(ch)
    if cp < 32 or 0x7F <= cp < 0xA0:
        return 0
    if cp in _ZERO_WIDTH or unicodedata.combining(ch):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    if _emoji_wide(cp):
        return 2
    return 1


def display_width(s: str) -> int:
    """Visible cell width, skipping ANSI SGR and OSC-8 hyperlink sequences."""
    width = 0
    last = 0
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\033":
            if s.startswith("\033]", i):                    # OSC ... ST | BEL
                end = s.find("\033\\", i)
                if end != -1:
                    i = end + 2
                else:
                    bel = s.find("\a", i)
                    i = n if bel == -1 else bel + 1
            elif s.startswith("\033[", i):                   # CSI ... final
                j = i + 2
                while j < n and not ("@" <= s[j] <= "~"):
                    j += 1
                i = min(j + 1, n)
            else:
                i += 2
            continue
        if ch == "\ufe0f":        # VS16 promotes the previous glyph to emoji
            if last == 1:
                width += 1
                last = 2
            i += 1
            continue
        if ch == "\ufe0e":        # VS15 forces text presentation
            i += 1
            continue
        last = cell_width(ch)
        width += last
        i += 1
    return width


# -------------------------------------------------------------------- util ---
def dig(obj, *path, default=None):
    for key in path:
        if not isinstance(obj, dict) or key not in obj:
            return default
        obj = obj[key]
    return obj if obj is not None else default


def num(value, default=None):
    """Coerce to float, tolerating the junk a host might hand us."""
    if value is None or isinstance(value, bool):
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return default if out != out else out          # reject NaN


def short_num(n) -> str:
    n = num(n)
    if n is None:
        return "?"
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


def dur(seconds) -> str:
    seconds = max(0, int(num(seconds, 0)))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d{h}h"
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m"


def pct_color(pct) -> str:
    t = CFG["thresholds"]
    pct = num(pct, 0)
    if pct >= t["red"]:
        return "red"
    if pct >= t["orange"]:
        return "orange"
    if pct >= t["yellow"]:
        return "yellow"
    return "green"


_EIGHTHS = "▏▎▍▌▋▊▉"          # 1/8 .. 7/8 of a cell


def make_bar(pct, width=None) -> str:
    """Usage bar with optional sub-cell resolution."""
    bcfg = CFG["bar"]
    width = bcfg["width"] if width is None else width
    if width <= 0:
        return ""
    pct = max(0.0, min(100.0, num(pct, 0)))
    color = pct_color(pct)
    full_ch, empty_ch = bcfg["full"], bcfg["empty"]

    if not bcfg.get("partial", True):
        filled = int(round(pct / 100.0 * width))
        return c(color, full_ch * filled) + c("dim", empty_ch * (width - filled))

    cells = pct / 100.0 * width
    full = int(cells)
    part = ""
    if full < width:
        eighths = int((cells - full) * 8)
        if eighths == 0 and full == 0 and pct > 0 and bcfg.get("min_sliver", True):
            eighths = 1
        if eighths:
            part = _EIGHTHS[eighths - 1]
    empty = width - full - (1 if part else 0)
    return c(color, full_ch * full + part) + c("dim", empty_ch * max(0, empty))


def home_path(path: str) -> str:
    home = os.path.expanduser("~")
    if path == home:
        return "~"
    if path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def compact_path(path: str, keep: int = 3) -> str:
    disp = home_path(path)
    parts = disp.split(os.sep)
    if len(parts) <= keep + 1:
        return disp
    return os.sep.join(["…"] + parts[-keep:])


def to_epoch(value):
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            ts = float(value)
            return ts / 1000.0 if ts > 1e11 else ts
        text = str(value).strip().replace("Z", "+00:00")
        return datetime.fromisoformat(text).timestamp()
    except Exception:
        return None


def run(args, cwd=None, timeout=1.5):
    try:
        p = subprocess.run(args, cwd=cwd, timeout=timeout,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return p.stdout.decode("utf-8", "replace") if p.returncode == 0 else None
    except Exception:
        return None


# -------------------------------------------------------------- git cache ---
def _cache_dir() -> str:
    base = os.environ.get("XDG_RUNTIME_DIR") or os.environ.get("TMPDIR")
    if not base or not os.path.isdir(base):
        # tempfile drags in shutil/fnmatch/re (~5 ms); only pay that off-path.
        if os.path.isdir("/tmp"):
            base = "/tmp"
        else:
            import tempfile
            base = tempfile.gettempdir()
    path = os.path.join(base, "claude-statusline")
    os.makedirs(path, exist_ok=True)
    return path


def _cache_file(root: str) -> str:
    tag = hashlib.sha1(root.encode("utf-8", "replace")).hexdigest()[:16]
    return os.path.join(_cache_dir(), f"git-{tag}.json")


def _repo_key(gitdir: str) -> str:
    """Cheap fingerprint that changes on commit / checkout / stage / merge.

    Worktree edits do not move these mtimes, so the TTL remains the real
    freshness bound; this key exists to invalidate *early* on ref changes.
    """
    parts = []
    for name in ("index", "HEAD", "MERGE_HEAD", "rebase-merge", "rebase-apply"):
        try:
            parts.append(f"{name}:{os.stat(os.path.join(gitdir, name)).st_mtime_ns}")
        except OSError:
            parts.append(f"{name}:-")
    return "|".join(parts)


def _cache_read(path: str, key: str):
    try:
        with open(path) as fh:
            blob = json.load(fh)
    except Exception:
        return None
    if blob.get("key") != key:
        return None
    gcfg = CFG["git"]
    ttl = gcfg["cache_ttl"]
    took = num(blob.get("took"), 0.0)
    if took > gcfg["slow_threshold"]:
        # Expensive repo: back off hard rather than stall every refresh.
        ttl = max(ttl, took * gcfg["slow_backoff"])
    if time.time() - num(blob.get("ts"), 0.0) > ttl:
        return None
    return blob.get("data")


def _cache_write(path: str, key: str, data, took: float) -> None:
    try:
        tmp = f"{path}.{os.getpid()}"
        with open(tmp, "w") as fh:
            json.dump({"key": key, "ts": time.time(), "took": took,
                       "data": data}, fh)
        os.replace(tmp, path)          # atomic; concurrent refreshes are safe
    except Exception:
        pass


# --------------------------------------------------------------------- git ---
def git_info(cwd: str):
    if not CFG["git"]["enabled"]:
        return None
    timeout = CFG["git"]["timeout"]
    top = run(["git", "rev-parse", "--path-format=absolute",
               "--show-toplevel", "--git-dir"], cwd=cwd, timeout=timeout)
    if not top:
        return None
    lines = top.strip().splitlines()
    if len(lines) < 2:
        return None
    root, gitdir = lines[0], lines[1]

    cache, key = _cache_file(root), _repo_key(gitdir)
    hit = _cache_read(cache, key)
    if hit is not None:
        return hit

    info = {"root": root, "gitdir": gitdir, "branch": None, "upstream": None,
            "ahead": 0, "behind": 0, "staged": 0, "dirty": 0, "untracked": 0,
            "conflict": 0, "stash": 0, "state": None, "sha": None,
            "last_commit": None}

    started = time.time()
    out = run(["git", "--no-optional-locks", "status", "--porcelain=v2",
               "--branch", "--untracked-files=normal"], cwd=cwd,
              timeout=max(timeout, 2.0))
    if out is None:
        return info
    for line in out.splitlines():
        if line.startswith("# branch.head "):
            head = line[14:].strip()
            info["branch"] = None if head == "(detached)" else head
        elif line.startswith("# branch.oid "):
            info["sha"] = line[13:].strip()[:7]
        elif line.startswith("# branch.upstream "):
            info["upstream"] = line[18:].strip()
        elif line.startswith("# branch.ab "):
            for tok in line[12:].split():
                if tok.startswith("+"):
                    info["ahead"] = int(tok[1:])
                elif tok.startswith("-"):
                    info["behind"] = int(tok[1:])
        elif line.startswith("u "):
            info["conflict"] += 1
        elif line.startswith("? "):
            info["untracked"] += 1
        elif line[:2] in ("1 ", "2 "):
            xy = line[2:4]
            if xy[0] != ".":
                info["staged"] += 1
            if xy[1] != ".":
                info["dirty"] += 1

    try:
        with open(os.path.join(gitdir, "logs", "refs", "stash")) as fh:
            info["stash"] = sum(1 for _ in fh)
    except Exception:
        pass

    def exists(*p):
        return os.path.exists(os.path.join(gitdir, *p))

    if exists("rebase-merge") or exists("rebase-apply"):
        info["state"] = "REBASE"
    elif exists("MERGE_HEAD"):
        info["state"] = "MERGE"
    elif exists("CHERRY_PICK_HEAD"):
        info["state"] = "CHERRY-PICK"
    elif exists("REVERT_HEAD"):
        info["state"] = "REVERT"
    elif exists("BISECT_LOG"):
        info["state"] = "BISECT"

    dirty = info["staged"] or info["dirty"] or info["conflict"]
    if CFG["features"]["last_commit"] and dirty:
        ct = run(["git", "--no-optional-locks", "log", "-1", "--format=%ct"],
                 cwd=cwd, timeout=timeout)
        if ct and ct.strip().isdigit():
            info["last_commit"] = int(ct.strip())

    _cache_write(cache, key, info, time.time() - started)
    return info


def repo_url(data) -> str | None:
    if not CFG["features"]["repo_links"]:
        return None
    host = dig(data, "workspace", "repo", "host")
    owner = dig(data, "workspace", "repo", "owner")
    name = dig(data, "workspace", "repo", "name")
    if host and owner and name:
        return f"https://{host}/{owner}/{name}"
    return None


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


# ---------------------------------------------------------------- PR badge ---
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


# ------------------------------------------------------------ rate limits ---
def _norm_key(key) -> str:
    """fiveHour / five-hour / FiveHour -> five_hour."""
    out = []
    prev_lower = False
    for ch in str(key):
        if ch.isupper() and prev_lower:
            out.append("_")
        out.append(ch.lower())
        prev_lower = ch.islower() or ch.isdigit()
    return "".join(out).replace("-", "_")


def find_windows(data):
    """Locate the 5h / 7d windows, tolerating key-name and shape variants."""
    node = data.get("rate_limits") or data.get("rateLimits") or data
    found = {}

    def take(slot, obj, label=None):
        if not isinstance(obj, dict) or slot in found:
            return
        pct = num(obj.get("used_percentage", obj.get("usedPercentage")))
        if pct is None:
            return
        found[slot] = {"pct": pct, "label": label,
                       "resets_at": obj.get("resets_at", obj.get("resetsAt"))}

    def classify(key, obj):
        k = _norm_key(key)
        if "five_hour" in k or k in ("5h", "five", "session"):
            take("5h", obj)
        elif "seven_day" in k or "week" in k or k in ("7d", "seven"):
            model = next((m for m in ("opus", "sonnet", "haiku") if m in k), None)
            take("7d_model" if model else "7d", obj, model)
        else:
            return False
        return True

    def walk(obj, depth=0):
        if depth > 3:
            return
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    tag = item.get("window") or item.get("type") or ""
                    if not classify(tag, item):
                        walk(item, depth + 1)
            return
        if not isinstance(obj, dict):
            return
        for key, val in obj.items():
            if isinstance(val, (dict, list)) and not classify(key, val):
                walk(val, depth + 1)

    walk(node)
    if "7d" not in found and "7d_model" in found:
        found["7d"] = found["7d_model"]
    return found


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


# ------------------------------------------------------- context and cache ---
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


# ------------------------------------------------------------------ render ---
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


def render(data, cols=None) -> str:
    if not isinstance(data, dict):
        data = {}
    cwd = (dig(data, "workspace", "current_dir")
           or data.get("cwd") or os.getcwd())
    worktree = dig(data, "workspace", "git_worktree")
    avail = usable_width(cols)
    sep = c("dim", CFG["layout"]["separator"])
    line1 = assemble_line1(build_line1(data, cwd, worktree), avail, sep)
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


# --------------------------------------------------------------- CLI modes ---
SAMPLE = {
    "model": {"display_name": "Opus 5 (1M context)", "id": "claude-opus-5[1m]"},
    "effort": {"level": "high"},
    "session_name": "demo session",
    "workspace": {"current_dir": os.path.expanduser("~/Projects/demo"),
                  "repo": {"host": "github.com", "owner": "octocat",
                           "name": "demo"}},
    "cost": {"total_cost_usd": 12.5, "total_duration_ms": 3_600_000,
             "total_lines_added": 420, "total_lines_removed": 69},
    "context_window": {"used_percentage": 38, "total_input_tokens": 380_000,
                       "context_window_size": 1_000_000},
    "prompt_cache": {"warm": True, "hit_ratio": 0.98},
    "rate_limits": {
        "five_hour": {"used_percentage": 62,
                      "resets_at": time.time() + 2 * 3600},
        "seven_day": {"used_percentage": 24,
                      "resets_at": time.time() + 4 * 86400},
    },
}


def cmd_ruler(cols=None) -> str:
    """Two rulers for calibrating layout.right_margin.

    Row 1 counts columns from the left; row 2 counts *down* to the right edge,
    so the last digit you can actually see is the number of columns the host
    clipped. Add that to right_margin.
    """
    if cols is None:
        try:
            cols = int(os.environ.get("COLUMNS") or 0)
        except ValueError:
            cols = 0
        cols = cols or CFG["layout"]["fallback_columns"]
    forward = "".join(
        str((i // 10) % 10) if i % 10 == 0 else ("+" if i % 5 == 0 else "·")
        for i in range(cols)
    )
    backward = "".join(str((cols - 1 - i) % 10) for i in range(cols))
    return forward + "\n" + backward


def cmd_doctor(cols=None) -> str:
    path = config_path()
    try:
        env_cols = int(os.environ.get("COLUMNS") or 0)
    except ValueError:
        env_cols = 0
    lines = [
        f"claude-statusline {__version__}",
        f"  python          {sys.version.split()[0]}",
        f"  config          {path or '(defaults; none found)'}",
        f"  searched        {', '.join(CONFIG_SEARCH)}",
        f"  COLUMNS         {env_cols or '(unset)'}"
        f"  →  fallback {CFG['layout']['fallback_columns']}",
        f"  right_margin    {CFG['layout']['right_margin']}",
        f"  usable width    {usable_width(cols)}",
        f"  bar             width={CFG['bar']['width']} "
        f"partial={CFG['bar']['partial']}",
        f"  git             enabled={CFG['git']['enabled']} "
        f"ttl={CFG['git']['cache_ttl']}s",
        f"  cache dir       {_cache_dir()}",
        f"  payload dump    {os.environ.get(DUMP_ENV) or '(off; set ' + DUMP_ENV + ')'}",
    ]
    try:
        entries = [f for f in os.listdir(_cache_dir()) if f.startswith("git-")]
        lines.append(f"  cached repos    {len(entries)}")
    except Exception:
        pass
    return "\n".join(lines)


def cmd_dump_config() -> str:
    def fmt(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, list):
            return "[" + ", ".join(fmt(x) for x in v) + "]"
        return json.dumps(str(v), ensure_ascii=False)

    out = [f"# claude-statusline {__version__} — effective configuration"]
    for section, body in CFG.items():
        out.append(f"\n[{section}]")
        for key, val in body.items():
            out.append(f"{key} = {fmt(val)}")
    return "\n".join(out)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    apply_config(load_config())

    if argv:
        flag = argv[0]
        if flag == "--version":
            print(f"claude-statusline {__version__}")
            return 0
        if flag == "--doctor":
            print(cmd_doctor())
            return 0
        if flag == "--ruler":
            print(cmd_ruler())
            return 0
        if flag == "--dump-config":
            print(cmd_dump_config())
            return 0
        if flag == "--demo":
            print(render(SAMPLE))
            return 0
        if flag in ("-h", "--help"):
            print(__doc__)
            return 0
        print(f"unknown flag: {flag}\n\n{__doc__}", file=sys.stderr)
        return 2

    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}

    dump = os.environ.get(DUMP_ENV)
    if dump and raw:
        try:
            with open(os.path.expanduser(dump), "w") as fh:
                fh.write(raw)
        except Exception:
            pass

    try:
        sys.stdout.write(render(data))
    except Exception:
        # A status line that degrades beats one that vanishes.
        if os.environ.get(DEBUG_ENV):
            import traceback
            traceback.print_exc(file=sys.stderr)
        sys.stdout.write(fallback(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
