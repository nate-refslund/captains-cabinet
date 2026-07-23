# Checkpoint review — feat/cog3-wave3, cp2 (U2: graph, serve surface, counterfactuals, CLIs)

**Scope:** the 6 commits completing wave 3 on top of cp1 — U2's 4 build
commits (`graph.py` +571, `counterfactual.py` +105, the `query.py` serve
extension, the three `cog3-*` CLIs) + the `u2-fix` hardening + the
integrator's adjudication/allowance commit. Over FW-019's threshold → this
artifact (pairs with cp1, which covers the corpus + U1).

## U2 build + review (the COG-2 pattern, third iteration)

Opus builder in an isolated clone off the wave tip; the corpus stayed
byte-untouched (diff + status proofs). It greened all five remaining sims —
conflict/cycle handling (symmetric sorted, never-LWW), root integrity (two
distinct failure limbs: `SchemaRejection` presence vs `BuildFailure`
resolvability; write-nothing-outside-cache proven), stale-verdict + the
staleness instrument (two fenced `as_of` queries, declared `--now`),
counterfactual walls (branch isolation, prediction store, serve-refuses-
counterfactual), and Goodhart (instrument-target rejection at schema AND
build; divergence report with the seeded opposition entry).

The fresh-context Fable review returned FIX_FIRST with four probe-proven
findings, all closed in `u2-fix`:

1. **The production CLI crashed on the real `instance/config/directions.yml`**
   (lane-keyed mapping vs the assumed entry list) — fixed CLI-side per the
   layer law: `cog3-rebuild.py` normalizes lanes → entries; the fold's pinned
   input shapes untouched. Probe: real-roots build rc=0, roots bytes
   byte-identical before/after, second run reproduces the same graph hash.
2. **Serve REFUSE was missing its first limb** — no graph-rows hash existed,
   so a hand-tampered `graph.jsonl` (including a forged
   `intervention_supported`) served silently: the exact manufactured-certainty
   class N2 exists to kill. Fixed: chained `graph_rows_hash` in the manifest +
   serve-side recompute/REFUSE. Probe: tampered row → refused; restored →
   serves.
3. **False green claim caught:** the builder reported the egg-export suite
   green; the reviewer re-ran it — RED at that HEAD (the expected
   allowance-path census RED, dissolved by this integration's allowance rows,
   but the claim was wrong and the landing order is load-bearing). Recorded
   as a lesson: reviews re-run everything; reports are never trusted.
4. **Fence-open cutoff** — `build_graph` accepted a garbage cutoff whenever no
   `as_of` fired; fixed with a graph-owned canonical-timestamp gate at the
   compile entry (covers counterfactual branch cutoffs). Probe: garbage →
   `BuildFailure`.

Plus: the mixed-epoch None-hole closed (built-without-store graphs refuse to
serve beside a live store), `roots_path` recorded in the manifest, dead code
removed.

## Integrator adjudications (recorded in the contract appendix addendum)

The THIRD stale absent-today vacuity guard (sim2's staleness-CLI guard)
retired in place — same unsatisfiable-self-contradiction class as the
sim3/sim4 twins; the builder reported it and touched neither cell (the prime
law held all three times). U2's judgment calls ratified: dual root-input
shapes (yaml stays CLI-only), stdlib `SchemaRejection` as the distinct
presence-limb type, the sibling-cortex-store convention, whole-file
`roots_hash`, `bound_subjects` = the store's subject keys. Evidence-binding
of causal edges from root inputs is a DECLARED wave-4 adapters deferral —
build-path causal edges derive P6 until the §2.2 adapters land.

## Verification on the integrated tree (`python3.12`, PG17)

- `test_cog3_*`: **297 passed, 0 failed** — THE ENTIRE CORPUS IS GREEN
  (state-function 59, sims 1-6 all, gates 139, tripwire 11).
- `test_cog2_*` 280 passed / 3 skipped; census tests + egg-export suite green
  (in-egg census verifier PASSES against committed HEAD — verified via
  `git archive` byte-parse before push); census `--check` PASS at exact zero
  headroom (modules 221==221, +7 running total; lines 64680==64680, +1194
  running total; compiler 1==1).
- `cog2-import-gate.py` rc=0; `check-layer-separation.sh` green.
- The single remaining local failure is the KNOWN pre-existing
  `test_cognitive_phase2_rollback.py::test_manifest_covers_committed_cog2_footprint`
  full-clone class (open-ended BASELINE..HEAD ratchet; CI shallow-skips it;
  backlogged systemic fix — same no-scope-creep precedent as cp1/COG-2).

Provenance: per the 2026-07-07 full-autonomy grant + the Captain 2026-07-20
cognitive-masterplan grant; contract + its build-time adjudications appendix.
