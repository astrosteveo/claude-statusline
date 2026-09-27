# Config schema

One TOML file (`~/.config/claude-statusline/config.toml`, or
`$CLAUDE_STATUSLINE_CONFIG`). Every key is optional and merges over the
defaults, so this is a complete config:

```toml
theme = "catppuccin"
style = "capsules"
```

## Top level

| key | default | meaning |
|-----|---------|---------|
| `preset` | `"classic"` | the lines to use when the file declares none: classic, compact, dashboard, focus, minimal |
| `theme` | `"claude"` | colours: claude, claude-light, midnight, catppuccin, catppuccin-latte, tokyo-night, nord, dracula, gruvbox, rose-pine, kanagawa, everforest, one-dark, solarized-dark, solarized-light, synthwave, mono, terminal, classic |
| `style` | `"auto"` | how segments are dressed: minimal, classic, dots, chips, capsules, pills, powerline, slant. `auto` is capsules in terminals that bundle Nerd Font symbols (kitty, WezTerm, Ghostty), chips elsewhere |
| `icons` | `"auto"` | nerd, unicode, emoji, none. `auto` follows the terminal the same way |
| `color` | `"auto"` | colour depth: truecolor, 256, 16, none. `auto` reads COLORTERM (NO_COLOR turns it off) |

## Lines

```toml
[[line]]                                  # one row of the bar
left  = ["model", "dir", "git"]           # flows from the left edge
right = ["context", "limit_5h"]          # pushed against the right edge
gap   = 2                                 # least space between the two groups
```

Declaring any `[[line]]` replaces the preset's lines. `[segment.*]` tables
from the preset still apply, with yours merged over them.

## Segments

`[segment.<name>]` tunes a segment placed on a line. With `type`, the table is
a new instance of that segment, so one type can be placed several times:

```toml
[segment.dir]
mode = "base"            # a segment option (statusline.py segments dir)

[segment.label]
type = "text"            # an instance of the text segment
text = "prod"
color = "red"
```

Every segment takes:

| key | meaning |
|-----|---------|
| `format` | the body template (below) |
| `priority` | higher survives longer when the line is too narrow |
| `icon` | its icon; `""` hides it. Default: from the icon set |
| `color` | the theme role (or `#hex`) its icon and chip wear |

## Templates

| construct | meaning |
|-----------|---------|
| `{field}` | a value the segment supplies; `{field:>4}` pads it to 4 cells (`<` left, `^` centre) |
| `[ ... ]` | shown only when every field inside has a value; an empty group also takes one neighbouring space |
| `<role> ... </role>` | a colour: a theme role (accent, text, subtext, muted, subtle, blue, cyan, teal, green, yellow, orange, red, pink, purple, gold), an alias (model, dir, dim, gray, ok, warn, alert, crit, info), a colour the segment computes, `#rrggbb`, or `on_<role>` for a background. `</>` closes the innermost |
| `<bold> <italic> <underline> <strike> <faint>` | attributes (`<b> <i> <u> <s>` too) |
| `<link> ... </link>` | an OSC-8 link to the segment's `url` |
| `\` | escapes `{ } [ ] < >` and itself |

`{icon}` (or v2's `{glyph}`) in a format places the icon yourself; the style
then does not add it.

## Sections

```toml
[bar]
style = "smooth"      # smooth, shade, line, slim, dots, pips, braille, ascii
width = 13            # 13 cells show all 101 percentages distinctly
fill = "level"        # level, gradient, tone, a role or #hex, or "cyan,purple" blended
track = "subtle"      # the empty part's colour
pulse = false         # flash past the red threshold
min_sliver = true
cap_left = ""         # e.g. "▕" and "▏"
cap_right = ""

[thresholds]          # where bars turn yellow, orange, red
yellow = 50
orange = 75
red = 90

[layout]
right_margin = 5      # columns the host keeps at the right edge (statusline.py ruler)
gap = 2
fallback_columns = 200
wide_glyphs = []      # glyphs your font draws two cells wide
separator = ""        # for the classic and dots styles

[quest]
enabled = false
placement = "line"    # line, inline, manual, game (the whole bar becomes the game)
avatar = "auto"       # the kitty picture of the pet: auto, on, off
avatar_cols = 8
event_seconds = 30.0
game_rows = 3         # game mode: rows of scene under the quest ticker
game_hud = ["context", "limit_5h", "limit_7d"]   # one gauge beside each row; any segment works
game_hud_width = "auto"   # "auto" (the gauges' width, more on wide terminals) or 0 to 60
game_details = "auto"     # session details on the ticker's row: "auto" or a list of segments

[activity]
enabled = false       # `statusline.py activity enable` registers the hooks and sets this
placement = "auto"    # auto: turn, tools, agents, tasks, mode get a line of their own; manual

[git]
enabled = true
cache_ttl = 2.0       # the background refresh's period

[colors]              # override any role or alias
accent = "#ff8800"

[glyphs]              # override marks: ahead, behind, stash, pace, reset, fast, age, heart…
ahead = "⇡"
```

## Fitting

Each line is measured against the usable width (`COLUMNS - right_margin`).
When it overflows, every segment on it steps down a detail level together:
`less` (tertiary detail: reset clock, stash), `lean` (secondary: pace, token
counts, titles), `narrow` (half-width bars, short names), `text` (no bars).
Only when even that overflows does the lowest-priority segment drop, and the
line is tried again from the richest level. `preview` shows what happened at
each width.

In game mode the ticker's row is fitted in two passes. The quest segments are
fitted alone, exactly as above, and the news then takes any columns left
over (its `max` applies only when the row is short). The session details get
what remains, right-aligned against the streak and gold. They give way one
at a time, lowest priority first: each steps down its levels, then to
`glance` (its icon alone, when the icon's colour carries its state: git, the
PR, the cache, vim, the gauges), then drops, before the next one gives up
anything. They never clip and never change the quest segments.
