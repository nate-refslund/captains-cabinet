"""§4.2 belief invalidation — the APPLY organ (memory-supersede-apply.py).

Fixture-driven (rows/conn/probe/needs injected; no psql, no Neon, no
psycopg2). Pins: the recomputed-Jaccard 0.75 boundary (0.74 refuses),
cross-source_type / raced / order refusals, windowless by-id liveness (a
probe-superseded row refuses terminally, a probe-absent row refuses
``refused-gone``, an UNREACHABLE probe leaves the pair OPEN as blocked-db —
aged-out live pairs are never silently dropped and still apply), the
14-day soak gate (13d no, 14d yes, reversal re-blocks, hold flag holds
forever, unknown flag value never arms, an unreadable EXISTING config
fails closed to hold), the reversal-resolved Captain ruling (re-arms; a
later reversal re-blocks; empty note refused), cue-class never-applies on
similarity + one-tap card filing RETRIED until a need id lands + the
HONEST card text, the approved-card EXECUTOR (the binder ``grant`` verb
marks ``approved_pending_apply`` for EVERY kind and grant-apply.sh
refuses kind!=standing_grant, so THAT status — never ``granted`` — is
the production signal that routes the pair through the guarded apply
path once armed, ``via: captain-grant``; the organ then closes the need
with the ``granted`` receipt so the approved set stops growing, a moot
pair closes it ``superseded``; denied/open/hand-granted never trigger;
the soak/hold gate still governs — pinned end-to-end through the REAL
framework.authority.needs API), the BINDING half-soak veto (a Captain
deny on the soak-halfway card holds the gate: held-by-captain-veto, no
arming, marker recorded, card never re-filed, lifted by a later grant
on the same card — full deny path through the real needs API), the
same-run touched-id defer (an equal-ts reciprocal pair can never
supersede BOTH rows), the MAX_APPLIES_PER_RUN blast-radius cap, the
armed-but-writer-unavailable loud blocked-db degrade (stays open, no
ledger spam, recovers), a failed --undo still latching the gate, the
once-per-soak half-way Captain card, ledger-surgery recovery (consumed
stamps reopen when the soak ledger lost them), undo + reversal,
idempotent re-run, per-row proposals consumption (detector dedup
preserved), ledger carries hashes not text, the module's store surface is
two parameterized UPDATE constants + one read-only by-id SELECT with no
row-removal verb, the egg-export manifest scrubs the live instance config
(.example twin ships), and the services rows: detect and apply are
SEPARATE single-command rows — the generated-plist wrapper ``exec``s the
command, so a ``&&`` chain silently loses everything after the first
program (pinned fleet-wide, pinned at render level + proven empirically
below).
"""
from __future__ import annotations

import datetime as dt
import importlib.util as _ilu
import json
import os
import re
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[3]

# The egg-export manifest is PRIVATE-SIDE export tooling — it drives the export
# and is stripped from the packaged egg. Absent on a clean/public checkout, so
# the scrub-row assertions below cannot be made there; skip loud + named. On the
# source instance the manifest is present ⇒ the R120 scrub pin runs full-teeth.
_EGG_MANIFEST = _REPO / "cabinet" / "scripts" / "egg-export-manifest.txt"
requires_egg_manifest = pytest.mark.skipif(
    not _EGG_MANIFEST.is_file(),
    reason="egg-export-manifest.txt absent — private-side export tooling, not "
           "shipped in the egg; the R120 scrub-row pin arms on the source instance",
)


def _load(name: str, fname: str):
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    spec = _ilu.spec_from_file_location(
        name, _REPO / "cabinet" / "scripts" / fname)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


msa = _load("memory_supersede_apply", "memory-supersede-apply.py")
mc = sys.modules["memory_contradictions"]  # loaded by the organ itself

NOW = dt.datetime(2026, 7, 15, 12, 0, 0, tzinfo=dt.timezone.utc)


def _iso(ts: dt.datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _live(id, content, ts="2026-07-01T10:00:00Z", stype="captain_decision"):
    return {"id": str(id), "source_type": stype, "officer": "cos",
            "content": content, "ts": ts}


def _prop(pid, old_id, new_id, reason="near-duplicate", cues=None):
    return {"proposal_id": pid, "status": "proposed", "reason": reason,
            "cues": cues or [], "jaccard": 0.9,
            "source_type": "captain_decision",
            "old": {"id": str(old_id), "ts": "2026-06-01T10:00:00Z",
                    "snippet": "old snippet"},
            "new": {"id": str(new_id), "ts": "2026-07-01T10:00:00Z",
                    "snippet": "new snippet"}}


def _toks(shared: int, union: int) -> tuple:
    """(old_text, new_text) with token-Jaccard EXACTLY shared/union
    (old ⊂ new; every token passes the detector's word regex)."""
    old = [f"tok{i:02d}" for i in range(1, shared + 1)]
    new = old + [f"tok{i:02d}" for i in range(shared + 1, union + 1)]
    return " ".join(old), " ".join(new)


def _write_jsonl(path: Path, rows) -> None:
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


class FakeCursor:
    def __init__(self, conn):
        self._conn = conn
        self.rowcount = -1

    def execute(self, sql, params=None):
        assert isinstance(params, tuple), \
            "store writes must be parameterized (params tuple)"
        assert all(isinstance(p, int) for p in params), \
            "only int()-validated ids may bind"
        self._conn.calls.append((sql, params))
        self.rowcount = self._conn._rowcount_for(sql, params)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConn:
    """cabinet_memory stand-in: {old_id: superseded_by-or-None}. Accepts
    ONLY the two module-constant statements — anything else asserts."""

    def __init__(self, live=None):
        self.live = dict(live or {})
        self.calls = []
        self.commits = 0
        self.closed = False

    def _rowcount_for(self, sql, params):
        if sql == msa._APPLY_SQL:
            new_id, old_id = params
            if self.live.get(old_id, "absent") is None:
                self.live[old_id] = new_id
                return 1
            return 0
        if sql == msa._UNDO_SQL:
            old_id, new_id = params
            if self.live.get(old_id) == new_id:
                self.live[old_id] = None
                return 1
            return 0
        raise AssertionError(f"unexpected SQL reached the store: {sql!r}")

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


class Boom:
    """conn factory that must never be reached."""

    def __init__(self):
        self.called = False

    def __call__(self):
        self.called = True
        raise RuntimeError("no store access expected in this test")


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, kind, **kw):
        self.calls.append((kind, kw))
        return "NEED-feedbeef"


class MarkRecorder:
    """mark_need_fn seam: records the organ's need-closure receipts —
    and keeps unit tests off the REAL needs ledger."""

    def __init__(self):
        self.calls = []

    def __call__(self, nid, status, reason):
        self.calls.append((nid, status, reason))
        return {"id": nid, "status": status}


def _run(tmp_path, proposals, live, *, soak_rows=None, config=None, now=NOW,
         conn=None, conn_factory=None, need_fn=None, fetch=None,
         needs_rows=None, mark_fn=None, dry_run=False, posture="sovereign"):
    # posture defaults to SOVEREIGN (hermetic — explicitly injected, never
    # the live ruling): these fixtures pin the organ's INNER law (soak
    # clock, hold flag, veto, jaccard, liveness, caps...), and sovereign is
    # the widest seam answer — an inner gate proven to hold under sovereign
    # holds under every posture. The action-seam OUTER gate (Captain law
    # 2026-07-17) has its own arms in TestActionSeamOuterGate with explicit
    # narrower postures.
    ppath = tmp_path / "proposals.jsonl"
    if not ppath.exists() or proposals is not None:
        _write_jsonl(ppath, proposals or [])
    spath = tmp_path / "soak.jsonl"
    if soak_rows is not None:
        _write_jsonl(spath, soak_rows)
    cpath = tmp_path / "memory-supersession.yml"
    if config is not None:
        cpath.write_text(config)
    npath = tmp_path / "needs-ledger.jsonl"   # ALWAYS isolated from the repo
    if needs_rows is not None:
        _write_jsonl(npath, needs_rows)
    factory = conn_factory or ((lambda: conn) if conn is not None else Boom())
    need = need_fn if need_fn is not None else Recorder()
    mark = mark_fn if mark_fn is not None else MarkRecorder()
    summary = msa.run_apply_pass(
        proposals_path=ppath, soak_path=spath, config_path=cpath,
        needs_path=npath, now=now, live_rows=live, conn_factory=factory,
        fetch_rows_fn=fetch, file_need_fn=need, mark_need_fn=mark,
        dry_run=dry_run, posture=posture)
    return summary, ppath, spath, need


def _decisions(spath: Path):
    return [r for r in msa.read_jsonl(spath) if r.get("proposal_id")]


ARMED_SEED = [{"ts": _iso(NOW - timedelta(days=15)), "decision": "run",
               "mode": "soak"}]


class TestJaccardBoundary:
    def test_075_would_apply_074_refuses(self, tmp_path):
        old75, new75 = _toks(3, 4)      # 3/4  = 0.75  → eligible
        old74, new74 = _toks(37, 50)    # 37/50 = 0.74 → refused
        live = [_live(1, old75), _live(2, new75),
                _live(3, old74), _live(4, new74)]
        props = [_prop("sup-aaa11111", 1, 2), _prop("sup-bbb22222", 3, 4)]
        s, _, spath, _ = _run(tmp_path, props, live)
        assert s["would_apply"] == 1 and s["refused"] == 1
        by_pid = {d["proposal_id"]: d for d in _decisions(spath)}
        assert by_pid["sup-aaa11111"]["decision"] == "would_apply"
        assert by_pid["sup-aaa11111"]["jaccard"] == 0.75
        assert by_pid["sup-bbb22222"]["decision"] == "refused-jaccard"
        assert by_pid["sup-bbb22222"]["jaccard"] == 0.74


class TestRefusals:
    def test_cross_source_type_refuses_even_armed(self, tmp_path):
        old, new = _toks(3, 4)
        live = [_live(1, old, stype="captain_decision"),
                _live(2, new, stype="telegram_dm")]
        conn = FakeConn({1: None})
        s, _, spath, _ = _run(tmp_path, [_prop("sup-ccc33333", 1, 2)], live,
                              soak_rows=ARMED_SEED, conn=conn)
        assert s["state"] == "armed"
        assert s["applied"] == 0 and s["refused"] == 1
        assert conn.calls == []
        assert _decisions(spath)[0]["decision"] == "refused-source-type"

    def test_probe_superseded_row_refuses_terminally(self, tmp_path):
        # absent from the windowed live view AND the by-id probe shows the
        # pointer already set → the pair is moot, refuse for good
        old, new = _toks(3, 4)
        live = [_live(2, new)]          # old row (id 1) not in the window
        probe_calls = []

        def probe(ids):
            probe_calls.append(ids)
            return [{**_live(1, old), "superseded_by": "42"}]

        conn = FakeConn()
        s, _, spath, _ = _run(tmp_path, [_prop("sup-ddd44444", 1, 2)], live,
                              soak_rows=ARMED_SEED, conn=conn, fetch=probe)
        assert probe_calls == [[1]]     # int-validated, only the missing id
        assert s["applied"] == 0 and s["refused"] == 1
        assert conn.calls == []
        assert _decisions(spath)[0]["decision"] == "refused-superseded"

    def test_probe_absent_row_refuses_gone(self, tmp_path):
        # probe ran fine and the id simply is not in the store
        old, new = _toks(3, 4)
        live = [_live(2, new)]
        conn = FakeConn()
        s, _, spath, _ = _run(tmp_path, [_prop("sup-ddd44445", 1, 2)], live,
                              soak_rows=ARMED_SEED, conn=conn,
                              fetch=lambda ids: [])
        assert s["applied"] == 0 and s["refused"] == 1
        assert conn.calls == []
        assert _decisions(spath)[0]["decision"] == "refused-gone"

    def test_raced_apply_is_refused_not_applied(self, tmp_path):
        # live view says live, but the store was superseded in between —
        # the guarded UPDATE hits 0 rows and MUST NOT count as applied
        old, new = _toks(3, 4)
        live = [_live(1, old), _live(2, new)]
        conn = FakeConn({1: 999})       # already superseded by someone else
        s, _, spath, _ = _run(tmp_path, [_prop("sup-eee55555", 1, 2)], live,
                              soak_rows=ARMED_SEED, conn=conn)
        assert s["applied"] == 0 and s["refused"] == 1
        assert len(conn.calls) == 1     # the guard fired, nothing else
        assert _decisions(spath)[0]["decision"] == "refused-raced"
        assert conn.live[1] == 999      # store untouched

    def test_inverted_timestamp_order_refuses(self, tmp_path):
        old, new = _toks(3, 4)
        live = [_live(1, old, ts="2026-07-10T10:00:00Z"),
                _live(2, new, ts="2026-06-01T10:00:00Z")]
        s, _, spath, _ = _run(tmp_path, [_prop("sup-fff66666", 1, 2)], live,
                              soak_rows=ARMED_SEED, conn=FakeConn({1: None}))
        assert s["applied"] == 0
        assert _decisions(spath)[0]["decision"] == "refused-order"

    def test_non_integer_ids_refused_before_any_sql(self, tmp_path):
        prop = _prop("sup-abc99999", "1; DROP TABLE x", 2)
        conn = FakeConn({1: None})
        probe_calls = []

        def probe(ids):
            probe_calls.append(ids)
            return []

        s, _, spath, _ = _run(tmp_path, [prop], [], soak_rows=ARMED_SEED,
                              conn=conn, fetch=probe)
        assert conn.calls == []
        assert _decisions(spath)[0]["decision"] == "refused-bad-id"
        # the injection-shaped id never even reaches the probe id set
        assert probe_calls == [[2]]


class TestSoakGate:
    def _eligible(self):
        old, new = _toks(3, 4)
        return [_live(1, old), _live(2, new)], [_prop("sup-abcd0001", 1, 2)]

    def test_13_days_stays_propose_only(self, tmp_path):
        live, props = self._eligible()
        seed = [{"ts": _iso(NOW - timedelta(days=13)), "decision": "run",
                 "mode": "soak"}]
        boom = Boom()
        s, _, spath, _ = _run(tmp_path, props, live, soak_rows=seed,
                              conn_factory=boom)
        assert s["state"] == "soak"
        assert s["would_apply"] == 1 and s["applied"] == 0
        assert boom.called is False
        assert _decisions(spath)[0]["decision"] == "would_apply"

    def test_14_days_arms_and_applies(self, tmp_path):
        live, props = self._eligible()
        seed = [{"ts": _iso(NOW - timedelta(days=14)), "decision": "run",
                 "mode": "soak"}]
        conn = FakeConn({1: None})
        s, _, spath, _ = _run(tmp_path, props, live, soak_rows=seed,
                              conn=conn)
        assert s["state"] == "armed" and s["applied"] == 1
        assert conn.calls == [(msa._APPLY_SQL, (2, 1))]
        assert conn.commits == 1 and conn.live[1] == 2
        assert _decisions(spath)[0]["decision"] == "applied"

    def test_reversal_blocks_arming(self, tmp_path):
        live, props = self._eligible()
        seed = ARMED_SEED + [{"ts": _iso(NOW - timedelta(days=2)),
                              "decision": "reversal",
                              "proposal_id": "sup-old00001",
                              "old_id": "7", "new_id": "8", "undone": True}]
        boom = Boom()
        s, *_ = _run(tmp_path, props, live, soak_rows=seed,
                     conn_factory=boom)
        assert s["state"] == "soak"
        assert s["applied"] == 0 and s["would_apply"] == 1
        assert boom.called is False

    def test_hold_flag_blocks_forever(self, tmp_path):
        live, props = self._eligible()
        boom = Boom()
        s, *_ = _run(tmp_path, props, live, soak_rows=ARMED_SEED,
                     config="auto_apply: hold\n", conn_factory=boom)
        assert s["state"] == "hold" and s["applied"] == 0
        assert s["would_apply"] == 1
        assert boom.called is False

    def test_unrecognized_flag_value_never_arms(self, tmp_path):
        live, props = self._eligible()
        boom = Boom()
        s, *_ = _run(tmp_path, props, live, soak_rows=ARMED_SEED,
                     config="auto_apply: yolo\n", conn_factory=boom)
        assert s["mode"] == "hold" and s["applied"] == 0
        assert boom.called is False

    def test_missing_config_defaults_to_soak(self, tmp_path):
        assert msa.load_mode(tmp_path / "nope.yml") == "soak"

    def test_repo_config_pins_ratified_default(self):
        # EGG-HERMETIC: the export manifest DELETES the live instance
        # config while this test file ships, so a fresh-egg run must not
        # read_text() it unconditionally. The ratified default is pinned
        # against the ALWAYS-shipped .example twin; the live file is
        # checked only when this checkout has one — its absence IS the
        # ratified soak default (test_missing_config_defaults_to_soak).
        twin = (_REPO / "instance" / "config" /
                "memory-supersession.yml.example")
        assert yaml.safe_load(twin.read_text())["auto_apply"] == "soak"
        assert "2026-07-15 Captain ratification" in twin.read_text()
        live = _REPO / "instance" / "config" / "memory-supersession.yml"
        if not live.exists():
            pytest.skip("live instance config egg-scrubbed — absence = "
                        "ratified soak default")
        assert yaml.safe_load(live.read_text())["auto_apply"] == "soak"
        assert "2026-07-15 Captain ratification" in live.read_text()

    def test_soaked_pair_applies_after_arming(self, tmp_path):
        # end-to-end: consumed during soak, then picked up once armed
        live, props = self._eligible()
        pid = props[0]["proposal_id"]
        ppath = tmp_path / "proposals.jsonl"
        _write_jsonl(ppath, props + [
            {"proposal_id": pid, "status": "consumed",
             "consumed_at": _iso(NOW - timedelta(days=15)),
             "decision": "would_apply"}])
        seed = [{"ts": _iso(NOW - timedelta(days=15)), "decision": "run",
                 "mode": "soak"},
                {"ts": _iso(NOW - timedelta(days=15)), "mode": "soak",
                 "decision": "would_apply", "proposal_id": pid,
                 "reason": "near-duplicate", "old_id": "1", "new_id": "2",
                 "jaccard": 0.75, "texts_hash": "x"}]
        conn = FakeConn({1: None})
        s, _, spath, _ = _run(tmp_path, None, live, soak_rows=seed,
                              conn=conn)
        assert s["state"] == "armed" and s["applied"] == 1
        assert conn.calls == [(msa._APPLY_SQL, (2, 1))]
        assert s["consumed"] == 0   # reopened, not re-consumed


class TestCueClass:
    def test_cue_never_applies_even_armed_and_identical(self, tmp_path):
        # identical texts (Jaccard 1.0) — the strongest possible near-dup
        # signal — still never applies when the REASON is contradiction-cue
        text = "the same identical belief text about the todos board"
        live = [_live(1, text), _live(2, text + " retired")]
        prop = _prop("sup-cue00001", 1, 2, reason="contradiction-cue",
                     cues=["retired"])
        conn = FakeConn({1: None})
        rec = Recorder()
        s, _, spath, _ = _run(tmp_path, [prop], live, soak_rows=ARMED_SEED,
                              conn=conn, need_fn=rec)
        assert s["state"] == "armed"
        assert s["cue_cards"] == 1 and s["applied"] == 0
        assert conn.calls == []                    # zero store writes
        # day 15 of the soak also files the half-soak heads-up — filter to
        # THIS pair's card
        cue_calls = [c for c in rec.calls
                     if c[1]["action_type"] == "memory-supersede:sup-cue00001"]
        assert len(cue_calls) == 1
        kind, kw = cue_calls[0]
        assert kind == "decision"
        assert kw["filed_by"] == "system:memory-supersession"
        assert "retired" in kw["why"]
        # HONEST card text: approve is a promise the organ keeps LATER —
        # never worded as an action that already happened
        assert "approve = supersede the older row" in kw["why"]
        assert "once the auto-apply gate arms" in kw["why"]
        assert "Nothing changes until the grant lands." in kw["why"]
        d = _decisions(spath)[0]
        assert d["decision"] == "cue-card" and d["need_id"] == "NEED-feedbeef"

    def test_cue_card_files_during_soak_too(self, tmp_path):
        live = [_live(1, "the office is in odense now"),
                _live(2, "the office is no longer in odense")]
        prop = _prop("sup-cue00002", 1, 2, reason="contradiction-cue",
                     cues=["no longer"])
        rec = Recorder()
        s, *_ = _run(tmp_path, [prop], live, need_fn=rec)
        assert s["cue_cards"] == 1 and len(rec.calls) == 1

    def test_stale_cue_pair_refuses_instead_of_carding(self, tmp_path):
        # rows provably gone from the store → no Captain card about ghosts
        prop = _prop("sup-cue00005", 1, 2, reason="contradiction-cue",
                     cues=["retired"])
        rec = Recorder()
        s, _, spath, _ = _run(tmp_path, [prop], [], need_fn=rec,
                              fetch=lambda ids: [])
        assert s["cue_cards"] == 0 and rec.calls == []
        assert _decisions(spath)[0]["decision"] == "refused-gone"


class TestUndo:
    def _applied_line(self):
        return json.dumps({"ts": _iso(NOW), "mode": "armed",
                           "decision": "applied",
                           "proposal_id": "sup-abcd0001",
                           "old_id": "1", "new_id": "2",
                           "jaccard": 0.75, "texts_hash": "x"})

    def test_undo_reverses_and_blocks_arming(self, tmp_path):
        spath = tmp_path / "soak.jsonl"
        _write_jsonl(spath, ARMED_SEED)
        conn = FakeConn({1: 2})         # pointer set by an earlier apply
        res = msa.run_undo(self._applied_line(), soak_path=spath,
                           conn_factory=lambda: conn, now=NOW)
        assert res["undone"] is True
        assert conn.calls == [(msa._UNDO_SQL, (1, 2))]
        assert conn.live[1] is None     # pointer re-nulled
        entries = msa.read_jsonl(spath)
        assert entries[-1]["decision"] == "reversal"
        # the reversal re-blocks arming even far past the 14-day window
        assert msa.gate_state(entries, "soak", now=NOW) == "soak"

    def test_undo_refuses_non_applied_line(self, tmp_path):
        spath = tmp_path / "soak.jsonl"
        line = json.dumps({"decision": "would_apply",
                           "old_id": "1", "new_id": "2"})
        boom = Boom()
        res = msa.run_undo(line, soak_path=spath, conn_factory=boom, now=NOW)
        assert res["undone"] is False and "error" in res
        assert boom.called is False
        assert not spath.exists()       # no reversal recorded

    def test_undo_refuses_garbage(self, tmp_path):
        res = msa.run_undo("{not json", soak_path=tmp_path / "s.jsonl",
                           conn_factory=Boom(), now=NOW)
        assert res["undone"] is False and "error" in res

    def test_undo_guard_misses_changed_pointer_still_latches(self, tmp_path):
        # pointer no longer what this organ set → guarded 0-row no-op; the
        # ATTEMPT is still recorded (undone: false) and still latches the
        # gate — a Captain distrusting an apply is the precision signal the
        # soak exists to catch, whether or not the pointer survived
        spath = tmp_path / "soak.jsonl"
        conn = FakeConn({1: 777})
        res = msa.run_undo(self._applied_line(), soak_path=spath,
                           conn_factory=lambda: conn, now=NOW)
        assert res["undone"] is False
        assert conn.live[1] == 777      # untouched
        entries = msa.read_jsonl(spath)
        assert entries[-1]["decision"] == "reversal"
        assert entries[-1]["undone"] is False
        # even far past the 14-day window the failed attempt re-blocks
        assert msa.gate_state(ARMED_SEED + entries, "soak", now=NOW) == "soak"


class TestIdempotency:
    def test_rerun_appends_no_new_decisions_or_stamps(self, tmp_path):
        old, new = _toks(3, 4)
        live = [_live(1, old), _live(2, new)]
        props = [_prop("sup-abcd0001", 1, 2)]
        s1, ppath, spath, _ = _run(tmp_path, props, live)
        n_dec = len(_decisions(spath))
        n_lines = len(ppath.read_text().splitlines())
        assert s1["consumed"] == 1 and n_dec == 1
        s2 = msa.run_apply_pass(proposals_path=ppath, soak_path=spath,
                                config_path=tmp_path / "nope.yml",
                                needs_path=tmp_path / "needs-ledger.jsonl",
                                now=NOW,
                                live_rows=live, conn_factory=Boom(),
                                file_need_fn=Recorder(), posture="sovereign")
        assert s2["consumed"] == 0
        assert len(_decisions(spath)) == n_dec          # no dup decisions
        assert len(ppath.read_text().splitlines()) == n_lines  # no dup stamps
        runs = [r for r in msa.read_jsonl(spath) if r.get("decision") == "run"]
        assert len(runs) == 2                           # one marker per run

    def test_applied_pair_never_reapplied(self, tmp_path):
        old, new = _toks(3, 4)
        live = [_live(1, old), _live(2, new)]
        props = [_prop("sup-abcd0001", 1, 2)]
        conn = FakeConn({1: None})
        s1, ppath, spath, _ = _run(tmp_path, props, live,
                                   soak_rows=ARMED_SEED, conn=conn)
        assert s1["applied"] == 1 and len(conn.calls) == 1
        # second run: same stale live view, decision is terminal → no SQL
        s2 = msa.run_apply_pass(proposals_path=ppath, soak_path=spath,
                                config_path=tmp_path / "nope.yml",
                                needs_path=tmp_path / "needs-ledger.jsonl",
                                now=NOW,
                                live_rows=live, conn_factory=lambda: conn,
                                file_need_fn=Recorder(), posture="sovereign")
        assert s2["applied"] == 0
        assert len(conn.calls) == 1                     # still exactly one


class TestConsumption:
    def test_per_row_stamps_preserve_detector_dedup(self, tmp_path):
        old, new = _toks(3, 4)
        live = [_live(1, old), _live(2, new), _live(3, "unrelated colors"),
                _live(4, "boat harbor pier")]
        props = [_prop("sup-abcd0001", 1, 2),
                 _prop("sup-abcd0002", 3, 4),
                 _prop("sup-cue00003", 1, 2, reason="contradiction-cue",
                       cues=["never"])]
        s, ppath, spath, _ = _run(tmp_path, props, live)
        assert s["pending"] == 3 and s["consumed"] == 3
        lines = ppath.read_text().splitlines()
        assert len(lines) == 6          # 3 originals + 3 stamps, no rewrite
        compacted = msa.compact_proposals(msa.read_jsonl(ppath))
        assert all(p["status"] == "consumed" for p in compacted.values())
        # the detector's skip-known dedup still sees every proposal id
        assert mc.known_ids(ppath) == {"sup-abcd0001", "sup-abcd0002",
                                       "sup-cue00003"}
        s2 = msa.run_apply_pass(proposals_path=ppath, soak_path=spath,
                                config_path=tmp_path / "nope.yml",
                                needs_path=tmp_path / "needs-ledger.jsonl",
                                now=NOW,
                                live_rows=live, conn_factory=Boom(),
                                file_need_fn=Recorder(), posture="sovereign")
        assert s2["pending"] == 0 and s2["consumed"] == 0

    def test_unmeasurable_store_consumes_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mc, "load_live_rows", lambda: None)
        props = [_prop("sup-abcd0001", 1, 2)]
        s, ppath, spath, rec = _run(tmp_path, props, None)
        assert s["measurable"] is False and s["consumed"] == 0
        assert len(ppath.read_text().splitlines()) == 1   # no stamps
        assert not spath.exists()       # no ledger writes, no clock start
        assert rec.calls == []

    def test_dry_run_writes_nothing(self, tmp_path):
        old, new = _toks(3, 4)
        live = [_live(1, old), _live(2, new), _live(5, "x y z aaa"),
                _live(6, "x y z aaa never")]
        props = [_prop("sup-abcd0001", 1, 2),
                 _prop("sup-cue00004", 5, 6, reason="contradiction-cue",
                       cues=["never"])]
        conn = FakeConn({1: None})
        rec = Recorder()
        s, ppath, spath, _ = _run(tmp_path, props, live,
                                  soak_rows=ARMED_SEED, conn=conn,
                                  need_fn=rec, dry_run=True)
        assert s["dry_run"] is True
        assert s["would_apply"] == 1 and s["cue_cards"] == 1
        assert s["applied"] == 0 and s["consumed"] == 0
        assert conn.calls == [] and rec.calls == []
        assert len(ppath.read_text().splitlines()) == 2   # untouched
        assert msa.read_jsonl(spath) == [r for r in ARMED_SEED]


class TestLedgerHygiene:
    def test_soak_entries_carry_hash_not_text(self, tmp_path):
        old, new = _toks(3, 4)
        live = [_live(1, old), _live(2, new)]
        s, _, spath, _ = _run(tmp_path, [_prop("sup-abcd0001", 1, 2)], live)
        d = _decisions(spath)[0]
        assert re.fullmatch(r"[0-9a-f]{16}", d["texts_hash"])
        assert "content" not in d and "snippet" not in d
        assert "tok01" not in json.dumps(d)

    def test_soak_ledger_is_gitignored(self):
        gi = (_REPO / ".gitignore").read_text()
        assert "shared/interfaces/memory-supersession-soak.jsonl" in gi


class TestWriteSurface:
    def test_sql_constants_are_guarded_and_parameterized(self):
        assert msa._APPLY_SQL.count("%s") == 2
        assert "superseded_by IS NULL" in msa._APPLY_SQL
        assert msa._UNDO_SQL.count("%s") == 2
        assert "superseded_by = %s" in msa._UNDO_SQL
        for sql in (msa._APPLY_SQL, msa._UNDO_SQL):
            assert sql.startswith("UPDATE cabinet_memory SET superseded_by")
            assert ";" not in sql

    def test_probe_sql_is_readonly_parameterized_and_windowless(self):
        sql = msa._ROWS_BY_ID_SQL
        assert sql.strip().upper().startswith("SELECT")
        assert sql.count("%s") == 1 and "ANY(%s)" in sql
        assert "superseded_by" in sql
        for verb in ("UPDATE", "DELETE", "INSERT", "DROP", "ALTER", ";"):
            assert verb not in sql.upper()
        # windowless BY DESIGN: the probe exists to tell "aged out of the
        # detector's 90-day window" apart from "superseded"
        assert "interval" not in sql.lower() and "NOW()" not in sql

    def test_fetch_rows_by_id_binds_validated_ids(self):
        seen = {}

        class ProbeCursor:
            def execute(self, sql, params):
                seen["sql"], seen["params"] = sql, params

            def fetchall(self):
                return [(7, "captain_decision", "cos", "text a",
                         "2026-07-01T10:00:00Z", None),
                        (9, "captain_decision", "cos", "text b",
                         "2026-07-02T10:00:00Z", 12)]

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        class ProbeConn:
            def cursor(self):
                return ProbeCursor()

            def close(self):
                seen["closed"] = True

        rows = msa.fetch_rows_by_id([9, 7, 9], conn_factory=ProbeConn)
        assert seen["sql"] == msa._ROWS_BY_ID_SQL
        assert seen["params"] == ([7, 9],)      # deduped, sorted, ints
        assert seen["closed"] is True
        by_id = {r["id"]: r for r in rows}
        assert by_id["7"]["superseded_by"] is None
        assert by_id["9"]["superseded_by"] == "12"
        # unreachable store is None (UNKNOWN), never an empty "all gone"
        assert msa.fetch_rows_by_id([1], conn_factory=Boom()) is None
        # ids that fail int() poison the whole probe to UNKNOWN
        assert msa.fetch_rows_by_id(["1; DROP x"],
                                    conn_factory=ProbeConn) is None

    def test_module_is_structurally_incapable_of_row_removal(self):
        src = (_REPO / "cabinet" / "scripts" /
               "memory-supersede-apply.py").read_text()
        # destructive verbs strictly absent anywhere in the module source
        for verb in ("DELETE", "TRUNCATE", "DROP"):
            assert not re.search(rf"(?i)\b{verb}\b", src), \
                f"forbidden SQL verb {verb} in the apply organ"
        # SQL-shaped mutation forms absent (sys.path.insert is Python)
        for form in (r"INSERT\s+INTO", r"ALTER\s+TABLE"):
            assert not re.search(rf"(?i)\b{form}\b", src), \
                f"forbidden SQL form {form} in the apply organ"
        # exactly the two write statements name the table
        assert src.count("UPDATE cabinet_memory") == 2

    def test_apply_and_undo_bind_ids_as_tuples(self):
        conn = FakeConn({5: None})
        assert msa.apply_pair(conn, 5, 6) is True
        assert conn.calls == [(msa._APPLY_SQL, (6, 5))]
        assert msa.undo_pair(conn, 5, 6) is True
        assert conn.calls[-1] == (msa._UNDO_SQL, (5, 6))


class TestReport:
    def test_report_counts_and_soak_day(self, tmp_path):
        spath = tmp_path / "soak.jsonl"
        base = NOW - timedelta(days=10)
        _write_jsonl(spath, [
            {"ts": _iso(base), "decision": "run", "mode": "soak"},
            {"ts": _iso(base), "decision": "would_apply",
             "proposal_id": "sup-a", "old_id": "1", "new_id": "2"},
            {"ts": _iso(base), "decision": "would_apply",
             "proposal_id": "sup-b", "old_id": "3", "new_id": "4"},
            {"ts": _iso(NOW - timedelta(days=1)), "decision": "applied",
             "proposal_id": "sup-b", "old_id": "3", "new_id": "4"},
            {"ts": _iso(NOW - timedelta(days=1)), "decision": "reversal",
             "proposal_id": "sup-b", "old_id": "3", "new_id": "4",
             "undone": True},
            {"ts": _iso(base), "decision": "cue-card",
             "proposal_id": "sup-c", "old_id": "5", "new_id": "6"},
            {"ts": _iso(base), "decision": "refused-jaccard",
             "proposal_id": "sup-d", "old_id": "7", "new_id": "8"},
        ])
        ppath = tmp_path / "proposals.jsonl"
        _write_jsonl(ppath, [
            _prop("sup-a", 1, 2),
            {"proposal_id": "sup-a", "status": "consumed"},
            _prop("sup-e", 9, 10),
        ])
        rep = msa.build_report(proposals_path=ppath, soak_path=spath,
                               config_path=tmp_path / "nope.yml", now=NOW)
        assert rep["days_into_soak"] == 10.0
        assert rep["proposed"] == 2 and rep["applied"] == 1
        assert rep["reverted"] == 1 and rep["cue_cards"] == 1
        assert rep["refused"] == 1
        assert rep["proposals_total"] == 2
        assert rep["proposals_consumed"] == 1
        assert rep["proposals_pending"] == 1
        assert rep["state"] == "soak"   # the reversal blocks arming
        text = msa.render_report(rep)
        assert "memory-supersession soak report" in text
        assert "reverted=1" in text and "10.0" in text


class TestLoadModeFailClosed:
    def test_unreadable_existing_hold_config_stays_hold(self, tmp_path):
        # a Captain-set hold whose file turns unreadable must NEVER flip to
        # the arming default — PermissionError is OSError but not missing
        if os.geteuid() == 0:
            pytest.skip("root reads through file modes")
        p = tmp_path / "memory-supersession.yml"
        p.write_text("auto_apply: hold\n")
        p.chmod(0)
        try:
            assert msa.load_mode(p) == "hold"
        finally:
            p.chmod(0o644)

    def test_unreadable_soak_config_never_arms_either(self, tmp_path):
        # direction pin: ANY unreadable existing file is hold, even one
        # that contained soak — a broken read must never arm
        if os.geteuid() == 0:
            pytest.skip("root reads through file modes")
        p = tmp_path / "memory-supersession.yml"
        p.write_text("auto_apply: soak\n")
        p.chmod(0)
        try:
            assert msa.load_mode(p) == "hold"
        finally:
            p.chmod(0o644)

    def test_directory_in_place_of_config_is_hold(self, tmp_path):
        assert msa.load_mode(tmp_path) == "hold"


class TestWindowlessProbe:
    """Absence from the detector's 90-day live view must NOT be terminal:
    without the by-id probe, every pair whose old row aged past the window
    was refused forever while both rows kept serving recall — the exact
    condition this lane was chartered to end."""

    def _aged(self):
        old, new = _toks(3, 4)
        rows = [{**_live(1, old, ts="2026-03-01T10:00:00Z"),
                 "superseded_by": None},
                {**_live(2, new, ts="2026-03-02T10:00:00Z"),
                 "superseded_by": None}]
        return rows, [_prop("sup-aged0001", 1, 2)]

    def test_aged_out_live_pair_still_applies(self, tmp_path):
        probe_rows, props = self._aged()
        conn = FakeConn({1: None})
        s, _, spath, _ = _run(tmp_path, props, [], soak_rows=ARMED_SEED,
                              conn=conn, fetch=lambda ids: probe_rows)
        assert s["state"] == "armed"
        assert s["applied"] == 1 and s["refused"] == 0
        assert conn.calls == [(msa._APPLY_SQL, (2, 1))]
        assert _decisions(spath)[0]["decision"] == "applied"

    def test_probe_unavailable_stays_open_never_terminal(self, tmp_path):
        probe_rows, props = self._aged()
        s1, ppath, spath, _ = _run(tmp_path, props, [], soak_rows=ARMED_SEED,
                                   conn=FakeConn(), fetch=lambda ids: None)
        assert s1["blocked"] == 1 and s1["refused"] == 0
        d = _decisions(spath)[0]
        assert d["decision"] == "blocked-db"
        assert d["note"] == "liveness probe unavailable"
        # probe still dark next run: stays open, NO ledger spam
        s2 = msa.run_apply_pass(proposals_path=ppath, soak_path=spath,
                                config_path=tmp_path / "nope.yml",
                                needs_path=tmp_path / "needs-ledger.jsonl",
                                now=NOW, live_rows=[], conn_factory=Boom(),
                                fetch_rows_fn=lambda ids: None,
                                file_need_fn=Recorder(), posture="sovereign")
        assert s2["blocked"] == 1
        assert len(_decisions(spath)) == 1
        # probe comes back, rows still live: the pair resolves and applies
        conn = FakeConn({1: None})
        s3 = msa.run_apply_pass(proposals_path=ppath, soak_path=spath,
                                config_path=tmp_path / "nope.yml",
                                needs_path=tmp_path / "needs-ledger.jsonl",
                                now=NOW, live_rows=[],
                                conn_factory=lambda: conn,
                                fetch_rows_fn=lambda ids: probe_rows,
                                file_need_fn=Recorder(), posture="sovereign")
        assert s3["applied"] == 1
        assert conn.calls == [(msa._APPLY_SQL, (2, 1))]


class TestReciprocalPairs:
    def test_same_run_reciprocal_equal_ts_applies_at_most_one(self, tmp_path):
        old, new = _toks(3, 4)
        ts = "2026-07-01T10:00:00Z"    # EQUAL timestamps — order check
        live = [_live(1, old, ts=ts), _live(2, new, ts=ts)]   # passes both ways
        props = [_prop("sup-recip0a1", 1, 2), _prop("sup-recip0b2", 2, 1)]
        conn = FakeConn({1: None, 2: None})
        s, ppath, spath, _ = _run(tmp_path, props, live,
                                  soak_rows=ARMED_SEED, conn=conn)
        # WITHOUT the touched-id defer both sides apply against the stale
        # in-run view and BOTH rows leave recall — the memory loss this
        # organ exists to prevent
        assert s["applied"] == 1 and s["would_apply"] == 1
        assert len(conn.calls) == 1
        assert conn.live == {1: 2, 2: None}      # exactly one side applied
        by_pid = {d["proposal_id"]: d for d in _decisions(spath)}
        assert by_pid["sup-recip0a1"]["decision"] == "applied"
        deferred = by_pid["sup-recip0b2"]
        assert deferred["decision"] == "would_apply"
        assert deferred["note"] == "deferred-touched-id"
        # next run, fresh liveness: row 1 is superseded now → the deferred
        # reciprocal closes terminally instead of flip-flopping
        s2 = msa.run_apply_pass(
            proposals_path=ppath, soak_path=spath,
            config_path=tmp_path / "nope.yml",
            needs_path=tmp_path / "needs-ledger.jsonl", now=NOW,
            live_rows=[_live(2, new, ts=ts)], conn_factory=lambda: conn,
            fetch_rows_fn=lambda ids: [{**_live(1, old, ts=ts),
                                        "superseded_by": "2"}],
            file_need_fn=Recorder(), posture="sovereign")
        assert s2["applied"] == 0 and s2["refused"] == 1
        assert len(conn.calls) == 1              # no second store write
        latest = msa.compact_soak(msa.read_jsonl(spath))
        assert latest["sup-recip0b2"]["decision"] == "refused-superseded"


class TestBlockedDbDegrade:
    def test_armed_writer_unavailable_is_loud_open_and_recovers(
            self, tmp_path):
        old, new = _toks(3, 4)
        live = [_live(1, old), _live(2, new)]
        props = [_prop("sup-degrade01", 1, 2)]
        failing = Boom()
        s1, ppath, spath, _ = _run(tmp_path, props, live,
                                   soak_rows=ARMED_SEED,
                                   conn_factory=failing)
        assert failing.called is True            # the armed run truly tried
        assert s1["state"] == "armed"
        assert s1["blocked"] == 1 and s1["applied"] == 0
        d = _decisions(spath)[0]
        assert d["decision"] == "blocked-db"
        assert d["note"] == "store writer unavailable"
        # still failing next run: stays open, retries, NO duplicate rows
        failing2 = Boom()
        s2 = msa.run_apply_pass(proposals_path=ppath, soak_path=spath,
                                config_path=tmp_path / "nope.yml",
                                needs_path=tmp_path / "needs-ledger.jsonl",
                                now=NOW, live_rows=live,
                                conn_factory=failing2,
                                file_need_fn=Recorder(), posture="sovereign")
        assert failing2.called is True and s2["blocked"] == 1
        assert len(_decisions(spath)) == 1       # no ledger spam
        # driver lands: the SAME pair resolves and applies
        conn = FakeConn({1: None})
        s3 = msa.run_apply_pass(proposals_path=ppath, soak_path=spath,
                                config_path=tmp_path / "nope.yml",
                                needs_path=tmp_path / "needs-ledger.jsonl",
                                now=NOW, live_rows=live,
                                conn_factory=lambda: conn,
                                file_need_fn=Recorder(), posture="sovereign")
        assert s3["applied"] == 1
        assert conn.calls == [(msa._APPLY_SQL, (2, 1))]
        latest = msa.compact_soak(msa.read_jsonl(spath))
        assert latest["sup-degrade01"]["decision"] == "applied"


class TestApplyCap:
    def test_apply_cap_bounds_blast_radius(self, tmp_path):
        n = msa.MAX_APPLIES_PER_RUN + 2
        old, new = _toks(3, 4)
        live, props, store = [], [], {}
        for i in range(n):
            oid, nid = 1000 + 2 * i, 1001 + 2 * i
            live += [_live(oid, old), _live(nid, new)]
            props.append(_prop(f"sup-cap{i:05d}", oid, nid))
            store[oid] = None
        conn = FakeConn(store)
        s, _, spath, _ = _run(tmp_path, props, live, soak_rows=ARMED_SEED,
                              conn=conn)
        assert s["applied"] == msa.MAX_APPLIES_PER_RUN
        assert s["would_apply"] == 2             # the overflow stays OPEN
        assert len(conn.calls) == msa.MAX_APPLIES_PER_RUN
        capped = [d for d in _decisions(spath)
                  if d.get("note") == "deferred-apply-cap"]
        assert len(capped) == 2
        assert all(d["decision"] == "would_apply" for d in capped)


class TestResolveReversals:
    REV = {"ts": _iso(NOW - timedelta(days=2)), "decision": "reversal",
           "proposal_id": "sup-old00001", "old_id": "7", "new_id": "8",
           "undone": True}

    def test_ruling_clears_latch_and_rearms(self, tmp_path):
        spath = tmp_path / "soak.jsonl"
        _write_jsonl(spath, ARMED_SEED + [self.REV])
        assert msa.gate_state(msa.read_jsonl(spath), "soak",
                              now=NOW) == "soak"
        res = msa.run_resolve_reversals(
            "precision reviewed, the apply was right", soak_path=spath,
            now=NOW)
        assert res == {"resolved": True, "reversals_cleared": 1}
        entries = msa.read_jsonl(spath)
        assert entries[-1]["decision"] == "reversal-resolved"
        assert entries[-1]["resolved_by"] == "captain"
        assert msa.gate_state(entries, "soak", now=NOW) == "armed"
        # a LATER reversal re-blocks — a ruling is not a standing waiver
        later = {**self.REV, "ts": _iso(NOW - timedelta(hours=1))}
        assert msa.gate_state(entries + [later], "soak", now=NOW) == "soak"

    def test_empty_note_is_not_a_ruling(self, tmp_path):
        spath = tmp_path / "soak.jsonl"
        _write_jsonl(spath, ARMED_SEED + [self.REV])
        before = spath.read_text()
        res = msa.run_resolve_reversals("   ", soak_path=spath, now=NOW)
        assert res["resolved"] is False
        assert spath.read_text() == before       # nothing appended

    def test_nothing_to_resolve_refuses(self, tmp_path):
        spath = tmp_path / "soak.jsonl"
        _write_jsonl(spath, ARMED_SEED)
        res = msa.run_resolve_reversals("why", soak_path=spath, now=NOW)
        assert res["resolved"] is False and res["reversals_cleared"] == 0
        assert len(msa.read_jsonl(spath)) == len(ARMED_SEED)

    def test_soak_stats_counts_unresolved_vs_raw(self):
        entries = ARMED_SEED + [
            self.REV,
            {"ts": _iso(NOW - timedelta(days=1)),
             "decision": "reversal-resolved", "note": "settled"},
            {**self.REV, "ts": _iso(NOW - timedelta(hours=2))}]
        st = msa.soak_stats(entries, now=NOW)
        assert st["reversals"] == 1              # one AFTER the marker
        assert st["counts"]["reversal"] == 2     # raw total preserved


class TestHalfSoakCard:
    def _seed(self, days):
        return [{"ts": _iso(NOW - timedelta(days=days)), "decision": "run",
                 "mode": "soak"}]

    def _halfway_calls(self, rec):
        return [c for c in rec.calls
                if c[1]["action_type"] == "memory-supersede:soak-halfway"]

    def test_files_once_at_day_seven_plus(self, tmp_path):
        s, ppath, spath, rec = _run(tmp_path, [], [], soak_rows=self._seed(8))
        calls = self._halfway_calls(rec)
        assert len(calls) == 1
        assert "day 8/14" in calls[0][1]["why"]
        assert "auto_apply: hold" in calls[0][1]["why"]
        markers = [r for r in msa.read_jsonl(spath)
                   if r.get("decision") == "soak-halfway-card"]
        assert len(markers) == 1 and markers[0]["need_id"] == "NEED-feedbeef"
        assert s["halfway_card"] == "NEED-feedbeef"
        # marker present → never re-files
        rec2 = Recorder()
        msa.run_apply_pass(proposals_path=ppath, soak_path=spath,
                           config_path=tmp_path / "nope.yml",
                           needs_path=tmp_path / "needs-ledger.jsonl",
                           now=NOW, live_rows=[], conn_factory=Boom(),
                           file_need_fn=rec2, posture="sovereign")
        assert self._halfway_calls(rec2) == []

    def test_not_before_day_seven(self, tmp_path):
        s, _, _, rec = _run(tmp_path, [], [], soak_rows=self._seed(3))
        assert self._halfway_calls(rec) == []
        assert s["halfway_card"] is None

    def test_guardian_dark_retries_next_run(self, tmp_path):
        s1, ppath, spath, _ = _run(tmp_path, [], [], soak_rows=self._seed(8),
                                   need_fn=lambda kind, **kw: None)
        assert s1["halfway_card"] is None
        assert all(r.get("decision") != "soak-halfway-card"
                   for r in msa.read_jsonl(spath))   # no marker → retry
        rec = Recorder()
        s2 = msa.run_apply_pass(proposals_path=ppath, soak_path=spath,
                                config_path=tmp_path / "nope.yml",
                                needs_path=tmp_path / "needs-ledger.jsonl",
                                now=NOW, live_rows=[], conn_factory=Boom(),
                                file_need_fn=rec, posture="sovereign")
        assert s2["halfway_card"] == "NEED-feedbeef"
        assert len(self._halfway_calls(rec)) == 1

    def test_hold_mode_files_no_card(self, tmp_path):
        s, _, _, rec = _run(tmp_path, [], [], soak_rows=self._seed(8),
                            config="auto_apply: hold\n")
        assert self._halfway_calls(rec) == [] and s["halfway_card"] is None


class TestCueRetry:
    def test_card_refiling_until_need_id_lands(self, tmp_path):
        live = [_live(1, "the office is in odense now"),
                _live(2, "the office is no longer in odense")]
        prop = _prop("sup-cue00006", 1, 2, reason="contradiction-cue",
                     cues=["no longer"])
        # guardian posture: file_need no-ops → no need id this run
        s1, ppath, spath, _ = _run(tmp_path, [prop], live,
                                   need_fn=lambda kind, **kw: None)
        assert s1["cue_cards"] == 1
        d1 = msa.compact_soak(msa.read_jsonl(spath))["sup-cue00006"]
        assert d1["decision"] == "cue-card" and "need_id" not in d1
        # run 2: the card re-files and finally gets its id
        rec = Recorder()
        msa.run_apply_pass(proposals_path=ppath, soak_path=spath,
                           config_path=tmp_path / "nope.yml",
                           needs_path=tmp_path / "needs-ledger.jsonl",
                           now=NOW, live_rows=live, conn_factory=Boom(),
                           file_need_fn=rec, posture="sovereign")
        assert len(rec.calls) == 1
        d2 = msa.compact_soak(msa.read_jsonl(spath))["sup-cue00006"]
        assert d2["need_id"] == "NEED-feedbeef"
        # run 3: id recorded → closed; no re-file, no new decision rows
        rec3 = Recorder()
        msa.run_apply_pass(proposals_path=ppath, soak_path=spath,
                           config_path=tmp_path / "nope.yml",
                           needs_path=tmp_path / "needs-ledger.jsonl",
                           now=NOW, live_rows=live, conn_factory=Boom(),
                           file_need_fn=rec3, posture="sovereign")
        assert rec3.calls == []
        decs = [r for r in msa.read_jsonl(spath)
                if r.get("proposal_id") == "sup-cue00006"]
        assert len(decs) == 2                    # cue-card, then +need_id


class TestGrantedExecution:
    """The cue card's approve is a promise THIS organ keeps: a
    Captain-approved need routes the pair through the guarded apply path
    — nothing else in the org consumes memory-supersede approvals
    (grant-apply.sh refuses kind!=standing_grant). The PRODUCTION signal
    is ``approved_pending_apply``: that is what the binder ``grant`` verb
    writes for every kind (binder_wire._NEED_VERB_STATUS) — ``granted``
    never arrives from outside; it is the organ's own post-apply
    receipt."""

    CUE_PID = "sup-cue00001"

    def _fixture(self):
        # low-similarity contradiction pair: Jaccard far under 0.75, so
        # ONLY the Captain approval can make it appliable
        live = [_live(1, "the todos board is the authoritative store"),
                _live(2, "the todos board is retired use the vault now")]
        prop = _prop(self.CUE_PID, 1, 2, reason="contradiction-cue",
                     cues=["retired"])
        return live, prop

    def _needs_rows(self, status="approved_pending_apply"):
        # LWW per id: open first, then the binder's status flip — the
        # binder grant verb writes approved_pending_apply, NEVER granted
        return [{"id": "NEED-cafe0001", "kind": "decision",
                 "action_type": f"memory-supersede:{self.CUE_PID}",
                 "status": "open"},
                {"id": "NEED-cafe0001", "kind": "decision",
                 "action_type": f"memory-supersede:{self.CUE_PID}",
                 "status": status}]

    def test_approved_cue_pair_applies_when_armed(self, tmp_path):
        live, prop = self._fixture()
        conn = FakeConn({1: None})
        s, _, spath, rec = _run(tmp_path, [prop], live,
                                soak_rows=ARMED_SEED, conn=conn,
                                needs_rows=self._needs_rows())
        assert s["applied"] == 1 and s["cue_cards"] == 0
        assert conn.calls == [(msa._APPLY_SQL, (2, 1))]
        d = msa.compact_soak(msa.read_jsonl(spath))[self.CUE_PID]
        assert d["decision"] == "applied"
        assert d["via"] == "captain-grant"
        assert d["jaccard"] < mc.NEAR_DUP_JACCARD   # bar waived BY APPROVAL only
        # no fresh card for an approved pair
        assert [c for c in rec.calls
                if c[1]["action_type"].endswith(self.CUE_PID)] == []

    def test_binder_status_not_granted_is_the_signal(self, tmp_path):
        # THE P2-1 regression pin, both directions. (a) production shape:
        # binder grant → approved_pending_apply → the pair executes (the
        # old status=="granted" match made every approval a silent no-op
        # forever). (b) receipt shape: a bare "granted" row (only ever
        # written by the organ itself AFTER an apply) is NOT a trigger —
        # a hand-granted card re-executes nothing.
        live, prop = self._fixture()
        seed = self._carded_state(tmp_path, prop)
        conn = FakeConn({1: None})
        s, _, spath, _ = _run(tmp_path, None, live, soak_rows=seed,
                              conn=conn,
                              needs_rows=self._needs_rows("granted"))
        assert s["applied"] == 0 and conn.calls == []
        d = msa.compact_soak(msa.read_jsonl(spath))[self.CUE_PID]
        assert d["decision"] == "cue-card"           # unchanged, closed
        assert msa.load_granted_pids(
            tmp_path / "needs-ledger.jsonl") == {}
        _write_jsonl(tmp_path / "needs-ledger.jsonl", self._needs_rows())
        assert msa.load_granted_pids(
            tmp_path / "needs-ledger.jsonl") == {
                self.CUE_PID: "NEED-cafe0001"}

    def test_applied_approval_closes_need_with_granted_receipt(
            self, tmp_path):
        # the mark phase (mirror of grant-apply.sh): applied → the need is
        # closed as granted, the ledger entry carries the need id, and the
        # approved set stops growing
        live, prop = self._fixture()
        conn = FakeConn({1: None})
        marks = MarkRecorder()
        s, _, spath, _ = _run(tmp_path, [prop], live, soak_rows=ARMED_SEED,
                              conn=conn, needs_rows=self._needs_rows(),
                              mark_fn=marks)
        assert s["applied"] == 1
        assert [(c[0], c[1]) for c in marks.calls] == [
            ("NEED-cafe0001", "granted")]
        assert self.CUE_PID in marks.calls[0][2]     # reason names the pair
        d = msa.compact_soak(msa.read_jsonl(spath))[self.CUE_PID]
        assert d["decision"] == "applied"
        assert d["need_id"] == "NEED-cafe0001"

    def test_moot_approval_closes_need_as_superseded(self, tmp_path):
        # both rows provably gone from the store → terminal refusal; the
        # approved need must not stay approved forever — closed as moot
        _, prop = self._fixture()
        marks = MarkRecorder()
        s, _, spath, _ = _run(tmp_path, [prop], [], soak_rows=ARMED_SEED,
                              conn=FakeConn(), fetch=lambda ids: [],
                              needs_rows=self._needs_rows(), mark_fn=marks)
        assert s["refused"] == 1
        assert [(c[0], c[1]) for c in marks.calls] == [
            ("NEED-cafe0001", "superseded")]
        d = msa.compact_soak(msa.read_jsonl(spath))[self.CUE_PID]
        assert d["decision"] == "refused-gone"
        assert d["need_id"] == "NEED-cafe0001"

    def test_unexecuted_approval_keeps_the_need_open(self, tmp_path):
        # day-0 soak: the approval queues as would_apply — NO receipt yet
        # (the executor retries next run; closing early would orphan the
        # promise), and dry-run never marks either
        live, prop = self._fixture()
        marks = MarkRecorder()
        s, *_ = _run(tmp_path, [prop], live, conn_factory=Boom(),
                     needs_rows=self._needs_rows(), mark_fn=marks)
        assert s["would_apply"] == 1 and s["applied"] == 0
        assert marks.calls == []
        marks2 = MarkRecorder()
        s2, *_ = _run(tmp_path, None, live, soak_rows=ARMED_SEED,
                      conn=FakeConn({1: None}),
                      needs_rows=self._needs_rows(), mark_fn=marks2,
                      dry_run=True)
        assert s2["applied"] == 0 and marks2.calls == []

    def test_ungranted_twin_still_cards_never_applies(self, tmp_path):
        # negative control: the SAME pair without a grant → card, zero SQL
        live, prop = self._fixture()
        conn = FakeConn({1: None})
        s, *_ = _run(tmp_path, [prop], live, soak_rows=ARMED_SEED, conn=conn)
        assert s["applied"] == 0 and s["cue_cards"] == 1
        assert conn.calls == []

    def _carded_state(self, tmp_path, prop):
        seed = ARMED_SEED + [
            {"ts": _iso(NOW - timedelta(days=3)), "mode": "soak",
             "decision": "cue-card", "proposal_id": self.CUE_PID,
             "reason": "contradiction-cue", "old_id": "1", "new_id": "2",
             "cues": ["retired"], "need_id": "NEED-cafe0001"}]
        ppath = tmp_path / "proposals.jsonl"
        _write_jsonl(ppath, [prop, {"proposal_id": self.CUE_PID,
                                    "status": "consumed",
                                    "decision": "cue-card"}])
        return seed

    def test_grant_reopens_prior_card_and_applies(self, tmp_path):
        live, prop = self._fixture()
        seed = self._carded_state(tmp_path, prop)
        conn = FakeConn({1: None})
        s, _, spath, _ = _run(tmp_path, None, live, soak_rows=seed,
                              conn=conn, needs_rows=self._needs_rows())
        assert s["applied"] == 1 and s["consumed"] == 0   # reopened, not re-consumed
        assert conn.calls == [(msa._APPLY_SQL, (2, 1))]
        d = msa.compact_soak(msa.read_jsonl(spath))[self.CUE_PID]
        assert d["decision"] == "applied" and d["via"] == "captain-grant"

    def test_denied_card_never_reopens(self, tmp_path):
        # veto = keep both: a denied need must not reopen the pair. A PAIR
        # veto is scoped to its pair — it must NOT hold the whole gate
        # (only the soak-halfway card's veto does that)
        live, prop = self._fixture()
        seed = self._carded_state(tmp_path, prop)
        conn = FakeConn({1: None})
        s, _, spath, _ = _run(tmp_path, None, live, soak_rows=seed,
                              conn=conn, needs_rows=self._needs_rows("denied"))
        assert s["applied"] == 0 and s["cue_cards"] == 0
        assert s["state"] == "armed"             # pair veto ≠ gate veto
        assert conn.calls == []
        d = msa.compact_soak(msa.read_jsonl(spath))[self.CUE_PID]
        assert d["decision"] == "cue-card"       # unchanged, closed

    def test_grant_still_respects_soak_gate(self, tmp_path):
        # day-0 soak: the grant queues as would_apply, applies once armed
        live, prop = self._fixture()
        boom = Boom()
        s, _, spath, _ = _run(tmp_path, [prop], live, conn_factory=boom,
                              needs_rows=self._needs_rows())
        assert s["state"] == "soak"
        assert s["would_apply"] == 1 and s["applied"] == 0
        assert boom.called is False
        d = msa.compact_soak(msa.read_jsonl(spath))[self.CUE_PID]
        assert d["decision"] == "would_apply"
        assert d["via"] == "captain-grant"

    def test_grant_still_respects_hold(self, tmp_path):
        live, prop = self._fixture()
        boom = Boom()
        s, *_ = _run(tmp_path, [prop], live, soak_rows=ARMED_SEED,
                     config="auto_apply: hold\n", conn_factory=boom,
                     needs_rows=self._needs_rows())
        assert s["state"] == "hold"
        assert s["applied"] == 0 and s["would_apply"] == 1
        assert boom.called is False


def _real_needs(tmp_path, monkeypatch):
    """The REAL framework.authority.needs module, fully sandboxed to a tmp
    cabinet root: filing enabled via CABINET_NEEDS_WIRED, CABINET_ROOT +
    the event-log dir pinned under tmp so nothing touches the repo's
    runtime ledgers."""
    root = tmp_path / "cabroot"
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    monkeypatch.setenv("CABINET_ROOT", str(root))
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    if str(_REPO) not in sys.path:
        sys.path.insert(0, str(_REPO))
    from framework.authority import needs
    return needs, root, needs.ledger_path(root)


class TestBinderFlowEndToEnd:
    """P2-1 pinned at PRODUCTION shape through the real needs API: the
    binder ``grant`` verb writes ``approved_pending_apply`` (see
    binder_wire._NEED_VERB_STATUS — never ``granted``; grant-apply.sh
    refuses kind!=standing_grant), THAT status triggers the executor, and
    the organ's post-apply ``granted`` receipt closes the need so
    load_granted_pids stops growing. Fails on the old status=="granted"
    match, where every real Captain approval was a silent no-op."""

    def test_full_approval_lifecycle_with_real_needs_api(
            self, tmp_path, monkeypatch):
        needs, root, npath = _real_needs(tmp_path, monkeypatch)
        live = [_live(1, "the todos board is the authoritative store"),
                _live(2, "the todos board is retired use the vault now")]
        prop = _prop("sup-cue00001", 1, 2, reason="contradiction-cue",
                     cues=["retired"])
        ppath = tmp_path / "proposals.jsonl"
        _write_jsonl(ppath, [prop])
        spath = tmp_path / "soak.jsonl"
        _write_jsonl(spath, ARMED_SEED)

        def real_file(kind, **kw):
            return needs.file_need(kind, root=root, **kw)

        def real_mark(nid, status, reason):
            return needs.mark(nid, status, by="system:memory-supersession",
                              reason=reason, root=root)

        common = dict(proposals_path=ppath, soak_path=spath,
                      config_path=tmp_path / "nope.yml", needs_path=npath,
                      live_rows=live, file_need_fn=real_file,
                      mark_need_fn=real_mark)
        # run 1: the card lands OPEN on the real ledger — no execution
        conn = FakeConn({1: None})
        s1 = msa.run_apply_pass(now=NOW, conn_factory=lambda: conn, **common, posture="sovereign")
        assert s1["cue_cards"] == 1 and s1["applied"] == 0
        nid = msa.compact_soak(msa.read_jsonl(spath))["sup-cue00001"][
            "need_id"]
        assert nid and nid.startswith("NEED-")
        assert msa.load_granted_pids(npath) == {}
        # the Captain taps grant: the binder verb's EXACT ledger effect
        row = needs.mark(nid, "approved_pending_apply", by="binder",
                         root=root)
        assert row is not None
        assert msa.load_granted_pids(npath) == {"sup-cue00001": nid}
        # run 2: the approval executes, then the receipt closes the need
        s2 = msa.run_apply_pass(now=NOW, conn_factory=lambda: conn, **common, posture="sovereign")
        assert s2["applied"] == 1 and conn.live[1] == 2
        final = [r for r in msa.read_jsonl(npath)
                 if r.get("id") == nid][-1]
        assert final["status"] == "granted"          # the receipt
        assert final["marked_by"] == "system:memory-supersession"
        assert msa.load_granted_pids(npath) == {}    # stops growing
        # run 3: closed pair + closed need — nothing re-executes/re-cards
        s3 = msa.run_apply_pass(now=NOW, conn_factory=Boom(), **common, posture="sovereign")
        assert s3["applied"] == 0 and s3["cue_cards"] == 0
        assert len(conn.calls) == 1                  # exactly one UPDATE ever


class TestHalfwayVetoBinds:
    """P2-2: the half-soak card's "veto = hold" is a BINDING promise. Full
    deny path through the real needs API: file the card → binder deny →
    the gate reads held-by-captain-veto, an armed apply refuses, a marker
    records it, the card is never re-filed — and the approve path (binder
    grant on the same card) still arms. Fails without the fix: the organ
    never read the need's status, so a Captain veto executed NOTHING."""

    def test_full_deny_path_holds_the_gate(self, tmp_path, monkeypatch):
        needs, root, npath = _real_needs(tmp_path, monkeypatch)
        spath = tmp_path / "soak.jsonl"
        _write_jsonl(spath, [{"ts": _iso(NOW - timedelta(days=8)),
                              "decision": "run", "mode": "soak"}])
        ppath = tmp_path / "proposals.jsonl"
        _write_jsonl(ppath, [])

        def real_file(kind, **kw):
            return needs.file_need(kind, root=root, **kw)

        common = dict(proposals_path=ppath, soak_path=spath,
                      config_path=tmp_path / "nope.yml", needs_path=npath)
        # day 8: the halfway card files on the REAL needs ledger
        s1 = msa.run_apply_pass(now=NOW, live_rows=[], conn_factory=Boom(),
                                file_need_fn=real_file, **common, posture="sovereign")
        nid = s1["halfway_card"]
        assert nid and nid.startswith("NEED-")
        assert msa.halfway_veto(npath) is None       # not vetoed yet
        # the Captain taps deny — the binder verb's exact ledger effect
        assert needs.mark(nid, "denied", by="binder", root=root) is not None
        assert msa.halfway_veto(npath) == nid
        # day 15 — 14d elapsed, zero reversals, config=soak: WOULD arm.
        # An eligible near-dup pair + a live store writer stand ready.
        old, new = _toks(3, 4)
        live = [_live(1, old), _live(2, new)]
        _write_jsonl(ppath, [_prop("sup-veto0001", 1, 2)])
        conn = FakeConn({1: None})
        later = NOW + timedelta(days=7)
        rec2 = Recorder()
        s2 = msa.run_apply_pass(now=later, live_rows=live,
                                conn_factory=lambda: conn,
                                file_need_fn=rec2, **common, posture="sovereign")
        assert s2["state"] == "held-by-captain-veto"
        assert s2["veto_need"] == nid
        assert s2["applied"] == 0 and s2["would_apply"] == 1
        assert conn.calls == []                      # arming impossible
        marks = [r for r in msa.read_jsonl(spath)
                 if r.get("decision") == "captain-veto-hold"]
        assert len(marks) == 1 and marks[0]["need_id"] == nid
        # while denied: never re-filed, marker never duplicated, still held
        s3 = msa.run_apply_pass(now=later + timedelta(days=7),
                                live_rows=live, conn_factory=lambda: conn,
                                file_need_fn=rec2, **common, posture="sovereign")
        assert s3["state"] == "held-by-captain-veto"
        assert s3["applied"] == 0 and conn.calls == []
        assert [c for c in rec2.calls
                if c[1]["action_type"] == msa._HALFWAY_ACTION] == []
        assert len([r for r in msa.read_jsonl(spath)
                    if r.get("decision") == "captain-veto-hold"]) == 1
        # the Captain re-rules the SAME card (binder grant): the hold
        # lifts with no ledger surgery and the soaked pair now applies
        assert needs.mark(nid, "approved_pending_apply", by="binder",
                          root=root) is not None
        assert msa.halfway_veto(npath) is None
        s4 = msa.run_apply_pass(now=later + timedelta(days=7),
                                live_rows=live, conn_factory=lambda: conn,
                                file_need_fn=rec2, **common, posture="sovereign")
        assert s4["state"] == "armed" and s4["applied"] == 1
        assert conn.calls == [(msa._APPLY_SQL, (2, 1))]

    def test_approve_path_still_arms(self, tmp_path, monkeypatch):
        # the positive one-tap: binder grant on the halfway card leaves
        # the gate on its normal clock — day 15 arms and applies
        needs, root, npath = _real_needs(tmp_path, monkeypatch)
        spath = tmp_path / "soak.jsonl"
        _write_jsonl(spath, [{"ts": _iso(NOW - timedelta(days=8)),
                              "decision": "run", "mode": "soak"}])
        ppath = tmp_path / "proposals.jsonl"
        _write_jsonl(ppath, [])
        s1 = msa.run_apply_pass(
            proposals_path=ppath, soak_path=spath,
            config_path=tmp_path / "nope.yml", needs_path=npath, now=NOW,
            live_rows=[], conn_factory=Boom(),
            file_need_fn=lambda kind, **kw: needs.file_need(
                kind, root=root, **kw), posture="sovereign")
        nid = s1["halfway_card"]
        assert needs.mark(nid, "approved_pending_apply", by="binder",
                          root=root) is not None
        assert msa.halfway_veto(npath) is None
        old, new = _toks(3, 4)
        live = [_live(1, old), _live(2, new)]
        _write_jsonl(ppath, [_prop("sup-appr0001", 1, 2)])
        conn = FakeConn({1: None})
        s2 = msa.run_apply_pass(
            proposals_path=ppath, soak_path=spath,
            config_path=tmp_path / "nope.yml", needs_path=npath,
            now=NOW + timedelta(days=7), live_rows=live,
            conn_factory=lambda: conn, file_need_fn=Recorder(), posture="sovereign")
        assert s2["state"] == "armed" and s2["applied"] == 1

    def test_gate_state_vetoed_outranks_everything(self):
        thirty = [{"ts": _iso(NOW - timedelta(days=30)), "decision": "run",
                   "mode": "soak"}]
        assert msa.gate_state(thirty, "soak", now=NOW) == "armed"
        assert msa.gate_state(thirty, "soak", now=NOW,
                              vetoed=True) == "held-by-captain-veto"
        assert msa.gate_state(thirty, "hold", now=NOW,
                              vetoed=True) == "held-by-captain-veto"
        assert msa.gate_state([], "soak", now=NOW,
                              vetoed=True) == "held-by-captain-veto"

    def test_pair_card_denial_is_not_a_gate_veto(self, tmp_path):
        npath = tmp_path / "needs.jsonl"
        _write_jsonl(npath, [{"id": "NEED-cafe0001", "kind": "decision",
                              "action_type": "memory-supersede:sup-cue00001",
                              "status": "denied"}])
        assert msa.halfway_veto(npath) is None

    def test_report_surfaces_the_veto(self, tmp_path):
        npath = tmp_path / "needs.jsonl"
        _write_jsonl(npath, [
            {"id": "NEED-beefcafe", "kind": "decision",
             "action_type": msa._HALFWAY_ACTION, "status": "open"},
            {"id": "NEED-beefcafe", "kind": "decision",
             "action_type": msa._HALFWAY_ACTION, "status": "denied"}])
        spath = tmp_path / "soak.jsonl"
        _write_jsonl(spath, ARMED_SEED)
        rep = msa.build_report(proposals_path=tmp_path / "p.jsonl",
                               soak_path=spath,
                               config_path=tmp_path / "nope.yml",
                               needs_path=npath, now=NOW)
        assert rep["state"] == "held-by-captain-veto"
        assert rep["veto_need"] == "NEED-beefcafe"
        assert "held-by-captain-veto" in msa.render_report(rep)
        assert "NEED-beefcafe" in msa.render_report(rep)


class TestLedgerSurgeryRecovery:
    def test_consumed_but_ledgerless_pair_reopens_from_stamps(self, tmp_path):
        old, new = _toks(3, 4)
        live = [_live(1, old), _live(2, new)]
        pid = "sup-abcd0001"
        ppath = tmp_path / "proposals.jsonl"
        _write_jsonl(ppath, [_prop(pid, 1, 2),
                             {"proposal_id": pid, "status": "consumed",
                              "consumed_at": _iso(NOW - timedelta(days=15)),
                              "decision": "would_apply"}])
        # the soak ledger LOST the pair's entry (hand surgery) — only the
        # run marker survives; the stamps must bring the pair back
        conn = FakeConn({1: None})
        s, _, spath, _ = _run(tmp_path, None, live, soak_rows=ARMED_SEED,
                              conn=conn)
        assert s["pending"] == 0 and s["consumed"] == 0
        assert s["applied"] == 1
        latest = msa.compact_soak(msa.read_jsonl(spath))
        assert latest[pid]["decision"] == "applied"


def _services():
    return yaml.safe_load(
        (_REPO / "cabinet" / "services.yml").read_text())["services"]


def test_detect_and_apply_are_separate_single_command_rows():
    """The launchd wrapper ``exec``s each row's command, so the apply organ
    MUST ride its own row — a ``&& apply`` chain on the detect row renders
    but never runs (the exact silent-dead-organ bug paid 2026-07-15)."""
    services = _services()
    det = [s for s in services if s.get("name") == "memory-contradictions"]
    app = [s for s in services if s.get("name") == "memory-supersede-apply"]
    assert len(det) == 1, "detect row lost — pass unscheduled"
    assert len(app) == 1, "apply row lost — proposals never consumed"
    det, app = det[0], app[0]
    assert det["label"] == "com.cabinet.memory-contradictions"
    assert app["label"] == "com.cabinet.memory-supersede-apply"
    assert "memory-contradictions.py" in det["command"]
    # the dead-chain regression: the apply organ must NOT be a tail on the
    # detect row's command
    assert "memory-supersede-apply.py" not in det["command"]
    assert "memory-supersede-apply.py" in app["command"]
    for row in (det, app):
        assert "&&" not in row["command"]
        assert row["schedule"]["calendar"] and not row.get("disabled")
    d_cal = det["schedule"]["calendar"][0]
    a_cal = app["schedule"]["calendar"][0]
    # SAME firing days (shape-agnostic: daily = no weekday key on either row,
    # per the 2026-07-16 Captain daily-cadence ruling; a weekday pin must match
    # on BOTH rows or apply consumes proposals the detect pass never wrote),
    # detect 05:30 strictly before apply 05:45 within each firing day.
    assert d_cal.get("weekday") == a_cal.get("weekday")
    assert d_cal["hour"] == a_cal["hour"]
    assert (d_cal["minute"], a_cal["minute"]) == (30, 45)
    assert "soak" in app["notes"]
    assert "2026-07-15 Captain ratification" in app["notes"]
    assert "captain-grant" in app["notes"] or "grant" in app["notes"]


def test_no_enabled_service_chains_past_the_exec_wrapper():
    """Fleet-wide pin: generate-plists wraps every row as
    ``... && REDIS_HOST=localhost exec {command}`` — bash ``exec`` REPLACES
    the shell at the first simple command, so everything after a ``&&``
    INSIDE {command} is dead code that still exits 0. If chaining is ever
    genuinely needed, nest it as one token: ``/bin/bash -c 'a && b'``."""
    offenders = []
    for svc in _services():
        if svc.get("disabled"):
            continue
        cmd = svc["command"]
        if "&&" in cmd and cmd.split()[0] not in (
                "/bin/bash", "bash", "/bin/sh", "sh"):
            offenders.append(svc["name"])
    assert offenders == [], \
        f"'&&' dies after the plist exec wrapper: {offenders}"


def test_rendered_plist_wrapper_execs_the_full_command():
    """Render-level pin through the REAL generate-plists.render(): the
    wrapper must end with ``exec <command>`` and nothing may trail the
    exec'd command — a ``&& second-prog`` tail here is exactly the
    dead-apply-organ bug."""
    gp = _load("generate_plists", "generate-plists.py")
    services = _services()
    root, home = Path("/repo"), Path("/home/x")
    for name in ("memory-contradictions", "memory-supersede-apply"):
        svc = next(s for s in services if s["name"] == name)
        pl = gp.render(svc, root, home)
        assert pl["ProgramArguments"][:2] == ["/bin/bash", "-lc"]
        wrapper = pl["ProgramArguments"][2]
        assert wrapper.endswith("exec " + svc["command"])
        assert "&&" not in wrapper.split(" exec ", 1)[1]


def test_exec_wrapper_kills_chained_tail_empirically():
    """The mechanism itself, proven: under the exact wrapper shape a
    ``&&``-chained second program NEVER runs (exec replaced the shell —
    exit stays 0, the failure is silent), while a ``bash -c`` nested chain
    runs both. If this fails, the wrapper semantics changed and the
    one-command-per-row rule needs re-deriving."""
    chained = ("cd /tmp && REDIS_HOST=localhost exec /bin/echo DETECT-RAN"
               " && /bin/echo APPLY-RAN")
    out = subprocess.run(["/bin/bash", "-lc", chained],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0
    assert "DETECT-RAN" in out.stdout
    assert "APPLY-RAN" not in out.stdout        # the silent dead tail
    nested = ("cd /tmp && REDIS_HOST=localhost exec /bin/bash -c "
              "'/bin/echo DETECT-RAN && /bin/echo APPLY-RAN'")
    out2 = subprocess.run(["/bin/bash", "-lc", nested],
                          capture_output=True, text=True, timeout=30)
    assert "DETECT-RAN" in out2.stdout and "APPLY-RAN" in out2.stdout


@requires_egg_manifest
def test_live_instance_config_is_egg_scrubbed():
    """R120: the tracked live instance config must be deleted by the egg
    manifest and its .example twin must ship — a new tracked
    instance/config file that skips the manifest turns the egg export RED
    (t_instance_verify: 'LIVE INSTANCE FILE SURVIVED THE PASS')."""
    manifest = _EGG_MANIFEST.read_text()
    assert "\ndelete instance/config/memory-supersession.yml\n" in manifest
    assert ("\nexpect-present instance/config/"
            "memory-supersession.yml.example\n") in manifest
    twin = _REPO / "instance" / "config" / "memory-supersession.yml.example"
    assert twin.exists()
    cfg = yaml.safe_load(twin.read_text())
    assert cfg["auto_apply"] == "soak"      # fresh-captain default = ratified


# --------------------------- autonomy-graded action seam (OUTER gate) -------
# Captain law 2026-07-17: even an ARMED soak only acts when the action seam
# (framework/authority/action_mode.py) answers an act mode for this organ's
# apply action. The seam may only TIGHTEN — a "go" never bypasses the
# soak/hold/veto law, and any narrower posture holds an armed gate. Postures
# here are always explicit (hermetic; the live instance ruling is never read).


class TestActionSeamOuterGate:
    def _armed_pair(self, tmp_path, posture):
        old, new = _toks(3, 4)
        live = [_live(1, old), _live(2, new)]
        conn = FakeConn({1: None})
        s, _, spath, _ = _run(tmp_path, [_prop("sup-5ea10001", 1, 2)], live,
                              soak_rows=ARMED_SEED, conn=conn,
                              posture=posture)
        return s, spath, conn

    def test_guardian_holds_an_armed_soak(self, tmp_path):
        # Yesterday's law would have applied here (day 15, zero reversals,
        # config soak). Under the seam, guardian = propose: recorded, never
        # executed — and the state string can satisfy no == "armed" check.
        s, spath, conn = self._armed_pair(tmp_path, "guardian")
        assert s["state"] == "held-by-action-seam"
        assert s["action_mode"] == "propose"
        assert s["applied"] == 0 and s["would_apply"] == 1
        assert conn.calls == []                  # store never touched
        by_pid = {d["proposal_id"]: d for d in _decisions(spath)}
        assert by_pid["sup-5ea10001"]["decision"] == "would_apply"

    def test_earn_up_holds_an_armed_soak(self, tmp_path):
        s, _, conn = self._armed_pair(tmp_path, "earn_up")
        assert s["state"] == "held-by-action-seam"
        assert s["applied"] == 0 and conn.calls == []

    def test_sovereign_armed_soak_still_applies(self, tmp_path):
        # The seam permits; the EXISTING law then decides — and does apply.
        s, _, conn = self._armed_pair(tmp_path, "sovereign")
        assert s["state"] == "armed" and s["action_mode"] == "go"
        assert s["applied"] == 1 and len(conn.calls) == 1

    def test_sovereign_plus_unarmed_soak_still_refuses(self, tmp_path):
        # THE tighten-only pin: a wide posture can never bypass the soak
        # clock. Day 0, sovereign — records would_apply, applies nothing.
        old, new = _toks(3, 4)
        live = [_live(1, old), _live(2, new)]
        conn = FakeConn({1: None})
        s, _, spath, _ = _run(tmp_path, [_prop("sup-5ea10002", 1, 2)], live,
                              conn=conn, posture="sovereign")
        assert s["state"] == "soak" and s["action_mode"] == "go"
        assert s["applied"] == 0 and s["would_apply"] == 1
        assert conn.calls == []
        by_pid = {d["proposal_id"]: d for d in _decisions(spath)}
        assert by_pid["sup-5ea10002"]["decision"] == "would_apply"

    def test_sovereign_plus_hold_config_still_holds(self, tmp_path):
        old, new = _toks(3, 4)
        live = [_live(1, old), _live(2, new)]
        conn = FakeConn({1: None})
        s, _, _, _ = _run(tmp_path, [_prop("sup-5ea10003", 1, 2)], live,
                          soak_rows=ARMED_SEED, config="auto_apply: hold\n",
                          conn=conn, posture="sovereign")
        assert s["state"] == "hold"
        assert s["applied"] == 0 and conn.calls == []

    def test_seam_hold_never_widens_and_only_narrows_armed(self):
        go = {"mode": "go", "captain_card": False}
        act = {"mode": "act_tell", "captain_card": False}
        ask = {"mode": "propose", "captain_card": False}
        # Captain veto / hold / soak pass through UNTOUCHED whatever the seam
        # says — the outer gate can only tighten, never lift.
        for state in ("held-by-captain-veto", "hold", "soak"):
            for disp in (go, act, ask, {}):
                assert msa.seam_hold(state, disp) == state
        # armed: act modes pass, anything else (or garbage) holds.
        assert msa.seam_hold("armed", go) == "armed"
        assert msa.seam_hold("armed", act) == "armed"
        assert msa.seam_hold("armed", ask) == "held-by-action-seam"
        assert msa.seam_hold("armed", {}) == "held-by-action-seam"
        assert msa.seam_hold("armed", {"mode": "GO"}) == "held-by-action-seam"

    def test_broken_seam_fails_closed_even_under_sovereign(
            self, tmp_path, monkeypatch):
        # An unimportable/raising seam must HOLD an armed gate, not crash
        # and not fall open — posture cannot rescue a broken law module.
        import types
        stub = types.ModuleType("framework.authority.action_mode")

        def _boom(*a, **k):
            raise RuntimeError("seam down")
        stub.action_decision = _boom
        stub.MODES = frozenset({"propose", "act_tell", "go"})
        monkeypatch.setitem(
            sys.modules, "framework.authority.action_mode", stub)
        assert msa.action_seam_disposition("sovereign") == {
            "mode": "propose", "captain_card": False}
        s, _, conn = self._armed_pair(tmp_path, "sovereign")
        assert s["state"] == "held-by-action-seam"
        assert s["applied"] == 0 and conn.calls == []

    def test_disposition_fails_closed_on_garbage_posture(self):
        assert msa.action_seam_disposition("Sovereign!!") == {
            "mode": "propose", "captain_card": False}

    def test_apply_action_descriptor_shape_pinned(self):
        # ring 2 (runtime organ plane — never a Ring-0 category), honest
        # reversibility, and the REGISTERED undo handle act_tell requires.
        assert msa._APPLY_ACTION["ring"] == 2
        assert msa._APPLY_ACTION["reversibility"] == "reversible"
        assert msa._APPLY_ACTION["category"] == "memory-supersede-apply"
        assert "--undo" in msa._APPLY_ACTION["undo_handle"]
        # a Ring-0 category here would captain-card every disposition — the
        # seam itself pins that; this pin keeps the descriptor honest.
        assert msa.action_seam_disposition("sovereign")["captain_card"] is False

    def test_report_and_render_carry_the_seam_verdict(self, tmp_path):
        spath = tmp_path / "soak.jsonl"
        _write_jsonl(spath, ARMED_SEED)
        rep = msa.build_report(proposals_path=tmp_path / "p.jsonl",
                               soak_path=spath,
                               config_path=tmp_path / "nope.yml",
                               needs_path=tmp_path / "needs-ledger.jsonl",
                               now=NOW, posture="guardian")
        assert rep["state"] == "held-by-action-seam"
        assert rep["action_mode"] == "propose"
        text = msa.render_report(rep)
        assert "held-by-action-seam" in text
        assert "action-mode=propose" in text
        rep2 = msa.build_report(proposals_path=tmp_path / "p.jsonl",
                                soak_path=spath,
                                config_path=tmp_path / "nope.yml",
                                needs_path=tmp_path / "needs-ledger.jsonl",
                                now=NOW, posture="sovereign")
        assert rep2["state"] == "armed" and rep2["action_mode"] == "go"


class TestSameSourceAskBatching:
    """N pending Captain asks cued by ONE row must arrive as ONE decision.

    Paid 2026-07-26 (Captain-seat dry run): eleven near-identical
    supersession asks sat a week as eleven cards at identical dwell — "I
    never gave ten answers, I gave zero". The detector's pair walk makes
    that shape structural (one new row cues supersession of every older
    row it contradicts), so the fix is producer-side grouping: same cueing
    row ⇒ ONE card listing every member; distinct rows stay distinct; one
    ask stays an ordinary per-pair card. His ruling fans out MECHANICALLY
    — approve-all puts each member through the SAME guarded per-item path
    with its own ledger row, skip-all records one skip per member — and
    the batch card's receipt lands only after every member closed, so the
    approval can never be spent on the first pair and lost for the rest.
    The attention plane and the needs API are germline: nothing here edits
    them, it only files fewer asks into them.
    """

    SRC = "100"

    @staticmethod
    def _cue_calls(rec):
        """Cards this pass filed about ASKS — the once-per-window
        soak-halfway heads-up rides the same seam and is not one."""
        return [c for c in rec.calls
                if c[1]["action_type"] != msa._HALFWAY_ACTION]

    def _fixture(self, n, *, src=None, first_old=1):
        """n contradiction-cue proposals, all cued by ONE live row."""
        src = src or self.SRC
        olds = list(range(first_old, first_old + n))
        live = [_live(o, f"belief {o} about the office") for o in olds]
        live.append(_live(src, "the office moved and is no longer there"))
        props = [_prop(f"sup-cue{src}{o:04d}", o, src,
                       reason="contradiction-cue", cues=["no longer"])
                 for o in olds]
        return live, props, [p["proposal_id"] for p in props]

    def _batch_row(self, nid, members, status, *, src=None):
        src = src or self.SRC
        return {"id": nid, "kind": "decision", "status": status,
                "action_type": f"{msa._ACTION_NS}:batch:{src}",
                "why": msa._am.render_batch_body(
                    src, sorted(members), noun="memory supersessions"),
                "filed_by": "system:memory-supersession"}

    # ---- minting -----------------------------------------------------

    def test_eleven_same_source_asks_are_one_card_listing_eleven(
            self, tmp_path):
        live, props, pids = self._fixture(11)
        rec = Recorder()
        s, _, spath, _ = _run(tmp_path, props, live, need_fn=rec)
        assert len(rec.calls) == 1, \
            f"eleven asks minted {len(rec.calls)} cards, not one"
        assert s["cue_cards"] == 11 and s["cue_batches"] == 1
        kind, kw = rec.calls[0]
        assert kind == "decision"
        assert kw["action_type"] == f"{msa._ACTION_NS}:batch:{self.SRC}"
        assert kw["filed_by"] == "system:memory-supersession"
        assert f"11 memory supersessions cued by row {self.SRC}" in kw["why"]
        assert "approve all / list / skip all" in kw["why"]
        # every member id is preserved on the card he sees
        assert msa._am.batch_members(kw["why"]) == tuple(sorted(pids))
        # ...and every ask is still recorded individually, naming its card
        decs = {d["proposal_id"]: d for d in _decisions(spath)}
        assert set(decs) == set(pids)
        for pid in pids:
            assert decs[pid]["decision"] == "cue-card"
            assert decs[pid]["need_id"] == "NEED-feedbeef"
            assert decs[pid]["batch"] == f"{msa._ACTION_NS}:batch:{self.SRC}"

    def test_three_distinct_sources_are_three_cards(self, tmp_path):
        live, props = [], []
        for i, src in enumerate(("100", "200", "300")):
            lv, pr, _ = self._fixture(2, src=src, first_old=10 * (i + 1))
            live += lv
            props += pr
        rec = Recorder()
        s, *_ = _run(tmp_path, props, live, need_fn=rec)
        assert len(rec.calls) == 3
        actions = sorted(kw["action_type"] for _k, kw in rec.calls)
        assert actions == [f"{msa._ACTION_NS}:batch:{s2}"
                           for s2 in ("100", "200", "300")]
        for _k, kw in rec.calls:
            assert len(msa._am.batch_members(kw["why"])) == 2
        assert s["cue_cards"] == 6 and s["cue_batches"] == 3

    def test_single_ask_stays_an_ordinary_unbatched_card(self, tmp_path):
        # degenerate end: a "batch of one" would be a second wording for
        # the identical decision
        live, props, pids = self._fixture(1)
        rec = Recorder()
        s, _, spath, _ = _run(tmp_path, props, live, need_fn=rec)
        assert len(rec.calls) == 1
        kw = rec.calls[0][1]
        assert kw["action_type"] == f"{msa._ACTION_NS}:{pids[0]}"
        assert msa._am.is_batch_action(kw["action_type"],
                                       producer=msa._ACTION_NS) is False
        assert "members (" not in kw["why"]
        assert "approve = supersede the older row" in kw["why"]
        d = _decisions(spath)[0]
        assert d["need_id"] == "NEED-feedbeef" and "batch" not in d
        assert s["cue_cards"] == 1 and s["cue_batches"] == 0

    def test_distinct_single_asks_never_merge_into_one_card(self, tmp_path):
        live, props = [], []
        for i, src in enumerate(("100", "200", "300")):
            lv, pr, _ = self._fixture(1, src=src, first_old=10 * (i + 1))
            live += lv
            props += pr
        rec = Recorder()
        s, *_ = _run(tmp_path, props, live, need_fn=rec)
        assert len(rec.calls) == 3
        assert all(not msa._am.is_batch_action(kw["action_type"],
                                               producer=msa._ACTION_NS)
                   for _k, kw in rec.calls)
        assert s["cue_cards"] == 3 and s["cue_batches"] == 0

    def test_a_guardian_dark_batch_retries_next_run(self, tmp_path):
        live, props, pids = self._fixture(3)
        s1, ppath, spath, _ = _run(tmp_path, props, live,
                                   need_fn=lambda kind, **kw: None)
        decs = msa.compact_soak(msa.read_jsonl(spath))
        assert all("need_id" not in decs[pid] for pid in pids)
        rec = Recorder()
        msa.run_apply_pass(proposals_path=ppath, soak_path=spath,
                           config_path=tmp_path / "nope.yml",
                           needs_path=tmp_path / "needs-ledger.jsonl",
                           now=NOW, live_rows=live, conn_factory=Boom(),
                           file_need_fn=rec, posture="sovereign")
        assert len(rec.calls) == 1
        decs = msa.compact_soak(msa.read_jsonl(spath))
        assert all(decs[pid]["need_id"] == "NEED-feedbeef" for pid in pids)
        assert s1["cue_batches"] == 1

    # ---- approve-all fan-out ------------------------------------------

    def test_approve_all_fans_out_to_every_member_individually(
            self, tmp_path):
        live, props, pids = self._fixture(3)
        rows = [self._batch_row("NEED-ba7c4001", pids,
                                "approved_pending_apply")]
        conn = FakeConn({1: None, 2: None, 3: None})
        mark = MarkRecorder()
        s, ppath, spath, rec = _run(tmp_path, props, live,
                                    soak_rows=ARMED_SEED, conn=conn,
                                    needs_rows=rows, mark_fn=mark)
        # ONE ruling, N members: each is re-validated and recorded on its
        # own, and no member is ever a cue-card again
        decs = msa.compact_soak(msa.read_jsonl(spath))
        assert set(decs) == set(pids)
        for pid in pids:
            assert decs[pid]["via"] == "captain-grant"
            assert decs[pid]["need_id"] == "NEED-ba7c4001"
        assert s["cue_cards"] == 0 and s["cue_batches"] == 0
        # the fan-out is the EXISTING per-item apply path, so the same-run
        # touched-id guard still binds: one apply now, the rest stay open
        # with the approval live and land on following runs
        assert s["applied"] == 1
        assert mark.calls == [], "the approval closed before every member ran"
        for _ in range(2):
            msa.run_apply_pass(proposals_path=ppath, soak_path=spath,
                               config_path=tmp_path / "nope.yml",
                               needs_path=tmp_path / "needs-ledger.jsonl",
                               now=NOW, live_rows=live, conn_factory=lambda: conn,
                               file_need_fn=rec, mark_need_fn=mark,
                               posture="sovereign")
        decs = msa.compact_soak(msa.read_jsonl(spath))
        assert [decs[pid]["decision"] for pid in pids] == ["applied"] * 3
        assert conn.live == {1: 100, 2: 100, 3: 100}
        # ONE receipt, once, only after the last member closed
        assert len(mark.calls) == 1
        nid, status, reason = mark.calls[0]
        assert (nid, status) == ("NEED-ba7c4001", "granted")
        assert "3/3 pairs applied" in reason

    def test_an_open_batch_card_resolves_nothing(self, tmp_path):
        # silence is never agreement: an unanswered batched card leaves
        # every member exactly where the N cards left them
        live, props, pids = self._fixture(3)
        rows = [self._batch_row("NEED-ba7c4002", pids, "open")]
        boom = Boom()
        s, _, spath, _ = _run(tmp_path, props, live, soak_rows=ARMED_SEED,
                              conn_factory=boom, needs_rows=rows)
        assert s["applied"] == 0 and boom.called is False
        decs = msa.compact_soak(msa.read_jsonl(spath))
        assert all(decs[pid]["decision"] == "cue-card" for pid in pids)

    def test_an_unreadable_membership_fans_out_to_nobody(self, tmp_path):
        live, props, pids = self._fixture(3)
        row = self._batch_row("NEED-ba7c4003", pids, "approved_pending_apply")
        row["why"] = row["why"].replace("members (3)", "members (2)")
        boom = Boom()
        s, _, spath, _ = _run(tmp_path, props, live, soak_rows=ARMED_SEED,
                              conn_factory=boom, needs_rows=[row])
        assert msa.load_batch_rulings(tmp_path / "needs-ledger.jsonl") == {}
        assert s["applied"] == 0 and boom.called is False
        decs = msa.compact_soak(msa.read_jsonl(spath))
        assert all(decs[pid]["decision"] == "cue-card" for pid in pids)

    def test_a_ruled_batch_is_never_re_filed_with_new_members(self, tmp_path):
        # membership may not grow after a ruling: a late ask waits for the
        # next window rather than joining an approval it was never listed in
        live, props, pids = self._fixture(3)
        rows = [self._batch_row("NEED-ba7c4004", pids[:2],
                                "approved_pending_apply")]
        conn = FakeConn({1: None, 2: None, 3: None})
        rec = Recorder()
        s, _, spath, _ = _run(tmp_path, props, live, soak_rows=ARMED_SEED,
                              conn=conn, needs_rows=rows, need_fn=rec)
        assert self._cue_calls(rec) == [], "a ruled source re-filed its card"
        decs = msa.compact_soak(msa.read_jsonl(spath))
        assert decs[pids[2]]["decision"] == "cue-card"
        assert "need_id" not in decs[pids[2]]
        assert 3 not in conn.live or conn.live[3] is None

    # ---- skip-all -----------------------------------------------------

    def test_skip_all_records_one_skip_per_member(self, tmp_path):
        live, props, pids = self._fixture(3)
        rows = [self._batch_row("NEED-ba7c4005", pids, "denied")]
        boom = Boom()
        rec = Recorder()
        s, ppath, spath, _ = _run(tmp_path, props, live,
                                  soak_rows=ARMED_SEED, conn_factory=boom,
                                  needs_rows=rows, need_fn=rec)
        assert self._cue_calls(rec) == []
        decs = msa.compact_soak(msa.read_jsonl(spath))
        assert set(decs) == set(pids)
        for pid in pids:
            assert decs[pid]["decision"] == "cue-card-skipped"
            assert decs[pid]["via"] == "captain-skip-all"
            assert decs[pid]["need_id"] == "NEED-ba7c4005"
        assert s["applied"] == 0 and boom.called is False
        assert s["skipped"] == 3 and s["cue_cards"] == 0
        # a skipped member is closed: no reopen, no re-file, no ledger growth
        before = len(msa.read_jsonl(spath))
        s2 = msa.run_apply_pass(proposals_path=ppath, soak_path=spath,
                                config_path=tmp_path / "nope.yml",
                                needs_path=tmp_path / "needs-ledger.jsonl",
                                now=NOW, live_rows=live, conn_factory=Boom(),
                                file_need_fn=rec, posture="sovereign")
        assert s2["skipped"] == 0 and self._cue_calls(rec) == []
        assert len(msa.read_jsonl(spath)) == before + 1   # the run marker

    def test_a_denied_batch_never_reaches_the_apply_path(self, tmp_path):
        live, props, pids = self._fixture(3)
        rows = [self._batch_row("NEED-ba7c4006", pids, "denied")]
        conn = FakeConn({1: None, 2: None, 3: None})
        s, *_ = _run(tmp_path, props, live, soak_rows=ARMED_SEED, conn=conn,
                     needs_rows=rows)
        assert s["state"] == "armed"          # a skip is not a gate veto
        assert conn.calls == []

    def test_a_pair_card_ruling_is_never_read_as_a_batch(self, tmp_path):
        # The ACTION TYPE is what separates the two card classes — not the
        # body. Both non-batch rows below carry a well-formed membership
        # line, so a reader that fell back to body-shape would fan a single
        # pair approval (and a soak-halfway veto) out over three pairs.
        body = msa._am.render_batch_body(
            "100", ["sup-cue1000001", "sup-cue1000002", "sup-cue1000003"],
            noun="memory supersessions")
        npath = tmp_path / "needs-ledger.jsonl"
        _write_jsonl(npath, [
            {"id": "NEED-pair0001", "status": "approved_pending_apply",
             "action_type": f"{msa._ACTION_NS}:sup-cue1000001", "why": body},
            {"id": "NEED-half0001", "status": "denied",
             "action_type": msa._HALFWAY_ACTION, "why": body},
            {"id": "NEED-other001", "status": "approved_pending_apply",
             "action_type": f"other-organ:batch:100", "why": body}])
        assert msa.load_batch_rulings(npath) == {}
        assert msa.load_granted_pids(npath) == {"sup-cue1000001":
                                                "NEED-pair0001"}
        assert msa.halfway_veto(npath) == "NEED-half0001"

    # ---- the boundary this fix had to respect -------------------------

    def test_batching_lives_entirely_outside_the_germline_set(self):
        """The attention plane and the needs API are schg-locked, so the
        batcher may only file FEWER asks into them — never edit them. This
        pins that the unit's own files are outside the locked set (and
        that the locked set still contains the plane it stayed out of)."""
        lock = (_REPO / "cabinet" / "scripts" / "germline-lock.sh").read_text()
        locked_files = set(re.findall(r'^\s*"([^"]+)"', lock, re.MULTILINE))
        assert "framework/authority/needs.py" in locked_files
        assert "framework/attention/queue.py" in locked_files
        assert "framework/attention/queue_card.py" in locked_files
        locked_dirs = set(re.findall(r'^\s*"([^"]+)"\s*(?:#.*)?$',
                                     lock[lock.index("DIRS=("):],
                                     re.MULTILINE))
        unit_paths = (
            "cabinet/scripts/lib/ask_mint.py",
            "cabinet/scripts/lib/tests/test_ask_mint.py",
            "cabinet/scripts/memory-supersede-apply.py",
            "cabinet/scripts/tests/test_memory_supersede_apply.py",
        )
        for rel in unit_paths:
            assert (_REPO / rel).is_file(), f"{rel} missing"
            assert rel not in locked_files, f"{rel} is germline-locked"
            assert not any(rel.startswith(d.rstrip("/") + "/")
                           for d in locked_dirs), \
                f"{rel} sits inside a germline-locked dir"
        # ...and the batcher only CALLS the locked needs API
        src = (_REPO / "cabinet" / "scripts" / "lib" / "ask_mint.py").read_text()
        assert "from framework.authority import needs" in src
        assert "needs.file_need(" in src
        assert "open(" not in src, "the batcher opened a file of its own"
