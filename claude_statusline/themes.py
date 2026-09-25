"""Colour themes.

A theme names colours by role, not by use. Segments and templates ask for
roles (`accent`, `green`, `muted`…) and the theme decides what they look
like, so switching theme recolours everything at once.

    text subtext muted subtle   four levels of foreground, loud to quiet
    base surface overlay        backgrounds: the terminal, a chip, a raised chip
    accent                      the signature colour (the model, the cursor)
    blue cyan teal green yellow orange red pink purple gold    hues

`None` means the terminal's own default colour. Aliases (`model`, `dir`,
`dim`, `gray`, `ok`, `warn`…) resolve to roles, and every one of them,
alias or role, can be overridden in `[colors]`.
"""
from __future__ import annotations

from .color import mix, parse

ROLES = ("text", "subtext", "muted", "subtle", "base", "surface", "overlay", "accent",
         "blue", "cyan", "teal", "green", "yellow", "orange", "red", "pink", "purple", "gold")

ALIASES = {
    "model": "accent", "dir": "blue", "dim": "muted", "gray": "subtext", "grey": "subtext",
    "ok": "green", "warn": "yellow", "alert": "orange", "crit": "red", "info": "cyan",
    "magenta": "pink", "violet": "purple", "fg": "text", "bg": "base", "track": "subtle",
    "sep": "subtle", "white": "text",
}


def _t(desc, light=False, **roles):
    roles["_desc"] = desc
    roles["_light"] = light
    return roles


THEMES = {
    "claude": _t(
        "Warm clay and cream, after Claude's own colours.",
        text="#ede6dc", subtext="#bdb3a7", muted="#8a8178", subtle="#57504a",
        base="#1f1b18", surface="#2f2a26", overlay="#3f3833",
        accent="#d97757", blue="#88a9d6", cyan="#7ec2c2", teal="#6fb5a0", green="#a3c47f",
        yellow="#e8c173", orange="#e8935b", red="#e06b64", pink="#d98cae", purple="#b39ddb",
        gold="#d6a95c"),
    "claude-light": _t(
        "Claude's clay on warm paper, for light terminals.", light=True,
        text="#2b2622", subtext="#5c544c", muted="#857c72", subtle="#cfc6b8",
        base="#faf9f5", surface="#ece6da", overlay="#ddd5c6",
        accent="#c15f3c", blue="#3f6fb0", cyan="#1f7a7a", teal="#2e8a6e", green="#5a8a2e",
        yellow="#a7780a", orange="#c4621d", red="#c2413b", pink="#b44b7e", purple="#7351b8",
        gold="#9c6f14"),
    "catppuccin": _t(
        "Catppuccin Mocha: soothing pastels on deep blue-grey.",
        text="#cdd6f4", subtext="#a6adc8", muted="#7f849c", subtle="#585b70",
        base="#1e1e2e", surface="#313244", overlay="#45475a",
        accent="#cba6f7", blue="#89b4fa", cyan="#89dceb", teal="#94e2d5", green="#a6e3a1",
        yellow="#f9e2af", orange="#fab387", red="#f38ba8", pink="#f5c2e7", purple="#b4befe",
        gold="#f9e2af"),
    "catppuccin-latte": _t(
        "Catppuccin Latte, the light flavour.", light=True,
        text="#4c4f69", subtext="#6c6f85", muted="#8c8fa1", subtle="#bcc0cc",
        base="#eff1f5", surface="#dce0e8", overlay="#ccd0da",
        accent="#8839ef", blue="#1e66f5", cyan="#04a5e5", teal="#179299", green="#40a02b",
        yellow="#df8e1d", orange="#fe640b", red="#d20f39", pink="#ea76cb", purple="#7287fd",
        gold="#df8e1d"),
    "tokyo-night": _t(
        "Tokyo Night: neon city lights at midnight.",
        text="#c0caf5", subtext="#a9b1d6", muted="#737aa2", subtle="#545c7e",
        base="#1a1b26", surface="#292e42", overlay="#3b4261",
        accent="#bb9af7", blue="#7aa2f7", cyan="#7dcfff", teal="#73daca", green="#9ece6a",
        yellow="#e0af68", orange="#ff9e64", red="#f7768e", pink="#ff79c6", purple="#9d7cd8",
        gold="#e0af68"),
    "midnight": _t(
        "Midnight: ink, lavender, blue and sea green (Tokyo Night Moon's hues).",
        text="#c8d3f5", subtext="#a9b8e8", muted="#828bb8", subtle="#3b4261",
        base="#161a26", surface="#252b3d", overlay="#2f3549",
        accent="#c099ff", blue="#82aaff", cyan="#86e1fc", teal="#4fd6be", green="#c3e88d",
        yellow="#ffc777", orange="#ff966c", red="#ff757f", pink="#fca7ea", purple="#c099ff",
        gold="#ffc777"),
    "nord": _t(
        "Nord: an arctic, north-bluish palette.",
        text="#eceff4", subtext="#d8dee9", muted="#8591a8", subtle="#4c566a",
        base="#2e3440", surface="#3b4252", overlay="#434c5e",
        accent="#88c0d0", blue="#81a1c1", cyan="#88c0d0", teal="#8fbcbb", green="#a3be8c",
        yellow="#ebcb8b", orange="#d08770", red="#bf616a", pink="#b48ead", purple="#b48ead",
        gold="#ebcb8b"),
    "dracula": _t(
        "Dracula: the classic dark theme with vivid accents.",
        text="#f8f8f2", subtext="#d0d0e0", muted="#7e89b8", subtle="#4d5068",
        base="#282a36", surface="#383a4a", overlay="#44475a",
        accent="#bd93f9", blue="#8be9fd", cyan="#8be9fd", teal="#69e5c0", green="#50fa7b",
        yellow="#f1fa8c", orange="#ffb86c", red="#ff5555", pink="#ff79c6", purple="#bd93f9",
        gold="#f1fa8c"),
    "gruvbox": _t(
        "Gruvbox: retro groove, warm and earthy.",
        text="#ebdbb2", subtext="#d5c4a1", muted="#a89984", subtle="#665c54",
        base="#282828", surface="#3c3836", overlay="#504945",
        accent="#fe8019", blue="#83a598", cyan="#8ec07c", teal="#8ec07c", green="#b8bb26",
        yellow="#fabd2f", orange="#fe8019", red="#fb4934", pink="#d3869b", purple="#d3869b",
        gold="#fabd2f"),
    "rose-pine": _t(
        "Rosé Pine: all natural pine, faux fur and a bit of soho vibes.",
        text="#e0def4", subtext="#b8b5d0", muted="#908caa", subtle="#524f67",
        base="#191724", surface="#26233a", overlay="#393552",
        accent="#c4a7e7", blue="#9ccfd8", cyan="#9ccfd8", teal="#7fb8b0", green="#95c4a0",
        yellow="#f6c177", orange="#f2a57e", red="#eb6f92", pink="#ebbcba", purple="#c4a7e7",
        gold="#f6c177"),
    "kanagawa": _t(
        "Kanagawa: the colours of Hokusai's Great Wave.",
        text="#dcd7ba", subtext="#c8c093", muted="#8a8980", subtle="#54546d",
        base="#1f1f28", surface="#2a2a37", overlay="#363646",
        accent="#957fb8", blue="#7e9cd8", cyan="#7fb4ca", teal="#7aa89f", green="#98bb6c",
        yellow="#e6c384", orange="#ffa066", red="#e46876", pink="#d27e99", purple="#957fb8",
        gold="#c0a36e"),
    "everforest": _t(
        "Everforest: a green-based, comfortable forest palette.",
        text="#d3c6aa", subtext="#b4b09a", muted="#859289", subtle="#4f585e",
        base="#2d353b", surface="#343f44", overlay="#3d484d",
        accent="#a7c080", blue="#7fbbb3", cyan="#83c092", teal="#83c092", green="#a7c080",
        yellow="#dbbc7f", orange="#e69875", red="#e67e80", pink="#d699b6", purple="#d699b6",
        gold="#dbbc7f"),
    "one-dark": _t(
        "One Dark: Atom's calm, balanced dark theme.",
        text="#d7dae0", subtext="#abb2bf", muted="#7f848e", subtle="#4b5263",
        base="#282c34", surface="#31353f", overlay="#3e4451",
        accent="#c678dd", blue="#61afef", cyan="#56b6c2", teal="#56b6c2", green="#98c379",
        yellow="#e5c07b", orange="#d19a66", red="#e06c75", pink="#de73a6", purple="#c678dd",
        gold="#e5c07b"),
    "solarized-dark": _t(
        "Solarized: precision colours, dark background.",
        text="#93a1a1", subtext="#839496", muted="#657b83", subtle="#35525c",
        base="#002b36", surface="#073642", overlay="#0f4555",
        accent="#6c71c4", blue="#268bd2", cyan="#2aa198", teal="#2aa198", green="#859900",
        yellow="#b58900", orange="#cb4b16", red="#dc322f", pink="#d33682", purple="#6c71c4",
        gold="#b58900"),
    "solarized-light": _t(
        "Solarized: precision colours, light background.", light=True,
        text="#586e75", subtext="#657b83", muted="#839496", subtle="#d6cfb9",
        base="#fdf6e3", surface="#eee8d5", overlay="#e2dbc5",
        accent="#6c71c4", blue="#268bd2", cyan="#2aa198", teal="#2aa198", green="#859900",
        yellow="#b58900", orange="#cb4b16", red="#dc322f", pink="#d33682", purple="#6c71c4",
        gold="#b58900"),
    "synthwave": _t(
        "Synthwave '84: neon glow on a purple night.",
        text="#f4eeff", subtext="#cdbfe6", muted="#9483b5", subtle="#4f3f6b",
        base="#262335", surface="#34294f", overlay="#463465",
        accent="#ff7edb", blue="#6fc3ff", cyan="#36f9f6", teal="#72f1b8", green="#72f1b8",
        yellow="#fede5d", orange="#ff8b39", red="#fe4450", pink="#ff7edb", purple="#b893ce",
        gold="#fede5d"),
    "mono": _t(
        "Monochrome, with colour kept only for warnings.",
        text="#e4e4e4", subtext="#b2b2b2", muted="#808080", subtle="#4e4e4e",
        base="#1c1c1c", surface="#2e2e2e", overlay="#3d3d3d",
        accent="#ffffff", blue="#c6c6c6", cyan="#c6c6c6", teal="#bcbcbc", green="#d0d0d0",
        yellow="#e0c070", orange="#e09050", red="#e06060", pink="#c6c6c6", purple="#c6c6c6",
        gold="#d0d0d0"),
    "terminal": _t(
        "Your terminal's own 16 colours, so the bar follows its theme.",
        text=None, subtext=7, muted=8, subtle=8,
        base=0, surface=8, overlay=8,
        accent=5, blue=4, cyan=6, teal=6, green=2,
        yellow=3, orange=11, red=1, pink=13, purple=5, gold=3),
    "classic": _t(
        "The original claude-statusline 256-colour palette.",
        text=None, subtext=245, muted=240, subtle=240,
        base=234, surface=236, overlay=238,
        accent=141, blue=39, cyan=80, teal=80, green=114,
        yellow=221, orange=208, red=203, pink=176, purple=176, gold=179),
}

DEFAULT_THEME = "claude"


def theme_names():
    return list(THEMES)


def describe(name):
    t = THEMES.get(name) or {}
    return t.get("_desc", "")


def is_light(name):
    return bool((THEMES.get(name) or {}).get("_light"))


def palette(name, overrides=None):
    """Role and alias -> colour tuple (or None for the terminal default).

    Unknown theme names fall back to the default theme. `overrides` maps a
    role or alias to any colour spec `color.parse` understands.
    """
    spec = THEMES.get(name) or THEMES[DEFAULT_THEME]
    pal = {}
    for role in ROLES:
        pal[role] = parse(spec.get(role)) if spec.get(role) is not None else None
    for alias, role in ALIASES.items():
        pal.setdefault(alias, pal.get(role))
    for key, val in (overrides or {}).items():
        if key in ("reset", "bold"):
            continue                    # v2 kept SGR attributes here; attributes are tags now
        c = parse(val)
        if c is not None:
            pal[key] = c
            for alias, role in ALIASES.items():
                if role == key and alias not in (overrides or {}):
                    pal[alias] = c
    # Derived tones the looks use for tracks and chip edges.
    base = pal.get("base") or (0, 0, 0, -1)
    text = pal.get("text") or ((20, 20, 20, -1) if is_light(name) else (230, 230, 230, -1))
    pal.setdefault("_text", text)
    pal["_dark"] = base if not is_light(name) else text
    pal["_light"] = text if not is_light(name) else base
    if pal.get("surface") is None:
        pal["surface"] = mix(base, text, 0.12)
    return pal
