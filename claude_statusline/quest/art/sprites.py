"""The pet, drawn with Cairo in two views, wearing whatever gear it has on.

Coordinates are pet space: origin on the ground under the pet, y up is
negative, about 100 units wide. The side view faces right; the front view
faces you. Each stage (egg, hatchling, lizard, drake, wyrm) has both.

`gear` maps slot -> visual spec (see items.py); `pose` says what the body
is doing. Gear is drawn at attachment points so it follows the pose.
"""
import math

from . import gear as G

TAU = 2 * math.pi
PALETTE = {
    "lizard": ((0.40, 0.78, 0.45), (0.85, 0.95, 0.60)),
    "drake": ((0.55, 0.45, 0.85), (0.95, 0.80, 0.60)),  # arcane, and the look before forms
    "wyrm": ((0.55, 0.45, 0.85), (0.95, 0.80, 0.60)),
}
# A drake or wyrm wears its form's colours: body, belly, wings.
FORM_PALETTE = {
    "ember": ((0.88, 0.42, 0.28), (1.00, 0.82, 0.55), (1.00, 0.62, 0.25)),
    "forge": ((0.52, 0.56, 0.64), (0.95, 0.78, 0.50), (0.95, 0.66, 0.30)),
    "lore": ((0.35, 0.62, 0.52), (0.93, 0.90, 0.70), (0.55, 0.85, 0.75)),
    "arcane": ((0.55, 0.45, 0.85), (0.95, 0.80, 0.60), (0.75, 0.60, 1.00)),
    "storm": ((0.30, 0.55, 0.88), (0.85, 0.93, 1.00), (0.55, 0.85, 1.00)),
}
WING = (0.75, 0.6, 1)
SIDE_BIG = {"lizard": 1.0, "drake": 1.2, "wyrm": 1.45}


class Pose:
    """What the body is doing in one frame."""

    def __init__(self, t=0.0, gait="still", eyes="open", look=0.0, tilt=0.0, arms=(0.0, 0.0),
                 mouth="smile", sparkle=False, carry="back", brows=False):
        self.t = t
        self.gait = gait          # still, walk, run, hop, sleep
        self.eyes = eyes          # open, blink, happy, closed
        self.look = look          # -1 left .. 1 right (front view)
        self.tilt = tilt          # head tilt, radians (front view)
        self.arms = arms          # (left, right) lift, 0 down .. 1 straight up
        self.mouth = mouth        # smile, open, o, grin
        self.sparkle = sparkle    # star-shaped eye highlights
        self.carry = carry        # where the hand item goes: hand, back, mouth, none
        self.brows = brows        # determined eyebrows

    @property
    def asleep(self):
        return self.gait == "sleep"


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


def eye(cr, x, y, r, mode, look=0.0, sparkle=False, side=False):
    if mode in ("blink", "closed"):
        cr.set_source_rgb(0.15, 0.15, 0.2)
        cr.set_line_width(max(1.2, r * 0.4))
        cr.move_to(x - r, y)
        cr.curve_to(x - r / 2, y + r / 2, x + r / 2, y + r / 2, x + r, y)
        cr.stroke()
        return
    if mode == "happy":
        cr.set_source_rgb(0.15, 0.15, 0.2)
        cr.set_line_width(max(1.2, r * 0.4))
        cr.move_to(x - r, y + r * 0.3)
        cr.curve_to(x - r / 2, y - r * 0.6, x + r / 2, y - r * 0.6, x + r, y + r * 0.3)
        cr.stroke()
        return
    cr.set_source_rgb(1, 1, 1)
    cr.arc(x, y, r, 0, TAU)
    cr.fill()
    px = x + (r * 0.3 if side else look * r * 0.35)
    cr.set_source_rgb(0.1, 0.1, 0.15)
    cr.arc(px, y + r * 0.1, r * 0.62, 0, TAU)
    cr.fill()
    cr.set_source_rgb(1, 1, 1)
    if sparkle:
        star(cr, px - r * 0.15, y - r * 0.1, r * 0.5)
        cr.fill()
    else:
        cr.arc(px + r * 0.25, y - r * 0.28, r * 0.24, 0, TAU)
        cr.fill()


def mouth(cr, x, y, kind, scale=1.0):
    cr.set_source_rgb(0.35, 0.12, 0.18)
    if kind == "open":
        cr.arc(x, y, 3.5 * scale, 0, math.pi)
        cr.fill()
    elif kind == "o":
        ellipse(cr, x, y + 1, 2 * scale, 2.6 * scale)
        cr.fill()
    elif kind == "grin":
        cr.set_line_width(1.4)
        cr.arc(x, y - 2.5 * scale, 4 * scale, 0.35, math.pi - 0.35)
        cr.stroke()
    else:
        cr.set_line_width(1.4)
        cr.arc(x, y - 1.5 * scale, 3 * scale, 0.3, math.pi - 0.3)
        cr.stroke()


def leg_pace(pose):
    return {"run": 12, "walk": 5, "hop": 8}.get(pose.gait, 0)


# ================================================================== side view

def draw_side(cr, stage, pose, gear):
    if stage == "egg":
        return _side_egg(cr, pose, gear)
    if stage == "hatchling":
        return _side_hatchling(cr, pose, gear)
    return _side_lizard(cr, stage, pose, gear)


def _side_egg(cr, pose, gear):
    wob = math.sin(pose.t * (6 if pose.gait in ("run", "hop") else 1.5)) * 0.12
    cr.save()
    cr.rotate(wob)
    ellipse(cr, 0, -26, 20, 26)
    g = _egg_gradient()
    cr.set_source(g)
    cr.fill()
    cr.set_source_rgb(0.55, 0.75, 0.95)
    for dx, dy, r in ((-8, -38, 4), (7, -26, 5), (-4, -14, 3)):
        cr.arc(dx, dy, r, 0, TAU)
        cr.fill()
    if "head" in gear:
        cr.save()
        cr.translate(0, -50)
        G.hat(cr, gear["head"], 18, "front", pose.t)
        cr.restore()
    cr.restore()


def _egg_gradient():
    import cairo
    g = cairo.LinearGradient(-20, -52, 20, 0)
    g.add_color_stop_rgb(0, 1, 0.98, 0.9)
    g.add_color_stop_rgb(1, 0.9, 0.82, 0.68)
    return g


def _side_hatchling(cr, pose, gear):
    t = pose.t
    if "back" in gear:
        cr.save()
        cr.translate(-4, -30)
        cr.scale(0.7, 0.7)
        G.back_side(cr, gear["back"], t, pose)
        cr.restore()
    if pose.carry == "back" and "hand" in gear:
        cr.save()
        cr.translate(-12, -30)
        cr.rotate(-0.6)
        cr.scale(0.7, 0.7)
        G.hand_item(cr, gear["hand"], t)
        cr.restore()
    cr.set_source_rgb(1, 0.95, 0.85)  # shell cup
    cr.move_to(-18, -12)
    for i in range(7):
        cr.line_to(-18 + i * 6, -12 - (6 if i % 2 else 0))
    cr.line_to(18, -12)
    cr.arc(0, -12, 18, 0, math.pi)
    cr.fill()
    cr.set_source_rgb(1, 0.85, 0.3)
    cr.arc(0, -28, 16, 0, TAU)
    cr.fill()
    flap = math.sin(t * 12) * 0.4 if pose.gait in ("run", "hop") else 0
    cr.save()
    cr.translate(-12, -26)
    cr.rotate(-0.5 + flap)
    ellipse(cr, 0, 0, 8, 4.4)
    cr.set_source_rgb(0.98, 0.75, 0.2)
    cr.fill()
    cr.restore()
    if "charm" in gear:
        G.charm(cr, gear["charm"], 8, -15, "side", t, scale=0.7)
    eye(cr, 6, -32, 4, pose.eyes if not pose.asleep else "closed", side=True, sparkle=pose.sparkle)
    cr.set_source_rgb(1, 0.55, 0.2)
    cr.move_to(14, -28)
    cr.line_to(22, -25)
    cr.line_to(14, -23)
    cr.fill()
    if "head" in gear:
        cr.save()
        cr.translate(0, -43)
        cr.rotate(-0.15)
        G.hat(cr, gear["head"], 15, "side", t)
        cr.restore()
    if pose.carry == "mouth" and "hand" in gear:
        cr.save()
        cr.translate(22, -26)
        cr.rotate(1.2)
        cr.scale(0.7, 0.7)
        G.hand_item(cr, gear["hand"], t)
        cr.restore()


def colours(stage, gear):
    """(body, belly, wing) for this stage, in the pet's form if it has one."""
    form = FORM_PALETTE.get(gear.get("form")) if stage in ("drake", "wyrm") else None
    return form or PALETTE[stage] + (WING,)


def _side_lizard(cr, stage, pose, gear):
    t = pose.t
    big = SIDE_BIG[stage]
    cr.scale(big, big)
    body, belly, wing = colours(stage, gear)
    dark = tuple(c * 0.85 for c in body)
    wings = stage in ("drake", "wyrm")
    asleep = pose.asleep
    pace = leg_pace(pose)
    hx, hy = 24, (-16 if asleep else -24)

    if "back" in gear:
        G.back_side(cr, gear["back"], t, pose)
    if pose.carry == "back" and "hand" in gear:
        cr.save()
        cr.translate(-6, -28)
        cr.rotate(-0.75)
        G.hand_item(cr, gear["hand"], t)
        cr.restore()

    wag = math.sin(t * (0.8 if asleep else 4)) * 6
    cr.move_to(-18, -14)
    cr.curve_to(-34, -14, -42, -8 + wag, -52, -18 + wag)
    cr.curve_to(-42, -2 + wag, -32, -4, -18, -6)
    cr.set_source_rgb(*body)
    cr.fill()

    import cairo
    cr.set_line_width(6)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    for lx, ph in ((-10, 0), (12, math.pi)):
        step = math.sin(t * pace + ph) * 5 if pace else 0
        fy = -4 if asleep else 0
        cr.move_to(lx, -10)
        cr.line_to(lx + step, fy)
        cr.set_source_rgb(*dark)
        cr.stroke()
        if "feet" in gear:
            G.foot(cr, gear["feet"], lx + step, fy, "side")

    ellipse(cr, 0, -16, 21, 14)
    cr.set_source_rgb(*body)
    cr.fill()
    ellipse(cr, 2, -11, 15.4, 6)
    cr.set_source_rgb(*belly)
    cr.fill()
    cr.set_source_rgb(*(c * 0.7 for c in body))
    for i in range(4):
        sx = -14 + i * 8
        cr.move_to(sx - 3, -28 + abs(sx) * 0.1)
        cr.line_to(sx, -35 + abs(sx) * 0.1)
        cr.line_to(sx + 3, -28 + abs(sx) * 0.1)
        cr.fill()
    if wings:
        flap = math.sin(t * (10 if pose.gait in ("run", "hop") else 2.5))
        cr.save()
        cr.translate(-4, -26)
        cr.rotate(-0.6 - flap * 0.5)
        cr.move_to(0, 0)
        cr.curve_to(-10, -30, -30, -34, -38, -26)
        cr.curve_to(-28, -20, -26, -10, 0, 0)
        cr.set_source_rgba(*wing, 0.85)
        cr.fill()
        cr.restore()
    if "charm" in gear:
        G.charm(cr, gear["charm"], 17, -13, "side", t)

    cr.arc(hx, hy, 12, 0, TAU)
    cr.set_source_rgb(*body)
    cr.fill()
    ellipse(cr, hx + 10, hy + 3, 9.1, 5.6)
    cr.fill()
    if wings:
        cr.set_source_rgb(1, 0.9, 0.6)
        for dx in (-4, 4):
            cr.move_to(hx + dx - 2, hy - 10)
            cr.line_to(hx + dx - 4, hy - 20)
            cr.line_to(hx + dx + 2, hy - 11)
            cr.fill()
    eye(cr, hx + 3, hy - 3, 4.5, "closed" if asleep else pose.eyes, side=True, sparkle=pose.sparkle)
    if pose.brows:
        cr.set_source_rgb(0.15, 0.2, 0.15)
        cr.set_line_width(2)
        cr.move_to(hx - 2, hy - 10)
        cr.line_to(hx + 7, hy - 7)
        cr.stroke()
    cr.set_source_rgba(1, 0.5, 0.6, 0.45)
    cr.arc(hx + 10, hy + 5, 3, 0, TAU)
    cr.fill()
    if pose.mouth in ("open", "grin"):
        cr.set_source_rgb(0.5, 0.15, 0.2)
        cr.arc(hx + 12, hy + 6, 3.5, 0, math.pi)
        cr.fill()
    if "head" in gear:
        cr.save()
        cr.translate(hx - 1, hy - 10)
        cr.rotate(-0.2)
        G.hat(cr, gear["head"], 12, "side", t)
        cr.restore()
    if pose.carry == "mouth" and "hand" in gear:
        cr.save()
        cr.translate(hx + 17, hy + 4)
        cr.rotate(0.6)
        G.hand_item(cr, gear["hand"], t)
        cr.restore()


# ================================================================== front view

def arm_angle(side, lift):
    return -side * (0.3 + lift * 2.4)


def front_hand(stage, lift):
    """Where the right hand is (pet space, before the stage's scale) at this lift."""
    if stage == "egg":
        return 24, -30 - 12 * lift
    if stage == "hatchling":
        return 20, -15 - 10 * lift
    a = arm_angle(1, lift)
    return 14 - 15 * math.sin(a), -24 + 15 * math.cos(a)


def draw_front(cr, stage, pose, gear):
    if stage == "egg":
        return _front_egg(cr, pose, gear)
    if stage == "hatchling":
        return _front_hatchling(cr, pose, gear)
    return _front_lizard(cr, stage, pose, gear)


def _front_egg(cr, pose, gear):
    cr.save()
    cr.rotate(math.sin(pose.t * 2) * 0.06)
    ellipse(cr, 0, -26, 20, 26)
    cr.set_source(_egg_gradient())
    cr.fill()
    cr.set_source_rgb(0.25, 0.2, 0.15)
    cr.set_line_width(1.5)
    cr.move_to(-16, -30)
    for i, x in enumerate(range(-12, 18, 4)):
        cr.line_to(x, -30 + (4 if i % 2 else -3))
    cr.stroke()
    for ex in (-6, 6):
        eye(cr, ex, -36, 3.5, pose.eyes, pose.look, pose.sparkle)
    if "head" in gear:
        cr.save()
        cr.translate(0, -50)
        G.hat(cr, gear["head"], 18, "front", pose.t)
        cr.restore()
    cr.restore()


def _front_hatchling(cr, pose, gear):
    t = pose.t
    if "back" in gear:
        cr.save()
        cr.translate(0, -22)
        cr.scale(0.75, 0.75)
        G.back_front(cr, gear["back"], t, pose)
        cr.restore()
    if pose.carry == "back" and "hand" in gear:
        cr.save()
        cr.translate(-14, -30)
        cr.rotate(-0.5)
        cr.scale(0.7, 0.7)
        G.hand_item(cr, gear["hand"], t)
        cr.restore()
    ellipse(cr, 0, -20, 17, 17)
    cr.set_source_rgb(1, 0.85, 0.3)
    cr.fill()
    for side, lift in ((-1, pose.arms[0]), (1, pose.arms[1])):
        cr.save()
        cr.translate(side * 15, -20)
        cr.rotate(side * (0.3 + lift * 1.8))
        ellipse(cr, side * 3, 0, 4, 8)
        cr.set_source_rgb(0.98, 0.72, 0.2)
        cr.fill()
        cr.restore()
    cr.set_source_rgb(1, 0.95, 0.85)
    cr.move_to(-17, -12)
    for i in range(7):
        cr.line_to(-17 + i * 5.7, -12 - (5 if i % 2 else 0))
    cr.line_to(17, -12)
    cr.arc(0, -12, 17, 0, math.pi)
    cr.fill()
    if "charm" in gear:
        G.charm(cr, gear["charm"], 0, -9, "front", t, scale=0.7)
    for ex in (-6, 6):
        eye(cr, ex, -25, 4, pose.eyes, pose.look, pose.sparkle)
    cr.set_source_rgb(1, 0.55, 0.2)
    cr.move_to(-3.5, -20)
    cr.line_to(3.5, -20)
    cr.line_to(0, -13 if pose.mouth == "open" else -15)
    cr.fill()
    if "head" in gear:
        cr.save()
        cr.translate(0, -36)
        cr.rotate(pose.tilt)
        G.hat(cr, gear["head"], 16, "front", t)
        cr.restore()
    if pose.carry == "hand" and "hand" in gear:
        hx, hy = front_hand("hatchling", pose.arms[1])
        cr.save()
        cr.translate(hx, hy)
        cr.rotate(0.2)
        cr.scale(0.75, 0.75)
        G.hand_item(cr, gear["hand"], t)
        cr.restore()


def _front_lizard(cr, stage, pose, gear):
    t = pose.t
    body, belly, wing = colours(stage, gear)
    dark = tuple(c * 0.8 for c in body)
    wings = stage in ("drake", "wyrm")

    if "back" in gear:
        G.back_front(cr, gear["back"], t, pose)
    if pose.carry == "back" and "hand" in gear:
        cr.save()
        cr.translate(-15, -30)
        cr.rotate(-0.55)
        G.hand_item(cr, gear["hand"], t)
        cr.restore()

    wag = math.sin(t * 4) * 5
    cr.move_to(10, -8)
    cr.curve_to(24, -6, 32, -14 + wag, 36, -24 + wag)
    cr.curve_to(28, -10 + wag, 22, -2, 8, -2)
    cr.set_source_rgb(*body)
    cr.fill()
    if wings:
        flap = math.sin(t * 3) * 0.12
        for side in (-1, 1):
            cr.save()
            cr.translate(side * 10, -30)
            cr.scale(side, 1)
            cr.rotate(-0.35 - flap)
            cr.move_to(0, 0)
            cr.curve_to(10, -22, 28, -26, 34, -18)
            cr.curve_to(26, -14, 22, -6, 0, 4)
            cr.set_source_rgba(*wing, 0.9)
            cr.fill()
            cr.restore()
    for fx in (-9, 9):
        ellipse(cr, fx, -2, 7, 4)
        cr.set_source_rgb(*dark)
        cr.fill()
        if "feet" in gear:
            G.foot(cr, gear["feet"], fx, -1, "front")
    ellipse(cr, 0, -17, 17, 16)
    cr.set_source_rgb(*body)
    cr.fill()
    ellipse(cr, 0, -15, 11, 11)
    cr.set_source_rgb(*belly)
    cr.fill()
    if "back" in gear:
        G.back_front_over(cr, gear["back"], t)
    if "charm" in gear:
        G.charm(cr, gear["charm"], 0, -26, "front", t)
    for side, lift in ((-1, pose.arms[0]), (1, pose.arms[1])):
        cr.save()
        cr.translate(side * 14, -24)
        cr.rotate(arm_angle(side, lift))
        ellipse(cr, 0, 8, 4.5, 8)
        cr.set_source_rgb(*dark)
        cr.fill()
        cr.restore()
    if pose.carry == "hand" and "hand" in gear:
        hx, hy = front_hand(stage, pose.arms[1])
        cr.save()
        cr.translate(hx, hy)
        cr.rotate(0.25)
        G.hand_item(cr, gear["hand"], t)
        cr.restore()

    cr.save()
    cr.translate(0, -44)
    cr.rotate(pose.tilt)
    for sx in (-8, 0, 8):
        cr.move_to(sx - 4, -14)
        cr.line_to(sx, -22)
        cr.line_to(sx + 4, -14)
        cr.set_source_rgb(*dark)
        cr.fill()
    if wings:
        for side in (-1, 1):
            cr.move_to(side * 9, -12)
            cr.line_to(side * 15, -24)
            cr.line_to(side * 14, -10)
            cr.set_source_rgb(1, 0.9, 0.6)
            cr.fill()
    ellipse(cr, 0, 0, 19, 16)
    cr.set_source_rgb(*body)
    cr.fill()
    ellipse(cr, 0, 7, 11, 7)
    cr.set_source_rgb(*belly)
    cr.fill()
    cr.set_source_rgba(1, 0.5, 0.6, 0.45)
    for bx in (-12, 12):
        cr.arc(bx, 5, 3.2, 0, TAU)
        cr.fill()
    for ex in (-7, 7):
        eye(cr, ex, -3, 5, pose.eyes, pose.look, pose.sparkle)
    if pose.brows:
        cr.set_source_rgb(0.15, 0.2, 0.15)
        cr.set_line_width(2)
        for side in (-1, 1):
            cr.move_to(side * 12, -11)
            cr.line_to(side * 3, -8)
            cr.stroke()
    cr.set_source_rgb(0.2, 0.3, 0.2)
    for nx in (-2.5, 2.5):
        cr.arc(nx, 5, 0.9, 0, TAU)
        cr.fill()
    mouth(cr, 0, 10, pose.mouth)
    if "head" in gear:
        cr.save()
        cr.translate(0, -14)
        G.hat(cr, gear["head"], 19, "front", t)
        cr.restore()
    cr.restore()
