# Checkpoint review — feat/cog3-wave3, cp1 (tests-first corpus + U1 derivation core)

**Scope:** 18 commits off `origin/master` `83009ce1` — the 12-commit wave-2
test corpus + the 4-commit U1 implementation (schemas, model+states, view
surface, review-fix) + the integrator's corpus-adjudication and
allowance/appendix commits. Well over FW-019's 300-line threshold (corpus
~4k lines, U1 ~900) → this artifact. It also covers the corpus authors'
self-flagged >300-line commits and U1's `cb38d92d` (468 lines).

## Corpus (tests-first, contract §12.2 steps 2-3)

Three Opus authors in isolated clones (T3: fixture library + the 42-cell
exhaustive §5.2 state-function table; T1: SIM-1/5/6; T2: SIM-2/3/4 + the
verdict-vocabulary drift tripwire, green-today), each adversarially reviewed
by a fresh-context Fable agent running wrong-implementation simulations. All
three reviews returned FIX_FIRST — 10 genuine must-fixes (missing
human×machine mix cells, never-varied `expected_effect`, a vacuous roots-hash
fallback, a staleness cell a correct implementation could not pass, an
over-pin rejecting contract-legal conflict storage, unpinned prediction
scoring, helper-only instrument-target enforcement, and more) — all closed by
surgical fix agents with per-suite absence-signature proofs (100% of contract
cells fail only for the absent implementation; 0 collection errors).

Two contract ambiguities were adjudicated during the fix pass and are now
recorded in the contract's build-time appendix: **R-A** (the assumptions gate
binds P5 as well — no promotion above `hypothesized` on an assumptions-less
edge) and **R-B** (review-less consequence rows carry no direction reading —
execution-happened is not effect-evidence).

## U1 — the derivation core

Four registry-path-resolved Draft-2020-12 schemas (disjoint id namespaces,
instrument-never-a-causal-target, root_ref required, no numeric weights,
typed enums) + `framework/objectives/{__init__,model,states,query,ovi_view}.py`:
canonical bytes + recorder-dialect digests (verified byte-identical to the
cortex dialect), the ordered total transition function P1>…>P6 with R-A/R-B,
the machine-checked verified-join (limb i: forged subject/claim pairing =
structural BuildFailure; limb ii: honest join mismatch = non-verified, capped),
the Captain-vocabulary bijection (internal tokens only in data; schema rejects
persisted Captain words), the four-field recommendation record, and the
per-instrument OVI view (composite structurally absent).

Builder discipline held: the corpus was byte-untouched (blob-hash proof), the
two stale absent-today vacuity guards it could not satisfy were REPORTED not
edited (prime law) and retired by the integrator in a dedicated adjudication
commit. The Fable review returned FIX_FIRST with two probe-proven must-fixes
(the forged-pairing degradation and a hybrid vocabulary leak) + six schema
nits — all closed in `u1-fix` with probe confirmations, red set byte-identical
to the expected U2-scope remainder.

## Verification on the integrated tree (`python3.12`, PG17 on PATH)

- `test_cog3_*`: **259 passed / 41 failed** — every failure an ImportError on
  the not-yet-built `graph`/`counterfactual` modules (U2 scope), enumerated
  and classified; state-function 59/59, sim6 22/22, landed gates 139 green,
  transitive-closure gate now RUNS (un-skipped) and is clean.
- `test_cog2_*`: 280 passed / 3 skipped. `cog2-import-gate.py` rc=0.
- Census `--check` PASS at exact zero headroom: modules 219==219, lines
  63988==63988 (running-total allowance rows: +5 modules / +502 lines
  measured), compiler 1==1.
- Egg-export suite 53 passed (the in-egg census verifier runs green against
  the committed tree — an amend fixed a stale-staged yml the first commit
  carried).
- Branch CI note: this branch's `framework-tests` job will show the 41
  U2-scope corpus failures if that job collects `cabinet/scripts/tests`; the
  wave lands via PR CI green (the CI suite scope is `framework/` tests + the
  gate scripts — verified per-job on the PR run before merge).

Provenance: per the 2026-07-07 full-autonomy grant + the Captain 2026-07-20
cognitive-masterplan grant; contract `docs/plans/cognitive-core-phase-3-contract-2026-07-22.md`
(CAPTAIN-APPROVED) + its build-time adjudications appendix (this wave).
