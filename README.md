# claude-statusline

A fast, good-looking status line for [Claude Code](https://claude.com/claude-code),
with an interactive configurator and **Claude Quest**, an RPG that plays itself
while you work.

![themes and styles](docs/gallery.png)

- **Looks**: 19 themes, 8 styles (from plain text to powerline and rounded
  capsules), Nerd Font, Unicode or emoji icons, 8 bar styles with sub-cell
  precision and gradient fills. Truecolor, 256 or 16 colours.
- **Configure it live**: `statusline.py configure` opens a full-screen editor
  with a live preview of your bar; every change shows before you save it.
- **Always fits**: every line is measured exactly the way Claude Code measures
  it, gives up detail gracefully when the terminal is narrow, and never clips.
- **Fast**: about 10 ms a refresh, 4 of them Python starting up. Git runs in
  the background, so the bar never waits for it.
- **Claude Quest**: XP for every tool Claude uses, loot as replies land,
  bosses summoned by failing tests, daily quests, a shop, and a pet that
  lives in the corner of your bar. One switch turns it on or off.

Pure Python 3.11+, standard library only (the kitty pet picture uses pycairo).

## Install

```sh
git clone https://github.com/astrosteveo/claude-statusline ~/Projects/claude-statusline
cd ~/Projects/claude-statusline
./install.sh            # add --quest to switch Claude Quest on too
```

That writes a small shim to `~/.claude/statusline.py`, creates
`~/.config/claude-statusline/config.toml` with a look your terminal can draw,
and points `statusLine` in `~/.claude/settings.json` at it, backing up
anything it replaces. The bar appears on Claude Code's next refresh.
`./install.sh --uninstall` puts your previous status line back.

As a plugin, the `design` skill lets Claude restyle the bar for you:

```
/plugin marketplace add astrosteveo/claude-statusline
/plugin install claude-statusline@claude-statusline
/claude-statusline:design one line, powerline, catppuccin
```

## Make it yours

```sh
python3 ~/.claude/statusline.py configure      # or `claude-statusline configure`, or no arguments in a terminal
```

The configurator shows your bar at the top, drawn with a sample (or the last
real payload it received), and changes it as you move:

| page | what you change |
|------|-----------------|
| Look | theme, style and icons; the configurator itself wears the theme you are on |
| Layout | presets, and every line: add, remove, reorder segments, move them between lines and sides |
| Segments | each segment's options, format, icon, colour and priority |
| Bars | bar style, width, fill and track, with sample bars |
| Quest | Claude Quest on or off, where its line goes, the pet picture |
| More | colour depth, margins, thresholds, git, the heartbeat tick, clock, directory style |

`s` saves (with a backup of your old file); the bar picks it up within a
second. From a shell, or for scripts:

```sh
statusline.py set theme catppuccin
statusline.py set style powerline
statusline.py set segment.dir.mode base
statusline.py themes          # every theme drawn with your own layout (also: styles, icons, bars)
statusline.py preview --width 80,120,160
```

## The config

`~/.config/claude-statusline/config.toml`. Every key is optional:

```toml
theme = "midnight"      # colours
style = "capsules"      # minimal, classic, dots, chips, capsules, pills, powerline, slant
icons = "nerd"          # nerd, unicode, emoji, none
preset = "classic"      # classic, compact, dashboard, focus, minimal

[[line]]                # your own lines replace the preset's
left = ["model", "dir", "git", "pr", "cost"]

[[line]]
left = ["context"]
right = ["limit_5h", "limit_7d"]

[segment.dir]
mode = "base"

[bar]
style = "slim"
fill = "gradient"
```

**Styles.** `minimal`, `classic` and `dots` are coloured text. `chips` sets
each segment on a soft surface with a coloured icon block and works in any
font; `capsules` is the same with rounded ends, `pills` makes each segment a
rounded pill of its own colour, and `powerline` and `slant` join coloured
segments with arrows or slants. Those four need a Nerd Font, or a terminal
that bundles the symbols: kitty, WezTerm and Ghostty do, so `auto` picks
capsules there and chips elsewhere.

**Themes.** claude, claude-light, midnight, catppuccin, catppuccin-latte,
tokyo-night, nord, dracula, gruvbox, rose-pine, kanagawa, everforest,
one-dark, solarized-dark, solarized-light, synthwave, mono, `terminal` (your
terminal's own 16 colours) and `classic` (the 2.x palette). Override any
colour in `[colors]`.

**Segments.**

| segment | shows |
|---------|-------|
| `model` | model, effort, fast mode |
| `dir` | working directory, abbreviated (fish, compact, full, base or project-relative) |
| `git` | branch, ahead/behind, staged/modified/untracked, conflicts, stashes, rebase/merge state, a nudge when a dirty tree goes stale |
| `pr`, `worktree` | the pull request and its review state; the worktree |
| `context` | context window: bar, percentage, tokens |
| `limit_5h`, `limit_7d`, `limit_7d_model`, `limit_spend` | rate-limit windows with a pace projection (`→94%`: where you will be at the reset) and the reset countdown |
| `cost`, `duration`, `diff`, `burn`, `tokens` | spend, wall time, lines changed, $/hour, tokens in and out |
| `cache` | the prompt cache, only while it is costing you |
| `env`, `host`, `session`, `agent`, `vim`, `output_style`, `version`, `clock` | the rest of what the host knows |
| `text` | your own label; place several with `type = "text"` |
| `heartbeat` | a tick that moves while the bar refreshes (off unless placed: a debugging aid) |
| `quest`, `quest_boss`, `quest_daily`, `quest_buffs`, `quest_event`, `quest_streak`, `quest_gold`, `quest_pet` | Claude Quest |

`statusline.py segments <name>` lists a segment's options, fields and colours;
[catalog.md](skills/design/reference/catalog.md) has all of them, and
[schema.md](skills/design/reference/schema.md) the format language
(`{field}`, `[optional]`, `<colour>`, `<bold>`, `<link>`).

**How a line fits.** When a line is too wide, every segment on it gives up
detail together (the reset clock, then the pace and token counts, then bars
at half width, then no bars) and only then does the lowest-priority segment
drop. Give what you care about a higher `priority`.

## Claude Quest

```sh
statusline.py quest enable      # hooks, the /quest command, the quest line
statusline.py quest disable     # all of it off again; your save is kept
```

Every tool Claude uses earns XP (your class is the school of tools you use
most), commits and pushes pay gold, loot drops as replies land, and a failing
test, build or lint run summons a boss with one HP per failure; fix it to win.
Three daily quests and a weekly one, a shop that restocks every day, a forge,
gear in five slots with set bonuses and titles, streaks, achievements, and a
pet that evolves at levels 5, 15, 30 and 50.

On the bar: your level, title and XP; today's quests; the boss's hearts; live
buffs; news of the latest loot or level-up; your streak and gold; and the pet.
In kitty the pet is an animated picture at the right edge, wearing your gear,
running while tools fire, fighting bosses, celebrating loot and dozing when
you step away; elsewhere it is a little text sprite.

Play with `/quest` inside Claude Code or `claude-quest` in a terminal: `sheet`,
`bag`, `equip`, `use`, `sell`, `forge`, `shop`, `buy`, `quests`, `boss`, `pet`,
`titles`, `achievements`, `log`, `guide`.

## Performance

The bar runs once a second in every session, so it is built to be cheap:

- the payload is parsed with the C JSON scanner directly (importing `json`
  and `re` would cost more than drawing the whole bar);
- the config is compiled once and cached; a refresh is a stat and a read;
- segment modules load only when placed;
- git runs in a detached background process that refreshes a cache, so a
  slow repository slows nothing; the branch comes straight from `HEAD`.

`statusline.py bench` measures it on your machine.

## Troubleshooting

```sh
statusline.py doctor      # what is installed, detected and in force
statusline.py validate    # every problem in the config, with suggestions
statusline.py preview     # the bar at several widths, with notes on what gave way
```

**Boxes instead of icons.** Your font lacks Nerd Font symbols:
`statusline.py set icons unicode` and `set style chips`.

**A line ends in `…` or the right side stops short.** Claude Code keeps a few
columns at the right edge. Run `statusline.py ruler` as the status line
command, read the last digit visible on the second row, and add it to
`layout.right_margin`. A glyph your font draws double-width does the same;
list it in `layout.wide_glyphs`.

**It only shows the model and directory.** That is the fallback: something
raised. `CLAUDE_STATUSLINE_DEBUG=1 statusline.py render --sample busy` prints
the traceback.

**Upgrading from 2.x.** 2.x configs still render. `statusline.py migrate --write`
tidies one (hand-placed avatar rows become automatic placement, bar glyph
overrides become bar styles) and keeps a backup. The new default look is
`auto`; `set style classic` and `set theme classic` bring back the 2.x look.

## Development

```sh
make test       # unit tests and installer tests
make catalog    # regenerate the skill's segment catalog
make gallery    # redraw docs/gallery.png (needs pycairo)
```

The suite renders every preset in every style, icon set and theme against
sample, empty and deliberately malformed payloads at many widths and checks
that no line ever exceeds its budget, drives the configurator both headless
and in a real pty, and runs the installer against throwaway home directories.

## License

MIT
