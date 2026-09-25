"""Start and stop the desktop field overlay: a transparent `kitten panel` in a screen corner."""
import json
import os
import re
import subprocess
import sys

from .. import home

FIELD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "field.py")
CONF = os.path.join(home(), "field.json")
DEFAULTS = {"width": 720, "height": 405, "right": 60, "bottom": 400, "enabled": False}
_PATTERN = f"^{re.escape(sys.executable)} {re.escape(FIELD)}$|^python3 {re.escape(FIELD)}$"


def conf():
    out = dict(DEFAULTS)
    try:
        with open(CONF) as fh:
            out.update(json.load(fh))
    except (OSError, ValueError):
        pass
    return out


def screen_size():
    try:
        out = subprocess.run(["kscreen-doctor", "-o"], capture_output=True, text=True).stdout
        m = re.search(r"Geometry: \d+,\d+ (\d+)x(\d+)", re.sub(r"\x1b\[[0-9;]*m", "", out))
        if m:
            return int(m.group(1)), int(m.group(2))
    except FileNotFoundError:
        pass
    return 1920, 1080


def running():
    return subprocess.run(["pgrep", "-f", _PATTERN], capture_output=True).returncode == 0


def stop():
    subprocess.run(["pkill", "-f", _PATTERN])


def start():
    if running():
        return
    cfg = conf()
    sw, sh = screen_size()
    w, h = cfg["width"], cfg["height"]
    subprocess.Popen(
        ["kitten", "panel", "--edge=none", "--layer=overlay", "--focus-policy=not-allowed",
         f"--columns={w}px", f"--lines={h}px",
         f"--margin-left={sw - w - cfg['right']}", f"--margin-top={sh - h - cfg['bottom']}",
         "--app-id=claude-quest", "-o", "background_opacity=0", "-o", "window_padding_width=0",
         "python3", FIELD],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)


def field(action="start"):
    if action == "stop":
        stop()
    elif action == "toggle":
        stop() if running() else start()
    else:
        start()


def autostart():
    if conf().get("enabled"):
        start()
