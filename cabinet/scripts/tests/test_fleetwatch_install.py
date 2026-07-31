"""Fleet dead-man installer tests.

These run on the CI runner, which is ubuntu. That is the point: the installer is
Python precisely so it is not left to `bash -n`, which parses a script and
executes nothing. The only step this file does NOT cover is `launchctl
bootstrap`, and it does not cover it because the installer deliberately does not
perform it — installing a LaunchAgent is a human act on someone's machine.

SANDBOX RULE: every write is steered by an explicit --output-dir under tmp_path
and asserted to land there. Nothing here can reach ~/Library/LaunchAgents.
"""
from __future__ import annotations

import importlib.util
import os
import plistlib

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))          # cabinet/scripts/tests
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))  # repo root
_SPEC = importlib.util.spec_from_file_location(
    "fleetwatch_install", os.path.join(_ROOT, "cabinet/scripts/fleetwatch-install.py"))
fwi = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fwi)


def _values(tmp_path):
    return fwi.default_values("/repo", str(tmp_path / "home"), "someone")


def test_render_substitutes_every_placeholder(tmp_path):
    out = fwi.render("a=${REPO_ROOT} b=${HOME} c=${USER}", _values(tmp_path))
    assert "${" not in out
    assert "/repo" in out and "someone" in out


def test_render_refuses_a_placeholder_it_was_given_no_value_for():
    """A half-rendered plist is worse than none: launchd loads it happily and
    then never works, at a path nobody can explain."""
    with pytest.raises(KeyError):
        fwi.render("x=${NOT_SUPPLIED}", {"REPO_ROOT": "/r"})


def test_the_shipped_template_renders_and_validates(tmp_path):
    with open(os.path.join(_ROOT, "cabinet/launchd",
                           f"{fwi.LABEL}.template.plist"), encoding="utf-8") as fh:
        tpl = fh.read()
    obj = fwi.validate(fwi.render(tpl, _values(tmp_path)))
    assert obj["Label"] == fwi.LABEL
    assert obj["StartInterval"] > 0
    assert obj["ProgramArguments"][-1] == "framework.liveness.fleetwatch"


def test_validate_rejects_a_com_cabinet_label(tmp_path):
    """THE invariant. A watcher inside `com.cabinet.*` is removed by the same
    command that removed the fleet on 2026-07-25 — the exact event it exists to
    survive. If someone ever 'tidies' the label into the fleet's namespace, this
    goes red."""
    with open(os.path.join(_ROOT, "cabinet/launchd",
                           f"{fwi.LABEL}.template.plist"), encoding="utf-8") as fh:
        tpl = fh.read()
    hijacked = fwi.render(tpl, _values(tmp_path)).replace(
        f"<string>{fwi.LABEL}</string>",
        "<string>com.cabinet.fleetwatch</string>", 1)
    with pytest.raises(ValueError):
        fwi.validate(hijacked)


def test_validate_rejects_a_schedule_free_agent(tmp_path):
    with open(os.path.join(_ROOT, "cabinet/launchd",
                           f"{fwi.LABEL}.template.plist"), encoding="utf-8") as fh:
        tpl = fh.read()
    rendered = fwi.render(tpl, _values(tmp_path))
    obj = plistlib.loads(rendered.encode())
    del obj["StartInterval"]
    with pytest.raises(ValueError):
        fwi.validate(plistlib.dumps(obj).decode())


def test_main_writes_only_where_it_was_told(tmp_path):
    out = tmp_path / "staged"
    rc = fwi.main(["--repo-root", _ROOT, "--output-dir", str(out)])
    assert rc == 0
    dest = fwi.destination(str(out))
    assert os.path.exists(dest)
    assert dest.startswith(str(tmp_path)), "sandbox escape"
    assert not os.path.exists(os.path.expanduser(
        f"~/Library/LaunchAgents/{fwi.LABEL}.plist"))


def test_install_and_output_dir_are_mutually_exclusive(tmp_path):
    assert fwi.main(["--repo-root", _ROOT, "--install",
                     "--output-dir", str(tmp_path)]) == 2


def test_default_run_writes_nothing(tmp_path, capsys):
    rc = fwi.main(["--repo-root", _ROOT])
    assert rc == 0
    assert "<plist" in capsys.readouterr().out
    assert not os.path.exists(fwi.destination(str(tmp_path)))


def test_installer_never_executes_launchctl():
    """The install is handed back to a human on purpose. If that ever changes it
    changes deliberately, and this goes red first.

    Asserted over the AST, not over the source text: a substring search would be
    satisfied by the word appearing in a docstring (it does, several times) and
    would therefore pass whatever the code did — a sensor testing something
    other than the control, which is this program's most-paid defect class."""
    import ast

    with open(os.path.join(_ROOT, "cabinet/scripts/fleetwatch-install.py"),
              encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    # Only PROCESS-SPAWNING calls are in scope. `print("launchctl bootstrap …")`
    # is the whole design — the commands are handed to a human — so a blanket
    # substring rule would either fail on the correct behaviour or have to be
    # loosened until it caught nothing.
    _EXEC = ("run", "call", "check_call", "check_output", "Popen", "system",
             "popen", "execv", "execvp", "execve", "spawnv", "spawnl")

    def spawns(tree_):
        hits = []
        for node in ast.walk(tree_):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name not in _EXEC:
                continue
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                for lit in ast.walk(arg):
                    if isinstance(lit, ast.Constant) and isinstance(lit.value, str) \
                            and "launchctl" in lit.value:
                        hits.append(lit.value)
        return hits

    assert spawns(tree) == [], \
        f"a process-spawning call carries launchctl: {spawns(tree)}"

    # The guard on the guard: this detector must be able to SEE such a call, or
    # it is a green that proves nothing.
    assert spawns(ast.parse('subprocess.run(["launchctl", "bootstrap", p])')), \
        "the detector cannot detect the thing it is looking for"
    # NOTE: the two strings above are PARSED, never executed — ast.parse builds
    # a syntax tree and runs nothing. They are fixtures proving the detector
    # sees both the argv form and the shell form; neither is a live sink.
    assert spawns(ast.parse('os.system("launchctl bootstrap x")')), \
        "the detector misses the shell form"


def test_under_rejects_a_path_that_escapes_its_root(tmp_path):
    assert fwi.under(str(tmp_path / "a" / "b"), str(tmp_path)) is True
    assert fwi.under("/etc/passwd", str(tmp_path)) is False
    assert fwi.under(str(tmp_path) + "-sibling", str(tmp_path)) is False
