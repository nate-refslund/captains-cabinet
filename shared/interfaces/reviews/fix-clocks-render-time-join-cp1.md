# fix/clocks-render-time-join — checkpoint 1 (FW-019 landing self-review)

Branch: `fix/clocks-render-time-join`. Base: `origin/master` `065f78b4`.
Reviewer: the landing agent, against its own previous landing (#336), which
shipped a correct extractor behind a join that could never fire.

## The defect, measured before it was fixed

On a fresh hatch from `065f78b4` over the archived estate, driving the REAL
operator order — answers on file, `run_genesis_proposal`, then journey
propose/ratify, then `genesis_intake_items`:

```
STEP1 derive:  status written, recall hits 21
  rows with recall_refs: ['口コミまとめ.md#気になった点',
                          '改修工事のお知らせ.md#工事期間中のご留意事項',
                          '消防点検通知.md#消防法第4条に基づく立入検査の実施について（通知）']
  rows with clocks     : []
STEP2 window:  rows_found 37, persisted rows 37
STEP3 briefing: '2026-08' occurrences 0 | 'DATES IN THOSE FILES' 0
   | 📜 Proposed outcome: 宿泊（本館・東館）: 3 of your own notes (undated)
```

A perfect artifact on disk, a card citing the very file whose clocks it holds,
and nothing in front of the operator.

**Two independent causes, and running the real order was the only thing that
would have found either.**

1. **The order.** Production runs edit-answers → generator → journey →
   briefing. The rows are derived BEFORE a window exists, and they correctly
   never re-derive afterwards — the answers digest has not moved (#324), and a
   row the operator may have edited is not genesis's to rewrite. So a line
   baked at derivation is always the empty one. My E2E arm ran
   window-then-derive: the one order production does not guarantee, and the
   only one under which the feature worked.
2. **The reference shape.** Recall does not cite a path. It cites
   `<file>.md#<heading>`. The join compared whole basenames, so it missed
   *every* reference recall actually produces — the join was empty even in the
   order I did test, and my own arm hid that by passing bare filenames no live
   seam emits. A fixture that models the shape you wish for is a fixture that
   tests nothing.

## The fix

Shape (a) from the coordinator's two: the join is now RENDER-time.
`genesis_intake_items` reads `estate.load_window_clocks(base)` and joins it
against each row's `recall_refs`. The derivation-time parameter, the persisted
`clocks` key and its passthrough are DELETED — not left as a second path.

**Staleness is impossible by construction rather than managed.** There is no
copy to go stale: the briefing shows what the window holds at the moment it is
read, and a superseded window deletes its artifact and takes the lines with it
in the same breath. That is why (a) beat (b) — joining window artifacts into
the derivation digest would have made a correct answer *reachable*, while this
makes a wrong one *unrepresentable*.

Plus the naming half the same measurement exposed. "(undated)" is a true
statement about when a NOTE WAS WRITTEN and was read as "this file holds no
dates", printed above three files one of which states a filing cutoff seven
days out. Both renderings now name their clock, and the dates those files
state print directly beneath.

And the forward window is now a briefing item of its own. It was on the
approval card only — an operator who approved a window last week and reads a
briefing today would never have seen it. One renderer (`journey.clocks_note`,
public and taking the payload) serves both surfaces, so a second copy of one
sentence cannot drift; an arm asserts the identical string appears in both.

## Class-11 — the four questions

**1. Red against pre-change bytes?** Six new arms, run against a pristine
clone at `065f78b4`: **5 failed, 1 passed**. The five reds are the order arm,
the heading-reference arm, the supersede arm, the headline-naming arm and the
one-renderer arm. The one green —
`test_a_card_whose_cited_files_state_no_date_renders_unchanged` — asserts the
"only when earned" degenerate behaviour of a pure function that was already
correct; it is a guard against regression, not a claim about this fix.

**2. Degenerate ends?** `_clock_lines` is asserted against no refs, an empty
payload, `None`, and a ref naming a file with no rows. The supersede arm is
the artifact-absent end of the render path, driven through the real action.

**3. What does the test environment guarantee that production does not?**
This is the question the previous landing got wrong, so it is the one this
one answers with the harness rather than with prose: the new arms hatch a
root, write real answers, bind a real `LocalNotesSource` over the fixture
estate, and call `run_genesis_proposal` / `journey.act` / `genesis_intake_items`
in production order. Nothing constructs a recall subject by hand any more
except the two arms that are explicitly unit tests of the reference-name
helper, and those use the shape measured on the live hatch.

**4. Wired to the live artifact?** Yes — `genesis_intake_items` is the
briefing's own item builder, and the arms read its rendered text.

## Residual, named

An estate-derived card that recall did not answer for carries no
`recall_refs`, so it gets no clock lines even though the manifest knows its
evidence paths. The row is what survives to render time and the row does not
carry them. Filed rather than smuggled: closing it means persisting evidence
paths on the row, which is a change to the proposal schema and belongs in its
own adjudication.

## Batteries, on this branch

- `python3.12 -m pytest framework/onboarding/tests framework/tests framework/fidelity/tests -q`
  — 1 failed, 2681 passed. The red is `test_retro_shim.py::test_reexports_constants`,
  reproduced red on a pristine clone at the base commit.
- `check-layer-separation.sh` — no new violations.
- `docs-track-code-sweep.sh` — GREEN.
- `cognitive-architecture-census.py` — PASS at zero headroom after the visible
  raise recorded in the contract (+27; zero new production modules).
- `null-hatch.sh` — PASS over `git archive HEAD`.
