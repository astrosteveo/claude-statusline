"""Daily and weekly quests: what they ask for, how they are picked, how they progress."""
import random
from datetime import date

# (id, title, text, counter, goal range, xp, gold). Text takes {n}, {s} and {es}.
DAILY = [
    ("commits", "Seal the Scrolls", "Make {n} commit{s}", "commits", (2, 4), 150, 40),
    ("tests", "Trial by Fire", "Run your tests {n} time{s}", "tests", (3, 6), 120, 35),
    ("edits", "Forge Ahead", "Edit or write files {n} times", "edits", (15, 30), 120, 35),
    ("reads", "Study the Archives", "Read or search {n} times", "reads", (25, 50), 100, 30),
    ("prompts", "Council of the Wise", "Send {n} prompts", "prompts", (8, 15), 100, 30),
    ("shell", "Command the Shell", "Run {n} shell commands", "shell", (20, 40), 110, 30),
    ("agents", "Call for Aid", "Spawn {n} subagent{s}", "agents", (1, 3), 140, 40),
    ("boss", "Slay a Beast", "Defeat {n} boss{es}", "bosses", (1, 1), 200, 60),
    ("loot", "Treasure Hunter", "Find {n} item{s}", "items_found", (1, 2), 120, 35),
    ("web", "Scout the Web", "Search or fetch the web {n} times", "web", (2, 4), 100, 30),
    ("use", "Put It to Use", "Use {n} item{s} from your bag", "items_used", (1, 2), 90, 25),
    ("thanks", "Mind Your Manners", "Thank Claude {n} time{s}", "thanks", (1, 2), 60, 20),
]
WEEKLY = [
    ("w_commits", "The Long Campaign", "Make {n} commits this week", "commits", (15, 25), 800, 250),
    ("w_tests", "Proving Grounds", "Run your tests {n} times this week", "tests", (20, 30), 700, 220),
    ("w_bosses", "Monster Hunter", "Defeat {n} bosses this week", "bosses", (3, 3), 900, 300),
    ("w_quests", "Dedicated", "Complete {n} daily quests this week", "quests_done", (10, 12), 800, 250),
    ("w_xp", "Grind Set", "Earn {n} XP this week", "xp_gained", (3000, 5000), 600, 250),
]
DAILY_COUNT = 3


def _make(spec, rng, weekly=False):
    qid, title, text, counter, (lo, hi), xp, gold = spec
    n = rng.randint(lo, hi)
    if weekly and counter == "xp_gained":
        n = round(n, -2)
    text = text.format(n=n, s="" if n == 1 else "s", es="" if n == 1 else "es")
    if n == 1:
        text = text.replace(" 1 time", " once")
    return {"id": qid, "title": title, "text": text,
            "counter": counter, "goal": n, "progress": 0, "done": False,
            "xp": xp, "gold": gold, "weekly": weekly}


def week_of(day):
    y, w, _ = day.isocalendar()
    return f"{y}-W{w:02d}"


def ensure(state, today=None):
    """Roll new quests when the day or week changes."""
    today = today or date.today()
    salt = state.get("created", "")
    daily = state["daily"]
    if daily.get("date") != today.isoformat():
        rng = random.Random(f"{today.isoformat()}:{salt}")
        picks = rng.sample(DAILY, DAILY_COUNT)
        state["daily"] = {"date": today.isoformat(), "quests": [_make(p, rng) for p in picks],
                          "free_reroll": True, "chest": daily.get("chest")}
    week = week_of(today)
    if state["weekly"].get("week") != week:
        rng = random.Random(f"{week}:{salt}")
        state["weekly"] = {"week": week, "quests": [_make(rng.choice(WEEKLY), rng, weekly=True)]}


def all_quests(state):
    return state["daily"].get("quests", []) + state["weekly"].get("quests", [])


def progress(state, counter, n):
    """Advance matching quests; returns the ones this completes."""
    finished = []
    for q in all_quests(state):
        if q["counter"] == counter and not q["done"]:
            q["progress"] = min(q["goal"], q["progress"] + n)
            if q["progress"] >= q["goal"]:
                q["done"] = True
                finished.append(q)
    return finished


def reroll(state, index=None):
    """Replace one daily quest (or all unfinished ones) with others from the pool."""
    quests = state["daily"].get("quests", [])
    taken = {q["id"] for q in quests}
    pool = [p for p in DAILY if p[0] not in taken]
    rng = random.Random()
    targets = [index] if index is not None else [i for i, q in enumerate(quests) if not q["done"]]
    changed = []
    for i in targets:
        if not pool or not (0 <= i < len(quests)) or quests[i]["done"]:
            continue
        spec = pool.pop(rng.randrange(len(pool)))
        quests[i] = _make(spec, rng)
        changed.append(quests[i])
    return changed
