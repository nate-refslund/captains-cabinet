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
_APP_VERSION = "0.6.0"

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


def test_no_apple_events_in_the_handoff_sources() -> None:
    # THE HANDOFF RULE, UNCHANGED: the .app stub reaches Terminal through
    # Launch Services and sends it no Apple events. One app driving another is
    # exactly the pairing macOS puts an automation consent prompt in front of,
    # and the runbook's per-target check is that no such prompt appears.
    #
    # The RUNNER TEMPLATE is the one deliberate exception (2026-08-13), and it
    # is not an exception to the rule above: the runner is already INSIDE the
    # Terminal window it closes, so its close is Terminal addressing itself —
    # a self-send, which macOS exempts from the consent prompt (measured on
    # macOS 27: the window closed, no prompt, no automation decision logged).
    # Proving the runner safe by ABSENCE would have been the weaker guard
    # anyway; the two tests below pin the properties that actually matter
    # (hatched-only, own window, by validated id) instead.
    #
    # Every other file in the area — including any added later — stays in
    # scope, which is why this iterates the directory rather than a list.
    for src in sorted(_APPSHELL.iterdir()):
        if not src.is_file() or src == _RUNNER_IN:
            continue
        text = src.read_text(encoding="utf-8", errors="replace").lower()
        assert "osascript" not in text, f"osascript reference in {src}"
        assert "applescript" not in text, f"AppleScript reference in {src}"
        assert "nsapplescript" not in text, f"NSAppleScript reference in {src}"


# ---------------------------------------------------------------------------
# the end-of-run goodbye + the auto-close (2026-08-13)
# ---------------------------------------------------------------------------
#
# From a live operator run: the notice ended, the window sat on "[Process
# completed]", and the operator did not know it was finished with or that it
# was theirs to close. Two answers ship — a sign-off printed on every path,
# and a self-close on the paths that actually hatched.
#
# WHAT THESE TESTS PROVE, and what they cannot: the behavioural test below
# runs the SHIPPED bytes of the notice block (sliced out of the template at
# the engine's own `RC=$?` line, so it exercises the real thing rather than a
# copy) and pins which sign-off each disposition prints and that the exit code
# survives. The static test pins that the close is gated on the SAME flag and
# can only ever name one window, by a number this script resolved for its own
# tty. Neither can drive Terminal.app, so THE WINDOW ACTUALLY CLOSING is
# human-verified: measured by hand on macOS 27 (2026-08-13) — a hatched run's
# own window closed ~8s after exit, every other window untouched, and a failed
# run's window still open 23s later.


def _slice(template: str, name: str) -> str:
    """The block between the runner's own `# >>> NAME BEGIN` / `# <<< NAME END`
    markers. Explicit markers, not line numbers or a nearby literal: the tests
    below run the SHIPPED bytes of these blocks, and the slice has to stay
    honest as the file around them changes."""
    begin = f"# >>> {name} BEGIN"
    end = f"# <<< {name} END"
    assert begin in template and end in template, f"runner lost the {name} markers"
    body = template[template.index(begin):template.index(end)]
    assert body.strip(), f"the {name} block is empty"
    return body


def _notice_block(rc: int, tmp_path: Path) -> Path:
    """The runner's post-run notice — the shipped bytes — with the engine
    stubbed to exit ``rc``. The window-close block comes with it because the
    notice calls it; both are sliced from the template, neither is a copy."""
    template = _RUNNER_IN.read_text(encoding="utf-8")
    assert "RC=$?\n" in template, "runner no longer captures the engine's exit code"
    script = tmp_path / f"notice-{rc}.sh"
    script.write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        f'LOG_DIR="{tmp_path}/logs"\nmkdir -p "$LOG_DIR"\nRC={rc}\nHATCHED=0\n'
        + _slice(template, "WINDOW-CLOSE")
        + "\n"
        + _slice(template, "NOTICE")
    )
    script.chmod(0o755)
    return script


_SIGNOFF = "✅ All done — your Cabinet is open in your browser. You can close this window."
_STAY = "You can close this window once you have read the above."


@pytest.mark.parametrize("rc,hatched", [(0, True), (75, True), (1, False), (2, False)])
def test_notice_signs_off_on_every_path_and_keeps_the_exit_code(
    tmp_path: Path, rc: int, hatched: bool
) -> None:
    # Both dispositions that got the operator all the way in say the same
    # goodbye; anything else keeps its window and says so without claiming the
    # Cabinet is up. Exit 75 is hatched-with-a-caveat, never a failure.
    res = _run(["bash", str(_notice_block(rc, tmp_path))])
    assert res.returncode == rc, f"the notice must not swallow the exit code: {res}"
    if hatched:
        assert _SIGNOFF in res.stdout, res.stdout
        assert _STAY not in res.stdout, res.stdout
    else:
        assert _STAY in res.stdout, res.stdout
        assert _SIGNOFF not in res.stdout, res.stdout
    # No tty and no TERM_PROGRAM here (a pipe, as in CI): the close never arms,
    # on any disposition, and the sign-off still lands.
    assert "close itself" not in res.stdout, res.stdout


def test_autoclose_is_hatched_only_and_can_only_name_its_own_window() -> None:
    template = _RUNNER_IN.read_text(encoding="utf-8")
    code = _code_lines(_RUNNER_IN)
    # Inside the post-run notice, only the two dispositions that got the
    # operator all the way in arm anything. (Scoped to the notice on purpose:
    # the launcher branch legitimately sets the same flag when it lands them in
    # a browser, and a whole-file count would have to be raised for every new
    # branch — a number nobody could keep honest.)
    notice = _slice(template, "NOTICE")
    assert notice.count("HATCHED=1") == 2, "a third disposition in the notice counts as hatched"
    # Everything that sets it must be a branch that actually arrived: exactly
    # the two above plus the launcher's success leg.
    assert code.count("HATCHED=1") == 3, (
        "a branch started counting as hatched — every HATCHED=1 must be a path "
        "that put the operator in front of their Cabinet"
    )
    # …and the close hangs off that same flag, plus a real Terminal around us.
    assert (
        'if [ "$HATCHED" = "1" ] && [ -t 1 ] && [ "${TERM_PROGRAM:-}" = "Apple_Terminal" ]; then'
        in code
    ), "the auto-close guard changed shape"
    # ONE window, named by id. The blunt instruments must never appear.
    assert "close (every window whose id is $own_window)" in code
    for blunt in ("to quit", "close every window", "close front window",
                  "close first window", "close windows"):
        assert blunt not in code, f"unscoped Terminal command in the runner: {blunt}"
    # The id is the ONLY value interpolated into the closer, so it is a plain
    # number or it is nothing — anything else is dropped before it gets there.
    assert '\'\'|*[!0-9]*) own_window="" ;;' in code, "the window id is no longer validated"


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


def test_the_app_version_is_declared_once() -> None:
    """It used to live as a literal in Info.plist.in and as a variable in the
    builder; the two drifted the first time one of them moved."""
    plist_in = (_APPSHELL / "Info.plist.in").read_text(encoding="utf-8")
    assert "@APP_VERSION@" in plist_in
    assert _APP_VERSION not in plist_in, "the plist template hardcodes a version again"
    builder = _BUILDER.read_text(encoding="utf-8")
    assert f'APP_VERSION="{_APP_VERSION}"' in builder
    swift = (_APPSHELL / "main.swift").read_text(encoding="utf-8")
    assert f'let appVersion = "{_APP_VERSION}"' in swift, (
        "the stub's dialogs would name a different version than the bundle"
    )


def test_info_plist_contract(built_app: Path) -> None:
    plist_path = built_app / "Contents" / "Info.plist"
    res = _run(["/usr/bin/plutil", "-lint", str(plist_path)])
    assert res.returncode == 0, res.stdout + res.stderr
    with plist_path.open("rb") as fh:
        plist = plistlib.load(fh)
    assert plist["CFBundleIdentifier"] == "org.captainscabinet.hatch"
    assert plist["CFBundleShortVersionString"] == _APP_VERSION
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
    assert info["app_version"] == _APP_VERSION
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


# ---------------------------------------------------------------------------
# the app is a LAUNCHER (2026-08-25)
# ---------------------------------------------------------------------------
#
# THE MEASURED FAILURE. Second double-click over a healthy install: no
# message, no browser, a Terminal window whose only content was the shell's own
# teardown. Two causes, both fixed and both pinned below — there was no branch
# that OPENED the Cabinet at all (only a read-only check-over and Quit), and
# the branch there was `exec`ed its engine, so the runner's closing sentence
# could never run.
#
# WHAT THESE PROVE vs WHAT THEY CANNOT. The detection arms and the archive arm
# run the SHIPPED stub (dev-Mac only, like every other builder test); the
# runner arms run the SHIPPED template with stub engines. None of them can
# drive an NSAlert, so WHICH DIALOG APPEARS is human-verified — the static
# wiring tests below pin that only a finished cabinet can reach the launcher
# request, and that the start-over path has no delete call in it.

_STUB_ENGINES = ("hatch.sh", "open-cabinet.sh", "cabinet-doctor.sh")


def _fake_prefix(tmp_path: Path, *, engine_rc: dict[str, int] | None = None) -> Path:
    """A prefix holding the runner and stub engines that record and exit."""
    engine_rc = engine_rc or {}
    prefix = tmp_path / "prefix"
    (prefix / "cabinet" / "scripts").mkdir(parents=True, exist_ok=True)
    rendered = _RUNNER_IN.read_text(encoding="utf-8").replace(
        "@APP_VERSION@", "test").replace("@BUILD_UTC@", "test")
    runner = prefix / "hatch-run.command"
    runner.write_text(rendered, encoding="utf-8")
    runner.chmod(0o755)
    for name in _STUB_ENGINES:
        script = prefix / "cabinet" / "scripts" / name
        script.write_text(
            "#!/bin/bash\n"
            f'echo "$@" >> "{prefix}/{name}.log"\n'
            f'echo "[{name}] ran"\n'
            f"exit {engine_rc.get(name, 0)}\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
    return prefix


def _run_runner(prefix: Path, request: str | None, tmp_path: Path):
    if request is not None:
        (prefix / ".hatch-run-args").write_text(request + "\n", encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return _run(["/bin/bash", str(prefix / "hatch-run.command")],
                timeout=120, env={"HOME": str(home), "PATH": "/usr/bin:/bin"})


_CLOSERS = (_SIGNOFF, _STAY)


@pytest.mark.parametrize("request_,engine,rc", [
    ("open", "open-cabinet.sh", 0),
    ("open", "open-cabinet.sh", 1),
    ("doctor", "cabinet-doctor.sh", 0),
    ("doctor", "cabinet-doctor.sh", 1),
    ("hatch", "hatch.sh", 0),
    ("hatch", "hatch.sh", 75),
    ("hatch", "hatch.sh", 3),
    ("hatch --with-launchd", "hatch.sh", 0),
    (None, "hatch.sh", 0),          # no request file at all
    ("nonsense", "hatch.sh", 0),    # outside the allowlist
])
def test_no_branch_of_the_runner_exits_in_silence(
    tmp_path: Path, request_: str | None, engine: str, rc: int
) -> None:
    """THE property. Whatever was asked and however it went, the last thing the
    window says is a sentence a person can act on — never a bare prompt."""
    prefix = _fake_prefix(tmp_path, engine_rc={engine: rc})
    res = _run_runner(prefix, request_, tmp_path)
    assert res.returncode == rc, f"exit code swallowed: {res.stdout}{res.stderr}"
    lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    assert lines, "the runner printed nothing at all — the exact defect this pins"
    assert lines[-1] in _CLOSERS, f"last line was {lines[-1]!r}, not a closing sentence"


def test_every_exit_in_the_runner_is_covered_by_the_arms_above() -> None:
    """A new branch cannot be added without a silence arm for it: the arms
    above drive three exits, so a fourth has to arrive with its own test."""
    code = _code_lines(_RUNNER_IN)
    exits = [ln for ln in code.splitlines() if ln.strip().startswith("exit ")]
    assert len(exits) == 3, (
        f"the runner has {len(exits)} exit points, not the 3 the silence arms "
        f"drive — add an arm to test_no_branch_of_the_runner_exits_in_silence: {exits}"
    )


def test_the_launcher_branch_runs_its_engine_as_a_child_not_exec() -> None:
    # `exec` was the root cause of the silent window: it REPLACES this shell,
    # so nothing after it can ever print. No branch may exec an engine again.
    code = _code_lines(_RUNNER_IN)
    for line in code.splitlines():
        assert not line.strip().startswith("exec "), (
            f"an engine is exec'd again ({line.strip()!r}) — the closing sentence "
            "after it can never run"
        )


def test_opening_calls_the_opener_and_nothing_else(tmp_path: Path) -> None:
    prefix = _fake_prefix(tmp_path)
    res = _run_runner(prefix, "open", tmp_path)
    assert res.returncode == 0, res.stderr
    assert (prefix / "open-cabinet.sh.log").is_file(), "the opener never ran"
    assert not (prefix / "hatch.sh.log").exists(), "opening must never re-run setup"
    assert not (prefix / "cabinet-doctor.sh.log").exists()
    assert _SIGNOFF in res.stdout
    # and the request file is consumed, so a stray re-open cannot replay it
    assert not (prefix / ".hatch-run-args").exists()


def test_a_failed_open_keeps_its_window_and_says_where_to_look(tmp_path: Path) -> None:
    prefix = _fake_prefix(tmp_path, engine_rc={"open-cabinet.sh": 1})
    res = _run_runner(prefix, "open", tmp_path)
    assert res.returncode == 1
    assert _SIGNOFF not in res.stdout, "a failed open must not claim the browser is up"
    assert _STAY in res.stdout
    assert "close itself" not in res.stdout, "a failed run must keep its window"


def test_the_check_over_no_longer_replaces_this_shell(tmp_path: Path) -> None:
    # It used to `exec` the checker. Now it runs it, keeps its verdict, and
    # says the check is over — which is what the operator was missing.
    prefix = _fake_prefix(tmp_path, engine_rc={"cabinet-doctor.sh": 1})
    res = _run_runner(prefix, "doctor", tmp_path)
    assert res.returncode == 1, "the checker's verdict must survive"
    assert "[cabinet-doctor.sh] ran" in res.stdout
    assert "That is the whole check" in res.stdout
    assert _STAY in res.stdout


def test_the_archive_line_is_printed_and_only_ever_a_path(tmp_path: Path) -> None:
    # Line 2 of the request file says where a previous Cabinet went. It is
    # echoed so the window says it too, and it is accepted only as an absolute
    # path — anything else is dropped rather than shown or run.
    prefix = _fake_prefix(tmp_path)
    (prefix / ".hatch-run-args").write_text("hatch\n/Users/somebody/Cabinet/archived-x\n")
    res = _run_runner(prefix, None, tmp_path)
    assert "/Users/somebody/Cabinet/archived-x" in res.stdout
    assert "nothing in it was deleted" in res.stdout

    prefix2 = _fake_prefix(tmp_path / "two")
    (prefix2 / ".hatch-run-args").write_text("hatch\nrm -rf ~; echo pwned\n")
    res2 = _run_runner(prefix2, None, tmp_path / "two")
    assert "pwned" not in res2.stdout and "rm -rf" not in res2.stdout
    assert res2.returncode == 0


def test_the_stub_and_the_runner_agree_on_the_request_allowlist() -> None:
    swift = (_APPSHELL / "main.swift").read_text(encoding="utf-8")
    line = next(ln for ln in swift.splitlines() if "allowedRequests" in ln and "Set<String>" in ln)
    sent = set(re.findall(r'"([^"]+)"', line))
    accepted = set()
    for ln in _code_lines(_RUNNER_IN).splitlines():
        m = re.match(r'\s*"?(hatch(?: --with-launchd)?|doctor|open)"?\)\s+MODE=', ln)
        if m:
            accepted.add(m.group(1))
    assert sent == accepted, (
        f"the stub may send {sorted(sent)} but the runner answers {sorted(accepted)} — "
        "a request the runner does not know falls through to a full setup"
    )


def test_starting_fresh_can_only_move_never_delete() -> None:
    """The one property that must be structurally impossible to get wrong.

    `removeItem` appears exactly once in the stub, on the app's own handoff
    script, and the start-over path reaches nothing but `moveItem`. No trash
    call, no recursive delete, anywhere."""
    swift = (_APPSHELL / "main.swift").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in swift.splitlines() if not ln.lstrip().startswith("//"))
    assert code.count("removeItem") == 1, "a second delete call appeared in the stub"
    # …and it is the runner refresh, nothing else
    fn = code[code.index("func installRunner"):code.index("func unpack")]
    assert "removeItem" in fn, "removeItem moved out of installRunner"
    for banned in ("trashItem", "removeItemAt", '"-rf"', "rm -rf"):
        assert banned not in code, f"a delete-shaped call ({banned}) is in the stub"
    # the archive is a rename, and it refuses to land on an existing name
    arch = code[code.index("func archiveInstall"):code.index("func stopOldCabinet")]
    assert "moveItem" in arch and "removeItem" not in arch
    assert "while fm.fileExists(atPath: dest)" in arch, (
        "the archive name must count up rather than land on an existing folder"
    )


def test_only_a_finished_cabinet_reaches_the_launcher() -> None:
    swift = (_APPSHELL / "main.swift").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in swift.splitlines() if not ln.lstrip().startswith("//"))
    # the open request is written on exactly one branch, and that branch is
    # guarded by the .cabinet state
    assert code.count('"open"') >= 1
    assert 'if prefixState(prefix) == .cabinet {' in code
    # the predicate needs a hatch-WRITTEN marker, not just an unpacked tree:
    # a half-finished unpack has the engine and nothing else.
    assert 'markerPreset = "instance/config/active-preset"' in code
    assert 'markerEnv = "cabinet/.env"' in code
    assert 'markerEngine = "cabinet/scripts/hatch.sh"' in code


def test_shell_sources_pass_shellcheck() -> None:
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck not installed")
    targets = [_RUNNER_IN, _BUILDER, _GATE, _LINT,
               _SCRIPTS_DIR / "open-cabinet.sh",
               _SCRIPTS_DIR / "lib" / "dashboard.sh"]
    res = _run(["shellcheck", "-s", "bash", *[str(t) for t in targets]], timeout=120)
    assert res.returncode == 0, res.stdout + res.stderr


# ---- detection, against the built stub (dev-Mac only) ---------------------------


def _probe(stub: Path, prefix: Path) -> str:
    env = {**os.environ, "HATCH_APP_PROBE": "1", "CABINET_HATCH_PREFIX": str(prefix)}
    res = _run([str(stub)], timeout=60, env=env)
    assert res.returncode == 0, res.stderr
    return dict(
        line.split("=", 1) for line in res.stdout.splitlines() if "=" in line
    )["state"]


def test_detection_arms(built_app: Path, tmp_path: Path) -> None:
    stub = built_app / "Contents" / "MacOS" / "HatchCabinet"

    # absent -> the installer
    assert _probe(stub, tmp_path / "nothing-here") == "absent"

    # empty dir -> the installer (an empty lot is safe to build on)
    empty = tmp_path / "empty"; empty.mkdir()
    assert _probe(stub, empty) == "empty"

    # a tree with the engine but nothing hatch WROTE: an unpack that died.
    # Never the launcher — there is nothing to open.
    half = tmp_path / "half"
    (half / "cabinet" / "scripts").mkdir(parents=True)
    (half / "cabinet" / "scripts" / "hatch.sh").write_text("#!/bin/bash\n")
    assert _probe(stub, half) == "occupied"

    # somebody else's folder entirely
    foreign = tmp_path / "foreign"; foreign.mkdir()
    (foreign / "notes.txt").write_text("mine, actually")
    assert _probe(stub, foreign) == "occupied"

    # a file where the folder should be
    afile = tmp_path / "afile"; afile.write_text("x")
    assert _probe(stub, afile) == "occupied"

    # the real thing: engine + a marker only a finished hatch writes
    real = tmp_path / "real"
    (real / "cabinet" / "scripts").mkdir(parents=True)
    (real / "cabinet" / "scripts" / "hatch.sh").write_text("#!/bin/bash\n")
    (real / "instance" / "config").mkdir(parents=True)
    (real / "instance" / "config" / "active-preset").write_text("portfolio\n")
    assert _probe(stub, real) == "cabinet"

    # an EMPTY preset file is not a finished setup — the degenerate end
    empty_marker = tmp_path / "emptymarker"
    (empty_marker / "cabinet" / "scripts").mkdir(parents=True)
    (empty_marker / "cabinet" / "scripts" / "hatch.sh").write_text("#!/bin/bash\n")
    (empty_marker / "instance" / "config").mkdir(parents=True)
    (empty_marker / "instance" / "config" / "active-preset").write_text("")
    assert _probe(stub, empty_marker) == "occupied"

    # the other marker on its own is enough
    envonly = tmp_path / "envonly"
    (envonly / "cabinet" / "scripts").mkdir(parents=True)
    (envonly / "cabinet" / "scripts" / "hatch.sh").write_text("#!/bin/bash\n")
    (envonly / "cabinet" / ".env").write_text("CABINET_DASHBOARD_PORT=3101\n")
    assert _probe(stub, envonly) == "cabinet"


def test_probe_changes_nothing(built_app: Path, tmp_path: Path) -> None:
    stub = built_app / "Contents" / "MacOS" / "HatchCabinet"
    prefix = tmp_path / "readonly-check"
    (prefix / "cabinet" / "scripts").mkdir(parents=True)
    (prefix / "cabinet" / "scripts" / "hatch.sh").write_text("#!/bin/bash\n")
    before = sorted(str(p.relative_to(prefix)) for p in prefix.rglob("*"))
    _probe(stub, prefix)
    after = sorted(str(p.relative_to(prefix)) for p in prefix.rglob("*"))
    assert before == after, "the probe wrote something"


def test_starting_fresh_moves_the_whole_install_and_keeps_every_byte(
    built_app: Path, tmp_path: Path
) -> None:
    """The archive half of "start completely fresh", run for real.

    (The fleet-stop is NOT exercised: `deploy-mac.sh --stop all` boots out
    LaunchAgents on whatever Mac the suite happens to run on, so it is a
    dialog-path act by construction and this smoke mode never reaches it.)"""
    stub = built_app / "Contents" / "MacOS" / "HatchCabinet"
    prefix = tmp_path / "prefix"
    (prefix / "cabinet" / "scripts").mkdir(parents=True)
    (prefix / "cabinet" / "scripts" / "hatch.sh").write_text("#!/bin/bash\n")
    (prefix / "instance" / "config").mkdir(parents=True)
    (prefix / "instance" / "config" / "active-preset").write_text("portfolio\n")
    treasure = prefix / "vault" / "notes.md"
    treasure.parent.mkdir(parents=True)
    treasure.write_text("everything it learned\n")
    keepsake = treasure.read_bytes()

    env = {**os.environ, "HATCH_APP_SMOKE": "fresh", "CABINET_HATCH_PREFIX": str(prefix)}
    res = _run([str(stub)], timeout=_SMOKE_TIMEOUT, env=env)
    assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    archives = sorted(p for p in tmp_path.iterdir() if p.name.startswith("archived-"))
    assert len(archives) == 1, f"expected exactly one archive beside the prefix: {archives}"
    archive = archives[0]
    # NOTHING was deleted: the old tree is intact, byte for byte, under its
    # new name — and the old install is gone from the install path.
    assert (archive / "vault" / "notes.md").read_bytes() == keepsake
    assert (archive / "instance" / "config" / "active-preset").read_text() == "portfolio\n"
    assert not (prefix / "vault" / "notes.md").exists()
    # …and a fresh cabinet was unpacked in its place
    assert (prefix / "cabinet" / "scripts" / "hatch.sh").stat().st_size > 100
    # The stub standardizes the path (macOS resolves /private/var <-> /var), so
    # pin the NAME it reported rather than a spelling of the same directory.
    assert "archived: " in res.stdout and archive.name in res.stdout, res.stdout[-400:]


def test_the_app_carries_the_opener_for_a_cabinet_that_predates_it(tmp_path: Path) -> None:
    """An install made before the opener existed is exactly the one someone
    double-clicks this app to get back into.

    The stub drops app-owned copies at the TOP of the prefix; the runner
    prefers the Cabinet's own opener and falls back to that copy. Without the
    fallback the everyday path would fail on every install older than it."""
    prefix = _fake_prefix(tmp_path)
    # remove the Cabinet's own opener — an older install
    (prefix / "cabinet" / "scripts" / "open-cabinet.sh").unlink()
    fallback = prefix / ".hatch-open.command"
    fallback.write_text(
        "#!/bin/bash\n"
        f'echo "fallback ran" >> "{prefix}/fallback.log"\n'
        'echo "[fallback] ran"\nexit 0\n',
        encoding="utf-8",
    )
    fallback.chmod(0o755)
    res = _run_runner(prefix, "open", tmp_path)
    assert res.returncode == 0, res.stdout + res.stderr
    assert (prefix / "fallback.log").is_file(), "the app-owned opener was never reached"
    assert _SIGNOFF in res.stdout


def test_the_cabinets_own_opener_wins_over_the_app_copy(tmp_path: Path) -> None:
    prefix = _fake_prefix(tmp_path)
    fallback = prefix / ".hatch-open.command"
    fallback.write_text(f'#!/bin/bash\necho fallback >> "{prefix}/fallback.log"\nexit 0\n')
    fallback.chmod(0o755)
    res = _run_runner(prefix, "open", tmp_path)
    assert res.returncode == 0
    assert (prefix / "open-cabinet.sh.log").is_file()
    assert not (prefix / "fallback.log").exists(), (
        "a newer Cabinet's own opener must win over the app's copy"
    )


def test_the_stub_installs_all_three_app_owned_files(built_app: Path, tmp_path: Path) -> None:
    stub = built_app / "Contents" / "MacOS" / "HatchCabinet"
    prefix = tmp_path / "prefix"
    env = {**os.environ, "HATCH_APP_SMOKE": "1", "CABINET_HATCH_PREFIX": str(prefix)}
    res = _run([str(stub)], timeout=_SMOKE_TIMEOUT, env=env)
    assert res.returncode == 0, res.stdout + res.stderr
    for name in ("hatch-run.command", ".hatch-open.command", ".hatch-dashboard-lib.sh"):
        p = prefix / name
        assert p.is_file() and os.access(p, os.X_OK), f"missing app-owned file {name}"
    # …and they are the SAME bytes the egg ships, not a second copy that can drift
    assert (prefix / ".hatch-open.command").read_bytes() == \
        (prefix / "cabinet" / "scripts" / "open-cabinet.sh").read_bytes()
    assert (prefix / ".hatch-dashboard-lib.sh").read_bytes() == \
        (prefix / "cabinet" / "scripts" / "lib" / "dashboard.sh").read_bytes()


def test_the_opener_runs_from_the_prefix_root_too(tmp_path: Path) -> None:
    """The app-owned copy sits beside the runner, not in cabinet/scripts — so
    the opener has to find its root and its lib from there."""
    prefix = tmp_path / "prefix"
    (prefix / "cabinet" / "scripts").mkdir(parents=True)
    (prefix / "cabinet" / ".env").write_text("CABINET_DASHBOARD_PORT=3141\n")
    shutil.copy(_SCRIPTS_DIR / "open-cabinet.sh", prefix / ".hatch-open.command")
    shutil.copy(_SCRIPTS_DIR / "lib" / "dashboard.sh", prefix / ".hatch-dashboard-lib.sh")
    (prefix / ".hatch-open.command").chmod(0o755)
    shim = tmp_path / "shims"
    shim.mkdir()
    (shim / "curl").write_text(
        "#!/bin/bash\n"
        "printf '%s' '{\"ok\":true,\"service\":\"cabinet-dashboard\"}'\nexit 0\n")
    (shim / "curl").chmod(0o755)
    (shim / "open").write_text(f'#!/bin/bash\necho "$@" >> "{shim}/open.log"\nexit 0\n')
    (shim / "open").chmod(0o755)
    home = tmp_path / "home"; home.mkdir()
    res = _run(["/bin/bash", str(prefix / ".hatch-open.command")], timeout=60,
               env={"HOME": str(home), "PATH": f"{shim}:/usr/bin:/bin"})
    assert res.returncode == 0, res.stdout + res.stderr
    # it read the port out of the install's own .env, from the prefix root
    assert "http://127.0.0.1:3141/" in res.stdout
    assert (shim / "open.log").read_text().strip() == "http://127.0.0.1:3141/"


def test_the_fleet_stop_is_reachable_from_exactly_one_place() -> None:
    """`deploy-mac.sh --stop all` boots out every installed cabinet LaunchAgent.

    It is the right thing to do before moving a Cabinet aside and the wrong
    thing to do anywhere else — above all in a headless mode, which would boot
    out the fleet on whatever Mac a test suite happens to run on. So: one
    definition, one call site, inside the typed-confirmation flow, guarded on
    the prefix actually being a Cabinet, with fixed argv."""
    swift = (_APPSHELL / "main.swift").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in swift.splitlines() if not ln.lstrip().startswith("//"))
    assert code.count("stopOldCabinet") == 2, (
        "the fleet-stop has more than one call site — every one of them is a "
        "chance to boot out a fleet nobody asked to stop"
    )
    fresh = code[code.index("func startFresh"):code.index("func dialogMain")]
    assert "if isCabinet { _ = stopOldCabinet(at: prefix) }" in fresh, (
        "the fleet-stop moved out of the typed-confirmation flow, or lost its guard"
    )
    # …after the typed phrase matched, never before it
    assert fresh.index("guard typed == freshConfirmPhrase") < fresh.index("stopOldCabinet")
    # fixed argv, no interpolation, no shell
    assert 'run("/bin/bash", [script, "--stop", "all"], cwd: prefix)' in code
    # and no headless mode can reach it
    for fn in ("func smokeMain", "func probeMain"):
        body = code[code.index(fn):]
        body = body[: body.index("\n}\n") + 3]
        assert "stopOldCabinet" not in body, f"{fn} can stop a live fleet"
