"""lib_cog5_scoring_fixtures.py — the COG-5 W2 T2 SCORING/CANDIDATE family
fixture core (contract cognitive-core-phase-5-contract-2026-07-24 §12 sims
2/3/4/5/8 + the §4 arming battery + §4.5 both honest-negative arms + the §9.3
certainty grammar + the §6.2/§6.3 league-closure machinery).

OWNERSHIP (W2 naming law): this file is authored and owned by the W2 T2 unit
(prefix family `lib_cog5_scoring*`). The cross-unit shared core
`lib_cog5_corpus.py` is W2 T1-OWNED — T2 IMPORTS it (guarded below while the
parallel T1 branch is un-joined) and never creates or edits it. T1 owns
`lib_cog5_archive*`, T3 owns `lib_cog5_boundary*` — the three units never
collide on a file (§13).

WHAT THIS LIB IS (and is not): `framework/evolution/{scorers,candidate,
league}.py` and `cabinet/scripts/cog5-gate-arm.py` do NOT exist yet — the
corpus lands BEFORE the implementation (tests-first, §13). The REFERENCE
machinery below implements the contract's scoring/admission semantics over
scratch fixtures so every sim assert + every §12 negative-control mutant is
proven BITING NOW, on this tree, with zero implementation present. Two REAL,
ALREADY-SHIPPED surfaces are deliberately bound live (they are inputs my
family composes, not future code): `framework.fidelity.regression_gate`
(the three-valued predicate the §4.3/§4.5 arming stage wraps) and
`framework.learning.gate.ratify` (the injectable seam — exercised on a
SCRATCH root only; gate.py is schg germline and stays byte-untouched, §4.1).
The reference machinery is NOT the implementation and never ships outside the
test surface. When the real modules land, the SAME assert batteries run
against them (integrator corpus surgery per §13 — builders never edit tests;
contradictions route to the integrator).

CORPUS-PINNED VOCABULARY (the executable spec the implementation binds to):
  admission outcomes    ADMISSION_ELIGIBLE "eligible" | ADMISSION_REFUSED
                        "refused" — nothing else; the regression stage's
                        three-valued outcome token rides the pack VERBATIM
                        (`pass`/`fail`/`no_verdict`, never converted — §4.5).
  refusal reasons       REASON_NO_REGRESSION_EVIDENCE "no_regression_evidence"
                        (§4.5 verbatim — the empty-corpus refusal, never
                        spelled `fail`, never spelled `pass`);
                        REASON_FROZEN_REGRESSION "frozen_regression";
                        the flat-candidate honest negative carries the REAL
                        regression_gate reason bytes ("no frozen case
                        improved (predicate requires >=1)") with empty
                        regressed/improved — distinguishable from a
                        regression fail AND from an evaluation failure.
  score vector (§9.1)   {"vector": {dim: {"value": float|"unknown",
                        "kind": "machine"|"judge", "derivation": str|None}},
                        "table_order": float}
                        — schema-SEPARATED: every eligibility predicate reads
                        `vector` only; `table_order` is presentation;
                        "unknown" never satisfies a floor (L239); judge dims
                        may rank, never satisfy a floor (X6).
  derivation (X6/§9.1)  the EVIDENCE SOURCE each dim's number was actually
                        read from, stamped by the CONSTRUCTOR from the
                        evidence object it read — the caller passes EVIDENCE,
                        never a derivation label (the §6.2 chain-of-custody
                        shape lifted to the vector). A MACHINE dim whose
                        derivation is judge-sourced, absent, out-of-enum, or
                        VALUE-MISMATCHED can NEVER satisfy a floor: the `kind`
                        label alone is a self-declaration, and X6 binds the
                        VALUE to machine evidence, not the label. A machine
                        dim's number is MEASURED from its evidence
                        (measure_from_evidence), never taken on the caller's
                        word — a declared number that disagrees with what its
                        evidence actually says stamps
                        `mismatch:value_not_measured_from_evidence` and dies
                        at the floor. What the wall does NOT cover is stated
                        verbatim in the HONEST SCOPE block at make_vector —
                        read it before quoting this law: the EVIDENCE CHANNEL
                        is still the caller's.
  provenance (§6.2)     CLOSED enum {real_live, real_mined, synthetic,
                        sim_replay}; stamped by the INGESTER from the named
                        source class — a row arriving with its own
                        `provenance` key REFUSES (chain-of-custody: candidate/
                        league/generator code can never set or rewrite it).
                        SET *and* REWRITE are both covered: ingestion seals
                        the custody fields under an ingester-plane key, so a
                        post-ingest rewrite breaks the seal and stops
                        counting. ONLY real_live/real_mined rows from the
                        NAMED real sources, with an INTACT seal, count toward
                        the §6.2 minimums.
  league rows (§6.3)    every league output while closed carries
                        `fitness_claim: "none"` (schema-required) and speaks
                        scored/ranked/observed — NEVER the Captain vocabulary
                        (tested / falsified / "it worked") in a value OR a
                        KEY, never review.source verdict_human (§9.3 SIM-2
                        extension), and its `certainty` is capped at the
                        states.py P5 rung: the states ABOVE the cap
                        (intervention_supported / falsified) are reachable in
                        `derive_edge_state` ONLY through human-verdict fuel,
                        so a machine artifact claiming one is the machine
                        speaking as the human channel.
  §6.2 minimums         real_trajectory_floor 10 (MIN_PAIRS), captain_label_
                        floor 10, judge_agreement_bar 0.80 (JUDGE_HARD_BAR),
                        judge_min_pairs 10, baseline_match_rate 0.083
                        (run_f1) — pinned here AND bound to the estate bytes
                        by estate_constant() drift tripwires.

Synthetic corpora are sanctioned for plumbing + mutants (§8.1); what synthetic
may NEVER do is open the league or ground a live-fitness claim — encoded here
as league_may_open() + the fitness_claim law + their mutants.

Pure stdlib + the sanctioned SHIPPED-framework imports named above (the
fidelity regression predicate + its CASE_FORMAT + the gate seam — real bytes
on the bare tree, never future surfaces; the objectives grammar tokens are
AST-read from file bytes, never imported — the boundary rows stay intact).
Data-plane store tokens are NEVER written contiguously in this file (the
assembled-token discipline; this family needs none of them).

S0: interpreter python3.12; no DB, no network (children are local
subprocesses with explicit env).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant (COG-5 contract §12/§13, W2 T2 — corpus
authorship is judgment-tier work). ORIGINAL BUILD (ab8fe00a): Fable 5. FIX
ROUNDS (27197a63 crown-jewel circumventions; this round's five re-review
notes): Opus 5, the program's primary model from 2026-07-25.
"""
from __future__ import annotations

import ast
import hashlib
import hmac
import inspect
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# --------------------------------------------------------------------------
# the t1-owned shared core — imported from the sibling W2 unit. The parallel
# branches built off one master tip and the integrator joined them; T1's
# lib_cog5_corpus.py is IN-TREE, so this import binds and the except-arm is
# now unreachable in a healthy checkout.
# RETIREMENT DISCHARGED at the W2 integration landing: the sibling test
# `test_cog5_sim_scoring.py::TestCorpusCoreJoin` no longer skips — both arms
# are LIVE assertions (the core imported, and it bound to THESE bytes).
# The except-arm is kept deliberately: it turns a vanished/renamed core into
# that test's named assertion failure instead of a collection error that
# takes the whole module down. It must never again be a silent skip. T2
# imports the core and never creates it (the W2 naming law, §13).
# --------------------------------------------------------------------------
try:
    import lib_cog5_corpus as CORE  # noqa: F401  (t1-owned; presence proven at join)
except ModuleNotFoundError:
    CORE = None  # pre-join bare tree — the sibling guard owns the honesty

# The two sanctioned SHIPPED surfaces this family composes (real bytes, on
# the tree today — not future implementation):
from framework.fidelity import regression_gate as _rg              # noqa: E402
from framework.fidelity.regression_corpus_lib import CASE_FORMAT   # noqa: E402
from framework.learning import gate as _gate                       # noqa: E402

# --------------------------------------------------------------------------
# shared constants (T2 family; the future implementation binds to THESE)
# --------------------------------------------------------------------------
EVOLUTION_TREE_REL = "framework/evolution"
SCORERS_MODULE = "framework.evolution.scorers"
CANDIDATE_MODULE = "framework.evolution.candidate"
LEAGUE_MODULE = "framework.evolution.league"
GATE_ARM_CLI_REL = "cabinet/scripts/cog5-gate-arm.py"
ARMING_RECORD_REL = "docs/plans/cog5-league-arming-record-2026-07-24.yml"

ADMISSION_ELIGIBLE = "eligible"
ADMISSION_REFUSED = "refused"
REASON_NO_REGRESSION_EVIDENCE = "no_regression_evidence"   # §4.5 verbatim
REASON_FROZEN_REGRESSION = "frozen_regression"
# the flat-candidate honest negative carries the REAL predicate reason bytes:
FLAT_REASON_FRAGMENT = "no frozen case improved"

MACHINE_KIND = "machine"
JUDGE_KIND = "judge"
UNKNOWN = "unknown"                    # quarantine value — never averaged

# §9.1/X6 DERIVATION enum (CLOSED): the evidence source a dim's number was
# actually read from. Stamped by the constructor from the evidence OBJECT, so
# there is no LABEL parameter for a caller to name (the §6.2 custody shape,
# lifted to the vector). PRECISELY: that closes the LABEL channel only — the
# caller still chooses which evidence object to hand over, and the object's
# TYPE decides the stamp. See the HONEST SCOPE block at make_vector for the
# full statement of what this wall covers and what it leaves open.
DERIVATION_KEY = "derivation"
DERIVATION_GATE_RESULT = "machine:gate_result"      # a real rg.GateResult
DERIVATION_REPLAY_MAP = "machine:replay_map"        # a real {case: bool} map
DERIVATION_SCORER_TRIPLE = "machine:scorer_triple"  # the sim-8 triple outputs
DERIVATION_JUDGE_LLM = "judge:llm_score"            # a judge/LLM number
# ...and the custody BREACH stamp: a machine dim whose declared number is not
# the number its own machine evidence yields. Deliberately OUTSIDE
# MACHINE_DERIVATIONS so the existing fail-closed path refuses it with no new
# plumbing at the joint (machine_derivation_violations → [FLOOR-DERIVATION]).
DERIVATION_VALUE_MISMATCH = "mismatch:value_not_measured_from_evidence"
MACHINE_DERIVATIONS = frozenset({DERIVATION_GATE_RESULT, DERIVATION_REPLAY_MAP,
                                 DERIVATION_SCORER_TRIPLE})
JUDGE_DERIVATIONS = frozenset({DERIVATION_JUDGE_LLM})

# §6.2 recorded minimums (derived from the estate's own constants; the
# estate_constant() tripwires below bind these to the real bytes):
REAL_TRAJECTORY_FLOOR = 10             # judge_calibration.MIN_PAIRS
CAPTAIN_LABEL_FLOOR = 10               # same MIN_PAIRS logic, human channel
JUDGE_AGREEMENT_BAR = 0.80             # judge_calibration.JUDGE_HARD_BAR
JUDGE_MIN_PAIRS = 10                   # judge_calibration.MIN_PAIRS
BASELINE_MATCH_RATE = 0.083            # run_f1.BASELINE_MATCH_RATE

# §6.2 provenance (CLOSED, schema-internal — validated here, never a central
# enum per §11.1):
PROVENANCE_ENUM = frozenset({"real_live", "real_mined", "synthetic", "sim_replay"})
REAL_PROVENANCE = frozenset({"real_live", "real_mined"})
# the NAMED real sources (§6.2 chain-of-custody / §5.3 / §2.2):
SOURCE_CLASS_TO_PROVENANCE: dict[str, str] = {
    "consequence_ledger": "real_mined",
    "fidelity_receipts": "real_mined",
    "instance_corpus": "real_mined",
    "verdict_inbox_labels": "real_mined",
    "live_emission": "real_live",
    "generator": "synthetic",
    "arena": "synthetic",
    "sim_replay": "sim_replay",
}
NAMED_REAL_SOURCES = frozenset(
    k for k, v in SOURCE_CLASS_TO_PROVENANCE.items() if v in REAL_PROVENANCE)

# §9.3 certainty grammar: machine-class artifacts speak these...
MACHINE_SPEAK = frozenset({"scored", "ranked", "observed"})
# ...and NEVER these (the Captain vocabulary; word-boundary scanned):
_CAPTAIN_VOCAB_RE = re.compile(r"\btested\b|\bfalsified\b|\bit worked\b",
                               re.IGNORECASE)
# the P5 cap token for machine artifacts on mission edges (bound to
# framework.objectives.states by estate_grammar() below):
P5_CAP = "observationally_supported"
HUMAN_VERDICT_SOURCE = "verdict_human"

DIVERGENCE_THRESHOLD = 0.15            # sim-5 fixture parameter
DEMOTE_WITHHOLD = "demote_withhold"    # the X4 signal token

HASHSEED_TRIPLE = ("0", "1", "2")      # sim 8: 3 subprocess runs, distinct seeds


# --------------------------------------------------------------------------
# estate byte-binds (drift tripwires — the §6.2 derivation + §9.3 grammar
# stay bound to the REAL constants, parsed from bytes so this lib never
# imports the heavier fidelity modules at import time)
# --------------------------------------------------------------------------
def estate_constant(rel_path: str, name: str) -> Any:
    """AST-read a module-level `NAME = <literal>` from a repo file's bytes.
    Byte-binding without importing (run_f1 pulls the officer-prompt stack)."""
    tree = ast.parse((_REPO / rel_path).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"{rel_path}: constant {name} not found")


STATES_REL = "framework/objectives/states.py"


def estate_grammar() -> dict[str, str]:
    """The REAL certainty-grammar tokens read from
    framework/objectives/states.py BYTES (AST, never an import — the
    objectives module row allowlists no cog5 importer, and this family
    needs the tokens, not the module; the boundary stays intact)."""
    rel = STATES_REL
    return {
        "p5": estate_constant(rel, "STATE_OBSERVATIONALLY_SUPPORTED"),
        "human_source": estate_constant(rel, "HUMAN_VERDICT_SOURCE"),
    }


def _names_in(node: ast.AST) -> frozenset[str]:
    """Every bare Name / attribute-tail identifier appearing in an expression."""
    out: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            out.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            out.add(sub.attr)
    return frozenset(out)


def _guarded_returns(stmts: list[ast.stmt], guard: frozenset[str],
                     out: list[tuple[ast.Return, frozenset[str]]]) -> None:
    """Collect (Return, enclosing-guard-names). An `if` test guards its BODY
    only; the else/elif branch inherits the OUTER guard (its own nested `if`
    contributes its own test)."""
    for st in stmts:
        if isinstance(st, ast.If):
            _guarded_returns(st.body, guard | _names_in(st.test), out)
            _guarded_returns(st.orelse, guard, out)
        elif isinstance(st, (ast.For, ast.While, ast.With, ast.Try)):
            for field in ("body", "orelse", "finalbody", "handlers"):
                block = getattr(st, field, None) or []
                if field == "handlers":
                    for handler in block:
                        _guarded_returns(handler.body, guard, out)
                else:
                    _guarded_returns(block, guard, out)
        elif isinstance(st, ast.Return):
            out.append((st, guard))


def estate_certainty_ladder(source: Optional[str] = None) -> dict[str, Any]:
    """DERIVE the §9.3 P5 cap from framework/objectives/states.py BYTES — the
    ladder is READ, never a hardcoded list (AST only; the objectives boundary
    row allowlists no cog5 importer).

    The derivation encodes the law states.py:237 states in its own comment —
    P5 `observationally_supported` is "the CAP for all non-human-verdict
    evidence": a state token is MACHINE-REACHABLE iff `derive_edge_state` has
    at least one `return EdgeState(STATE_X, ...)` whose enclosing guards do
    NOT test a human-verdict fuel flag (a flag assigned True inside a branch
    whose test names HUMAN_VERDICT_SOURCE — states.py:34-39, "the ONLY
    promotion fuel" / "the ONLY refutation fuel"). Everything else is ABOVE
    THE CAP: reachable only through the human channel, so a machine-class
    artifact claiming it is the machine speaking as the human.

    `source` overrides the bytes (the discriminator proof feeds a mutated
    states.py and watches the derived sets move — the scan must be a
    discriminator, never a constant)."""
    text = source if source is not None else \
        (_REPO / STATES_REL).read_text(encoding="utf-8")
    tree = ast.parse(text)

    tokens: dict[str, str] = {}          # STATE_* name -> its literal token
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id.startswith("STATE_"):
                    tokens[tgt.id] = ast.literal_eval(node.value)
    fn = next((n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == "derive_edge_state"),
              None)
    assert fn is not None, f"{STATES_REL}: derive_edge_state not found"

    human_fuel: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.If) and "HUMAN_VERDICT_SOURCE" in _names_in(node.test):
            for sub in node.body:
                if isinstance(sub, ast.Assign):
                    for tgt in sub.targets:
                        if isinstance(tgt, ast.Name):
                            human_fuel.add(tgt.id)

    returns: list[tuple[ast.Return, frozenset[str]]] = []
    _guarded_returns(fn.body, frozenset(), returns)
    machine_reachable: set[str] = set()
    for ret, guard in returns:
        call = ret.value
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                and call.func.id == "EdgeState" and call.args):
            continue
        arg0 = call.args[0]
        if not (isinstance(arg0, ast.Name) and arg0.id in tokens):
            continue
        if not (guard & human_fuel):
            machine_reachable.add(tokens[arg0.id])
    all_states = frozenset(tokens.values())
    return {
        "all_states": all_states,
        "human_fuel_flags": frozenset(human_fuel),
        "machine_reachable": frozenset(machine_reachable),
        "above_cap": all_states - frozenset(machine_reachable),
        "cap": tokens.get("STATE_OBSERVATIONALLY_SUPPORTED"),
    }


# --------------------------------------------------------------------------
# scratch regression corpus (REAL case format — load_corpus() validates it)
# --------------------------------------------------------------------------
def case_ids(n: int = 20) -> list[str]:
    return [f"case-{i:03d}" for i in range(1, n + 1)]


def write_scratch_corpus(corpus_dir: Path, ids: list[str]) -> Path:
    """A frozen-corpus scratch fixture in the REAL on-disk case format
    (CASE_FORMAT + the load_corpus() required keys) so corpus_case_ids()
    reads it through the SHIPPED loader, not a shortcut."""
    cases = corpus_dir / "cases"
    cases.mkdir(parents=True, exist_ok=True)
    for cid in ids:
        (cases / f"{cid}.json").write_text(json.dumps({
            "case_format": CASE_FORMAT,
            "case_id": cid,
            "cell": {"actor": "officer", "action_type": "fixture"},
            "situation": {"prompt": f"fixture situation {cid}"},
            "human_verdict": {"verdict": "edit", "correction": "fixture"},
        }, indent=2), encoding="utf-8")
    return corpus_dir


def results_baseline(ids: list[str], learned: int = 15) -> dict[str, bool]:
    """Baseline replay results: the first `learned` frozen cases agree, the
    rest still fail (room for improvement AND for regression — both sims)."""
    return {cid: (i < learned) for i, cid in enumerate(ids)}


def results_improving(base: Mapping[str, bool], fix: str) -> dict[str, bool]:
    out = dict(base)
    assert out[fix] is False, "fixture invariant: `fix` must be a failing case"
    out[fix] = True
    return out


def results_known_bad(base: Mapping[str, bool], lose: str) -> dict[str, bool]:
    out = dict(base)
    assert out[lose] is True, "fixture invariant: `lose` must be a learned case"
    out[lose] = False
    return out


# --------------------------------------------------------------------------
# §9.1 score vectors + machine-floor eligibility + ranking (+ their mutants)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class JudgeEvidence:
    """A judge/LLM score, as an EVIDENCE object. Wrapping it makes the
    derivation classifiable: a bare float is indistinguishable from a machine
    measurement, and that indistinguishability IS the X6 escape."""
    score: float


def _classify_evidence(evidence: Any) -> tuple[Optional[str], Any]:
    """ONE read of an evidence object, yielding BOTH what it is (the closed
    derivation enum) and what NUMBER it says. Stamp and measurement come from
    the same classification by construction, so they can never disagree about
    the object — two separate reads could drift apart, which is a hole of
    exactly the kind this family exists to catch.

    Unrecognized/absent evidence yields (None, None) — and None never
    satisfies a floor (fail closed: an unprovenanced number is exactly as
    untrustworthy as a judge-sourced one)."""
    if isinstance(evidence, _rg.GateResult):
        return DERIVATION_GATE_RESULT, len(evidence.regressed)
    if isinstance(evidence, JudgeEvidence):
        return DERIVATION_JUDGE_LLM, evidence.score
    if isinstance(evidence, Mapping) and evidence and \
            all(isinstance(v, bool) for v in evidence.values()):
        passed = sum(1 for v in evidence.values() if v is True)
        return DERIVATION_REPLAY_MAP, passed / len(evidence)
    if isinstance(evidence, (list, tuple)) and evidence and \
            all(isinstance(o, str) for o in evidence):
        try:
            return DERIVATION_SCORER_TRIPLE, quarantine_fold(list(evidence))
        except ValueError:
            # unparseable scorer output is not a number — quarantine, never
            # crash the constructor (fail closed, the L239 posture).
            return DERIVATION_SCORER_TRIPLE, UNKNOWN
    return None, None


def derive_from_evidence(evidence: Any) -> Optional[str]:
    """The derivation STAMP an evidence object earns (see _classify_evidence)."""
    return _classify_evidence(evidence)[0]


def measure_from_evidence(evidence: Any) -> Any:
    """The NUMBER an evidence object itself yields — a gate result's regressed
    COUNT, a replay map's pass RATE, a scorer triple's quarantine fold. This is
    what a machine dim's value must BE; a caller's declared number is a claim
    checked against it, never the source (X6 binds the VALUE)."""
    return _classify_evidence(evidence)[1]


def make_vector(dims: Mapping[str, tuple[Any, str]],
                table_order: float = 0.0,
                evidence: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    """The §9.1 schema-SEPARATED scorer output: `vector` (floors-checkable)
    apart from `table_order` (presentation only).

    CHAIN OF CUSTODY (X6, the §6.2 ingester shape lifted to the vector). Two
    channels are closed here, and they are NOT the same channel:

      * the LABEL channel — each dim's `derivation` is STAMPED from the
        evidence OBJECT the caller handed over, and there is no derivation
        parameter, so a caller cannot NAME a machine derivation. A judge
        number passed as a machine dim's evidence stamps `judge:llm_score`
        and dies at the floor; evidence the constructor cannot classify
        stamps None and dies the same way.
      * the VALUE channel — a MACHINE dim carrying MACHINE evidence takes its
        number FROM that evidence (measure_from_evidence). A declared number
        that disagrees with its own evidence is a custody breach: the vector
        records the MEASUREMENT (the caller's claim never enters it) and
        stamps DERIVATION_VALUE_MISMATCH, which is outside MACHINE_DERIVATIONS
        and so dies at the floor exactly like a judge-sourced one.

    HONEST SCOPE — what this wall does NOT cover (the claim that stood here
    before, "there is no derivation parameter, so a caller can never NAME
    machine custody for a number it did not measure", was FALSE as written,
    and a docstring claiming what the bytes do not deliver is the failure
    class this corpus exists to catch):

      (1) THE EVIDENCE CHANNEL IS STILL THE CALLER'S. The stamp follows the
          evidence object's TYPE, so a machine-SHAPED object fabricated by the
          caller — a one-row `{"case-001": True}` map — stamps
          `machine:replay_map` with no label forgery anywhere. Closing the
          value channel means such a pack can no longer carry the judge's
          number, but a fabricated map that AGREES with its own declared value
          still reads as machine custody. Binding a replay map to the identity
          of the frozen corpus that produced it is an UPSTREAM obligation (it
          lives at the replay stage that mints the map, not at the vector
          layer), and §9.1 ratifies no such clause here. DECLARED RESIDUAL,
          pinned by test_declared_residual_self_consistent_fabricated_evidence
          so it cannot rot back into a claim.
      (2) THE VALUE LAW IS FIXTURE-TIER, NOT RE-RUNNABLE AT W6. It holds at
          CONSTRUCTION, because that is the only place the evidence exists.
          A §9.1 pack carries {value, kind, derivation} and NOT its evidence,
          so `assert_machine_values_measured_from_evidence` cannot re-derive a
          landed `scorers.py` pack's numbers without an obligation §9.1 does
          not ratify (the pack carrying its evidence). DECLARED RESIDUAL of
          the same class as the keyed seal deliberately NOT shipped for the
          label channel. What DOES re-run at W6 against the real surface:
          `assert_machine_floors_machine_derived` (the stamps),
          `assert_no_derivation_parameter` (the label channel, over the real
          constructor's signature) and `assert_derivation_refused` (the
          joint)."""
    ev = dict(evidence or {})
    vector: dict[str, Any] = {}
    for name, (value, kind) in dims.items():
        assert kind in (MACHINE_KIND, JUDGE_KIND), f"bad dim kind {kind!r}"
        assert value == UNKNOWN or isinstance(value, (int, float)), name
        derivation, measured = _classify_evidence(ev.get(name))
        if kind == MACHINE_KIND and derivation in MACHINE_DERIVATIONS:
            if value != measured:
                derivation = DERIVATION_VALUE_MISMATCH
            value = measured        # the CLAIM never enters the vector
        vector[name] = {"value": value, "kind": kind, DERIVATION_KEY: derivation}
    return {"vector": vector, "table_order": float(table_order)}


def candidate_vector(*, candidate_results: Mapping[str, bool],
                     gate_result: "_rg.GateResult",
                     judge_score: float,
                     table_order: float = 0.0) -> dict[str, Any]:
    """The reference scorer: machine dims measured from the REAL replay maps
    + the REAL gate result; the judge dim is ranking-only by construction.
    Every dim's derivation is stamped from the evidence object actually read
    (never declared) — the reference scorer's own custody proof."""
    total = len(candidate_results)
    passed = sum(1 for v in candidate_results.values() if v is True)
    return make_vector({
        "frozen_pass_rate": (passed / total, MACHINE_KIND),
        "frozen_regressions": (len(gate_result.regressed), MACHINE_KIND),
        "judge_score": (judge_score, JUDGE_KIND),
    }, table_order=table_order, evidence={
        "frozen_pass_rate": candidate_results,
        "frozen_regressions": gate_result,
        "judge_score": JudgeEvidence(judge_score),
    })


def mutant_judge_number_into_machine_dim(*, judge_score: float,
                                         table_order: float = 0.0,
                                         ) -> dict[str, Any]:
    """§12 sim-4 NEGATIVE CONTROL (X6, the DERIVATION arm): the same escape
    built through the HONEST constructor — the scorer hands the judge's
    number over as the machine dim's evidence. Construction stamps the truth
    (`judge:llm_score`) and the floor predicate must refuse it. This is the
    exact repro the fresh-context review filed: a judge-derived value
    satisfying a MACHINE floor while every `kind` label reads 'machine'.

    `frozen_regressions` is deliberately HONEST (a real gate result whose
    regressed count the declared 0 matches) — the SAME discipline the sibling
    `mutant_fabricated_evidence_for_a_machine_dim` already carried, applied
    here by integrator surgery. It used to carry the judge's evidence too, so
    the mutant was OVER-DETERMINED: two machine dims were bad at once, and
    reverting the MF1 construction stamp ALONE no longer REDed
    `test_mutant_judge_derived_number_on_a_machine_floor_REDS` — the value law
    independently caught the revert via the second dim, MASKING it. The escape
    under test is ONE machine floor fed the judge's number, so exactly one dim
    models it and the bite isolates to the property being proven."""
    return make_vector({
        "frozen_pass_rate": (judge_score, MACHINE_KIND),
        "frozen_regressions": (0, MACHINE_KIND),
        "judge_score": (judge_score, JUDGE_KIND),
    }, table_order=table_order, evidence={
        "frozen_pass_rate": JudgeEvidence(judge_score),
        "frozen_regressions": _rg.GateResult(outcome=_rg.OUTCOME_PASS),
        "judge_score": JudgeEvidence(judge_score),
    })


def mutant_fabricated_evidence_for_a_machine_dim(*, judge_score: float,
                                                 table_order: float = 0.0,
                                                 ) -> dict[str, Any]:
    """§12 sim-4 NEGATIVE CONTROL (X6, the EVIDENCE-CHANNEL arm — the escape
    the targeted re-review proved was STILL open after the label channel was
    closed): the scorer keeps the judge's number but hands the machine dim a
    machine-SHAPED evidence object — ONE fabricated replay row — beside it.
    No label is forged and no derivation parameter is used, so the stamp came
    out `machine:replay_map` and the pack was admitted `(True, [])`.

    With the value channel closed, the declared 0.99 no longer matches what
    the fabricated map actually says (1/1), so the dim stamps
    DERIVATION_VALUE_MISMATCH and dies at the floor.

    `frozen_regressions` is deliberately HONEST here (a real gate result whose
    regressed count the declared 0 matches): the mutant must fail for the ONE
    reason under test, never for a second unrelated defect."""
    return make_vector({
        "frozen_pass_rate": (judge_score, MACHINE_KIND),
        "frozen_regressions": (0, MACHINE_KIND),
        "judge_score": (judge_score, JUDGE_KIND),
    }, table_order=table_order, evidence={
        "frozen_pass_rate": {"case-001": True},        # ONE fabricated row
        "frozen_regressions": _rg.GateResult(outcome=_rg.OUTCOME_PASS),
        "judge_score": JudgeEvidence(judge_score),
    })


def mutant_constructor_with_derivation_parameter(
        dims: Mapping[str, tuple[Any, str]], table_order: float = 0.0,
        derivation: Optional[Mapping[str, str]] = None) -> dict[str, Any]:
    """§9.1 NEGATIVE CONTROL for the LABEL channel: the constructor this
    family must never grow — one that lets the caller NAME each dim's
    custody. `assert_no_derivation_parameter` must RED on it, or that battery
    is decoration (§12)."""
    labels = dict(derivation or {})
    return {"vector": {n: {"value": v, "kind": k,
                           DERIVATION_KEY: labels.get(n)}
                       for n, (v, k) in dims.items()},
            "table_order": float(table_order)}


def machine_derivation_violations(pack: Mapping[str, Any]) -> list[str]:
    """Every MACHINE dim whose stamped derivation is not machine evidence —
    judge-sourced, absent, out-of-enum, or value-mismatched (fail closed)."""
    bad: list[str] = []
    for name, dim in pack["vector"].items():
        if dim.get("kind") != MACHINE_KIND:
            continue
        derivation = dim.get(DERIVATION_KEY)
        if derivation not in MACHINE_DERIVATIONS:
            bad.append(f"{name}={derivation!r}")
    return bad


def machine_dims(pack: Mapping[str, Any]) -> dict[str, Any]:
    return {n: d["value"] for n, d in pack["vector"].items()
            if d["kind"] == MACHINE_KIND}


def admission_eligible(pack: Mapping[str, Any],
                       incumbent: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """The reference floor predicate (§9.1/X6): MACHINE floors only —
    zero frozen regressions AND strict machine improvement over the
    incumbent pass-rate; `unknown` never satisfies a floor; judge dims are
    structurally invisible here; `table_order` is never read.

    X6 IS ABOUT THE VALUE, NOT THE LABEL: before any floor is read, every
    machine dim on BOTH sides must carry a MACHINE derivation. A `kind:
    machine` label is the scorer's own self-declaration — binding the floor
    to it alone lets a scorer copy the judge's number into a machine dim and
    satisfy the crown-jewel law with judge evidence. Judge-sourced, absent,
    and out-of-enum derivations all refuse (fail closed)."""
    reasons: list[str] = []
    for who, side in (("candidate", pack), ("incumbent", incumbent)):
        for bad in machine_derivation_violations(side):
            reasons.append(f"[FLOOR-DERIVATION] {who} machine dim {bad} is not "
                           "derived from machine evidence — a machine FLOOR is "
                           "satisfied by machine EVIDENCE, never by a dim that "
                           "merely calls itself machine (X6/§9.1)")
    if reasons:
        return False, reasons
    mine, theirs = machine_dims(pack), machine_dims(incumbent)
    for name in ("frozen_pass_rate", "frozen_regressions"):
        if mine.get(name) == UNKNOWN or theirs.get(name) == UNKNOWN:
            reasons.append(f"[FLOOR-UNKNOWN] {name} is quarantined 'unknown' — "
                           "missing evidence never satisfies a floor (L239)")
    if reasons:
        return False, reasons
    if mine["frozen_regressions"] != 0:
        reasons.append("[FLOOR-REGRESSION] frozen case(s) regressed")
    if not mine["frozen_pass_rate"] > theirs["frozen_pass_rate"]:
        reasons.append("[FLOOR-IMPROVEMENT] no machine-dimension improvement "
                       "over the incumbent")
    return (not reasons), reasons


def mutant_judge_floor_eligibility(pack: Mapping[str, Any],
                                   incumbent: Mapping[str, Any],
                                   ) -> tuple[bool, list[str]]:
    """§12 sim-4 NEGATIVE CONTROL (X3, the certainty-law arm): a judge score
    satisfying a floor — must make the sim-4 battery RED."""
    ok, reasons = admission_eligible(pack, incumbent)
    judge = pack["vector"].get("judge_score", {}).get("value", 0.0)
    if not ok and judge != UNKNOWN and judge >= JUDGE_AGREEMENT_BAR:
        return True, []          # the escape: judge evidence reaches the joint
    return ok, reasons


def mutant_table_order_eligibility(pack: Mapping[str, Any],
                                   incumbent: Mapping[str, Any],
                                   ) -> tuple[bool, list[str]]:
    """§9.1 NEGATIVE CONTROL: a predicate keying on `table_order` (the
    presentation scalar reaching an admission joint) — must RED."""
    del incumbent
    return (pack["table_order"] > 0.5), []


def rank_by_machine(named: Mapping[str, Mapping[str, Any]],
                    fold: Optional[Callable[[float], float]] = None,
                    incumbent: Optional[str] = None) -> list[str]:
    """The reference MACHINE-dimension ranking (sims 2/3): pass-rate
    dominant, regressions penalized; judge dims structurally absent from the
    key; quarantined 'unknown' sorts LAST (never above known evidence).
    TIE LAW: a challenger outranks ONLY by STRICT machine superiority —
    machine-key ties resolve incumbent-first (a tie is not an improvement,
    the §4.2/§9.1 demonstrated-improvement posture)."""
    def key(item: tuple[str, Mapping[str, Any]]):
        name, pack = item
        dims = machine_dims(pack)
        rate, regressions = dims["frozen_pass_rate"], dims["frozen_regressions"]
        not_incumbent = 0 if (incumbent is not None and name == incumbent) else 1
        if rate == UNKNOWN or regressions == UNKNOWN:
            return (1, 0.0, 0, not_incumbent, name)   # quarantine bucket: last
        r = fold(rate) if fold is not None else rate
        return (0, -r, regressions, not_incumbent, name)
    return [n for n, _ in sorted(named.items(), key=key)]


def mutant_judge_only_rank(named: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """§12 sim-2 NEGATIVE CONTROL: scorer ignores machine outcomes —
    judge-only rank. Must make the sim-2 battery RED."""
    def key(item: tuple[str, Mapping[str, Any]]):
        name, pack = item
        judge = pack["vector"].get("judge_score", {}).get("value", 0.0)
        return (-(judge if judge != UNKNOWN else 0.0), name)
    return [n for n, _ in sorted(named.items(), key=key)]


def insensitive_fold(rate: float) -> float:
    """§12 sim-3 NEGATIVE CONTROL: quarter-bucket aggregation that buries a
    one-case improvement (0.75 and 0.80 collapse into one bucket)."""
    import math
    return math.floor(rate * 4) / 4


# ---- sim assert batteries (the live tier runs these on reference outputs;
# ---- the mutant tier proves each REDs; the landed real surface re-runs the
# ---- SAME batteries via the integrator's corpus surgery per §13) ----------
def assert_sim2_known_bad_loses(rank: list[str], *, bad: str,
                                incumbent: str) -> None:
    assert rank.index(bad) > rank.index(incumbent), (
        "[SIM2-MACHINE-RANK] the known-bad candidate must rank BELOW the "
        "incumbent on machine-outcome dimensions (X2) — a judge-only rank is "
        "the named §12 escape")


def assert_sim3_improvement_detected(rank: list[str], *, good: str,
                                     incumbent: str) -> None:
    assert rank.index(good) < rank.index(incumbent), (
        "[SIM3-SENSITIVITY] the known-good small improvement must rank ABOVE "
        "the incumbent on the machine dimension — an insensitive fold that "
        "buries a one-case improvement is the named §12 escape")


def assert_sim4_judge_only_ineligible(eligible: bool, reasons: list[str]) -> None:
    assert eligible is False, (
        "[SIM4-X3] a judge-only winner must be admission/promotion-INELIGIBLE "
        "— a judge score satisfying a floor is the named §12 escape (the "
        "composite certainty law, §9.2)")
    assert any("[FLOOR-IMPROVEMENT]" in r or "[FLOOR-UNKNOWN]" in r
               for r in reasons), (
        "[SIM4-X3] the refusal must cite the unmet MACHINE floor")


def assert_machine_floors_machine_derived(pack: Mapping[str, Any]) -> None:
    """[SIM4-X6-DERIVATION] the re-runnable form of the custody law: every
    MACHINE dim in a scorer pack must be stamped with MACHINE evidence. Run
    this over the real `scorers.py` output at W6 surgery — it is the arm that
    stops a judge-derived number from ever reaching a machine floor, and it
    holds without executing the eligibility predicate at all."""
    bad = machine_derivation_violations(pack)
    assert not bad, (
        "[SIM4-X6-DERIVATION] machine dim(s) " + str(bad) + " are not derived "
        "from machine evidence — a scorer stamping a judge-derived (or "
        "unprovenanced) number as a machine dimension is the X6 escape the "
        "`kind` label alone cannot see (§9.1/§9.2)")


def value_evidence_mismatches(pack: Mapping[str, Any]) -> list[str]:
    """Every dim whose declared number disagreed with what its own machine
    evidence said (stamped at construction)."""
    return sorted(name for name, dim in pack["vector"].items()
                  if dim.get(DERIVATION_KEY) == DERIVATION_VALUE_MISMATCH)


def assert_machine_values_measured_from_evidence(pack: Mapping[str, Any]) -> None:
    """[SIM4-X6-MEASURED] the VALUE channel of the custody law: a machine
    dim's number must BE what its evidence says, not a number declared
    alongside it. DISTINCT tag from [SIM4-X6-DERIVATION] on purpose — a
    mismatch also trips the stamp battery (fail closed), and a shared tag
    would let a mutant test for one law go green on the other firing.

    SCOPE (see make_vector's HONEST SCOPE (2)): this is a FIXTURE-tier law,
    enforced where the evidence exists — at construction. It is NOT part of
    the W6 re-runnable set, because a §9.1 pack does not carry its
    evidence."""
    bad = value_evidence_mismatches(pack)
    assert not bad, (
        "[SIM4-X6-MEASURED] machine dim(s) " + str(bad) + " declared a number "
        "their own machine evidence does not yield — a scorer that reads real "
        "evidence and then reports a DIFFERENT number has machine custody in "
        "name only (§9.1/§9.2)")


def assert_no_derivation_parameter(*constructors: Callable) -> None:
    """[SIM4-X6-NO-LABEL] the LABEL channel of the custody law, as a
    re-runnable battery (promoted out of an inline test assert so integrator
    surgery can point it at the REAL scorer/vector constructor at W6 — the
    same promotion N4's table_order law got): no vector constructor may expose
    a parameter through which a caller NAMES a dim's derivation. Custody is
    stamped from evidence or it is not custody."""
    for fn in constructors:
        named = sorted(p for p in inspect.signature(fn).parameters
                       if "derivation" in p.lower())
        assert not named, (
            f"[SIM4-X6-NO-LABEL] {getattr(fn, '__name__', fn)!r} exposes "
            f"derivation parameter(s) {named} — a caller could then NAME "
            "machine custody for a judge number, which is the X6 escape the "
            "`kind` label alone cannot see (§9.1)")


def assert_derivation_refused(eligible: bool, reasons: list[str]) -> None:
    """[SIM4-X6-DERIVATION] the joint side of the same law: the predicate must
    REFUSE, citing the derivation, before any floor is read."""
    assert eligible is False, (
        "[SIM4-X6-DERIVATION] a pack whose machine floors rest on judge-"
        "derived or unprovenanced numbers must be admission-INELIGIBLE")
    assert any("[FLOOR-DERIVATION]" in r for r in reasons), (
        "[SIM4-X6-DERIVATION] the refusal must cite the DERIVATION, not merely "
        "an unmet floor — the law is about where the number came from")


def assert_table_order_never_reaches_the_joint(
        pack: Mapping[str, Any], incumbent: Mapping[str, Any],
        predicate: Callable = admission_eligible) -> None:
    """[LC-TABLE-ORDER] the §9.1 structural law, as a re-runnable battery
    (promoted out of an inline assert so integrator surgery can run it
    against the REAL league/scorer joint): two packs identical except for the
    presentation scalar must get the SAME answer. No scalar reaches any
    promotion, admission, or graduation joint."""
    high = {**pack, "table_order": 0.99}
    low = {**pack, "table_order": 0.01}
    assert predicate(high, incumbent) == predicate(low, incumbent), (
        "[LC-TABLE-ORDER] a predicate keying on table_order reaches an "
        "admission joint on a presentation scalar — `table_order` is display "
        "ordering; no scalar reaches any promotion, admission, or graduation "
        "joint (§9.1)")


def assert_sim5_divergence_flagged(out: Mapping[str, Any]) -> None:
    assert "public" in out and "private" in out, (
        "[SIM5-NO-SILENT-AVERAGE] both aggregates must survive in the output "
        "— a single averaged scalar replacing the pair is the named §12 escape")
    assert out.get("divergent") is True and out.get("signal") == DEMOTE_WITHHOLD, (
        "[SIM5-X4] public/private divergence must emit the demote/withhold "
        "signal, never a silent average")


def assert_sim8_quarantined(fold_value: Any) -> None:
    assert fold_value == UNKNOWN, (
        "[SIM8-QUARANTINE] a nondeterministic scorer's outputs must be "
        "quarantined 'unknown', NEVER averaged into the vector (the named "
        "§12 escape is exactly that averaging)")


# --------------------------------------------------------------------------
# sim 5 — public/private divergence (X4)
# --------------------------------------------------------------------------
def divergence_check(public: float, private: float,
                     threshold: float = DIVERGENCE_THRESHOLD) -> dict[str, Any]:
    """Reference aggregate comparator: BOTH aggregates preserved; divergence
    past the declared threshold emits the demote/withhold signal. There is no
    averaged replacement scalar anywhere in the output."""
    divergence = abs(public - private)
    divergent = divergence > threshold
    return {
        "public": public,
        "private": private,
        "divergence": round(divergence, 6),
        "divergent": divergent,
        "signal": DEMOTE_WITHHOLD if divergent else None,
    }


def mutant_average_divergence(public: float, private: float,
                              threshold: float = DIVERGENCE_THRESHOLD,
                              ) -> dict[str, Any]:
    """§12 sim-5 NEGATIVE CONTROL: the divergence silently averaged away."""
    del threshold
    return {"aggregate": (public + private) / 2}


# --------------------------------------------------------------------------
# sim 8 — nondeterministic scorer: the triple-run discipline
# --------------------------------------------------------------------------
DET_SCORER_SRC = """\
import hashlib, sys
token = sys.argv[1] if len(sys.argv) > 1 else "case-fixture"
val = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16) % 1000
print(f"{val/1000:.3f}")
"""

NONDET_SCORER_SRC = """\
import sys
token = sys.argv[1] if len(sys.argv) > 1 else "case-fixture"
print(f"{(hash(token) % 1000)/1000:.3f}")
"""


def write_scorer(workdir: Path, name: str, src: str) -> Path:
    path = workdir / name
    path.write_text(src, encoding="utf-8")
    return path


def run_scorer_triple(script: Path, workdir: Path,
                      token: str = "case-fixture-input") -> list[str]:
    """The §12 sim-8 discipline: 3 SUBPROCESS runs under 3 DISTINCT
    PYTHONHASHSEED values on identical input; the outputs are the evidence."""
    outputs: list[str] = []
    for seed in HASHSEED_TRIPLE:
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": seed}
        proc = subprocess.run(
            [sys.executable, str(script), token],
            cwd=str(workdir), env=env, capture_output=True, text=True,
            timeout=60, check=False)
        assert proc.returncode == 0, f"scorer child failed: {proc.stderr}"
        outputs.append(proc.stdout.strip())
    return outputs


def classify_determinism(outputs: list[str]) -> str:
    return "deterministic" if len(set(outputs)) == 1 else "nondeterministic"


def quarantine_fold(outputs: list[str]) -> Any:
    """Reference fold: a flagged nondeterministic scorer's scores are
    quarantined `unknown` — never a number, never averaged."""
    if classify_determinism(outputs) != "deterministic":
        return UNKNOWN
    return float(outputs[0])


def mutant_average_fold(outputs: list[str]) -> Any:
    """§12 sim-8 NEGATIVE CONTROL: nondeterminism silently averaged into the
    vector."""
    vals = [float(o) for o in outputs]
    return sum(vals) / len(vals)


# --------------------------------------------------------------------------
# the §4 ARMING battery — reference composition over the REAL shipped
# predicate (regression_gate.evaluate_gate) + the REAL injectable seam
# (gate.ratify(runner=, probe_fn=, root=<scratch>)); gate.py byte-untouched.
# This composition IS the executable spec of the future cog5-gate-arm.py.
# --------------------------------------------------------------------------
def reference_decision(res: "_rg.GateResult") -> tuple[str, Optional[str], bool]:
    """(admission, reason, proceed_to_ratify) — the §4.5 decision table.
    The three-valued outcome token itself is NEVER converted."""
    if res.outcome == _rg.OUTCOME_NO_VERDICT:
        return ADMISSION_REFUSED, REASON_NO_REGRESSION_EVIDENCE, False
    if res.outcome == _rg.OUTCOME_FAIL:
        if res.regressed:
            return ADMISSION_REFUSED, REASON_FROZEN_REGRESSION, False
        # the OTHER honest negative (§4.5 second arm): flat candidate —
        # carry the REAL predicate reason bytes; empty regressed/improved
        # keep it distinguishable from a regression fail.
        return ADMISSION_REFUSED, (res.reasons[0] if res.reasons else
                                   FLAT_REASON_FRAGMENT), False
    return ADMISSION_ELIGIBLE, None, True


def mutant_no_verdict_to_pass(res: "_rg.GateResult"):
    """§4.5 NEGATIVE CONTROL: no_verdict converted to admission."""
    if res.outcome == _rg.OUTCOME_NO_VERDICT:
        return ADMISSION_ELIGIBLE, None, False
    return reference_decision(res)


def mutant_no_verdict_to_fail(res: "_rg.GateResult"):
    """§4.5 NEGATIVE CONTROL: honest absence misrecorded as regression."""
    if res.outcome == _rg.OUTCOME_NO_VERDICT:
        return ADMISSION_REFUSED, REASON_FROZEN_REGRESSION, False
    return reference_decision(res)


def mutant_flat_to_pass(res: "_rg.GateResult"):
    """§4.5 NEGATIVE CONTROL: an all-green-but-flat candidate slips through."""
    if res.outcome == _rg.OUTCOME_FAIL and not res.regressed:
        return ADMISSION_ELIGIBLE, None, True
    return reference_decision(res)


def mutant_flat_to_error(res: "_rg.GateResult"):
    """§4.5 NEGATIVE CONTROL: the honest negative misrecorded as an
    evaluation failure (`no_verdict`)."""
    if res.outcome == _rg.OUTCOME_FAIL and not res.regressed:
        return ADMISSION_REFUSED, REASON_NO_REGRESSION_EVIDENCE, False
    return reference_decision(res)


# outcome-token rewrites some mutants smuggle into the pack:
_MUTANT_TOKEN_REWRITE = {
    mutant_no_verdict_to_fail: (_rg.OUTCOME_NO_VERDICT, _rg.OUTCOME_FAIL),
    mutant_flat_to_error: (_rg.OUTCOME_FAIL, _rg.OUTCOME_NO_VERDICT),
    mutant_no_verdict_to_pass: (_rg.OUTCOME_NO_VERDICT, _rg.OUTCOME_PASS),
}


def make_scratch_gate_root(tmp: Path) -> Path:
    """A scratch cabinet root for the REAL ratify: a minimal-but-real
    immutable-core.yml so load_ring0() sees Ring-0 (an unreadable enumeration
    refuses everything — gate.py law). All ratify writes land UNDER this
    root; the live tree is never touched."""
    root = tmp / "scratch-gate-root"
    pol = root / "framework" / "policies"
    pol.mkdir(parents=True, exist_ok=True)
    (pol / "immutable-core.yml").write_text(
        "files:\n"
        "  - path: framework/policies/immutable-core.yml\n"
        "dirs:\n"
        "  - path: framework/policies\n",
        encoding="utf-8")
    return root


FIXTURE_DIFF = (
    "diff --git a/docs/notes/cog5-fixture.txt b/docs/notes/cog5-fixture.txt\n"
    "--- a/docs/notes/cog5-fixture.txt\n"
    "+++ b/docs/notes/cog5-fixture.txt\n"
    "@@ -1 +1 @@\n"
    "-old fixture line\n"
    "+new fixture line\n"
)

RING0_DIFF = (
    "diff --git a/framework/policies/immutable-core.yml "
    "b/framework/policies/immutable-core.yml\n"
    "--- a/framework/policies/immutable-core.yml\n"
    "+++ b/framework/policies/immutable-core.yml\n"
    "@@ -1 +1 @@\n"
    "-files:\n"
    "+files: []\n"
)

_PROBE_CHILD_SRC = """\
import json, os, sys
out = {"env": dict(os.environ), "cwd": os.getcwd()}
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(out, fh)
print("probe-ok")
"""

CANARY_ENV = "COG5_T2_CANARY_SECRET"
# §4.4 is an ALLOWLIST law, so the escape arm cannot be a single named canary:
# a harness leaking some OTHER credential var would sail past a name check.
# Credential-SHAPED variable NAMES (never values — nothing here reads or
# records an env value) are refused as a class.
CREDENTIAL_ENV_RE = re.compile(r"TOKEN|KEY|SECRET|PASSWORD|ANTHROPIC|OAUTH",
                               re.IGNORECASE)
LEAK_ENV = "ANTHROPIC_OAUTH_TOKEN"     # a NON-canary credential-shaped name


def _run_probe_child(stage: str, workdir: Path, env: dict[str, str]) -> dict[str, Any]:
    """One REAL verify-stage execution (arg-list, no shell, explicit env):
    the child records its observed environment into the workdir so the
    escape asserts read evidence, not intent."""
    probe_file = workdir / f"probe-{stage}.json"
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE_CHILD_SRC, str(probe_file)],
        cwd=str(workdir), env=env, capture_output=True, text=True,
        timeout=60, check=False)
    ok = proc.returncode == 0 and "probe-ok" in proc.stdout
    return {"ok": ok,
            "detail": f"{stage}: probe child rc={proc.returncode}, "
                      f"evidence {probe_file.name}"}


def make_scrubbed_runner(workdir: Path) -> Callable[[str, dict], dict]:
    """The reference HARNESS runner for the ratify seam: explicit ALLOWLIST
    environment (§4.4 — an allowlist, not a denylist), arg-list no-shell,
    cwd pinned to the candidate workdir."""
    def runner(stage: str, spec: dict[str, Any]) -> dict[str, Any]:
        del spec  # the fixture harness runs its own probe per stage
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": "0"}
        return _run_probe_child(stage, workdir, env)
    return runner


def make_passthrough_mutant_runner(workdir: Path) -> Callable[[str, dict], dict]:
    """§12 escape NEGATIVE CONTROL (the §4.4 arm at the arming seam): the
    harness passes the LIVE environment through to candidate code."""
    def runner(stage: str, spec: dict[str, Any]) -> dict[str, Any]:
        del spec
        return _run_probe_child(stage, workdir, dict(os.environ))
    return runner


def make_partial_leak_mutant_runner(workdir: Path, leak_var: str = LEAK_ENV,
                                    ) -> Callable[[str, dict], dict]:
    """§12 escape NEGATIVE CONTROL (the §4.4 arm, PATTERN direction): a
    harness that scrubs the environment but leaks ONE credential-shaped var
    that is NOT the named canary. It defeats a single-name canary check and
    must still RED — the allowlist law is about the class, not one name."""
    def runner(stage: str, spec: dict[str, Any]) -> dict[str, Any]:
        del spec
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": "0",
               leak_var: "leaked-credential-fixture"}
        return _run_probe_child(stage, workdir, env)
    return runner


def make_outside_writer_mutant_runner(workdir: Path, outside: Path,
                                      ) -> Callable[[str, dict], dict]:
    """Escape NEGATIVE CONTROL: candidate-stage code writes OUTSIDE its
    arena workdir (the X5 outside-workdir-diff arm at fixture scale)."""
    def runner(stage: str, spec: dict[str, Any]) -> dict[str, Any]:
        del spec
        (outside / f"escaped-{stage}.txt").write_text("escape", encoding="utf-8")
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": "0"}
        return _run_probe_child(stage, workdir, env)
    return runner


def snapshot_tree(root: Path) -> frozenset[str]:
    if not root.exists():
        return frozenset()
    return frozenset(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def observed_env(workdir: Path, stage: str) -> dict[str, str]:
    data = json.loads((workdir / f"probe-{stage}.json").read_text(encoding="utf-8"))
    return dict(data["env"])


def reference_arming_composition(
        *, scratch_root: Path, corpus_dir: Path,
        baseline: Mapping[str, Any], candidate: Mapping[str, Any],
        proposal: Optional[dict[str, Any]] = None,
        runner: Optional[Callable[[str, dict], dict]] = None,
        probe_fn: Optional[Callable[[], dict]] = None,
        decision: Callable = reference_decision) -> dict[str, Any]:
    """The call-site composition the future cog5-gate-arm.py must implement
    (§4.3): the REAL regression predicate as a mandatory admission stage
    AROUND the REAL ratify seam. gate.py is consumed, never edited."""
    try:
        ids = _rg.corpus_case_ids(corpus_dir)
        res = _rg.evaluate_gate(ids, baseline, candidate)
    except _rg.CorpusError as exc:  # fail-safe: corpus trouble is no_verdict
        res = _rg.GateResult(outcome=_rg.OUTCOME_NO_VERDICT,
                             reasons=[f"gate error (no verdict): {exc!r}"])
    admission, reason, proceed = decision(res)
    pack: dict[str, Any] = {
        "regression": res.to_dict(),
        "admission": admission,
        "reason": reason,
        "ratify": None,
    }
    rewrite = _MUTANT_TOKEN_REWRITE.get(decision)
    if rewrite and pack["regression"]["outcome"] == rewrite[0]:
        pack["regression"]["outcome"] = rewrite[1]   # the mutant's smuggle
    if proceed:
        ratify_pack = _gate.ratify(
            dict(proposal or {"id": "cand-fixture", "diff": FIXTURE_DIFF}),
            root=scratch_root,
            runner=runner or (lambda s, spec: {"ok": True, "detail": f"{s} ok"}),
            probe_fn=probe_fn or (lambda: {"ok": True,
                                           "detail": "fixture ceiling probe"}),
            now="2026-07-24T00:00:00Z")
        pack["ratify"] = ratify_pack
        if ratify_pack.get("verdict") != "pass":
            pack["admission"] = ADMISSION_REFUSED
            pack["reason"] = f"ratify verdict {ratify_pack.get('verdict')!r}"
    return pack


# ---- arming assert batteries ---------------------------------------------
def assert_arm_no_verdict_refusal(pack: Mapping[str, Any]) -> None:
    assert pack["regression"]["outcome"] == _rg.OUTCOME_NO_VERDICT, (
        "[ARM-NOVERDICT] the empty-corpus outcome token must stay "
        "'no_verdict' — never spelled 'fail', never spelled 'pass' (§4.5)")
    assert pack["admission"] == ADMISSION_REFUSED and \
        pack["reason"] == REASON_NO_REGRESSION_EVIDENCE, (
        "[ARM-NOVERDICT] no_verdict must REFUSE admission with the recorded "
        "reason 'no_regression_evidence' (§4.5)")


def assert_arm_flat_honest_negative(pack: Mapping[str, Any]) -> None:
    reg = pack["regression"]
    assert reg["outcome"] == _rg.OUTCOME_FAIL, (
        "[ARM-FLAT] a flat candidate is an HONEST NEGATIVE ('fail'), never "
        "an error and never 'no_verdict' (§4.5 second arm)")
    assert reg["regressed"] == [] and reg["improved"] == [], (
        "[ARM-FLAT] the honest negative is distinguishable via EMPTY "
        "regressed/improved fields")
    assert pack["admission"] == ADMISSION_REFUSED and \
        FLAT_REASON_FRAGMENT in str(pack["reason"]), (
        "[ARM-FLAT] the flat candidate must NOT be admitted and must carry "
        "the predicate's own reason bytes")


def assert_arm_known_bad_refused(pack: Mapping[str, Any], *, case: str) -> None:
    assert pack["regression"]["outcome"] == _rg.OUTCOME_FAIL and \
        case in pack["regression"]["regressed"], (
        "[ARM-KNOWN-BAD] the regression stage must catch the seeded frozen "
        "regression (X2)")
    assert pack["admission"] == ADMISSION_REFUSED and \
        pack["reason"] == REASON_FROZEN_REGRESSION, (
        "[ARM-KNOWN-BAD] a known-bad candidate must FAIL the composition")


def assert_arm_honest_pass(pack: Mapping[str, Any]) -> None:
    assert pack["admission"] == ADMISSION_ELIGIBLE and \
        pack["regression"]["outcome"] == _rg.OUTCOME_PASS, (
        "[ARM-HONEST-PASS] the improving candidate must ratify end-to-end")
    ratify_pack = pack["ratify"]
    assert ratify_pack and ratify_pack.get("verdict") == "pass", (
        "[ARM-HONEST-PASS] ratify verdict must be 'pass'")
    stages = {s["stage"]: s for s in ratify_pack["stages"]}
    assert tuple(s["stage"] for s in ratify_pack["stages"]) == _gate.STAGES, (
        "[ARM-HONEST-PASS] every gate stage must be present, in order")
    for name in _gate.STAGES:
        st = stages[name]
        assert st["status"] != "skipped" and str(st["detail"]).strip(), (
            f"[ARM-HONEST-PASS] stage {name} must be non-vacuous (§4.2: "
            "'Honest' = no stage vacuous, asserted per-stage)")
    assert ratify_pack.get("applies_nothing") is True, (
        "[ARM-HONEST-PASS] ratify APPLIES NOTHING (§4.6) — the pack must say so")


def assert_arm_escape(workdir: Path, *, outside_before: frozenset[str],
                      outside_after: frozenset[str]) -> None:
    for stage in ("S1_verify", "S2_falsifier"):
        env = observed_env(workdir, stage)
        assert CANARY_ENV not in env, (
            f"[ARM-ESCAPE] candidate-stage code OBSERVED the live credential "
            f"canary in {stage} — the harness must pass an explicit ALLOWLIST "
            "environment (§4.4), never the live env")
        # the canary is one name; §4.4 is a CLASS law — any credential-shaped
        # NAME reaching candidate-stage code is the same escape (values are
        # never read or recorded, only names).
        leaked = sorted(n for n in env if CREDENTIAL_ENV_RE.search(n))
        assert not leaked, (
            f"[ARM-ESCAPE] candidate-stage code OBSERVED credential-shaped env "
            f"var(s) {leaked} in {stage} — the §4.4 allowlist admits no "
            "credential-class name, canary or otherwise")
        assert "PATH" in env, "[ARM-ESCAPE] the allowlist env lost PATH"
    assert outside_before == outside_after, (
        "[ARM-ESCAPE] the outside-workdir diff must be EMPTY after a "
        "candidate run (X5 at fixture scale)")


# --------------------------------------------------------------------------
# §6.2 provenance: ingester (chain-of-custody), counting predicate, mutants
# --------------------------------------------------------------------------
CUSTODY_SEAL_KEY = "custody_seal"
CUSTODY_FIELDS = ("source_class", "provenance", "stratum", "payload_ref")

# The INGESTER-PLANE key. §6.2 says candidate/league/generator code can never
# "set OR REWRITE" provenance; a stamp alone only covers SET, because nothing
# stops a later writer from editing the field it already owns. Sealing the
# custody fields under a key only the ingester holds makes a post-ingest
# rewrite DETECTABLE, so the rewrite direction is armed too.
# HONEST SCOPE: this models the plane boundary (§5.2 WALL) — it is not a
# cryptographic defence against code running in this same process, and it is
# not the physical guarantee. The physical counterpart is W2 T1's append-only
# archive chain (§5.2 prev_hash/sequence/sealed segments). No assertion in
# this family depends on the key's VALUE, so the suite stays deterministic.
_INGEST_KEY = os.urandom(32)


def _custody_seal(row: Mapping[str, Any], key: bytes) -> str:
    payload = json.dumps({f: row.get(f) for f in CUSTODY_FIELDS}, sort_keys=True)
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def custody_intact(row: Mapping[str, Any]) -> bool:
    """True iff the row still carries the seal the INGESTER bound over its
    custody fields — i.e. neither `provenance` nor `source_class` (nor the
    stratum/payload identity they were stamped for) changed after ingestion."""
    seal = row.get(CUSTODY_SEAL_KEY)
    if not isinstance(seal, str):
        return False
    return hmac.compare_digest(seal, _custody_seal(row, _INGEST_KEY))


def ingest_rows(raw_rows: list[Mapping[str, Any]],
                ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The reference archive INGESTER: provenance is stamped HERE from the
    named source class — never accepted from the row (the §5.2 WALL covers
    the field) — and the custody fields are SEALED under the ingester-plane
    key so a later rewrite is detectable. Returns (accepted, refused);
    refused rows never count."""
    accepted: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    for raw in raw_rows:
        row = dict(raw)
        if "provenance" in row:
            refused.append({**row, "refusal": "row-supplied provenance — "
                            "candidate/league/generator code can never set it"})
            continue
        source = row.get("source_class")
        if source not in SOURCE_CLASS_TO_PROVENANCE:
            refused.append({**row, "refusal": f"unknown source_class {source!r} "
                            "— missing/out-of-enum provenance refuses ingestion"})
            continue
        row["provenance"] = SOURCE_CLASS_TO_PROVENANCE[source]
        assert row["provenance"] in PROVENANCE_ENUM
        row[CUSTODY_SEAL_KEY] = _custody_seal(row, _INGEST_KEY)
        accepted.append(row)
    return accepted, refused


def mutant_rewrite_after_ingest(rows: list[Mapping[str, Any]], *,
                                as_source: str = "consequence_ledger",
                                ) -> list[dict[str, Any]]:
    """§6.2 NEGATIVE CONTROL (the REWRITE direction of the laundering
    vector): league/generator code reaches into ALREADY-INGESTED rows and
    rewrites BOTH `provenance` and `source_class` so every non-real row reads
    as real. Nothing is re-ingested, so the stale seal no longer verifies —
    which is exactly what makes the rewrite detectable rather than silent.
    It launders EVERY non-real row (not a subset) so the laundered corpus
    actually clears the §6.2 floor — a mutant that cannot reach the floor
    could never prove the opening predicate holds."""
    out: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        if row.get("provenance") not in REAL_PROVENANCE:
            row["source_class"] = as_source
            row["provenance"] = SOURCE_CLASS_TO_PROVENANCE[as_source]
        out.append(row)
    return out


def mutant_count_ignoring_custody(rows: list[Mapping[str, Any]],
                                  ) -> dict[str, dict[str, int]]:
    """§6.2 NEGATIVE CONTROL: a counter that reads the provenance FIELD and
    never checks the seal — so a post-ingest rewrite counts."""
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        stratum = str(row.get("stratum", "unstrated"))
        cell = out.setdefault(stratum, {"real_live": 0, "real_mined": 0,
                                        "counted": 0})
        if row.get("provenance") in REAL_PROVENANCE and \
                row.get("source_class") in NAMED_REAL_SOURCES:
            cell[row["provenance"]] += 1
            cell["counted"] += 1
    return out


def assert_custody_intact(rows: list[Mapping[str, Any]]) -> None:
    """[LC-CUSTODY] every corpus row must still carry the seal the ingester
    bound at ingestion. A broken/absent seal means `provenance` or
    `source_class` was set or REWRITTEN outside the ingester — §6.2's wall
    covers rewrite as well as set."""
    broken = sorted(str(r.get("payload_ref")) for r in rows
                    if not custody_intact(r))
    assert not broken, (
        f"[LC-CUSTODY] row(s) {broken} carry a broken/absent ingest seal — "
        "their provenance or source_class was set or REWRITTEN after "
        "ingestion; candidate/league/generator code can do NEITHER (§6.2)")


def mutant_ingest_trusting(raw_rows: list[Mapping[str, Any]],
                           ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """§6.2 NEGATIVE CONTROL (the laundering vector): an ingester that TRUSTS
    a row-supplied provenance stamp. Its ONLY defect is trust — it seals like
    the reference ingester, so the laundering cannot hide behind a missing
    seal; it surfaces where it really lives, at the counting predicate."""
    accepted: list[dict[str, Any]] = []
    for raw in raw_rows:
        row = dict(raw)
        row["provenance"] = row.get(
            "provenance",
            SOURCE_CLASS_TO_PROVENANCE.get(row.get("source_class"), "synthetic"))
        row[CUSTODY_SEAL_KEY] = _custody_seal(row, _INGEST_KEY)
        accepted.append(row)
    return accepted, []


def count_toward_minimums(rows: list[Mapping[str, Any]],
                          ) -> dict[str, dict[str, int]]:
    """The §6.2 counting predicate: ONLY real_live/real_mined rows ingested
    from the NAMED real sources — WITH AN INTACT INGEST SEAL — count.
    Per-stratum {real_live, real_mined, counted}; synthetic/sim_replay never
    appear in `counted`, and neither does a row whose custody fields were
    rewritten after ingestion."""
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        stratum = str(row.get("stratum", "unstrated"))
        cell = out.setdefault(stratum, {"real_live": 0, "real_mined": 0,
                                        "counted": 0})
        if custody_intact(row) and row.get("provenance") in REAL_PROVENANCE and \
                row.get("source_class") in NAMED_REAL_SOURCES:
            cell[row["provenance"]] += 1
            cell["counted"] += 1
    return out


def mutant_count_all(rows: list[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """§6.2 NEGATIVE CONTROL: a counter that lets synthetic/sim_replay rows
    count toward the minimums (provenance laundering)."""
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        stratum = str(row.get("stratum", "unstrated"))
        cell = out.setdefault(stratum, {"real_live": 0, "real_mined": 0,
                                        "counted": 0})
        prov = row.get("provenance")
        if prov in ("real_live", "real_mined"):
            cell[prov] += 1
        cell["counted"] += 1
    return out


def assert_count_honest(counts: Mapping[str, Mapping[str, int]],
                        rows: list[Mapping[str, Any]]) -> None:
    """[LC-LAUNDER] `counted` must equal the real_live+real_mined sum from
    named real sources WITH INTACT CUSTODY — a synthetic-marked row reaching
    the count REDs, and so does a row whose provenance was rewritten after
    ingestion (the recomputation refuses a broken seal, so a mutated row can
    no longer make the battery agree with itself)."""
    for stratum, cell in counts.items():
        real = sum(1 for r in rows
                   if str(r.get("stratum", "unstrated")) == stratum
                   and custody_intact(r)
                   and r.get("provenance") in REAL_PROVENANCE
                   and r.get("source_class") in NAMED_REAL_SOURCES)
        assert cell["counted"] == real == cell["real_live"] + cell["real_mined"], (
            f"[LC-LAUNDER] stratum {stratum!r}: counted={cell['counted']} but "
            f"only {real} rows are real_live/real_mined from NAMED real "
            "sources with intact custody — synthetic (or rewritten) rows may "
            "never count toward a §6.2 minimum")


# --------------------------------------------------------------------------
# §6.3 league closure: record validator + open predicate + league rows
# --------------------------------------------------------------------------
EXPECTED_MINIMUMS = {
    "real_trajectory_floor": REAL_TRAJECTORY_FLOOR,
    "captain_label_floor": CAPTAIN_LABEL_FLOOR,
    "judge_agreement_bar": JUDGE_AGREEMENT_BAR,
    "judge_min_pairs": JUDGE_MIN_PAIRS,
    "baseline_match_rate": BASELINE_MATCH_RATE,
}
OPEN_CONDITIONS = ("per_stratum_floors_met", "judge_calibration_green",
                   "holdout_freeze_landed", "captain_informed")
HOLDOUT_FREEZE_INTERIM = "pending-captain-window"   # §7.5.5 verbatim posture


def good_arming_record(actuals: Optional[Mapping[str, Mapping[str, int]]] = None,
                       ) -> dict[str, Any]:
    return {
        "league_open": False,
        "minimums": dict(EXPECTED_MINIMUMS),
        "open_conditions": {c: False for c in OPEN_CONDITIONS},
        "holdout_freeze": HOLDOUT_FREEZE_INTERIM,
        "actuals": {k: dict(v) for k, v in (actuals or {}).items()},
    }


def validate_arming_record(record: Mapping[str, Any],
                           rows: Optional[list[Mapping[str, Any]]] = None,
                           ) -> list[str]:
    """The §6.3 closure validator (violations list; [] = valid). When `rows`
    is given, the recorded actuals are RECOMPUTED via the §6.2 counting
    predicate — a laundered actuals block is caught at the record too."""
    v: list[str] = []
    if record.get("league_open") is not False:
        conds = record.get("open_conditions") or {}
        if not (record.get("league_open") is True
                and all(conds.get(c) is True for c in OPEN_CONDITIONS)
                and record.get("holdout_freeze") == "landed"):
            v.append("[LC-OPEN] league_open must be false while any §6.3 open "
                     "condition is unmet (opening is a post-phase amendment "
                     "event, never a code-existence event)")
    if record.get("minimums") != EXPECTED_MINIMUMS:
        v.append("[LC-MINIMUMS] the recorded minimums must be the §6.2 "
                 "derivation verbatim")
    if "holdout_freeze" not in record:
        v.append("[LC-FREEZE] the holdout_freeze line is required (§7.5.5)")
    if rows is not None:
        recomputed = count_toward_minimums(list(rows))
        recorded = record.get("actuals") or {}
        for stratum, cell in recorded.items():
            honest = recomputed.get(stratum, {"real_live": 0, "real_mined": 0,
                                              "counted": 0})
            if {k: cell.get(k) for k in ("real_live", "real_mined", "counted")} \
                    != honest:
                v.append(f"[LC-LAUNDER] actuals for stratum {stratum!r} do not "
                         "match the §6.2 counting predicate over the corpus")
    return v


def league_may_open(record: Mapping[str, Any],
                    rows: list[Mapping[str, Any]]) -> bool:
    """Reference open predicate: every stratum present in the corpus must
    meet the real-trajectory floor BY THE COUNTING PREDICATE (synthetic can
    never open the league — §8.1) and every §6.3 condition must hold."""
    counts = count_toward_minimums(rows)
    floors = record.get("minimums", EXPECTED_MINIMUMS)
    per_stratum = counts and all(
        cell["counted"] >= floors["real_trajectory_floor"]
        for cell in counts.values())
    conds = record.get("open_conditions") or {}
    return bool(per_stratum
                and all(conds.get(c) is True for c in OPEN_CONDITIONS)
                and record.get("holdout_freeze") == "landed")


def mutant_open_on_total_rows(record: Mapping[str, Any],
                              rows: list[Mapping[str, Any]]) -> bool:
    """§6.2/§8.1 NEGATIVE CONTROL: an opener keyed on TOTAL row count —
    synthetic volume opens the league."""
    floors = record.get("minimums", EXPECTED_MINIMUMS)
    return len(rows) >= floors["real_trajectory_floor"]


def make_league_row(candidate_id: str, *, scored: float, ranked: int,
                    ) -> dict[str, Any]:
    """A reference league output row while CLOSED: machine-class speech
    (scored/ranked/observed), the schema-required fitness_claim none, no
    review.source, certainty capped at P5."""
    return {
        "candidate": candidate_id,
        "scored": scored,
        "ranked": ranked,
        "observed": {"cases": 20},
        "fitness_claim": "none",
        "certainty": P5_CAP,
    }


def mutant_league_row_fitness(candidate_id: str, **kw: Any) -> dict[str, Any]:
    """§6.3 NEGATIVE CONTROL: a closed-league row claiming live fitness."""
    row = make_league_row(candidate_id, **kw)
    row["fitness_claim"] = "live_fitness"
    return row


def mutant_league_row_verdict_human(candidate_id: str, **kw: Any) -> dict[str, Any]:
    """§9.3 SIM-2 extension NEGATIVE CONTROL: a foundry code path minting
    review.source verdict_human."""
    row = make_league_row(candidate_id, **kw)
    row["review"] = {"verdict": "confirmed", "source": HUMAN_VERDICT_SOURCE}
    return row


def mutant_league_row_above_cap(candidate_id: str,
                                state_name: str = "STATE_INTERVENTION_SUPPORTED",
                                **kw: Any) -> dict[str, Any]:
    """§9.3 NEGATIVE CONTROL (the P5 cap arm): a league row claiming an
    ABOVE-cap certainty. The default is the real states.py P3 token
    `intervention_supported` — whose Captain word is literally 'tested' —
    chosen because it slips past the Captain-vocabulary regex entirely: the
    cap needs its own binding to the ladder, not a word scan."""
    row = make_league_row(candidate_id, **kw)
    row["certainty"] = estate_constant(STATES_REL, state_name)
    return row


def mutant_league_row_captain_vocab_keys(candidate_id: str,
                                         **kw: Any) -> dict[str, Any]:
    """§9.3 NEGATIVE CONTROL (the KEY arm): a foundry artifact minting the
    Captain vocabulary as FIELD NAMES rather than values — invisible to a
    values-only scan while saying the forbidden word just as loudly."""
    row = make_league_row(candidate_id, **kw)
    row["tested"] = True
    row["falsified"] = False
    return row


def assert_league_row_closed_shape(row: Mapping[str, Any]) -> None:
    assert row.get("fitness_claim") == "none", (
        "[LC-FITNESS] every league output while closed carries "
        "fitness_claim 'none' structurally (schema-required — §6.3)")
    review = row.get("review") or {}
    assert review.get("source") != HUMAN_VERDICT_SOURCE, (
        "[SIM2X-VH] a foundry artifact minting review.source "
        "verdict_human REDs (§9.3 — the league can never speak as the human "
        "channel)")
    # the cap rides the closed-shape battery so every row-validating caller
    # gets it (it was previously only an inline assert against the reference
    # row-maker, which sets the value itself — near-tautological).
    assert_certainty_capped(row)


# ---- §9.2/§9.3 promotion joint + vocabulary ------------------------------
MACHINE_CLASS_MARKERS = frozenset({"fitness_claim", "league_score"})


def is_machine_class_artifact(item: Any) -> bool:
    """Structural machine-class identification (§9.3): a foundry/league
    artifact is recognisable by its own schema — the closed-league
    `fitness_claim` field, the machine-class speech keys
    (scored/ranked/observed), or a declared league_score kind."""
    if not isinstance(item, Mapping):
        return False
    keys = set(item)
    return bool(keys & MACHINE_CLASS_MARKERS) or bool(keys & MACHINE_SPEAK) \
        or item.get("kind") in MACHINE_CLASS_MARKERS


def reference_edge_promotion(evidence: list[Mapping[str, Any]]) -> bool:
    """The reference mission-edge promotion predicate (§9.2): promotes ONLY
    on a human verdict; machine/league/judge artifacts may demote or
    withhold, never promote.

    CLASS BEFORE CONTENT: a machine-class artifact is skipped BEFORE its
    `review` is read. Trusting any dict that merely carries
    `review.source: verdict_human` means a forged league row — the very
    artifact the §9.3 minting battery REDs on — walks straight into the
    promotion joint, because the two laws were never composed. The forgery
    must fail at the joint too, not only in a battery nobody calls."""
    for item in evidence:
        if is_machine_class_artifact(item):
            continue        # may demote/withhold; NEVER promote (§9.2/§9.3)
        review = item.get("review", {})
        if review.get("verdict") == "confirmed" and \
                review.get("source") == HUMAN_VERDICT_SOURCE:
            return True
    return False


def mutant_promotes_on_league_score(evidence: list[Mapping[str, Any]]) -> bool:
    """§9.3 SIM-2 extension NEGATIVE CONTROL: an edge predicate consuming a
    league score as promotion fuel."""
    if reference_edge_promotion(evidence):
        return True
    return any(e.get("kind") == "league_score"
               and isinstance(e.get("value"), (int, float))
               and e["value"] >= 0.9
               for e in evidence)


def mutant_promotes_on_forged_league_review(evidence: list[Mapping[str, Any]],
                                            ) -> bool:
    """§9.3 SIM-2 extension NEGATIVE CONTROL (the FORGERY arm): the
    class-blind promotion predicate — it reads `review.source` off ANY dict,
    so a league row that minted `verdict_human` promotes a mission edge. This
    was the reference predicate's own shape before the class check; keeping
    it as a named mutant pins the escape it used to allow."""
    return any(
        e.get("review", {}).get("verdict") == "confirmed"
        and e.get("review", {}).get("source") == HUMAN_VERDICT_SOURCE
        for e in evidence)


def assert_no_promotion_without_human(promoted: bool) -> None:
    assert promoted is False, (
        "[SIM2X-LEAGUE-FUEL] no edge/graduation predicate may consume a "
        "league/judge score as promotion fuel — only verdict_human promotes "
        "(§9.2, the composite certainty law)")


def assert_machine_class_never_promotes(evidence: list[Mapping[str, Any]],
                                        promoted: bool) -> None:
    """[SIM2X-FORGED-VH] the COMPOSED law (the two §9.3 SIM-2 arms run
    together, which is the point — separately they leave a forged league row
    minting `verdict_human` promoting a mission edge while the minting
    battery sits uncalled): every league ROW in the evidence must survive the
    closed-shape battery, AND the joint must not have promoted (bare
    `{kind: league_score}` refs are evidence pointers, not rows — they are
    machine-class for the joint, but carry no row schema to validate)."""
    for item in evidence:
        if isinstance(item, Mapping) and (
                "fitness_claim" in item or (set(item) & MACHINE_SPEAK)):
            assert_league_row_closed_shape(item)
    assert promoted is False, (
        "[SIM2X-FORGED-VH] a machine-class artifact fuelled a promotion — "
        "league/benchmark/holdout artifacts may demote or withhold, never "
        "promote, no matter what `review` they carry (§9.2/§9.3)")


def vocab_violations(artifact: Any) -> list[str]:
    """The §9.3 tripwire clone: walk a foundry artifact; every string
    carrying the Captain vocabulary (tested / falsified / 'it worked') is a
    violation — machine artifacts speak scored/ranked/observed.

    KEYS COUNT AS SPEECH: a scan of string VALUES only is blind to a row that
    mints the Captain vocabulary as FIELD NAMES (`{"tested": true,
    "falsified": false}`) — the artifact says the forbidden word just as
    loudly, and the tripwire stayed green. Keys and values are both walked."""
    found: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, str):
            if _CAPTAIN_VOCAB_RE.search(node):
                found.append(f"{path}: {node!r}")
        elif isinstance(node, Mapping):
            for k, val in node.items():
                if isinstance(k, str) and _CAPTAIN_VOCAB_RE.search(k):
                    found.append(f"{path}.<key>: {k!r}")
                walk(val, f"{path}.{k}")
        elif isinstance(node, (list, tuple)):
            for i, val in enumerate(node):
                walk(val, f"{path}[{i}]")
    walk(artifact, "$")
    return found


def assert_machine_class_vocab(artifact: Any) -> None:
    bad = vocab_violations(artifact)
    assert not bad, (
        "[VOCAB] league/benchmark/holdout artifacts are MACHINE-CLASS: they "
        "speak scored/ranked/observed and cap at P5 — never the Captain "
        f"vocabulary (§9.3), in a value OR a key. Violations: {bad}")


def assert_certainty_capped(row: Mapping[str, Any], *,
                            source: Optional[str] = None) -> None:
    """[P5-CAP] a machine-class artifact's `certainty` must sit at or below
    the states.py P5 rung. The admissible set is DERIVED FROM BYTES
    (estate_certainty_ladder) — the states above the cap are precisely those
    `derive_edge_state` can reach only through human-verdict fuel, so a
    machine artifact carrying one has minted a human-channel claim. The
    Captain-vocabulary regex does NOT catch this: `intervention_supported` is
    a real states.py token whose Captain word is 'tested', and it contains
    none of the banned words. Missing/unknown tokens fail closed.

    `source` overrides the states.py bytes — the same injection seam
    estate_certainty_ladder carries, so the [P5-LADDER] integrity guards below
    can be ARMED against a genuinely broken states.py rather than asserted by
    hand. Defaults to the real bytes; no caller passes it except the mutant
    arms."""
    # NOTE the DISTINCT tag: the ladder-integrity failures below must never be
    # mistakable for a cap violation, or a mutant test matching [P5-CAP] would
    # go green on a broken scan (paid in the fix round's own mutation proof).
    ladder = estate_certainty_ladder(source)
    assert ladder["above_cap"], (
        "[P5-LADDER] the ladder derivation found NO above-cap states — the "
        "scan went vacuous against states.py and would pass anything")
    assert ladder["cap"] == P5_CAP and P5_CAP in ladder["machine_reachable"], (
        f"[P5-LADDER] the P5 cap token drifted: states.py derives "
        f"{ladder['cap']!r} (machine-reachable: "
        f"{sorted(ladder['machine_reachable'])})")
    token = row.get("certainty")
    assert token in ladder["all_states"], (
        f"[P5-CAP] certainty {token!r} is not a states.py internal state — a "
        "machine-class row states its certainty in the estate's own closed "
        "vocabulary or not at all (fail closed; §9.3/§5.2 'no second drifting "
        f"enum'). Known: {sorted(ladder['all_states'])}")
    assert token not in ladder["above_cap"], (
        f"[P5-CAP] certainty {token!r} is ABOVE the P5 cap — states.py reaches "
        "it ONLY through human-verdict fuel, so a league/benchmark/holdout "
        "artifact claiming it is the machine speaking as the human channel. "
        f"Machine artifacts cap at {P5_CAP!r} (§9.3)")


# --------------------------------------------------------------------------
# vacuity machinery: absence + armed import probes (cwd-neutral — the COG-4
# inherited-cwd lesson is applied: children run from a NEUTRAL cwd with the
# target repo injected on sys.path, so landing surfaces flip the probe)
# --------------------------------------------------------------------------
def import_probe(module: str, repo_root: Path, neutral_cwd: Path,
                 ) -> tuple[int, str]:
    code = (f"import sys; sys.path.insert(0, {str(repo_root)!r}); "
            f"import {module}")
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(neutral_cwd),
        env={"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": "0"},
        capture_output=True, text=True, timeout=120, check=False)
    return proc.returncode, proc.stderr


def plant_evolution_module(tree: Path, leaf: str) -> None:
    """Scratch-tree planting for the probe-flip fixture proof."""
    pkg = tree / "framework" / "evolution"
    pkg.mkdir(parents=True, exist_ok=True)
    (tree / "framework" / "__init__.py").touch()
    (pkg / "__init__.py").touch()
    (pkg / f"{leaf}.py").write_text("SURFACE = 'fixture'\n", encoding="utf-8")
