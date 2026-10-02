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
          "servers": (22, 2)}
TITLES = {"files": "Changes", "graph": "History", "branches": "Branches", "stash": "Stash", "ci": "CI",
          "servers": "Servers"}
SEP = " │ "
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
                        servers=[[r[0], r[1], when(r[2])] for r in fake.get("servers") or []])
        if not ctx.comp["git"].get("enabled", True):
            return None
        from .gitpanels import data
        cfg = ctx.comp.get("panels") or {}
        d = data(ctx.cwd, cfg, ctx.comp["git"], sync=ctx.sync_git, spawn=ctx.live)
        if d is None:
            return None
        shown = {n for c in cfg.get("show") or [] for n in members(c)}
        if "ci" in shown:
            from .ci import data as ci_data
            d["ci"] = ci_data(d["root"], d["gitdir"], d["common"], cfg, sync=ctx.sync_git, spawn=ctx.live)
        if "servers" in shown:
            from .servers import data as server_data
            d["servers"] = server_data(d["root"], sync=ctx.sync_git, spawn=ctx.live)
        return d
    return ctx.memo("panels", get)


def _says(d, name):
    """Whether a panel that shows only when it has something to say has it."""
    if name == "stash":
        return bool(d.get("stashes"))
    if name == "ci":
        return bool((d.get("ci") or {}).get("runs"))
    if name == "servers":
        return bool(d.get("servers"))
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
    cfg = ctx.comp.get("panels") or {}
    cols = [[n for n in members(c) if not d.get("pending") and _says(d, n) or
             d.get("pending") and n in ("files", "graph", "branches")] for c in cfg.get("show") or []]
    cols = columns(ctx.avail, [c if len(c) > 1 else c[0] for c in cols if c])
    if not cols:
        return None
    drawn = []
    for col, w in cols:
        if d.get("pending"):                        # the titles at once, so nothing moves when git answers
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
            t = Text([("⠀", PAD)] + t.clip(t.width - 1).spans)    # braille cell is not whitespace
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


def _head(ctx, name, count=None, right=None, w=0):
    left = Text.of(TITLES[name], _st(ctx, "accent", BOLD))
    if count is not None:
        left.add(f" {count}", _st(ctx, "muted"))
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
    out = [_head(ctx, "files", len(fs) if fs else None, total, w)]
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
        left = _code(ctx, xy).add(" ")
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
    for r in shown:
        _, glyph, role = _run_state(r)
        left = Text.of(glyph + " ", _st(ctx, role)).add(r[1], _st(ctx, "text", 0, r[8] or None))
        if r[3] != "completed":
            when = Text.of(("queued " if r[3] in ("queued", "waiting", "pending") else "") +
                           _clock(ctx.now - r[6]) if r[6] else r[3], _st(ctx, "yellow"))
        else:
            when = Text.of(age(ctx, r[7] or r[6]), _st(ctx, "muted"))
        out.append(_row(left, when, w))
    if more:
        out.append(more)
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


DRAW = {"files": files, "graph": graph, "branches": branches, "stash": stash, "ci": ci, "servers": servers}
