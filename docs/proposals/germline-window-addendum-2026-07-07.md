# Germline Window Addendum — Claude Code audit one-liners (2026-07-07)

**Purpose.** The 2026-07-07 setup audit (`~/cabinet-claude-code-audit-2026-07-07.md`) surfaced a batch of
one-line/near-one-line fixes whose targets are **schg-locked germline files**. None can be applied by an officer;
ALL of them ride **tonight's unlock window** as one batch (CG-13 pattern: unlock → apply → test → relock same day).
Line numbers verified against the live tree at branch `feat/fidelity-harness-design` (2026-07-07 15:xx). Apply order
is as listed; every edit is independent. After the batch: `bash cabinet/scripts/run-hook-regression.sh` +
`python3.12 -m pytest framework/ -q` + `germline-lock.sh verify` green, relock same day.

Non-germline rows from the same audit are tracked as AUD-1..AUD-12 in
`docs/plans/operative-egg-ledger-2026-07-07.yml` (plan §10 addendum). Audit #6 (flip-to-Fable) is **SUPERSEDED**
by the Captain ruling 2026-07-07 pinning `claude-opus-4-8[1m]` — no model edits in this window.

---

## 1. Audit #2 — pre-captain-dm hook `"timeout": 120`

- **File:** `.claude/settings.json` (schg)
- **Where:** `hooks.UserPromptSubmit[0].hooks[0]` — the pre-captain-dm entry (~line 42–47).
- **Edit:** add a sibling key to the hook object:
  ```json
  {
    "type": "command",
    "command": "bash",
    "args": ["${CLAUDE_PROJECT_DIR}/cabinet/scripts/hooks/pre-captain-dm.sh"],
    "timeout": 120
  }
  ```
- **Why:** UserPromptSubmit default timeout is 30s; the voice path budgets up to ~100s of synchronous network and
  emits its single JSON payload only at the end (pre-captain-dm.sh:319) — slow voice DMs silently lose transcript +
  semantic-recall block.
- **Test:** `python3 -c "import json; json.load(open('.claude/settings.json'))"`; then send a voice DM to a live
  officer and confirm the transcript block lands in the prompt (or replay the hook with a stub payload and `time`
  it past 30s without a kill).

## 2. Audit #4 (germline half) — flip pre-tool-use.sh §9 two fail-open paths to exit-2

- **File:** `cabinet/scripts/hooks/pre-tool-use.sh` (schg)
- **Path A — parser failure swallowed (line 1856):**
  `python3 - "$MCP_SCOPE_FILE" "$MCP_SCOPE_CACHE" <<'PY' 2>/dev/null || true`
  → capture the exit: on parser failure, `echo "BLOCKED: mcp-scope cache rebuild failed — failing CLOSED" >&2; exit 2`
  (matches the axes-contract "corrupt allowlist loads EMPTY" doctrine).
- **Path B — unknown-officer warn-and-allow (lines 1917–1922):** replace the
  `WARN: … Allowing '$MCP_SERVER' call …` branch with
  `echo "BLOCKED: mcp-scope — officer '$AGENT_KEY' has no entry in cabinet/mcp-scope.yml." >&2; exit 2`.
  (Hiring-flow ergonomics: create-officer.sh must add the mcp-scope entry BEFORE first boot — it already edits
  config in the same flow; a bricked unscoped call is the desired signal now that the structural launch-time
  scoping [audit #4, commit e206bdae] is live fleet-wide.)
- **Note:** the launch-time half (per-officer `--mcp-config` + `--strict-mcp-config` + `--settings` overlay) is
  already deployed and live on all 4 officers as of the 2026-07-07 rolling restart; this hook flip is
  defense-in-depth hardening only. `enableAllProjectMcpServers: true` at `.claude/settings.json:35` may also be
  flipped to `false` in the same window (officer sessions already override it per-officer; flipping the germline
  default protects captain-started sessions too).
- **Test:** `bash cabinet/scripts/run-hook-regression.sh`; manual: `OFFICER=nonexistent` + a synthetic
  `mcp__brain__*` tool call through the hook → expect exit 2; corrupt a COPY of mcp-scope.yml pointed via
  `MCP_SCOPE_FILE` override if supported, else rely on regression suite.

## 3. Audit #8 — delete inert `defaultMode: "auto"` from project settings

- **File:** `.claude/settings.json` (schg), line 33 (`permissions.defaultMode`).
- **Edit:** delete the `"defaultMode": "auto"` key (and its preceding comma). If auto-mode is still wanted for
  captain interactive sessions, add it to **user** settings (`~/.claude/settings.json`) instead — project-source
  `defaultMode:auto` is ignored by 2.1.202 and logs a warning every session.
- **Test:** JSON parse check; start a scratch session in the repo and confirm the per-session
  "defaultMode ignored" warning is gone.

## 4. Audit #9 — statusLine → cabinet/scripts/statusline.sh

- **File:** `.claude/settings.json` (schg), lines 359–362.
- **Edit:**
  ```json
  "statusLine": {
    "type": "command",
    "command": "bash",
    "args": ["${CLAUDE_PROJECT_DIR}/cabinet/scripts/statusline.sh"]
  }
  ```
  (Today it is bare `bash` → exit 127 → renders nothing. `cabinet/scripts/statusline.sh` already exists, built for
  gap G8; it can show OFFICER_NAME, context %, killswitch, pending triggers.)
- **Test:** JSON parse; open a session and confirm the status line renders; `bash cabinet/scripts/statusline.sh`
  standalone exits 0.

## 5. Audit #10 — delete bogus `voice` key

- **File:** `.claude/settings.json` (schg), lines 367–369.
- **Edit:** delete the `"voice": {"enabled": true}` block — not a Claude Code settings key (voice is a TUI flag +
  `/voice`); cabinet voice is actually done by the post-reply-voice hook, which is unaffected.
- **Test:** JSON parse; confirm post-reply voice still fires on a Telegram reply (hook path untouched).

## 6. Audit #11 — post-compact.sh BSD date fix + liveness stamp

- **File:** `cabinet/scripts/hooks/post-compact.sh` (schg), line 49.
- **Edit:** replace
  `CAPTURE_EPOCH=$(date -d "$CAPTURED" +%s 2>/dev/null || echo "0")`
  with the exact BSD fallback pattern already proven in post-tool-use.sh:562–564:
  ```bash
  CAPTURE_EPOCH=$(date -d "$CAPTURED" +%s 2>/dev/null \
    || date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "${CAPTURED%%.*}Z" +%s 2>/dev/null \
    || echo "0")
  ```
  Plus liveness: append one JSONL stamp per firing (officer, ts) to
  `shared/interfaces/hook-liveness.jsonl` (or the existing telemetry stream) so post-compact firing is auditable.
- **Why:** GNU-only `date -d` fails on macOS → every compaction prints "state is ~494,000h old", training officers
  to ignore the one real staleness signal.
- **Test:** `bash -n` the hook; run the hook body with `CAPTURED=$(date -u +%Y-%m-%dT%H:%M:%SZ)` and assert the
  computed age is ~0h, not ~494,000h; hook-regression suite green.

## 7. Audit #12 — Docker-era `REDIS_HOST:-redis` → `127.0.0.1` (locked hook set)

- **Files (schg):**
  - `cabinet/scripts/hooks/session-stop.sh:12`
  - `cabinet/scripts/hooks/on-session-end.sh:20`
  - `cabinet/scripts/hooks/on-post-tool-failure.sh:18`
  - `cabinet/scripts/hooks/stop-hook.sh:9` (same edit if the file survives item 8 below)
- **Edit:** `REDIS_HOST="${REDIS_HOST:-redis}"` → `REDIS_HOST="${REDIS_HOST:-127.0.0.1}"` in each.
- **Why:** any session not launched by launchd (captain interactive, subagents) has no REDIS_HOST → hooks dial the
  dead Docker DNS name `redis` → Stop-guard + session telemetry silently no-op.
- **Stragglers (grep `':-redis}'` — NOT locked, can ride a normal commit outside the window):**
  `cabinet/scripts/lib/memory.sh:26`, `lib/incr-counter.sh:15`, `lib/captain-attention.sh:40`, plus ~20 non-hook
  scripts (my-tasks, list-officers, cost-report, set-activity, resume-officer, assemble-config, create-project,
  switch-project, cabinet-spawn ×2, test-advisor-crew, release-issue, suspend-officer, org-health-audit,
  claim-issue, test-captain-attention, list-projects, publish-skill-update, cost-delta). `cabinet/deploy/docker/`
  keeps `redis` (correct in-container).
- **Test:** in a shell with REDIS_HOST unset: `bash cabinet/scripts/hooks/session-stop.sh <<< '{}'` writes its
  telemetry against 127.0.0.1 (redis-cli reachable); grep `':-redis}'` over `cabinet/scripts/hooks/` → 0 hits.

## 8. Audit #13 — cost ledger revive: move transcript-usage parse into session-stop.sh

- **Files (schg):** `cabinet/scripts/hooks/stop-hook.sh` (source of the parse, lines ~12–82) and
  `cabinet/scripts/hooks/session-stop.sh` (the hook actually wired to Stop).
- **Edit:** port the transcript-usage extraction + `cabinet:cost:tokens:*` HSET/EXPIRE block from stop-hook.sh
  into session-stop.sh (before its `exit 0` at line 81). Then either delete stop-hook.sh or leave it with a
  one-line header "UNWIRED — parse moved to session-stop.sh 2026-07-07" (Docs-Must-Track-Code: update any doc
  naming stop-hook.sh in the same window).
- **Why:** verified twice — the only writer of `cabinet:cost:tokens:daily:*` is stop-hook.sh, which is wired to NO
  event; live Redis holds zero `cabinet:cost:*` keys with 4 officers running; cost-report.sh, cron/cost-summary.sh,
  cost-dashboard.sh and the mcp-server cost surface all read an empty ledger.
- **Test:** end a session (or fire session-stop.sh with a real transcript_path payload) → 
  `redis-cli keys 'cabinet:cost:tokens:*'` non-empty; `bash cabinet/scripts/cost-report.sh` renders non-zero.
- **Follow-on:** AUD-3 (hook overhead batch) is sequenced after this decision.

## 9. Audit #14 — SessionEnd outbox relay path fix

- **File:** `cabinet/scripts/hooks/on-session-end.sh` (schg), line 42.
- **Edit:** `OUTBOX_RELAY="$CABINET_ROOT/cabinet/scripts/outbox-relay.py"` →
  `OUTBOX_RELAY="$CABINET_ROOT/framework/outbox/relay.py"` (the file that actually exists; cron wrapper
  `cabinet/cron/outbox-relay.sh` already points there). Alternatively delete the dead flush branch and let cron
  remain the only flush path — but the fix is one token, prefer it.
- **Test:** `test -f "$CABINET_ROOT/framework/outbox/relay.py"`; fire on-session-end.sh with a pending outbox row
  → flush attempt logged instead of silent skip.

## 10. Audit #20 — on-notification.sh classify on `.message`, emit `notification_received`

- **File:** `cabinet/scripts/hooks/on-notification.sh` (schg), lines 12 and 19–22.
- **Edit:**
  - Line 12: `NOTIFICATION_TYPE=$(echo "$HOOK_INPUT" | jq -r '.type // "unknown"')` → classify from `.message`
    (the field the Notification payload actually carries), e.g.
    `NOTIFICATION_KIND=$(echo "$HOOK_INPUT" | jq -r '.message // "unknown"' | head -c 120)` + a small case-pattern
    classifier (permission / idle / limit / other).
  - Lines 19–22: emit `notification_received` (not `session_started`) via `framework/events/emitter.py` so each
    notification stops polluting the session-start audit trail.
- **Test:** replay a captured Notification payload through the hook → stderr shows a real kind (not
  `type=unknown`), org_events gains a `notification_received` row and NO `session_started` row.

## 11. Audit #3b — descope the unregistered `cabinet` server from mcp-scope.yml

- **File:** `cabinet/mcp-scope.yml` (schg), line 136.
- **Edit:** `universal: [telegram, library, cabinet]` → `universal: [telegram, library]`.
- **Why:** no config layer registers a `cabinet` MCP server (verified — it exists in no `.mcp.json` variant), so
  every tool on it is unreachable while scope + docs claim it's live (Docs-Must-Track-Code violation). Descope
  until the server is actually registered; when FW-005 federation lands in a config layer, re-grant in the same
  commit that registers it. Update the CLAUDE.md "MCP Scope" list line for **Cabinet** in the same window (mark
  "declared, not yet registered — descoped 2026-07-07") — CLAUDE.md is not schg but the change is atomic with this
  one.
- **Test:** regenerate one officer config: `python3 cabinet/scripts/gen-officer-mcp-config.py --officer cos ...`
  → `cabinet` no longer in allowed set; pre-tool-use §9 cache rebuild picks up the new universal list
  (`rm /tmp/cabinet-mcp-scope.tsv` first); hook-regression green.

---

## Window close checklist

1. `python3 -c "import json; json.load(open('.claude/settings.json'))"` — settings parse.
2. `bash cabinet/scripts/run-hook-regression.sh` — green.
3. `python3.12 -m pytest framework/ -q` — green (3480 passed baseline 2026-07-07).
4. `bash cabinet/scripts/check-layer-separation.sh` — new=0.
5. `sudo cabinet/scripts/germline-lock.sh lock && cabinet/scripts/germline-lock.sh verify` — relock same day.
6. Rolling officer restart (comms → polads → stephie → cos; tmux kill-session, KeepAlive respawns, verify boot
   green + /loop armed) so the hook edits take effect fleet-wide.
