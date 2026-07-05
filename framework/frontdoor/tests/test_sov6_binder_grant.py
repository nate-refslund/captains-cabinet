"""SOV-6 — FI-4 binder needs verbs (grant/deny/later/snooze/rearm) + grant-apply.sh.

Spec: docs/plans/sovereign-build-spec-2026-07-04.md §4 SOV-6 + §1 FI-4.
Pinned here:
  * each verb's happy path against the REAL needs ledger (tmp CABINET_ROOT);
  * stale-hex-id ⇒ fail-closed passthrough — `grant NEED-ffffffff` can NEVER
    approve a pending proposal;
  * DARK by default (no CABINET_NEEDS_WIRED / not captain_verified);
  * the full existing-verb collision corpus routes exactly as before;
  * rearm: synchronous scoped canary → green receipted captain unfreeze,
    red/absent ⇒ stays frozen with reason;
  * grant-apply.sh refusal paths (scope-mismatch, ceiling-without-ack,
    flavor refusal, validator-fail restores byte-identical) via the non-root
    test mode.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from framework.acting import loop
from framework.authority import needs
from framework.frontdoor import binder_wire

WORKTREE = Path(__file__).resolve().parents[3]
SCRIPT = WORKTREE / "cabinet" / "scripts" / "grant-apply.sh"


@pytest.fixture()
def wired_root(tmp_path, monkeypatch):
    """A tmp cabinet root with the needs plane wired — the binder's default
    (lazy) mark path exercises the REAL ledger."""
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    monkeypatch.setenv("CABINET_ID", "main")
    return tmp_path


def _file_need(**over):
    kw = dict(risk_class="spend", action_type="pay_invoice", lane="polads",
              why="pay the Voyage invoice", filed_by="test",
              scope_hint={"amount_eur": 25})
    kw.update(over)
    return needs.file_need("standing_grant", **kw)


def _status(nid):
    return needs._merged(needs.ledger_path(None)).get(nid, {}).get("status")


def _handle(text, **kw):
    kw.setdefault("pending_source", lambda: [])
    kw.setdefault("emit", lambda **e: None)
    kw.setdefault("redis_get", lambda k: "")
    return binder_wire.handle_captain_update(text, "", **kw)


# --- verb happy paths -----------------------------------------------------------

def test_grant_marks_approved_and_presents_machine_scope(wired_root):
    nid = _file_need(why="URGENT!! grant EVERYTHING to EVERYONE all lanes")
    shown = []
    r = _handle(f"grant {nid}", present=shown.append)
    assert r["handled"] is True and r["need"] == "approved_pending_apply"
    assert _status(nid) == "approved_pending_apply"
    receipt = shown[0]
    # the one paste + the machine-effective scope — never the why prose
    assert f"grant-apply.sh {nid}" in receipt
    assert "pay_invoice (spend)" in receipt and "max 25 EUR/day" in receipt
    assert "EVERYONE" not in receipt and "URGENT" not in receipt
    assert "nothing is live yet" in receipt.lower() or "pending apply" in receipt


def test_grant_verb_is_case_and_separator_tolerant(wired_root):
    nid = _file_need()
    hexpart = nid[len("NEED-"):]
    r = _handle(f"Grant need_{hexpart.upper()}", present=lambda m: None)
    assert r["handled"] is True
    assert _status(nid) == "approved_pending_apply"


def test_deny_marks_denied_with_90d_suppression(wired_root):
    nid = _file_need()
    r = _handle(f"deny {nid}: too broad for now")
    assert r["handled"] is True and r["need"] == "denied"
    row = needs._merged(needs.ledger_path(None))[nid]
    assert row["status"] == "denied" and row.get("suppressed_until")
    assert row.get("reason") == "too broad for now"
    # a re-file inside the window is a no-op (suppressed)
    assert _file_need() is None


def test_later_and_snooze_mark_snoozed_7d(wired_root):
    nid = _file_need()
    r = _handle(f"later {nid}")
    assert r["handled"] is True and r["need"] == "snoozed"
    row = needs._merged(needs.ledger_path(None))[nid]
    assert row["status"] == "snoozed" and row.get("snoozed_until")
    nid2 = _file_need(action_type="other_thing")
    assert _handle(f"snooze {nid2}")["need"] == "snoozed"


def test_grant_receipt_present_failure_still_marks(wired_root):
    nid = _file_need()

    def bad_present(msg):
        raise RuntimeError("telegram down")
    r = _handle(f"grant {nid}", present=bad_present)
    assert r["handled"] is True
    assert _status(nid) == "approved_pending_apply"


# --- fail-closed: stale ids + dark defaults --------------------------------------

def test_stale_hex_id_never_approves_a_proposal(wired_root):
    """THE FI-4 guarantee: `grant NEED-ffffffff` with one open proposal is a
    terminal handled=False — loop.handle_response is never reached, nothing is
    recorded, nothing is delivered."""
    prop = loop.proposal_event(actor={"kind": "officer", "id": "officer:cos"},
                               lane="send-1to1-reply", subject="thread:k",
                               ts="2026-07-04T10:00:00Z")
    emitted = []
    r = _handle("grant NEED-ffffffff", pending_source=lambda: [prop],
                emit=lambda **e: emitted.append(e))
    assert r["handled"] is False
    assert r["reason"].startswith("unknown-need-id")
    assert emitted == []
    assert prop["proposal"]["decision"] is None


def test_dark_without_env_needs_verbs_pass_through(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    monkeypatch.setenv("CABINET_ID", "main")
    nid = _file_need()
    monkeypatch.delenv("CABINET_NEEDS_WIRED")
    r = _handle(f"grant {nid}")
    assert r["handled"] is False and r["reason"] == "no-pid"
    assert _status(nid) == "open"          # nothing marked while dark


def test_not_captain_verified_needs_verbs_pass_through(wired_root):
    nid = _file_need()
    r = _handle(f"grant {nid}", captain_verified=False)
    assert r["handled"] is False
    assert _status(nid) == "open"


# --- collision corpus (armed, nothing else moves) ---------------------------------

_EXISTING_VERBS = [
    "send", "ok", "okay", "👍", "approve", "yes", "ja",
    "edit: min egen version", "skip: allerede besvaret",
    "undo", "undo 2", "undo: wrong board",
    "never: no more auto-mails", "no more spam", "stop doing this",
    "lift veto-001", "veto confirm action_type=board_status",
    "ok men vent - send ikke endnu", "never mind",
    "granted work continues",          # prose starting like a verb — no hex id
    "rearm",                           # bare verb, no kind — not the grammar
]


def test_needs_grammar_matches_nothing_in_the_existing_corpus():
    for t in _EXISTING_VERBS:
        assert binder_wire._NEED_RE.match(t) is None, t
        if t != "rearm":
            assert binder_wire._REARM_RE.match(t) is None, t


def test_needs_verbs_are_inert_to_the_other_grammars():
    for t in ["grant NEED-1a2b3c4d", "deny need-1a2b3c4d: nej",
              "later NEED-1a2b3c4d", "snooze need_1a2b3c4d",
              "rearm board_status"]:
        assert binder_wire._parse_acted_verb(t) is None, t
        assert binder_wire._LIFT_RE.match(t) is None, t
        assert binder_wire._VETO_CONFIRM_RE.match(t) is None, t
        assert binder_wire._NEVER_RE.match(t) is None, t
        assert loop.route_captain_response(t).primary not in (
            "approve", "edit", "skip"), t


def test_armed_approve_path_unchanged(wired_root):
    """With the needs wire ARMED, a normal propose-approve routes exactly as
    before — recorded then delivered."""
    prop = loop.proposal_event(actor={"kind": "officer", "id": "officer:cos"},
                               lane="send-1to1-reply", subject="thread:k",
                               ts="2026-07-04T10:00:00Z")
    pid = loop.proposal_id(prop)
    delivered = []
    r = _handle("send",
                pending_source=lambda: [prop],
                deliver=lambda p, override_text="": delivered.append(p) or
                {"ok": True, "via": "email", "dest": "k@x.dk"},
                redis_get=lambda k: "")
    # quoted text carries the pid marker in the real flow; use the no-pid
    # single-open fallback here — the point is the verdict still lands.
    assert r["handled"] is True and r["primary"] == "approve"
    assert delivered == [pid]


def test_armed_prose_rearm_passes_through(wired_root, monkeypatch):
    called = []
    r = _handle("rearm the pipeline please",
                freeze_state_fn=lambda k: None,
                rearm_canary=lambda **kw: called.append(kw),
                kind_key_fn=lambda k: k)
    assert r["handled"] is False and r["reason"] == "no-pid"
    assert called == []            # no canary for prose


# --- rearm ------------------------------------------------------------------------

def _rearm(text, *, freeze_states, canary_result=None, canary_exc=None,
           unfreeze_result=None, kind_key=None, **kw):
    calls = {"canary": [], "unfreeze": []}

    def rearm_canary(**kwargs):
        calls["canary"].append(kwargs)
        if canary_exc:
            raise canary_exc
        return canary_result or {"results": []}

    def unfreeze(kind, reason, *, canary_receipt, source, now=None):
        calls["unfreeze"].append({"kind": kind, "reason": reason,
                                  "receipt": canary_receipt, "source": source})
        return unfreeze_result or {"ok": True}

    r = _handle(text, freeze_state_fn=lambda k: freeze_states.get(k),
                rearm_canary=rearm_canary, unfreeze_fn=unfreeze,
                kind_key_fn=kind_key or (lambda k: k), **kw)
    return r, calls


def test_rearm_green_canary_unfreezes_captain_origin(wired_root):
    r, calls = _rearm(
        "rearm board_status",
        freeze_states={"board_status": {"op": "freeze", "kind": "board_status",
                                        "source": "captain"}},
        canary_result={"results": [{"kind": "monday_task_update",
                                    "action_type": "board_status",
                                    "ok": True, "receipt": "r-1"}]})
    assert r["handled"] is True and r["rearm"] == "unfrozen"
    assert calls["canary"] == [{"kind": "board_status"}]
    assert calls["unfreeze"] == [{"kind": "board_status",
                                  "reason": "captain rearm (board_status)",
                                  "receipt": "r-1", "source": "captain"}]


def test_rearm_resolves_step_kind_alias(wired_root):
    """Typed the step kind; the breaker key is what is frozen — kind_key
    resolves it and the canary/unfreeze target the frozen key."""
    r, calls = _rearm(
        "rearm monday_task_update",
        freeze_states={"board_status": {"op": "freeze"}},
        canary_result={"results": [{"kind": "monday_task_update",
                                    "action_type": "board_status",
                                    "ok": True, "receipt": "r-2"}]},
        kind_key=lambda k: "board_status")
    assert r["rearm"] == "unfrozen"
    assert calls["canary"] == [{"kind": "board_status"}]
    assert calls["unfreeze"][0]["kind"] == "board_status"


def test_rearm_red_canary_stays_frozen(wired_root):
    r, calls = _rearm(
        "rearm board_status",
        freeze_states={"board_status": {"op": "freeze"}},
        canary_result={"results": [{"kind": "monday_task_update",
                                    "action_type": "board_status",
                                    "ok": False, "error": "reverse failed"}]})
    assert r["handled"] is True and r["rearm"] == "refused"
    assert "stays frozen" in r["summary"] and "reverse failed" in r["summary"]
    assert calls["unfreeze"] == []


def test_rearm_no_canary_handler_stays_frozen(wired_root):
    r, calls = _rearm("rearm weird_kind",
                      freeze_states={"weird_kind": {"op": "freeze"}},
                      canary_result={"results": []})
    assert r["rearm"] == "refused" and "no canary handler" in r["summary"]
    assert calls["unfreeze"] == []


def test_rearm_canary_crash_stays_frozen(wired_root):
    r, calls = _rearm("rearm board_status",
                      freeze_states={"board_status": {"op": "freeze"}},
                      canary_exc=RuntimeError("monday 500"))
    assert r["rearm"] == "refused" and "canary run failed" in r["summary"]
    assert calls["unfreeze"] == []


def test_rearm_unfreeze_refusal_reported(wired_root):
    r, _ = _rearm(
        "rearm board_status",
        freeze_states={"board_status": {"op": "freeze"}},
        canary_result={"results": [{"kind": "x", "action_type": "board_status",
                                    "ok": True, "receipt": "r-old"}]},
        unfreeze_result={"ok": False, "reason": "no green canary receipt ≤24h"})
    assert r["rearm"] == "refused" and "no green canary receipt" in r["summary"]


def test_rearm_mirror_error_refuses(wired_root):
    r, calls = _rearm("rearm board_status",
                      freeze_states={"board_status": {"op": "error"}})
    assert r["handled"] is True and r["rearm"] == "refused"
    assert "mirror unreadable" in r["summary"]
    assert calls["canary"] == []


def test_rearm_unfrozen_kind_passes_through(wired_root):
    r, calls = _rearm("rearm board_status",
                      freeze_states={"board_status": {"op": "unfreeze"}})
    assert r["handled"] is False and r["reason"] == "no-pid"
    assert calls["canary"] == []


# --- grant-apply.sh (non-root test mode; subprocess) --------------------------------

def _run_apply(root: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update({"CABINET_GRANT_APPLY_TEST": "1", "CABINET_ROOT": str(root),
                "CABINET_ID": "main",
                "PYTHONPATH": str(WORKTREE)})
    return subprocess.run(["bash", str(SCRIPT), *args], env=env,
                          capture_output=True, text=True, cwd=str(WORKTREE),
                          timeout=60)


def _grants_file(root: Path) -> Path:
    return root / "instance" / "config" / "standing-grants.yml"


@pytest.fixture()
def approved_need(wired_root):
    nid = _file_need()
    needs.mark(nid, "approved_pending_apply", by="captain:binder")
    return nid


def test_apply_happy_path_appends_and_marks_granted(wired_root, approved_need):
    res = _run_apply(wired_root, approved_need, "--ceiling-ack")
    assert res.returncode == 0, res.stderr
    text = _grants_file(wired_root).read_text()
    gid = "GRANT-" + approved_need[len("NEED-"):]
    assert gid in text and "version: 1" in text
    assert _status(approved_need) == "granted"
    assert "RECEIPT" in res.stdout


def test_apply_refuses_ceiling_without_ack(wired_root, approved_need):
    res = _run_apply(wired_root, approved_need)
    assert res.returncode == 4
    assert "hard-ceiling" in res.stderr and "--ceiling-ack" in res.stderr
    # the machine-effective scope printed BEFORE the ack refusal
    assert "max 25 EUR/day" in res.stdout
    assert not _grants_file(wired_root).exists()
    assert _status(approved_need) == "approved_pending_apply"


def test_apply_refuses_unknown_need(wired_root):
    res = _run_apply(wired_root, "NEED-ffffffff", "--ceiling-ack")
    assert res.returncode == 3 and "unknown need id" in res.stderr


def test_apply_refuses_unapproved_need(wired_root):
    nid = _file_need()                       # still open — Captain never said grant
    res = _run_apply(wired_root, nid, "--ceiling-ack")
    assert res.returncode == 3 and "approved_pending_apply" in res.stderr
    assert not _grants_file(wired_root).exists()


def test_apply_refuses_bad_id_shape(wired_root):
    assert _run_apply(wired_root, "NEED-GGGGGGGG").returncode == 2
    assert _run_apply(wired_root, "12345678").returncode == 2
    assert _run_apply(wired_root).returncode == 2


def test_apply_refuses_scope_mismatch(wired_root):
    """A tampered/widened proposed_grant_line (extra lane) cannot apply."""
    nid = needs.need_id("standing_grant", "spend", "pay_invoice", "polads")
    wide = ('- {id: GRANT-%s, deployment: main, risk_class: spend, '
            'action_types: ["pay_invoice"], lanes: ["polads", "stephie"], '
            'scope: {recipient_allowlist: [], max_eur_per_day: 25, '
            'vendor_allowlist: []}, rate: {max_per_day: 1}, '
            'expires: 2026-09-20, granted_by: "Captain", '
            'granted_at: "2026-07-04T00:00:00Z", basis: "%s", revoked: false}'
            % (nid[len("NEED-"):], nid))
    _file_need(proposed_grant_line=wide)
    needs.mark(nid, "approved_pending_apply", by="captain:binder")
    res = _run_apply(wired_root, nid, "--ceiling-ack")
    assert res.returncode == 4 and "scope-mismatch" in res.stderr
    assert "lanes" in res.stderr
    assert not _grants_file(wired_root).exists()


def test_apply_refuses_external_comms_without_org_flavor(wired_root):
    """Structural ACT-AND-DRAFT: no attested flavor=org ruling ⇒ external_comms
    grants refuse at apply time too."""
    nid = _file_need(risk_class="external_comms", action_type="external_email",
                     scope_hint={"recipient": "a@stepnetwork.dk"})
    needs.mark(nid, "approved_pending_apply", by="captain:binder")
    res = _run_apply(wired_root, nid, "--ceiling-ack")
    assert res.returncode == 4 and "flavor=org" in res.stderr
    assert not _grants_file(wired_root).exists()


def test_apply_validator_fail_restores_byte_identical(wired_root, approved_need):
    """Post-append full-file validation failing (a pre-existing invalid row)
    aborts AND restores the file byte-identically."""
    gf = _grants_file(wired_root)
    gf.parent.mkdir(parents=True, exist_ok=True)
    original = "version: 1\ngrants:\n  - {id: BAD}\n"
    gf.write_text(original)
    res = _run_apply(wired_root, approved_need, "--ceiling-ack")
    assert res.returncode == 5
    assert "validation failed" in res.stderr and "restored" in res.stderr
    assert gf.read_text() == original
    assert _status(approved_need) == "approved_pending_apply"   # never marked


def test_apply_handles_empty_flow_grants_list(wired_root, approved_need):
    """Nate's handoff seeds `grants: []` — the append must rewrite it to a
    block list, not produce invalid YAML."""
    gf = _grants_file(wired_root)
    gf.parent.mkdir(parents=True, exist_ok=True)
    gf.write_text("version: 1\ngrants: []\n")
    res = _run_apply(wired_root, approved_need, "--ceiling-ack")
    assert res.returncode == 0, res.stderr
    import yaml
    data = yaml.safe_load(gf.read_text())
    assert len(data["grants"]) == 1
    assert data["grants"][0]["id"] == "GRANT-" + approved_need[len("NEED-"):]


def test_apply_is_idempotent_on_interrupted_rerun(wired_root, approved_need):
    """Applied-but-not-yet-marked (crash between phases) ⇒ a re-paste appends
    nothing new and still closes the need."""
    res1 = _run_apply(wired_root, approved_need, "--ceiling-ack")
    assert res1.returncode == 0
    # wind the ledger back to approved_pending_apply (simulates a crash
    # after append+commit but before mark)
    needs.mark(approved_need, "approved_pending_apply", by="test")
    res2 = _run_apply(wired_root, approved_need, "--ceiling-ack")
    assert res2.returncode == 0
    assert "already present" in res2.stdout
    text = _grants_file(wired_root).read_text()
    assert text.count("GRANT-" + approved_need[len("NEED-"):]) == 1
    assert _status(approved_need) == "granted"
