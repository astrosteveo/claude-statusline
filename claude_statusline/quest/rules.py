"""The numbers the game runs on: XP per tool, schools, ranks, levels, pet stages."""
import math

XP_BY_TOOL = {
    "Edit": 5, "Write": 8, "MultiEdit": 7, "NotebookEdit": 6,
    "Bash": 3, "Read": 1, "Grep": 1, "Glob": 1,
    "Agent": 12, "Workflow": 20, "WebSearch": 3, "WebFetch": 2,
    "Artifact": 15, "Skill": 4,
}
DEFAULT_TOOL_XP = 2
PROMPT_XP = 2
COMMIT_XP = 25
PUSH_XP = 30
TEST_XP = 10
COMMIT_GOLD = 3
PUSH_GOLD = 5

TOOL_LOOT_CHANCE = 0.01   # per tool call
STOP_LOOT_CHANCE = 0.08   # each time Claude finishes a reply
CHEST_LOOT_CHANCE = 0.35  # the first session of the day

SCHOOLS = {
    "shell": ("Shell Sorcerer", "🧙"),
    "edit": ("Code Smith", "🔨"),
    "read": ("Lore Seeker", "📜"),
    "agent": ("Summoner", "🔮"),
    "web": ("Net Ranger", "🏹"),
}
TOOL_SCHOOL = {
    "Bash": "shell", "Edit": "edit", "Write": "edit", "MultiEdit": "edit",
    "NotebookEdit": "edit", "Read": "read", "Grep": "read", "Glob": "read",
    "Agent": "agent", "Workflow": "agent", "Skill": "agent",
    "WebSearch": "web", "WebFetch": "web",
}

RANKS = [
    (1, "Wandering Prompter"), (5, "Apprentice"), (10, "Journeyman"),
    (15, "Adept"), (20, "Veteran"), (30, "Master"), (40, "Grandmaster"),
    (50, "Archmage"), (75, "Mythic"), (100, "Ascended"),
]
PET_STAGES = [
    (1, "egg", "a mysterious egg"),
    (5, "hatchling", "a hatchling byte"),
    (15, "lizard", "a little lint lizard"),
    (30, "drake", "a young stack drake"),
    (50, "wyrm", "an elder kernel wyrm"),
]
# From the drake on, the pet takes the form of your top school at the moment
# it evolves, and keeps it. A wyrm doubles its form's gift.
FORM_STAGES = ("drake", "wyrm")
FORMS = {
    # school: (form, emoji, the gift's fx)
    "shell": ("ember", "🔥", {"xp_shell": 0.10, "test_xp": 5}),
    "edit": ("forge", "⚒️", {"xp_edit": 0.10, "commit_xp": 10}),
    "read": ("lore", "📚", {"xp_read": 0.10, "luck": 0.10}),
    "agent": ("arcane", "🔮", {"xp_agent": 0.10, "quest": 0.10}),
    "web": ("storm", "⚡", {"xp_web": 0.10, "gold": 0.05}),
}
FORM_BY_KEY = {f[0]: school for school, f in FORMS.items()}
BOND_LEVELS = [(0, "Curious"), (10, "Friendly"), (30, "Loyal"), (60, "Devoted"), (100, "Soulbound")]


def level_for(xp):
    return int(math.sqrt(max(0, xp) / 50)) + 1


def xp_for_level(level):
    return 50 * (level - 1) ** 2


def rank_for(level):
    return [name for need, name in RANKS if level >= need][-1]


def stage_for(level):
    """(key, description) of the pet at this level."""
    need, key, name = [s for s in PET_STAGES if level >= s[0]][-1]
    return key, name


def top_school(school):
    return max(school, key=school.get) if school else None


def form_for(school):
    """The form key your top school would give, or None before any tool use."""
    return FORMS[school][0] if school in FORMS else None


def form_of(state):
    """(form, emoji, fx) of the pet's form, or None while it has none."""
    school = FORM_BY_KEY.get((state.get("pet") or {}).get("form"))
    if not school or stage_for(level_for(state.get("xp", 0)))[0] not in FORM_STAGES:
        return None
    return FORMS[school]


def form_fx(state):
    """The form's gift, doubled for a wyrm."""
    form = form_of(state)
    if not form:
        return {}
    mult = 2 if stage_for(level_for(state.get("xp", 0)))[0] == "wyrm" else 1
    return {k: v * mult for k, v in form[2].items()}


def pet_description(state):
    """'a young ember drake', or the stage's plain description."""
    key, desc = stage_for(level_for(state.get("xp", 0)))
    form = form_of(state)
    if not form:
        return desc
    words = desc.split()       # "a young stack drake" -> "a young ember drake"
    return " ".join(words[:-2] + [form[0], words[-1]])


def bond_level(bond):
    """(index, name) of the bond tier."""
    tiers = [i for i, (need, _) in enumerate(BOND_LEVELS) if bond >= need]
    i = tiers[-1] if tiers else 0
    return i, BOND_LEVELS[i][1]


def base_tool(name):
    return "mcp" if name.startswith("mcp__") else name


def school_of(tool):
    return TOOL_SCHOOL.get(base_tool(tool))


def tool_xp(tool):
    return XP_BY_TOOL.get(base_tool(tool), DEFAULT_TOOL_XP)
