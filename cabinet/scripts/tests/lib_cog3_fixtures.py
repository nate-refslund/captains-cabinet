"""COG-3 shared fixture library (tests-first, contract rev 1 — Phase-3
Objectives). The ONE seeding surface every COG-3 suite reuses.

DISCIPLINE (contract §7.2 + this wave's brief):
  * FILE-SEEDED, NO DSN, NO postgres. Belief stores fold from proto-beliefs;
    consequence evidence is seeded to real `consequence-events-*.jsonl` day
    files behind `_safe_ledger_files`/`iter_ledger_rows` — the D1 idiom in
    `test_cog2_asof_fence.py::TestD1ConsequenceCabinetStamp`, reused verbatim.
  * SEED INPUTS, RUN THE REAL ENGINE — this library never fabricates a served
    view by hand: it seeds proto-beliefs / ledger rows, folds them through the
    real `framework.cortex.engine.fold`, and serves them through the real
    `framework.cortex.query.as_of`. The BeliefViews the suites assert over are
    produced by the substrate, not by this file.
  * IMPORT-INERT re: the phase under test. This module imports ONLY the cortex
    query surface + the consequence ledger reader — it NEVER imports
    `framework.objectives` (which does not exist yet); only the test files do,
    inside a test body, so the honest failure signature is the absence of the
    implementation and this library imports clean today.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; Fable-5 two-tier law (test-authoring).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])                     # repo root (tests/ is a package)
for _p in (str(_HERE), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The ONLY substrate imports — the sanctioned cortex query surface + the
# consequence ledger reader (§3 disposition table). NEVER framework.objectives.
from framework.cortex import adapters, belief, engine, query  # noqa: E402
from framework.fidelity import consequence                    # noqa: E402

# ===========================================================================
# Canonical constants (one build cutoff per graph — §5.1(2))
# ===========================================================================

LOCAL_CABINET = "main"
SCOPE = {"cabinet_id": LOCAL_CABINET}

# One canonical build cutoff; every seeded evidence datum sits strictly before
# it (so the fence includes it, never the boundary-open case). Canonical
# "…Z" spelling — a non-canonical cutoff hard-errors (query.py:_CANON_TS_RE).
CUTOFF = "2026-07-21T00:00:00Z"
EVIDENCE_TS = "2026-07-20T08:00:00Z"

# The outcome dimension a fixture edge claims to move (adapter-pinned in prod;
# fixed here so observation evidence is "about" the edge's dimension).
DIMENSION = "cost"

# Producers. The consequence producer is the real one (§3); observation
# producers are fixture-local. A/B differ so a two-producer seed on ONE
# (subject_key, dimension) cross-links into a real conflict_set (engine.py
# contradiction post-pass — the P1 "contested" seam).
CONSEQUENCE_PRODUCER = "framework/fidelity/consequence"
OBS_PRODUCER_A = "cortex/observation-a"
OBS_PRODUCER_B = "cortex/observation-b"
_CONSEQUENCE_RANK = engine.RANK_TABLE["consequence"]     # 1 — the verified-join stream
_OBS_RANK = engine.RANK_TABLE["envelope_file"]           # 2 — NOT the consequence stream

# One trust table covering every producer any COG-3 seed uses (ppm confidence).
TRUST_TABLE = {
    "table_version": 1,
    "producers": {
        CONSEQUENCE_PRODUCER: 850000,
        OBS_PRODUCER_A: 800000,
        OBS_PRODUCER_B: 700000,
    },
}

# ---------------------------------------------------------------------------
# Derived-state vocabulary (§5.2 / §6.3) — the internal states the ordered
# total transition function yields, plus the answer-level fifth, plus the
# bijective Captain vocabulary (§5.2 "Captain vocabulary … maps bijectively").
# These name the EXPECTED outputs; the implementation must use these tokens.
# ---------------------------------------------------------------------------

STATE_HYPOTHESIZED = "hypothesized"                       # P1 / P4 / P6
STATE_FALSIFIED = "falsified"                             # P2
STATE_INTERVENTION_SUPPORTED = "intervention_supported"  # P3
STATE_OBSERVATIONALLY_SUPPORTED = "observationally_supported"  # P5
STATE_UNKNOWN = "unknown"                                 # answer-level (never stored)

FLAG_CONTESTED = "contested"                     # P1
FLAG_DIRECTION_CONTESTED = "direction_contested"  # P4

# §5.2: bijective internal → Captain vocabulary.
CAPTAIN_VOCAB = {
    STATE_UNKNOWN: "unknown",
    STATE_HYPOTHESIZED: "hypothesized",
    STATE_OBSERVATIONALLY_SUPPORTED: "observed",
    STATE_INTERVENTION_SUPPORTED: "tested",
    STATE_FALSIFIED: "refuted",
}


# ===========================================================================
# (b) Consequence evidence — file-seeded via the D1 path (§6.1)
# ===========================================================================

def consequence_row(action, subject, *, verdict=None, source=None,
                    actor_kind="officer", actor_id="cos", ts=EVIDENCE_TS):
    """A raw consequence-ledger row (the shape `iter_ledger_rows` yields). When
    `verdict` is given, a `review` sub-object rides along in the claim — THE
    §5.2 evaluation surface (`BeliefView.value` carries the full row). `source`
    omitted => an absent-source review (fail-closed-inert for promotion, §5.2
    human-confirm). `source` values are the consequence domain's own vocabulary
    (`consequence.py:126` `_REVIEW_SOURCES`)."""
    row = {"ts": ts, "actor": {"kind": actor_kind, "id": actor_id},
           "lane": "acting", "action": action, "subject": subject, "refs": []}
    if verdict is not None:
        review = {"verdict": verdict}
        if source is not None:
            review["source"] = source
        row["review"] = review
    return row


def consequence_subject_key(row):
    """'consequence/' + recorder digest of the ledger's OWN ts-inclusive
    identity tuple (`consequence._identity` = (actor 'kind:id', action, subject,
    ts)) — the subject_key the adapter derives. The verified-join limb-(i)
    check recomputes THIS from the served claim bytes (§5.2b)."""
    return "consequence/" + belief.digest(list(consequence._identity(row)))


def consequence_join_key(row):
    """The (actor 'kind:id', action, subject) triple an intervention node's
    `join_spec` must contain for verified-join limb-(ii) to hold (§4.1/§5.2b).
    Actor is flattened 'kind:id' exactly as `consequence._identity` does."""
    actor = row["actor"]
    return (f"{actor['kind']}:{actor['id']}", row["action"], row["subject"])


def seed_consequence_ledger(log_dir, rows, *, date="2026-07-20"):
    """Append rows to a real `consequence-events-<date>.jsonl` day file inside
    `log_dir` — the file set `_safe_ledger_files`/`iter_ledger_rows` consume.
    `log_dir` must already be on CABINET_EVENT_LOG_DIR (the operator-set env the
    reader honors) so `consequence_protos()` reads exactly these rows."""
    path = Path(log_dir) / f"consequence-events-{date}.jsonl"
    with open(path, "a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    return path


def consequence_protos(local_cabinet_id=LOCAL_CABINET):
    """Read the env-configured consequence ledger through its OWN history-
    preserving reader and D1-stamp the local cabinet_id (the ONLY way a
    `consequence/<digest>` subject survives the scope filter — §6.1). This is
    `read_consequence_protos`, i.e. the exact production fold-prepare path."""
    return adapters.read_consequence_protos(local_cabinet_id=local_cabinet_id)


# ===========================================================================
# (a) Cortex belief store — file-seeded proto-beliefs, real fold
# ===========================================================================

def observation_proto(subject_key, dimension, *, producer=OBS_PRODUCER_A,
                      claim=None, seq=0, ts=EVIDENCE_TS, purged=False,
                      stream_rank=_OBS_RANK, event_suffix=""):
    """One proto-belief (kind observation) with a controllable subject / kind /
    producer / claim / cutoff / purge marker. `purged=True` seeds the input the
    fold turns into a `source_purged` view (admissible() excludes it — §5.2).
    A distinct (producer, event_suffix) yields a distinct belief_id so multiple
    protos never collide."""
    provenance = {
        "event_id": belief.digest(
            f"{producer}|{subject_key}|{dimension}|{seq}|{event_suffix}"),
        "producer": producer,
        "stream_rank": stream_rank,
        "intra_stream_seq": seq,
        "cabinet_id": LOCAL_CABINET,             # D1-shaped local scope stamp
    }
    proto = {
        "kind": "observation",
        "subject_key": subject_key,
        "dimension": dimension,
        "adapter_ordinal": 0,
        "claim": claim,
        "source_time": ts,
        "observation_time": ts,
        "provenance": provenance,
        "claim_completeness": "inline",
    }
    if purged:
        proto["purged"] = True
    return proto


def observed_effect_claim(effect):
    """An observation claim carrying the adapter-pinned movement reading on the
    edge's dimension (§5.2 direction predicates). `effect` ∈
    {increase, decrease, maintain}."""
    return {"observed_effect": effect}


def conflict_protos(subject_key, dimension, *, effect_a="increase",
                    effect_b="decrease"):
    """TWO independent-producer protos on ONE (subject_key, dimension) — the
    engine's contradiction post-pass cross-links them into a non-empty
    conflict_set on each served view (the P1 "contested" seam, query.py
    :269-286). Verified in this library's self-checks."""
    return [
        observation_proto(subject_key, dimension, producer=OBS_PRODUCER_A,
                          claim=observed_effect_claim(effect_a), seq=0,
                          event_suffix="cflA"),
        observation_proto(subject_key, dimension, producer=OBS_PRODUCER_B,
                          claim=observed_effect_claim(effect_b), seq=1,
                          event_suffix="cflB"),
    ]


def fold_beliefs(protos):
    """Fold proto-beliefs through the REAL engine (dedupe → supersession →
    contradiction → status → confidence). Returns beliefs sorted by id."""
    return engine.fold(protos, trust_table=TRUST_TABLE)


def serve(beliefs, subject_key, *, dimension=None, cutoff=CUTOFF):
    """Serve one subject through the REAL as_of query at the canonical cutoff,
    in-scope. Returns the full AsOfResult (views + evidence closure + status)."""
    return query.as_of(beliefs, subject_key, scope=SCOPE, dimension=dimension,
                       observation=cutoff)


def views_for(beliefs, subject_key, *, dimension=None, cutoff=CUTOFF):
    """The served BeliefViews (the re-derived heads) for one subject."""
    return serve(beliefs, subject_key, dimension=dimension, cutoff=cutoff).views


# ===========================================================================
# (c) Captain-direction root files (minimal now — roots-adapter era; §7.6)
# ===========================================================================

def write_roots_yml(dir_path, entries, *, name="directions.yml"):
    """Write a Captain-direction root file to a tmp path (`roots_path` the CLI
    injects — §7.6; framework code carries NO instance literal). `entries` is a
    list of {slug, statement}. MINIMAL by design: the roots adapter does not
    exist yet, so the schema is provisional — extended when the adapter lands.
    Kept as plain text (no yaml dependency) to stay import-inert."""
    lines = ["# fixture Captain-direction roots (COG-3, provisional shape)",
             "directions:"]
    for entry in entries:
        lines.append(f"  - slug: {entry['slug']}")
        lines.append(f"    statement: {json.dumps(entry.get('statement', ''), ensure_ascii=False)}")
    path = Path(dir_path) / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ===========================================================================
# (d) Graph-input assembly — what FUTURE suites hand to build_graph
# ===========================================================================

@dataclass(frozen=True)
class GraphInputs:
    """The declared, recorded parameter set of the pure build (§5.3:
    `build_graph(roots_path, cache_dir, scope, cutoff)` — every parameter
    declared, none read from the environment, A-M6)."""
    roots_path: Path
    cache_dir: Path
    scope: dict
    cutoff: Optional[str]


def persist_cortex_store(cache_dir, beliefs):
    """Write beliefs.jsonl + fold-manifest.json under cache_dir so the ONE
    cortex read path — `load_beliefs_verified(cache_dir)` (§5.1) — can serve the
    seeded store with its C-F15 store-hash binding intact. Consequence/
    observation-only store => frontier/max_id absent (outbox-free)."""
    manifest = engine.build_manifest(list(beliefs), trust_table=TRUST_TABLE,
                                     frontier=None, max_id=None)
    return engine.write_projection(list(beliefs), manifest, Path(cache_dir))


def graph_inputs(roots_path, cache_dir, *, scope=None, cutoff=CUTOFF):
    """Assemble the declared build-input tuple future suites hand to
    build_graph. `cache_dir` is where `persist_cortex_store` wrote the store."""
    return GraphInputs(Path(roots_path), Path(cache_dir),
                       dict(scope if scope is not None else SCOPE), cutoff)


# ===========================================================================
# (e) The step-3 expected-verdict TABLE type + the edge input shape
# ===========================================================================
#
# PINNED API (THE surface the implementation must provide — §5/§8):
#
#   framework.objectives.states.derive_edge_state(edge, bound_views, cutoff)
#       -> EdgeState(state: str, flags: frozenset[str])
#       raises states.BuildFailure on a structural binding violation
#              (out-of-admissible-subjects | dangling binding — §4.2/§5.1(3)).
#
#   `edge` exposes exactly the attributes of `EdgeSpec` below; `bound_views` is
#   the tuple of real `query.BeliefView`s the edge's bindings resolved to;
#   `cutoff` is the canonical build cutoff. This is the NARROWEST plausible
#   surface for the §5.2 ordered total function; see the wave report for the
#   layering note (whether the admissibility/closure guards live in
#   derive_edge_state or in build_graph — the test pins the OBSERVABLE contract:
#   a structured build-failure for those two cells).

@dataclass(frozen=True)
class BindingRef:
    """One authored evidence binding ref (§4.2 `evidence_bindings`), narrowed to
    the two fields the ordered function + its structural guards read."""
    subject_key: str
    belief_id: str


@dataclass(frozen=True)
class EdgeSpec:
    """The minimal causal-edge shape `derive_edge_state` consumes. THE input
    contract the implementation's edge record must satisfy (expose these
    attributes). `assumptions` non-empty is P3's third gate; `join_spec` is the
    verified-join limb-(ii) matcher set; `admissible_subjects` bounds the
    citable subjects; `evidence_bindings` are the authored refs (so a dangling
    ref — a belief_id absent from `bound_views` — is detectable)."""
    authored: bool
    expected_effect: str                     # increase | decrease | maintain
    assumptions: tuple                        # non-empty => P3 eligible
    admissible_subjects: frozenset
    join_spec: tuple                          # ((actor_key, action, subject), …)
    evidence_bindings: tuple                  # (BindingRef, …)


@dataclass(frozen=True)
class ExpectedOutcome:
    """The pinned expected outcome of one step-3 cell."""
    kind: str                                 # "state" | "build_failure"
    state: Optional[str] = None
    flags: frozenset = field(default_factory=frozenset)


def expect_state(state, *flags):
    return ExpectedOutcome("state", state=state, flags=frozenset(flags))


def expect_build_failure():
    return ExpectedOutcome("build_failure")


# ---------------------------------------------------------------------------
# Declarative cell seed-spec + the materializer (seeds → real engine → inputs)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BindingSpec:
    """One declarative binding in a step-3 cell. `role` selects the seam:
      * "verdict"     — a consequence belief carrying review.{verdict,source};
                        feeds the verified-join / verdict axis (§5.2b).
      * "observation" — a cortex observation carrying `observed_effect`; feeds
                        the direction axis (§5.2 direction predicates). Set
                        `contested=True` to seed a two-producer conflict_set.
      * "purged"      — a source_purged observation (admissible() excludes it).
    Anomaly knobs: `join` ("match"|"mismatch") controls verified-join limb-(ii);
    `admissible=False` drops the subject from admissible_subjects (build fail);
    `resolve=False` makes the ref dangling — no served view (build fail)."""
    role: str
    verdict: Optional[str] = None             # confirmed | wrong
    source: Optional[str] = None              # verdict_human|verdict_judge|verdict_gate|system|None
    observed_effect: Optional[str] = None     # increase | decrease | maintain
    join: str = "match"                       # match | mismatch
    contested: bool = False
    admissible: bool = True
    resolve: bool = True
    tag: str = ""


@dataclass(frozen=True)
class EdgeCell:
    """A declarative step-3 cell: an edge + its bindings. `assumptions` is a
    bool here (materialized to a non-empty tuple when True — assumptions are
    declaration-only, §4.2)."""
    expected_effect: str = "increase"
    assumptions: bool = False
    authored: bool = True
    bindings: tuple = ()                       # (BindingSpec, …)


def materialize(cell, log_dir, *, local_cabinet=LOCAL_CABINET):
    """Seed a cell through the REAL engine and return (EdgeSpec, bound_views).

    Verdict bindings are FILE-SEEDED to the consequence ledger under `log_dir`
    (which the caller has placed on CABINET_EVENT_LOG_DIR) and read back through
    the D1 path; observation/purged bindings are proto-seeded. Everything folds
    together and each binding is served through real as_of — the returned views
    are substrate output, never hand-built.

    admissible_subjects / join_spec / evidence_bindings are assembled from the
    seeded reality: EVERY verdict binding gives the edge a non-empty join_spec
    entry (its expected matcher) — a "match" verdict's expected matcher EQUALS
    the seeded belief's identity (limb-(ii) holds), a "mismatch" verdict's
    expected matcher is a DIFFERENT identity than the belief carries (limb-(ii)
    fails — the edge expected a consequence about another subject); an
    `admissible=False` binding is served but withheld from admissible_subjects;
    a `resolve=False` binding contributes an evidence ref to a belief_id that
    has NO served view (dangling)."""
    cons_rows = []
    obs_protos = []
    plan = []                                  # (spec, subject_key, expected_join_key|None)

    for i, spec in enumerate(cell.bindings):
        tag = spec.tag or f"b{i}"
        if spec.role == "verdict":
            subject = f"release/{tag}"         # distinct subject => distinct identity
            row = consequence_row("ship", subject, verdict=spec.verdict,
                                  source=spec.source)
            cons_rows.append(row)
            actual_key = consequence_join_key(row)
            if spec.join == "match":
                expected_key = actual_key      # edge expects exactly this identity
            else:                              # mismatch: edge expected a DIFFERENT subject
                expected_key = (actual_key[0], actual_key[1], f"release/expected-{tag}")
            plan.append((spec, consequence_subject_key(row), expected_key))
        elif spec.role == "observation":
            sk = f"observation/{tag}"
            if spec.contested:
                obs_protos.extend(conflict_protos(sk, DIMENSION))
            else:
                obs_protos.append(observation_proto(
                    sk, DIMENSION, claim=observed_effect_claim(spec.observed_effect),
                    seq=0, event_suffix=tag))
            plan.append((spec, sk, None))
        elif spec.role == "purged":
            sk = f"observation/{tag}"
            obs_protos.append(observation_proto(
                sk, DIMENSION, claim=observed_effect_claim("increase"),
                seq=0, purged=True, event_suffix=tag))
            plan.append((spec, sk, None))
        else:                                  # pragma: no cover — guard a typo
            raise ValueError(f"unknown binding role {spec.role!r}")

    if cons_rows:
        seed_consequence_ledger(log_dir, cons_rows)
    protos = (consequence_protos(local_cabinet) if cons_rows else []) + obs_protos
    beliefs = fold_beliefs(protos) if protos else []

    bound_views = []
    admissible = set()
    join_spec = []
    evidence_bindings = []
    for spec, sk, expected_join_key in plan:
        if expected_join_key is not None:      # every verdict binding => an edge matcher
            join_spec.append(expected_join_key)
        if spec.admissible:
            admissible.add(sk)
        if spec.resolve:
            for view in views_for(beliefs, sk):
                bound_views.append(view)
                evidence_bindings.append(BindingRef(view.subject_key, view.belief_id))
        else:
            # dangling: an authored ref whose belief_id resolves to NO view.
            evidence_bindings.append(BindingRef(sk, "0" * 64))

    edge = EdgeSpec(
        authored=cell.authored,
        expected_effect=cell.expected_effect,
        assumptions=(("declared-confounder-and-selection",) if cell.assumptions else ()),
        admissible_subjects=frozenset(admissible),
        join_spec=tuple(join_spec),
        evidence_bindings=tuple(evidence_bindings),
    )
    return edge, tuple(bound_views)
