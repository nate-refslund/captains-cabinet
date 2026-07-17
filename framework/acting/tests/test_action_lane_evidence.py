"""Batch B (G1) — act-class evidence-before-action on the action lane.

Scratch stores ONLY: under pytest the executor's evidence seam resolves OFF
unless a store is injected explicitly (``evidence_store=`` /
``CABINET_ACTION_EVIDENCE_STORE``) — the evidence_mirror pytest fence — so
nothing here can ever touch ``instance/evidence/v1`` (the live runtime store);
the undo journal is tmp-pointed per test (``CABINET_UNDO_DIR``).

What this file proves (the Batch B review contract):

1. HAPPY-PATH STABILITY — recording ON produces the exact BASE lane effects:
   identical return dict, identical Monday transport calls, identical journal
   rows modulo minted ids — the only structural delta is the additive
   ``evidence_trial_id`` correlation key.
2. The trial verifies (stored bytes == hashed bytes, chain + signatures) and
   carries the full choreography with BOTH-direction undo-journal correlation
   (row -> trial via ``evidence_trial_id``; trial -> row via the
   ``undo-journal:<jid>`` receipt link; both -> proposal via the cid).
3. FAIL-CLOSED, exclusively on evidence-plane failure — an unwritable store
   refuses the action BEFORE any mutation through the lane's EXISTING refusal
   shapes (act-first: the propose_only downgrade dict; approved: the ok:False
   error dict); a mid-chain failure stops the chain and reports what ran.
4. The reconciler's machine outcome labels (ttl_ok / silent_revert with
   judge-vs-human provenance) land as verification+outcome receipts on the
   SAME trial, degrade LOUD on a broken plane, and NEVER block the
   consequence-ledger supersede (receipt-class law).
5. Daemon process attestation rides every event as
   ``attestation_mode: process`` with the attested actor/component.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.evidence import identity as ev_identity
from framework.evidence.lifecycle import ActLifecycle
from framework.evidence.recorder import EvidenceRecorder
from framework.evidence.verifier import verify_trial
from framework.frontdoor import action_exec as ax
from framework.frontdoor import action_reconcile as ar
from framework.frontdoor import action_undo as au

CID = "c" * 32                       # uuid4-hex-shaped correlation id


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    """tmp undo journal, neutered Redis transports, per-test identity reset
    (identity is process-global freeze-once; tests must not leak it)."""
    monkeypatch.setenv("CABINET_UNDO_DIR", str(tmp_path / "undo"))
    monkeypatch.delenv("CABINET_ACTION_EVIDENCE_STORE", raising=False)
    monkeypatch.setattr(ax, "_redis", lambda *a, **k: "")
    monkeypatch.setattr(au, "_default_redis_set", lambda *a, **k: None)
    monkeypatch.setattr(au, "_default_redis_get", lambda *a, **k: "")
    monkeypatch.setattr(au, "_default_redis_del", lambda *a, **k: None)
    monkeypatch.setattr(ev_identity, "_ATTESTED", None)
    yield


def _surfaces():
    return {"denylist": {},
            "caps": {"per_kind_per_day": 20, "estate_per_day": 40}}


class MondaySpy:
    def __init__(self):
        self.calls = []

    def __call__(self, query, variables):
        self.calls.append((query, variables))
        if "create_item" in query:
            return {"create_item": {"id": "12345"}}
        return {"create_update": {"id": "u1"}, "change_column_value": {"id": "c1"}}


def _create_steps(n=1):
    return [{"kind": "monday_task_create",
             "payload": {"board_id": "42424242", "title": f"t{i}"}}
            for i in range(n)]


def _getter(steps, cid=CID):
    body = {"lane": "bakery", "steps": steps, "cid": cid,
            "steps_sha256": ax._canonical_sha(steps)}
    rec = json.dumps(body)

    def g(k):
        return rec if k.startswith("cabinet:action:") else ""
    return g


def _trials(store):
    d = Path(store) / "trials"
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.exists() else []


def _events(store, trial_id):
    path = Path(store) / "trials" / trial_id / "events.jsonl"
    return [json.loads(line) for line in path.read_text().split("\n")
            if line.strip()]


# --- 1. happy-path stability (recording on == BASE effects) ------------------

def test_happy_path_effects_identical_with_recording_on(tmp_path, monkeypatch):
    """The lane's artifacts with recording ON are the BASE artifacts: same
    return dict, same transport calls, same journal rows modulo minted ids —
    the additive evidence_trial_id key is the ONLY structural delta."""
    monkeypatch.setattr(ax, "_load_act_first_surfaces", lambda: _surfaces())
    steps = _create_steps(2)

    def run(undo_dir, store):
        monkeypatch.setenv("CABINET_UNDO_DIR", str(undo_dir))
        spy = MondaySpy()
        r = ax.deliver_action("pid-parity", act_first=True,
                              redis_get=_getter(steps), monday_post=spy,
                              osascript=lambda c: "ok",
                              redis_incr=lambda k, t: None,
                              evidence_store=store)
        return r, spy.calls, au._read_journal()

    # OFF = the BASE path (pytest fence keeps the default store disabled).
    r_off, calls_off, rows_off = run(tmp_path / "undo-off", None)
    r_on, calls_on, rows_on = run(tmp_path / "undo-on", tmp_path / "ev")

    assert r_on == r_off == {
        "ok": True, "via": "action-lane", "dest": "bakery",
        "executed": r_off["executed"]}
    assert [e["kind"] for e in r_on["executed"]] == ["monday_task_create"] * 2
    assert calls_on == calls_off                 # identical transport traffic

    volatile = {"jid", "ts", "ttl_expires_at", "executed_at",
                "evidence_trial_id"}

    def scrub(rows):
        return [{k: v for k, v in row.items() if k not in volatile}
                for row in rows]

    assert scrub(rows_on) == scrub(rows_off)     # journal rows identical
    assert all("evidence_trial_id" in row for row in rows_on)
    assert all("evidence_trial_id" not in row for row in rows_off)


def test_dry_run_records_no_evidence(tmp_path):
    """dry_run is the contractually side-effect-free probe: no trial, no
    store directory, even with an explicit store injected."""
    store = tmp_path / "ev"
    r = ax.deliver_action("pid-dry", dry_run=True,
                          redis_get=_getter(_create_steps(1)),
                          evidence_store=store)
    assert r["ok"] is True and r["executed"][0]["dry_run"] is True
    assert not store.exists()


def test_pytest_fence_keeps_default_store_off(tmp_path, monkeypatch):
    """Under pytest the DEFAULT store resolves to None (never the live
    instance/evidence/v1) unless a scratch override is set — the coded
    2026-07-04 leak lesson."""
    assert ax._evidence_store_root(None) is None
    assert ar._evidence_store_root(None) is None
    monkeypatch.setenv("CABINET_ACTION_EVIDENCE_STORE", str(tmp_path / "s"))
    assert ax._evidence_store_root(None) == tmp_path / "s"
    assert ar._evidence_store_root(None) == tmp_path / "s"
    # explicit always wins
    assert ax._evidence_store_root(tmp_path / "x") == tmp_path / "x"


# --- 2. the trial: choreography, verification, correlation -------------------

def test_trial_verifies_with_full_choreography_and_correlation(tmp_path, monkeypatch):
    monkeypatch.setattr(ax, "_load_act_first_surfaces", lambda: _surfaces())
    store = tmp_path / "ev"
    spy = MondaySpy()
    r = ax.deliver_action("pid-choreo", act_first=True,
                          redis_get=_getter(_create_steps(1)), monday_post=spy,
                          osascript=lambda c: "ok", redis_incr=lambda k, t: None,
                          evidence_store=store)
    assert r["ok"] is True
    trials = _trials(store)
    assert len(trials) == 1 and trials[0].startswith("actlane-")
    trial_id = trials[0]

    report = verify_trial(store, trial_id)       # determinism: bytes == hashes
    assert report["ok"] is True, report

    evs = _events(store, trial_id)
    assert [(e["phase"], e["status"]) for e in evs] == [
        ("intent", "started"), ("policy", "proposed"),
        ("execution", "started"), ("verification", "verified"),
        ("receipt", "succeeded"), ("outcome", "succeeded")]
    # correlation: every event rides the stored record's cid …
    assert all(e["correlation_id"] == CID for e in evs)
    # … the receipt links back to the undo-journal row and the proposal …
    rows = au._read_journal()
    assert len(rows) == 1
    jid = rows[0]["jid"]
    receipt = next(e for e in evs if e["phase"] == "receipt")
    assert "undo-journal:" + jid in receipt["links"]
    assert "cabinet-proposal-id:" + CID in receipt["links"]
    # … and the journal row points back at THIS trial (both directions).
    assert rows[0]["evidence_trial_id"] == trial_id
    # intent carries the card shape; pid rides as a digest only (not ID-safe).
    intent = evs[0]
    assert intent["detail"]["lane"] == "bakery"
    assert intent["detail"]["steps_total"] == 1
    assert intent["detail"]["act_first"] is True
    assert len(intent["detail"]["pid_sha256"]) == 64
    assert "pid-choreo" not in json.dumps(intent)


def test_approved_path_records_the_same_trial_shape(tmp_path):
    """The Captain-approved (binder) path records too — same choreography,
    act_first False in the intent detail."""
    store = tmp_path / "ev"
    spy = MondaySpy()
    r = ax.deliver_action("pid-approved",
                          redis_get=_getter(_create_steps(1)), monday_post=spy,
                          osascript=lambda c: "ok", evidence_store=store)
    assert r["ok"] is True
    evs = _events(store, _trials(store)[0])
    assert [(e["phase"], e["status"]) for e in evs][-1] == ("outcome", "succeeded")
    assert evs[0]["detail"]["act_first"] is False


def test_precondition_refusal_carries_refused_tail(tmp_path, monkeypatch):
    """An existing refusal (killswitch) rides its EXISTING return dict AND
    lands the refused tail on the trial — no new return shape."""
    monkeypatch.setattr(ax, "_load_act_first_surfaces", lambda: _surfaces())
    store = tmp_path / "ev"
    steps = _create_steps(1)
    body = {"lane": "bakery", "steps": steps, "cid": CID,
            "steps_sha256": ax._canonical_sha(steps)}
    rec_json = json.dumps(body)

    def g(k):
        if k == "cabinet:killswitch":
            return "active"
        return rec_json if k.startswith("cabinet:action:") else ""

    spy = MondaySpy()
    r = ax.deliver_action("pid-ks", act_first=True, redis_get=g,
                          monday_post=spy, osascript=lambda c: "ok",
                          redis_incr=lambda k, t: None, evidence_store=store)
    assert r["ok"] is False and r.get("halted") == "killswitch"
    assert spy.calls == []                        # nothing ran
    evs = _events(store, _trials(store)[0])
    assert [(e["phase"], e["status"]) for e in evs] == [
        ("intent", "started"), ("policy", "proposed"),
        ("policy", "refused"), ("outcome", "refused")]
    assert evs[-1]["detail"]["error_code"] == "killswitch"


# --- 3. fail-closed, exclusively on injected evidence-plane failure ----------

def test_fail_closed_unwritable_store_act_first_downgrades(tmp_path, monkeypatch):
    """Evidence-before-action: an unwritable store refuses the whole card
    through the act-first propose_only downgrade shape; the mutation and the
    journal NEVER run."""
    monkeypatch.setattr(ax, "_load_act_first_surfaces", lambda: _surfaces())
    bad = tmp_path / "not-a-dir"
    bad.write_text("a FILE where the store dir must be")
    spy = MondaySpy()
    r = ax.deliver_action("pid-fc1", act_first=True,
                          redis_get=_getter(_create_steps(1)), monday_post=spy,
                          osascript=lambda c: "ok", redis_incr=lambda k, t: None,
                          evidence_store=bad)
    assert r == {"ok": False, "gate": "propose_only", "via": "action-lane",
                 "dest": "bakery", "executed": [], "held": [],
                 "reasons": r["reasons"]}         # the existing downgrade shape
    assert len(r["reasons"]) == 1
    assert "evidence recording unavailable" in r["reasons"][0]
    assert spy.calls == []                        # the mutation NEVER ran
    assert au._read_journal() == []               # nothing journaled either


def test_fail_closed_unwritable_store_approved_path_errors(tmp_path):
    """The approved path fails closed too, through the ok:False error shape
    (the named doctrine inversion, broken-evidence-plane branch only)."""
    bad = tmp_path / "not-a-dir"
    bad.write_text("file")
    spy = MondaySpy()
    r = ax.deliver_action("pid-fc2",
                          redis_get=_getter(_create_steps(1)), monday_post=spy,
                          osascript=lambda c: "ok", evidence_store=bad)
    assert r["ok"] is False and "gate" not in r
    assert r["executed"] == []
    assert "evidence recording unavailable" in r["error"]
    assert spy.calls == []


def test_mid_chain_evidence_failure_stops_chain(tmp_path, monkeypatch):
    """Chain rule under a mid-run evidence-plane failure: step 1 acts and is
    reported; step 2's pre-mutation record fails, so step 2 NEVER runs and
    the card downgrades through the existing shape."""
    monkeypatch.setattr(ax, "_load_act_first_surfaces", lambda: _surfaces())
    store = tmp_path / "ev"
    real = ActLifecycle.record
    seen = {"n": 0}

    def flaky(self, *, phase, status, **kw):
        if phase == "execution" and status == "started":
            seen["n"] += 1
            if seen["n"] == 2:                    # step 2's pre-mutation record
                raise ax._evidence_unavailable()
        return real(self, phase=phase, status=status, **kw)

    monkeypatch.setattr(ActLifecycle, "record", flaky)
    spy = MondaySpy()
    r = ax.deliver_action("pid-fc3", act_first=True,
                          redis_get=_getter(_create_steps(2)), monday_post=spy,
                          osascript=lambda c: "ok", redis_incr=lambda k, t: None,
                          evidence_store=store)
    assert r["ok"] is False and r["gate"] == "propose_only"
    assert len(r["executed"]) == 1                # step 1 reported, never hidden
    creates = [c for c in spy.calls if "create_item" in c[0]]
    assert len(creates) == 1                      # step 2's create NEVER ran
    assert any("step 2/2" in x and "evidence recording unavailable" in x
               for x in r["reasons"])


def test_happy_path_never_fails_closed_without_injection(tmp_path, monkeypatch):
    """The refusal branch fires EXCLUSIVELY on evidence-plane failure: a
    plain good store never trips it (10 consecutive runs, all ok)."""
    monkeypatch.setattr(ax, "_load_act_first_surfaces", lambda: _surfaces())
    store = tmp_path / "ev"
    for i in range(10):
        spy = MondaySpy()
        r = ax.deliver_action(f"pid-loop-{i}", act_first=True,
                              redis_get=_getter(_create_steps(1)),
                              monday_post=spy, osascript=lambda c: "ok",
                              redis_incr=lambda k, t: None,
                              evidence_store=store)
        assert r["ok"] is True
        assert len([c for c in spy.calls if "create_item" in c[0]]) == 1
    assert len(_trials(store)) == 10              # one trial per execution


# --- 4. reconciler outcome labels (receipt-class: loud, never blocking) ------

def _sweep_row(trial_id=None, jid="j1"):
    row = au.new_row(pid="p1", cid=CID, step=1, kind="monday_task_create",
                     backend="monday", lane="bakery", subject="thr",
                     actor={"kind": "officer", "id": "cos"},
                     created={"monday_id": "555"},
                     inverse=au.inverse_for("monday_task_create", "monday",
                                            {"board_id": "9"},
                                            {"monday_id": "555"}, {}),
                     executed_at="2026-07-04T10:00:00Z", jid=jid)
    row["ttl_expires_at"] = "2026-07-06T10:00:00Z"    # past TTL vs the test now
    if trial_id:
        row["evidence_trial_id"] = trial_id
    return row


def _mk_trial(store, trial_id="actlane-" + "a" * 32):
    rec = EvidenceRecorder(store)
    ctx = rec.trace(trial_id, surface="system")
    rec.append(ctx, phase="intent", status="started",
               actor={"kind": "system", "id": "action-executor"},
               component={"name": "action-executor", "version": "1"},
               detail={"action": "deliver_action"})
    return trial_id


def test_sweep_ttl_ok_receipt_lands_on_act_trial(tmp_path):
    store = tmp_path / "ev"
    trial_id = _mk_trial(store)
    emitted = []
    res = ar.run_sweep(now="2026-07-08T10:00:00Z",
                       journal_rows=[_sweep_row(trial_id)],
                       monday_probe=lambda r: {"exists": True, "archived": False},
                       read_ledger_fn=lambda: [],
                       emit=lambda **ev: emitted.append(ev),
                       gc=False, evidence_store=store)
    assert res["ttl_ok"] == ["j1"] and len(emitted) == 1
    assert res["evidence_receipts"] == {"recorded": 1, "skipped": 0, "degraded": 0}
    evs = _events(store, trial_id)
    assert [(e["phase"], e["status"]) for e in evs] == [
        ("intent", "started"),
        ("verification", "verified"), ("outcome", "succeeded")]
    tail = evs[-1]
    assert tail["detail"]["outcome"] == "ok"
    assert tail["detail"]["result_code"] == "ttl_ok"
    assert tail["detail"]["jid"] == "j1"
    assert "source" not in tail["detail"]         # ttl_ok carries no verdict source
    assert "undo-journal:j1" in tail["links"]
    assert tail["correlation_id"] == CID          # joined to the proposal's cid
    assert verify_trial(store, trial_id)["ok"] is True


def test_sweep_silent_revert_receipt_carries_provenance(tmp_path):
    """failed + judge-vs-human provenance: the Captain-attributed revert
    labels verdict_human; the plain disappearance labels verdict_judge."""
    store = tmp_path / "ev"
    t_human = _mk_trial(store, "actlane-" + "a" * 32)
    t_judge = _mk_trial(store, "actlane-" + "b" * 32)
    emitted = []
    ar.run_sweep(now="2026-07-08T10:00:00Z",
                 journal_rows=[_sweep_row(t_human, jid="jh")],
                 monday_probe=lambda r: {"exists": False, "archived": False,
                                         "reverted_by_captain": True},
                 read_ledger_fn=lambda: [],
                 emit=lambda **ev: emitted.append(ev),
                 gc=False, evidence_store=store)
    ar.run_sweep(now="2026-07-08T10:00:00Z",
                 journal_rows=[_sweep_row(t_judge, jid="jj")],
                 monday_probe=lambda r: {"exists": False, "archived": False,
                                         "reverted_by_captain": False},
                 read_ledger_fn=lambda: [],
                 emit=lambda **ev: emitted.append(ev),
                 gc=False, evidence_store=store)
    assert len(emitted) == 2                      # both supersedes landed
    human_tail = _events(store, t_human)[-1]
    judge_tail = _events(store, t_judge)[-1]
    for tail in (human_tail, judge_tail):
        assert (tail["phase"], tail["status"]) == ("outcome", "failed")
        assert tail["detail"]["outcome"] == "failed"
        assert tail["detail"]["result_code"] == "silent_revert"
    assert human_tail["detail"]["source"] == "verdict_human"
    assert judge_tail["detail"]["source"] == "verdict_judge"
    ver = _events(store, t_judge)[-2]
    assert (ver["phase"], ver["status"]) == ("verification", "unverified")


def test_sweep_rows_without_trial_id_skip_honestly(tmp_path):
    """Pre-evidence journal rows are an honest gap: the domain write still
    lands, nothing touches the store."""
    store = tmp_path / "ev"
    emitted = []
    res = ar.run_sweep(now="2026-07-08T10:00:00Z",
                       journal_rows=[_sweep_row(None)],
                       monday_probe=lambda r: {"exists": True, "archived": False},
                       read_ledger_fn=lambda: [],
                       emit=lambda **ev: emitted.append(ev),
                       gc=False, evidence_store=store)
    assert len(emitted) == 1                      # ledger supersede unaffected
    assert res["evidence_receipts"] == {"recorded": 0, "skipped": 1, "degraded": 0}
    assert not store.exists()                     # no store touch for a gap row


def test_sweep_receipt_degrades_loud_never_blocks_emit(tmp_path, capsys):
    """RECEIPT-class law: a broken evidence plane degrades LOUD (stderr) and
    never blocks the acted_verdict_event supersede — the exact inverse of the
    executor's fail-closed act seam."""
    bad = tmp_path / "broken-store"
    bad.write_text("a file, not a store")
    emitted = []
    res = ar.run_sweep(now="2026-07-08T10:00:00Z",
                       journal_rows=[_sweep_row("actlane-" + "d" * 32)],
                       monday_probe=lambda r: {"exists": True, "archived": False},
                       read_ledger_fn=lambda: [],
                       emit=lambda **ev: emitted.append(ev),
                       gc=False, evidence_store=bad)
    assert len(emitted) == 1                      # the domain write LANDED
    assert res["ttl_ok"] == ["j1"]
    assert res["evidence_receipts"]["degraded"] == 1
    assert "WARN evidence outcome receipt degraded" in capsys.readouterr().err


def test_end_to_end_act_then_sweep_labels_same_trial(tmp_path, monkeypatch):
    """The full journey: the executor acts (trial minted, journal stamped),
    the hourly sweep later labels the outcome ON THE SAME TRIAL — the
    correlation survives the JSONL round-trip and the trial still verifies."""
    monkeypatch.setattr(ax, "_load_act_first_surfaces", lambda: _surfaces())
    store = tmp_path / "ev"
    spy = MondaySpy()
    r = ax.deliver_action("pid-e2e", act_first=True,
                          redis_get=_getter(_create_steps(1)), monday_post=spy,
                          osascript=lambda c: "ok", redis_incr=lambda k, t: None,
                          evidence_store=store)
    assert r["ok"] is True
    rows = au._read_journal()                     # the round-tripped row
    assert len(rows) == 1
    trial_id = rows[0]["evidence_trial_id"]
    rows[0]["ttl_expires_at"] = "2026-07-06T10:00:00Z"   # force past-TTL
    emitted = []
    res = ar.run_sweep(now="2026-07-08T10:00:00Z", journal_rows=rows,
                       monday_probe=lambda r_: {"exists": True, "archived": False},
                       read_ledger_fn=lambda: [],
                       emit=lambda **ev: emitted.append(ev),
                       gc=False, evidence_store=store)
    assert res["evidence_receipts"]["recorded"] == 1
    evs = _events(store, trial_id)
    assert len(evs) == 8                          # 6 executor + 2 sweep events
    assert [(e["phase"], e["status"]) for e in evs][-2:] == [
        ("verification", "verified"), ("outcome", "succeeded")]
    assert evs[-1]["detail"]["jid"] == rows[0]["jid"]
    assert verify_trial(store, trial_id)["ok"] is True


# --- 5. identity attestation ---------------------------------------------------

def test_attested_identity_rides_events(tmp_path, monkeypatch):
    monkeypatch.setattr(ax, "_load_act_first_surfaces", lambda: _surfaces())
    ev_identity.attest_process_identity("system", "action-lane", "action-lane")
    store = tmp_path / "ev"
    spy = MondaySpy()
    r = ax.deliver_action("pid-att", act_first=True,
                          redis_get=_getter(_create_steps(1)), monday_post=spy,
                          osascript=lambda c: "ok", redis_incr=lambda k, t: None,
                          evidence_store=store)
    assert r["ok"] is True
    evs = _events(store, _trials(store)[0])
    assert all(e["actor"] == {"kind": "system", "id": "action-lane"} for e in evs)
    assert all(e["component"]["name"] == "action-lane" for e in evs)
    assert all(e["detail"].get("attestation_mode") == "process" for e in evs)


def test_unattested_process_uses_fixed_fallback_actor(tmp_path, monkeypatch):
    """No attestation -> the fixed module constant (never payload-derived:
    the stored record's actor stays DATA on the journal row)."""
    monkeypatch.setattr(ax, "_load_act_first_surfaces", lambda: _surfaces())
    store = tmp_path / "ev"
    spy = MondaySpy()
    ax.deliver_action("pid-fall", act_first=True,
                      redis_get=_getter(_create_steps(1)), monday_post=spy,
                      osascript=lambda c: "ok", redis_incr=lambda k, t: None,
                      evidence_store=store)
    evs = _events(store, _trials(store)[0])
    assert all(e["actor"] == {"kind": "system", "id": "action-executor"}
               for e in evs)
    assert all("attestation_mode" not in e["detail"] for e in evs)


def test_lane_main_attests_process_identity(monkeypatch):
    """run_action_lane.main() freezes the daemon identity at process start —
    and prints nothing new to stdout (the flag-off byte contract)."""
    from framework.acting import run_action_lane as r
    monkeypatch.setattr(r.sys, "argv", ["run_action_lane"])
    monkeypatch.setattr(r, "_acquire_lock", lambda: True)
    monkeypatch.setattr(r, "_load_env", lambda: None)
    monkeypatch.setattr(r, "_expire_stale_cards", lambda now: 0)
    monkeypatch.setattr(r, "_act_first_on", lambda: False)
    monkeypatch.setattr(r, "gather_signals", lambda *a, **k: "")
    assert not ev_identity.is_attested()
    assert r.main() == 0
    assert ev_identity.is_attested()
    assert ev_identity.attested_actor() == {"kind": "system", "id": "action-lane"}
