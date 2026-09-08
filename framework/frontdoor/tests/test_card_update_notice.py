"""The briefing's update line — every arm, including the degenerate ones.

WHAT THIS FILE IS FOR. `run_briefing._update_notice` is the briefing half of
the update path (contract of record phase1-contracts-v2-2026-09-07, A5.13): the
one sentence that tells the Captain, on the door he already reads every day,
that better bytes are sitting in the inbox or that the ones he has just took
themselves back. It ends in a blanket `except Exception: return ""`, which is
the right default and is also a total fail-open — the exact shape this program
has paid for repeatedly. The web half shipped with five arms on
`updateHeadline`; this half shipped with none, so every sentence below is a
sentence nobody had ever seen the code produce.

Fully fixtured: a tmp install root, a tmp event ledger, no clock, no network,
no subprocess. Each arm names the state it is in and the sentence that state
must produce — and the degenerate arms name what must NOT be produced, because
"you are up to date" from an install that cannot answer is the failure this
notice exists to keep off his screen.
"""
from __future__ import annotations

import json
from pathlib import Path

from framework.frontdoor import run_briefing


OLD = "a" * 40
NEW = "b" * 40


def _install(tmp_path, *, source_commit=OLD) -> Path:
    root = tmp_path / "install"
    (root / ".updates" / "inbox").mkdir(parents=True)
    (root / "egg-manifest.json").write_text(
        json.dumps({"source_commit": source_commit}), encoding="utf-8")
    return root


def _waiting(root: Path, sha=NEW, *, files=3, built_at="2026-09-07T00:00:00Z",
             with_tarball=True) -> None:
    inbox = root / ".updates" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / (sha + ".manifest.json")).write_text(json.dumps({
        "source_sha": sha, "built_at": built_at,
        "files": {("f%d" % i): "d" for i in range(files)},
    }), encoding="utf-8")
    if with_tarball:
        (inbox / (sha + ".tar.gz")).write_bytes(b"not really a tarball")


def _state(root: Path, doc) -> None:
    path = root / ".updates" / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")


def _ledger(monkeypatch, tmp_path) -> Path:
    """Point the REAL emitter at a throwaway ledger and hand it back."""
    log_dir = tmp_path / "events"
    log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(log_dir))
    return log_dir


def _emit(event_type: str, payload: dict) -> None:
    """Through the REAL emitter, so an unregistered type raises here rather
    than passing as a fixture the production path would refuse."""
    from framework.events.emitter import emit
    emit(event_type, "system", payload)


# ---------------------------------------------------------------------------
# the three states the state file knows about
# ---------------------------------------------------------------------------

def test_a_waiting_bundle_leads_because_it_is_the_one_he_can_act_on(tmp_path):
    root = _install(tmp_path)
    _waiting(root, files=7)
    line = run_briefing._update_notice(str(root))
    assert line.startswith("An update is ready to take")
    assert NEW[:8] in line and "7 files" in line
    assert "tap Apply" in line


def test_an_applied_state_says_what_landed(tmp_path):
    root = _install(tmp_path, source_commit=NEW)
    _state(root, {"phase": "applied", "to_sha": NEW, "changed": 4})
    assert run_briefing._update_notice(str(root)) == "Updated to %s: 4 changes" % NEW[:8]


def test_a_rolled_back_state_says_so_and_carries_the_reason(tmp_path):
    root = _install(tmp_path)
    _state(root, {"phase": "rolled_back", "to_sha": OLD,
                  "reason": "the health gate was red"})
    line = run_briefing._update_notice(str(root))
    assert line == "An update was rolled back: the health gate was red"


def test_a_rolled_back_state_with_no_reason_still_says_something_true(tmp_path):
    root = _install(tmp_path)
    _state(root, {"phase": "rolled_back", "to_sha": OLD})
    assert run_briefing._update_notice(str(root)) == (
        "An update was rolled back: it did not come up healthy")


def test_an_apply_in_flight_says_it_is_happening_now(tmp_path):
    root = _install(tmp_path)
    _state(root, {"phase": "applying", "to_sha": NEW})
    assert run_briefing._update_notice(str(root)) == "An update is being taken right now"


# ---------------------------------------------------------------------------
# the degenerate end — silence, never "you are up to date"
# ---------------------------------------------------------------------------

def test_an_install_with_no_updater_at_all_says_nothing(tmp_path):
    """Every install that predates this leg. The answer is silence."""
    bare = tmp_path / "bare"
    bare.mkdir()
    assert run_briefing._update_notice(str(bare)) == ""


def test_a_root_that_does_not_exist_says_nothing(tmp_path):
    assert run_briefing._update_notice(str(tmp_path / "nowhere")) == ""


def test_an_unreadable_state_file_says_nothing(tmp_path):
    root = _install(tmp_path)
    _state(root, "{not json at all")
    assert run_briefing._update_notice(str(root)) == ""


def test_a_manifest_with_no_tarball_beside_it_is_not_waiting(tmp_path):
    """Half a bundle is not an update. The manifest alone must not produce
    "ready to take" — there is nothing there to take."""
    root = _install(tmp_path)
    _waiting(root, with_tarball=False)
    assert run_briefing._update_notice(str(root)) == ""


def test_a_bundle_of_the_installed_commit_is_not_waiting(tmp_path):
    root = _install(tmp_path, source_commit=NEW)
    _waiting(root, sha=NEW)
    assert run_briefing._update_notice(str(root)) == ""


def test_the_newest_of_several_waiting_bundles_wins(tmp_path):
    root = _install(tmp_path)
    _waiting(root, sha="c" * 40, files=1, built_at="2026-09-01T00:00:00Z")
    _waiting(root, sha=NEW, files=9, built_at="2026-09-07T00:00:00Z")
    line = run_briefing._update_notice(str(root))
    assert NEW[:8] in line and "9 files" in line


# ---------------------------------------------------------------------------
# the receipts — the channel `state.json` has never carried
# ---------------------------------------------------------------------------

def test_a_refused_bundle_does_not_read_as_ready_to_take(tmp_path, monkeypatch):
    """A refusal writes no state file: it is a receipt and nothing else.

    So a bundle whose diff touches the constitutional set sits in the inbox for
    ever while the only sentence the Captain ever sees says "ready to take —
    tap Apply", which does nothing every time he taps it."""
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _waiting(root)
    _emit("cabinet_update_refused", {
        "to_sha": NEW, "reason": "it changes locked constitutional paths",
        "locked_paths": ["cabinet/scripts/germline-lock.sh"], "door": "terminal"})
    line = run_briefing._update_notice(str(root))
    assert "REFUSED" in line, line
    assert "locked constitutional paths" in line
    assert "tap Apply" not in line


def test_a_bundle_that_already_rolled_back_says_so_while_it_waits(tmp_path, monkeypatch):
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _waiting(root)
    _emit("cabinet_update_rolled_back", {
        "from_sha": NEW, "to_sha": OLD, "reason": "the health gate was red",
        "door": "web"})
    _emit("cabinet_update_rolled_back", {
        "from_sha": NEW, "to_sha": NEW, "reason": "the health gate was red",
        "door": "web"})
    line = run_briefing._update_notice(str(root))
    assert "rolled back" in line and NEW[:8] in line
    assert "tap Apply" not in line


def test_a_receipt_about_a_different_bundle_does_not_silence_this_one(tmp_path, monkeypatch):
    """The selector is the bundle, not the newest row: an earlier refusal of
    some other sha must not turn a good bundle into a refusal."""
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _waiting(root)
    _emit("cabinet_update_refused", {"to_sha": "c" * 40, "reason": "busy",
                                     "locked_paths": [], "door": "web"})
    _emit("cabinet_update_applied", {"from_sha": "d" * 40, "to_sha": "c" * 40,
                                     "changed": 1, "deleted": 0, "door": "web"})
    line = run_briefing._update_notice(str(root))
    assert line.startswith("An update is ready to take"), line


def test_an_applied_receipt_for_the_waiting_bundle_still_offers_it(tmp_path, monkeypatch):
    """Half-landed: the bytes went in but the identity stamp did not stick, so
    the install still reports the older commit. The honest sentence is still
    that there is something here to take."""
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _waiting(root)
    _emit("cabinet_update_applied", {"from_sha": OLD, "to_sha": NEW,
                                     "changed": 2, "deleted": 0, "door": "web"})
    assert run_briefing._update_notice(str(root)).startswith("An update is ready to take")


def test_an_unreadable_ledger_never_costs_the_notice(tmp_path, monkeypatch):
    """Fail-open, in the direction that keeps the sentence rather than the one
    that invents it: a ledger this cannot read is not an excuse to go silent
    about a bundle that is demonstrably on disk."""
    log_dir = _ledger(monkeypatch, tmp_path)
    (log_dir / "events-2026-09-07.jsonl").write_text("{ torn\n", encoding="utf-8")
    root = _install(tmp_path)
    _waiting(root)
    assert run_briefing._update_notice(str(root)).startswith("An update is ready to take")


# ---------------------------------------------------------------------------
# the wiring — the sentence has to reach the card
# ---------------------------------------------------------------------------

def test_the_headline_carries_the_update_line(tmp_path, monkeypatch):
    """Without this the notice could be perfect and never reach a surface."""
    root = _install(tmp_path)
    _waiting(root)
    monkeypatch.setenv("CABINET_ROOT", str(root))
    head = run_briefing._plain_headline({"items": []}, None)
    assert "An update is ready to take" in head


def test_the_headline_is_unharmed_when_there_is_no_update_to_report(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path / "bare"))
    head = run_briefing._plain_headline({"items": []}, None)
    assert "update" not in head.lower()
    assert head.endswith(".")


# ---------------------------------------------------------------------------
# A5.15 — the state file finally carries a refusal, and this line reads it
#
# Until 2026-09-08 a refusal wrote no state at all, so this notice could only
# learn about one from the ledger — and the ledger is exactly what a
# pre-update-path emitter refuses to write (A5.16). Both channels were silent
# on the same event on the first real apply, and the sentence the Captain would
# have read was "an update is ready to take — tap Apply".
# ---------------------------------------------------------------------------

def test_a_refused_state_file_is_read_even_when_the_ledger_never_heard(tmp_path,
                                                                       monkeypatch):
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _waiting(root)
    _state(root, {"phase": "refused", "bundle": NEW, "ts": "2026-09-08T18:58:00Z",
                  "reason": "bundle changes locked constitutional paths",
                  "paths": ["cabinet/scripts/start-officer-mac.sh"], "door": "terminal"})
    line = run_briefing._update_notice(str(root))
    assert "refused" in line.lower(), line
    assert "1 constitutional file" in line
    assert "tap Apply" not in line


def test_a_refusal_names_more_than_one_file_in_the_plural(tmp_path, monkeypatch):
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _waiting(root)
    _state(root, {"phase": "refused", "bundle": NEW, "ts": "2026-09-08T18:58:00Z",
                  "reason": "bundle changes locked constitutional paths",
                  "paths": ["a.sh", "b.sh"], "door": "web"})
    assert "2 constitutional files" in run_briefing._update_notice(str(root))


def test_a_refusal_with_no_paths_says_its_own_reason(tmp_path, monkeypatch):
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _waiting(root)
    _state(root, {"phase": "refused", "bundle": NEW, "ts": "2026-09-08T18:58:00Z",
                  "reason": "failed per-file digest verification", "paths": [],
                  "door": "terminal"})
    line = run_briefing._update_notice(str(root))
    assert "refused" in line.lower()
    assert "digest" in line
    assert "constitutional" not in line


def test_a_refusal_of_a_bundle_that_is_gone_still_says_what_happened(tmp_path,
                                                                    monkeypatch):
    """No bundle in the inbox and no apply since: the last thing that happened
    is still the last thing that happened."""
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _state(root, {"phase": "refused", "bundle": NEW, "ts": "2026-09-08T18:58:00Z",
                  "reason": "bundle changes locked constitutional paths",
                  "paths": ["cabinet/scripts/start-officer-mac.sh"], "door": "terminal"})
    assert "refused" in run_briefing._update_notice(str(root)).lower()


def test_a_refusal_of_some_other_bundle_never_silences_the_waiting_one(tmp_path,
                                                                      monkeypatch):
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _waiting(root)
    _state(root, {"phase": "applied", "to_sha": "c" * 40, "changed": 2,
                  "last_refusal": {"bundle": "e" * 40, "reason": "busy", "paths": [],
                                   "ts": "2026-09-08T18:00:00Z", "door": "web"}})
    assert run_briefing._update_notice(str(root)).startswith("An update is ready to take")


def test_a_busy_refusal_of_the_waiting_bundle_does_not_speak_over_it(tmp_path,
                                                                     monkeypatch):
    """PARITY with the card, and the second half of the round-1 defect.

    `lib/updates.refusalToShow` and this helper read the same state file and
    must not be able to disagree about it — a card offering Apply under a
    briefing line that says the bundle was refused is two surfaces calling the
    same fact differently, which is the failure the shared helper on each side
    exists to prevent. `busy` means another updater held the lock: it is a fact
    about timing, never a verdict on these bytes, and `phase` does not change
    that. Round 1 filtered `busy` only once the phase had moved on, so for the
    whole window where the phase still said `refused` this line announced a
    refusal of a bundle nothing had judged."""
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _waiting(root)
    _state(root, {"phase": "refused", "bundle": NEW, "reason": "busy", "paths": [],
                  "ts": "2026-09-08T18:58:00Z", "door": "web"})
    assert run_briefing._update_notice(str(root)).startswith("An update is ready to take")


def test_a_ledger_fault_is_named_rather_than_reported_as_version_skew(tmp_path,
                                                                      monkeypatch):
    """A5.16, round 2, on the door the Captain reads every day.

    A held record has two possible causes and only one of them heals itself.
    "The next update files it" is true of an emitter that does not know the
    event type yet and false of a full disk, and round 1 said it about both."""
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _waiting(root)
    _state(root, {"phase": "applied", "to_sha": NEW, "changed": 2,
                  "event_fallback": True,
                  "ledger_error": "OSError: [Errno 28] No space left on device: "
                                  "events-2026-09-08.jsonl"})
    line = run_briefing._update_notice(str(root))
    assert "ledger fault" in line, line
    assert "No space left on device" in line, line


def test_a_held_record_with_no_fault_does_not_raise_an_alarm(tmp_path, monkeypatch):
    """The inverse, and the arm that stops the fix being a blanket relabel.

    The ordinary bootstrap case — a record held because the emitter is one
    version behind — is not something to interrupt the Captain about: the
    waiting bundle is still the sentence he can act on."""
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _waiting(root)
    _state(root, {"phase": "applied", "to_sha": NEW, "changed": 2,
                  "event_fallback": True})
    line = run_briefing._update_notice(str(root))
    assert line.startswith("An update is ready to take"), line
    assert "fault" not in line, line
