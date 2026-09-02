#!/usr/bin/env python3
"""The plugin and the design skill: manifests parse, references stay in sync,
and every example layout the skill hands out validates and fits."""
import json
import os
import re
import sys
import tomllib
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKILL = os.path.join(ROOT, "skills", "design")
FIXTURES = os.path.join(HERE, "fixtures")
sys.path.insert(0, ROOT)
import claude_statusline as S  # noqa: E402
from claude_statusline.cli import catalog_markdown, check_config  # noqa: E402
from claude_statusline.segments import REGISTRY  # noqa: E402

WIDTHS = (200, 160, 120, 100, 80, 60, 40)
_BLOCK = re.compile(r"```toml\n(.*?)```", re.S)


def toml_blocks(path):
    with open(path) as fh:
        return _BLOCK.findall(fh.read())


def fixtures():
    for name in sorted(os.listdir(FIXTURES)):
        if name.endswith(".json"):
            with open(os.path.join(FIXTURES, name)) as fh:
                data = json.load(fh)
            if not isinstance(data.get("cwd"), str) and "workspace" not in data:
                data["cwd"] = "/home/u/proj"      # keep the test's own cwd out of the bar
            yield name, data


class PluginTests(unittest.TestCase):
    def test_manifest(self):
        with open(os.path.join(ROOT, ".claude-plugin", "plugin.json")) as fh:
            m = json.load(fh)
        self.assertEqual(m["name"], "claude-statusline")
        self.assertRegex(m["version"], r"^\d+\.\d+\.\d+")

    def test_marketplace_points_at_this_repo(self):
        with open(os.path.join(ROOT, ".claude-plugin", "marketplace.json")) as fh:
            m = json.load(fh)
        entry = m["plugins"][0]
        self.assertEqual(entry["name"], "claude-statusline")
        self.assertEqual(entry["source"]["repo"], "astrosteveo/claude-statusline")

    def test_skill_frontmatter(self):
        with open(os.path.join(SKILL, "SKILL.md")) as fh:
            text = fh.read()
        self.assertTrue(text.startswith("---\n"))
        front = text.split("---\n", 2)[1]
        self.assertIn("name: design", front)
        self.assertIn("description:", front)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/statusline.py", front)

    def test_skill_references_exist(self):
        for name in ("schema.md", "constraints.md", "catalog.md", "examples.md"):
            self.assertTrue(os.path.exists(os.path.join(SKILL, "reference", name)), name)


class CatalogSyncTests(unittest.TestCase):
    def test_catalog_reference_is_generated_from_the_code(self):
        with open(os.path.join(SKILL, "reference", "catalog.md")) as fh:
            on_disk = fh.read()
        self.assertEqual(on_disk, catalog_markdown(),
                         "skills/design/reference/catalog.md is stale: run `make catalog`")

    def test_every_segment_is_documented(self):
        with open(os.path.join(SKILL, "reference", "catalog.md")) as fh:
            text = fh.read()
        for name in REGISTRY:
            self.assertIn(f"## {name}\n", text)

    def test_schema_reference_names_every_level(self):
        with open(os.path.join(SKILL, "reference", "schema.md")) as fh:
            text = fh.read()
        for level in ("full", "less", "lean", "narrow", "text"):
            self.assertIn(f"`{level}`", text)


class ExampleLayoutTests(unittest.TestCase):
    def tearDown(self):
        S.apply_config(S.deep_merge(S.DEFAULTS, {}))

    def test_examples_exist(self):
        self.assertGreaterEqual(len(toml_blocks(os.path.join(SKILL, "reference", "examples.md"))), 5)

    def test_every_example_validates_clean(self):
        for i, block in enumerate(toml_blocks(os.path.join(SKILL, "reference", "examples.md"))):
            raw = tomllib.loads(block)
            layout = S.build_layout(S.deep_merge(S.DEFAULTS, raw))
            problems = [str(p) for p in check_config(raw) + layout.problems]
            self.assertEqual(problems, [], f"examples.md block {i}:\n{block}")

    def test_every_example_fits_every_fixture(self):
        for i, block in enumerate(toml_blocks(os.path.join(SKILL, "reference", "examples.md"))):
            S.apply_config(S.deep_merge(S.DEFAULTS, {**tomllib.loads(block), "git": {"enabled": False}}))
            for name, data in fixtures():
                for cols in WIDTHS:
                    out = S.render(data, cols=cols, now=1_787_950_000)
                    for j, line in enumerate(out.split("\n"), 1):
                        self.assertLessEqual(S.display_width(line), S.usable_width(cols),
                                             f"example {i} / {name} @ {cols}: line {j} overflows")

    def test_schema_examples_validate(self):
        """The snippets in schema.md are fragments; each must at least be TOML the
        engine accepts without errors when merged over the classic layout."""
        for i, block in enumerate(toml_blocks(os.path.join(SKILL, "reference", "schema.md"))):
            raw = tomllib.loads(block)
            layout = S.build_layout(S.deep_merge(S.DEFAULTS, raw))
            self.assertEqual([str(p) for p in layout.errors], [], f"schema.md block {i}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
