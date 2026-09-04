# Layout schema

The config is one TOML file. Every key is optional and merges over the defaults;
a three-line file is a complete config.

```toml
preset = "classic"        # supplies the lines when none are declared: classic | minimal | dashboard

[[line]]                  # a row of the bar; declare as many as you want (three is plenty)
left  = ["model", "dir", "git"]      # flows from the left edge, joined by layout.separator
right = ["heartbeat"]                # pushed against the right edge
gap   = 1                            # minimum columns between the groups (default 2)

[segment.dir]             # options for a catalog segment used above
depth = 2
priority = 95
format = "<dir>{glyph} {path}</dir>"

[segment.greeting]        # a named instance of a segment, so one type can appear twice
type = "text"
text = "hello"
format = "<gold>{text}</gold>"
```

## Resolution

- `preset` names a bundled layout. Its `[[line]]` tables are used only when the
  config has none of its own; its `[segment.*]` tables always apply, with the
  config's tables merged over them. `statusline.py presets` shows each one.
- A name in `left`/`right` is looked up in `[segment.<name>]`. If that table has
  `type`, it is an instance of that catalog segment; otherwise the name must be
  a catalog segment itself.
- Unknown segments, options and templates are reported by `validate` and skipped
  by the renderer. A broken config degrades; it never blanks the bar.

## Universal options

Every segment accepts:

| key | type | meaning |
|-----|------|---------|
| `format` | string | the template (below) |
| `priority` | int | higher survives longer when the line is too narrow |

Segment-specific options are listed by `statusline.py segments <name>`.

## Templates

A format string is text plus four constructs:

| construct | meaning |
|-----------|---------|
| `{field}` | a value the segment supplies; empty when unknown |
| `[ ... ]` | optional group: shown only when every `{field}` inside is non-empty. An empty group also removes a doubled space, so `[ · {effort}]` leaves no trace |
| `<name> ... </name>` | colour span. `name` is a key of `[colors]` or a colour the segment computes (its `colours` list). `</>` closes the innermost span |
| `<link> ... </link>` | OSC-8 hyperlink to the segment's `url` field; plain text when there is none |

Escape a literal `{ } [ ] < >` with a backslash (in a TOML basic string that is
`"\\["`; in a literal string `'\['`). Leading and trailing spaces are trimmed.
Fields that already contain escape sequences (bars) are emitted untouched.

Examples:

```toml
[segment.model]
format = "<model>{name}</model>"                        # just the name
[segment.cost]
format = "<gold>${usd}</gold>"                          # cost alone
[segment.context]
format = "{bar} <level>{pct}%</level>"                  # no label
[segment.limit_5h]
format = "<gray>5h</gray> {bar}[ <dim>{reset}</dim>]"   # no percentage, no pace
```

## Fitting

For each line the engine renders every segment at detail level 0 (`full`),
joins the groups, and checks the width against the usable columns
(`COLUMNS - layout.right_margin`). If it overflows, every segment on the line
steps down one level together:

| level | what goes |
|-------|-----------|
| `full` | nothing |
| `less` | the reset clock on limit bars |
| `lean` | the pace projection |
| `narrow` | bars shrink to half width |
| `text` | bars disappear; percentages remain; `limit_7d_model` hides |

Only when `text` still overflows does the engine drop the lowest-priority
segment present, then try again from `full`. The last segment on a line is
never dropped; it may overflow, and the host truncates it with an ellipsis.

The right group is padded to the edge; when both groups are present at least
`gap` columns separate them. A line with nothing to show is omitted.

## Style sections

These are global and unchanged from 1.x:

| section | keys |
|---------|------|
| `[layout]` | `right_margin`, `separator`, `fallback_columns`, `wide_glyphs` |
| `[bar]` | `width`, `style`, `fill`, `track`, `cap_left`, `cap_right`, `full`, `empty`, `partial`, `partial_style`, `min_sliver`, `pulse` |
| `[thresholds]` | `yellow`, `orange`, `red` (percentages) |
| `[git]` | `enabled`, `timeout`, `cache_ttl`, `slow_threshold`, `slow_backoff` |
| `[glyphs]` | one glyph per named use, plus `heartbeat_frames` |
| `[colors]` | name → SGR parameters; add your own names for templates |

`[features]` from 1.x is no longer read. `statusline.py migrate` rewrites it.

## Bars

A bar is `width` cells; three choices are independent and any bar segment
(`context`, `limit_*`) may override the first two with its own `style` and
`fill` options.

| key | values | meaning |
|-----|--------|---------|
| `style` | `block` `shade` `thin` `dots` `pips` `ascii` | the glyph set; `statusline.py bars` draws them all |
| `fill` | `level`, `gradient`, a `[colors]` key, or `"key,key"` | one colour by threshold; a colour per cell by its position; a fixed colour; colours spread along the bar |
| `track` | a `[colors]` key | colour of the empty cells and the caps (default `dim`) |
| `cap_left` / `cap_right` | one glyph each | frame the bar; they sit outside `width` |
| `full` / `empty` | one glyph each | override the style's glyphs; `""` means "from the style" |
| `pulse` | bool | past the red threshold, embolden the fill on odd seconds |

```toml
[bar]
style = "shade"
fill = "gradient"
cap_left = "▕"
cap_right = "▏"

[segment.context]
style = "thin"
fill = "cyan"
```

Every glyph must be one cell wide; the fitter depends on it. The narrow
detail level halves `width`; caps stay.
