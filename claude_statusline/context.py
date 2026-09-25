"""Everything a segment may look at while rendering one refresh."""
from __future__ import annotations

import os
import time

from . import icons as iconmod
from .bar import level_role, make_bar
from .color import detect_mode, mix, parse as parse_color, readable_on
from .util import dig

VIVID = ("powerline", "slant", "pills")
NERD_STYLES = ("powerline", "slant", "pills", "capsules")


def nerd_terminal(env) -> bool:
    """Terminals that bundle the Nerd Font symbols, so icons work with any font."""
    term = env.get("TERM", "")
    prog = env.get("TERM_PROGRAM", "")
    return (term in ("xterm-kitty", "xterm-ghostty") or "KITTY_WINDOW_ID" in env
            or prog in ("WezTerm", "ghostty"))


def resolve_look(comp, env):
    """(style, iconset, colour mode) with every "auto" decided."""
    nerd = nerd_terminal(env)
    icons = comp.get("icons", "auto")
    if icons == "auto":
        icons = "nerd" if nerd else "unicode"
    style = comp.get("style", "auto")
    if style == "auto":
        style = "capsules" if icons == "nerd" else "chips"
    if style in NERD_STYLES and icons != "nerd" and not nerd and comp.get("icons") == "auto":
        style = "chips"
    mode = comp.get("color", "auto")
    if mode == "auto":
        mode = detect_mode(env)
    return style, icons, mode


class Context:
    def __init__(self, data, comp, cols=None, now=None, env=None, sync_git=False, live=None):
        env = os.environ if env is None else env
        self.env = env
        self.data = data if isinstance(data, dict) else {}
        self.comp = comp
        self.pal = comp["palette"]
        self.thresholds = comp["thresholds"]
        self.bar_cfg = comp["bar"]
        self.quest_cfg = comp.get("quest") or {}
        self.style, self.iconset, self.mode = resolve_look(comp, env)
        self.vivid = self.style in VIVID
        self.marks = iconmod.marks(self.iconset, comp.get("glyphs"))
        self.now = time.time() if now is None else float(now)
        lay = comp["layout"]
        if cols is None:
            try:
                cols = int(env.get("COLUMNS") or 0)
            except ValueError:
                cols = 0
            cols = cols or lay.get("fallback_columns", 200)
        self.cols = cols
        self.avail = max(20, cols - max(0, lay.get("right_margin", 5)))
        cwd = dig(self.data, "workspace", "current_dir") or self.data.get("cwd")
        self.cwd = cwd if isinstance(cwd, str) and cwd else os.getcwd()
        home = self.data.get("_home")              # sample payloads name their own home
        self.home = home if isinstance(home, str) and home else os.path.expanduser("~")
        self.sync_git = sync_git
        # A live render (the bar itself) may start background work: git
        # refreshes, avatar uploads. Previews and tests never do.
        self.live = (not sync_git) if live is None else live
        self.avatar_active = False
        self._memo = {}

    def memo(self, key, compute):
        if key not in self._memo:
            self._memo[key] = compute()
        return self._memo[key]

    # -- colours -----------------------------------------------------------
    def color(self, name):
        """A theme role, alias, or #hex -> colour tuple (None if unknown)."""
        if name is None:
            return None
        c = self.pal.get(name)
        if c is not None:
            return c
        return parse_color(name) if isinstance(name, str) and name.startswith("#") else None

    def level_role(self, pct):
        return level_role(pct, self.thresholds)

    def chip_ink(self, tone):
        """Text colour that reads on a chip of colour `tone`."""
        dark, light = self.pal.get("_dark"), self.pal.get("_light")
        if tone is None or dark is None or light is None:
            return dark
        return readable_on(tone, dark, light)

    # -- bars --------------------------------------------------------------
    def bar(self, pct, width, style="", fill="", tone=None):
        b = self.bar_cfg
        tone_c = self.color(tone) if isinstance(tone, str) else tone
        ink = None
        if self.vivid and tone_c is not None:
            # On a coloured chip the bar is drawn in the chip's own hue: a deep
            # fill on a track just a shade darker than the chip.
            ink_c = self.chip_ink(tone_c)
            ink = (mix(tone_c, ink_c, 0.8), mix(tone_c, ink_c, 0.22))
        return make_bar(pct, width, pal=self.pal, thresholds=self.thresholds,
                        style=style or b.get("style", "smooth"), fill=fill or b.get("fill", "level"),
                        track=b.get("track", "subtle"), tone=tone_c, now=self.now,
                        pulse=b.get("pulse", False), ink=ink, mono=self.mode == "none",
                        min_sliver=b.get("min_sliver", True),
                        caps=(b.get("cap_left", ""), b.get("cap_right", ""))
                        if (b.get("cap_left") or b.get("cap_right")) else None)

    def bar_width(self, opts, level):
        """A bar segment's width at a detail level: half at narrow, none at text."""
        from .fit import NARROW, TEXT
        base = opts.get("width", -1)
        if base is None or base < 0:
            base = self.bar_cfg.get("width", 13)
        if level >= TEXT:
            return 0
        if level >= NARROW:
            return max(4, base // 2)
        return base

    # -- shared lookups ----------------------------------------------------
    def git(self, last_commit=True):
        def get():
            fake = self.data.get("_git")
            if isinstance(fake, dict):          # sample payloads carry their own repo state
                g = {"branch": None, "sha": None, "upstream": None, "ahead": 0, "behind": 0,
                     "staged": 0, "dirty": 0, "untracked": 0, "conflict": 0, "stash": 0,
                     "state": None, "last_commit": None}
                g.update({k: v for k, v in fake.items() if k in g})
                if fake.get("last_commit_ago"):
                    g["last_commit"] = self.now - float(fake["last_commit_ago"])
                return g
            if not self.comp["git"].get("enabled", True):
                return None
            from .gitstatus import status
            return status(self.cwd, self.comp["git"], sync=self.sync_git, last_commit=last_commit)
        return self.memo(("git", last_commit), get)

    def windows(self):
        def get():
            from .payload import find_windows
            return find_windows(self.data)
        return self.memo("windows", get)

    def mark(self, key):
        return self.marks.get(key, "")
