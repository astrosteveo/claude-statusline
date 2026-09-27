"""Add up everything that modifies the game: gear, set bonuses, buffs, the pet's form and bond."""
from collections import defaultdict

from . import items, rules


def entry(state, uid):
    return next((e for e in state["bag"] if e["uid"] == uid), None)


def equipped_items(state):
    """{slot: item} for what is worn right now."""
    out = {}
    for slot, uid in state["equipped"].items():
        e = entry(state, uid)
        if e and e["id"] in items.ITEMS:
            out[slot] = items.ITEMS[e["id"]]
    return out


def active_sets(state):
    """[(set_id, pieces_worn, [bonus fx reached])] for sets with 2+ pieces on."""
    worn = {i["id"] for i in equipped_items(state).values()}
    out = []
    for set_id, spec in items.SETS.items():
        n = len(worn & set(spec["pieces"]))
        reached = [fx for need, fx in sorted(spec["bonus"].items()) if n >= need]
        if reached:
            out.append((set_id, n, reached))
    return out


def live_buffs(state, now):
    return [b for b in state["buffs"] if b["until"] > now]


def total(state, now):
    fx = defaultdict(float)

    def add(d):
        for k, v in d.items():
            fx[k] += v

    for item in equipped_items(state).values():
        add(item["fx"])
    for _, _, reached in active_sets(state):
        for bonus in reached:
            add(bonus)
    for buff in live_buffs(state, now):
        add(buff["fx"])
    add(rules.form_fx(state))
    tier, _ = rules.bond_level(state["pet"].get("bond", 0))
    fx["xp"] += 0.01 * tier
    return fx
