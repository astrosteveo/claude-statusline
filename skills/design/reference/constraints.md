# What the host allows, and what it does not

This is the knowledge that makes a status line trustworthy. Read it before
promising anything.

## The contract with Claude Code

- Claude Code runs `statusLine.command` as a **new process** on every refresh
  and pipes a JSON payload to stdin. It runs at session start, after each
  assistant message, after `/compact`, on permission-mode and vim-mode
  changes, when a rate-limit or cache window resets, and every
  `refreshInterval` seconds (minimum 1). The engine is installed with
  `refreshInterval: 1` and `padding: 0`.
- Whatever the command prints is the bar. Each `\n` is a row. Rows are taken
  from the conversation area: keep to three or fewer.
- The host **truncates each row with an ellipsis** when it is wider than the
  space it has. That space is smaller than `COLUMNS` by a margin the host does
  not report (about 4 columns in the fullscreen TUI). `layout.right_margin`
  (default 5) accounts for it; `statusline.py ruler` calibrates it: point
  `statusLine.command` at the ruler, read the last visible digit of the second
  row, add it to `right_margin`, then put the command back.
- Because each refresh is a fresh process there is **no state between
  refreshes**. Anything that looks animated must derive from the wall clock.
  The `heartbeat` segment does exactly that, which is why a stalled bar
  freezes: motion is evidence the bar is live.
- The plugin manifest cannot set `statusLine`. `install.sh` writes a shim into
  `~/.claude/` and patches `~/.claude/settings.json`, backing both up.

## The refresh budget

Once a second, forever. The engine renders in ~18 ms including interpreter
start; git state is cached on disk and backs off on slow repositories. This
is why the catalog is closed: a user-supplied shell command in a segment would
run once a second with no cache, and nothing about the bar's cost could be
promised any more. If someone needs data the payload does not carry, the
honest answer is that it is not supported yet, not a workaround.

## Width

- Widths are measured in terminal cells. CJK and emoji-presentation glyphs are
  two cells; combining marks are zero. The engine accounts for both, but some
  fonts draw glyphs wide that Unicode calls narrow (`⏱ ⬢ ⚑ ⎇` are the usual
  suspects). Symptom: the right edge clips by exactly the number of such
  glyphs on the row. Fix: list them in `layout.wide_glyphs`.
- Bar glyphs must be one cell. `[bar].full`/`empty` accept `█ ░ ▒ ▓` or a
  space; nothing else has been checked.
- The default bar width of 13 is not taste: the host sends whole percentages,
  and 13 cells at 8 sub-steps is the narrowest bar that draws all 101 of them
  distinctly.

## The payload

Fields the host documents (see `statusline.py segments` for which segment
reads which):

`model.{id,display_name}`, `cwd`, `workspace.{current_dir,project_dir,added_dirs,git_worktree,repo.{host,owner,name}}`,
`cost.{total_cost_usd,total_duration_ms,total_api_duration_ms,total_lines_added,total_lines_removed}`,
`context_window.{total_input_tokens,total_output_tokens,context_window_size,used_percentage,remaining_percentage,current_usage}`,
`exceeds_200k_tokens`, `fast_mode`, `effort.level`, `thinking.enabled`,
`rate_limits.{five_hour,seven_day,spend_limit}.{used_percentage,resets_at}`,
`prompt_cache.{warm,hit_ratio,...}`, `session_id`, `session_name`, `version`,
`output_style.name`, `vim.mode`, `agent.name`, `pr.{number,url,review_state,kind}`,
`worktree.{name,path,branch,original_cwd,original_branch}`.

Many are **absent or null** depending on the session: `session_name`, `effort`,
`vim`, `agent`, `pr`, `worktree`, `rate_limits`, `prompt_cache`,
`workspace.repo`, and `context_window.used_percentage` before the first API
call. A segment with nothing to show renders nothing, and its separator goes
with it; design layouts that still read well when the optional pieces are
missing. `preview --sample quiet` is the sparse case, `hot` the loud one.

Percentages arrive as whole numbers. `resets_at` is Unix epoch seconds.

## Colour and links

- Colours are raw SGR parameters: `38;5;N` (256-colour) or `38;2;R;G;B`
  (truecolor). The user's terminal theme decides what those look like; the
  defaults are chosen to read on dark backgrounds. There is no way to detect
  the theme from inside the command.
- OSC-8 hyperlinks (branch, PR) are supported by most modern terminals and
  ignored harmlessly by the rest.
- The host does not interpret markup; only ANSI escapes work.

## Not possible today

- A different layout per terminal width (the fit algorithm degrades one layout
  instead).
- Conditional segments ("only when dirty"); segments hide only when they have
  nothing to show.
- User-authored segments or shell commands.
- Reading anything not in the payload, except git state and the environment
  variables the `env`/`host` segments already read.
- Detecting the terminal theme, or the mouse, or keypresses.
