"""Game mode's menu tabs for playing: quests, bag, shop and hero.

`cells` draws a tab from the full save (the bar's cached copy leaves out the
bag, quests, shop and titles); it never changes the save. `act` carries out a
click under the save's lock, the way `claude-quest <command>` does. Links name
what they act on by something that survives the save changing between the
drawing and the click: an item's id, a title's place in the list (it only
grows), and the day for a quest or the shop (both change at midnight).
"""
from __future__ import annotations

import json
import time
from datetime import date

from ..text import BOLD, Text

RARITY_ROLE = {"common": "text", "uncommon": "green", "rare": "blue", "epic": "purple", "legendary": "gold"}
FORGEABLE = ("common", "uncommon", "rare", "epic")
CONFIRM = ("spares", "forge")         # these take a second click
HINT = {"quests": "your daily and weekly quests", "bag": "use, wear or sell", "shop": "new stock every day",
        "hero": "click a title to wear it"}


def load():
    """The full save, read fresh, or None."""
    from . import state_path
    try:
        with open(state_path()) as fh:
            s = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(s, dict):
        return None
    from .state import migrate
    return migrate(s)


def _t(ctx, text, role, url=None, bold=False):
    return Text([(text, (ctx.color(role), None, BOLD if bold else 0, url))]) if text else Text()


def _act(ctx, label, url):
    return _t(ctx, f"[{label}]", "accent", url)


def _game(s, now):
    from .game import Game
    return Game(s, now=now)


def _spares(groups):
    return sum(len(es) - 1 for _, es in groups)


def _forge_counts(groups):
    from . import items
    have = {r: sum(len(es) for it, es in groups if it["rarity"] == r) for r in FORGEABLE}
    return [(r, have[r], items.FORGE_COST[r]) for r in FORGEABLE]


def quests_tab(ctx, s, mk):
    out = []
    daily = s.get("daily") or {}
    day = daily.get("date", "")
    free = daily.get("free_reroll") and day == date.fromtimestamp(ctx.now).isoformat()
    for i, q in enumerate(daily.get("quests") or []):
        main = _t(ctx, "✅ " if q.get("done") else "⬜ ", "text")
        main.extend(_t(ctx, q.get("title", "?"), "green" if q.get("done") else "text", bold=True))
        main.extend(_t(ctx, f"  {q.get('progress', 0)}/{q.get('goal', 0)}", "subtext"))
        main.extend(_t(ctx, f"  {q.get('text', '')}", "muted"))
        acts = [_act(ctx, "reroll", mk("reroll", f"{i}-{day.replace('-', '')}"))] if free and not q.get("done") else []
        out.append((main, acts))
    for q in (s.get("weekly") or {}).get("quests") or []:
        main = _t(ctx, "✅ " if q.get("done") else "🗓 ", "text")
        main.extend(_t(ctx, q.get("title", "?"), "green" if q.get("done") else "gold", bold=True))
        main.extend(_t(ctx, f"  {q.get('progress', 0)}/{q.get('goal', 0)}", "subtext"))
        main.extend(_t(ctx, f"  weekly · {q.get('text', '')}", "muted"))
        out.append((main, []))
    return out


def bag_tab(ctx, s, mk):
    from . import items
    g = _game(s, ctx.now)
    groups = g.bag_groups()
    out = []
    spare = _spares(groups)
    if spare:
        out.append((_t(ctx, f"🪙 {spare} spare copies", "gold"), [_act(ctx, "sell spares", mk("confirm", "spares"))]))
    for r, have, need in _forge_counts(groups):
        if have >= need:
            out.append((_t(ctx, f"🔥 forge {need} {r} into 1 {items.RARITIES[items.rarity_rank(r) + 1]}", "orange"),
                        [_act(ctx, "forge", mk("confirm", f"forge-{r}"))]))
    # Things you can use first, then gear, rarest first within each.
    order = sorted(groups, key=lambda ge: (ge[0]["kind"] != "consumable", -items.rarity_rank(ge[0]["rarity"]),
                                           ge[0]["name"]))
    for item, entries in order:
        main = _t(ctx, f"{item['icon']} ", "text")
        main.extend(_t(ctx, item["name"], RARITY_ROLE.get(item["rarity"], "text"), bold=item["rarity"] != "common"))
        if len(entries) > 1:
            main.extend(_t(ctx, f" ×{len(entries)}", "subtext"))
        acts = [_act(ctx, "use" if item["kind"] == "consumable" else "wear",
                     mk("use" if item["kind"] == "consumable" else "wear", item["id"]))]
        if len(entries) > 1:
            acts.append(_act(ctx, "sell", mk("sell", item["id"])))
        out.append((main, acts))
    if not groups:
        out.append((_t(ctx, "Your bag is empty. Loot drops as you work.", "muted"), []))
    return out


def shop_tab(ctx, s, mk):
    import copy
    from . import items
    g = _game(copy.deepcopy(s), ctx.now)          # rolling a new day's stock must not touch the real save
    stock = g.shop_stock()
    day = g.s["shop"]["date"].replace("-", "")
    gold = int(s.get("gold") or 0)
    out = [(_t(ctx, f"🪙 {gold:,} gold", "gold", bold=True), [])]
    for i, slot in enumerate(stock):
        item = items.ITEMS.get(slot["id"])
        if not item:
            continue
        main = _t(ctx, f"{item['icon']} ", "text")
        main.extend(_t(ctx, item["name"], RARITY_ROLE.get(item["rarity"], "text"), bold=True))
        main.extend(_t(ctx, f"  {slot['price']}g", "gold" if slot.get("deal") else "subtext"))
        if slot.get("deal"):
            main.extend(_t(ctx, " deal", "green"))
        if slot.get("sold"):
            acts = [_t(ctx, "sold out", "muted")]
        elif slot["price"] > gold:
            acts = [_t(ctx, "too dear", "muted")]
        else:
            acts = [_act(ctx, "buy", mk("buy", f"{i}-{day}"))]
        out.append((main, acts))
    return out


def hero_tab(ctx, s, mk):
    from . import effects, rules
    g = _game(s, ctx.now)
    lvl = g.level()
    out = [(_t(ctx, f"Lv {lvl} ", "gold", bold=True).extend(
        _t(ctx, s.get("title") or rules.rank_for(lvl), "purple")), [])]
    pet = s.get("pet") or {}
    out.append((_t(ctx, f"🐾 {pet.get('name') or 'Your pet'}", "green").extend(
        _t(ctx, f"  bond {pet.get('bond', 0)}" + (f" · {pet['form']}" if pet.get("form") else ""), "subtext")), []))
    b = s.get("boss")
    if b:
        out.append((_t(ctx, f"{b.get('icon', '👾')} {b.get('name', 'a boss')}", "red", bold=True).extend(
            _t(ctx, f"  {b.get('hp', 0)}/{b.get('max_hp', 0)} HP in {b.get('project', '?')}", "subtext")), []))
    worn = effects.equipped_items(s)
    if worn:
        out.append((_t(ctx, "Wearing " + " ".join(i["icon"] for i in worn.values()), "text"), []))
    current = s.get("title")
    out.append((_t(ctx, ("● " if not current else "  ") + rules.rank_for(lvl) + " (rank)",
                   "accent" if not current else "text", mk("title", "rank"), bold=not current), []))
    for i, t in enumerate(s.get("titles") or []):
        out.append((_t(ctx, ("● " if t == current else "  ") + t, "accent" if t == current else "text",
                       mk("title", str(i)), bold=t == current), []))
    for d in (s.get("dungeons") or {}).values():
        out.append((_t(ctx, f"🏰 {d.get('name', 'a dungeon')}", "purple").extend(
            _t(ctx, f"  #{d.get('number', '?')} in {d.get('project', '?')}: merge it to clear", "subtext")), []))
    for project, r in (s.get("raids") or {}).items():
        if not r.get("defeated"):
            out.append((_t(ctx, f"🐙 {r.get('name', 'a raid boss')}", "blue").extend(
                _t(ctx, f"  {r.get('hp', 0)}/{r.get('max_hp', 0)} in {project}", "subtext")), []))
    return out


TABS = {"quests": quests_tab, "bag": bag_tab, "shop": shop_tab, "hero": hero_tab}


def cells(ctx, tab, mk, width):
    """(cell Texts, cell width) for a tab: each cell is what it shows, then its buttons."""
    s = load()
    if s is None:
        return [_t(ctx, "No save yet: Claude Quest starts with your next prompt.", "muted")], width
    pairs = TABS[tab](ctx, s, mk)
    cap = max(24, (width - 3) // 2) if width >= 90 else width
    natural = max((m.width + sum(a.width + 1 for a in acts) for m, acts in pairs), default=10)
    cell_w = min(cap, natural)
    out = []
    for main, acts in pairs:
        tail = Text()
        for a in acts:
            tail.add(" ").extend(a)
        room = max(4, cell_w - tail.width)
        body = main.clip(room)
        out.append(Text(body.spans + [(" " * (cell_w - body.width - tail.width), (None, None, 0, None))]
                        + tail.spans) if acts else body)
    return out, cell_w


def confirm_text(what):
    if what == "spares":
        return "Sell every spare copy in your bag (keeping one of each)?"
    if what.startswith("forge-"):
        from . import items
        r = what[6:]
        return f"Melt {items.FORGE_COST[r]} {r} items into one of the next rarity?"
    return "Are you sure?"


# ---- clicks -------------------------------------------------------------------------------

def _check_day(arg, today):
    """(index, ok) from an `<index>-<yyyymmdd>` argument."""
    idx, _, day = arg.partition("-")
    if not idx.isdigit() or not day.isdigit():
        raise ValueError("bad argument")
    return int(idx), day == today.isoformat().replace("-", "")


def act(action, arg, now=None):
    """Carry out one game click. Returns (what the game said, pop-ups); raises GameError when the
    game says no and ValueError for an argument it does not accept."""
    from . import items
    from . import state as store
    from .game import Game, GameError
    now = time.time() if now is None else now
    with store.Locked() as state:
        g = Game(state, now=now)
        g.tick()
        if action == "reroll":
            idx, same = _check_day(arg, g.today)
            if not same:
                raise GameError("Those were yesterday's quests; here are today's.")
            g.reroll(idx)
        elif action == "buy":
            idx, same = _check_day(arg, g.today)
            if not same:
                g.shop_stock()
                raise GameError("The shop has new stock today; have a look.")
            g.buy(str(idx + 1))
        elif action in ("use", "wear", "sell"):
            if arg not in items.ITEMS:
                raise ValueError("no such item")
            groups = g.bag_groups()
            n = next((i for i, (it, _) in enumerate(groups) if it["id"] == arg), None)
            if n is None:
                raise GameError(f"No {items.ITEMS[arg]['name']} left in your bag.")
            if action == "use":
                g.use(str(n + 1))
            elif action == "wear":
                g.equip(str(n + 1))
            else:
                if len(groups[n][1]) < 2:
                    raise GameError(f"That is your only {items.ITEMS[arg]['name']}; the menu sells spares only.")
                g.sell(str(n + 1), "1")
        elif action == "spares":
            g.sell("dupes")
        elif action == "forge":
            if arg not in FORGEABLE:
                raise ValueError("no such rarity")
            g.forge(arg)
        elif action == "title":
            if arg == "rank":
                g.set_title("rank")
            elif arg.isdigit() and int(arg) < len(state.get("titles") or []):
                g.set_title(state["titles"][int(arg)])
            else:
                raise ValueError("no such title")
        else:
            raise ValueError(f"unknown action {action!r}")
        g.finish(activity=False)
        store.add_news(state, g.msgs, now)
    return g.msgs, g.toasts
