"""COG-2 UNIT 2 — temporal-fence gate (§8 sim 2, tests-first).

The mechanical proof that the as-of query answers "what did we believe, as of
when" WITHOUT temporal leaks across BOTH axes, and that DERIVED state
(status/superseded_by/contradicts) is re-derived PER CUTOFF (C-F7) — never read
back from a stored final status.

Honesty clause (§1 M2 / A-B1): both production streams this phase are
single-clock (occurred_at == observation_time on the outbox). The two-axis
proof therefore rides the production ENVELOPE-FILE adapter (§5.2a), a real
fold+query path with independent occurred_at (source/valid time) and
recorded_at (observation/transaction time). Declared, not hidden.

Seed (one producer correcting itself — a supersession, source order):
  * E1 original : occurred_at S1, recorded_at O1, state "open"
  * E2 correction: occurred_at S1 (about the SAME valid instant), recorded_at
                   T3 (learned later), state "closed" — supersedes E1
As-of the observation axis:
  * observation = T2 (O1 < T2 < T3) -> only E1 visible -> "open", asserted,
    empty conflict set, no superseded_by (re-derived over the sub-history)
  * observation = T4 (> T3) -> both visible -> E2 supersedes E1 -> "closed"
Boundary is INCLUSIVE-<= (leak predicate ts > cutoff, C-F8): a same-second seed.

Negative controls (MUST fail):
  * a source_time-only fence LEAKS the correction into the T2 view (E2's
    source_time is S1 <= T2, so a valid-time fence wrongly shows "closed")
  * a stored-final-status server returns "superseded" at T2 (fails re-derivation)

S0: interpreter python3.12. No DB — the envelope-file adapter reads a JSONL.
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

from framework.cortex import adapters, belief, engine, query  # noqa: E402
import lib_cog2_envelope as L  # noqa: E402

TT = L.TRUST_TABLE
MAIN = {"cabinet_id": "main"}

# The pinned timeline (canonical UTC-second spellings).
S1 = "2026-07-20T00:00:00Z"          # source/valid time — both envelopes
O1 = "2026-07-20T01:00:00Z"          # observation of E1 (early)
T2 = "2026-07-20T02:00:00Z"          # cutoff between O1 and T3
T3 = "2026-07-20T03:00:00Z"          # observation of E2 (the correction)
T4 = "2026-07-20T04:00:00Z"          # cutoff after T3
BEFORE_S1 = "2026-07-19T00:00:00Z"   # a source cutoff before the fact existed
SUBJECT = "observations/widget-1"


def _seed_correction(tmp_path):
    """Two envelopes: original then a later-observed correction (same subject,
    same producer -> a supersession lineage)."""
    envs = [
        L.envelope(seed=1, producer=L.PRIMARY, subject="widget-1", state="open",
                   occurred_at=S1, recorded_at=O1),
        L.envelope(seed=2, producer=L.PRIMARY, subject="widget-1", state="closed",
                   occurred_at=S1, recorded_at=T3),
    ]
    path = L.write_jsonl(tmp_path / "obs.jsonl", envs)
    protos, receipts = adapters.read_envelope_file(path, local_cabinet_id="main")
    assert receipts == [], f"unexpected quarantine: {receipts}"
    return engine.fold(protos, trust_table=TT)


def _state(result) -> str | None:
    assert len(result.views) == 1, f"expected one current belief, got {result.views}"
    return result.views[0].value["state"]


# ===========================================================================
# the envelope-file adapter carries the TWO independent clocks (§5.2a)
# ===========================================================================

class TestEnvelopeFileAdapterTwoAxis:
    def test_source_and_observation_axes_are_independent(self, tmp_path):
        beliefs = _seed_correction(tmp_path)
        by_state = {b.claim["state"]: b for b in beliefs}
        # E1: occurred S1, recorded O1; E2: occurred S1, recorded T3.
        assert by_state["open"].source_time == S1
        assert by_state["open"].observation_time == O1
        assert by_state["closed"].source_time == S1
        assert by_state["closed"].observation_time == T3       # the second axis
        # the axes DIFFER on E2 (recorded != occurred) — a real two-clock path
        assert by_state["closed"].source_time != by_state["closed"].observation_time

    def test_envelope_beliefs_carry_full_v2_provenance_and_validate(self, tmp_path):
        beliefs = _seed_correction(tmp_path)
        for b in beliefs:
            prov = b.provenance
            for key in ("event_id", "producer", "stream_rank", "cabinet_id",
                        "scope_kind", "correlation_id", "classification",
                        "payload_schema", "idempotency_key"):
                assert key in prov, f"missing provenance key {key}"
            assert prov["stream_rank"] == engine.RANK_TABLE["envelope_file"]  # 2
            assert b.subject_key == SUBJECT and b.dimension == "observations/observation"
            assert b.kind == "observation"
            # the envelope regime is a valid production belief
            assert belief.validate_belief(b) == ()


# ===========================================================================
# observation-axis fence — pre-correction vs corrected
# ===========================================================================

class TestObservationAxisFence:
    def test_asof_T2_is_pre_correction(self, tmp_path):
        beliefs = _seed_correction(tmp_path)
        r = query.as_of(beliefs, SUBJECT, scope=MAIN, observation=T2)
        assert _state(r) == "open"

    def test_asof_T4_is_corrected(self, tmp_path):
        beliefs = _seed_correction(tmp_path)
        r = query.as_of(beliefs, SUBJECT, scope=MAIN, observation=T4)
        assert _state(r) == "closed"


# ===========================================================================
# source-axis fence distinguishes the axes (§8 sim 2)
# ===========================================================================

class TestSourceAxisDistinguishesAxes:
    def test_source_S1_observation_now_is_corrected(self, tmp_path):
        # source <= S1 keeps both; observation "now" (unfenced) sees the whole
        # history -> the correction wins. Contrast with observation=T2 (open):
        # same source coverage, different observation cutoff -> different answer.
        beliefs = _seed_correction(tmp_path)
        r = query.as_of(beliefs, SUBJECT, scope=MAIN, source=S1, observation=None)
        assert _state(r) == "closed"

    def test_source_before_the_fact_is_unknown(self, tmp_path):
        # same observation coverage (now), a source cutoff before S1 -> the
        # valid-time axis independently fences everything out -> unknown.
        beliefs = _seed_correction(tmp_path)
        r = query.as_of(beliefs, SUBJECT, scope=MAIN, source=BEFORE_S1)
        assert r.is_unknown()

    def test_observation_axis_moves_independently_of_source(self, tmp_path):
        # source coverage identical (S1), only the observation cutoff changes.
        beliefs = _seed_correction(tmp_path)
        pre = query.as_of(beliefs, SUBJECT, scope=MAIN, source=S1, observation=T2)
        post = query.as_of(beliefs, SUBJECT, scope=MAIN, source=S1, observation=T4)
        assert _state(pre) == "open" and _state(post) == "closed"


# ===========================================================================
# derived state is RE-DERIVED per cutoff (C-F7) + closure assertion
# ===========================================================================

def _referenced_ids(result) -> set:
    ids = set()
    for v in result.views:
        ids.update(v.supersedes)
        ids.update(v.conflict_set)
        if v.superseded_by is not None:
            ids.add(v.superseded_by)
    return ids


class TestPerCutoffRederivation:
    def test_T2_status_asserted_no_links(self, tmp_path):
        beliefs = _seed_correction(tmp_path)
        r = query.as_of(beliefs, SUBJECT, scope=MAIN, observation=T2)
        v = r.views[0]
        # at T2 the only visible belief is E1 — NOT superseded (the superseding
        # event is not yet observed), no conflict, status re-derived to asserted.
        assert v.status == "asserted"
        assert v.superseded_by is None
        assert v.conflict_set == () and v.supersedes == ()
        assert r.status == "asserted"

    def test_T4_rederives_the_supersession_chain(self, tmp_path):
        beliefs = _seed_correction(tmp_path)
        r = query.as_of(beliefs, SUBJECT, scope=MAIN, observation=T4)
        v = r.views[0]                       # the current head = E2 ("closed")
        assert v.status == "asserted" and v.value["state"] == "closed"
        # the head records that it supersedes E1 (history preserved, not erased)
        assert len(v.supersedes) == 1

    def test_closure_every_referenced_belief_resolves_within_the_cutoff(self, tmp_path):
        beliefs = _seed_correction(tmp_path)
        for cut in (T2, T4, None):
            r = query.as_of(beliefs, SUBJECT, scope=MAIN, observation=cut)
            assert _referenced_ids(r) <= set(r.evidence_ids), (
                f"closure breach at cutoff {cut}: an answer links a belief "
                "outside its own fenced sub-history")


# ===========================================================================
# NEGATIVE CONTROLS (must fail) — leak + stored-status mutants
# ===========================================================================

class TestFenceMutantsBite:
    def test_source_time_only_fence_leaks_the_correction(self, tmp_path):
        # MUTANT (source_time-only fence): E2.source_time is S1 <= T2, so a
        # valid-time fence wrongly admits the not-yet-observed correction and
        # returns "closed" — a temporal leak. The correct observation fence
        # returns "open".
        beliefs = _seed_correction(tmp_path)
        correct = query.as_of(beliefs, SUBJECT, scope=MAIN, observation=T2)
        leaked = query.as_of(beliefs, SUBJECT, scope=MAIN, observation=T2,
                             fence_axis="source_time")
        assert _state(correct) == "open"
        assert _state(leaked) == "closed"          # the leak — mutant bites
        assert _state(correct) != _state(leaked)

    def test_stored_final_status_server_fails_the_T2_assert(self, tmp_path):
        # MUTANT (stored-final-status): serve the belief's stored (full-history)
        # status instead of re-deriving over the sub-history. At T2 the stored
        # status of E1 is "superseded"; re-derivation makes it "asserted".
        beliefs = _seed_correction(tmp_path)
        correct = query.as_of(beliefs, SUBJECT, scope=MAIN, observation=T2)
        mutant = query.as_of(beliefs, SUBJECT, scope=MAIN, observation=T2,
                             rederive=False)
        assert correct.views[0].status == "asserted"
        assert mutant.views[0].status == "superseded"   # stored final status — bites


# ===========================================================================
# inclusive-<= boundary at the exact same second (C-F8)
# ===========================================================================

class TestInclusiveBoundarySameSecond:
    def _same_second_seed(self, tmp_path):
        # two envelopes recorded in the SAME second; E4 (later line) supersedes.
        sec = "2026-07-20T05:00:00Z"
        envs = [
            L.envelope(seed=11, producer=L.PRIMARY, subject="widget-b", state="a",
                       occurred_at=S1, recorded_at=sec),
            L.envelope(seed=12, producer=L.PRIMARY, subject="widget-b", state="b",
                       occurred_at=S1, recorded_at=sec),
        ]
        path = L.write_jsonl(tmp_path / "sec.jsonl", envs)
        protos, _ = adapters.read_envelope_file(path, local_cabinet_id="main")
        return engine.fold(protos, trust_table=TT), sec

    def test_cutoff_exactly_at_the_second_includes_both(self, tmp_path):
        beliefs, sec = self._same_second_seed(tmp_path)
        r = query.as_of(beliefs, "observations/widget-b", scope=MAIN, observation=sec)
        # inclusive-<=: both are within the cutoff; the later-line one wins.
        assert set(r.evidence_ids) and len(r.views) == 1
        assert r.views[0].value["state"] == "b"

    def test_cutoff_one_second_before_excludes_both(self, tmp_path):
        beliefs, _ = self._same_second_seed(tmp_path)
        r = query.as_of(beliefs, "observations/widget-b", scope=MAIN,
                        observation="2026-07-20T04:59:59Z")
        assert r.is_unknown()          # ts > cutoff excludes both (strict)


# ===========================================================================
# adapter is FAIL-CLOSED on every ingested line (no silent skip)
# ===========================================================================

class TestEnvelopeFileFailClosed:
    def test_invalid_envelope_line_is_quarantined_with_a_receipt(self, tmp_path):
        good = L.envelope(seed=21, producer=L.PRIMARY, subject="widget-c",
                          state="ok", occurred_at=S1, recorded_at=O1)
        bad = L.envelope(seed=22, producer=L.PRIMARY, subject="widget-c",
                         state="no", occurred_at=S1, recorded_at=O1)
        bad["classification"] = "not-a-tier"       # validate_any rejects
        path = L.write_jsonl(tmp_path / "mix.jsonl", [good, bad])
        protos, receipts = adapters.read_envelope_file(path, local_cabinet_id="main")
        assert len(protos) == 1                    # only the valid line folds
        assert len(receipts) == 1                  # the invalid line is NOT silently skipped
        assert receipts[0]["reason"]

    def test_malformed_json_line_is_quarantined_not_crashed(self, tmp_path):
        path = tmp_path / "broken.jsonl"
        good = L.envelope(seed=23, producer=L.PRIMARY, subject="widget-d",
                          state="ok", occurred_at=S1, recorded_at=O1)
        import json as _json
        path.write_text(_json.dumps(good) + "\n" + "{not json\n", encoding="utf-8")
        protos, receipts = adapters.read_envelope_file(path, local_cabinet_id="main")
        assert len(protos) == 1 and len(receipts) == 1

    def test_foreign_cabinet_id_is_quarantined(self, tmp_path):
        foreign = L.envelope(seed=24, producer=L.PRIMARY, subject="widget-e",
                             state="x", occurred_at=S1, recorded_at=O1,
                             cabinet_id="other-cabinet")
        path = L.write_jsonl(tmp_path / "foreign.jsonl", [foreign])
        protos, receipts = adapters.read_envelope_file(path, local_cabinet_id="main")
        assert protos == [] and len(receipts) == 1


# ===========================================================================
# REVIEW FIX F6: a VALIDATED envelope whose payload declares no pinned subject
# is quarantined-with-receipt, never a KeyError that aborts the whole file
# ===========================================================================

def _no_subject_envelope(seed):
    """A VALID v2 envelope on the platform's own tasks/task-event@1 relay shape
    — it passes validate_any but declares no `subject` field, so the
    envelope-file adapter cannot key a belief from it."""
    return {
        "schema_version": "cabinet-envelope/v2", "event_id": L.make_ulid(seed),
        "event_type": "tasks.status_changed", "occurred_at": S1, "recorded_at": O1,
        "cabinet_id": "main", "scope_kind": "cabinet",
        "producer": "officer_tasks/outbox-relay", "correlation_id": L.make_cid(seed),
        "idempotency_key": f"task:{seed}:done", "classification": "system",
        "payload_schema": "tasks/task-event@1",
        "payload": {"task_id": seed, "new_status": "done", "actor": "cos"},
    }


class TestNoSubjectFieldQuarantine:
    def test_validated_envelope_without_subject_is_quarantined_not_crashed(self, tmp_path):
        good = L.envelope(seed=31, producer=L.PRIMARY, subject="widget-ok",
                          state="ok", occurred_at=S1, recorded_at=O1)
        path = L.write_jsonl(tmp_path / "nosub.jsonl",
                             [good, _no_subject_envelope(88)])
        protos, receipts = adapters.read_envelope_file(path, local_cabinet_id="main")
        assert len(protos) == 1                        # the valid line STILL folds
        assert protos[0]["subject_key"] == "observations/widget-ok"
        assert len(receipts) == 1                      # the no-subject line refused
        assert "subject" in receipts[0]["reason"]      # a subject-reason, not a crash

    def test_no_subject_line_between_two_valid_lines_does_not_abort_the_file(self, tmp_path):
        # the KeyError bug aborted the WHOLE file mid-iteration; prove both
        # valid lines around the offender still fold.
        a = L.envelope(seed=32, producer=L.PRIMARY, subject="widget-a", state="a",
                       occurred_at=S1, recorded_at=O1)
        b = L.envelope(seed=33, producer=L.PRIMARY, subject="widget-b", state="b",
                       occurred_at=S1, recorded_at=O1)
        path = L.write_jsonl(tmp_path / "sandwich.jsonl",
                             [a, _no_subject_envelope(89), b])
        protos, receipts = adapters.read_envelope_file(path, local_cabinet_id="main")
        assert sorted(p["subject_key"] for p in protos) == \
            ["observations/widget-a", "observations/widget-b"]
        assert len(receipts) == 1


# ===========================================================================
# REVIEW FIX (cutoff): a non-canonical cutoff is a HARD ERROR (was fail-open)
# ===========================================================================

class TestCutoffValidation:
    def test_noncanonical_iso_offset_cutoff_hard_errors(self, tmp_path):
        # legal ISO, non-canonical ("+00:00" instead of "Z") — a string compare
        # against canonical stored timestamps would fence OPEN. Hard-error.
        beliefs = _seed_correction(tmp_path)
        with pytest.raises(ValueError):
            query.as_of(beliefs, SUBJECT, scope=MAIN,
                        observation="2026-07-20T03:00:00+00:00")

    def test_garbage_cutoff_hard_errors(self, tmp_path):
        beliefs = _seed_correction(tmp_path)
        with pytest.raises(ValueError):
            query.as_of(beliefs, SUBJECT, scope=MAIN, observation="garbage")

    def test_noncanonical_source_cutoff_hard_errors(self, tmp_path):
        beliefs = _seed_correction(tmp_path)
        with pytest.raises(ValueError):
            query.as_of(beliefs, SUBJECT, scope=MAIN, source="2026-07-20")

    def test_canonical_z_cutoff_still_fences(self, tmp_path):
        beliefs = _seed_correction(tmp_path)
        r = query.as_of(beliefs, SUBJECT, scope=MAIN, observation=T2)  # "...Z"
        assert _state(r) == "open"                     # canonical cutoff unaffected


# ===========================================================================
# §8 sim 2 C-F9: out-of-order arrival — the fence keys on observation_time,
# NOT on arrival/file-line (rowid) order (every other seed is arrival-monotone)
# ===========================================================================

class TestOutOfOrderArrivalFencesOnObservationTime:
    def _seed(self, tmp_path):
        # line 0 ARRIVES first but is OBSERVED late (recorded T4);
        # line 1 ARRIVES last  but is OBSERVED early (recorded T2).
        envs = [
            L.envelope(seed=61, producer=L.PRIMARY, subject="widget-ooo",
                       state="late-observed", occurred_at=S1, recorded_at=T4),
            L.envelope(seed=62, producer=L.PRIMARY, subject="widget-ooo",
                       state="early-observed", occurred_at=S1, recorded_at=T2),
        ]
        path = L.write_jsonl(tmp_path / "ooo.jsonl", envs)
        protos, _ = adapters.read_envelope_file(path, local_cabinet_id="main")
        return engine.fold(protos, trust_table=TT)

    def test_early_observed_late_arrival_is_visible_at_early_cutoff(self, tmp_path):
        beliefs = self._seed(tmp_path)
        by_state = {b.claim["state"]: b for b in beliefs}
        early, late = by_state["early-observed"], by_state["late-observed"]
        # arrival/source order and observation order are INVERTED for this seed:
        assert early.provenance["intra_stream_seq"] > late.provenance["intra_stream_seq"]
        assert early.observation_time < late.observation_time
        # as-of an observation cutoff between the two: ONLY the early-observed
        # (late-ARRIVING) belief is visible — the fence follows observation_time.
        r = query.as_of(beliefs, "observations/widget-ooo", scope=MAIN, observation=T3)
        assert set(r.evidence_ids) == {early.belief_id}
        assert late.belief_id not in r.evidence_ids
        assert len(r.views) == 1 and r.views[0].value["state"] == "early-observed"

    def test_an_arrival_order_fence_would_pick_the_wrong_belief(self, tmp_path):
        # DEMONSTRATION that a rowid/arrival-order fence mutant BITES on this seed
        # (no query seam added — that mutant needs a seq-typed cutoff, which is
        # engine plumbing, deferred): an arrival fence keeps the FIRST-arriving
        # beliefs (lowest intra_stream_seq) and so returns the LATE-observed one —
        # the exact temporal leak the observation fence avoids.
        beliefs = self._seed(tmp_path)
        arrival_fenced = [b.claim["state"] for b in beliefs
                          if b.provenance["intra_stream_seq"] <= 0]   # rowid MUTANT
        assert arrival_fenced == ["late-observed"]                    # the WRONG one
        correct = query.as_of(beliefs, "observations/widget-ooo", scope=MAIN,
                              observation=T3)
        assert correct.views[0].value["state"] == "early-observed"    # opposite => bites
