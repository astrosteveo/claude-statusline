# Backlog

Roughly ordered; each item is independently mergeable.

- [ ] Capture golden output for every fixture at every test width from the current single file; add a test that asserts against them.
- [ ] Split `statusline.py` into the `statusline/` package (config, width, colour, bar, git, payload, fit, segments, cli) with `statusline.py` as a thin entry. Goldens must still pass byte for byte.
- [ ] Define the segment protocol: name, documented fields, option schema with defaults, default priority, `candidates(ctx) -> list[str]` richest to cheapest.
- [ ] Port every existing piece of the bar to a catalog segment; add `text` and `clock`.
- [ ] Implement the unified fit algorithm and the left/right line assembler; delete `assemble_line1`, `assemble_line2` and `_levels`.
- [ ] Layout schema: parse `[[line]]` and `[segment.<name>]`, validate against the catalog, produce line-precise errors.
- [ ] Format strings: `{field}` and `[color]…[/]`, required-field rule, whitespace collapse.
- [ ] Default layout as `presets/classic.toml`; goldens pass through the new path. Add `minimal` and `dashboard`.
- [ ] Width invariant test over every preset × fixture × width.
- [ ] Subcommands: `render`, `segments`, `validate`, `preview`, `doctor`, `ruler`, `dump-config`, with old `--flag` aliases.
- [ ] `migrate`: map `[features]` keys onto segment options, rewrite the file with a backup, report what changed. `doctor` lists legacy keys.
- [ ] `install.sh`: copy the package directory in `--copy` mode; tests updated.
- [ ] Plugin manifest; `statusline-design` skill with `SKILL.md` and reference files (schema, catalog, host constraints, worked examples). Every example validates in the test suite.
- [ ] README rewrite around the engine: schema, catalog, presets, the skill, migration notes.
