"""Tests for the Hatch Cabinet.app thin shell (HATCH-APPSHELL-V05, Wave D).

Two halves:

1. claims-lint contract (no toolchain needed): the eleven forbidden
   WORLD-ONBOARDING-V1B claim strings (spec section 0) must each be CAUGHT by
   cabinet/scripts/appshell/claims-lint.sh — verbatim forms plus the spec's
   ASCII/wording variants (14 planted docs in all), case-insensitively, with
   file:line + pattern id named in the output. The single allowed markdown
   fence must pass; a fence in a non-markdown file must NOT be honored; an
   UNTERMINATED fence is itself a violation and disables stripping
   (fail-closed — the adversarial fix pass closed the fail-open bypass where
   an unclosed fence blanked every line below it); more than one fence per
   file is a violation; the real runbook and every appshell source must lint
   clean. This pins the under-enforcement gap flagged in adversarial review:
   a planted violation MUST fail the lint, proven by fixture.

2. builder contract (skipped when swiftc is absent — the builder is a
   dev-Mac tool by doctrine; hatch targets never compile anything): one real
   build into a pytest tmp dir, then bundle structure, plist fields, ad-hoc
   signature, payload sha256 == payload-info.json, headless stub smoke
   (HATCH_APP_SMOKE=1 -> unpack + engine --dry-run --defaults, exit 0), and
   the refuse-to-clobber re-run.

Every subprocess uses a fixed argv and an explicit timeout.

Run: python3.12 -m pytest cabinet/scripts/tests/test_appshell_build.py -q
"""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_APPSHELL = _SCRIPTS_DIR / "appshell"
_LINT = _APPSHELL / "claims-lint.sh"
_BUILDER = _APPSHELL / "build-hatch-app.sh"
_GATE = _APPSHELL / "appshell-gate.sh"
_RUNNER_IN = _APPSHELL / "hatch-run.command.in"
_RUNBOOK = _REPO_ROOT / "docs" / "runbooks" / "hatch-appshell-v05-2026-07-10.md"

_BUILD_TIMEOUT = 600  # fresh egg cut + swiftc; generous for cold runners
_SMOKE_TIMEOUT = 300
_LINT_TIMEOUT = 60

# Dev-Mac only: the builder needs xcrun/ditto/plutil/codesign beyond swiftc,
# so a bare `swiftc` on PATH is NOT enough — GitHub's ubuntu runners ship a
# Linux Swift toolchain that fooled the PATH-only probe and ran the builder
# to its honest exit 3 (master CI first exposure, 2026-07-10).
_HAVE_SWIFTC = sys.platform == "darwin" and shutil.which("swiftc") is not None

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _run(argv: list[str], timeout: int = _LINT_TIMEOUT, env: dict | None = None,
         cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv, capture_output=True, text=True, timeout=timeout,
        env=env, cwd=cwd,
    )


def _lint(*targets: Path) -> subprocess.CompletedProcess:
    return _run(["bash", str(_LINT), *[str(t) for t in targets]])


# ---------------------------------------------------------------------------
# 1) claims-lint: every forbidden claim is caught (the planted-violation proof)
# ---------------------------------------------------------------------------

# The eleven spec-section-0 strings verbatim, plus the spec's variants for F4
# (ASCII forms) and F11 (worded form). Each MUST make the lint exit non-zero
# and name the file, a line number, and the right pattern id.
_PLANTED = [
    ("F1", "the stranger path is ZERO Terminal, promised"),
    ("F2", "zero commands, zero ENTER, zero typing"),
    ("F3", "at most one native admin prompt on the way in"),
    ("F4", "hatched in ≤90 min wall-clock"),
    ("F4", "hatched in <=90 min flat"),
    ("F4", "done within 90 minutes end to end"),
    ("F5", "works for a non-technical captain, fresh macOS user account"),
    ("F6", "opens the living world and can never re-hatch"),
    ("F7", "zero hand-edits beyond documented steps"),
    ("F8", "the /api/hatch/* plane answers 410 after genesis"),
    ("F9", "the pipeline is byte-identical end to end"),
    ("F10", "full multi-cabinet support on one Mac"),
    ("F11", "a true 5-minute install"),
    ("F11", "a true five-minute install"),
]


@pytest.mark.parametrize("fid,text", _PLANTED, ids=[f"{fid}-{i}" for i, (fid, _) in enumerate(_PLANTED)])
def test_lint_catches_each_planted_violation(tmp_path: Path, fid: str, text: str) -> None:
    doc = tmp_path / "planted.md"
    doc.write_text(f"# scratch doc\n\nSome honest sentence first.\nThen: {text}\n")
    res = _lint(doc)
    assert res.returncode == 1, (
        f"lint MUST fail on planted {fid} ({text!r}); rc={res.returncode} out={res.stdout} err={res.stderr}"
    )
    # names file:line and the correct pattern id (line 4 of the doc)
    assert re.search(rf"planted\.md:4: {fid}: ", res.stdout), (
        f"expected 'planted.md:4: {fid}: ' in output, got: {res.stdout}"
    )


def test_lint_is_case_insensitive(tmp_path: Path) -> None:
    doc = tmp_path / "case.md"
    doc.write_text("ZeRo TeRmInAl\nMULTI-CABINET\nByte-Identical\n")
    res = _lint(doc)
    assert res.returncode == 1
    for fid, lineno in (("F1", 1), ("F10", 2), ("F9", 3)):
        assert re.search(rf"case\.md:{lineno}: {fid}: ", res.stdout), res.stdout


def test_lint_fence_allows_quoting_in_markdown(tmp_path: Path) -> None:
    doc = tmp_path / "fenced.md"
    fenced = "\n".join(text for _, text in _PLANTED)
    doc.write_text(
        "# doc with the single allowed fence\n\n"
        "```forbidden-claims\n" + fenced + "\n```\n\nClean text after the fence.\n"
    )
    res = _lint(doc)
    assert res.returncode == 0, f"fenced quotes must pass: {res.stdout}{res.stderr}"


def test_lint_violation_outside_fence_still_fails(tmp_path: Path) -> None:
    doc = tmp_path / "mixed.md"
    doc.write_text(
        "```forbidden-claims\nzero commands, zero ENTER, zero typing\n```\n"
        "But outside the fence: byte-identical.\n"
    )
    res = _lint(doc)
    assert res.returncode == 1
    assert re.search(r"mixed\.md:4: F9: ", res.stdout), res.stdout


def test_lint_fence_not_honored_in_non_markdown(tmp_path: Path) -> None:
    # Non-markdown sources get no fence: the strings must not appear at all.
    doc = tmp_path / "sneaky.sh"
    doc.write_text("#!/bin/bash\n# ```forbidden-claims\n# byte-identical\n# ```\n")
    res = _lint(doc)
    assert res.returncode == 1
    assert ": F9: " in res.stdout, res.stdout


def test_lint_unterminated_fence_fails_closed(tmp_path: Path) -> None:
    # Adversarial fix (2026-07-10): an unclosed fence used to leave the strip
    # flag set, blanking EVERY line below it — a silent fail-open bypass of
    # the wave's primary honesty gate. It must now (a) be reported as a
    # violation itself and (b) disable stripping for the file, so violations
    # below (and inside) the broken fence are still individually caught.
    doc = tmp_path / "unclosed.md"
    doc.write_text(
        "# doc with a broken fence\n\n"
        "```forbidden-claims\n"
        "zero commands, zero ENTER, zero typing\n"
        "the fence above is never closed\n"
        "sneaky claim below: byte-identical\n"
    )
    res = _lint(doc)
    assert res.returncode == 1, (
        f"unclosed fence must fail the lint: rc={res.returncode} out={res.stdout} err={res.stderr}"
    )
    assert re.search(r"unclosed\.md:3: FENCE: unterminated", res.stdout), res.stdout
    # fail-closed: the violation below the broken fence is still named
    assert re.search(r"unclosed\.md:6: F9: ", res.stdout), res.stdout
    # ... and so is the one inside it (stripping is disabled wholesale)
    assert re.search(r"unclosed\.md:4: F2: ", res.stdout), res.stdout


def test_lint_more_than_one_fence_is_a_violation(tmp_path: Path) -> None:
    # The contract allows exactly ONE forbidden-claims block per markdown
    # file (spec section 0 writer's rule / section 8).
    doc = tmp_path / "twofences.md"
    doc.write_text(
        "```forbidden-claims\nbyte-identical\n```\n"
        "honest middle text\n"
        "```forbidden-claims\nmulti-cabinet\n```\n"
    )
    res = _lint(doc)
    assert res.returncode == 1
    assert re.search(r"twofences\.md:5: FENCE: more than one", res.stdout), res.stdout


def test_lint_ordinary_code_blocks_untouched(tmp_path: Path) -> None:
    # Regular ```lang blocks are not forbidden-claims fences: they neither
    # strip content nor trip the fence-structure guard.
    doc = tmp_path / "codeblocks.md"
    doc.write_text(
        "# honest doc\n\n```bash\necho build\n```\n\n"
        "```forbidden-claims\nbyte-identical\n```\n\nclean tail\n"
    )
    res = _lint(doc)
    assert res.returncode == 0, f"{res.stdout}{res.stderr}"


def test_lint_clean_doc_passes(tmp_path: Path) -> None:
    doc = tmp_path / "clean.md"
    doc.write_text(
        "# honest doc\n\nDouble-clickable entry to the technical-captain face.\n"
        "First receipt in minutes once hatched. Single-install only.\n"
    )
    res = _lint(doc)
    assert res.returncode == 0, f"{res.stdout}{res.stderr}"


def test_lint_no_args_is_usage_error_not_a_verdict() -> None:
    # No targets => usage error rc=2 on stderr, distinct from the lint
    # verdict codes (0 clean / 1 violations). The file:line:id output format
    # itself is pinned per planted case in
    # test_lint_catches_each_planted_violation. (Renamed in the fix pass —
    # the old name claimed format coverage this body never had.)
    res = _run(["bash", str(_LINT)])
    assert res.returncode == 2
    assert "usage:" in res.stderr


def test_lint_real_runbook_and_appshell_sources_clean() -> None:
    assert _RUNBOOK.is_file(), f"runbook missing: {_RUNBOOK}"
    targets = [_RUNBOOK] + sorted(p for p in _APPSHELL.iterdir() if p.is_file())
    res = _lint(*targets)
    assert res.returncode == 0, (
        f"forbidden claim leaked into shell sources or runbook:\n{res.stdout}{res.stderr}"
    )


# ---------------------------------------------------------------------------
# shell-source hygiene (mechanical guards)
# ---------------------------------------------------------------------------


def test_bash_syntax_clean() -> None:
    for script in (_BUILDER, _GATE, _LINT, _RUNNER_IN):
        res = _run(["bash", "-n", str(script)])
        assert res.returncode == 0, f"bash -n failed for {script}: {res.stderr}"


def test_no_osascript_or_applescript_in_shell_sources() -> None:
    # Hard rule: handoff is Launch Services only. No Apple-events automation.
    for src in sorted(_APPSHELL.iterdir()):
        if not src.is_file():
            continue
        text = src.read_text(encoding="utf-8", errors="replace").lower()
        assert "osascript" not in text, f"osascript reference in {src}"
        assert "applescript" not in text, f"AppleScript reference in {src}"
        assert "nsapplescript" not in text, f"NSAppleScript reference in {src}"


def test_no_dead_dashboard_env_names_anywhere() -> None:
    # OC-LOOPBACK standing constraint: only CABINET_DASHBOARD_HOST is the
    # canonical name (owned by the APP-FEEL area); the dead names must appear
    # nowhere. Built by concatenation so THIS file never contains them either.
    dead = ["CABINET_DASHBOARD_" + "BIND", "CABINET_DASHBOARD_" + "HOSTNAME"]
    targets = [p for p in sorted(_APPSHELL.iterdir()) if p.is_file()] + [_RUNBOOK]
    for src in targets:
        text = src.read_text(encoding="utf-8", errors="replace")
        for name in dead:
            assert name not in text, f"dead env name {name} in {src}"


def _code_lines(src: Path) -> str:
    """Source minus comment lines (comments may honestly DOCUMENT what the
    shell never does; the guard is about invocations in code)."""
    out = []
    for line in src.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        out.append(line)
    return "\n".join(out)


def test_shell_never_references_forbidden_actuators() -> None:
    # The shell never invokes the kill switch or the dashboard starter, and
    # performs no launchctl mutations itself (move-in belongs to the engine).
    for src in (_APPSHELL / "main.swift", _RUNNER_IN, _BUILDER, _GATE):
        code = _code_lines(src)
        assert "kill-switch" not in code, f"kill-switch reference in {src}"
        assert "start-dashboard" not in code, f"start-dashboard reference in {src}"
        assert "launchctl" not in code, f"launchctl call in {src}"


def test_manifest_excludes_appshell_once_tracked() -> None:
    # Belt-and-braces for the D4 sequencing contract (adversarial nit,
    # 2026-07-10): the appshell area is dev-side tooling that builds the
    # vehicle and never rides in it. The egg-manifest delete/expect-absent
    # rows are D4-owned and must land in the SAME commit that first tracks
    # these files — if the files are ever git-tracked WITHOUT the rows,
    # every future egg silently carries the dev tooling with no loud
    # failure. This makes the exclusion self-enforcing. Skips while the
    # files are untracked (pre-integration working tree) or outside git.
    res = _run(["git", "-C", str(_REPO_ROOT), "ls-files", "--",
                "cabinet/scripts/appshell/"])
    if res.returncode != 0:
        pytest.skip("not a git checkout (egg exports carry no .git)")
    if not res.stdout.strip():
        pytest.skip("appshell not git-tracked yet; the APPSHELL-V05 manifest "
                    "rows land with the tracking commit (D4)")
    manifest = (_SCRIPTS_DIR / "egg-export-manifest.txt").read_text(encoding="utf-8")
    for directive in ("delete", "expect-absent"):
        for path in ("cabinet/scripts/appshell",
                     "cabinet/scripts/tests/test_appshell_build.py",
                     "docs/runbooks/hatch-appshell-v05-2026-07-10.md"):
            assert re.search(rf"^{directive} {re.escape(path)}(\s|$)", manifest, re.M), (
                f"appshell is git-tracked but egg-export-manifest.txt lacks "
                f"'{directive} {path}' — dev tooling would ride every future "
                f"egg (APPSHELL-V05 exclusion contract, spec section 4)"
            )


# ---------------------------------------------------------------------------
# 2) builder contract (dev-Mac only; skipped without swiftc)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built_app(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not _HAVE_SWIFTC:
        pytest.skip("swiftc not available — builder is a dev-Mac tool (targets never compile)")
    out = tmp_path_factory.mktemp("hatch-app-dist")
    res = _run(["bash", str(_BUILDER), "--out", str(out)],
               timeout=_BUILD_TIMEOUT, cwd=_REPO_ROOT)
    assert res.returncode == 0, f"builder failed:\n{res.stdout}\n{res.stderr}"
    app = out / "Hatch Cabinet.app"
    assert app.is_dir(), f"no bundle at {app}"
    return app


def test_bundle_structure(built_app: Path) -> None:
    stub = built_app / "Contents" / "MacOS" / "HatchCabinet"
    runner = built_app / "Contents" / "Resources" / "hatch-run.command"
    zip_ = built_app / "Contents" / "Resources" / "payload" / "cabinet-egg.zip"
    info = built_app / "Contents" / "Resources" / "payload" / "payload-info.json"
    plist = built_app / "Contents" / "Info.plist"
    for p in (stub, runner, zip_, info, plist):
        assert p.is_file(), f"missing bundle member: {p}"
    assert os.access(stub, os.X_OK), "stub not executable"
    assert os.access(runner, os.X_OK), "runner not executable"
    # signature seal present (explicit ad-hoc bundle signing)
    assert (built_app / "Contents" / "_CodeSignature").is_dir(), "bundle unsealed"


def test_info_plist_contract(built_app: Path) -> None:
    plist_path = built_app / "Contents" / "Info.plist"
    res = _run(["/usr/bin/plutil", "-lint", str(plist_path)])
    assert res.returncode == 0, res.stdout + res.stderr
    with plist_path.open("rb") as fh:
        plist = plistlib.load(fh)
    assert plist["CFBundleIdentifier"] == "org.captainscabinet.hatch"
    assert plist["CFBundleShortVersionString"] == "0.5.1"
    assert plist["LSMinimumSystemVersion"] == "14.0"
    assert plist["CFBundleExecutable"] == "HatchCabinet"
    # template placeholders must be rendered away
    assert "@" not in plist["CFBundleVersion"]
    assert "@" not in plist["CabinetBuildUTC"]


def test_runner_rendered_without_placeholders(built_app: Path) -> None:
    runner = built_app / "Contents" / "Resources" / "hatch-run.command"
    text = runner.read_text(encoding="utf-8")
    assert "@APP_VERSION@" not in text and "@BUILD_UTC@" not in text
    res = _run(["bash", "-n", str(runner)])
    assert res.returncode == 0, res.stderr


def test_codesign_verifies(built_app: Path) -> None:
    res = _run(["/usr/bin/codesign", "--verify", "--strict", str(built_app)])
    assert res.returncode == 0, f"codesign verify failed: {res.stderr}"


def test_payload_sha_matches_payload_info(built_app: Path) -> None:
    payload_dir = built_app / "Contents" / "Resources" / "payload"
    info = json.loads((payload_dir / "payload-info.json").read_text())
    digest = hashlib.sha256((payload_dir / "cabinet-egg.zip").read_bytes()).hexdigest()
    assert info["payload_sha256"] == digest
    assert re.fullmatch(r"[0-9a-f]{40}", info["source_head"]), info["source_head"]
    assert re.fullmatch(r"[0-9a-f]{64}", info["egg_manifest_sha256"])
    assert info["source_branch"], "empty source_branch"
    assert info["app_version"] == "0.5.1"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", info["built_utc"])
    assert int(info["egg_file_count"]) > 0


def test_headless_smoke_then_refuses_to_clobber(built_app: Path, tmp_path: Path) -> None:
    stub = built_app / "Contents" / "MacOS" / "HatchCabinet"
    prefix = tmp_path / "prefix"
    env = {**os.environ, "HATCH_APP_SMOKE": "1", "CABINET_HATCH_PREFIX": str(prefix)}
    res = _run([str(stub)], timeout=_SMOKE_TIMEOUT, env=env)
    assert res.returncode == 0, f"smoke failed:\n{res.stdout}\n{res.stderr}"
    assert (prefix / "cabinet" / "scripts" / "hatch.sh").is_file(), "payload not unpacked"
    runner = prefix / "hatch-run.command"
    assert runner.is_file() and os.access(runner, os.X_OK), "runner not installed in prefix"
    assert not (prefix / ".hatch-run-args").exists(), "smoke must not write a runner request"
    # dry-run prints the plan; make sure the engine actually spoke
    assert "dry" in res.stdout.lower() or "plan" in res.stdout.lower(), res.stdout[-2000:]
    # second run over the now-populated prefix must refuse (never clobber)
    res2 = _run([str(stub)], timeout=_SMOKE_TIMEOUT, env=env)
    assert res2.returncode != 0, "stub must refuse a non-empty prefix"
    assert "refus" in (res2.stderr + res2.stdout).lower(), res2.stderr
