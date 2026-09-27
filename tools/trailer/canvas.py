"""Terminal text for the trailer: the engine's styled Text drawn cell by cell.

Glyphs come from JetBrainsMono Nerd Font Mono, emoji from Noto Color Emoji.
Block elements and powerline caps are drawn as shapes, the way kitty draws
them, so chips and bars join without seams. Rows are cached by content.
"""
import os
import sys

import cairo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from claude_statusline.width import char_width  # noqa: E402

MONO = "JetBrainsMono Nerd Font Mono"
EMOJI = "Noto Color Emoji"
SANS = "Noto Sans"


class Grid:
    """Cell metrics for one font size."""

    def __init__(self, size):
        probe = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 8, 8))
        probe.select_font_face(MONO)
        probe.set_font_size(size)
        self.size = size
        self.cw = probe.text_extents("M").x_advance
        ascent, descent, height = probe.font_extents()[:3]
        self.ch = round(height * 1.08)
        self.base = (self.ch - height) / 2 + ascent


def rgb(c, default):
    if c is None:
        return default
    return (c[0] / 255, c[1] / 255, c[2] / 255)


class Canvas:
    def __init__(self, grid, fg=(0.8, 0.83, 0.93)):
        self.g = grid
        self.fg = fg
        self.cache = {}

    def row(self, text, cols):
        """A surface `cols` cells wide with one row of Text on it (transparent where unstyled)."""
        key = (tuple(text.spans), cols)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        g = self.g
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, max(1, int(cols * g.cw + 1)), g.ch)
        cr = cairo.Context(surf)
        cr.set_font_size(g.size)
        x = 0
        cells = []
        for t, st in text.spans:
            chars = list(t)
            i = 0
            while i < len(chars):
                ch = chars[i]
                if i + 1 < len(chars) and chars[i + 1] == "️":
                    ch += "️"
                    i += 1
                cells.append((ch, st))
                i += 1
        for ch, (fg, bg, attrs, _) in cells:
            w = char_width(ch[0]) + (1 if len(ch) > 1 and char_width(ch[0]) == 1 else 0)
            if w == 0:
                continue
            if x >= cols:
                break
            px = x * g.cw
            if bg is not None:
                cr.set_source_rgb(*rgb(bg, (0, 0, 0)))
                cr.rectangle(px, 0, g.cw * w + 0.6, g.ch)
                cr.fill()
            if ch != " ":
                color = rgb(fg, self.fg)
                if attrs & 2:                        # faint
                    color = tuple(c * 0.6 for c in color)
                cr.set_source_rgb(*color)
                cp = ord(ch[0])
                if 0x2580 <= cp <= 0x259F:
                    block(cr, cp, px, g.cw, g.ch)
                elif cp in (0xE0B0, 0xE0B2, 0xE0B4, 0xE0B6, 0xE0B8, 0xE0BA, 0xE0BC, 0xE0BE):
                    cap(cr, cp, px, g.cw, g.ch)
                elif w == 2 or len(ch) > 1:
                    cr.save()
                    cr.select_font_face(EMOJI)
                    cr.set_font_size(g.size * 0.92)
                    cr.move_to(px, g.base - g.size * 0.05)
                    cr.show_text(ch)
                    cr.restore()
                else:
                    cr.select_font_face(MONO, cairo.FONT_SLANT_NORMAL,
                                        cairo.FONT_WEIGHT_BOLD if attrs & 1 else cairo.FONT_WEIGHT_NORMAL)
                    cr.move_to(px, g.base)
                    cr.show_text(ch)
            x += w
        surf.flush()
        if len(self.cache) > 4000:
            self.cache.clear()
        self.cache[key] = surf
        return surf


def block(cr, cp, x, w, h):
    if 0x2581 <= cp <= 0x2588:
        k = cp - 0x2580
        cr.rectangle(x, h * (1 - k / 8), w, h * k / 8)
    elif 0x2589 <= cp <= 0x258F:
        k = 0x2590 - cp
        cr.rectangle(x, 0, w * k / 8, h)
    elif cp == 0x2590:
        cr.rectangle(x + w / 2, 0, w / 2, h)
    elif cp == 0x2580:
        cr.rectangle(x, 0, w, h / 2)
    elif cp == 0x2596:
        cr.rectangle(x, h / 2, w / 2, h / 2)
    elif cp == 0x2584:
        cr.rectangle(x, h / 2, w, h / 2)
    elif cp in (0x2591, 0x2592, 0x2593):
        r, g, b, _ = cr.get_source().get_rgba()
        cr.set_source_rgba(r, g, b, {0x2591: 0.25, 0x2592: 0.5, 0x2593: 0.75}[cp])
        cr.rectangle(x, 0, w, h)
    else:
        cr.rectangle(x, 0, w, h)
    cr.fill()


def cap(cr, cp, x, w, h):
    cr.new_path()
    if cp == 0xE0B0:
        cr.move_to(x, 0); cr.line_to(x + w, h / 2); cr.line_to(x, h)
    elif cp == 0xE0B2:
        cr.move_to(x + w, 0); cr.line_to(x, h / 2); cr.line_to(x + w, h)
    elif cp == 0xE0B4:
        cr.save(); cr.translate(x, h / 2); cr.scale(w, h / 2); cr.move_to(0, -1); cr.arc(0, 0, 1, -1.5708, 1.5708)
        cr.restore()
    elif cp == 0xE0B6:
        cr.save(); cr.translate(x + w, h / 2); cr.scale(w, h / 2); cr.move_to(0, 1); cr.arc(0, 0, 1, 1.5708, 4.7124)
        cr.restore()
    elif cp == 0xE0BC:
        cr.move_to(x, 0); cr.line_to(x + w, 0); cr.line_to(x, h)
    elif cp == 0xE0BA:
        cr.move_to(x + w, 0); cr.line_to(x + w, h); cr.line_to(x, h)
    elif cp == 0xE0B8:
        cr.move_to(x, 0); cr.line_to(x + w, h); cr.line_to(x, h)
    elif cp == 0xE0BE:
        cr.move_to(x, 0); cr.line_to(x + w, 0); cr.line_to(x + w, h)
    cr.close_path()
    cr.fill()


def rounded(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -1.5708, 0)
    cr.arc(x + w - r, y + h - r, r, 0, 1.5708)
    cr.arc(x + r, y + h - r, r, 1.5708, 3.1416)
    cr.arc(x + r, y + r, r, 3.1416, 4.7124)
    cr.close_path()


def label(cr, text, x, y, size, rgb_, weight=cairo.FONT_WEIGHT_NORMAL, font=SANS, center=False):
    cr.select_font_face(font, cairo.FONT_SLANT_NORMAL, weight)
    cr.set_font_size(size)
    ext = cr.text_extents(text)
    cr.set_source_rgb(*rgb_)
    cr.move_to(x - (ext.x_advance / 2 if center else 0), y)
    cr.show_text(text)
    return ext.x_advance
