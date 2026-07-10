"""SOV-8 dark-lane tests — gate-apply.sh + com.cabinet.gate-apply.plist.

Pins D15's structural guarantees:
  * the plist is DARK: Disabled=true, RunAtLoad=false, and NO setup script
    references it (the dark grep);
  * gate-apply.sh contains no root pytest and disables git hooks on every
    apply;
  * the refusal paths (forged pack, Ring-0 diff, missing sandbox, unlocked
    posture) all refuse via CABINET_GATE_APPLY_TEST=1 — no root needed.
"""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

SCRIPT = _REPO / "cabinet" / "scripts" / "gate-apply.sh"
PLIST = _REPO / "cabinet" / "launchd" / "com.cabinet.gate-apply.plist"
LABEL = "com.cabinet.gate-apply"


# ---------------------------------------------------------------------------
# DARK: plist disabled + loaded by no setup script
# ---------------------------------------------------------------------------

class TestPlistDark:
    def test_plist_exists_and_is_disabled(self):
        with open(PLIST, "rb") as fh:
            data = plistlib.load(fh)
        assert data["Label"] == LABEL
        assert data["Disabled"] is True
        assert data["RunAtLoad"] is False

    def test_no_setup_script_references_the_label(self):
        """The dark grep: no script under cabinet/scripts or cabinet/cron —
        and no launchd install doc — may mention the label. Only the plist
        itself, the runbook, tests, and the sovereign spec may."""
        offenders = []
        roots = [
            _REPO / "cabinet" / "scripts",
            _REPO / "cabinet" / "cron",
            _REPO / "cabinet" / "launchd" / "INSTALL-flip.md",
        ]
        allowed = {
            SCRIPT.resolve(),  # the dark lane itself documents its label
            # Germline ENFORCEMENT lists (SOV-9a): these must NAME the plist
            # to schg-lock / hook-block it — naming is not loading, and the
            # launchctl-load sweep below still covers both files.
            (_REPO / "cabinet" / "scripts" / "germline-lock.sh").resolve(),
            (_REPO / "cabinet" / "scripts" / "hooks" /
             "pre-tool-use.sh").resolve(),
            # Egg packaging rules (PC-E R160 launchd-portable-only + its
            # amendment): the manifest NAMES the plist to pin its packaging
            # rule, and the exporter NAMES it to rewrite the EXPORT COPY
            # portable-dark (source untouched, Disabled/RunAtLoad preserved).
            # Naming-for-packaging is anti-arming — neither file copies to
            # /Library/LaunchDaemons or bootstraps anything, neither ships
            # in the egg (self-exclusion delete rows), and the
            # launchctl-load sweep below still covers both.
            (_REPO / "cabinet" / "scripts" /
             "egg-export-manifest.txt").resolve(),
            (_REPO / "cabinet" / "scripts" / "egg-export.sh").resolve(),
            # ...and the pytest twin that PINS the portable-dark packaging
            # contract (tests may name the label per this test's docstring;
            # this one lives under cabinet/scripts/tests so the roots sweep
            # sees it). Also export-deleted, never ships.
            (_REPO / "cabinet" / "scripts" / "tests" /
             "test_egg_export.py").resolve(),
        }
        for root in roots:
            files = [root] if root.is_file() else (
                sorted(root.rglob("*")) if root.is_dir() else [])
            for f in files:
                if not f.is_file() or f.resolve() in allowed:
                    continue
                if "__pycache__" in f.parts or f.suffix == ".pyc":
                    # Compiled-bytecode twins are DERIVATIVE artifacts, not
                    # setup surfaces: running cabinet/scripts/tests writes
                    # __pycache__/test_egg_export*.pyc whose bytecode embeds
                    # the (allowlisted) source's label string, tripping this
                    # sweep only when the suites run in that order. The
                    # source .py files themselves are still swept above.
                    continue
                try:
                    text = f.read_text(errors="ignore")
                except OSError:
                    continue
                if LABEL in text:
                    offenders.append(str(f.relative_to(_REPO)))
        assert offenders == [], (
            f"dark daemon referenced by setup surface(s): {offenders}")

    def test_no_script_loads_the_plist(self):
        """No launchctl load/bootstrap of the label anywhere in the repo's
        shell scripts (the plist may only ever be armed by the Captain's
        hands, per the runbook)."""
        pattern = re.compile(r"launchctl\s+(load|bootstrap).*gate-apply")
        offenders = []
        for f in sorted((_REPO / "cabinet").rglob("*.sh")):
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue  # comments/docs may cite the Captain ritual
                if pattern.search(stripped):
                    offenders.append(str(f.relative_to(_REPO)))
        assert offenders == []


# ---------------------------------------------------------------------------
# Script text invariants — no root pytest, hooks disabled
# ---------------------------------------------------------------------------

class TestScriptInvariants:
    def test_no_root_pytest(self):
        text = SCRIPT.read_text()
        for line in text.splitlines():
            if "pytest" in line and not line.strip().startswith("#"):
                assert "sudo" not in line, f"root pytest: {line!r}"
        # and the verify path structurally refuses/drops root
        assert 'refuse "verify must not run as root' in text
        assert 'sudo -u "$VERIFY_USER"' in text

    def test_every_git_apply_disables_hooks(self):
        # every git-apply INVOCATION (command position: line-start, `&&`,
        # `||`, `;`, `(`, or `|`) must disable hooks; log strings are exempt.
        invocation = re.compile(r"(?:^|&&|\|\||;|\(|\|)\s*git\s+.*\bapply\b")
        text = SCRIPT.read_text()
        checked = 0
        for line in text.splitlines():
            if line.strip().startswith("#"):
                continue
            if invocation.search(line):
                assert "core.hooksPath=/dev/null" in line, line
                checked += 1
        assert checked >= 3  # verify (check+apply) + apply (check+apply) + watch -R

    def test_apply_reads_ring0_from_live_tree_not_bundle(self):
        text = SCRIPT.read_text()
        assert 'LIVE_ROOT/framework/policies/immutable-core.yml' in text
        # and never resolves the enumeration out of the pack dir
        assert not re.search(r"packdir[^\n]*immutable-core", text)


# ---------------------------------------------------------------------------
# Functional refusals (CABINET_GATE_APPLY_TEST=1 — no root, no mutation)
# ---------------------------------------------------------------------------

def _run(args, **env):
    full_env = {**os.environ, "CABINET_GATE_APPLY_TEST": "1", **env}
    return subprocess.run(
        ["/bin/bash", str(SCRIPT), *args],
        capture_output=True, text=True, env=full_env, timeout=120)


def _mk_pack(tmp_path, diff, *, sha=None, verdict="pass"):
    packdir = tmp_path / "pack"
    packdir.mkdir(parents=True, exist_ok=True)
    (packdir / "bundle.patch").write_text(diff)
    real = hashlib.sha256(diff.encode()).hexdigest()
    (packdir / "pack.json").write_text(json.dumps({
        "pack_id": f"pack-{real[:16]}", "verdict": verdict,
        "sha256": sha if sha is not None else real}))
    return packdir


_CLEAN_DIFF = ("diff --git a/framework/learning/x.py b/framework/learning/x.py\n"
               "--- a/framework/learning/x.py\n+++ b/framework/learning/x.py\n"
               "@@ -1 +1 @@\n-a\n+b\n")
_RING0_DIFF = ("diff --git a/framework/authority/matrix.py "
               "b/framework/authority/matrix.py\n"
               "--- a/framework/authority/matrix.py\n"
               "+++ b/framework/authority/matrix.py\n"
               "@@ -1 +1 @@\n-a\n+b\n")


class TestRefusals:
    def test_verify_refuses_forged_pack(self, tmp_path):
        packdir = _mk_pack(tmp_path, _CLEAN_DIFF, sha="0" * 64)
        cp = _run(["verify", str(packdir)])
        assert cp.returncode == 2
        assert "forged pack" in cp.stderr

    def test_verify_refuses_non_pass_verdict(self, tmp_path):
        packdir = _mk_pack(tmp_path, _CLEAN_DIFF, verdict="fail")
        cp = _run(["verify", str(packdir)])
        assert cp.returncode == 2 and "not pass" in cp.stderr

    def test_verify_refuses_ring0_diff(self, tmp_path):
        packdir = _mk_pack(tmp_path, _RING0_DIFF)
        cp = _run(["verify", str(packdir)])
        assert cp.returncode == 2
        assert "Ring-0" in cp.stderr

    def test_verify_fails_closed_without_sandbox_workdir(self, tmp_path):
        packdir = _mk_pack(tmp_path, _CLEAN_DIFF)
        cp = _run(["verify", str(packdir)])
        assert cp.returncode == 2
        assert "sandbox harness not built" in cp.stderr

    def test_apply_refuses_live_repo_in_test_mode(self, tmp_path):
        packdir = _mk_pack(tmp_path, _CLEAN_DIFF)
        cp = _run(["apply", str(packdir)])
        assert cp.returncode == 2
        assert "scratch" in cp.stderr

    def test_apply_refuses_absent_posture(self, tmp_path):
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        packdir = _mk_pack(tmp_path, _CLEAN_DIFF)
        cp = _run(["apply", str(packdir)],
                  CABINET_GATE_APPLY_ROOT=str(scratch))
        assert cp.returncode == 2
        assert "posture.yml absent" in cp.stderr

    def test_apply_refuses_unlocked_posture(self, tmp_path):
        scratch = tmp_path / "scratch"
        (scratch / "instance" / "config").mkdir(parents=True)
        (scratch / "instance" / "config" / "posture.yml").write_text(
            "version: 1\nposture: sovereign\n")
        packdir = _mk_pack(tmp_path, _CLEAN_DIFF)
        cp = _run(["apply", str(packdir)],
                  CABINET_GATE_APPLY_ROOT=str(scratch))
        assert cp.returncode == 2
        assert "not schg-locked" in cp.stderr

    def test_missing_pack_dir_refuses(self, tmp_path):
        cp = _run(["verify", str(tmp_path / "ghost")])
        assert cp.returncode == 2 and "not found" in cp.stderr

    def test_unknown_subcommand_usage(self):
        cp = _run(["florble"])
        assert cp.returncode == 2 and "usage" in cp.stderr
