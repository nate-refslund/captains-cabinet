# Checkpoint review — feat/trial-instrument cp1

**Scope:** the 14-day briefing-value trial instrument.
**Reviewer:** the building session, adversarially, on Opus 5 (1M). This is a
SELF-review, not an independent frozen-context panel — stated plainly so
nobody reads it as two opinions. Base: `origin/master` @ `05871f12`.

## What landed

| Path | Lines | What |
|---|---|---|
| `cabinet/scripts/lib/briefing_score.py` | ~330 | the whole instrument: grammar, append-only store, summary, CLI |
| `cabinet/scripts/lib/tests/test_briefing_score.py` | ~320 | 44 arms |
| `cabinet/scripts/tests/test_briefing_score_command.py` | ~170 | 22 arms on the phone door |
| `cabinet/scripts/officer-inbound-poller.py` | +85 | `/score` mechanical branch + docstring |
| `conftest.py` | +12 | `CABINET_BRIEFING_SCORES_DIR` write fence |
| `.gitignore` | +6 | the store is runtime data |
| `docs/runbooks/captain-briefing-score.md` | new | the runbook |

## Defects found and fixed DURING the build (all by adversarial passes, not
by the happy path)

1. **Two same-second unbound scores collapsed into one.** The summary keyed
   unbound rows on their timestamp, so two scores recorded in the same second
   read as one. Found by the very first smoke run. Fixed to key on position;
   `test_two_unbound_scores_in_the_same_second_are_two_scores` pins it.
2. **`/score 3.5` silently recorded 3.** The lookahead blocked a following
   digit but not a decimal separator. The Captain is Danish and would write
   `2,5`; both now REFUSE so he retypes. A number the instrument cannot
   represent must never be quietly rounded.
3. **`summarize(days=0)` silently meant "all rows".** `if days` is falsy at 0.
   Now `days is not None` — a caller who asked for an empty window gets one.
4. **A test claimed a guard that was not the real one.** The mutation sweep
   showed removing `^` from the regex left the suite green, because
   `re.match` already anchors. The docstring claiming `^` as THE anchor was a
   false claim on the claim surface; corrected to name the pair, and the
   mutation is now compound.
5. **A product token leaked into `cabinet/`.** Example strings said "VIES";
   `cabinet/` must not name a product. Replaced.

## Evidence

- **19/19 targeted guard mutations proven** — each named guard mutated in
  place, the specific arm shown to go from rc=0 to rc=1, source restored.
  Absence-failure was NOT used: on a brand-new module every arm would fail on
  ImportError for reasons unrelated to what it claims.
- 66 new tests, both suites in CI-collected directories (`cabinet/scripts/lib/tests`
  via the "full lib suite" step, `cabinet/scripts/tests` via its own step).
- Baseline re-measured before writing any code; full serial sweep after.

## Design calls a reviewer should challenge

- **Home = `instance/memory/briefing-scores.jsonl`.** Chosen because
  `runtime-provision.sh` links `instance/memory` as a WHOLE directory
  (`INSTANCE_PERSISTENT_SEEDED_DIRS`), so a file that did not exist at
  release-cut still survives a deploy with no persistence-list edit. The test
  asserts this against that script's real text, so the claim fails loudly if
  the lists change. Rejected: `memory/tier3/` (no list names it — a deploy
  strands it) and a new `shared/interfaces/*.jsonl` series (per-file list AND
  `link_instance_data` only links a leaf that already exists in shared/, so
  the FIRST write would be lost).
- **`cabinet/scripts/lib/`, not `framework/`.** `framework/` is under a
  zero-headroom census budget (`framework_production_modules: 238 <= 238`);
  landing there needs a `temporary_allowances` bump in
  `cabinet/config/cognitive-architecture-contract.yml`. That mechanism is
  sanctioned, but spending it on a 330-line operator instrument — and growing
  the exported layer for an instance-scoped trial — is disproportionate. The
  census is untouched, not relaxed.
- **The poller graft.** Requirement 1 demands a phone-usable control; the
  standing 2026-07-17 ruling says Captain controls never require a terminal.
  A CLI-only instrument would not have met it. The branch mirrors the
  already-ratified `/killswitch` mechanical shape, adds no launchd job and no
  `services.yml` row, and fails OPEN to the Chair relay at every step.

## Known limits, stated rather than hidden

- `briefing_id` is stored verbatim, including a caller-supplied
  `../../etc/passwd`. Verified non-exploitable: nothing in the module uses
  `briefing_id` in a filesystem path (checked by running it — one file was
  created). It is data in a JSON string.
- Concurrent appends rely on a single small `write()` under `O_APPEND`. Notes
  are capped at 280 chars so a row stays far under the atomic-write size. One
  Captain on one phone is not a concurrent-writer scenario; this is noted, not
  engineered around.
- Nothing prompts the Captain to score. The instrument records what he sends;
  if he sends nothing, the summary reports the silence. That is deliberate —
  a nagger is the next thing that would make him stop reading.
- `n` can exceed `briefings_seen` inside a window if he scores a briefing
  older than the window. Honest, and rare enough not to complicate the shape.

## Verdict

**approve.** Small, falsifiable, and it answers exactly the question asked —
one number per briefing, stored where a deploy cannot eat it, summarised on
demand, with silence counted rather than dropped. It builds no pipeline, no
dashboard and no north-star computation, and a test fails the suite if it ever
gets a schedule.
