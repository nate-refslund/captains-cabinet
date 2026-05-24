#!/bin/bash
# officer-boot.sh — shared officer-session boot handler.
#
# Sourced by BOTH start-officer.sh (Docker/Hetzner) and start-officer-mac.sh
# (Mac native). Previously this logic was duplicated in both files, so every
# fix had to be applied twice — and they drifted (e.g. the settings.json
# PROMPT_REGEX patterns landed in start-officer-mac.sh + master's
# start-officer.sh but NOT mac-native's). Extracting it here means a fix lands
# ONCE and both platforms stay in lockstep.
#
# The only genuinely platform-specific bit (the boot-prompt text: send-to-group
# path + "(Mac native)" suffix) stays in each caller and is passed in.
#
# Usage:
#   source .../lib/officer-boot.sh
#   officer_boot_drive "<tmux-target>" "<boot-prompt-text>"

# officer_boot_drive <tmux-target> <boot-prompt-text>
#   Polls the freshly-launched Claude Code pane, auto-confirms known startup
#   prompts, then submits the boot prompt and verifies it registered.
officer_boot_drive() {
  local pane="$1"
  local boot_prompt="$2"

  # Prompts we auto-confirm (all via C-m — Enter doesn't reliably register on
  # cold CC sessions):
  #   - "--dangerously-load-development-channels" warning (our redis channel)
  #   - .claude/settings.json edit/trust dialogs
  #   - theme / welcome / folder-trust dialogs
  local PROMPT_REGEX="(I am using this for local development|Continue (as-is|conversation)|Summari[sz]e|Trust the (files|hooks)|Do you trust|Choose your theme|Welcome to Claude|edit .*\.claude/settings\.json|allow .*\.claude/settings\.json|Edit .*settings\.json|update .*\.claude/settings|Allow Claude to (edit|modify))"
  # Stale-session resume prompt → send "2" = "Resume full session as-is"
  # (Captain msg 2726 2026-05-24: Opus 4.7's 1M window has headroom + auto-compact
  # carries context cleanly; bare C-m would select option 1 / summary).
  local SELECT2_REGEX="(Resume from summary|Resume full session as-is)"
  # Stable-input indicators — stop dismissing once CC is ready for input.
  local STABLE_REGEX="(Try.*for new ideas|tab.*complete|Bypassing Permissions|esc to interrupt|^[[:space:]]*>[[:space:]]*\$)"
  # 120s budget: cold Opus 4.7 starts load slowly and the stale-session prompt
  # can render well past the old 45s budget (Captain msgs 2718-2726).
  local DEADLINE=$(($(date +%s) + 120))

  local pane_output
  while [ "$(date +%s)" -lt "$DEADLINE" ]; do
    sleep 2
    # Strip blank/whitespace-only lines BEFORE tail: CC renders modal startup
    # prompts at the TOP of the pane and pads the rest with blanks, so a raw
    # `tail -N` on a tall pane captures only padding and misses the menu
    # (proven 2026-05-24: tail-30 NO-MATCH vs strip-blank+tail-40 MATCH). This
    # was the intermittent "officer stuck on a startup prompt" bug.
    pane_output=$(tmux capture-pane -t "$pane" -p 2>/dev/null | grep -v '^[[:space:]]*$' | tail -40)
    if echo "$pane_output" | grep -qE "$SELECT2_REGEX"; then
      tmux send-keys -t "$pane" "2"
      sleep 0.5
      tmux send-keys -t "$pane" C-m
      sleep 1
    elif echo "$pane_output" | grep -qE "$PROMPT_REGEX"; then
      tmux send-keys -t "$pane" C-m
      sleep 1
    elif echo "$pane_output" | grep -qE "$STABLE_REGEX"; then
      break
    fi
  done

  # Brief settle, then submit the boot prompt (text, then C-m separately).
  sleep 2
  tmux send-keys -t "$pane" "$boot_prompt"
  sleep 0.5
  tmux send-keys -t "$pane" C-m
  # Verify it submitted. "esc to interrupt" only shows while CC is actively
  # processing; its absence means the text is still sitting unsent in the input
  # buffer (Captain msgs 2718/2724 — "prompt kept but not sent"). Nudge once.
  sleep 3
  if ! tmux capture-pane -t "$pane" -p 2>/dev/null | grep -v '^[[:space:]]*$' | tail -6 | grep -q "esc to interrupt"; then
    tmux send-keys -t "$pane" C-m
  fi
}
