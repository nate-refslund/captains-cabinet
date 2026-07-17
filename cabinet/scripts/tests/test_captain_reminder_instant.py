"""captain-reminder INSTANT push + tap-button round trip (Captain ruling
2026-07-17: "the time of day is set by the captain → push instantly").

Teeth:
  * push_card submits ONE kind="captain-reminder" gate item at fire time:
    floor-class primary + deadline_iso/ping-now belt, per-fire situation
    identity (uuid5 of task+instant — a snooze-bumped due_at re-PUSHES, the
    same fire re-submitted dedups), buttons whose callback payloads are the
    fixed verb enum + the need id's hex tail ONLY;
  * the REAL round trip with no Telegram/Redis: file_card → needs ledger →
    tap (tap_wire → the REAL binder door handle_captain_update) → the need
    status flips → the arm's reconcile (the phase the tick runs EVERY tick)
    closes a granted card and emits the snoozed card's task id for the +7d
    due_at bump; the later verb stamps snoozed_until exactly +SNOOZE_DAYS;
  * INJECTION CONTROL: a hostile title (quotes / $() / backticks / markdown
    / U+00B7 / newlines) stays DATA in the card body, never changes the
    callback payload bytes, and cannot forge a binder pid-marker;
  * the file-card CLI stays fail-quiet: a shell with sends blocked
    (allow_sends()=False, the dev default) still exits 0, prints the need
    id, and notes the undelivered push on stderr — the tick never breaks.

Hermetic: tmp CABINET_ROOT (needs ledger), tmp CABINET_ATTENTION_DIR
(standing map), CABINET_NEEDS_WIRED=1, UTC clock; the binder door runs with
its redis/pending/present seams injected (no live estate).
"""
from __future__ import annotations

import datetime as dt
import importlib.util as _ilu
import io
import os
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO / "cabinet" / "scripts"

if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _load(name: str, fname: str):
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    spec = _ilu.spec_from_file_location(name, _SCRIPTS / fname)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


arm = _load("captain_reminder_arm", "captain-reminder-arm.py")

UTC = dt.timezone.utc
CPH = ZoneInfo("Europe/Copenhagen")
DUE = "2026-07-17T03:00:00Z"          # deep inside default quiet hours


@pytest.fixture
def wired(tmp_path, monkeypatch):
    """Tmp cabinet root, needs plane WIRED, hermetic attention dir."""
    (tmp_path / "shared" / "interfaces").mkdir(parents=True)
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    monkeypatch.setenv("CABINET_ATTENTION_DIR", str(tmp_path / "attention"))
    monkeypatch.setenv("CABINET_CAPTAIN_TZ", "UTC")
    monkeypatch.setenv("CABINET_BRIEFING_TIMES", "07:30,19:30")
    monkeypatch.delenv("CABINET_CAPTAIN_SLUG", raising=False)
    import framework.env as fe
    fe._captain_slug_cache = None
    return tmp_path


def _rows(root):
    from framework.authority import needs
    return needs._merged(needs.ledger_path(str(root)))


# ===========================================================================
# build_push_item / push_card — the instant gate item
# ===========================================================================

class TestPushItem:

    def test_item_shape_floor_kind_belt_and_buttons(self, wired):
        nid = arm.file_card(42, DUE, "sign the quarterly filing", tz=CPH)
        item = arm.build_push_item(42, DUE, "sign the quarterly filing", nid)
        assert item["kind"] == "captain-reminder"       # the FLOOR class kind
        assert item["urgency"] == "ping-now"
        assert item["deadline_iso"] == DUE              # the belt: real instant
        assert "sign the quarterly filing" in item["subject"]
        assert nid in item["situation"]                 # typed verbs still work
        hex8 = nid[len("NEED-"):]
        [row] = item["buttons"]
        assert [b["data"] for b in row] == [
            f"cv2|ndg|{hex8}", f"cv2|ndl|{hex8}", f"cv2|ndd|{hex8}"]
        assert [b["text"] for b in row] == ["✓ Done", "⏰ Later 7d", "✗ Drop"]

    def test_push_card_submits_and_confirms_on_transport_ok(self, wired):
        nid = arm.file_card(43, DUE, "x", tz=CPH)
        seen = []

        def submit_fn(item):
            seen.append(item)
            return {"decision": {"action": "send"},
                    "result": {"sent": True, "message_ids": [700]}}

        assert arm.push_card(43, DUE, "x", nid, submit_fn=submit_fn) is True
        assert len(seen) == 1 and seen[0]["kind"] == "captain-reminder"

    def test_push_card_reports_undelivered_transport(self, wired):
        nid = arm.file_card(44, DUE, "x", tz=CPH)
        blocked = {"decision": {"action": "send"},
                   "result": {"status": "blocked-dev", "sent": False}}
        assert arm.push_card(44, DUE, "x", nid,
                             submit_fn=lambda item: blocked) is False

    def test_push_card_never_raises(self, wired):
        nid = arm.file_card(45, DUE, "x", tz=CPH)

        def boom(item):
            raise RuntimeError("gate down")

        assert arm.push_card(45, DUE, "x", nid, submit_fn=boom) is False

    def test_snooze_bump_mints_new_situation_same_fire_dedups(self, wired):
        """The per-fire identity law: same (task, due) → same situation key
        (crash re-file suppresses); a +7d-bumped due_at → NEW key (the re-arm
        PUSHES again instead of silently editing a week-old card)."""
        from framework.attention.situation import situation_key
        nid = arm.file_card(46, DUE, "x", tz=CPH)
        a = arm.build_push_item(46, DUE, "x", nid)
        b = arm.build_push_item(46, DUE, "x", nid)              # same fire
        c = arm.build_push_item(46, "2026-07-24T03:00:00Z", "x", nid)  # bumped
        k = lambda it: situation_key(it["evidence"], it["subject"])
        assert k(a) == k(b)
        assert k(a) != k(c)

    def test_instant_send_through_real_gate_inside_quiet_hours(self, wired):
        """END-TO-END through the REAL gate at 03:00: decision=send (the
        floor law), buttons ride to the transport, NOT a briefing fold."""
        from framework.attention import gate
        nid = arm.file_card(47, DUE, "wake me — I chose 03:00", tz=CPH)
        sent = []

        def send_fn(text, **kw):
            sent.append({"text": text, **kw})
            return {"sent": True, "message_ids": [801]}

        night = dt.datetime(2026, 7, 17, 3, 0, tzinfo=UTC)
        res = arm.push_card(
            47, DUE, "wake me — I chose 03:00", nid,
            submit_fn=lambda item: gate.submit(item, now=night,
                                               send_fn=send_fn))
        assert res is True
        assert len(sent) == 1
        assert "wake me — I chose 03:00" in sent[0]["text"]
        assert sent[0]["buttons"] and sent[0]["buttons"][0][0]["data"] == \
            f"cv2|ndg|{nid[len('NEED-'):]}"
        assert sent[0]["silent"] is False


# ===========================================================================
# INJECTION CONTROL — hostile title stays data end-to-end
# ===========================================================================

EVIL = ("x\" '; DROP TABLE t; -- $(rm -rf /) `id` *bold* _i_ [l](u)\n"
        "second·line·with·markers\ttab")


class TestInjectionStaysData:

    def test_hostile_title_is_card_data_only(self, wired):
        nid = arm.file_card(60, DUE, EVIL, tz=CPH)
        item = arm.build_push_item(60, DUE, EVIL, nid)
        subj = item["subject"]
        assert "\n" not in subj and "\t" not in subj    # one-line subject
        assert "·" not in subj                          # pid-marker stripped
        assert "$(rm -rf /)" in subj                    # payload survives AS TEXT
        assert "`id`" in subj
        assert "DROP TABLE t" in subj

    def test_hostile_title_never_touches_callback_payload(self, wired):
        nid_e = arm.file_card(61, DUE, EVIL, tz=CPH)
        nid_b = arm.file_card(62, DUE, "benign", tz=CPH)
        evil_item = arm.build_push_item(61, DUE, EVIL, nid_e)
        benign_item = arm.build_push_item(62, DUE, "benign", nid_b)

        def datas(it):
            return [b["data"].split("|")[:2] for b in it["buttons"][0]]

        # verb enum identical; args are each card's own hex tail and NOTHING
        # from the title (byte-shape check: cv2|verb|hex8)
        assert datas(evil_item) == datas(benign_item)
        for b in evil_item["buttons"][0]:
            prefix, verb, arg = b["data"].split("|")
            assert (prefix, verb in ("ndg", "ndl", "ndd")) == ("cv2", True)
            assert arg == nid_e[len("NEED-"):]
            assert len(b["data"]) <= 64

    def test_button_captions_are_fixed_never_title_bearing(self, wired):
        nid = arm.file_card(63, DUE, EVIL, tz=CPH)
        item = arm.build_push_item(63, DUE, EVIL, nid)
        assert [b["text"] for b in item["buttons"][0]] == \
            ["✓ Done", "⏰ Later 7d", "✗ Drop"]

    def test_malformed_need_id_ships_no_buttons(self, wired):
        assert arm.reminder_buttons("NEED-ZZZZZZZZ") is None
        assert arm.reminder_buttons("NEED-aabbccddee") is None
        assert arm.reminder_buttons("aabbccdd") is None
        assert arm.reminder_buttons("") is None


# ===========================================================================
# The tap → binder door → ledger → reconcile ROUND TRIP (no Telegram/Redis)
# ===========================================================================

def _door(text: str, quoted: str, receipts: list) -> dict:
    """The REAL equal-authority door with its estate seams injected (no
    redis, no pending proposals, receipts recorded instead of sent)."""
    from framework.frontdoor import binder_wire
    return binder_wire.handle_captain_update(
        text, quoted,
        redis_get=lambda k: "",
        pending_source=lambda: [],
        list_undo_windows=lambda: [],
        present=lambda s: receipts.append(s),
        log=lambda m: None)


class TestTapRoundTrip:

    def test_done_tap_flips_need_and_reconcile_closes_it(self, wired):
        from framework.comms.surface import tap_wire
        nid = arm.file_card(70, DUE, "done-me", tz=CPH)
        hex8 = nid[len("NEED-"):]
        receipts, marks = [], []

        res = tap_wire.apply_tap(
            f"cv2|ndg|{hex8}", message_id=901,
            wire=lambda t, q: _door(t, q, receipts),
            edit_markup=lambda mid, kb: marks.append((mid, kb)))

        assert res["handled"] is True and res["outcome"] == "approved_pending_apply"
        assert _rows(wired)[nid]["status"] == "approved_pending_apply"
        assert marks and marks[0][0] == 901          # keyboard receipt swapped

        # ...and the phase the tick runs EVERY tick picks it up:
        out = io.StringIO()
        summary = arm.reconcile(out=out)
        assert summary["closed"] == 1
        assert out.getvalue().strip() == ""          # nothing to bump
        assert _rows(wired)[nid]["status"] == "granted"

    def test_later_tap_snoozes_7d_and_reconcile_emits_task_id(self, wired):
        from framework.authority import needs
        from framework.comms.surface import tap_wire
        nid = arm.file_card(71, DUE, "later-me", tz=CPH)
        hex8 = nid[len("NEED-"):]

        res = tap_wire.apply_tap(f"cv2|ndl|{hex8}", message_id=902,
                                 wire=lambda t, q: _door(t, q, []))
        assert res["outcome"] == "snoozed"

        row = _rows(wired)[nid]
        assert row["status"] == "snoozed"
        until = dt.datetime.fromisoformat(row["snoozed_until"].replace("Z", "+00:00"))
        marked = dt.datetime.fromisoformat(row["marked_at"].replace("Z", "+00:00"))
        assert until - marked == dt.timedelta(days=needs.SNOOZE_DAYS)  # +7d law

        # the tick's reconcile phase prints EXACTLY this task id for the
        # guarded +7d due_at bump (the 041 re-arm trigger then refires it)
        out = io.StringIO()
        summary = arm.reconcile(out=out)
        assert summary["snoozed"] == 1
        assert out.getvalue().split() == ["71"]

    def test_drop_tap_denies_and_never_bumps(self, wired):
        from framework.comms.surface import tap_wire
        nid = arm.file_card(72, DUE, "drop-me", tz=CPH)
        hex8 = nid[len("NEED-"):]

        res = tap_wire.apply_tap(f"cv2|ndd|{hex8}", message_id=903,
                                 wire=lambda t, q: _door(t, q, []))
        assert res["outcome"] == "denied"
        row = _rows(wired)[nid]
        assert row["status"] == "denied"
        assert row.get("suppressed_until")           # 90d re-file suppression

        out = io.StringIO()
        summary = arm.reconcile(out=out)
        assert summary == {"closed": 0, "snoozed": 0, "skipped": 0}
        assert out.getvalue().strip() == ""          # deny NEVER bumps due_at

    def test_stale_id_tap_fails_closed_through_the_door(self, wired):
        """A hex8 that matches the grammar but names no ledger row: the door
        refuses (needs.mark fail-closed) and the tap relays to the Chair —
        byte-parity with the typed verb's refusal."""
        from framework.comms.surface import tap_wire
        res = tap_wire.apply_tap("cv2|ndg|00000000", message_id=904,
                                 wire=lambda t, q: _door(t, q, []))
        assert res["handled"] is False and res["relay"] is True
        assert not any(r.get("status") == "approved_pending_apply"
                       for r in _rows(wired).values())

    def test_typed_verbs_unchanged_by_the_button_wiring(self, wired):
        """Typed-path parity guard: the SAME canonical line typed by the
        Captain still works — the buttons added a caller, not a grammar."""
        nid = arm.file_card(73, DUE, "typed-me", tz=CPH)
        res = _door(f"later {nid}", "", [])
        assert res.get("handled") is True and res.get("need") == "snoozed"
        assert _rows(wired)[nid]["status"] == "snoozed"


# ===========================================================================
# file-card CLI — fail-quiet with sends blocked (dev default)
# ===========================================================================

class TestFileCardCli:

    def test_cli_files_card_and_degrades_push_loudly_but_exits_zero(
            self, wired, monkeypatch):
        env = {**os.environ,
               "CABINET_ROOT": str(wired),
               "CABINET_NEEDS_WIRED": "1",
               "CABINET_ATTENTION_DIR": str(wired / "attention"),
               "CABINET_CAPTAIN_TZ": "UTC"}
        env.pop("CABINET_ALLOW_SENDS", None)   # dev default: sends blocked
        r = subprocess.run(
            [sys.executable, str(_SCRIPTS / "captain-reminder-arm.py"),
             "file-card", "--task-id", "80", "--due-at", DUE],
            input="cli reminder", capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        nid = r.stdout.strip()
        assert nid.startswith("NEED-")
        assert _rows(wired)[nid]["action_type"] == "captain-reminder:80"
        # the push could not deliver (no transport in a dev shell) — ONE
        # honest stderr line, never a broken tick
        assert "instant push" in r.stderr
