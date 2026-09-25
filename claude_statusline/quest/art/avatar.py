#!/usr/bin/env python3
"""Upload the pet's whole repertoire to a kitty window, for Unicode placeholders.

    python3 -m claude_statusline.quest.art.avatar --tty /dev/pts/5 --base 200 --cols 8 --rows 3

Every action in ACTIONS becomes its own looping animation, stored by kitty
under image id base + index; the statusline picks one by colouring its
placeholder cells with that id, so switching is instant and writes nothing
to the terminal. The pet's stage and gear come from the save. Each escape
goes out in a single write() so it cannot interleave with Claude Code's own
output. Frames are cached on disk by everything that shapes them.

    python3 -m claude_statusline.quest.art.avatar --png sheet.png [--stage drake] [--action look] [--gear all]
"""
import argparse
import array
import base64
import fcntl
import hashlib
import io
import json
import math
import os
import random
import shutil
import sys
import termios

import cairo

from .sprites import Pose, draw_front, draw_side, ellipse, front_hand, star  # noqa: E402

TAU = 2 * math.pi
# The order is the id layout, published in the manifest for the statusline.
ACTIONS = ["stand", "walk", "look", "lookaround", "hop", "sleep", "work", "perk", "yourturn",
           "levelup", "achievement", "loot", "battle", "victory", "quest", "eat", "strut"]
BIG = {"egg": 0.8, "hatchling": 0.85, "lizard": 1.0, "drake": 1.2, "wyrm": 1.45}
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
                     "claude-statusline", "avatar")
MANIFEST = os.path.join(CACHE, "manifest.json")
SAMPLE_GEAR = {
    "head": {"kind": "wizard", "color": "#6c4bd1", "accent": "#ffd966"},
    "hand": {"kind": "sword", "color": "#7fd4ff", "accent": "#ffd966", "glow": True},
    "back": {"kind": "cape", "color": "#3b2a6b", "accent": "#ffd966", "stars": True},
    "feet": {"kind": "boots", "color": "#7a4a2a"},
    "charm": {"kind": "amulet", "color": "#ff9f1c", "glow": True},
}


def blink(k, *moments):
    return "blink" if any(abs(k - m) < 0.025 for m in moments) else "open"


# ------------------------------------------------------------------ actions
# Each draws the pet (and any prop) in pet space for loop position k in [0, 1).

def act_stand(cr, t, k, stage, gear):
    cr.scale(1, 1 + 0.025 * math.sin(k * TAU * 2))
    draw_side(cr, stage, Pose(t, "still", eyes=blink(k, 0.3, 0.8)), gear)


def act_walk(cr, t, k, stage, gear):
    draw_side(cr, stage, Pose(t, "walk", eyes=blink(k, 0.6)), gear)


def act_look(cr, t, k, stage, gear):
    look = [0, 0, -1, -1, 0, 0, 1, 1, 0, 0][int(k * 10)]
    draw_front(cr, stage, Pose(t, eyes=blink(k, 0.45, 0.95), look=look,
                               tilt=0.08 * math.sin(k * TAU), carry="hand"), gear)


def act_lookaround(cr, t, k, stage, gear):
    if k >= 0.5:
        cr.scale(-1, 1)
    draw_side(cr, stage, Pose(t, "still", eyes=blink(k, 0.25, 0.75)), gear)


def act_hop(cr, t, k, stage, gear):
    cr.translate(0, -abs(math.sin(k * TAU * 2)) * 12)
    draw_side(cr, stage, Pose(t, "hop", mouth="open"), gear)


def act_sleep(cr, t, k, stage, gear):
    cr.scale(1, 1 + 0.03 * math.sin(k * TAU))
    draw_side(cr, stage, Pose(t * 0.4, "sleep", eyes="closed"), gear)


def act_work(cr, t, k, stage, gear):
    cr.translate(0, -abs(math.sin(k * TAU * 4)) * 5)
    draw_side(cr, stage, Pose(t, "run"), gear)


def act_perk(cr, t, k, stage, gear):
    cr.translate(0, -abs(math.sin(k * TAU)) * 4)
    draw_front(cr, stage, Pose(t, mouth="o", arms=(0.1, 0.1), carry="hand"), gear)


def act_yourturn(cr, t, k, stage, gear):
    wave = 0.75 + 0.2 * math.sin(k * TAU * 4) if 0.55 < k < 0.9 else 0.0
    draw_front(cr, stage, Pose(t, eyes=blink(k, 0.3), tilt=0.15 * math.sin(k * TAU),
                               arms=(0.0, wave), carry="hand"), gear)


def act_levelup(cr, t, k, stage, gear):
    cr.translate(0, -abs(math.sin(k * TAU * 2)) * 16)
    draw_front(cr, stage, Pose(t, arms=(1, 1), mouth="open", sparkle=True, carry="hand"), gear)
    cr.set_source_rgba(1, 0.9, 0.4, 0.35 + 0.25 * math.sin(k * TAU * 2))
    cr.set_line_width(2.5)
    cr.arc(0, -30, 30 + 6 * math.sin(k * TAU * 2), 0, TAU)
    cr.stroke()


def act_achievement(cr, t, k, stage, gear):
    cr.translate(0, -abs(math.sin(k * TAU * 2)) * 6)
    draw_front(cr, stage, Pose(t, arms=(0.1, 0.95), mouth="open", carry="back"), gear)
    x, y = front_hand(stage, 0.95)
    trophy(cr, x, y - 9, k)


def act_loot(cr, t, k, stage, gear):
    cr.translate(0, -abs(math.sin(k * TAU)) * 4)
    draw_front(cr, stage, Pose(t, arms=(0.55, 0.55), mouth="o", sparkle=True, carry="back"), gear)
    gem(cr, 0, -27 if stage not in ("egg", "hatchling") else -14, k)


def act_battle(cr, t, k, stage, gear):
    lunge = math.sin(k * TAU * 2)
    cr.translate(-9 + lunge * 6, 0)  # stand back so the weapon stays in frame
    cr.scale(0.85, 0.85)
    cr.rotate(0.06 * max(0, lunge))
    draw_side(cr, stage, Pose(t, "run", mouth="grin", brows=True, carry="mouth"), gear)


def act_victory(cr, t, k, stage, gear):
    cr.translate(0, -abs(math.sin(k * TAU * 2)) * 10)
    pump = 0.8 + 0.2 * math.sin(k * TAU * 2)
    draw_front(cr, stage, Pose(t, arms=(pump, 1.0), mouth="open", sparkle=True, carry="hand"), gear)


def act_quest(cr, t, k, stage, gear):
    cr.translate(0, -abs(math.sin(k * TAU * 2)) * 5)
    draw_front(cr, stage, Pose(t, arms=(0.1, 0.9), mouth="grin", eyes="happy", carry="back"), gear)
    x, y = front_hand(stage, 0.9)
    scroll(cr, x, y - 8, k)


def act_eat(cr, t, k, stage, gear):
    chew = int(k * 8) % 2
    draw_front(cr, stage, Pose(t, arms=(0.45, 0.45), eyes="happy",
                               mouth="o" if chew else "smile", carry="back"), gear)
    small = stage in ("egg", "hatchling")
    cookie(cr, 0, -18 if small else -33, k, bitten=1 + int(k * 3))


def act_strut(cr, t, k, stage, gear):
    cr.translate(0, -abs(math.sin(k * TAU * 2)) * 3)
    draw_front(cr, stage, Pose(t, tilt=0.14 * math.sin(k * TAU), eyes="happy" if k % 0.5 > 0.3 else "open",
                               mouth="grin", arms=(0.0, 0.35), carry="hand"), gear)


# ------------------------------------------------------------------ props (pet space)

def trophy(cr, x, y, k):
    cr.set_source_rgb(1, 0.8, 0.25)
    cr.move_to(x - 7, y - 10)
    cr.line_to(x + 7, y - 10)
    cr.curve_to(x + 7, y, x + 3, y + 2, x, y + 2)
    cr.curve_to(x - 3, y + 2, x - 7, y, x - 7, y - 10)
    cr.fill()
    cr.set_line_width(1.4)
    for side in (-1, 1):
        cr.arc(x + side * 7.5, y - 6, 3, 0, TAU)
        cr.stroke()
    cr.rectangle(x - 1.5, y + 2, 3, 5)
    cr.rectangle(x - 5, y + 7, 10, 3)
    cr.fill()
    cr.set_source_rgba(1, 1, 1, 0.6 + 0.4 * math.sin(k * TAU * 3))
    star(cr, x - 3, y - 6, 2.5)
    cr.fill()


def gem(cr, x, y, k):
    cr.move_to(x, y - 8)
    cr.line_to(x + 7, y - 2)
    cr.line_to(x, y + 7)
    cr.line_to(x - 7, y - 2)
    cr.close_path()
    cr.set_source_rgb(0.35, 0.8, 1)
    cr.fill()
    cr.move_to(x - 7, y - 2)
    cr.line_to(x + 7, y - 2)
    cr.set_source_rgba(1, 1, 1, 0.5)
    cr.set_line_width(0.8)
    cr.stroke()
    cr.set_source_rgba(1, 1, 1, 0.5 + 0.5 * math.sin(k * TAU * 2))
    star(cr, x - 2, y - 3, 3)
    cr.fill()


def scroll(cr, x, y, k):
    unfurl = 7 + 3 * math.sin(k * TAU)
    cr.rectangle(x - 6, y - unfurl, 12, unfurl * 2)
    cr.set_source_rgb(0.96, 0.9, 0.72)
    cr.fill()
    cr.set_source_rgb(0.6, 0.45, 0.3)
    cr.set_line_width(0.7)
    for i in range(3):
        yy = y - unfurl + 3 + i * 3.2
        if yy < y + unfurl - 2:
            cr.move_to(x - 4, yy)
            cr.line_to(x + 4, yy)
            cr.stroke()
    for yy in (y - unfurl, y + unfurl):
        ellipse(cr, x, yy, 7.5, 2.2)
        cr.set_source_rgb(0.85, 0.72, 0.5)
        cr.fill()
    cr.arc(x + 4, y + unfurl - 3, 2, 0, TAU)
    cr.set_source_rgb(0.85, 0.2, 0.25)
    cr.fill()


def cookie(cr, x, y, k, bitten=1):
    bite = min(0.9, 0.3 * bitten)
    cr.move_to(x, y)
    cr.arc(x, y, 7, -math.pi / 2 + bite, -math.pi / 2 - bite + TAU)
    cr.close_path()
    cr.set_source_rgb(0.85, 0.62, 0.35)
    cr.fill()
    cr.set_source_rgb(0.35, 0.2, 0.12)
    for dx, dy in ((-3, 1), (2, 3), (3, -2), (-1, -3)):
        cr.arc(x + dx, y + dy, 1, 0, TAU)
        cr.fill()


# ------------------------------------------------------------------ overlays (screen space)

def _text(cr, s, x, y, size, rgba):
    cr.select_font_face("sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(size)
    cr.set_source_rgba(*rgba)
    cr.move_to(x, y)
    cr.show_text(s)


def _stars_around(cr, k, w, h, s, n, spread=0.4):
    colors = [(1, .85, .3), (1, .5, .7), (.5, .9, 1), (.7, 1, .5), (1, .7, .3)]
    for i in range(n):
        a = k * TAU + i * TAU / n
        r = 0.55 + 0.45 * math.sin(k * TAU * 2 + i)
        cr.set_source_rgba(*colors[i % 5], r)
        star(cr, w / 2 + math.cos(a) * w * spread, h * 0.45 + math.sin(a) * h * 0.32, 5 * s * r)
        cr.fill()


def heart(cr, x, y, r):
    cr.move_to(x, y + r * 0.9)
    cr.curve_to(x - r * 1.6, y - r * 0.2, x - r * 0.6, y - r * 1.4, x, y - r * 0.4)
    cr.curve_to(x + r * 0.6, y - r * 1.4, x + r * 1.6, y - r * 0.2, x, y + r * 0.9)
    cr.close_path()


def overlay(cr, action, k, w, h, s):
    if action == "sleep":
        for i in range(2):
            kk = (k + i / 2) % 1
            _text(cr, "z", w * 0.64 + kk * w * 0.18, h * 0.42 - kk * h * 0.36,
                  (10 + 8 * kk) * s, (1, 1, 1, math.sin(kk * math.pi)))
    elif action == "perk":
        _text(cr, "!", w * 0.72, h * 0.42, 26 * s * (1 + 0.1 * math.sin(k * TAU * 2)), (1, 0.85, 0.3, 1))
    elif action == "yourturn" and k < 0.5:
        _text(cr, "?", w * 0.72, h * 0.38, 20 * s, (1, 1, 1, math.sin(k * 2 * math.pi)))
    elif action == "work":
        for i in range(3):
            kk = (k * 2 + i / 3) % 1
            cr.set_source_rgba(0.8, 0.75, 0.65, 0.5 * (1 - kk))
            cr.arc(w * 0.22 - kk * w * 0.12, h * 0.8 - kk * 6 * s, (3 + 5 * kk) * s, 0, TAU)
            cr.fill()
    elif action in ("levelup", "achievement", "loot"):
        _stars_around(cr, k, w, h, s, 7 if action == "levelup" else 5)
    elif action == "battle":
        lunge = math.sin(k * TAU * 2)
        if lunge > 0.2:
            a = lunge
            cr.set_line_width(2.2 * s)
            cr.set_source_rgba(1, 1, 1, a)
            for i in range(2):
                cr.arc(w * 0.8, h * 0.62 + i * 6 * s, (10 + i * 5) * s, -1.6, 0.1)
                cr.stroke()
            cr.set_source_rgba(1, 0.85, 0.3, a)
            star(cr, w * 0.92, h * 0.5, 5 * s * a)
            cr.fill()
        _text(cr, "!", w * 0.1, h * 0.3, 16 * s, (1, 0.35, 0.3, 0.6 + 0.4 * abs(lunge)))
    elif action == "victory":
        rng = random.Random(7)
        colors = [(1, .85, .3), (1, .5, .7), (.5, .9, 1), (.7, 1, .5), (.8, .6, 1)]
        for i in range(18):
            x0, y0, spin = rng.random(), rng.random(), rng.uniform(2, 6)
            y = ((y0 + k) % 1) * h * 0.9
            cr.save()
            cr.translate(x0 * w, y)
            cr.rotate(spin * k * TAU)
            cr.rectangle(-2 * s, -1 * s, 4 * s, 2 * s)
            cr.set_source_rgb(*colors[i % 5])
            cr.fill()
            cr.restore()
    elif action == "quest":
        a = 0.6 + 0.4 * math.sin(k * TAU * 2)
        cr.set_source_rgba(0.45, 0.9, 0.45, a)
        cr.set_line_width(3 * s)
        cr.move_to(w * 0.12, h * 0.3)
        cr.line_to(w * 0.18, h * 0.38)
        cr.line_to(w * 0.3, h * 0.2)
        cr.stroke()
    elif action == "eat":
        for i in range(3):
            kk = (k + i / 3) % 1
            cr.set_source_rgba(1, 0.45, 0.6, math.sin(kk * math.pi))
            heart(cr, w * (0.3 + 0.2 * i) + math.sin(kk * TAU) * 3 * s, h * 0.35 - kk * h * 0.3, 4 * s)
            cr.fill()
    elif action == "strut":
        for i, (x, y) in enumerate(((0.3, 0.12), (0.72, 0.3), (0.2, 0.55))):
            a = max(0.0, math.sin(k * TAU * 2 + i * 2))
            cr.set_source_rgba(1, 1, 0.8, a)
            star(cr, w * x, h * y, 4 * s * a)
            cr.fill()


ACTION_SPECS = {
    "stand": (TAU, 28, act_stand), "walk": (TAU, 28, act_walk), "look": (5.0, 30, act_look),
    "lookaround": (4.0, 24, act_lookaround), "hop": (math.pi, 20, act_hop),
    "sleep": (TAU, 28, act_sleep), "work": (math.pi / 2, 16, act_work),
    "perk": (2.0, 16, act_perk), "yourturn": (4.0, 28, act_yourturn),
    "levelup": (math.pi, 22, act_levelup), "achievement": (math.pi, 20, act_achievement),
    "loot": (math.pi, 20, act_loot), "battle": (math.pi, 20, act_battle),
    "victory": (math.pi, 20, act_victory), "quest": (math.pi, 20, act_quest),
    "eat": (math.pi, 20, act_eat), "strut": (TAU, 24, act_strut),
}
SIDE_ACTIONS = {"stand", "walk", "lookaround", "hop", "sleep", "work", "battle"}


# ------------------------------------------------------------------ rendering

# How far each hat rises above the head, in head radii.
HAT_RISE = {"wizard": 1.8, "beanie": 1.05, "helm": 0.9, "paper": 0.85, "halo": 0.8,
            "crown": 0.7, "headphones": 0.5, "goggles": 0.0}


def layout(stage, w, h, gear):
    """(scale, ground y) shared by every action, so the pet keeps its size between poses."""
    big = BIG[stage]
    ground = h * 0.86
    rise = HAT_RISE.get((gear.get("head") or {}).get("kind"), 0.0) * 19
    top = (62 + rise + 14) * big          # front view: head, hat and a little jump
    s = min(w / (104 * big), (ground - 2) / top)
    return s, ground


def render(stage, action, i, w, h, gear):
    T, n, fn = ACTION_SPECS[action]
    k = i / n
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surf)
    big = BIG[stage]
    s, ground = layout(stage, w, h, gear)
    cr.save()
    cr.translate(w / 2, ground + 2 * s)
    cr.scale(1, 0.25)
    cr.set_source_rgba(0, 0, 0, 0.28)
    cr.arc(0, 0, 26 * s * big, 0, TAU)
    cr.fill()
    cr.restore()
    side = action in SIDE_ACTIONS
    cr.save()
    cr.translate(w / 2 + (4 * s if side and big >= 1 else 0), ground)
    scale = s if side else s * big
    cr.scale(scale, scale)
    fn(cr, k * T, k, stage, gear)
    cr.restore()
    overlay(cr, action, k, w, h, s)
    surf.flush()
    return surf


def png(surf):
    buf = io.BytesIO()
    surf.write_to_png(buf)
    return buf.getvalue()


def _source_hash():
    here = os.path.dirname(os.path.realpath(__file__))
    h = hashlib.sha1()
    for name in ("avatar.py", "sprites.py", "gear.py"):
        with open(os.path.join(here, name), "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()[:10]


def frames_for(stage, action, w, h, gear):
    """PNG frames for one action, from the disk cache when nothing that shapes them changed."""
    sig = hashlib.sha1(json.dumps(gear, sort_keys=True).encode()).hexdigest()[:10]
    folder = os.path.join(CACHE, f"{_source_hash()}-{stage}-{sig}-{w}x{h}", action)
    _, n, _ = ACTION_SPECS[action]
    paths = [os.path.join(folder, f"{i:03d}.png") for i in range(n)]
    if all(os.path.exists(p) for p in paths):
        out = []
        for p in paths:
            with open(p, "rb") as fh:
                out.append(fh.read())
        return out
    os.makedirs(folder, exist_ok=True)
    out = [png(render(stage, action, i, w, h, gear)) for i in range(n)]
    for p, data in zip(paths, out):
        with open(p + ".tmp", "wb") as fh:
            fh.write(data)
        os.replace(p + ".tmp", p)
    return out


def prune_cache(keep=12):
    try:
        dirs = [os.path.join(CACHE, d) for d in os.listdir(CACHE)
                if os.path.isdir(os.path.join(CACHE, d))]
    except OSError:
        return
    dirs.sort(key=os.path.getmtime, reverse=True)
    for d in dirs[keep:]:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ upload

def cell_size(fd):
    buf = array.array("H", [0, 0, 0, 0])
    fcntl.ioctl(fd, termios.TIOCGWINSZ, buf)
    rows, cols, xpix, ypix = buf
    if not (rows and cols and xpix and ypix):
        return 10, 20
    return xpix / cols, ypix / rows


def apc(fd, head, data=b""):
    """Send one graphics command, chunked, each chunk in a single write()."""
    if not data:
        os.write(fd, b"\x1b_G" + head.encode() + b"\x1b\\")
        return
    payload = base64.standard_b64encode(data)
    chunks = [payload[i:i + 4096] for i in range(0, len(payload), 4096)]
    for n, chunk in enumerate(chunks):
        more = 1 if n < len(chunks) - 1 else 0
        keys = f"{head},m={more}" if n == 0 else f"m={more}"
        os.write(fd, b"\x1b_G" + keys.encode() + b";" + chunk + b"\x1b\\")


def upload(fd, image_id, frames, gap, cols, rows):
    apc(fd, f"a=d,d=I,i={image_id},q=2")
    apc(fd, f"a=T,U=1,i={image_id},f=100,c={cols},r={rows},q=2", frames[0])
    for f in frames[1:]:
        apc(fd, f"a=f,i={image_id},f=100,z={gap},q=2", f)
    apc(fd, f"a=a,i={image_id},r=1,z={gap},q=2")
    apc(fd, f"a=a,i={image_id},s=3,v=1,q=2")


def current_look():
    """Stage and gear from the save."""
    from .. import state as store
    view = store.load_readonly().get("view") or {}
    return view.get("stage", "lizard"), view.get("gear") or {}


def write_manifest(base):
    os.makedirs(CACHE, exist_ok=True)
    tmp = MANIFEST + ".tmp"
    with open(tmp, "w") as fh:
        json.dump({"actions": ACTIONS, "base": base}, fh)
    os.replace(tmp, MANIFEST)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tty")
    ap.add_argument("--base", type=int, default=200)
    ap.add_argument("--cols", type=int, default=8)
    ap.add_argument("--rows", type=int, default=3)
    ap.add_argument("--stage", help="override the stage from the save")
    ap.add_argument("--action", help="only this action (with --png)")
    ap.add_argument("--gear", help="with --png: 'all' for sample gear, 'none', or JSON")
    ap.add_argument("--png", help="write a contact sheet here instead of uploading")
    a = ap.parse_args(argv)

    stage, gear = current_look()
    stage = a.stage or stage
    if a.png:
        if a.gear == "all":
            gear = SAMPLE_GEAR
        elif a.gear == "none":
            gear = {}
        elif a.gear:
            gear = json.loads(a.gear)
        w, h = 20 * a.cols, 54 * a.rows
        acts = [a.action] if a.action else ACTIONS
        per = 8
        sheet = cairo.ImageSurface(cairo.FORMAT_ARGB32, w * per, h * len(acts))
        cr = cairo.Context(sheet)
        cr.set_source_rgb(0.12, 0.12, 0.16)
        cr.paint()
        for row, act in enumerate(acts):
            _, n, _ = ACTION_SPECS[act]
            for j in range(per):
                cr.set_source_surface(render(stage, act, j * n // per, w, h, gear), j * w, row * h)
                cr.paint()
        sheet.write_to_png(a.png)
        return 0

    fd = os.open(a.tty, os.O_WRONLY | os.O_NOCTTY)
    try:
        cw, ch = cell_size(fd)
        w, h = int(cw * a.cols), int(ch * a.rows)
        write_manifest(a.base)
        for idx, act in enumerate(ACTIONS):
            T, n, _ = ACTION_SPECS[act]
            upload(fd, a.base + idx, frames_for(stage, act, w, h, gear),
                   max(20, int(T / n * 1000)), a.cols, a.rows)
    finally:
        os.close(fd)
    prune_cache()
    return 0


if __name__ == "__main__":
    sys.exit(main())
