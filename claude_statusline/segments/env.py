"""Where the session is running, and whether it is still running."""
from __future__ import annotations

import os

from ..config import CFG, GLYPHS
from ..util import num
from . import Opt, Segment, register


def _venv():
    venv = os.environ.get("VIRTUAL_ENV") or os.environ.get("CONDA_DEFAULT_ENV")
    return os.path.basename(venv) if venv else ""


def _remote():
    return bool(os.environ.get("SSH_CONNECTION") or os.path.exists("/.dockerenv"))


@register
class Env(Segment):
    name = "env"
    doc = "Active virtualenv, and the hostname when the session is remote."
    priority = 50
    format = "<cyan>[{venv_glyph} {venv}][ {host_glyph} {host}]</cyan>"
    fields = {"venv": "virtualenv or conda env name", "venv_glyph": "the env glyph",
              "host": "hostname, only over SSH or in a container", "host_glyph": "the host glyph"}

    def fields_at(self, ctx, opts, level):
        venv = _venv()
        host = os.uname().nodename if _remote() else ""
        if not venv and not host:
            return None
        return {"venv": venv, "venv_glyph": GLYPHS["env"], "host": host, "host_glyph": GLYPHS["host"]}


@register
class Host(Segment):
    name = "host"
    doc = "The machine's hostname."
    priority = 45
    format = "<cyan>{glyph} {host}</cyan>"
    options = {"always": Opt(bool, False, "Show even when not over SSH or in a container.")}
    fields = {"glyph": "the host glyph", "host": "hostname"}

    def fields_at(self, ctx, opts, level):
        if not (opts["always"] or _remote()):
            return None
        return {"glyph": GLYPHS["host"], "host": os.uname().nodename}


@register
class Heartbeat(Segment):
    name = "heartbeat"
    doc = ("A tick that advances every refresh. Each refresh is a fresh process, "
           "so the frame comes from the wall clock; a stalled bar freezes on one frame.")
    priority = 99
    format = "<tick>{frame}</tick>"
    options = {
        "frames": Opt(str, "", "One glyph per frame; empty means [glyphs].heartbeat_frames."),
        "period": Opt(float, 1.0, "Seconds per frame; match refreshInterval."),
        "color": Opt(str, "dim", "A [colors] key for the tick."),
    }
    fields = {"frame": "the current frame"}
    colors = {"tick": "the configured `color`"}

    def fields_at(self, ctx, opts, level):
        frames = opts["frames"] or GLYPHS.get("heartbeat_frames") or ""
        if not frames:
            return None
        period = num(opts["period"], 1.0) or 1.0
        return {"frame": frames[int(ctx.now / period) % len(frames)]}

    def colors_at(self, ctx, opts, fields):
        return {"tick": CFG["colors"].get(opts["color"], "")}
