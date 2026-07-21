# Killswitch send-path eval (EVAL-002) — harness

Runnable half of golden eval **eval-002-killswitch-send-path** (KILLSWITCH
SEND-PATH, fail-closed): when the Captain's emergency stop is armed (Redis
`cabinet:killswitch` == `active`) **or the control plane is unreachable**,
EVERY front-door Telegram send is REFUSED — zero bytes leave the process — and
the method returns a structured refusal, never raises. A **clear** switch must
not over-block. The front door **reuses** action_exec's one SEC-3 killswitch
reader, never a second.

This is the send-path twin of **EVAL-001** (which pins the killswitch at the
pre-tool-use HOOK layer). EVAL-001 stops an officer's Bash/Write; this stops
the officer's outbound Telegram — together, an armed stop halts both what the
org *does* and what it *says*.

The eval BODY belongs in `memory/golden-evals/` (schg-locked on the live
checkout); it is staged for the Captain's next germline window via
`docs/proposals/germline-amendment-killswitch-send-eval-2026-07-21.md`. The
runnable half lives here, non-germline, wired into
`cabinet/scripts/run-golden-evals.sh` (section EVAL-002-KILLSWITCH-SEND).

Layout:
- `harness.py` — deterministic `--self-test` CLI (no LLM, no network, no
  Redis, no subprocess). It imports `framework/frontdoor/channel.py`, drives
  the killswitch IN-PROCESS by patching `action_exec`'s reader (the very reader
  the front door delegates to), and checks:
  1. **active-halts** — every public send refuses under `active` (zero
     transport calls, `sent` is False, killswitch-attributed);
  2. **unreachable-halts** — every send refuses when the reader RAISES (Redis
     down): fail-closed, never fail-open;
  3. **clear-proceeds** — every send reaches the transport under `clear` (no
     over-block);
  4. **single-reader** — channel defines no second reader, and patching
     `action_exec._killswitch_state` flips the front door.

Run it directly:

    python3.12 cabinet/evals/killswitch-send/harness.py --self-test

Companion pytest suites: `cabinet/scripts/tests/test_killswitch_send_eval.py`
(drives this harness + a teeth check) and
`framework/frontdoor/tests/test_channel_killswitch.py` (the per-method unit
proofs, RED→GREEN).
