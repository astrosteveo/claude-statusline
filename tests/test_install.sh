#!/usr/bin/env bash
# install.sh against throwaway homes; it can never touch the real one.
#
#   ./tests/test_install.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  \033[32mok\033[0m   %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  \033[31mFAIL\033[0m %s\n' "$1"; }
check(){ if eval "$2"; then ok "$1"; else bad "$1"; fi; }

fresh() {
  HOME="$WORK/h$RANDOM$RANDOM"
  mkdir -p "$HOME/.claude"
  export HOME
  export XDG_RUNTIME_DIR="$HOME"
  export CLAUDE_QUEST_NO_MCP=1
  unset CLAUDE_CONFIG_DIR XDG_CONFIG_HOME CLAUDE_STATUSLINE_CONFIG CLAUDE_QUEST_HOME
}
run() { (cd "$REPO" && TERM=xterm-256color ./install.sh "$@" >/dev/null 2>&1); }
runv(){ (cd "$REPO" && TERM=xterm-256color ./install.sh "$@" 2>&1); }
jq_() { python3 -c "import json,os,sys; c=json.load(open(os.environ['HOME']+'/.claude/settings.json')); sys.exit(0 if ($1) else 1)"; }

echo "install.sh"

fresh; run
check "writes the shim"                    '[ -f "$HOME/.claude/statusline.py" ]'
check "creates a config"                   '[ -f "$HOME/.config/claude-statusline/config.toml" ]'
check "the config picks a look"            'grep -q "^style = \"chips\"" "$HOME/.config/claude-statusline/config.toml"'
check "points settings.json at it"         'jq_ "c[\"statusLine\"][\"command\"] == \"python3 -S ~/.claude/statusline.py\""'
check "the shim renders a payload"         'echo "{}" | python3 -S "$HOME/.claude/statusline.py" | grep -q .'
check "links claude-statusline"            '[ -L "$HOME/.local/bin/claude-statusline" ]'
check "leaves no backups"                  '! ls "$HOME"/.claude/*.bak-* >/dev/null 2>&1'

fresh; run; run; run
check "three installs: no backups" '[ $(ls -1 "$HOME"/.claude/*.bak-* 2>/dev/null | wc -l) -eq 0 ]'

# The data-loss regression: repeated installs within a second used to back
# up our own shim over the user's real file.
fresh
printf '#!/usr/bin/env python3\nprint("USER ORIGINAL")\n' > "$HOME/.claude/statusline.py"
run; run; run
check "the user's file is backed up once" '[ $(ls -1 "$HOME"/.claude/statusline.py.bak-* 2>/dev/null | wc -l) -eq 1 ]'
check "the backup is the user's file"     'grep -q "USER ORIGINAL" "$HOME"/.claude/statusline.py.bak-*'
run --uninstall
check "uninstall restores it"             'grep -q "USER ORIGINAL" "$HOME/.claude/statusline.py"'
check "uninstall removes the link"        '[ ! -e "$HOME/.local/bin/claude-statusline" ]'

fresh
cat > "$HOME/.claude/settings.json" <<'JSON'
{"permissions": {"defaultMode": "acceptEdits"}, "statusLine": {"type": "command", "command": "echo old"}, "tui": "fullscreen"}
JSON
run
check "unrelated settings survive"        'jq_ "c[\"tui\"] == \"fullscreen\" and c[\"permissions\"][\"defaultMode\"] == \"acceptEdits\""'
check "statusLine is replaced"            'jq_ "\"statusline.py\" in c[\"statusLine\"][\"command\"]"'
check "and backed up once"                '[ $(ls -1 "$HOME"/.claude/settings.json.bak-* 2>/dev/null | wc -l) -eq 1 ]'
check "the backup has the old command"    'grep -q "echo old" "$HOME"/.claude/settings.json.bak-*'

fresh
echo 'this is not { json' > "$HOME/.claude/settings.json"
out="$(runv)"
check "bad settings.json: install goes on" '[ -f "$HOME/.claude/statusline.py" ]'
check "bad settings.json: left intact"     'grep -q "not { json" "$HOME/.claude/settings.json"'
check "bad settings.json: says what to add" 'printf "%s" "$out" | grep -q "statusLine"'

fresh; run --symlink
check "--symlink makes a symlink"          '[ -L "$HOME/.claude/statusline.py" ]'
check "--symlink renders"                  'echo "{}" | python3 -S "$HOME/.claude/statusline.py" | grep -q .'

fresh; run --copy
check "--copy is a real file"              '[ -f "$HOME/.claude/statusline.py" ] && [ ! -L "$HOME/.claude/statusline.py" ]'
check "--copy is standalone"               '! grep -q "sys.path.insert" "$HOME/.claude/statusline.py"'
check "--copy renders"                     'echo "{}" | python3 -S "$HOME/.claude/statusline.py" | grep -q .'
run
check "a shim install clears the copy"     '[ ! -d "$HOME/.claude/claude_statusline" ]'

fresh; run --no-config
check "--no-config makes no config"        '[ ! -f "$HOME/.config/claude-statusline/config.toml" ]'

fresh; run --quest
check "--quest registers eight hooks"      'jq_ "sum(len(e[\"hooks\"]) for ev in c[\"hooks\"].values() for e in ev) == 8"'
check "--quest installs /quest"            '[ -f "$HOME/.claude/commands/quest.md" ]'
check "--quest installs the skill"         '[ -f "$HOME/.claude/skills/claude-quest/SKILL.md" ]'
check "--quest switches it on"             'grep -q "enabled = true" "$HOME/.config/claude-statusline/config.toml"'
check "--quest links claude-quest"         '[ -L "$HOME/.local/bin/claude-quest" ]'
check "claude-quest runs the game"         '"$HOME/.local/bin/claude-quest" guide | grep -q "How Claude Quest works"'
run --uninstall
check "uninstall takes the hooks out"      'jq_ "\"hooks\" not in c"'
check "uninstall removes /quest"           '[ ! -f "$HOME/.claude/commands/quest.md" ]'

fresh; run
out="$(runv --uninstall)"
check "uninstall removes the shim"         '[ ! -f "$HOME/.claude/statusline.py" ]'
check "uninstall says nothing to restore"  'printf "%s" "$out" | grep -q "no previous status line"'

fresh; run
echo '# my edits' >> "$HOME/.config/claude-statusline/config.toml"
run
check "an existing config is kept"         'grep -q "my edits" "$HOME/.config/claude-statusline/config.toml"'

echo
printf '%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
