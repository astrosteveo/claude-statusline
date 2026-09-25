# claude-statusline 3

## Problem

Version 2 made the bar composable: lines of named segments, a closed catalog,
one fit algorithm, a design skill. Three things held it back. Its look was
fixed (one palette of 256-colour codes, `│` separators, a handful of glyphs),
so "make it prettier" meant hand-editing SGR codes. Configuring it meant
editing TOML blind and running `preview`. And Claude Quest, the RPG grown
around the bar, lived in a separate, unversioned project wired in by hand,
with its segments half-added to this repo.

## What 3 is

A rewrite of the engine around styled text, with the same guarantees (never
blank, never too wide, never slow) and:

- **Looks as data.** Themes are palettes of roles (text, subtext, muted,
  subtle, surface, accent, hues). Segments name roles, never codes, so a
  theme recolours everything. Styles dress segments: plain text looks,
  soft chips, capsules, pills, powerline, slant. Icon sets: Nerd Font,
  Unicode (only glyphs JetBrains Mono and DejaVu both carry), emoji, none.
- **Styled text, serialised last.** Segments render to runs of
  (text, style); widths are measured on the text alone and ANSI is produced
  once, at the end. That is what makes backgrounds under whole segments,
  per-look recolouring, and exact widths possible.
- **An interactive configurator** with a live preview, drawn directly on the
  terminal (raw mode, synchronized updates), wearing the theme you browse.
- **Claude Quest inside**: the game, its hooks, its CLI and its art in
  `claude_statusline/quest`, switched on and off by `[quest] enabled` (the
  hooks check it) and `statusline.py quest enable|disable` (which manages the
  hooks, `/quest` and `claude-quest`). Saves from every earlier version load.
- **Faster**: ~10 ms a refresh against v2's ~21 ms.

## Key decisions

- **Measure like the host.** Widths follow `string-width` (Claude Code's
  measure): East Asian wide and emoji-presentation characters are two cells,
  VS16 promotes text-style emoji, ZWJ sequences and skin tones join.
- **Nothing on the hot path that is not drawing.** No `json`/`re`/`tomllib`/
  `subprocess` imports on a refresh: the payload goes through `_json`'s
  scanner, the config through a marshal cache keyed on file and source
  mtimes, git through a stale-while-revalidate cache refreshed by a detached
  process. Segment modules load only when placed.
- **Bars on chips take the chip's hue** (a deep fill on a track a shade darker
  than the chip) instead of their usual colours, so they read inside any tone.
  Runs a look must not recolour carry a KEEP flag.
- **Previews never have side effects.** A `live` render may start git
  refreshes and kitty uploads; previews, the configurator and tests never do.
- **The quest line is automatic.** Enabling Quest appends its line (or the
  hero badge, inline) unless quest segments are already placed. The kitty
  pet is pinned to the right edge of the first lines, replacing v2's
  hand-placed avatar rows.
- **Compatibility over purity.** v2 configs render unchanged: SGR colour
  strings parse, `{glyph}` is the icon, v2 colour names are theme aliases.
  `migrate` tidies them rather than being required.

## Rejected

- A compiled client talking to a daemon: ~2 ms instead of ~10 ms, at the cost
  of a build step and a process to babysit. Not worth it at once a second.
- curses for the configurator: its colour model cannot show truecolor
  previews faithfully.
- Plugin hooks for Quest: they would fire for everyone who installs the
  plugin, and double up with settings.json hooks for install.sh users.
- User-authored segments: unchanged from v2, the refresh budget forbids them.
