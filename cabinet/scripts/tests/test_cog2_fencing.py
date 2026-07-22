"""COG-2 UNIT 4 — cross-cabinet + boundary fence gate (§8 sim 7, tests-first).

The mechanical proof that a cross-cabinet envelope is QUARANTINED at ingest
(never folded into the local projection) and that a cross-cabinet / foreign /
unresolvable-scope query fails CLOSED with a HARD ERROR (ScopeError) — never an
empty-success that lets an attacker distinguish "denied" from "no data" by the
emptiness of the answer.

Two fences, two surfaces (§7.4 / C-F19):

  * INGEST (framework.cortex.adapters._envelope_scope_reason): a fail-closed
    scope check on a validate_any-passing v2 envelope. It OWNS three refusals so
    a cross-cabinet envelope never reaches the fold:
      - classification == "cross_cabinet" — a VALID taint tier (envelope
        .TAINT_TIERS = captain/officer/system/cross_cabinet/external) that PASSES
        validate_any, so the validator never stops it; a cross_cabinet envelope
        carrying a LOCAL cabinet_id would otherwise FOLD (the pinned leak). The
        fence refuses it REGARDLESS of cabinet_id.
      - absent cabinet_id — absent is never local, fail closed.
      - foreign cabinet_id — not the local cabinet.
    Every refusal writes a QUARANTINE RECEIPT; a silent skip is itself a pinned
    mutant failure (a silent drop is an undetected loss).

  * QUERY (framework.cortex.query.as_of scope gate, unit 2): a missing /
    unresolvable / foreign scope is a HARD ERROR (ScopeError), never
    empty-success; a scoped query over a mixed local+foreign store leaks NO
    foreign belief (in_scope filters on provenance.cabinet_id).

Negative controls (MUST fail):
  * a cross_cabinet-classified envelope FOLDED (a proto produced) instead of
    quarantined — the fence gap this unit closes (pinned by the direct
    _envelope_scope_reason unit test AND the ingest quarantine assertions).
  * quarantine-WITHOUT-a-receipt / a silently-skipped refused line.
  * the cross_cabinet refusal rejecting a NORMAL local system-classification
    envelope (over-fencing — would break unit 2/3; pinned by the allow tests).
  * an empty-success query fence (empty views, no error) instead of a hard
    ScopeError — the documented scope_mode="lenient" mutant seam; an attacker
    must not read denial as ignorance.

S0: interpreter python3.12. No DB — the envelope-file adapter reads a JSONL and
the query folds an in-memory belief list (the sim-3 discipline).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
for _p in (str(_HERE), _ROOT):          # tests/ is a package: put it on the path
    if _p not in sys.path:
        sys.path.insert(0, _p)

from framework.cortex import adapters, engine, query  # noqa: E402
from framework.triggers import envelope as _envelope  # noqa: E402
import lib_cog2_envelope as L  # noqa: E402

TT = L.TRUST_TABLE
MAIN = {"cabinet_id": "main"}
S1 = "2026-07-20T00:00:00Z"
O1 = "2026-07-20T01:00:00Z"


# ---------------------------------------------------------------------------
# helpers — build a JSONL the PRODUCTION adapter reads read-only (no test seam)
# ---------------------------------------------------------------------------

def _ingest(tmp_path, envs, *, local="main", name="fence.jsonl"):
    """(protos, receipts) straight from the production read_envelope_file path —
    NOT asserting a clean run (sim 7 WANTS the quarantines)."""
    path = L.write_jsonl(tmp_path / name, envs)
    return adapters.read_envelope_file(path, local_cabinet_id=local)


def _fold_local(tmp_path, envs, *, local, name):
    """Fold envelopes that ARE local to `local` into a belief list (asserts a
    clean ingest — used to seed a store, never to test the fence)."""
    protos, receipts = _ingest(tmp_path, envs, local=local, name=name)
    assert receipts == [], f"unexpected quarantine seeding {local}: {receipts}"
    return engine.fold(protos, trust_table=TT)


def _local_env(**kw):
    kw.setdefault("seed", 1)
    kw.setdefault("producer", L.PRIMARY)
    kw.setdefault("subject", "widget-1")
    kw.setdefault("state", "hot")
    kw.setdefault("occurred_at", S1)
    kw.setdefault("recorded_at", O1)
    return L.envelope(**kw)


# ===========================================================================
# INGEST fence — foreign / cross_cabinet / sentinel each quarantined WITH a
# receipt, never a proto (§7.4; silent skip = failure)
# ===========================================================================

class TestIngestQuarantine:
    def test_foreign_cabinet_id_quarantined_with_receipt(self, tmp_path):
        env = _local_env(seed=10, cabinet_id="other-cabinet")
        protos, receipts = _ingest(tmp_path, [env])
        assert protos == []                              # never folded
        assert len(receipts) == 1
        assert "foreign" in receipts[0]["reason"]
        assert receipts[0]["event_id"] == env["event_id"]   # receipt carries identity

    def test_cross_cabinet_classification_quarantined_even_with_local_id(self, tmp_path):
        # THE PINNED GAP: classification cross_cabinet is a VALID taint tier that
        # PASSES validate_any, and the cabinet_id is LOCAL — so the ONLY thing
        # that can stop it folding is the adapter's own classification fence.
        env = _local_env(seed=11, cabinet_id="main", classification="cross_cabinet")
        ok, reasons = _envelope.validate_any(env)
        assert ok, f"fixture must be a VALID-tier envelope the validator passes: {reasons}"
        protos, receipts = _ingest(tmp_path, [env])
        assert protos == []                              # NOT folded (mutant would fold)
        assert len(receipts) == 1
        assert "cross_cabinet" in receipts[0]["reason"]
        assert receipts[0]["event_id"] == env["event_id"]

    def test_sentinel_scope_id_quarantined_with_receipt(self, tmp_path):
        # a sentinel cabinet_id ("*") is refused by validate_any (V2_SENTINEL_IDS)
        # — still a QUARANTINE WITH A RECEIPT, never a silent drop.
        env = _local_env(seed=12, cabinet_id="*")
        protos, receipts = _ingest(tmp_path, [env])
        assert protos == []
        assert len(receipts) == 1
        assert "sentinel" in receipts[0]["reason"]

    def test_absent_cabinet_id_fails_closed_with_receipt(self, tmp_path):
        # absent cabinet_id (never local) — validate_any flags the missing
        # required key; the line is quarantined, never folded as-local.
        env = _local_env(seed=13)
        env.pop("cabinet_id")
        protos, receipts = _ingest(tmp_path, [env])
        assert protos == []
        assert len(receipts) == 1

    def test_every_refused_line_has_a_receipt_never_silent_skip(self, tmp_path):
        # a mixed file: 2 GOOD local lines + 3 BAD (foreign / cross_cabinet /
        # sentinel). Exactly the 2 good fold; exactly the 3 bad get receipts.
        # Pins BOTH "quarantine-without-receipt" and "silent skip" mutants.
        envs = [
            _local_env(seed=20, subject="ok-a"),
            _local_env(seed=21, cabinet_id="foreign"),
            _local_env(seed=22, classification="cross_cabinet"),
            _local_env(seed=23, cabinet_id="null"),          # sentinel
            _local_env(seed=24, subject="ok-b"),
        ]
        protos, receipts = _ingest(tmp_path, envs)
        assert len(protos) == 2                          # only the 2 good
        assert {p["subject_key"] for p in protos} == {
            "observations/ok-a", "observations/ok-b"}
        assert len(receipts) == 3                         # every bad line -> a receipt
        # accounting is exact: goods + bads == total lines (no silent skip)
        assert len(protos) + len(receipts) == len(envs)


# ===========================================================================
# INGEST fence — the COMPLETE standalone _envelope_scope_reason contract
# (a validated envelope need not have run through validate_any first)
# ===========================================================================

class TestScopeReasonUnit:
    def test_cross_cabinet_refused_even_with_local_cabinet_id(self):
        # the exact mutant-kill: a LOCAL cabinet_id + cross_cabinet class must
        # return a REFUSAL. The pre-fix fence returned None here (would fold).
        reason = adapters._envelope_scope_reason(
            {"classification": "cross_cabinet", "cabinet_id": "main"},
            local_cabinet_id="main")
        assert reason is not None
        assert "cross_cabinet" in reason

    def test_cross_cabinet_refused_regardless_of_cabinet_id(self):
        # cross_cabinet + a foreign cabinet_id is still refused (either axis).
        reason = adapters._envelope_scope_reason(
            {"classification": "cross_cabinet", "cabinet_id": "elsewhere"},
            local_cabinet_id="main")
        assert reason is not None

    def test_local_system_classification_is_allowed(self):
        # NO OVER-FENCING: a normal local system envelope folds (None) — the
        # cross_cabinet refusal must not reject unit 2/3's real local streams.
        assert adapters._envelope_scope_reason(
            {"classification": "system", "cabinet_id": "main"},
            local_cabinet_id="main") is None

    @pytest.mark.parametrize("cls", ["system", "officer", "captain", "external"])
    def test_non_cross_cabinet_local_classifications_allowed(self, cls):
        # ONLY cross_cabinet is fenced by classification; the other four taint
        # tiers on a LOCAL cabinet_id fold (external taint is a different concern
        # — it is NOT a cross-cabinet marker, so it is not refused here).
        assert adapters._envelope_scope_reason(
            {"classification": cls, "cabinet_id": "main"},
            local_cabinet_id="main") is None

    def test_foreign_cabinet_id_refused(self):
        reason = adapters._envelope_scope_reason(
            {"classification": "system", "cabinet_id": "other"},
            local_cabinet_id="main")
        assert reason is not None
        assert "foreign" in reason

    def test_absent_cabinet_id_fails_closed(self):
        reason = adapters._envelope_scope_reason(
            {"classification": "system"}, local_cabinet_id="main")
        assert reason is not None
        assert "absent" in reason


# ===========================================================================
# QUERY fence — HARD ERROR, never empty-success (§7.4, denial != ignorance)
# ===========================================================================

class TestQueryFailsClosed:
    def _local_store(self, tmp_path):
        return _fold_local(tmp_path, [_local_env(seed=30)],
                           local="main", name="q-local.jsonl")

    def test_foreign_scope_is_a_hard_error(self, tmp_path):
        beliefs = self._local_store(tmp_path)
        with pytest.raises(query.ScopeError):
            query.as_of(beliefs, "observations/widget-1",
                        scope={"cabinet_id": "some-other-cabinet"})

    def test_sentinel_scope_is_a_hard_error(self, tmp_path):
        beliefs = self._local_store(tmp_path)
        with pytest.raises(query.ScopeError):
            query.as_of(beliefs, "observations/widget-1",
                        scope={"cabinet_id": "*"})            # sentinel scope id

    def test_missing_scope_is_a_hard_error(self, tmp_path):
        beliefs = self._local_store(tmp_path)
        with pytest.raises(query.ScopeError):
            query.as_of(beliefs, "observations/widget-1", scope=None)

    def test_empty_success_mutant_bites(self, tmp_path):
        # MUTANT (scope_mode="lenient"): a foreign scope returns an empty-success
        # unknown instead of raising — denial masquerading as ignorance. This is
        # EXACTLY the shape the strict fence forbids: were the fence to return
        # empty-success, the strict ScopeError assertions above would not hold and
        # an attacker could not distinguish "denied" from "no data".
        beliefs = self._local_store(tmp_path)
        r = query.as_of(beliefs, "observations/widget-1",
                        scope={"cabinet_id": "some-other-cabinet"},
                        scope_mode="lenient")
        assert r.is_unknown()                            # the mutant's tell
        assert r.views == ()                             # empty-success (no error)


# ===========================================================================
# QUERY fence — a scoped query over a MIXED local+foreign store leaks NO
# foreign belief (C-F19 / IDOR-shaped cross-cabinet read)
# ===========================================================================

class TestScopedQueryNoForeignLeak:
    def _mixed_store(self, tmp_path):
        # SAME subject_key present in two cabinets: a local "main" belief and a
        # foreign "other" belief carrying a sentinel-obvious secret state. Each is
        # local to ITS OWN fold, so both fold cleanly; the query scope must
        # isolate them. Distinct seeds => distinct event_ids => distinct
        # belief_ids (no collapse), same subject "widget-1".
        main = _fold_local(
            tmp_path,
            [_local_env(seed=101, subject="widget-1", state="local-truth")],
            local="main", name="mix-main.jsonl")
        other = _fold_local(
            tmp_path,
            [_local_env(seed=202, subject="widget-1", state="FOREIGN-SECRET",
                        cabinet_id="other")],
            local="other", name="mix-other.jsonl")
        return list(main) + list(other), main, other

    def test_local_scope_returns_only_local_belief(self, tmp_path):
        store, main, other = self._mixed_store(tmp_path)
        r = query.as_of(store, "observations/widget-1", scope=MAIN)
        assert not r.is_unknown()
        assert len(r.views) >= 1
        # every returned view is local; no foreign cabinet_id, no secret state
        for v in r.views:
            assert v.provenance.get("cabinet_id") == "main"
            assert (v.value or {}).get("state") != "FOREIGN-SECRET"
        # the foreign belief is nowhere in the fenced evidence set either
        foreign_ids = {b.belief_id for b in other}
        assert not (r.evidence_ids & foreign_ids)
        # sanity: the local belief IS the one served
        assert r.evidence_ids == {main[0].belief_id}

    def test_third_cabinet_scope_over_mixed_store_hard_errors(self, tmp_path):
        # the subject exists (in main AND other) but NOT in "third" — a
        # cross-cabinet mismatch is a HARD ERROR, never a silent unknown that
        # would leak the subject's cross-cabinet existence as ignorance.
        store, _main, _other = self._mixed_store(tmp_path)
        with pytest.raises(query.ScopeError):
            query.as_of(store, "observations/widget-1",
                        scope={"cabinet_id": "third"})
