"""Terminal cell widths, measured the way Claude Code measures them.

Claude Code draws the status line with Ink, which sizes text with the
`string-width` package: East Asian Wide and Fullwidth characters (every
emoji with emoji presentation among them) take two cells, combining marks
and format characters take none, a text-style emoji followed by VS16 is
promoted to two, and everything else takes one. Measuring identically is
what keeps a right-aligned group exactly on the host's right edge.

`WIDE` holds glyphs the user's font draws two cells wide although Unicode
calls them narrow; the config fills it from `layout.wide_glyphs`.
"""
from __future__ import annotations

import unicodedata

WIDE: set = set()

# Emoji=Yes code points that are narrow by default and become a two-cell
# emoji when followed by VS16 (U+FE0F). From Unicode 16 emoji-data.txt.
_VS16_RANGES = (
    (0x23, 0x23), (0x2A, 0x2A), (0x30, 0x39), (0xA9, 0xA9), (0xAE, 0xAE), (0x203C, 0x203C),
    (0x2049, 0x2049), (0x2122, 0x2122), (0x2139, 0x2139), (0x2194, 0x2199), (0x21A9, 0x21AA),
    (0x2328, 0x2328), (0x23CF, 0x23CF), (0x23ED, 0x23EF), (0x23F1, 0x23F2), (0x23F8, 0x23FA),
    (0x24C2, 0x24C2), (0x25AA, 0x25AB), (0x25B6, 0x25B6), (0x25C0, 0x25C0), (0x25FB, 0x25FC),
    (0x2600, 0x2604), (0x260E, 0x260E), (0x2611, 0x2611), (0x2618, 0x2618), (0x261D, 0x261D),
    (0x2620, 0x2620), (0x2622, 0x2623), (0x2626, 0x2626), (0x262A, 0x262A), (0x262E, 0x262F),
    (0x2638, 0x263A), (0x2640, 0x2640), (0x2642, 0x2642), (0x265F, 0x2660), (0x2663, 0x2663),
    (0x2665, 0x2666), (0x2668, 0x2668), (0x267B, 0x267B), (0x267E, 0x267E), (0x2692, 0x2692),
    (0x2694, 0x2697), (0x2699, 0x2699), (0x269B, 0x269C), (0x26A0, 0x26A0), (0x26A7, 0x26A7),
    (0x26B0, 0x26B1), (0x26C8, 0x26C8), (0x26CF, 0x26CF), (0x26D1, 0x26D1), (0x26D3, 0x26D3),
    (0x26E9, 0x26E9), (0x26F0, 0x26F1), (0x26F4, 0x26F4), (0x26F7, 0x26F9), (0x2702, 0x2702),
    (0x2708, 0x2709), (0x270C, 0x270D), (0x270F, 0x270F), (0x2712, 0x2712), (0x2714, 0x2714),
    (0x2716, 0x2716), (0x271D, 0x271D), (0x2721, 0x2721), (0x2733, 0x2734), (0x2744, 0x2744),
    (0x2747, 0x2747), (0x2763, 0x2764), (0x27A1, 0x27A1), (0x2934, 0x2935), (0x2B05, 0x2B07),
    (0x1F170, 0x1F171), (0x1F17E, 0x1F17F), (0x1F321, 0x1F321), (0x1F324, 0x1F32C),
    (0x1F336, 0x1F336), (0x1F37D, 0x1F37D), (0x1F396, 0x1F397), (0x1F399, 0x1F39B),
    (0x1F39E, 0x1F39F), (0x1F3CB, 0x1F3CE), (0x1F3D4, 0x1F3DF), (0x1F3F3, 0x1F3F3),
    (0x1F3F5, 0x1F3F5), (0x1F3F7, 0x1F3F7), (0x1F43F, 0x1F43F), (0x1F441, 0x1F441),
    (0x1F4FD, 0x1F4FD), (0x1F549, 0x1F54A), (0x1F56F, 0x1F570), (0x1F573, 0x1F579),
    (0x1F587, 0x1F587), (0x1F58A, 0x1F58D), (0x1F590, 0x1F590), (0x1F5A5, 0x1F5A5),
    (0x1F5A8, 0x1F5A8), (0x1F5B1, 0x1F5B2), (0x1F5BC, 0x1F5BC), (0x1F5C2, 0x1F5C4),
    (0x1F5D1, 0x1F5D3), (0x1F5DC, 0x1F5DE), (0x1F5E1, 0x1F5E1), (0x1F5E3, 0x1F5E3),
    (0x1F5E8, 0x1F5E8), (0x1F5EF, 0x1F5EF), (0x1F5F3, 0x1F5F3), (0x1F5FA, 0x1F5FA),
    (0x1F6CB, 0x1F6CB), (0x1F6CD, 0x1F6CF), (0x1F6E0, 0x1F6E5), (0x1F6E9, 0x1F6E9),
    (0x1F6F0, 0x1F6F0), (0x1F6F3, 0x1F6F3),
)


def _promotable(cp: int) -> bool:
    lo, hi = 0, len(_VS16_RANGES) - 1
    while lo <= hi:
        mid = (lo + hi) >> 1
        a, b = _VS16_RANGES[mid]
        if cp < a:
            hi = mid - 1
        elif cp > b:
            lo = mid + 1
        else:
            return True
    return False


_CHAR: dict = {}


def char_width(ch: str) -> int:
    """Cells one code point takes on its own."""
    w = _CHAR.get(ch)
    if w is not None:
        return w
    cp = ord(ch)
    if ch in WIDE:
        w = 2
    elif cp < 0x20 or 0x7F <= cp < 0xA0:
        w = 0
    elif unicodedata.category(ch) in ("Mn", "Me", "Cf"):
        w = 0
    elif unicodedata.east_asian_width(ch) in ("W", "F"):
        w = 2
    else:
        w = 1
    _CHAR[ch] = w
    return w


_STR: dict = {}


def width(s: str) -> int:
    """Cells a run of plain text (no escape sequences) takes."""
    if s.isascii():
        if s.isprintable():
            return len(s)
        return sum(1 for ch in s if " " <= ch <= "~")
    w = _STR.get(s)
    if w is not None:
        return w
    total = 0
    prev_cp = -1
    prev_w = 0
    joined = False
    for ch in s:
        cp = ord(ch)
        if cp == 0xFE0F:                         # VS16: emoji presentation
            if prev_w == 1 and _promotable(prev_cp):
                total += 1
                prev_w = 2
            continue
        if cp == 0x200D:                         # ZWJ glues the next glyph on
            joined = True
            continue
        if joined:
            joined = False
            continue
        if 0x1F3FB <= cp <= 0x1F3FF and prev_w == 2:
            continue                             # skin tone modifies the emoji before it
        cw = char_width(ch)
        total += cw
        if cw:
            prev_cp, prev_w = cp, cw
    if len(_STR) < 4096:
        _STR[s] = total
    return total


def ansi_width(s: str) -> int:
    """Width of text that may carry SGR and OSC-8 sequences."""
    if "\033" not in s:
        return width(s)
    return width(strip_ansi(s))


def strip_ansi(s: str) -> str:
    out = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch != "\033":
            j = s.find("\033", i)
            if j == -1:
                out.append(s[i:])
                break
            out.append(s[i:j])
            i = j
            continue
        if s.startswith("\033]", i):             # OSC ... ST | BEL
            end = s.find("\033\\", i)
            bel = s.find("\a", i)
            if end == -1 or (bel != -1 and bel < end):
                i = n if bel == -1 else bel + 1
            else:
                i = end + 2
        elif s.startswith("\033[", i):           # CSI ... final byte
            j = i + 2
            while j < n and not ("@" <= s[j] <= "~"):
                j += 1
            i = j + 1
        else:
            i += 2
    return "".join(out)


def clip(s: str, cells: int, ellipsis: str = "…") -> str:
    """Plain text cut to at most `cells` cells, ending in `ellipsis` if cut."""
    if width(s) <= cells:
        return s
    if cells <= 0:
        return ""
    room = cells - width(ellipsis)
    out, used = [], 0
    for ch in s:
        cw = char_width(ch)
        if used + cw > room:
            break
        out.append(ch)
        used += cw
    return "".join(out).rstrip() + ellipsis if room > 0 else ellipsis[:cells]
