# What the host allows, and what it does not

Read this before promising anything.

## The contract with Claude Code

- Claude Code runs `statusLine.command` as a new process on every refresh
  and pipes a JSON payload to stdin: at session start, after each assistant
  message, on mode changes, and every `refreshInterval` seconds. The
  installer sets `refreshInterval: 1` and `padding: 0`.
- Whatever the command prints is the bar; each line is a row taken from the
  conversation area. The bar hides while menus and prompts are open.
- ANSI colour (truecolor and background colours) and OSC-8 links work.
- The host sets `COLUMNS`. It keeps a few columns at the right edge and
  cuts a line that is wider than the rest; `layout.right_margin` (default 5)
  accounts for that and `statusline.py ruler` calibrates it: point
  `statusLine.command` at the ruler, read the last digit visible on its second
  row, add it to `right_margin`, then put the command back.
- There is no state between refreshes. Anything that moves (the pet, the
  optional `heartbeat` tick) derives from the clock, so a stalled bar freezes.
- A plugin cannot set `statusLine`; `install.sh` writes a small shim to
  `~/.claude/statusline.py` and patches `settings.json`, backing both up.

## The refresh budget

Once a second, forever, per session. A refresh takes about 10 ms, 4 of
which are Python starting up: the payload is parsed without importing
`json`, the config is compiled once and cached, segment modules load only when
placed, and git state comes from a cache that a detached background process
refreshes, so the bar never waits for git. This is why the catalog is closed:
a user-supplied command in a segment would run every second with no cache,
and nothing about the bar's cost could be promised. If someone needs data the
payload does not carry, the honest answer is that it is not supported.

## Width

- Widths are measured exactly as Claude Code measures them (the
  `string-width` rules): wide East Asian characters and emoji take two cells,
  a text-style emoji followed by VS16 takes two, combining marks none.
- Some fonts draw glyphs wide that Unicode calls narrow (`⏱ ⬢ ⚑ ⎇` are
  common). Symptom: the right edge clips by the number of such glyphs. Fix:
  list them in `layout.wide_glyphs`.
- Nerd Font icons and the powerline/rounded caps need a Nerd Font, or a
  terminal that bundles the symbols (kitty, WezTerm, Ghostty). Without one,
  use `icons = "unicode"` and a style that needs no special glyphs (minimal,
  classic, dots, chips).
- A bar of 13 cells is the narrowest that shows all 101 whole percentages
  distinctly (8 steps a cell).

## The payload

Documented fields the segments read: `model.{id,display_name}`, `cwd`,
`workspace.{current_dir,project_dir,git_worktree,repo.{host,owner,name}}`,
`cost.{total_cost_usd,total_duration_ms,total_api_duration_ms,total_lines_added,total_lines_removed}`,
`context_window.{total_input_tokens,total_output_tokens,context_window_size,used_percentage,current_usage}`,
`exceeds_200k_tokens`, `fast_mode`, `effort.level`, `thinking.enabled`,
`rate_limits.{five_hour,seven_day,spend_limit}.{used_percentage,resets_at}`,
`prompt_cache.{warm,hit_ratio,miss_recache_tokens,ttl,…}`, `session_name`,
`version`, `output_style.name`, `vim.mode`, `agent.name`,
`pr.{number,url,review_state,kind}`, `worktree.{name,branch,original_branch}`.

Many are absent depending on the session (`rate_limits` and `prompt_cache`
until the first response; `pr`, `vim`, `agent`, `worktree`, `session_name`,
`effort` when not in use). A segment with nothing to show renders nothing and
its separator goes with it; a line with nothing on it is left out. Preview
with `--sample quiet` for the sparse case and `--sample hot` for the loud one;
`--sample live` uses the last payload the bar actually received.

## Live activity

- `activity enable` registers command hooks with `async: true` for
  SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, PostToolUseFailure,
  SubagentStart, SubagentStop, Stop, StopFailure, PreCompact, PostCompact,
  TaskCreated, TaskCompleted and SessionEnd, and sets `[activity] enabled`.
  Each event updates `activity-<session>.bin` in the runtime directory.
- The payload carries none of this: without the hooks the `turn`, `tools`,
  `agents`, `tasks` and `mode` segments show nothing.
- The permission mode reaches the bar with the next hook event, not the
  moment it changes. The task list exists only where the model has the task
  tools (off by default on current models).

## Claude Quest

- `quest enable` registers five hooks in `settings.json` (SessionStart,
  UserPromptSubmit, PostToolUse, PostToolUseFailure, Stop), installs `/quest`,
  and sets `[quest] enabled = true`. `quest disable` removes them again and
  keeps the save (`~/.claude/quest/state.json`).
- The hooks do nothing while `[quest] enabled` is false, so the config is the
  single switch.
- The pet picture needs kitty (Unicode placeholders) and pycairo; elsewhere
  the pet is drawn as text.
- Game mode (`placement = "game"`) replaces your lines with the quest ticker
  and the scene. Your lines still name the session details on the ticker's
  row (`game_details`), and they give way before any quest segment does.

## Not possible

- User-authored segments or shell commands.
- A different layout per terminal width (the fitter degrades one layout).
- Conditional segments beyond "shown when there is something to show".
- Detecting the terminal's font, background colour, mouse or keys from the bar.
