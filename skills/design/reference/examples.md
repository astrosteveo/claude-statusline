# Worked configs

Every block below is a complete config. The test suite validates each one and
renders it at many widths, so what you copy is known to work.

## A look, not a layout

The cheapest good result: keep the default lines, change the dress.

```toml
theme = "catppuccin"
style = "powerline"
icons = "nerd"
```

## For any font

No Nerd Font needed: Unicode icons and square chips.

```toml
theme = "nord"
style = "chips"
icons = "unicode"
```

## One quiet line

Identity on the left, the numbers that matter on the right.

```toml
theme = "tokyo-night"
style = "minimal"

[[line]]
left = ["model", "dir", "git"]
right = ["context", "limit_5h"]
gap = 2

[segment.context]
label = ""
tokens = false
width = 8

[segment.limit_5h]
clock = false
width = 8
```

## Bars only

Three bars and when they reset; no labels or percentages.

```toml
style = "classic"

[[line]]
left = ["context", "limit_5h", "limit_7d"]

[segment.context]
format = "{bar}"

[segment.limit_5h]
format = "{bar}[ <muted>{reset}</muted>]"

[segment.limit_7d]
format = "{bar}[ <muted>{reset}</muted>]"
```

## Your own labels

The text segment placed twice under different names.

```toml
style = "capsules"

[[line]]
left = ["env_label", "model", "dir", "git"]
right = ["note", "clock"]

[segment.env_label]
type = "text"
text = "prod"
color = "red"
format = "<red><bold>{text}</bold></red>"

[segment.note]
type = "text"
text = "pairing with Claude"
icon = ""
```

## A gradient dashboard

Three lines, bars coloured along their length.

```toml
preset = "dashboard"
theme = "synthwave"
style = "pills"

[bar]
fill = "cyan,purple"
style = "slim"
```

## Claude Quest

The RPG's line at the bottom, the kitty pet at the right edge.

```toml
theme = "midnight"
style = "capsules"

[quest]
enabled = true
avatar = "auto"
```

## Claude Quest, inline

Just the hero badge on the first line.

```toml
preset = "minimal"

[quest]
enabled = true
placement = "inline"
```
