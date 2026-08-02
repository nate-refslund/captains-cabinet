"""The CLI contract every web surface actually consumes.

`cabinet/dashboard/src/lib/onboarding/bridge.ts` reaches this core exactly one
way — ``python3.12 -m framework.onboarding.journey act`` with the request as
JSON on stdin — and reads whatever that prints. Everything else in this
directory calls :func:`journey.act` in-process, so the boundary the Dashboard,
the World overlay and Telegram all sit behind had no test of its own: a refusal
could stop reaching stdout, or an answer stop landing on state, and every
in-process arm would stay green while all three surfaces broke.

The arms below are the ones the salience path depends on, driven the way the
bridge drives them. They are the other half of
`cabinet/dashboard/src/lib/onboarding/parity.test.ts`: that file pins the
vocabulary the surfaces send, this one pins what sending it does.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from framework.onboarding import journey

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Two sources naming the same things, so a ranking exists at all. Shaped like
#: the fixture the in-process salience arms use; kept local because this file
#: drives a SUBPROCESS and must not depend on another test module's helpers.
_TRACKER = (
    "Blue Harbour plan", "Blue Harbour ops", "Red Anchor", "Green Lantern brief",
    "Internal admin 1", "Internal admin 2", "Internal admin 3",
)
_REPO = (
    "blue-harbour", "blue-harbour-api", "red-anchor", "green-lantern",
    "solo-repo", "another-repo", "third-repo",
)


def _estate(root: Path) -> None:
    rows = [
        {"connector": "tracker", "name": name,
         "updated": f"2026-07-{index + 1:02d}T09:00:00Z"}
        for index, name in enumerate(_TRACKER)
    ] + [
        {"connector": "repo", "name": name,
         "updated": f"2026-07-{index + 10:02d}T09:00:00Z"}
        for index, name in enumerate(_REPO)
    ]
    data = root / journey.DATA_REL
    data.mkdir(parents=True, exist_ok=True)
    state = journey._fresh_state()
    state["salience_rows"] = {"rows": rows, "identities": [], "not_reached": []}
    state["entry_grants"] = {
        "connectors": sorted({row["connector"] for row in rows}),
        "local_files": False,
        "web": False,
    }
    (data / journey.STATE_NAME).write_text(json.dumps(state), encoding="utf-8")


def _run(root: Path, command: str, request: dict | None = None) -> dict:
    """One bridge-shaped invocation: fixed argv, shell-free, JSON on stdin."""
    completed = subprocess.run(
        [sys.executable, "-m", "framework.onboarding.journey", command],
        input=json.dumps(request) if request is not None else "",
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={**os.environ, "CABINET_ROOT": str(root)},
        timeout=120,
    )
    assert completed.stdout.strip(), (
        f"the core printed nothing on {command}; a surface has nothing to read"
        f"\nstderr: {completed.stderr[:800]}"
    )
    return json.loads(completed.stdout)


def _folder(root: Path, name: str) -> Path:
    folder = (root / "estates" / name).resolve()
    folder.mkdir(parents=True)
    (folder / "README.md").write_text("# a folder\n", encoding="utf-8")
    return folder


def _window(root: Path, source: Path, **extra) -> dict:
    return _run(root, "act", {
        "action": "propose_window", "surface": "dashboard",
        "action_id": f"window-{source.name}-{len(extra)}",
        "source": str(source),
        "purpose": "Find one release risk before it surprises the team.",
        "ownership": "self", "authority_basis": "my own machine, my own folder",
        "relationship_destination": "reversible", **extra,
    })


@pytest.fixture()
def estate(tmp_path: Path) -> Path:
    _estate(tmp_path)
    return tmp_path


def test_the_ranked_question_reaches_a_surface_with_its_candidates(estate: Path):
    """A card that prints a question and no way to answer it is the dead end
    this whole path exists to abolish. The candidates and the escape hatch have
    to arrive THROUGH the process boundary, not just exist in-process."""
    card = _run(estate, "snapshot")["card"]
    offer = next((o for o in card["options"] if o["action"] == "answer_salience"), None)
    assert offer, "the ranked question reached no surface"
    assert offer["input"] == "choice", "a surface cannot know it needs a picker"
    ids = [o["id"] for o in offer["options"]]
    assert len(ids) >= 2 and ids[-1] == "other", (
        "the escape hatch is never omitted: the right answer can sit outside the "
        "shortlist, and an offer with no way to say 'none of these' turns that "
        "into a wrong answer the operator had to accept"
    )
    assert all(o.get("why") for o in offer["options"]), "a rank with no evidence"


def test_a_bare_answer_is_refused_by_the_core_and_the_refusal_reaches_the_surface(estate: Path):
    """WHICH LAYER REFUSES IS THE WHOLE POINT. Until the bridge admitted this
    action the send died there as `action_invalid` — a surface-invented sentence
    about an action the operator never chose. The core's own refusal names what
    is missing and what to do about it, and it only arrives if the request is
    allowed to cross."""
    refusal = _run(estate, "act", {
        "action": "answer_salience", "surface": "dashboard", "action_id": "bare",
    })
    assert refusal["ok"] is False
    assert refusal["code"] == "salience_choice_required"
    assert refusal["error"], "a refusal with no sentence is unanswerable"


def test_picking_a_candidate_lands_the_target_on_state(estate: Path):
    card = _run(estate, "snapshot")["card"]
    offer = next(o for o in card["options"] if o["action"] == "answer_salience")
    first = offer["options"][0]
    out = _run(estate, "act", {
        "action": "answer_salience", "surface": "dashboard",
        "action_id": "pick", "choice": first["id"],
    })
    assert out["ok"] is True
    assert out["state"]["salience"]["target"] == first["label"]
    assert out["state"]["salience"]["from_escape_hatch"] is False


def test_the_escape_hatch_records_a_typed_name_as_the_operators_own(estate: Path):
    out = _run(estate, "act", {
        "action": "answer_salience", "surface": "dashboard",
        "action_id": "typed", "choice": "other", "name": "Harbour Yard",
    })
    assert out["ok"] is True
    salience = out["state"]["salience"]
    assert salience["target"] == "Harbour Yard"
    assert salience["from_escape_hatch"] is True, (
        "an answer the ranking did not offer must be distinguishable from one it "
        "did — it is the loud signal that the shortlist missed"
    )


def test_an_off_target_window_is_refused_with_the_material_to_answer_it(estate: Path):
    """THE REFUSAL A SURFACE HAS TO BE ABLE TO ANSWER.

    The card builds its two relation buttons from the answered target (which is
    on state, above) and the folder it just submitted. Measured 2026-08-02:
    `journey._cli` prints `{ok, code, error}` and does NOT forward
    `JourneyError.detail`, so the target reaches the browser through the state
    and the error sentence rather than through a detail block — which is why the
    Dashboard reconstructs it and treats a detail block as enrichment.
    """
    _run(estate, "act", {
        "action": "answer_salience", "surface": "dashboard",
        "action_id": "answer-before-window", "choice": "other", "name": "Blue Harbour",
    })
    refusal = _window(estate, _folder(estate, "quarterly-tax-returns"))
    assert refusal["ok"] is False
    assert refusal["code"] == "salience_window_off_target"
    assert "Blue Harbour" in refusal["error"] or "blueharbour" in refusal["error"]
    snapshot = _run(estate, "snapshot")
    assert snapshot["state"]["salience"]["target"], (
        "the answered target must survive the refusal on state — it is what the "
        "surface names back to the operator"
    )
    assert snapshot["state"]["stage"] == "welcome", "a refusal moved the stage"


def test_stating_the_relation_lets_the_same_window_through_and_is_recorded(estate: Path):
    """The operator knows what is in the folder and this module does not. Both
    statements are accepted and BOTH are recorded, because they make two
    different sentences true on the Charter the operator is about to approve."""
    _run(estate, "act", {
        "action": "answer_salience", "surface": "dashboard",
        "action_id": "answer-before-relation", "choice": "other", "name": "Blue Harbour",
    })
    elsewhere = _folder(estate, "quarterly-tax-returns")
    assert _window(estate, elsewhere)["ok"] is False

    stated = _window(estate, elsewhere, salience_relation="elsewhere")
    assert stated["ok"] is True
    assert stated["state"]["salience"]["window"]["relation"] == "elsewhere"
    assert stated["state"]["stage"] == "charter_pending"


def test_the_other_relation_is_a_real_second_answer_not_a_synonym(estate: Path):
    """Lopsided on purpose. A gate that accepted any string, or that recorded
    both statements as one value, passes a single-relation arm — only the pair
    shows the core is reading which claim was made."""
    _run(estate, "act", {
        "action": "answer_salience", "surface": "dashboard",
        "action_id": "answer-same-thing", "choice": "other", "name": "Blue Harbour",
    })
    # A name sharing NO word with the answer, so `same_thing` is doing real work
    # here: a folder the name test would have matched anyway proves nothing
    # about whether the stated relation was read.
    same = _window(estate, _folder(estate, "ledger-archive"), salience_relation="same_thing")
    assert same["ok"] is True
    assert same["state"]["salience"]["window"]["relation"] == "same_thing"

    invented = _window(estate, _folder(estate, "another-folder"), salience_relation="probably")
    assert invented["ok"] is False
    assert invented["code"] == "salience_relation_invalid", (
        "a relation the vocabulary does not carry must be refused by name, or "
        "the surface's two buttons are decoration over a free-text field"
    )


def test_every_relation_the_core_publishes_is_one_it_accepts(estate: Path):
    """The vocabulary is published to surfaces (WINDOW_RELATIONS is mirrored in
    the Dashboard types and pinned by parity.test.ts). A published value the core
    then refuses would be a button that can only earn a refusal."""
    for index, relation in enumerate(sorted(journey.WINDOW_RELATIONS)):
        root = estate / f"vocab-{index}"
        _estate(root)
        _run(root, "act", {
            "action": "answer_salience", "surface": "dashboard",
            "action_id": f"vocab-answer-{index}", "choice": "other", "name": "Blue Harbour",
        })
        out = _window(root, _folder(root, f"unrelated-{index}"), salience_relation=relation)
        assert out["ok"] is True, f"{relation} is published but refused"
        assert out["state"]["salience"]["window"]["relation"] == relation
