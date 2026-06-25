#!/bin/bash
# cabinet/scripts/hooks/captain-escalation-precheck.sh
#
# STRUCTURAL guard for the repeated-forgetting of two encoded Captain
# patterns (shared/interfaces/captain-patterns.md):
#   - verify-before-surfacing            (test the claim + check the decision trail)
#   - deep-dive-and-fix-before-escalating (HARD rule: deep-dive → fix → only then escalate)
#
# WHY THIS EXISTS (meta-rule `repeated-forgetting-means-change-the-mechanism`):
# Nate has had to remind the Chair of these rules MULTIPLE times — "Monday key
# dead"→worked, "Vercel 403"→worked, "promote access lacking"→an unbuilt
# command. Each was a forwarded inference, not a verified root cause. Repeated
# forgetting means the reminder mechanism is inadequate; the fix is to make the
# check AUTOMATIC at the exact moment the Chair is about to escalate to Nate.
#
# WHAT IT CATCHES
# The Chair sends Captain-facing messages by running a Bash command that pipes
# text into framework.frontdoor.channel.send (the sole cos→Captain Telegram
# path), e.g.:
#     cat > /tmp/cc_x.txt <<'EOF' … EOF
#     MSG="$(cat /tmp/cc_x.txt)" python3.12 -c "...channel.send(os.environ['MSG'])"
# When that outbound payload contains escalation/blocker language (needs you,
# blocked, can't, token, rotate, access, dead, 403, expired, …) this hook
# injects a non-blocking advisory reminding the Chair to deep-dive FIRST.
#
# DESIGN (matches build-vs-buy-precheck.sh — the proven sibling advisory):
#   - Wired as PreToolUse(Bash), ALONGSIDE pre-tool-use.sh (does NOT modify it,
#     so the killswitch / spending / prohibited-actions contracts are untouched).
#   - Advisory ONLY: emits {hookSpecificOutput:{additionalContext}} on stdout
#     and ALWAYS exit 0. Never blocks — the Chair must stay able to escalate a
#     genuine residual. (Anti-FW-042: warn-only, never exits non-zero.)
#   - Scoped STRICTLY to the cos officer. Other officers / non-cos sessions are
#     never touched (they are Telegram-dark and do not use channel.send).
#   - Low false-positive: fires only when BOTH (a) the Bash call is a
#     Captain-facing send AND (b) the payload carries escalation/blocker
#     keywords. Plain "all green" status sends stay silent.
#
# Controls:
#   - Env-var disable: CAPTAIN_ESCALATION_HOOK_ENABLED=0
#   - FP-rate logging to cabinet/logs/hook-fires/captain-escalation-precheck.jsonl
#
# Reversibility: rm this file + drop its settings.json PreToolUse(Bash) entry.

set -u

if [ "${CAPTAIN_ESCALATION_HOOK_ENABLED:-1}" = "0" ]; then
  exit 0
fi

# ------------------------------------------------------------------
# 1. Scope strictly to the Chair (cos). Mirror build-vs-buy-precheck.sh's
#    officer resolution (OFFICER_NAME → CABINET_OFFICER). Anything else exits
#    immediately and silently — zero effect on other officers / sessions.
# ------------------------------------------------------------------
OFFICER="${OFFICER_NAME:-${CABINET_OFFICER:-${OFFICER:-unknown}}}"
[ "$OFFICER" = "cos" ] || exit 0

INPUT="$(cat)"
[ -z "$INPUT" ] && exit 0

# Only Bash tool calls carry a send command. (Belt-and-braces — settings.json
# already scopes this hook to the Bash matcher.)
TOOL_NAME="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)"
[ -n "$TOOL_NAME" ] && [ "$TOOL_NAME" != "Bash" ] && exit 0

COMMAND="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)"
[ -z "$COMMAND" ] && exit 0

# ------------------------------------------------------------------
# 2. Detect a Captain-facing send — an actual EXECUTION of the send path,
#    not a mere mention of it. The cos→Captain path is
#    framework.frontdoor.channel.send (channel.py is the ONLY send path, and
#    its recipient is ALWAYS CAPTAIN_TELEGRAM_ID).
#
#    CRITICAL (low-FP): the send token must co-occur with a Python EXECUTION
#    (`python … -c …` / `python … -m …` / `python … script.py`) or be the cos
#    Telegram bot `sendMessage` curl. This is what separates a real send from a
#    DEV command that merely names the path — `git commit -m "...channel.send..."`,
#    `grep channel.send`, `cat chair_drafts.py`, this hook's own tests, etc.
#    (Same lesson as pre-tool-use.sh's quote/heredoc-strip machinery: match the
#    invocation, not the substring.)
#
#    First, hard-exclude obvious dev/inspection commands whose FIRST word is a
#    reader/VCS/editor — they reference the path as data, never execute it.
# ------------------------------------------------------------------
# Leading command word — the first real argv[0] after skipping any leading
# env-var assignments (VAR=val) and pass-through wrappers (sudo/command/exec/…).
# Portable awk (no BSD-vs-GNU sed branch-label divergence): walk tokens, drop
# assignments + wrapper words, print the first survivor, strip its dir prefix.
_FIRST_WORD="$(printf '%s' "$COMMAND" | awk '{
  for (i = 1; i <= NF; i++) {
    w = $i
    if (w ~ /^[A-Za-z_][A-Za-z0-9_]*=/) continue            # VAR=val
    if (w == "sudo" || w == "command" || w == "exec" \
        || w == "env" || w == "nohup" || w == "time") continue
    sub(/.*\//, "", w)                                       # basename
    print w; exit
  }
}')"
case "$_FIRST_WORD" in
  git|grep|rg|ag|cat|bat|less|more|head|tail|sed|awk|vim|vi|nano|emacs|code|diff|wc|ls|find|fd|cp|mv|rm|chmod|nl|tee|sort|uniq|jq|cut|tr|xxd|hexdump|file|stat|touch|mkdir|echo|printf)
    exit 0 ;;
esac

# A genuine channel.send execution: the send token next to a python -c/-m/script
# invocation (env-var-prefixed forms like `MSG="$(cat ...)" python3.12 -c "…"`
# are covered because we search the whole command for both signals).
IS_CAPTAIN_SEND=0
_HAS_PY_EXEC=0
printf '%s' "$COMMAND" | grep -qE '(^|[;&|[:space:]])(python3?(\.[0-9]+)?)([[:space:]]+(-[A-Za-z]+|[^[:space:]]+))*[[:space:]]+(-c|-m|[^[:space:]]*\.py)' && _HAS_PY_EXEC=1
case "$COMMAND" in
  *channel.send*|*"frontdoor.channel"*|*run_send_path*|*chair_drafts*|*run_frontdoor*|*run_briefing*|*morning_synthesis*|*frontdoor*send*|*send*frontdoor*)
    [ "$_HAS_PY_EXEC" = "1" ] && IS_CAPTAIN_SEND=1 ;;
esac
# Legacy cos Telegram bot send (curl POST to sendMessage using the cos token).
case "$COMMAND" in
  *TELEGRAM_COS_TOKEN*sendMessage*|*sendMessage*TELEGRAM_COS_TOKEN*)
    IS_CAPTAIN_SEND=1 ;;
esac
[ "$IS_CAPTAIN_SEND" = "1" ] || exit 0

# ------------------------------------------------------------------
# 3. Resolve the OUTGOING MESSAGE BODY — and scan ONLY that, never the raw
#    command string.
#
#    CRITICAL (production FP fix): every real cos send-bash carries env-setup
#    boilerplate, e.g.
#        export TELEGRAM_COS_TOKEN="$(grep '^TELEGRAM_COS_TOKEN=' cabinet/.env …)"
#    The env-var NAME contains "TOKEN", so scanning the whole command string
#    tripped the escalation keyword on EVERY send (benign sweeps included). The
#    blocker keywords must be matched against the message the Captain will read,
#    not the shell plumbing around the send.
#
#    Extract the body from the three real send shapes (in priority order):
#      (a) /tmp/*.txt the send reads via cat  — the documented heredoc shape
#          (`cat > /tmp/cc_x.txt <<'EOF' … EOF` then `MSG="$(cat /tmp/cc_x.txt)"`).
#      (b) the literal string argument to channel.send("…") / .send('…').
#      (c) the value assigned to MSG=/TEXT=/BODY= (quoted inline literal).
#    If NONE resolves (we can't see the body), stay SILENT — a body we cannot
#    read is not something to escalate-scan (fail-quiet, never fire on plumbing).
# ------------------------------------------------------------------
BODY=""

# (a) /tmp/*.txt contents the send reads. Bounded read (head -c) so a huge file
#     can't blow the hook up; we only need enough to keyword-scan.
while IFS= read -r tmpf; do
  [ -z "$tmpf" ] && continue
  if [ -f "$tmpf" ]; then
    FILE_BODY="$(head -c 65536 "$tmpf" 2>/dev/null)"
    BODY="$BODY
$FILE_BODY"
  fi
done < <(printf '%s' "$COMMAND" | grep -oE '/tmp/[A-Za-z0-9._/-]+\.txt' | sort -u)

# (b) literal argument to channel.send("…")/send('…') and (c) MSG=/TEXT=/BODY=
#     "...". Perl pulls the quoted literal(s) out of the command so we scan the
#     human text, not the surrounding python/shell. Both quote styles; multiline.
INLINE_BODY="$(printf '%s' "$COMMAND" | perl -0777 -ne '
  my @hits;
  # channel.send("…") / .send('"'"'…'"'"')  — the message argument
  while (/\bsend\s*\(\s*(?:f|r|fr|rf)?(["'"'"'])(.*?)\1/sgi) { push @hits, $2; }
  # MSG= / TEXT= / BODY= / MESSAGE= "…"  (quoted inline literal)
  while (/\b(?:MSG|TEXT|BODY|MESSAGE)\s*=\s*(["'"'"'])(.*?)\1/sgi) { push @hits, $2; }
  print join("\n", @hits) if @hits;
' 2>/dev/null)"
[ -n "$INLINE_BODY" ] && BODY="$BODY
$INLINE_BODY"

# Trim — if nothing resolved, we cannot see the outgoing text: stay silent.
BODY="$(printf '%s' "$BODY" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
[ -z "$BODY" ] && exit 0

HAYSTACK="$BODY"

# ------------------------------------------------------------------
# 4. Escalation / blocker keyword scan (case-insensitive, WHOLE-WORD anchored).
#    These are the phrases that mean "I'm forwarding a doesn't-work to Nate"
#    — exactly when the deep-dive rule must fire.
#
#    WHOLE-WORD on the bare nouns (token|access|rotate|expired|stuck|blocker|
#    unauthorized|…) via \< \> so an env-var name, a path, or a python symbol
#    (TELEGRAM_COS_TOKEN, /tmp/cc.txt, os.environ['TOKEN'], access_token) can
#    NEVER trip — only a free-standing word does ("the token is dead",
#    "no access"). grep -iwE-style boundaries are emulated with \< \> (GNU/BSD
#    grep both honor these in -E mode). Multi-word phrases are inherently
#    boundaried; the numeric codes 403/401 keep digit boundaries.
# ------------------------------------------------------------------
ESCALATION_RE='needs you|needs your|need you to|only you can|i need you|\<blocked\>|\<blocker\>|\<blockers\>|can'\''t|cannot|can not|won'\''t work|not working|doesn'\''t work|does not work|\<token\>|\<tokens\>|\<rotate\>|\<rotation\>|\<expired\>|dead key|dead token|is dead|no access|lack(s|ing)? access|\<access\> (is )?(lacking|missing|denied)|permission denied|\<403\>|\<401\>|\<unauthorized\>|\<stuck\>|re-?auth|reauthenticate'

# Negated-reassurance guard (low-FP). A GREEN status send very often *mentions*
# blocker vocabulary to say there is NONE: "nothing needs you", "no blockers",
# "nothing's blocking", "no token issues". Neutralize those negated phrasings
# BEFORE the trigger scan so reassurance doesn't read as escalation. Applied to
# a scan-only copy (SCAN) — the advisory text/log are unaffected. Conservative:
# only strips an escalation keyword when an explicit negator immediately
# precedes it (nothing/no/none/zero/not/n't/without/no-longer), so a real
# "X is blocked" still fires.
SCAN="$(printf '%s' "$HAYSTACK" | perl -0777 -pe '
  # (i) negator BEFORE keyword: "nothing needs you", "no blockers", "no token issues"
  s/\b(nothing|no|none|zero|not|without|no[ -]longer|n'\''t)\b([[:space:][:punct:]]+(is|are|that|which|to|currently|any|of|the|a|an|more|seems|appears|looks|reads|returns)\b)*[[:space:][:punct:]]+(needs?[[:space:]]+you[a-z]*|need[[:space:]]+you|blocked|blocker[s]?|token[s]?|rotat\w*|expired|stuck|access|403|401|unauthorized)/ /gi;
  # (ii) keyword followed by a benign-tail idiom: "tokens are not a constraint",
  #      "access is not an issue", "the blocker is no longer a problem". Strips the
  #      keyword when a "(is/are/was) not a {constraint|issue|problem|blocker|concern}"
  #      tail closely follows it.
  s/(needs?[[:space:]]+you[a-z]*|blocked|blocker[s]?|token[s]?|rotat\w*|expired|stuck|access)([[:space:][:punct:]]+\w+){0,3}[[:space:][:punct:]]+(is|are|was|were|'\''s|'\''re)?[[:space:]]*(not|no[ -]longer|never)[[:space:]]+(an?[[:space:]]+)?(constraint|issue|problem|blocker|concern|worry)/ /gi;
' 2>/dev/null)"
# perl-missing fallback: if perl failed, SCAN is empty → scan the raw haystack.
[ -z "$SCAN" ] && SCAN="$HAYSTACK"

if ! printf '%s' "$SCAN" | grep -qiE "$ESCALATION_RE"; then
  # Captain-facing send, but no (un-negated) escalation language — stay silent
  # (the common "here's the status, all green / nothing needs you" case).
  exit 0
fi

MATCHED_KW="$(printf '%s' "$SCAN" | grep -ioE "$ESCALATION_RE" | head -1)"

# ------------------------------------------------------------------
# 5. Log the fire (FP-rate observability — same convention as the sibling hook).
# ------------------------------------------------------------------
REPO_ROOT="${REPO_ROOT:-${CABINET_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}}"
LOG_DIR="$REPO_ROOT/cabinet/logs/hook-fires"
LOG_FILE="$LOG_DIR/captain-escalation-precheck.jsonl"
NOW_ISO="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
mkdir -p "$LOG_DIR" 2>/dev/null
LOG_LINE="$(jq -cn \
  --arg ts "$NOW_ISO" \
  --arg officer "$OFFICER" \
  --arg matched "$MATCHED_KW" \
  '{ts:$ts, hook:"captain-escalation-precheck", officer:$officer, matched_keyword:$matched}' 2>/dev/null)"
[ -n "$LOG_LINE" ] && echo "$LOG_LINE" >> "$LOG_FILE"

# ------------------------------------------------------------------
# 6. Inject the non-blocking advisory. The send PROCEEDS; this surfaces in the
#    Chair's next turn (additionalContext on PreToolUse — same mechanism as
#    build-vs-buy-precheck.sh).
# ------------------------------------------------------------------
WARN="⚠️ DEEP-DIVE CHECK before escalating to Nate: (a) did you TEST the claim (auth the token / fetch the asset / check the date)? (b) can you self-serve via Chrome/computer-use (create account, pull API key, configure the dashboard)? (c) checked the decision trail? Escalate ONLY the genuine residual that ONLY Nate can do (a payment, a personal/legal call).

[Triggered by escalation/blocker language (\"${MATCHED_KW}\") in a Captain-facing send. Rules: verify-before-surfacing + deep-dive-and-fix-before-escalating (shared/interfaces/captain-patterns.md). Advisory only — the send is NOT blocked; if you have already deep-dived + verified + fixed and this is the genuine residual, proceed. Disable via CAPTAIN_ESCALATION_HOOK_ENABLED=0.]"

jq -n --arg ctx "$WARN" '{hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: $ctx}}'
exit 0
