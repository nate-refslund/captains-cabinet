# Review artifact — feat/captain-availability-dial cp1 (FW-019)

**Branch:** `feat/captain-availability-dial` · **base:** `f07787faa861f429626a75bfa0c04ff690d6f2f9`
**Provenance:** Captain ruling 2026-07-26 (captain-decisions officer-note
2026-07-26T21:11:04Z); per 2026-07-07 full-autonomy grant + 2026-07-21
ownership-on-GO.
**Design of record:** `designs/captain-perspective-retro-2026-07-26.md` §5 in the
orchestrator workspace (the ruling's written form: a captain-declared
AVAILABILITY DIAL, adjustable from Telegram, the Captain-Seat Review judging
cost relative to it, correspondence deriving from it, and the balancing rule —
the org fits the declared budget, never the reverse).

## What landed

| # | Component | Files |
|---|---|---|
| 1 | Resolver + the canonical mode table | `framework/env.py` |
| 2 | Onboarding question (fixed verb enum) | `framework/onboarding/availability.py`, `.claude/skills/cabinet-init/SKILL.md`, `cabinet/scripts/generate-instance.py` |
| 3 | Telegram verb (store owner + dispatch) | `cabinet/scripts/lib/captain_availability.py`, `cabinet/scripts/officer-inbound-poller.py`, `conftest.py` |
| 4 | Captain-Seat consumer | `cabinet/scripts/meta-cognition/captain-seat-pack.sh`, `memory/skills/cross-officer-retro.md` + doctrine-pack twin, `cabinet/evals/captain-seat/{harness.py,fixtures/}` |
| 5 | Pacing consumer | `framework/comms/surface/config.py`, `instance/config/comms-surface.yml.example` |
| 6 | Dashboard (display only) | `cabinet/dashboard/src/lib/config.ts`, `settings/page.tsx`, `settings-consumer.tsx`, `settings-mode-switch.tsx` |
| 7 | Persistence / egg / docs | `.gitignore`, `cabinet/scripts/runtime-provision.sh`, `cabinet/scripts/egg-export-manifest.txt`, `instance/config/{platform,captain-availability}.yml.example`, `docs/runbooks/captain-availability.md`, `cabinet/scripts/docs-sweep-allowlist.txt`, `cabinet/config/cognitive-architecture-contract.yml` |

## The design decisions worth arguing with

**UNKNOWN is a first-class state, not a gap to fill.** `captain_availability()`
returns the same four keys in every state; `minutes_per_day is None` is the one
unknown test. Every consumer keeps its own shipped default there. The
`--defaults` generator lane and the `skip` interview verb both write **nothing**
— the 1/3-briefing lesson (a placeholder that pretends to be an answer is worse
than an honest absence) applied literally.

**Precedence puts the phone above onboarding.** Adjustment store (latest valid
entry) → platform key → unknown. So a generator re-run can never demote a ruling
he made later from his phone, and `render_question` says so out loud when it
detects an existing declaration.

**Fail-closed per ROW, not per file.** An out-of-range number, a bool, an
unknown mode with no number: each reads as *absent at that level*, so the
next-oldest ruling stands. Nothing is clamped or repaired into a figure nobody
declared.

**One mode table.** `framework.env.AVAILABILITY_MODES` is read by the interview
question, the phone grammar, the generator's validator and every renderer. A
band change lands everywhere; the negative-control test proves the question is
not a hardcoded copy.

**Verbatim captain text is a COMMENT, never a value.** `_comment_safe` flattens
control characters, so a newline in his message cannot become a second YAML line
in the file his own budget lives in.

**One knob on the pacing side.** `cap` only, derived only when the deployment
set no cap of its own; `availability_pacing: false` turns it off. Front-door
expiry/TTL constants deliberately untouched (hardcoded and germline).

## Evidence — every new sensor shown RED before the change

Pre-change reference tree: a separate worktree at `f07787fa`. `__pycache__`
purged before every run (class-6).

**EVAL-027 (new arms carried into the pre-change tree, old pack + old skill):**
`CAPTAIN-SEAT-EVAL: RED — 5 mismatch(es)` — the two repetition-arm availability
pins, the healthy-arm ABSENT marker, and both new contract pins. Post-change:
`GREEN — 13 Part 1c clauses pinned; fixture trees unmutated` (the A4 read-only
digest arm still passes).

**Wiring suite in the pre-change tree:** 14 of 15 arms RED. The one green is
`test_pack_does_not_write_into_the_tree_it_reads` — a read-only *control* that
must be green in both directions, so its passing is the expected result, not a
blind arm.

**Guard-mutation sweep** (each guard mutated in place, the named arm run, then
reverted):

| guard | mutation | arm | verdict |
|---|---|---|---|
| bool-is-not-a-budget | drop the `isinstance(bool)` guard | `test_a_boolean_is_never_a_budget` | RED |
| 0..1440 range | drop the range check | `test_a_malformed_latest_entry_falls_back_to_the_last_valid_one` | RED |
| store beats platform | read platform unconditionally | `test_adjustment_store_beats_the_platform_stamp` | RED |
| YAML-datetime rescue | drop the `datetime` branch | same arm's `set_at` | RED |
| 0 is a declaration | `is None` → falsiness | `test_away_is_a_ruling_not_an_absence` | RED |
| unknown changes nothing | return the floor on unknown | `test_unknown_budget_leaves_the_shipped_cap_untouched` | RED |
| configured cap wins | ignore the configured value | `test_a_configured_cap_always_wins_over_the_budget` | RED |
| refuse-don't-round | drop the integrality refusal | `test_fractional_minutes_are_refused_rather_than_rounded` | RED |
| comment-safe | drop the control-char flatten | `test_multiline_text_cannot_break_out_of_its_comment` | RED |
| skip writes nothing | make `skip` fall through to the write | `test_skip_writes_nothing_at_all` | RED |
| question from live table | hardcode the option prose | `test_question_follows_the_live_table_not_a_hardcoded_copy` | RED |

**One blind arm found and fixed, in this file's own class-11 spirit.** The first
sweep showed the grammar-anchor arm STILL GREEN under `match`→`search`, under
dropping the leading `^`, and even under both — because the *tail* anchor was
doing all the rejecting for every case in the list. Measured, then fixed by
adding the case only the START anchor rejects (`"so availability 20m"`); the
pair mutation is now RED and each single mutation is still green, which is the
same finding the score grammar recorded and is now written into the regex's own
comment rather than asserted.

## Gates run this session

| gate | result |
|---|---|
`cognitive-architecture-census.py` | PASS; modules 239 ≤ 239, non-comment lines 67326 ≤ 67326 (zero headroom, allowance stated at its exact measured total)
`check-layer-separation.sh` | OK — new=0 (the instance path crosses only via `framework/env.py`)
`state-persistence-preflight.py` | OK — no durable path would be lost (store added to `INSTANCE_PERSISTENT_FILES`)
`docs-track-code-sweep.sh` | GREEN (files=62 findings=0) on the STAGED tree
`framework/tests/test_env.py` | 111 passed
`framework/onboarding/tests/test_availability.py` | 21 passed
`cabinet/scripts/lib/tests/test_captain_availability.py` | 37 passed
`cabinet/scripts/tests/test_captain_availability_wiring.py` | 15 passed
`cabinet/scripts/tests/test_briefing_time_parity.py` | 8 passed
`cabinet/scripts/tests/test_memory_distill.py` | 19 passed (doctrine-pack byte parity)
`cabinet/scripts/tests/test_cognitive_architecture_census.py` | 29 passed
`framework/tests/test_no_launcher_hardcode.py` | 21 passed
`cabinet/evals/captain-seat/harness.py --self-test` | GREEN
dashboard `tsc --noEmit` | exit 0
dashboard `vitest run` | 2204 passed, 1 skipped

## Doctrine checks

- **Never-a-score.** The dial is a value the Captain typed about HIMSELF — not
  evidence-derived, not about an officer, and it is read as a BUDGET (what may
  reach him), never rendered as a measure of anyone. Repeat counts in the retro
  stay retro inputs. No new file names the report-only suite-scalar series by
  either scanned token, so its consumer allowlist is untouched (this paragraph
  deliberately avoids quoting those tokens — the previous cp1 in this directory
  tripped the guard by quoting one).
- **Layer separation.** `framework/onboarding/availability.py` and
  `framework/comms/surface/config.py` reach instance config only through
  `framework.env` resolvers (`captain_availability_path`,
  `cabinet_init_answers_path`); the gate reports new=0.
- **Test fence.** `CABINET_CAPTAIN_AVAILABILITY_FILE` is fenced in the repo-root
  `conftest.py` at birth, for the same reason the score store was: a fabricated
  row would tell the org it may spend time the Captain never offered.
- **Fail-open relay.** The poller branch is Captain-id-gated, archives the DM,
  records before it confirms, and relays his words to the Chair on any error —
  a message is never silently eaten.
- **Germline.** Nothing schg-locked was touched. The onboarding bridge/dir the
  brief named off-limits (`api/onboarding`, `lib/onboarding/bridge.ts`,
  `journey-card.tsx`, `framework/onboarding/journey.py`) is untouched — no lock
  was hit, so there is no handback.

## Known limits, stated rather than hidden

- **The pack reads the store with a line-shaped regex, not the resolver.** It
  must, because the eval points `CAPTAIN_SEAT_ROOT` at a fixture tree while
  `framework.env` would read the real deployment — and the pack imports stdlib
  only. Consequence: a hand-written mode-only row reads as absent in the pack
  where the resolver would derive the band. That can only ever under-claim,
  never invent a budget, and it is stated in the section's own comment.
- **The dashboard is display-only.** No platform.yml write action exists yet
  (the same tech-debt as Timezone). It mirrors the resolver's precedence so it
  cannot show a value the runtime does not use.
- **Correspondence beyond the pacing cap is not wired.** The ruling's
  "correspondence derives from it" reaches ONE knob in this unit; expiry clocks,
  FYI-vs-demands-a-response classification and batching are not yet availability
  aware. Deliberate scope, not an oversight — the frontdoor TTL constants are
  germline and were declared off-limits for this unit.
- **`full_time` = 480 min/day** is the framework's stated reading of a full
  working day, not something the Captain said. An explicit number always wins,
  and the reading is documented where a reader will hit it.
