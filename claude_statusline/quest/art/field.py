#!/usr/bin/env python3
"""The Claude Quest field: an animated overlay for your companion.

Runs inside a transparent `kitten panel` (see `claude-quest field`). Each frame
is drawn with Cairo and streamed to kitty over the graphics protocol, so the
scene is resolution-independent and alpha-blended over the desktop.

The pet's mood and stage come from ~/.claude/quest/state.json, the same file
the hooks and the statusline read. The sky follows the real time of day.
"""
import array
import base64
import fcntl
import json
import math
import os
import random
import signal
import struct
import subprocess
import sys
import termios
import time
import zlib
from datetime import datetime

import cairo

STATE = os.path.join(os.path.expanduser(os.environ.get("CLAUDE_QUEST_HOME") or "~/.claude/quest"),
                     "state.json")
FPS = 20
EXCITED_S, SLEEPY_S, WORKING_S = 20, 600, 15
IDLE_EXIT_S = 120  # close once no claude process has run for this long

STAGES = [(1, "egg"), (5, "hatchling"), (15, "lizard"), (30, "drake"), (50, "wyrm")]
TITLES = [(1, "Wandering Prompter"), (5, "Apprentice"), (10, "Journeyman"),
          (15, "Adept"), (20, "Veteran"), (30, "Master"), (40, "Grandmaster"),
          (50, "Archmage"), (75, "Mythic"), (100, "Ascended")]


# ---------------------------------------------------------------- terminal

def pixel_size():
    buf = array.array("H", [0, 0, 0, 0])
    fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, buf)
    rows, cols, w, h = buf
    return (w or 640), (h or 360)


def send_frame(surface, w, h):
    """Replace image 1 with this frame, placed at the top-left cell."""
    data = zlib.compress(bytes(bgra_to_rgba(surface)), 1)
    payload = base64.standard_b64encode(data)
    out = [b"\x1b[H"]
    first = True
    for i in range(0, len(payload), 4096):
        chunk = payload[i:i + 4096]
        more = 1 if i + 4096 < len(payload) else 0
        if first:
            head = f"a=T,f=32,o=z,s={w},v={h},i=1,p=1,q=2,C=1,z=-1,m={more}"
            first = False
        else:
            head = f"m={more}"
        out.append(b"\x1b_G" + head.encode() + b";" + chunk + b"\x1b\\")
    sys.stdout.buffer.write(b"".join(out))
    sys.stdout.buffer.flush()


def bgra_to_rgba(surface):
    """Cairo gives premultiplied BGRA; kitty wants straight RGBA."""
    surface.flush()
    buf = surface.get_data()
    mv = memoryview(buf)
    b = bytearray(mv)
    # swap B and R (premultiplied alpha is fine against a transparent window)
    b[0::4], b[2::4] = b[2::4], b[0::4]
    return b


# ---------------------------------------------------------------- state

class Quest:
    def __init__(self):
        self.mtime = 0
        self.data = {}

    def refresh(self):
        try:
            m = os.stat(STATE).st_mtime
            if m != self.mtime:
                with open(STATE) as f:
                    self.data = json.load(f)
                self.mtime = m
        except (OSError, ValueError):
            pass
        return self.data

    @property
    def level(self):
        return int(math.sqrt(max(0, self.data.get("xp", 0)) / 50)) + 1

    @property
    def stage(self):
        return [s for need, s in STAGES if self.level >= need][-1]

    @property
    def progress(self):
        lvl = self.level
        lo, hi = 50 * (lvl - 1) ** 2, 50 * lvl ** 2
        return (self.data.get("xp", 0) - lo) / (hi - lo)

    def mood(self, now):
        ev = self.data.get("last_event") or {}
        if now - ev.get("at", 0) < EXCITED_S:
            return "excited"
        if now - self.data.get("last_tool", 0) < WORKING_S:
            return "working"
        if now - self.data.get("last_activity", 0) > SLEEPY_S:
            return "sleepy"
        return "idle"


# ---------------------------------------------------------------- drawing

def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return tuple(lerp(a, b, t) for a, b in zip(c1, c2))


def hexc(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) / 255 for i in (0, 2, 4))


SKIES = [  # hour, top, horizon
    (0, hexc("0b1026"), hexc("1c2a4a")),
    (5, hexc("1c2a4a"), hexc("5b4a7a")),
    (6.5, hexc("5f7fbf"), hexc("f4a987")),
    (9, hexc("5aa9e6"), hexc("bfe3f5")),
    (16, hexc("4f9ad9"), hexc("cfe8f2")),
    (18.5, hexc("5d5a9e"), hexc("f59e6b")),
    (20, hexc("22264d"), hexc("6b4a78")),
    (22, hexc("0b1026"), hexc("1c2a4a")),
    (24, hexc("0b1026"), hexc("1c2a4a")),
]


def sky_at(hour):
    for (h1, t1, b1), (h2, t2, b2) in zip(SKIES, SKIES[1:]):
        if h1 <= hour <= h2:
            k = (hour - h1) / (h2 - h1)
            return mix(t1, t2, k), mix(b1, b2, k)
    return SKIES[0][1], SKIES[0][2]


def night_amount(hour):
    if 7 <= hour <= 18:
        return 0.0
    if hour >= 21 or hour <= 4.5:
        return 1.0
    if hour < 7:
        return (7 - hour) / 2.5
    return (hour - 18) / 3


def rounded(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


class Field:
    def __init__(self, w, h):
        self.w, self.h = w, h
        rnd = random.Random(7)
        self.stars = [(rnd.random(), rnd.random() * 0.55, rnd.random() * 6.28,
                       rnd.uniform(0.6, 1.6)) for _ in range(45)]
        self.clouds = [(rnd.random(), rnd.uniform(0.08, 0.35), rnd.uniform(0.6, 1.3),
                        rnd.uniform(0.004, 0.012)) for _ in range(4)]
        self.blades = [(rnd.random(), rnd.uniform(0.5, 1.0), rnd.random() * 6.28)
                       for _ in range(90)]
        self.flies = [(rnd.random(), rnd.uniform(0.45, 0.8), rnd.random() * 6.28)
                      for _ in range(9)]
        self.particles = []
        self.pet_x = 0.5
        self.pet_dir = 1
        self.last_event_at = 0
        self.jump_t = -10

    # --- scene -------------------------------------------------------
    def draw(self, cr, t, quest):
        w, h = self.w, self.h
        s = min(w / 640, h / 360)  # design units are 640x360
        now = time.time()
        hour = float(os.environ.get("QUEST_HOUR") or
                     datetime.now().hour + datetime.now().minute / 60)
        night = night_amount(hour)
        mood = quest.mood(now)

        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        pad = 6 * s
        rounded(cr, pad, pad, w - 2 * pad, h - 2 * pad, 26 * s)
        cr.save()
        cr.clip_preserve()

        top, bottom = sky_at(hour)
        g = cairo.LinearGradient(0, 0, 0, h * 0.7)
        g.add_color_stop_rgba(0, *top, 0.93)
        g.add_color_stop_rgba(1, *bottom, 0.93)
        cr.set_source(g)
        cr.fill()

        self.draw_stars(cr, t, night, s)
        self.draw_celestial(cr, hour, night, s)
        self.draw_clouds(cr, t, night, s)
        self.draw_hills(cr, night, s)
        self.draw_grass(cr, t, night, s, mood)
        if night > 0.3:
            self.draw_fireflies(cr, t, night, s)
        self.update_pet(t, now, quest, mood)
        self.draw_pet(cr, t, quest.stage, mood, night, s)
        self.draw_particles(cr, s)
        self.draw_hud(cr, quest, s, night)
        if mood == "excited":
            text = (quest.data.get("last_event") or {}).get("text", "")
            self.draw_bubble(cr, text, s)
        cr.restore()

        # frame
        rounded(cr, pad, pad, w - 2 * pad, h - 2 * pad, 26 * s)
        cr.set_source_rgba(1, 1, 1, 0.18)
        cr.set_line_width(2 * s)
        cr.stroke()

    def draw_stars(self, cr, t, night, s):
        if night <= 0:
            return
        for x, y, ph, sz in self.stars:
            a = night * (0.55 + 0.45 * math.sin(t * 2 + ph))
            cr.set_source_rgba(1, 1, 0.9, a)
            cr.arc(x * self.w, y * self.h, sz * s, 0, 6.3)
            cr.fill()

    def draw_celestial(self, cr, hour, night, s):
        w, h = self.w, self.h
        if 6 <= hour <= 19.5:  # sun arcs across the day
            k = (hour - 6) / 13.5
            x, y = lerp(0.1, 0.9, k) * w, (0.62 - 0.5 * math.sin(k * math.pi)) * h
            g = cairo.RadialGradient(x, y, 0, x, y, 60 * s)
            g.add_color_stop_rgba(0, 1, 0.95, 0.7, 0.55)
            g.add_color_stop_rgba(1, 1, 0.8, 0.4, 0)
            cr.set_source(g)
            cr.arc(x, y, 60 * s, 0, 6.3)
            cr.fill()
            cr.set_source_rgb(1, 0.93, 0.62)
            cr.arc(x, y, 22 * s, 0, 6.3)
            cr.fill()
        if night > 0:
            hh = hour if hour >= 12 else hour + 24
            k = min(1, max(0, (hh - 19) / 11))
            x, y = lerp(0.15, 0.85, k) * w, (0.55 - 0.4 * math.sin(k * math.pi)) * h
            cr.set_source_rgba(0.95, 0.95, 1, night)
            cr.arc(x, y, 17 * s, 0, 6.3)
            cr.fill()
            top, _ = sky_at(hour)
            cr.set_source_rgba(*top, night)
            cr.arc(x + 7 * s, y - 4 * s, 15 * s, 0, 6.3)
            cr.fill()

    def draw_clouds(self, cr, t, night, s):
        for x0, y, scale, speed in self.clouds:
            x = ((x0 + t * speed) % 1.4 - 0.2) * self.w
            yy = y * self.h
            c = 1 - 0.55 * night
            cr.set_source_rgba(c, c, c * 1.02, 0.75)
            for dx, dy, r in ((0, 0, 18), (20, -8, 22), (42, 0, 17), (22, 6, 18)):
                cr.arc(x + dx * s * scale, yy + dy * s * scale, r * s * scale, 0, 6.3)
                cr.fill()

    def draw_hills(self, cr, night, s):
        w, h = self.w, self.h
        dark = 1 - 0.6 * night
        for base, amp, color, freq in ((0.64, 0.07, (0.36, 0.62, 0.45), 1.3),
                                       (0.72, 0.05, (0.30, 0.68, 0.36), 2.1)):
            cr.move_to(0, h)
            for i in range(0, 65):
                x = i / 64
                cr.line_to(x * w, (base - amp * math.sin(x * math.pi * freq + base * 9)) * h)
            cr.line_to(w, h)
            cr.close_path()
            cr.set_source_rgb(*(c * dark for c in color))
            cr.fill()
        ground = self.ground_y()
        g = cairo.LinearGradient(0, ground, 0, h)
        g.add_color_stop_rgb(0, *(c * dark for c in (0.35, 0.72, 0.33)))
        g.add_color_stop_rgb(1, *(c * dark for c in (0.22, 0.52, 0.25)))
        cr.rectangle(0, ground, w, h - ground)
        cr.set_source(g)
        cr.fill()

    def ground_y(self):
        return self.h * 0.8

    def draw_grass(self, cr, t, night, s, mood):
        dark = 1 - 0.6 * night
        wind = 1.8 if mood == "working" else 1.0
        cr.set_line_width(2 * s)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for x, ht, ph in self.blades:
            bx, by = x * self.w, self.ground_y() + 3 * s
            sway = math.sin(t * 1.7 * wind + ph + x * 4) * 4 * s * wind
            cr.move_to(bx, by)
            cr.curve_to(bx, by - 6 * s * ht, bx + sway * 0.5, by - 10 * s * ht,
                        bx + sway, by - 14 * s * ht)
            cr.set_source_rgba(0.45 * dark, 0.85 * dark, 0.4 * dark, 0.9)
            cr.stroke()

    def draw_fireflies(self, cr, t, night, s):
        for x0, y0, ph in self.flies:
            x = (x0 + 0.05 * math.sin(t * 0.4 + ph)) * self.w
            y = (y0 + 0.04 * math.sin(t * 0.7 + ph * 2)) * self.h
            a = night * max(0, math.sin(t * 1.5 + ph)) ** 2
            g = cairo.RadialGradient(x, y, 0, x, y, 9 * s)
            g.add_color_stop_rgba(0, 1, 1, 0.5, a)
            g.add_color_stop_rgba(1, 1, 1, 0.3, 0)
            cr.set_source(g)
            cr.arc(x, y, 9 * s, 0, 6.3)
            cr.fill()

    # --- pet ---------------------------------------------------------
    def update_pet(self, t, now, quest, mood):
        ev = quest.data.get("last_event") or {}
        if ev.get("at", 0) != self.last_event_at:
            if self.last_event_at:  # not on startup
                self.jump_t = t
                self.burst(12)
            self.last_event_at = ev.get("at", 0)
        speed = {"working": 0.0045, "idle": 0.0012, "excited": 0.0, "sleepy": 0.0}[mood]
        self.pet_x += speed * self.pet_dir
        if self.pet_x > 0.82 or self.pet_x < 0.18:
            self.pet_dir *= -1
            self.pet_x = min(0.82, max(0.18, self.pet_x))
        if mood == "idle" and random.random() < 0.003:
            self.pet_dir *= -1
        if mood == "excited" and random.random() < 0.25:
            self.burst(1)
        if mood == "sleepy" and random.random() < 0.02:
            self.particles.append({"kind": "z", "x": self.pet_x * self.w + 20,
                                   "y": self.ground_y() - 40, "vx": 0.4, "vy": -0.5,
                                   "life": 1.0})

    def burst(self, n):
        colors = [(1, 0.85, 0.3), (1, 0.5, 0.7), (0.5, 0.9, 1), (0.7, 1, 0.5)]
        for _ in range(n):
            a = random.uniform(0, math.pi)
            v = random.uniform(1.5, 4)
            self.particles.append({"kind": "spark", "x": self.pet_x * self.w,
                                   "y": self.ground_y() - 50, "vx": math.cos(a) * v,
                                   "vy": -math.sin(a) * v, "life": 1.0,
                                   "color": random.choice(colors)})

    def draw_particles(self, cr, s):
        alive = []
        for p in self.particles:
            p["x"] += p["vx"] * s
            p["y"] += p["vy"] * s
            if p["kind"] == "spark":
                p["vy"] += 0.12
                p["life"] -= 0.03
            else:
                p["life"] -= 0.008
            if p["life"] <= 0:
                continue
            alive.append(p)
            if p["kind"] == "spark":
                cr.set_source_rgba(*p["color"], p["life"])
                star(cr, p["x"], p["y"], 5 * s * (0.5 + p["life"]))
                cr.fill()
            else:
                cr.set_source_rgba(1, 1, 1, p["life"])
                cr.select_font_face("sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                cr.set_font_size(14 * s * (1.6 - p["life"] * 0.6))
                cr.move_to(p["x"], p["y"])
                cr.show_text("z")
        self.particles = alive[-200:]

    def draw_pet(self, cr, t, stage, mood, night, s):
        x = self.pet_x * self.w
        y = self.ground_y()
        hop = 0.0
        if mood == "working":
            hop = abs(math.sin(t * 10)) * 5 * s
        elif mood == "idle":
            hop = abs(math.sin(t * 4)) * 2 * s
        dt = t - self.jump_t
        if 0 <= dt < 0.8:
            hop += math.sin(dt / 0.8 * math.pi) * 40 * s
        elif mood == "excited":
            hop += abs(math.sin(t * 6)) * 14 * s
        blink = (t % 3.7) < 0.12
        asleep = mood == "sleepy"

        # shadow
        cr.save()
        cr.translate(x, y + 4 * s)
        cr.scale(1, 0.25)
        cr.set_source_rgba(0, 0, 0, 0.25 * (1 - min(hop / (60 * s), 0.7)))
        cr.arc(0, 0, 30 * s, 0, 6.3)
        cr.fill()
        cr.restore()

        cr.save()
        cr.translate(x, y - hop)
        cr.scale(1.5 * s * self.pet_dir, 1.5 * s)
        glow = 0.25 + 0.15 * math.sin(t * 3) if stage == "wyrm" else 0
        if glow:
            g = cairo.RadialGradient(0, -30, 0, 0, -30, 70)
            g.add_color_stop_rgba(0, 0.7, 0.5, 1, glow)
            g.add_color_stop_rgba(1, 0.7, 0.5, 1, 0)
            cr.set_source(g)
            cr.arc(0, -30, 70, 0, 6.3)
            cr.fill()
        getattr(self, f"pet_{stage}")(cr, t, mood, blink, asleep)
        cr.restore()

    def pet_egg(self, cr, t, mood, blink, asleep):
        wob = math.sin(t * (6 if mood != "sleepy" else 1.5)) * 0.12
        cr.rotate(wob)
        cr.save()
        cr.scale(1, 1.3)
        cr.arc(0, -20, 20, 0, 6.3)
        cr.restore()
        g = cairo.LinearGradient(-20, -50, 20, 0)
        g.add_color_stop_rgb(0, 1, 0.98, 0.9)
        g.add_color_stop_rgb(1, 0.9, 0.82, 0.68)
        cr.set_source(g)
        cr.fill()
        cr.set_source_rgb(0.55, 0.75, 0.95)
        for dx, dy, r in ((-8, -32, 4), (7, -20, 5), (-4, -10, 3)):
            cr.arc(dx, dy, r, 0, 6.3)
            cr.fill()

    def _eyes(self, cr, ex, ey, r, blink, asleep):
        if blink or asleep:
            cr.set_source_rgb(0.15, 0.15, 0.2)
            cr.set_line_width(2)
            cr.move_to(ex - r, ey)
            cr.curve_to(ex - r / 2, ey + r / 2, ex + r / 2, ey + r / 2, ex + r, ey)
            cr.stroke()
            return
        cr.set_source_rgb(1, 1, 1)
        cr.arc(ex, ey, r, 0, 6.3)
        cr.fill()
        cr.set_source_rgb(0.1, 0.1, 0.15)
        cr.arc(ex + r * 0.3, ey, r * 0.6, 0, 6.3)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.arc(ex + r * 0.45, ey - r * 0.3, r * 0.22, 0, 6.3)
        cr.fill()

    def pet_hatchling(self, cr, t, mood, blink, asleep):
        cr.set_source_rgb(1, 0.95, 0.85)  # shell cup
        cr.move_to(-18, -12)
        for i in range(7):
            cr.line_to(-18 + i * 6, -12 - (6 if i % 2 else 0))
        cr.line_to(18, -12)
        cr.arc(0, -12, 18, 0, math.pi)
        cr.fill()
        cr.set_source_rgb(1, 0.85, 0.3)
        cr.arc(0, -28, 16, 0, 6.3)
        cr.fill()
        flap = math.sin(t * 12) * 0.4 if mood in ("working", "excited") else 0
        cr.save()
        cr.translate(-12, -26)
        cr.rotate(-0.5 + flap)
        cr.scale(1, 0.55)
        cr.arc(0, 0, 8, 0, 6.3)
        cr.set_source_rgb(0.98, 0.75, 0.2)
        cr.fill()
        cr.restore()
        self._eyes(cr, 6, -32, 4, blink, asleep)
        cr.set_source_rgb(1, 0.55, 0.2)
        cr.move_to(14, -28)
        cr.line_to(22, -25)
        cr.line_to(14, -23)
        cr.fill()

    def pet_lizard(self, cr, t, mood, blink, asleep, wings=False, big=1.0):
        cr.scale(big, big)
        body = (0.4, 0.78, 0.45) if not wings else (0.55, 0.45, 0.85)
        belly = (0.85, 0.95, 0.6) if not wings else (0.95, 0.8, 0.6)
        pace = {"working": 12, "idle": 5, "excited": 8, "sleepy": 0}[mood]
        # tail
        wag = math.sin(t * (4 if mood != "sleepy" else 0.8)) * 6
        cr.move_to(-18, -14)
        cr.curve_to(-34, -14, -42, -8 + wag, -52, -18 + wag)
        cr.curve_to(-42, -2 + wag, -32, -4, -18, -6)
        cr.set_source_rgb(*body)
        cr.fill()
        # legs
        cr.set_line_width(6)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for lx, ph in ((-10, 0), (12, math.pi)):
            step = math.sin(t * pace + ph) * 5 if pace else 0
            cr.move_to(lx, -10)
            cr.line_to(lx + step, 0 if not asleep else -4)
            cr.set_source_rgb(*(c * 0.85 for c in body))
            cr.stroke()
        # body
        cr.save()
        cr.translate(0, -16)
        cr.scale(1.5, 1)
        cr.arc(0, 0, 14, 0, 6.3)
        cr.restore()
        cr.set_source_rgb(*body)
        cr.fill()
        cr.save()
        cr.translate(2, -11)
        cr.scale(1.4, 0.55)
        cr.arc(0, 0, 11, 0, 6.3)
        cr.restore()
        cr.set_source_rgb(*belly)
        cr.fill()
        # spikes
        cr.set_source_rgb(*(c * 0.7 for c in body))
        for i in range(4):
            sx = -14 + i * 8
            cr.move_to(sx - 3, -28 + abs(sx) * 0.1)
            cr.line_to(sx, -35 + abs(sx) * 0.1)
            cr.line_to(sx + 3, -28 + abs(sx) * 0.1)
            cr.fill()
        if wings:
            flap = math.sin(t * (10 if mood in ("working", "excited") else 2.5))
            cr.save()
            cr.translate(-4, -26)
            cr.rotate(-0.6 - flap * 0.5)
            cr.move_to(0, 0)
            cr.curve_to(-10, -30, -30, -34, -38, -26)
            cr.curve_to(-28, -20, -26, -10, 0, 0)
            cr.set_source_rgba(0.75, 0.6, 1, 0.85)
            cr.fill()
            cr.restore()
        # head
        hx, hy = 24, -24 if not asleep else -16
        cr.arc(hx, hy, 12, 0, 6.3)
        cr.set_source_rgb(*body)
        cr.fill()
        cr.save()
        cr.translate(hx + 10, hy + 3)
        cr.scale(1.3, 0.8)
        cr.arc(0, 0, 7, 0, 6.3)
        cr.restore()
        cr.fill()
        if wings:
            cr.set_source_rgb(1, 0.9, 0.6)
            for dx in (-4, 4):
                cr.move_to(hx + dx - 2, hy - 10)
                cr.line_to(hx + dx - 4, hy - 20)
                cr.line_to(hx + dx + 2, hy - 11)
                cr.fill()
        self._eyes(cr, hx + 3, hy - 3, 4.5, blink, asleep)
        # blush
        cr.set_source_rgba(1, 0.5, 0.6, 0.45)
        cr.arc(hx + 10, hy + 5, 3, 0, 6.3)
        cr.fill()
        if mood == "excited":
            cr.set_source_rgb(0.5, 0.15, 0.2)
            cr.arc(hx + 12, hy + 6, 3.5, 0, math.pi)
            cr.fill()

    def pet_drake(self, cr, t, mood, blink, asleep):
        self.pet_lizard(cr, t, mood, blink, asleep, wings=True, big=1.2)

    def pet_wyrm(self, cr, t, mood, blink, asleep):
        self.pet_lizard(cr, t, mood, blink, asleep, wings=True, big=1.45)

    # --- overlays ----------------------------------------------------
    def draw_hud(self, cr, quest, s, night):
        lvl = quest.level
        title = [t for need, t in TITLES if lvl >= need][-1]
        x, y = 22 * s, 30 * s
        cr.select_font_face("sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(16 * s)
        label = f"Lv {lvl}  {title}"
        ext = cr.text_extents(label)
        rounded(cr, x - 10 * s, y - 20 * s, ext.x_advance + 20 * s, 44 * s, 12 * s)
        cr.set_source_rgba(0, 0, 0, 0.35)
        cr.fill()
        cr.set_source_rgb(1, 0.87, 0.5)
        cr.move_to(x, y)
        cr.show_text(label)
        bw = ext.x_advance
        rounded(cr, x, y + 8 * s, bw, 8 * s, 4 * s)
        cr.set_source_rgba(1, 1, 1, 0.2)
        cr.fill()
        p = max(0.02, min(1, quest.progress))
        g = cairo.LinearGradient(x, 0, x + bw, 0)
        g.add_color_stop_rgb(0, 0.37, 0.85, 0.85)
        g.add_color_stop_rgb(1, 0.8, 0.5, 0.95)
        rounded(cr, x, y + 8 * s, bw * p, 8 * s, 4 * s)
        cr.set_source(g)
        cr.fill()

    def draw_bubble(self, cr, text, s):
        if not text:
            return
        cr.select_font_face("sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(14 * s)
        text = "".join(ch for ch in text if ord(ch) < 0x2190 or 0x2500 <= ord(ch) < 0x2600).strip()
        if len(text) > 48:
            text = text[:47].rstrip() + "…"
        ext = cr.text_extents(text)
        bw, bh = ext.x_advance + 24 * s, 32 * s
        px = self.pet_x * self.w
        bx = min(max(12 * s, px - bw / 2), self.w - bw - 12 * s)
        by = self.ground_y() - 150 * s
        rounded(cr, bx, by, bw, bh, 12 * s)
        cr.move_to(px - 8 * s, by + bh)
        cr.line_to(px, by + bh + 12 * s)
        cr.line_to(px + 8 * s, by + bh)
        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.fill()
        cr.set_source_rgb(0.15, 0.15, 0.25)
        cr.move_to(bx + 12 * s, by + 21 * s)
        cr.show_text(text)


def star(cr, x, y, r):
    for i in range(10):
        a = i * math.pi / 5 - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.45
        (cr.move_to if i == 0 else cr.line_to)(x + math.cos(a) * rr, y + math.sin(a) * rr)
    cr.close_path()


# ---------------------------------------------------------------- main

def claude_running():
    try:
        out = subprocess.run(["pgrep", "-x", "claude"], capture_output=True)
        return out.returncode == 0
    except FileNotFoundError:
        return True


def main():
    out = sys.stdout.buffer
    out.write(b"\x1b[?25l\x1b[2J")  # hide cursor, clear
    out.flush()
    resized = [True]
    signal.signal(signal.SIGWINCH, lambda *_: resized.__setitem__(0, True))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    quest = Quest()
    field = surface = cr = None
    start = time.monotonic()
    last_alive = time.monotonic()
    last_check = 0
    frame = 1 / FPS
    try:
        while True:
            t0 = time.monotonic()
            if resized[0]:
                w, h = pixel_size()
                surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
                cr = cairo.Context(surface)
                old = field
                field = Field(w, h)
                if old:
                    field.pet_x, field.pet_dir = old.pet_x, old.pet_dir
                    field.last_event_at = old.last_event_at
                resized[0] = False
            quest.refresh()
            field.draw(cr, t0 - start, quest)
            send_frame(surface, field.w, field.h)
            if t0 - last_check > 10:
                last_check = t0
                if claude_running():
                    last_alive = t0
                elif t0 - last_alive > IDLE_EXIT_S:
                    return 0
            time.sleep(max(0, frame - (time.monotonic() - t0)))
    except (KeyboardInterrupt, BrokenPipeError):
        return 0
    finally:
        try:
            out.write(b"\x1b_Ga=d,d=A,q=2\x1b\\\x1b[?25h")
            out.flush()
        except Exception:
            pass


if __name__ == "__main__":
    if sys.argv[1:2] == ["--snapshot"]:  # render one frame to PNG for testing
        quest = Quest()
        quest.refresh()
        if len(sys.argv) > 3:
            quest.data = dict(quest.data, **json.loads(sys.argv[3]))
        f = Field(640, 360)
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 640, 360)
        c = cairo.Context(surf)
        for i in range(30):
            f.draw(c, 1.0 + i / FPS, quest)
        surf.write_to_png(sys.argv[2])
        sys.exit(0)
    sys.exit(main())
