"""The open half of the action vocabulary — proven for an operator whose work
the shipped vocabulary does not describe.

WHAT WAS WRONG, measured on master at 70bf330e before this suite existed:

    submit-filing --court district    -> ambiguous, risk_class None
    rx-dispense --patient 12          -> ambiguous, risk_class None
    order-concrete --yards 40         -> ambiguous, risk_class None
    kiln-fire --batch 7 --temp 1240   -> ambiguous, risk_class None

`ambiguous` carries no risk class by design, and no risk class resolves
fail-safe to propose_only. The fail-safe was right; its REACH was the defect.
The 30-member vocabulary is built from one industry's verbs, so every act in
any other kind of work fell into the backstop — permanently, with the autonomy
ladder unreachable. Symmetrically, the always-gated ceilings guarded classes
with no members in such an operator's world: protection that reads as
protection and protects nothing.

WHAT IS TRUE NOW. The framework keeps the CLASSES of consequence and what each
earns; the deployment supplies the OPERATIONS that fall in them. Every property
that made the closed vocabulary safe survives, and each is asserted below:

  * un-collidable        a declared id is namespaced; all 30 members proven
                         un-matchable by the shape (test_namespacing_*)
  * ceiling-safe         a declaration cannot escape or claim a ceiling
                         (test_declaration_cannot_*)
  * fail-closed          malformed / unknown-class / unreadable all leave the
                         operation unclassified, i.e. propose-only
                         (test_malformed_*, test_unknown_class_*)
  * function             one id, one class; a declaration never re-points an
                         existing binding (test_cannot_repoint_*)

S0: python3.12, no network, no DB, deterministic.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from framework import env                                          # noqa: E402
from framework.authority import matrix as authority_matrix         # noqa: E402
from framework.authority.classifier import (                       # noqa: E402
    ACTION_TYPES, AMBIGUOUS, classify_action,
)
from framework.authority.policy_engine import (                    # noqa: E402
    resolve_verdict, risk_of,
)

# Three operations from three unrelated kinds of work, none of which the
# shipped vocabulary names. Deliberately not software.
_FILING = "submit-filing --court district"
_DISPENSE = "rx-dispense --patient 12"
_ORDER = "order-concrete --yards 40"

_DECLARATION = {
    "operations": [
        {"id": "practice/submit-filing", "invoked_as": ["submit-filing"],
         "risk_class": "pm_write"},
        {"id": "clinic/dispense", "invoked_as": ["rx-dispense"],
         "risk_class": "deploy_prod"},          # irreversible in their world
        {"id": "site/order-materials", "invoked_as": ["order-concrete"],
         "risk_class": "reversible"},
    ]
}


@pytest.fixture
def declared(tmp_path, monkeypatch):
    """Point the resolver at a scratch deployment root and return a writer.

    Writes `instance/config/operations.yml` under a temp root, clears the
    process caches (this resolver is read-once, like every other env resolver)
    and restores them afterwards.
    """
    saved_ops = env._declared_operations_cache
    saved_root = env._cabinet_root

    def write(doc):
        cfg = tmp_path / "instance/config"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "operations.yml").write_text(yaml.safe_dump(doc), encoding="utf-8")
        env._declared_operations_cache = None
        return tmp_path

    monkeypatch.setattr(env, "_cabinet_root", lambda: tmp_path)
    env._declared_operations_cache = None
    try:
        yield write
    finally:
        env._declared_operations_cache = saved_ops
        env._cabinet_root = saved_root


def _floor():
    """The shipped floor, with whatever this deployment declared bound in."""
    data = yaml.safe_load(
        (_REPO / "framework" / "policies" / "authority-matrix.yml").read_text(
            encoding="utf-8"))
    policy = authority_matrix.matrix_policy(data)
    authority_matrix.bind_declared_operations(policy)
    return policy


def _verdict(command):
    """(action_type, risk_class, verdict-at-unmeasured) for one command."""
    policy = _floor()
    at = classify_action("Bash", {"command": command})
    rc = risk_of(at, policy["risk_classes"])
    if rc is None:
        return at, None, "propose_only"          # the caller's fail-safe
    return at, rc, resolve_verdict(policy["verdicts"], rc, "unmeasured")


# ---------------------------------------------------------------------------
# THE DEFECT, still reproducible with nothing declared
# ---------------------------------------------------------------------------

class TestUndeclaredIsStillTheBackstop:

    def test_three_kinds_of_work_are_unclassified_and_propose_only(self, declared):
        declared({"operations": []})
        for cmd in (_FILING, _DISPENSE, _ORDER):
            at, rc, verdict = _verdict(cmd)
            assert at == AMBIGUOUS, cmd
            assert rc is None, cmd
            assert verdict == "propose_only", cmd


# ---------------------------------------------------------------------------
# THE FIX — the ladder moves, and the ceiling guards something real
# ---------------------------------------------------------------------------

class TestDeclaredOperationsMoveTheLadder:

    def test_declared_operation_classifies_and_earns_a_verdict(self, declared):
        declared(_DECLARATION)
        at, rc, verdict = _verdict(_FILING)
        assert at == "practice/submit-filing"
        assert rc == "pm_write"
        # The whole point: NOT propose_only at unmeasured. This class is
        # trust-first, so the operator acts on day one with an undo path.
        assert verdict == "act_with_undo"

    def test_a_reversible_declaration_acts_immediately(self, declared):
        declared(_DECLARATION)
        at, rc, verdict = _verdict(_ORDER)
        assert at == "site/order-materials"
        assert rc == "reversible"
        assert verdict != "propose_only"

    def test_a_ceiling_declaration_is_always_gated(self, declared):
        """The symmetric half: a ceiling that names only one industry's verbs
        protects nothing outside it. Declared into the ceiling, an operator's
        own irreversible operation is gated at EVERY confidence state."""
        declared(_DECLARATION)
        policy = _floor()
        at = classify_action("Bash", {"command": _DISPENSE})
        assert at == "clinic/dispense"
        rc = risk_of(at, policy["risk_classes"])
        assert rc == "deploy_prod"
        assert rc in policy["hard_ceiling"]
        for state in ("unmeasured", "propose_only", "eligible",
                      "graduated", "demote"):
            assert resolve_verdict(policy["verdicts"], rc, state) == "always_gated"

    def test_the_ledger_accepts_the_cell_key(self, declared):
        """Graduation AND demotion both key on (actor, lane, action_type). An
        operation the ledger cannot record can be neither earned nor lost, so
        the open branch has to reach the event validator too."""
        declared(_DECLARATION)
        from framework.fidelity import consequence
        event = {
            "ts": "2026-07-29T10:00:00Z",
            "actor": {"kind": "officer", "id": "chair"},
            "lane": "somewhere",
            "action": "filed",
            "subject": "a matter",
            "action_type": "practice/submit-filing",
        }
        consequence.validate_consequence(event)    # raises on rejection
        bad = dict(event, action_type="not-namespaced-and-not-a-member")
        with pytest.raises(consequence.ConsequenceValidationError):
            consequence.validate_consequence(bad)

    def test_a_named_tool_call_classifies_too(self, declared):
        """Not every deployment's work arrives as a shell command."""
        declared({"operations": [
            {"id": "studio/render", "invoked_as": ["RenderQueue"],
             "risk_class": "reversible"}]})
        assert classify_action("RenderQueue", {}) == "studio/render"


# ---------------------------------------------------------------------------
# THE SAFETY PROPERTIES — each one an arm, not a claim
# ---------------------------------------------------------------------------

class TestNamespacingKeepsTheVocabulariesApart:

    def test_every_framework_member_is_un_declarable(self):
        """All 30 proven: no member of the closed vocabulary can be spelled as
        a declared id, so a declaration can never shadow or redefine one."""
        for member in ACTION_TYPES:
            assert not env.is_declared_operation_id(member), member

    def test_shape_rejects_the_near_misses(self):
        for bad in ("", "/", "a/", "/b", "a//b", "a/b/c", "A/B", "a b/c",
                    "a/b c", None, 7):
            assert not env.is_declared_operation_id(bad), repr(bad)
        for good in ("a/b", "practice/submit-filing", "site/order.materials"):
            assert env.is_declared_operation_id(good), good


class TestDeclarationsCannotWiden:

    def test_declaration_cannot_soften_a_ceiling(self, declared):
        """A declaration matching a token that ALSO trips a ceiling rule loses:
        the lookup runs after every positive ceiling check."""
        declared({"operations": [
            {"id": "somewhere/harmless", "invoked_as": ["cat"],
             "risk_class": "reversible"}]})
        # `cat .env` is a secrets-ceiling read regardless of any declaration.
        assert classify_action("Bash", {"command": "cat .env"}) == "secret_read"

    def test_declaration_cannot_repoint_an_existing_binding(self, declared):
        declared({"operations": [
            {"id": "somewhere/x", "invoked_as": ["x"], "risk_class": "reversible"}]})
        policy = _floor()
        # A second binding of the same id is refused — the map stays a function.
        policy["risk_classes"]["reversible"]["action_types"].append("somewhere/x")
        before = list(policy["risk_classes"]["pm_write"]["action_types"])
        authority_matrix.bind_declared_operations(policy)
        assert policy["risk_classes"]["pm_write"]["action_types"] == before

    def test_unknown_class_is_dropped_not_guessed(self, declared):
        declared({"operations": [
            {"id": "somewhere/y", "invoked_as": ["y"],
             "risk_class": "no-such-class"}]})
        policy = _floor()
        bound = {at for rc in policy["risk_classes"].values()
                 for at in rc["action_types"]}
        assert "somewhere/y" not in bound
        # It still CLASSIFIES (so the operator sees the name in a receipt and
        # knows what to bind) and still has no risk class, i.e. propose-only.
        at, rc, verdict = _verdict("y --go")
        assert at == "somewhere/y" and rc is None and verdict == "propose_only"

    @pytest.mark.parametrize("row", [
        {"id": "no-namespace", "invoked_as": ["z"], "risk_class": "reversible"},
        {"id": "somewhere/z", "invoked_as": [], "risk_class": "reversible"},
        {"id": "somewhere/z", "invoked_as": ["z z"], "risk_class": "reversible"},
        {"id": "somewhere/z", "invoked_as": ["z"], "risk_class": ""},
        {"id": "somewhere/z", "invoked_as": ["z"]},
        {"invoked_as": ["z"], "risk_class": "reversible"},
        {"id": "somewhere/z", "invoked_as": "z", "risk_class": "reversible"},
    ])
    def test_malformed_rows_are_dropped(self, declared, row):
        declared({"operations": [row]})
        assert classify_action("Bash", {"command": "z --go"}) != "somewhere/z"

    def test_absent_file_is_an_empty_declaration(self, tmp_path, monkeypatch):
        saved = env._declared_operations_cache
        monkeypatch.setattr(env, "_cabinet_root", lambda: tmp_path)
        env._declared_operations_cache = None
        try:
            assert env.declared_operations() == ()
        finally:
            env._declared_operations_cache = saved

    def test_unparseable_file_is_an_empty_declaration(self, tmp_path, monkeypatch):
        saved = env._declared_operations_cache
        cfg = tmp_path / "instance/config"
        cfg.mkdir(parents=True)
        (cfg / "operations.yml").write_text("operations: [ unclosed", encoding="utf-8")
        monkeypatch.setattr(env, "_cabinet_root", lambda: tmp_path)
        env._declared_operations_cache = None
        try:
            assert env.declared_operations() == ()
        finally:
            env._declared_operations_cache = saved

    def test_matrix_still_refuses_a_typo(self, declared):
        """Opening the vocabulary must not open it to garbage: a bare id that
        is neither a framework member nor namespaced still fails validation,
        so a typo cannot read as a binding while binding nothing."""
        declared({"operations": []})
        data = yaml.safe_load(
            (_REPO / "framework" / "policies" / "authority-matrix.yml").read_text(
                encoding="utf-8"))
        pol = authority_matrix.matrix_policy(data)
        pol["risk_classes"]["reversible"]["action_types"].append("locel_edit")
        with pytest.raises(authority_matrix.MatrixValidationError):
            authority_matrix.validate_matrix(data)

    def test_matrix_still_refuses_relocating_a_ceiling_kind(self, declared):
        """The invariant the exactly-equal ceiling check existed for, asserted
        against the superset check that replaced it."""
        declared({"operations": []})
        data = yaml.safe_load(
            (_REPO / "framework" / "policies" / "authority-matrix.yml").read_text(
                encoding="utf-8"))
        pol = authority_matrix.matrix_policy(data)
        pol["risk_classes"]["external_comms"]["action_types"].remove("external_email")
        pol["risk_classes"]["draft_only"]["action_types"].append("external_email")
        with pytest.raises(authority_matrix.MatrixValidationError):
            authority_matrix.validate_matrix(data)

    def test_shipped_floor_validates_unchanged(self, declared):
        """A deployment that declared nothing gets the floor exactly as it
        ships — the open half costs the launching deployment nothing."""
        declared({"operations": []})
        authority_matrix.load_matrix()


# ---------------------------------------------------------------------------
# THE DEFAULT ACTOR — a ratchet, not a one-time cleanup
# ---------------------------------------------------------------------------

class TestDefaultActorComesFromTheRoster:
    """A default actor is unavoidable (the graduation/demotion cell key is
    (actor, lane, action_type), so an act recorded against nobody can be
    neither earned nor lost). WHICH actor is a fact about one operator's org
    shape, and it was spelled as a literal across the acting, frontdoor,
    attention, watchdog, learning, measurement and fidelity planes — a sole
    practitioner inherited a coordinating-officer org chart from a roster they
    never wrote, and every ledger cell was keyed on a stranger's role name.

    The forcing arm below is SHRINK-ONLY: a framework production module may
    construct an officer-typed actor from a literal only if it is listed, and
    the list may only get shorter. It is deliberately shape-based rather than
    name-based — a rule keyed on the launching roster's actual names would go
    red on a stranger's fresh deployment, which is the opposite of the point.
    """

    # Every framework production module allowed to spell an officer-typed
    # actor id as a literal, each with the reason it is not a role.
    _LITERAL_ACTOR_ALLOWED = {
        # Not a role: the component that owns the veto registry, naming itself
        # as the writer of its own rows.
        "framework/frontdoor/veto_registry.py",
    }

    def test_no_framework_module_spells_a_default_actor(self):
        import re as _re
        rx = _re.compile(r'"kind"\s*:\s*"officer"\s*,\s*"id"\s*:\s*"[^"]+"')
        offenders = set()
        for path in sorted((_REPO / "framework").rglob("*.py")):
            rel = path.relative_to(_REPO).as_posix()
            if "/tests/" in rel or path.name.startswith("test_"):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue          # a comment explaining the shape is not the shape
                if "<" in line and ">" in line:
                    continue          # a docstring placeholder, not a name
                if rx.search(line):
                    offenders.add(rel)
        assert offenders <= self._LITERAL_ACTOR_ALLOWED, (
            "framework production code must resolve its default actor through "
            "env.chair_officer(), never a role literal: "
            + ", ".join(sorted(offenders - self._LITERAL_ACTOR_ALLOWED)))

    def test_the_arm_is_not_vacuous(self, tmp_path):
        """The arm must FAIL on the shape it exists to catch — otherwise a
        rename or a regex typo would leave it permanently, silently green."""
        import re as _re
        rx = _re.compile(r'"kind"\s*:\s*"officer"\s*,\s*"id"\s*:\s*"[^"]+"')
        assert rx.search('    actor = {"kind": "officer", "id": "somebody"}')
        assert rx.search('{"kind":"officer","id":"x"}')
        assert not rx.search('actor = {"kind": "officer", "id": env.chair_officer()}')

    def test_the_resolver_falls_back_to_nothing_not_to_a_name(
            self, tmp_path, monkeypatch):
        """A deployment with no roster must resolve to the EMPTY string. The
        failure mode of a missing roster has to be visibly empty, never a role
        name the framework picked."""
        saved_o, saved_c = env._officers_cache, env._chair_officer_cache
        monkeypatch.setattr(env, "_cabinet_root", lambda: tmp_path)
        env._officers_cache = None
        env._chair_officer_cache = None
        try:
            assert env.chair_officer() == ""
        finally:
            env._officers_cache, env._chair_officer_cache = saved_o, saved_c

    def test_the_resolver_is_the_rosters_first_entry(self, tmp_path, monkeypatch):
        saved_o, saved_c = env._officers_cache, env._chair_officer_cache
        conf = tmp_path / "cabinet"
        conf.mkdir()
        (conf / "officer-capabilities.conf").write_text(
            "# comment\nprincipal:does_the_work\nsecond:reviews\n", encoding="utf-8")
        monkeypatch.setattr(env, "_cabinet_root", lambda: tmp_path)
        env._officers_cache = None
        env._chair_officer_cache = None
        try:
            assert env.chair_officer() == "principal"
        finally:
            env._officers_cache, env._chair_officer_cache = saved_o, saved_c
