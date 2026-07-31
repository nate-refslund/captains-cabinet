# feat/window-clocks — checkpoint 1 (FW-019 landing self-review)

Branch: `feat/window-clocks`. Base: `origin/master` `3a61bb0f`.
Reviewer: the landing agent, adversarially, against its own diff. Nothing here
is trusted un-run; every number below was produced by a command in this
session on this branch.

## What landed

Dates written inside a ratified First Window are extracted as DATA and rendered.
The briefing previously said "(undated)" beside files that carried a filing
cutoff seven days out, in a folder the window had already read.

- `framework/onboarding/salience.py` — the extraction. Marker and era-calendar
  TABLES (one entry per semantic role, language tags as organisation only, no
  function naming a tag), a length-preserving digit/separator normaliser, an
  ordered grammar alternation, the anchor-else-refuse year rule, the spine
  measurement, and the row builder.
- `framework/onboarding/journey.py` — derivation invoked from the window pass,
  a manifest-hash-bound artifact beside the first dividend, its lifecycle, and
  a bounded forward-window note on the dividend card.
- `framework/onboarding/estate.py` + `genesis.py` — the bound loader and the
  clock lines a subject card carries beside the citations it already prints.

## The property that is structural rather than promised

A clock row carries exactly seven keys and there is no field for what a date
RELATES to. Two suites assert the key set, and one asserts the forbidden names
explicitly, so a future field called `blocks` or `collides_with` fails before
it reaches an operator. Relating two dated statements is a judgment; the
measured deterministic ceiling for it on a real estate was four true joins
inside fifty-two same-shaped candidates, and a schema that cannot express a
relation cannot quietly grow one that is wrong most of the time.

## Class-11 — the four questions, answered with commands

**1. Does the arm fail against pre-change bytes?** Measured, not assumed. A
second clone at `3a61bb0f`, caches purged, `PYTHONDONTWRITEBYTECODE=1`, with
ONLY the two new suites and the new fixture copied in:
**57 failed, 3 passed**. The three that pass are named and are green by
design, which is the honest version of this claim:

- `test_format_matrix_is_wide_enough_to_be_a_matrix` — a meta-assertion over
  the suite's own constant; it exists so a later trim cannot make the
  parametrised arms pass by covering less.
- `test_content_ts_still_reads_the_document_clock` and
  `test_the_hit_is_fenced_by_when_it_was_written_not_by_what_it_mentions` —
  both assert that the retrodiction fence did NOT move. They must be green on
  both sides; a red on either would mean the landing changed the fence, which
  is the one thing it promised not to do.

**2. What happens at the degenerate end?** Enumerated and counted: no files,
all-blank lines, no dates, one date, one date repeated, a window of nothing
but calendar-shaped files, and a calendar-shaped file that resolves NOTHING.
Two further degenerate ends are asserted because they are where a data-driven
grammar turns dangerous: an empty marker role must produce a never-match
rather than an empty alternation (which matches the empty string, i.e. fires
between every pair of characters in every file), and an unusable run clock
must leave every direction unknown rather than answering "ahead of you".

**3. What does the test environment guarantee that production does not?**
One thing, and it was designed around rather than accepted: the run clock. The
suite pins `now`; production passes a wall clock. So `now` is an ARGUMENT to
the extractor, nothing in the clock section reads the system clock, and an arm
asserts the same row reads past or future depending only on that argument.
Everything else is the real path — the estate fixture is a blind-authored
17-file business folder, and the end-to-end arms drive the real action and the
real briefing item builder.

**4. Is the sensor wired to the live artifact?** Yes, and deliberately not to a
twin. The end-to-end arms call `journey.act` for propose and ratify, then read
the persisted file and the rendered card body; the briefing arm calls the
composer's own item builder and asserts the clock line appears after the
citation line in the text an operator reads. Nothing asserts against a
re-implementation of the render.

## Two defects this review found, and fixed in the same commit

Both were found by attacking the code rather than by reading it, and both are
the same failure class this program keeps paying for — a number that does not
mean what it says.

1. **An unusable run clock answered "ahead of you" for everything.**
   `direction` was a string comparison against `now[:10]`. With an empty or
   malformed `now`, every ISO date sorts at-or-after `""`, so a caller who
   forgot the argument would have put an entire folder — including last
   year's dates — on the operator's forward list. Now an unparseable run clock
   yields `direction: None` on every row, and an arm covers empty, `None` and
   a non-date string.
2. **The unresolved-date count was taken over the survivors.** A
   calendar-shaped file is trimmed to a few forward rows, and the "N dates
   name a month and a day but no year" figure was computed after that trim.
   A rota written in bare month-days with no letterhead resolves to nothing at
   all, and would have reported nothing unresolved. The count is now taken
   over every row found; the arm builds exactly that rota and asserts 24.

## Residuals — named, not hidden

- **Recall is deliberately traded for precision.** Bare slashed pairs
  (`8/12`) are refused outright. Measured on the acceptance estate, that shape
  is a rota column, a booking-ledger key, a review date, a season opening, a
  room ratio and — after normalisation of a wide solidus — a pair of dinner
  seating times. Two spreadsheets and a handover log therefore contribute zero
  rows. This is the intended trade under a precision-first frame with no
  recall floor, and it is reversible only with evidence, not with a hunch.
- **English month names are absent** because that language's month set
  contains a modal and a verb. A month-name grammar there fires on prose.
- **The spine guard has no live consumer on the acceptance estate**, because
  that estate's two calendar-shaped files are written in the refused slashed
  form. It is exercised on purpose-built windows instead, and that gap is
  stated rather than papered over.
- **The card-level attachment matches by file NAME.** The window reaches a
  folder by the granted path and recall reaches it by its own binding, so the
  name is the only handle both carry. The risk is a same-named file in
  another folder; it is contained by printing the file and line beside every
  date, so a wrong attachment is visible rather than silent.
- **A landline that is exactly a valid date is indistinguishable from one.**
  Four-digit groups beginning with zero are refused, which removes every
  area code measured; an eight-digit number whose middle groups form a valid
  month and day would still resolve. No character distinguishes them.

## Batteries, run on this branch

- `python3.12 -m pytest framework/onboarding/tests framework/tests framework/fidelity/tests -q`
  — 1 failed, 2673 passed, 3 skipped. The single red is
  `framework/fidelity/tests/test_retro_shim.py::test_reexports_constants`,
  which is red on this machine BEFORE the branch (reproduced on a pristine
  clone at the base commit) and green in CI.
- `bash cabinet/scripts/null-hatch.sh` — PASS, over `git archive HEAD`.
- `bash cabinet/scripts/check-layer-separation.sh` — no new violations.
- `bash cabinet/scripts/docs-track-code-sweep.sh` — GREEN.
- `python3.12 cabinet/scripts/cognitive-architecture-census.py` — PASS at
  zero headroom after the visible raise recorded in the contract.
