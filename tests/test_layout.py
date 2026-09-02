#!/usr/bin/env python3
"""Layout schema, presets and the promise that a bad config never blanks the bar."""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(HERE, "fixtures")
sys.path.insert(0, ROOT)
import claude_statusline as S  # noqa: E402
from claude_statusline.layout import build_layout, list_presets  # noqa: E402
from claude_statusline.segments import REGISTRY  # noqa: E402

WIDTHS = (200, 174, 160, 120, 100, 80, 60, 40)
_SGR = re.compile(r"\033\[[0-9;]*[@-~]")


def strip(s):
    return _SGR.sub("", s)


def fixtures():
    for name in sorted(os.listdir(FIXTURES)):
        if name.endswith(".json"):
            with open(os.path.join(FIXTURES, name)) as fh:
                yield name, json.load(fh)


def cfg(**over):
    return S.deep_merge(S.DEFAULTS, over)


def problems(layout):
    return [str(p) for p in layout.problems]


class PresetTests(unittest.TestCase):
    def tearDown(self):
        S.apply_config(cfg())

    def test_presets_exist(self):
        self.assertEqual(list_presets(), ["classic", "dashboard", "minimal"])

    def test_every_preset_validates_clean(self):
        for name in list_presets():
            self.assertEqual(problems(build_layout(cfg(preset=name))), [], name)

    def test_every_preset_fits_every_fixture_at_every_width(self):
        """The core invariant, now over every shipped layout."""
        for preset in list_presets():
            S.apply_config(cfg(preset=preset, git={"enabled": False}))
            for name, data in fixtures():
                for cols in WIDTHS:
                    out = S.render(data, cols=cols, now=1_787_950_000)
                    budget = S.usable_width(cols)
                    for i, line in enumerate(out.split("\n"), 1):
                        self.assertLessEqual(
                            S.display_width(line), budget,
                            f"{preset}/{name} @ {cols}: line {i} overflows")

    def test_unknown_preset_falls_back_to_classic(self):
        layout = build_layout(cfg(preset="nope"))
        self.assertEqual(layout.preset, "classic")
        self.assertEqual(len(layout.lines), 2)
        self.assertTrue(any("unknown preset" in p for p in problems(layout)))

    def test_explicit_lines_replace_preset_lines(self):
        layout = build_layout(cfg(preset="dashboard", line=[{"left": ["model"]}]))
        self.assertEqual(len(layout.lines), 1)
        self.assertEqual(layout.segment_names(), ["model"])

    def test_segment_tables_merge_over_preset(self):
        layout = build_layout(cfg(preset="minimal", segment={"context": {"size": False}}))
        ctx = next(s for line in layout.lines for s in line.left if s.name == "context")
        self.assertFalse(ctx.opts["tokens"], "preset option lost")
        self.assertFalse(ctx.opts["size"], "user option not applied")


class SchemaTests(unittest.TestCase):
    def test_unknown_segment_with_hint(self):
        layout = build_layout(cfg(line=[{"left": ["model", "gti"]}]))
        self.assertEqual(layout.segment_names(), ["model"])
        self.assertIn("error: line.gti: unknown segment 'gti' (did you mean 'git'?)",
                      problems(layout))

    def test_unknown_option_with_hint(self):
        layout = build_layout(cfg(line=[{"left": ["dir"]}], segment={"dir": {"dept": 2}}))
        self.assertIn("error: segment.dir.dept: unknown option (did you mean 'depth'?)",
                      problems(layout))

    def test_wrong_type_keeps_default(self):
        layout = build_layout(cfg(line=[{"left": ["dir"]}], segment={"dir": {"depth": "two"}}))
        self.assertEqual(layout.lines[0].left[0].opts["depth"], 3)
        self.assertTrue(any(p.startswith("error: segment.dir.depth: expected int") for p in problems(layout)))

    def test_int_accepts_whole_float_and_rejects_bool(self):
        ok = build_layout(cfg(line=[{"left": ["dir"]}], segment={"dir": {"depth": 2.0}}))
        self.assertEqual(ok.lines[0].left[0].opts["depth"], 2)
        bad = build_layout(cfg(line=[{"left": ["dir"]}], segment={"dir": {"depth": True}}))
        self.assertTrue(bad.errors)

    def test_bad_template_falls_back_to_default(self):
        layout = build_layout(cfg(line=[{"left": ["model"]}], segment={"model": {"format": "<red>{name}"}}))
        self.assertEqual(layout.lines[0].left[0].opts["format"], REGISTRY["model"].format)
        self.assertTrue(any("unclosed '<red>'" in p for p in problems(layout)))

    def test_unknown_field_and_colour_are_warnings(self):
        layout = build_layout(cfg(line=[{"left": ["model"]}],
                                  segment={"model": {"format": "<pink>{nme}</pink>"}}))
        self.assertEqual(layout.errors, [])
        msgs = problems(layout)
        self.assertIn("warning: segment.model.format: {nme} is not a field of 'model'", msgs)
        self.assertIn("warning: segment.model.format: <pink> is not a colour", msgs)

    def test_named_instance(self):
        layout = build_layout(cfg(line=[{"left": ["hi", "text"]}],
                                  segment={"hi": {"type": "text", "text": "hello"},
                                           "text": {"text": "plain"}}))
        self.assertEqual(problems(layout), [])
        self.assertEqual([s.type for s in layout.lines[0].left], ["text", "text"])
        self.assertEqual([s.opts["text"] for s in layout.lines[0].left], ["hello", "plain"])

    def test_configured_but_unplaced_is_a_warning(self):
        layout = build_layout(cfg(line=[{"left": ["model"]}], segment={"dir": {"depth": 1}}))
        self.assertIn("warning: segment.dir: configured but not placed on any line", problems(layout))

    def test_legacy_features_are_reported_not_honoured(self):
        layout = build_layout(cfg(features={"pace": False, "heartbeat": False}))
        msgs = problems(layout)
        self.assertTrue(any(p.startswith("warning: features.pace: no longer read") for p in msgs))
        self.assertTrue(any(p.startswith("warning: features.heartbeat: no longer read") for p in msgs))
        self.assertIn("heartbeat", layout.segment_names())

    def test_bad_line_shapes(self):
        layout = build_layout(cfg(line=[{"left": "model"}, "nope", {"left": ["model"], "gap": -1, "centre": []}]))
        msgs = problems(layout)
        self.assertIn("error: line[0].left: must be a list of segment names", msgs)
        self.assertIn("error: line[1]: must be a table", msgs)
        self.assertIn("error: line[2].gap: must be a non-negative integer", msgs)
        self.assertIn("error: line[2].centre: unknown key (left, right, gap)", msgs)
        self.assertEqual(len(layout.lines), 1)

    def test_every_catalog_default_format_is_valid(self):
        from claude_statusline.template import Template
        for name, seg in REGISTRY.items():
            tpl = Template(seg.format)
            unknown = tpl.fields - set(seg.fields) - {"url"}
            self.assertEqual(unknown, set(), f"{name}: default format uses undocumented fields")
            for color in tpl.colors:
                self.assertTrue(color in S.DEFAULTS["colors"] or color in seg.colors,
                                f"{name}: default format uses undocumented colour <{color}>")


class RenderRobustnessTests(unittest.TestCase):
    def tearDown(self):
        S.apply_config(cfg())

    def test_typo_never_blanks_the_bar(self):
        S.apply_config(cfg(line=[{"left": ["model", "gti"], "right": ["hartbeat"]}]))
        with open(os.path.join(FIXTURES, "full.json")) as fh:
            data = json.load(fh)
        self.assertIn("Opus 5", strip(S.render(data, cols=120)))

    def test_empty_lines_are_omitted(self):
        S.apply_config(cfg(line=[{"left": ["model"]}, {"left": ["session"]}]))
        out = S.render({"model": {"display_name": "X"}}, cols=120)
        self.assertEqual(out.count("\n"), 0)

    def test_gap_is_honoured(self):
        S.apply_config(cfg(line=[{"left": ["model"], "right": ["text"], "gap": 4}],
                           segment={"text": {"text": "hi"}}))
        out = strip(S.render({"model": {"display_name": "X" * 60}}, cols=80))
        self.assertIn("    hi", out)
        self.assertEqual(S.display_width(out), S.usable_width(80))

    def test_custom_format_renders(self):
        S.apply_config(cfg(line=[{"left": ["model"]}],
                           segment={"model": {"format": "<bold>[{name}]</bold>[ @ {effort}]"}}))
        out = strip(S.render({"model": {"display_name": "Opus"}, "effort": {"level": "max"}}, cols=80))
        self.assertEqual(out, "Opus @ max")


if __name__ == "__main__":
    unittest.main(verbosity=2)
