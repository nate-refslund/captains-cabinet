"""Phase 2 Batch B — R-1 authority/control-plane producer (G4).

Pins the batch's laws for the authority verbs:
* VOCABULARY: the new receipt classes (posture_cap_narrowed/cleared,
  posture_changed, germline_unlock_observed/germline_relock_observed,
  need_approved, kind_frozen) are registered in the emitter AND selected by
  the evidence-mirror allow-list, keeping the subset/disjointness laws green;
* RECEIPT SEMANTICS (per-class contract): every producer here records an
  already-happened control-plane change best-effort — a dead event plane
  NEVER blocks or fails the verb/brake (fault-injected per producer);
* HAPPY-PATH STABILITY: verb return shapes, cap-file contents, freeze mirror
  rows, and veto yml writes are byte-identical to BASE behavior — evidence is
  additive receipts only;
* §2.5 JOIN STRUCTURE: payloads/refs carry verb, provenance
  (captain-vs-machine), target ref, and prior-state -> new-state;
* WATCHER DISCIPLINE (emit-authority-transitions.py): transitions only,
  baseline seeds silently, an unobservable section carries prior state
  (error never reads as a state change), at-least-once on emit failure, and
  the off-platform germline guard never emits phantom unlock windows;
* NON-COLLISION: the new ``veto-scope:`` consequence refs mint no attention
  canonical_refs identity and never equal consequence.DIRECT_DEMOTE_REF.

Scratch stores only: org events ride per-test CABINET_EVENT_LOG_DIR tmp
dirs; the evidence mirror runs only against the pytest-fence override
(CABINET_EVIDENCE_MIRROR_STORE) exactly like test_evidence_mirror.py.
python3.12 only.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from framework import evidence_mirror
from framework.events import emitter

REPO = Path(__file__).resolve().parents[2]
WATCHER_SCRIPT = REPO / "cabinet" / "scripts" / "emit-authority-transitions.py"

NEW_CLASSES = (
    "posture_cap_narrowed",
    "posture_cap_cleared",
    "posture_changed",
    "germline_unlock_observed",
    "germline_relock_observed",
    "need_approved",
    "kind_frozen",
)


def _load_watcher():
    spec = importlib.util.spec_from_file_location(
        "emit_authority_transitions", WATCHER_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


watcher = _load_watcher()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _org_events(events_dir: Path) -> list:
    rows = []
    for f in sorted(Path(events_dir).glob("events-*.jsonl")):
        rows += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return rows


def _receipts(store: Path, trial_id: str) -> list:
    path = store / "trials" / trial_id / "events.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@pytest.fixture()
def events_env(tmp_path, monkeypatch):
    """Scratch org-event ledger; mirror fenced OFF (no store override)."""
    events = tmp_path / "events"
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(events))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
    return events


@pytest.fixture()
def mirror_env(tmp_path, monkeypatch):
    """Fence-open sandbox (the test_evidence_mirror.py pattern): scratch
    store + marker + isolated domain ledgers."""
    store = tmp_path / "evidence-store"
    marker = tmp_path / "degradations.jsonl"
    events = tmp_path / "events"
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(events))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
    monkeypatch.setenv("CABINET_EVIDENCE_MIRROR_STORE", str(store))
    monkeypatch.setenv("CABINET_EVIDENCE_MIRROR_MARKER", str(marker))
    evidence_mirror._reset_state()
    yield SimpleNamespace(store=store, marker=marker, events=events)
    evidence_mirror._reset_state()


# ---------------------------------------------------------------------------
# Vocabulary + allow-list law
# ---------------------------------------------------------------------------


class TestVocabulary:
    def test_new_classes_are_registered(self):
        for cls in NEW_CLASSES:
            assert cls in emitter.VALID_EVENT_TYPES, cls

    def test_new_classes_are_mirror_selected(self):
        for cls in NEW_CLASSES:
            assert cls in evidence_mirror.MIRRORED_ORG_EVENT_TYPES, cls

    def test_allow_list_laws_still_hold(self):
        assert evidence_mirror.MIRRORED_ORG_EVENT_TYPES < emitter.VALID_EVENT_TYPES
        assert not (evidence_mirror.MIRRORED_ORG_EVENT_TYPES
                    & evidence_mirror.NEVER_MIRRORED_EXHAUST)

    def test_kill_switch_classes_were_already_selected(self):
        # The watcher's kill-switch leg emits PRE-registered classes — R-1
        # added emitters, not vocabulary, for these two.
        for cls in ("kill_switch_activated", "kill_switch_deactivated"):
            assert cls in emitter.VALID_EVENT_TYPES
            assert cls in evidence_mirror.MIRRORED_ORG_EVENT_TYPES

    def test_aggregate_map_resolves_new_classes(self):
        assert emitter._resolve_aggregate(
            "posture_cap_narrowed", {"posture": "guardian"}
        ) == ("system", "guardian")
        assert emitter._resolve_aggregate(
            "germline_unlock_observed", {"boundary_id": "germline"}
        ) == ("system", "germline")
        assert emitter._resolve_aggregate(
            "need_approved", {"need_id": "NEED-1a2b3c4d"}
        ) == ("need", "NEED-1a2b3c4d")
        # kind_frozen deliberately unmapped — prefix-derived like its sibling
        # kind_unfrozen so the freeze/unfreeze pair aggregates alike.
        assert emitter._resolve_aggregate("kind_frozen", {"kind": "board_status"})[0] \
            == emitter._resolve_aggregate("kind_unfrozen", {"kind": "board_status"})[0]


# ---------------------------------------------------------------------------
# Mirror receipts for the new classes (org-event chokepoint)
# ---------------------------------------------------------------------------


class TestMirrorReceipts:
    def test_posture_cap_receipt_lands_signed(self, mirror_env):
        event = emitter.emit(
            "posture_cap_narrowed",
            actor="captain:binder",
            payload={"posture": "guardian", "cap": "guardian",
                     "prior_cap": None, "surface": "binder"},
        )
        trial_id = f"evt-orgmirror-{_today()}"
        assert event["payload"][evidence_mirror.PAYLOAD_KEY] == {"trial_id": trial_id}
        receipts = _receipts(mirror_env.store, trial_id)
        assert [r["detail"]["org_event_type"] for r in receipts] == [
            "posture_cap_narrowed"]
        assert receipts[0]["correlation_id"] == event["id"]
        # Fixed chokepoint identity — never payload-derived (A6).
        assert receipts[0]["actor"] == {"kind": "system", "id": "org-event-mirror"}

    def test_germline_window_receipt_lands(self, mirror_env):
        emitter.emit(
            "germline_unlock_observed",
            actor="authority-watch",
            payload={"boundary_id": "germline", "unlocked_count": 2,
                     "locked_count": 70, "armed": False,
                     "changed_paths": ["framework/authority/needs.py"],
                     "changed_count": 1, "precision": "sweep-cadence"},
        )
        receipts = _receipts(mirror_env.store, f"evt-orgmirror-{_today()}")
        assert [r["detail"]["org_event_type"] for r in receipts] == [
            "germline_unlock_observed"]

    def test_receipt_detail_carries_no_payload_copy(self, mirror_env):
        # Redaction doctrine: ids + digests only — the germline path list
        # must never ride into the signed receipt detail.
        emitter.emit(
            "germline_unlock_observed",
            actor="authority-watch",
            payload={"boundary_id": "germline",
                     "changed_paths": ["framework/authority/needs.py"]},
        )
        (receipt,) = _receipts(mirror_env.store, f"evt-orgmirror-{_today()}")
        assert "changed_paths" not in json.dumps(receipt["detail"])


# ---------------------------------------------------------------------------
# Binder posture verb — posture_cap_narrowed / posture_cap_cleared receipts
# ---------------------------------------------------------------------------


@pytest.fixture()
def wired_root(tmp_path, monkeypatch):
    """A tmp cabinet root with the needs plane wired (the AX-7 test shape)
    plus a scratch org-event ledger to read receipts back from."""
    monkeypatch.delenv("CABINET_POSTURE", raising=False)
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    monkeypatch.setenv("CABINET_ID", "main")
    events = tmp_path / "org-events"
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(events))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
    return SimpleNamespace(root=tmp_path, events=events)


def _handle(text, **kw):
    from framework.frontdoor import binder_wire
    kw.setdefault("pending_source", lambda: [])
    kw.setdefault("emit", lambda **e: None)
    kw.setdefault("redis_get", lambda k: "")
    kw.setdefault("present", lambda m: None)
    return binder_wire.handle_captain_update(text, "", **kw)


class TestBinderPostureReceipts:
    def test_narrow_emits_cap_receipt_with_prior_state(self, wired_root):
        r = _handle("posture guardian")
        assert r["handled"] is True and r["posture_verb"] == "narrow"
        rows = [e for e in _org_events(wired_root.events)
                if e["event_type"] == "posture_cap_narrowed"]
        assert len(rows) == 1
        assert rows[0]["actor"] == "captain:binder"
        p = rows[0]["payload"]
        assert p["cap"] == "guardian" and p["prior_cap"] is None
        assert p["posture"] == "guardian"       # no ruling -> guardian, capped
        assert p["surface"] == "binder"

    def test_renarrow_carries_prior_cap(self, wired_root):
        _handle("posture guardian")
        _handle("posture earn_up")
        rows = [e for e in _org_events(wired_root.events)
                if e["event_type"] == "posture_cap_narrowed"]
        assert [(e["payload"]["prior_cap"], e["payload"]["cap"]) for e in rows] \
            == [(None, "guardian"), ("guardian", "earn_up")]

    def test_clear_emits_cleared_receipt(self, wired_root):
        _handle("posture earn_up")
        _handle("posture clear")
        rows = [e for e in _org_events(wired_root.events)
                if e["event_type"] == "posture_cap_cleared"]
        assert len(rows) == 1
        p = rows[0]["payload"]
        assert p["prior_cap"] == "earn_up" and p["cap"] is None

    def test_clear_of_nothing_emits_no_receipt(self, wired_root):
        r = _handle("posture clear")
        assert r["handled"] is True and r["posture_verb"] == "clear"
        assert [e for e in _org_events(wired_root.events)
                if e["event_type"].startswith("posture_cap")] == []

    def test_refused_and_failed_verbs_emit_nothing(self, wired_root):
        _handle("posture sovereign")           # refused: widening never a verb
        assert _org_events(wired_root.events) == []

    def test_write_failure_emits_nothing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CABINET_POSTURE", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
        monkeypatch.setenv("CABINET_ID", "main")
        events = tmp_path / "org-events"
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(events))
        # Sabotage the cap file's directory root (derived from posture.py's
        # own canonical path helper — never a re-typed layout literal).
        from framework.authority import posture
        posture.narrow_cap_path(tmp_path).parents[1].write_text(
            "not a directory")
        r = _handle("posture guardian")
        assert r["posture_verb"] == "narrow-failed"
        assert _org_events(events) == []

    def test_emit_failure_never_blocks_the_verb(self, wired_root, monkeypatch):
        """RECEIPT law: a dead event plane must not fail the cap write."""
        from framework.authority import posture

        def boom(*a, **k):
            raise RuntimeError("event plane down")

        monkeypatch.setattr(emitter, "emit", boom)
        logged = []
        r = _handle("posture guardian", log=logged.append)
        assert r["handled"] is True and r["posture_verb"] == "narrow"
        assert posture.narrow_cap(wired_root.root) == "guardian"
        assert any("posture cap receipt emit failed" in m for m in logged)


# ---------------------------------------------------------------------------
# needs.py — the Captain's grant verb decision moment emits need_approved
# ---------------------------------------------------------------------------


class TestNeedApproved:
    def _file(self, tmp_path):
        from framework.authority import needs
        return needs.file_need(
            "standing_grant", risk_class="external_comms",
            action_type="external_email", lane="bakery",
            why="test", filed_by="t", root=tmp_path,
        )

    def test_approved_pending_apply_emits_need_approved(self, tmp_path, events_env, monkeypatch):
        monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
        from framework.authority import needs
        nid = self._file(tmp_path)
        row = needs.mark(nid, "approved_pending_apply", by="captain:binder",
                         root=tmp_path)
        assert row["status"] == "approved_pending_apply"
        rows = [e for e in _org_events(events_env)
                if e["event_type"] == "need_approved"]
        assert len(rows) == 1
        p = rows[0]["payload"]
        assert p["need_id"] == nid
        assert p["status"] == "approved_pending_apply"
        # §2.5 cell fields ride structurally (needs._emit already carried them)
        assert p["risk_class"] == "external_comms"
        assert p["action_type"] == "external_email" and p["lane"] == "bakery"

    def test_approved_and_granted_stay_distinct_verbs(self, tmp_path, events_env, monkeypatch):
        monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
        from framework.authority import needs
        nid = self._file(tmp_path)
        needs.mark(nid, "approved_pending_apply", by="captain:binder", root=tmp_path)
        needs.mark(nid, "granted", by="grant-apply.sh", root=tmp_path)
        types = [e["event_type"] for e in _org_events(events_env)]
        assert types.count("need_approved") == 1
        assert types.count("need_granted") == 1

    def test_mark_survives_dead_event_plane(self, tmp_path, events_env, monkeypatch):
        monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
        from framework.authority import needs

        nid = self._file(tmp_path)
        monkeypatch.setattr(emitter, "emit",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
        row = needs.mark(nid, "approved_pending_apply", by="captain:binder",
                         root=tmp_path)
        assert row is not None and row["status"] == "approved_pending_apply"


# ---------------------------------------------------------------------------
# action_undo.freeze — the kind_frozen receipt (brake never blocked)
# ---------------------------------------------------------------------------


@pytest.fixture()
def undo_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_UNDO_DIR", str(tmp_path / "undo"))
    events = tmp_path / "events"
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(events))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
    return SimpleNamespace(undo=tmp_path / "undo", events=events)


class TestKindFrozen:
    def _freeze(self, source="machine"):
        from framework.frontdoor import action_undo
        return action_undo.freeze(
            "board_status", "3 reverts in 24h",
            redis_set=lambda k, v, ttl: None,
            file_need_fn=lambda **kw: None,
            source=source,
        )

    def test_freeze_emits_kind_frozen(self, undo_env):
        row = self._freeze()
        assert row["op"] == "freeze"                       # return unchanged
        rows = [e for e in _org_events(undo_env.events)
                if e["event_type"] == "kind_frozen"]
        assert len(rows) == 1
        assert rows[0]["actor"] == "action_undo.machine"   # machine provenance
        p = rows[0]["payload"]
        assert p["kind"] == "board_status" and p["source"] == "machine"
        assert p["reason"].startswith("3 reverts")

    def test_captain_source_rides_actor(self, undo_env):
        self._freeze(source="captain")
        (row,) = [e for e in _org_events(undo_env.events)
                  if e["event_type"] == "kind_frozen"]
        assert row["actor"] == "action_undo.captain"

    def test_freeze_and_unfreeze_events_are_symmetric(self, undo_env):
        from framework.frontdoor import action_undo
        self._freeze()
        action_undo.unfreeze(
            "board_status", "green canary", source="captain",
            redis_get=lambda k: "", redis_del=lambda k: None,
            canary_receipt=None,
        )
        types = [e["event_type"] for e in _org_events(undo_env.events)]
        assert "kind_frozen" in types and "kind_unfrozen" in types

    def test_dead_event_plane_never_blocks_the_brake(self, undo_env, monkeypatch):
        monkeypatch.setattr(emitter, "emit",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
        row = self._freeze()
        assert row["op"] == "freeze" and row["kind"] == "board_status"
        # The durable mirror row landed even though the receipt did not.
        mirror = undo_env.undo / "frozen-kinds.jsonl"
        assert mirror.is_file()
        assert json.loads(mirror.read_text().splitlines()[-1])["op"] == "freeze"


# ---------------------------------------------------------------------------
# veto_registry — structured veto-scope refs (§2.5 cell join, non-identity)
# ---------------------------------------------------------------------------


class TestVetoScopeRefs:
    def _record(self, tmp_path, scope):
        from framework.frontdoor import veto_registry
        captured = []
        veto = veto_registry.record_veto(
            scope, "never do this", ts="2026-07-17T10:00:00Z",
            path=tmp_path / "captain-vetoes.yml",
            emit=lambda **ev: captured.append(ev),
        )
        return veto, captured

    def test_refs_carry_cell_fields(self, tmp_path):
        veto, captured = self._record(
            tmp_path, {"action_type": "board_status", "lane": "bakery"})
        (ev,) = captured
        assert ev["refs"] == [
            f"veto:{veto['id']}",
            "veto-scope:action_type=board_status",
            "veto-scope:lane=bakery",
        ]
        # The ROW keeps its deliberate action_type absence (graduation law).
        assert "action_type" not in ev

    def test_partial_scope_emits_only_present_fields(self, tmp_path):
        veto, captured = self._record(tmp_path, {"board": "jobs"})
        (ev,) = captured
        assert ev["refs"] == [f"veto:{veto['id']}"]

    def test_lift_carries_the_same_ref_shape(self, tmp_path):
        from framework.frontdoor import veto_registry
        veto, _ = self._record(
            tmp_path, {"action_type": "board_status", "lane": "bakery"})
        captured = []
        veto_registry.lift_veto(
            veto["id"], ts="2026-07-17T11:00:00Z",
            path=tmp_path / "captain-vetoes.yml",
            emit=lambda **ev: captured.append(ev),
        )
        (ev,) = captured
        assert "veto-scope:action_type=board_status" in ev["refs"]

    def test_scope_refs_mint_no_canonical_identity(self):
        """Non-collision pin: veto-scope refs are identity-free for the
        attention plane (the evidence-trial: precedent) and never equal the
        graduation demote sentinel."""
        from framework.attention.situation import canonical_refs
        from framework.fidelity.consequence import DIRECT_DEMOTE_REF
        refs = ["veto-scope:action_type=board_status", "veto-scope:lane=bakery"]
        assert canonical_refs(refs) == frozenset()
        assert all(r != DIRECT_DEMOTE_REF for r in refs)
        # The id ref itself still extracts (unchanged behavior).
        assert canonical_refs(["veto:veto-001"]) == frozenset({"veto:veto-001"})


# ---------------------------------------------------------------------------
# The authority-transitions watcher — pure sweep logic
# ---------------------------------------------------------------------------


class TestWatcherSweep:
    def test_baseline_seeds_silently(self):
        observed = {"killswitch": "inactive",
                    "germline": {"unlocked": [], "locked_count": 70},
                    "posture": {"resolved": "guardian", "narrow_cap": None,
                                "ruling_posture": None, "ruling_attested": False}}
        result = watcher.sweep(observed, None)
        assert result["baseline"] is True
        assert result["transitions"] == []
        assert result["current"]["killswitch"] == "inactive"

    def test_kill_switch_flip_emits_transitions(self):
        prev = {"killswitch": "inactive"}
        result = watcher.sweep({"killswitch": "active", "germline": None,
                                "posture": None}, prev)
        (t,) = result["transitions"]
        assert t["event_type"] == "kill_switch_activated"
        assert t["payload"]["prior_state"] == "inactive"
        assert t["payload"]["new_state"] == "active"
        assert t["payload"]["killswitch_id"] == "cabinet:killswitch"

        back = watcher.sweep({"killswitch": "inactive", "germline": None,
                              "posture": None}, result["current"])
        (t2,) = back["transitions"]
        assert t2["event_type"] == "kill_switch_deactivated"

    def test_unobservable_sections_carry_prior_state(self):
        prev = {"killswitch": "active",
                "germline": {"unlocked": ["a"], "locked_count": 69},
                "posture": {"resolved": "guardian"}}
        result = watcher.sweep(
            {"killswitch": None, "germline": None, "posture": None}, prev)
        assert result["transitions"] == []
        assert result["current"] == prev      # error never reads as a change

    def test_no_change_emits_nothing(self):
        prev = {"killswitch": "inactive",
                "germline": {"unlocked": [], "locked_count": 70}}
        result = watcher.sweep(
            {"killswitch": "inactive",
             "germline": {"unlocked": [], "locked_count": 70},
             "posture": None}, prev)
        assert result["transitions"] == []

    def test_germline_window_open_and_close(self):
        prev = {"germline": {"unlocked": [], "locked_count": 70}}
        opened = watcher.sweep(
            {"killswitch": None, "posture": None,
             "germline": {"unlocked": ["framework/authority/needs.py",
                                       "framework/learning/gate.py"],
                          "locked_count": 68}}, prev)
        (t,) = opened["transitions"]
        assert t["event_type"] == "germline_unlock_observed"
        assert t["payload"]["changed_paths"] == [
            "framework/authority/needs.py", "framework/learning/gate.py"]
        assert t["payload"]["armed"] is False
        assert t["payload"]["unlocked_count"] == 2
        assert t["payload"]["precision"] == "sweep-cadence"

        closed = watcher.sweep(
            {"killswitch": None, "posture": None,
             "germline": {"unlocked": [], "locked_count": 70}},
            opened["current"])
        (t2,) = closed["transitions"]
        assert t2["event_type"] == "germline_relock_observed"
        assert t2["payload"]["armed"] is True
        assert t2["payload"]["changed_count"] == 2

    def test_partial_relock_emits_both_directions(self):
        prev = {"germline": {"unlocked": ["a", "b"], "locked_count": 68}}
        result = watcher.sweep(
            {"killswitch": None, "posture": None,
             "germline": {"unlocked": ["b", "c"], "locked_count": 68}}, prev)
        types = sorted(t["event_type"] for t in result["transitions"])
        assert types == ["germline_relock_observed", "germline_unlock_observed"]

    def test_posture_change_carries_prior_and_new(self):
        prev = {"posture": {"resolved": "guardian", "narrow_cap": None,
                            "ruling_posture": None, "ruling_attested": False}}
        new = {"resolved": "earn_up", "narrow_cap": "earn_up",
               "ruling_posture": None, "ruling_attested": False}
        result = watcher.sweep(
            {"killswitch": None, "germline": None, "posture": new}, prev)
        (t,) = result["transitions"]
        assert t["event_type"] == "posture_changed"
        assert t["payload"]["posture"] == "earn_up"
        assert t["payload"]["prior"]["resolved"] == "guardian"
        assert t["payload"]["new"] == new
        assert t["payload"]["resolution_scope"] == "watcher-process"

    def test_section_first_sighting_after_baseline_seeds_silently(self):
        # germline was unobservable at baseline; coming online later is a
        # SEED for that section, never a fabricated window event.
        prev = {"killswitch": "inactive"}
        result = watcher.sweep(
            {"killswitch": "inactive", "posture": None,
             "germline": {"unlocked": ["a"], "locked_count": 69}}, prev)
        assert result["transitions"] == []
        assert result["current"]["germline"]["unlocked"] == ["a"]


# ---------------------------------------------------------------------------
# The watcher end-to-end — state file + org emits + at-least-once
# ---------------------------------------------------------------------------


class TestWatcherMain:
    def _run(self, monkeypatch, state, *, killswitch=None, germline=None,
             posture=None):
        monkeypatch.setattr(watcher, "observe_killswitch", lambda: killswitch)
        monkeypatch.setattr(watcher, "observe_germline", lambda root=None: germline)
        monkeypatch.setattr(watcher, "observe_posture", lambda: posture)
        return watcher.main(["--state-file", str(state)])

    def test_seed_then_transition_then_quiet(self, tmp_path, monkeypatch, events_env):
        state = tmp_path / "state.json"
        assert self._run(monkeypatch, state, killswitch="inactive") == 0
        assert _org_events(events_env) == []              # baseline: silent

        assert self._run(monkeypatch, state, killswitch="active") == 0
        rows = _org_events(events_env)
        assert [e["event_type"] for e in rows] == ["kill_switch_activated"]
        assert rows[0]["actor"] == "authority-watch"

        assert self._run(monkeypatch, state, killswitch="active") == 0
        assert len(_org_events(events_env)) == 1          # quiet sweep: nothing

    def test_at_least_once_on_emit_failure(self, tmp_path, monkeypatch, events_env):
        state = tmp_path / "state.json"
        self._run(monkeypatch, state, killswitch="inactive")

        def boom(*a, **k):
            raise RuntimeError("event plane down")

        monkeypatch.setattr(emitter, "emit", boom)
        assert self._run(monkeypatch, state, killswitch="active") == 0
        # Section reverted: the state file still says inactive …
        assert json.loads(state.read_text())["state"]["killswitch"] == "inactive"

        monkeypatch.undo()
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(events_env))
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
        # … so the SAME transition re-detects and re-emits next sweep.
        assert self._run(monkeypatch, state, killswitch="active") == 0
        assert [e["event_type"] for e in _org_events(events_env)] == [
            "kill_switch_activated"]

    def test_corrupt_state_reseeds_without_emitting(self, tmp_path, monkeypatch,
                                                    events_env, capsys):
        state = tmp_path / "state.json"
        state.write_text("{not json")
        assert self._run(monkeypatch, state, killswitch="active") == 0
        assert _org_events(events_env) == []
        assert "re-seeding baseline" in capsys.readouterr().err

    def test_dry_run_writes_no_state_and_emits_nothing(self, tmp_path,
                                                       monkeypatch, events_env):
        state = tmp_path / "state.json"
        self._run(monkeypatch, state, killswitch="inactive")
        monkeypatch.setattr(watcher, "observe_killswitch", lambda: "active")
        monkeypatch.setattr(watcher, "observe_germline", lambda root=None: None)
        monkeypatch.setattr(watcher, "observe_posture", lambda: None)
        assert watcher.main(["--state-file", str(state), "--dry-run"]) == 0
        assert _org_events(events_env) == []
        assert json.loads(state.read_text())["state"]["killswitch"] == "inactive"


# ---------------------------------------------------------------------------
# The watcher observers — lock-set parse + platform guard
# ---------------------------------------------------------------------------


class TestWatcherObservers:
    def test_lock_set_parses_the_real_script(self):
        files, dirs = watcher.germline_lock_set(
            REPO / "cabinet" / "scripts" / "germline-lock.sh")
        assert "framework/authority/needs.py" in files
        assert "framework/frontdoor/action_undo.py" in files
        assert "framework/evidence" in dirs
        assert all(not p.startswith("#") for p in files + dirs)

    def test_lock_set_none_on_missing_script(self, tmp_path):
        assert watcher.germline_lock_set(tmp_path / "nope.sh") is None

    def test_off_platform_germline_is_unobservable_not_unlocked(self, monkeypatch):
        """The phantom-window guard: schg cannot attest off-Darwin, so the
        boundary must read UNOBSERVABLE (None), never all-unlocked."""
        from framework.authority import posture
        monkeypatch.setattr(posture, "infer_deployment_target", lambda: "macbook")
        monkeypatch.setattr(sys, "platform", "linux")
        assert watcher.observe_germline() is None

    def test_observable_platform_probes_via_posture_backend(self, tmp_path,
                                                            monkeypatch):
        from framework.authority import posture
        scripts = tmp_path / "cabinet" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "germline-lock.sh").write_text(
            'FILES=(\n  "locked.txt"\n  "open.txt"   # comment\n)\n'
            'DIRS=(\n)\n')
        (tmp_path / "locked.txt").write_text("x")
        (tmp_path / "open.txt").write_text("y")
        monkeypatch.setattr(posture, "infer_deployment_target", lambda: "macbook")
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(
            posture, "is_locked",
            lambda p, target=None: Path(p).name == "locked.txt")
        observed = watcher.observe_germline(tmp_path)
        assert observed == {"unlocked": ["open.txt"], "locked_count": 1}

    def test_absent_paths_are_skipped_like_the_lock_script(self, tmp_path,
                                                           monkeypatch):
        from framework.authority import posture
        scripts = tmp_path / "cabinet" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "germline-lock.sh").write_text(
            'FILES=(\n  "ghost.txt"\n)\nDIRS=(\n)\n')
        monkeypatch.setattr(posture, "infer_deployment_target", lambda: "macbook")
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(posture, "is_locked", lambda p, target=None: False)
        assert watcher.observe_germline(tmp_path) == {
            "unlocked": [], "locked_count": 0}

    def test_redis_hostport_parity_with_kill_switch_sh(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        assert watcher._redis_hostport() == ("127.0.0.1", "6379")
        monkeypatch.setenv("REDIS_URL", "redis://redis:6379")
        assert watcher._redis_hostport() == ("127.0.0.1", "6379")  # residue guard
        monkeypatch.setenv("REDIS_URL", "redis://10.0.0.5:6380")
        assert watcher._redis_hostport() == ("10.0.0.5", "6380")

    def test_posture_observation_never_files_needs(self, tmp_path, monkeypatch):
        """file_needs=False discipline: observing must not append to the
        needs ledger even when the needs plane is wired."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
        monkeypatch.delenv("CABINET_POSTURE", raising=False)
        # A corrupt ruling is exactly the shape that files a config need on
        # a file_needs=True read.  Path derived from posture.py's own
        # canonical helper — never a re-typed layout literal.
        from framework.authority import posture
        ruling = posture.posture_path(tmp_path)
        ruling.parent.mkdir(parents=True)
        ruling.write_text("posture: [broken")
        observed = watcher.observe_posture()
        assert observed is not None and observed["resolved"] == "guardian"
        ledger = tmp_path / "shared" / "interfaces" / "needs-ledger.jsonl"
        assert not ledger.exists()
