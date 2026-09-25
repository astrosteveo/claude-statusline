"""The terminal, driven directly: raw mode, the alternate screen, keys, mouse.

Frames are written whole inside a synchronized-update bracket (DEC 2026),
so terminals that support it swap them in without flicker and the rest just
draw them quickly. Everything is restored on exit, even after a crash.
"""
from __future__ import annotations

import os
import select
import signal
import sys


class Key:
    """A key press: `name` ('up', 'enter', 'a', 'ctrl-s'…), or a mouse event."""
    __slots__ = ("name", "char", "x", "y", "button")

    def __init__(self, name, char="", x=0, y=0, button=None):
        self.name = name
        self.char = char
        self.x = x
        self.y = y
        self.button = button

    def __repr__(self):
        return f"Key({self.name!r})"

    def __eq__(self, other):
        return self.name == other if isinstance(other, str) else NotImplemented

    def __hash__(self):
        return hash(self.name)


CSI_KEYS = {
    "A": "up", "B": "down", "C": "right", "D": "left", "H": "home", "F": "end", "Z": "shift-tab",
    "1~": "home", "4~": "end", "7~": "home", "8~": "end", "2~": "insert", "3~": "delete",
    "5~": "pgup", "6~": "pgdn",
}
MODS = {"2": "shift-", "3": "alt-", "4": "shift-alt-", "5": "ctrl-", "6": "ctrl-shift-"}


def parse_keys(data: str):
    """Split raw input into Keys."""
    keys = []
    i, n = 0, len(data)
    while i < n:
        ch = data[i]
        if ch == "\x1b":
            if i + 1 >= n:
                keys.append(Key("esc"))
                i += 1
                continue
            nxt = data[i + 1]
            if nxt == "[":
                j = i + 2
                if j < n and data[j] == "<":                   # SGR mouse
                    k = j + 1
                    while k < n and data[k] not in "mM":
                        k += 1
                    body = data[j + 1:k]
                    press = k < n and data[k] == "M"
                    i = k + 1
                    try:
                        b, x, y = (int(v) for v in body.split(";"))
                    except ValueError:
                        continue
                    if b in (64, 65):
                        keys.append(Key("wheel-up" if b == 64 else "wheel-down", x=x - 1, y=y - 1))
                    elif press and b in (0, 1, 2):
                        keys.append(Key("click", x=x - 1, y=y - 1, button=b))
                    continue
                k = j
                while k < n and not ("@" <= data[k] <= "~"):
                    k += 1
                if k >= n:
                    keys.append(Key("esc"))
                    i += 1
                    continue
                params, final = data[j:k], data[k]
                i = k + 1
                name = None
                if final == "~":
                    base, _, mod = params.partition(";")
                    name = CSI_KEYS.get(base + "~")
                    if name and mod in MODS:
                        name = MODS[mod] + name
                elif final in CSI_KEYS:
                    name = CSI_KEYS[final]
                    _, _, mod = params.partition(";")
                    if mod in MODS:
                        name = MODS[mod] + name
                if name:
                    keys.append(Key(name))
                continue
            if nxt == "O" and i + 2 < n:
                name = {"A": "up", "B": "down", "C": "right", "D": "left", "H": "home", "F": "end"}.get(data[i + 2])
                if name:
                    keys.append(Key(name))
                i += 3
                continue
            keys.append(Key("alt-" + nxt, nxt))
            i += 2
            continue
        if ch in ("\r", "\n"):
            keys.append(Key("enter"))
        elif ch == "\t":
            keys.append(Key("tab"))
        elif ch in ("\x7f", "\x08"):
            keys.append(Key("backspace"))
        elif ch == "\x00":
            keys.append(Key("ctrl-space"))
        elif ord(ch) < 32:
            keys.append(Key("ctrl-" + chr(ord(ch) + 96)))
        else:
            keys.append(Key(ch, ch))
        i += 1
    return keys


class Terminal:
    def __init__(self, mouse=True):
        self.fd_in = sys.stdin.fileno()
        self.fd_out = sys.stdout.fileno()
        self.mouse = mouse
        self.saved = None
        self.resized = True
        self._old_winch = None

    def __enter__(self):
        import termios
        import tty
        self.saved = termios.tcgetattr(self.fd_in)
        tty.setraw(self.fd_in)
        seq = "\x1b[?1049h\x1b[?25l\x1b[?7l"          # alt screen, hide cursor, no autowrap
        if self.mouse:
            seq += "\x1b[?1000h\x1b[?1006h"
        self.write(seq)
        self._old_winch = signal.signal(signal.SIGWINCH, self._on_winch)
        return self

    def __exit__(self, *exc):
        import termios
        seq = "\x1b[?1000l\x1b[?1006l" if self.mouse else ""
        self.write(seq + "\x1b[0m\x1b[?7h\x1b[?25h\x1b[?1049l")
        if self.saved is not None:
            termios.tcsetattr(self.fd_in, termios.TCSADRAIN, self.saved)
        if self._old_winch is not None:
            signal.signal(signal.SIGWINCH, self._old_winch)
        return False

    def _on_winch(self, *_):
        self.resized = True

    def size(self):
        try:
            sz = os.get_terminal_size(self.fd_out)
            return sz.columns, sz.lines
        except OSError:
            return 80, 24

    def write(self, s: str):
        data = s.encode("utf-8", "replace")
        while data:
            try:
                n = os.write(self.fd_out, data)
            except InterruptedError:
                continue
            data = data[n:]

    def frame(self, lines):
        """Draw a whole screen: one string per row, already padded."""
        out = ["\x1b[?2026h\x1b[H"]
        for i, line in enumerate(lines):
            out.append(line)
            out.append("\x1b[0m\x1b[K")
            if i < len(lines) - 1:
                out.append("\r\n")
        out.append("\x1b[J\x1b[?2026l")
        self.write("".join(out))

    def keys(self, timeout=None):
        """Keys typed within `timeout` seconds (an empty list on timeout or resize)."""
        try:
            ready, _, _ = select.select([self.fd_in], [], [], timeout)
        except InterruptedError:
            return []
        if not ready:
            return []
        data = os.read(self.fd_in, 4096)
        # A lone ESC might be the start of a sequence still arriving.
        if data.endswith(b"\x1b"):
            more, _, _ = select.select([self.fd_in], [], [], 0.03)
            if more:
                data += os.read(self.fd_in, 4096)
        return parse_keys(data.decode("utf-8", "replace"))
