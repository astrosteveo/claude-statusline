#!/usr/bin/env bash
# Bootstrap tests for install.sh. Each case runs against a throwaway $HOME so
# it can never touch the real one.
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

# Fresh isolated home; returns with $HOME pointing at it.
fresh() {
  HOME="$WORK/h$RANDOM$RANDOM"
  mkdir -p "$HOME/.claude"
  export HOME
  unset CLAUDE_CONFIG_DIR XDG_CONFIG_HOME
}
run() { (cd "$REPO" && ./install.sh "$@" >/dev/null 2>&1); }
runv(){ (cd "$REPO" && ./install.sh "$@" 2>&1); }

echo "install.sh bootstrap tests"

# --- clean install -----------------------------------------------------------
fresh; run
check "clean install writes the shim"      '[ -f "$HOME/.claude/statusline.py" ]'
check "clean install seeds the config"     '[ -f "$HOME/.config/claude-statusline/config.toml" ]'
check "clean install writes settings.json" '[ -f "$HOME/.claude/settings.json" ]'
check "shim renders a payload"             'echo "{}" | python3 "$HOME/.claude/statusline.py" | grep -q .'
check "clean install leaves no backups"    '! ls "$HOME"/.claude/*.bak-* >/dev/null 2>&1'

# --- idempotency -------------------------------------------------------------
fresh; run; run; run
n_sl=$(ls -1 "$HOME"/.claude/statusline.py.bak-* 2>/dev/null | wc -l)
n_st=$(ls -1 "$HOME"/.claude/settings.json.bak-* 2>/dev/null | wc -l)
check "3 installs leave no statusline backups" "[ $n_sl -eq 0 ]"
check "3 installs leave no settings backups"   "[ $n_st -eq 0 ]"

# --- the data-loss regression ------------------------------------------------
# Three installs inside one second used to back up our own shim over the user's
# real file (same timestamp), destroying it; uninstall then restored a shim.
fresh
printf '#!/usr/bin/env python3\nprint("USER ORIGINAL")\n' > "$HOME/.claude/statusline.py"
run; run; run
check "user's original is backed up exactly once" \
      '[ $(ls -1 "$HOME"/.claude/statusline.py.bak-* 2>/dev/null | wc -l) -eq 1 ]'
check "the backup is the user's file, not our shim" \
      'grep -q "USER ORIGINAL" "$HOME"/.claude/statusline.py.bak-*'
run --uninstall
check "uninstall restores the user's original" \
      'grep -q "USER ORIGINAL" "$HOME/.claude/statusline.py"'

# --- settings.json handling --------------------------------------------------
fresh
cat > "$HOME/.claude/settings.json" <<'JSON'
{"permissions": {"defaultMode": "acceptEdits"},
 "statusLine": {"type": "command", "command": "echo old"},
 "tui": "fullscreen"}
JSON
run
check "unrelated settings keys survive" \
      'python3 -c "import json,os,sys; c=json.load(open(os.environ[\"HOME\"]+\"/.claude/settings.json\")); sys.exit(0 if c[\"tui\"]==\"fullscreen\" and c[\"permissions\"][\"defaultMode\"]==\"acceptEdits\" else 1)"'
check "statusLine is replaced" \
      'python3 -c "import json,os,sys; c=json.load(open(os.environ[\"HOME\"]+\"/.claude/settings.json\")); sys.exit(0 if \"statusline.py\" in c[\"statusLine\"][\"command\"] else 1)"'
check "replacing statusLine backs it up once" \
      '[ $(ls -1 "$HOME"/.claude/settings.json.bak-* 2>/dev/null | wc -l) -eq 1 ]'
check "the settings backup holds the old command" \
      'grep -q "echo old" "$HOME"/.claude/settings.json.bak-*'

# --- malformed settings.json -------------------------------------------------
fresh
echo 'this is not { json' > "$HOME/.claude/settings.json"
out="$(runv)"
check "malformed settings.json does not abort the install" \
      '[ -f "$HOME/.claude/statusline.py" ]'
check "malformed settings.json is left intact" \
      'grep -q "not { json" "$HOME/.claude/settings.json"'
check "malformed settings.json tells the user what to add" \
      'printf "%s" "$out" | grep -q "statusLine"'

# --- install modes -----------------------------------------------------------
fresh; run --symlink
check "--symlink installs a symlink" '[ -L "$HOME/.claude/statusline.py" ]'
check "--symlink renders"            'echo "{}" | python3 "$HOME/.claude/statusline.py" | grep -q .'

fresh; run --copy
check "--copy installs a real file"  '[ -f "$HOME/.claude/statusline.py" ] && [ ! -L "$HOME/.claude/statusline.py" ]'
check "--copy is standalone"         '! grep -q "sys.path.insert" "$HOME/.claude/statusline.py"'
check "--copy renders"               'echo "{}" | python3 "$HOME/.claude/statusline.py" | grep -q .'

fresh; run --no-config
check "--no-config skips the config" '[ ! -f "$HOME/.config/claude-statusline/config.toml" ]'

# --- uninstall with nothing to restore ---------------------------------------
fresh; run
out="$(runv --uninstall)"
check "uninstall removes the shim"        '[ ! -f "$HOME/.claude/statusline.py" ]'
check "uninstall reports nothing to restore" \
      'printf "%s" "$out" | grep -q "no previous statusline"'

# --- existing config is never clobbered --------------------------------------
fresh; run
echo '# my edits' >> "$HOME/.config/claude-statusline/config.toml"
run
check "an existing config is preserved" \
      'grep -q "my edits" "$HOME/.config/claude-statusline/config.toml"'

echo
printf '%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
