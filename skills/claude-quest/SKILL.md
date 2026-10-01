---
name: claude-quest
description: Play Claude Quest, the RPG in the user's status line, on their behalf. Use when the user asks about their hero, gear, bag, gold, quests, shop, bosses, dungeons, raids, pet, titles or levelling, wants advice ("what should I buy?", "how do I level faster?"), or wants something done in the game ("equip my best gear", "sell my junk", "use my XP potions").
allowed-tools: Bash(python3 -S ${CLAUDE_PLUGIN_ROOT}/statusline.py quest:*)
---

# Playing Claude Quest

Claude Quest is an RPG that plays itself while the user works with Claude
Code: tool calls, prompts, commits, pushes and test runs earn XP, gold and
loot. Never edit the save (`~/.claude/quest/state.json`) by hand.

## Use the tools first

When the `claude-quest` MCP tools are there, use them: they return exact JSON
and act in one call each.

- `quest_status`: level, gold, worn gear, set bonuses, buffs, the total of
  every bonus, quests (numbered), boss, dungeons, raids, history. Start here.
- `quest_bag` (optionally `kind`: gear or consumable): items with id, count,
  what they do and sell price. `quest_shop`: today's numbered stock.
- `quest_best_gear` (`equip`: true to wear it): the best gear for this hero.
- `quest_act` with `action` and `target` (and `count`): equip, unequip, use
  (count = times), sell (count = copies, 0 = all), sell_dupes, buy, forge,
  reroll, title, name_pet. Name items by their id from `quest_bag`.

Look up what you need in one call, act, then answer. Batch the work: "use
all my XP potions" is one `quest_act` per kind of potion with `count` set.

## Without the tools

The same game runs from one command:

```
Q="python3 -S ${CLAUDE_PLUGIN_ROOT}/statusline.py quest"
$Q                      # the character sheet: level, gear, set bonuses, buffs, schools
$Q bag                  # what they carry, numbered; numbers change as the bag does
$Q inspect <item>       # one item: its bonuses, set, sell price
$Q best                 # the gear that earns the most XP, scored on their own history
$Q best equip           # wear it
$Q equip <item> | unequip <slot|item> | use <item>
$Q sell <item> [n|all] | sell dupes     # dupes keeps one of each
$Q forge <rarity>       # 5 common / 4 uncommon / 3 rare / 3 epic -> one of the next rarity
$Q shop | buy <n|name>  # new stock daily, one deal of the day
$Q quests | reroll <n>  # three daily, one weekly; one free reroll a day
$Q boss | dungeons | raid | pet | titles | title <t> | achievements | log | guide
```

Items can be named by bag number or by part of their name. Run a look-up
command before you act, and act in as few commands as you can.

## How it works

- **XP**: Bash +3 (shell school), Edit +5 / Write +8 (edit), Read, Grep and
  Glob +1 (read), Agent +12 / Workflow +20 (agent), web tools +2 to +3 (web),
  each prompt +2, a commit +25, a push +30, a test run +10. Level n needs
  50·(n−1)² XP. The class is the school used most.
- **Bonuses add up**: gear, set bonuses, the pet's form and buffs from
  consumables. `+10% XP` multiplies all XP; `+20% shell XP` multiplies shell
  XP only; `+25 XP per commit` is added to each commit. The sheet's "All
  bonuses" line is the total.
- **Gear** fills five slots: head, hand, back, feet, charm. Wearing every
  piece of a set adds its bonus and earns its title for good, so a set can
  beat stronger single items. `best` already weighs sets against single items
  using the hero's real history, so trust it over rarity.
- **Consumables** give timed buffs (XP, loot chance, per-commit XP) or open
  into loot. Several buffs stack, so using them together, just before a long
  working session, pays most.
- **Gold** comes from level-ups, quests, bosses, commits, pushes and selling.
  Selling spares (`sell dupes`) is safe; the forge turns spares into rarer
  items, and the shop sells one discounted deal a day.
- **Bosses**: a failing test, build or lint run summons one with an HP per
  failure; fewer failures hit it and a clean run wins. **Dungeons**: each open
  pull request; merging clears it. **Raids**: each project's TODO, FIXME, XXX
  and HACK count; commits that remove them strike it. A **treasure goblin**
  is caught by committing within ten minutes.

## Doing what the user asks

- "Equip my best gear": `$Q best equip`, then say what changed and the gain.
- "What should I do with my bag?": `$Q bag`, then sell dupes or forge only if
  they agree, because both remove items.
- "How do I level faster?": read the sheet, then give two or three concrete
  steps from their own numbers (their top school, sets they nearly have,
  buffs in the bag).
- Spending, selling, forging and using items change the save for good: do
  them when the user asked for that, and say what you did.

Answer in a few plain sentences. Show the game's own output only when the
user asked to see it.
