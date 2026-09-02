# Worked layouts

Every block below is a complete, valid config. Tests validate each one and
render it at every width, so what you copy is known to fit.

## A preset with two tweaks

The cheapest good result. Start here whenever a preset is close.

```toml
preset = "dashboard"

[segment.context]
size = false           # tokens without the window size

[segment.heartbeat]
frames = "◐◓◑◒"
color = "purple"
```

## One quiet line

Identity on the left, the two numbers that matter on the right.

```toml
[[line]]
left = ["model", "dir", "git"]
right = ["context", "limit_5h", "heartbeat"]
gap = 2

[segment.context]
format = "<gray>ctx</gray> {bar} <level>{pct}%</level>"
tokens = false

[segment.limit_5h]
pace = false
clock = false
```

## Bars only

No labels, no percentages: three bars and their reset times.

```toml
[[line]]
left = ["context", "limit_5h", "limit_7d"]

[segment.context]
format = "{bar}"

[segment.limit_5h]
format = "{bar}[ <dim>{reset}</dim>]"

[segment.limit_7d]
format = "{bar}[ <dim>{reset}</dim>]"
```

## Labelled sections with text segments

The same segment type placed twice under different names.

```toml
[[line]]
left = ["where", "dir", "git", "what", "cost"]
right = ["clock"]

[segment.where]
type = "text"
text = "repo"
format = "<bold>{text}</bold>"

[segment.what]
type = "text"
text = "spend"
format = "<bold>{text}</bold>"

[segment.cost]
format = "<gold>${usd}</gold>[ <gray>{duration}</gray>]"
```

## Custom formats and colours

A trimmed model name, the directory as its last component only, a truecolor
palette, and a wider bar with a textured track.

```toml
[[line]]
left = ["model", "dir", "git", "pr"]
right = ["session", "heartbeat"]
gap = 1

[[line]]
left = ["context"]
right = ["limit_5h", "limit_7d"]

[segment.model]
format = "<accent>{name}</accent>"

[segment.dir]
format = "<dir>{base}</dir>"

[segment.git]
format = "<gitstate>{branch}</gitstate>[ <yellow>{dirty}</yellow>][ <green>{staged}</green>]"

[bar]
width = 16
empty = "░"

[colors]
accent = "38;2;255;176;0"
dir = "38;2;120;180;255"
```

## The old bar, minus the things you never look at

Classic lines, written out, with the cache warning and output style gone and
the per-model window kept.

```toml
[[line]]
left = ["model", "dir", "git", "pr", "cost", "env", "session"]
right = ["heartbeat"]
gap = 1

[[line]]
left = ["context"]
right = ["limit_5h", "limit_7d", "limit_7d_model"]

[segment.limit_7d]
clock = false
```

## Migrating a 1.x config

If `doctor` or `validate` prints `features.* : no longer read`, run

```
python3 statusline.py migrate ~/.config/claude-statusline/config.toml          # show
python3 statusline.py migrate ~/.config/claude-statusline/config.toml --write  # apply, with backup
```

`features.heartbeat = false` becomes lines without `heartbeat`;
`features.pace = false` becomes `pace = false` on both limit segments; and so on.
The command prints every mapping it applied.
