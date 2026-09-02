"""Terminal cell-width accounting, including the glyphs fonts get wrong."""
from __future__ import annotations

import unicodedata

from .config import WIDE


_ZERO_WIDTH = frozenset(
    {0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0xFEFF}
)

# Codepoints with Emoji_Presentation=Yes render two cells even though their
# East_Asian_Width is Neutral. Abridged to the ranges that actually occur in
# terminal UI text.
_EMOJI_WIDE = (
    (0x231A, 0x231B), (0x23E9, 0x23EC), (0x23F0, 0x23F0), (0x23F3, 0x23F3),
    (0x25FD, 0x25FE), (0x2614, 0x2615), (0x2648, 0x2653), (0x267F, 0x267F),
    (0x2693, 0x2693), (0x26A1, 0x26A1), (0x26AA, 0x26AB), (0x26BD, 0x26BE),
    (0x26C4, 0x26C5), (0x26CE, 0x26CE), (0x26D4, 0x26D4), (0x26EA, 0x26EA),
    (0x26F2, 0x26F3), (0x26F5, 0x26F5), (0x26FA, 0x26FA), (0x26FD, 0x26FD),
    (0x2705, 0x2705), (0x270A, 0x270B), (0x2728, 0x2728), (0x274C, 0x274C),
    (0x274E, 0x274E), (0x2753, 0x2755), (0x2757, 0x2757), (0x2795, 0x2797),
    (0x27B0, 0x27B0), (0x27BF, 0x27BF), (0x2B1B, 0x2B1C), (0x2B50, 0x2B50),
    (0x2B55, 0x2B55), (0x1F004, 0x1F004), (0x1F0CF, 0x1F0CF),
    (0x1F18E, 0x1F18E), (0x1F191, 0x1F19A), (0x1F1E6, 0x1F1FF),
    (0x1F201, 0x1F202), (0x1F21A, 0x1F21A), (0x1F22F, 0x1F22F),
    (0x1F232, 0x1F236), (0x1F238, 0x1F23A), (0x1F250, 0x1F251),
    (0x1F300, 0x1F320), (0x1F32D, 0x1F335), (0x1F337, 0x1F37C),
    (0x1F37E, 0x1F393), (0x1F3A0, 0x1F3CA), (0x1F3CF, 0x1F3D3),
    (0x1F3E0, 0x1F3F0), (0x1F3F4, 0x1F3F4), (0x1F3F8, 0x1F43E),
    (0x1F440, 0x1F440), (0x1F442, 0x1F4FC), (0x1F4FF, 0x1F53D),
    (0x1F54B, 0x1F54E), (0x1F550, 0x1F567), (0x1F5A4, 0x1F5A4),
    (0x1F5FB, 0x1F64F), (0x1F680, 0x1F6C5), (0x1F6CC, 0x1F6CC),
    (0x1F6D0, 0x1F6D2), (0x1F6D5, 0x1F6D7), (0x1F6EB, 0x1F6EC),
    (0x1F6F4, 0x1F6FC), (0x1F7E0, 0x1F7EB), (0x1F90C, 0x1F93A),
    (0x1F93C, 0x1F945), (0x1F947, 0x1F978), (0x1F97A, 0x1F9CB),
    (0x1F9CD, 0x1F9FF), (0x1FA70, 0x1FA74), (0x1FA78, 0x1FA7A),
    (0x1FA80, 0x1FA86), (0x1FA90, 0x1FAA8), (0x1FAB0, 0x1FAB6),
    (0x1FAC0, 0x1FAC2), (0x1FAD0, 0x1FAD6),
)


def _emoji_wide(cp: int) -> bool:
    lo, hi = 0, len(_EMOJI_WIDE) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        start, end = _EMOJI_WIDE[mid]
        if cp < start:
            hi = mid - 1
        elif cp > end:
            lo = mid + 1
        else:
            return True
    return False


def cell_width(ch: str) -> int:
    """Terminal cells one character occupies."""
    if ch in WIDE:
        return 2
    cp = ord(ch)
    if cp < 32 or 0x7F <= cp < 0xA0:
        return 0
    if cp in _ZERO_WIDTH or unicodedata.combining(ch):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    if _emoji_wide(cp):
        return 2
    return 1


def display_width(s: str) -> int:
    """Visible cell width, skipping ANSI SGR and OSC-8 hyperlink sequences."""
    width = 0
    last = 0
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\033":
            if s.startswith("\033]", i):                    # OSC ... ST | BEL
                end = s.find("\033\\", i)
                if end != -1:
                    i = end + 2
                else:
                    bel = s.find("\a", i)
                    i = n if bel == -1 else bel + 1
            elif s.startswith("\033[", i):                   # CSI ... final
                j = i + 2
                while j < n and not ("@" <= s[j] <= "~"):
                    j += 1
                i = min(j + 1, n)
            else:
                i += 2
            continue
        if ch == "\ufe0f":        # VS16 promotes the previous glyph to emoji
            if last == 1:
                width += 1
                last = 2
            i += 1
            continue
        if ch == "\ufe0e":        # VS15 forces text presentation
            i += 1
            continue
        last = cell_width(ch)
        width += last
        i += 1
    return width
