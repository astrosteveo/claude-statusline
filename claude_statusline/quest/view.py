"""A derived snapshot of the save, written beside it for the status line.

The status line renders from `state["view"]` so it never needs the game's
rules; only timestamps (buff expiry, the latest event) are left for it to
compare against the clock.
"""
import hashlib
import json
import time
from datetime import date

from . import effects, items, rules


def build(s, now=None):
    now = time.time() if now is None else now
    xp = s["xp"]
    level = rules.level_for(xp)
    lo, hi = rules.xp_for_level(level), rules.xp_for_level(level + 1)
    school = s.get("school") or {}
    top = max(school, key=school.get) if school else None
    stage, _ = rules.stage_for(level)
    form = rules.form_of(s)
    nxt = [(need, key) for need, key, _ in rules.PET_STAGES if need > level]
    worn = effects.equipped_items(s)
    gear = {slot: item["visual"] for slot, item in sorted(worn.items())}
    look = dict(gear, form=form[0]) if form else gear
    daily = s.get("daily", {}).get("quests", [])
    weekly = s.get("weekly", {}).get("quests", [])
    b = s.get("boss")
    tier, bond_name = rules.bond_level(s["pet"].get("bond", 0))
    from .game import streak_of
    return {
        "level": level,
        "rank": rules.rank_for(level),
        "title": s.get("title") or rules.rank_for(level),
        "xp": xp,
        "xp_in": xp - lo,
        "xp_need": hi - lo,
        "class": rules.SCHOOLS[top][0] if top else None,
        "class_icon": rules.SCHOOLS[top][1] if top else "",
        "gold": s.get("gold", 0),
        "bag": len(s.get("bag", [])),
        "stage": stage,
        "stage_name": rules.pet_description(s),
        "form": form[0] if form else None,
        "form_icon": form[1] if form else "",
        "next_stage": nxt[0][1] if nxt else None,
        "next_stage_level": nxt[0][0] if nxt else None,
        "pet_name": s["pet"].get("name"),
        "bond": bond_name,
        "bond_tier": tier,
        "streak": streak_of(s.get("days", []), date.fromtimestamp(now)),
        "gear": gear,
        "gear_sig": hashlib.sha1(json.dumps(look, sort_keys=True).encode()).hexdigest()[:10],
        "buffs": [{"icon": x["icon"], "name": x["name"], "until": x["until"]}
                  for x in effects.live_buffs(s, now)],
        "daily_done": sum(1 for q in daily if q["done"]),
        "daily_total": len(daily),
        "daily": [{"title": q["title"], "text": q["text"], "progress": q["progress"], "goal": q["goal"],
                   "done": q["done"]} for q in daily],
        "weekly": [{"title": q["title"], "progress": q["progress"], "goal": q["goal"], "done": q["done"]}
                   for q in weekly],
        "boss": {"icon": b["icon"], "name": b["name"], "hp": b["hp"], "max_hp": b["max_hp"],
                 "kind": b["kind"], "project": b["project"]} if b else None,
        "dungeons": [{"project": d["project"], "number": d["number"], "name": d["name"], "rooms": d["rooms"],
                      "traps": d["traps"], "failing": d.get("failing", 0)}
                     for d in sorted(s.get("dungeons", {}).values(), key=lambda d: -d["opened"])],
        "raids": {p: {"name": r["name"], "hp": r["hp"], "max_hp": r["max_hp"], "defeated": r["defeated"]}
                  for p, r in s.get("raids", {}).items()},
        "achievements": len(s.get("achievements", {})),
        "rarest": max((items.rarity_rank(items.ITEMS[e["id"]]["rarity"]) for e in s.get("bag", [])
                       if e["id"] in items.ITEMS), default=None),
    }
