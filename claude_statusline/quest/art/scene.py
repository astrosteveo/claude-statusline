#!/usr/bin/env python3
"""Game mode's scene: the whole width of the bar as one animated picture.

    python3 -m claude_statusline.quest.art.scene --tty /dev/pts/5 --base 230 --cols 140 --rows 3 \\
        [--boss test] [--raid] [--dungeon] [--tod night]

Each situation in SITUATIONS (the pet wandering, working, fighting,
celebrating, asleep, waiting for you) is its own looping kitty animation,
stored under image id base + index, so the bar switches between them by
colour alone, like the avatar. A situation is a still backdrop (sky, hills,
and whatever the game has going on: a castle for an open PR dungeon, the
kraken of a tech-debt raid, the boss) plus small frames of just the actors,
which kitty lays over the backdrop itself. So an animation costs one
picture and a strip of little ones, not a full picture per frame.

    python3 -m claude_statusline.quest.art.scene --png scene.png --cols 140 --rows 3 [--boss lint] ...
"""
import argparse
import base64
import hashlib
import json
import math
import os
import random
import shutil
import sys

import cairo

from . import avatar
from .avatar import CACHE, TAU, apc, cell_size, current_look, render_at
from .sprites import star

SITUATIONS = ["idle", "work", "battle", "celebrate", "sleep", "yourturn"]
SKY = {  # top, bottom, hills far, hills near, ground
    "dawn": ((0.36, 0.33, 0.55), (0.96, 0.66, 0.52), (0.52, 0.42, 0.55), (0.36, 0.50, 0.40), (0.30, 0.44, 0.30)),
    "day": ((0.32, 0.56, 0.86), (0.66, 0.84, 0.97), (0.52, 0.70, 0.78), (0.38, 0.66, 0.40), (0.33, 0.56, 0.30)),
    "dusk": ((0.20, 0.16, 0.36), (0.86, 0.46, 0.40), (0.40, 0.28, 0.42), (0.26, 0.36, 0.32), (0.22, 0.30, 0.24)),
    "night": ((0.04, 0.05, 0.13), (0.10, 0.13, 0.27), (0.12, 0.15, 0.26), (0.09, 0.16, 0.16), (0.07, 0.13, 0.12)),
}
GROUND = 0.86          # as a fraction of the height, the same line the avatar stands on
FOE = 1.6              # foes and the castle are drawn this much bigger than their unit


# ------------------------------------------------------------------ the backdrop

def _hills(cr, w, h, base, amp, freq, phase, rgb):
    cr.move_to(0, h)
    for x in range(0, w + 8, 8):
        y = base + amp * (math.sin(x * freq + phase) * 0.6 + math.sin(x * freq * 2.3 + phase * 1.7) * 0.4)
        cr.line_to(x, y)
    cr.line_to(w, h)
    cr.close_path()
    cr.set_source_rgb(*rgb)
    cr.fill()


def backdrop(w, h, tod, boss=None, raid=False, dungeon=False, omit=None):
    """The still part of the scene."""
    top, bottom, far, near, ground = SKY[tod]
    u = h / 60
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surf)
    r = 5 * u                                   # a rounded window onto the world
    cr.new_sub_path()
    for (cx, cy, a) in ((w - r, r, -math.pi / 2), (w - r, h - r, 0), (r, h - r, math.pi / 2), (r, r, math.pi)):
        cr.arc(cx, cy, r, a, a + math.pi / 2)
    cr.close_path()
    cr.clip()
    g = cairo.LinearGradient(0, 0, 0, h)
    g.add_color_stop_rgb(0, *top)
    g.add_color_stop_rgb(1, *bottom)
    cr.set_source(g)
    cr.paint()
    rng = random.Random(42)
    if tod in ("night", "dusk"):
        for _ in range(max(8, w // 14)):
            x, y = rng.random() * w, rng.random() * h * 0.55
            cr.set_source_rgba(1, 1, 0.9, rng.uniform(0.3, 0.9) * (1 if tod == "night" else 0.5))
            cr.arc(x, y, rng.uniform(0.4, 1.1) * u, 0, TAU)
            cr.fill()
    body_x, body_y = w * 0.08, h * 0.26
    if tod == "night":
        cr.set_source_rgb(0.95, 0.94, 0.82)
        cr.arc(body_x, body_y, 6 * u, 0, TAU)
        cr.fill()
        cr.set_source_rgb(*top)
        cr.arc(body_x + 2.6 * u, body_y - 1.4 * u, 5.2 * u, 0, TAU)
        cr.fill()
    else:
        glow = cairo.RadialGradient(body_x, body_y, 0, body_x, body_y, 16 * u)
        glow.add_color_stop_rgba(0, 1, 0.95, 0.7, 0.55)
        glow.add_color_stop_rgba(1, 1, 0.95, 0.7, 0)
        cr.set_source(glow)
        cr.paint()
        cr.set_source_rgb(1, 0.93, 0.6) if tod == "day" else cr.set_source_rgb(1, 0.72, 0.45)
        cr.arc(body_x, body_y, 6 * u, 0, TAU)
        cr.fill()
        for i in range(3):                      # a few clouds
            cx, cy = w * (0.25 + 0.27 * i + rng.uniform(-0.05, 0.05)), h * rng.uniform(0.14, 0.34)
            cr.set_source_rgba(1, 1, 1, 0.55 if tod == "day" else 0.3)
            for dx, rr in ((-6, 4), (0, 6), (7, 4.5)):
                cr.arc(cx + dx * u, cy, rr * u, 0, TAU)
                cr.fill()
    _hills(cr, w, h, h * 0.58, h * 0.1, 0.006 * 60 / h, 1.3, far)
    if dungeon:
        castle(cr, w * 0.62, h * 0.62, u * 1.3, tod)
    _hills(cr, w, h, h * 0.74, h * 0.05, 0.011 * 60 / h, 4.1, near)
    gy = h * GROUND
    cr.rectangle(0, gy - u, w, h)
    cr.set_source_rgb(*ground)
    cr.fill()
    cr.set_line_width(max(1.0, 0.6 * u))
    for _ in range(w // 9):                     # grass
        x = rng.random() * w
        cr.set_source_rgba(*(c * 1.25 for c in ground), 0.9)
        cr.move_to(x, gy)
        cr.line_to(x + rng.uniform(-1.5, 1.5) * u, gy - rng.uniform(1.5, 3.5) * u)
        cr.stroke()
    if raid:
        pond(cr, w, gy, u)
        if omit != "raid":
            kraken(cr, w * 0.93, gy, u * FOE, 0.0)
    if boss and omit != "boss":
        monster(cr, boss, w * 0.8, gy, u * FOE, 0.0)
    if tod == "night":
        cr.set_source_rgba(0.02, 0.03, 0.1, 0.25)
        cr.paint()
    surf.flush()
    return surf


def castle(cr, x, base, u, tod):
    stone = (0.45, 0.43, 0.52) if tod != "night" else (0.22, 0.22, 0.3)
    dark = tuple(c * 0.75 for c in stone)
    cr.set_source_rgb(*stone)
    cr.rectangle(x - 16 * u, base - 14 * u, 32 * u, 16 * u)
    cr.fill()
    for tx in (-16, 10):
        cr.set_source_rgb(*dark)
        cr.rectangle(x + tx * u, base - 22 * u, 6 * u, 24 * u)
        cr.fill()
        cr.move_to(x + (tx - 1) * u, base - 22 * u)
        cr.line_to(x + (tx + 3) * u, base - 28 * u)
        cr.line_to(x + (tx + 7) * u, base - 22 * u)
        cr.close_path()
        cr.set_source_rgb(0.62, 0.25, 0.3)
        cr.fill()
    cr.set_source_rgb(*stone)
    for i in range(5):                          # battlements
        cr.rectangle(x + (-10 + i * 4.4) * u, base - 17 * u, 2.6 * u, 3 * u)
        cr.fill()
    cr.move_to(x - 4 * u, base + 2 * u)
    cr.line_to(x - 4 * u, base - 5 * u)
    cr.arc(x, base - 5 * u, 4 * u, math.pi, 0)
    cr.line_to(x + 4 * u, base + 2 * u)
    cr.close_path()
    cr.set_source_rgb(1, 0.78, 0.35)            # the gate is lit: someone's home
    cr.fill()
    cr.set_source_rgb(0.3, 0.25, 0.3)
    cr.set_line_width(0.6 * u)
    cr.move_to(x + 13 * u, base - 28 * u)
    cr.line_to(x + 13 * u, base - 35 * u)
    cr.stroke()
    cr.move_to(x + 13 * u, base - 35 * u)
    cr.line_to(x + 19 * u, base - 33 * u)
    cr.line_to(x + 13 * u, base - 31 * u)
    cr.close_path()
    cr.set_source_rgb(0.95, 0.75, 0.3)
    cr.fill()


def pond(cr, w, gy, u):
    g = cairo.LinearGradient(0, gy - 2 * u, 0, gy + 8 * u)
    g.add_color_stop_rgb(0, 0.2, 0.45, 0.65)
    g.add_color_stop_rgb(1, 0.08, 0.2, 0.35)
    cr.save()
    cr.translate(w * 0.93, gy + 2 * u)
    cr.scale(1, 0.28)
    cr.arc(0, 0, max(w * 0.06, 26 * u), 0, TAU)
    cr.restore()
    cr.set_source(g)
    cr.fill()


def kraken(cr, x, gy, u, t, hit=0.0):
    """The tech-debt kraken rising from its pond; t animates the tentacles."""
    body = (0.62 + 0.3 * hit, 0.32, 0.55 - 0.2 * hit)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    for i, side in enumerate((-1, 1, -0.45, 0.45)):
        sway = math.sin(t * 2.2 + i * 1.3)
        cr.set_source_rgb(*body)
        cr.set_line_width((3.2 - 0.5 * abs(side)) * u)
        cr.move_to(x + side * 6 * u, gy)
        cr.curve_to(x + side * 13 * u, gy - 8 * u, x + side * (9 + 4 * sway) * u, gy - 18 * u,
                    x + side * (15 + 5 * sway) * u, gy - (24 - 3 * abs(side)) * u)
        cr.stroke()
    cr.save()
    cr.translate(x, gy - 8 * u)
    cr.scale(1, 1.15)
    cr.arc(0, 0, 8 * u, math.pi, TAU)
    cr.restore()
    cr.close_path()
    cr.set_source_rgb(*body)
    cr.fill()
    for side in (-1, 1):
        cr.set_source_rgb(1, 0.95, 0.6)
        cr.arc(x + side * 3.2 * u, gy - 10 * u, 1.9 * u, 0, TAU)
        cr.fill()
        cr.set_source_rgb(0.1, 0.05, 0.1)
        cr.arc(x + side * 3.2 * u, gy - 10 * u, 0.9 * u, 0, TAU)
        cr.fill()


def monster(cr, kind, x, gy, u, t, hit=0.0):
    """The boss of a failing test (a hydra), build (a golem) or lint run (a goblin)."""
    bob = math.sin(t * 3) * 0.8 * u
    flash = (1, 1, 1) if hit > 0.6 else None
    if kind == "build":
        rock = flash or (0.55, 0.53, 0.5)
        for (dx, dy, bw, bh) in ((-7, -9, 14, 9), (-9, -20, 18, 11), (-6, -28, 12, 8)):
            cr.rectangle(x + dx * u, gy + dy * u + bob, bw * u, bh * u)
            cr.set_source_rgb(*rock)
            cr.fill()
        for side in (-1, 1):
            cr.rectangle(x + (side * 12 - 2.5) * u, gy - 19 * u + bob, 5 * u, 10 * u)
            cr.fill()
        cr.set_source_rgb(1, 0.55, 0.2)
        for side in (-1, 1):
            cr.rectangle(x + (side * 2.6 - 1) * u, gy - 25 * u + bob, 2 * u, 1.6 * u)
            cr.fill()
    elif kind == "lint":
        skin = flash or (0.82, 0.3, 0.28)
        cr.set_source_rgb(*skin)
        cr.save()
        cr.translate(x, gy - 7 * u + bob)
        cr.scale(1, 1.2)
        cr.arc(0, 0, 6 * u, 0, TAU)
        cr.restore()
        cr.fill()
        cr.arc(x, gy - 17 * u + bob, 5.5 * u, 0, TAU)
        cr.fill()
        for side in (-1, 1):
            cr.move_to(x + side * 4 * u, gy - 19 * u + bob)
            cr.line_to(x + side * 11 * u, gy - 23 * u + bob)
            cr.line_to(x + side * 5 * u, gy - 15 * u + bob)
            cr.close_path()
            cr.fill()
        cr.set_source_rgb(0.4, 0.3, 0.2)
        cr.set_line_width(0.8 * u)
        cr.move_to(x - 8 * u, gy)
        cr.line_to(x - 8 * u, gy - 26 * u + bob)
        cr.stroke()
        cr.set_source_rgb(0.8, 0.8, 0.85)
        cr.move_to(x - 9.5 * u, gy - 26 * u + bob)
        cr.line_to(x - 8 * u, gy - 30 * u + bob)
        cr.line_to(x - 6.5 * u, gy - 26 * u + bob)
        cr.fill()
        cr.set_source_rgb(1, 0.9, 0.3)
        for side in (-1, 1):
            cr.arc(x + side * 2.2 * u, gy - 18 * u + bob, 1.1 * u, 0, TAU)
            cr.fill()
    else:                                       # test: a three-headed hydra
        scale = flash or (0.35, 0.7, 0.38)
        cr.set_source_rgb(*scale)
        cr.save()
        cr.translate(x, gy - 5 * u)
        cr.scale(1.5, 0.8)
        cr.arc(0, 0, 7 * u, math.pi, TAU)
        cr.restore()
        cr.fill()
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for i, dx in enumerate((-6, 0, 6)):
            sway = math.sin(t * 2.5 + i * 2.1) * 2 * u
            hx, hy = x + dx * u + sway, gy - (19 + 3 * (i == 1)) * u + bob
            cr.set_source_rgb(*scale)
            cr.set_line_width(2.6 * u)
            cr.move_to(x + dx * 0.6 * u, gy - 6 * u)
            cr.curve_to(x + dx * u, gy - 12 * u, hx - 3 * u, hy + 5 * u, hx, hy)
            cr.stroke()
            cr.arc(hx, hy, 3 * u, 0, TAU)
            cr.fill()
            cr.set_source_rgb(0.95, 0.2, 0.2)
            cr.arc(hx - 1 * u, hy - 0.6 * u, 0.8 * u, 0, TAU)
            cr.fill()
            cr.set_source_rgb(*scale)


# ------------------------------------------------------------------ the actors

def pet_sprite(stage, action, k, h, gear, flip=False):
    """The pet as a transparent picture one scene tall, and its width."""
    pw = int(h * 1.3)
    surf = render_at(stage, action, k % 1.0, pw, h, gear)
    if not flip:
        return surf, pw
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, pw, h)
    cr = cairo.Context(out)
    cr.translate(pw, 0)
    cr.scale(-1, 1)
    cr.set_source_surface(surf, 0, 0)
    cr.paint()
    out.flush()
    return out, pw


def _pingpong(frac):
    """0 -> 1 -> 0 over one loop, with the direction."""
    return (frac * 2, False) if frac < 0.5 else (2 - frac * 2, True)


def target_of(situation, boss, raid):
    """What a battle is fought against: the boss, else the raid's kraken; drawn moving, not in the backdrop."""
    if situation != "battle":
        return None
    return "boss" if boss else ("raid" if raid else None)


def plan(situation, w, h, boss, raid):
    """(frames, seconds per loop, frame(i) -> (x, surface)) for one situation."""
    stage, gear = LOOK
    u = h / 60
    pw = int(h * 1.3)
    gy = h * GROUND
    lo, hi = w * 0.14, max(w * 0.14 + pw, w * (0.5 if (boss or raid) else 0.58))

    if situation in ("idle", "work"):
        action, period = ("walk", TAU) if situation == "idle" else ("work", math.pi / 2)
        loops = 2 if situation == "idle" else 8
        n = 112 if situation == "idle" else 128
        span = (hi - lo) * (1.0 if situation == "work" else 0.7)

        def frame(i):
            frac = i / n
            pos, back = _pingpong(frac)
            surf, _ = pet_sprite(stage, action, frac * loops, h, gear, flip=back)
            return int(lo + pos * span - pw / 2), surf
        return n, period * loops, frame

    if situation == "battle":
        target = target_of(situation, boss, raid)
        tx = w * 0.8 if boss else w * 0.93
        n, period = 40, math.pi
        x0 = int(tx - 22 * u * FOE - pw * 0.8)  # the pet stands just short of its foe
        box_w = int(tx - x0 + 20 * u * FOE)

        def frame(i):
            k = i / n
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, box_w, h)
            cr = cairo.Context(surf)
            lunge = math.sin(k * 2 * TAU)
            if target == "raid":
                kraken(cr, tx - x0, gy, u * FOE, k * period * 2, hit=max(0, lunge))
            elif target == "boss":
                cr.save()
                cr.translate(max(0, lunge) * 1.5 * u, 0)
                monster(cr, boss, tx - x0, gy, u * FOE, k * period * 2, hit=max(0, lunge))
                cr.restore()
            pet, _ = pet_sprite(stage, "battle", k * 2, h, gear)
            cr.set_source_surface(pet, 0, 0)
            cr.paint()
            if lunge > 0.5:
                cr.set_source_rgba(1, 0.9, 0.4, lunge)
                star(cr, tx - x0 - 8 * u * FOE, gy - 14 * u * FOE, 4 * u * FOE * lunge)
                cr.fill()
            surf.flush()
            return x0, surf
        return n, period * 2, frame

    if situation == "celebrate":
        n, period = 40, math.pi
        box_w = int(pw * 3)
        x0 = int(w * 0.3 - box_w / 2)
        rng = random.Random(7)
        bits = [(rng.random(), rng.random(), rng.uniform(2, 6), i % 5) for i in range(26)]
        colours = [(1, .85, .3), (1, .5, .7), (.5, .9, 1), (.7, 1, .5), (.8, .6, 1)]

        def frame(i):
            k = i / n
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, box_w, h)
            cr = cairo.Context(surf)
            for bx, by, spin, c in bits:
                cr.save()
                cr.translate(bx * box_w, ((by + k) % 1) * h * 0.85)
                cr.rotate(spin * k * TAU)
                cr.rectangle(-1.6 * u, -0.8 * u, 3.2 * u, 1.6 * u)
                cr.set_source_rgb(*colours[c])
                cr.fill()
                cr.restore()
            pet, _ = pet_sprite(stage, "victory", k * 2, h, gear)
            cr.set_source_surface(pet, (box_w - pw) / 2, 0)
            cr.paint()
            surf.flush()
            return x0, surf
        return n, period * 2, frame

    action, n, period = {"sleep": ("sleep", 28, TAU), "yourturn": ("yourturn", 28, 4.0)}[situation]

    def frame(i):
        surf, _ = pet_sprite(stage, action, i / n, h, gear)
        return int(w * 0.24 - pw / 2), surf
    return n, period, frame


LOOK = ("lizard", {})


# ------------------------------------------------------------------ frames, cached

def _key(w, h, tod, boss, raid, dungeon):
    here = os.path.dirname(os.path.realpath(__file__))
    hsh = hashlib.sha1()
    for name in ("scene.py", "avatar.py", "sprites.py", "gear.py"):
        with open(os.path.join(here, name), "rb") as fh:
            hsh.update(fh.read())
    hsh.update(json.dumps([LOOK, w, h, tod, boss, raid, dungeon], sort_keys=True).encode())
    return hsh.hexdigest()[:16]


def _save(surf, dest):
    """Write a PNG kitty may be reading: a new file renamed into place, never the old one
    emptied and refilled. Kitty maps the file it was sent; if that file shrinks under it,
    kitty dies of SIGBUS. After a rename it keeps reading the old, complete file."""
    tmp = f"{dest}.{os.getpid()}.tmp"
    surf.write_to_png(tmp)
    os.replace(tmp, dest)


def frames_for(situation, w, h, tod, boss, raid, dungeon):
    """(backdrop PNG path, [(x, PNG path)], gap ms), drawn once and kept on disk."""
    folder = os.path.join(CACHE, f"scene-{_key(w, h, tod, boss, raid, dungeon)}", situation)
    index = os.path.join(folder, "index.json")
    bg = os.path.join(folder, "bg.png")

    def path(n):
        return os.path.join(folder, f"{n:03d}.png")
    try:
        with open(index) as fh:
            meta = json.load(fh)
        if os.path.exists(bg) and all(os.path.exists(path(n)) for n in range(len(meta["x"]))):
            return bg, [(x, path(n)) for n, x in enumerate(meta["x"])], meta["gap"]
    except (OSError, ValueError, KeyError):
        pass
    n, seconds, frame = plan(situation, w, h, boss, raid)
    os.makedirs(folder, exist_ok=True)
    _save(backdrop(w, h, tod, boss, raid, dungeon, omit=target_of(situation, boss, raid)), bg)
    xs = []
    for i in range(n):
        x, surf = frame(i)
        sw = surf.get_width()
        if x < 0 or x + sw > w:                # keep every frame inside the picture
            left, right = max(0, x), min(w, x + sw)
            if right <= left:
                continue
            clipped = cairo.ImageSurface(cairo.FORMAT_ARGB32, right - left, h)
            cr = cairo.Context(clipped)
            cr.set_source_surface(surf, x - left, 0)
            cr.paint()
            surf, x = clipped, left
        _save(surf, path(len(xs)))
        xs.append(x)
    gap = max(40, int(seconds / n * 1000))
    with open(index + ".tmp", "w") as fh:
        json.dump({"x": xs, "gap": gap}, fh)
    os.replace(index + ".tmp", index)
    return bg, [(x, path(i)) for i, x in enumerate(xs)], gap


def send_file(fd, head, path):
    """One graphics command whose pixels kitty reads from a file: a short escape, never chunked.
    (Frames sent in chunks lose their placement keys in kitty, and this sends a fraction of the bytes.)"""
    os.write(fd, b"\x1b_G" + head.encode() + b",t=f;" + base64.standard_b64encode(path.encode()) + b"\x1b\\")


def upload(fd, image_id, bg, patches, gap, cols, rows):
    """The backdrop as the root frame, each patch a frame drawn over it."""
    apc(fd, f"a=d,d=I,i={image_id},q=2")
    send_file(fd, f"a=T,U=1,i={image_id},f=100,c={cols},r={rows},q=2", bg)
    for x, path in patches:
        send_file(fd, f"a=f,i={image_id},f=100,x={x},y=0,c=1,z={gap},q=2", path)
    apc(fd, f"a=a,i={image_id},r=1,z=-1,q=2")   # gapless: the bare backdrop is only a canvas, never shown
    apc(fd, f"a=a,i={image_id},s=3,v=1,q=2")


def main(argv=None):
    global LOOK
    ap = argparse.ArgumentParser()
    ap.add_argument("--tty")
    ap.add_argument("--base", type=int, default=230)
    ap.add_argument("--cols", type=int, default=120)
    ap.add_argument("--rows", type=int, default=3)
    ap.add_argument("--boss", default="")
    ap.add_argument("--raid", action="store_true")
    ap.add_argument("--dungeon", action="store_true")
    ap.add_argument("--tod", default="day", choices=list(SKY))
    ap.add_argument("--stage", help="override the stage from the save")
    ap.add_argument("--form", help="override the form")
    ap.add_argument("--png", help="write every situation's first frames here instead of uploading")
    a = ap.parse_args(argv)
    stage, gear = current_look()
    if a.form:
        gear = dict(gear, form=a.form)
    LOOK = (a.stage or stage, gear)
    boss = a.boss or None

    if a.png:
        w, h = 10 * a.cols, 21 * a.rows
        sheet = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h * len(SITUATIONS) * 2)
        cr = cairo.Context(sheet)
        for row, sit in enumerate(SITUATIONS):
            n, _, frame = plan(sit, w, h, boss, a.raid)
            bg = backdrop(w, h, a.tod, boss, a.raid, a.dungeon, omit=target_of(sit, boss, a.raid))
            for j, i in enumerate((0, n // 3)):
                y = (row * 2 + j) * h
                cr.set_source_surface(bg, 0, y)
                cr.paint()
                x, surf = frame(i)
                cr.set_source_surface(surf, x, y)
                cr.paint()
        sheet.write_to_png(a.png)
        return 0

    fd = os.open(a.tty, os.O_WRONLY | os.O_NOCTTY)
    try:
        cw, ch = cell_size(fd)
        w, h = int(cw * a.cols), int(ch * a.rows)
        for idx, sit in enumerate(SITUATIONS):
            bg, patches, gap = frames_for(sit, w, h, a.tod, boss, a.raid, a.dungeon)
            upload(fd, a.base + idx, bg, patches, gap, a.cols, a.rows)
    finally:
        os.close(fd)
    prune()
    return 0


def prune(keep=8):
    try:
        dirs = [os.path.join(CACHE, d) for d in os.listdir(CACHE) if d.startswith("scene-")]
    except OSError:
        return
    dirs.sort(key=os.path.getmtime, reverse=True)
    for d in dirs[keep:]:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
