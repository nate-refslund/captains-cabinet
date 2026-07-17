# Captain controls without a terminal (ratified 2026-07-17)

**Captain ruling (2026-07-17):** any captain — the design target is a
pensioner, not an engineer — must be able to operate every captain-only
control (the kill switch, the constitution unlock/relock) from the
dashboard, the World, or their phone, without ever touching a terminal.
The terminal remains available as the nerd path, never the required one.
Orchestrator design proposed, Captain ratified verbatim: "yes, this is
the way to do it".

## The one law the UX must not break

Both switches exist so that **software — including every AI in the
cabinet — cannot flip them alone**. "Simple" therefore never means "a
button anything on the machine can press"; it means "one tap that only
the captain can perform". Anything served on localhost (dashboard, World)
is pressable by any AI with a browser tool, so no localhost surface may
execute a captain-only action directly — it may only *request* it,
routed through a captain-held factor:

1. **The captain's Telegram identity** — already the cabinet's trust
   anchor; taps arrive on the captain's own device, gated by chat id,
   through the verified tap door (`decision_card` minter → `tap_wire`
   re-validation, allowlisted verb enums, bounded payloads).
2. **The OS authorization prompt** (Touch ID / admin password) — the
   macOS-native factor for root-level actions, via a privileged helper.

## Principles (bind every phase)

- **Emergency-stop asymmetry:** HALTING stays easy for everyone —
  officers, dashboard, World, captain, any script may arm the kill
  switch (`activate` is unrestricted by design). RESUMING requires the
  captain factor. Easy-on, hard-off, like a physical E-stop.
- **Every flip is attributable:** all sanctioned transitions ride
  `kill-switch.sh` (audit rows `kill_switch_activated/_deactivated`,
  landed @cbf1c8ef+ceremony 2026-07-17). Unlock windows get the same
  treatment (see Phase 3: `germline_unlocked/_relocked` events).
- **Raw-write backstop:** local Redis has no auth, so a raw `DEL
  cabinet:killswitch` bypasses everything silently (the 2026-07-15→16
  unattributable clearing). A watchdog re-arms the switch whenever it is
  cleared WITHOUT a matching audit row inside a short window —
  fail-safe, no secret handling.
- **Discoverability is a safety feature:** onboarding SHOWS every new
  captain the emergency stop and the unlock flow during the interview
  (per the interview-as-discoverability principle — a safety switch
  nobody knows about is an invisible feature).
- **Skins route, never execute:** dashboard tile and World lever render
  status read-only and *request* flips through phase-1's Telegram
  confirmation (later: the Touch ID helper). One door, many skins.

## Phase 1 — kill switch on the phone (build NOW, on master)

Ships with the fresh `~/.cabinet/runtime` hatch since the hatch pulls
from this repo; nearly all machinery exists (reminders-mini wave built
the same card/tap/verb shapes).

- `/killswitch` bot command + a standing control card: status line +
  `Halt` / `Resume` buttons. Buttons carry allowlisted verbs through the
  `decision_card` minter; `tap_wire` re-validates before composing the
  action; the callback path is captain-chat-gated in the poller.
- `Resume` executes `kill-switch.sh deactivate` (read-back verified +
  audit row; actor records the telegram provenance). `Halt` executes
  `activate`. Failure of either → the card says so; never silent.
- Re-arm watchdog: a small tick (launchd) compares switch state against
  the newest `kill_switch_*` audit row; cleared-without-a-row → re-arm +
  one captain notification ("the emergency stop was cleared by something
  that didn't sign its name — I re-armed it").
  *As built (2026-07-17, per 2026-07-07 full-autonomy grant): the verdict
  keys on PROVENANCE, not row order — newest arm of any provenance vs
  newest SANCTIONED deactivation (`payload.via="kill-switch.sh"`) at/after
  it — because the staged authority-transitions sweep emits OBSERVED
  `kill_switch_deactivated` rows (actor `authority-watch`, no `via`) that
  merely describe a raw clear; the literal newest-row rule would let that
  sweep mask every clear it observes
  (`cabinet/scripts/killswitch-watchdog.py`).*
- Teeth: golden-eval/pytest pins — officer-side deactivate stays
  hook-refused (EVAL-001b unchanged); the tap door rejects out-of-enum
  verbs; the watchdog's re-arm proven against a disposable redis.

## Phase 2 — dashboard tile + World lever (skins)

Status tile on the dashboard home; a lever/beacon in the World render.
Both read-only for state; their "flip" affordance sends the Phase-1
Telegram confirmation card to the captain's phone. No localhost-served
route may execute a captain-only transition (see the one law).

## Phase 3 — constitution locks behind Touch ID (native milestone)

The unlock genuinely requires root — that is the design (even the user
account cannot edit the constitution; only the OS's own authorization
can). The pensionist-grade path is the macOS privileged-helper pattern
(`SMAppService` daemon + Authorization Services), surfaced through the
menu-bar companion (`cabinet/companion/` — existing germline surface):

- Orchestrator/officer REQUESTS an unlock window → the companion shows
  the native Touch ID / password prompt with a plain sentence ("Cabinet
  asks to unlock its constitution for 15 minutes to apply approved
  changes") → helper runs `germline-lock.sh unlock`.
- **Auto-relock on a timer** (default 15 min) or on the requester's
  done-signal, whichever first — the forgot-to-relock class dies.
- Emits `germline_unlocked` / `germline_relocked` audit events (register
  the pair in `framework/events/emitter.py`), same family as the kill
  switch — every window attributable.
- Terminal `sudo germline-lock.sh` remains fully supported (nerd path;
  also the recovery path if the helper itself is broken).
- Real native work: code signing, helper installation ceremony, its own
  adversarial review. Do not bolt on — build as its own milestone.

## Explicit non-goals

- No web-exposed control plane; everything stays device-local (Telegram
  rides the bot the captain already owns).
- No weakening of `activate` (halting must never acquire friction).
- No second config store: thresholds/timeouts live in the existing
  charter/instance config surfaces.

## Sequencing

Phase 1 lands on current master (pre-flip repo) so the fresh instance
hatches with it; Phase 2 after the fresh cabinet's dashboard is the
live one; Phase 3 as its own milestone, also public-repo-relevant (every
future captain needs it). Ledger/meta tracking: cabinet-meta BACKLOG
(program entry, 2026-07-17); no egg-ledger rows until Phase-1 lands its
first commit.
