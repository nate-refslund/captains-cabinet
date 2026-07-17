# Checkpoint review — feat/reminders-mini cp1 (2026-07-17)

Integrator checkpoint (FW-019) for the reminders mini-wave: TWO reviewed
lane diffs landed as one unit on a clean worktree off origin/master
@ed5b64d8 — instant-buttons (instant push + tap buttons + root fix) and
quiet-hours-interview. Staged churn 1,698 insertions / 26 deletions across
17 files (15 lane files verified against the two lane manifests — nothing
extra, nothing dropped — plus the ledger pair). Lanes touch disjoint file
sets; no cross-lane merge was needed.

## What landed

1. **instant push** (Captain ruling 2026-07-17 — *"the time of day is set
   by the captain → push instantly"*) — `captain-reminder-arm.py` gains
   `build_push_item`/`push_card`/`reminder_buttons`: after the needs card
   files, ONE `kind="captain-reminder"` item rides the attention gate at
   fire time. Primary: the charter default's new kind-matched
   `captain-reminder` FLOOR class (Captain provenance recorded on the
   floor comment — the §4.10.4 louder-needs-Captain path; floor placement
   also exempts the class from H5 expiry-streak demotion). Belt: a real
   `deadline_iso=due_at` + `urgency=ping-now`, so an instance charter
   missing the class still delivers via the gate's structural deadline
   pierce — and a deadline beyond the next briefing does NOT pierce (no
   free loudness, test-pinned). Per-fire uuid5 situation identity: a
   snooze-bumped `due_at` re-pushes; a crash-before-mark re-file
   suppresses. Push failure = one stderr line; the briefing digest stays
   the durable fallback; the tick never breaks.
2. **tap buttons** — `[✓ Done] [⏰ Later 7d] [✗ Drop]`. Callback payloads
   are the fixed verb enum + the need id's 8-hex tail ONLY
   (`cv2|ndg/ndl/ndd|<hex8>`, minted by the allowlisted
   `decision_card.cb`, ≤64 bytes) — the untrusted reminder title never
   rides a button (it is card DATA: U+00B7 pid-marker stripped, one-line,
   clipped). `tap_wire._apply_need` re-validates
   `fullmatch [0-9a-f]{8}` BEFORE composing the CANONICAL typed binder
   line (`grant/later/deny NEED-<hex8>`) and routes it through the SAME
   door as the Captain's typed replies (`binder_wire.handle_captain_update`
   with its own CABINET_NEEDS_WIRED + stale-id fail-closed gates); door
   refusal relays to the Chair; a markup-receipt failure never un-handles
   the tap. Injection controls pinned: hostile titles (quotes, `$()`,
   backticks, markdown, U+00B7, newlines) stay data end-to-end and never
   change callback bytes; malformed/uppercase/oversized args never reach
   the composer.
3. **root fix** — `remind-captain.sh` dropped the dead convergence-era
   `CABINET_ROOT=/opt/founders-cabinet` default (existed on no live box;
   every env-less direct run failed the context lookup) for
   script-relative resolution from `$HERE/../..` (explicit env still
   wins); the missing-context refusal now names the RESOLVED path.
   Test matrix: repo-root cwd, unrelated cwd, refusal path names this
   repo never /opt, explicit override wins, no /opt string left.
4. **quiet-hours interview question** (Captain insight 2026-07-17 — a
   silent default is an invisible feature) — new
   `framework/onboarding/quiet_hours.py`: `render_question` reads the
   LIVE `framework/attention/charter-default.yml` (never hardcoded — a
   changed default changes the question, negative-control pinned;
   malformed default fails closed); `apply_answer` accepts only the fixed
   verb enum keep/change/disable + strict 24h HH:MM (free text and
   injection strings refused before any write, byte-untouched charter
   proven); every write rides `charter.amend` (schema-validated
   fail-closed BEFORE write, atomic replace, amendments-ledger provenance
   row `trust=chair via=cabinet-init-interview`); `keep` never silently
   reverts a standing override; `disable` = the zero-length window proven
   at the GATE level; `floor_classes` carried unchanged — the question can
   neither widen nor quietly re-widen the floor (Captain-narrowed floor
   preserved, test-pinned). `.claude/skills/cabinet-init/SKILL.md` gains
   the Phase-2 step; `.gitignore` gains the deployment override + its
   amendments ledger (runtime files, never tracked).
5. **ledger** — REMIND-2 appended (status=done) + plan-doc §43 parity row.

## Review posture

Both lane diffs arrived pre-reviewed from their build lanes (lane
deliverable contract); integrator re-verification here is independent:
full suites re-run on the merged tree, injection/negative controls read
and confirmed present in the test bodies, charter YAML change read line
by line (floor addition + one kind-matched class; no matcher widening on
any other class), `.gitignore` additions confirmed deployment-local only.
Corridor plan analysis run pre-apply: no guardrail flags (matches the
house allowlisting/fail-closed conventions).

## Verification evidence (this worktree, python3.12)

- Lane suites: `test_captain_reminder_instant.py` +
  `test_remind_captain_rootfix.py` → **21 passed**;
  `test_gate_captain_reminder.py` + `test_tap_wire.py` +
  `test_quiet_hours.py` → **53 passed**.
- Full `cabinet/scripts/tests`: **1392 passed, 4 skipped** (pre-existing
  skips only).
- Full `framework/attention` + `framework/comms` +
  `framework/onboarding`: **644 passed, 1 skipped**.
- `bash -n cabinet/scripts/remind-captain.sh` clean.
- `docs-track-code-sweep.sh` GREEN (files=44 findings=0).
- `check-layer-separation.sh` new=0 (baseline=24 allowlist=18 current=42).
- Ledger gates pre AND post edit: A13 parity PASS, id-uniqueness PASS,
  `ledger-status-parity.sh` GREEN (326 ids = 326 md rows, findings=0).
- SCHG guard: `ls -lO` on every touched live-box path — zero `schg`
  flags; no locked hunks, nothing staged for a ceremony window.
- No `cabinet/services.yml` change → no generate-plists render in this
  wave; no DB schema change.

## Residuals

- None new. The runbook's former "Known residual" (no at-fire-time push)
  is closed by this wave and rewritten in place.
