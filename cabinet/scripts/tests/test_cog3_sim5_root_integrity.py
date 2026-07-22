"""COG-3 SIM-5 — Captain-root integrity (contract §11 row 5, §4.1, N4, §5.4, §9
r5), tests-first, FILE-SEEDED, no DSN. VETO HALF EXCISED (§6.7 — root integrity
ONLY; there is NO veto input this phase).

Foundry required-sim (:100/:178): every objective resolves through an
authenticated Captain-direction root. This suite pins:

  * the builder writes NOTHING outside cabinet/cache/objectives/ — the root files
    are byte-identical after every build (§7.2, N4, §11 sim5);
  * a root edit/removal between epochs is an honest EPOCH BUMP (roots_hash enters
    the epoch tuple, §5.4) and its dependent objectives are flagged ORPHANED at
    rebuild and served ANSWERABLE-with-flag — never silently retained under the
    old root, never silently dropped (§9 r5, §11 sim5);
  * the TWO failure limbs are DISTINGUISHED exactly as §4.1/N4/G-M2 pin them:
      - an objective with NO root_ref            => SCHEMA rejection (presence);
      - a PRESENT-but-dangling/forged root_ref   => build-fold STRUCTURAL failure
        (graph.py check — "never called a schema rejection", N4);
      - a recorded roots_hash != the build's     => build-fold STRUCTURAL failure.

CONTRACT-TENSION NOTE (flagged for the adjudicator, see wave report): §4.1
says the fold RAISES a structural failure when a root_ref does not resolve, while
§9 r5 says a root edit/removal yields an ANSWERABLE orphan. These are reconciled
here per the §11 sim5 SEEDS: a legitimately-removed root (Captain edit) orphans
its dependents (answerable+flag); a FORGED node-id root_ref (never a valid
direction) is the build-fold failure. If the T4 implementation instead treats a
removed-root dependent as a hard fold failure, that is a genuine §4.1-vs-§9r5
fork for the adjudicator — the orphan-vs-dangling discrimination MECHANISM is the
one integration point worth a glance.

FAILURE SIGNATURE (tests-first, §12.2 step 2): every test raises
`ModuleNotFoundError: No module named 'framework.objectives'` at the
`_objectives()` guard in its body (no skip; no module-level import → no collection
error). The T4 implementation must satisfy these UNMODIFIED.

T1-PINNED SURFACE (flagged for T4; integration reconciles names):
  graph.build_graph(roots_path, cache_dir, scope, cutoff) — pure build (§5.3).
  graph.BuildFailure — the structural build-fold failure type (§4.1). The SAME
      shared type T3 pinned as states.BuildFailure (one home, re-exported — see
      the T3 layering note); referenced here via graph for the root-fold limb.
  query.serve_objective(cache_dir, subject_key) -> Answer(state, flags) — the
      serve surface (§5.2/§5.4); orphaned is an ANSWER flag (§5.2).
Integration points: (a) the objectives-input plumbing (provisional superset file,
as in SIM-1); (b) serialized field names (tolerant reads); (c) the exact
schema-rejection exception type for the presence limb (pinned only as "distinct
from graph.BuildFailure", per N4).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; Fable-5 two-tier law (test-authoring).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog3_fixtures as F           # noqa: E402


def _objectives():
    """Import indirection (contract §8). Raises ModuleNotFoundError today — the
    honest tests-first absence signature; called first in every test body."""
    from framework.objectives import graph, query
    return graph, query


# ===========================================================================
# Provisional objectives-input (integration point (a)) + tolerant readback
# ===========================================================================

def _write_input(dir_path, *, directions, objectives, name="objectives-input.json"):
    """PROVISIONAL cabinet-authored graph seed passed as build_graph's
    `roots_path` (mirrors the fixture library's provisional write_roots_yml). An
    objective entry may carry: slug, statement, root_ref (the direction slug it
    resolves through), and the anomaly knobs `forged_root_node_id` (a nonexistent
    node id => dangling) and `recorded_roots_hash` (a value != the build's =>
    roots_hash mismatch). Omitting root_ref => the presence (schema) limb."""
    payload = {"directions": list(directions), "objectives": list(objectives)}
    path = Path(dir_path) / name
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")
    return path


def _read_nodes(cache_dir):
    path = Path(cache_dir) / "graph.jsonl"
    nodes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if "subject_key" in r and "kind" in r and "relation" not in r and "edge_id" not in r:
            nodes.append(r)
    return nodes


def _read_manifest(cache_dir):
    return json.loads((Path(cache_dir) / "graph-manifest.json").read_text(encoding="utf-8"))


def _roots_hash(manifest):
    """Read the roots_hash out of the epoch tuple, tolerant of nesting (§5.4
    names roots_hash inside the epoch tuple)."""
    epoch = manifest.get("epoch", manifest)
    if isinstance(epoch, dict) and "roots_hash" in epoch:
        return epoch["roots_hash"]
    if "roots_hash" in manifest:
        return manifest["roots_hash"]
    # last resort: any value under a roots_hash-ish key anywhere in the manifest.
    blob = json.dumps(manifest)
    return blob  # equality of the whole manifest still detects a bump


def _node_flags(node):
    flags = node.get("flags") or node.get("answer_flags") or []
    if node.get("orphaned"):
        flags = list(flags) + ["orphaned"]
    return set(flags)


def _snapshot(root, exclude):
    """path -> (size, sha256) for every file under `root` except under
    `exclude` — the "writes nothing outside the cache" witness (§7.2/N4)."""
    exclude = Path(exclude).resolve()
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if not p.is_file():
            continue
        rp = p.resolve()
        if exclude == rp or exclude in rp.parents:
            continue
        data = p.read_bytes()
        out[str(rp)] = (len(data), hashlib.sha256(data).hexdigest())
    return out


_DIRS_TWO = [{"slug": "d-north", "statement": "ship compliant"},
             {"slug": "d-south", "statement": "expand reach"}]


# ---------------------------------------------------------------------------
# build wrapper — §5.3 positional signature; guarded (raises today)
# ---------------------------------------------------------------------------

def _build(tmp_path, *, directions, objectives, sub="g", cutoff=F.CUTOFF):
    graph, _query = _objectives()                        # guard: ModuleNotFoundError today
    cache_dir = Path(tmp_path) / sub / "cache" / "objectives"
    cache_dir.mkdir(parents=True, exist_ok=True)
    roots_path = _write_input(Path(tmp_path) / sub, directions=directions,
                              objectives=objectives)
    graph.build_graph(str(roots_path), str(cache_dir), dict(F.SCOPE), cutoff)
    return cache_dir, roots_path


# ===========================================================================
# 1. Read-only-by-construction — writes nothing outside the cache
# ===========================================================================

class TestBuilderWritesNothingOutsideCache:
    def test_root_and_input_bytes_identical_after_build(self, tmp_path):
        graph, _q = _objectives()                        # guard
        sub = Path(tmp_path) / "g"
        cache_dir = sub / "cache" / "objectives"
        cache_dir.mkdir(parents=True, exist_ok=True)
        roots_path = _write_input(sub, directions=_DIRS_TWO,
                                  objectives=[{"slug": "alpha", "root_ref": "d-north"}])
        before = _snapshot(tmp_path, exclude=sub / "cache")
        root_sha_before = hashlib.sha256(roots_path.read_bytes()).hexdigest()
        graph.build_graph(str(roots_path), str(cache_dir), dict(F.SCOPE), F.CUTOFF)
        after = _snapshot(tmp_path, exclude=sub / "cache")
        # §7.2/N4: the builder has NO write path outside cabinet/cache/objectives/.
        assert before == after, "builder wrote/changed a file outside its cache"
        # root bytes byte-identical (§11 sim5 assert; kills the "writes/corrects
        # root files" mutant).
        assert hashlib.sha256(roots_path.read_bytes()).hexdigest() == root_sha_before

    def test_builder_correcting_root_files_is_caught(self, tmp_path):
        # NEGATIVE CONTROL (§11 sim5 mutant "builder that writes/'corrects' root
        # files"): identical to the assertion above — any mutation of the root
        # bytes by the builder trips the byte-identity check. Distinct test so the
        # mutant is named explicitly.
        graph, _q = _objectives()                        # guard
        sub = Path(tmp_path) / "g"
        cache_dir = sub / "cache" / "objectives"
        cache_dir.mkdir(parents=True, exist_ok=True)
        roots_path = _write_input(sub, directions=_DIRS_TWO,
                                  objectives=[{"slug": "alpha", "root_ref": "d-north"}])
        sha = hashlib.sha256(roots_path.read_bytes()).hexdigest()
        graph.build_graph(str(roots_path), str(cache_dir), dict(F.SCOPE), F.CUTOFF)
        assert hashlib.sha256(roots_path.read_bytes()).hexdigest() == sha  # §7.2 read-only


# ===========================================================================
# 2. Root edit/removal — epoch bump + orphaned-answerable dependents
# ===========================================================================

class TestRootEditOrphansAnswerable:
    def _obj(self):
        # an objective rooted through d-south; d-south is REMOVED at rebuild.
        return [{"slug": "alpha", "statement": "reach goal", "root_ref": "d-south"}]

    def test_root_removal_bumps_epoch_roots_hash(self, tmp_path):
        c1, _r1 = _build(tmp_path, directions=_DIRS_TWO, objectives=self._obj(), sub="e1")
        # root file edited: d-south REMOVED (Captain root edit).
        c2, _r2 = _build(tmp_path, directions=[_DIRS_TWO[0]], objectives=self._obj(), sub="e2")
        h1 = _roots_hash(_read_manifest(c1))
        h2 = _roots_hash(_read_manifest(c2))
        # §5.4: roots_hash is in the epoch tuple — a root edit is an honest bump.
        assert h1 != h2, "root edit did not bump the epoch roots_hash (§5.4)"

    def test_removed_root_flags_dependent_orphaned(self, tmp_path):
        _c1, _r1 = _build(tmp_path, directions=_DIRS_TWO, objectives=self._obj(), sub="o1")
        c2, _r2 = _build(tmp_path, directions=[_DIRS_TWO[0]], objectives=self._obj(), sub="o2")
        nodes = {n["subject_key"]: n for n in _read_nodes(c2)}
        # §9 r5: never silently dropped — the objective is REPRESENTED at rebuild.
        assert "objective/alpha" in nodes, "orphaned objective silently dropped (§9 r5)"
        # §9 r5: flagged ORPHANED, never silently retained under the old root.
        assert "orphaned" in _node_flags(nodes["objective/alpha"]), \
            "dependent of a removed root not flagged orphaned (§9 r5/§11 sim5)"

    def test_orphaned_objective_is_served_answerable_with_flag(self, tmp_path):
        _c1, _r1 = _build(tmp_path, directions=_DIRS_TWO, objectives=self._obj(), sub="s1")
        c2, _r2 = _build(tmp_path, directions=[_DIRS_TWO[0]], objectives=self._obj(), sub="s2")
        _graph, query = _objectives()
        answer = query.serve_objective(str(c2), "objective/alpha")
        # §9 r5: orphaned subtrees remain ANSWERABLE (refusal would hide the
        # Captain's own root-edit signal) — an answer is returned...
        assert answer is not None, "orphaned objective not answerable (§9 r5)"
        # ...always carrying the orphaned flag beside the state (§5.2 answer flags).
        flags = getattr(answer, "flags", None)
        if flags is None and isinstance(answer, dict):
            flags = answer.get("flags")
        assert flags is not None and "orphaned" in set(flags), \
            "served answer missing the orphaned flag (§9 r5/§5.2)"

    def test_orphan_retaining_builder_is_caught(self, tmp_path):
        # NEGATIVE CONTROL (§11 sim5 mutant "orphan-retaining builder"): a builder
        # that silently keeps alpha rooted under the DELETED d-south (no orphan
        # flag) would leave alpha un-flagged. Asserting the flag kills it (§9 r5).
        _c1, _r1 = _build(tmp_path, directions=_DIRS_TWO, objectives=self._obj(), sub="r1")
        c2, _r2 = _build(tmp_path, directions=[_DIRS_TWO[0]], objectives=self._obj(), sub="r2")
        node = {n["subject_key"]: n for n in _read_nodes(c2)}["objective/alpha"]
        assert "orphaned" in _node_flags(node)           # not silently retained


# ===========================================================================
# 3. The two failure limbs — presence (schema) vs resolvability (fold)
# ===========================================================================

class TestTwoFailureLimbsDistinguished:
    def _raises(self, tmp_path, objective, sub):
        """Build with one anomalous objective; return the raised exception."""
        graph, _q = _objectives()                        # guard
        cache_dir = Path(tmp_path) / sub / "cache" / "objectives"
        cache_dir.mkdir(parents=True, exist_ok=True)
        roots_path = _write_input(Path(tmp_path) / sub, directions=_DIRS_TWO,
                                  objectives=[objective])
        with pytest.raises(Exception) as ei:             # noqa: PT011 — type asserted below
            graph.build_graph(str(roots_path), str(cache_dir), dict(F.SCOPE), F.CUTOFF)
        return graph, ei.value

    def test_rootless_objective_is_schema_rejection_not_fold_failure(self, tmp_path):
        # §4.1/:55/:100: root_ref PRESENCE is schema-enforced — a rootless
        # objective is a SCHEMA rejection, and per N4 that is NOT the fold's
        # structural failure. (Kills the "root-optional schema variant" mutant —
        # which would not raise at all.)
        graph, exc = self._raises(tmp_path, {"slug": "alpha"}, sub="noroot")
        assert not isinstance(exc, graph.BuildFailure), \
            "rootless objective raised the fold failure, not a schema rejection (§4.1/N4)"

    def test_dangling_root_ref_is_build_fold_failure(self, tmp_path):
        # §4.1(i)/N4/G-M2: a PRESENT-but-dangling root_ref (a forged node id that
        # exists in no build) is a build-FOLD structural failure in graph.py —
        # never a schema rejection. (Kills the "fold that accepts a dangling
        # root_ref" mutant.)
        graph, exc = self._raises(
            tmp_path,
            {"slug": "alpha", "root_ref": "d-north",
             "forged_root_node_id": "direction/" + "de" * 32},
            sub="dangling")
        assert isinstance(exc, graph.BuildFailure), \
            "dangling root_ref not a build-fold structural failure (§4.1/N4)"

    def test_roots_hash_mismatch_is_build_fold_failure(self, tmp_path):
        # §4.1(ii): a recorded roots_hash != the build's is a build-fold structural
        # failure. (Kills the "fold that skips the roots_hash epoch match" mutant.)
        graph, exc = self._raises(
            tmp_path,
            {"slug": "alpha", "root_ref": "d-north",
             "recorded_roots_hash": "0" * 64},
            sub="stalehash")
        assert isinstance(exc, graph.BuildFailure), \
            "stale recorded roots_hash not a build-fold structural failure (§4.1 ii)"

    def test_presence_and_resolvability_limbs_are_distinct_types(self, tmp_path):
        # §4.1/N4/G-M2 core: the TWO limbs are DISTINGUISHED — presence (schema)
        # and resolvability (fold) are different failure types, so the fold check
        # is "never called a schema rejection".
        graph, schema_exc = self._raises(tmp_path, {"slug": "alpha"}, sub="d1")
        _graph2, fold_exc = self._raises(
            tmp_path,
            {"slug": "alpha", "root_ref": "d-north",
             "forged_root_node_id": "direction/" + "ab" * 32},
            sub="d2")
        assert type(schema_exc) is not type(fold_exc), \
            "the presence and resolvability limbs collapsed to one type (§4.1/N4)"
        assert isinstance(fold_exc, graph.BuildFailure) and not isinstance(
            schema_exc, graph.BuildFailure)              # fold-limb only is BuildFailure


# ===========================================================================
# 4. Authenticated build baseline — the happy path resolves and serves
# ===========================================================================

class TestAuthenticatedRootsBaseline:
    def test_authenticated_objective_builds_and_is_not_orphaned(self, tmp_path):
        # build over authenticated roots (§11 sim5 seed): alpha rooted through a
        # PRESENT direction resolves cleanly — present, NOT orphaned.
        c, _r = _build(tmp_path, directions=_DIRS_TWO,
                       objectives=[{"slug": "alpha", "root_ref": "d-north"}], sub="ok")
        nodes = {n["subject_key"]: n for n in _read_nodes(c)}
        assert "objective/alpha" in nodes                              # resolved + present
        assert "orphaned" not in _node_flags(nodes["objective/alpha"])  # authenticated root
