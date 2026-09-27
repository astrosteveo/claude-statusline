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
| `spend` | what today cost across every session, the month so far, and an optional daily budget as a bar |
| `cache` | the prompt cache: while it is costing you (with the likely cause of the last miss), and counting down the last minutes before a warm cache goes cold |
| `env`, `host`, `session`, `agent`, `vim`, `output_style`, `version`, `clock` | the rest of what the host knows |
| `text` | your own label; place several with `type = "text"` |
| `command` | the first line of your own command's output, run in the background (below) |
| `turn`, `tools`, `agents`, `tasks`, `mode` | live activity: what Claude is doing now (below) |
| `heartbeat` | a tick that moves while the bar refreshes (off unless placed: a debugging aid) |
| `quest`, `quest_boss`, `quest_raid`, `quest_dungeon`, `quest_daily`, `quest_buffs`, `quest_event`, `quest_streak`, `quest_gold`, `quest_pet` | Claude Quest |

`statusline.py segments <name>` lists a segment's options, fields and colours;
[catalog.md](skills/design/reference/catalog.md) has all of them, and
[schema.md](skills/design/reference/schema.md) the format language
(`{field}`, `[optional]`, `<colour>`, `<bold>`, `<link>`).

**How a line fits.** When a line is too wide, every segment on it gives up
detail together (the reset clock, then the pace and token counts, then bars
at half width, then no bars) and only then does the lowest-priority segment
drop. Give what you care about a higher `priority`.

## Your own commands

```toml
[[line]]
left = ["model", "dir", "git", "oncall"]

[segment.oncall]
type = "command"
command = "oncall-now --short"     # anything that prints a line; colours are kept
every = 60                          # seconds between runs
timeout = 2                         # killed after this long
```

A command segment shows the first line its command printed. The bar never
runs the command itself or waits for it: a detached runner does, at most
every `every` seconds (at least 2) and for at most `timeout` seconds (at most
10), and the bar reads its last output from a cache. The command runs with
`/bin/sh` in the session's directory, with `STATUSLINE_CWD`,
`STATUSLINE_PROJECT_DIR`, `STATUSLINE_MODEL` and `STATUSLINE_SESSION_ID` set;
`per = "global"` shares one output across directories. `[commands] enabled =
false` (or `CLAUDE_STATUSLINE_NO_COMMANDS=1`) turns them all off, and
`doctor` shows each one's last run.

## Spend today

The `spend` segment adds up what every session cost today, as this bar saw
it, in your local day: `today $61.20 · month $489`. Set `budget` for a daily
limit drawn as a bar that turns yellow, orange and red as it fills, and
`week = true` for the last seven days. The ledger lives in
`~/.local/state/claude-statusline/spend.bin`; it counts only sessions this
status line drew (not `claude -p`, not other machines). The `dashboard`
preset shows it; elsewhere add it on the configurator's Layout page.

## Live activity

```sh
statusline.py activity enable      # background hooks; the segments get a line of their own
statusline.py activity disable
```

The bar shows what Claude is doing right now:

| segment | shows |
|---------|-------|
| `turn` | `working 2m14s` while Claude answers, `waiting 4m` once it has, `compacting`, or why a turn stopped |
| `tools` | the tool running (the longest-running, if several), what it works on and for how long, then this turn's finished ones: `Bash pytest -q 18s ✓ Edit ×2 · ✓ Read ×2` |
| `agents` | the subagents at work: kind, task and time |
| `tasks` | the task list, where the model keeps one: the task in hand and how many are done |
| `mode` | the permission mode when it is not the default: plan, accept edits, auto, don't ask, bypass |

The hooks run in the background (`async`), so no tool call waits for them,
and each event updates a small file per session that a refresh reads once.
Nothing reads the transcript. The segments get a line of their own under
yours (in game mode they join the top row's details) unless you place any of
them yourself; `[activity] placement = "manual"` turns that off.

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
pet that evolves at levels 5, 15, 30 and 50. At 30 it takes the form of the
school you use most (ember, forge, lore, arcane or storm), with a bonus
to match; a wyrm doubles it.

A pull request opened with `gh pr create` is a dungeon: every push is a room,
failing `gh pr checks` spring traps, and `gh pr merge` clears it, paying more
the deeper it went. Each week your first commit in a project summons a
tech-debt raid boss with one HP per TODO, FIXME, XXX or HACK; commits that
remove them strike it.

On the bar: your level, title and XP; today's quests; the boss's hearts; this
project's raid boss and dungeon; live buffs; news of the latest loot or
level-up; your streak and gold; and the pet.
In kitty the pet is an animated picture at the right edge, wearing your gear,
running while tools fire, fighting bosses, celebrating loot and dozing when
you step away; elsewhere it is a little text sprite.

### Game mode

```toml
[quest]
enabled = true
placement = "game"
```

The whole bar becomes the game. Below the top line a scene spans the width:
your pet wanders, runs while tools fire, charges the boss or the tech-debt
kraken, throws confetti at loot, waits for you after a reply and sleeps when
you step away, with a castle on the hill while a PR dungeon is open. In kitty
it is an animated picture (drawn once per situation and looped by kitty
itself, so it moves smoothly between refreshes); elsewhere it is a little
text world. `game_rows` sets the height.

The top line is the quest ticker, with your session details beside it: the
model first, then the segments of your own lines (or your preset's), less
what the gauges show. The ticker is fitted first and never changes for
them, and the news takes any room left before they do. The details give way
one at a time, lowest priority first: less detail, then just the icon, then
gone. `game_details` sets the list yourself (`[]` for none); the
configurator's Layout page edits it.

Beside each row of scene sits one gauge from `game_hud` (context, 5h and 7d
by default; any segment works). On a wide terminal the gauges also show a
bar, the pace and the reset time.

Play with `/quest` inside Claude Code or `claude-quest` in a terminal: `sheet`,
`bag`, `equip`, `use`, `sell`, `forge`, `shop`, `buy`, `quests`, `boss`, `dungeons`, `raid`, `pet`,
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
