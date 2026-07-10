"""SOV-1 — standing-grants kernel [FI-2]: fail-closed loader + check().

Ceilings-only, Captain-locked, hard-scope-predicated. Every ambiguity narrows:
absent/corrupt/unlocked file ⇒ [], malformed row ⇒ line-drop, Redis down ⇒
treated revoked / not granted, missing scope context ⇒ predicate fails,
risk_class ∈ posture.yml never_grant ⇒ dropped + ONE decision need per class
(Captain ruling 2026-07-05: grantability is instance-scoped — the old
flavor≠org structural refusal is gone), unreadable never_grant intent ⇒
every row dropped.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.authority import grants as G
from framework.authority import matrix as M
from framework.authority import needs as N

LOCKED = lambda p: True  # noqa: E731
NOT_VETOED = lambda at: False  # noqa: E731
REDIS_EMPTY = lambda key: ""  # noqa: E731 — reachable, no tombstone/count

NOW = "2026-07-10T12:00:00Z"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for var in ("CABINET_POSTURE", "CABINET_NEEDS_WIRED", "CABINET_ID",
                "CABINET_ROOT", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))


def grant_row(**over):
    g = {
        "id": "GRANT-test1",
        "deployment": "main",
        "risk_class": "external_comms",
        "action_types": ["external_email"],
        "lanes": ["bakery"],
        "scope": {"recipient_allowlist": ["*@testburg.example"],
                  "max_eur_per_day": 0, "vendor_allowlist": []},
        "rate": {"max_per_day": 10},
        "expires": "2026-08-01T00:00:00Z",
        "granted_by": "Captain",
        "granted_at": "2026-07-01T00:00:00Z",
        "basis": "NEED-abc12345",
        "revoked": False,
    }
    g.update(over)
    return g


def write_grants(root: Path, rows, text: str | None = None) -> Path:
    d = root / "instance" / "config"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "standing-grants.yml"
    p.write_text(text if text is not None else
                 yaml.safe_dump({"version": 1, "grants": rows}))
    return p


def write_posture(root: Path, flavor="org", never_grant=None) -> Path:
    d = root / "instance" / "config"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "posture.yml"
    doc = {
        "version": 1, "status": "ruled", "ruled_at": "2026-07-05T00:00:00Z",
        "basis": "test", "deployment": "main", "flavor": flavor,
        "posture": "sovereign",
    }
    if never_grant is not None:
        doc["never_grant"] = never_grant
    p.write_text(yaml.safe_dump(doc))
    return p


def check(**over):
    kw = dict(lane="bakery", now=NOW, context={"recipient": "x@testburg.example"},
              grants=[grant_row()], redis_get=REDIS_EMPTY,
              is_vetoed_fn=NOT_VETOED, file_needs=False)
    kw.update(over)
    rc = kw.pop("risk_class", "external_comms")
    at = kw.pop("action_type", "external_email")
    return G.check(rc, at, **kw)


# ---------------------------------------------------------------------------
# Ceilings-only pin vs the shipped floor matrix
# ---------------------------------------------------------------------------

def test_ceiling_classes_pinned_to_floor_matrix():
    policy = M.matrix_policy(M.load_matrix())
    assert set(policy["hard_ceiling"]) == set(G.CEILING_RISK_CLASSES)


# ---------------------------------------------------------------------------
# Loader fail-closed paths
# ---------------------------------------------------------------------------

def test_absent_loads_empty_and_files_need_when_wired(tmp_path, monkeypatch):
    assert G.load_grants(tmp_path, is_locked_fn=LOCKED) == []
    assert not N.ledger_path(tmp_path).exists()  # unwired ⇒ silent
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    assert G.load_grants(tmp_path, is_locked_fn=LOCKED) == []
    rows = N.list_open(root=tmp_path)
    assert len(rows) == 1 and "absent" in rows[0]["why"]


def test_unlocked_loads_empty(tmp_path):
    write_posture(tmp_path)
    write_grants(tmp_path, [grant_row()])
    # Default attestation on the real tmp file: no schg ⇒ empty.
    assert G.load_grants(tmp_path) == []


def test_unparseable_loads_empty(tmp_path):
    write_grants(tmp_path, [], text="grants: [broken\n  ")
    assert G.load_grants(tmp_path, is_locked_fn=LOCKED) == []


@pytest.mark.parametrize("doc", [
    {"version": 2, "grants": []},
    {"version": 1},
    {"version": 1, "grants": {}},
    {"version": 1, "grants": [], "extra": True},
])
def test_corrupt_root_shape_loads_empty(tmp_path, doc):
    write_grants(tmp_path, [], text=yaml.safe_dump(doc))
    assert G.load_grants(tmp_path, is_locked_fn=LOCKED) == []


@pytest.mark.parametrize("bad", [
    grant_row(id="nope"),
    grant_row(risk_class="reversible"),           # ceilings-only
    grant_row(action_types=[]),
    grant_row(lanes=["*"]),                       # never lane:'*'
    grant_row(lanes=[]),
    grant_row(scope={"recipient_allowlist": [], "surprise": 1}),
    grant_row(rate={"max_per_day": 0}),
    grant_row(expires="2026-11-01T00:00:00Z"),    # >90d horizon
    grant_row(expires="2026-06-01T00:00:00Z"),    # expires before granted_at
    grant_row(revoked="no"),
    dict(grant_row(), dev_note="x"),              # unknown key
])
def test_malformed_rows_are_line_dropped(tmp_path, bad):
    write_posture(tmp_path)
    write_grants(tmp_path, [bad, grant_row(id="GRANT-good",
                                           risk_class="spend")])
    out = G.load_grants(tmp_path, is_locked_fn=LOCKED)
    assert [g["id"] for g in out] == ["GRANT-good"]


def test_line_drop_files_row_need_when_wired(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    write_posture(tmp_path)
    write_grants(tmp_path, [grant_row(rate={"max_per_day": 0})])
    assert G.load_grants(tmp_path, is_locked_fn=LOCKED) == []
    rows = N.list_open(root=tmp_path)
    assert any(r["action_type"] == "standing_grants_row" and
               "GRANT-test1" in r["why"] for r in rows)


# ---------------------------------------------------------------------------
# never_grant — instance-scoped class refusal (Captain ruling 2026-07-05)
# ---------------------------------------------------------------------------

def test_flavor_personal_no_longer_refuses_external_comms(tmp_path):
    # Captain ruling 2026-07-05: grantability is instance-scoped, never
    # flavor-structural — personal flavor without never_grant keeps the row.
    write_posture(tmp_path, flavor="personal")
    write_grants(tmp_path, [grant_row()])
    out = G.load_grants(tmp_path, is_locked_fn=LOCKED)
    assert [g["id"] for g in out] == ["GRANT-test1"]


def test_absent_ruling_defaults_all_classes_grantable(tmp_path):
    # No posture.yml: never_grant defaults [] — external_comms rows load
    # (the grants file's OWN schg attestation stays the gate).
    write_grants(tmp_path, [grant_row(),
                            grant_row(id="GRANT-spend", risk_class="spend")])
    out = G.load_grants(tmp_path, is_locked_fn=LOCKED)
    assert [g["id"] for g in out] == ["GRANT-test1", "GRANT-spend"]


def test_never_grant_drops_listed_class(tmp_path):
    write_posture(tmp_path, never_grant=["external_comms"])
    write_grants(tmp_path, [grant_row(),
                            grant_row(id="GRANT-spend", risk_class="spend")])
    out = G.load_grants(tmp_path, is_locked_fn=LOCKED)
    assert [g["id"] for g in out] == ["GRANT-spend"]


def test_never_grant_files_one_decision_need_per_class(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    write_posture(tmp_path, never_grant=["external_comms"])
    write_grants(tmp_path, [grant_row(),
                            grant_row(id="GRANT-test2",
                                      action_types=["external_teams"])])
    assert G.load_grants(tmp_path, is_locked_fn=LOCKED) == []
    rows = [r for r in N.list_open(root=tmp_path)
            if r["action_type"] == "never_grant_refusal"]
    assert len(rows) == 1                       # ONE per CLASS, not per row
    assert rows[0]["kind"] == "decision"
    assert rows[0]["risk_class"] == "external_comms"
    assert rows[0]["count"] == 1                # in-pass dedup, single filing


def test_never_grant_multiple_classes(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    write_posture(tmp_path, never_grant=["external_comms", "spend"])
    write_grants(tmp_path, [
        grant_row(),
        grant_row(id="GRANT-spend", risk_class="spend"),
        grant_row(id="GRANT-prod", risk_class="deploy_prod"),
    ])
    out = G.load_grants(tmp_path, is_locked_fn=LOCKED)
    assert [g["id"] for g in out] == ["GRANT-prod"]
    rows = [r for r in N.list_open(root=tmp_path)
            if r["action_type"] == "never_grant_refusal"]
    assert {r["risk_class"] for r in rows} == {"external_comms", "spend"}


def test_never_grant_honored_from_unattested_ruling(tmp_path):
    # Narrowing is fail-safe: an UNLOCKED posture.yml's never_grant still
    # drops rows (the grants file itself stays attested here).
    write_posture(tmp_path, never_grant=["external_comms"])
    write_grants(tmp_path, [grant_row(),
                            grant_row(id="GRANT-spend", risk_class="spend")])
    not_posture = lambda p: Path(p).name != "posture.yml"  # noqa: E731
    out = G.load_grants(tmp_path, is_locked_fn=not_posture)
    assert [g["id"] for g in out] == ["GRANT-spend"]


@pytest.mark.parametrize("text", [
    "never_grant: [broken\n  ",                          # unparseable yaml
    "- just\n- a\n- list\n",                             # not a mapping
    yaml.safe_dump({"never_grant": "external_comms"}),   # not a list
    yaml.safe_dump({"never_grant": [1, 2]}),             # not strings
])
def test_never_grant_unreadable_ruling_drops_all_rows(tmp_path, text):
    # Present-but-unreadable never_grant intent ⇒ most-restrictive: every
    # ceiling class treated never-granted (never widen on ambiguity).
    d = tmp_path / "instance" / "config"
    d.mkdir(parents=True, exist_ok=True)
    (d / "posture.yml").write_text(text)
    write_grants(tmp_path, [grant_row(id="GRANT-spend", risk_class="spend")])
    assert G.load_grants(tmp_path, is_locked_fn=LOCKED) == []


# ---------------------------------------------------------------------------
# check() — the full predicate chain
# ---------------------------------------------------------------------------

def test_check_happy_path_attributed_allow():
    res = check()
    assert res["granted"] is True
    assert res["grant_id"] == "GRANT-test1"
    assert "GRANT-test1" in res["reason"]


def test_check_non_ceiling_class_never_grants():
    res = check(risk_class="pm_write", action_type="task_create")
    assert res["granted"] is False and res["grant_id"] is None
    assert "ceilings-only" in res["reason"]


@pytest.mark.parametrize("kw", [
    dict(action_type="external_teams"),
    dict(lane="newsletter"),
    dict(lane=None),
    dict(grants=[grant_row(deployment="mini-bakery")]),
    dict(grants=[grant_row(revoked=True)]),
    dict(now="2026-08-02T00:00:00Z"),                       # past expires
    dict(context={"recipient": "x@evil.com"}),              # allowlist miss
    dict(context=None),                                     # no context ⇒ fail-closed
    dict(context={}),
])
def test_check_misses_fail_closed(kw):
    res = check(**kw)
    assert res["granted"] is False and res["grant_id"] is None


def test_check_tombstone_revokes():
    get = lambda key: "1" if key.startswith("cabinet:grant:revoked:") else ""  # noqa: E731
    res = check(redis_get=get)
    assert res["granted"] is False
    assert "tombstone" in res["reason"]


def test_check_redis_down_treated_revoked():
    def get(key):
        raise RuntimeError("connection refused")
    res = check(redis_get=get)
    assert res["granted"] is False
    assert "treated revoked" in res["reason"]


def test_check_rate_exhausted_blocks():
    get = lambda key: "10" if key.startswith("cabinet:grant:count:") else ""  # noqa: E731
    res = check(redis_get=get)
    assert res["granted"] is False and "rate exhausted" in res["reason"]


def test_check_rate_counter_unreadable_blocks():
    def get(key):
        if key.startswith("cabinet:grant:count:"):
            raise RuntimeError("down")
        return ""
    res = check(redis_get=get)
    assert res["granted"] is False and "rate counter unreadable" in res["reason"]


def test_check_vetoed_blocks_before_grants():
    res = check(is_vetoed_fn=lambda at: True)
    assert res["granted"] is False and "veto" in res["reason"]


def test_check_veto_registry_failure_narrows():
    def boom(at):
        raise RuntimeError("registry unreadable")
    res = check(is_vetoed_fn=boom)
    assert res["granted"] is False and "veto" in res["reason"]


def test_check_spend_hard_scope():
    g = grant_row(id="GRANT-spend", risk_class="spend",
                  action_types=["vendor_payment"],
                  scope={"recipient_allowlist": [], "max_eur_per_day": 50,
                         "vendor_allowlist": []})
    ok = check(risk_class="spend", action_type="vendor_payment", grants=[g],
               context={"amount_eur": 25})
    assert ok["granted"] is True
    over = check(risk_class="spend", action_type="vendor_payment", grants=[g],
                 context={"amount_eur": 51})
    assert over["granted"] is False and "hard-scope" in over["reason"]
    blind = check(risk_class="spend", action_type="vendor_payment", grants=[g],
                  context={})
    assert blind["granted"] is False


def test_check_vendor_hard_scope():
    g = grant_row(id="GRANT-prod", risk_class="deploy_prod",
                  action_types=["deploy_prod"],
                  scope={"recipient_allowlist": [], "max_eur_per_day": 0,
                         "vendor_allowlist": ["vercel"]})
    ok = check(risk_class="deploy_prod", action_type="deploy_prod", grants=[g],
               context={"vendor": "Vercel"})
    assert ok["granted"] is True
    miss = check(risk_class="deploy_prod", action_type="deploy_prod",
                 grants=[g], context={"vendor": "aws"})
    assert miss["granted"] is False


def test_check_loads_from_locked_file(tmp_path):
    write_posture(tmp_path)
    write_grants(tmp_path, [grant_row()])
    res = G.check("external_comms", "external_email", lane="bakery",
                  root=tmp_path, now=NOW,
                  context={"recipient": "a@testburg.example"},
                  is_locked_fn=LOCKED, redis_get=REDIS_EMPTY,
                  is_vetoed_fn=NOT_VETOED)
    assert res["granted"] is True and res["grant_id"] == "GRANT-test1"


# ---------------------------------------------------------------------------
# covers() + record_use()
# ---------------------------------------------------------------------------

def test_covers_matches_without_act_time_data():
    res = G.covers("external_comms", "external_email", lane="bakery",
                   now=NOW, grants=[grant_row()], redis_get=REDIS_EMPTY,
                   is_vetoed_fn=NOT_VETOED)
    assert res["granted"] is True and res["grant_id"] == "GRANT-test1"
    # …but still refuses a revoked/expired grant.
    gone = G.covers("external_comms", "external_email", lane="bakery",
                    now=NOW, grants=[grant_row(revoked=True)],
                    redis_get=REDIS_EMPTY, is_vetoed_fn=NOT_VETOED)
    assert gone["granted"] is False


def test_record_use_increments_day_key():
    calls = []
    G.record_use("GRANT-test1", now=NOW,
                 redis_incr=lambda k: calls.append(("incr", k)) or "1",
                 redis_expire=lambda k, t: calls.append(("expire", k)))
    assert calls[0] == ("incr", "cabinet:grant:count:GRANT-test1:2026-07-10")
    assert calls[1][0] == "expire"


def test_record_use_failure_is_reported_not_raised():
    def boom(k):
        raise RuntimeError("down")
    assert G.record_use("GRANT-test1", now=NOW, redis_incr=boom) is False


# ---------------------------------------------------------------------------
# The shipped example validates row-by-row
# ---------------------------------------------------------------------------

def test_shipped_example_rows_are_valid():
    example = _REPO_ROOT / "instance" / "config" / "standing-grants.yml.example"
    data = yaml.safe_load(example.read_text())
    assert data["version"] == 1
    assert data["grants"], "example must ship at least one row"
    for row in data["grants"]:
        assert G._row_error(row) is None
