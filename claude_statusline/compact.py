"""How many more turns fit before Claude Code compacts the conversation.

The bar sees the context's size at each refresh, and the activity hooks say
when a turn ends. So once per finished turn this keeps the tokens in use, in
a small file per session in the runtime directory. The typical turn's growth
is the median of the last few; the turns left are the room up to the
compaction point divided by that. The compaction point follows Claude
Code's own rules (compact_at). When the tokens drop (a compaction, or
/clear) the history starts again.
"""
from __future__ import annotations

import marshal
import os

KEEP = 8                 # turns remembered
NEED = 2                 # turns of growth needed before guessing
BIG_AT = 967_000         # where Claude Code compacts a native 1M window by default


def _env(name):
    try:
        return float(os.environ.get(name) or 0)
    except ValueError:
        return 0.0


def compact_at(opt, size):
    """Tokens at which Claude Code compacts: the option, else CLAUDE_CODE_AUTO_COMPACT_WINDOW,
    else the model's window (about 967K for a 1M one), lowered by
    CLAUDE_CODE_AUTOCOMPACT_PCT_OVERRIDE. Never past the window."""
    at = float(opt) if opt and opt > 0 else (_env("CLAUDE_CODE_AUTO_COMPACT_WINDOW") or
                                             (BIG_AT if size >= 1_000_000 else size))
    pct = _env("CLAUDE_CODE_AUTOCOMPACT_PCT_OVERRIDE")
    if 0 < pct < 100:
        at = at * pct / 100.0
    return min(at, size)


def _path(sid):
    from .config import runtime_dir
    sid = "".join(ch for ch in str(sid) if ch.isalnum() or ch in "-_")[:64] or "none"
    return os.path.join(runtime_dir(), f"turns-{sid}.bin")


def record(history, stop, tokens):
    """Fold the tokens at the end of the turn that ended at `stop` into `history`, a list of
    [stop, tokens]. Returns (history, changed)."""
    if history and stop <= history[-1][0]:
        return history, False
    if history and tokens < history[-1][1]:
        return [[stop, tokens]], True          # compacted or cleared: start over
    return (history + [[stop, tokens]])[-KEEP:], True


def per_turn(history):
    """The typical growth of a turn, in tokens, or None with too little to go on."""
    grew = sorted(b[1] - a[1] for a, b in zip(history, history[1:]) if b[1] > a[1])
    if len(grew) < NEED:
        return None
    return grew[len(grew) // 2]


def turns_left(tokens, at, growth):
    if not growth or not at:
        return None
    return max(0, int((at - tokens) // growth))


def history(sid, stop, tokens, write=True):
    """The session's history, with this turn's end folded in."""
    path = _path(sid)
    try:
        with open(path, "rb") as fh:
            h = marshal.loads(fh.read())
        h = [list(x) for x in h] if isinstance(h, list) else []
    except Exception:
        h = []
    if not stop or not tokens:
        return h
    h, changed = record(h, stop, tokens)
    if changed and write:
        try:
            tmp = f"{path}.{os.getpid()}"
            with open(tmp, "wb") as fh:
                marshal.dump(h, fh)
            os.replace(tmp, path)
        except OSError:
            pass
    return h
