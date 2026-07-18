# Checkpoint review — feat/config-rot cp1 (2026-07-18)

Integrator checkpoint (FW-019) for the config-rot wave: TWO reviewed lane
diffs landed as one unit on a clean worktree off origin/master @b8d49277 —
briefing-tz (builder → 2-lens review → fix pass P2/P3/P4 → re-verify incl.
the tr-d quote-strip mutant) and charter (builder → review → mutant pass).
Staged churn ~2,571 insertions / 74 deletions across 39 lane files plus the
docs-sweep allowlist, the ledger pair and this artifact. Lanes touch
DISJOINT file sets; no cross-lane merge was needed. Fresh-instance-first:
sources fixed, not symptoms — closes the silent-defaults audit findings
(2026-07-17 reminders mini-wave; recorded in the external orchestration
workspace backlog, never packaged).

## What landed

1. **Briefing-time SOURCE OF TRUTH (audit C)** — ONE key,
   `instance/config/platform.yml` `briefing_times`, resolved by the new
   `framework.env.briefing_times()` (list or CSV; YAML-1.1 sexagesimal ints
   rescued as minutes-since-midnight so an unquoted `19:30` → 1170 can
   never silently drop or shift a slot; bounds-checked; deduped; fleet
   default 07:30/19:30). `generate-plists.py` stamps the
   `com.cabinet.frontdoor-briefing` StartCalendarInterval from the key with
   a printed provenance line; the `cabinet/services.yml` calendar row and
   the `instance/config/watchdog.yml` `briefing:` block are demoted to
   documented parity-pinned MIRRORS (the watchdog keeps its no-PyYAML
   survival parser, so parity is pinned from outside). The 07:00/19:00
   prose rot (preset + instance cos.md, /cabinet-briefing command, deploy
   runbook, coo quarter-close — wrong to the Captain's face for weeks) is
   fixed and pinned by `cabinet/scripts/tests/test_briefing_time_parity.py`
   (PROSE_FILES: any HH:MM on a briefing-mentioning line must be a declared
   slot; example twins must ship `briefing_times` + every comms-surface
   DEFAULTS key incl. the once-missing `hard_all_cap`).
2. **TZ unification** — `framework.env.captain_timezone()` is THE one
   resolver: default flipped silent `Europe/Berlin` → **UTC with ONE loud
   stderr warn** (cache suppresses repeats; unloadable IANA names count as
   unconfigured and warn naming the bad value). The attention gate + comms
   surface engine fall THROUGH an unloadable `CABINET_CAPTAIN_TZ` (e.g.
   leaked YAML quotes) to the resolver instead of silently assuming UTC;
   `watchdog/check.py` rides env-or-resolver; the 5 wrapper one-line greps
   (`run-frontdoor-briefing.sh`, `run-outcome-watchdog.sh`,
   `start-inbound-poller.sh`, `cron/surface-pin-tick.sh`,
   `org-health-audit.sh`) quote-strip via `tr -d` (a QUOTED
   `captain_timezone` — the runbook's own shape — must not leak quotes into
   the env → ZoneInfo reject → silent UTC) and warn loudly when the key is
   missing; final fallback UTC everywhere (was a Berlin-here/UTC-there
   split = two different quiet-hours clocks).
   `test_briefing_tz_hardening.py` executes each wrapper's REAL
   `CAPTAIN_TZ_LINE=` extraction line against fixture roots — a reverted
   `tr -d` reddens it (mutant-proven in review). `generate-plists.py`
   additionally warns (never fails) when the MACHINE tz ≠ Captain tz by
   CURRENT UTC OFFSET (Copenhagen==Berlin stays silent; a UTC-clocked
   clean-room hatch with a Berlin Captain warns). Out-of-range
   `CABINET_BRIEFING_TIMES` env slots (`25:99`) are dropped by the shared
   normalizer instead of reaching `.replace(hour=26)` (gate crash).
3. **Comms-Charter edit path (audit A/META)** — the only tunable family
   with no `.example` twin and a promised-but-absent amend verb now has
   both: tracked `instance/config/comms-charter.yml.example`
   (value-identical to `framework/attention/charter-default.yml`,
   test-pinned in BOTH directions — a default change that forgets the twin
   fails); `framework/frontdoor/charter_amend.py` — `charter: <sentence>` /
   `charter grant CHM-<hex8>` / `charter drop CHM-<hex8>` on the Captain
   channel. PROPOSE-ONLY by construction: request parses an anchored
   deterministic grammar onto bounded intents (fixed enums, HH:MM
   validated, class slugs must already exist — free text never mints a
   yaml value), validates the ENTIRE merged result against the schema
   FAIL-CLOSED before any write, files a card with the rendered yaml diff
   into the gitignored `comms-charter-proposals.jsonl` sidecar
   (content-fingerprint ids — re-filing is idempotent). Grant re-derives +
   re-classifies at grant time (§4.10.4 asymmetry, conservative: only
   provably-quieter is `quieten` → chair-trust auto-apply; everything else
   is `louder` and applies ONLY with the grant reply's own inbound
   Telegram message id as citable Captain provenance — the poller passes
   `mid or None`, so a missing id refuses instead of forging a receipt).
   Matched verbs are TERMINAL including refusals; `None` ⇒ byte-identical
   fall-through (collision corpus vs every existing binder verb family).
   Runbook `docs/runbooks/comms-charter-amend.md`; charter-default.yml
   header now points at the real ladder.

## Integrator deltas beyond the two lane diffs

- `cabinet/scripts/docs-sweep-allowlist.txt`: 3 entries (comms-charter.yml
  override + amendments/proposals jsonl — gitignored runtime ledgers the
  new runbook must name; sweep was RED n=10 pre-staging, GREEN 58/0 after
  staging + entries).
- Ledger row CONFIG-ROT-1 + plan-doc parity row (A13 + uniqueness + status
  gates green pre + post).

## SCHG guard

`ls -lO` on the live-tree counterpart of every touched path: ZERO locked.
The known germline target `memory/golden-evals/eval-006-briefings-on-
schedule.md` (07:00/19:00 rot INSIDE the locked eval — a judge asserting
the WRONG slots) is NOT edited: fix staged at
`patches/germline-eval-006-briefing-times-2026-07-18.patch` (target
re-verified schg-locked 2026-07-18, file + dir). RESIDUAL: Captain
unlock-window ceremony applies it, then the eval file joins
`test_briefing_time_parity.py` PROSE_FILES.

## Gates at this checkpoint (worktree, python3.12)

- Lane suites: briefing parity + tz-hardening 33 passed; env/gate/comms
  config 138 passed; charter (test_charter + test_reply_binder_charter)
  58 passed.
- Full-fleet `generate-plists.py` render to tmp: exit 0, 46 plists
  lint=OK, provenance line `stamped from platform.yml briefing_times →
  07:30,19:30`, stamped calendar exactly 07:30/19:30, no machine-tz
  false alarm (Copenhagen vs Berlin — same offset, correctly silent).
- framework/frontdoor 1088 passed / 21 skipped; framework/attention 291
  passed; framework/comms 199 passed; framework/watchdog 55 passed;
  framework/tests 1067 passed / 1 skipped.
- Full cabinet/scripts/tests: 1686 passed / 5 skipped; the 2 initial fails
  root-caused NOT-lane: `test_docs_sweep` real-tree calibration ran mid-run
  against the not-yet-staged tree (green on serial re-run post-staging);
  `test_evidence_seam_bypass_replay[evidence-access.sh]` is PRE-EXISTING
  live-box env state — the harness's two ALLOW probes come back blocked
  (observe-only soak marker intercepting Bash, the known class from the
  evidence-phase1 wave), reproduced byte-identical on a PRISTINE b8d49277
  worktree; master CI run 29646100273 is green at that same SHA — CI is
  the authority.
- docs-track-code-sweep: GREEN (files=58 findings=0).
- check-layer-separation: baseline=24 current=43 new=0 (OK).
