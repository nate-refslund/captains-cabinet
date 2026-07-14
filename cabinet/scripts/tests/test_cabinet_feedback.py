"""cabinet-feedback.sh — scrub-proof, consent gate, and no-gh dry-run.

Contracts under test (Wave E contribution design):

1. REDACTION-PROOF — planted captain-suite tokens (SYNTHETIC qz*
   placeholders fed through a fixture publish-scan-patterns.local, plus the
   gate line's generic classes; no real value ever appears in this file's
   source — R166) are scrubbed from the printed bundle, line-for-line
   replaced with "[scrubbed]".
2. --dry-run NEVER invokes gh — proven via a PATH shim that logs every
   invocation (the log must not exist afterwards).
3. Consent gating — an interactive "n" posts nothing; a piped/non-TTY stdin
   is refused outright (piped "y" cannot post); an interactive "y" posts via
   the shim with the fixed argv (repo slug parsed from the script under
   test, never hardcoded here).
4. Honest failures — gh missing and gh unauthenticated each name themselves.
5. FAIL-CLOSED — a present-but-unextractable pattern source aborts the run;
   so do a private-side checkout (gate present) MISSING its captain
   patterns file, and a malformed patterns-file directive (which aborts
   naming file:LINE-NUMBER, never echoing the content).
6. BASELINE MODE — with the gate file absent AND no patterns file (the
   unconfigured packaged-egg shape), $HOME paths, emails, and 9+-digit id
   runs still scrub, and the mode is announced; with a patterns file
   present on an egg cut, its tokens scrub too.
7. ZERO-HIT PASS-THROUGH — a bundle with no scrub hits prints IN FULL
   (regression: the two-file awk's empty-hit-list mis-fire silently emptied
   the whole bundle in exactly the clean-environment case).
8. BINARY-TINGED BUNDLE — a single NUL byte anywhere in the gathered bundle
   must NOT disarm the scrubber (regression: without forced text mode grep
   degrades to "Binary file ... matches" — no -n line numbers, so zero
   lines were replaced while the banner still claimed a count: a silent
   fail-open with a false redaction receipt). Tokens on and after NUL
   lines scrub, and the reported count stays honest.

Hermetic: scratch roots under tmp_path, fake HOME, fake doctor (never the
real prober — it stamps a Redis heartbeat), fixed-argv subprocesses, stdlib
pty for the interactive consent paths.
"""
from __future__ import annotations

import os
import pty
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "cabinet" / "scripts" / "cabinet-feedback.sh"
GATE = REPO / "cabinet" / "scripts" / "egg-publish-gate.sh"

gate_required = pytest.mark.skipif(
    not GATE.is_file(),
    reason="publish-gate pattern source is private-side prep (absent from egg "
           "cuts by manifest); baseline-mode coverage below still runs",
)

# A 13-digit id run, concatenated so this source file never carries 9+
# consecutive digits (the digit-run guard applies to test sources too).
PLANTED_DIGITS = "123456" + "7890123"

# Synthetic captain-suite tokens (R166): the gate's tracked GREP_PATTERNS
# line carries GENERIC classes only, so the captain-specific tokens the
# scrub must catch are planted here through a fixture patterns file — every
# token a qz* placeholder; no real value appears in this source.
SYN_SUB = "qzemployer"
SYN_WORD = "qzcaptain"
SYN_PATTERNS = f"# synthetic fixture\npattern sub:{SYN_SUB}\npattern word:{SYN_WORD}\nallow QZ-1 qzhandle/qz-cabinet\n"


def _mk_root(tmp_path: Path, *, gate: str = "real",
             patterns: str | None = SYN_PATTERNS,
             doctor_lines: tuple[str, ...] = ()) -> Path:
    """Scratch CABINET_FEEDBACK_ROOT: optional gate copy + optional captain
    patterns file (SYNTHETIC by default; pass patterns=None for the
    unconfigured-machine shape) + a FAKE doctor."""
    root = tmp_path / "root"
    scripts = root / "cabinet" / "scripts"
    scripts.mkdir(parents=True)
    if gate == "real":
        shutil.copy2(GATE, scripts / "egg-publish-gate.sh")
    elif gate == "malformed":
        (scripts / "egg-publish-gate.sh").write_text(
            "#!/bin/bash\n# gate reformatted — no extractable pattern line\n",
            encoding="utf-8")
    elif gate != "absent":
        raise AssertionError(f"unknown gate mode {gate!r}")
    if patterns is not None:
        cfg = root / "instance" / "config"
        cfg.mkdir(parents=True)
        (cfg / "publish-scan-patterns.local").write_text(
            patterns, encoding="utf-8")
    (scripts / "doctor-output.txt").write_text(
        "\n".join(doctor_lines) + "\n", encoding="utf-8")
    doctor = scripts / "cabinet-doctor.sh"
    doctor.write_text('#!/bin/sh\ncat "$(dirname "$0")/doctor-output.txt"\n',
                      encoding="utf-8")
    doctor.chmod(0o755)
    return root


def _mk_home(tmp_path: Path, flight_lines: tuple[str, ...] | None = None) -> Path:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    if flight_lines is not None:
        d = home / "hatch-logs" / "hatch-20260710T000000Z"
        d.mkdir(parents=True)
        (d / "flight.log").write_text("\n".join(flight_lines) + "\n",
                                      encoding="utf-8")
    return home


_SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def _mk_toolbox_bin(tmp_path: Path) -> Path:
    """A private bin dir holding ONLY the tools cabinet-feedback.sh needs,
    symlinked from the fixed system dirs — provably gh-free no matter what
    the host preinstalls (GitHub ubuntu runners carry /usr/bin/gh, so a
    bare system PATH is NOT a gh-absence guarantee). The pinned scrub
    engine /usr/bin/grep is an absolute path and needs no PATH entry."""
    tools = ("bash", "awk", "cat", "cp", "cut", "date", "dirname", "head",
             "mktemp", "rm", "sed", "sort", "tail", "tr", "uname", "wc")
    box = tmp_path / "toolbox-bin"
    box.mkdir(exist_ok=True)
    for tool in tools:
        src = shutil.which(tool, path=_SYSTEM_PATH)
        if src is None:  # pragma: no cover — core POSIX tool missing
            pytest.skip(f"system dirs lack {tool!r}; cannot stage the toolbox")
        (box / tool).symlink_to(src)
    return box


def _mk_gh_shim(tmp_path: Path, *, auth_ok: bool = True) -> tuple[Path, Path]:
    """PATH-shim gh that logs every invocation; returns (bin_dir, log_path)."""
    bin_dir = tmp_path / "shim-bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "gh-invocations.log"
    gh = bin_dir / "gh"
    body = ['#!/bin/sh', f'printf \'%s\\n\' "$*" >> "{log}"']
    if not auth_ok:
        body.append('case "$1" in auth) exit 1 ;; esac')
    body.append('exit 0')
    gh.write_text("\n".join(body) + "\n", encoding="utf-8")
    gh.chmod(0o755)
    return bin_dir, log


def _env(root: Path, home: Path, bin_dir: Path | None = None) -> dict[str, str]:
    tmp = home.parent / "subtmp"
    tmp.mkdir(exist_ok=True)
    path = "/usr/bin:/bin:/usr/sbin:/sbin"
    if bin_dir is not None:
        path = f"{bin_dir}:{path}"
    return {
        "CABINET_FEEDBACK_ROOT": str(root),
        "HOME": str(home),
        "USER": "tester",
        "PATH": path,
        "TMPDIR": str(tmp),
        "LC_ALL": "C",
    }


def _run(args: list[str], env: dict[str, str], *, stdin_bytes: bytes | None = None,
         timeout: int = 180) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["bash", str(SCRIPT), *args],
        input=stdin_bytes if stdin_bytes is not None else b"",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, cwd=str(env["TMPDIR"]), timeout=timeout)
    return (proc.returncode, proc.stdout.decode("utf-8", "replace"),
            proc.stderr.decode("utf-8", "replace"))


def _run_interactive(args: list[str], env: dict[str, str], reply: bytes,
                     timeout: int = 180) -> tuple[int, str]:
    """Run with stdin on a real pty (consent path) — output via a pipe."""
    master, slave = pty.openpty()
    proc = None
    try:
        proc = subprocess.Popen(
            ["bash", str(SCRIPT), *args],
            stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=env, cwd=str(env["TMPDIR"]))
        os.close(slave)
        slave = -1
        os.write(master, reply)          # buffered by the tty until the read
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, out.decode("utf-8", "replace")
    finally:
        if slave != -1:
            os.close(slave)
        os.close(master)
        if proc is not None and proc.poll() is None:
            proc.kill()


def _word_hit(word: str, text: str) -> bool:
    """The gate's word-boundary semantics, for assertions."""
    return re.search(rf"(^|[^0-9A-Za-z_]){re.escape(word)}([^0-9A-Za-z_]|$)",
                     text, re.IGNORECASE | re.MULTILINE) is not None


def _bundle_of(out: str) -> str:
    """The postable bundle body (between the review markers). The scrub
    contract binds THIS text — the surrounding UI (e.g. the dry-run argv
    preview) legitimately names the CG-19 canonical repo coordinate."""
    m = re.search(r"---8<--- redacted bundle[^\n]*\n(.*?)\n---8<--- end of bundle",
                  out, re.DOTALL)
    assert m, f"bundle markers not found in output:\n{out}"
    return m.group(1)


# ---------------------------------------------------------------------------
# 1. redaction-proof (full suite)
# ---------------------------------------------------------------------------
@gate_required
def test_planted_captain_suite_tokens_are_scrubbed(tmp_path):
    """Full mode: gate generic classes + fixture captain patterns. The
    planted sub/word tokens come from the fixture patterns file; the digit
    run from the gate's tracked generic class."""
    sub, word = SYN_SUB, SYN_WORD
    root = _mk_root(tmp_path, doctor_lines=(
        f"token {sub} appears here",
        f"standalone {word} name",
        f"chat id {PLANTED_DIGITS} run",
        "all services nominal",
    ))
    home = _mk_home(tmp_path, flight_lines=(
        f"step ok - contact {word}",
        "flight nominal line",
    ))
    rc, out, err = _run(["--dry-run"], _env(root, home))
    assert rc == 0, err
    bundle = _bundle_of(out)
    assert sub not in bundle.lower()               # sub token gone
    assert not _word_hit(word, bundle)             # word token gone
    assert PLANTED_DIGITS not in bundle            # id run gone
    assert bundle.count("[scrubbed]") >= 4         # all four planted lines
    assert "all services nominal" in bundle        # clean lines survive
    assert "flight nominal line" in bundle


@gate_required
def test_title_tripping_the_suite_is_refused(tmp_path):
    word = SYN_WORD
    root = _mk_root(tmp_path, doctor_lines=("nominal",))
    home = _mk_home(tmp_path)
    rc, out, err = _run(["--dry-run", "--title", f"about {word} things"],
                        _env(root, home))
    assert rc != 0
    assert "title trips the leak-scrub suite" in err
    assert "nothing was posted" in err


# ---------------------------------------------------------------------------
# 2. --dry-run never invokes gh (PATH shim proof) — egg-safe (no gate needed)
# ---------------------------------------------------------------------------
def test_dry_run_never_invokes_gh(tmp_path):
    root = _mk_root(tmp_path, gate="absent", doctor_lines=("nominal",))
    home = _mk_home(tmp_path)
    bin_dir, log = _mk_gh_shim(tmp_path)
    rc, out, err = _run(["--dry-run"], _env(root, home, bin_dir))
    assert rc == 0, err
    assert "DRY RUN" in out
    assert "would run: gh issue create" in out     # argv previewed, not run
    assert not log.exists()                        # gh NEVER invoked


# ---------------------------------------------------------------------------
# 3. consent gating
# ---------------------------------------------------------------------------
def test_consent_refusal_posts_nothing(tmp_path):
    root = _mk_root(tmp_path, gate="absent", doctor_lines=("nominal",))
    home = _mk_home(tmp_path)
    bin_dir, log = _mk_gh_shim(tmp_path)
    rc, out = _run_interactive([], _env(root, home, bin_dir), b"n\n")
    assert rc != 0
    assert "aborted by user" in out
    assert "nothing was posted" in out
    invoked = log.read_text(encoding="utf-8") if log.exists() else ""
    assert "issue create" not in invoked           # preflight only, no post


def test_piped_stdin_cannot_consent(tmp_path):
    """A piped "y" is NOT interactive consent — the TTY guard refuses it."""
    root = _mk_root(tmp_path, gate="absent", doctor_lines=("nominal",))
    home = _mk_home(tmp_path)
    bin_dir, log = _mk_gh_shim(tmp_path)
    rc, out, err = _run([], _env(root, home, bin_dir), stdin_bytes=b"y\n")
    assert rc != 0
    assert "stdin is not a TTY" in err
    invoked = log.read_text(encoding="utf-8") if log.exists() else ""
    assert "issue create" not in invoked


def test_consent_yes_posts_via_fixed_argv(tmp_path):
    root = _mk_root(tmp_path, gate="absent", doctor_lines=("nominal",))
    home = _mk_home(tmp_path)
    bin_dir, log = _mk_gh_shim(tmp_path)
    rc, out = _run_interactive([], _env(root, home, bin_dir), b"y\n")
    assert rc == 0, out
    # The canonical repo is parsed from the script under test — the CG-19
    # adjudicated coordinate lives in exactly one place, never here.
    m = re.search(r'^CANONICAL_REPO="([^"]+)"', SCRIPT.read_text(encoding="utf-8"),
                  re.MULTILINE)
    assert m, "CANONICAL_REPO not found in script"
    invoked = log.read_text(encoding="utf-8")
    assert f"issue create --repo {m.group(1)} --title" in invoked
    assert "--label cabinet-feedback" in invoked
    assert "--body-file" in invoked
    assert "issue created" in out


# ---------------------------------------------------------------------------
# 4. honest gh failures
# ---------------------------------------------------------------------------
def test_gh_unauthenticated_fails_honestly(tmp_path):
    root = _mk_root(tmp_path, gate="absent", doctor_lines=("nominal",))
    home = _mk_home(tmp_path)
    bin_dir, log = _mk_gh_shim(tmp_path, auth_ok=False)
    rc, out, err = _run([], _env(root, home, bin_dir))
    assert rc != 0
    assert "not authenticated" in err
    assert "gh auth login" in err
    invoked = log.read_text(encoding="utf-8") if log.exists() else ""
    assert "issue create" not in invoked


def test_gh_missing_fails_honestly(tmp_path):
    """gh-absence made DETERMINISTIC: PATH is a private toolbox of exactly
    the tools the script needs and nothing else. A bare system PATH is not
    enough — GitHub-hosted ubuntu runners preinstall /usr/bin/gh, where the
    script would instead reach the auth preflight and fail with "not
    authenticated" rather than "not installed"."""
    root = _mk_root(tmp_path, gate="absent", doctor_lines=("nominal",))
    home = _mk_home(tmp_path)
    env = _env(root, home)
    env["PATH"] = str(_mk_toolbox_bin(tmp_path))   # toolbox ONLY — no gh
    rc, out, err = _run([], env)
    assert rc != 0
    assert "gh is not installed" in err


# ---------------------------------------------------------------------------
# 5. fail-closed pattern extraction
# ---------------------------------------------------------------------------
def test_present_but_unextractable_gate_fails_closed(tmp_path):
    root = _mk_root(tmp_path, gate="malformed", doctor_lines=("nominal",))
    home = _mk_home(tmp_path)
    rc, out, err = _run(["--dry-run"], _env(root, home))
    assert rc == 2
    assert "could not extract GREP_PATTERNS" in err
    assert "bundle" not in out                     # nothing was built


def test_gate_present_but_patterns_file_missing_fails_closed(tmp_path):
    """R166: a private-side checkout (gate file present) without the
    captain-specific patterns file must REFUSE the bundle — the gate line
    now carries generic classes only, so proceeding would scrub nothing
    personal."""
    root = _mk_root(tmp_path, gate="real", patterns=None,
                    doctor_lines=("nominal",))
    home = _mk_home(tmp_path)
    rc, out, err = _run(["--dry-run"], _env(root, home))
    assert rc == 2
    assert "captain-specific scan patterns not configured" in err
    assert "refusing to build an under-scrubbed bundle" in err
    assert "bundle" not in out                     # nothing was built


def test_malformed_patterns_directive_fails_closed(tmp_path):
    """An unrecognized patterns-file directive aborts naming
    file:LINE-NUMBER only — the content (which may carry a real value)
    must not smear into stderr."""
    root = _mk_root(tmp_path, gate="absent",
                    patterns="pattern sub:qzemployer\nscrub sub:qzsecrettoken\n",
                    doctor_lines=("nominal",))
    home = _mk_home(tmp_path)
    rc, out, err = _run(["--dry-run"], _env(root, home))
    assert rc == 2
    assert "unrecognized directive at" in err
    assert ":2 " in err                            # the line NUMBER...
    assert "qzsecrettoken" not in err              # ...never the content


def test_template_verbatim_patterns_value_fails_closed(tmp_path):
    """Mirror of the publish gate's template-copy refusal (review fix on
    R166): a patterns value still verbatim in the tracked synthetic twin
    means an unedited template copy — it would scrub placeholders, not real
    values. Abort exit 2, naming file:LINE-NUMBER only; the value (which on
    a half-edited file may be a real one) never smears into output."""
    root = _mk_root(tmp_path, gate="absent",
                    patterns="pattern sub:qzedited\npattern sub:qzremnant\n",
                    doctor_lines=("nominal",))
    (root / "instance" / "config" /
     "publish-scan-patterns.local.example").write_text(
        "# synthetic template twin\npattern sub:qzremnant\n",
        encoding="utf-8")
    home = _mk_home(tmp_path)
    rc, out, err = _run(["--dry-run"], _env(root, home))
    assert rc == 2
    assert "appears verbatim among the synthetic template twin's directives" \
        in err
    assert ":2 " in err                            # the line NUMBER...
    assert "qzremnant" not in err                  # ...never the value
    assert "bundle" not in out                     # nothing was built


def test_template_prose_substring_is_not_refused(tmp_path):
    """False-positive guard on the twin-copy refusal (mirrors the gate):
    template '#' prose can carry a real value inside an ordinary English
    word; only DIRECTIVE lines are placeholder carriers. A value found
    solely in prose must scrub normally, never die."""
    root = _mk_root(tmp_path, gate="absent",
                    patterns="pattern word:qzprose\n",
                    doctor_lines=("token qzprose appears here",
                                  "all services nominal"))
    (root / "instance" / "config" /
     "publish-scan-patterns.local.example").write_text(
        "# prose where coordiqzprose rides inside an ordinary word\n"
        "pattern sub:qzplaceholder\n", encoding="utf-8")
    home = _mk_home(tmp_path)
    rc, out, err = _run(["--dry-run"], _env(root, home))
    assert rc == 0, err
    bundle = _bundle_of(out)
    assert "qzprose" not in bundle.lower()       # the value scrubbed...
    assert "all services nominal" in bundle      # ...bundle still built


def test_egg_cut_with_patterns_file_scrubs_captain_tokens(tmp_path):
    """Packaged-egg shape (gate absent) WITH a configured patterns file:
    the captain tokens scrub and the mode is announced as captain+baseline,
    not baseline-only."""
    root = _mk_root(tmp_path, gate="absent", doctor_lines=(
        f"token {SYN_SUB} appears here",
        "all services nominal",
    ))
    home = _mk_home(tmp_path)
    rc, out, err = _run(["--dry-run"], _env(root, home))
    assert rc == 0, err
    assert "BASELINE scrub only" not in err
    bundle = _bundle_of(out)
    assert SYN_SUB not in bundle.lower()
    assert "captain patterns + baseline" in bundle  # suite-mode banner line
    assert "all services nominal" in bundle


# ---------------------------------------------------------------------------
# 6. baseline mode (the packaged-egg shape) — runs everywhere
# ---------------------------------------------------------------------------
def test_baseline_mode_scrubs_home_email_and_digit_runs(tmp_path):
    home = _mk_home(tmp_path)
    root = _mk_root(tmp_path, gate="absent", patterns=None, doctor_lines=(
        f"home dir is {home} today",
        "mail me at someone@example.com please",
        f"id {PLANTED_DIGITS} run",
        "clean line stays",
    ))
    rc, out, err = _run(["--dry-run"], _env(root, home))
    assert rc == 0, err
    assert "BASELINE scrub only" in err            # mode announced honestly
    bundle = _bundle_of(out)
    assert str(home) not in bundle
    assert "someone@example.com" not in bundle
    assert PLANTED_DIGITS not in bundle
    assert "clean line stays" in bundle
    assert bundle.count("[scrubbed]") >= 3


# ---------------------------------------------------------------------------
# 7. zero-hit pass-through (regression) — runs everywhere
# ---------------------------------------------------------------------------
def test_zero_hit_bundle_survives_intact(tmp_path):
    """A bundle with ZERO scrub hits must print IN FULL. The original
    two-file awk (NR==FNR) treated every bundle line as a hit-list record
    when the hit list was empty and silently emptied the whole bundle — the
    CLEAN-environment case (scratch root outside $HOME, nominal doctor
    output, no flight logs) is exactly the one that broke, and every
    content-asserting test above plants itself at least one hit."""
    home = _mk_home(tmp_path)                       # no flight logs
    root = _mk_root(tmp_path, gate="absent",
                    doctor_lines=("all services nominal",))
    rc, out, err = _run(["--dry-run"], _env(root, home))
    assert rc == 0, err
    bundle = _bundle_of(out)
    assert "all services nominal" in bundle         # doctor output intact
    assert "## versions" in bundle                  # gathered sections intact
    assert "## hatch flight log" in bundle
    assert "0 line(s) replaced with [scrubbed]" in bundle   # honest count
    # ...and NO line was redacted: the banner's own wording (asserted just
    # above) is the marker's only occurrence in the whole bundle.
    assert bundle.count("[scrubbed]") == 1


# ---------------------------------------------------------------------------
# 8. binary-tinged bundle (NUL byte) still scrubs — runs everywhere
# ---------------------------------------------------------------------------
def test_binary_tinged_bundle_still_scrubs(tmp_path):
    """A single NUL byte in the gathered bundle (crashed-process doctor
    output, a binary-tinged flight-log tail) must NOT disarm the scrubber.
    Regression: without forced text mode (grep -a), the file scan degraded
    to "Binary file ... matches" — no -n line numbers — so scrub_file
    replaced ZERO lines while the banner still claimed a positive count:
    a silent fail-open with a false redaction receipt, reproduced
    end-to-end (planted email + digit run printed unredacted). The planted
    self-test could not catch it: it probes line_matches via stdin text,
    not the file-scan path that degrades."""
    home = _mk_home(tmp_path)
    root = _mk_root(tmp_path, gate="absent", doctor_lines=(
        "binary\x00tinged line",                            # the NUL trigger
        "then\x00mail planted.after.nul@example.com too",   # token AFTER a NUL
        "mail me at someone@example.com please",
        f"id {PLANTED_DIGITS} run",
        "clean line stays",
    ))
    rc, out, err = _run(["--dry-run"], _env(root, home))
    assert rc == 0, err
    bundle = _bundle_of(out)
    assert "planted.after.nul@example.com" not in bundle    # post-NUL token gone
    assert "someone@example.com" not in bundle              # email gone
    assert PLANTED_DIGITS not in bundle                     # id run gone
    assert "clean line stays" in bundle                     # clean lines survive
    # HONEST receipt: exactly the three planted lines were replaced — the
    # banner count matches reality, and the only [scrubbed] occurrence
    # beyond those three lines is the banner's own wording.
    assert "3 line(s) replaced with [scrubbed]" in bundle
    assert bundle.count("[scrubbed]") == 4
