"""The game engine. Every change to a save goes through a Game.

A Game wraps one loaded state for one moment. Handlers (hooks) and player
actions (the CLI) call its methods; it collects the lines to show, the
desktop toasts to send, and the pet's reaction, which the caller delivers
after the save is written.
"""
import random
import re
import time
from datetime import date, datetime, timedelta

from . import boss, dungeon, effects, items, quests, raid, rules

ACHIEVEMENTS = {
    # key: (name, description, title granted)
    "first_blood": ("First Blood", "Make your first edit under Claude Quest", None),
    "committed": ("Commitment Issues Resolved", "Make a git commit", None),
    "ten_commits": ("Serial Committer", "Make 10 git commits", None),
    "pusher": ("Ship It", "Push to a remote", None),
    "polite": ("Well Raised", "Say please or thanks", "the Polite"),
    "night_owl": ("Night Owl", "Prompt between 1am and 5am", "Night Owl"),
    "early_bird": ("Early Bird", "Prompt between 5am and 7am", "Early Bird"),
    "summoner": ("Call for Backup", "Spawn a subagent", None),
    "legion": ("Legion", "Spawn 50 subagents", "Lord of Legions"),
    "centurion": ("Centurion", "100 tool calls in one session", None),
    "marathon": ("Marathon", "500 tool calls in one session", "the Tireless"),
    "streak3": ("On a Roll", "Play 3 days in a row", None),
    "streak7": ("Habit Formed", "Play 7 days in a row", None),
    "streak30": ("Unstoppable", "Play 30 days in a row", "the Unstoppable"),
    "hoarder": ("Hoarder", "Hold 10 items at once", None),
    "legendary": ("Touched by Legend", "Find a legendary item", "Touched by Legend"),
    "tester": ("Trust but Verify", "Run a test suite", None),
    "rm_rf": ("Living Dangerously", "Run rm -rf (hopefully on purpose)", "the Reckless"),
    "lvl10": ("Double Digits", "Reach level 10", None),
    "lvl25": ("Quarter Century", "Reach level 25", None),
    "lvl50": ("Half Way to Ascension", "Reach level 50", None),
    "lvl75": ("Mythic Status", "Reach level 75", None),
    "lvl100": ("Ascended", "Reach level 100", "the Ascended"),
    "first_quest": ("Adventurer", "Complete a daily quest", None),
    "quest25": ("Quest Master", "Complete 25 daily quests", "Quest Master"),
    "weekly": ("Week Warrior", "Complete a weekly quest", None),
    "all_daily": ("Clean Sweep", "Finish all three daily quests in one day", None),
    "first_boss": ("Bug Hunter", "Defeat your first boss", None),
    "slayer10": ("Bug Slayer", "Defeat 10 bosses", "Bug Slayer"),
    "clean_kill": ("Clean Kill", "Defeat a boss on your very next run", None),
    "dressed": ("Dressed for Success", "Equip an item", None),
    "full_kit": ("Fully Kitted", "Fill all five gear slots", None),
    "set_bonus": ("Matching Outfit", "Complete a gear set", None),
    "first_use": ("Try It Out", "Use an item", None),
    "alchemist": ("Alchemist", "Forge an item", None),
    "shopper": ("Retail Therapy", "Buy something from the shop", None),
    "rich": ("Dragon's Hoard", "Hold 1000 gold", None),
    "mogul": ("Merchant Prince", "Earn 5000 gold in total", "Merchant Prince"),
    "named": ("Best Friends", "Give your pet a name", None),
    "soulbound": ("Soulbound", "Reach the highest bond with your pet", "Soulbound"),
    "evolved": ("Taking Shape", "Your pet takes its drake form", None),
    "delver": ("Dungeon Crawler", "Clear a PR dungeon by merging it", None),
    "deep_delve": ("Deep Delver", "Clear a PR dungeon of 5 rooms or more", "the Delver"),
    "raider": ("Debt Collector", "Damage a tech-debt raid boss", None),
    "debt_free": ("Debt Free", "Defeat a tech-debt raid boss", "the Solvent"),
}

PRIORITY = {"victory": 90, "dungeon": 65, "raid": 65, "levelup": 80, "boss": 70, "quest": 60, "achievement": 42,
            "chest": 35, "eat": 30, "strut": 30, "use": 30, "hit": 20, "escape": 15}
DROP_SOURCES = ["a treasure chest", "under your keyboard", "a forgotten branch", "the dungeon floor",
                "a stale pull request", "deep in node_modules", "the bottom of the backlog",
                "a git stash from 2023", "the recycle bin", "behind a TODO comment"]
_GIT = re.compile(r"^git\s+(?:(?:-C|-c|--git-dir|--work-tree)\s+\S+\s+|--?\S+\s+)*(\w[\w-]*)")


class GameError(Exception):
    """A player action that cannot happen, with the reason to show them."""


def streak_of(days, today):
    ds = sorted({date.fromisoformat(d) for d in days}, reverse=True)
    if not ds:
        return 0
    cur = today if ds[0] == today else today - timedelta(days=1)
    n = 0
    for d in ds:
        if d == cur:
            n += 1
            cur -= timedelta(days=1)
        elif d < cur:
            break
    return n


def git_subcommands(command):
    for seg in boss.segments(command):
        m = _GIT.match(seg)
        if m:
            yield m.group(1)


class Game:
    def __init__(self, state, now=None, rng=None):
        self.s = state
        self.now = time.time() if now is None else now
        self.today = date.fromtimestamp(self.now)
        self.rng = rng or random.Random()
        self.msgs = []
        self.toasts = []
        self.reaction = None
        self._fx = None

    # ------------------------------------------------------------ plumbing

    @property
    def fx(self):
        if self._fx is None:
            self._fx = effects.total(self.s, self.now)
        return self._fx

    def refresh_fx(self):
        self._fx = None

    def stamp(self):
        return datetime.fromtimestamp(self.now).isoformat(timespec="seconds")

    def say(self, text):
        self.msgs.append(text)

    def log(self, kind, text):
        self.s["log"].append({"at": self.now, "kind": kind, "text": text})

    def announce(self, kind, text, toast=None, sound=None, priority=None):
        """Show a line, log it, maybe toast it, and offer it as the pet's reaction."""
        self.say(text)
        self.log(kind, text.split("\n")[0])
        if toast:
            self.toasts.append((toast[0], toast[1], sound))
        pri = PRIORITY.get(kind, 10) if priority is None else priority
        if self.reaction is None or pri >= self.reaction[0]:
            self.reaction = (pri, kind, text.split("\n")[0])

    def finish(self, activity=True):
        if self.reaction:
            _, kind, text = self.reaction
            self.s["last_event"] = {"text": text, "at": self.now, "kind": kind}
        if activity:
            self.s["last_activity"] = self.now

    def tick(self):
        """Housekeeping before anything else: buffs expire, days roll, bosses flee."""
        s = self.s
        for b in s["buffs"]:
            if b["until"] <= self.now:
                self.say(f"{b['icon']} {b['name']} wore off.")
        s["buffs"] = effects.live_buffs(s, self.now)
        quests.ensure(s, self.today)
        if not s["pet"].get("form") and rules.stage_for(self.level())[0] in rules.FORM_STAGES:
            gift = self._take_form()
            self.announce("levelup", f"✨ Your pet settles into its form: {rules.pet_description(s)}.{gift}")
        b = s.get("boss")
        if b and self.now - b["spawned"] > boss.ESCAPE_AFTER:
            self.announce("escape", f"{b['icon']} The {b['name']} slipped away while you were gone.")
            s["boss"] = None
        for k, d in list(s["dungeons"].items()):
            if self.now - d["opened"] > dungeon.COLLAPSE_AFTER:
                del s["dungeons"][k]
                self.announce("escape", f"{dungeon.ICON} The {d['name']} (#{d['number']}) crumbled while "
                                        "nobody merged it.")
        week = quests.week_of(self.today)
        for project, r in list(s["raids"].items()):
            if r["week"] != week:
                del s["raids"][project]
        self.refresh_fx()

    # ------------------------------------------------------------ progression

    def level(self):
        return rules.level_for(self.s["xp"])

    def gain_xp(self, base, school=None, flat=0):
        fx = self.fx
        mult = 1 + fx.get("xp", 0) + (fx.get(f"xp_{school}", 0) if school else 0)
        amount = round(base * mult + flat)
        if amount <= 0:
            return 0
        before = self.level()
        self.s["xp"] += amount
        after = self.level()
        if after > before:
            self._level_up(before, after)
        self.bump("xp_gained", amount)
        return amount

    def _level_up(self, before, after):
        gold = self.gain_gold(20 * after)
        rank = rules.rank_for(after)
        text = f"⬆️  LEVEL UP! You are now level {after}, {rank}. (+{gold} gold)"
        was, now = rules.stage_for(before), rules.stage_for(after)
        if was[0] != now[0]:
            gift = self._take_form()
            text += f"\n✨ Your pet evolved into {rules.pet_description(self.s)}!{gift}"
        self.announce("levelup", text, toast=(f"⬆️ Level {after}!", rank), sound="service-login")
        for need, key in ((10, "lvl10"), (25, "lvl25"), (50, "lvl50"), (75, "lvl75"), (100, "lvl100")):
            if after >= need:
                self.unlock(key)

    def _take_form(self):
        """Settle the pet's form on reaching a drake: the school you use most, for good.
        Returns the words describing its gift, or '' when nothing changed."""
        pet = self.s["pet"]
        if pet.get("form") or rules.stage_for(self.level())[0] not in rules.FORM_STAGES:
            return ""
        form = rules.form_for(rules.top_school(self.s.get("school"))) or rules.FORMS["agent"][0]
        pet["form"] = form
        self.refresh_fx()
        icon, fx = rules.FORMS[rules.FORM_BY_KEY[form]][1:]
        self.unlock("evolved")
        return f" {icon} Its gift: {'; '.join(items.fx_lines(fx))}."

    def gain_gold(self, amount):
        amount = round(amount * (1 + self.fx.get("gold", 0)))
        if amount <= 0:
            return 0
        self.s["gold"] += amount
        self.s["counters"]["gold_earned"] += amount
        if self.s["gold"] >= 1000:
            self.unlock("rich")
        if self.s["counters"]["gold_earned"] >= 5000:
            self.unlock("mogul")
        return amount

    def bump(self, counter, n=1):
        self.s["counters"][counter] = self.s["counters"].get(counter, 0) + n
        for q in quests.progress(self.s, counter, n):
            self._complete_quest(q)

    def _complete_quest(self, q):
        mult = 1 + self.fx.get("quest", 0)
        xp = self.gain_xp(q["xp"] * mult)
        gold = self.gain_gold(q["gold"] * mult)
        what = "Weekly quest" if q.get("weekly") else "Quest"
        self.announce("quest", f"📜 {what} complete: {q['title']} ({q['text']}). +{xp} XP, +{gold} gold",
                      toast=(f"📜 {what} complete!", q["title"]), sound="complete")
        if q.get("weekly"):
            self.unlock("weekly")
            self.roll_loot(1.0, fortune=1.0, source="your weekly quest")
            return
        self.unlock("first_quest")
        self.bump("quests_done")
        if self.s["counters"]["quests_done"] >= 25:
            self.unlock("quest25")
        daily = self.s["daily"].get("quests", [])
        if daily and all(d["done"] for d in daily):
            self.unlock("all_daily")
            bonus = self.gain_gold(50)
            self.say(f"🌟 All daily quests done! Bonus +{bonus} gold.")

    def unlock(self, key):
        if key in self.s["achievements"] or key not in ACHIEVEMENTS:
            return
        self.s["achievements"][key] = self.stamp()
        name, desc, title = ACHIEVEMENTS[key]
        text = f"🏆 Achievement unlocked: {name}. {desc}"
        if title:
            self.grant_title(title)
            text += f" (new title: {title})"
        self.announce("achievement", text, toast=(f"🏆 {name}", desc), sound="complete")

    def grant_title(self, title):
        if title not in self.s["titles"]:
            self.s["titles"].append(title)

    def streak(self):
        return streak_of(self.s["days"], self.today)

    def record_day(self):
        """Mark today as played. True on the first event of a new day."""
        today = self.today.isoformat()
        if today in self.s["days"]:
            return False
        if self.s["days"]:
            last = date.fromisoformat(max(self.s["days"]))
            if (self.today - last).days > 1:
                length = streak_of(self.s["days"], last)
                if length >= 2:
                    self.s["broken_streak"] = {"length": length, "last": last.isoformat()}
        self.s["days"] = sorted(set(self.s["days"]) | {today})[-400:]
        self.s["pet"]["bond"] = self.s["pet"].get("bond", 0) + 1
        self._check_bond()
        n = self.streak()
        for need, key in ((3, "streak3"), (7, "streak7"), (30, "streak30")):
            if n >= need:
                self.unlock(key)
        return True

    def _check_bond(self):
        tier, _ = rules.bond_level(self.s["pet"]["bond"])
        if tier == len(rules.BOND_LEVELS) - 1:
            self.unlock("soulbound")

    # ------------------------------------------------------------ loot

    def owns(self, item_id):
        return any(e["id"] == item_id for e in self.s["bag"])

    def roll_rarity(self, fortune=0.0, minimum=None):
        f = fortune + self.fx.get("fortune", 0)
        floor = items.rarity_rank(minimum) if minimum else 0
        weights = [items.RARITY_WEIGHT[r] * (1 + f) ** i if i >= floor else 0
                   for i, r in enumerate(items.RARITIES)]
        return self.rng.choices(items.RARITIES, weights)[0]

    def roll_loot(self, chance, fortune=0.0, source=None):
        if chance < 1 and self.rng.random() > chance * (1 + self.fx.get("luck", 0)):
            return None
        minimum = self.s["charges"].pop("guarantee", None)
        rarity = self.roll_rarity(fortune, minimum)
        item = self.rng.choice(items.droppable(rarity))
        if self.fx.get("dedupe") and self.owns(item["id"]):
            item = self.rng.choice(items.droppable(rarity))
        return self.grant(item["id"], source or self.rng.choice(DROP_SOURCES))

    def grant(self, item_id, source, found=True):
        item = items.ITEMS[item_id]
        entry = {"uid": self.s["next_uid"], "id": item_id, "at": self.stamp(), "from": source}
        self.s["next_uid"] += 1
        self.s["bag"].append(entry)
        rank = items.rarity_rank(item["rarity"])
        icon = items.RARITY_ICON[item["rarity"]]
        big = rank >= 3
        self.announce("loot", f"{icon} Loot! {item['icon']} {item['name']} ({item['rarity']}), found in {source}.",
                      toast=(f"{icon} {item['rarity'].title()} loot!", item["name"]) if big else None,
                      sound="bell" if big else None, priority=40 + 5 * rank)
        if found:
            self.bump("items_found")
        if len(self.s["bag"]) >= 10:
            self.unlock("hoarder")
        if item["rarity"] == "legendary":
            self.unlock("legendary")
        return entry

    # ------------------------------------------------------------ hook events

    def session_start(self):
        self.record_day()
        self.daily_chest()

    def daily_chest(self):
        today = self.today.isoformat()
        if self.s["daily"].get("chest") == today:
            return
        self.s["daily"]["chest"] = today
        gold = self.gain_gold(25 + 5 * min(self.streak(), 15))
        self.announce("chest", f"📦 Daily chest opened: +{gold} gold.")
        self.roll_loot(rules.CHEST_LOOT_CHANCE, source="the daily chest")

    def prompt(self, text):
        self.record_day()
        self.daily_chest()
        low = (text or "").lower()
        self.bump("prompts")
        if re.search(r"\b(please|pls|thanks|thank you|thx|ty)\b", low):
            self.unlock("polite")
            self.bump("thanks")
        hour = datetime.fromtimestamp(self.now).hour
        if 1 <= hour < 5:
            self.unlock("night_owl")
        elif 5 <= hour < 7:
            self.unlock("early_bird")
        self.gain_xp(rules.PROMPT_XP, flat=self.fx.get("prompt_xp", 0))
        self.s["last_prompt"] = self.now

    def tool(self, event, failed=False):
        self.record_day()
        self.daily_chest()
        name = event.get("tool_name", "")
        base = rules.base_tool(name)
        school = rules.school_of(name)
        if school:
            self.s["school"][school] = self.s["school"].get(school, 0) + 1

        sid = event.get("session_id", "?")
        sessions = self.s["sessions"]
        sessions[sid] = sessions.get(sid, 0) + 1
        for k in list(sessions)[:-20]:
            del sessions[k]
        if sessions[sid] >= 100:
            self.unlock("centurion")
        if sessions[sid] >= 500:
            self.unlock("marathon")

        if base in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            self.bump("edits")
            self.unlock("first_blood")
        elif base in ("Read", "Grep", "Glob"):
            self.bump("reads")
        elif base in ("WebSearch", "WebFetch"):
            self.bump("web")
        elif base == "Agent":
            self.bump("agents")
            self.unlock("summoner")
            if self.s["counters"]["agents"] >= 50:
                self.unlock("legion")

        flat = 0
        if base == "Bash":
            self.bump("shell")
            flat = self._shell(event, failed)
        self.gain_xp(rules.tool_xp(name), school, flat)
        self.roll_loot(rules.TOOL_LOOT_CHANCE)
        self.s["last_tool"] = self.now

    def _shell(self, event, failed):
        tin = event.get("tool_input") or {}
        cmd = tin.get("command", "") or ""
        resp = event.get("tool_response")
        if isinstance(resp, dict) and resp.get("interrupted"):
            return 0
        if failed:
            out = str(event.get("error", ""))
        elif isinstance(resp, dict):
            out = f"{resp.get('stdout', '')}\n{resp.get('stderr', '')}"
        else:
            out = str(resp or "")
        fx = self.fx
        flat = 0
        subs = set(git_subcommands(cmd))
        if not failed and "commit" in subs:
            flat += rules.COMMIT_XP + fx.get("commit_xp", 0)
            self.gain_gold(rules.COMMIT_GOLD)
            self.bump("commits")
            self.unlock("committed")
            if self.s["counters"]["commits"] >= 10:
                self.unlock("ten_commits")
        project = (event.get("cwd") or "").rstrip("/").rsplit("/", 1)[-1] or "?"
        if not failed and "push" in subs:
            flat += rules.PUSH_XP + fx.get("push_xp", 0)
            self.gain_gold(rules.PUSH_GOLD)
            self.bump("pushes")
            self.unlock("pusher")
            self.dungeon_push(project)
        if not failed and "commit" in subs:
            self.raid_commit(project, raid.count_debt(event.get("cwd")))
        for verb, rest in dungeon.commands(boss.segments(cmd)):
            self.dungeon_command(verb, rest, project, out, failed)
        if re.search(r"\brm\s+-(?:rf|fr)\b", cmd):
            self.unlock("rm_rf")

        kind = boss.classify(cmd)
        if kind:
            if kind == "test":
                self.bump("tests")
                flat += rules.TEST_XP + fx.get("test_xp", 0)
                self.unlock("tester")
            failures = boss.count_failures(out)
            if failed or (failures or 0) > 0:
                self.boss_failure(kind, project, failures)
            else:
                self.boss_cleared(kind, project)
        return flat

    def stop(self):
        self.record_day()
        self.daily_chest()
        self.s["last_stop"] = self.now
        self.roll_loot(rules.STOP_LOOT_CHANCE)

    # ------------------------------------------------------------ bosses

    def boss_failure(self, kind, project, failures):
        b = self.s.get("boss")
        if not b:
            b = boss.spawn(kind, project, failures, self.now, self.rng)
            self.s["boss"] = b
            self.announce("boss", f"{b['icon']} A wild {b['name']} appears in {project}! {b['hp']} HP. "
                                  f"Get the {boss.KIND_NOUN[kind]} passing to defeat it.",
                          toast=(f"{b['icon']} {b['name']} appears!", f"{b['hp']} HP, in {project}"),
                          sound="dialog-warning")
            return
        if b["kind"] != kind or b["project"] != project:
            return
        b["attempts"] += 1
        if not failures:
            return
        n = max(1, min(boss.MAX_HP, failures))
        if n < b["hp"]:
            self.announce("hit", f"⚔️  You hit the {b['name']} for {b['hp'] - n}! {n}/{b['max_hp']} HP left.")
            b["hp"] = n
        elif n > b["hp"]:
            b["hp"] = n
            b["max_hp"] = max(b["max_hp"], n)
            self.announce("hit", f"🩸 The {b['name']} grows stronger! {n} HP.")

    def boss_cleared(self, kind, project):
        b = self.s.get("boss")
        if b and b["kind"] == kind and b["project"] == project:
            self.defeat_boss(b)

    def defeat_boss(self, b, banished=False):
        self.s["boss"] = None
        bounty = 1 + self.fx.get("bounty", 0)
        xp = self.gain_xp((30 * b["max_hp"] + 5 * self.level()) * bounty)
        gold = self.gain_gold((12 * b["max_hp"] + 10) * bounty)
        verb = "banished" if banished else "defeated"
        self.announce("victory", f"⚔️  You {verb} the {b['name']}! +{xp} XP, +{gold} gold",
                      toast=(f"⚔️ {b['name']} {verb}!", f"+{xp} XP, +{gold} gold"), sound="complete")
        self.bump("bosses")
        self.unlock("first_boss")
        if self.s["counters"]["bosses"] >= 10:
            self.unlock("slayer10")
        if b["attempts"] <= 1 and not banished:
            self.unlock("clean_kill")
        self.roll_loot(1.0, fortune=0.5 + 0.1 * b["max_hp"], source=f"the {b['name']}'s hoard")

    # ------------------------------------------------------------ PR dungeons

    def dungeon_command(self, verb, rest, project, out, failed):
        dungeons = self.s["dungeons"]
        if verb == "create":
            number = None if failed else dungeon.url_number(out)
            if number is None or dungeon.key(project, number) in dungeons:
                return
            d = dungeon.open_(project, number, self.now, self.rng)
            dungeons[dungeon.key(project, number)] = d
            for k in sorted(dungeons, key=lambda k: dungeons[k]["opened"])[:-dungeon.KEEP]:
                del dungeons[k]
            self.announce("dungeon", f"{dungeon.ICON} PR #{number} opens the {d['name']} in {project}. "
                                     "Merge it to clear the dungeon; every push is another room.")
            return
        number = dungeon.number_in(rest)
        d = dungeon.find(dungeons, project, number)
        if verb == "checks":
            if not d:
                return
            n = dungeon.failing_checks(out)
            if n and not d.get("failing"):
                d["traps"] += 1
                self.announce("hit", f"🪤 A trap in the {d['name']}! {n} check{'s' if n != 1 else ''} "
                                     f"failing on #{d['number']}.")
            d["failing"] = n
        elif verb == "close" and not failed and d:
            del dungeons[dungeon.key(d["project"], d["number"])]
            self.announce("escape", f"{dungeon.ICON} You left the {d['name']} (#{d['number']}) unexplored.")
        elif verb == "merge" and not failed and "--auto" not in rest:
            if d:
                del dungeons[dungeon.key(d["project"], d["number"])]
            else:
                d = {"name": "an uncharted dungeon", "number": number or "?", "rooms": 1, "traps": 0}
            self.clear_dungeon(d)

    def dungeon_push(self, project):
        d = dungeon.find(self.s["dungeons"], project)
        if d:
            d["rooms"] += 1

    def clear_dungeon(self, d):
        xp, gold, fortune = dungeon.rewards(d, self.level())
        xp, gold = self.gain_xp(xp), self.gain_gold(gold)
        depth = f"{d['rooms']} room{'s' if d['rooms'] != 1 else ''}" + \
            (f", {d['traps']} trap{'s' if d['traps'] != 1 else ''}" if d["traps"] else "")
        self.announce("victory", f"{dungeon.ICON} PR #{d['number']} merged: you cleared the {d['name']} "
                                 f"({depth}). +{xp} XP, +{gold} gold",
                      toast=(f"{dungeon.ICON} Dungeon cleared!", f"PR #{d['number']}, {depth}"), sound="complete")
        self.bump("dungeons")
        self.unlock("delver")
        if d["rooms"] >= 5:
            self.unlock("deep_delve")
        self.roll_loot(1.0, fortune=fortune, source=f"the {d['name']}")

    # ------------------------------------------------------------ tech-debt raids

    def raid_commit(self, project, debt):
        if debt is None:
            return
        raids = self.s["raids"]
        r = raids.get(project)
        if not r:
            if debt <= 0:
                return
            raids[project] = r = raid.summon(project, quests.week_of(self.today), debt, self.rng)
            self.announce("raid", f"{raid.ICON} The {r['name']} rises from {project}'s backlog: "
                                  f"{debt} TODOs and FIXMEs. Commits that remove them strike it.",
                          toast=(f"{raid.ICON} {r['name']} rises!", f"{debt} HP, in {project}"),
                          sound="dialog-warning")
            return
        if r["defeated"]:
            return
        r["hp"] = debt
        r["max_hp"] = max(r["max_hp"], debt)
        hit = r["low"] - debt
        if hit <= 0:
            return
        r["low"] = debt
        self.unlock("raider")
        if debt == 0:
            r["defeated"] = True
            xp, gold, fortune = raid.rewards(r, self.level())
            xp, gold = self.gain_xp(xp), self.gain_gold(gold)
            self.announce("victory", f"{raid.ICON} The {r['name']} is slain: {project} is debt-free! "
                                     f"+{xp} XP, +{gold} gold",
                          toast=(f"{raid.ICON} {r['name']} slain!", f"{project} is debt-free"), sound="complete")
            self.bump("raids")
            self.unlock("debt_free")
            self.roll_loot(1.0, fortune=fortune, source=f"the {r['name']}'s hoard")
            return
        xp = self.gain_xp(15 * min(hit, 50))
        gold = self.gain_gold(2 * min(hit, 50))
        self.announce("raid", f"⚔️  You strike the {r['name']} for {hit}! {debt}/{r['max_hp']} HP left. "
                              f"+{xp} XP, +{gold} gold")

    # ------------------------------------------------------------ player actions

    def bag_groups(self):
        """Unequipped items, stacked by kind, in the order `bag` numbers them."""
        worn = set(self.s["equipped"].values())
        groups = {}
        for e in self.s["bag"]:
            if e["uid"] not in worn and e["id"] in items.ITEMS:
                groups.setdefault(e["id"], []).append(e)
        order = sorted(groups, key=lambda i: (-items.rarity_rank(items.ITEMS[i]["rarity"]),
                                              items.ITEMS[i]["kind"] != "gear", items.ITEMS[i]["name"]))
        return [(items.ITEMS[i], groups[i]) for i in order]

    def find(self, query, include_worn=False):
        """An item (and one of its bag entries) from a bag number or part of its name."""
        query = (query or "").strip()
        if not query:
            raise GameError("Which item? Give its number from `claude-quest bag` or part of its name.")
        groups = self.bag_groups()
        if query.isdigit():
            i = int(query) - 1
            if 0 <= i < len(groups):
                return groups[i][0], groups[i][1][0]
            raise GameError(f"There is no item #{query} in your bag.")
        pool = [(item, entries[0]) for item, entries in groups]
        if include_worn:
            for slot, item in effects.equipped_items(self.s).items():
                pool.append((item, effects.entry(self.s, self.s["equipped"][slot])))
        q = items._norm(query)
        exact = [p for p in pool if items._norm(p[0]["name"]) == q]
        if exact:
            return exact[0]
        words = q.split()
        hits = [p for p in pool if all(w in items._norm(p[0]["name"]) for w in words)]
        ids = {p[0]["id"] for p in hits}
        if len(ids) == 1:
            return hits[0]
        if not hits:
            raise GameError(f"Nothing in your bag matches '{query}'.")
        names = ", ".join(sorted({p[0]["name"] for p in hits}))
        raise GameError(f"'{query}' could be: {names}. Be more specific.")

    def equip(self, query):
        item, entry = self.find(query)
        if item["kind"] != "gear":
            raise GameError(f"{item['name']} isn't something you wear. Try `use`.")
        slot = item["slot"]
        old = effects.entry(self.s, self.s["equipped"].get(slot))
        self.s["equipped"][slot] = entry["uid"]
        self.refresh_fx()
        swap = f" (back in the bag: {items.ITEMS[old['id']]['name']})" if old else ""
        self.announce("strut", f"{item['icon']} Equipped {item['name']} ({slot}){swap}. "
                               + "; ".join(items.describe(item)))
        self.unlock("dressed")
        if len(self.s["equipped"]) >= len(items.SLOTS):
            self.unlock("full_kit")
        for set_id, n, _ in effects.active_sets(self.s):
            spec = items.SETS[set_id]
            if n == len(spec["pieces"]):
                self.unlock("set_bonus")
                if spec["title"] not in self.s["titles"]:
                    self.grant_title(spec["title"])
                    self.say(f"👑 Set complete: {spec['name']}! New title: {spec['title']}.")
        return item

    def unequip(self, query):
        query = (query or "").strip().lower()
        slot = query if query in items.SLOTS else None
        if not slot:
            item, entry = self.find(query, include_worn=True)
            slot = next((s for s, uid in self.s["equipped"].items() if uid == entry["uid"]), None)
            if not slot:
                raise GameError(f"You aren't wearing {item['name']}.")
        uid = self.s["equipped"].pop(slot, None)
        if uid is None:
            raise GameError(f"Nothing is equipped in your {slot} slot.")
        item = items.ITEMS[effects.entry(self.s, uid)["id"]]
        self.refresh_fx()
        self.say(f"{item['icon']} Took off {item['name']}.")
        return item

    def remove(self, entry):
        self.s["bag"] = [e for e in self.s["bag"] if e["uid"] != entry["uid"]]
        for slot, uid in list(self.s["equipped"].items()):
            if uid == entry["uid"]:
                del self.s["equipped"][slot]
        self.refresh_fx()

    def use(self, query):
        item, entry = self.find(query)
        if item["kind"] != "consumable":
            raise GameError(f"{item['name']} is gear. Try `equip`.")
        use = item["use"]
        s = self.s
        if "banish" in use and not s.get("boss"):
            pass  # falls back to XP below
        self.remove(entry)
        lines = []
        kind = "use"
        if "buff" in use:
            until = self.now + use["minutes"] * 60
            live = next((b for b in s["buffs"] if b["id"] == item["id"]), None)
            if live:
                live["until"] += use["minutes"] * 60
                lines.append(f"{use['icon']} {item['name']} extended: {round((live['until'] - self.now) / 60)} min left.")
            else:
                s["buffs"].append({"id": item["id"], "name": item["name"], "icon": use["icon"],
                                   "fx": use["buff"], "until": until})
                lines.append(f"{use['icon']} {item['name']}: " + ", ".join(items.fx_lines(use["buff"]))
                             + f" for {use['minutes']} min.")
            self.refresh_fx()
        if "treat" in use:
            s["pet"]["bond"] = s["pet"].get("bond", 0) + use["treat"]
            _, tier = rules.bond_level(s["pet"]["bond"])
            lines.append(f"🍪 {self.pet_name()} munches happily. Bond +{use['treat']} ({tier}).")
            self._check_bond()
            kind = "eat"
        if "guarantee" in use:
            s["charges"]["guarantee"] = use["guarantee"]
            lines.append(f"✨ Your next drop will be {use['guarantee']} or better.")
        if "streak" in use:
            lines.append(self._restore_streak())
        if "reroll" in use:
            new = quests.reroll(s)
            lines.append("🔀 New daily quests: " + ", ".join(q["title"] for q in new) if new
                         else "🔀 No unfinished daily quests to reroll.")
        if "gamble" in use:
            chance, xp = use["gamble"]
            if self.rng.random() < chance:
                lines.append(f"🎲 Cache hit! +{self.gain_xp(xp)} XP.")
            else:
                lines.append("🎲 Cache miss. The entry was from 2019.")
        if "xp" in use:
            lines.append(f"📈 +{self.gain_xp(use['xp'])} XP.")
        if "crate" in use:
            lines.append("📦 You pry the crate open...")
        if "banish" in use:
            if s.get("boss"):
                lines.append("🐞 The bug simply... stops happening.")
            else:
                lines.append(f"🐞 No boss to banish, so the mystery pays out: +{self.gain_xp(2500)} XP.")
        self.announce(kind, f"{item['icon']} Used {item['name']}.\n" + "\n".join(lines))
        if "crate" in use:
            self.roll_loot(1.0, fortune=use["crate"], source="the mystery crate")
        if "banish" in use and s.get("boss"):
            self.defeat_boss(s["boss"], banished=True)
        self.bump("items_used")
        self.unlock("first_use")
        return item

    def _restore_streak(self):
        broken = self.s.pop("broken_streak", None)
        if broken:
            last = date.fromisoformat(broken["last"])
            gap = (self.today - last).days - 1
            if 0 < gap <= 7:
                fill = {(last + timedelta(days=i)).isoformat() for i in range(1, gap + 1)}
                self.s["days"] = sorted(set(self.s["days"]) | fill)
                return f"📜 git reflog found your lost days. Streak restored: {self.streak()} days."
        until = self.now + 3600
        self.s["buffs"].append({"id": "reflog_scroll", "name": "Scroll of git reflog", "icon": "🔁",
                                "fx": {"commit_xp": 25}, "until": until})
        self.refresh_fx()
        return "📜 No broken streak to restore, so the scroll grants +25 XP per commit for an hour."

    def sell(self, query, count="1"):
        s = self.s
        if query == "dupes":
            sold = []
            for item, entries in self.bag_groups():
                for e in entries[1:]:
                    sold.append((item, e))
        else:
            item, _ = self.find(query)
            entries = next(es for it, es in self.bag_groups() if it["id"] == item["id"])
            n = len(entries) if count == "all" else int(count)
            if n < 1 or n > len(entries):
                raise GameError(f"You have {len(entries)} of {item['name']}.")
            sold = [(item, e) for e in entries[:n]]
        if not sold:
            raise GameError("Nothing to sell.")
        total = 0
        for item, e in sold:
            self.remove(e)
            total += items.SELL_PRICE[item["rarity"]]
        s["gold"] += total
        s["counters"]["gold_earned"] += total
        self.bump("sold", len(sold))
        names = ", ".join(sorted({i["name"] for i, _ in sold}))
        self.say(f"🪙 Sold {len(sold)} item{'s' if len(sold) != 1 else ''} ({names}) for {total} gold. "
                 f"You have {s['gold']} gold.")
        return total

    def shop_stock(self):
        today = self.today.isoformat()
        shop = self.s["shop"]
        if shop.get("date") != today:
            rng = random.Random(f"shop:{today}:{self.s.get('created', '')}")
            stock = []
            for kind, n in (("consumable", 3), ("gear", 2)):
                pool = [i for i in items.ITEMS.values() if i["kind"] == kind and i["rarity"] in items.BUY_PRICE]
                for _ in range(n):
                    weights = [items.RARITY_WEIGHT[i["rarity"]] for i in pool]
                    pick = rng.choices(pool, weights)[0]
                    pool.remove(pick)
                    stock.append({"id": pick["id"], "price": items.BUY_PRICE[pick["rarity"]],
                                  "sold": False, "deal": False})
            deal = rng.randrange(len(stock))
            stock[deal]["deal"] = True
            stock[deal]["price"] = round(stock[deal]["price"] * 0.75)
            self.s["shop"] = {"date": today, "stock": stock}
        return self.s["shop"]["stock"]

    def buy(self, query):
        stock = self.shop_stock()
        slot = None
        if query.isdigit() and 1 <= int(query) <= len(stock):
            slot = stock[int(query) - 1]
        else:
            words = items._norm(query).split()
            slot = next((x for x in stock
                         if all(w in items._norm(items.ITEMS[x["id"]]["name"]) for w in words)), None)
        if not slot:
            raise GameError(f"The shop has nothing called '{query}' today.")
        item = items.ITEMS[slot["id"]]
        if slot["sold"]:
            raise GameError(f"{item['name']} is sold out today.")
        if self.s["gold"] < slot["price"]:
            raise GameError(f"{item['name']} costs {slot['price']} gold; you have {self.s['gold']}.")
        self.s["gold"] -= slot["price"]
        slot["sold"] = True
        self.bump("bought")
        self.unlock("shopper")
        self.grant(item["id"], "the shop", found=False)
        self.say(f"🪙 Paid {slot['price']} gold. {self.s['gold']} left.")
        return item

    def forge(self, rarity):
        rarity = (rarity or "").lower()
        if rarity not in items.FORGE_COST:
            raise GameError("Forge which rarity? common (5), uncommon (4), rare (3) or epic (3).")
        need = items.FORGE_COST[rarity]
        pool = [(item, entries) for item, entries in self.bag_groups() if item["rarity"] == rarity]
        # spend spare copies first, then singles, cheapest-looking last
        spend = [(i, e) for i, es in pool for e in es[1:]] + [(i, es[0]) for i, es in pool]
        if len(spend) < need:
            raise GameError(f"The forge needs {need} unequipped {rarity} items; you have {len(spend)}.")
        used = spend[:need]
        for _, e in used:
            self.remove(e)
        target = items.RARITIES[items.rarity_rank(rarity) + 1]
        item = self.rng.choice(items.droppable(target))
        self.say("🔥 The forge roars, consuming " + ", ".join(i["name"] for i, _ in used) + ".")
        self.grant(item["id"], "the forge", found=False)
        self.bump("forged")
        self.unlock("alchemist")
        return item

    def pet_name(self):
        return self.s["pet"].get("name") or "Your pet"

    def name_pet(self, name):
        name = " ".join((name or "").split())[:24]
        if not name:
            raise GameError("Give your pet a name, e.g. `claude-quest name Sparky`.")
        self.s["pet"]["name"] = name
        self.announce("strut", f"🐾 Your pet is now called {name}. They seem to like it.")
        self.unlock("named")

    def set_title(self, title):
        title = (title or "").strip()
        if title.lower() in ("", "none", "rank", "default"):
            self.s["title"] = None
            self.say(f"🎖  Showing your rank again: {rules.rank_for(self.level())}.")
            return
        match = next((t for t in self.s["titles"] if t.lower() == title.lower()), None) or \
            next((t for t in self.s["titles"] if title.lower() in t.lower()), None)
        if not match:
            raise GameError(f"You haven't earned a title like '{title}'. See `claude-quest titles`.")
        self.s["title"] = match
        self.say(f"🎖  You are now known as {match}.")

    def reroll(self, index):
        daily = self.s["daily"]
        if not daily.get("free_reroll"):
            raise GameError("Today's free reroll is used. A Scroll of Re-Prioritization rerolls them all.")
        new = quests.reroll(self.s, index)
        if not new:
            raise GameError("That quest can't be rerolled (finished, or no such number).")
        daily["free_reroll"] = False
        self.say(f"🔀 New quest: {new[0]['title']} ({new[0]['text']}).")
