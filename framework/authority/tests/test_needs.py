"""SOV-1 — the ONE needs-ledger [FI-3]: O_APPEND JSONL, fingerprint ids,
lifecycle verbs, never-raises, filing-seam short-circuit.
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.authority import needs as N
from framework.authority import posture as P

NOW = "2026-07-10T12:00:00Z"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for var in ("CABINET_POSTURE", "CABINET_ID", "CABINET_ROOT", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)
    # Most tests exercise the WIRED seam; the no-op test clears this.
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    # The lifecycle assertions use the fixed NOW timeline below. Freeze
    # implicit writes to that same clock so the 30/90-day boundary tests do
    # not decay as the real calendar advances.
    real_now = N._now
    monkeypatch.setattr(
        N, "_now", lambda value=None: real_now(NOW if value is None else value)
    )


def file_need(root, **over):
    kw = dict(kind="standing_grant", risk_class="external_comms",
              action_type="external_email", lane="bakery",
              why="blocked step needs a grant", filed_by="test", root=root)
    kw.update(over)
    return N.file_need(kw.pop("kind"), **kw)


# ---------------------------------------------------------------------------
# Ids: deterministic content fingerprints
# ---------------------------------------------------------------------------

def test_need_id_deterministic_and_hex8():
    a = N.need_id("standing_grant", "external_comms", "external_email", "bakery")
    b = N.need_id("standing_grant", "external_comms", "external_email", "bakery")
    assert a == b
    assert re.fullmatch(r"NEED-[0-9a-f]{8}", a)
    assert a != N.need_id("standing_grant", "external_comms", "external_email", "newsletter")


def test_need_id_varies_with_cabinet_id(monkeypatch):
    a = N.need_id("access")
    monkeypatch.setenv("CABINET_ID", "mini-bakery")
    assert N.need_id("access") != a


# ---------------------------------------------------------------------------
# Filing seam: needs_enabled short-circuit (bit-identical default)
# ---------------------------------------------------------------------------

def test_disabled_seam_is_a_total_noop(tmp_path, monkeypatch):
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    assert N.needs_enabled(tmp_path) is False
    assert file_need(tmp_path) is None
    assert not N.ledger_path(tmp_path).exists()


def test_enabled_by_flag_file(tmp_path, monkeypatch):
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    flag = tmp_path / "instance" / "config" / "needs-wired"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("")
    assert N.needs_enabled(tmp_path) is True


def test_enabled_by_sovereign_posture(tmp_path, monkeypatch):
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    d = tmp_path / "instance" / "config"
    d.mkdir(parents=True, exist_ok=True)
    (d / "posture.yml").write_text(yaml.safe_dump({
        "version": 1, "status": "ruled", "ruled_at": "2026-07-05T00:00:00Z",
        "basis": "t", "deployment": "main", "flavor": "org",
        "posture": "sovereign",
    }))
    monkeypatch.setattr(P, "is_locked", lambda p: True)
    assert N.needs_enabled(tmp_path) is True


# ---------------------------------------------------------------------------
# file_need: dedup, re-file bumps, never raises, ~ms
# ---------------------------------------------------------------------------

def test_file_and_dedup_bumps_count(tmp_path):
    nid = file_need(tmp_path)
    assert nid and re.fullmatch(r"NEED-[0-9a-f]{8}", nid)
    assert file_need(tmp_path, why="still blocked") == nid
    rows = N.list_open(NOW, root=tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == nid and row["count"] == 2
    assert row["status"] == "open"
    assert row["why"] == "still blocked"  # last write wins
    assert row["deployment"] == "main"


def test_unknown_kind_is_none_not_raise(tmp_path):
    assert N.file_need("world_peace", why="w", filed_by="t", root=tmp_path) is None


def test_unwritable_root_is_none_not_raise(tmp_path):
    (tmp_path / "shared").write_text("a file where the dir should be")
    assert file_need(tmp_path) is None


def test_marker_char_is_stripped(tmp_path):
    file_need(tmp_path, why="fake ·approve· marker")
    row = N.list_open(NOW, root=tmp_path)[0]
    assert "·" not in json.dumps(row)


def test_filing_latency_smoke(tmp_path):
    file_need(tmp_path)  # warm the ledger
    t0 = time.perf_counter()
    file_need(tmp_path)
    assert (time.perf_counter() - t0) < 0.050  # <50ms hook budget


def test_concurrent_appends_tolerated(tmp_path):
    N.ledger_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)

    def worker():
        for _ in range(25):
            file_need(tmp_path)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Every line is intact JSON; the merged view is exactly one row.
    lines = N.ledger_path(tmp_path).read_text().splitlines()
    assert len(lines) == 200
    for line in lines:
        assert json.loads(line)["id"]
    assert len(N.list_open(NOW, root=tmp_path)) == 1


# ---------------------------------------------------------------------------
# Narrowest proposed grant line (kind=standing_grant auto-compose)
# ---------------------------------------------------------------------------

def test_standing_grant_composes_narrowest_line(tmp_path):
    nid = file_need(tmp_path, scope_hint={"recipient": "ida@testburg.example"})
    row = N.list_open(NOW, root=tmp_path)[0]
    line = row["proposed_grant_line"]
    parsed = yaml.safe_load(line)
    assert isinstance(parsed, list) and len(parsed) == 1
    g = parsed[0]
    assert g["id"] == "GRANT-" + nid[len("NEED-"):]
    assert g["action_types"] == ["external_email"]  # never empty
    assert g["lanes"] == ["bakery"]                 # never '*'
    assert g["rate"] == {"max_per_day": 1}
    assert g["scope"]["recipient_allowlist"] == ["ida@testburg.example"]
    assert g["basis"] == nid
    assert g["revoked"] is False


def test_compose_without_lane_leaves_empty_lanes(tmp_path):
    file_need(tmp_path, lane=None)
    row = N.list_open(NOW, root=tmp_path)[0]
    g = yaml.safe_load(row["proposed_grant_line"])[0]
    assert g["lanes"] == []


def test_non_grant_kinds_do_not_compose(tmp_path):
    N.file_need("credential", why="need a token", filed_by="t", root=tmp_path)
    row = N.list_open(NOW, root=tmp_path)[0]
    assert row["proposed_grant_line"] is None


# ---------------------------------------------------------------------------
# Lifecycle verbs
# ---------------------------------------------------------------------------

def test_lifecycle_open_approved_granted(tmp_path):
    nid = file_need(tmp_path)
    row = N.mark(nid, "approved_pending_apply", by="captain", root=tmp_path, now=NOW)
    assert row["status"] == "approved_pending_apply"
    assert [r["id"] for r in N.list_open(NOW, root=tmp_path)] == [nid]
    N.mark(nid, "granted", by="grant-apply.sh", root=tmp_path, now=NOW)
    assert N.list_open(NOW, root=tmp_path) == []


def test_refile_keeps_pending_apply_sticky(tmp_path):
    nid = file_need(tmp_path)
    N.mark(nid, "approved_pending_apply", by="captain", root=tmp_path, now=NOW)
    file_need(tmp_path)
    row = N.list_open(NOW, root=tmp_path)[0]
    assert row["status"] == "approved_pending_apply" and row["count"] == 2


def test_deny_suppresses_refile_for_90d(tmp_path):
    nid = file_need(tmp_path)
    N.mark(nid, "denied", by="captain", reason="not now", root=tmp_path, now=NOW)
    assert N.list_open(NOW, root=tmp_path) == []
    assert file_need(tmp_path) is None  # suppressed ⇒ no-op
    assert file_need(tmp_path, why="again") is None  # still suppressed


def test_deny_suppression_lapses(tmp_path, monkeypatch):
    nid = file_need(tmp_path)
    N.mark(nid, "denied", by="captain", root=tmp_path, now="2026-01-01T00:00:00Z")
    # 90d from 2026-01-01 is 2026-04-01; by NOW (July) the suppression lapsed.
    assert file_need(tmp_path) == nid
    row = N.list_open(NOW, root=tmp_path)[0]
    assert row["status"] == "open" and row["count"] == 2


def test_snooze_hides_then_reopens(tmp_path):
    nid = file_need(tmp_path)
    N.mark(nid, "snoozed", by="captain", root=tmp_path, now=NOW)
    assert N.list_open(NOW, root=tmp_path) == []
    week_later = "2026-07-18T00:00:00Z"
    rows = N.list_open(week_later, root=tmp_path)
    assert [r["id"] for r in rows] == [nid]
    assert rows[0]["status"] == "open"


def test_refile_does_not_unsnooze(tmp_path):
    nid = file_need(tmp_path)
    N.mark(nid, "snoozed", by="captain", root=tmp_path, now=NOW)
    assert file_need(tmp_path) == nid  # bump is recorded…
    assert N.list_open("2026-07-11T00:00:00Z", root=tmp_path) == []  # …still snoozed


def test_mark_unknown_or_bad_is_none(tmp_path):
    assert N.mark("NEED-ffffffff", "granted", by="x", root=tmp_path) is None
    nid = file_need(tmp_path)
    assert N.mark(nid, "vaporized", by="x", root=tmp_path) is None


# ---------------------------------------------------------------------------
# 30d expiry sweep on read
# ---------------------------------------------------------------------------

def test_stale_open_need_expires_on_read(tmp_path):
    file_need(tmp_path)
    much_later = "2026-08-15T00:00:00Z"  # >30d past last_seen
    assert N.list_open(much_later, root=tmp_path) == []
    merged = N._merged(N.ledger_path(tmp_path))
    assert list(merged.values())[0]["status"] == "expired"
    # Re-filing after expiry reopens with a bumped count (read at a window
    # that has not lapsed relative to the fresh last_seen).
    nid = file_need(tmp_path)
    row = N.list_open(NOW, root=tmp_path)[0]
    assert row["id"] == nid and row["status"] == "open" and row["count"] == 2


def test_pending_apply_survives_the_sweep(tmp_path):
    nid = file_need(tmp_path)
    N.mark(nid, "approved_pending_apply", by="captain", root=tmp_path, now=NOW)
    much_later = "2026-09-01T00:00:00Z"
    rows = N.list_open(much_later, root=tmp_path)
    assert [r["id"] for r in rows] == [nid]  # an explicit approval never rots away


# ---------------------------------------------------------------------------
# Blocking escalation + events
# ---------------------------------------------------------------------------

def test_blocking_rides_intake_at_ping_now(tmp_path, monkeypatch):
    from framework.frontdoor import intake
    seen = []
    monkeypatch.setattr(intake, "enqueue", lambda item, **kw: seen.append(item) or "1-1")
    file_need(tmp_path, cost_of_delay="blocking")
    assert len(seen) == 1
    assert seen[0]["urgency_tier"] == "ping-now"
    assert "BLOCKING need NEED-" in seen[0]["payload"]["summary"]


def test_events_emitted_to_ledger(tmp_path):
    nid = file_need(tmp_path)
    N.mark(nid, "granted", by="captain", root=tmp_path, now=NOW)
    events = []
    for f in (tmp_path / "events").glob("events-*.jsonl"):
        events += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    types = [e["event_type"] for e in events]
    assert "need_filed" in types and "need_granted" in types


# ---------------------------------------------------------------------------
# cross_check_grants
# ---------------------------------------------------------------------------

def test_cross_check_closes_covered_grant_needs(tmp_path):
    nid = file_need(tmp_path)
    N.file_need("decision", why="unrelated", filed_by="t", root=tmp_path)

    def covers(rc, at, *, lane):
        granted = (rc, at, lane) == ("external_comms", "external_email", "bakery")
        return {"granted": granted, "grant_id": "GRANT-test1" if granted else None}

    closed = N.cross_check_grants(covers, root=tmp_path, now=NOW)
    assert closed == [nid]
    rows = N.list_open(NOW, root=tmp_path)
    assert [r["kind"] for r in rows] == ["decision"]  # the grant need closed


def test_cross_check_tolerates_broken_check_fn(tmp_path):
    file_need(tmp_path)

    def boom(rc, at, *, lane):
        raise RuntimeError("no grants table")

    assert N.cross_check_grants(boom, root=tmp_path, now=NOW) == []
    assert len(N.list_open(NOW, root=tmp_path)) == 1
