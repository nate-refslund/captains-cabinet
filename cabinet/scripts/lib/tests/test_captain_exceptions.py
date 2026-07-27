"""The Captain exception surface — deny-only guardrails (CAPTAIN-RULING 2026-07-27).

    "cabinet should decide what action is allowed. if captain wants some
     specific actions not allowed, captain can just say so and cabinet should
     be able to adjust, e.g. guardrails through hooks."

`instance/config/authority-exceptions.yml` is that "just say so": a DENY-ONLY
list the Captain appends to, read on every tool call, no deploy and no code
change. These tests are the proof that it is HONOURED — an exception surface
nobody proves is honoured is the same failure as an eval pointed at a dead twin.

Both directions are asserted for every predicate: a row present REFUSES, the
same call with the row absent ALLOWS. A test that only ever asserts the refusal
cannot tell a working denylist from one that blocks everything.
"""
from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

_LIB_DIR = Path(__file__).parent.parent.resolve()
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SHADOW_PATH = _REPO_ROOT / "cabinet" / "scripts" / "policy-shadow.py"


def _load_shadow():
    spec = importlib.util.spec_from_file_location("policy_shadow_exceptions_test", _SHADOW_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def shadow():
    return _load_shadow()


@pytest.fixture()
def root(tmp_path, monkeypatch):
    """An isolated CABINET_ROOT with NO policies — so a block can only come
    from the exception surface, never from a typed rule leaking in."""
    (tmp_path / "instance" / "config").mkdir(parents=True)
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.delenv("OFFICER", raising=False)
    monkeypatch.delenv("OFFICER_NAME", raising=False)
    return tmp_path


def _write(root: Path, body: str) -> Path:
    path = root / "instance" / "config" / "authority-exceptions.yml"
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return path


BASH = {"tool_name": "Bash", "tool_input": {"command": "vercel deploy --prod"}}
READ = {"tool_name": "Read", "tool_input": {"file_path": "/tmp/notes.md"}}


class TestDefaultPosture:
    def test_absent_file_is_an_empty_denylist(self, shadow, root):
        assert not (root / "instance" / "config" / "authority-exceptions.yml").exists()
        assert shadow.captain_exception(BASH, "cos") is None

    def test_empty_denylist_allows(self, shadow, root):
        _write(root, "version: 1\ndenylist: []\n")
        assert shadow.captain_exception(BASH, "cos") is None

    def test_empty_document_allows(self, shadow, root):
        _write(root, "")
        assert shadow.captain_exception(BASH, "cos") is None

    def test_shipped_example_parses_and_denies_nothing(self, shadow, root):
        """The .example the Captain edits must itself be a valid empty posture."""
        example = _REPO_ROOT / "instance" / "config" / "authority-exceptions.yml.example"
        assert example.is_file(), "the Captain-facing template must ship"
        _write(root, example.read_text(encoding="utf-8"))
        assert shadow.captain_exception(BASH, "cos") is None


class TestPredicatesBothDirections:
    """Each predicate: present ⇒ refuse, absent ⇒ allow. Never only one arm."""

    def test_command_contains(self, shadow, root):
        _write(root, """
            version: 1
            denylist:
              - id: no-prod-deploys
                why: "I ship production myself."
                command_contains: "vercel deploy --prod"
        """)
        blocked = shadow.captain_exception(BASH, "cos")
        assert blocked is not None
        assert "captain_exception:no-prod-deploys" in blocked
        assert "I ship production myself." in blocked, "the officer is told WHY"

        # same row, a command it does not name → allowed
        assert shadow.captain_exception(
            {"tool_name": "Bash", "tool_input": {"command": "git status"}}, "cos"
        ) is None

        # row removed → the SAME call is allowed again
        _write(root, "version: 1\ndenylist: []\n")
        assert shadow.captain_exception(BASH, "cos") is None

    def test_officer_scoping(self, shadow, root):
        _write(root, """
            version: 1
            denylist:
              - id: cro-no-shell
                why: "CRO works through the API."
                officer: cro
                tool: Bash
        """)
        assert shadow.captain_exception(BASH, "cro") is not None
        assert shadow.captain_exception(BASH, "cos") is None, "must not leak to other officers"

    def test_tool_scoping(self, shadow, root):
        _write(root, """
            version: 1
            denylist:
              - id: no-writes
                why: "read-only week"
                tool: Write
        """)
        assert shadow.captain_exception(
            {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x"}}, "cos") is not None
        assert shadow.captain_exception(READ, "cos") is None

    def test_path_contains(self, shadow, root):
        _write(root, """
            version: 1
            denylist:
              - id: billing-frozen
                why: "frozen until the audit closes"
                path_contains: "/billing/"
        """)
        assert shadow.captain_exception(
            {"tool_name": "Edit", "tool_input": {"file_path": "/srv/app/billing/rates.py"}},
            "cto") is not None
        assert shadow.captain_exception(
            {"tool_name": "Edit", "tool_input": {"file_path": "/srv/app/docs/rates.md"}},
            "cto") is None

    def test_action_type_uses_the_real_classifier(self, shadow, root):
        _write(root, """
            version: 1
            denylist:
              - id: no-pushing-main
                why: "main is mine"
                action_type: git_push_main
        """)
        assert shadow.captain_exception(
            {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}},
            "cto") is not None
        assert shadow.captain_exception(
            {"tool_name": "Bash", "tool_input": {"command": "git push origin feat/x"}},
            "cto") is None

    def test_predicates_are_ANDed(self, shadow, root):
        _write(root, """
            version: 1
            denylist:
              - id: narrow
                why: "only this officer, only this command"
                officer: cro
                command_contains: "deploy"
        """)
        cmd = {"tool_name": "Bash", "tool_input": {"command": "vercel deploy --prod"}}
        assert shadow.captain_exception(cmd, "cro") is not None
        assert shadow.captain_exception(cmd, "cos") is None, "officer must also match"
        assert shadow.captain_exception(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}}, "cro") is None


class TestFailClosed:
    """An unreadable Captain exclusion list is never ignored."""

    def test_unparseable_yaml_refuses(self, shadow, root):
        _write(root, "version: 1\ndenylist: [ this is not: valid: yaml\n")
        reason = shadow.captain_exception(READ, "cos")
        assert reason is not None
        assert "captain_exceptions" in reason

    def test_top_level_not_a_mapping_refuses(self, shadow, root):
        _write(root, "- just\n- a\n- list\n")
        assert shadow.captain_exception(READ, "cos") is not None

    def test_denylist_not_a_list_refuses(self, shadow, root):
        _write(root, "version: 1\ndenylist: nope\n")
        assert shadow.captain_exception(READ, "cos") is not None

    def test_symlink_refuses(self, shadow, root, tmp_path):
        """A symlink at the control-surface path is broken, not absent. Without
        this, `ln -sf /dev/null <path>` silently erases every Captain exclusion
        and leaves no error — erasure must be loud."""
        real = tmp_path / "elsewhere.yml"
        real.write_text("version: 1\ndenylist: []\n", encoding="utf-8")
        link = root / "instance" / "config" / "authority-exceptions.yml"
        link.symlink_to(real)
        reason = shadow.captain_exception(READ, "cos")
        assert reason is not None
        assert "symlink" in reason

    def test_dangling_symlink_refuses(self, shadow, root, tmp_path):
        link = root / "instance" / "config" / "authority-exceptions.yml"
        link.symlink_to(tmp_path / "does-not-exist.yml")
        assert shadow.captain_exception(READ, "cos") is not None

    def test_directory_refuses(self, shadow, root):
        (root / "instance" / "config" / "authority-exceptions.yml").mkdir()
        reason = shadow.captain_exception(READ, "cos")
        assert reason is not None
        assert "regular file" in reason

    def test_row_without_id_refuses(self, shadow, root):
        _write(root, "version: 1\ndenylist:\n  - command_contains: rm\n")
        assert shadow.captain_exception(READ, "cos") is not None

    @pytest.mark.parametrize("value", ['["echo hello"]', "true", "42", "{a: 1}", '""'])
    def test_non_string_predicate_is_a_load_error(self, shadow, root, value):
        """A list is the natural YAML for "any of these" — and
        `str(["echo hello"]).lower()` is never a substring of a command, so the
        row would load clean and never fire while the Captain believed the deny
        was live. Same rule as the predicate-LESS check, on predicate VALUES."""
        _write(root, f"""
            version: 1
            denylist:
              - id: typed-wrong
                why: "a list looks like 'any of these'"
                command_contains: {value}
        """)
        reason = shadow.captain_exception(BASH, "cos")
        assert reason is not None
        assert "captain_exceptions_malformed" in reason
        assert "must be a non-empty string" in reason

    def test_unknown_action_type_is_a_load_error(self, shadow, root):
        """An action_type outside the classifier enum can never match. Fail at
        LOAD, naming the typo — at match time it is indistinguishable from
        "no call was of that type"."""
        _write(root, """
            version: 1
            denylist:
              - id: typo
                why: "fat-fingered the enum"
                action_type: vercel_deploy_production
        """)
        reason = shadow.captain_exception(BASH, "cos")
        assert reason is not None
        assert "is not a known action type" in reason

    def test_known_action_type_still_loads(self, shadow, root):
        _write(root, """
            version: 1
            denylist:
              - id: fine
                why: "real enum member"
                action_type: git_push_main
        """)
        assert shadow.captain_exception(
            {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}},
            "cto") is not None

    def test_non_string_id_is_a_load_error(self, shadow, root):
        _write(root, "version: 1\ndenylist:\n  - id: {a: 1}\n    command_contains: rm\n")
        reason = shadow.captain_exception(READ, "cos")
        assert reason is not None
        assert "no string id" in reason

    def test_predicateless_row_is_a_load_error_not_a_wildcard(self, shadow, root):
        """A row with no predicate would deny every call. That reads like a typo
        and behaves like an outage, so it must be rejected AS AN ERROR — and the
        refusal must say so, not masquerade as a deliberate Captain exclusion."""
        _write(root, """
            version: 1
            denylist:
              - id: oops
                why: "forgot the predicate"
        """)
        reason = shadow.captain_exception(READ, "cos")
        assert reason is not None
        assert "captain_exceptions_malformed" in reason
        assert "no predicate" in reason
        assert not reason.startswith("captain_exception:oops")


class TestDecisionWiring:
    """The surface is wired into the decision the live hook actually reads."""

    def test_decision_blocks_on_a_matching_row(self, shadow, root):
        _write(root, """
            version: 1
            denylist:
              - id: no-prod-deploys
                why: "I ship production myself."
                command_contains: "vercel deploy --prod"
        """)
        res = shadow.decision(BASH)
        assert res["decision"] == "block"
        assert "captain_exception:no-prod-deploys" in res["reason"]
        assert res["policy_version"] == "shadow-v1", "shape unchanged for the hook"

    def test_decision_allows_when_no_row_matches(self, shadow, root):
        _write(root, """
            version: 1
            denylist:
              - id: unrelated
                why: "something else"
                command_contains: "terraform apply"
        """)
        assert shadow.decision(BASH)["decision"] == "allow"

    def test_exception_cannot_widen_a_typed_block(self, shadow, monkeypatch):
        """DENY-ONLY, proven: with the real policy stack loaded, a call the typed
        engine blocks stays blocked. There is no syntax here that permits
        anything."""
        monkeypatch.setenv("CABINET_ROOT", str(_REPO_ROOT))
        monkeypatch.delenv("OFFICER", raising=False)
        res = shadow.decision({
            "tool_name": "Bash",
            "tool_input": {"command": "vercel deploy --prod"},
        })
        assert res["decision"] == "block"
        # The reason is the TYPED policy's — the repo ships NO live denylist,
        # so nothing here can have come from the Captain surface.
        assert "captain_exception" not in res["reason"]


class TestWhatShips:
    def test_no_live_denylist_ships(self):
        """ABSENT is the ruled posture and is identical in behaviour to an empty
        file, so the repo ships only the .example. Shipping the live file would
        (a) need an egg-manifest materialize transform to survive the export and
        (b) turn a missing-PyYAML degradation into a total estate halt, since the
        loader would then reach `import yaml` on every call."""
        assert not (_REPO_ROOT / "instance" / "config" /
                    "authority-exceptions.yml").exists()

    def test_example_ships_and_is_the_empty_posture(self):
        import yaml

        path = _REPO_ROOT / "instance" / "config" / "authority-exceptions.yml.example"
        assert path.is_file(), "the Captain-facing template must ship"
        assert yaml.safe_load(path.read_text(encoding="utf-8"))["denylist"] == []
