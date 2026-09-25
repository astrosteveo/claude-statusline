"""Redraw docs/gallery.png: the bar in several themes and styles.

    python3 tools/gallery.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("CLAUDE_QUEST_HOME", os.path.join(ROOT, "tools", "gallery-quest"))

from claude_statusline import samples  # noqa: E402
from claude_statusline.layout import compile_config  # noqa: E402
from claude_statusline.render import render  # noqa: E402

NOW = 1_790_400_000
SHOWN = [
    ("midnight", "capsules", "nerd", "classic"),
    ("catppuccin", "powerline", "nerd", "classic"),
    ("tokyo-night", "pills", "nerd", "compact"),
    ("claude", "chips", "unicode", "classic"),
    ("gruvbox", "slant", "nerd", "minimal"),
    ("nord", "minimal", "nerd", "classic"),
    ("rose-pine", "classic", "unicode", "compact"),
]


def main():
    out = []
    data = samples.load("busy", NOW)
    for theme, style, icons, preset in SHOWN:
        comp = compile_config({"theme": theme, "style": style, "icons": icons, "preset": preset})
        out.append(f"#! {theme} · {style} · {icons} icons · {preset}")
        out.append(render(data, comp, cols=150, now=NOW, env={"COLORTERM": "truecolor"}, live=False))
    text = "\n".join(out)
    dest = os.path.join(ROOT, "docs", "gallery.png")
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "shot.py"), dest, "--bg", "#161a26",
                    "--size", "14"], input=text.encode(), check=True)
    print(dest)


if __name__ == "__main__":
    main()
