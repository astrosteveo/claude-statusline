# claude-statusline

A two-line status line for [Claude Code](https://claude.com/claude-code): model,
repo state and cost on top; context and rate-limit bars underneath, anchored
flush to the right edge of the terminal.

```
◆ Opus 5 (1M context) · high │ ▸ …/u/Projects/widget-factory │ $24.73 59m +1006/-21 │ refactor the parser
ctx ███▋█████████ 28% (279k/1.0M)                                                             5h █▌███████████ 12% ⇢18% ↻1h43m·19:26 │ 7d ▊████████████ 6% ⇢56% ↻6d5h
```

Pure Python 3.11+, no third-party dependencies, no network calls.

## Install

```sh
git clone https://github.com/astrosteveo/claude-statusline ~/Projects/claude-statusline
cd ~/Projects/claude-statusline
./install.sh
```

That installs a small shim into `~/.claude/`, seeds a config at
`~/.config/claude-statusline/config.toml`, and patches `statusLine` into
`~/.claude/settings.json` — backing up anything it replaces. Start a new
session (or run `/statusline`) to see it.

`./install.sh --symlink` symlinks the script instead; `--copy` installs a
standalone snapshot that does not need the repo to stay put; and
`./install.sh --uninstall` puts your previous status line back.

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

`padding: 0` matters — the layout does its own right-edge accounting.

## What it shows

**Line 1** — model and effort (`⚡` when fast mode is on), working directory,
git state, PR badge, prompt-cache warning, cost / wall time / lines changed,
virtualenv and SSH host, session name. Segments have priorities and the
lowest-value ones drop out as the terminal narrows.

**Line 2** — context usage on the left, then the 5-hour and 7-day rate-limit
windows pushed against the right edge. Each limit bar carries a burn-rate
projection (`⇢103%` means "at this pace you will exhaust the window") and a
reset countdown with wall-clock time. A per-model weekly cap appears as
`7d·opus` when it differs from the overall one.

Git state reads: `⎇ branch`, `↑↓` ahead/behind, `∅` no upstream, `+staged`,
`~dirty`, `?untracked`, `!conflicts`, `⚑stashes`, and `⏱` since the last commit
once a dirty tree goes stale. Branch and PR are OSC-8 hyperlinks when the host
supplies repo metadata.

## Configuration

Everything lives in `~/.config/claude-statusline/config.toml` (or
`~/.claude/statusline.toml`, or wherever `$CLAUDE_STATUSLINE_CONFIG` points).
Every key is optional and merges over the defaults, so a three-line file is
fine:

```toml
[bar]
width = 16

[features]
pace = false
```

Bars carry sub-cell resolution, so a 2% window does not render identically to
an empty one.

The default width of 13 is chosen, not taste. The host reports whole-number
percentages, so there are 101 possible inputs; at 8 sub-steps per cell, 13
cells give 104 distinct renderings and every input gets its own. Twelve cells
give 96 and collide on 1/2, 25/26, 50/51 and 75/76 — the four points where a
change genuinely happened but the bar does not move. Beyond 13 the input runs
out first, so extra cells cost columns and return nothing.

The boundary cell between filled and empty is the fiddly part. Eighth-blocks
(`▏▎▍`) ink only the left fraction of their cell, so the remainder has to be
painted to match the track or the bar reads as notched. `partial_style =
"auto"` picks a family that matches whatever track you configured:

| `empty` | family | steps/cell | boundary remainder |
|---------|--------|-----------|--------------------|
| `"█"` solid *(default)* | eighth `▏▎▍` | 8 | painted in the track colour |
| `"░"` textured | shade `░▒▓` | 3 | inked by the glyph itself |
| `"  "` blank | eighth `▏▎▍` | 8 | nothing to match |

A solid track cannot distinguish 0% from 2% by shape, since fill and track are
the same glyph — only colour separates them. If you need the distinction to
survive a mono or low-contrast theme, use `empty = " "`, which keeps all eight
steps, or `empty = "░"`, which trades down to three. Set `partial_style`
explicitly to override the pairing, or `"off"` to round to whole cells.

See [`statusline.example.toml`](statusline.example.toml) for the annotated set,
`--dump-config` for the resolved values, and `--doctor` for which file actually
loaded.

## Calibrating `right_margin`

The host reserves some columns at the right edge before it truncates with an
ellipsis, and the count is not discoverable from inside the script — Claude
Code's fullscreen TUI takes about 4 beyond the `COLUMNS` it reports. If your
line 2 ends in `…`, or the bars stop short of the edge, calibrate:

```sh
python3 ~/.claude/statusline.py --ruler
```

Temporarily point `statusLine.command` at that and look at the second row,
which counts *down* to the right edge:

- The last digit you can see is how many columns are being clipped. Add it to
  `right_margin`.
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

The script runs on every refresh — once a second by default. Git state is
cached in `$XDG_RUNTIME_DIR/claude-statusline/`, keyed on the mtimes of
`index`, `HEAD` and the merge/rebase markers so a commit or checkout
invalidates it immediately, with a TTL (default 2s) as the real freshness
bound. Worktree edits do not move those mtimes, so dirty-file counts refresh on
the TTL rather than instantly.

A repo whose `git status` exceeds `slow_threshold` gets exponentially backed
off (`ttl = duration × slow_backoff`), so a monorepo that takes 800 ms to stat
is polled every 8 seconds instead of stalling every refresh. Set
`git.enabled = false` to opt out entirely.

Typical cost on a small repo is ~18 ms, a third of it Python interpreter
startup. `install.sh` writes a shim into `~/.claude/` rather than symlinking,
because a script run directly is never bytecode-cached — letting CPython cache
`statusline.pyc` saves about 4 ms of recompilation on every refresh. Use
`--symlink` or `--copy` if you would rather not have the shim.

## Troubleshooting

```sh
python3 ~/.claude/statusline.py --doctor    # config path, width, cache state
python3 ~/.claude/statusline.py --demo      # render a sample payload
make test                                   # full suite
```

**The bar is blank.** The script never exits non-zero and always prints
something; a blank bar means Claude Code is not running it. Check
`statusLine.command` in `settings.json`.

**It shows only model and directory.** That is the fallback: rendering raised.
Reproduce with the real payload:

```sh
CLAUDE_STATUSLINE_DUMP=~/payload.json  # add to settings env, reload, then:
CLAUDE_STATUSLINE_DEBUG=1 python3 ~/.claude/statusline.py < ~/payload.json
```

`CLAUDE_STATUSLINE_DEBUG=1` prints the traceback to stderr instead of
swallowing it. Payload capture is off by default so the script is not writing
to disk once a second.

**Limits show `—` or `limits n/a`.** The host is not sending `rate_limits`.
The parser handles snake_case, camelCase, list-shaped and nested variants; if
yours differs, capture a payload as above and open an issue.

## Development

```sh
make test     # 47 tests, stdlib unittest
make lint     # byte-compile + config drift check
```

The suite renders every fixture in `tests/fixtures/` at eight terminal widths
and asserts no line ever exceeds its budget — that invariant is the whole
point of the layout, so it is checked exhaustively rather than by eye.
`hostile.json` feeds deliberately wrong types through every field to keep the
"never crash" guarantee honest.

## License

MIT
