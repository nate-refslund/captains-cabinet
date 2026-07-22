"""COG-3 SIM-1 — objective-conflict / cycle / impossible-constraint (contract §11
row 1, §4.1, §4.2, §5.4, N1), tests-first, FILE-SEEDED, no DSN.

Foundry required-sim (:178): cyclic deps + mutually-exclusive goals + impossible
constraint. This suite pins the STRUCTURAL guarantees of the pure graph build:

  * conflicts stored symmetric + SORTED, BOTH sides retained, full set surfaced,
    never last-write-wins (§4.2 "conflicts stored symmetric + SORTED, never
    auto-resolved"; COG-2 §5.5 law; §11 sim1);
  * a depends_on cycle A->B->C->A is DETECTED, REPRESENTED (every edge kept) and
    FLAGGED — never silently topo-sorted away (§11 sim1);
  * an unsatisfiable constraint is marked with its evidence refs, never dropped
    (§11 sim1);
  * node_id is the DETERMINISTIC recorder-dialect digest of (kind, subject_key)
    — never a build-time ULID, content-independent (§4.1; §11 sim1 mutant);
  * the conflicted fixture rebuilds HASH-IDENTICAL across the C-F3 subprocess
    triple — 3 rebuilds under 3 PYTHONHASHSEED values (§5.4, N1, §11 sim1 —
    rev-1 reword of C-m10: identical across the triple, NOT a with/without
    collision).

FAILURE SIGNATURE (tests-first, contract §12.2 step 2): `framework.objectives`
does not exist yet, so every test raises `ModuleNotFoundError: No module named
'framework.objectives'` at the `_objectives()` guard in its body (never a skip —
importorskip is forbidden here; never a module-level import — that would be a
COLLECTION error). The later T4 implementation must satisfy these UNMODIFIED.

T1-PINNED SURFACE (flagged for the T4 implementer — the narrowest plausible
graph surface for these structural guarantees; integration reconciles names):
  framework.objectives.graph.build_graph(roots_path, cache_dir, scope, cutoff)
      -> writes canonical graph.jsonl + graph-manifest.json under cache_dir
         (§5.3/§5.4), returns a build result. Pure, env-free (A-M6).
  framework.objectives.graph.chained_graph_hash(cache_dir) -> str
      -> the N1 chained hash over graph.jsonl + graph-manifest.json + the
         disposable index (the `cog3-graph-hash.py` instrument's core, §8).
  framework.objectives.model.node_id(kind, subject_key) -> str  (recorder digest)
INTEGRATION-RECONCILIATION POINTS (see wave report): (a) how the cabinet-authored
objectives/outcomes/constraints/relational-edges are fed to the build — pinned
here as a provisional superset file passed as `roots_path` (mirrors the fixture
library's own provisional `write_roots_yml`); (b) the serialized record field
names in graph.jsonl (read here through TOLERANT accessors); (c) the exact
recorder-dialect container for node_id (pinned via set-membership over the
plausible encodings, so a ULID is rejected but the container is not over-fixed).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; Fable-5 two-tier law (test-authoring).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog3_fixtures as F           # noqa: E402  (the ONE seeding surface)
from framework.cortex import belief     # noqa: E402  (recorder dialect only)


# ===========================================================================
# Import indirection (contract §8) — the HONEST tests-first failure signature
# ===========================================================================

def _objectives():
    """Import the objectives graph/model surface. Raises `ModuleNotFoundError`
    today (the package is absent) — the honest absence signature. Called FIRST
    in every test body, so the failure is per-test, never a collection error and
    never a skip (importorskip is forbidden for this wave)."""
    from framework.objectives import graph, model
    return graph, model


# ===========================================================================
# Provisional objectives-input file (FLAGGED integration point (a)) + tolerant
# graph.jsonl readback (FLAGGED integration point (b)).
# ===========================================================================

def _write_objectives_input(dir_path, *, directions, objectives,
                            outcomes=(), constraints=(), name="objectives-input.json"):
    """Write the cabinet-authored graph seed as ONE provisional JSON file passed
    as build_graph's `roots_path`. PROVISIONAL by design — exactly as the fixture
    library's `write_roots_yml` is provisional until the roots adapter lands; the
    T4 implementer reconciles whether objectives ride this file or separate
    workgraph/mission/product adapter sources. The suite asserts over the OUTPUT
    graph (whose record schema IS contract-pinned, §4), so the structural
    guarantees hold regardless of the input plumbing."""
    payload = {
        "directions": list(directions),
        "objectives": list(objectives),
        "outcomes": list(outcomes),
        "constraints": list(constraints),
    }
    path = Path(dir_path) / name
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")
    return path


def _read_records(cache_dir):
    """Parse the written graph.jsonl into (nodes, edges) using TOLERANT
    accessors — the OUTPUT artifact is contract-pinned (§4/§5.4); minor field
    spellings are an integration detail, so node/edge discrimination and endpoint
    reads accept the plausible spellings."""
    path = Path(cache_dir) / "graph.jsonl"
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    nodes = [r for r in records if _is_node(r)]
    edges = [r for r in records if _is_edge(r)]
    return nodes, edges


def _is_edge(r):
    return ("relation" in r or "edge_id" in r or "source" in r
            or "source_node_id" in r or "source_id" in r)


def _is_node(r):
    return ("subject_key" in r and "kind" in r) and not _is_edge(r)


def _endpoint(edge, which):
    for k in (which, f"{which}_node_id", f"{which}_id"):
        if k in edge:
            return edge[k]
    return None


def _relation(edge):
    return edge.get("relation") or edge.get("edge_kind") or edge.get("relational_kind")


def _read_manifest(cache_dir):
    return json.loads((Path(cache_dir) / "graph-manifest.json").read_text(encoding="utf-8"))


def _slug_to_node_id(nodes):
    """Map every `<kind>/<slug>` subject_key to its node_id (for relation reads)."""
    out = {}
    for n in nodes:
        out[n["subject_key"]] = n["node_id"]
    return out


def _conflict_sets(nodes, edges):
    """For each objective subject_key, its conflicts_with peer subject_keys,
    SORTED — read symmetrically from whichever endpoint touches the node."""
    id_to_sk = {n["node_id"]: n["subject_key"] for n in nodes}
    peers = {n["subject_key"]: set() for n in nodes}
    for e in edges:
        if _relation(e) != "conflicts_with":
            continue
        s, t = _endpoint(e, "source"), _endpoint(e, "target")
        s_sk, t_sk = id_to_sk.get(s), id_to_sk.get(t)
        if s_sk is not None and t_sk is not None:
            # symmetric: the peer is visible from BOTH sides regardless of the
            # stored direction (§4.2 "conflicts stored symmetric").
            peers[s_sk].add(t_sk)
            peers[t_sk].add(s_sk)
    return {sk: sorted(v) for sk, v in peers.items()}


def _depends_on_pairs(nodes, edges):
    id_to_sk = {n["node_id"]: n["subject_key"] for n in nodes}
    out = set()
    for e in edges:
        if _relation(e) == "depends_on":
            s, t = id_to_sk.get(_endpoint(e, "source")), id_to_sk.get(_endpoint(e, "target"))
            if s is not None and t is not None:
                out.add((s, t))
    return out


# ---------------------------------------------------------------------------
# The build wrapper — §5.3 positional signature. Guarded (raises today).
# ---------------------------------------------------------------------------

def _build(tmp_path, *, directions, objectives, outcomes=(), constraints=(),
           beliefs=(), cutoff=F.CUTOFF, scope=None, sub="g"):
    graph, _model = _objectives()                     # guard: ModuleNotFoundError today
    cache_dir = Path(tmp_path) / sub / "objectives"
    cortex_dir = Path(tmp_path) / sub / "cortex"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cortex_dir.mkdir(parents=True, exist_ok=True)
    if beliefs:
        # the ONE cortex read path serves this store (§5.1); wiring of the cortex
        # dir vs the objectives cache root is an integration-reconciliation point.
        F.persist_cortex_store(cortex_dir, beliefs)
    roots_path = _write_objectives_input(
        Path(tmp_path) / sub, directions=directions, objectives=objectives,
        outcomes=outcomes, constraints=constraints)
    graph.build_graph(str(roots_path), str(cache_dir),
                      dict(scope if scope is not None else F.SCOPE), cutoff)
    return cache_dir


# Canonical seed fixtures reused across tests -------------------------------

_DIRECTIONS = [{"slug": "d-north", "statement": "ship the compliant platform"}]


def _two_conflicting_objectives():
    """alpha and beta: conflicts_with each other, mutually unsatisfiable floors
    on the SAME dimension (§11 sim1 "mutually unsatisfiable floors")."""
    return [
        {"slug": "alpha", "statement": "minimise spend", "root_ref": "d-north",
         "conflicts_with": ["beta"], "floors": {"cost": "at_most_low"}},
        {"slug": "beta", "statement": "maximise reach", "root_ref": "d-north",
         "conflicts_with": ["alpha"], "floors": {"cost": "at_least_high"}},
    ]


def _cycle_objectives():
    """A->B->C->A depends_on cycle (§11 sim1)."""
    return [
        {"slug": "A", "statement": "a", "root_ref": "d-north", "depends_on": ["B"]},
        {"slug": "B", "statement": "b", "root_ref": "d-north", "depends_on": ["C"]},
        {"slug": "C", "statement": "c", "root_ref": "d-north", "depends_on": ["A"]},
    ]


# ===========================================================================
# 1. Conflicts — symmetric + SORTED, both sides retained, full set (never LWW)
# ===========================================================================

class TestConflictSymmetry:
    def test_conflict_is_symmetric_both_sides_retained(self, tmp_path):
        # §4.2: "conflicts stored symmetric + SORTED, never auto-resolved" — the
        # conflict is visible from BOTH alpha and beta, never one-directional.
        cache = _build(tmp_path, directions=_DIRECTIONS,
                       objectives=_two_conflicting_objectives())
        nodes, edges = _read_records(cache)
        cs = _conflict_sets(nodes, edges)
        assert "beta" in "".join(cs["objective/alpha"])   # alpha side retained
        assert cs["objective/alpha"] == ["objective/beta"]  # §4.2 symmetric (alpha->beta)
        assert cs["objective/beta"] == ["objective/alpha"]  # §4.2 symmetric (beta->alpha)

    def test_full_conflict_set_surfaced_never_lww(self, tmp_path):
        # §11 sim1: "BOTH sides retained with the full conflict set surfaced
        # (never LWW)". alpha conflicts with beta AND gamma — a last-write-wins
        # builder would keep only the last, collapsing the set.
        objs = [
            {"slug": "alpha", "root_ref": "d-north", "conflicts_with": ["beta", "gamma"]},
            {"slug": "beta", "root_ref": "d-north", "conflicts_with": ["alpha"]},
            {"slug": "gamma", "root_ref": "d-north", "conflicts_with": ["alpha"]},
        ]
        cache = _build(tmp_path, directions=_DIRECTIONS, objectives=objs)
        nodes, edges = _read_records(cache)
        cs = _conflict_sets(nodes, edges)
        # full set surfaced AND sorted (§4.2 SORTED) — never {gamma} alone (LWW).
        assert cs["objective/alpha"] == ["objective/beta", "objective/gamma"]

    def test_conflict_edges_stored_sorted(self, tmp_path):
        # §4.2 SORTED: the stored conflicts_with edge endpoints are in sorted
        # canonical order (a symmetric relation has one canonical orientation).
        cache = _build(tmp_path, directions=_DIRECTIONS,
                       objectives=_two_conflicting_objectives())
        nodes, edges = _read_records(cache)
        id_to_sk = {n["node_id"]: n["subject_key"] for n in nodes}
        cw = [e for e in edges if _relation(e) == "conflicts_with"]
        assert cw, "no conflicts_with edge was stored"           # §4.2 relation exists
        for e in cw:
            s_sk = id_to_sk.get(_endpoint(e, "source"))
            t_sk = id_to_sk.get(_endpoint(e, "target"))
            # canonical sorted orientation source<=target (§4.2 SORTED / COG-2 §5.5)
            assert (s_sk, t_sk) == tuple(sorted((s_sk, t_sk)))

    def test_auto_resolving_builder_dropping_one_side_is_caught(self, tmp_path):
        # NEGATIVE CONTROL (§11 sim1 mutant "auto-resolving builder (drops one
        # side)"): an auto-resolver would keep alpha->beta but silently drop the
        # reciprocal beta->alpha (LWW-style). Asserting BOTH sides retained kills
        # that mutant. §4.2 "never auto-resolved".
        cache = _build(tmp_path, directions=_DIRECTIONS,
                       objectives=_two_conflicting_objectives())
        nodes, edges = _read_records(cache)
        cs = _conflict_sets(nodes, edges)
        assert cs["objective/alpha"] and cs["objective/beta"]   # neither side dropped


# ===========================================================================
# 2. depends_on cycle — detected, represented, flagged (never silently sorted)
# ===========================================================================

def _cycle_flag(manifest, nodes, edges):
    """Read a cycle indication tolerantly from the manifest or a node/edge flag
    (integration point (b)). Returns the set of subject_keys named in the cycle
    report, or None when no cycle is represented anywhere."""
    id_to_sk = {n["node_id"]: n["subject_key"] for n in nodes}
    for key in ("cycles", "depends_on_cycles", "cycle_report", "relational_cycles"):
        rep = manifest.get(key)
        if rep:
            named = set()
            for cyc in rep:
                members = cyc if isinstance(cyc, list) else cyc.get("nodes", cyc)
                for m in members:
                    named.add(id_to_sk.get(m, m))
            return named
    # fallback: a per-node/edge "in_cycle"/"flags:[cycle]" marker.
    named = set()
    for n in nodes:
        flags = n.get("flags") or []
        if n.get("in_cycle") or "cycle" in flags or "in_cycle" in flags:
            named.add(n["subject_key"])
    return named or None


class TestDependsOnCycle:
    def test_cycle_detected_represented_and_flagged(self, tmp_path):
        cache = _build(tmp_path, directions=_DIRECTIONS, objectives=_cycle_objectives())
        nodes, edges = _read_records(cache)
        manifest = _read_manifest(cache)
        # REPRESENTED: every depends_on edge of the cycle is kept (§11 sim1).
        pairs = _depends_on_pairs(nodes, edges)
        assert ("objective/A", "objective/B") in pairs
        assert ("objective/B", "objective/C") in pairs
        assert ("objective/C", "objective/A") in pairs
        # DETECTED + FLAGGED: the cycle is named over {A,B,C} (§11 sim1).
        named = _cycle_flag(manifest, nodes, edges)
        assert named is not None, "cycle not flagged anywhere (§11 sim1)"
        assert {"objective/A", "objective/B", "objective/C"} <= named

    def test_silent_topo_sort_is_caught(self, tmp_path):
        # NEGATIVE CONTROL (§11 sim1 mutant "silent topo-sort that 'breaks' the
        # cycle"): a topo-sorting builder would drop one back-edge to linearise
        # A->B->C and emit NO cycle flag. Asserting all three edges kept AND the
        # cycle flagged kills that mutant (§4.2 relational edges "no epistemic
        # machinery" — but never silently rewritten).
        cache = _build(tmp_path, directions=_DIRECTIONS, objectives=_cycle_objectives())
        nodes, edges = _read_records(cache)
        pairs = _depends_on_pairs(nodes, edges)
        assert len(pairs & {("objective/A", "objective/B"),
                            ("objective/B", "objective/C"),
                            ("objective/C", "objective/A")}) == 3   # no edge dropped
        assert _cycle_flag(_read_manifest(cache), nodes, edges) is not None  # not silent


# ===========================================================================
# 3. Unsatisfiable constraint — marked with evidence refs, never dropped
# ===========================================================================

class TestConstraintRetention:
    def _seed(self, tmp_path):
        # a constraint on `cost` bound to one observation whose movement violates
        # it against every bound outcome (unsatisfiable, §11 sim1). Observation
        # evidence (not consequence) — no CABINET_EVENT_LOG_DIR needed.
        obs_sk = "observation/cost-blows-budget"
        protos = [F.observation_proto(obs_sk, F.DIMENSION,
                                      claim=F.observed_effect_claim("increase"),
                                      seq=0, event_suffix="c1")]
        beliefs = F.fold_beliefs(protos)
        constraints = [{"slug": "budget-cap", "dimension": "cost",
                        "floor": "at_most_low", "evidence_subjects": [obs_sk]}]
        outcomes = [{"slug": "spend", "dimension": "cost"}]
        objectives = [{"slug": "alpha", "root_ref": "d-north"}]
        cache = _build(tmp_path, directions=_DIRECTIONS, objectives=objectives,
                       outcomes=outcomes, constraints=constraints, beliefs=beliefs)
        return cache, obs_sk

    def test_unsatisfiable_constraint_is_retained_with_evidence_refs(self, tmp_path):
        cache, obs_sk = self._seed(tmp_path)
        nodes, _edges = _read_records(cache)
        by_sk = {n["subject_key"]: n for n in nodes}
        # RETAINED — the constraint node is present (§4.1 subject_key constraint/<slug>).
        assert "constraint/budget-cap" in by_sk, "constraint dropped (§11 sim1)"
        node = by_sk["constraint/budget-cap"]
        # MARKED WITH EVIDENCE REFS — the bound observation is still cited, never
        # dropped (§11 sim1 "marked with evidence refs, never dropped"; §4.2
        # evidence_bindings carried whole).
        assert obs_sk in json.dumps(node), "constraint lost its evidence ref (§11 sim1)"

    def test_unsatisfiable_constraint_marked_not_silently_satisfied(self, tmp_path):
        cache, _obs = self._seed(tmp_path)
        nodes, _edges = _read_records(cache)
        node = {n["subject_key"]: n for n in nodes}["constraint/budget-cap"]
        blob = json.dumps(node).lower()
        # MARKED unsatisfiable — the record carries a not-met signal (§4.4 "unknown
        # never passes a floor"; a below-floor constraint is not a pass). Tolerant
        # read of the state/marker field (integration point (b)).
        assert any(tok in blob for tok in
                   ("unsatisf", "violated", "unmet", "below_floor", "\"met\": false",
                    "not_met", "failed")), f"constraint not marked unsatisfiable: {node}"

    def test_constraint_dropping_builder_is_caught(self, tmp_path):
        # NEGATIVE CONTROL (§11 sim1 mutant "constraint-dropping builder"): a
        # builder that omits an unsatisfiable constraint to "clean up" the graph
        # would leave no constraint node. Asserting presence kills it (§11 sim1).
        cache, _obs = self._seed(tmp_path)
        nodes, _edges = _read_records(cache)
        assert any(n["subject_key"] == "constraint/budget-cap" for n in nodes)


# ===========================================================================
# 4. node_id — deterministic recorder digest of (kind, subject_key), no ULID
# ===========================================================================

def _plausible_recorder_ids(kind, subject_key):
    """Every recorder-dialect digest of the pair (kind, subject_key) under a
    plausible canonical container. node_id MUST be one of these (§4.1 "recorder-
    dialect digest of (kind, subject_key)") — pinning by membership rejects a
    build-time ULID/random id while NOT over-fixing the exact container (that is
    integration point (c); the named-key dict mirrors compute_belief_id)."""
    return {
        belief.digest({"kind": kind, "subject_key": subject_key}),
        belief.digest([kind, subject_key]),
        belief.digest((kind, subject_key)),
        belief.digest(f"{kind}|{subject_key}"),
        belief.digest(f"{kind}\x1f{subject_key}"),
    }


class TestNodeIdIdentity:
    def test_node_id_is_recorder_digest_of_kind_subject_key(self, tmp_path):
        cache = _build(tmp_path, directions=_DIRECTIONS,
                       objectives=_two_conflicting_objectives())
        nodes, _edges = _read_records(cache)
        assert nodes, "no nodes emitted"
        for n in nodes:
            # §4.1: node_id is the recorder-dialect digest of (kind, subject_key).
            assert n["node_id"] in _plausible_recorder_ids(n["kind"], n["subject_key"]), n

    def test_node_id_is_not_a_ulid(self, tmp_path):
        cache = _build(tmp_path, directions=_DIRECTIONS,
                       objectives=_two_conflicting_objectives())
        nodes, _edges = _read_records(cache)
        for n in nodes:
            nid = n["node_id"]
            # a recorder digest is 64 lowercase hex; a ULID is 26 Crockford
            # base32. §4.1 "never a build-time ULID"; §11 sim1 mutant.
            assert len(nid) == 64 and all(c in "0123456789abcdef" for c in nid), nid

    def test_node_ids_identical_across_two_builds(self, tmp_path):
        # DETERMINISM (§4.1 / §11 sim1 "fresh-ULID node ids" mutant): two builds
        # of the SAME seed yield identical node_ids. A ULID-minting builder differs.
        objs = _two_conflicting_objectives()
        c1 = _build(tmp_path, directions=_DIRECTIONS, objectives=objs, sub="b1")
        c2 = _build(tmp_path, directions=_DIRECTIONS, objectives=objs, sub="b2")
        n1 = {n["subject_key"]: n["node_id"] for n in _read_records(c1)[0]}
        n2 = {n["subject_key"]: n["node_id"] for n in _read_records(c2)[0]}
        assert n1 == n2 and n1                                   # identical, non-empty

    def test_node_id_survives_content_change(self, tmp_path):
        # COG-2 identity law (§4.1 "survives content change"): the SAME (kind,
        # subject_key) with DIFFERENT content (statement) keeps the SAME node_id
        # — identity excludes content. A content-keyed id would change.
        a = [{"slug": "alpha", "root_ref": "d-north", "statement": "first wording"}]
        b = [{"slug": "alpha", "root_ref": "d-north", "statement": "TOTALLY different"}]
        ca = _build(tmp_path, directions=_DIRECTIONS, objectives=a, sub="ca")
        cb = _build(tmp_path, directions=_DIRECTIONS, objectives=b, sub="cb")
        ida = {n["subject_key"]: n["node_id"] for n in _read_records(ca)[0]}
        idb = {n["subject_key"]: n["node_id"] for n in _read_records(cb)[0]}
        assert ida["objective/alpha"] == idb["objective/alpha"]   # §4.1 content-independent


# ===========================================================================
# 5. C-F3 hash triple — the conflicted fixture rebuilds hash-identical across
#    3 subprocesses under 3 distinct PYTHONHASHSEED values (§5.4, N1)
# ===========================================================================

# A tiny driver run as a child: rebuild-from-zero into a fresh cache from the
# SAME seeded authorities, print the N1 chained graph hash. Under a distinct
# PYTHONHASHSEED per child, an unsorted-collection determinism bug would differ.
_DRIVER = textwrap.dedent(
    """
    import sys, json
    repo, tests, roots_path, out_cache = sys.argv[1:5]
    sys.path.insert(0, tests); sys.path.insert(0, repo)
    import lib_cog3_fixtures as F
    from framework.objectives import graph
    graph.build_graph(roots_path, out_cache, dict(F.SCOPE), F.CUTOFF)
    print(graph.chained_graph_hash(out_cache))
    """
).strip()


def _run_child(tmp_path, roots_path, hashseed, idx):
    driver = Path(tmp_path) / "driver.py"
    driver.write_text(_DRIVER, encoding="utf-8")
    out_cache = Path(tmp_path) / f"child-{idx}" / "objectives"
    out_cache.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = str(hashseed)
    return subprocess.run(
        [sys.executable, str(driver), str(_REPO), str(_HERE),
         str(roots_path), str(out_cache)],
        capture_output=True, text=True, env=env)


class TestConflictedRebuildHashTriple:
    def test_three_subprocesses_distinct_hashseeds_identical(self, tmp_path):
        # GUARD (in-process): today this raises ModuleNotFoundError before any
        # child is spawned — the uniform absence signature for this suite. Post-
        # implementation the guard passes and the subprocess triple runs for real.
        _objectives()
        # seed the conflicted fixture ONCE; each child rebuilds from it (N1
        # "delete->rebuild-from-zero reproduces the hash").
        roots_path = _write_objectives_input(
            tmp_path, directions=_DIRECTIONS,
            objectives=_two_conflicting_objectives())
        hashes = []
        for idx, seed in enumerate((0, 1, 987654321)):
            r = _run_child(tmp_path, roots_path, seed, idx)
            assert r.returncode == 0, r.stderr        # rebuild succeeded
            hashes.append(r.stdout.strip())
        # §5.4/N1/§11 sim1 (rev-1 C-m10 reword): identical across the C-F3 triple.
        assert hashes[0] and len(set(hashes)) == 1, hashes
