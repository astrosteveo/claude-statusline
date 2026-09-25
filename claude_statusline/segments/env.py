"""Where the session runs, and proof that the bar is alive."""
from __future__ import annotations

import os

from ..icons import HEARTBEAT_FRAMES
from ..util import num
from . import Opt, Segment, register


def _venv():
    venv = os.environ.get("VIRTUAL_ENV") or os.environ.get("CONDA_DEFAULT_ENV")
    return os.path.basename(venv.rstrip("/")) if venv else ""


def _remote():
    return bool(os.environ.get("SSH_CONNECTION") or os.path.exists("/.dockerenv")
                or os.environ.get("container"))


def _hostname():
    try:
        return os.uname().nodename.split(".")[0]
    except (AttributeError, OSError):
        return ""


@register
class Env(Segment):
    name = "env"
    doc = "The active virtualenv or conda env, and the host when the session is remote."
    priority = 50
    tone = "teal"
    format = "[<teal>{venv}</teal>][ <subtext>@{host}</subtext>]"
    fields_doc = {"venv": "virtualenv or conda env name", "host": "hostname, over SSH or in a container"}

    def fields(self, ctx, opts, level):
        venv = _venv()
        host = _hostname() if _remote() else ""
        return {"venv": venv, "host": host} if (venv or host) else None


@register
class Host(Segment):
    name = "host"
    doc = "The machine's name (only over SSH or in a container, unless `always`)."
    priority = 45
    tone = "teal"
    format = "<teal>{host}</teal>"
    options = {"always": Opt(bool, False, "Show it on the local machine too."),
               "user": Opt(bool, False, "Prefix the user name.")}
    fields_doc = {"host": "hostname", "user": "user name"}

    def fields(self, ctx, opts, level):
        if not (opts["always"] or _remote()):
            return None
        user = os.environ.get("USER") or ""
        host = _hostname()
        return {"host": f"{user}@{host}" if opts["user"] and user else host, "user": user}


@register
class Heartbeat(Segment):
    name = "heartbeat"
    doc = ("A debugging aid, off unless placed: a tick that moves on every refresh. The frame comes "
           "from the clock, so a bar that has stopped refreshing freezes on one frame.")
    priority = 99
    tone = "muted"
    bare = True
    format = "<tick>{frame}</tick>"
    options = {
        "frames": Opt(str, "dots", "A named set (" + ", ".join(HEARTBEAT_FRAMES) +
                      ") or a string of one-cell glyphs."),
        "period": Opt(float, 1.0, "Seconds per frame; match refreshInterval."),
        "color": Opt(str, "muted", "Theme role or #hex for the tick."),
    }
    fields_doc = {"frame": "the current frame"}
    colors_doc = {"tick": "the configured `color`"}

    def fields(self, ctx, opts, level):
        frames = opts["frames"] or ctx.comp.get("glyphs", {}).get("heartbeat_frames") or "dots"
        frames = HEARTBEAT_FRAMES.get(frames, frames)
        if not frames:
            return None
        period = num(opts["period"], 1.0) or 1.0
        return {"frame": frames[int(ctx.now / period) % len(frames)]}

    def colors(self, ctx, opts, f):
        return {"tick": opts["color"] or "muted"}
