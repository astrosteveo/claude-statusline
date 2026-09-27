# Build claude-statusline 4

You're building version 4.0.0 of claude-statusline, the project in this repository. The work has three parts:

1. Session details in game mode's top row. Users asked for this, and the spec is in section 1.
2. Improvements to the engine and to Claude Quest that you choose. The aim is the best status line available for Claude Code.
3. A trailer that shows version 4.

## Context

claude-statusline draws the status line under Claude Code's conversation. Claude Code runs it once a second in every session and pipes it a JSON payload, and whatever it prints is the bar. It has 19 themes, 8 styles, an interactive configurator (`statusline.py configure`), and Claude Quest, an RPG driven by Claude Code's hooks. It's Python 3.11+ with the standard library only. pycairo draws the kitty pictures.

People keep this bar on screen in every Claude Code session, all day, so speed and reliability come before features.

Read these before changing anything:

- `docs/plan.md`: the version 3 design, its decisions, and the ideas it rejected.
- `skills/design/reference/constraints.md`: what Claude Code allows, the refresh budget, and how widths are measured.
- `README.md`, then the code named below.

State of `main` on 2026-09-26 (measure it again):

- 163 tests pass in about 10 seconds with `python3 -m unittest discover -s tests`. `make test` adds the installer tests.
- `statusline.py bench` reports a median of about 10 ms a refresh. Python startup is 4 ms of that.
- The user runs Claude Code's fullscreen TUI in kitty, with the midnight theme and JetBrainsMono Nerd Font. Their config is `~/.config/claude-statusline/config.toml`, with Quest in game mode.

This checkout is live. `~/.claude/statusline.py` imports it on every refresh, and the Quest hooks in `~/.claude/settings.json` run it on every tool call, yours included. A half-edited file here breaks every Claude Code session on the machine, so do all work in a separate worktree (see "How to work").

## 1. Session details in game mode's top row

Users call game mode (`[quest] placement = "game"`) the full-screen mode, and they like it. They want its top row to show the model, and as many other session details as fit, without truncating or displacing the game sections. Game sections are the quest segments on that row. Session details are every other segment.

What happens now:

- In game mode, `compile_config` in `claude_statusline/layout.py` replaces the configured lines with `GAME_TICKER` and the scene rows. The user's own lines disappear, and with them the model, directory, git, and cost.
- `_game_lines` in `claude_statusline/render.py` fits the top row with `fit_line` from `claude_statusline/fit.py`. It steps every segment down a detail level together, then drops the lowest-priority one. Session details added to that row unchanged would take detail away from game sections, so the fitting has to change.
- On 2026-09-26, with the user's config and save at 220 columns, the row had 73 blank columns while the news section (`quest_event`) stopped at its fixed 48-character cap: "Loot! 🪵 Walking Stick of Stack Traces (comm…". At 80 columns the streak dropped.

Build it so that:

- Game sections get the room they need first. At a given width, they render identically with and without session details on the row. Test this across widths from 40 to 300 columns, every style and icon set, the quiet, busy, and hot samples, and Quest states with a boss, a raid, a dungeon, buffs, and fresh news.
- Game text such as the news uses the room the row has before any session detail gets it. A fixed cap applies only when the row is short of space.
- The model comes first. After it, by default, come the segments from the user's own lines (or their preset) in order, skipping what the scene's gauges already show. A config key lets users set the list.
- Session details give up detail first (for example full, then short, then icon only), then drop, lowest priority first. Nothing overlaps or clips.
- At 220 columns, with a copy of the user's config, the busy sample, and no news on the row, the row shows at least the model with effort, the directory, git, the PR, and the cost.
- `configure`, `validate`, `doctor`, and `preview` understand the new behavior. `preview` notes say what gave way at each width.

Where the details sit in the row and how they're grouped is your call, as long as the row reads as one line and the game sections stay easy to find. If the columns beside the scene rows (`game_hud`) can hold more on wide terminals, extend them too.

## 2. The engine and Claude Quest

You choose this part's scope. Pick the improvements that would matter most to people who keep this bar open all day, then build them to the standard of version 3. A few finished features are worth more than many half-done ones. Each feature you ship has tests, is documented in the README and the skill's reference files, has its settings in the configurator, and appears in the trailer if it's visible on the bar. Leave the rest of the code as it is unless a feature you chose needs the change.

Ideas for the engine (none required):

- Read Claude Code's current status line and hooks documentation, and use the payload fields and hook events added since version 3.
- Show live activity, such as the tool running now, subagents at work, and progress through the todo list. Hooks could write it to a small runtime file that a refresh reads with one call. That would let the engine use hooks without Quest.
- Lines that change with the terminal width. `constraints.md` lists this as not possible. That was a design choice. The host sends the width on every refresh.
- A per-project config layered over the user's.
- Sparklines of context, spend, and rate-limit use over the session, from a small history kept in the runtime directory.
- A theme built from the terminal's own colors (kitty, Ghostty, WezTerm, Alacritty).
- A `demo` command that plays a scripted session in the terminal. The trailer can reuse it.
- Features users request from other Claude Code status line projects. Read their READMEs and issues, and don't copy their code.

Ideas for Claude Quest (none required):

- Respond to more of what Claude Code does, such as subagents joining the scene as party members, context compaction, plan mode, permission prompts, and long waits for the user.
- Seasonal and rare events. Halloween is five weeks away.
- More animation and detail in the game-mode scene, including the text scene for terminals without kitty, the boss's health and the dungeon's depth drawn in the scene, and smoother kitty animation.
- Progression past level 50, pet bonds and forms, more gear sets and bosses, and XP that follows real work more than the count of tool calls.
- A full-screen `claude-quest` interface for the bag, shop, and forge, built on the configurator's terminal code in `claude_statusline/tui`.

Keep these properties:

- `statusline.py bench` stays within 1 ms of the median you measure at the start. The refresh path imports none of `json`, `re`, `tomllib`, or `subprocess`.
- The bar is never blank and never wider than its budget. Widths are measured the way Claude Code measures them.
- The standard library only, plus pycairo for kitty pictures.
- Version 2 and 3 configs still render, and Quest saves from every version load. A breaking change is fine when it makes a real improvement, `migrate` handles it, and the README says so.
- New visuals use theme roles, never raw color codes, so every theme recolors them.
- `docs/plan.md` rejects user-authored segments because a command would run on every refresh. Revisit that only with a design that keeps commands off the refresh path (the background cache that git uses), limits how long they run, and has an off switch.
- Item flavor text, boss names, and the pet keep the playful voice they have now. Menus, help, settings, and errors stay plain, like the current README and CLI help.

## 3. The trailer

When version 4 is built, make a trailer for it.

- Make it 60 to 90 seconds long, 1920×1080 at 60 fps, encoded as H.264 (yuv420p) with AAC audio. Also make a 10 to 15 second looping GIF of game mode for the README, under 8 MB.
- Everything on screen comes from the real engine, so the trailer shows the actual product and can be rebuilt when the product changes. Status lines come from `render()` fed scripted payloads and Quest states, drawn the way `tools/shot.py` draws ANSI. Kitty pictures come from the code in `claude_statusline/quest/art`, placed where kitty would show them (`shot.py` doesn't draw kitty placeholders). Don't use mockups. Use current model names in the scripted payloads.
- `make trailer` rebuilds both files from source. Keep the source in the repo, write the MP4 to a gitignored `dist/`, and commit the GIF.
- Show the bar in context, under a plain terminal conversation. Don't copy Claude Code's interface in detail or use Anthropic or Claude logos.
- Captions are short, plain, and in sentence case, and they say what's on screen, as in "Failing tests summon a boss. Fix them to win." No taglines.
- Compose an original chiptune score in code, cut on the beat, and normalize to about −14 LUFS. Don't use downloaded or copyrighted audio. The trailer has to make sense muted. If the VoiceStudio skill works on this machine, you can add a short voiceover.
- Use the product's own themes, midnight first, and its font. Terminal text has to be readable at full screen on a laptop.
- Leave out macOS window buttons, typewriter reveals, glitch and chromatic-aberration transitions, CRT scanlines, neon purple-to-cyan gradients, synthwave grids, lens flares, slow zooms over still screenshots, numbered "01 / 02 / 03" cards, italic accent words in titles, and confetti other than the game's own.

A possible sequence. Reorder or replace beats to show what version 4 ships.

1. The bar appears in a Claude Code session.
2. The window narrows from 220 to 60 columns. The bar gives up detail and never clips.
3. Themes and styles change on the beat.
4. The configurator changes the bar live.
5. Game mode. The pet works while tools run, failing tests summon a boss, a fix wins the fight, then loot and a level-up, a PR dungeon, and the tech-debt raid.
6. The new top row fills with the model, git, and cost beside the game.
7. 10 ms a refresh.
8. The install command.

To check it, pull a still from each beat with ffmpeg and look at each one. Fix anything hard to read, badly timed, or wrongly captioned, and render again.

## How to work

- Check that the main checkout is clean. If `git status` shows changes other than `docs/v4-prompt.md`, stop and ask the user to commit them. Then run `git worktree add ../claude-statusline-v4 -b v4` and work only in that worktree.
- Measure the baseline there: the tests, `make lint`, and `statusline.py bench`.
- Write `docs/v4.md` in the shape of `docs/plan.md` (Problem, What 4 is, Key decisions, Rejected). Include the improvements you chose and what done means for each. Commit it before any code.
- Do section 1 first, then section 2, then the trailer.
- Commit each finished piece on `v4`, with messages in the style of the existing log. Don't push, merge into `main`, tag, or publish anything.
- Keep a `NOTES.md` in the worktree and list it in `.git/info/exclude` of the main checkout. It holds the plan as a checklist, your decisions, and the next step. Update it after each commit. If your context is compacted, read it before anything else.
- For experiments, point `CLAUDE_STATUSLINE_CONFIG`, `CLAUDE_QUEST_HOME`, and `XDG_RUNTIME_DIR` at scratch paths, so nothing you run shares a config, save, or cache with the live bar. Don't write to `~/.claude/quest`, `~/.claude/settings.json`, `~/.claude/statusline.py`, or `~/.config/claude-statusline`. To test save migration, copy `~/.claude/quest/state.json` into a scratch Quest home.
- Look at what you build. Render the bar to PNG with `tools/shot.py` and view it. Check game mode at 80, 120, 160, and 220 columns, and each theme and style your changes affect. `statusline.py preview --sample live` uses the last payload your own session sent.
- Write tests the way the suite does, with property sweeps over widths, styles, icon sets, and payloads for the engine, and unit tests for game rules. Keep the suite fast (about 10 seconds now), and keep scratch checks out of the repo.
- Use subagents for broad read-only research, such as documentation and other projects, and for tracks that touch different files, each in its own worktree. Run at most three at a time, and review their results yourself.
- When you start a milestone, say in one line what it is.

The user isn't watching and can't answer questions mid-task, so asking "Shall I...?" stops the work. Go ahead with reversible steps that follow from this brief. Stop only for destructive or outward-facing actions (pushing, publishing, writing outside the worktree and your scratch directories) or for a scope change the user has to decide. Don't stop or trim the work because the session is long. Context is compacted automatically, and `NOTES.md` records where you are. Before you end a turn, read your last paragraph. If it's a plan or a promise about work you haven't done, do the work now. If something can't be done, finish everything else and say what's missing and why.

Report only what a tool result in this session shows. If tests fail, say so and include the output. If you skipped a step, say so.

## Done

- The top row meets section 1, and the game-section test passes.
- Each improvement in `docs/v4.md` is shipped and meets its own definition of done.
- `make test` and `make lint` pass, and `statusline.py bench` is within 1 ms of the baseline.
- `README.md`, `docs/v4.md`, `statusline.example.toml`, and `skills/design/reference/*.md` are current. `make catalog` has regenerated the catalog, and `make gallery` has redrawn `docs/gallery.png`.
- The version is 4.0.0 in `claude_statusline/__init__.py` and `.claude-plugin/*.json`.
- The trailer MP4 is in `dist/`, the GIF is committed and shown in the README, and `make trailer` rebuilds both.
- The code-review skill has reviewed the `v4` branch at high effort, and you've fixed the findings it confirmed.
- Everything is committed on `v4`, and `main` is unchanged.

## Your last message

Write it for someone who didn't watch you work. Start with the outcome, then cover:

- what shipped, one line each
- what you left out, and why
- where the trailer is
- how to make version 4 the live bar (merge `v4` into `main` in `~/Projects/claude-statusline`), and how to go back
- anything that needs the user's decision
