"""Phase 2 Batch A — chokepoint telemetry mirrors (framework/evidence_mirror.py).

Pins the mirror tier's laws:
* explicit ALLOW-LIST (subset of VALID_EVENT_TYPES, disjoint from the
  nervous-system exhaust; the degradation class never mirrors itself);
* correlation both directions (payload stamp / consequence ref forward,
  correlation_id + detail join keys reverse);
* fail isolation by fault injection — a raising or unimportable recorder
  NEVER blocks the domain emit, and degradation is LOUD (doctor-readable
  marker + evidence_mirror_degraded org event) and rate-limited;
* recorder public API only (fixed producer identity, no CLI surface);
* observation-only: with the pytest fence closed (the default) every
  existing code path is byte-identical — no stamp, no ref, no store write;
  with the fence open, new events appear ONLY additively.

Lives OUTSIDE the germline framework/evidence dir (the doctrine-laws /
retention-classes precedent). python3.12 only.
"""
from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from framework import evidence_mirror
from framework.events import emitter
from framework.fidelity import consequence as consequence_mod

REPO = Path(__file__).resolve().parents[2]


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _receipts(store: Path, trial_id: str) -> list:
    path = store / "trials" / trial_id / "events.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _marker_rows(marker: Path) -> list:
    if not marker.is_file():
        return []
    return [json.loads(line) for line in marker.read_text().splitlines() if line.strip()]


@pytest.fixture()
def mirror_env(tmp_path, monkeypatch):
    """Fence-open sandbox: scratch store + marker + isolated domain ledgers."""
    store = tmp_path / "evidence-store"
    marker = tmp_path / "degradations.jsonl"
    events = tmp_path / "events"
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(events))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
    monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
    # Pytest-fence overrides — the ONLY way the mirror runs under pytest.
    monkeypatch.setenv("CABINET_EVIDENCE_MIRROR_STORE", str(store))
    monkeypatch.setenv("CABINET_EVIDENCE_MIRROR_MARKER", str(marker))
    evidence_mirror._reset_state()
    yield SimpleNamespace(store=store, marker=marker, events=events)
    evidence_mirror._reset_state()


# ---------------------------------------------------------------------------
# Allow-list law
# ---------------------------------------------------------------------------


class TestAllowList:
    def test_mirrored_classes_are_a_strict_subset_of_valid_event_types(self):
        assert evidence_mirror.MIRRORED_ORG_EVENT_TYPES < emitter.VALID_EVENT_TYPES

    def test_exhaust_is_never_mirrored(self):
        overlap = evidence_mirror.MIRRORED_ORG_EVENT_TYPES & evidence_mirror.NEVER_MIRRORED_EXHAUST
        assert not overlap, f"exhaust classes leaked into the mirror allow-list: {sorted(overlap)}"

    def test_named_exhaust_families_stay_out(self):
        # The 59%-plumbing families, pinned individually so a future edit
        # cannot quietly re-admit one.
        for exhaust in (
            "session_started", "session_ended", "notification_received",
            "subagent_completed", "outbox_queued", "outbox_dispatched",
            "outbox_failed", "policy_evaluated", "eval_run_started",
        ):
            assert exhaust not in evidence_mirror.MIRRORED_ORG_EVENT_TYPES
            assert exhaust in evidence_mirror.NEVER_MIRRORED_EXHAUST

    def test_degradation_class_never_mirrors_itself(self):
        assert evidence_mirror.DEGRADATION_EVENT_TYPE in emitter.VALID_EVENT_TYPES
        assert evidence_mirror.DEGRADATION_EVENT_TYPE not in evidence_mirror.MIRRORED_ORG_EVENT_TYPES

    def test_captain_gate_bounced_is_registered_and_selected(self):
        # The latent-bug fix: attention/escalation.py has emitted this class
        # since the gate shipped; unregistered, the ValueError was swallowed
        # and the durable record never landed. Registration is additive.
        assert "captain_gate_bounced" in emitter.VALID_EVENT_TYPES
        assert "captain_gate_bounced" in evidence_mirror.MIRRORED_ORG_EVENT_TYPES

    def test_consequence_lifecycle_vocabulary(self):
        assert evidence_mirror.MIRRORED_CONSEQUENCE_LIFECYCLE == frozenset(
            {"proposal", "outcome", "review"}
        )


# ---------------------------------------------------------------------------
# Org-event chokepoint — happy path + correlation both directions
# ---------------------------------------------------------------------------


class TestOrgMirror:
    def test_allowlisted_emit_lands_receipt_and_stamps_forward_pointer(self, mirror_env):
        caller_payload = {"need_id": "need-4242", "summary": "quota"}
        event = emitter.emit("need_filed", actor="system", payload=caller_payload)

        trial_id = f"evt-orgmirror-{_today()}"
        # Forward correlation: the org row carries the trial pointer …
        assert event["payload"][evidence_mirror.PAYLOAD_KEY] == {"trial_id": trial_id}
        # … in a COPY — the caller's dict is never mutated.
        assert evidence_mirror.PAYLOAD_KEY not in caller_payload

        receipts = _receipts(mirror_env.store, trial_id)
        assert len(receipts) == 1
        receipt = receipts[0]
        # Reverse correlation: recorder-native correlation_id + detail keys.
        assert receipt["correlation_id"] == event["id"]
        assert receipt["detail"]["org_event_id"] == event["id"]
        assert receipt["detail"]["org_event_type"] == "need_filed"
        assert receipt["detail"]["ledger_date"] == event["created_at"][:10]
        assert receipt["detail"]["org_event_sha256"] == evidence_mirror._canonical_sha256(event)
        # Fixed producer identity — never payload-derived (A6).
        assert receipt["actor"] == {"kind": "system", "id": "org-event-mirror"}
        assert receipt["component"]["name"] == "evidence-mirror"
        assert receipt["phase"] == "system" and receipt["status"] == "succeeded"

        from framework.evidence.verifier import verify_trial

        assert verify_trial(mirror_env.store, trial_id)["ok"] is True

    def test_domain_jsonl_carries_the_same_stamp(self, mirror_env):
        event = emitter.emit("policy_blocked", actor="system", payload={"policy_id": "p1"})
        (day_file,) = mirror_env.events.glob("events-*.jsonl")
        rows = [json.loads(l) for l in day_file.read_text().splitlines() if l.strip()]
        assert rows[-1]["id"] == event["id"]
        assert rows[-1]["payload"][evidence_mirror.PAYLOAD_KEY]["trial_id"].startswith("evt-orgmirror-")

    def test_non_allowlisted_class_is_untouched_and_unmirrored(self, mirror_env):
        event = emitter.emit("session_started", actor="system", payload={"session_id": "s1"})
        assert evidence_mirror.PAYLOAD_KEY not in event["payload"]
        assert not (mirror_env.store / "trials").exists()

    def test_registered_gate_bounce_now_lands_and_mirrors(self, mirror_env):
        event = emitter.emit(
            "captain_gate_bounced",
            actor="attention-gate",
            payload={"subject": "s", "kind": "k", "reason": "r", "missing": []},
        )
        assert event["id"]
        receipts = _receipts(mirror_env.store, f"evt-orgmirror-{_today()}")
        assert [r["detail"]["org_event_type"] for r in receipts] == ["captain_gate_bounced"]


# ---------------------------------------------------------------------------
# Consequence chokepoint — refs stamp + receipt + supersede + neutrality
# ---------------------------------------------------------------------------


def _emit_row(**overrides):
    base = dict(
        ts="2026-07-17T10:00:00Z",
        actor={"kind": "officer", "id": "cos"},
        lane="draft",
        action="reply to captain",
        subject="msg-001",
        proposal={"required": True, "decision": "approved", "decided_at": "2026-07-17T10:01:00Z"},
    )
    base.update(overrides)
    return consequence_mod.emit_consequence(**base)


class TestConsequenceMirror:
    def test_lifecycle_row_gets_ref_and_receipt(self, mirror_env):
        row = _emit_row()
        trial_id = f"evt-consequence-{_today()}"
        ref = evidence_mirror.CONSEQUENCE_REF_PREFIX + trial_id
        assert ref in row["refs"]

        receipts = _receipts(mirror_env.store, trial_id)
        assert len(receipts) == 1
        detail = receipts[0]["detail"]
        assert detail["consequence_actor"] == "officer:cos"
        assert detail["consequence_action"] == "reply to captain"
        assert detail["consequence_subject"] == "msg-001"
        assert detail["consequence_ts"] == "2026-07-17T10:00:00Z"
        assert detail["lifecycle"] == ["proposal"]
        assert receipts[0]["actor"] == {"kind": "system", "id": "consequence-mirror"}

        # Join recipe: parse the WRITTEN ledger line, re-canonicalize, sha256.
        (ledger,) = mirror_env.events.glob("consequence-events-*.jsonl")
        written = json.loads(ledger.read_text().splitlines()[-1])
        assert detail["row_sha256"] == evidence_mirror._canonical_sha256(written)
        assert receipts[0]["correlation_id"] == detail["row_sha256"]

    def test_superseding_enrichment_recarries_the_ref(self, mirror_env):
        _emit_row()
        _emit_row(outcome={"status": "ok", "evidence": "ttl_ok"})  # same identity tuple
        collapsed = consequence_mod.read_ledger()
        assert len(collapsed) == 1
        ref = evidence_mirror.CONSEQUENCE_REF_PREFIX + f"evt-consequence-{_today()}"
        assert ref in collapsed[0]["refs"]
        # Two lifecycle rows -> two receipts (receipts are per-append, the
        # domain reader still collapses by identity).
        assert len(_receipts(mirror_env.store, f"evt-consequence-{_today()}")) == 2

    def test_ref_never_changes_graduation_math(self, mirror_env):
        _emit_row(review={"verdict": "confirmed", "source": "verdict_human"})
        ledger = consequence_mod.read_ledger()
        with_ref = consequence_mod.compute_ratios(ledger=ledger)
        stripped = [dict(row, refs=[r for r in row.get("refs", []) if not r.startswith(
            evidence_mirror.CONSEQUENCE_REF_PREFIX)]) for row in ledger]
        without_ref = consequence_mod.compute_ratios(ledger=stripped)
        assert {k: vars(v) for k, v in with_ref.items()} == {k: vars(v) for k, v in without_ref.items()}

    def test_ref_is_identity_free_for_the_attention_plane(self):
        from framework.attention.situation import canonical_refs

        ref = evidence_mirror.CONSEQUENCE_REF_PREFIX + "evt-consequence-20260717"
        assert canonical_refs([ref]) == frozenset()
        assert ref != consequence_mod.DIRECT_DEMOTE_REF
        assert evidence_mirror.CONSEQUENCE_REF_PREFIX.endswith(":")

    def test_sim_rows_are_never_stamped_or_mirrored(self, tmp_path, monkeypatch, mirror_env):
        sim_dir = tmp_path / "events-sim"
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(sim_dir))
        monkeypatch.setenv("CABINET_SIM_MODE", "1")
        row = _emit_row()
        assert row["sim"] is True
        assert row["refs"] == []
        assert not (mirror_env.store / "trials").exists()

    def test_refused_rows_are_never_mirrored(self, tmp_path, monkeypatch, mirror_env):
        # Live row aimed at a '-sim' dir: SimQuarantineError fires inside the
        # domain write, BEFORE the mirror — no receipt may exist.
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "quarantine-sim"))
        with pytest.raises(consequence_mod.SimQuarantineError):
            _emit_row()
        assert not (mirror_env.store / "trials").exists()

    def test_bare_stub_rows_are_not_mirrored(self, mirror_env):
        row = consequence_mod.emit_consequence(
            ts="2026-07-17T10:00:00Z",
            actor={"kind": "pipe", "id": "seed"},
            lane=None,
            action="observed",
            subject="stub-1",
        )
        assert row["refs"] == []
        assert not (mirror_env.store / "trials").exists()


# ---------------------------------------------------------------------------
# Fail isolation — fault injection (deliverable 3)
# ---------------------------------------------------------------------------


class TestFailIsolation:
    def test_raising_recorder_never_blocks_the_domain_emit(self, mirror_env, monkeypatch, capsys):
        def boom(store_root):
            raise RuntimeError("recorder down")

        monkeypatch.setattr(evidence_mirror, "_recorder", boom)

        event = emitter.emit("need_filed", actor="system", payload={"need_id": "n1"})

        # Domain emit succeeded and landed in the org JSONL.
        assert event["id"]
        assert any(
            e["id"] == event["id"] for e in emitter.replay(event_types=["need_filed"])
        )
        # LOUD: stderr WARN …
        assert "evidence-mirror: WARN degraded" in capsys.readouterr().err
        # … doctor-readable marker …
        rows = _marker_rows(mirror_env.marker)
        assert len(rows) == 1
        assert rows[0]["chokepoint"] == "org"
        assert rows[0]["reason"] == "recorder_error"
        # … and the degradation org event (never itself mirrored).
        degradations = emitter.replay(event_types=[evidence_mirror.DEGRADATION_EVENT_TYPE])
        assert len(degradations) == 1
        assert degradations[0]["payload"] == {"chokepoint": "org", "reason": "recorder_error"}
        assert evidence_mirror.PAYLOAD_KEY not in degradations[0]["payload"]

    def test_degradation_is_rate_limited_across_repeats(self, mirror_env, monkeypatch):
        monkeypatch.setattr(
            evidence_mirror, "_recorder",
            lambda root: (_ for _ in ()).throw(RuntimeError("still down")),
        )
        for index in range(5):
            emitter.emit("need_filed", actor="system", payload={"need_id": f"n{index}"})
        # Five failures, ONE marker line + ONE degradation event in-window.
        assert len(_marker_rows(mirror_env.marker)) == 1
        assert len(emitter.replay(event_types=[evidence_mirror.DEGRADATION_EVENT_TYPE])) == 1
        # The five domain emits all landed regardless.
        assert len(emitter.replay(event_types=["need_filed"])) == 5

    def test_unimportable_recorder_degrades_loud_with_named_reason(self, mirror_env, monkeypatch):
        # Simulates the system-python-3.9 contexts where framework/evidence
        # cannot import (the named shell-hook coverage gap).
        def no_import():
            raise ImportError("framework.evidence needs Python 3.11+")

        monkeypatch.setattr(evidence_mirror, "_import_recorder", no_import)
        event = emitter.emit("mission_created", actor="cos", payload={"mission_id": "m1"})

        # The forward stamp exists (a documented dangling pointer the daily
        # digest-anchor + reconciler catch) — the domain emit is unharmed.
        assert event["payload"][evidence_mirror.PAYLOAD_KEY]["trial_id"]
        rows = _marker_rows(mirror_env.marker)
        assert [r["reason"] for r in rows] == ["recorder_unimportable"]
        assert not (mirror_env.store / "trials").exists()

    def test_consequence_domain_write_survives_recorder_outage(self, mirror_env, monkeypatch):
        monkeypatch.setattr(
            evidence_mirror, "_recorder",
            lambda root: (_ for _ in ()).throw(RuntimeError("down")),
        )
        row = _emit_row()
        (ledger,) = mirror_env.events.glob("consequence-events-*.jsonl")
        assert json.loads(ledger.read_text().splitlines()[-1])["subject"] == "msg-001"
        assert any(r.startswith(evidence_mirror.CONSEQUENCE_REF_PREFIX) for r in row["refs"])
        assert [r["chokepoint"] for r in _marker_rows(mirror_env.marker)] == ["consequence"]


# ---------------------------------------------------------------------------
# Envelope — per-trial cap + chain segments (R-8)
# ---------------------------------------------------------------------------


class TestEnvelope:
    def test_cap_chains_to_suffixed_day_segments(self, mirror_env, monkeypatch):
        monkeypatch.setattr(evidence_mirror, "MAX_MIRROR_EVENTS_PER_TRIAL", 2)
        events = [
            emitter.emit("need_filed", actor="system", payload={"need_id": f"n{i}"})
            for i in range(5)
        ]
        day = _today()
        base = _receipts(mirror_env.store, f"evt-orgmirror-{day}")
        seg_b = _receipts(mirror_env.store, f"evt-orgmirror-b-{day}")
        seg_c = _receipts(mirror_env.store, f"evt-orgmirror-c-{day}")
        assert [len(base), len(seg_b), len(seg_c)] == [2, 2, 1]

        # The chained id still parses as a retention-classed taxonomy trial.
        from framework.evidence.recorder import TRIAL_CLASS_RE

        match = TRIAL_CLASS_RE.match(f"evt-orgmirror-b-{day}")
        assert match and match.group(1) == "orgmirror-b"

        # Every stamp points at the trial its receipt actually landed in.
        landed = {
            r["detail"]["org_event_id"]: r["trial_id"]
            for r in base + seg_b + seg_c
        }
        for event in events:
            stamp = event["payload"][evidence_mirror.PAYLOAD_KEY]["trial_id"]
            assert landed[event["id"]] == stamp

    def test_segment_exhaustion_degrades_and_skips(self, mirror_env, monkeypatch):
        monkeypatch.setattr(evidence_mirror, "MAX_MIRROR_EVENTS_PER_TRIAL", 1)
        monkeypatch.setattr(evidence_mirror, "MAX_CHAIN_SEGMENTS", 2)
        emitted = [
            emitter.emit("need_filed", actor="system", payload={"need_id": f"n{i}"})
            for i in range(3)
        ]
        # First two mirrored (base + '-b'); the third is skipped LOUDLY.
        assert evidence_mirror.PAYLOAD_KEY in emitted[0]["payload"]
        assert evidence_mirror.PAYLOAD_KEY in emitted[1]["payload"]
        assert evidence_mirror.PAYLOAD_KEY not in emitted[2]["payload"]
        assert emitted[2]["id"]  # the domain emit itself is untouched
        assert [r["reason"] for r in _marker_rows(mirror_env.marker)] == ["trial_cap_exhausted"]

    def test_cap_constant_is_code_not_env(self):
        source = (REPO / "framework" / "evidence_mirror.py").read_text()
        assert "MAX_MIRROR_EVENTS_PER_TRIAL = 500" in source
        # The only env reads are the pytest fence (store/marker overrides
        # + PYTEST_CURRENT_TEST) — nothing else may consult the environment.
        env_reads = [
            line.strip() for line in source.splitlines() if "os.environ" in line
        ]
        for line in env_reads:
            assert (
                "PYTEST_CURRENT_TEST" in line or "CABINET_EVIDENCE_MIRROR_" in line
            ), f"unexpected env read in evidence_mirror.py: {line}"


# ---------------------------------------------------------------------------
# Observation-only: the fence-closed default changes NOTHING
# ---------------------------------------------------------------------------


class TestFenceClosedDefault:
    @pytest.fixture()
    def fenced(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
        monkeypatch.delenv("CABINET_EVIDENCE_MIRROR_STORE", raising=False)
        monkeypatch.delenv("CABINET_EVIDENCE_MIRROR_MARKER", raising=False)
        monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
        evidence_mirror._reset_state()
        return tmp_path

    def test_org_emit_is_byte_identical_without_the_fence_override(self, fenced):
        payload = {"need_id": "n-fence"}
        event = emitter.emit("need_filed", actor="system", payload=payload)
        assert evidence_mirror.PAYLOAD_KEY not in event["payload"]
        assert event["payload"] is payload  # pre-existing by-reference behavior

    def test_consequence_emit_is_byte_identical_without_the_fence_override(self, fenced):
        row = _emit_row()
        assert row["refs"] == []

    def test_additive_only_existing_trials_untouched(self, mirror_env):
        from framework.evidence.recorder import EvidenceRecorder
        from framework.evidence.verifier import verify_store

        recorder = EvidenceRecorder(mirror_env.store)
        context = recorder.trace("evt-foreign-20260101", surface="system")
        recorder.append(
            context, phase="system", status="succeeded",
            actor={"kind": "system", "id": "seed"},
            component={"name": "seed", "version": "1", "commit": "unset"},
            detail={"action": "seed"},
        )
        foreign = mirror_env.store / "trials" / "evt-foreign-20260101" / "events.jsonl"
        before = foreign.read_bytes()

        emitter.emit("need_filed", actor="system", payload={"need_id": "n1"})
        _emit_row()

        assert foreign.read_bytes() == before
        result = verify_store(mirror_env.store)
        assert result["ok"] is True
        assert result["trial_count"] == 3  # foreign + orgmirror + consequence


# ---------------------------------------------------------------------------
# Surface discipline
# ---------------------------------------------------------------------------


class TestSurfaceDiscipline:
    def test_no_cli_surface(self):
        source = (REPO / "framework" / "evidence_mirror.py").read_text()
        assert 'if __name__' not in source  # no CLI entrypoint guard
        assert "argparse" not in source
        tree = ast.parse(source)
        assert not any(
            isinstance(node, ast.If) and "__main__" in ast.dump(node.test)
            for node in ast.walk(tree)
        )

    def test_module_parses_under_python_39_grammar(self):
        # The chokepoints are imported from system-Python-3.9 CLI contexts;
        # the mirror module itself must stay 3.9-parseable (only the lazy
        # recorder import inside the append path needs 3.11+).
        for rel in (
            "framework/evidence_mirror.py",
            "framework/events/emitter.py",
            "framework/fidelity/consequence.py",
        ):
            source = (REPO / rel).read_text()
            ast.parse(source, filename=rel, feature_version=(3, 9))

    def test_production_store_root_reuses_the_journey_constant(self, monkeypatch):
        # Resolution only — nothing is written. The production root must come
        # from the ONE canonical framework->instance coupling (journey.py
        # EVIDENCE_REL), so this module never mints a second layer-separation
        # debt row, and must never consult env outside the pytest fence.
        from framework.onboarding.journey import EVIDENCE_REL

        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("CABINET_EVIDENCE_MIRROR_STORE", "/tmp/should-be-ignored")
        evidence_mirror._reset_state()
        try:
            assert evidence_mirror._store_root() == REPO / EVIDENCE_REL
        finally:
            evidence_mirror._reset_state()

    def test_receipt_detail_keys_survive_sanitize_and_stay_out_of_projection(self, mirror_env):
        from framework.evidence.recorder import PROJECTION_ALLOWED_DETAIL

        emitter.emit("need_filed", actor="system", payload={"need_id": "n1"})
        (receipt,) = _receipts(mirror_env.store, f"evt-orgmirror-{_today()}")
        assert receipt["redactions"] == []  # no key tripped the redactor
        correlation_keys = {
            "org_event_id", "org_event_type", "org_created_at",
            "org_event_sha256", "ledger_date",
        }
        assert correlation_keys <= set(receipt["detail"])
        # Fail-closed projection: none of the join keys are officer-visible.
        assert not (correlation_keys & PROJECTION_ALLOWED_DETAIL)
