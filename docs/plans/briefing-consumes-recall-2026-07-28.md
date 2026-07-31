# The first briefing reads what recall already holds

**Date:** 2026-07-28
**Trigger:** a measured hatch, not a review. An agent ran the genuine path —
personal answers → `generate-instance.py --adopt` → the hatch's own
`do_set_preset` → `load-preset.sh` → `first-briefing.sh --local` — got three
cards and a research-brief IOU, and **scored the result 1 of 3: "read it, no
value"** on the shipped instrument (`cabinet/scripts/lib/briefing_score.py`).

That honest 1 is why this unit exists. It is worth more than a defensible 3.

---

## 1. What was actually wrong

Recall was **working**. On that same box `available()` returned True, and three
probes — *tax_quote latency*, *rollback window*, *error budget* — returned 3, 2
and 2 hits, each with a `file#heading` ref and a `content_ts` derived from
frontmatter or filename, never mtime. The notes folder held a live incident: a
latency regression traceable to a billing-migration cutover, with a rollback
window closing the same week the error budget ran out. **A join nobody at that
altitude had made, and the briefing referenced none of it.**

Two defects, both on the `generate-instance.py` / briefing-composition path.

### 1.1 The briefing consumed ZERO recall

Nothing in the genesis chain ever called `framework.sources.get_source()`.
`propose_outcome_cards` composed from the answers file and — since the ordering
inversion — the derived estate. So the best the org could say about a lane was
that the operator had declared it: *"First verifiable improvement shipped in the
Checkout Service lane"*. True of every deployment ever hatched, and checkable
against nothing.

### 1.2 `local_root` was hardcoded, and the fallback was a confident false positive

`render_sources_personal(ORG_VAULT_DEFAULT)` — the answers file had **no way**
to declare the operator's notes folder. And the value it was pinned to,
`vault`, is the **cabinet's own shipped documentation**: `vault/README.md` and
`vault/architecture.md` are tracked files in this repo.

Reproduced on master before the fix, on a fresh personal hatch:

```
MASTER resolve_root -> <root>/vault
MASTER available    -> True
MASTER search hits  -> ['README.md#Where a document lives (the placement one-pager)',
                        'README.md#What belongs here',
                        "README.md#vault — the cabinet's knowledge vault",
                        'README.md#Conventions',
                        'architecture.md#Architecture — <product>']
```

A personal box reported live recall while answering out of the framework's own
docs. **Nothing downstream could tell that apart from working recall**, which
makes it worse than the honest empty it replaced: an operator can act on an
honest unavailable and cannot even see a plausible wrong folder.

### 1.3 The altitude failure, one layer down

A subject card's `what` ended *"task → change → verified deploy/close"* at
**every** rung — precisely the authority an IC does not hold. The PROOF line had
already been corrected for altitude; the WHAT line had not, so the card was
still gated on a permission that belongs to the operator's employer.

## 2. What is true now

| Change | Where |
|---|---|
| `probe_recall()` asks the BOUND seam about every declared subject; hits reach cards as DATA | `framework/onboarding/genesis.py` |
| Cards quote the operator's own sentence, cite each file with its derived date, and name the wording ≥2 of their files share | same |
| `genesis-recall` provenance card states live / unbound / not-consulted, with the fix | same |
| `sources.notes_root` in the answers declares the folder; **no default** | `cabinet/scripts/generate-instance.py` |
| `resolve_root()` returns `None` when undeclared; `binding_status()` separates unset / missing / empty | `framework/sources/local.py` |
| Altitude reaches the WHAT line, not only the proof | `framework/onboarding/genesis.py` |

**`propose_outcome_cards` stays PURE.** The probe runs in
`run_genesis_proposal`, beside the estate load, and the result is passed in
exactly the way `estate` already is. No LLM, no network, no writes anywhere in
the derivation: the join is term overlap across DISTINCT files, the order is
time (not retrieval score), and the quotes are verbatim.

**When recall holds nothing the cards are byte-identical to the pre-recall
derivation**, and a card that cited nothing carries no `recall_refs` key at all.
An unearned citation is the defect this removes, not a smaller version of it.

`CABINET_GENESIS_RECALL=0` skips the probe. The probe is root-guarded: the
bound seam answers for `CABINET_ROOT` and is not consulted on behalf of a
different tree.

## 3. Proven by hatching, and scored honestly

A real personal hatch against a three-note fixture (an incident, a decision, an
SLO note) produced this card:

> **📜 Proposed outcome: Checkout Service: 3 of your own notes (2026-07-01 … 2026-07-21), never read together**
> **WHAT:** Read these notes of yours side by side (2026-07-01 … 2026-07-21), newest first: `incidents/2026-07-21-tax-quote-latency.md#What we know` (dated 2026-07-21); `decisions/2026-07-14-billing-migration.md#Owner` (dated 2026-07-14); `slo/error-budget.md#Checkout error budget — July` (dated 2026-07-01). Shared wording: regression, migration, rollback, billing. Then write the one-page finding and take it to whoever owns the decision.
> **WHY:** You staked Checkout Service as a lane at genesis (repos: acme/checkout). I did not ask you for this, I read it: "The billing migration moved tax_quote onto the new pricing service. Rollback is still possible." — `incidents/2026-07-21-tax-quote-latency.md#What we know` (dated 2026-07-21). …

And the undeclared-folder hatch produced, instead of a wrong answer:

> **🧠 Recall: bound to NOTHING** — no folder has been granted, so it answers
> nothing rather than guessing. Declare `sources.notes_root` in
> `instance/config/cabinet-init.answers.yml` and re-run
> `cabinet/scripts/generate-instance.py`, or export `CABINET_LOCAL_SOURCE_ROOT`.

### SCORE: 2 of 3 — "told me something I didn't know"

Not 3, and the reason matters. Rung 3 is *"changed what I did next"*, which is
a thing the **operator** does and reports. I am not the operator and cannot
observe it, so claiming 3 would be exactly the unfounded claim that produced
the 1 in the first place. What is defensibly true at 2: the individual facts on
that card are the operator's own — they wrote them — but the **join** (three
files, spanning three weeks, sharing four terms, never read together) is a fact
about their own corpus they did not have, and every part of it opens.

### What is still weak, stated rather than papered over

- **Quote selection is by date, not salience.** The newest dated hit wins. On
  the fixture that picked `#What we know` over the better `#Impact` sentence in
  the same file. Both are real; the pick is not ranked by importance, because
  nothing here judges importance.
- **The join is term overlap, not semantics.** It reports that several of the
  operator's notes use the same words — a fact they can verify by opening them.
  It never claims causality; the operator makes that call.
- **Only DECLARED subjects are probed.** An operator who declared nothing gets
  no probes, by design (a probe invented here is the guessing the
  read-don't-ask direction removes) — but it means value scales with what they
  declared, and the residual card is what answers the zero-declaration case.
- **An empty answer is not a stale one, and the first version said it was.**
  A real clean-room hatch — not this unit's suite — caught the provenance card
  telling an org box whose backend held nothing that "the proposals on file
  were written before this run", i.e. blaming ordering for emptiness. Fixed,
  with the arm that would have caught it. The lesson is the one this repo keeps
  paying: the sensor tested something other than the control.
- **Genesis-time only.** `write_proposals` is write-once, so a later
  `formation.sh` plus re-probe needs the staging file removed or
  `merge_proposals`. The `genesis-recall` card says so when it happens.

### Two corrections found by a hostile pass on the landed unit (2026-07-28)

Both were this unit's own new code putting an unearned claim on an
operator-facing surface — the defect it exists to remove — and both were
reproduced before being fixed.

1. **"Shared wording" could name a term appearing in none of the files the card
   prints.** `_join_terms` was fed all `_MAX_RECALL_HITS` (8) hits while a card
   cites at most `_MAX_RECALL_FILES` (3), so on any corpus answering from four
   or more files the caption drew from files the operator never saw. Measured
   through the real `LocalNotesSource` and the real `first-briefing.sh --local`:
   three cited notes about widget alignment, invoice numbering and onboarding
   copy, captioned *"Shared wording: kubernetes"* — a word living only in two
   older notes the card never showed. The operator finds that out by doing
   exactly what the card told them to do. The join is now computed over the
   CITED set only, so every term is checkable in the files named beside it.
   `presets/personal/README.md`'s promise — *"nothing is asserted that a
   citation does not already show"* — was false until this; it is true now.
2. **A recall-enriched ESTATE card stopped counting as estate provenance.**
   `_estate_subject_cards` relabelled its card `derived_from: recall` whenever
   recall answered, and the estate provenance item counts `derived_from ==
   "estate"` — so the count fell to zero and the briefing told the operator
   *"No card above derives from it: the proposals on file were written before
   this estate existed. Re-run genesis"* about a card composed from that estate
   in that same run. An ordering story told about a card with no ordering
   problem: the empty-vs-stale confusion above, one surface over. The field
   stays `estate`; recall provenance for such a card rides `recall_refs`, which
   is what the recall item already counts, so both sentences are true at once.

Both arms fail against the pre-fix bytes and pass after
(`framework/onboarding/tests/test_genesis.py`), plus a third arm that keeps a
genuinely shared term reported, so the first fix cannot be satisfied by
deleting the clause.

**The review pass on this fix found the second arm half-vacuous, and it is
corrected here.** It wrote the two-entity `ESTATE_DOC`, whose second entity
(`labs`) recall never answers for — so that card kept `derived_from: estate`
against the PRE-FIX bytes too, the estate count never reached zero, and the arm
went green on the very branch it names. Measured: with the label assertions
removed and `"recall" if subject else "estate"` restored, the body passed. It
was pinning the LABEL while its docstring claimed the BRIEFING SENTENCE — a
sensor wired to something other than the control, the dominant defect class of
this fortnight, inside the fix for that same class. The arm now writes a
single-entity estate, which is the shape that actually drives the count to
zero, and the "Re-run genesis" assertion fires against the pre-fix bytes.

### Residual overclaims on this surface — NOT introduced here, still true

Found by the same pass, in code that predates this fix; recorded rather than
silently carried. Each is the same class this unit exists to remove:

- **`never read together`** (`_recall_card_name`) is the headline of every join
  card — *"Acme Storefront: 3 of your own notes (2026-07-19 … 2026-07-21),
  never read together"* — and nothing the cabinet can read shows it. It is an
  assertion about the operator's own reading history, offered as a finding.
- **`Shared wording:`** is printed beside up to three citations while
  `_MIN_JOIN_FILES` is 2, so a term can be absent from one of the files named
  beside it. Measured post-fix: three cites captioned *"Shared wording:
  reconciliation, ledger, late"* where `c.md` carries none of the three. Far
  weaker than the pre-fix version (a term in ZERO cited files) but the same
  shape — the operator finds out by opening the files.
- **The headline span covers only the DATED cites.** Three cited files with one
  `content_ts` renders *"3 of your own notes (2026-07-21)"*; the other two say
  `(undated)` in the citation line, but the headline dates all three.
  STILL OPEN after window clocks landed (2026-07-31), and the distinction is
  the point: `(undated)` here means the file has no derivable `content_ts` —
  no frontmatter date, no dated filename — i.e. nobody can say WHEN IT WAS
  WRITTEN. Window clocks answer a different question, WHAT DATES IT STATES,
  and a subject card now prints those beside its citations
  (`DATES IN THOSE FILES:`). The two must not be merged: a note written in June
  that mentions December is not a December note, and letting the stated date
  date the document would poison the retrodiction fence
  (`framework/fidelity/tests/test_window_clocks_fence.py` is the arm that
  keeps them apart). The two renderings now NAME which clock they mean —
  "(the notes carry no date of their own)" in the headline, "(no date on the
  note)" on a citation — because "(undated)" was read as "this file holds no
  dates" beside a file stating a filing cutoff seven days out.
- **The clock join is a RENDER-TIME join, never a persisted field.** The
  proposal rows are derived before any window is ratified (the real order is
  edit-answers → generator → journey → briefing) and correctly never
  re-derive afterwards, so anything about the window baked into a row is
  baked empty. `genesis_intake_items` reads `estate.load_window_clocks()` at
  render time and joins on each row's `recall_refs`; a superseded window
  removes the artifact and the lines with it. Residual: an estate-derived
  card that recall did not answer for carries no refs, so it gets no clock
  lines even though the manifest knows its evidence paths.
