"""cabinet/scripts/task-events-watch.py — exemplar consumer contracts.

Fixture-driven; NO redis, NO network — the _redis_cli/_xack seams inject
(the test_exhaust_archive.py convention). What is pinned:

  * a task ENTERING 'blocked' files ONE Captain card on the needs ledger
    (kind decision, action_type task-blocked:<ctx>:<id>, filed_by
    system:task-events-watch) — and the fingerprint DEDUPES: the same task
    blocking again (or a redelivered event) bumps the SAME need's count
    instead of filing a second card;
  * config arms: missing file/key = ON (the ratified default); recognized
    off = OFF (events still processed + ACKed, no card); an unrecognized
    value fails safe to OFF (a Captain disarm attempt is never steamrolled);
  * the needs seam holds: with needs NOT wired (guardian world) nothing is
    filed even though the rule is ON;
  * envelope law consumer-side: an entry whose envelope is missing/invalid
    JSON/validate()-rejected is skipped AND ACKed (poison discard), never
    acted on;
  * injection controls: $(...)/quote/semicolon garbage in actor/context (and
    a rogue `title` field) never reaches the needs ledger bytes and never
    reaches a shell (canary) — card text interpolates validated tokens only;
  * transport parse: the redis-cli --json XREADGROUP shapes (dict fields and
    flat pairs) parse; garbage parses to nothing; run_once reads pending
    ('0') then new ('>').

Run: python3.12 -m pytest cabinet/scripts/tests/test_task_events_watch.py -q
"""
from __future__ import annotations

import importlib.util as _ilu
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / "cabinet" / "scripts" / "task-events-watch.py"

_spec = _ilu.spec_from_file_location("task_events_watch", _SCRIPT)
tew = _ilu.module_from_spec(_spec)
sys.modules["task_events_watch"] = tew
_spec.loader.exec_module(tew)

VALID_ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


def _envelope(actor: str = "cto") -> str:
    return json.dumps({
        "id": VALID_ULID,
        "from": actor,
        "to": "task-watchers",
        "kind": "evidence",
        "provenance": "test fixture",
        "taint": {"tier": "officer", "sources": ["officer_tasks"]},
        "budget": 0,
    })


def _entry(rid: str = "1-1", *, task_id: str = "7", old: str = "wip",
           new: str = "blocked", actor: str = "cto", ctx: str = "testctx",
           envelope: str | None = None, extra: dict | None = None):
    fields = {
        "envelope": _envelope(actor) if envelope is None else envelope,
        "task_id": task_id,
        "old_status": old,
        "new_status": new,
        "actor": actor,
        "context_slug": ctx,
        "ts": "2026-07-17T12:00:00Z",
    }
    if extra:
        fields.update(extra)
    return (rid, fields)


@pytest.fixture()
def acked():
    """ACKed entry ids recorded by the seam-injected _xack."""
    return []


@pytest.fixture()
def wired_root(tmp_path, monkeypatch, acked):
    """Needs-wired tmp cabinet root + recorded ACKs; no real redis."""
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    monkeypatch.setenv("CABINET_ID", "testcab")
    monkeypatch.setattr(tew, "_xack", lambda rid: acked.append(rid))
    return tmp_path


def _ledger_rows(root: Path) -> list[dict]:
    p = root / "shared" / "interfaces" / "needs-ledger.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def _write_config(root: Path, value: str) -> None:
    cfg = root / "instance" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "task-watch.yml").write_text(f"rules:\n  blocked_card: {value}\n")


# ---------------------------------------------------------------------------
# The rule: enters-blocked → fingerprint-deduped Captain card
# ---------------------------------------------------------------------------

def test_blocked_files_one_card(wired_root, acked):
    stats = tew.process_entries([_entry()], root=wired_root)
    assert stats["blocked_cards"] == 1
    assert stats["acked"] == 1 and acked == ["1-1"]
    rows = _ledger_rows(wired_root)
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "decision"
    assert row["action_type"] == "task-blocked:testctx:7"
    assert row["filed_by"] == "system:task-events-watch"
    assert row["status"] == "open"
    assert "task 7" in row["why"]


def test_same_task_dedupes_to_one_need(wired_root):
    tew.process_entries([_entry("1-1")], root=wired_root)
    tew.process_entries([_entry("1-2")], root=wired_root)  # re-block/redelivery
    rows = _ledger_rows(wired_root)
    assert len(rows) == 2  # append-only ledger: full-row re-file
    assert len({r["id"] for r in rows}) == 1, "one fingerprint per task"
    assert rows[-1]["count"] == 2


def test_different_tasks_get_different_cards(wired_root):
    tew.process_entries([_entry("1-1", task_id="7"),
                         _entry("1-2", task_id="8")], root=wired_root)
    assert len({r["id"] for r in _ledger_rows(wired_root)}) == 2


def test_non_blocked_transition_files_nothing(wired_root):
    stats = tew.process_entries(
        [_entry(new="done", old="wip"), _entry("1-2", new="wip", old="")],
        root=wired_root)
    assert stats["blocked_cards"] == 0
    assert _ledger_rows(wired_root) == []
    assert stats["acked"] == 2  # still consumed


def test_needs_seam_holds_when_not_wired(wired_root, monkeypatch):
    # Guardian world: rule ON but needs not wired → file_need no-ops (None).
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    stats = tew.process_entries([_entry()], root=wired_root)
    assert stats["blocked_cards"] == 0
    assert _ledger_rows(wired_root) == []
    assert stats["acked"] == 1  # consumption is independent of the seam


# ---------------------------------------------------------------------------
# Config arms
# ---------------------------------------------------------------------------

def test_config_missing_defaults_on(wired_root):
    assert tew.blocked_card_enabled(wired_root) is True


def test_config_off_disarms(wired_root):
    _write_config(wired_root, "off")
    assert tew.blocked_card_enabled(wired_root) is False
    stats = tew.process_entries([_entry()], root=wired_root)
    assert stats["blocked_cards"] == 0 and stats["rule_off_skips"] == 1
    assert _ledger_rows(wired_root) == []
    assert stats["acked"] == 1


def test_config_on_arms(wired_root):
    _write_config(wired_root, "on")
    assert tew.blocked_card_enabled(wired_root) is True


def test_config_unrecognized_fails_safe_off(wired_root, capsys):
    _write_config(wired_root, "offf")  # Captain typo'd a disarm — honor it
    assert tew.blocked_card_enabled(wired_root) is False
    assert "unrecognized" in capsys.readouterr().err


def test_config_file_without_key_defaults_on(wired_root):
    cfg = wired_root / "instance" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "task-watch.yml").write_text("rules: {}\n")
    assert tew.blocked_card_enabled(wired_root) is True


@pytest.mark.parametrize("value", [
    "off  # disarmed 2026-07-17 by Captain",
    '"off" # noisy',
    "false # stop the cards",
], ids=["plain+comment", "quoted+comment", "false+comment"])
def test_config_inline_comment_disarm_is_honored(wired_root, value):
    # P2 regression (2026-07-17 review): an inline YAML comment made the line
    # unmatchable, falling through to the absent-key default — steamrolling a
    # Captain disarm back to ON. Ordinary YAML comments must disarm cleanly.
    _write_config(wired_root, value)
    assert tew.blocked_card_enabled(wired_root) is False
    stats = tew.process_entries([_entry()], root=wired_root)
    assert stats["blocked_cards"] == 0 and stats["rule_off_skips"] == 1
    assert _ledger_rows(wired_root) == []


def test_config_inline_comment_on_stays_on(wired_root):
    # Negative control: comment stripping must not invert an ARM either.
    _write_config(wired_root, "on  # keep the cards coming")
    assert tew.blocked_card_enabled(wired_root) is True


def test_config_comment_body_cannot_smuggle_an_arm(wired_root):
    # Injection control: the comment is dead text — 'off # on' is OFF.
    _write_config(wired_root, "off # on")
    assert tew.blocked_card_enabled(wired_root) is False


def test_config_hash_glued_to_scalar_fails_safe_off(wired_root, capsys):
    # YAML: '#' NOT preceded by whitespace is part of the scalar, so 'off#x'
    # is ONE unrecognized token → fail-safe OFF + warn (still no steamroll).
    _write_config(wired_root, "off#x")
    assert tew.blocked_card_enabled(wired_root) is False
    assert "unrecognized" in capsys.readouterr().err


def test_config_empty_value_fails_safe_off(wired_root, capsys):
    # Key PRESENT with empty/comment-only value is not the missing-key
    # default: a half-typed disarm ('blocked_card:' with the value deleted)
    # must land OFF + warn, mirroring load_mode's str(None)→hold stance.
    _write_config(wired_root, "# disarm tomorrow?")
    assert tew.blocked_card_enabled(wired_root) is False
    assert "unrecognized" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Envelope law, consumer side (poison discard)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["", "not json", json.dumps({"id": "nope"})],
                         ids=["missing", "not-json", "validate-rejects"])
def test_invalid_envelope_skipped_and_acked(wired_root, bad):
    stats = tew.process_entries([_entry(envelope=bad)], root=wired_root)
    assert stats["invalid_envelope"] == 1
    assert stats["blocked_cards"] == 0
    assert _ledger_rows(wired_root) == []
    assert stats["acked"] == 1, "poison entries must not wedge the group"


# ---------------------------------------------------------------------------
# Injection controls
# ---------------------------------------------------------------------------

def test_injection_never_reaches_ledger_or_shell(wired_root, tmp_path):
    canary = tmp_path / "c"
    # Single canary reference keeps the envelope `from` under the 256-char
    # bound: the point HERE is sanitization of a VALID-envelope event.
    evil = f"$(touch {canary}); `id`"
    stats = tew.process_entries(
        [_entry(actor=evil, ctx='"; rm -rf /tmp/x',
                extra={"title": f"$(touch {canary})"})],
        root=wired_root)
    assert stats["blocked_cards"] == 1  # the card still files — on the ID
    assert not canary.exists(), "event field reached a shell"
    rows = _ledger_rows(wired_root)
    assert rows[0]["action_type"] == "task-blocked:unknown:7"
    raw = (wired_root / "shared" / "interfaces" / "needs-ledger.jsonl").read_text()
    assert "$(" not in raw and "`" not in raw and "rm -rf" not in raw
    assert "title" not in rows[0]["why"], "titles never reach a Captain surface"


def test_malformed_task_id_files_no_card(wired_root, capsys):
    stats = tew.process_entries([_entry(task_id="7; DROP TABLE")],
                                root=wired_root)
    assert stats["blocked_cards"] == 0
    assert _ledger_rows(wired_root) == []
    assert "malformed task_id" in capsys.readouterr().err
    assert stats["acked"] == 1


# ---------------------------------------------------------------------------
# Transport parse + read discipline (no redis — seam-injected)
# ---------------------------------------------------------------------------

def test_parse_entries_dict_and_flat_shapes():
    raw = json.dumps([["cabinet:tasks:events", [
        ["1-1", {"task_id": "7", "new_status": "blocked"}],
        ["1-2", ["task_id", "8", "new_status", "done"]],
    ]]])
    got = tew._parse_entries(raw)
    assert [rid for rid, _ in got] == ["1-1", "1-2"]
    assert got[0][1]["task_id"] == "7"
    assert got[1][1]["new_status"] == "done"


def test_parse_entries_garbage_yields_empty():
    assert tew._parse_entries("not json") == []
    assert tew._parse_entries(json.dumps({"nope": 1})) == []
    assert tew._parse_entries(json.dumps([["s", "not-a-list"]])) == []


def test_run_once_reads_pending_then_new(wired_root, monkeypatch):
    calls: list[tuple[str, ...]] = []

    def fake_cli(*args):
        calls.append(args)
        return ""

    monkeypatch.setattr(tew, "_redis_cli", fake_cli)
    stats = tew.run_once()
    assert stats["seen"] == 0
    assert calls[0][:4] == ("XGROUP", "CREATE", tew.STREAM, tew.GROUP)
    reads = [c for c in calls if "XREADGROUP" in c]
    assert [c[-1] for c in reads] == ["0", ">"], \
        "pending (crash recovery) must be read before new entries"
