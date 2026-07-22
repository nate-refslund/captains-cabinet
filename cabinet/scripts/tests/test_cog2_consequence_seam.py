"""COG-2 UNIT 3 — the consequence-ledger SEAM (§3 A-M6/C-F5/O-B2, tests-first).

The thin slice's ONE legacy adapter. What it proves is the SEAM (§2, A-m12) —
NOT "hardest translation" (withdrawn) and NOT cross-time supersession (the
ledger identity tuple is ts-INCLUSIVE — consequence.py:515-528 — so the same
(actor, action, subject) at different ts never supersedes by construction):

  * TRANSLATION-vs-COLLAPSE EQUIVALENCE (§3): the additive iter_ledger_rows()
    carries EVERY row read_ledger()'s last-write-wins collapse needs — the
    adapter's per-identity chain HEADS equal read_ledger()'s survivors.
  * DETERMINISTIC SYNTHETIC PROVENANCE (§5.4): a legacy row has no event_id, so
    the adapter mints a deterministic one — digest("consequence:" + canonical
    row) — reproduced byte-for-byte across builds; producer + stream_rank pinned.
  * LEGACY-REGIME BELIEF VALIDATION (A-M7): a consequence-derived belief
    validates at the BELIEF level even though the source row is NOT a v2
    envelope (validate_any is never forced on it — §3).
  * ENV-FREE FOLD (O-B2 / §5.1): the fold's sim-row policy is UNCONDITIONAL —
    iter_ledger_rows drops sim rows regardless of CABINET_SIM_MODE, unlike
    read_ledger which is env-sensitive. No environment variable is a fold input.
  * ts PARSE-OR-ABSENT (C-F6): the adapter parses ts to the single canonical
    UTC-second spelling or yields honest absence — NEVER a garbage passthrough.

REVERSE-IMPORT DISCIPLINE (§7.1 G-F1): the adapter imports ONLY iter_ledger_rows
from framework.fidelity.consequence; the domain's OWN fences (_safe_ledger_files
symlink fence + _is_consequence_row shape filter) are reused, never cloned. This
test may import consequence._identity to build the expected collapse (tests are
not bound by the reverse gate); the adapter mirrors that identity inline and this
equivalence test is the standing drift tripwire.

S0: interpreter python3.12. No DB — the ledger is local JSONL.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
for _p in (str(_HERE), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from framework.cortex import adapters, belief, engine  # noqa: E402
from framework.fidelity import consequence  # noqa: E402

# The consequence adapter's declared producer (mirrors the extended
# cortex-source-trust.v1.yml / source-trust.v1.json enum). Component identity,
# never an officer identity (the G-F4 never-a-score latch).
CONSEQUENCE_PRODUCER = "framework/fidelity/consequence"
TT = {"table_version": 1, "producers": {CONSEQUENCE_PRODUCER: 850000}}


@pytest.fixture
def ledger_dir(tmp_path, monkeypatch):
    """An isolated consequence-ledger dir wired through CABINET_EVENT_LOG_DIR
    (the same operator-set env consequence.py reads). Sim mode OFF by default."""
    d = tmp_path / "events"
    d.mkdir()
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(d))
    monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
    return d


def _row(ts, action, subject, *, kind="officer", actor_id="cos", **extra):
    """A schema-valid consequence event. Enrichment = the SAME identity tuple
    (actor, action, subject, ts) with extra lifecycle fields (outcome/review)."""
    row = {"ts": ts, "actor": {"kind": kind, "id": actor_id}, "lane": "acting",
           "action": action, "subject": subject, "refs": []}
    row.update(extra)
    return row


def _write_day(ledger_dir, date, rows):
    path = ledger_dir / f"consequence-events-{date}.jsonl"
    with open(path, "a") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    return path


def _sk(row):
    """The subject_key the adapter derives — 'consequence/' + digest of the
    ledger's OWN ts-inclusive identity tuple (consequence._identity)."""
    return "consequence/" + belief.digest(list(consequence._identity(row)))


def _protos(ledger_dir=None):
    # D1 (§6.1): build_consequence_protos now requires the DECLARED local
    # cabinet_id scope stamp (mirroring build_envelope_protos(*, local_cabinet_id)).
    return adapters.build_consequence_protos(
        list(consequence.iter_ledger_rows()), local_cabinet_id="main")


def _fold(ledger_dir=None):
    return engine.fold(_protos(), trust_table=TT)


# ===========================================================================
# iter_ledger_rows: history-preserving, additive (read_ledger byte-unchanged)
# ===========================================================================

class TestIterLedgerRows:
    def test_yields_all_history_no_collapse(self, ledger_dir):
        a = _row("2026-07-20T08:00:00Z", "task_status_move", "task/1")
        a2 = _row("2026-07-20T08:00:00Z", "task_status_move", "task/1",
                  outcome={"status": "ok", "evidence": "done"})   # enrichment
        b = _row("2026-07-20T09:00:00Z", "label", "task/2")
        _write_day(ledger_dir, "2026-07-20", [a, a2, b])
        raw = list(consequence.iter_ledger_rows())
        # ALL THREE rows survive raw iteration (no LWW), (file, line) carried.
        assert len(raw) == 3
        assert [(Path(f).name, ln) for (f, ln, _r) in raw] == [
            ("consequence-events-2026-07-20.jsonl", 1),
            ("consequence-events-2026-07-20.jsonl", 2),
            ("consequence-events-2026-07-20.jsonl", 3)]
        # read_ledger COLLAPSES a,a2 -> a2 and keeps b: 2 survivors (unchanged).
        assert len(consequence.read_ledger()) == 2

    def test_skips_malformed_json_lines(self, ledger_dir):
        path = ledger_dir / "consequence-events-2026-07-20.jsonl"
        with open(path, "w") as handle:
            handle.write(json.dumps(_row("2026-07-20T08:00:00Z", "label", "task/1")) + "\n")
            handle.write("{ not valid json\n")
            handle.write(json.dumps(_row("2026-07-20T09:00:00Z", "label", "task/2")) + "\n")
        raw = list(consequence.iter_ledger_rows())
        assert {r["subject"] for (_f, _l, r) in raw} == {"task/1", "task/2"}

    def test_skips_non_consequence_rows(self, ledger_dir):
        # a co-located org_events-shaped row (string actor) is shape-filtered out
        # by the module's OWN _is_consequence_row (reused, never cloned).
        path = ledger_dir / "consequence-events-2026-07-20.jsonl"
        with open(path, "w") as handle:
            handle.write(json.dumps(_row("2026-07-20T08:00:00Z", "label", "task/1")) + "\n")
            handle.write(json.dumps({"actor": "string-actor", "kind": "org"}) + "\n")
        raw = list(consequence.iter_ledger_rows())
        assert {r["subject"] for (_f, _l, r) in raw} == {"task/1"}

    def test_missing_dir_yields_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "nope"))
        assert list(consequence.iter_ledger_rows()) == []


# ===========================================================================
# translation-vs-collapse EQUIVALENCE (§3): chain-heads == read_ledger survivors
# ===========================================================================

class TestSeamEquivalence:
    def _seed(self, ledger_dir, tmp_path):
        # multi-day history + enrichment (same-ts) + a sim row + a symlink that
        # escapes the dir — the fences and the collapse must agree on all of it.
        a = _row("2026-07-20T08:00:00Z", "task_status_move", "task/1")
        a2 = _row("2026-07-20T08:00:00Z", "task_status_move", "task/1",
                  proposal={"required": True, "decision": "approved"})   # enrichment
        b = _row("2026-07-20T09:00:00Z", "label", "task/2")
        sim = _row("2026-07-20T09:30:00Z", "label", "task/SIM")
        sim["sim"] = True                                    # dropped by BOTH
        _write_day(ledger_dir, "2026-07-20", [a, a2, b, sim])
        c = _row("2026-07-21T08:00:00Z", "tier2_note", "task/3")
        c2 = _row("2026-07-21T08:00:00Z", "tier2_note", "task/3",
                  outcome={"status": "ok", "evidence": "landed"})        # enrichment
        _write_day(ledger_dir, "2026-07-21", [c, c2])
        # a valid consequence file OUTSIDE the dir, symlinked in under a ledger
        # name — _safe_ledger_files must refuse it (both readers).
        outside = tmp_path / "escape.jsonl"
        outside.write_text(json.dumps(
            _row("2026-07-22T08:00:00Z", "label", "task/OUTSIDE")) + "\n")
        (ledger_dir / "consequence-events-2026-07-22.jsonl").symlink_to(outside)
        return a, a2, b, c, c2

    def test_chain_heads_equal_read_ledger_survivors(self, ledger_dir, tmp_path):
        self._seed(ledger_dir, tmp_path)
        survivors = consequence.read_ledger()               # the domain's own LWW
        beliefs = _fold()
        heads = [x for x in beliefs if x.superseded_by is None]
        assert len(heads) == len(survivors) == 3            # task/1, task/2, task/3
        surv_by_sk = {_sk(s): s for s in survivors}
        assert {h.subject_key for h in heads} == set(surv_by_sk)
        for head in heads:
            # translation head == collapse survivor (claim IS the surviving row)
            assert head.claim == surv_by_sk[head.subject_key]

    def test_symlinked_escape_and_sim_row_are_invisible_to_both(self, ledger_dir, tmp_path):
        self._seed(ledger_dir, tmp_path)
        raw_subjects = {r["subject"] for (_f, _l, r) in consequence.iter_ledger_rows()}
        # the escaping symlink and the sim row are absent from raw iteration...
        assert "task/OUTSIDE" not in raw_subjects and "task/SIM" not in raw_subjects
        # ...and from read_ledger (the fences + sim policy agree).
        assert {e["subject"] for e in consequence.read_ledger()} == {
            "task/1", "task/2", "task/3"}


# ===========================================================================
# enrichment supersedes by SOURCE ORDER (ts-inclusive identity => no cross-time)
# ===========================================================================

class TestConsequenceSupersession:
    def test_enrichment_supersedes_original_lineage_intact(self, ledger_dir):
        a = _row("2026-07-20T08:00:00Z", "task_status_move", "task/1")
        a2 = _row("2026-07-20T08:00:00Z", "task_status_move", "task/1",
                  outcome={"status": "ok", "evidence": "done"})
        _write_day(ledger_dir, "2026-07-20", [a, a2])
        beliefs = _fold()
        group = [x for x in beliefs if x.subject_key == _sk(a)]
        assert len(group) == 2                              # both stored (no erase)
        head = [x for x in group if x.superseded_by is None][0]
        old = [x for x in group if x.superseded_by is not None][0]
        assert head.claim == a2 and head.status == "asserted"
        assert old.status == "superseded"
        assert head.supersedes == (old.belief_id,)          # lineage preserved

    def test_distinct_ts_never_supersedes_ts_inclusive_identity(self, ledger_dir):
        # the ledger identity is ts-INCLUSIVE, so the SAME (actor, action,
        # subject) at two different ts is TWO subjects — never a supersession
        # (the seam proves translation, not cross-time supersession — A-m12).
        a = _row("2026-07-20T08:00:00Z", "task_status_move", "task/1")
        b = _row("2026-07-20T09:00:00Z", "task_status_move", "task/1")
        _write_day(ledger_dir, "2026-07-20", [a, b])
        beliefs = _fold()
        assert _sk(a) != _sk(b)                             # two distinct subjects
        assert all(x.superseded_by is None for x in beliefs)  # neither supersedes
        assert len(beliefs) == 2


# ===========================================================================
# deterministic synthetic provenance (documented formula) + pinned fields
# ===========================================================================

class TestSyntheticProvenance:
    def test_synthetic_event_id_is_deterministic_and_documented(self, ledger_dir):
        a = _row("2026-07-20T08:00:00Z", "task_status_move", "task/1")
        _write_day(ledger_dir, "2026-07-20", [a])
        protos1 = _protos()
        protos2 = _protos()
        assert protos1 == protos2                           # byte-stable across builds
        prov = protos1[0]["provenance"]
        # DOCUMENTED formula: digest("consequence:" + canonical row bytes).
        expect = belief.digest("consequence:" + belief.canonical_bytes(a).decode("utf-8"))
        assert prov["event_id"] == expect and len(prov["event_id"]) == 64
        assert prov["producer"] == CONSEQUENCE_PRODUCER
        assert prov["stream_rank"] == 1                     # RANK_TABLE["consequence"]
        assert protos1[0]["kind"] == "observation"
        assert protos1[0]["dimension"] == "consequence"
        assert protos1[0]["adapter_ordinal"] == 0

    def test_distinct_rows_get_distinct_synthetic_ids(self, ledger_dir):
        a = _row("2026-07-20T08:00:00Z", "task_status_move", "task/1")
        a2 = _row("2026-07-20T08:00:00Z", "task_status_move", "task/1",
                  outcome={"status": "ok", "evidence": "done"})
        _write_day(ledger_dir, "2026-07-20", [a, a2])
        ids = {p["provenance"]["event_id"] for p in _protos()}
        assert len(ids) == 2                                # per-row synthetic id


# ===========================================================================
# legacy-regime belief validation (A-M7): validates at the BELIEF level
# ===========================================================================

class TestLegacyRegimeValidation:
    def test_consequence_belief_validates_at_belief_level(self, ledger_dir):
        a = _row("2026-07-20T08:00:00Z", "task_status_move", "task/1")
        b = _row("2026-07-20T09:00:00Z", "label", "task/2",
                 outcome={"status": "ok", "evidence": "e"})
        _write_day(ledger_dir, "2026-07-20", [a, b])
        beliefs = _fold()
        assert beliefs
        for x in beliefs:
            # validates against cortex/belief@1 + cortex/source-trust@1 even
            # though the source row is NOT a v2 envelope (validate_any unforced).
            assert belief.validate_belief(x) == ()
            # universal provenance minimum present on every belief (M4).
            assert x.provenance["event_id"] and x.provenance["producer"]
            assert x.provenance["stream_rank"] == 1
            # source_trust carries the consequence producer (enum extended).
            assert x.source_trust["producer_key"] == CONSEQUENCE_PRODUCER

    def test_confidence_derived_from_trust_table(self, ledger_dir):
        a = _row("2026-07-20T08:00:00Z", "task_status_move", "task/1")
        _write_day(ledger_dir, "2026-07-20", [a])
        x = _fold()[0]
        assert x.confidence == 850000                       # ppm from TT
        assert x.source_trust == {"table_version": 1,
                                  "producer_key": CONSEQUENCE_PRODUCER}


# ===========================================================================
# ts parse-or-absent (C-F6): canonical UTC-second or honest absence, never garbage
# ===========================================================================

class TestTsParseOrAbsent:
    def test_fractional_offset_canonicalized_garbage_absent(self, ledger_dir):
        good = _row("2026-07-20T08:00:00.123456Z", "label", "task/1")     # fractional
        offset = _row("2026-07-20T10:00:00+02:00", "label", "task/2")     # offset
        garbage = _row("not-a-timestamp", "label", "task/3")              # garbage
        _write_day(ledger_dir, "2026-07-20", [good, offset, garbage])
        by_sk = {p["subject_key"]: p for p in _protos()}
        assert by_sk[_sk(good)]["source_time"] == "2026-07-20T08:00:00Z"   # canonical
        assert by_sk[_sk(offset)]["source_time"] == "2026-07-20T08:00:00Z"  # -> UTC
        assert by_sk[_sk(garbage)]["source_time"] is None                  # honest absence
        assert by_sk[_sk(garbage)]["observation_time"] is None             # both axes
        # a canonically-parsed row still validates and folds.
        beliefs = _fold()
        for x in beliefs:
            assert belief.validate_belief(x) == ()


# ===========================================================================
# ENV-FREE FOLD (O-B2): iter_ledger_rows drops sim rows UNCONDITIONALLY
# ===========================================================================

class TestEnvFreeFold:
    def test_iter_drops_sim_regardless_of_env_read_ledger_does_not(self, ledger_dir, monkeypatch):
        live = _row("2026-07-20T08:00:00Z", "label", "task/1")
        sim = _row("2026-07-20T09:00:00Z", "label", "task/2")
        sim["sim"] = True
        _write_day(ledger_dir, "2026-07-20", [live, sim])

        # default (non-sim): iter drops the sim row.
        raw_default = list(consequence.iter_ledger_rows())
        assert [r["subject"] for (_f, _l, r) in raw_default] == ["task/1"]

        # sim mode ON: iter STILL drops it (env-free fold — no env branch, O-B2).
        monkeypatch.setenv("CABINET_SIM_MODE", "1")
        raw_sim = list(consequence.iter_ledger_rows())
        assert raw_sim == raw_default

        # read_ledger, by contrast, IS env-sensitive — it keeps the sim row in
        # sim mode (the contrast that makes the env-free property meaningful).
        assert {e["subject"] for e in consequence.read_ledger()} == {"task/1", "task/2"}
        monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
        assert {e["subject"] for e in consequence.read_ledger()} == {"task/1"}

    def test_folded_beliefs_never_include_a_sim_row(self, ledger_dir, monkeypatch):
        live = _row("2026-07-20T08:00:00Z", "label", "task/1")
        sim = _row("2026-07-20T09:00:00Z", "label", "task/2")
        sim["sim"] = True
        _write_day(ledger_dir, "2026-07-20", [live, sim])
        monkeypatch.setenv("CABINET_SIM_MODE", "1")         # even in sim mode
        beliefs = _fold()
        assert {b.claim["subject"] for b in beliefs} == {"task/1"}


# ===========================================================================
# F1 (review): duplicate-row dedupe — a double-emit retry within one second
# (log_consequence stamps no nonce; ts is second-resolution) writes a
# byte-identical row. The fold collapses it FIRST-OCCURRENCE-WINS (honoring
# read_ledger's own collapse + sim-1's shuffle/dup-invariance) instead of
# crashing the whole rebuild on the divergent-content identity guard.
# ===========================================================================
class TestDuplicateRowDedupe:

    def test_byte_identical_dup_collapses_to_one_no_crash(self, ledger_dir):
        r = _row("2026-07-20T03:00:00Z", "ship", "release-9")
        _write_day(ledger_dir, "2026-07-20", [r, dict(r)])   # exact double-emit
        protos = _protos()
        assert len(protos) == 1
        _fold()                                              # must not raise

    def test_key_reordered_dup_collapses_to_one(self, ledger_dir):
        r = _row("2026-07-20T03:00:00Z", "ship", "release-9")
        reordered = dict(reversed(list(r.items())))          # same content, other order
        _write_day(ledger_dir, "2026-07-20", [r, reordered])
        assert len(_protos()) == 1

    def test_dedupe_first_occurrence_deterministic(self, ledger_dir):
        a = _row("2026-07-20T03:00:00Z", "ship", "release-9")
        b = _row("2026-07-20T03:00:01Z", "ship", "release-9", outcome="ok")
        _write_day(ledger_dir, "2026-07-20", [a, dict(a), b])  # dup of a, then b
        p1, p2 = _protos(), _protos()
        ids = lambda ps: [x["provenance"]["event_id"] for x in ps]
        assert ids(p1) == ids(p2)                            # deterministic
        assert len(p1) == 2                                  # a(first) + b, not 3
