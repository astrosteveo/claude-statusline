"""Gear, drawn at an attachment point the sprite has already translated to.

Each function draws one slot's item from its visual spec
(`{"kind": ..., "color": "#rrggbb", "accent": ..., "glow": bool}`).
Hats sit on the top of the head, with `r` the head's radius; held items
have their grip at the origin and point up (-y).
"""
import math

import cairo

TAU = 2 * math.pi


def rgb(spec, key="color", default="#cccccc"):
    h = (spec.get(key) or default).lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def shade(color, k):
    return tuple(max(0.0, min(1.0, c * k)) for c in color)


def ellipse(cr, x, y, rx, ry):
    cr.save()
    cr.translate(x, y)
    cr.scale(rx, ry)
    cr.arc(0, 0, 1, 0, TAU)
    cr.restore()


def star(cr, x, y, r):
    for i in range(10):
        a = i * math.pi / 5 - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.45
        (cr.move_to if i == 0 else cr.line_to)(x + math.cos(a) * rr, y + math.sin(a) * rr)
    cr.close_path()


def glow(cr, x, y, radius, color, alpha):
    g = cairo.RadialGradient(x, y, 0, x, y, radius)
    g.add_color_stop_rgba(0, *color, alpha)
    g.add_color_stop_rgba(1, *color, 0)
    cr.set_source(g)
    cr.arc(x, y, radius, 0, TAU)
    cr.fill()


# ------------------------------------------------------------------ head

def hat(cr, spec, r, view, t):
    kind = spec.get("kind")
    col, acc = rgb(spec), rgb(spec, "accent", "#ffffff")
    cr.save()
    if kind == "paper":
        cr.move_to(-1.1 * r, 0.2 * r)
        cr.line_to(0, -0.85 * r)
        cr.line_to(1.1 * r, 0.2 * r)
        cr.close_path()
        cr.set_source_rgb(*col)
        cr.fill_preserve()
        cr.set_source_rgb(*shade(col, 0.75))
        cr.set_line_width(max(1, r * 0.06))
        cr.stroke()
        cr.move_to(-0.95 * r, 0.05 * r)
        cr.line_to(0.95 * r, 0.05 * r)
        cr.stroke()
    elif kind == "beanie":
        cr.arc(0, 0.25 * r, 1.02 * r, math.pi, TAU)
        cr.close_path()
        cr.set_source_rgb(*col)
        cr.fill()
        cr.rectangle(-1.06 * r, 0.05 * r, 2.12 * r, 0.32 * r)
        cr.set_source_rgb(*acc)
        cr.fill()
        cr.arc(0, -0.8 * r, 0.24 * r, 0, TAU)
        cr.fill()
    elif kind == "headphones":
        cr.set_line_width(0.2 * r)
        cr.set_source_rgb(*col)
        cr.arc(0, 0.6 * r, 1.05 * r, math.pi + 0.2, TAU - 0.2)
        cr.stroke()
        cups = [(-1.0, 0.6), (1.0, 0.6)] if view == "front" else [(-0.15, 0.75)]
        for cx, cy in cups:
            ellipse(cr, cx * r, cy * r, 0.26 * r, 0.36 * r)
            cr.set_source_rgb(*acc)
            cr.fill()
            ellipse(cr, cx * r, cy * r, 0.14 * r, 0.22 * r)
            cr.set_source_rgb(*col)
            cr.fill()
    elif kind == "goggles":
        cr.rectangle(-1.05 * r, 0.3 * r, 2.1 * r, 0.18 * r)
        cr.set_source_rgb(*col)
        cr.fill()
        lenses = [(-0.38, 0.38), (0.38, 0.38)] if view == "front" else [(0.45, 0.38)]
        for lx, ly in lenses:
            cr.arc(lx * r, ly * r, 0.28 * r, 0, TAU)
            cr.set_source_rgba(*acc, 0.85)
            cr.fill_preserve()
            cr.set_source_rgb(*shade(col, 0.7))
            cr.set_line_width(max(1, 0.08 * r))
            cr.stroke()
            cr.arc((lx - 0.1) * r, (ly - 0.1) * r, 0.07 * r, 0, TAU)
            cr.set_source_rgba(1, 1, 1, 0.8)
            cr.fill()
    elif kind == "crown":
        w = 0.72 * r
        cr.move_to(-w, 0.25 * r)
        pts = [(-w, -0.55), (-w / 2, -0.15), (0, -0.7), (w / 2, -0.15), (w, -0.55)]
        for x, y in pts:
            cr.line_to(x, y * r)
        cr.line_to(w, 0.25 * r)
        cr.close_path()
        cr.set_source_rgb(*col)
        cr.fill_preserve()
        cr.set_source_rgb(*shade(col, 0.75))
        cr.set_line_width(max(1, 0.06 * r))
        cr.stroke()
        for x in (-w / 2, 0, w / 2):
            cr.arc(x, 0.08 * r, 0.09 * r, 0, TAU)
            cr.set_source_rgb(*acc)
            cr.fill()
    elif kind == "helm":
        cr.arc(0, 0.4 * r, 1.08 * r, math.pi, TAU)
        cr.close_path()
        g = cairo.LinearGradient(-r, -r, r, r)
        g.add_color_stop_rgb(0, *shade(col, 1.15))
        g.add_color_stop_rgb(1, *shade(col, 0.75))
        cr.set_source(g)
        cr.fill()
        cr.rectangle(-1.12 * r, 0.28 * r, 2.24 * r, 0.2 * r)
        cr.set_source_rgb(*shade(col, 0.7))
        cr.fill()
        if view == "front":
            cr.rectangle(-0.07 * r, 0.4 * r, 0.14 * r, 0.42 * r)
            cr.fill()
        ellipse(cr, 0, -0.72 * r, 0.14 * r, 0.3 * r)
        cr.set_source_rgb(*acc)
        cr.fill()
    elif kind == "wizard":
        ellipse(cr, 0, 0.2 * r, 1.35 * r, 0.3 * r)
        cr.set_source_rgb(*shade(col, 0.75))
        cr.fill()
        sway = math.sin(t * 2) * 0.12 * r
        cr.move_to(-0.72 * r, 0.18 * r)
        cr.curve_to(-0.4 * r, -0.6 * r, 0.1 * r, -1.2 * r, 0.25 * r + sway, -1.55 * r)
        cr.line_to(0.75 * r + sway, -1.75 * r)
        cr.curve_to(0.3 * r, -1.2 * r, 0.6 * r, -0.4 * r, 0.72 * r, 0.18 * r)
        cr.close_path()
        cr.set_source_rgb(*col)
        cr.fill()
        cr.rectangle(-0.66 * r, -0.02 * r, 1.32 * r, 0.18 * r)
        cr.set_source_rgb(*acc)
        cr.fill()
        star(cr, 0.05 * r, -0.55 * r, 0.24 * r)
        cr.fill()
    elif kind == "halo":
        pulse = 0.35 + 0.2 * math.sin(t * 3)
        cr.set_line_width(0.34 * r)
        cr.set_source_rgba(*col, pulse * 0.6)
        ellipse(cr, 0, -0.55 * r, 0.82 * r, 0.22 * r)
        cr.stroke()
        cr.set_line_width(0.13 * r)
        cr.set_source_rgb(*col)
        ellipse(cr, 0, -0.55 * r, 0.82 * r, 0.22 * r)
        cr.stroke()
    cr.restore()


# ------------------------------------------------------------------ hand

def hand_item(cr, spec, t):
    kind = spec.get("kind")
    col, acc = rgb(spec), rgb(spec, "accent", "#8b5a2b")
    cr.save()
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    if kind == "sword":
        if spec.get("glow"):
            glow(cr, 0, -18, 18, col, 0.35 + 0.2 * math.sin(t * 4))
        cr.move_to(-2.2, -4)
        cr.line_to(-2.2, -28)
        cr.line_to(0, -34)
        cr.line_to(2.2, -28)
        cr.line_to(2.2, -4)
        cr.close_path()
        cr.set_source_rgb(*col)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.6)
        cr.set_line_width(0.8)
        cr.move_to(0, -6)
        cr.line_to(0, -29)
        cr.stroke()
        cr.rectangle(-7, -5, 14, 3)
        cr.set_source_rgb(*acc)
        cr.fill()
        cr.rectangle(-1.5, -2, 3, 7)
        cr.set_source_rgb(0.45, 0.3, 0.18)
        cr.fill()
        cr.arc(0, 6, 2, 0, TAU)
        cr.set_source_rgb(*acc)
        cr.fill()
    elif kind == "duck":
        bob = math.sin(t * 3) * 0.8
        ellipse(cr, 0, -5 + bob, 7.5, 5)
        cr.set_source_rgb(*col)
        cr.fill()
        cr.arc(4, -12 + bob, 4.2, 0, TAU)
        cr.fill()
        ellipse(cr, 8.8, -11.5 + bob, 2.8, 1.5)
        cr.set_source_rgb(*acc)
        cr.fill()
        cr.arc(5, -13 + bob, 0.9, 0, TAU)
        cr.set_source_rgb(0.1, 0.1, 0.1)
        cr.fill()
        cr.set_source_rgb(*shade(col, 0.85))
        cr.set_line_width(1.2)
        cr.arc(-1, -5 + bob, 3.5, 0.2, 2.2)
        cr.stroke()
    elif kind == "pointer":
        hop = abs(math.sin(t * 5)) * 3
        cr.set_source_rgb(0.55, 0.35, 0.2)
        cr.set_line_width(1)
        cr.move_to(0, 0)
        cr.curve_to(3, 8, 8, 10, 12, 12 - hop)
        cr.stroke()
        cr.set_source_rgb(*col)
        cr.rectangle(10, 11 - hop, 6, 3.4)
        cr.fill()
        cr.move_to(16, 8.5 - hop)
        cr.line_to(21, 12.7 - hop)
        cr.line_to(16, 16.9 - hop)
        cr.close_path()
        cr.fill()
        cr.arc(17.3, 11.5 - hop, 0.8, 0, TAU)
        cr.set_source_rgb(0.1, 0.1, 0.15)
        cr.fill()
    elif kind == "stick":
        cr.set_source_rgb(*col)
        cr.set_line_width(3)
        cr.move_to(0, 12)
        cr.curve_to(-1, 0, 1, -14, 0, -26)
        cr.stroke()
        cr.set_source_rgb(*shade(col, 0.7))
        for y in (-6, -16):
            cr.arc(0.3, y, 1.4, 0, TAU)
            cr.fill()
    elif kind == "wand":
        cr.set_source_rgb(*col)
        cr.set_line_width(2)
        cr.move_to(0, 6)
        cr.line_to(0, -16)
        cr.stroke()
        glow(cr, 0, -19, 8, acc, 0.4 + 0.3 * math.sin(t * 5))
        cr.set_source_rgb(*acc)
        star(cr, 0, -19, 4.5)
        cr.fill()
    elif kind == "staff":
        cr.set_source_rgb(*col)
        cr.set_line_width(3)
        cr.move_to(0, 14)
        cr.line_to(0, -28)
        cr.stroke()
        cr.set_line_width(1.5)
        cr.arc(0, -32, 5.5, 0.5, math.pi - 0.5)
        cr.stroke()
        if spec.get("glow"):
            glow(cr, 0, -33, 12, acc, 0.35 + 0.25 * math.sin(t * 3))
        cr.arc(0, -33, 4.5, 0, TAU)
        cr.set_source_rgb(*acc)
        cr.fill()
        cr.arc(-1.3, -34.5, 1.3, 0, TAU)
        cr.set_source_rgba(1, 1, 1, 0.7)
        cr.fill()
    elif kind == "hammer":
        cr.set_source_rgb(*acc)
        cr.set_line_width(3)
        cr.move_to(0, 8)
        cr.line_to(0, -14)
        cr.stroke()
        cr.rectangle(-8, -22, 16, 9)
        cr.set_source_rgb(*col)
        cr.fill()
        cr.rectangle(-8, -22, 16, 2.5)
        cr.set_source_rgba(1, 1, 1, 0.35)
        cr.fill()
    cr.restore()


# ------------------------------------------------------------------ back

def _cape_path_side(cr, t, running):
    flow = 6 if running else 2
    w = math.sin(t * (9 if running else 2.5)) * flow
    cr.move_to(16, -27)
    cr.curve_to(4, -33, -14, -28, -26 - flow, -18 + w)
    cr.curve_to(-30 - flow, -10 + w, -28, -2, -22, -3 - w * 0.5)
    cr.curve_to(-12, -4, -2, -12, 12, -18)
    cr.close_path()


def back_side(cr, spec, t, pose):
    kind = spec.get("kind")
    col, acc = rgb(spec), rgb(spec, "accent", "#ffffff")
    running = pose.gait in ("run", "hop")
    cr.save()
    if kind == "cape":
        _cape_path_side(cr, t, running)
        g = cairo.LinearGradient(16, -27, -26, -6)
        g.add_color_stop_rgb(0, *col)
        g.add_color_stop_rgb(1, *shade(col, 0.7))
        cr.set_source(g)
        cr.fill()
        if spec.get("stars"):
            cr.set_source_rgb(*acc)
            for x, y in ((-8, -22), (-18, -14), (-2, -16)):
                star(cr, x, y, 1.8)
                cr.fill()
    elif kind == "wings":
        flap = math.sin(t * (10 if running else 2.5))
        cr.translate(-2, -28)
        cr.rotate(-0.4 - flap * 0.45)
        for i, (length, width) in enumerate(((30, 7), (25, 6), (19, 5))):
            cr.save()
            cr.rotate(-0.25 * i)
            ellipse(cr, -length / 2, -4 - i * 2, length / 2, width / 2)
            cr.set_source_rgb(*(col if i % 2 == 0 else acc))
            cr.fill()
            cr.restore()
    elif kind == "backpack":
        cr.translate(-14, -34)
        cr.rotate(-0.15)
        _rounded(cr, -8, 0, 16, 18, 4)
        cr.set_source_rgb(*col)
        cr.fill()
        _rounded(cr, -8, 0, 16, 7, 3)
        cr.set_source_rgb(*acc)
        cr.fill()
    cr.restore()


def back_front(cr, spec, t, pose):
    """The part of back gear seen behind the body in the front view."""
    kind = spec.get("kind")
    col, acc = rgb(spec), rgb(spec, "accent", "#ffffff")
    cr.save()
    if kind == "cape":
        w = math.sin(t * 2.5) * 1.5
        cr.move_to(-13, -32)
        cr.line_to(13, -32)
        cr.curve_to(19, -20, 22, -10, 24 + w, 0)
        cr.curve_to(10, 2 - w, -10, 2 + w, -24 - w, 0)
        cr.curve_to(-22, -10, -19, -20, -13, -32)
        cr.close_path()
        cr.set_source_rgb(*shade(col, 0.72))
        cr.fill()
        if spec.get("stars"):
            cr.set_source_rgb(*acc)
            for x, y in ((-20, -8), (19, -12)):
                star(cr, x, y, 1.8)
                cr.fill()
    elif kind == "wings":
        flap = math.sin(t * 3) * 0.15
        for side in (-1, 1):
            cr.save()
            cr.translate(side * 8, -30)
            cr.scale(side, 1)
            cr.rotate(-0.55 - flap)
            for i, (length, width) in enumerate(((28, 7), (23, 6), (17, 5))):
                cr.save()
                cr.rotate(0.28 * i)
                ellipse(cr, length / 2, -3, length / 2, width / 2)
                cr.set_source_rgb(*(col if i % 2 == 0 else acc))
                cr.fill()
                cr.restore()
            cr.restore()
    elif kind == "backpack":
        _rounded(cr, -15, -40, 30, 14, 5)
        cr.set_source_rgb(*col)
        cr.fill()
    cr.restore()


def back_front_over(cr, spec, t):
    """What back gear shows over the body in the front view: straps and collars."""
    kind = spec.get("kind")
    col, acc = rgb(spec), rgb(spec, "accent", "#ffffff")
    cr.save()
    if kind == "backpack":
        cr.set_source_rgb(*acc)
        cr.set_line_width(2.5)
        for side in (-1, 1):
            cr.move_to(side * 8, -31)
            cr.curve_to(side * 10, -24, side * 11, -16, side * 10, -9)
            cr.stroke()
    elif kind == "cape":
        cr.set_source_rgb(*col)
        for side in (-1, 1):
            cr.move_to(side * 4, -32)
            cr.line_to(side * 14, -33)
            cr.line_to(side * 12, -26)
            cr.close_path()
            cr.fill()
        cr.arc(0, -31, 2.2, 0, TAU)
        cr.set_source_rgb(*acc if spec.get("accent") else (0.95, 0.8, 0.3))
        cr.fill()
    cr.restore()


def _rounded(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


# ------------------------------------------------------------------ feet

def foot(cr, spec, x, y, view):
    kind = spec.get("kind")
    col, acc = rgb(spec), rgb(spec, "accent", "#ffffff")
    cr.save()
    if kind in ("boots", "sneakers"):
        if view == "side":
            _rounded(cr, x - 4.5, y - 8, 11, 9, 3)
        else:
            _rounded(cr, x - 7.5, y - 8, 15, 9, 3.5)
        cr.set_source_rgb(*col)
        cr.fill()
        sole = acc if kind == "sneakers" else shade(col, 0.55)
        if view == "side":
            cr.rectangle(x - 4.5, y - 1.5, 11, 2)
        else:
            cr.rectangle(x - 7.5, y - 1.5, 15, 2)
        cr.set_source_rgb(*sole)
        cr.fill()
        if kind == "sneakers":
            cr.set_source_rgb(*acc)
            cr.set_line_width(1)
            cr.move_to(x - 3, y - 4)
            cr.curve_to(x, y - 3, x + 2, y - 5, x + 4, y - 6)
            cr.stroke()
    elif kind == "socks":
        w = 7 if view == "side" else 11
        cr.rectangle(x - w / 2, y - 9, w, 7)
        cr.set_source_rgb(*col)
        cr.fill()
        cr.rectangle(x - w / 2, y - 7, w, 2)
        cr.set_source_rgb(*acc)
        cr.fill()
    cr.restore()


# ------------------------------------------------------------------ charm

def charm(cr, spec, x, y, view, t, scale=1.0):
    col = rgb(spec)
    cr.save()
    cr.translate(x, y)
    cr.scale(scale, scale)
    cr.set_source_rgba(0.95, 0.85, 0.45, 0.9)
    cr.set_line_width(0.9)
    if view == "front":
        cr.move_to(-8, -7)
        cr.curve_to(-6, -1, 6, -1, 8, -7)
    else:
        cr.move_to(-5, -9)
        cr.curve_to(-3, -2, 3, -2, 4, -9)
    cr.stroke()
    if spec.get("glow"):
        glow(cr, 0, 1, 9, col, 0.4 + 0.25 * math.sin(t * 3))
    cr.move_to(0, -3)
    cr.line_to(3.2, 1)
    cr.line_to(0, 5)
    cr.line_to(-3.2, 1)
    cr.close_path()
    cr.set_source_rgb(*col)
    cr.fill()
    cr.move_to(-1, -1)
    cr.line_to(0.6, -1.8)
    cr.set_source_rgba(1, 1, 1, 0.8)
    cr.set_line_width(0.8)
    cr.stroke()
    cr.restore()
