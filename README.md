# claude-statusline

A status line engine for [Claude Code](https://claude.com/claude-code). You
describe the bar as lines of named segments in a small TOML file; the engine
renders it, keeps it inside the terminal at every width, and never blanks.
It ships as a plugin with a skill, so you can also just tell Claude what you
want to see and let it write the layout for you.

```
◆ Opus 5 (1M context) · high │ ▸ …/u/Projects/widget-factory │ $24.73 59m +1006/-21 │ refactor the parser                                                               ⠋
ctx ███▓░░░░░░░░░ 28% (279k/1.0M)                                                                5h ████████░░░░░ 62% ⇢94% ↻1h43m·22:29 │ 7d ███░░░░░░░░░░ 24% ⇢58% ↻4d3h
```

(Shown with the textured `░` track so the fill reads in plain text; the default solid track carries it in colour.)

Pure Python 3.11+, stdlib only, no network calls, about 18 ms per refresh.

## Install

```sh
git clone https://github.com/astrosteveo/claude-statusline ~/Projects/claude-statusline
cd ~/Projects/claude-statusline
./install.sh
```

That writes a small shim into `~/.claude/`, seeds a config at
`~/.config/claude-statusline/config.toml`, and patches `statusLine` into
`~/.claude/settings.json`, backing up anything it replaces. Start a new
session or run `/statusline` to see it. `./install.sh --uninstall` puts your
previous status line back.

### As a plugin

```
/plugin marketplace add astrosteveo/claude-statusline
/plugin install claude-statusline@claude-statusline
```

Then ask for a bar:

```
/claude-statusline:design one line, bars on the right, muted colours
```

The skill runs `install.sh` for you if the status line is not wired up yet,
writes the config, validates it, previews it at your terminal's width and at
narrower ones, and shows you what you will see before you see it. It knows
the host's constraints (see
[constraints.md](skills/design/reference/constraints.md)) so it will tell you
when something is not possible rather than produce a bar that clips.

### Manual install

Point `~/.claude/settings.json` at the script yourself:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/.claude/statusline.py",
    "padding": 0,
    "refreshInterval": 1
  }
}
```

`padding: 0` matters; the layout does its own right-edge accounting.

## Upgrading from 1.x

The `[features]` table is no longer read. Everything it switched is now an
option on the segment it belongs to, or a matter of which segments you place.
The old file still renders (as the classic layout) and `doctor` lists each
legacy key with its replacement. To rewrite it:

```sh
python3 ~/.claude/statusline.py migrate ~/.config/claude-statusline/config.toml --write
```

It backs the file up and prints every mapping it applied.

## The layout

Everything lives in `~/.config/claude-statusline/config.toml` (or
`~/.claude/statusline.toml`, or wherever `$CLAUDE_STATUSLINE_CONFIG` points).
Every key is optional and merges over the defaults, so this is a complete
config:

```toml
preset = "dashboard"

[segment.heartbeat]
frames = "◐◓◑◒"
```

A **preset** supplies the lines: `classic` (two lines, the default),
`minimal` (one line) or `dashboard` (three lines, bars on the left).
`statusline.py presets` shows them. Declare your own with `[[line]]` tables,
each with a `left` group that flows from the left edge and a `right` group
pushed against the right edge:

```toml
[[line]]
left = ["model", "dir", "git", "pr"]
right = ["session", "heartbeat"]
gap = 1                       # minimum columns between the groups

[[line]]
left = ["context", "limit_5h", "limit_7d"]
```

A **segment** is tuned with a `[segment.<name>]` table. Every segment takes
`format` and `priority`; the rest are listed by `statusline.py segments
<name>`. A table with `type` names an instance, so the same segment can appear
twice:

```toml
[segment.dir]
depth = 2

[segment.greeting]
type = "text"
text = "hello"
format = "<gold>{text}</gold>"
```

Full schema: [schema.md](skills/design/reference/schema.md). Whole layouts to
copy: [examples.md](skills/design/reference/examples.md).

### Segments

| segment | shows |
|---------|-------|
| `model` | model name, effort level, `⚡` in fast mode |
| `dir` | working directory, compacted |
| `git` | branch, `↑↓` ahead/behind, `∅` no upstream, `+staged ~dirty ?untracked !conflicts ⚑stashes`, `⏱` since the last commit once a dirty tree goes stale |
| `pr` | pull or merge request number, review state, checks |
| `worktree` | worktree name and branch |
| `context` | context-window bar, percentage, tokens |
| `limit_5h`, `limit_7d`, `limit_7d_model`, `limit_spend` | rate-limit bars with burn-rate projection (`⇢103%` means "at this pace you will exhaust the window") and reset countdown |
| `cost`, `duration`, `diff` | dollars, wall time, lines changed, together or apart |
| `cache` | prompt-cache warning, only when it is costing money |
| `env`, `host` | virtualenv, hostname over SSH or in a container |
| `session`, `output_style`, `version`, `agent`, `vim` | what the host says about the session |
| `text`, `clock` | a label; the time |
| `heartbeat` | a tick that proves the bar is still refreshing |

The complete list, with every option, field and colour, is
[catalog.md](skills/design/reference/catalog.md), generated from the code.

### Templates

A segment's `format` is text with `{field}` placeholders, `[optional groups]`
that vanish when a field inside is empty, `<colour>…</colour>` spans naming a
key of `[colors]`, and `<link>…</link>` for an OSC-8 hyperlink:

```toml
[segment.model]
format = "<model>{name}</model><dim>[ · {effort}]</dim>"

[segment.limit_5h]
format = "<gray>5h</gray> {bar}[ <dim>{reset}</dim>]"    # bar and countdown, no percentage
```

### How a line fits

The engine measures every line against the usable width. When a line is too
wide, every segment on it steps down one detail level together: the reset
clock goes, then the pace projection, then bars shrink to half width, then
bars disappear. Only when the leanest rendering still overflows does the
lowest-priority segment drop, after which the richest level that fits is
chosen again. Bars on one line therefore always share a width, and the thing
you care about survives if you give it a higher `priority`.

`statusline.py preview --width 80,120,160` shows the layout at each width
and annotates every line with its level and anything dropped.

### The heartbeat

Each refresh is a separate process with no memory of the previous one, so
the tick's frame is derived from the wall clock rather than a counter. That is
what makes it trustworthy: a status line that has stopped being invoked
freezes on whatever frame it last drew instead of continuing to animate.
Motion is evidence, not decoration. Leave `heartbeat` out of the line to turn
it off, or pick different frames:

```toml
[segment.heartbeat]
frames = "◐◓◑◒"    # or "▘▝▗▖", "▁▂▃▄▅▆▇▆▅▄▃▂", "⠁⠂⠄⡀⢀⠠⠐⠈"
period = 1.0       # seconds per frame; match refreshInterval
```

### Bars

Bars carry sub-cell resolution, so a 2% window does not render identically to
an empty one. The default width of 13 is chosen, not taste: the host reports
whole-number percentages, so there are 101 possible inputs, and 13 cells at 8
sub-steps per cell is the narrowest bar that renders every one of them
distinctly. `[bar].empty` picks the track (`█` solid, `░` textured, `" "`
blank) and `partial_style = "auto"` picks a boundary-cell family that matches
it so the bar never reads as notched. See
[statusline.example.toml](statusline.example.toml) for the annotated set.

## Calibrating `right_margin`

The host reserves some columns at the right edge before it truncates with an
ellipsis, and the count is not discoverable from inside the script; Claude
Code's fullscreen TUI takes about 4 beyond the `COLUMNS` it reports. If a line
ends in `…`, or the right group stops short of the edge, calibrate:

```sh
python3 ~/.claude/statusline.py ruler
```

Temporarily point `statusLine.command` at that and look at the second row,
which counts *down* to the right edge:

- The last digit you can see is how many columns are being clipped. Add it to
  `layout.right_margin`.
- If the row ends in `0` with no gap, `right_margin` is already correct.
- If there is blank space after the `0`, reduce `right_margin` by that much.

Then put `statusLine.command` back.

Glyph width is the other cause of clipping. Some fonts render `⏱`, `⬢`, `⚑` or
`⎇` two cells wide even though Unicode calls them narrow, which pushes the row
over by one column each. List the offenders and the layout will account for
them:

```toml
[layout]
wide_glyphs = ["⏱", "⬢"]
```

## Performance

The script runs on every refresh, once a second by default. Git state is
cached in `$XDG_RUNTIME_DIR/claude-statusline/`, keyed on the mtimes of
`index`, `HEAD` and the merge/rebase markers so a commit or checkout
invalidates it immediately, with a TTL (default 2s) as the real freshness
bound. A repo whose `git status` exceeds `slow_threshold` gets exponentially
backed off, so a monorepo that takes 800 ms to stat is polled every 8 seconds
instead of stalling every refresh. Set `git.enabled = false` to opt out.

Typical cost on a small repo is ~18 ms, half of it interpreter startup.
`install.sh` writes a shim rather than a symlink so CPython can cache the
engine's bytecode; `--symlink` and `--copy` are there if you prefer.

The catalog is closed on purpose. A user-supplied shell command in a segment
would run once a second with no cache, and nothing about the bar's cost could
be promised any more.

## Troubleshooting

```sh
python3 ~/.claude/statusline.py doctor      # config path, preset, lines, problems, width
python3 ~/.claude/statusline.py validate    # every problem in the config, with hints
python3 ~/.claude/statusline.py preview     # the layout at 100, 140 and 200 columns
make test                                   # full suite
```

**The bar is blank.** The script never exits non-zero and always prints
something; a blank bar means Claude Code is not running it. Check
`statusLine.command` in `settings.json`.

**A segment is missing.** Run `validate`. A misspelt segment or option is
reported with a suggestion and skipped, so the rest of the bar still renders.

**It shows only model and directory.** That is the fallback: rendering raised.
Reproduce with the real payload:

```sh
CLAUDE_STATUSLINE_DUMP=~/payload.json  # add to settings env, reload, then:
CLAUDE_STATUSLINE_DEBUG=1 python3 ~/.claude/statusline.py < ~/payload.json
```

`CLAUDE_STATUSLINE_DEBUG=1` prints the traceback to stderr instead of
swallowing it. Payload capture is off by default so the script is not writing
to disk once a second.

**Limits show `—`.** The host is not sending that `rate_limits` window. The
parser handles snake_case, camelCase, list-shaped and nested variants; if
yours differs, capture a payload as above and open an issue.

## Development

```sh
make test       # unit suite + install.sh tests, stdlib unittest
make lint       # byte-compile; example config and skill catalog in sync
make catalog    # regenerate skills/design/reference/catalog.md from the code
```

The suite renders every preset and every example layout from the skill
against every fixture at eight terminal widths and asserts no line ever
exceeds its budget; that invariant is the whole point of the layout, so it is
checked exhaustively rather than by eye. A golden file pins the classic
layout's exact output so refactors cannot move it by a column, and
`hostile.json` feeds deliberately wrong types through every field to keep the
"never crash" guarantee honest.

## License

MIT
