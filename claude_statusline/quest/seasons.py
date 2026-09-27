"""Seasons: a few days a year when Claude Quest dresses up.

A season is data: its dates, boss names, loot, a daily quest, and the props
the scene draws. During one, bosses take seasonal names, seasonal items can
drop, one daily quest is the season's, and the news announces it once.
`[quest] seasons = false` turns them off; QUEST_SEASON=<name> or =none
forces one (for the demo and tests).
"""
import os
from datetime import date

SEASONS = {
    "halloween": {
        "name": "Hallowed Harvest",
        "icon": "🎃",
        "dates": ((10, 24), (11, 1)),
        "announce": "🎃 The Hallowed Harvest has begun: haunted bosses and seasonal loot until the first of "
                    "November.",
        "bosses": {
            "test": ["Headless Heisenbug", "Ghost of Tests Past", "Phantom Assertion"],
            "build": ["Mummy of Missing Modules", "Frankenbuild", "Skeleton Key Error"],
            "lint": ["Poltergeist of Unused Imports", "Witch of Whitespace", "Banshee of Bad Names"],
        },
        "quest": ("trick", "Trick or Treat", "Find {n} item{s}", "items_found", (2, 3), 160, 50),
    },
}


def current(day=None, enabled=True):
    """The season in force on `day` (a key of SEASONS), or None."""
    forced = os.environ.get("QUEST_SEASON")
    if forced:
        return forced if forced in SEASONS else None
    if not enabled:
        return None
    day = day or date.today()
    for key, spec in SEASONS.items():
        (m0, d0), (m1, d1) = spec["dates"]
        if (m0, d0) <= (day.month, day.day) <= (m1, d1):
            return key
    return None


def enabled_in_config():
    try:
        from ..config import compiled
        return compiled()["quest"].get("seasons", True) is not False
    except Exception:
        return True
