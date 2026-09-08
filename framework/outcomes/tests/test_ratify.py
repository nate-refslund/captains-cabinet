"""THE TAP — one proposed card becomes a ratified responsibility.

Every arm here drives the PUBLIC entry point (``ratify`` / ``list_ratifiable``
/ the CLI ``main``) against a hermetic tmp root, never the checkout's own
instance/. The rows under test are built by ``genesis.merge_proposals`` rather
than hand-written, because the defect these tests exist to prevent is exactly
"the writer validates a shape the org never proposes": a real genesis row
carries what / why / lane / derived_from / proposed_by / proof_expected /
proposed_digest, and the outcome schema's item is ``additionalProperties:
false``, so validating the whole row would refuse every card in existence.

DEGENERATE ENDS, asserted rather than assumed: an absent proposals file, an
unparseable one, an unknown id, an empty principal, an unknown door, and a
second identical call all have their own arm, and each asserts that NOTHING
was written and NO event landed — a refusal that leaves a half-written file is
worse than the act it refused.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from framework.events import emitter
from framework.onboarding import genesis
from framework.outcomes import ratify as ratify_mod
from framework.outcomes.ratify import (
    OUTCOMES_REL, list_ratifiable, main, projection, ratify, schema_item_keys,
)

_REPO = Path(__file__).resolve().parents[3]

ANSWERS = {
    "version": 1,
    "cabinet": {"id": "acme-hq", "mode": "single", "org_shape": "portfolio"},
    "lanes": [{"name": "Acme Storefront", "slug": "acme-store",
               "repos": ["acme/storefront"]}],
}


def _card(cid: str, what: str = "ship the thing") -> dict:
    return {"id": cid, "name": "Card %s" % cid, "lane": "acme-store",
            "what": what, "why": "because the operator said so",
            "proof_expected": "a receipt the operator can read",
            "proposed_by": "onboarding-genesis"}


@pytest.fixture
def hatched(tmp_path, monkeypatch):
    """A root shaped like a hatched instance: one REAL proposed card, written
    through genesis's own merge writer, and a ledger of its own."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    genesis.merge_proposals([_card("acme-001"), _card("acme-002")], tmp_path,
                            answers=ANSWERS, now="2026-09-01T00:00:00Z")
    return tmp_path


def _proposals(root: Path) -> dict:
    return yaml.safe_load((root / genesis.PROPOSALS_REL).read_text(encoding="utf-8"))


def _outcomes(root: Path) -> dict:
    return yaml.safe_load((root / OUTCOMES_REL).read_text(encoding="utf-8"))


def _events() -> list:
    return emitter.replay(event_types=["captain_outcome_ratified"])


# ---------------------------------------------------------------------------
# A1.1 — the projection, on a REAL row.
# ---------------------------------------------------------------------------
def test_ratify_accepts_merge_proposals_row(hatched):
    """The row the org actually proposes is ratifiable.

    Written as its own arm because the whole-row reading of "validate against
    outcome.schema.json" would return invalid_row for every card the cabinet
    has ever produced — a unit that is green on fixtures and refuses reality.
    """
    row = _proposals(hatched)["outcomes"][0]
    # The premise this arm rests on, asserted rather than believed: the real
    # row carries keys the schema's item does not allow.
    assert set(row) - schema_item_keys(), "a real genesis row has extra keys"
    res = ratify("acme-001", door="web", principal="session-1", root=hatched)
    assert res["status"] == "ratified", res


def test_projection_drops_exactly_the_keys_the_schema_does_not_declare(hatched):
    row = _proposals(hatched)["outcomes"][0]
    proj = projection(row)
    assert set(proj) <= schema_item_keys()
    assert set(proj) == set(row) & schema_item_keys()
    assert "what" not in proj and "id" in proj and "measurable_criteria" in proj


def test_schema_carries_the_ratification_keys():
    """The schema extension is part of this unit, not an assumption about it."""
    keys = schema_item_keys()
    for key in ("ratified_by", "ratified_via", "ratified_at",
                "ratified_from_digest", "proposed_digest",
                "edited_since_proposed"):
        assert key in keys, key


# ---------------------------------------------------------------------------
# The act: copy, mark, emit.
# ---------------------------------------------------------------------------
def test_copies_marks_emits(hatched):
    res = ratify("acme-001", door="web", principal="session-1", root=hatched)
    assert res["status"] == "ratified"
    assert res["event_id"]

    live = {r["id"]: r for r in _outcomes(hatched)["outcomes"]}
    assert set(live) == {"acme-001"}
    row = live["acme-001"]
    assert row["status"] == "active" and row["captain_ratified"] is True
    assert row["ratified_by"] == "captain" and row["ratified_via"] == "web"
    assert row["ratified_at"] and row["ratified_from_digest"]
    assert row["edited_since_proposed"] is False
    # measurable_criteria survives untouched — the tap never edits the contract.
    proposed = {r["id"]: r for r in _proposals(hatched)["outcomes"]}
    assert row["measurable_criteria"] == proposed["acme-001"]["measurable_criteria"]
    # `deployment` is never written: an absent gate compiles everywhere.
    assert "deployment" not in _outcomes(hatched)

    # The proposal is MARKED, never deleted — and the untouched card stays draft.
    assert proposed["acme-001"]["status"] == "ratified"
    assert proposed["acme-002"]["status"] == "draft"

    events = _events()
    assert len(events) == 1
    ev = events[0]
    assert ev["actor"] == "captain"
    payload = ev["payload"]
    assert payload["outcome_id"] == "acme-001"
    assert payload["proposal_id"] == "acme-001"
    assert payload["door"] == "web" and payload["principal"] == "session-1"
    assert payload["criteria_count"] == 1
    assert payload["root"] == str(hatched)
    # A1.7: the line the operator reads afterwards is "Taking on: <name>", and
    # the receipt is the only thing that says a tap happened — so the name has
    # to be ON it, not fetched back out of a file anybody could have edited.
    assert payload["name"] == "Card acme-001"


def test_idempotent_second_call(hatched):
    first = ratify("acme-001", door="web", principal="session-1", root=hatched)
    before = ((hatched / OUTCOMES_REL).read_bytes(),
              (hatched / genesis.PROPOSALS_REL).read_bytes())
    second = ratify("acme-001", door="web", principal="session-1", root=hatched)
    assert second["status"] == "already_ratified"
    assert second["event_id"] == first["event_id"]
    after = ((hatched / OUTCOMES_REL).read_bytes(),
             (hatched / genesis.PROPOSALS_REL).read_bytes())
    assert after == before, "a second tap must leave both files byte-identical"
    assert len(_events()) == 1


def test_edited_since_proposed_is_reported_not_refused(hatched):
    path = hatched / genesis.PROPOSALS_REL
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["outcomes"][0]["what"] = "the operator rewrote this"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    res = ratify("acme-001", door="web", principal="session-1", root=hatched)
    assert res["status"] == "ratified"
    assert res["edited_since_proposed"] is True
    assert _events()[0]["payload"]["edited_since_proposed"] is True


# ---------------------------------------------------------------------------
# A1.2 — the terminal door is attribution, not authentication.
# ---------------------------------------------------------------------------
def test_terminal_door_never_yields_the_captain_actor(hatched):
    res = ratify("acme-001", door="terminal", principal="uid:501", root=hatched)
    assert res["status"] == "ratified"
    row = {r["id"]: r for r in _outcomes(hatched)["outcomes"]}["acme-001"]
    assert row["ratified_by"] == "operator"
    assert row["ratified_via"] == "terminal"
    ev = _events()[0]
    assert ev["actor"] == "operator", (
        "the terminal door runs as the same uid as every officer; calling it "
        "'captain' would be a claim the door cannot support")
    assert ev["payload"]["principal"] == "uid:501"


@pytest.mark.parametrize("door,actor", [("web", "captain"), ("chat", "captain"),
                                        ("terminal", "operator")])
def test_actor_for_each_door(door, actor):
    assert ratify_mod.actor_for(door) == actor


# ---------------------------------------------------------------------------
# Refusals — each one asserts NOTHING was written and NO event landed.
# ---------------------------------------------------------------------------
def _nothing_happened(root: Path) -> None:
    assert not (root / OUTCOMES_REL).exists(), "a refusal wrote the live file"
    assert _events() == [], "a refusal emitted a receipt"


def test_unknown_id_writes_nothing(hatched):
    res = ratify("no-such-card", door="web", principal="s", root=hatched)
    assert res["status"] == "not_found"
    _nothing_happened(hatched)


def test_absent_proposals_file_is_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    res = ratify("acme-001", door="web", principal="s", root=tmp_path)
    assert res["status"] == "not_found"
    _nothing_happened(tmp_path)


def test_unparseable_proposals_doc_writes_nothing(hatched):
    (hatched / genesis.PROPOSALS_REL).write_text("{[not: yaml", encoding="utf-8")
    res = ratify("acme-001", door="web", principal="s", root=hatched)
    assert res["status"] == "invalid_row"
    _nothing_happened(hatched)


def test_invalid_row_writes_nothing(hatched):
    path = hatched / genesis.PROPOSALS_REL
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["outcomes"][0].pop("measurable_criteria")
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    res = ratify("acme-001", door="web", principal="s", root=hatched)
    assert res["status"] == "invalid_row"
    _nothing_happened(hatched)


@pytest.fixture
def no_jsonschema(monkeypatch):
    """Make ``import jsonschema`` fail, so the fallback path is the one that
    runs. A degraded validator that accepts everything is the disabled-sensor
    shape this repo keeps finding, so the fallback gets its own arms."""
    import builtins

    real_import = builtins.__import__

    def _blocked(name, *args, **kwargs):
        if name == "jsonschema":
            raise ImportError("jsonschema is not installed here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked)
    return None


def test_minimal_validator_is_the_one_that_runs_and_still_refuses(
        hatched, no_jsonschema):
    good = {"id": "x", "name": "X", "measurable_criteria": ["a"], "status": "active"}
    assert ratify_mod.validate_projection(good) == "minimal", (
        "the fallback must be the validator that actually ran")
    with pytest.raises(ratify_mod.RatifyError):
        ratify_mod.validate_projection({"id": "x", "name": "X"})
    with pytest.raises(ratify_mod.RatifyError):
        ratify_mod.validate_projection(
            {"id": "x", "name": "X", "measurable_criteria": []})
    with pytest.raises(ratify_mod.RatifyError):
        ratify_mod.validate_projection(
            {"id": "x", "name": "X", "measurable_criteria": ["a"],
             "status": "nonsense"})


def test_minimal_validator_refuses_the_same_row_end_to_end(hatched, no_jsonschema):
    path = hatched / genesis.PROPOSALS_REL
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["outcomes"][0].pop("measurable_criteria")
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    res = ratify("acme-001", door="web", principal="s", root=hatched)
    assert res["status"] == "invalid_row"
    _nothing_happened(hatched)


def test_the_authoritative_validator_is_the_one_that_runs_by_default():
    good = {"id": "x", "name": "X", "measurable_criteria": ["a"], "status": "active"}
    assert ratify_mod.validate_projection(good) == "jsonschema"


def test_a_door_that_cannot_name_a_principal_refuses(hatched):
    res = ratify("acme-001", door="web", principal="  ", root=hatched)
    assert res["status"] == "refused"
    assert "principal" in res["reason"]
    _nothing_happened(hatched)


def test_unknown_door_refuses(hatched):
    res = ratify("acme-001", door="carrier-pigeon", principal="s", root=hatched)
    assert res["status"] == "refused"
    _nothing_happened(hatched)


# ---------------------------------------------------------------------------
# A1.6 — a git worktree's outcomes file is TRACKED.
# ---------------------------------------------------------------------------
def test_repo_root_is_refused_unless_allowed(hatched):
    (hatched / ".git").mkdir()
    res = ratify("acme-001", door="web", principal="s", root=hatched)
    assert res["status"] == "refused"
    assert "git worktree" in res["reason"]
    _nothing_happened(hatched)

    allowed = ratify("acme-001", door="web", principal="s", root=hatched,
                     allow_repo=True)
    assert allowed["status"] == "ratified"


# ---------------------------------------------------------------------------
# Invariant 6 — killed between the two writes.
# ---------------------------------------------------------------------------
def test_ratified_files_without_the_event_get_their_receipt(hatched):
    ratify("acme-001", door="web", principal="s", root=hatched)
    # Simulate the kill: the files landed, the ledger did not.
    for log in (hatched / "events").glob("events-*.jsonl"):
        log.unlink()
    assert _events() == []
    res = ratify("acme-001", door="web", principal="s", root=hatched)
    assert res["status"] == "already_ratified"
    assert res["event_id"], "the repair call must emit the missing receipt"
    assert len(_events()) == 1


# ---------------------------------------------------------------------------
# Invariant 5 — concurrency, through real processes.
# ---------------------------------------------------------------------------
_TAPPER = """
import sys
from pathlib import Path
sys.path.insert(0, %r)
from framework.outcomes.ratify import ratify
res = ratify(sys.argv[1], door="web", principal="p" + sys.argv[2],
             root=Path(sys.argv[3]))
print(res["status"])
"""


def _tap_processes(root: Path, ids: list) -> list:
    env = dict(os.environ)
    # A0.4: pin the ledger explicitly — unset, every child gets its own.
    env["CABINET_EVENT_LOG_DIR"] = str(root / "events")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTEST_CURRENT_TEST", None)
    script = _TAPPER % str(_REPO)
    procs = [
        subprocess.Popen([sys.executable, "-c", script, oid, str(i), str(root)],
                         env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True)
        for i, oid in enumerate(ids)
    ]
    return [(p.wait(timeout=180), p.stdout.read(), p.stderr.read()) for p in procs]


def test_concurrent_taps_emit_once(hatched):
    results = _tap_processes(hatched, ["acme-001"] * 5)
    for rc, out, err in results:
        assert rc == 0, err
        assert out.strip() in ("ratified", "already_ratified"), out
    assert len(_events()) == 1, "five taps on one card must leave ONE receipt"
    statuses = [out.strip() for _rc, out, _err in results]
    assert statuses.count("ratified") == 1


def test_concurrent_taps_on_two_cards_both_land(hatched):
    results = _tap_processes(hatched, ["acme-001", "acme-002"])
    for rc, _out, err in results:
        assert rc == 0, err
    live = {r["id"] for r in _outcomes(hatched)["outcomes"]}
    assert live == {"acme-001", "acme-002"}
    assert len(_events()) == 2


# ---------------------------------------------------------------------------
# Invariant 7 — the compiler compiles what was ratified.
# ---------------------------------------------------------------------------
def test_compiler_compiles_ratified(hatched):
    ratify("acme-001", door="web", principal="s", root=hatched)
    from framework.missions.compiler import compile_from_yaml
    roles = [{"slug": "coordinator", "title": "Coordinator",
              "capabilities": ["engineering", "product"]}]
    missions = compile_from_yaml(hatched / OUTCOMES_REL, roles=roles,
                                 emit_event=False)
    assert len(missions) == 1
    assert missions[0]["outcome_id"] == "acme-001"


# ---------------------------------------------------------------------------
# The read model the doors render.
# ---------------------------------------------------------------------------
def test_list_ratifiable_hides_what_is_already_ratified(hatched):
    before = {row["id"] for row in list_ratifiable(hatched)}
    assert before == {"acme-001", "acme-002"}
    assert all(row["name"] and row["proposed_digest"]
               for row in list_ratifiable(hatched))
    ratify("acme-001", door="web", principal="s", root=hatched)
    after = {row["id"] for row in list_ratifiable(hatched)}
    assert after == {"acme-002"}


def test_list_ratifiable_on_an_empty_root_is_an_honest_empty(tmp_path):
    assert list_ratifiable(tmp_path) == []


# ---------------------------------------------------------------------------
# The terminal door's exit codes.
# ---------------------------------------------------------------------------
def test_cli_exit_codes(hatched, capsys):
    assert main(["acme-001", "--door", "terminal", "--principal", "uid:1",
                 "--root", str(hatched), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["status"] == "ratified" and payload["outcome_id"] == "acme-001"

    assert main(["nope", "--door", "terminal", "--principal", "uid:1",
                 "--root", str(hatched)]) == 3
    capsys.readouterr()

    path = hatched / genesis.PROPOSALS_REL
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    for row in doc["outcomes"]:
        if row["id"] == "acme-002":
            row.pop("measurable_criteria")
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    assert main(["acme-002", "--door", "terminal", "--principal", "uid:1",
                 "--root", str(hatched)]) == 4
    capsys.readouterr()

    (hatched / ".git").mkdir()
    assert main(["acme-002", "--door", "terminal", "--principal", "uid:1",
                 "--root", str(hatched)]) == 5


def test_cli_list_json(hatched, capsys):
    assert main(["--list", "--json", "--root", str(hatched)]) == 0
    rows = json.loads(capsys.readouterr().out.strip())
    assert [row["id"] for row in rows] == ["acme-001", "acme-002"]


# ---------------------------------------------------------------------------
# Agnostic law — this package names no vendor, product or person.
# ---------------------------------------------------------------------------
def test_no_vendor_noun_in_the_package_or_the_ledger(hatched):
    banned = ("telegram", "slack", "discord", "whatsapp", "signal", "docker",
              "redis", "github", "notion", "linear")
    for path in sorted((_REPO / "framework" / "outcomes").rglob("*.py")):
        if path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8").lower()
        for word in banned:
            assert word not in text, "%s names %s" % (path, word)
    ratify("acme-001", door="chat", principal="p-1", root=hatched)
    dumped = json.dumps(_events()[0]).lower()
    for word in banned:
        assert word not in dumped, "the ledger row names %s" % word
