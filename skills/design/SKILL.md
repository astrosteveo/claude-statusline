---
name: design
description: Design, change, preview and install a Claude Code status line with the claude-statusline engine. Use when the user wants a new status line, wants to change what their status line shows (segments, lines, order, colours, bars, formats), asks why their status line is clipped or truncated, or wants to migrate an old claude-statusline config.
argument-hint: [what you want the bar to show]
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/statusline.py *) Bash(${CLAUDE_PLUGIN_ROOT}/install.sh *) Bash(tput cols) Read Write Edit
---

# Designing a status line

You are driving the claude-statusline engine. It renders a bar from a TOML
layout: lines of named segments, each with a format string, a priority and
options. You never write rendering code; you write the layout and let the
engine prove it fits. Everything the engine knows is one command away:

```
ENGINE="python3 ${CLAUDE_PLUGIN_ROOT}/statusline.py"
$ENGINE doctor                      # config path, preset, lines, problems, usable width
$ENGINE segments [name] [--json]    # the catalog: options, fields, colours
$ENGINE presets                     # classic, minimal, dashboard
$ENGINE bars [--width N]            # every bar style and fill, side by side
$ENGINE validate <config>           # errors with did-you-mean; exit 1 on errors
$ENGINE preview --config <config> --width 80,120,<cols> --plain
$ENGINE migrate <config> [--write]  # fold a pre-2.0 [features] table into segment options
$ENGINE ruler                       # calibrate layout.right_margin
```

Read `reference/schema.md` before writing a layout, and `reference/constraints.md`
before promising anything about what the bar can do. `reference/catalog.md` is
the segment list; `reference/examples.md` has whole layouts to start from.

## The loop

1. **Find the ground.** Run `doctor`. Note the config path (default
   `~/.config/claude-statusline/config.toml`), the preset in force, and any
   problems. If it lists `features.*` warnings, the config predates the engine:
   offer `migrate --write` first, and show the user the diff it prints.
   If the status line is not installed at all (`doctor` will not even run
   from Claude Code's settings), run `${CLAUDE_PLUGIN_ROOT}/install.sh`; it
   backs up whatever it replaces and tells the user what it did.

2. **Learn the terminal width.** `tput cols` gives the width of the terminal
   Claude Code is running in. Always preview at that width, and at something
   narrower (say 100 and 80) so the user sees how the bar degrades.

3. **Get the intent, not a spec.** Ask at most one question if the request is
   vague, and lead with a recommendation: which preset is the closest start,
   which segments they seem to care about, one or two lines. People rarely
   know the catalog; you do. Offer what is possible ("the five-hour bar can
   carry a projection of where it will land") rather than asking them to
   enumerate.

4. **Write the layout.** Start from a preset when one is close (`preset =
   "dashboard"` plus a few `[segment.*]` tweaks beats a hand-written `[[line]]`
   list). Declare `[[line]]` tables only when the arrangement itself is new.
   Keep the file small: every key is optional and merges over the defaults.
   Write it to the config path; keep a copy of the previous file if you are
   changing one that exists (`cp config.toml config.toml.bak`).

5. **Validate, then preview.** `validate` must exit 0 with no warnings; fix
   every message it prints. Then `preview --config <path> --width 80,100,<cols>
   --plain` and read the `↳` notes: `level less/lean/narrow/text` means the
   line degraded at that width, `dropped x, y` means segments went, `OVERFLOWS`
   means the highest-priority segment alone does not fit. At the user's real
   width the goal is level `full` with nothing dropped. Show the user the plain
   preview at their width; it is what they will see.

6. **Tune priorities before cutting content.** If something they care about
   drops at their width, raise its `priority` rather than removing other
   segments; the engine drops lowest priority first and steps bars down before
   dropping anything.

7. **Finish.** The engine reads its config on every refresh, so the change is
   live the moment the file is written; no restart. Tell the user what they
   are looking at, and how to change one thing later (`[segment.x] option =`).

## What the user can ask for, and how it maps

| They say | You do |
|----------|--------|
| "one line" / "less noise" | `preset = "minimal"`, or a single `[[line]]` with 4–6 segments |
| "put X on the right" | move it into the line's `right` list; the engine anchors it to the edge |
| "I want to see cost/time/lines separately" | `cost` is the trio; `duration` and `diff` are the separate pieces |
| "bars look wrong / clipped at the edge" | `layout.right_margin` needs calibrating; walk them through `ruler` (constraints.md) |
| "different colour for X" | a `<colour>` tag in that segment's `format`; add new names under `[colors]` |
| "a label / a divider / my name" | `text` segments, one `[segment.<name>] type = "text"` per instance |
| "no percentage, just the bar" | `format` without `{pct}`; keep `{bar}` |
| "prettier bars" / "a different bar look" | `[bar] style =` one of block, shade, thin, dots, pips, ascii; show them with `bars` |
| "rainbow bar" / "colour the bar by usage" | `[bar] fill = "gradient"`; a fixed colour is `fill = "cyan"`, a spread is `"cyan,purple"` |
| "brackets around the bar" | `[bar] cap_left = "▕"` and `cap_right = "▏"` (or `[` `]`); caps sit outside `width` |
| "make it obvious when I'm nearly out" | `[bar] pulse = true`; the fill emboldens every other second past the red threshold |
| "one bar different from the others" | `style` and `fill` on that segment: `[segment.context] style = "thin"` |
| "a different spinner" | `[segment.heartbeat] frames = "arc"` (dots, orbit, quadrants, arc, wave, pulse, bounce, line) or a string of glyphs |
| "hide when idle / only show when dirty" | not expressible yet: segments hide only when they have nothing to show |
| "run my own script in the bar" | not supported, by design (constraints.md explains the refresh budget) |

## Rules

- Never hand-edit `~/.claude/settings.json` for the status line; `install.sh`
  does that and backs it up.
- Never claim a layout fits without a `preview` at the user's width.
- Colours are SGR parameters, not names: `"38;5;141"` or `"38;2;R;G;B"`.
  Templates then use the *key* from `[colors]`.
- Glyphs must be single-cell. If the user picks an emoji or a glyph their font
  draws wide, the right edge will clip; add it to `layout.wide_glyphs`.
- Keep the whole bar to three lines or fewer; each line is a row taken from
  the conversation.
