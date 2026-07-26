"""Sanity + write-plane gates for the STAGED germline boot-pack patch (lane BC).

The three target files are schg-locked germline:
  cabinet/scripts/hooks/session-start.sh   — digest boot injection
  cabinet/scripts/hooks/pre-tool-use.sh    — §5 Write/Edit arm + §5c bash screen
  cabinet/scripts/lib/officer-sandbox.sh   — kernel seatbelt deny
The change ships as ONE staged artifact
(docs/proposals/germline-session-start-digest-2026-07-15.patch — a plain FILE
directly under docs/proposals/ BY CONTRACT: the egg exporter's
t_proposals_archive rm -f's each entry under set -e, so a subdirectory there
aborts the export) and is applied only inside a Captain unlock window (see the
same-named -addendum doc). These tests keep the artifact honest WITHOUT
touching the locks: every check runs against COPIES in a pytest tmp tree.

STATE-AWARE: pre-ceremony the live files lack the digest markers — the
fixture applies the staged patch to pristine copies, and the load-bearing
negative controls also run (the UNPATCHED hook must ALLOW digest writes /
carry no digest section — proving the guard and the injection are the
patch's work, not latent behavior). Post-ceremony the live files ARE the
patched state — the fixture uses them directly and the pre-state-only
controls skip. A MIXED state (some targets patched, some not) fails loudly:
that is a half-applied ceremony.

Pins:
  * the patch applies clean (patch -p1, no rejects) and all three patched
    files pass bash -n;
  * the digest section is injected BEFORE the tail-40 ledger sections
    (which stay);
  * jq -Rs envelope round-trip: a digest full of quotes / backslashes /
    newlines / $( ) / format directives survives byte-exactly into
    hookSpecificOutput.additionalContext and the output stays valid JSON;
  * the backslash-doubling line is LOAD-BEARING: a mutant without it fails
    the byte-exact round-trip (%b mangles the content);
  * absent digest → patched hook output is byte-identical to the unpatched
    hook's output (no behavior change until a digest is PROMOTED);
  * WRITE-PLANE GATES — the 2026-07-07 audit-CRITICAL injection-persistence
    channel, closed for the digest in the SAME ceremony that starts
    boot-injecting it: the patched pre-tool-use.sh BLOCKS (exit 2)
    Write/Edit and the write-shaped Bash vectors (redirect, append, tee,
    rm) against captain-law-digest.md — for cos too — and blocks doorway
    tampering with memory-distill.py; while ALLOWING (exit 0) reads, the
    sanctioned distiller invocations (default/--apply/--check), writes to
    the .proposal.md review sibling, and unrelated interface writes. The
    existing three-ledger plane keeps blocking (regex-fold regression pin);
  * the patched officer-sandbox.sh emits kernel deny lines for the digest
    vnode (text-level pin — executing seatbelt profiles is macOS-only, and
    the hook plane above is the behavioral gate under test).

Run: python3.12 -m pytest cabinet/scripts/tests/test_session_start_digest_patch.py -q
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
HOOK_SS = REPO / "cabinet" / "scripts" / "hooks" / "session-start.sh"
HOOK_PTU = REPO / "cabinet" / "scripts" / "hooks" / "pre-tool-use.sh"
SANDBOX = REPO / "cabinet" / "scripts" / "lib" / "officer-sandbox.sh"
PATCH = (REPO / "docs" / "proposals"
         / "germline-session-start-digest-2026-07-15.patch")

TARGETS = (
    "cabinet/scripts/hooks/session-start.sh",
    "cabinet/scripts/hooks/pre-tool-use.sh",
    "cabinet/scripts/lib/officer-sandbox.sh",
)

DOUBLING_LINE = 'body="${body//\\\\/\\\\\\\\}"'
DIGEST_MARK = "captain-law-digest.md"

TRICKY_DIGEST = (
    'Line "double" \'single\' `backtick` $(reboot) ${HOME}\n'
    "Back\\slash literal-\\n literal-\\t double-\\\\ pct-%s pct-%b\n"
    'Danish: æøå JSON breakers: {"a": "b"}, ] }\n'
)

# Ceremony state, per target file. All three flip in ONE unlock window.
_STATES = {t: DIGEST_MARK in (REPO / t).read_text(errors="replace")
           for t in TARGETS}
LIVE_PATCHED = all(_STATES.values())

pytestmark = pytest.mark.skipif(
    not PATCH.exists() or shutil.which("patch") is None,
    reason="staged patch artifact or patch(1) unavailable")


def test_ceremony_state_consistent():
    """The three germline targets are patched together or not at all — a
    mixed state means a half-applied unlock window (boot-injection without
    the write guard, or vice versa) and must fail loudly."""
    assert all(_STATES.values()) or not any(_STATES.values()), _STATES


# --------------------------------------------------------------- helpers ----
@pytest.fixture()
def patched_tree(tmp_path: Path) -> Path:
    """COPIES of the three germline targets in the post-ceremony state:
    pre-ceremony = pristine copies + staged patch applied here; post-ceremony
    = the live (already-patched) files verbatim. Never touches the locks."""
    tree = tmp_path / "tree"
    for rel in TARGETS:
        dst = tree / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, dst)
    if not LIVE_PATCHED:
        proc = subprocess.run(
            ["patch", "-p1", "-d", str(tree)],
            stdin=PATCH.open("rb"), capture_output=True, text=False, timeout=60)
        assert proc.returncode == 0, f"patch failed: {proc.stdout!r} {proc.stderr!r}"
        assert not list(tree.rglob("*.rej")), "patch produced rejects"
    return tree


def _hook_env(root: Path) -> dict:
    env = {**os.environ, "CABINET_ROOT": str(root)}
    # No officer identity → the hook's Redis heartbeat block is skipped
    # (session-start.sh gates it on OFFICER != unknown) — hermetic, no redis.
    for var in ("OFFICER_NAME", "CABINET_OFFICER", "SESSION_START_HOOK_ENABLED"):
        env.pop(var, None)
    return env


def make_fixroot(tmp_path: Path, digest: str | None) -> Path:
    root = tmp_path / "fixroot"
    iface = root / "shared" / "interfaces"
    iface.mkdir(parents=True)
    (iface / "captain-patterns.md").write_text(
        "## 2026-07-01 — pattern entry\n- **Rule:** tail-forty stays\n")
    (iface / "captain-decisions.md").write_text(
        "## 2026-07-02 — decision entry\n- **Decision:** tails unchanged\n")
    if digest is not None:
        # Simulates the PROMOTED digest (only memory-distill.py --apply
        # writes this path; the .proposal.md sibling is never injected).
        (iface / "captain-law-digest.md").write_text(digest)
    return root


def run_hook(hook: Path, root: Path) -> str:
    proc = subprocess.run(["bash", str(hook)], env=_hook_env(root),
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def context_of(stdout: str) -> str:
    out = json.loads(stdout)  # raises = envelope broken
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    return out["hookSpecificOutput"]["additionalContext"]


def _shim_bin(tmp_path: Path) -> Path:
    """PATH-prepended redis-cli shim: kill-switch / telemetry lookups inside
    pre-tool-use.sh short-circuit locally — hermetic even on a host running
    the real cabinet redis.

    The shim ANSWERS the reader's frame rather than staying silent.
    killswitch-read.sh proves its read with a nonce sandwich
    (``ECHO <n1>`` / ``GET cabinet:killswitch`` / ``ECHO <n2>``) and only calls
    the switch CLEAR when both fresh nonces come back around the value, because
    redis-cli prints NOAUTH/NOPERM/WRONGTYPE/LOADING errors on stdout with exit
    0 — so silence proves nothing. This shim replays each ECHO argument and
    answers GET with an empty value (= key absent), which is the honest
    "reachable, authenticated, no stop armed" posture these tests need. It is
    not permissive: it cannot mask an armed switch, and a reader whose question
    it fails to answer still fails closed."""
    bindir = tmp_path / "shimbin"
    if not bindir.is_dir():
        bindir.mkdir()
        shim = bindir / "redis-cli"
        shim.write_text(
            "#!/bin/sh\n"
            'while IFS= read -r l; do case "$l" in "ECHO "*) echo "${l#ECHO }";;'
            ' *) echo "";; esac; done\n'
        )
        shim.chmod(0o755)
    return bindir


def probe(hook: Path, tmp_path: Path, payload: dict,
          officer: str = "cro") -> subprocess.CompletedProcess:
    """Drive a pre-tool-use.sh COPY exactly like Claude Code does: the
    {tool_name, tool_input} JSON on stdin, decision = exit code (0 allow /
    2 block). CABINET_HOOK_TEST_MODE=1 per the house harness contract
    (fences production sinks); CABINET_ROOT is dropped so the hook resolves
    its root from its own tmp-tree location (no live policy-shadow)."""
    env = {**os.environ,
           "CABINET_HOOK_TEST_MODE": "1",
           "OFFICER_NAME": officer,
           "PATH": f"{_shim_bin(tmp_path)}:{os.environ['PATH']}"}
    for var in ("CABINET_ROOT", "CABINET_AUTHORITY_ENFORCING", "OFFICER"):
        env.pop(var, None)
    return subprocess.run(
        ["bash", str(hook)], input=json.dumps(payload),
        env=env, capture_output=True, text=True, timeout=60)


def _ptu(tree: Path) -> Path:
    return tree / "cabinet" / "scripts" / "hooks" / "pre-tool-use.sh"


def _ss(tree: Path) -> Path:
    return tree / "cabinet" / "scripts" / "hooks" / "session-start.sh"


# ------------------------------------------------------ apply + injection ----
def test_patch_applies_clean_and_bash_n(patched_tree):
    for rel in TARGETS:
        proc = subprocess.run(["bash", "-n", str(patched_tree / rel)],
                              capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, f"{rel}: {proc.stderr}"


def test_digest_section_inserted_before_tail40_sections(patched_tree):
    patched = _ss(patched_tree).read_text()
    if not LIVE_PATCHED:
        # Pre-state control: the locked hook has no digest section today —
        # only the staged patch adds it.
        assert DIGEST_MARK not in HOOK_SS.read_text()
    assert DIGEST_MARK in patched
    assert patched.index(DIGEST_MARK) < patched.index(
        "captain-patterns.md"), "digest must be injected BEFORE the tails"
    assert DOUBLING_LINE in patched


def test_envelope_round_trip_with_hostile_digest(patched_tree, tmp_path):
    root = make_fixroot(tmp_path, TRICKY_DIGEST)
    ctx = context_of(run_hook(_ss(patched_tree), root))
    # Byte-exact recovery THROUGH printf %b + jq -Rs (the doubling makes %b
    # a no-op; jq handles the JSON quoting).
    assert TRICKY_DIGEST.rstrip("\n") in ctx, "digest not byte-exact in context"
    # Order: digest section first, tail-40 sections still present after it.
    assert ctx.index("Captain Law Digest") < ctx.index("Captain Patterns")
    assert "tail-forty stays" in ctx and "tails unchanged" in ctx


def test_doubling_line_is_load_bearing(patched_tree, tmp_path):
    """MUTANT CONTROL: strip the backslash-doubling line and the hostile
    digest no longer round-trips byte-exact (%b expands its sequences) —
    the escaping line is doing real work, not decoration."""
    mutant = tmp_path / "mutant.sh"
    src = _ss(patched_tree).read_text()
    lines = [ln for ln in src.splitlines() if DOUBLING_LINE not in ln]
    assert len(lines) < len(src.splitlines()), \
        "mutant did not remove the doubling line"
    mutant.write_text("\n".join(lines) + "\n")
    root = make_fixroot(tmp_path, TRICKY_DIGEST)
    ctx = context_of(run_hook(mutant, root))
    assert TRICKY_DIGEST.rstrip("\n") not in ctx, (
        "round-trip survived WITHOUT the doubling line — control has no teeth")


def test_absent_digest_is_behavior_neutral(patched_tree, tmp_path):
    """No digest file → the patched hook must emit byte-identical output to
    the pristine hook (the germline-review-critical property: the patch
    changes nothing until a digest has been PROMOTED — and deleting the
    digest is the documented Captain-side kill switch)."""
    root = make_fixroot(tmp_path, digest=None)
    assert run_hook(_ss(patched_tree), root) == run_hook(HOOK_SS, root)


# ------------------------------------------------- write-plane gate (BC) ----
_WRITE_DIGEST = {"tool_name": "Write",
                 "tool_input": {"file_path": "shared/interfaces/captain-law-digest.md",
                                "content": "forged boot law"}}

BLOCK_PROBES = [
    ("write-digest-cro", "cro", _WRITE_DIGEST),
    ("write-digest-cos", "cos", _WRITE_DIGEST),  # the plane binds EVERY officer
    ("edit-digest-abs-path", "cro",
     {"tool_name": "Edit",
      "tool_input": {"file_path": "/opt/founders-cabinet/shared/interfaces/captain-law-digest.md",
                     "old_string": "a", "new_string": "b"}}),
    ("bash-redirect-digest", "cro",
     {"tool_name": "Bash",
      "tool_input": {"command": "echo forged-boot-law > shared/interfaces/captain-law-digest.md"}}),
    ("bash-append-digest", "cro",
     {"tool_name": "Bash",
      "tool_input": {"command": "printf x >> shared/interfaces/captain-law-digest.md"}}),
    ("bash-tee-digest", "cro",
     {"tool_name": "Bash",
      "tool_input": {"command": "cat /tmp/evil.md | tee shared/interfaces/captain-law-digest.md"}}),
    ("bash-rm-digest-killswitch-is-captains", "cro",
     {"tool_name": "Bash",
      "tool_input": {"command": "rm shared/interfaces/captain-law-digest.md"}}),
    ("bash-sed-doorway-distiller", "cro",
     {"tool_name": "Bash",
      "tool_input": {"command": "sed -i 's/reflection/captain/' cabinet/scripts/memory-distill.py"}}),
    ("write-doorway-distiller", "cro",
     {"tool_name": "Write",
      "tool_input": {"file_path": "cabinet/scripts/memory-distill.py",
                     "content": "poisoned distiller"}}),
    # Regression pin: folding the ledger regex to captain-(…|law-digest)\.md
    # must not drop the existing three-ledger plane.
    ("bash-append-patterns-still-blocked", "cro",
     {"tool_name": "Bash",
      "tool_input": {"command": "echo forged-law >> shared/interfaces/captain-patterns.md"}}),
]

ALLOW_PROBES = [
    # The sanctioned writer lane: bare distiller invocations carry no
    # write-shaped token targeting a plane path — they must pass.
    ("distill-default", {"tool_name": "Bash",
                         "tool_input": {"command": "python3.12 cabinet/scripts/memory-distill.py"}}),
    ("distill-apply", {"tool_name": "Bash",
                       "tool_input": {"command": "python3.12 cabinet/scripts/memory-distill.py --apply"}}),
    ("distill-check", {"tool_name": "Bash",
                       "tool_input": {"command": "python3.12 cabinet/scripts/memory-distill.py --check"}}),
    # Reads stay open.
    ("digest-cat", {"tool_name": "Bash",
                    "tool_input": {"command": "cat shared/interfaces/captain-law-digest.md"}}),
    ("digest-grep", {"tool_name": "Bash",
                     "tool_input": {"command": "grep -n telegram shared/interfaces/captain-law-digest.md"}}),
    ("digest-read-tool", {"tool_name": "Read",
                          "tool_input": {"file_path": "shared/interfaces/captain-law-digest.md"}}),
    # The .proposal.md REVIEW sibling is deliberately outside the plane
    # (--apply refuses on any divergence from a fresh render, so tampering
    # it can never reach boot) — pin the narrowness so a future widening is
    # a deliberate decision.
    ("proposal-write-allowed", {"tool_name": "Write",
                                "tool_input": {"file_path": "shared/interfaces/captain-law-digest.proposal.md",
                                               "content": "reviewed draft"}}),
    # Unrelated interface files keep today's behavior.
    ("other-interface-write", {"tool_name": "Write",
                               "tool_input": {"file_path": "shared/interfaces/scratch-note.md",
                                              "content": "notes"}}),
]


@pytest.mark.parametrize("label,officer,payload", BLOCK_PROBES,
                         ids=[p[0] for p in BLOCK_PROBES])
def test_patched_hook_blocks_digest_write_plane(patched_tree, tmp_path,
                                                label, officer, payload):
    proc = probe(_ptu(patched_tree), tmp_path, payload, officer=officer)
    assert proc.returncode == 2, (
        f"{label}: expected BLOCK (2), got rc={proc.returncode}; "
        f"stderr={proc.stderr!r}")
    assert "Captain-law" in proc.stderr


@pytest.mark.parametrize("label,payload", ALLOW_PROBES,
                         ids=[p[0] for p in ALLOW_PROBES])
def test_patched_hook_allows_sanctioned_lanes(patched_tree, tmp_path,
                                              label, payload):
    proc = probe(_ptu(patched_tree), tmp_path, payload)
    assert proc.returncode == 0, (
        f"{label}: expected ALLOW (0), got rc={proc.returncode}; "
        f"stderr={proc.stderr!r}")


@pytest.mark.skipif(LIVE_PATCHED,
                    reason="ceremony landed — no pristine hook to control against")
def test_unpatched_hook_allows_digest_write_negative_control(tmp_path):
    """PRE-STATE CONTROL (the finding this lane closes): today's locked hook
    does NOT guard the digest — the Write passes. Proves the BLOCK pins
    above are the staged patch's work; if this ever fails pre-ceremony, the
    guard landed some other way and the patch/addendum must be re-derived."""
    tree = tmp_path / "pristine"
    (tree / "cabinet" / "scripts" / "hooks").mkdir(parents=True)
    hook = tree / "cabinet" / "scripts" / "hooks" / "pre-tool-use.sh"
    shutil.copy(HOOK_PTU, hook)
    proc = probe(hook, tmp_path, _WRITE_DIGEST)
    assert proc.returncode == 0, (
        "pristine hook unexpectedly blocks the digest write — control stale")


def test_patched_sandbox_denies_digest_vnode(patched_tree):
    """Kernel plane (text-level pin): the patched officer-sandbox.sh ledger
    loop must include the digest so seatbelt denies file-write* AND
    file-write-unlink on its vnode; the three existing ledgers stay; the
    .proposal.md review sibling stays deliberately writable."""
    text = (patched_tree / "cabinet" / "scripts" / "lib"
            / "officer-sandbox.sh").read_text()
    loop = next(ln for ln in text.splitlines()
                if ln.strip().startswith("for _ledger in"))
    assert "captain-law-digest.md" in loop
    for ledger in ("captain-patterns.md", "captain-intents.md",
                   "captain-decisions.md"):
        assert ledger in loop, f"existing kernel plane lost: {ledger}"
    assert "captain-law-digest.proposal.md" not in loop
    if not LIVE_PATCHED:
        pristine = next(ln for ln in SANDBOX.read_text().splitlines()
                        if ln.strip().startswith("for _ledger in"))
        assert "captain-law-digest.md" not in pristine, (
            "pristine sandbox already denies the digest — control stale")
