# FW-019 cp1 — fix/hostile-input-red-team

Reviewed-Scope-Digest: a5979179e7c45caf86b1c7d33a51a89459370125eb3fa50cbe4bda1cfc99677d

Second-context review of the staged diff (326 changed lines). Full attack
record, including every attack that correctly failed, is in
`docs/plans/hostile-input-red-team-2026-07-28.md`.

## What the diff claims, and whether the diff does it

| claim | check | verdict |
|---|---|---|
| a source file can no longer type its own provenance header | `_FENCE_RE.search(neutralize_fence_shapes(forged))` is `None`; the end-to-end vault-walk repro now taints `2-Meetings/…` instead of the forged `9-Codebases/…` | holds |
| all producers neutralize | `git grep 'ref=' -- '*.py'` finds exactly three fence f-strings outside tests; all three call the helper | holds |
| the forgery ATTEMPT is attributed, not just silenced | `fence-forgery` matches the raw AND defanged shapes, so `_tainted_refs` taints the real enclosing ref | holds |
| the D13 floor is no longer escapable by re-spelling | five spellings (`./`, leading space, `vault/`, `see …`, `#anchor`) all read `inbound`; pre-fix four of them read `internal` | holds |
| the screen reads Danish | nine non-English probes blocked that scored zero hits on master; three ordinary Danish work sentences pinned NOT to fire | holds |

## Where I attacked the fix itself

* **Over-strip.** The neutralizer is a zero-width `sub` at line start requiring
  BOTH a dash run and `ref=` on that line. Pinned not to touch: ordinary prose,
  a markdown horizontal rule, `ref=` with no dash run, a dash run with no
  `ref=`, and an inline (non-line-start) shape. An over-strip here would
  corrupt every excerpt the proposer reads — a worse failure than the one
  being fixed — so the degenerate ends are arms, not comments.
* **Idempotency.** The rewritten line no longer starts with the dash run, so a
  second pass is a no-op; pinned.
* **Ordering.** `_fence_block` neutralizes AFTER the character cap, so what is
  screened is exactly what is emitted — a cap can itself leave a half-header
  behind, and that half-header is pinned as neutralized.
* **The metadata twin.** The body fix alone leaves the header's own `ref` field
  forgeable, because a POSIX filename may contain a newline. Verified pre-fix
  that such a name made `_FENCE_RE` parse ONLY the forged ref (the real one
  vanished from the taint map entirely) and closed it at both header producers.
  A partial fix that relabels the rest as covered is a green hole.
* **Fence widening.** `_INBOUND_REF_RE` can only ever ADD `inbound` verdicts
  relative to `startswith`; over-matching costs a propose, which is D13's own
  stated fail-safe direction. It cannot narrow the floor.
* **The screen's own false positives.** Three ordinary Danish sentences,
  including one containing `ignorerer`, are pinned clean; the two pre-existing
  negative arms (`Bakery scrum: …`, `the approval workflow is documented`)
  still pass unchanged.

## Vacuity — cache purged, four mutants, each RED for its own reason

| mutant | red arm |
|---|---|
| `neutralize_fence_shapes` returns `body` unchanged | `TestForgedFence::test_proposer_…` |
| the four `*-nordic` entries deleted | `TestNonEnglishInjection`, BOTH layers |
| `_card_provenance` back to `str.startswith` | `TestForgedFence::test_proposer_…` |
| the `fence-forgery` entry deleted | `TestForgedFence::test_proposer_…` |

Restored: green. The pre-change bytes cannot run the arms at all (the helper
does not exist there), which is why the proof is per-mutant rather than a
whole-file revert — an ImportError proves nothing about the defect.

## Test-helper change, called out deliberately

`_propose_from_tainted` (shared by ten pre-existing attack classes) now builds
its bundle through the REAL producer `run_action_lane._fence_block` instead of
an f-string. This is the fixture-agreeing-with-its-own-defect class: a
hand-rolled bundle skips the neutralizer and therefore tests a shape production
can no longer emit. All ten pre-existing classes still pass through the real
producer.

## Budget

`framework_production_noncomment_lines` +31, measured with
`cognitive-architecture-census.py` against master `49ed144e` (73016, itself
exactly at its pinned maximum) → 73047, paid by a `temporary_allowances` row
with a named owner, sunset and deletion gate. ZERO new modules; no bijection
class moves. Docstrings counted as written, not reformatted into `#` comments.
The contract file is inside the frozen COG-4 §15 digest scope, so the
Reviewed-Scope-Digest re-bind of
`shared/interfaces/reviews/cognitive-core-phase-4-review.md` rides in the same
commit.

## Evidence

* master baseline re-measured this session: `framework/` 7407 passed, 1 failed
  (`test_retro_shim.py::test_reexports_constants`, the known local-only red — a
  third-party lib on this machine drifted its model id past a hardcoded pin;
  CI lacks the lib); `cabinet/scripts/tests` 5012 passed, 34 skipped, exit 0.
* this tree: `framework/` 7413 passed (+6), the SAME single known red;
  `cabinet/scripts/tests` 5012 passed, 34 skipped, exit 0 — identical.
* skip sets compared line-by-line between the two trees: **identical**. No
  sensor was disabled to buy a green.
* layer separation OK (baseline 24 / allowlist 19 / new 0), import gate OK,
  A13 parity OK (353 rows), census PASS at zero headroom.

## Not closed here, and why (each with a reproduction in the plan doc)

* R1 the regex screen remains evadable by unicode/paraphrase — documented
  design; the provenance floor is the control, which is why F1/F2 mattered.
* R2 a cited ref absent from the bundle is still judged as if real — a new
  control over the whole evidence plane; needs its own gate.
* R3 attacker prose can render a fake card above the real payload; the `·pid·`
  bind is NOT hijackable, so it misleads rather than executes.
* R4 `9-Codebases/` is attacker-writable via commit messages and sits outside
  the D13 floor — a one-line widening, but a policy call about autonomy scope,
  so it goes to the Captain.
