"""AX-7 — the narrow-only `posture` binder verb (axes spec 2026-07-05 §1).

Pinned here:
  * `posture guardian|earn_up` writes instance/config/posture-narrow
    (atomic, single validated word) and reports the effective posture;
  * `posture clear` removes the cap with the WARNING that this restores
    the attested level;
  * `posture sovereign` / any other word is REFUSED with the attestation
    ritual — widening is never a chat verb, and a matched verb is TERMINAL
    (never the propose path);
  * DARK by default (no CABINET_NEEDS_WIRED / not captain_verified) — the
    same gate as the grant verbs;
  * zero collisions with every existing binder grammar;
  * a write failure reports FAILED (posture unchanged), never a false cap.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from framework.acting import loop
from framework.authority import posture
from framework.frontdoor import binder_wire


@pytest.fixture()
def wired_root(tmp_path, monkeypatch):
    """A tmp cabinet root with the needs plane wired (the posture verb rides
    the same CABINET_NEEDS_WIRED + captain_verified gate)."""
    monkeypatch.delenv("CABINET_POSTURE", raising=False)
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    monkeypatch.setenv("CABINET_ID", "main")
    return tmp_path


def _handle(text, **kw):
    kw.setdefault("pending_source", lambda: [])
    kw.setdefault("emit", lambda **e: None)
    kw.setdefault("redis_get", lambda k: "")
    kw.setdefault("present", lambda m: None)
    return binder_wire.handle_captain_update(text, "", **kw)


def _cap_file(root: Path) -> Path:
    return root / "instance/config" / "posture-narrow"


# --- narrow happy paths -----------------------------------------------------------

def test_posture_guardian_writes_the_narrow_cap(wired_root):
    shown = []
    r = _handle("posture guardian", present=shown.append)
    assert r["handled"] is True and r["posture_verb"] == "narrow"
    assert r["cap"] == "guardian"
    assert _cap_file(wired_root).read_text() == "guardian\n"
    assert posture.narrow_cap(wired_root) == "guardian"
    assert "Narrow cap set: guardian" in shown[0]
    assert "posture clear" in shown[0]           # the undo handle is named


def test_posture_earn_up_caps_the_resolution(wired_root):
    shown = []
    r = _handle("posture earn_up", present=shown.append)
    assert r["handled"] is True and r["cap"] == "earn_up"
    assert posture.narrow_cap(wired_root) == "earn_up"
    # no ruling ⇒ guardian, min-capped by the file ⇒ earn_up
    assert posture.resolve_posture(root=wired_root) == "earn_up"
    assert "earn_up" in shown[0]


def test_posture_verb_is_case_and_hyphen_tolerant(wired_root):
    r = _handle("Posture Earn-Up")
    assert r["handled"] is True and r["cap"] == "earn_up"
    assert _cap_file(wired_root).read_text() == "earn_up\n"


def test_posture_set_overwrites_previous_cap_atomically(wired_root):
    _handle("posture earn_up")
    _handle("posture guardian")
    assert _cap_file(wired_root).read_text() == "guardian\n"
    # no tmp litter left behind
    leftovers = [p for p in _cap_file(wired_root).parent.iterdir()
                 if p.name.startswith("posture-narrow.tmp")]
    assert leftovers == []


# --- clear ------------------------------------------------------------------------

def test_posture_clear_removes_cap_with_warning(wired_root):
    _handle("posture earn_up")
    shown = []
    r = _handle("posture clear", present=shown.append)
    assert r["handled"] is True and r["posture_verb"] == "clear"
    assert not _cap_file(wired_root).exists()
    assert posture.narrow_cap(wired_root) is None
    assert "WARNING" in shown[0]
    assert "attested" in shown[0]                # restores the attested level


def test_posture_clear_with_no_cap_is_still_handled(wired_root):
    r = _handle("posture clear")
    assert r["handled"] is True and r["posture_verb"] == "clear"


# --- refusal: widening is never a chat verb ----------------------------------------

def test_posture_sovereign_is_refused_with_the_ritual(wired_root):
    shown = []
    r = _handle("posture sovereign", present=shown.append)
    assert r["handled"] is True and r["posture_verb"] == "refused"
    assert not _cap_file(wired_root).exists()
    msg = shown[0]
    assert "germline-lock.sh unlock" in msg and "germline-lock.sh lock" in msg
    assert "posture-presets" in msg
    assert "posture guardian" in msg             # the allowed verbs are listed


def test_posture_unknown_word_is_refused(wired_root):
    r = _handle("posture banana", present=lambda m: None)
    assert r["handled"] is True and r["posture_verb"] == "refused"
    assert not _cap_file(wired_root).exists()


def test_refused_posture_verb_is_terminal_never_approves(wired_root):
    """A matched posture verb NEVER falls through to the propose path — even
    with exactly one open proposal (the no-pid fallback's trigger shape)."""
    prop = loop.proposal_event(actor={"kind": "officer", "id": "officer:cos"},
                               lane="send-1to1-reply", subject="thread:k",
                               ts="2026-07-05T10:00:00Z")
    emitted = []
    for text in ("posture sovereign", "posture guardian", "posture clear"):
        r = _handle(text, pending_source=lambda: [prop],
                    emit=lambda **e: emitted.append(e))
        assert r["handled"] is True
    assert emitted == []
    assert prop["proposal"]["decision"] is None


# --- dark by default ---------------------------------------------------------------

def test_dark_without_env_posture_verbs_pass_through(tmp_path, monkeypatch):
    monkeypatch.delenv("CABINET_POSTURE", raising=False)
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("CABINET_ID", "main")
    r = _handle("posture guardian")
    assert r["handled"] is False and r["reason"] == "no-pid"
    assert not _cap_file(tmp_path).exists()


def test_not_captain_verified_posture_verbs_pass_through(wired_root):
    r = _handle("posture guardian", captain_verified=False)
    assert r["handled"] is False
    assert not _cap_file(wired_root).exists()


# --- grammar: anchored + collision-free --------------------------------------------

_EXISTING_VERBS = [
    "send", "ok", "okay", "👍", "approve", "yes", "ja",
    "edit: min egen version", "skip: allerede besvaret",
    "undo", "undo 2", "undo: wrong board",
    "never: no more auto-mails", "no more spam", "stop doing this",
    "lift veto-001", "veto confirm action_type=board_status",
    "grant NEED-1a2b3c4d", "rearm board_status",
    "ok men vent - send ikke endnu", "never mind",
]


def test_posture_grammar_matches_nothing_in_the_existing_corpus():
    for t in _EXISTING_VERBS:
        assert binder_wire._POSTURE_VERB_RE.match(t) is None, t


def test_posture_verbs_are_inert_to_the_other_grammars():
    for t in ("posture guardian", "posture earn_up", "posture clear",
              "posture sovereign"):
        assert binder_wire._parse_acted_verb(t) is None, t
        assert binder_wire._NEED_RE.match(t) is None, t
        assert binder_wire._REARM_RE.match(t) is None, t
        assert binder_wire._LIFT_RE.match(t) is None, t
        assert binder_wire._VETO_CONFIRM_RE.match(t) is None, t
        assert binder_wire._NEVER_RE.match(t) is None, t
        assert loop.route_captain_response(t).primary not in (
            "approve", "edit", "skip"), t


def test_posture_prose_passes_through(wired_root):
    """Multi-word prose about posture is NOT the grammar — the Chair gets it."""
    for t in ("posture looks wrong today", "what posture are we in?",
              "posture guardian please", "posture"):
        r = _handle(t)
        assert r["handled"] is False, t
    assert not _cap_file(wired_root).exists()


# --- failure polarity --------------------------------------------------------------

def test_write_failure_reports_failed_and_sets_nothing(wired_root):
    """instance/ exists as a FILE ⇒ mkdir/write fails ⇒ the verb must say the
    brake did NOT engage (never claim a cap that isn't on disk)."""
    (wired_root / "instance/").write_text("not a directory")
    shown = []
    r = _handle("posture guardian", present=shown.append)
    assert r["handled"] is True and r["posture_verb"] == "narrow-failed"
    assert "FAILED" in shown[0] and "UNCHANGED" in shown[0]
    assert "CABINET_POSTURE=guardian" in shown[0]     # the env fallback brake


def test_present_failure_still_sets_the_cap(wired_root):
    def bad_present(msg):
        raise RuntimeError("telegram down")
    r = _handle("posture guardian", present=bad_present)
    assert r["handled"] is True and r["posture_verb"] == "narrow"
    assert posture.narrow_cap(wired_root) == "guardian"
