---
name: design
description: Design, restyle, preview and install a Claude Code status line with the claude-statusline engine, and switch Claude Quest on or off. Use when the user wants a new status line, a different look (theme, style, icons, bars), different contents (segments, lines, order, formats), asks why the bar is clipped, or wants Claude Quest.
argument-hint: [what you want the bar to show or look like]
allowed-tools: Bash(python3 -S ${CLAUDE_PLUGIN_ROOT}/statusline.py *) Bash(python3 ${CLAUDE_PLUGIN_ROOT}/statusline.py *) Bash(${CLAUDE_PLUGIN_ROOT}/install.sh *) Read Write Edit
---

# Designing a status line

You drive the claude-statusline engine. It draws the bar from a small TOML
config: a theme (colours), a style (how segments are dressed), an icon set,
and lines of named segments. You never write rendering code: you change the
config and let the engine prove the result fits. Everything is one command away:

```
SL="python3 -S ${CLAUDE_PLUGIN_ROOT}/statusline.py"
$SL doctor                          # what is installed and in force; problems
$SL preview --width 80,120,<cols> --plain       # the bar at several widths, with notes
$SL themes --plain | styles --plain | icons | bars   # every choice, drawn with the user's layout
$SL segments [name]                 # the catalog: options, fields, colours
$SL presets                         # ready-made layouts
$SL set <key> <value>               # one change, validated; comments in the file survive
$SL get <key> | unset <key>
$SL validate                        # every problem, with did-you-mean; exit 1 on errors
$SL activity enable | disable       # live activity (background hooks) on or off
$SL quest enable | disable | status # Claude Quest on or off
$SL migrate --write                 # tidy a config from an earlier version
```

Read `reference/schema.md` before writing config by hand and
`reference/constraints.md` before promising anything. `reference/catalog.md`
is the segment list; `reference/examples.md` has whole configs to start from.

## The loop

1. **Find the ground.** Run `doctor`. If `statusLine` is not set, run
   `${CLAUDE_PLUGIN_ROOT}/install.sh` (it backs up whatever it replaces).
   Note the config path and any problems.
2. **Learn the width.** The payload's terminal is not yours; ask the user for
   their terminal width if it matters, or preview at 80, 120 and 160.
3. **Get the intent, not a spec.** Offer what is possible rather than asking
   them to enumerate: "a one-line bar with the meters on the right", "the
   powerline look in Catppuccin". Lead with a recommendation.
4. **Change it with `set`.** One key at a time: `set theme catppuccin`,
   `set style powerline`, `set segment.dir.mode base`. `set` refuses changes
   that add errors. Write `[[line]]` tables by hand (Edit the config file)
   only when the arrangement itself changes; prefer a preset when one is close.
5. **Preview.** `preview --width 80,120,<cols> --plain` and read the `↳`
   notes: `level less/lean/narrow/text` means a line degraded at that width,
   `dropped x` means a segment went. At the user's width aim for no drops of
   things they care about; raise a segment's `priority` rather than cutting
   others. Show them the plain preview.
6. **Finish.** The bar reads its config on every refresh: the change is live
   within a second. Tell them about `statusline.py configure`, the interactive
   configurator with a live preview, for fine-tuning themselves.

## What people ask for

| They say | You do |
|----------|--------|
| "make it prettier" / "a different look" | show `styles` and `themes`; `set style capsules`, `set theme …` |
| "I don't have Nerd Fonts" / boxes instead of icons | `set icons unicode` and `set style chips` (or minimal/classic) |
| "match my terminal theme" | pick the matching theme; `terminal` uses the terminal's own 16 colours |
| "one line" / "less noise" | `set preset minimal` or `compact`; or a single `[[line]]` |
| "put X on the right" | move it to that line's `right` list |
| "hide X" | take it off the line (`preset` lines: copy them into `[[line]]` first) |
| "just the bar, no percentage" | `set segment.context.format "{bar}"` |
| "a rainbow / gradient bar" | `set bar.fill gradient`; blends: `set bar.fill "cyan,purple"` |
| "a slimmer bar" | `set bar.style slim` (or line, dots, braille, pips) |
| "my own label" | a `[segment.<name>]` table with `type = "text"` and `text = "…"`, placed on a line |
| "what did today cost" / "a daily budget" | place `spend`; `set segment.spend.budget 50` |
| "show what Claude is doing" / "running tools" / "subagents" | `activity enable`; `turn`, `tools`, `agents`, `tasks`, `mode` get a line of their own |
| "the RPG" / "Claude Quest" | `quest enable`; its line appears at the bottom; `/quest` plays |
| "no pet picture" | `set quest.avatar off` (the text pet shows instead) |
| "run my own script in the bar" | not supported by design (constraints.md: the refresh budget) |

## Rules

- Never hand-edit `~/.claude/settings.json`; `install.sh` and `quest enable`
  do that, with backups.
- Never claim a layout fits without a `preview`.
- Colours in `[colors]` are theme roles overridden with `#rrggbb` (or an
  xterm index). Templates name roles: `<accent>`, `<muted>`, `<green>`.
- Glyphs must be one cell (emoji are two and are counted correctly). If a
  font draws a glyph wider than Unicode says, add it to `layout.wide_glyphs`.
- Keep the bar to three or four lines: each is a row taken from the conversation.
