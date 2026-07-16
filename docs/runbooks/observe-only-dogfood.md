# Observe-only Cabinet dogfood

Use this posture for a time-boxed soak in which the Cabinet may inspect,
reason, record internal runtime evidence, and reply/react in the existing
Captain conversation, but may not mutate product/Cabinet source, call an
untyped MCP, spawn subagents, use computer-control, or dispatch production
actions.

## Activate

```bash
bash cabinet/scripts/observe-only.sh enable
cat > instance/config/posture-narrow <<'EOF'
earn_up
EOF
bash cabinet/scripts/egress-guard.sh apply
```

Then restart every officer. A fresh Mac launch must report both
`observe_only=1` and `egress_enforced=1` in dry-run output before the real
restart. Enabling the observe marker constrains already-running tool calls
immediately; restarting adds the sticky process, computer-control removal,
clean dispatch environment, and Seatbelt layers. Egress also requires a fresh
process to inherit proxy and kernel policy.

The observe marker is Captain-side and user-immutable where macOS supports
`chflags uchg`. Do not edit it by hand. A present but malformed or symlinked
marker fails closed and refuses new officer boots.

## Enforced layers

1. `pre-tool-use.sh` permits local inspection, Todo state, the bounded
   `evidence-read.sh` projection, receipt-only `hooks/observe-ack.sh`, and only
   `cabinet-comms.reply_current` / `react_current` for Captain contact. Every
   other Bash shape, Native WebFetch/WebSearch, writes/edits, tasks, unknown
   tools, and every other MCP call are blocked. Trigger notifications expose
   their Redis receipt ID; after processing each trigger the officer ACKs that
   exact ID. This preserves consumer-side at-least-once delivery without
   granting a general Redis or shell surface, and lets retention trim the
   processed prefix during the soak.
2. The launcher pins `CABINET_OBSERVE_ONLY=1` and `CABINET_ENV=dev`, so removing
   the marker cannot widen a running process and the framework dispatch adapter
   refuses sends.
3. The generated MCP config is replaced with the closed local set
   `redis-trigger-channel` + `cabinet-comms`. Remote MCPs and their credentials
   (CUA, Neon, Vercel, Make, brain, search, etc.) never boot or enter the child
   environment; only the resolved Telegram bot token survives for comms.
4. macOS Seatbelt defaults HOME to write-denied, then allows only the officer's
   own tier-2 memory and reviewed Cabinet cache/runtime stores. Cabinet/product
   source, evidence, egress state, other officers' memory, and secrets remain
   denied.
5. `posture-narrow=earn_up` keeps every authority cell at the propose-only
   floor. This is defense in depth; it is not the sole observe-only boundary.
6. Enforced egress routes remote HTTP(S) through the hostname allowlist and
   rejects direct external TCP/UDP on macOS.

## Verify before starting the clock

- An officer `Edit` and a harmless `Bash` command are both blocked with
  `OBSERVE-ONLY BLOCK`.
- A raw socket to an external IP fails, while localhost Redis and the egress
  proxy remain reachable.
- A write to the Cabinet checkout and every configured product Git root fails
  at the OS boundary; a tier-2 observation write succeeds.
- CUA/computer-control servers are absent from the generated officer MCP file.
- The generated MCP file contains exactly `redis-trigger-channel` and
  `cabinet-comms`; the child environment has no remote-MCP credentials.
- Overlong `reply_current` text and unsupported reactions fail with zero
  Telegram requests; arbitrary/new-message sends remain blocked.
- The authority resolver reports `earn_up`; spend caps are non-zero.
- Evidence projection, Cabinet Doctor, fidelity, backup restore, and rollback
  drills are green and recorded before the 72-hour clock begins.
- The rollback drill is the exact fleet drill, not a service-count smoke test:
  `bash cabinet/scripts/test-recovery.sh --evidence-dir <readiness-dir>/recovery`.
  It refuses to begin unless the kill switch is active, the loaded jobs equal
  the enabled `cabinet/services.yml` rows plus roster officers, observe-only
  is active at `earn_up`, egress is attested, and Cabinet Doctor is green. It
  boots out and restores only that allowlist; disabled/legacy plists are never
  activation inputs. The evidence captures exact pre/post label and session
  sets, the raw observe-posture hash plus kill-switch status, egress
  runtime/status attestations, Redis result, and the Cabinet Doctor semantic
  verdict. Run `--dry-run` first to prove every precondition without changing
  the fleet.
- A synthetic trigger is delivered with an observe-only receipt, its exact
  `cabinet/scripts/hooks/observe-ack.sh <id>` command succeeds, pending returns
  to zero, and replaying the same receipt is an idempotent `already_clear`
  success.

## Honest residuals

- Linux/Docker has the hook and proxy environment but no Seatbelt. Use a
  container/host filesystem and network policy for an equivalent OS boundary.
- Same-UID macOS is not the final commercial multi-tenant boundary. Localhost
  daemons and Accessibility-authorized GUI processes can be confused deputies;
  computer-control is therefore excluded from this soak. High-autonomy
  commercialization still needs separate OS identities/App Sandbox and
  capability brokers for write credentials.
- Unsandboxed Cabinet services continue to maintain logs, ledgers, backups,
  evidence, and the dashboard. “Observe-only” constrains officer authority,
  not the operation of the audit system itself.

## Disable after the recorded decision

```bash
bash cabinet/scripts/observe-only.sh disable
rm -f instance/config/posture-narrow
# Egress widening is a separate Captain unlock/edit/relock decision.
```

Restart officers. Disabling is intentionally sticky-safe: a process launched
under observe-only remains capped until it is replaced. Do not widen authority
as part of the soak itself; make that a separate Captain decision after the
signed evidence review.
