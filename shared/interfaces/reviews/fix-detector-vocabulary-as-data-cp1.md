# fix/detector-vocabulary-as-data — cp1 self-review

Reviewed-Scope-Digest: e08beb123b0268c099f1cd44ec6ad7b1b524bcab6bb57f3564a3d04bc55be0af

Scope: 4 staged paths. `framework/onboarding/journey.py`,
`framework/onboarding/tests/test_detector_vocabulary.py`,
`cabinet/config/cognitive-architecture-contract.yml`,
`instance/config/detector-vocabulary.yml.example`.

## What this changes, in one line

Every detector LABEL was an inline English literal in framework code; they are
now one table, one entry per semantic role, that a deployment may extend and
no detector body names a language in.

## The measured defect this is paying off

A fresh First Window over a seventeen-file Japanese estate returned
`orientation_map` — *"no contradiction, broken documented command, or explicit
urgent marker"* — over a folder holding all three. The finding path had just
been taught to read any script (the segmentation seam that landed earlier the
same day), so the tokens were reachable; what stopped every detector one step
later was its own vocabulary:

| detector | the literals it carried |
|---|---|
| `_risk_markers` | `urgent\|blocked\|overdue\|needs action\|action required`, `status\|state\|priority`, `todo\|fixme\|xxx` |
| `_contradictions` | `launch (date)\|go-live (date)\|deadline\|delivery date` |
| `_untracked_commitment` | `todo\|…\|follow-up`, and thirteen closed statuses |
| `_tracker_rows` | `title\|summary\|…`, `status\|state\|…`, `id\|key\|…` |

至急, 期限, 完了 and a CSV headed 件名/状態 could fire none of them. The
strongest negative this module prints was reached by being unreadable rather
than by being clean, which is the same failure the coverage disclosure and the
detector roster were each built to refuse one layer up.

## The four class-11 questions, asked of this diff

**1. Does each arm FAIL against pre-change code — both directions, cache
purged?** Run, not reasoned about. A detached worktree at `origin/master`
(4fd9b2b4), the new suite copied in, every `__pycache__` removed,
`PYTHONDONTWRITEBYTECODE=1`:

```
pre-change:   30 failed, 23 passed
post-change:  53 passed
```

24 of the 30 fail on an ASSERTION, because the defect arms go through entry
points that predate this branch (`_risk_markers`, `_contradictions`,
`_tracker_rows`, `_untracked_commitment`, `_scan_source`, `_first_dividend`)
and steer the deployment root with `CABINET_ROOT`, an environment variable
`journey.cabinet_root()` already read — so even the extension-point arms
execute against the old code and fail on what they assert. The remaining 6
(five test functions, one parametrised twice) raise `AttributeError`: they
grade names that did not exist, and the file's docstring names all five rather
than leaving a reader to notice. The 23 that pass pre-change are every English
pin, which is what a pin is for; each writes the RETIRED pattern out inline as
its oracle, so it cannot re-derive its expectation from the code it grades.

**2. What happens at the degenerate end — zero, empty, absent, null?**

* **An empty role.** The dangerous one, and the reason `_label_alternation`
  exists as a function rather than a `"|".join`. `"|".join([])` is `""`, and
  `^(?:)\s*(?::|…|$)` matches essentially every line — a role that lost its
  data would turn a silent detector into one that fires on every line of every
  file. Empty yields `(?!)`, pinned by `test_an_empty_vocabulary_role_matches_
  nothing` over all nine roles at once.
* **A single-character label.** 済 is a whole closed status and a fragment of
  未済 ("not done"). The status comparison is equality, never containment, and
  the arm asserts both directions of that one pair.
* **A blank label.** `""`, `"   "` and an ideographic space are dropped before
  the alternation, because `urgent|` matches everything ever written.
* **A line that is only the label.** No separator, no text after it. The
  retired patterns accepted this with `$` and the arm pins that the table did
  not quietly start requiring a colon.
* **Absent / malformed instance file.** Six shapes (not YAML, a list, a bare
  string, a mapping to a string, a list of ints, an empty file) each land on
  exactly the defaults, asserted in BOTH languages so "fell back" cannot be
  confused with "lost the extension AND the Japanese".
* **A header-only export in Japanese.** Right shape, no rows: still not a
  tracker. A file is not a connection, in any script.

**3. What does the test environment guarantee that production does not?** The
one real answer here was the deployment root. Without pinning it, every
default-vocabulary arm would read whatever `instance/config/detector-vocabulary.yml`
the checkout happened to carry, and an operator's own additions could make a
framework-default arm pass — the failure in its most literal form. The
`framework_only` fixture points `CABINET_ROOT` at an empty tmp dir, so the
arms grade the shipped table and nothing else. Nothing else in the file
depends on the environment: no network, no clock, no subprocess, and `yaml` is
imported inside the loader (already a hard dependency of this package's
`research` module and of CI's install list).

**4. Is the sensor wired to the LIVE artifact?** The four detectors under test
are the four `_first_dividend` composes — asserted by the end-to-end arm, which
scans a real folder on disk with `_scan_source` and reads the finding out of
the dividend rather than out of a detector called directly. The census note
and the ceiling it raises are the live ones (`git blame` on
`framework_production_noncomment_lines`), re-measured over this tree rather
than summed.

## The agnosticism claim, and how it is checked

The claim is that adding a language is adding rows, never a code change. A
source grep cannot check that — a docstring may legitimately name a label, and
this diff's do. What checks it is
`test_emptying_one_role_silences_exactly_what_that_role_feeds`: empty a role,
and the detector it feeds must go silent while its sibling keeps firing. If any
label were still inlined anywhere in a detector body, emptying its role would
not silence it. A cheaper companion arm walks each detector's AST and refuses a
label that only a non-first language tag carries as a string constant — minus
the labels the first tag also carries, because `id` is both a Japanese export
header and a legitimate field name in the row a detector builds.

## Judgement calls, stated rather than buried

* **The table lives in `journey.py`, next to the detectors that read it.** It
  is detector semantics, not a text primitive: `salience` owns what a WORD is,
  and this owns what a MARKER means. A module holding nothing but nine tuples
  would need an expansion row whose `merge_refuted` anchor cannot honestly
  refute the four functions that are its only caller — the same reasoning the
  splitter's placement gate reached, applied to the opposite conclusion because
  the subject is different. Bijection class untouched at 248.
* **Framework defaults are CODE, the extension is a FILE.** Defaults cannot go
  missing, cannot fail to parse, and need no YAML on the path a fresh hatch
  takes; a defaults file that failed to load would silently empty every role,
  which is the degenerate end above with the worst possible trigger. The
  extension is `instance/config/detector-vocabulary.yml`, read fail-open — the
  `egress.yml` precedent, one directory over — with a documented `.example`
  twin that ships in the egg and is never materialised.
* **Extend, never replace, structurally.** The loader returns additions and
  the caller only unions them, so no file shape deletes a shipped label. A
  deployment able to drop `done` from the closed set would turn every finished
  tracker row back into an open commitment and hand the operator that noise as
  a judgement. The arm is written as the attempt, not as the invariant.
* **Declaration order survives; only the regex roles re-sort.** The three
  export column roles are preference-ordered — first recognised header wins —
  so a longest-first sort would have silently changed which column a
  multi-column export is read by. Caught by writing the pin (every ordered pair
  of every column role, 33 pairs) before trusting the refactor; it failed on
  `status` before `state`, which is exactly the class of change that ships
  unnoticed.
* **Grammar widening, bounded and declared.** NFKC (already applied by the
  shared fold) converts ：（）－＃＊ and ＴＯＤＯ to their ASCII twins for free.
  The CJK bracket pair 【】 does not fold, so opening marks join the scaffolding
  strip and closing marks join the separator class — the role `[` and `(`
  already play. Neither character can occur in an English corpus, so the Latin
  grammar is untouched by construction rather than by hope.
* **The contradiction VALUE stays an opaque string.** It is now folded on the
  same terms as everything else, so ２０２６-０８-１２ and 2026-08-12 are one date
  rather than a contradiction manufactured by the reader. What the dates MEAN
  is a calendar question this module has no business answering.

## What this does NOT fix, said plainly

* **Two languages, and only two.** English and Japanese are what could be
  verified word by word. A wrong label does not sit inert — it fires on a real
  line of somebody's material and spends their trust — so the table ships
  short and the extension point is the answer for everything else. A deployment
  in a third language still gets nothing until someone fills the file.
* **The card's own sentences are English.** A Japanese estate now produces a
  finding, cited in the operator's own words, wrapped in an English summary.
  That is a separate surface and a separate landing.
* **The dividend's plain-language negative still enumerates the English
  semantics** ("urgent, blocked, overdue, or needing action"). It describes
  what the detector MEANS, which stays true, but it reads as a label list and
  will want rewording when the card is localised.

## Gates

| gate | result |
|---|---|
| `pytest framework/onboarding/tests framework/tests -q` | 1990 passed, 2 skipped (caches purged) |
| new file alone | 53 passed |
| pre-change proof (worktree @ origin/master 4fd9b2b4) | 30 failed, 23 passed |
| `cognitive-architecture-census.py --check` | PASS; 248 <= 248 modules, ceiling 61724 -> 61891 (+167 measured) |
| `check-layer-separation.sh` | baseline=24 allowlist=19 new=0 |
| guarded-token grep over the diff | clean |

Verdict: PASS
