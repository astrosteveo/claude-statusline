"""Game mode's settings menu, worked by clicking links in the bar.

Claude Code sends the status line no clicks, but kitty opens a link you
ctrl+shift+click (a plain click when Claude Code is not holding the mouse).
`statusline.py clicks enable` makes this tool the opener of
claude-statusline:// links, so a click runs `statusline.py click <link>`. That
changes a setting or the menu's page, and the next refresh (a second later)
draws the result.

    claude-statusline://<session>/open          the gear: open the menu
    claude-statusline://<session>/close
    claude-statusline://<session>/page/<n>      a page of the menu, or of a list
    claude-statusline://<session>/step/<item>/up|down
    claude-statusline://<session>/pick/<item>   every choice of a setting at once
    claude-statusline://<session>/set/<item>/<value>
    claude-statusline://<session>/back
    claude-statusline://<session>/rerun/ask/<cache>/<run>   the CI panel: rerun a failed run?
    claude-statusline://<session>/rerun/yes/<token>/-       ... yes (the token the panel shows)
    claude-statusline://<session>/rerun/no/-/-

Anything printed in the terminal can carry such a link, so `handle` trusts
none of it: it knows a fixed set of verbs, settings and values, and never
runs what a link says. The menu's state is a small file per session, so it
opens only where you clicked. With no file (the usual case) the bar pays one
failed open per refresh.
"""
from __future__ import annotations

import os
import time

from .text import BOLD, UNDERLINE, Text
from .util import num

SCHEME = "claude-statusline"
DESKTOP = "claude-statusline-click.desktop"
IDLE = 300.0                 # seconds without a click before the menu closes itself
GAP = 3                      # columns between the menu's cells
GEAR = {"nerd": "", "unicode": "⚙", "emoji": "⚙", "none": "≡"}
HINT = "ctrl+shift+click to change"

# id, label, config key, kind. Leaving game mode is not here: the gear would go with it.
ITEMS = (
    ("layout", "Layout", "preset", "choice"),
    ("theme", "Theme", "theme", "choice"),
    ("style", "Style", "style", "choice"),
    ("icons", "Icons", "icons", "choice"),
    ("bars", "Bars", "bar.style", "choice"),
    ("rows", "Rows", "quest.game_rows", "int"),
    ("picture", "Picture", "quest.avatar", "choice"),
    ("news", "News", "quest.game_news", "choice"),
    ("party", "Party", "quest.party", "bool"),
    ("seasons", "Seasons", "quest.seasons", "bool"),
    ("popups", "Pop-ups", "quest.notify", "bool"),
)
ITEM = {i[0]: i for i in ITEMS}
TABS = ("quests", "bag", "shop", "hero", "settings")
TAB_LABEL = {"quests": "Quests", "bag": "Bag", "shop": "Shop", "hero": "Hero", "settings": "Settings"}
# What a game tab's buttons do (quest/pages.py). They spend gold and items, so their links carry the
# open menu's token: a link printed by anything else in the terminal cannot act.
ACTIONS = ("reroll", "buy", "use", "wear", "sell", "spares", "forge", "title", "confirm", "cancel")
PICKERS = ("layout", "theme", "style", "icons", "bars")      # long enough to list on a page of their own
ROWS = (1, 8)


def choices(item):
    if item == "layout":
        from .layout import list_presets
        return list_presets()
    if item == "theme":
        from .themes import THEMES
        return list(THEMES)
    if item == "style":
        from .config import STYLES
        return list(STYLES)
    if item == "icons":
        from .config import ICONSETS
        return list(ICONSETS)
    if item == "bars":
        from .bar import STYLES
        return list(STYLES)
    if item == "picture":
        return ["auto", "on", "off"]
    if item == "news":
        return ["auto", "off"]
    return []


def current(comp, item):
    """The setting's value in a compiled config."""
    quest = comp.get("quest") or {}
    if item == "layout":
        return comp.get("preset")
    if item == "bars":
        return (comp.get("bar") or {}).get("style")
    if item == "rows":
        return quest.get("game_rows")
    if item == "picture":
        v = quest.get("avatar", "auto")
        return {True: "on", False: "off"}.get(v, v) if isinstance(v, bool) else v
    if item in ("party", "seasons"):
        return quest.get(item) is not False
    if item == "popups":
        return quest.get("notify") is not False
    if item == "news":
        v = quest.get("game_news", "auto")
        return v if v in ("auto", "off") else "auto"
    return comp.get(item)


def _word(s, extra="-_"):
    return isinstance(s, str) and 0 < len(s) <= 64 and s.isascii() and all(c.isalnum() or c in extra for c in s)


def session_of(data):
    """The payload's session id, if it is safe to put in a file name and a link."""
    sid = data.get("session_id") if isinstance(data, dict) else None
    return sid if _word(sid, "-") else None


def link(sid, *parts):
    return f"{SCHEME}://{sid}/" + "/".join(parts)


def desktop_path():
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "applications", DESKTOP)


def installed():
    return os.path.exists(desktop_path())


def state_path(sid):
    from .config import runtime_dir
    return os.path.join(runtime_dir(), f"menu-{sid}.json")


def _load(sid, now):
    """The session's open menu, or None. A menu left idle is closed here, from its file's age,
    before anything is parsed, so a forgotten one costs nothing on later refreshes."""
    path = state_path(sid)
    try:
        with open(path, "rb") as fh:
            if time.time() - os.fstat(fh.fileno()).st_mtime > IDLE:
                raise TimeoutError
            raw = fh.read()
    except TimeoutError:
        try:
            os.unlink(path)
        except OSError:
            pass
        return None
    except OSError:
        return None
    from .fastjson import loads
    try:
        st = loads(raw)
    except ValueError:
        return None
    if not isinstance(st, dict) or now - num(st.get("at"), 0) > IDLE:
        return None
    return st


def read_state(ctx):
    """The open menu's state for this session, or None. Sample payloads may carry their own (`_menu`)."""
    fake = ctx.data.get("_menu")
    if isinstance(fake, dict):
        return fake
    if not ctx.live:
        return None
    sid = session_of(ctx.data)
    return _load(sid, ctx.now) if sid else None


def state(ctx):
    return ctx.memo(("menu",), lambda: read_state(ctx))


def view_path(sid):
    from .config import runtime_dir
    return os.path.join(runtime_dir(), f"view-{sid}.json")


def _read_views(sid):
    try:
        with open(view_path(sid), "rb") as fh:
            raw = fh.read()
        from .fastjson import loads
        v = loads(raw)
    except (OSError, ValueError):
        return {}
    return {k: n for k, n in v.items() if isinstance(n, int)} if isinstance(v, dict) else {}


def views(ctx):
    """{slot: clicks so far} for this session's cycle slots and panel pages. Samples may carry `_view`."""
    def get():
        fake = ctx.data.get("_view")
        if isinstance(fake, dict):
            return fake
        sid = session_of(ctx.data) if ctx.live else None
        return _read_views(sid) if sid else {}
    return ctx.memo(("views",), get)


def cycle_link(ctx, slot):
    """The link a click on `slot` follows, or None where a click could not work."""
    def get():
        if isinstance(ctx.data.get("_view"), dict):
            return session_of(ctx.data) or "sample"
        sid = session_of(ctx.data) if ctx.live else None
        return sid if sid and installed() else None
    sid = ctx.memo(("clicksid",), get)
    return link(sid, "cycle", slot) if sid else None


def focus_link(ctx, key, verb="focus"):
    """The link that brings a fleet session's window forward, or None where a click could not work."""
    sid = None
    if not _word(key, "-_"):
        return None
    if isinstance(ctx.data.get("_view"), dict):
        sid = session_of(ctx.data) or "sample"
    elif ctx.live:
        sid = session_of(ctx.data)
        sid = sid if sid and installed() else None
    return link(sid, verb, key) if sid else None


def attach_link(ctx, bg_id):
    """The link that opens a background session in a new kitty tab, or None where a click could not work."""
    return focus_link(ctx, bg_id, "attach")


def gear(ctx):
    """(glyph, link, menu open?) for the gear on game mode's top row, or None where a click could not work."""
    if not ctx.live or ctx.quest_cfg.get("placement") != "game":
        return None
    sid = session_of(ctx.data)
    if not sid or not installed():
        return None
    st = state(ctx)
    return GEAR.get(ctx.iconset, "⚙"), link(sid, "close" if st else "open"), st is not None


# ---- drawing ------------------------------------------------------------------------------

def _t(ctx, text, role, url=None, bold=False, underline=False):
    attrs = (BOLD if bold else 0) | (UNDERLINE if underline else 0)
    return Text([(text, (ctx.color(role), None, attrs, url))]) if text else Text()


def _pad(t, w):
    return t.add(" " * (w - t.width)) if t.width < w else t


def _control(ctx, sid, item, comp, label_w):
    """One setting: its label, then ‹ value › (or − n +, or ● on). The arrows sit as far apart
    as the setting's longest choice needs, so they stay put while you step through it."""
    id_, label, _, kind = ITEM[item]
    cur = current(comp, item)
    t = _t(ctx, label.ljust(label_w) + "  ", "subtext")
    if kind == "bool":
        t.extend(_t(ctx, "● on" if cur else "○ off", "green" if cur else "muted", link(sid, "step", id_, "up"),
                    bold=bool(cur)))
    elif kind == "int":
        lo, hi = ROWS
        n = int(num(cur, lo))
        t.extend(_t(ctx, "−", "accent" if n > lo else "subtle", link(sid, "step", id_, "down") if n > lo else None))
        t.extend(_t(ctx, f" {n} ", "text", bold=True))
        t.extend(_t(ctx, "+", "accent" if n < hi else "subtle", link(sid, "step", id_, "up") if n < hi else None))
    else:
        value = str(cur) if cur is not None else "?"
        value_w = max([len(c) for c in choices(item)] + [len(value)])
        t.extend(_t(ctx, "‹ ", "accent", link(sid, "step", id_, "down")))
        t.extend(_t(ctx, value, "text", link(sid, "pick" if id_ in PICKERS else "step", id_,
                                             *(() if id_ in PICKERS else ("up",))), bold=True,
                    underline=id_ in PICKERS))           # underlined: it opens the list of every choice
        t.add(" " * max(0, value_w - len(value)))
        t.extend(_t(ctx, " ›", "accent", link(sid, "step", id_, "up")))
    return t


def _pages(cells, cell_w, width, nrows):
    """The cells in pages of rows. A page that is not full spreads evenly over the rows it needs."""
    cols = max(1, (width + GAP) // (cell_w + GAP))
    per = cols * max(1, nrows)
    out = []
    for i in range(0, max(1, len(cells)), per):
        page = cells[i:i + per]
        if not page:
            out.append([])
            continue
        need = -(-len(page) // cols)
        across = -(-len(page) // need)
        out.append([page[j:j + across] for j in range(0, len(page), across)])
    return out


def _row(cells, cell_w, width):
    t = Text()
    for i, c in enumerate(cells):
        if i:
            t.add(" " * GAP)
        t.extend(_pad(c.clip(cell_w), cell_w) if i < len(cells) - 1 else c.clip(cell_w))
    return t.clip(width)


def _pager(ctx, sid, page, pages):
    if pages <= 1:
        return Text()
    t = _t(ctx, "‹", "accent" if page > 0 else "subtle", link(sid, "page", str(page - 1)) if page > 0 else None)
    t.extend(_t(ctx, f" {page + 1}/{pages} ", "subtext"))
    t.extend(_t(ctx, "›", "accent" if page < pages - 1 else "subtle",
                link(sid, "page", str(page + 1)) if page < pages - 1 else None))
    return t


def _join(left, right, width, middle=None):
    """`left`, then `middle`, then `right` against the right edge, all within `width`."""
    t = left.copy()
    if middle:
        t.add(" " * GAP).extend(middle)
    pad = width - t.width - right.width
    if pad < 1:
        return Text(t.spans + [(" ", (None, None, 0, None))] + right.spans).clip(width)
    return Text(t.spans + [(" " * pad, (None, None, 0, None))] + right.spans)


def _tab_of(st):
    return st.get("tab") if st.get("tab") in TABS else TABS[0]


def _page_of(st, tab):
    if tab == "settings" and st.get("pick") in PICKERS:
        return int(num(st.get("ppage"), 0))
    pages = st.get("pages") if isinstance(st.get("pages"), dict) else {}
    return int(num(pages.get(tab), 0))


def _settings_cells(ctx, sid, st):
    comp = ctx.comp
    pick = st.get("pick") if st.get("pick") in PICKERS else None
    if pick:
        cur = current(comp, pick)
        names = choices(pick)
        cells = [_t(ctx, ("● " if n == cur else "  ") + n, "accent" if n == cur else "text",
                    link(sid, "set", pick, n), bold=n == cur) for n in names]
        return cells, 2 + max(len(n) for n in names), f"pick a {ITEM[pick][1].lower()}"
    label_w = max(len(i[1]) for i in ITEMS)
    cells = [_control(ctx, sid, i[0], comp, label_w) for i in ITEMS]
    return cells, max(c.width for c in cells), HINT


def rows(ctx, width, count, st):
    """The menu as `count` Texts at most `width` cells wide: the tabs, then the tab's cells in a
    grid, with pages when they do not fit."""
    sid = session_of(ctx.data) or "preview"
    tab = _tab_of(st)
    token = st.get("token") if _word(st.get("token")) else "none"
    pick = tab == "settings" and st.get("pick") in PICKERS
    if tab == "settings":
        cells, cell_w, hint = _settings_cells(ctx, sid, st)
    else:
        from .quest import pages as game_pages
        cells, cell_w = game_pages.cells(ctx, tab, lambda action, arg: link(sid, "do", token, action, arg), width)
        hint = game_pages.HINT[tab]
    note = st.get("note") if ctx.now - num(st.get("note_at"), 0) < 90 else None
    confirm = st.get("confirm") if tab == "bag" and isinstance(st.get("confirm"), str) else None
    close = _t(ctx, "✕ close", "subtext", link(sid, "close"))
    back = _t(ctx, "‹ back", "subtext", link(sid, "back")) if pick else Text()
    glyph = GEAR.get(ctx.iconset, "⚙")
    page = _page_of(st, tab)

    def right(pager):
        t = Text()
        for part in (pager, back, close):
            if part:
                if t:
                    t.add(" " * GAP)
                t.extend(part)
        return t

    def confirm_row():
        from .quest.pages import confirm_text
        action, _, arg = confirm.partition("-")
        t = _t(ctx, confirm_text(confirm) + " ", "gold", bold=True)
        t.extend(_t(ctx, "[yes]", "green", link(sid, "do", token, action, arg or "all"), bold=True))
        t.add(" ").extend(_t(ctx, "[no]", "subtext", link(sid, "do", token, "cancel", "x")))
        return t.clip(width)

    if count == 1:              # one row: ‹ tab ›, as many cells as fit, then the pager and the close
        i = TABS.index(tab)
        left = _t(ctx, glyph + " ", "accent", bold=True)
        left.extend(_t(ctx, "‹", "accent", link(sid, "tab", TABS[i - 1])))
        left.extend(_t(ctx, f" {TAB_LABEL[tab]} ", "accent", bold=True))
        left.extend(_t(ctx, "›", "accent", link(sid, "tab", TABS[(i + 1) % len(TABS)])))
        if confirm:
            return [_join(left, right(Text()), width, confirm_row())]
        reserve = right(_t(ctx, "‹ 9/9 ›", "text")).width
        mid = max(1, width - left.width - reserve - 2 * GAP)
        pages = _pages(cells, cell_w, mid, 1)
        page = max(0, min(page, len(pages) - 1))
        middle = _row(pages[page][0], cell_w, mid) if pages[page] else Text()
        return [_join(left, right(_pager(ctx, sid, page, len(pages))), width, middle)]
    head = _t(ctx, glyph, "accent", bold=True)
    for name in TABS:
        head.add("  ")
        head.extend(Text([(TAB_LABEL[name], (ctx.color("accent" if name == tab else "subtext"), None,
                                             (BOLD | UNDERLINE) if name == tab else 0, link(sid, "tab", name)))]))
    body = count - 1 - (1 if confirm else 0)
    pages = _pages(cells, cell_w, width, max(1, body))
    page = max(0, min(page, len(pages) - 1))
    tail = right(_pager(ctx, sid, page, len(pages)))
    extra = _t(ctx, note, "text") if note else _t(ctx, hint, "muted")
    room = width - head.width - GAP - 1 - tail.width
    if room >= 12:
        head = head.add(" " * GAP).extend(extra.clip(room))
    out = [_join(head, tail, width)]
    if confirm:
        out.append(confirm_row())
    if body > 0:
        out += [_row(r, cell_w, width) for r in pages[page]]
    while len(out) < count:
        out.append(Text.of(" "))            # kept as a blank row, so the bar keeps its height
    return out[:count]


# ---- clicks -------------------------------------------------------------------------------

class _Lock:
    """Two quick clicks start two handlers; the second waits for the first."""

    def __enter__(self):
        from .config import runtime_dir
        self.fh = open(os.path.join(runtime_dir(), "menu.lock"), "w")
        try:
            import fcntl
            fcntl.flock(self.fh, fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        return self

    def __exit__(self, *exc):
        self.fh.close()


def _save(sid, st):
    import json
    path = state_path(sid)
    tmp = f"{path}.{os.getpid()}"
    with open(tmp, "w") as fh:
        json.dump(st, fh)
    os.replace(tmp, path)


def _change(item, verb, arg):
    """Write one setting; returns what it is now."""
    from . import tomlw
    from .config import compiled, write_path
    _, _, key, kind = ITEM[item]
    cur = current(compiled(), item)
    if verb == "set":
        if arg not in choices(item):
            raise ValueError(f"{arg!r} is not a choice for {item}")
        new = arg
    elif arg not in ("up", "down"):
        raise ValueError("step takes up or down")
    elif kind == "bool":
        new = not cur
    elif kind == "int":
        lo, hi = ROWS
        new = max(lo, min(hi, int(num(cur, lo)) + (1 if arg == "up" else -1)))
    else:
        options = choices(item)
        i = options.index(cur) if cur in options else -1
        new = options[(i + (1 if arg == "up" else -1)) % len(options)]
    if new == cur:
        return new
    if item == "layout":            # a preset brings its own settings, which yours must not hide
        from .cli import apply_preset
        apply_preset(new)
        return new
    path = write_path()
    _, text, _ = tomlw.edit(path, key, new)
    tomlw.write(path, text)
    return new


def parse(url):
    """(session, verb, args) of a link the menu accepts; ValueError for any other."""
    from urllib.parse import urlsplit
    try:
        u = urlsplit(url)
    except ValueError:
        raise ValueError("not a link") from None
    if u.scheme != SCHEME or u.query or u.fragment:
        raise ValueError("not a claude-statusline link")
    sid = u.netloc
    if not _word(sid, "-"):
        raise ValueError("bad session id")
    parts = [p for p in u.path.split("/") if p]
    if not parts or len(parts) > 4 or not all(_word(p) for p in parts):
        raise ValueError("bad path")
    verb, args = parts[0], parts[1:]
    shape = {"open": 0, "close": 0, "back": 0, "page": 1, "pick": 1, "step": 2, "set": 2, "tab": 1, "do": 3,
             "cycle": 1, "rerun": 3, "focus": 1, "attach": 1}
    if shape.get(verb) != len(args):
        raise ValueError(f"unknown action {verb!r}")
    if verb in ("pick", "step", "set") and args[0] not in ITEM:
        raise ValueError(f"unknown setting {args[0]!r}")
    if verb == "pick" and args[0] not in PICKERS:
        raise ValueError(f"{args[0]} has no list")
    if verb == "page" and not (args[0].isdigit() and int(args[0]) < 1000):
        raise ValueError("bad page")
    if verb == "tab" and args[0] not in TABS:
        raise ValueError(f"unknown tab {args[0]!r}")
    if verb == "do" and args[1] not in ACTIONS:
        raise ValueError(f"unknown action {args[1]!r}")
    if verb == "rerun" and args[0] not in ("ask", "yes", "no"):
        raise ValueError(f"unknown step {args[0]!r}")
    return sid, verb, args


def _note(st, text, now):
    st["note"], st["note_at"] = text, now


def _do(st, token, action, arg, now):
    """A game tab's button. Returns pop-ups to deliver once the locks are let go."""
    if st.get("token") != token:
        raise ValueError("that button belongs to a menu that is no longer open")
    if action == "confirm":
        if arg != "spares" and not (arg.startswith("forge-") and arg[6:] in ("common", "uncommon", "rare", "epic")):
            raise ValueError("nothing to confirm")
        st["confirm"] = arg
        return []
    if action == "cancel":
        st.pop("confirm", None)
        return []
    if action in ("spares", "forge"):
        want = "spares" if action == "spares" else f"forge-{arg}"
        if st.pop("confirm", None) != want:
            raise ValueError("press the button first, then yes")
    from .quest.game import GameError
    from .quest.pages import act
    try:
        msgs, toasts = act(action, arg, now)
    except GameError as exc:
        _note(st, f"✋ {exc}", now)
        return []
    _note(st, (msgs[-1].split("\n")[0] if msgs else "Done."), now)
    return toasts


def handle(url, now=None):
    """Carry out one click. Returns what it did; raises ValueError for a link it does not accept."""
    sid, verb, args = parse(url)
    now = time.time() if now is None else now
    toasts = []
    if verb == "cycle":                 # a cycle slot or a panel's page: this session's view, never the menu
        import json
        with _Lock():
            v = _read_views(sid)
            v[args[0]] = v.get(args[0], 0) + 1
            path = view_path(sid)
            tmp = f"{path}.{os.getpid()}"
            with open(tmp, "w") as fh:
                json.dump(v, fh)
            os.replace(tmp, path)
        return f"moved {args[0]} on"
    if verb == "focus":                 # a session on the fleet map: agentboard brings its window forward
        from .fleet import focus
        return focus(args[0])
    if verb == "attach":                # a background session on the fleet map: `claude attach` in a new kitty tab
        from .fleet import attach
        return attach(args[0])
    if verb == "rerun":                 # the CI panel's rerun button: two clicks, see ci.py
        from .ci import rerun_click
        with _Lock():
            return rerun_click(sid, args, now)
    with _Lock():
        if verb == "close":
            try:
                os.unlink(state_path(sid))
            except OSError:
                pass
            return "closed the menu"
        st = _load(sid, now)
        if verb == "do" and st is None:
            raise ValueError("the menu is closed")
        if verb == "open" or st is None:
            import secrets
            st = {"tab": (st or {}).get("tab", TABS[0]), "token": secrets.token_hex(8)}
        did = "opened the menu"
        if verb == "tab":
            st["tab"] = args[0]
            for k in ("pick", "confirm"):
                st.pop(k, None)
            did = f"the {args[0]} tab"
        elif verb == "page":
            if st.get("pick") and _tab_of(st) == "settings":
                st["ppage"] = int(args[0])
            else:
                st.setdefault("pages", {})[_tab_of(st)] = int(args[0])
            did = f"page {int(args[0]) + 1}"
        elif verb == "pick":
            st["tab"], st["pick"], st["ppage"] = "settings", args[0], 0
            did = f"listed every {args[0]}"
        elif verb == "back":
            st.pop("pick", None)
            did = "back to the settings"
        elif verb in ("step", "set"):
            did = f"{ITEM[args[0]][2]} = {_change(args[0], verb, args[1])}"
            st.pop("pick", None)
        elif verb == "do":
            toasts = _do(st, args[0], args[1], args[2], now)
            did = st.get("note") if st.get("note_at") == now else f"{args[1]} {args[2]}"
        st["at"] = now
        _save(sid, st)
    if toasts:
        from .quest.hooks import deliver
        deliver(toasts)
    return did


def _log(line):
    from .config import runtime_dir
    path = os.path.join(runtime_dir(), "clicks.log")
    try:
        if os.path.getsize(path) > 20000:
            os.replace(path, path + ".1")
    except OSError:
        pass
    try:
        with open(path, "a") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} {line}\n")
    except OSError:
        pass


def click(url) -> int:
    """`statusline.py click <link>`: what the desktop's link opener runs."""
    try:
        did = handle(url)
    except Exception as exc:
        _log(f"{url} refused: {exc}")
        print(f"refused: {exc}")
        return 1
    _log(f"{url} {did}")
    print(did)
    return 0


# ---- the link opener ----------------------------------------------------------------------

def _quote(arg):
    """An Exec argument, quoted the way desktop entries want."""
    if arg and not any(c in arg for c in ' \t"\'\\><~|&;$*?#()`'):
        return arg
    return '"' + "".join("\\" + c if c in '"`$\\' else c for c in arg) + '"'


def _mimeapps():
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "mimeapps.list")


def _refresh(folder, log):
    """Tell the desktop about the change; KDE reads its own cache, not the folder."""
    import shutil
    import subprocess
    for cmd in (["update-desktop-database", folder], ["kbuildsycoca6"], ["kbuildsycoca5"]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
            except (OSError, subprocess.SubprocessError):
                log(f"  {cmd[0]} failed; log out and in if clicks do nothing")
            if cmd[0].startswith("kbuildsycoca"):
                break


def enable(entry=None, log=print) -> int:
    import shutil
    import subprocess
    import sys
    if sys.platform == "darwin" or os.name != "posix":
        log("  clicks need a Linux desktop (xdg-open); this system has none")
        return 1
    if not shutil.which("xdg-mime"):
        log("  xdg-mime not found: install xdg-utils, then run this again")
        return 1
    if entry is None:
        from .settings import ENTRY
        entry = ENTRY if os.path.exists(ENTRY) else os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "statusline.py")
    entry = os.path.abspath(os.path.expanduser(entry))
    python = shutil.which("python3") or "python3"
    path = desktop_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write("[Desktop Entry]\n"
                 "Type=Application\n"
                 "Name=claude-statusline clicks\n"
                 "Comment=Opens claude-statusline:// links, the buttons of game mode's settings menu\n"
                 f"Exec={_quote(python)} -S {_quote(entry)} click %u\n"
                 "NoDisplay=true\n"
                 f"MimeType=x-scheme-handler/{SCHEME};\n")
    log(f"  wrote {path}")
    try:
        subprocess.run(["xdg-mime", "default", DESKTOP, f"x-scheme-handler/{SCHEME}"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=True)
    except (OSError, subprocess.SubprocessError):
        log(f"  xdg-mime could not register it; add x-scheme-handler/{SCHEME}={DESKTOP} to {_mimeapps()}")
        return 1
    log(f"  registered it for {SCHEME}:// links")
    _refresh(os.path.dirname(path), log)
    log("  game mode's top row now ends in a gear: ctrl+shift+click it in kitty to open the settings menu")
    return 0


def disable(log=print) -> int:
    path = desktop_path()
    try:
        os.unlink(path)
        log(f"  removed {path}")
    except FileNotFoundError:
        log("  no link opener was registered")
    mime = _mimeapps()
    try:
        with open(mime) as fh:
            lines = fh.read().split("\n")
        kept = [ln for ln in lines if not ln.startswith(f"x-scheme-handler/{SCHEME}=")]
        if len(kept) != len(lines):
            from . import tomlw
            tomlw.write(mime, "\n".join(kept).rstrip("\n"))
            log(f"  removed {SCHEME}:// from {mime}")
    except OSError:
        pass
    _refresh(os.path.dirname(path), log)
    return 0


def status(log=print) -> int:
    path = desktop_path()
    if not os.path.exists(path):
        log("  clicks       off (statusline.py clicks enable)")
        return 0
    exec_line = ""
    try:
        with open(path) as fh:
            exec_line = next((ln[5:] for ln in fh.read().split("\n") if ln.startswith("Exec=")), "")
    except OSError:
        pass
    log(f"  clicks       on: {SCHEME}:// links run {exec_line}")
    return 0


def main(argv) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "enable":
        entry = None
        if "--entry" in argv:
            i = argv.index("--entry")
            if i + 1 >= len(argv):
                print("usage: statusline.py clicks enable [--entry PATH]")
                return 2
            entry = argv[i + 1]
        return enable(entry)
    fn = {"disable": disable, "status": status}.get(cmd)
    if fn is None:
        print("usage: statusline.py clicks enable [--entry PATH] | disable | status")
        return 2
    return fn()
