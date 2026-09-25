"""Text output: colours (only on a real terminal), bars, and the pet's ASCII portrait."""
import os
import sys

from . import items, rules

ANSI = {"dim": "2", "bold": "1", "gold": "38;5;179", "purple": "38;5;176", "cyan": "38;5;80",
        "green": "38;5;114", "red": "38;5;203", "gray": "38;5;245", "yellow": "38;5;221"}
RARITY_ANSI = {"common": "38;5;250", "uncommon": "38;5;114", "rare": "38;5;75",
               "epic": "38;5;177", "legendary": "38;5;214"}

ART = {
    "egg": ["  ___  ", " /   \\ ", "|  ?  |", " \\___/ "],
    "hatchling": ["  \\_/  ", " (o o) ", " ( v ) ", "  ^ ^  "],
    "lizard": [" _____ ", "(o   o)", " \\_=_/ ", " /| |\\~"],
    "drake": [" /\\_/\\ ", "( o o )", " > ^ <~", "/|| ||\\"],
    "wyrm": [" /\\/\\/\\ ", "( *  * )", "<  ===  >", " \\/\\/\\/ "],
}


def color_on():
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def c(style, text):
    if not color_on():
        return str(text)
    code = ANSI.get(style, style)
    return f"\x1b[{code}m{text}\x1b[0m"


def rarity(item, text=None):
    return c(RARITY_ANSI[item["rarity"]], text if text is not None else item["name"])


def bar(frac, width=20):
    frac = max(0.0, min(1.0, frac))
    filled = round(frac * width)
    return "█" * filled + "░" * (width - filled)


def item_line(item, count=1):
    n = f" ×{count}" if count > 1 else ""
    return f"{items.RARITY_ICON[item['rarity']]} {item['icon']} {rarity(item)}{n}"


def banner(view, streak):
    art = ART.get(view["stage"], ART["lizard"])
    pet = view.get("pet_name") or view["stage_name"]
    lines = [
        f"⚔️  CLAUDE QUEST — Lv {view['level']} {view['title']}",
        f"{view['class_icon'] or '❔'} {view['class'] or 'Unclassed'}   🔥 {streak}-day streak   🪙 {view['gold']}",
        f"XP {bar(view['xp_in'] / max(1, view['xp_need']))} {view['xp_in']}/{view['xp_need']}",
        f"🐾 {pet} ({view['bond']})   🎒 {view['bag']}   📜 {view['daily_done']}/{view['daily_total']} quests",
    ]
    b = view.get("boss")
    if b:
        lines.append(f"{b['icon']} {b['name']} lurks in {b['project']}: {b['hp']}/{b['max_hp']} HP")
    w = max(len(a) for a in art)
    art = art + [""] * (len(lines) - len(art))
    return "\n".join(f"{a.ljust(w)}   {line}" for a, line in zip(art, lines))


def rank_name(level):
    return rules.rank_for(level)
