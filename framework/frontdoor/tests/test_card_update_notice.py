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


# ---------------------------------------------------------------------------
# A5.15 rule 3 — AN APPLY IN FLIGHT OUTRANKS THE REFUSAL OF THE BUNDLE IT IS
# TAKING.
#
# The card has had this since round 2 (`refusalToShow` opens with
# `phase === 'applying' -> null`); this side had no `applying` guard at all,
# and `_update_notice`'s own `applying` arm sat AFTER the waiting-bundle arm,
# which a waiting bundle makes unreachable. So on the one state where the two
# surfaces are most likely to be read together — the Captain taps Apply on the
# card and then looks at his briefing — the card said "Taking an update to
# bbbbbbbb" and this line said "Update refused — failed per-file digest
# verification (bbbbbbbb)", or, with a locked-path refusal on record, "needs
# the Captain" over an apply that was running.
#
# REACHABLE BY DESIGN, not by accident: the card deliberately keeps Apply for a
# digest-mismatch, unreadable or busy refusal, because a retry is a reasonable
# thing to do about all three. Tap it and `phase` becomes `applying` with the
# same sha still in `last_refusal` (the state write carries that field) and the
# bundle still in the inbox, which is where it stays until the apply lands. And
# durable with it: a killed apply leaves `phase: applying` plus its snapshot on
# disk on purpose, so the wrong sentence outlives the process that caused it.
# ---------------------------------------------------------------------------

def _applying_over_a_refusal(root, refusal_reason, refusal_paths):
    _waiting(root, files=7)
    _state(root, {
        "phase": "applying", "to_sha": NEW, "snapshot": "20260908T185800-aaaaaaaa",
        "last_refusal": {"bundle": NEW, "reason": refusal_reason,
                         "paths": list(refusal_paths), "ts": "2026-09-08T18:58:00Z",
                         "door": "web"},
    })


def test_an_apply_in_flight_outranks_the_refusal_of_the_bundle_it_is_taking(
        tmp_path, monkeypatch):
    """The retry, mid-flight: the line is about the apply, not the refusal."""
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _applying_over_a_refusal(root, "failed per-file digest verification", [])
    line = run_briefing._update_notice(str(root))
    assert line == "An update is being taken right now", line
    assert "refused" not in line.lower(), line
    assert run_briefing._update_refusal_line(root, NEW) == ""


def test_an_apply_in_flight_outranks_even_a_constitutional_refusal_on_record(
        tmp_path, monkeypatch):
    """The worse half of the same defect: "needs the Captain", over a running
    apply, for as long as it runs — and after a kill, for ever."""
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _applying_over_a_refusal(root, "bundle changes locked constitutional paths",
                             ["cabinet/scripts/start-officer-mac.sh"])
    line = run_briefing._update_notice(str(root))
    assert line == "An update is being taken right now", line
    assert "Captain" not in line, line


def test_the_apply_in_flight_sentence_is_reachable_with_a_bundle_in_the_inbox(
        tmp_path, monkeypatch):
    """`_update_notice`'s `applying` arm sat last, after the waiting-bundle arm.

    An apply is running BECAUSE a bundle is in the inbox — the entry is not
    removed until it lands — so the only situation that sentence describes was
    the only situation it could not be reached in. It said "An update is ready
    to take — tap Apply" instead, over an apply already in flight, which is an
    invitation to start a second one."""
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _waiting(root, files=7)
    _state(root, {"phase": "applying", "to_sha": NEW,
                  "snapshot": "20260908T185800-aaaaaaaa"})
    assert run_briefing._update_notice(str(root)) == "An update is being taken right now"


def test_a_refusal_still_speaks_once_the_apply_is_no_longer_in_flight(tmp_path,
                                                                      monkeypatch):
    """The inverse arm, so the guard is a RANKING and not a mute button.

    The retry failed the same way: phase leaves `applying`, and the refusal of
    the bundle still in the inbox is the sentence again."""
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _waiting(root, files=7)
    _state(root, {"phase": "refused", "bundle": NEW,
                  "reason": "failed per-file digest verification", "paths": [],
                  "ts": "2026-09-08T19:02:00Z", "door": "web",
                  "last_refusal": {"bundle": NEW,
                                   "reason": "failed per-file digest verification",
                                   "paths": [], "ts": "2026-09-08T19:02:00Z",
                                   "door": "web"}})
    line = run_briefing._update_notice(str(root))
    assert line.startswith("Update refused"), line
    assert "digest" in line


# ---------------------------------------------------------------------------
# CURRENCY — a refusal speaks while it is the LAST THING THAT HAPPENED.
#
# `last_refusal` is carried onto every later state document on purpose
# (`update_bundle.CARRIED_STATE_FIELDS`), and nothing ever clears it: a refusal
# is still true after the next thing happens, and the record of it is what
# keeps a refused bundle from being offered as "ready" again. What it is NOT is
# still the news. Until 2026-09-09 the nothing-waiting branch of this helper
# asked only "is there a refusal on record", so one refusal made the applied
# and rolled-back sentences unreachable for the life of the install — the
# busy race that the `phase != applying` guard exists for ends in exactly that
# state (winner applies bbbb..., loser records `busy` about bbbb..., the
# install IS bbbb... so nothing is waiting) and the Captain's briefing said
# "Update refused — busy (bbbbbbbb)" over a Cabinet running those very bytes.
# ---------------------------------------------------------------------------

def _overtaken_refusal(root, phase, reason, paths, *, to_sha="c" * 40):
    """A completed apply / rollback carrying the refusal it overtook."""
    doc = {"phase": phase, "to_sha": to_sha,
           "last_refusal": {"bundle": NEW, "reason": reason, "paths": list(paths),
                            "ts": "2026-09-08T18:58:00Z", "door": "web"}}
    if phase == "applied":
        doc["changed"] = 4
    else:
        doc["reason"] = "the health gate was red"
    _state(root, doc)


def test_an_apply_since_the_refusal_overtakes_it_and_the_applied_line_wins(
        tmp_path, monkeypatch):
    """The busy race, at rest: the apply landed, so the apply is the news."""
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _overtaken_refusal(root, "applied", "busy", [])
    line = run_briefing._update_notice(str(root))
    assert line == "Updated to cccccccc: 4 changes", line
    assert run_briefing._update_refusal_line(root, "") == ""


def test_a_rollback_since_the_refusal_overtakes_it_too(tmp_path, monkeypatch):
    """The same, one branch along, and the sentence master used to give."""
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _overtaken_refusal(root, "rolled_back", "busy", [])
    line = run_briefing._update_notice(str(root))
    assert line == "An update was rolled back: the health gate was red", line
    assert run_briefing._update_refusal_line(root, "") == ""


def test_even_a_constitutional_refusal_is_overtaken_by_a_later_apply(
        tmp_path, monkeypatch):
    """The ceremony flow: locked refusal on bbbb..., the Captain unlocks and
    relocks, a NEW bundle applies. The install has been updated, and "Nothing
    was applied. These files change by a deliberate unlock..." over it is the
    card withdrawing Apply for a decision already taken."""
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _overtaken_refusal(root, "applied", "bundle changes locked constitutional paths",
                       ["cabinet/scripts/start-officer-mac.sh"])
    line = run_briefing._update_notice(str(root))
    assert line == "Updated to cccccccc: 4 changes", line
    assert "Captain" not in line, line


def test_the_refusal_still_speaks_when_it_IS_the_last_thing_that_happened(
        tmp_path, monkeypatch):
    """The inverse, so the currency check is a RANKING and not a mute button.

    Nothing waiting, nothing since: `phase` is still `refused`, and the refusal
    is the whole of the news. `test_a_refusal_of_a_bundle_that_is_gone_still_
    says_what_happened` is the same property from the other end; this one pins
    it beside its own negative so a fix that silenced both would be visible."""
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _state(root, {"phase": "refused", "bundle": NEW, "reason": "busy", "paths": [],
                  "ts": "2026-09-08T18:58:00Z", "door": "web",
                  "last_refusal": {"bundle": NEW, "reason": "busy", "paths": [],
                                   "ts": "2026-09-08T18:58:00Z", "door": "web"}})
    line = run_briefing._update_notice(str(root))
    assert line == "Update refused — busy (bbbbbbbb)", line
    assert run_briefing._update_refusal_line(root, "") != ""


def test_a_refusal_of_a_bundle_still_waiting_survives_a_later_apply_of_another(
        tmp_path, monkeypatch):
    """The half the currency check must NOT narrow.

    A later apply of some other bundle does not make the refused one safe to
    offer: it is still in the inbox and still refused, and "Update ready" over
    it is a button that cannot work. The sha scope decides here, not the phase."""
    _ledger(monkeypatch, tmp_path)
    root = _install(tmp_path)
    _waiting(root)
    _overtaken_refusal(root, "applied", "bundle changes locked constitutional paths",
                       ["cabinet/scripts/start-officer-mac.sh"])
    line = run_briefing._update_notice(str(root))
    assert line.startswith("Update refused"), line
    assert "constitutional" in line, line


# ---------------------------------------------------------------------------
# PARITY — the same state file, both readers, one fixture set on disk.
#
# `update_surface_parity.json` beside this file is the whole contract: the
# states the home card and this line must agree about. The card's half is
# `cabinet/dashboard/src/lib/updates.test.ts` ("surface parity"), reading the
# SAME file. Two independently-authored fixture sets could not have caught the
# defect above — each side proved only itself, and both sides carried a comment
# claiming they could not disagree.
#
# The wording differs on purpose (a card headline is not a briefing line), so
# what is asserted is: the KIND each sentence classifies to, that no sentence
# names a bundle other than the one the case is about, and any wording the two
# genuinely share. The classifier is total — an unrecognised sentence is
# `unclassified` and fails naming itself, never a silent pass.
# ---------------------------------------------------------------------------

import re  # noqa: E402

PARITY_FIXTURES = Path(__file__).parent / "update_surface_parity.json"
_SHA_TOKEN = re.compile(r"\b[0-9a-f]{8}\b")


def _classify_kind(line: str) -> str:
    """The one classifier, in the oracle's vocabulary. TOTAL: a sentence it
    does not recognise is `unclassified` and fails naming itself."""
    if not line:
        return "quiet"
    if line.startswith("An update is being taken right now"):
        return "applying"
    if line.startswith("Update records are not reaching the ledger"):
        return "fault"
    if line.startswith("Update refused") or "REFUSED" in line:
        return "refused"
    if line.startswith("An update is ready to take"):
        return "ready"
    if line.startswith("Updated to "):
        return "applied"
    if line.startswith("An update was rolled back"):
        return "rolled_back"
    return "unclassified"


#: The parity fixture predates the oracle and names its kinds its own way.
_PARITY_KIND = {"refused": "refusal", "applying": "apply-in-flight",
                "rolled_back": "rolled-back", "quiet": "silent"}


def _classify(line: str) -> str:
    kind = _classify_kind(line)
    return _PARITY_KIND.get(kind, kind)


def _install_case(tmp_path, case) -> Path:
    root = _install(tmp_path, source_commit=case["installed"])
    if case["waiting"]:
        _waiting(root, sha=case["waiting"]["sha"], files=case["waiting"]["file_count"],
                 built_at=case["waiting"]["built_at"])
    if case["state"] is not None:
        _state(root, case["state"])
    return root


def test_the_parity_fixture_carries_every_state_the_two_surfaces_argue_about():
    """A fixture set that quietly shrank would take both suites with it."""
    doc = json.loads(PARITY_FIXTURES.read_text(encoding="utf-8"))
    kinds = [case["agree"]["kind"] for case in doc["cases"]]
    assert len(doc["cases"]) == 7, kinds
    assert kinds.count("apply-in-flight") == 1, kinds
    assert kinds.count("refusal") == 1, kinds
    assert kinds.count("ready") == 3, kinds
    # TWO applied cases: one with no refusal on record and one carrying the
    # refusal it overtook. The first cannot see the round-3 defect, because
    # `last_refusal` is the one field the carry rule guarantees will be there.
    assert kinds.count("applied") == 2, kinds


def test_the_briefing_says_what_the_card_says_on_every_shared_state(tmp_path,
                                                                    monkeypatch):
    """This half. The card's half asserts the same table in vitest."""
    _ledger(monkeypatch, tmp_path)
    doc = json.loads(PARITY_FIXTURES.read_text(encoding="utf-8"))
    for index, case in enumerate(doc["cases"]):
        root = _install_case(tmp_path / ("case%d" % index), case)
        line = run_briefing._update_notice(str(root))
        agree = case["agree"]
        assert _classify(line) == agree["kind"], (case["name"], line)
        named = set(_SHA_TOKEN.findall(line))
        assert named <= {agree["bundle"]}, (case["name"], line, named)
        for wording in agree["shared_wording"]:
            assert wording in line, (case["name"], wording, line)
        # The card's `refusalToShow` is null on everything but a refusal, and
        # that is what withdraws Apply and names the files. Its twin here is
        # the helper the notice asks first, so it is pinned on the same states.
        waiting_sha = (case["waiting"] or {}).get("sha", "")
        spoke = bool(run_briefing._update_refusal_line(root, waiting_sha))
        assert spoke == (agree["kind"] == "refusal"), (case["name"], line)

# ---------------------------------------------------------------------------
# THE EXHAUSTIVE SWEEP — every state, not the ones somebody thought of.
#
# Three review rounds each found one more adjacent state in these same two
# readers, and every arm written for each of them was aimed at the state that
# already worked: round 1's two arms pinned `phase: applied`, round 2's pinned
# a state with no waiting bundle, round 3's both pinned `phase: refused`. That
# is not three unlucky arms, it is the shape of hand-written arms — the defect
# is always in the state nobody thought to write one for.
#
# `update_surface_oracle.json` is the whole product of the five axes the two
# readers actually branch on (240 rows), with the expected headline kind for
# EACH surface and whether the refusal sub-surface speaks. It is derived from
# the contract (A5.13/A5.15/A5.16), not from either implementation: a row where
# the code disagrees is a defect in the code. The card's half of the same table
# is `cabinet/dashboard/src/lib/updates.test.ts` ("the whole state space"),
# reading the SAME file, so a kind flipped in it reds both suites.
# ---------------------------------------------------------------------------

ORACLE_FIXTURES = Path(__file__).parent / "update_surface_oracle.json"


def test_the_oracle_covers_the_whole_product_of_the_axes_it_declares():
    """A table that quietly shrank would take both suites with it, silently.

    Derived from the declared axes rather than compared to a number, so it
    detects a REMOVED row as well as a changed one — a completeness claim that
    cannot see removal from the set it checks is the sensor this program has
    found broken most often."""
    import itertools

    doc = json.loads(ORACLE_FIXTURES.read_text(encoding="utf-8"))
    axes = doc["axes"]
    expected = set()
    for phase, waiting, refusal, ledger, fallback in itertools.product(
            axes["phase"], axes["waiting"], axes["refusal"],
            axes["ledger_error"], axes["event_fallback"]):
        expected.add("%s/%s/%s/%s/%s" % (
            phase, waiting, refusal,
            "fault" if ledger else "noledger", "held" if fallback else "nohold"))
    ids = [row["id"] for row in doc["rows"]]
    assert len(expected) == 240, len(expected)
    assert sorted(ids) == sorted(expected), (
        set(expected) - set(ids), set(ids) - set(expected))
    assert len(ids) == len(set(ids)), "duplicate row id"
    # Every row's id must describe the row's own axes, or the table is indexed
    # by a label that has come loose from what it labels.
    for row in doc["rows"]:
        a = row["axes"]
        assert row["id"] == "%s/%s/%s/%s/%s" % (
            a["phase"], a["waiting"], a["refusal"],
            "fault" if a["ledger_error"] else "noledger",
            "held" if a["event_fallback"] else "nohold"), row["id"]


def test_the_briefing_answers_every_state_the_way_the_oracle_says(tmp_path,
                                                                  monkeypatch):
    """This half of the sweep. The card's half asserts the same 240 rows."""
    _ledger(monkeypatch, tmp_path)
    doc = json.loads(ORACLE_FIXTURES.read_text(encoding="utf-8"))
    rows = doc["rows"]
    assert len(rows) == 240, len(rows)
    wrong = []
    for index, row in enumerate(rows):
        root = _install(tmp_path / ("row%03d" % index),
                        source_commit=row["installed"])
        if row["waiting"]:
            _waiting(root, sha=row["waiting"]["sha"],
                     files=row["waiting"]["file_count"],
                     built_at=row["waiting"]["built_at"])
        if row["state"] is not None:
            _state(root, row["state"])
        line = run_briefing._update_notice(str(root))
        kind = _classify_kind(line)
        waiting_sha = (row["waiting"] or {}).get("sha", "")
        spoke = bool(run_briefing._update_refusal_line(root, waiting_sha))
        expect = row["expect"]
        if kind != expect["briefing"] or spoke != expect["refusal_speaks"]:
            wrong.append("%s: kind %s (want %s), refusal spoke %s (want %s) -- %r"
                         % (row["id"], kind, expect["briefing"], spoke,
                            expect["refusal_speaks"], line))
    assert not wrong, "%d of %d states are not what the contract says:\n%s" % (
        len(wrong), len(rows), "\n".join(wrong[:20]))
