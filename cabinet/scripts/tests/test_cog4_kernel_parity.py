"""COG-4 W3 u1 — C3 kernel BYTE-COMPAT parity vs the two SHIPPED instantiations
(contract cognitive-core-phase-4-contract-2026-07-23 §6.1/§6.4).

The kernel is EXTRACTION, not invention: both shipped stores must be
reproducible through it BYTE-IDENTICALLY. This suite builds a REAL cortex
belief store and a REAL objectives graph in tmp roots through the SHIPPED
implementations, then recomputes every extracted law through
framework.projection.kernel and asserts identity:

  * cortex store — built by a tmp-root subprocess DRIVER that seeds
    deterministic outbox rows and runs the shipped fold + writer
    (framework.cortex engine.fold / build_manifest / write_projection — the
    exact post-DB path cog2-rebuild.py executes; the DSN CLI itself requires a
    live PostgreSQL outbox, and the COG-4 corpus law pins suites file-seeded /
    no-DSN, §12). The driver lives ONLY in tmp: test_cog4_* files are not
    allowlisted cortex importers (boundary-manifest row 1), so this file holds
    NO framework.cortex import — the subprocess idiom the corpus itself uses.
  * objectives graph — built by the REAL CLI cabinet/scripts/cog3-rebuild.py,
    file-seeded (roots yaml + canonical cutoff), no DB.

Parity proven per §6.1 part: (a) canonical dialect — every stored JSONL line
byte-equals kernel.canonical_bytes of its re-parsed row, for BOTH stores;
(b) identity law — stored belief_id / node_id equal identity_digest of the
content-excluded identity tuple; (c) BOTH hash algebras — the kernel
chained_rows_hash reproduces fold-manifest.json belief_store_hash
(sha256-chain + domain seed + id-order) AND graph-manifest.json
graph_rows_hash (digest-list + empty seed + canonical-bytes order) exactly,
with negative controls proving the parity bites; (d) manifest envelope —
manifest_envelope() reconstructs both shipped manifests dict-equal;
(h) rollback grammar — kernel.rollback_delete then rebuild restores both
stores BYTE-identically (cache-delete reversible-by-rebuild).

S0: python3.12, no DB, no network; subprocess + tmp roots only (the COG-3
fixture idiom). Provenance: authored per the 2026-07-07 full-autonomy grant +
the 2026-07-20 cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent          # cabinet/scripts/tests
_REPO = _HERE.parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from framework.projection import kernel  # noqa: E402  (row-6 allowlisted glob)

_COG3_REBUILD = _REPO / "cabinet" / "scripts" / "cog3-rebuild.py"

# ---------------------------------------------------------------------------
# the domain parameters of the two shipped algebras (mirrored BY VALUE — the
# parity assertions against the shipped manifests are the drift tripwires)
# ---------------------------------------------------------------------------
_CORTEX_SEED = b"cortex-belief-hash/v1"          # belief.py _BELIEF_HASH_SEED


def _cortex_order(row: dict) -> str:
    return row["belief_id"]                       # belief.py id-order


def _cortex_normalize(row: dict) -> dict:
    """The hash_canonical_rows _sorted_row shape (cortex domain law, §6.2)."""
    out = dict(row)
    if isinstance(out.get("supersedes"), list):
        out["supersedes"] = sorted(out["supersedes"])
    if isinstance(out.get("contradicts"), list):
        out["contradicts"] = sorted(out["contradicts"])
    return out


def _cortex_rows_hash(rows) -> str:
    return kernel.chained_rows_hash(
        rows, algebra=kernel.ALGEBRA_SHA256_CHAIN, seed=_CORTEX_SEED,
        order_key=_cortex_order, normalize=_cortex_normalize)


def _objectives_rows_hash(rows) -> str:
    return kernel.chained_rows_hash(
        rows, algebra=kernel.ALGEBRA_DIGEST_LIST, seed="",
        order_key=kernel.canonical_bytes)


# ---------------------------------------------------------------------------
# real-store builders (shipped implementations, tmp roots)
# ---------------------------------------------------------------------------
_CORTEX_DRIVER = """\
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from framework.cortex import adapters, engine
TT = {"table_version": 1, "producers": {"officer_tasks/outbox-relay": 900000}}
def orow(row_id, task_id, new_status, *, event_id, old_status=None,
         old_blocked=None, new_blocked=False):
    return {"id": row_id, "event_id": event_id, "task_id": task_id,
            "old_status": old_status, "new_status": new_status,
            "old_blocked": old_blocked, "new_blocked": new_blocked,
            "blocked_reason": None, "actor": "cos", "context_slug": "cog1",
            "cabinet_id": "cog4-kernel", "correlation_id": f"corr{row_id:032d}",
            "causation_id": None,
            "occurred_at": f"2026-07-20T08:00:{row_id % 60:02d}Z"}
rows = [orow(1, 100, "wip", event_id="evt-1"),
        orow(2, 100, "wip", event_id="evt-2", old_status="wip",
             old_blocked=False, new_blocked=True),
        orow(3, 100, "wip", event_id="evt-3", old_status="wip",
             old_blocked=True, new_blocked=False),
        orow(4, 100, "done", event_id="evt-4", old_status="wip"),
        orow(5, 101, "queue", event_id="evt-5"),
        orow(6, 101, "cancelled", event_id="evt-6", old_status="queue")]
beliefs = engine.fold(adapters.build_proto_beliefs(rows), trust_table=TT)
manifest = engine.build_manifest(beliefs, trust_table=TT, frontier=6, max_id=6)
engine.write_projection(beliefs, manifest, Path(sys.argv[1]))
print(manifest["belief_store_hash"])
"""

_ROOTS_YML = """\
# fixture Captain-direction roots (COG-4 kernel parity)
directions:
  - slug: north
    statement: "Ship the cabinet \\u2014 verified value per unit of attention"
  - slug: quality
    statement: "Never trade determinism for speed"
  - slug: safety
    statement: "Shadow before authority"
"""

_CUTOFF = "2026-07-20T00:00:00Z"


def _build_cortex_store(store_dir: Path) -> str:
    """Run the tmp driver; returns the shipped fold's belief_store_hash."""
    driver = store_dir.parent / "cortex_driver.py"
    driver.write_text(_CORTEX_DRIVER, encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(driver), str(store_dir), str(_REPO)],
        capture_output=True, text=True, cwd=str(_REPO))
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _build_objectives_graph(cache_dir: Path, roots: Path) -> None:
    """Run the REAL cog3-rebuild CLI (file-seeded, no DB)."""
    r = subprocess.run(
        [sys.executable, str(_COG3_REBUILD), "--roots", str(roots),
         "--cache", str(cache_dir), "--cabinet-id", "cog4-kernel-parity",
         "--cutoff", _CUTOFF, "--json"],
        capture_output=True, text=True, cwd=str(_REPO))
    assert r.returncode == 0, r.stderr


@pytest.fixture(scope="module")
def cortex_store(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("cog4_kernel_cortex")
    store = root / "cortex"
    printed = _build_cortex_store(store)
    rows = kernel.read_jsonl_rows(store / "beliefs.jsonl")
    manifest = json.loads((store / "fold-manifest.json").read_text(encoding="utf-8"))
    assert rows, "driver built an empty belief store"
    return {"dir": store, "rows": rows, "manifest": manifest, "printed": printed}


@pytest.fixture(scope="module")
def objectives_store(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("cog4_kernel_objectives")
    roots = root / "directions.yml"
    roots.write_text(_ROOTS_YML, encoding="utf-8")
    cache = root / "objectives"
    _build_objectives_graph(cache, roots)
    rows = kernel.read_jsonl_rows(cache / "graph.jsonl")
    manifest = json.loads((cache / "graph-manifest.json").read_text(encoding="utf-8"))
    assert rows, "CLI built an empty graph"
    return {"dir": cache, "roots": roots, "rows": rows, "manifest": manifest}


# ===========================================================================
# (a) canonical dialect — writer bytes == kernel re-derived bytes, BOTH stores
# ===========================================================================
class TestCanonicalDialectParity:
    def _lines_roundtrip(self, path: Path):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                assert kernel.canonical_bytes(json.loads(line)).decode("utf-8") == line

    def test_cortex_store_lines_are_kernel_canonical(self, cortex_store):
        self._lines_roundtrip(cortex_store["dir"] / "beliefs.jsonl")

    def test_objectives_store_lines_are_kernel_canonical(self, objectives_store):
        self._lines_roundtrip(objectives_store["dir"] / "graph.jsonl")

    def test_dialect_shape(self):
        # sort_keys + compact separators + ensure_ascii=False + utf-8.
        assert kernel.canonical_bytes({"b": 1, "a": [2, 1]}) == b'{"a":[2,1],"b":1}'
        assert kernel.canonical_bytes({"k": "æøå"}) == '{"k":"æøå"}'.encode("utf-8")

    def test_digest_is_sha256_of_canonical_bytes(self):
        import hashlib
        v = {"x": ["y", 1]}
        assert kernel.digest(v) == hashlib.sha256(kernel.canonical_bytes(v)).hexdigest()


# ===========================================================================
# (b) the identity law — stored ids ARE digests of content-excluded tuples
# ===========================================================================
class TestIdentityLawParity:
    def test_cortex_belief_ids_are_identity_digests(self, cortex_store):
        for row in cortex_store["rows"]:
            assert row["belief_id"] == kernel.identity_digest({
                "kind": row["kind"],
                "subject_key": row["subject_key"],
                "dimension": row["dimension"],
                "event_id": row["provenance"]["event_id"],
                "adapter_ordinal": row["adapter_ordinal"],
            }), row["belief_id"]

    def test_objectives_node_ids_are_identity_digests(self, objectives_store):
        nodes = [r for r in objectives_store["rows"] if "node_id" in r]
        assert nodes
        for row in nodes:
            assert row["node_id"] == kernel.identity_digest(
                [row["kind"], row["subject_key"]])

    def test_identity_excludes_content_and_tracks_identity_fields(self):
        base = {"kind": "entity", "subject_key": "tasks/1", "dimension": "status",
                "event_id": "evt-9", "adapter_ordinal": 0}
        assert kernel.identity_digest(base) == kernel.identity_digest(dict(base))
        assert kernel.identity_digest(base) != kernel.identity_digest(
            {**base, "event_id": "evt-10"})


# ===========================================================================
# (c) BOTH hash algebras reproduce the SHIPPED store hashes byte-identically
# ===========================================================================
class TestChainedRowsHashParity:
    def test_cortex_algebra_reproduces_belief_store_hash(self, cortex_store):
        expected = cortex_store["manifest"]["belief_store_hash"]
        assert expected == cortex_store["printed"]
        assert _cortex_rows_hash(cortex_store["rows"]) == expected

    def test_objectives_algebra_reproduces_graph_rows_hash(self, objectives_store):
        expected = objectives_store["manifest"]["graph_rows_hash"]
        assert _objectives_rows_hash(objectives_store["rows"]) == expected

    def test_order_invariance_under_shuffle(self, cortex_store, objectives_store):
        # the total-order parameter makes arrival order irrelevant (C-F3).
        c = list(reversed(cortex_store["rows"]))
        o = list(reversed(objectives_store["rows"]))
        assert _cortex_rows_hash(c) == _cortex_rows_hash(cortex_store["rows"])
        assert _objectives_rows_hash(o) == _objectives_rows_hash(objectives_store["rows"])

    def test_negative_control_tampered_row_changes_hash(self, cortex_store,
                                                        objectives_store):
        # the parity gate BITES: a single tampered row breaks both algebras.
        c = [dict(r) for r in cortex_store["rows"]]
        c[0]["status"] = "asserted" if c[0]["status"] != "asserted" else "superseded"
        assert _cortex_rows_hash(c) != cortex_store["manifest"]["belief_store_hash"]
        o = [dict(r) for r in objectives_store["rows"]]
        o[0]["subject_key"] = o[0].get("subject_key", "") + "-tampered"
        assert _objectives_rows_hash(o) != objectives_store["manifest"]["graph_rows_hash"]

    def test_negative_control_wrong_algebra_is_not_parity(self, cortex_store):
        # the parameterization is load-bearing: the objectives algebra over the
        # cortex rows does NOT reproduce the cortex hash.
        wrong = kernel.chained_rows_hash(
            cortex_store["rows"], algebra=kernel.ALGEBRA_DIGEST_LIST, seed="",
            order_key=kernel.canonical_bytes)
        assert wrong != cortex_store["manifest"]["belief_store_hash"]

    def test_seed_type_confusion_fails_loud(self):
        with pytest.raises(ValueError):
            kernel.chained_rows_hash([], algebra=kernel.ALGEBRA_SHA256_CHAIN,
                                     seed="not-bytes", order_key=repr)
        with pytest.raises(ValueError):
            kernel.chained_rows_hash([], algebra=kernel.ALGEBRA_DIGEST_LIST,
                                     seed=b"not-str", order_key=repr)
        with pytest.raises(ValueError):
            kernel.chained_rows_hash([], algebra="md5-chain", seed=b"", order_key=repr)


# ===========================================================================
# (d) the manifest envelope reconstructs BOTH shipped manifests dict-equal
# ===========================================================================
class TestManifestEnvelopeParity:
    def _rebuild(self, manifest: dict, *, hash_key: str, count_keys: tuple):
        extra = {k: v for k, v in manifest.items()
                 if k not in {"schema_version", "epoch", hash_key, *count_keys}}
        return kernel.manifest_envelope(
            schema_version=manifest["schema_version"], epoch=manifest["epoch"],
            store_hash_key=hash_key, store_hash=manifest[hash_key],
            counts={k: manifest[k] for k in count_keys}, extra=extra)

    def test_cortex_fold_manifest_is_an_envelope(self, cortex_store):
        m = cortex_store["manifest"]
        assert self._rebuild(m, hash_key="belief_store_hash",
                             count_keys=("belief_count",)) == m

    def test_objectives_graph_manifest_is_an_envelope(self, objectives_store):
        m = objectives_store["manifest"]
        assert self._rebuild(m, hash_key="graph_rows_hash",
                             count_keys=("node_count", "edge_count")) == m

    def test_envelope_refuses_missing_hash_and_collisions(self):
        with pytest.raises(ValueError):
            kernel.manifest_envelope(schema_version="s/v1", epoch={},
                                     store_hash_key="store_hash", store_hash="")
        with pytest.raises(ValueError):
            kernel.manifest_envelope(schema_version="s/v1", epoch={},
                                     store_hash_key="store_hash", store_hash="h",
                                     extra={"epoch": {}})


# ===========================================================================
# (h) rollback grammar — cache-delete reversible-by-rebuild, BYTE-identical
# ===========================================================================
class TestRollbackGrammarParity:
    def _bytes(self, base: Path, names) -> dict:
        return {n: (base / n).read_bytes() for n in names}

    def test_cortex_delete_then_rebuild_restores_bytes(self, cortex_store):
        names = ("beliefs.jsonl", "fold-manifest.json")
        before = self._bytes(cortex_store["dir"], names)
        deleted = kernel.rollback_delete(cortex_store["dir"], filenames=names)
        assert len(deleted) == 2
        assert not any((cortex_store["dir"] / n).exists() for n in names)
        _build_cortex_store(cortex_store["dir"])
        assert self._bytes(cortex_store["dir"], names) == before

    def test_objectives_delete_then_rebuild_restores_bytes(self, objectives_store):
        names = ("graph.jsonl", "graph-manifest.json")
        before = self._bytes(objectives_store["dir"], names)
        deleted = kernel.rollback_delete(objectives_store["dir"], filenames=names)
        assert len(deleted) == 2
        _build_objectives_graph(objectives_store["dir"], objectives_store["roots"])
        assert self._bytes(objectives_store["dir"], names) == before

    def test_rollback_is_idempotent_and_jailed(self, tmp_path):
        assert kernel.rollback_delete(tmp_path, filenames=("absent.jsonl",)) == []
        with pytest.raises(ValueError):
            kernel.rollback_delete(tmp_path, filenames=("../escape.jsonl",))
        with pytest.raises(ValueError):
            kernel.rollback_delete(tmp_path, filenames=("/etc/hosts",))
