#!/usr/bin/env python3
"""The subcommand surface the design skill drives."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "statusline.py")
sys.path.insert(0, ROOT)
from claude_statusline.cli import migrate_config, to_toml  # noqa: E402
from claude_statusline.segments import REGISTRY  # noqa: E402


def run(*args, stdin="", cols="120", config="/nonexistent"):
    env = {**os.environ, "COLUMNS": cols, "CLAUDE_STATUSLINE_CONFIG": config, "TZ": "UTC"}
    return subprocess.run([sys.executable, SCRIPT, *args], input=stdin,
                          capture_output=True, text=True, env=env, timeout=30)


def tmp_toml(text):
    fh = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
    fh.write(text)
    fh.close()
    return fh.name


class CatalogCommands(unittest.TestCase):
    def test_segments_lists_every_catalog_entry(self):
        p = run("segments")
        self.assertEqual(p.returncode, 0, p.stderr)
        for name in REGISTRY:
            self.assertIn(name, p.stdout)

    def test_segments_json_is_complete(self):
        data = json.loads(run("segments", "--json").stdout)
        self.assertEqual({d["name"] for d in data}, set(REGISTRY))
        for d in data:
            for key in ("doc", "priority", "format", "options", "fields", "colors"):
                self.assertIn(key, d, d["name"])

    def test_segment_detail(self):
        p = run("segments", "limit_5h")
        self.assertIn("pace_min_elapsed", p.stdout)
        self.assertIn("{pace}", p.stdout)
        self.assertIn("<pacecolor>", p.stdout)
        detail = json.loads(run("segments", "limit_5h", "--json").stdout)
        self.assertEqual(detail["options"]["clock"]["type"], "bool")

    def test_unknown_segment(self):
        self.assertIn("unknown segment", run("segments", "nope").stdout)

    def test_presets(self):
        p = run("presets")
        for name in ("classic", "minimal", "dashboard"):
            self.assertIn(name, p.stdout)
        data = json.loads(run("presets", "--json").stdout)
        self.assertEqual([d["name"] for d in data], ["classic", "dashboard", "minimal"])
        self.assertTrue(all(d["lines"] for d in data))


class ValidateCommand(unittest.TestCase):
    def test_clean_file(self):
        path = tmp_toml('preset = "minimal"\n[segment.context]\ntokens = false\n')
        try:
            p = run("validate", path)
            self.assertEqual(p.returncode, 0, p.stdout)
            self.assertIn("ok: preset minimal, 1 line(s)", p.stdout)
        finally:
            os.unlink(path)

    def test_errors_exit_one_and_name_the_path(self):
        path = tmp_toml('[[line]]\nleft = ["model", "gti"]\n[segment.dir]\ndept = 2\n[nonsense]\nx = 1\n')
        try:
            p = run("validate", path)
            self.assertEqual(p.returncode, 1)
            self.assertIn("line.gti: unknown segment 'gti' (did you mean 'git'?)", p.stdout)
            self.assertIn("segment.dir.dept: unknown option", p.stdout)
            self.assertIn("nonsense: unknown section", p.stdout)
            data = json.loads(run("validate", path, "--json").stdout)
            self.assertFalse(data["ok"])
            self.assertTrue(any(pr["path"] == "line.gti" for pr in data["problems"]))
        finally:
            os.unlink(path)

    def test_legacy_features_are_warnings_only(self):
        path = tmp_toml("[features]\npace = false\n")
        try:
            p = run("validate", path)
            self.assertEqual(p.returncode, 0)
            self.assertIn("features.pace: no longer read", p.stdout)
        finally:
            os.unlink(path)

    def test_bad_toml(self):
        path = tmp_toml("this is not [toml")
        try:
            p = run("validate", path)
            self.assertEqual(p.returncode, 1)
            self.assertIn("not valid TOML", p.stdout)
        finally:
            os.unlink(path)

    def test_example_config_validates(self):
        p = run("validate", os.path.join(ROOT, "statusline.example.toml"))
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertNotIn("warning", p.stdout)


class PreviewCommand(unittest.TestCase):
    def test_widths_and_notes(self):
        p = run("preview", "--width", "60,200", "--plain", "--sample", "hot")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("60 columns, 55 usable", p.stdout)
        self.assertIn("200 columns, 195 usable", p.stdout)
        self.assertIn("↳ line", p.stdout)          # the narrow one degrades
        self.assertNotIn("\033[", p.stdout)

    def test_json_shape_and_budget(self):
        data = json.loads(run("preview", "--width", "80,120", "--json", "--preset", "dashboard").stdout)
        self.assertEqual(data["preset"], "dashboard")
        self.assertEqual([w["columns"] for w in data["widths"]], [80, 120])
        for w in data["widths"]:
            for ln in w["lines"]:
                if ln is not None:
                    self.assertLessEqual(ln["width"], w["usable"])
                    self.assertIn(ln["level"], ("full", "less", "lean", "narrow", "text"))
                    self.assertEqual(ln["overflow"], 0)

    def test_config_file_drives_preview(self):
        path = tmp_toml('[[line]]\nleft = ["model"]\nright = ["greeting"]\n'
                        '[segment.greeting]\ntype = "text"\ntext = "howdy"\n')
        try:
            p = run("preview", "--config", path, "--width", "100", "--plain")
            self.assertIn("howdy", p.stdout)
            self.assertNotIn("ctx", p.stdout)
        finally:
            os.unlink(path)

    def test_samples_resolve_relative_reset_times(self):
        p = run("preview", "--width", "200", "--plain", "--sample", "busy")
        self.assertIn("↻1h43m", p.stdout)

    def test_unknown_sample(self):
        self.assertEqual(run("preview", "--sample", "nope").returncode, 2)


class RenderCommand(unittest.TestCase):
    def test_sample_render(self):
        p = run("render", "--sample", "quiet", "--width", "120")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("Sonnet 5", p.stdout)

    def test_stdin_render_with_width(self):
        p = run("render", "--width", "100", stdin='{"model": {"display_name": "X"}}')
        self.assertIn("X", p.stdout)

    def test_legacy_flags_still_work(self):
        for flag in ("--version", "--doctor", "--ruler", "--dump-config", "--demo", "--help"):
            p = run(flag)
            self.assertEqual(p.returncode, 0, f"{flag}: {p.stderr}")
            self.assertTrue(p.stdout.strip(), flag)

    def test_unknown_command(self):
        self.assertEqual(run("frobnicate").returncode, 2)

    def test_doctor_reports_layout(self):
        p = run("doctor")
        self.assertIn("preset          classic", p.stdout)
        self.assertIn("layout          clean", p.stdout)

    def test_dump_config_roundtrips(self):
        import tomllib
        cfg = tomllib.loads(run("dump-config").stdout)
        self.assertEqual(cfg["preset"], "classic")
        self.assertIn("bar", cfg)


class MigrateCommand(unittest.TestCase):
    OLD = {
        "features": {"pace": False, "reset_clock": True, "last_commit_nudge_min": 30,
                     "context_size": False, "heartbeat": False, "model_window": False,
                     "heartbeat_period": 2.0, "mystery": 1},
        "bar": {"width": 16},
    }

    def test_mapping(self):
        new, changes = migrate_config(self.OLD)
        self.assertNotIn("features", new)
        self.assertEqual(new["bar"], {"width": 16})
        self.assertFalse(new["segment"]["limit_5h"]["pace"])
        self.assertFalse(new["segment"]["limit_7d"]["pace"])
        self.assertEqual(new["segment"]["git"]["nudge_min"], 30)
        self.assertFalse(new["segment"]["context"]["size"])
        self.assertNotIn("heartbeat", new["segment"], "options for a removed segment must go too")
        self.assertNotIn("clock", new["segment"].get("limit_5h", {}), "default value must not be written")
        names = [n for ln in new["line"] for n in ln.get("left", []) + ln.get("right", [])]
        self.assertNotIn("heartbeat", names)
        self.assertNotIn("limit_7d_model", names)
        self.assertIn("context", names)
        self.assertTrue(any("mystery" in c for c in changes))

    def test_output_is_valid_and_clean(self):
        import tomllib
        new, _ = migrate_config(self.OLD)
        text = to_toml(new)
        path = tmp_toml(text)
        try:
            tomllib.loads(text)
            p = run("validate", path)
            self.assertEqual(p.returncode, 0, p.stdout)
            self.assertNotIn("warning", p.stdout)
        finally:
            os.unlink(path)

    def test_write_backs_up(self):
        path = tmp_toml("[features]\npace = false\n")
        try:
            p = run("migrate", path, "--write")
            self.assertEqual(p.returncode, 0, p.stdout)
            backups = [f for f in os.listdir(os.path.dirname(path))
                       if f.startswith(os.path.basename(path) + ".bak-")]
            self.assertTrue(backups)
            with open(path) as fh:
                self.assertIn("[segment.limit_5h]", fh.read())
            for b in backups:
                os.unlink(os.path.join(os.path.dirname(path), b))
        finally:
            os.unlink(path)

    def test_current_file_needs_nothing(self):
        path = tmp_toml('preset = "classic"\n')
        try:
            self.assertIn("already current", run("migrate", path).stdout)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
