# Statusline engine

## Problem

claude-statusline renders one very good status line. Its knowledge of the host
(right-edge accounting, wide glyphs, tolerant payload parsing, the stateless
heartbeat, git caching, the never-blank fallback) is exactly what anyone
building a Claude Code status line needs, but the layout itself is hardcoded in
two build functions. Users can restyle it; they cannot recompose it. The goal
is to turn the project into an engine that lets people, and Claude on their
behalf, design their own bars while the engine guarantees they fit and refresh
cheaply.

## Approach

Make the layout data. A config declares lines, each with a left and right
group of named segments drawn from a built-in catalog; the engine keeps doing
the fitting, dropping and edge maths. Ship the repo as a Claude Code plugin
whose skill teaches Claude the catalog, the host constraints and the schema,
and gives it subcommands to validate, preview and install a layout. Today's
bar becomes the default layout, so a config with no `[[line]]` renders what it
renders now.

Rejected: more toggles on the fixed layout (does not become an engine);
user-authored shell or Python segments (uncached subprocesses on a once-a-second
refresh, so the engine can no longer promise anything about cost; revisit when
someone needs data the payload does not carry); width-tiered layouts and
`when` conditions (nobody has asked yet; the schema leaves room for both).

## Scope

In:

- A `statusline/` package replacing the single file, with a thin `statusline.py`
  entry so the existing shim keeps working. `install.sh --copy` copies the
  package directory.
- Layout schema in the existing TOML config: `[[line]]` tables with `left` and
  `right` lists of segment names, `[segment.<name>]` tables for per-segment
  format, colour, priority and options.
- Segment catalog covering everything rendered today: `model`, `dir`, `git`,
  `pr`, `cache`, `cost`, `duration`, `diff`, `env`, `host`, `session`,
  `output_style`, `context`, `limit_5h`, `limit_7d`, `limit_7d_model`,
  `heartbeat`, plus `text` (a static label) and `clock` (wall time) because
  they cost nothing and are what people reach for first when designing.
- Three presets in `statusline/presets/`: `classic` (today's bar), `minimal`
  (one line), `dashboard` (three lines, bars on the left).
- Subcommands: `render` (default when stdin is a payload), `segments
  [--json]`, `validate [path]`, `preview [--layout path] [--preset name]
  [--width 100,140,200] [--fixture name]`, `migrate [path]`, `doctor`, `ruler`,
  `dump-config`. The old `--flag` forms keep working as aliases for one release.
- Plugin manifest and a `statusline-design` skill with reference files for
  the schema, the catalog and the host constraints, and a workflow that ends
  in a validated, previewed, installed config.
- Tests: golden snapshots of today's output captured before the refactor and
  asserted against the default layout; the width invariant over every preset,
  fixture and width; schema validation errors; `migrate` on the current
  example config.

Out:

- User-authored segments of any kind.
- Layouts that vary by terminal width, `when` conditions, separate theme files.
- A payload recorder beyond the existing `CLAUDE_STATUSLINE_DUMP`.
- Rewriting `install.sh` in Python. It stays, gains nothing but the package
  copy, and the skill calls it.

## Key decisions

- **Declarative layout, built-in segments only.** Creative freedom means
  arrangement, anchoring, format and colour, not code. Keeps every layout
  checkable and keeps the refresh budget owned by the engine.
- **Plugin with a design skill.** The constraint knowledge should reach users
  through Claude, not only through the README. The skill drives subcommands;
  it never reads the engine source.
- **Clean break on `[features]`.** Its toggles become options on the segment
  they belong to. `[layout]`, `[bar]`, `[thresholds]`, `[glyphs]`, `[colors]`
  and `[git]` stay as global style and behaviour. The engine renders an old
  file without crashing, ignores legacy keys, and `doctor` lists each one
  with the replacement; `migrate` rewrites the file.
- **One fit algorithm for every line.** Each segment offers renderings from
  richest to cheapest (a bar with pace and clock, then without clock, then a
  narrower bar, then just the percentage). While a line overflows, the engine
  steps the lowest-priority segment that still has a cheaper rendering down
  one notch; when nothing can step down, it drops the lowest-priority segment.
  This replaces both today's drop loop on line 1 and the ladder on line 2.
- **Format strings are small.** `{field}` placeholders from the segment's
  documented fields, `[colorname]…[/]` spans using `[colors]` names, and
  nothing else. A segment declares which fields it requires; if one is
  missing the segment renders nothing. Missing optional fields render empty
  and adjacent whitespace collapses.
- **Right groups are anchored, left groups flow.** The gap between them is
  padding, minimum two columns when both sides are present. Empty lines are
  omitted from output.
- **Goldens before refactor.** The current output for every fixture at every
  test width is captured first and becomes the default layout's acceptance
  test, so the package split cannot drift the bar by a column.

## Edge cases & failure modes

- Unknown segment or option in a layout: `validate` fails with the table and
  key; `render` skips the segment and keeps going, so a typo never blanks the
  bar. `doctor` reports the same list.
- A layout no width can satisfy (too many high-priority segments): the fit
  algorithm ends by dropping everything but the highest priority segment on
  each line, which then truncates with an ellipsis. `preview` shows the
  narrowest width at which nothing was dropped.
- Segment name used twice in one layout: allowed, rendered twice, since
  `text` needs it; `validate` warns for data segments.
- Payload missing whole sections: segments requiring them render nothing and
  their separators vanish, as today.
- Fallback on render exception is unchanged: model and directory, never blank.
- Legacy config with `[features]` and no `[[line]]`: default layout, legacy
  keys ignored and reported, never honoured.

## Open questions

- ~~Whether a plugin manifest can register the `statusLine` command itself.~~
  Resolved: it cannot (plugin `settings.json` supports only `agent` and
  `subagentStatusLine`), so `install.sh` keeps patching `settings.json` and
  the skill runs it when needed.
- Whether `limit_7d_model` should stay a separate segment or become an option
  on `limit_7d`. Separate for now because it has its own priority.
