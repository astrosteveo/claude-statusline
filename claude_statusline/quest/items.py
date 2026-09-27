"""Every item in the game: gear with passive bonuses, consumables, and gear sets.

Gear `fx` keys (all additive across gear, sets, buffs and bond):
    xp             +fraction of every XP gain
    xp_<school>    +fraction of XP from that school's tools (shell, edit, read, agent, web)
    commit_xp, push_xp, test_xp, prompt_xp    flat XP on those events
    luck           +fraction of loot drop chance
    fortune        shifts drops toward rarer items
    gold           +fraction of gold gains
    bounty         +fraction of boss rewards
    quest          +fraction of quest rewards
    dedupe         re-roll a drop you already own, once

Consumable `use` keys:
    buff + minutes + icon   a timed set of fx
    xp                      instant XP
    gamble = [chance, xp]   maybe XP
    treat                   pet bond
    guarantee = rarity      the next drop is at least this rare
    streak                  restores a broken streak
    crate = fortune         opens into a random item
    reroll                  new daily quests
    banish                  defeats the current boss outright
"""
import re

RARITIES = ["common", "uncommon", "rare", "epic", "legendary"]
RARITY_WEIGHT = {"common": 60, "uncommon": 25, "rare": 10, "epic": 4, "legendary": 1}
RARITY_ICON = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", "epic": "🟣", "legendary": "🟠"}
BUY_PRICE = {"common": 30, "uncommon": 90, "rare": 300, "epic": 900}
SELL_PRICE = {"common": 10, "uncommon": 30, "rare": 100, "epic": 300, "legendary": 1000}
FORGE_COST = {"common": 5, "uncommon": 4, "rare": 3, "epic": 3}
SLOTS = ["head", "hand", "back", "feet", "charm"]

ITEMS = {}


def _gear(id, name, rarity, slot, fx, flavor, visual, icon, set=None, drop=True, season=None):
    ITEMS[id] = {"id": id, "name": name, "rarity": rarity, "kind": "gear", "slot": slot,
                 "fx": fx, "flavor": flavor, "visual": visual, "icon": icon,
                 "set": set, "drop": drop, "season": season}


def _use(id, name, rarity, use, flavor, icon, drop=True, season=None):
    ITEMS[id] = {"id": id, "name": name, "rarity": rarity, "kind": "consumable",
                 "use": use, "flavor": flavor, "icon": icon, "drop": drop, "season": season}


# ---- head
_gear("paper_hat", "Paper Hat from the Standup", "common", "head", {"prompt_xp": 1},
      "Folded from yesterday's action items.", {"kind": "paper", "color": "#f4f1e8"}, "📰")
_gear("beanie", "Beanie of Late Nights", "common", "head", {"xp": 0.02},
      "Smells faintly of energy drinks.",
      {"kind": "beanie", "color": "#4a6fa5", "accent": "#f2f2f2"}, "🧢")
_gear("headphones", "Headphones of Deep Focus", "uncommon", "head", {"xp": 0.05},
      "Noise-cancelling. Slack-cancelling, too.",
      {"kind": "headphones", "color": "#303642", "accent": "#e05d5d"}, "🎧")
_gear("goggles", "Goggles of Coverage", "uncommon", "head", {"test_xp": 5},
      "Every untested line glows faintly red.",
      {"kind": "goggles", "color": "#6b4f2e", "accent": "#7fe0c9"}, "🥽", set="green_build")
_gear("crown_review", "Crown of the Code Reviewer", "rare", "head", {"xp_read": 0.15, "gold": 0.1},
      "LGTM, but with gravitas.", {"kind": "crown", "color": "#f2c14e", "accent": "#e05d8a"}, "👑")
_gear("helm_signed", "Helm of Signed Commits", "rare", "head", {"commit_xp": 10},
      "Verified. The little green badge is load-bearing.",
      {"kind": "helm", "color": "#b8c2cc", "accent": "#5fb35f"}, "🪖", set="version_control")
_gear("wizard_hat", "Wizard Hat of Many Pipes", "epic", "head", {"xp_shell": 0.2},
      "cat | grep | awk | sed | magic",
      {"kind": "wizard", "color": "#6c4bd1", "accent": "#ffd966"}, "🎩", set="terminal_wizard")
_gear("halo", "Halo of Zero Downtime", "legendary", "head", {"xp": 0.15, "luck": 0.1},
      "Five nines, worn with humility.", {"kind": "halo", "color": "#ffe27a", "glow": True}, "😇")

# ---- hand
_gear("rubber_duck", "Rubber Duck (squeaks)", "common", "hand", {"test_xp": 3, "bounty": 0.25},
      "Listens patiently while you explain the bug to yourself.",
      {"kind": "duck", "color": "#ffd84d", "accent": "#ff8c2b"}, "🦆")
_gear("dangling_pointer", "Dangling Pointer, leashed", "common", "hand", {"luck": 0.03},
      "Good boy. Points at nothing in particular.", {"kind": "pointer", "color": "#c9c9d6"}, "👉")
_gear("stack_stick", "Walking Stick of Stack Traces", "common", "hand", {"xp": 0.02},
      "Every knot is a frame you once stepped through.", {"kind": "stick", "color": "#8b5a2b"}, "🪵")
_gear("regex_wand", "Wand of Regex", "uncommon", "hand", {"xp_edit": 0.1},
      "^(?:magic)+$", {"kind": "wand", "color": "#3a2f4a", "accent": "#9be7ff"}, "🪄")
_gear("hotfix_hammer", "Hammer of Hotfixes", "rare", "hand", {"commit_xp": 8, "xp_edit": 0.05},
      "Friday, 4:55 pm. You know what to do.",
      {"kind": "hammer", "color": "#9aa3ad", "accent": "#8b5a2b"}, "🔨")
_gear("async_staff", "Staff of Async/Await", "rare", "hand", {"xp_agent": 0.2},
      "Returns a promise. Keeps it, eventually.",
      {"kind": "staff", "color": "#7a5230", "accent": "#b58cff", "glow": True}, "🔮")
_gear("blade_green_ci", "Blade of Green CI", "epic", "hand", {"test_xp": 15, "bounty": 0.5},
      "Forged in a pipeline that has never once been flaky.",
      {"kind": "sword", "color": "#5fdc6a", "accent": "#8b5a2b", "glow": True}, "✅", set="green_build")
_gear("excalibash", "Excalibash", "epic", "hand", {"xp_shell": 0.25},
      "Drawn from a stone labelled /bin.",
      {"kind": "sword", "color": "#7fd4ff", "accent": "#ffd966", "glow": True}, "🔱",
      set="terminal_wizard")

# ---- back
_gear("ticket_cape", "Cape of Closed Tickets", "common", "back", {"quest": 0.1},
      "Stitched from JIRA-1 through JIRA-1000.", {"kind": "cape", "color": "#c9a86a"}, "🧣")
_gear("rebase_cape", "Cape of Rebased History", "uncommon", "back", {"commit_xp": 5},
      "The past is whatever you say it is.", {"kind": "cape", "color": "#e0843a"}, "🧣",
      set="version_control")
_gear("tabs_backpack", "Backpack of Unlimited Tabs", "uncommon", "back", {"luck": 0.08},
      "Holds 347 browser tabs. You'll read them later.",
      {"kind": "backpack", "color": "#8a5a3c", "accent": "#d9b38c"}, "🎒")
_gear("zero_warnings_cloak", "Cloak of Zero Warnings", "rare", "back", {"xp_edit": 0.1, "test_xp": 5},
      "The compiler has nothing to say. Nothing at all.",
      {"kind": "cape", "color": "#2fb3a0"}, "🧥", set="green_build")
_gear("dotfiles_robe", "Robe of Dotfiles", "rare", "back", {"xp_shell": 0.1},
      "Hand-tuned since 2009. Do not touch the .zshrc.",
      {"kind": "cape", "color": "#3b2a6b", "accent": "#ffd966", "stars": True}, "🧥",
      set="terminal_wizard")
_gear("async_wings", "Wings of Async", "epic", "back", {"xp_agent": 0.25, "luck": 0.05},
      "They flap concurrently.", {"kind": "wings", "color": "#f5f0ff", "accent": "#c9b8ff"}, "🪶")

# ---- feet
_gear("mismatched_socks", "Mismatched Socks", "common", "feet", {"luck": 0.02, "xp": 0.01},
      "One tab, one space.", {"kind": "socks", "color": "#e05d5d", "accent": "#4a90e2"}, "🧦")
_gear("ff_boots", "Boots of Fast-Forward Merge", "uncommon", "feet", {"commit_xp": 5, "push_xp": 10},
      "No merge commits were harmed.", {"kind": "boots", "color": "#7a4a2a"}, "👢",
      set="version_control")
_gear("hot_reload_sneakers", "Sneakers of Hot Reload", "rare", "feet", {"xp_edit": 0.1},
      "Changes appear before you finish saving.",
      {"kind": "sneakers", "color": "#e0454f", "accent": "#ffffff"}, "👟")

# ---- charm
_gear("bent_semicolon", "Slightly Bent Semicolon", "common", "charm", {"xp_edit": 0.03},
      "Still terminates statements. Mostly.", {"kind": "amulet", "color": "#9aa3ad"}, "🔩")
_gear("tabs_and_spaces", "2 Tabs and 4 Spaces", "common", "charm", {"xp_edit": 0.02, "luck": 0.01},
      "A truce, worn around the neck.", {"kind": "amulet", "color": "#b5b5b5"}, "📏")
_gear("idempotence_amulet", "Amulet of Idempotence", "uncommon", "charm", {"gold": 0.1, "dedupe": 1},
      "Wearing it twice does nothing extra.", {"kind": "amulet", "color": "#4a90e2"}, "📿")
_gear("o1_ring", "Ring of O(1) Lookup", "rare", "charm", {"xp_read": 0.1, "luck": 0.05},
      "Finds what you need before you know you need it.", {"kind": "amulet", "color": "#f2c14e"}, "💍")
_gear("green_check_clover", "Clover of Green Checks", "rare", "charm", {"luck": 0.15},
      "Four leaves, four passing checks.", {"kind": "amulet", "color": "#5fdc6a"}, "🍀")
_gear("force_with_lease", "Sacred --force-with-lease", "legendary", "charm", {"xp": 0.1, "push_xp": 50},
      "Force, but considerate.", {"kind": "amulet", "color": "#ff9f1c", "glow": True}, "🔥",
      set="version_control")

# ---- consumables
_use("cookie", "Half-Eaten Cookie (session)", "common", {"treat": 3, "xp": 15},
     "Your pet's favourite. Expires when you close the tab.", "🍪")
_use("stale_cache", "Stale Cache Entry", "common", {"gamble": [0.5, 80]},
     "Might be valid. Might be from 2019.", "🎲")
_use("energy_drink", "Energy Drink (Warm)", "common",
     {"buff": {"xp": 0.25}, "minutes": 15, "icon": "⚡"}, "Tastes like deadlines.", "⚡")
_use("requeue_scroll", "Scroll of Re-Prioritization", "common", {"reroll": True},
     "The backlog is a suggestion.", "🔀")
_use("so_answer", "Stack Overflow Answer (Accepted)", "uncommon", {"xp": 150},
     "Marked as a duplicate, but correct.", "📗")
_use("cold_brew", "Flask of Cold Brew +2", "uncommon",
     {"buff": {"xp": 1.0}, "minutes": 30, "icon": "☕"}, "Double XP for half an hour. Jittery.", "☕")
_use("reflog_scroll", "Scroll of git reflog", "uncommon", {"streak": True},
     "Nothing is ever truly lost.", "📜")
_use("mystery_crate", "Mystery Crate (Unlabeled)", "uncommon", {"crate": 0.6},
     "Shipped from node_modules. Contents unknown.", "📦")
_use("lucky_coin", "Lucky Coin (Heads)", "rare",
     {"buff": {"luck": 1.0}, "minutes": 60, "icon": "🍀"}, "Both sides are heads. Don't ask.", "🪙")
_use("first_try_regex", "Regex That Works First Try", "rare", {"guarantee": "rare"},
     "Nobody will believe you.", "✨")
_use("refactor_tome", "Tome of Refactoring", "epic", {"xp": 1000},
     "Chapter 1: Extract Method. Chapter 2: Extract Method.", "📕")
_use("self_fixing_bug", "a Bug That Fixed Itself", "legendary", {"banish": True},
     "Nobody knows why. Nobody will ever know why.", "🐞")

# ---- the Hallowed Harvest (seasons.py): these drop only in late October
_gear("pumpkin_helm", "Jack-o'-Lantern Helm", "uncommon", "head", {"xp": 0.05, "luck": 0.03},
      "Carved with a merge conflict marker. Glows faintly when tests fail.",
      {"kind": "pumpkin", "color": "#ff8a1f", "accent": "#3f7a2a"}, "🎃", set="hallowed_harvest",
      season="halloween")
_gear("branch_broom", "Broom of Branch Sweeping", "rare", "hand", {"xp_shell": 0.1, "commit_xp": 5},
      "Sweeps away merged branches. Flies, if you believe in it.",
      {"kind": "staff", "color": "#7a4f2a", "accent": "#e0a030"}, "🧹", set="hallowed_harvest", season="halloween")
_gear("midnight_cloak", "Cloak of Midnight Deploys", "rare", "back", {"commit_xp": 8, "luck": 0.05},
      "Worn by those who ship at 23:59 on a Friday. Smells of rollbacks.",
      {"kind": "cape", "color": "#2d1f45", "accent": "#ff8a1f", "stars": True}, "🦇", set="hallowed_harvest",
      season="halloween")
_gear("last_resort_candle", "Candle of Last Resort", "epic", "charm", {"xp": 0.08, "luck": 0.1},
      "Lit when every other debugging idea has burned out.",
      {"kind": "amulet", "color": "#ffb347", "glow": True}, "🕯️", set="hallowed_harvest", season="halloween")
_use("fun_size_bar", "Fun-Size Candy Bar", "common", {"treat": 2, "xp": 30},
     "Technically a meal. Your pet disagrees.", "🍫", season="halloween")
_use("candy_corn", "Bag of Candy Corn", "uncommon", {"buff": {"luck": 0.5}, "minutes": 20, "icon": "🍬"},
     "Nobody admits to liking it. Everybody eats it.", "🍬", season="halloween")

SETS = {
    "version_control": {
        "name": "Keeper of History", "title": "Keeper of History",
        "pieces": ["helm_signed", "rebase_cape", "ff_boots", "force_with_lease"],
        "bonus": {2: {"commit_xp": 10}, 4: {"commit_xp": 30, "push_xp": 50}},
    },
    "green_build": {
        "name": "Guardian of Main", "title": "Guardian of Main",
        "pieces": ["goggles", "zero_warnings_cloak", "blade_green_ci"],
        "bonus": {2: {"test_xp": 10}, 3: {"bounty": 1.0}},
    },
    "hallowed_harvest": {
        "name": "Hallowed Harvest", "title": "the Haunted",
        "pieces": ["pumpkin_helm", "branch_broom", "midnight_cloak", "last_resort_candle"],
        "bonus": {2: {"luck": 0.05}, 4: {"xp": 0.1, "luck": 0.1}},
    },
    "terminal_wizard": {
        "name": "Archwizard of the Shell", "title": "Archwizard of the Shell",
        "pieces": ["wizard_hat", "dotfiles_robe", "excalibash"],
        "bonus": {2: {"xp_shell": 0.1}, 3: {"xp_shell": 0.3}},
    },
}

FX_TEXT = {
    "xp": "+{p}% XP", "xp_shell": "+{p}% shell XP", "xp_edit": "+{p}% editing XP",
    "xp_read": "+{p}% reading XP", "xp_agent": "+{p}% subagent XP", "xp_web": "+{p}% web XP",
    "commit_xp": "+{n} XP per commit", "push_xp": "+{n} XP per push",
    "test_xp": "+{n} XP per test run", "prompt_xp": "+{n} XP per prompt",
    "luck": "+{p}% loot chance", "fortune": "+{p}% rarer loot", "gold": "+{p}% gold",
    "bounty": "+{p}% boss rewards", "quest": "+{p}% quest rewards",
    "dedupe": "duplicate drops are re-rolled",
}


def fx_lines(fx):
    out = []
    for key, value in fx.items():
        tmpl = FX_TEXT.get(key, key + " {n}")
        out.append(tmpl.format(p=round(value * 100), n=round(value)))
    return out


def use_lines(use):
    out = []
    if "buff" in use:
        out.append(f"for {use['minutes']} min: " + ", ".join(fx_lines(use["buff"])))
    if "xp" in use:
        out.append(f"+{use['xp']} XP")
    if "gamble" in use:
        chance, xp = use["gamble"]
        out.append(f"{round(chance * 100)}% chance of +{xp} XP")
    if "treat" in use:
        out.append(f"+{use['treat']} pet bond")
    if "guarantee" in use:
        out.append(f"your next drop is {use['guarantee']} or better")
    if "streak" in use:
        out.append("restores a broken streak (or +25 XP per commit for an hour)")
    if "crate" in use:
        out.append("opens into a random item, luck on your side")
    if "reroll" in use:
        out.append("rerolls today's daily quests")
    if "banish" in use:
        out.append("defeats the current boss outright, full rewards (or +2500 XP)")
    return out


def describe(item):
    return fx_lines(item["fx"]) if item["kind"] == "gear" else use_lines(item["use"])


def _norm(name):
    name = re.sub(r"[`'\"]", "", name.lower()).strip()
    return re.sub(r"^(a|an|the) ", "", name)


_BY_NORM = {_norm(i["name"]): i["id"] for i in ITEMS.values()}


def by_name(name):
    """The id of an item from its display name, tolerating old spellings."""
    return _BY_NORM.get(_norm(name))


def droppable(rarity, season=None):
    """Items that can drop at `rarity`: the everyday ones, plus the season's while it lasts."""
    return [i for i in ITEMS.values() if i["rarity"] == rarity and i["drop"] and i.get("season") in (None, season)]


def seasonal(rarity, season):
    return [i for i in ITEMS.values() if i["rarity"] == rarity and i["drop"] and season and i.get("season") == season]


def rarity_rank(rarity):
    return RARITIES.index(rarity)
