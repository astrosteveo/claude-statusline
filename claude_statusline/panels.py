"""The git panels: a block of rows under the bar with the changed files, the
commit graph, the branches and the stashes side by side.

    [panels]
    show = ["files", "graph", ["branches", "ci", "servers", "stash"]]
    rows = 6

Left to right, and a list stacks its panels in one column. The last columns
give way first.

The block keeps its height whatever the repository holds, so the
conversation above it never jumps: a panel with less to say is padded, and
a clean tree says so. The columns follow the terminal's width; a panel that
no longer fits its smallest width drops, the last named first. A rebase,
merge or other operation in progress heads the changes panel. The stash, CI and servers
panels show only while they have something to say; in a stack, each takes
the rows it needs and the last takes what is left.
"""
from __future__ import annotations

import os

from .text import BOLD, Text
from .width import char_width, width as cells

# name -> (smallest width, share of the spare columns)
PANELS = {"files": (26, 3), "graph": (34, 4), "branches": (24, 2), "stash": (24, 2), "ci": (24, 2),
          "servers": (22, 2), "checks": (26, 2), "sessions": (24, 2), "reviews": (26, 2),
          "fleet": (40, 6)}
TITLES = {"files": "Changes", "graph": "History", "branches": "Branches", "stash": "Stash", "ci": "CI",
          "servers": "Servers", "checks": "Checks", "sessions": "Sessions",
          "reviews": "Reviews", "fleet": "Fleet"}
SEP = " │ "
CLAUDE = "✻"                   # marks a file Claude edited this session
PAD = (None, None, 0, None)


def members(col):
    """The panels in one column of `show`: a name, or a list of names stacked."""
    return [n for n in ([col] if isinstance(col, str) else col) if n in PANELS]


def _size(col):
    """(smallest width, share of the spare columns) of a column: its widest panel's."""
    return tuple(max(PANELS[n][i] for n in members(col)) for i in (0, 1))


def columns(avail, cols):
    """[(column, width)] for the columns of `show` that fit `avail` columns, in order."""
    cols = [c for c in cols if members(c)]
    if not cols:
        return []
    while len(cols) > 1 and sum(_size(c)[0] for c in cols) + len(SEP) * (len(cols) - 1) > avail:
        cols.pop()
    if len(cols) == 1:
        return [(cols[0], avail)]
    spare = avail - sum(_size(c)[0] for c in cols) - len(SEP) * (len(cols) - 1)
    weight = sum(_size(c)[1] for c in cols)
    out, given = [], 0
    for i, c in enumerate(cols):
        extra = spare - given if i == len(cols) - 1 else spare * _size(c)[1] // weight
        given += extra
        out.append((c, _size(c)[0] + extra))
    return out


def panel_data(ctx):
    def get():
        fake = ctx.data.get("_panels")
        if isinstance(fake, dict):                 # sample payloads carry their own repository, aged "-3h"
            from .samples import _relative
            when = lambda v: _relative(v, ctx.now) if isinstance(v, str) else v
            return dict(fake, graph=[r[:3] + [when(r[3])] + r[4:] for r in fake.get("graph") or []],
                        branches=[r[:4] + [when(r[4])] + r[5:] for r in fake.get("branches") or []],
                        stashes=[[r[0], when(r[1])] + r[2:] for r in fake.get("stashes") or []],
                        ci=dict(fake["ci"], runs=[r[:6] + [when(r[6]), when(r[7])] + r[8:] for r in fake["ci"]["runs"]])
                        if fake.get("ci") else None,
                        servers=[[r[0], r[1], when(r[2])] for r in fake.get("servers") or []],
                        sessions=[[r[0], r[1], when(r[2]), r[3]] for r in fake.get("sessions") or []],
                        reviews=dict(fake["reviews"], asked=[r[:5] + [when(r[5])] + r[6:]
                                                             for r in fake["reviews"]["asked"]])
                        if fake.get("reviews") else None)
        cfg = ctx.comp.get("panels") or {}
        shown = {n for c in cfg.get("show") or [] for n in members(c)}
        fleet = None
        if "fleet" in shown:                       # every session on the machine, so it needs no repository
            from .fleet import data as fleet_data, save_payload
            if ctx.live:                           # agentboard reads it for context windows and limits
                save_payload(ctx.data, ctx.now)
            fleet = fleet_data(sync=ctx.sync_git, spawn=ctx.live)
        d = None
        if ctx.comp["git"].get("enabled", True):
            from .gitpanels import data
            d = data(ctx.cwd, cfg, ctx.comp["git"], sync=ctx.sync_git, spawn=ctx.live)
        if d is None:
            return {"fleet": fleet, "nogit": True} if "fleet" in shown else None
        d["fleet"] = fleet
        if "ci" in shown:
            from .ci import data as ci_data
            d["ci"] = ci_data(d["root"], d["gitdir"], d["common"], cfg, sync=ctx.sync_git, spawn=ctx.live)
        if "servers" in shown:
            from .servers import data as server_data
            d["servers"] = server_data(d["root"], sync=ctx.sync_git, spawn=ctx.live)
        if "reviews" in shown:
            from .reviews import data as review_data
            d["reviews"] = review_data(d["root"], d["gitdir"], sync=ctx.sync_git, spawn=ctx.live)
        if "sessions" in shown:
            from .sessions import others
            d["sessions"] = others(ctx.data.get("session_id"), ctx.now) if ctx.live else []
        return d
    return ctx.memo("panels", get)


def with_activity(ctx, d):
    """The panel data plus what this session's activity knows: the files Claude edited and the
    last test, lint and build runs."""
    from .segments.live import activity
    s = activity(ctx) or {}
    return dict(d, edited=s.get("edited") or {}, checks=s.get("checks") or {})


def _says(d, name):
    """Whether a panel that shows only when it has something to say has it."""
    if name == "fleet":
        return True
    if d.get("nogit"):
        return False
    if name == "stash":
        return bool(d.get("stashes"))
    if name == "ci":
        return bool((d.get("ci") or {}).get("runs"))
    if name == "servers":
        return bool(d.get("servers"))
    if name == "sessions":
        return bool(d.get("sessions"))
    if name == "checks":
        return bool(d.get("checks"))
    if name == "reviews":
        r = d.get("reviews") or {}
        mine = r.get("mine")
        return bool(r.get("asked") or mine and (mine[4] or mine[3] == "CHANGES_REQUESTED"))
    return True


def _stack(ctx, d, names, w, rows):
    """Panels one under another. Each takes the rows it needs when they all fit; otherwise each
    gets two (the last panels give way when even that is too many) and the rest go round them in
    turn to those that want more, which then page."""
    if len(names) == 1:
        return DRAW[names[0]](ctx, d, w, rows)
    full = [DRAW[n](ctx, d, w, rows) for n in names]
    need = [len(f) for f in full]
    if sum(need) <= rows:
        return [line for f in full for line in f]
    names, need = names[:max(1, rows // 2)], need[:max(1, rows // 2)]
    give = [min(2, n) for n in need]
    left = rows - sum(give)
    while left > 0 and any(g < n for g, n in zip(give, need)):
        for i in range(len(give)):
            if left and give[i] < need[i]:
                give[i] += 1
                left -= 1
    out = []
    for name, n in zip(names, give):
        out += DRAW[name](ctx, d, w, n)[:n]
    return out


def block(ctx, rows):
    """`rows` Texts, each at most ctx.avail wide, or None outside a repository."""
    d = panel_data(ctx)
    if d is None:
        return None
    d = with_activity(ctx, d)
    cfg = ctx.comp.get("panels") or {}
    cols = [[n for n in members(c) if not d.get("pending") and _says(d, n) or
             d.get("pending") and n in ("files", "graph", "branches")] for c in cfg.get("show") or []]
    cols = columns(ctx.avail, [c if len(c) > 1 else c[0] for c in cols if c])
    if not cols:
        return None
    drawn = []
    for col, w in cols:
        if d.get("pending") and "fleet" not in members(col):   # the titles at once, so nothing moves when git answers
            lines = [_head(ctx, members(col)[0], w=w)] + \
                ([Text.of("Reading git…", _st(ctx, "muted"))] if not drawn else [])
        else:
            lines = _stack(ctx, d, members(col), w, rows)
        drawn.append([_exact(t, w) for t in (lines + [Text()] * rows)[:rows]])
    sep = Text.of(SEP, _st(ctx, "subtle"))
    out = []
    for r in range(rows):
        t = Text()
        for i, col in enumerate(drawn):
            if i:
                t.extend(sep)
            t.extend(col[r])
        if not t.plain().strip():                   # Claude Code trims a row of spaces away: a blank
            t = Text([("⠀", PAD)])                 # braille cell is not whitespace
        out.append(t)
    return out


# -- drawing helpers ---------------------------------------------------------

def _st(ctx, role, attrs=0, link=None):
    return (ctx.color(role), None, attrs, link)


def _exact(t, w):
    """`t` clipped or padded to exactly `w` cells."""
    t = t.clip(w)
    cut = w
    while t.width > w and cut > 1:                 # a glyph with a variation selector can clip one long
        cut -= 1
        t = t.clip(cut)
    return Text(t.spans + [(" " * (w - t.width), PAD)]) if t.width < w else t


def _row(left, right, w):
    """`left` then `right` against the right edge; `left` gives way first."""
    if not right:
        return left
    room = w - right.width - 1
    if room < 6:
        return left
    left = left.clip(room)
    return Text(left.spans + [(" " * (w - left.width - right.width), PAD)] + right.spans)


def _tail(s, n):
    """The end of `s` in at most `n` cells, starting with … when cut."""
    if cells(s) <= n:
        return s
    out, used = [], 1
    for ch in reversed(s):
        cw = char_width(ch)
        if used + cw > n:
            break
        out.append(ch)
        used += cw
    return "…" + "".join(reversed(out))


_SAFE_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/-_.~"
_SAFE = frozenset(_SAFE_CHARS.encode())
_SAFE_SET = frozenset(_SAFE_CHARS)


def _quote(path):
    """A path for a file:// link, percent-encoded (urllib.parse would cost the bar 1.5 ms to import)."""
    if _SAFE_SET.issuperset(path):
        return path
    return "".join(chr(b) if b in _SAFE else "%%%02X" % b for b in path.encode("utf-8", "surrogateescape"))


def _drop_hash(msg):
    """"main: 1a2b3c4 subject" -> "main: subject": the hash says little."""
    head, sep, rest = msg.partition(": ")
    sha, space, subject = rest.partition(" ")
    if sep and space and " " not in head and len(sha) >= 7 and all(c in "0123456789abcdef" for c in sha):
        return head + sep + subject
    return msg


def age(ctx, ts):
    if not ts:
        return ""
    s = max(0, ctx.now - ts)
    if s < 3600:
        return f"{int(s // 60)}m"
    if s < 86400:
        return f"{int(s // 3600)}h"
    if s < 86400 * 60:
        return f"{int(s // 86400)}d"
    if s < 86400 * 730:
        return f"{int(s // (86400 * 30))}mo"
    return f"{int(s // (86400 * 365))}y"


def _head(ctx, name, count=None, right=None, w=0, extra=None):
    left = Text.of(TITLES[name], _st(ctx, "accent", BOLD))
    if count is not None:
        left.add(f" {count}", _st(ctx, "muted"))
    if extra:
        left.extend(extra)
    return _row(left, right or Text(), w)


def _page(ctx, name, items, rows):
    """The items that fit under a title in `rows` rows, and the row under them when they do not
    all fit: `+7 more`, or with clicks on, the page and a link to the next one."""
    room = max(0, rows - 1)
    if len(items) <= room:
        return items, None
    per = room - 1
    if per < 1:                         # room for the title and one line: say how many there are
        return [], Text.of(f"{len(items)} more", _st(ctx, "muted"))
    from .menu import cycle_link, views
    url = cycle_link(ctx, f"panel-{name}")
    if not url:
        return items[:per], Text.of(f"+{len(items) - per} more", _st(ctx, "muted"))
    pages = -(-len(items) // per)
    page = views(ctx).get(f"panel-{name}", 0) % pages
    return items[page * per:(page + 1) * per], Text.of(f"page {page + 1}/{pages} ›", _st(ctx, "muted", 0, url))


# -- the panels ----------------------------------------------------------------

def _rank(xy):
    if "U" in xy or xy in ("AA", "DD"):
        return 0
    if xy == "??":
        return 3
    return 1 if xy[0] != " " else 2


def _code(ctx, xy):
    if xy == "??":
        return Text.of("??", _st(ctx, "subtext"))
    if "U" in xy or xy in ("AA", "DD"):
        return Text.of(xy, _st(ctx, "red", BOLD))
    t = Text()
    t.add(xy[0], _st(ctx, "red" if xy[0] == "D" else "green"))
    t.add(xy[1], _st(ctx, "red" if xy[1] == "D" else "yellow"))
    return t


def files(ctx, d, w, rows):
    fs = sorted(d.get("files") or [], key=lambda f: (_rank(f[0]), f[1]))
    added = sum(f[2] or 0 for f in fs)
    removed = sum(f[3] or 0 for f in fs)
    total = Text()
    if added:
        total.add(f"+{added}", _st(ctx, "green"))
    if removed:
        total.add((" " if added else "") + f"-{removed}", _st(ctx, "red"))
    edited = d.get("edited") or {}
    root = d.get("root") or ""
    claude = {f[1] for f in fs if os.path.join(root, f[1]) in edited}
    mine = Text.of(f" {CLAUDE}{len(claude)}", _st(ctx, "accent")) if claude else None
    out = [_head(ctx, "files", len(fs) if fs else None, total, w, mine)]
    p = d.get("progress")
    if p:
        out.append(_row(*_progress(ctx, p), w))
    if not fs:
        return out + [Text.of(f"{ctx.mark('ok') or '✓'} clean", _st(ctx, "green"))]
    shown, more = _page(ctx, "files", fs, rows - (1 if p else 0))
    for xy, path, a, r in shown:
        right = Text()
        if xy == "??":
            right.add("new", _st(ctx, "muted"))
        elif a is None and r is None:
            right.add("bin" if xy[1] != "D" and xy[0] != "D" else "", _st(ctx, "muted"))
        else:
            if a:
                right.add(f"+{a}", _st(ctx, "green"))
            if r:
                right.add((" " if a else "") + f"-{r}", _st(ctx, "red"))
        room = w - 3 - (right.width + 1 if right else 0)
        shown_path = _tail(path, max(4, room))
        head, base = os.path.split(shown_path)
        left = _code(ctx, xy).add(CLAUDE if path in claude else " ", _st(ctx, "accent"))
        link = ("file://" + _quote(os.path.join(d["root"], path))) if d.get("root") else None
        if head:
            left.add(head + "/", _st(ctx, "subtext", 0, link))
        left.add(base, _st(ctx, "text", 0, link))
        out.append(_row(left, right, w))
    if more:
        out.append(more)
    return out


def _refs(ctx, refs, local):
    """The refs on a commit, as a Text: HEAD's branch bold, local branches green, the rest muted."""
    t = Text()
    for i, ref in enumerate(r.strip() for r in refs.split(",")):
        if not ref or ref.endswith("/HEAD"):
            continue
        if ref.startswith("HEAD -> "):
            part = (ref[8:], _st(ctx, "green", BOLD))
        elif ref == "HEAD":
            part = ("HEAD", _st(ctx, "cyan", BOLD))
        elif ref.startswith("tag: "):
            part = (ref[5:], _st(ctx, "yellow"))
        elif ref in local:
            part = (ref, _st(ctx, "green"))
        else:
            part = (ref, _st(ctx, "blue"))
        if t:
            t.add(" ", PAD)
        t.add(*part)
    return t


def graph(ctx, d, w, rows):
    from .payload import repo_url
    base = repo_url(ctx.data)
    local = {b[1] for b in d.get("branches") or []}
    out = [_head(ctx, "graph", w=w)]
    commits = d.get("graph") or []
    if not commits:
        return out + [Text.of("no commits yet", _st(ctx, "muted"))]
    for prefix, sha, refs, ct, subject in commits[:max(0, rows - 1)]:
        left = Text()
        lanes = max(4, w // 4)
        if len(prefix) > lanes:                     # many branches side by side: keep room for the commit
            prefix = prefix[:lanes - 1] + "…"
        for ch in prefix:
            left.add(ch, _st(ctx, "accent" if ch == "*" else "subtle"))
        if not sha:
            out.append(left)
            continue
        left.add(sha[:7], _st(ctx, "yellow", 0, f"{base}/commit/{sha}" if base else None))
        tags = _refs(ctx, refs, local)
        if tags:
            left.add(" ", PAD)
            left.extend(tags.clip(max(8, w // 3)))
        left.add(" " + subject, _st(ctx, "text"))
        out.append(_row(left, Text.of(age(ctx, ct), _st(ctx, "muted")), w))
    return out


def _sync(ctx, track):
    t = Text()
    if track == "gone":
        return t.add("gone", _st(ctx, "red"))
    for part in track.split(","):
        word, _, n = part.strip().partition(" ")
        if word == "ahead":
            t.add(f"{ctx.mark('ahead') or '↑'}{n}", _st(ctx, "cyan"))
        elif word == "behind":
            t.add(f"{ctx.mark('behind') or '↓'}{n}", _st(ctx, "orange"))
    return t


def branches(ctx, d, w, rows):
    bs = sorted(d.get("branches") or [], key=lambda b: not b[0])
    out = [_head(ctx, "branches", len(bs), w=w)]
    shown, more = _page(ctx, "branches", bs, rows)
    for current, name, upstream, track, ct, merged in shown:
        left = Text.of("● " if current else "  ", _st(ctx, "accent"))
        left.add(name, _st(ctx, "muted" if merged else "text", BOLD if current else 0))
        right = Text()
        if merged:
            right.add("merged", _st(ctx, "muted"))
        elif not upstream:
            right.add("local", _st(ctx, "muted"))
        else:
            right.extend(_sync(ctx, track))
        if right:
            right.add(" ", PAD)
        right.add(age(ctx, ct), _st(ctx, "muted"))
        out.append(_row(left, right, w))
    if more:
        out.append(more)
    return out


def _progress(ctx, p):
    t = Text.of(p["op"], _st(ctx, "red", BOLD))
    if p.get("branch"):
        t.add(" " + p["branch"], _st(ctx, "text"))
    if p.get("op") in ("rebasing", "applying") and p.get("onto"):
        t.add(" onto " + p["onto"], _st(ctx, "muted"))
    elif p.get("message"):
        t.add(" " + p["message"], _st(ctx, "muted"))
    right = Text.of(f"{p['step']}/{p['total']}", _st(ctx, "yellow")) if p.get("step") and p.get("total") else Text()
    return t, right


def stash(ctx, d, w, rows):
    ss = d.get("stashes") or []
    out = [_head(ctx, "stash", len(ss), w=w)]
    shown, more = _page(ctx, "stash", ss, rows)
    for idx, ct, msg in shown:
        for lead in ("WIP on ", "On "):
            if msg.startswith(lead):
                msg = msg[len(lead):]
                break
        msg = _drop_hash(msg)
        left = Text.of(f"{idx} ", _st(ctx, "muted")).add(msg, _st(ctx, "text"))
        out.append(_row(left, Text.of(age(ctx, ct), _st(ctx, "muted")), w))
    if more:
        out.append(more)
    return out


_MARK = {"success": ("ok", "✓", "green"), "failure": ("fail", "✗", "red"), "timed_out": ("fail", "✗", "red"),
         "startup_failure": ("fail", "✗", "red"), "cancelled": ("", "⊘", "muted"), "skipped": ("", "–", "muted"),
         "neutral": ("", "–", "muted"), "action_required": ("wait", "●", "orange")}


def _run_state(r):
    """(rank, mark, role): failures first, then what is running, then the rest."""
    if r[3] != "completed":
        return 1, "●", "yellow"
    _, glyph, role = _MARK.get(r[4], ("", "?", "muted"))
    return (0 if role == "red" else 2), glyph, role


def ci(ctx, d, w, rows):
    c = d.get("ci") or {}
    runs = sorted(c.get("runs") or [], key=lambda r: _run_state(r)[0])
    tally = {}
    for r in runs:
        _, glyph, role = _run_state(r)
        tally.setdefault((glyph, role), 0)
        tally[(glyph, role)] += 1
    right = Text()
    for (glyph, role), n in sorted(tally.items(), key=lambda kv: ["red", "yellow", "orange"].index(kv[0][1])
                                   if kv[0][1] in ("red", "yellow", "orange") else 3):
        right.add((" " if right else "") + f"{glyph}{n}", _st(ctx, role))
    head = _head(ctx, "ci", w=w) if not c.get("stale") else \
        Text.of("CI", _st(ctx, "accent", BOLD)).add(" stale", _st(ctx, "muted"))
    out = [_row(head, right, w) if right else head]
    shown, more = _page(ctx, "ci", runs, rows)
    rerun = _rerun_links(ctx, d, runs)
    for r in shown:
        _, glyph, role = _run_state(r)
        left = Text.of(glyph + " ", _st(ctx, role)).add(r[1], _st(ctx, "text", 0, r[8] or None))
        if r[3] != "completed":
            when = Text.of(("queued " if r[3] in ("queued", "waiting", "pending") else "") +
                           _clock(ctx.now - r[6]) if r[6] else r[3], _st(ctx, "yellow"))
        else:
            when = Text.of(age(ctx, r[7] or r[6]), _st(ctx, "muted"))
        if r[0] in rerun:
            when = rerun[r[0]].add(" ", PAD).extend(when)
        out.append(_row(left, when, w))
    if more:
        out.append(more)
    return out


def _rerun_links(ctx, d, runs):
    """{run id: Text} for the failed runs a click can rerun: `rerun`, or `rerun? yes no` once asked."""
    from .ci import RERUNNABLE, cache_tag, pending
    from .menu import cycle_link, link, session_of
    failed = [r for r in runs if r[3] == "completed" and r[4] in RERUNNABLE]
    if not failed or not d.get("root") or not cycle_link(ctx, "ci"):
        return {}
    sid = session_of(ctx.data) or "sample"
    asked = ctx.data.get("_rerun") if isinstance(ctx.data.get("_rerun"), dict) else \
        (pending(sid, ctx.now) if ctx.live else None)
    tag = cache_tag(d["root"])
    out = {}
    for r in failed:
        if asked and asked.get("run") == r[0]:
            t = Text.of("rerun?", _st(ctx, "orange", BOLD)).add(" ", PAD)
            t.add("yes", _st(ctx, "green", BOLD, link(sid, "rerun", "yes", str(asked.get("token")), "-")))
            t.add(" ", PAD).add("no", _st(ctx, "muted", 0, link(sid, "rerun", "no", "-", "-")))
        else:
            t = Text.of("↻ rerun", _st(ctx, "subtext", 0, link(sid, "rerun", "ask", tag, str(r[0]))))
        out[r[0]] = t
    return out


def _clock(s):
    """A running timer: 45s, 3m05s, 1h02m."""
    s = max(0, int(s))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{s % 3600 // 60:02d}m"


def servers(ctx, d, w, rows):
    ss = d.get("servers") or []
    out = [_head(ctx, "servers", len(ss), w=w)]
    shown, more = _page(ctx, "servers", ss, rows)
    for port, label, started in shown:
        url = f"http://localhost:{port}"
        left = Text.of(f":{port}", _st(ctx, "cyan", BOLD, url)).add(" " + label, _st(ctx, "text", 0, url))
        out.append(_row(left, Text.of(age(ctx, started), _st(ctx, "muted")), w))
    if more:
        out.append(more)
    return out


KINDS = (("test", "tests"), ("lint", "lint"), ("build", "build"))


def checks(ctx, d, w, rows):
    """The last test, lint and build runs this session: failures first, then each failure by name."""
    cs = d.get("checks") or {}
    runs = sorted(((k, label, cs[k]) for k, label in KINDS if k in cs), key=lambda r: r[2][1])
    bad = sum(1 for r in runs if not r[2][1])
    right = Text.of(f"✗{bad}", _st(ctx, "red")) if bad else Text.of(ctx.mark("ok") or "✓", _st(ctx, "green"))
    out = [_head(ctx, "checks", right=right, w=w)]
    items = []
    for kind, label, (cmd, ok, n, passed, names, at, cwd) in runs:
        left = Text.of((ctx.mark("ok") or "✓") if ok else (ctx.mark("fail") or "✗"), _st(ctx, "green" if ok else "red"))
        left.add(f" {label}", _st(ctx, "text", BOLD))
        if not ok:
            left.add(f" {n} failed", _st(ctx, "red"))
        if passed is not None:
            left.add((" ·" if not ok else "") + f" {passed} passed", _st(ctx, "muted"))
        items.append(_row(left, Text.of(age(ctx, at), _st(ctx, "muted")), w))
        root = d.get("root") or cwd
        for name, path, line in names:
            t = Text.of("  ")
            full = path if os.path.isabs(path) else os.path.join(cwd or root, path) if path else ""
            rel = os.path.relpath(full, root) if full and root and full.startswith(root + "/") else path
            where = Text()
            if rel:
                where.add(_tail(os.path.basename(rel), max(8, w // 3)) + (f":{line}" if line else ""),
                          _st(ctx, "subtext", 0, "file://" + _quote(full)))
            t.add(name, _st(ctx, "text", 0, "file://" + _quote(full) if full else None))
            items.append(_row(t, where, w))
    shown, more = _page(ctx, "checks", items, rows)
    out += shown
    if more:
        out.append(more)
    return out


SESSION = {"ask": ("!", "red", "needs you"), "work": ("●", "accent", ""), "wait": ("○", "muted", "waiting")}


def sessions(ctx, d, w, rows):
    """Your other Claude Code sessions: those that need you, those working, those waiting."""
    ss = d.get("sessions") or []
    asks = sum(1 for r in ss if r[1] == "ask")
    right = Text.of(f"{asks} need{'s' if asks == 1 else ''} you", _st(ctx, "red", BOLD)) if asks else None
    out = [_head(ctx, "sessions", len(ss), right, w)]
    shown, more = _page(ctx, "sessions", ss, rows)
    for project, state, since, what in shown:
        glyph, role, word = SESSION.get(state, SESSION["wait"])
        left = Text.of(glyph + " ", _st(ctx, role, BOLD)).add(project, _st(ctx, "text", BOLD))
        if word and state == "ask":
            left.add(" " + word, _st(ctx, "red"))
        if what:
            left.add(" " + " ".join(what.split()), _st(ctx, "subtext"))
        out.append(_row(left, Text.of(_clock(ctx.now - since), _st(ctx, role if state != "work" else "muted")), w))
    if more:
        out.append(more)
    return out


DECISION = {"CHANGES_REQUESTED": ("changes requested", "red"), "APPROVED": ("approved", "green"),
            "REVIEW_REQUIRED": ("review required", "yellow")}


def reviews(ctx, d, w, rows):
    """This branch's pull request with its open threads, then the pull requests waiting on your review."""
    r = d.get("reviews") or {}
    mine, asked = r.get("mine"), r.get("asked") or []
    right = Text.of(f"{len(asked)} for you", _st(ctx, "yellow", BOLD)) if asked else None
    head = _head(ctx, "reviews", w=w, right=right)
    if r.get("stale"):
        head = _row(Text.of("Reviews", _st(ctx, "accent", BOLD)).add(" stale", _st(ctx, "muted")), right, w)
    out, items = [head], []
    if mine:
        number, title, url, decision, threads = mine
        left = Text.of(f"#{number}", _st(ctx, "cyan", BOLD, url or None))
        word, role = DECISION.get(decision, ("", "muted"))
        if word:
            left.add(" " + word, _st(ctx, role))
        if threads:
            left.add(f" · {len(threads)} open", _st(ctx, "orange"))
        items.append(_row(left, Text.of("this branch", _st(ctx, "muted")), w))
        for path, line, author, body, link, outdated in threads:
            t = Text.of("  ")
            if author:
                t.add(author + " ", _st(ctx, "subtext", BOLD, link or None))
            t.add(body, _st(ctx, "muted" if outdated else "text", 0, link or None))
            where = Text.of(_tail(os.path.basename(path), max(8, w // 3)) + (f":{line}" if line else ""),
                            _st(ctx, "subtext")) if path else Text()
            items.append(_row(t, where, w))
    for repo, number, title, url, author, updated, draft in asked:
        left = Text.of(f"{repo.rsplit('/', 1)[-1]}#{number}", _st(ctx, "yellow", 0, url or None))
        left.add(" " + title, _st(ctx, "muted" if draft else "text", 0, url or None))
        right = Text.of((author + " " if author else "") + age(ctx, updated), _st(ctx, "muted"))
        items.append(_row(left, right, w))
    shown, more = _page(ctx, "reviews", items, rows)
    out += shown
    if more:
        out.append(more)
    return out


FLEET = {"needs": ("!", "red"), "turn": ("◆", "pink"), "working": ("●", "accent"), "settled": ("○", "muted")}
FLEET_ORDER = {"needs": 0, "turn": 1, "working": 2, "settled": 3}
FLEET_COL = 56                  # the narrowest column of systems
SPIN = "◐◓◑◒"                    # a working session turns, one step a second
FLARE = 5.0                     # seconds a tool call's name flashes on its session
SPARK = " ▁▂▃▄▅▆▇█"


def _glyph(ctx, r):
    if r.get("fresh"):
        return "◌", "subtle"
    if r.get("failed"):
        return "✗", "red"
    if r["section"] == "working":
        return SPIN[int(ctx.now) % len(SPIN)], "accent"
    if r["section"] == "needs":                    # pulses while it waits on you
        return "!", "red" if int(ctx.now) % 2 else "orange"
    return FLEET[r["section"]]


def _context(ctx, r):
    """The session's context use in percent: agentboard's, or worked out from this session's
    window when it runs the same model and the tokens fit in it."""
    if r.get("ctx") is not None:
        return r["ctx"]
    cw = ctx.data.get("context_window") or {}
    size = cw.get("context_window_size") if isinstance(cw, dict) else None
    model = (ctx.data.get("model") or {}).get("id") if isinstance(ctx.data.get("model"), dict) else None
    if isinstance(size, int) and size > 0 and model and r.get("model") == model and 0 < r.get("tokens", 0) <= size:
        return r["tokens"] * 100 // size
    return None


def _meter(ctx, pct):
    """`▰▰▱▱ 47%`, coloured by the thresholds."""
    th = ctx.comp.get("thresholds") or {}
    role = "red" if pct >= th.get("red", 90) else "orange" if pct >= th.get("orange", 75) else \
        "yellow" if pct >= th.get("yellow", 50) else "green"
    full = min(4, (pct + 12) // 25)
    return Text.of("▰" * full, _st(ctx, role)).add("▱" * (4 - full), _st(ctx, "subtle")) \
        .add(f" {pct}%", _st(ctx, role)).add(" ")


def _open_link(ctx, f, r):
    """Where a click on a session takes you: its window brought forward, or a background one attached in
    a new kitty tab. A session you can't switch to from here (the desktop app's) has no link."""
    if r.get("window"):
        from .menu import focus_link
        return focus_link(ctx, r["key"])
    if r.get("bg"):
        from .menu import attach_link
        return attach_link(ctx, r["bg"])
    return None


def _system(ctx, f, project, ss, w, own):
    """One project as a star with its sessions in orbit and their agents as moons."""
    worst = min(ss, key=lambda r: FLEET_ORDER[r["section"]])["section"]
    out = [Text.of("★ ", _st(ctx, FLEET[worst][1], BOLD)).add(project, _st(ctx, "text", BOLD))
           .add(f" {sum(r.get('count', 1) for r in ss)}", _st(ctx, "muted"))]
    for i, r in enumerate(ss):
        last = i == len(ss) - 1
        glyph, role = _glyph(ctx, r)
        left = Text.of("└ " if last else "├ ", _st(ctx, "subtle")).add(glyph + " ", _st(ctx, role, BOLD))
        if r.get("fork"):
            left.add("⑂ ", _st(ctx, "muted"))
        left.add(r["title"], _st(ctx, "text", BOLD if r["section"] != "settled" else 0, _open_link(ctx, f, r)))
        if r.get("count", 1) > 1:
            left.add(f" ×{r['count']}", _st(ctx, "muted", BOLD))
        if own and own in (r.get("sids") or [r.get("sid")]):
            left.add(" ◂ here", _st(ctx, "accent", BOLD))
        for flag in r.get("flags") or []:
            left.add(f" ⚠{flag}", _st(ctx, "orange"))
        flare = r.get("flare")
        if flare and r["section"] == "working" and 0 <= ctx.now - flare[0] < FLARE:
            left.add(f" ⚡{flare[1]}", _st(ctx, "yellow", BOLD))
        when = _clock(ctx.now - r["since"]) if r["section"] == "working" else age(ctx, r["since"])
        right = Text()
        pct = _context(ctx, r)
        if pct is not None and w >= 48:
            right.extend(_meter(ctx, pct))
        right.add(r.get("where", ""), _st(ctx, "subtle")).add(" " + when if when else "", _st(ctx, role))
        orbit = "  " if last else "│ "
        what = r.get("what") if r["section"] != "settled" else ""    # an idle session's last reply is old news
        if r.get("failed") and what.lower().startswith("failed"):    # ✗ says it already
            what = ""
        style = _st(ctx, "red" if r["section"] == "needs" and not r.get("failed") else "subtext")
        if what and left.width + 1 + cells(what) + 1 + right.width <= w:    # short: on the same line
            left.add(" " + what, style)
            what = ""
        out.append(_row(left, right, w))
        if what:
            out.append(Text.of(orbit + "  ", _st(ctx, "subtle")).add(what, style))
        for a in r.get("agents") or []:
            out.append(Text.of(orbit, _st(ctx, "subtle")).add("  ◦ ", _st(ctx, "cyan")).add(a, _st(ctx, "subtext")))
    return out


def _timeline(ctx, f, ss, w, lanes):
    """The fleet's last hour: a lane per busy session, a bar for each slice of time by its tool calls."""
    span = float(f.get("window") or 3600)
    busy = [r for r in ss if any(ctx.now - t <= span for t in r.get("ticks") or [])][:lanes]
    if not busy:
        return []
    label_w = max(10, min(24, w // 5))
    n = max(1, w - label_w - 1)
    counts = []
    for r in busy:
        c = [0] * n
        for t in r["ticks"]:
            age_ = ctx.now - t
            if 0 <= age_ <= span:
                c[min(n - 1, int((span - age_) / span * n))] += 1
        counts.append(c)
    top = max(max(c) for c in counts) or 1
    mins = int(span // 60)
    out = [_row(Text.of("Activity", _st(ctx, "accent", BOLD)).add(f" {mins}m", _st(ctx, "muted")),
                Text.of("now", _st(ctx, "muted")), w)]
    for r, c in zip(busy, counts):
        glyph, role = _glyph(ctx, r)
        label = _exact(Text.of(glyph + " ", _st(ctx, role, BOLD)).add(r["title"], _st(ctx, "subtext")), label_w)
        bars = "".join(SPARK[0 if not v else max(1, round(v / top * 8))] for v in c)
        out.append(label.add(" ").add(bars, _st(ctx, role if r["section"] != "settled" else "muted")))
    return out


def fleet(ctx, d, w, rows):
    """Every Claude Code session on the machine, from agentboard: each project a star, its
    sessions in orbit around it and their agents as moons, laid out in columns like a map, with
    the last hour's activity in the rows left under it."""
    try:
        return _fleet(ctx, d, w, rows)
    except Exception:                              # a bad row must not cost the session its bar
        if os.environ.get("CLAUDE_STATUSLINE_DEBUG"):
            raise
        return [_head(ctx, "fleet", w=w), Text.of("The map hit an error; agentboard's data looks new.",
                                                  _st(ctx, "muted"))]


def _fleet(ctx, d, w, rows):
    f = d.get("fleet")
    if f is None:
        return [_head(ctx, "fleet", w=w), Text.of("Asking agentboard…", _st(ctx, "muted"))]
    if f.get("missing"):
        return [_head(ctx, "fleet", w=w), Text.of("agentboard isn't installed or didn't answer. "
                                                  "Install it, or run `agentboard web`.", _st(ctx, "muted"))]
    ss = f.get("rows") or []
    total = sum(r.get("count", 1) for r in ss)
    count = {k: sum(r.get("count", 1) for r in ss if r["section"] == k) for k in FLEET}
    extra = Text()
    for k, word in (("needs", "need you"), ("turn", "your turn"), ("working", "working")):
        if count[k]:
            extra.add(f" · {count[k]} {word}", _st(ctx, FLEET[k][1], BOLD if k == "needs" else 0))
    stale = ctx.now - float(f.get("at") or ctx.now)
    right = Text.of(f"stale {age(ctx, f['at'])}", _st(ctx, "orange")) if stale > 60 else None
    groups = {}
    for r in ss:                                  # already in queue order, so a star's place is its first session's
        groups.setdefault(r["project"], []).append(r)
    ncols = max(1, min(len(groups), (w + len(SEP)) // (FLEET_COL + len(SEP))))
    cw = (w - len(SEP) * (ncols - 1)) // ncols
    room = max(0, rows - 1)
    cols, hidden = [[] for _ in range(ncols)], 0
    own = ctx.data.get("session_id")
    for project, members_ in groups.items():
        lines = _system(ctx, f, project, members_, cw, own)
        col = min(cols, key=len)
        gap = 1 if col else 0
        free = room - len(col) - gap
        if free < 2:
            hidden += sum(r.get("count", 1) for r in members_)
            continue
        if len(lines) > free:
            cut = sum(1 for t in lines[free - 1:] if t.plain()[:1] in "├└")
            lines = lines[:free - 1] + [Text.of(f"  +{cut} more", _st(ctx, "muted"))]
        col += [Text()] * gap + lines
    if hidden:                                    # on the right, which gives way last
        note = Text.of(f"{hidden} off the map", _st(ctx, "muted"))
        right = note.add(" ").extend(right) if right else note
    out = [_head(ctx, "fleet", total, right, w, extra)]
    sep = Text.of(SEP, _st(ctx, "subtle"))
    for i in range(max((len(c) for c in cols), default=0)):
        t = Text()
        for j, c in enumerate(cols):
            if j:
                t.extend(sep)
            t.extend(_exact(c[i] if i < len(c) else Text(), cw))
        out.append(t)
    if not ss:
        out.append(Text.of("No sessions.", _st(ctx, "muted")))
    spare = rows - len(out)
    if spare >= 3:                                # the rows the map leaves: the fleet's last hour
        tl = _timeline(ctx, f, ss, w, spare - 2)
        if tl:
            out += [Text()] + tl
    return out


DRAW = {"fleet": fleet, "files": files, "graph": graph, "branches": branches, "stash": stash, "ci": ci, "servers": servers,
        "checks": checks, "sessions": sessions, "reviews": reviews}
