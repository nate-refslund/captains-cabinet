# Checkpoint review — feat/channel-flatline-alarm cp1

**Unit:** channel-flatline alarm (Captain-Seat dry-run finding 2).
**Source:** `/Users/nate/cabinet-meta/designs/captain-perspective-retro-2026-07-26.md`
§4 — *"card series 146 sent / 2 approved then seven consecutive zero days with
no alarm"* (one of the three dry-run findings verified true against reality in
that session), carried forward as a SEED generalization under the 2026-07-26
scope ruling.
**Authority:** Captain GO 2026-07-27 on the queued Captain-Seat follow-ups
(captain-decisions officer-note 2026-07-26T23:05:00Z); per 2026-07-07
full-autonomy grant + 2026-07-21 ownership-on-GO.
**Base:** clean clone of `origin`, tip `19d1c2e17cb47cb04405738f4cf386b91846b655`
(contains `856ef494`, the previous unit's master).
**Diff:** 11 files, +1411 / -8.

---

## 1. What was built, and what was deliberately NOT built

A captain-facing channel that goes silent must say so — **once**.

| piece | file | why there |
|---|---|---|
| detector (pure) | `framework/frontdoor/card_flatline.py` (new) | series + current gates → one verdict; no store, no clock beyond `now`, no import of what it watches |
| Captain line — text path | `framework/frontdoor/tell_digest.py` | the LOOP section already parsed `proactive_cards_7d` and dropped it; the line now leads that section |
| Captain line — card path | `framework/frontdoor/run_briefing.py` | card mode ARCHIVES the composed body, so the headline is the only surface the Captain sees; the digest line alone would have been unconsumed machinery |
| fleet probe | `cabinet/scripts/card-flatline-probe.py` (new) → `cabinet/scripts/cabinet-doctor.sh` check 16 | standing signal for as long as the channel is dark |
| read fence | `conftest.py` (`CABINET_FALSIFIER_SERIES`) | no pytest run may judge — or be judged by — a live deployment's emission history |
| runbook | `docs/runbooks/card-flatline-alarm.md` (new) | operator view; allowlist row for the gitignored series path |
| budget | `cabinet/config/cognitive-architecture-contract.yml` | two allowance rows at the EXACT measured totals (zero headroom) |

NOT built, each on purpose: **no new durable store** (the once-per-episode
property is a function of the series, not a flag that can rot or be lost on a
deploy) · **no new services row** (the probe rides the doctor; the detector
rides the briefing) · **no new send** (the availability dial is respected by
construction — the line rides correspondence already going out) · **no
watchdog `Expectation` row** (that would have pulled `instance/config/watchdog.yml`
and its `.example` into scope, both pinned by the evidence ratchets, for a
signal the doctor already carries).

## 2. The three judgment calls worth attacking

**(a) Delivery through TWO seams, not one.** The scout map recommended the
digest LOOP section alone. That is wrong on a default deployment: `briefing_card`
is ON by default (`run_briefing.py` ~line 122), and in card mode the composed
body — LOOP section included — is archived to `instance/memory/briefings/`
rather than sent. A line that lands only in an archive nobody reads is the
named "machinery outruns value" failure. Both seams now render from ONE
function (`card_flatline.render_line`), and an arm asserts the wording appears
in neither consumer's source, so the two surfaces cannot drift into two
accounts of the same silence.

**(b) `allow_sends()` is deliberately NOT a gate.** It was in the first draft
and was removed on inspection: it reports whether *this* process may send, and
this process is the doctor or the briefing — not the action lane that mints the
cards. It measures the observer instead of the observed, which is the exact
sensor failure this unit exists to correct, and it would have parked the alarm
permanently green on every box where the probe runs outside the runtime. The
comment stating this sits at the removal site so it does not get "fixed" back
in.

**(c) Once-per-episode is a crossing test, not a stored flag.** `announce` is
true only where the silence crosses 48h (`prev_hours < bar <= hours`),
measured in HOURS off the series dates so a box that slept through a day still
crosses exactly once. Recovery ends the run, so the next silence is a new
episode — that IS the cooldown, and there is nothing to fence, migrate or lose.
`ANNOUNCE_FRESH_HOURS` (26h from the series date) bounds delivery so a producer
that dies right after a crossing row cannot pin the question on his screen
forever.

## 3. Attack list — what could make this alarm worse than nothing

| attack | verdict |
|---|---|
| fires on a fresh hatch (zero cards from birth) | REFUSED — `never-active`; requires a live row BEFORE the run. Doctor prints `ok`, so a fresh hatch stays GREEN |
| fires when the whole fleet is down | REFUSED — `quiet` when no acts, no new stamped rows and no labels across the run. Misattribution would point the Captain at the wrong organ |
| asks whether his own declared absence was deliberate | REFUSED — the availability dial `away` and a `disabled: true` producer row both gate it, and the inline `# ABSENCE-DISABLE …` comment is stripped BEFORE matching (the parser bug that once made parked services page every sweep) |
| reads a missing count as zero | REFUSED — `null` is `unmeasured`; an unmeasured row BREAKS the silent run rather than extending it |
| reads a dead series as a dead channel | REFUSED — `stale` past 3 days; no verdict at all |
| repeats every briefing until answered | REFUSED — crossing row only, plus the 26h delivery bound |
| a broken detector costs the briefing | REFUSED — three independent fail-open wrappers; an arm makes `evaluate` and `render_line` raise and asserts the headline, the digest section and the gather leg all survive, with the reason landing in `errors` |
| the alarm becomes an officer-visible score | N/A — the verdict is a state name and a date; no scalar reaches any surface |

**Known bound, stated rather than hidden:** the gates are read as of NOW, not
as of each series row, so a deliberate window that ENDS mid-silence suppresses
the one-time Captain question for that episode. The doctor probe reports BREACH
for the whole silence, which is why the fleet half is standing rather than
once-per-episode. Recorded in the module docstring and the runbook.

## 4. Sensor evidence (class-11 discipline)

Two-tier red demonstration, `__pycache__` purged between runs, in a separate
clone at the same base:

* **Tier A — pristine pre-change:** both new test modules fail at collection
  (`ImportError: cannot import name 'card_flatline'`). Nothing existed.
* **Tier B — detector present, wiring still pre-change** (isolates each wiring
  sensor against the actual defect): **18 failed, 23 passed**. The 18 are the
  digest-render arm, the card-headline arm, the `flatline_notice` arms, the
  conftest-fence arm, the gather-key arm, the fail-open arm, the
  one-wording arm, and all 11 doctor-case arms — each red by ASSERTION, not by
  import error.
* **Mutation sweep — 9 mutants, all killed** (unmutated control 41/41 green):
  bar→0h (9 arms red) · never-active guard off (1) · quiet guard off (1) ·
  deliberate guard off (1) · crossing always true (3) · `None` counted as zero
  (1) · freshness bound off (1) · inline comment not stripped (1) ·
  staleness off (1).
* One defect the arms caught in this session and fixed: the probe suite's
  fixtures were hardcoded calendar dates, so the probe (which runs against the
  real clock in a subprocess) read them as STALE — a time bomb that would have
  read healthy this week and red next. Fixtures are now seeded relative to
  today. A second: a doctor text-scan matched its own explanatory comment
  rather than the `case` block; it now splits on `case "$CFL_PROBE" in`.

## 5. Gates run in this session (local, before push)

`framework/frontdoor` 1184 passed / 23 skipped · `cabinet/scripts/tests` 4768
passed / 28 skipped · `cabinet/scripts/lib/tests` 402 passed · `framework/`
6748 passed (1 pre-existing failure, `framework/fidelity/tests/test_retro_shim.py`,
present identically on unmodified master and environment-dependent — it loads
the Captain's local retrodiction lib, absent in CI) · docs-track-code sweep
GREEN 64/0 · layer separation new=0 · state-persistence preflight 0 UNACCOUNTED ·
ledger status-parity GREEN · whole-tree ratchets (launcher-hardcode,
bash-3.2 empty-array) 35 passed · `bash -n` + `shellcheck -S error` on the
doctor · cognitive-architecture census PASS at 244/244 modules and
69051/69051 lines · `verify-cognitive-architecture.sh` PASS.

## 6. Budget growth — argued, not waved through

The census correctly blocked this change (+1 module, +390 non-comment
framework lines). The module docstring was cut by ~half first (the enumerated
tables live in the runbook, where an operator will actually look), then two
`temporary_allowances` rows were added at the EXACT measured totals with zero
headroom, following the captain-dates precedent (`b5e6cda3`) rather than
raising a `maximum` — so the ratchet still bites at the new level and the next
silent growth still REDs. The reason field states why the detector is a module
rather than a helper: three consumers need the verdict, one of which (the
cabinet doctor probe) must reach it without importing the digest's live-ledger
surface.
