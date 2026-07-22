"""COG-2 UNIT 4 — corruption + gap gate (§8 sim 5, tests-first).

Plan: docs/plans/cognitive-core-phase-2-contract-2026-07-22.md §6 (serve-time
store-hash binding C-F15), §5.3 / §7.3 (frontier + retention → gap taxonomy),
§8 sim 5. The mechanical proof that a corrupt canonical store is NEVER served
from an intact index, and that a hole in the outbox id sequence is DETECTED and
classified (never bridged with fabricated beliefs).

Two proofs, both pure (no DB) plus a PG-backed realism arm:

  * SERVE-TIME HASH BINDING (C-F15): re-derive the chained hash from the
    re-parsed beliefs.jsonl ROWS (never file bytes — A-m11), compare to the
    fold-manifest belief_store_hash; a byte-flip / truncation / partial write
    ⇒ StoreCorruptError (REFUSE), no window where the corrupt store is served.
    Rebuild-from-zero over the (unchanged) source restores the pre-corruption
    hash.
  * GAP TAXONOMY (§8 sim 5, seen-set regression): the fold manifest records the
    outbox seen-set as intervals; a later fold's seen-set is regressed against
    the prior manifest. (a) a rollback-burned BIGSERIAL id = a benign hole;
    (b) a deleted row BELOW the frontier = a breach; (c) a genesis shift =
    a breach. Zero fabricated bridging beliefs.

The prompt-pinned negative-control mutants MUST fail: a SELF-HEALING store that
re-serves corrupted rows (verify=False); a gap SILENTLY BRIDGED; a HOLE-AS-BREACH
classifier (fails seed a); a FORWARD-WINDOW checker blind to below-frontier
deletion (fails seed b). Each rides a documented non-default seam.

S0: harness/CI pin PostgreSQL MAJOR 17. Interpreter python3.12.
"""
from __future__ import annotations

import copy
import importlib.util as _ilu
import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.cortex import adapters, belief, engine  # noqa: E402
from framework.cortex import query as cortex_query  # noqa: E402
from framework.fidelity import consequence  # noqa: E402


def _load(path: str, name: str):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


# hyphenated scripts (importlib, the falsifier-test idiom)
c2v = _load(str(_HERE.parent / "cog2-verifier.py"), "cog2_verifier")
c2bh = _load(str(_HERE.parent / "cog2-belief-hash.py"), "cog2_belief_hash")

# the relay harness re-exports EphemeralPG17 + seed_transition + pg_available
HR = _load(_ROOT + "/framework/outbox/tests/lib_relay_harness.py",
           "lib_relay_harness_cog2_corruption")
_PG_SKIP = pytest.mark.skipif(not HR.pg_available(), reason=HR.PG_SKIP_REASON)

# The UNIT-1 trust table (mirrors cabinet/config/cortex-source-trust.v1.yml).
TT = {"table_version": 1, "producers": {"officer_tasks/outbox-relay": 900000}}


def _orow(row_id, task_id, new_status, *, event_id, old_status=None,
          old_blocked=None, new_blocked=False, occurred_at=None,
          actor="cos", cabinet_id="cog1-harness"):
    return {
        "id": row_id, "event_id": event_id, "task_id": task_id,
        "old_status": old_status, "new_status": new_status,
        "old_blocked": old_blocked, "new_blocked": new_blocked,
        "blocked_reason": None, "actor": actor, "context_slug": "cog1",
        "cabinet_id": cabinet_id, "correlation_id": f"corr{row_id:032d}",
        "causation_id": None,
        "occurred_at": occurred_at or f"2026-07-20T08:00:{row_id % 60:02d}Z",
    }


def _sample_rows():
    """task 100: wip -> block -> unblock -> done; task 101: queue -> cancel."""
    return [
        _orow(1, 100, "wip", event_id="evt-1", old_status=None),
        _orow(2, 100, "wip", event_id="evt-2", old_status="wip",
              old_blocked=False, new_blocked=True),
        _orow(3, 100, "wip", event_id="evt-3", old_status="wip",
              old_blocked=True, new_blocked=False),
        _orow(4, 100, "done", event_id="evt-4", old_status="wip"),
        _orow(5, 101, "queue", event_id="evt-5", old_status=None),
        _orow(6, 101, "cancelled", event_id="evt-6", old_status="queue"),
    ]


def _fold(rows):
    return engine.fold(adapters.build_proto_beliefs(rows), trust_table=TT)


def _write(rows, cache_dir):
    beliefs = _fold(rows)
    ids = [int(r["id"]) for r in rows]
    manifest = engine.build_manifest(beliefs, trust_table=TT,
                                     frontier=max(ids), max_id=max(ids))
    engine.write_projection(beliefs, manifest, cache_dir)
    return manifest


# --- consequence stream seeding (§8 sim 5 day-file deletion) -----------------
# The consequence adapter reads the append-only JSONL ledger under
# CABINET_EVENT_LOG_DIR; a day-file is one consequence-events-YYYY-MM-DD.jsonl.
CTT = {"table_version": 1, "producers": {"framework/fidelity/consequence": 850000}}


@pytest.fixture
def cledger(tmp_path, monkeypatch):
    d = tmp_path / "events"
    d.mkdir()
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(d))
    monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
    return d


def _crow(ts, action, subject, *, actor_id="cos"):
    return {"ts": ts, "actor": {"kind": "officer", "id": actor_id}, "lane": "acting",
            "action": action, "subject": subject, "refs": []}


def _write_cday(ledger_dir, date, rows):
    """Append rows to a consequence day-file (one UTC day per file)."""
    with open(ledger_dir / f"consequence-events-{date}.jsonl", "a") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _ctriples():
    """The raw (file, line, row) triples the consequence seen-set is built from."""
    return list(consequence.iter_ledger_rows())


# ===========================================================================
# serve-time store-hash binding (C-F15)
# ===========================================================================

class TestServeTimeHashBinding:
    def test_intact_store_verifies_and_serves(self, tmp_path):
        manifest = _write(_sample_rows(), tmp_path)
        verified = cortex_query.verify_store(tmp_path)
        assert verified == manifest["belief_store_hash"]
        beliefs = cortex_query.load_beliefs_verified(tmp_path)
        assert len(beliefs) == 12

    def test_byte_flip_refuses_to_serve(self, tmp_path):
        _write(_sample_rows(), tmp_path)
        jsonl = tmp_path / "beliefs.jsonl"
        # a content byte-flip that keeps the line valid JSON (the hardest case:
        # an intact index would happily serve it) — the re-derived hash diverges.
        jsonl.write_text(jsonl.read_text().replace("tasks/100", "tasks/999", 1))
        with pytest.raises(cortex_query.StoreCorruptError, match="hash mismatch"):
            cortex_query.verify_store(tmp_path)
        with pytest.raises(cortex_query.StoreCorruptError):
            cortex_query.load_beliefs_verified(tmp_path)

    def test_truncated_store_refuses_to_serve(self, tmp_path):
        _write(_sample_rows(), tmp_path)
        jsonl = tmp_path / "beliefs.jsonl"
        lines = jsonl.read_text().splitlines()
        jsonl.write_text("\n".join(lines[:-1]) + "\n")   # drop the last belief
        with pytest.raises(cortex_query.StoreCorruptError):
            cortex_query.verify_store(tmp_path)

    def test_malformed_json_line_refuses_to_serve(self, tmp_path):
        _write(_sample_rows(), tmp_path)
        jsonl = tmp_path / "beliefs.jsonl"
        jsonl.write_text(jsonl.read_text() + '{"belief_id": "x", not-json\n')
        with pytest.raises(cortex_query.StoreCorruptError):
            cortex_query.verify_store(tmp_path)

    def test_missing_manifest_hash_refuses(self, tmp_path):
        _write(_sample_rows(), tmp_path)
        mpath = tmp_path / "fold-manifest.json"
        m = json.loads(mpath.read_text())
        del m["belief_store_hash"]
        mpath.write_text(json.dumps(m))
        with pytest.raises(cortex_query.StoreCorruptError):
            cortex_query.verify_store(tmp_path)

    def test_rebuild_from_zero_restores_pre_corruption_hash(self, tmp_path):
        rows = _sample_rows()
        manifest = _write(rows, tmp_path)
        good = manifest["belief_store_hash"]
        jsonl = tmp_path / "beliefs.jsonl"
        jsonl.write_text(jsonl.read_text().replace("done", "cancelled", 1))
        with pytest.raises(cortex_query.StoreCorruptError):
            cortex_query.verify_store(tmp_path)
        # rebuild-from-zero over the UNCHANGED source overwrites the corrupt
        # store; the deterministic fold reproduces the exact pre-corruption hash.
        restored = _write(copy.deepcopy(rows), tmp_path)
        assert restored["belief_store_hash"] == good
        assert cortex_query.verify_store(tmp_path) == good

    def test_mutant_self_healing_serves_corrupt_rows(self, tmp_path):
        """SELF-HEALING mutant (verify=False): serves whatever bytes are on disk
        — the negative control the serve-time binding kills."""
        _write(_sample_rows(), tmp_path)
        jsonl = tmp_path / "beliefs.jsonl"
        jsonl.write_text(jsonl.read_text().replace("tasks/100", "tasks/999", 1))
        # correct path refuses...
        with pytest.raises(cortex_query.StoreCorruptError):
            cortex_query.load_beliefs_verified(tmp_path)
        # ...the mutant serves the corrupted rows (proves the binding is load-bearing).
        served = cortex_query.load_beliefs_verified(tmp_path, verify=False)
        assert any(b.subject_key == "tasks/999" for b in served)

    def test_verifier_cli_refuses_corrupt_store(self, tmp_path, capsys):
        _write(_sample_rows(), tmp_path)
        assert c2v.main(["verify", "--cache-dir", str(tmp_path)]) == 0
        jsonl = tmp_path / "beliefs.jsonl"
        jsonl.write_text(jsonl.read_text().replace("tasks/100", "tasks/999", 1))
        assert c2v.main(["verify", "--cache-dir", str(tmp_path)]) == 1
        assert "REFUSE" in capsys.readouterr().out

    def test_toctou_rebuild_between_hash_and_serve_cannot_slip_bytes(
            self, tmp_path, monkeypatch):
        """F4 (C-F15 no-window): the serve path reads beliefs.jsonl EXACTLY ONCE,
        so the nightly rebuild's own os.replace landing AFTER the hash cannot swap
        in unhashed bytes. Race the read — the 1st read returns the intact (hashed)
        rows; ANY 2nd read returns a poisoned variant a concurrent rebuild could
        have written. The fixed one-read serve never performs that 2nd read, so
        the poison is never served (the old two-read path would hash intact then
        serve poison — this test fails on it: calls==2 and 'tasks/pwned' served)."""
        _write(_sample_rows(), tmp_path)
        intact = engine.read_beliefs_jsonl(tmp_path / "beliefs.jsonl")
        poisoned = copy.deepcopy(intact)
        poisoned[0] = {**poisoned[0], "subject_key": "tasks/pwned"}
        calls = {"n": 0}

        def racing(_path):
            calls["n"] += 1
            return intact if calls["n"] == 1 else poisoned

        monkeypatch.setattr(engine, "read_beliefs_jsonl", racing)
        served = cortex_query.load_beliefs_verified(tmp_path)
        assert calls["n"] == 1                       # ONE read — no TOCTOU window
        assert all(b.subject_key != "tasks/pwned" for b in served)
        assert len(served) == 12                     # the verified rows, intact


# ===========================================================================
# gap taxonomy — seen-set regression (§8 sim 5, A-M9/C-F14)
# ===========================================================================

def _seen(rows):
    """The manifest 'seen' block for a set of outbox rows (via the real fold)."""
    beliefs = _fold(rows)
    ids = [int(r["id"]) for r in rows]
    return engine.build_manifest(beliefs, trust_table=TT,
                                 frontier=max(ids), max_id=max(ids))["seen"]


class TestSeenSetRecorded:
    def test_manifest_records_outbox_seen_intervals(self):
        seen = _seen(_sample_rows())
        assert seen["stream_rank"] == 0
        assert seen["genesis"] == 1 and seen["max_seen"] == 6
        assert seen["intervals"] == [[1, 6]]            # contiguous
        assert seen["count"] == 6

    def test_seen_intervals_compress_a_hole(self):
        rows = [r for r in _sample_rows() if int(r["id"]) != 3]   # burn id 3
        seen = _seen(rows)
        assert seen["intervals"] == [[1, 2], [4, 6]]
        assert seen["genesis"] == 1 and seen["count"] == 5


class TestGapTaxonomy:
    def test_rollback_burned_hole_never_seen_is_benign(self):
        """(a) a BIGSERIAL id allocated then rolled back = a hole never seen in
        EITHER fold — benign, never a breach, never bridged."""
        rows = [r for r in _sample_rows() if int(r["id"]) != 3]   # id 3 burned pre-fold
        prior = _seen(rows)
        current = _seen(rows + [_orow(7, 102, "queue", event_id="evt-7")])
        verdict = c2v.classify_gaps(prior, current)
        assert verdict["status"] == "ok"
        assert verdict["regressions"] == []
        assert 3 in verdict["benign_holes"]

    def test_deleted_below_frontier_row_is_a_breach(self):
        """(b) a row that WAS folded is now gone (below the frontier) = a
        seen-set regression = breach."""
        prior = _seen(_sample_rows())                       # ids 1..6 seen
        current = _seen([r for r in _sample_rows() if int(r["id"]) != 2])  # id 2 deleted
        verdict = c2v.classify_gaps(prior, current, frontier=6)
        assert verdict["status"] == "breach"
        assert 2 in verdict["regressions"]

    def test_genesis_shift_is_a_breach(self):
        """(c) the earliest seen id moved up = source history truncated = breach."""
        prior = _seen(_sample_rows())                       # genesis 1
        current = _seen([r for r in _sample_rows() if int(r["id"]) not in (1, 2)])
        verdict = c2v.classify_gaps(prior, current)
        assert verdict["status"] == "breach"
        assert verdict["genesis_shift"] is True

    def test_no_fabricated_bridging_beliefs(self):
        # the classifier reports the gap; it never invents a belief to fill it.
        prior = _seen(_sample_rows())
        current = _seen([r for r in _sample_rows() if int(r["id"]) != 2])
        verdict = c2v.classify_gaps(prior, current, frontier=6)
        assert "bridged" not in verdict and "fabricated" not in verdict
        assert verdict.get("regressions")            # detected, not filled

    def test_mutant_hole_as_breach_flags_benign_hole(self):
        """HOLE-AS-BREACH mutant (fails seed a): any sequence hole => breach,
        so the benign rollback-burned hole is wrongly flagged."""
        rows = [r for r in _sample_rows() if int(r["id"]) != 3]
        prior = _seen(rows)
        current = _seen(rows + [_orow(7, 102, "queue", event_id="evt-7")])
        assert c2v.classify_gaps(prior, current)["status"] == "ok"
        assert c2v.classify_gaps(prior, current, mode="hole_as_breach")["status"] == "breach"

    def test_mutant_forward_window_misses_below_frontier_deletion(self):
        """FORWARD-WINDOW mutant (fails seed b): only ids >= frontier examined,
        so a deleted row below the frontier is invisible."""
        prior = _seen(_sample_rows())
        current = _seen([r for r in _sample_rows() if int(r["id"]) != 2])
        assert c2v.classify_gaps(prior, current, frontier=6)["status"] == "breach"
        mutant = c2v.classify_gaps(prior, current, frontier=6, mode="forward_window")
        assert mutant["status"] == "ok"     # the below-frontier deletion is missed


# ===========================================================================
# consequence-stream gap taxonomy (§8 sim 5): a deleted day-file is a breach on
# stable (file, line) coordinates — the ids-only seen-set structurally misses it
# ===========================================================================

class TestConsequenceGapTaxonomy:
    def test_manifest_records_consequence_seen_set(self, cledger):
        _write_cday(cledger, "2026-07-20",
                    [_crow("2026-07-20T08:00:00Z", "ship", "rel/1"),
                     _crow("2026-07-20T09:00:00Z", "label", "rel/2")])
        triples = _ctriples()
        beliefs = engine.fold(
            adapters.build_consequence_protos(triples, local_cabinet_id="main"),  # D1 §6.1
            trust_table=CTT)
        manifest = engine.build_manifest(beliefs, trust_table=CTT, frontier=None,
                                         max_id=None, consequence_rows=triples)
        sc = manifest["seen_consequence"]
        assert sc["stream_rank"] == 1 and sc["count"] == 2
        day = sc["files"]["consequence-events-2026-07-20.jsonl"]
        assert day["intervals"] == [[1, 2]] and day["count"] == 2
        # ADDITIVE: the default outbox-only rebuild carries NO consequence block.
        assert "seen_consequence" not in engine.build_manifest(
            beliefs, trust_table=CTT, frontier=None, max_id=None)

    def test_consequence_day_file_deletion_is_a_breach(self, cledger):
        # prior: two day-files (a day-file loss is a GAP, not a purge — §5.4b:
        # the consequence domain has no purge mechanism this phase).
        _write_cday(cledger, "2026-07-20",
                    [_crow("2026-07-20T08:00:00Z", "ship", "rel/1"),
                     _crow("2026-07-20T09:00:00Z", "label", "rel/2")])
        _write_cday(cledger, "2026-07-21", [_crow("2026-07-21T08:00:00Z", "ship", "rel/3")])
        prior = engine.consequence_seen(_ctriples())
        (cledger / "consequence-events-2026-07-20.jsonl").unlink()   # delete a day
        current = engine.consequence_seen(_ctriples())
        verdict = c2v.classify_gaps({}, {}, prior_consequence=prior,
                                    current_consequence=current)
        assert verdict["status"] == "breach"
        assert verdict["consequence"]["keyed"] == "file_line"
        assert ("consequence-events-2026-07-20.jsonl"
                in verdict["consequence"]["deleted_files"])
        # detected, NEVER bridged with a fabricated belief.
        assert "bridged" not in verdict and "fabricated" not in verdict

    def test_consequence_row_deletion_shrinks_coverage_is_a_breach(self, cledger):
        _write_cday(cledger, "2026-07-20",
                    [_crow("2026-07-20T08:00:00Z", "ship", "rel/1"),
                     _crow("2026-07-20T09:00:00Z", "label", "rel/2"),
                     _crow("2026-07-20T10:00:00Z", "note", "rel/3")])
        prior = engine.consequence_seen(_ctriples())
        # drop the LAST row of the surviving day-file -> line coverage shrinks.
        p = cledger / "consequence-events-2026-07-20.jsonl"
        p.write_text("".join(p.read_text().splitlines(keepends=True)[:-1]))
        current = engine.consequence_seen(_ctriples())
        verdict = c2v.classify_gaps({}, {}, prior_consequence=prior,
                                    current_consequence=current)
        assert verdict["status"] == "breach"
        assert verdict["consequence"]["regressed_lines"][
            "consequence-events-2026-07-20.jsonl"] == [3]

    def test_mutant_ids_only_seen_set_misses_day_file_deletion(self, cledger):
        """IDS-ONLY seen-set (engine.consequence_seen key='seq') mirrors the
        re-enumerated belief intra_stream_seq. A day-file deletion MASKED by an
        append to another file renumbers the survivors into the SAME dense range,
        so an id regression sees nothing — MISSED. The correct (file, line)
        seen-set catches the same deletion (the day-20 basename vanishes)."""
        _write_cday(cledger, "2026-07-20",
                    [_crow("2026-07-20T08:00:00Z", "ship", "rel/1"),
                     _crow("2026-07-20T09:00:00Z", "label", "rel/2"),
                     _crow("2026-07-20T10:00:00Z", "note", "rel/3")])
        _write_cday(cledger, "2026-07-21",
                    [_crow("2026-07-21T08:00:00Z", "ship", "rel/4"),
                     _crow("2026-07-21T09:00:00Z", "label", "rel/5"),
                     _crow("2026-07-21T10:00:00Z", "note", "rel/6")])
        prior_triples = _ctriples()
        prior_good = engine.consequence_seen(prior_triples)
        prior_ids = engine.consequence_seen(prior_triples, key="seq")
        # delete day-20 AND append 3 rows to day-21 so the TOTAL count (the dense
        # id range) is PRESERVED — the deletion is masked from an ids-only view.
        (cledger / "consequence-events-2026-07-20.jsonl").unlink()
        _write_cday(cledger, "2026-07-21",
                    [_crow("2026-07-21T11:00:00Z", "ship", "rel/7"),
                     _crow("2026-07-21T12:00:00Z", "label", "rel/8"),
                     _crow("2026-07-21T13:00:00Z", "note", "rel/9")])
        cur_triples = _ctriples()
        assert len(cur_triples) == len(prior_triples) == 6      # count preserved
        cur_good = engine.consequence_seen(cur_triples)
        cur_ids = engine.consequence_seen(cur_triples, key="seq")
        # CORRECT (file, line): the vanished day-20 basename is a breach.
        good = c2v.classify_gaps({}, {}, prior_consequence=prior_good,
                                 current_consequence=cur_good)
        assert good["status"] == "breach"
        assert ("consequence-events-2026-07-20.jsonl"
                in good["consequence"]["deleted_files"])
        # MUTANT ids-only: the dense range is unchanged -> no regression -> MISS.
        mutant = c2v.classify_gaps({}, {}, prior_consequence=prior_ids,
                                   current_consequence=cur_ids)
        assert mutant["status"] == "ok"
        assert mutant["consequence"]["keyed"] == "seq"


# ===========================================================================
# PG-backed realism: a real BIGSERIAL rollback burns an id (benign hole)
# ===========================================================================

@_PG_SKIP
class TestGapOverPostgres:
    @pytest.fixture(scope="class")
    def cluster(self, tmp_path_factory):
        c = HR.EphemeralPG17(tmp_path_factory.mktemp("cog2gap"), cabinet_id=HR.CAB_ID)
        try:
            c.start()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"could not start ephemeral PG17: {e}")
        try:
            c.apply_base_chain()
            c.apply_identity_guc(HR.CAB_ID)
            c.apply_047()
            yield c
        finally:
            c.stop()

    def _read_seen(self, pg):
        protos, frontier, max_id = adapters.read_and_build(pg.conninfo())
        beliefs = engine.fold(protos, trust_table=TT)
        return engine.build_manifest(beliefs, trust_table=TT, frontier=frontier,
                                     max_id=max_id)["seen"]

    def test_real_rollback_burned_id_is_a_benign_hole(self, cluster):
        cluster.psql("TRUNCATE officer_tasks_outbox RESTART IDENTITY;")
        a = HR.seed_transition(cluster, "start", "cos")
        HR.seed_transition(cluster, "done", "cos", task_id=a)
        cluster.psql("UPDATE officer_tasks_outbox SET event_id = 'evt-' || id;")
        prior = self._read_seen(cluster)
        # a rolled-back INSERT burns the next BIGSERIAL id, leaving a hole.
        cluster.psql("BEGIN; "
                     "INSERT INTO officer_tasks_outbox (idempotency_key, task_id, "
                     "new_status, actor, cabinet_id, correlation_id, payload) VALUES "
                     "('burn', 999, 'wip', 'x', 'cog1-harness', "
                     "replace(gen_random_uuid()::text,'-',''), '{}'::jsonb); ROLLBACK;")
        b = HR.seed_transition(cluster, "queue", "cpo")
        cluster.psql("UPDATE officer_tasks_outbox SET event_id = 'evt-' || id "
                     "WHERE event_id IS NULL;")
        current = self._read_seen(cluster)
        assert current["genesis"] == prior["genesis"]        # no genesis shift
        verdict = c2v.classify_gaps(prior, current)
        assert verdict["status"] == "ok"                     # the burned id is benign
        assert verdict["regressions"] == []
