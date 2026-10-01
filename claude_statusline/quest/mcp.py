"""`statusline.py quest mcp`: Claude Quest as tools Claude can call (an MCP server on stdio).

Claude reads the hero as JSON in one call and acts in one more, instead of
reading the CLI's text. Every call opens the save under its lock, does what it
was asked like `claude-quest <command>` would, and writes it back. `quest
enable` registers the server with Claude Code (`claude mcp add`).

The protocol is JSON-RPC 2.0, one message per line. Only what tools need is
here: initialize, tools/list, tools/call and ping.
"""
from __future__ import annotations

import json
import sys

NAME = "claude-quest"
ACTIONS = ("equip", "unequip", "use", "sell", "sell_dupes", "buy", "forge", "reroll", "title", "name_pet")

TOOLS = [
    {"name": "quest_status",
     "description": "The hero now: level and XP, gold, title, class, streak, pet, what is worn, set bonuses, "
                    "live buffs, the total of every bonus, daily and weekly quests (numbered for reroll), "
                    "and any boss, PR dungeons and tech-debt raids. Start here.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "quest_bag",
     "description": "Everything carried and not worn, stacked by kind: id, name, kind (gear or consumable), "
                    "slot, rarity, count, what it does, and its sell price. Pass an item's id as `target` to "
                    "quest_act.",
     "inputSchema": {"type": "object", "properties": {
         "kind": {"type": "string", "enum": ["gear", "consumable"], "description": "Only this kind."}}}},
    {"name": "quest_shop",
     "description": "Today's shop: numbered stock with price, the deal of the day, what each item does, "
                    "whether it is sold out or affordable, and the gold carried.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "quest_best_gear",
     "description": "The gear that earns the most XP, found by trying every combination of the gear owned "
                    "against the hero's own history (tool calls, prompts, commits, pushes, test runs) with set "
                    "bonuses. With equip=true it is put on.",
     "inputSchema": {"type": "object", "properties": {
         "equip": {"type": "boolean", "description": "Wear the best gear now.", "default": False}}}},
    {"name": "quest_act",
     "description": "Do one thing in the game and get back what the game said, with gold and level after. "
                    "Actions: equip <item>, unequip <slot or item>, use <item> (count = how many times), "
                    "sell <item> (count = how many, or 0 for all), sell_dupes (every spare copy, keeping one "
                    "of each), buy <shop number or name>, forge <rarity: common, uncommon, rare or epic>, "
                    "reroll <daily quest number>, title <an earned title, or 'rank'>, name_pet <name>. "
                    "Items are named by id (from quest_bag) or by name. Selling, forging and using items "
                    "cannot be undone: do them when the user asked.",
     "inputSchema": {"type": "object", "required": ["action"], "properties": {
         "action": {"type": "string", "enum": list(ACTIONS)},
         "target": {"type": "string", "description": "The item, slot, shop number, rarity, quest number, "
                                                     "title or name the action needs."},
         "count": {"type": "integer", "minimum": 0, "description": "use: times; sell: copies (0 = all)."}}}},
]


# ---- the game, as data ----------------------------------------------------------------------

def _item(it, count=None, worn=False):
    from . import items
    out = {"id": it["id"], "name": it["name"], "kind": it["kind"], "rarity": it["rarity"],
           "does": "; ".join(items.describe(it)), "sell_price": items.SELL_PRICE[it["rarity"]]}
    if it.get("slot"):
        out["slot"] = it["slot"]
    if it.get("set"):
        out["set"] = items.SETS[it["set"]]["name"]
    if count is not None:
        out["count"] = count
    if worn:
        out["worn"] = True
    return out


def status(g):
    from . import effects, items, rules
    s = g.s
    lvl = g.level()
    pet = s["pet"]
    worn = effects.equipped_items(s)
    k = s["counters"]
    return {
        "level": lvl, "xp_into_level": s["xp"] - rules.xp_for_level(lvl),
        "xp_for_next_level": rules.xp_for_level(lvl + 1) - rules.xp_for_level(lvl),
        "gold": s["gold"], "title": s.get("title") or rules.rank_for(lvl), "titles_earned": s["titles"],
        "class": rules.SCHOOLS.get(rules.top_school(s.get("school")) or "", ("?",))[0],
        "streak_days": g.streak(),
        "pet": {"name": pet.get("name"), "looks": rules.pet_description(s), "bond": pet.get("bond", 0)},
        "worn": {slot: _item(it, worn=True) for slot, it in worn.items()},
        "set_bonuses": [{"set": items.SETS[sid]["name"], "pieces": f"{n}/{len(items.SETS[sid]['pieces'])}",
                         "bonus": "; ".join(line for fx in fxs for line in items.fx_lines(fx))}
                        for sid, n, fxs in effects.active_sets(s)],
        "buffs": [{"name": b["name"], "bonus": "; ".join(items.fx_lines(b["fx"])),
                   "minutes_left": max(0, round((b["until"] - g.now) / 60))} for b in s["buffs"]],
        "all_bonuses": "; ".join(items.fx_lines(g.fx)),
        "daily_quests": [{"number": i + 1, "title": q["title"], "task": q["text"],
                          "progress": f"{q['progress']}/{q['goal']}", "done": q["done"],
                          "reward": f"{q['xp']} XP, {q['gold']} gold"}
                         for i, q in enumerate(s["daily"].get("quests", []))],
        "free_reroll_today": bool(s["daily"].get("free_reroll")),
        "weekly_quests": [{"title": q["title"], "task": q["text"], "progress": f"{q['progress']}/{q['goal']}",
                           "done": q["done"]} for q in s["weekly"].get("quests", [])],
        "boss": ({"name": s["boss"]["name"], "hp": f"{s['boss']['hp']}/{s['boss']['max_hp']}",
                  "project": s["boss"]["project"], "kind": s["boss"].get("kind")} if s.get("boss") else None),
        "dungeons": [{"name": d["name"], "pr": d["number"], "project": d["project"]} for d in s["dungeons"].values()],
        "raids": [{"name": r["name"], "project": p, "hp": f"{r['hp']}/{r['max_hp']}", "defeated": r["defeated"]}
                  for p, r in s["raids"].items()],
        "history": {key: k.get(key, 0) for key in ("shell", "edits", "reads", "agents", "web", "prompts",
                                                     "commits", "pushes", "tests", "bosses", "quests_done")},
    }


def bag(g, kind=None):
    return {"gold": g.s["gold"],
            "items": [_item(it, len(es)) for it, es in g.bag_groups() if kind in (None, it["kind"])]}


def shop(g):
    from . import items
    gold = g.s["gold"]
    out = []
    for i, slot in enumerate(g.shop_stock()):
        it = items.ITEMS.get(slot["id"])
        if it:
            out.append(dict(_item(it), number=i + 1, price=slot["price"], deal=slot["deal"], sold_out=slot["sold"],
                            affordable=not slot["sold"] and slot["price"] <= gold))
    return {"gold": gold, "stock": out}


def best_gear(g, equip=False):
    from . import effects, items
    from .cli import best_loadout
    best, best_xp, now_xp = best_loadout(g)
    worn = {slot: effects.entry(g.s, uid) for slot, uid in g.s["equipped"].items()}
    worn = {slot: e["id"] for slot, e in worn.items() if e}
    changes = {slot: {"from": items.ITEMS[worn[slot]]["name"] if slot in worn else None,
                      "to": items.ITEMS[e["id"]]["name"]}
               for slot, e in best.items() if worn.get(slot) != e["id"]}
    gain = round((best_xp / now_xp - 1) * 100, 1) if now_xp else 0.0
    if equip:
        for slot, e in best.items():
            if worn.get(slot) != e["id"]:
                g.equip(items.ITEMS[e["id"]]["name"])
    return {"best": {slot: _item(items.ITEMS[e["id"]]) for slot, e in best.items()},
            "changes": changes, "xp_gain_percent": gain, "equipped": bool(equip and changes),
            "messages": list(g.msgs)}


def _query(target):
    """An item id becomes its name, which `Game.find` matches exactly; anything else is used as given."""
    from . import items
    target = (target or "").strip()
    return items.ITEMS[target]["name"] if target in items.ITEMS else target


def act(g, action, target="", count=None):
    from .game import GameError
    if action == "equip":
        g.equip(_query(target))
    elif action == "unequip":
        g.unequip(target if target in ("head", "hand", "back", "feet", "charm") else _query(target))
    elif action == "use":
        times = max(1, int(count or 1))
        done = 0
        for _ in range(times):
            try:
                g.use(_query(target))
                done += 1
            except GameError:
                if not done:
                    raise
                g.say(f"(used {done} of the {times} asked; none left)")
                break
    elif action == "sell":
        g.sell(_query(target), "all" if count == 0 else str(count or 1))
    elif action == "sell_dupes":
        g.sell("dupes")
    elif action == "buy":
        g.buy(target)
    elif action == "forge":
        g.forge(target)
    elif action == "reroll":
        if not str(target).isdigit():
            raise GameError("reroll takes a daily quest's number, from quest_status.")
        g.reroll(int(target) - 1)
    elif action == "title":
        g.set_title(target)
    elif action == "name_pet":
        g.name_pet(target)
    else:
        raise GameError(f"Unknown action {action!r}; one of {', '.join(ACTIONS)}.")
    return {"messages": list(g.msgs), "gold": g.s["gold"], "level": g.level()}


def call(name, args):
    """(result, is it an error?) for one tool call."""
    from . import state as store
    from .game import Game, GameError
    from .hooks import deliver
    args = args if isinstance(args, dict) else {}
    try:
        with store.Locked() as state:
            g = Game(state)
            g.tick()
            if name == "quest_status":
                out = status(g)
            elif name == "quest_bag":
                out = bag(g, args.get("kind"))
            elif name == "quest_shop":
                out = shop(g)
            elif name == "quest_best_gear":
                out = best_gear(g, bool(args.get("equip")))
            elif name == "quest_act":
                out = act(g, str(args.get("action") or ""), str(args.get("target") or ""), args.get("count"))
            else:
                return {"error": f"no tool {name!r}"}, True
            g.finish(activity=False)
            store.add_news(state, g.msgs, g.now)
    except GameError as exc:
        return {"error": str(exc)}, True
    deliver(g.toasts)
    return out, False


# ---- the protocol ---------------------------------------------------------------------------

def reply(msg):
    from .. import __version__
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return None                                   # a notification: nothing to say back
    if method == "initialize":
        version = (msg.get("params") or {}).get("protocolVersion") or "2025-06-18"
        result = {"protocolVersion": version, "capabilities": {"tools": {}},
                  "serverInfo": {"name": NAME, "version": __version__},
                  "instructions": "Claude Quest, the RPG in the user's status line. quest_status first; "
                                  "quest_act to do things; quest_best_gear for the best gear."}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = msg.get("params") or {}
        out, err = call(params.get("name"), params.get("arguments"))
        result = {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}], "isError": err}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"no method {method!r}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(stdin=None, stdout=None):
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            out = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "not JSON"}}
        else:
            try:
                out = reply(msg) if isinstance(msg, dict) else None
            except Exception as exc:          # one bad call must not end the server
                out = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": str(exc)}}
        if out is not None:
            stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
            stdout.flush()
    return 0
