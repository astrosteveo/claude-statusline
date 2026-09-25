"""Draw ANSI text (SGR colours; OSC-8 ignored) into a PNG the way a terminal would.

    python3 tools/shot.py out.png [--bg '#1e1e2e'] [--size 15] < ansi.txt

Lines starting with '#! ' are drawn as captions. Needs pycairo and a Nerd Font
(JetBrainsMono Nerd Font Mono by default; set SHOT_FONT to change it). Block
elements and powerline caps are drawn as shapes, as kitty does.
"""
import re
import sys

import cairo

import os  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from claude_statusline.color import index_rgb  # noqa: E402
from claude_statusline.width import char_width  # noqa: E402

FONT = os.environ.get("SHOT_FONT", "JetBrainsMono Nerd Font Mono")


def parse_line(line):
    """[(char, fg, bg, bold)]"""
    out = []
    fg = bg = None
    bold = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\x1b":
            if line.startswith("\x1b]", i):
                end = line.find("\x1b\\", i)
                i = len(line) if end == -1 else end + 2
                continue
            m = re.match(r"\x1b\[([0-9;]*)m", line[i:])
            if m:
                params = [int(p) if p else 0 for p in m.group(1).split(";")] if m.group(1) else [0]
                j = 0
                while j < len(params):
                    p = params[j]
                    if p == 0:
                        fg = bg = None; bold = False
                    elif p == 1:
                        bold = True
                    elif p == 22:
                        bold = False
                    elif p in (38, 48) and j + 1 < len(params):
                        if params[j + 1] == 2:
                            c = tuple(params[j + 2:j + 5]); j += 4
                        else:
                            c = index_rgb(params[j + 2]); j += 2
                        if p == 38: fg = c
                        else: bg = c
                    elif p == 39:
                        fg = None
                    elif p == 49:
                        bg = None
                    elif 30 <= p <= 37: fg = index_rgb(p - 30)
                    elif 90 <= p <= 97: fg = index_rgb(p - 82)
                    elif 40 <= p <= 47: bg = index_rgb(p - 40)
                    elif 100 <= p <= 107: bg = index_rgb(p - 92)
                    j += 1
                i += m.end()
                continue
            i += 1
            continue
        out.append((ch, fg, bg, bold))
        i += 1
    return out


def main():
    args = sys.argv[1:]
    out = args[0]
    bg = "#1c1b1f"
    size = 15
    if "--bg" in args:
        bg = args[args.index("--bg") + 1]
    if "--size" in args:
        size = float(args[args.index("--size") + 1])
    text = sys.stdin.read().rstrip("\n").split("\n")
    probe = cairo.ImageSurface(cairo.FORMAT_RGB24, 10, 10)
    cr = cairo.Context(probe)
    cr.select_font_face(FONT)
    cr.set_font_size(size)
    fe = cr.font_extents()
    cw = cr.text_extents("M").x_advance
    chh = fe[2] * 1.12
    rows = [parse_line(l) if not l.startswith("#! ") else l for l in text]
    ncols = max((sum(max(1, char_width(c[0])) for c in r) if isinstance(r, list) else len(r)) for r in rows)
    W, H = int(ncols * cw + 24), int(len(rows) * chh + 20)
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
    cr = cairo.Context(surf)
    h = bg.lstrip("#")
    base = tuple(int(h[k:k + 2], 16) / 255 for k in (0, 2, 4))
    cr.set_source_rgb(*base)
    cr.paint()
    default_fg = (0.85, 0.85, 0.85) if sum(base) < 1.5 else (0.15, 0.15, 0.15)
    for r, row in enumerate(rows):
        y0 = 10 + r * chh
        if isinstance(row, str):
            cr.select_font_face(FONT, cairo.FONT_SLANT_ITALIC)
            cr.set_font_size(size * 0.85)
            cr.set_source_rgb(0.5, 0.5, 0.55)
            cr.move_to(12, y0 + fe[0])
            cr.show_text(row[3:])
            continue
        x = 12
        for ch, fg, bgc, bold in row:
            w = char_width(ch)
            if w == 0:
                continue
            cells = w
            if bgc is not None:
                cr.set_source_rgb(*(v / 255 for v in bgc))
                cr.rectangle(x, y0, cw * cells + 0.6, chh + 0.6)
                cr.fill()
            if ch != " ":
                c = tuple(v / 255 for v in fg) if fg is not None else default_fg
                cr.set_source_rgb(*c)
                cr.select_font_face(FONT, cairo.FONT_SLANT_NORMAL,
                                    cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
                cr.set_font_size(size)
                # block elements: draw as rectangles like kitty does
                cp = ord(ch)
                if 0x2580 <= cp <= 0x259F:
                    draw_block(cr, ch, x, y0, cw, chh)
                elif cp in (0xE0B0, 0xE0B2, 0xE0B4, 0xE0B6, 0xE0BC, 0xE0BA, 0xE0B8, 0xE0BE):
                    draw_pl(cr, cp, x, y0, cw, chh)
                else:
                    cr.move_to(x, y0 + (chh - fe[2]) / 2 + fe[0])
                    cr.show_text(ch)
            x += cw * cells
    surf.write_to_png(out)


def draw_block(cr, ch, x, y, w, h):
    cp = ord(ch)
    if 0x2581 <= cp <= 0x2588:            # lower eighths .. full
        k = cp - 0x2580
        cr.rectangle(x, y + h * (1 - k / 8), w, h * k / 8)
    elif 0x2589 <= cp <= 0x258F:          # left 7/8 .. 1/8
        k = 0x2590 - cp
        cr.rectangle(x, y, w * k / 8, h)
    elif cp == 0x2590:                    # right half
        cr.rectangle(x + w / 2, y, w / 2, h)
    elif cp == 0x2580:                    # upper half
        cr.rectangle(x, y, w, h / 2)
    elif cp == 0x2596:                    # quadrant lower left
        cr.rectangle(x, y + h / 2, w / 2, h / 2)
    elif cp == 0x2584:
        cr.rectangle(x, y + h / 2, w, h / 2)
    elif cp in (0x2591, 0x2592, 0x2593):
        alpha = {0x2591: 0.25, 0x2592: 0.5, 0x2593: 0.75}[cp]
        r, g, b, _ = cr.get_source().get_rgba()
        cr.set_source_rgba(r, g, b, alpha)
        cr.rectangle(x, y, w, h)
    else:
        cr.rectangle(x, y, w, h)
    cr.fill()


def draw_pl(cr, cp, x, y, w, h):
    cr.new_path()
    if cp == 0xE0B0:
        cr.move_to(x, y); cr.line_to(x + w, y + h / 2); cr.line_to(x, y + h)
    elif cp == 0xE0B2:
        cr.move_to(x + w, y); cr.line_to(x, y + h / 2); cr.line_to(x + w, y + h)
    elif cp == 0xE0B4:
        cr.save(); cr.translate(x, y + h / 2); cr.scale(w, h / 2); cr.move_to(0, -1); cr.arc(0, 0, 1, -1.5708, 1.5708); cr.restore()
    elif cp == 0xE0B6:
        cr.save(); cr.translate(x + w, y + h / 2); cr.scale(w, h / 2); cr.move_to(0, 1); cr.arc(0, 0, 1, 1.5708, 4.7124); cr.restore()
    elif cp == 0xE0BC:
        cr.move_to(x, y); cr.line_to(x + w, y); cr.line_to(x, y + h)
    elif cp == 0xE0BA:
        cr.move_to(x + w, y); cr.line_to(x + w, y + h); cr.line_to(x, y + h)
    elif cp == 0xE0B8:
        cr.move_to(x, y); cr.line_to(x + w, y + h); cr.line_to(x, y + h)
    elif cp == 0xE0BE:
        cr.move_to(x, y); cr.line_to(x + w, y); cr.line_to(x + w, y + h)
    cr.close_path()
    cr.fill()


if __name__ == "__main__":
    main()
