"""Icon sets: the glyph each segment wears, and the small marks inside them.

    nerd     Nerd Font icons. Kitty, WezTerm and Ghostty bundle the symbols,
             so they work there without installing a patched font.
    unicode  Plain Unicode symbols that ordinary monospace fonts carry.
    emoji    Colour emoji, two cells each.
    none     No segment icons; text only.

Every icon except the emoji set is one cell. `[glyphs]` in the config
overrides single entries, and `[segment.<name>] icon = "..."` overrides one
segment.
"""
from __future__ import annotations

SETS = ("nerd", "unicode", "emoji", "none")

# Segment icons.
ICONS = {
    "nerd": {
        "model": "\U000f0674", "dir": "", "git": "", "pr": "",
        "worktree": "\U000f0645", "context": "\U000f035b", "limit_5h": "\U000f051f",
        "limit_7d": "\U000f00ed", "limit_7d_model": "\U000f00ed", "limit_spend": "\U000f0114",
        "cost": "", "duration": "\U000f051b", "diff": "", "cache": "\U000f01bc",
        "env": "", "host": "", "session": "\U000f018d", "output_style": "\U000f03d8",
        "version": "", "agent": "\U000f06a9", "vim": "", "clock": "\U000f0954",
        "tokens": "\U000f04e1", "burn": "\U000f0238",
        "quest": "\U000f04e5", "quest_boss": "\U000f068c", "quest_daily": "",
        "quest_buffs": "\U000f0241", "quest_streak": "\U000f0238", "quest_pet": "\U000f03e9",
        "quest_event": "", "quest_gold": "\U000f0e95", "text": "", "heartbeat": "",
    },
    # Every glyph here is in JetBrains Mono and DejaVu Sans Mono, so none
    # depends on font fallback.
    "unicode": {
        "model": "✶", "dir": "▸", "git": "⌥", "pr": "⊕", "worktree": "⊞",
        "context": "◔", "limit_5h": "◶", "limit_7d": "⊡", "limit_7d_model": "⊡",
        "limit_spend": "¤", "cost": "$", "duration": "◕", "diff": "±", "cache": "⊙",
        "env": "◉", "host": "⌂", "session": "§", "output_style": "¶", "version": "v",
        "agent": "⍟", "vim": "", "clock": "", "tokens": "≡", "burn": "∆",
        "quest": "†", "quest_boss": "Ω", "quest_daily": "✓", "quest_buffs": "▲",
        "quest_streak": "◆", "quest_pet": "♥", "quest_event": "◈", "quest_gold": "◎",
        "text": "", "heartbeat": "",
    },
    "emoji": {
        "model": "🤖", "dir": "📂", "git": "🌿", "pr": "🔀", "worktree": "🌳",
        "context": "🧠", "limit_5h": "⏳", "limit_7d": "📅", "limit_7d_model": "📅",
        "limit_spend": "💳", "cost": "💰", "duration": "⌛", "diff": "📝", "cache": "💾",
        "env": "🐍", "host": "💻", "session": "💬", "output_style": "🎨", "version": "🔖",
        "agent": "🦾", "vim": "📟", "clock": "🕐", "tokens": "🔢", "burn": "🔥",
        "quest": "⚔️", "quest_boss": "👹", "quest_daily": "📜", "quest_buffs": "✨",
        "quest_streak": "🔥", "quest_pet": "🐾", "quest_event": "🔔", "quest_gold": "🪙",
        "text": "", "heartbeat": "",
    },
    "none": {},
}

# Marks used inside segments. Keys double as v2 `[glyphs]` names.
MARKS = {
    "nerd": {"ahead": "↑", "behind": "↓", "stash": "\U000f03d7", "pace": "→", "reset": "\U000f0450",
             "fast": "\U000f140b", "age": "\U000f0954", "noupstream": "∅", "conflict": "!",
             "staged": "+", "dirty": "~", "untracked": "?", "ok": "✓", "fail": "✗", "wait": "●",
             "heart": "\U000f02d1", "heart_empty": "\U000f02d5", "sep": "·"},
    "unicode": {"ahead": "↑", "behind": "↓", "stash": "≡", "pace": "→", "reset": "↻",
                "fast": "⚡", "age": "◔", "noupstream": "∅", "conflict": "!",
                "staged": "+", "dirty": "~", "untracked": "?", "ok": "✓", "fail": "✗", "wait": "●",
                "heart": "♥", "heart_empty": "♡", "sep": "·"},
}
MARKS["emoji"] = dict(MARKS["unicode"], fast="⚡")
MARKS["none"] = MARKS["unicode"]

# v2 `[glyphs]` keys that named segment icons.
LEGACY_ICON_KEYS = {"model": "model", "dir": "dir", "git": "git", "pr": "pr", "host": "host",
                    "env": "env", "cache": "cache"}

HEARTBEAT_FRAMES = {
    "dots": "⠋⠙⠹⠸⠼⠴⠦⠧", "orbit": "⠁⠂⠄⡀⢀⠠⠐⠈", "quadrants": "▘▝▗▖", "arc": "◐◓◑◒",
    "wave": "▁▂▃▄▅▆▇▆▅▄▃▂", "pulse": "·•●•", "bounce": "⠁⠂⠄⠂", "line": "|/-\\",
    "moon": "◯◔◑◕●◕◑◔", "grow": "▏▎▍▌▋▊▉█▉▊▋▌▍▎", "star": "✶✷✸✹✺✹✸✷",
}


def icon_for(name: str, iconset: str, overrides=None) -> str:
    """The icon a segment type wears in `iconset` (after `[glyphs]` overrides)."""
    if overrides and name in overrides and name in LEGACY_ICON_KEYS:
        return str(overrides[name])
    return ICONS.get(iconset, ICONS["unicode"]).get(name, "")


def marks(iconset: str, overrides=None) -> dict:
    out = dict(MARKS.get(iconset, MARKS["unicode"]))
    for key, val in (overrides or {}).items():
        if key in out and isinstance(val, str):
            out[key] = val
    return out
