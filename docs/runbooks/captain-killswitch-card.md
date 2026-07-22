# /killswitch Card Runbook — the emergency stop on the Captain's phone

**Status: LIVE with the inbound poller** (Phase 1 of the
captain-controls-no-terminal plan, 2026-07-17). The Captain sends
`/killswitch` to the officer bot; the POLLER — not the Chair, not any LLM —
replies with the standing control card: a fresh switch-state line plus inline
`[⏹ Halt] [▶ Resume]` buttons. Taps execute the sanctioned script and repaint
the card with the script's own verified words.

## The one law, applied here

Software — including every AI in the cabinet — must not be able to flip the
switch alone. This card routes through the captain-held Telegram factor:

- the **text command** and every **tap** are captain-chat-gated in
  `officer-inbound-poller.py` (a stray's tap is acked so the spinner clears,
  then dropped — never applied, never journaled, never relayed);
- callback payloads are minted ONLY by `decision_card.cb` from the
  allowlisted verb enum (`cv2|ksh` = Halt, `cv2|ksr` = Resume, **no
  argument**); `tap_wire` re-validates the verb and refuses ANY payload
  fail-closed before anything runs;
- execution is the poller's **seam-injected door only**
  (`run_kill_switch` → `bash cabinet/scripts/kill-switch.sh <action>`).
  Importing `tap_wire` grants nothing: with no `ks_exec` seam the verbs are
  refused, so an officer session calling `apply_tap` cannot flip the switch —
  and the officer-side pre-tool-use refusal (EVAL-001b) stays intact as its
  own, untouched door
  (`cabinet/scripts/tests/test_killswitch_telegram_card.py` pins both doors
  in one test).

## E-stop asymmetry (unchanged)

HALT stays easy for everyone — `kill-switch.sh activate` is unrestricted by
design and this lane adds a door, never a gate. RESUME requires the captain
factor: the only sanctioned no-terminal resume is a captain-chat-gated tap on
this card. The terminal remains the nerd path
(`bash cabinet/scripts/kill-switch.sh deactivate`).

## The pieces

| Piece | What it does |
|---|---|
| `cabinet/scripts/officer-inbound-poller.py` | `/killswitch` routing (anchored regex, `@botname`-tolerant); `run_kill_switch` — the ONLY shell-out, `CABINET_OFFICER=captain-telegram`; `killswitch_command_reply` sends the card; `apply_tap_live` injects the `edit_text` + `ks_exec` seams. |
| `framework/comms/surface/killswitch_card.py` | PURE face: status-line wording (fail-closed UNKNOWN ⇒ "treat it as ARMED"), the verbatim script-report block, the Halt/Resume keyboard mint. No redis, no subprocess. |
| `framework/comms/surface/decision_card.py` | The verb enum — `ksh`/`ksr` appended; `cb()` remains the single mint. |
| `framework/comms/surface/tap_wire.py` | `_apply_killswitch`: payload re-validation, seam-only execution, fresh `status` re-read, loud-failure repaint, receipt floor. |
| `cabinet/scripts/kill-switch.sh` | **Untouched, germline-locked.** Read-back verification and the `kill_switch_activated/_deactivated` audit rows live HERE — the card only ever quotes it. |

## Provenance

Every phone flip is attributable: the script's own audit row records
`actor=captain-telegram` (vs `captain` for terminal flips, or an officer name
for sanctioned officer activations). Unverified flips emit nothing — a failed
flip shows 🚨 on the card with the script's stderr verbatim instead.

## Failure modes

| Symptom | Meaning | What happens |
|---|---|---|
| Card says `⚠️ UNKNOWN … treat it as ARMED` | `status` rc 2 — control plane unreachable | Fail-closed wording; buttons stay live for retry. |
| Card says `🚨 HALT/RESUME FAILED — NOT verified` | flip rc ≠ 0 (redis down, write unverified) | Loud face + the tap also relays the bracket line to the Chair (for a failed HALT the Chair is a legitimate fallback halter; a failed RESUME relay gets the officer-side refusal restated — honest). No audit row (the script emits only on verified flips). |
| `/killswitch` answered by the Chair in prose | card send failed (Telegram error) | Fail-open floor: the command falls back to the normal relay, never silently consumed. |
| Buttons do nothing for a non-captain | working as designed | Ack-only; the captain gate sits before the door. |

## Verify

```
python3.12 -m pytest framework/comms/surface/tests/test_killswitch_card.py \
  framework/comms/surface/tests/test_tap_wire_killswitch.py \
  cabinet/scripts/tests/test_killswitch_telegram_card.py -q
```

Redis-backed cases use a disposable `redis-server` (skip when binaries are
absent) — the live switch is never touched by tests.

## Out of scope (other Phase-1 lanes)

The raw-write re-arm watchdog (cleared-without-an-audit-row ⇒ re-arm +
captain notification) and the dashboard/World skins are separate lanes of the
same plan — this runbook covers only the Telegram card.
