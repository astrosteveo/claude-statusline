"""Build the version 4 trailer and the README's game-mode GIF from the product itself.

    python3 tools/trailer                    # dist/trailer.mp4 and docs/game-mode.gif (make trailer)
    python3 tools/trailer --stills DIR       # one PNG a second, for checking
    python3 tools/trailer --only mp4|gif

Every status line on screen comes from render() fed the scripted sessions in
claude_statusline/demo.py; the configurator is the real one, drawn from its
own rows; the game-mode picture is composited from the frames the kitty
uploader draws (quest/art/scene.py), where kitty would place them. Needs
pycairo, ffmpeg and gifski.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BUILD = os.path.join(ROOT, "dist", "trailer-build")
os.makedirs(BUILD, exist_ok=True)
os.environ["XDG_CACHE_HOME"] = os.path.join(BUILD, "cache")          # the scene frames: kept apart from yours
os.environ["XDG_RUNTIME_DIR"] = os.path.join(BUILD, "runtime")
os.environ["CLAUDE_QUEST_HOME"] = os.path.join(BUILD, "quest")
os.environ["QUEST_SEASON"] = "none"
os.makedirs(os.environ["XDG_RUNTIME_DIR"], exist_ok=True)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import cairo  # noqa: E402

import canvas  # noqa: E402
import kitty  # noqa: E402
import music  # noqa: E402
from claude_statusline import demo, gamemode  # noqa: E402
from claude_statusline.render import scene_geometry  # noqa: E402
from claude_statusline.text import BOLD, Text  # noqa: E402
from claude_statusline.themes import palette  # noqa: E402

W, H, FPS = 1920, 1080, 60
GRID = canvas.Grid(24)
COLS, ROWS = 130, 24
WIDE = canvas.Grid(18)                   # the top-row shot needs a wider terminal
WIDE_COLS = 160
PAD = 14
WIN_X, WIN_Y = 48, 44
BACK = (0.055, 0.063, 0.098)
TERM_BG = (22 / 255, 26 / 255, 38 / 255)            # the midnight theme's background, as in kitty
BORDER = (0.2, 0.23, 0.33)
CAPTION = (0.88, 0.9, 0.97)
MUTED = (0.5, 0.55, 0.7)
MIDNIGHT = palette("midnight", {})


class Shot:
    """What is on screen at one moment."""

    def __init__(self, cols, talk, bar, caption, ctx=None, game=None, note="", extra=None, title="", grid=None):
        self.cols, self.talk, self.bar, self.caption, self.ctx = cols, talk, bar, caption, ctx
        self.game, self.note, self.extra, self.title = game, note, extra, title
        self.grid = grid or GRID


# --- the shots -------------------------------------------------------------------------------------
def from_demo(frame, cols=None, caption=None, limit=COLS):
    frame.cols = min(cols or frame.cols, limit)
    lines, ctx = demo.bar(frame)
    game = None
    if ctx.quest_cfg.get("enabled") and ctx.quest_cfg.get("placement") == "game":
        game = game_picture(frame, ctx)
    return Shot(frame.cols, demo.talk_lines(frame, ctx.pal), lines, caption or frame.caption, ctx, game, frame.note)


def game_picture(frame, ctx):
    """Where kitty would put the scene's picture, and what it would show."""
    from claude_statusline.segments.quest import load_state, view_of
    width, hud_w, _ = scene_geometry(ctx, ctx.comp["lines"])
    rows = sum(1 for ln in ctx.comp["lines"] if ln.get("scene") is not None)
    state = load_state(ctx) or {}
    view = view_of(state)
    project = ctx.cwd.rstrip("/").rsplit("/", 1)[-1]
    boss, raid, dungeon = gamemode.props(view, project)
    season, goblin = gamemode.extras(view, ctx.now)
    return {"width": width, "cols": max(gamemode.STEP, width // gamemode.STEP * gamemode.STEP), "rows": rows,
            "situation": gamemode.situation(state, ctx.now, boss or raid), "boss": boss, "raid": raid,
            "dungeon": dungeon, "party": gamemode.party_of(view), "season": season, "goblin": goblin,
            "tod": gamemode.time_of_day(ctx.now)}


def scene_at(name, t):
    return next(s for s in demo.SCENES if s.name == name).build(t)


def shot_intro(t):
    return from_demo(scene_at("session", 0.5 + t * 0.9), COLS)


def shot_narrow(t):
    f = scene_at("narrow", 0.0)
    cols = int(COLS - (COLS - 60) * min(1.0, max(0.0, t - 0.5) / 5.5))
    f.note = f"{cols} columns"
    return from_demo(f, cols)


def shot_looks(t):
    theme, style = demo.LOOKS[min(len(demo.LOOKS) - 1, int(t))]
    f = scene_at("looks", 0)
    f.raw = {"theme": theme, "style": style, "icons": "nerd", "preset": "classic"}
    f.note = f"{theme} · {style}"
    return from_demo(f, COLS)


def shot_game(t):
    # the music's work, boss, victory and level-up sections, then the dungeon: 4, 6, 4, 4 and 6 seconds
    if t < 4:
        dt = t
    elif t < 10:
        dt = 4 + (t - 4) * 4.9 / 6
    elif t < 14:
        dt = 9 + (t - 10)
    elif t < 18:
        dt = 13 + (t - 14)
    else:
        dt = 17 + (t - 18) * 3.9 / 6
    return from_demo(scene_at("game", dt), COLS)


def shot_top_row(t):
    f = scene_at("top row", 0.5)
    f.raw = dict(f.raw, quest=dict(f.raw["quest"], game_details=["model", "git", "cost"]),
                 segment={"quest_daily": {"weekly": False}, "quest": {"width": 6}})
    f.data["pr"] = {"number": 214, "review_state": "approved"}
    cols = int(WIDE_COLS - (WIDE_COLS - 104) * min(1.0, max(0.0, t - 3.0) / 4.0))
    f.note = f"{cols} columns"
    shot = from_demo(f, cols, "New in 4: the model, git and cost share the game's top row, and give way first.",
                     limit=WIDE_COLS)
    shot.grid = WIDE
    return shot


def shot_party(t):
    return from_demo(scene_at("party", min(5.9, t * 1.1)), COLS)


def shot_harvest(t):
    os.environ["QUEST_SEASON"] = "halloween"
    try:
        return from_demo(scene_at("harvest", min(6.9, t * 1.1)), COLS)
    finally:
        os.environ["QUEST_SEASON"] = "none"


def shot_live(t):
    return from_demo(scene_at("live", t), COLS)


_APP = {}


def shot_config(t):
    """The real configurator, changing the bar as keys arrive on the beat."""
    from claude_statusline.tui.app import App
    from claude_statusline.tui.term import Key
    if "app" not in _APP:
        path = os.path.join(BUILD, "configure.toml")
        with open(path, "w") as fh:
            fh.write('theme = "midnight"\nstyle = "capsules"\nicons = "nerd"\npreset = "classic"\n')
        payload = os.path.join(BUILD, "payload.json")
        with open(payload, "w") as fh:
            json.dump(demo.payload(__import__('time').time()), fh)     # the configurator reads the real clock
        os.environ["CLAUDE_STATUSLINE_CONFIG"] = path
        app = App(path)
        app.sample = payload
        _APP.update(app=app, done=0)
    app = _APP["app"]
    script = [(1.0, "down"), (2.0, "down"), (3.0, "right"), (3.5, "down"), (4.0, "down"), (5.0, "tab")]
    while _APP["done"] < len(script) and script[_APP["done"]][0] <= t:
        k = script[_APP["done"]][1]
        app.on_key(Key(k, k if len(k) == 1 else ""))
        _APP["done"] += 1
    rows = app.draw(COLS, ROWS)
    return Shot(COLS, [], [], "The configurator changes the bar as you move.", None, None, extra=rows)


BENCH = {}


def shot_bench(t):
    if not BENCH:
        env = dict(os.environ, CLAUDE_STATUSLINE_CONFIG=os.path.join(BUILD, "none.toml"),
                   XDG_RUNTIME_DIR=os.path.join(BUILD, "bench"))
        os.makedirs(env["XDG_RUNTIME_DIR"], exist_ok=True)
        out = subprocess.run([sys.executable, os.path.join(ROOT, "statusline.py"), "bench"], capture_output=True,
                             text=True, env=env).stdout
        BENCH["lines"] = out.rstrip("\n").split("\n")
        nums = [float(line.split("median")[1].split("ms")[0]) for line in BENCH["lines"] if "median" in line]
        BENCH["median"], BENCH["startup"] = nums[0], nums[-1]
    pal = MIDNIGHT
    rows = [Text().add("$ ", (pal["accent"], None, BOLD, None)).add("python3 statusline.py bench", (pal["text"], None, 0, None)),
            Text()]
    shown = min(len(BENCH["lines"]), int(t * 2) + 1)
    rows += [Text().add(line, (pal["subtext"], None, 0, None)) for line in BENCH["lines"][:shown]]
    cap = (f"A refresh takes about {BENCH['median']:.0f} ms, {BENCH['startup']:.0f} of them Python starting up.")
    return Shot(COLS, rows, [], cap)


def shot_outro(t):
    pal = MIDNIGHT
    rows = [Text().add("$ ", (pal["accent"], None, BOLD, None)).add(
        "git clone https://github.com/astrosteveo/claude-statusline ~/Projects/claude-statusline",
        (pal["text"], None, 0, None)), Text(),
        Text().add("$ ", (pal["accent"], None, BOLD, None)).add("cd ~/Projects/claude-statusline && ./install.sh --quest",
                                                                (pal["text"], None, 0, None))]
    return Shot(COLS, rows, [], "Install it with one script. It backs up whatever it replaces.",
                title="claude-statusline 4")


SHOTS = [("intro", shot_intro), ("narrow", shot_narrow), ("looks", shot_looks), ("config", shot_config),
         ("work", shot_game), ("toprow", shot_top_row), ("party", shot_party), ("harvest", shot_harvest),
         ("live", shot_live), ("bench", shot_bench), ("outro", shot_outro)]
GAME_SECTIONS = ("work", "boss", "victory", "levelup", "dungeon")


def timeline():
    """[(start, end, builder)] on the music's sections."""
    starts = music.section_starts()
    order = [name for name, *_ in music.SONG]
    end = sum(bars * 4 for _, bars, *_ in music.SONG) * music.BEAT
    out = []
    for i, (name, fn) in enumerate(SHOTS):
        start = starts[name]
        nxt = SHOTS[i + 1][0] if i + 1 < len(SHOTS) else None
        stop = starts[nxt] if nxt else end
        out.append((start, stop, fn))
    assert [n for n in order if n not in GAME_SECTIONS[1:]] == [n for n, _ in SHOTS]
    return out, end


# --- drawing a frame ----------------------------------------------------------------------------------
_CAPTIONS = {}


def draw(cr, shot, t_global):
    g = shot.grid
    cv = CANVASES.setdefault(g.size, canvas.Canvas(g, fg=(0.78, 0.83, 0.96)))
    rows_n = int((ROWS * GRID.ch) // g.ch)
    cr.set_source_rgb(*BACK)
    cr.paint()
    ww = shot.cols * g.cw + 2 * PAD
    wh = ROWS * GRID.ch + 2 * PAD + 30
    canvas.rounded(cr, WIN_X, WIN_Y, ww, wh, 12)
    cr.set_source_rgb(*TERM_BG)
    cr.fill_preserve()
    cr.set_source_rgb(*BORDER)
    cr.set_line_width(1.5)
    cr.stroke()
    title = shot.title or "~/Projects/widget-factory — claude"
    canvas.label(cr, title, WIN_X + ww / 2, WIN_Y + 22, 15, MUTED, center=True)
    x0, y0 = WIN_X + PAD, WIN_Y + PAD + 30
    rows = shot.extra if shot.extra is not None else None
    if rows is None:
        body = list(shot.talk)
        room = rows_n - len(shot.bar)
        body = body[:room] + [Text()] * max(0, room - len(body))
        rows = [r.clip(shot.cols) for r in body] + list(shot.bar)
    scene_rows = set()
    if shot.game:
        top = rows_n - len(shot.bar)
        scene_rows = {top + 1 + i for i in range(shot.game["rows"])}
    for i, row in enumerate(rows[:rows_n]):
        surf = cv.row(row, shot.cols)
        y = y0 + i * g.ch
        if i in scene_rows:                   # the picture's cells: kitty draws the image there, not text
            cr.save()
            cr.rectangle(x0 + shot.game["width"] * g.cw, y, (shot.cols - shot.game["width"]) * g.cw + 1, g.ch)
            cr.clip()
            cr.set_source_surface(surf, x0, y)
            cr.paint()
            cr.restore()
        else:
            cr.set_source_surface(surf, x0, y)
            cr.paint()
    if shot.game:
        gm = shot.game
        pic = kitty.picture(gm["situation"], int(gm["cols"] * g.cw), int(gm["rows"] * g.ch), t_global,
                            gm["tod"], gm["boss"], gm["raid"], gm["dungeon"], gm["party"], gm["season"], gm["goblin"],
                            kitty.HARVEST if gm["season"] == "halloween" else kitty.LOOK)
        cr.set_source_surface(pic, x0, y0 + (min(scene_rows)) * g.ch)
        cr.paint()
    if shot.note:
        canvas.label(cr, shot.note, WIN_X + ww - 14, WIN_Y + 22, 15, MUTED)
    cap = _CAPTIONS.get(shot.caption)
    if cap is None:
        cap = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, 90)
        c2 = cairo.Context(cap)
        canvas.label(c2, shot.caption, W / 2, 58, 38, CAPTION, cairo.FONT_WEIGHT_NORMAL, center=True)
        _CAPTIONS[shot.caption] = cap
    cr.set_source_surface(cap, 0, H - 106)
    cr.paint()


CANVASES = {}


def frame_at(t, plan):
    for start, stop, fn in plan:
        if start <= t < stop:
            return fn(t - start)
    return plan[-1][2](plan[-1][1] - plan[-1][0] - 0.001)


# --- output ----------------------------------------------------------------------------------------------
def stills(folder, plan, end, every=1.0):
    os.makedirs(folder, exist_ok=True)
    t = 0.25
    while t < end:
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        draw(cairo.Context(surf), frame_at(t, plan), t)
        surf.write_to_png(os.path.join(folder, f"{t:05.2f}.png"))
        t += every
    print(folder)


def video(path, plan, end):
    wav = os.path.join(BUILD, "score.wav")
    norm = os.path.join(BUILD, "score-14lufs.wav")
    music.render(wav)
    measured = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", wav, "-af",
                               "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                              capture_output=True, text=True).stderr
    m = json.loads(measured[measured.rindex("{"):measured.rindex("}") + 1])
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", wav, "-af",
                    f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                    f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
                    f"linear=true", "-ar", "48000", norm], check=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    enc = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", norm, "-c:v", "libx264",
                            "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                            "-shortest", "-movflags", "+faststart", path], stdin=subprocess.PIPE)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(surf)
    n = int(end * FPS)
    for i in range(n):
        t = i / FPS
        draw(cr, frame_at(t, plan), t)
        surf.flush()
        enc.stdin.write(bytes(surf.get_data()))
        if i % (FPS * 5) == 0:
            print(f"  {t:5.1f}s / {end:.0f}s", file=sys.stderr)
    enc.stdin.close()
    if enc.wait():
        raise SystemExit("ffmpeg failed")
    print(path)


def gif(path, seconds=12.0, fps=15):
    """Game mode's bar, cropped: the work, the boss, the win, the loot."""
    folder = tempfile.mkdtemp(prefix="gif-", dir=BUILD)
    starts = music.section_starts()
    plan = [(0.0, seconds, lambda t: shot_game(min(17.9, t * 18 / seconds)))]
    g = GRID
    bar_rows = 5                         # the ticker and four rows of scene
    crop_h = bar_rows * g.ch + PAD
    y_top = WIN_Y + PAD + 30 + (ROWS - bar_rows) * g.ch - 4
    for i in range(int(seconds * fps)):
        t = i / fps
        full = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        draw(cairo.Context(full), frame_at(t, plan), starts["work"] + t)
        out = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(COLS * g.cw + 2 * PAD), int(crop_h))
        c = cairo.Context(out)
        c.set_source_surface(full, -WIN_X, -y_top)
        c.paint()
        out.write_to_png(os.path.join(folder, f"{i:04d}.png"))
    frames = sorted(os.path.join(folder, f) for f in os.listdir(folder))
    subprocess.run(["gifski", "--quiet", "--fps", str(fps), "--width", "1200", "--quality", "80", "-o", path] + frames,
                   check=True)
    shutil.rmtree(folder, ignore_errors=True)
    print(path, f"{os.path.getsize(path) / 1e6:.1f} MB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills")
    ap.add_argument("--only", choices=("mp4", "gif"))
    ap.add_argument("--out", default=os.path.join(ROOT, "dist", "trailer.mp4"))
    ap.add_argument("--gif", default=os.path.join(ROOT, "docs", "game-mode.gif"))
    a = ap.parse_args()
    plan, end = timeline()
    if a.stills:
        stills(a.stills, plan, end)
        return 0
    if a.only != "gif":
        video(a.out, plan, end)
    if a.only != "mp4":
        gif(a.gif)
    return 0


if __name__ == "__main__":
    sys.exit(main())
