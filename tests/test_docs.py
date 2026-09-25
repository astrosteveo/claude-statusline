"""Every config the docs show is valid and fits."""
import os
import re
import sys
import tomllib
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from claude_statusline import samples  # noqa: E402
from claude_statusline.context import Context  # noqa: E402
from claude_statusline.layout import compile_config  # noqa: E402
from claude_statusline.render import render_lines  # noqa: E402

NOW = 1_790_400_000


def toml_blocks(path):
    with open(path) as fh:
        text = fh.read()
    return re.findall(r"```toml\n(.*?)```", text, re.S)


class DocTests(unittest.TestCase):
    def check(self, raw, where):
        comp = compile_config(raw)
        self.assertEqual(comp["problems"], [], where)
        data = samples.load("busy", NOW)
        for cols in (60, 100, 160, 220):
            ctx = Context(data, comp, cols=cols, now=NOW, env={"COLORTERM": "truecolor"}, live=False)
            for f in render_lines(data, comp, ctx=ctx):
                if f:
                    self.assertLessEqual(f.text.width, ctx.avail, (where, cols))

    def test_examples(self):
        blocks = toml_blocks(os.path.join(ROOT, "skills", "design", "reference", "examples.md"))
        self.assertGreaterEqual(len(blocks), 6)
        for i, block in enumerate(blocks):
            self.check(tomllib.loads(block), f"examples.md block {i}")

    def test_example_config(self):
        with open(os.path.join(ROOT, "statusline.example.toml"), "rb") as fh:
            self.check(tomllib.load(fh), "statusline.example.toml")

    def test_readme_blocks_parse(self):
        for i, block in enumerate(toml_blocks(os.path.join(ROOT, "README.md"))):
            raw = tomllib.loads(block)
            errors = [p for p in compile_config(raw)["problems"] if p[0] == "error"]
            self.assertEqual(errors, [], f"README block {i}")


if __name__ == "__main__":
    unittest.main()
