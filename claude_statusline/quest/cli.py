"""`claude-quest`: the character sheet, the bag, the shop, and everything you can do.

    claude-quest [sheet]              your character
    claude-quest bag                  what you carry, numbered
    claude-quest inspect <item>       one item in detail
    claude-quest equip <item>         wear gear
    claude-quest unequip <slot|item>  take it off
    claude-quest use <item>           drink, read, eat or open a consumable
    claude-quest sell <item> [n|all]  sell for gold; `sell dupes` sells spare copies
    claude-quest forge <rarity>       melt spares into one item of the next rarity
    claude-quest shop                 today's stock
    claude-quest buy <n|name>         buy from the shop
    claude-quest quests               daily and weekly quests
    claude-quest reroll <n>           swap a daily quest (once a day)
    claude-quest boss                 the monster you are fighting, if any
    claude-quest dungeons             open pull requests, as dungeons to clear
    claude-quest raid                 this week's tech-debt raid bosses
    claude-quest pet [name <name>]    your companion
    claude-quest titles | title <t>   earned titles; wear one
    claude-quest achievements         every achievement, earned or not
    claude-quest log                  recent adventures
    claude-quest guide                how everything is earned
    claude-quest field start|stop     the desktop overlay (kitty)
    claude-quest enable | disable     switch Claude Quest on or off (hooks, status line, /quest)
    claude-quest status               whether it is on, and where everything lives
"""
import sys
import time
from datetime import datetime

from . import boss as bosses
from . import dungeon, effects, items, quests, raid, rules
from . import state as store
from .game import ACHIEVEMENTS, Game, GameError
from .ui import bar, c, item_line, rarity

STAGE_AT = {key: need for need, key, _ in rules.PET_STAGES}


def _mins(until, now):
    m = max(0, round((until - now) / 60))
    return f"{m // 60}h{m % 60:02d}m" if m >= 60 else f"{m}m"


def _hearts(hp, max_hp):
    if max_hp <= 10:
        return c("red", "♥" * hp) + c("dim", "♡" * (max_hp - hp))
    return c("red", "♥") + f" {hp}/{max_hp}"


# ------------------------------------------------------------------ views

def show_sheet(g):
    from .ui import banner
    from .view import build
    s = g.s
    v = build(s, g.now)
    print(banner(v, g.streak()))
    worn = effects.equipped_items(s)
    print("\n" + c("bold", "Equipment"))
    for slot in items.SLOTS:
        item = worn.get(slot)
        if item:
            print(f"  {slot:<6} {item_line(item)}  {c('dim', '; '.join(items.describe(item)))}")
        else:
            print(f"  {slot:<6} {c('dim', '(empty)')}")
    sets = effects.active_sets(s)
    if sets:
        print("\n" + c("bold", "Set bonuses"))
        for set_id, n, reached in sets:
            spec = items.SETS[set_id]
            fx = "; ".join(line for b in reached for line in items.fx_lines(b))
            print(f"  {spec['name']} ({n}/{len(spec['pieces'])}): {fx}")
    buffs = effects.live_buffs(s, g.now)
    if buffs:
        print("\n" + c("bold", "Buffs"))
        for b in buffs:
            print(f"  {b['icon']} {b['name']}: {'; '.join(items.fx_lines(b['fx']))}, "
                  f"{_mins(b['until'], g.now)} left")
    fx = {k: v for k, v in g.fx.items() if v}
    if fx:
        print("\n" + c("bold", "All bonuses") + "  " + c("dim", "; ".join(items.fx_lines(fx))))
    b = s.get("boss")
    if b:
        print("\n" + c("bold", "Boss") + f"  {b['icon']} {b['name']} in {b['project']}  "
              f"{_hearts(b['hp'], b['max_hp'])}")
    school = s.get("school") or {}
    if school:
        total = sum(school.values())
        print("\n" + c("bold", "Schools of magic"))
        for k, n in sorted(school.items(), key=lambda kv: -kv[1]):
            name, icon = rules.SCHOOLS[k]
            print(f"  {icon} {name:<16} {bar(n / total, 15)} {n}")
    k = s["counters"]
    print("\n" + c("dim", f"Commits {k['commits']} · pushes {k['pushes']} · test runs {k['tests']} · "
                          f"bosses {k['bosses']} · quests {k['quests_done']} · items found {k['items_found']} · "
                          f"legacy XP {s.get('legacy_xp', 0)}"))


def show_bag(g):
    s = g.s
    groups = g.bag_groups()
    print(c("bold", f"🎒 Bag") + f"  {len(s['bag'])} items   🪙 {s['gold']} gold")
    if not groups:
        print(c("dim", "  Nothing unequipped. Loot drops as you work."))
    for n, (item, entries) in enumerate(groups, 1):
        kind = f"{item['slot']}" if item["kind"] == "gear" else "use"
        what = "; ".join(items.describe(item))
        print(f"  {n:>2}  {item_line(item, len(entries))}  {c('dim', f'[{kind}] {what}')}")
    worn = effects.equipped_items(s)
    if worn:
        print(c("bold", "Wearing") + "  " + " · ".join(f"{slot}: {i['icon']} {rarity(i)}" for slot, i in worn.items()))
    print(c("dim", "Try: claude-quest inspect 1 · equip 1 · use 2 · sell dupes · forge common"))


def show_item(g, query):
    item, _ = g.find(query, include_worn=True)
    owned = sum(1 for e in g.s["bag"] if e["id"] == item["id"])
    kind = f"gear, {item['slot']}" if item["kind"] == "gear" else "consumable"
    extra = ""
    if item.get("set"):
        spec = items.SETS[item["set"]]
        extra = f", part of the {spec['name']} set"
    detail = f"({item['rarity']} {kind}{extra})"
    print(f"{items.RARITY_ICON[item['rarity']]} {item['icon']} {c('bold', rarity(item))}  {c('dim', detail)}")
    print(f"  {c('gray', chr(8220) + item['flavor'] + chr(8221))}")
    for line in items.describe(item):
        print(f"  • {line}")
    if item.get("set"):
        spec = items.SETS[item["set"]]
        pieces = ", ".join(items.ITEMS[p]["name"] for p in spec["pieces"])
        bonus = "; ".join(f"{n} pieces: " + ", ".join(items.fx_lines(fx)) for n, fx in sorted(spec["bonus"].items()))
        print(f"  Set: {pieces}")
        print(f"  Set bonus: {bonus}; full set grants the title {spec['title']}")
    print(c("dim", f"  You have {owned}. Sells for {items.SELL_PRICE[item['rarity']]} gold."))


def show_quests(g):
    s = g.s
    print(c("bold", "📜 Daily quests") + c("dim", "  (new ones at midnight)"))
    for n, q in enumerate(s["daily"].get("quests", []), 1):
        mark = "✅" if q["done"] else "⬜"
        prog = f"{bar(q['progress'] / q['goal'], 10)} {q['progress']}/{q['goal']}"
        reward = c("dim", f"+{q['xp']} XP +{q['gold']} gold")
        print(f"  {n}  {mark} {c('bold', q['title']):<22} {q['text']:<34} {prog}  {reward}")
    if s["daily"].get("free_reroll"):
        print(c("dim", "  Free reroll today: claude-quest reroll <n>"))
    for q in s["weekly"].get("quests", []):
        mark = "✅" if q["done"] else "🗓 "
        print(c("bold", "\n🗓  Weekly quest"))
        print(f"     {mark} {c('bold', q['title'])}: {q['text']}  {bar(q['progress'] / q['goal'], 10)} "
              f"{q['progress']}/{q['goal']}  {c('dim', f'+{q["xp"]} XP +{q["gold"]} gold + rare-leaning loot')}")


def show_shop(g):
    stock = g.shop_stock()
    print(c("bold", "🏪 The Shop") + c("dim", "  (new stock daily)") + f"   🪙 {g.s['gold']} gold")
    for n, slot in enumerate(stock, 1):
        item = items.ITEMS[slot["id"]]
        price = f"{slot['price']:>4} gold"
        tag = ""
        if slot["deal"]:
            tag = c("green", f" deal of the day (was {items.BUY_PRICE[item['rarity']]})")
        if slot["sold"]:
            price, tag = c("dim", "sold out"), ""
        print(f"  {n}  {item_line(item)}  {price}{tag}")
        print(f"      {c('dim', '; '.join(items.describe(item)))}")
    print(c("dim", "Buy: claude-quest buy <n>   Sell: claude-quest sell <item> | sell dupes"))


def show_boss(g):
    b = g.s.get("boss")
    if not b:
        print("🌿 No monsters about. A failing test, build or lint run will summon one.")
        return
    age = round((g.now - b["spawned"]) / 60)
    print(f"{b['icon']} {c('bold', b['name'])}, lurking in {b['project']} for {age} min")
    print(f"  HP {_hearts(b['hp'], b['max_hp'])}   runs so far: {b['attempts']}")
    print(f"  Get the {bosses.KIND_NOUN[b['kind']]} passing to defeat it. Each run with fewer failures hits it.")
    bounty = 1 + g.fx.get("bounty", 0)
    print(c("dim", f"  Bounty: about {round((30 * b['max_hp'] + 5 * g.level()) * bounty)} XP, "
                   f"{round((12 * b['max_hp'] + 10) * bounty)} gold and a guaranteed drop. "
                   f"It flees after 24 hours."))


def show_dungeons(g):
    ds = sorted(g.s["dungeons"].values(), key=lambda d: -d["opened"])
    if not ds:
        print(f"{dungeon.ICON} No dungeons open. `gh pr create` opens one; merging it clears it.")
        return
    print(c("bold", f"{dungeon.ICON} Open dungeons"))
    for d in ds:
        age = round((g.now - d["opened"]) / 86400, 1)
        trap = c("red", f"  🪤 {d['failing']} checks failing") if d.get("failing") else ""
        xp, gold, _ = dungeon.rewards(d, g.level())
        print(f"  #{d['number']:<5} {c('bold', d['name'])} in {d['project']}: {d['rooms']} rooms, "
              f"{d['traps']} traps, {age} days{trap}")
        print(c("dim", f"         clear it now for about {xp} XP, {gold} gold and a guaranteed drop"))
    print(c("dim", "  Each push is a room, each failing `gh pr checks` a trap; `gh pr merge` clears it. "
                   "Unmerged dungeons crumble after 14 days."))


def show_raid(g):
    rs = g.s["raids"]
    if not rs:
        print(f"{raid.ICON} No raid this week yet. Your next commit counts the TODO, FIXME, XXX and HACK "
              "markers in the project and summons its boss.")
        return
    print(c("bold", f"{raid.ICON} Tech-debt raids") + c("dim", "  (new ones each week)"))
    for project, r in sorted(rs.items()):
        if r["defeated"]:
            print(f"  {project:<20} {c('green', '✓ ' + r['name'] + ' slain, debt-free this week')}")
            continue
        xp, gold, _ = raid.rewards(r, g.level())
        print(f"  {project:<20} {c('bold', r['name'])}  {bar(r['hp'] / max(1, r['max_hp']), 12)} "
              f"{r['hp']}/{r['max_hp']}  {c('dim', f'slay it for {xp} XP, {gold} gold')}")
    print(c("dim", "  Commits that remove markers strike it (15 XP each); zero markers slays it."))


def show_pet(g):
    s = g.s
    level = g.level()
    tier, tier_name = rules.bond_level(s["pet"].get("bond", 0))
    name = s["pet"].get("name")
    form = rules.form_of(s)
    print(f"🐾 {c('bold', name or 'Your pet')}, {rules.pet_description(s)}" + (f" {form[1]}" if form else ""))
    if form:
        print("  Gift: " + "; ".join(items.fx_lines(rules.form_fx(s))))
    nxt = [(need, key, d) for need, key, d in rules.PET_STAGES if need > level]
    if nxt:
        print(f"  Evolves into {nxt[0][2]} at level {nxt[0][0]}.")
    if not form and nxt and nxt[0][1] in rules.FORM_STAGES:
        top = rules.top_school(s.get("school"))
        if top:
            key, icon, fx = rules.FORMS[top]
            print(f"  Heading for the {icon} {key} form, from your top school ({rules.SCHOOLS[top][0]}): "
                  + "; ".join(items.fx_lines(fx)) + ".")
        print(c("dim", "  The form is fixed by the school you use most when it evolves. Other forms: "
                       + ", ".join(f"{f[1]} {f[0]} ({rules.SCHOOLS[k][0]})"
                                   for k, f in rules.FORMS.items() if k != top) + "."))
    bond = s["pet"].get("bond", 0)
    levels = rules.BOND_LEVELS
    if tier + 1 < len(levels):
        lo, hi = levels[tier][0], levels[tier + 1][0]
        print(f"  Bond: {tier_name} {bar((bond - lo) / (hi - lo), 12)} {bond}/{hi}, next: {levels[tier + 1][1]}")
    else:
        print(f"  Bond: {tier_name} ({bond}). Inseparable.")
    print(c("dim", f"  Bond grows by one each day you play, and with treats. Each tier adds +1% XP (now +{tier}%)."))
    if not name:
        print(c("dim", "  Give them a name: claude-quest pet name <name>"))


def show_titles(g):
    s = g.s
    rank = rules.rank_for(g.level())
    print(c("bold", "🎖  Titles") + f"  showing: {s.get('title') or rank}")
    print(f"  • {rank} {c('dim', '(your rank, the default)')}")
    for t in s["titles"]:
        print(f"  • {t}")
    locked = [(n, d, t) for k, (n, d, t) in ACHIEVEMENTS.items() if t and t not in s["titles"]]
    locked += [(spec["name"], "complete the set", spec["title"]) for spec in items.SETS.values()
               if spec["title"] not in s["titles"]]
    if locked:
        print(c("dim", "  Still to earn: " + ", ".join(f"{t} ({d.lower()})" for _, d, t in locked)))
    print(c("dim", "  Wear one: claude-quest title <name>   Back to rank: claude-quest title none"))


def show_achievements(g):
    got = g.s["achievements"]
    print(c("bold", f"🏆 Achievements {len(got)}/{len(ACHIEVEMENTS)}"))
    for key, (name, desc, title) in ACHIEVEMENTS.items():
        when = got.get(key)
        mark = "🏆" if when else "🔒"
        t = c("dim", f" → title: {title}") if title else ""
        stamp = c("dim", f"  {when[:10]}") if when else ""
        text = f"{name:<28} {desc}"
        print(f"  {mark} {text if when else c('dim', text)}{t}{stamp}")


def show_log(g, n=25):
    entries = g.s["log"][-n:]
    if not entries:
        print("Your story hasn't started yet.")
        return
    print(c("bold", "📖 Adventure log"))
    for e in entries:
        when = datetime.fromtimestamp(e["at"]).strftime("%b %d %H:%M")
        print(f"  {c('dim', when)}  {e['text']}")


def show_guide(g):
    print(c("bold", "⚔️  How Claude Quest works") + "\n")
    print(c("bold", "XP") + " comes from everything Claude does for you:")
    for tool, xp in sorted(rules.XP_BY_TOOL.items(), key=lambda kv: -kv[1]):
        school = rules.TOOL_SCHOOL.get(tool)
        cls = f"  {rules.SCHOOLS[school][1]} {rules.SCHOOLS[school][0]}" if school else ""
        print(f"  {tool:<13} +{xp:<3}{c('dim', cls)}")
    print(f"  other tools   +{rules.DEFAULT_TOOL_XP}      each prompt +{rules.PROMPT_XP}")
    print(f"  git commit +{rules.COMMIT_XP} (+{rules.COMMIT_GOLD} gold)   git push +{rules.PUSH_XP} "
          f"(+{rules.PUSH_GOLD} gold)   test run +{rules.TEST_XP}")
    print(c("dim", "  Your class is the school you use most. Level n needs 50·(n−1)² XP in total; "
                   "each level-up pays 20 gold × the new level."))
    print("\n" + c("bold", "Loot") + f" drops {round(rules.STOP_LOOT_CHANCE * 100)}% of the time Claude finishes "
          f"a reply and {round(rules.TOOL_LOOT_CHANCE * 100)}% per tool call. Luck raises that.")
    total = sum(items.RARITY_WEIGHT.values())
    print("  " + "  ".join(f"{items.RARITY_ICON[r]} {r} {round(w * 100 / total)}%" for r, w in items.RARITY_WEIGHT.items()))
    print(c("dim", "  Gear goes in five slots (head, hand, back, feet, charm) and shows up on your pet. "
                   "Consumables are used once. Sets of matching gear give bonuses and a title."))
    print("\n" + c("bold", "Gold") + " pays for the shop. Earn it from level-ups, quests, bosses, commits, "
          "the daily chest, and selling items.")
    print(c("dim", "  The forge melts " + ", ".join(f"{n} {r}" for r, n in items.FORGE_COST.items())
                   + " items into one of the next rarity."))
    print("\n" + c("bold", "Quests") + ": three daily quests and one weekly. One free reroll a day.")
    print("\n" + c("bold", "Bosses") + ": a failing test, build or lint run summons a monster with one HP per "
          "failure. Runs with fewer failures hit it; a clean run defeats it for XP, gold and a guaranteed drop.")
    print("\n" + c("bold", "PR dungeons") + ": `gh pr create` opens one. Each push is a room, each "
          "failing `gh pr checks` a trap; `gh pr merge` clears it, paying more the deeper it went.")
    print("\n" + c("bold", "Tech-debt raids") + ": your first commit of the week in a project summons a boss "
          "with one HP per TODO, FIXME, XXX or HACK. Commits that remove them strike it.")
    print("\n" + c("bold", "Your pet") + " evolves at levels " +
          ", ".join(f"{need} ({d.split()[-1]})" for need, _, d in rules.PET_STAGES[1:]) +
          ", wears your gear, and bonds with you over time. As a drake it takes the form of your top "
          "school, with a gift to match; a wyrm's gift is doubled.")
    print("\n" + c("dim", "Commands: claude-quest help"))


# ------------------------------------------------------------------ dispatch

READS = {"sheet", "bag", "loot", "inv", "inventory", "inspect", "quests", "shop", "boss", "titles",
         "achievements", "log", "guide", "pet", "dungeons", "dungeon", "raid", "raids"}


def main(argv):
    cmd = argv[0].lower() if argv else "sheet"
    args = argv[1:]
    if cmd in ("help", "-h", "--help"):
        print(__doc__.strip())
        return 0
    if cmd == "field":
        from .art import field_launcher
        field_launcher.field(args[0] if args else "start")
        return 0
    if cmd in ("enable", "disable", "status"):
        from . import setup
        return setup.command(cmd, args)
    if cmd == "reset":
        if args[:1] != ["--yes"]:
            print("This wipes your hero, bag and progress. Run `claude-quest reset --yes` to confirm.")
            return 1
        with store.Locked() as s:
            s.clear()
            s.update(store.fresh())
        print("Your hero has been reborn.")
        return 0

    from .hooks import deliver
    try:
        with store.Locked() as state:
            g = Game(state)
            g.tick()
            if cmd == "sheet":
                show_sheet(g)
            elif cmd in ("bag", "loot", "inv", "inventory"):
                show_bag(g)
            elif cmd == "inspect":
                show_item(g, " ".join(args))
            elif cmd == "equip":
                g.equip(" ".join(args))
            elif cmd in ("unequip", "remove"):
                g.unequip(" ".join(args))
            elif cmd == "use":
                g.use(" ".join(args))
            elif cmd == "sell":
                if args[:1] == ["dupes"]:
                    g.sell("dupes")
                else:
                    count = "1"
                    if len(args) > 1 and (args[-1].isdigit() or args[-1] == "all"):
                        count = args[-1]
                        args = args[:-1]
                    g.sell(" ".join(args), count)
            elif cmd == "forge":
                if not args:
                    print("🔥 The forge melts spare items into rarer ones:")
                    for r, n in items.FORGE_COST.items():
                        have = sum(len(es) for it, es in g.bag_groups() if it["rarity"] == r)
                        nxt = items.RARITIES[items.rarity_rank(r) + 1]
                        print(f"  {n} {r:<9} → 1 {nxt:<10} (you have {have})")
                    print(c("dim", "  claude-quest forge <rarity>. Spare copies are melted first; gear you wear never is."))
                else:
                    g.forge(args[0])
            elif cmd == "shop":
                show_shop(g)
            elif cmd == "buy":
                g.buy(" ".join(args))
            elif cmd == "quests":
                show_quests(g)
            elif cmd == "reroll":
                if not args or not args[0].isdigit():
                    raise GameError("Which quest? claude-quest reroll <n>, numbered as in `claude-quest quests`.")
                g.reroll(int(args[0]) - 1)
            elif cmd == "boss":
                show_boss(g)
            elif cmd in ("dungeons", "dungeon"):
                show_dungeons(g)
            elif cmd in ("raid", "raids"):
                show_raid(g)
            elif cmd == "pet":
                if args[:1] == ["name"]:
                    g.name_pet(" ".join(args[1:]))
                else:
                    show_pet(g)
            elif cmd == "name":
                g.name_pet(" ".join(args))
            elif cmd == "titles":
                show_titles(g)
            elif cmd == "title":
                g.set_title(" ".join(args))
            elif cmd == "achievements":
                show_achievements(g)
            elif cmd == "log":
                show_log(g, int(args[0]) if args and args[0].isdigit() else 25)
            elif cmd == "guide":
                show_guide(g)
            else:
                raise GameError(f"Unknown command '{cmd}'. Try `claude-quest help`.")
            g.finish(activity=False)
    except GameError as e:
        print(f"✋ {e}")
        return 1
    for line in g.msgs:
        print(line)
    if cmd not in READS:
        deliver(g.toasts)
    return 0
