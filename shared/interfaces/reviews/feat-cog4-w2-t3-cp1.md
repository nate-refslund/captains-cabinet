# Checkpoint review — feat/cog4-w2-t3, cp1 (COG-4 W2 corpus, unit T3: gate batteries)

**Scope:** the T3 gate-battery corpus unit of the COG-4 contract
(`docs/plans/cognitive-core-phase-4-contract-2026-07-23.md` §10 N6, §5.3/N9,
§9.2 floor conservation, §4.3 organ-manifest controls + §5.2 + §5.5), off
`origin/master` `cee6741e`. Five NEW files, 2145 lines total — over the
FW-019 300-line threshold → this artifact is required. Purely ADDITIVE:
`git status --porcelain` shows ONLY the five new files (corpus law §13 —
no existing test/lib file touched; zero contradictions encountered).

1. `cabinet/scripts/tests/lib_cog4_floors.py` (NEW, 280 lines) — the §9.2
   floor-conservation REFERENCE checker (COUNT + TUPLE strength, SF5) the W6
   compose commits will run: absorbed-row floors derived through the REAL
   `framework.watchdog.registry` helpers read-only (`_parse_services_manifest`,
   `_floor_for_entry`, `_service_log_candidates` — fidelity by construction);
   per-organ expectations = the reference twin of the future
   `registry._parse_organ_manifests`; association law = organ name == absorbed
   row name, 1:1 over the composed set. Plus `wall_clock_bound(p95)` — the §10
   S0 floor-aware bound formula: max(p95 × 1.25, p95 + 5s) for sub-10s rows,
   ×1.25 above.
2. `cabinet/scripts/tests/test_cog4_measurement.py` (NEW, 396) — N6: the
   anti-phantom consumer scan (CONSUMPTION patterns, never doc mentions; this
   file is itself the §10.3 designated consumer via its `_enforced()` environ
   read, so the ≥1-real-consumer invariant holds from this commit onward);
   verify-twin vacuity arm (REDs if the twin lands without the flag, REDs the
   companion if it lands with it); the deterministic proxies (activation counts
   + budget units EXACT from a seeded schedule.jsonl) in the ALWAYS-ON battery
   with over-activation + inflated-cost mutants; the wall-clock tripwire
   (declared measure-only skip unarmed, live fixture assertion armed) with the
   inflated-p95 mutant proven under monkeypatch-armed enforcement; the
   cog4-measure/S0-baseline vacuity arm.
3. `cabinet/scripts/tests/test_cog4_parity.py` (NEW, 266) — N9: record-shape +
   divergent-tuple checkers over `cog4-parity-record.json` (ceiling compares
   as a SET; empty rows = error, the R-A non-empty idiom; flat operation ids
   refused); single-member divergence proven to bite per tuple member
   (risk_class / ceiling / undo_contract / shadow_verdict); real-CLI+record
   vacuity arm (rglob for the record, so W5/W6's landing location cannot dodge
   the companion).
4. `cabinet/scripts/tests/test_cog4_floor_conservation.py` (NEW, 287) — the
   §9.2 battery over synthetic services.yml/manifest pairs, all LIVE: clean
   compose green; count-drop, missing-freshness, LOOSENED-threshold (SF5),
   cadence-slower, shared-runner-log probe (against the REAL
   `_service_log_candidates` path AND the relative basename spelling),
   duplicate-probe, non-atomic-compose, keepalive-target mutants each RED;
   the real `_floor_for_entry` values pinned (43800/93600/87000) so a
   watchdog floor-law change REDs this corpus honestly; the
   `_parse_organ_manifests` vacuity arm (hasattr companion).
5. `cabinet/scripts/tests/test_cog4_organ_manifest.py` (NEW, 916) — §4.3
   controls AGAINST THE CG-33 AMENDMENT PROPOSAL TEXT (germline pair
   byte-untouched, schg never worked around): a reference validator
   transcribed from proposal §1a/§1b (13 required-when-organ keys;
   starvation_bound optional per SF2; top-level key closure anchored to the
   REAL schema's property set ∪ the proposed 14); missing freshness_needs /
   descriptor RED; ALL 30 ACTION_TYPES members proven un-collidable in
   `domain_operations` (the `/` separator law); duplicate `state_ownership`
   RED at SUITE level (N-b); N-d matrix consistency through the real loaded
   matrix (`risk_of` + `ceiling_frozenset_map`, both the risk and ceiling
   limbs proven; `ambiguous` fails closed); the §5.2 capability-keyed verdict
   mutant RED (identical descriptor, divergent verdicts — the hard-ceiling
   bypass named); §5.5 trajectory-v2 shapes (version dispatch BEFORE v1
   checks with the v1-first mutant proven to misroute; namespaced
   `action_type` RED; 7-status enum pinned to the real v1 schema bytes);
   germline-pair + v2-schema vacuity arms with per-limb companions.

## Verification evidence (all python3.12, this clone, pre-commit)

- **Bare tree:** the four new suites 83 passed / 7 skipped (6 vacuity arms +
  1 DECLARED wall-clock posture skip); full `test_cog4_*` set (W1 guards +
  T3) 277 passed / 14 skipped (the other 7 skips are W1's own vacuity
  guards, untouched).
- **Armed run** (`COG4_ENFORCE_BOUND=1`): measurement suite 18 passed /
  2 skipped — the posture skip flips to a live assertion, green.
- **Companion tripwires proven to RED** via transient untracked files
  (created → run → removed) and in-process mutation: verify twin without the
  flag (§10.3 RED) and with it (retire RED); `cog4-measure.py`;
  `cog4-parity.py`; a tracked parity record; `registry._parse_organ_manifests`
  (setattr); the germline arm per limb (kind enum / undo grammar / proposed
  field / ORGAN BLOCK, via deep-copied schema + text swap — the real files
  never touched); the v2 schema file. Tree state after: only the five new
  files untracked.
- **Gates:** `cog2-import-gate.py` exit 0 (the new files ride the
  `test_cog4_*`/`lib_cog4_*` allowlist globs; no forbidden token anywhere, so
  no assembled-token spelling was needed); `check-layer-separation.sh` OK
  (new=0); `cognitive-architecture-census.py --check` exit 0 — framework
  modules 226 ≤ 226 and lines 65012 ≤ 65012 unchanged (tests are
  budget-exempt, verified not assumed).
- **Model:** authored on Fable 5 (corpus authorship = judgment tier, §14.3).

Provenance: per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
