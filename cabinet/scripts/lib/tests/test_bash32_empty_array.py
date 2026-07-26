"""macOS ``/bin/bash`` 3.2 empty-array guards for the officer boot path.

WHY THIS MODULE EXISTS
======================
macOS ships ``/bin/bash`` **3.2.57** and always will (Apple froze it at the
last GPLv2 release; a newer bash only ever arrives as a *separate* Homebrew
binary).  In bash 3.2, expanding an **empty** array under ``set -u`` aborts::

    $ /bin/bash -c 'set -u; a=(); echo "${a[@]}"'
    /bin/bash: a[@]: unbound variable

Bash >= 4.4 allows it.  Every officer LaunchAgent hardcodes ``/bin/bash``
(``cabinet/launchd/com.cabinet.officer.template.plist``) and every officer
launcher runs ``set -euo pipefail``, so this is not a style nit: one empty
array on a boot path takes the whole fleet down on the only OS the fleet runs
on.  It did exactly that between 2026-07-15 and this module's landing —
``officer_env_load_file`` built ``local -a _observe_arg=()`` and expanded it
unguarded, so the DEFAULT (not observe-only) path — i.e. every normal boot —
died, and the error text blamed ``cabinet/.env`` rather than the shell.

WHY THE EXISTING TESTS DID NOT CATCH IT
=======================================
Two independent sensor failures, and the second is the interesting one:

1. All seven CI jobs are ``ubuntu-latest`` (bash 5.x), where the construct is
   legal.  CI structurally cannot see this class.
2. ``test_officer_env.py`` *does* call ``officer_env_load_file`` under
   ``/bin/bash`` — but its harnesses run ``set -e`` only, never ``set -u``,
   while the real callers run ``set -euo pipefail``.  So all 18 of those tests
   passed **on a Mac, under bash 3.2, while no officer could boot.**  A harness
   that does not reproduce the caller's shell options is not a sensor for
   anything the shell options decide.

Every test below therefore runs the code path under the *real* interpreter
(``/bin/bash``, resolved by absolute path — never ``bash`` from ``PATH``, which
is how a bash-5 machine gives a false green) with the *real* shell options.

HONEST SKIP CONTRACT
====================
These tests need an interpreter that actually has the 3.2 behaviour.  On bash
>= 4.4 they SKIP with a reason naming the interpreter and version, rather than
passing vacuously.  In practice that means **CI (ubuntu) skips every test in
this module** — the framework suite runs pytest with ``-rs`` so the skip and
its reason are printed, never silent.  The macOS-only coverage is deliberate
and is the point: the defect is macOS-only.

The interpreter-independent half of this guard — a whole-tree ratchet that
goes red on the same *shape* anywhere in the tree — lives in
``framework/tests/test_bash32_empty_array_ratchet.py`` and DOES run on CI.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Tree listing — must work on the DELIVERED egg, which has no ``.git``.
#
# ``hatch.sh`` and ``null-hatch.sh`` both export with ``git archive HEAD |
# tar -x`` (null-hatch falls back to a ``--exclude='./.git'`` tree copy), so
# the artifact a stranger unpacks and runs this suite on is gitless. A listing
# that shells out to ``git ls-files`` under ``check=True`` turns that into a
# hard ERROR — the same shape that took ``bash cabinet/scripts/null-hatch.sh``
# from exit 0 to exit 1 via the ratchet twin of this module.
#
# Pruned on the WALK path only (git already excludes them). Verified
# 2026-07-26: no tracked file lives under any of these names, and
# ``test_the_sandbox_copies_the_same_tree_without_git`` goes red the day that
# changes.
# ---------------------------------------------------------------------------
_WALK_PRUNE = frozenset(
    {
        ".git", ".hg", ".svn",
        "node_modules",
        "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        ".venv", "venv",
        ".next", "out", "dist", "build",
        "pgdata", "redisdata",
    }
)


# Ambient git-control env vars — a leaked GIT_DIR/GIT_WORK_TREE would point the
# probe below at a DIFFERENT repository, making the listing mode depend on the
# caller's environment rather than on the filesystem. Child process only.
_GIT_ENV_OVERRIDES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
    "GIT_CEILING_DIRECTORIES",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
)


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
    for name in _GIT_ENV_OVERRIDES:
        env.pop(name, None)
    return env


def _git_tracked_files(root: Path) -> list[Path] | None:
    """Tracked files under ``root``, or ``None`` when git cannot answer FOR IT.

    The toplevel comparison is not belt-and-braces. Unpack a gitless egg inside
    some *other* checkout and ``git ls-files`` SUCCEEDS, listing the outer
    repo's tracked files under this directory — i.e. none of them, exit 0. The
    sandbox would come out EMPTY and the officer-boot assertion below would
    fail with a mystery, or worse, some future caller would read the empty copy
    as a clean result.
    """
    toplevel = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
        env=_git_env(),
    )
    if toplevel.returncode != 0 or not toplevel.stdout.strip():
        return None
    if Path(toplevel.stdout.strip()).resolve() != root.resolve():
        return None
    listing = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        check=False,
        env=_git_env(),
    )
    if listing.returncode != 0:
        return None
    return [
        root / raw.decode()
        for raw in listing.stdout.split(b"\0")
        if raw and (root / raw.decode()).is_file()
    ]


def _walked_files(root: Path) -> list[Path]:
    """Filesystem fallback for a gitless tree — the delivered egg."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _WALK_PRUNE)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.is_file():
                found.append(path)
    return found


def _tree_files(root: Path) -> list[Path]:
    """Every shipped file under ``root`` — git listing when git can answer for
    it, filesystem walk otherwise."""
    tracked = _git_tracked_files(root)
    return tracked if tracked is not None else _walked_files(root)


BIN_BASH = "/bin/bash"
ROOT = Path(__file__).resolve().parents[4]
SHELL_LIB = ROOT / "cabinet" / "scripts" / "lib" / "officer-env.sh"
BOOTSTRAP_ROLES = ROOT / "cabinet" / "scripts" / "bootstrap-roles.sh"
START_OFFICER_MAC = ROOT / "cabinet" / "scripts" / "start-officer-mac.sh"


def _bash_major_minor() -> tuple[int, int]:
    """(major, minor) of /bin/bash — read from the interpreter, not uname."""
    out = subprocess.run(
        [BIN_BASH, "-c", 'printf "%s %s" "${BASH_VERSINFO[0]}" "${BASH_VERSINFO[1]}"'],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.split()
    return int(out[0]), int(out[1])


def _requires_legacy_bash() -> None:
    """Skip loudly on an interpreter that cannot exhibit the defect."""
    if not os.path.exists(BIN_BASH):
        pytest.skip(f"no {BIN_BASH} on this host — nothing to guard")
    major, minor = _bash_major_minor()
    if (major, minor) >= (4, 4):
        pytest.skip(
            f"{BIN_BASH} is bash {major}.{minor}, which permits empty-array "
            "expansion under `set -u`. This guard only has teeth on the bash "
            "3.2 that macOS ships, which is the only OS the officer fleet "
            "runs on. Skipped honestly rather than passed vacuously."
        )


def _scope_file(tmp_path: Path) -> Path:
    path = tmp_path / "mcp-scope.yml"
    path.write_text(
        "agents:\n"
        "  cto:\n"
        "    mcps: [notion, telegram]\n"
        "universal: [library]\n"
    )
    return path


def _dotenv(tmp_path: Path) -> Path:
    path = tmp_path / "officer.env"
    path.write_text("NOTION_API_KEY=n-key\nTELEGRAM_CTO_TOKEN=t-key\n")
    return path


def _load_file_under_launcher_options(tmp_path: Path, observe: str) -> subprocess.CompletedProcess:
    """Source the library and call the loader with the REAL launcher options.

    ``set -euo pipefail`` is copied verbatim from
    ``cabinet/scripts/start-officer-mac.sh``; reproducing it is the entire
    point of this helper.
    """
    script = f"""
      set -euo pipefail
      source {SHELL_LIB!s}
      officer_env_load_file {_dotenv(tmp_path)!s} cto
      printf 'NOTION=%s\\n' "${{NOTION_API_KEY:-<unset>}}"
      printf 'NAMES=%s\\n' "${{CABINET_OFFICER_ENV_NAMES:-<unset>}}"
    """
    env = dict(os.environ)
    env.update(
        CABINET_MCP_SCOPE_FILE=str(_scope_file(tmp_path)),
        CABINET_OBSERVE_ONLY=observe,
        PYTHONDONTWRITEBYTECODE="1",
    )
    env.pop("CABINET_OFFICER_ENV_NAMES", None)
    env.pop("NOTION_API_KEY", None)
    return subprocess.run(
        [BIN_BASH, "-c", script], text=True, capture_output=True, check=False, env=env
    )


def test_bin_bash_really_rejects_empty_array_expansion_under_set_u():
    """Pin the interpreter property the rest of this module depends on.

    If this ever stops holding on a machine, the other tests are measuring
    nothing and the skip logic above is the thing to re-derive.
    """
    _requires_legacy_bash()
    unguarded = subprocess.run(
        [BIN_BASH, "-c", 'set -u; a=(); echo "${a[@]}"'],
        text=True,
        capture_output=True,
        check=False,
    )
    assert unguarded.returncode != 0, (
        "this /bin/bash accepted an empty-array expansion under `set -u`; the "
        "version gate in _requires_legacy_bash() is wrong"
    )
    assert "unbound variable" in unguarded.stderr

    guarded = subprocess.run(
        [BIN_BASH, "-c", 'set -u; a=(); echo "${a[@]+"${a[@]}"}"; echo ok'],
        text=True,
        capture_output=True,
        check=False,
    )
    assert guarded.returncode == 0, guarded.stderr
    assert "ok" in guarded.stdout


def test_officer_env_load_file_survives_the_launcher_shell_options(tmp_path: Path):
    """THE regression sensor: the DEFAULT boot path must not abort.

    Default here means ``CABINET_OBSERVE_ONLY=0`` — the observe-only array is
    EMPTY, which is precisely why the default path was the broken one and no
    env override could route around it.
    """
    _requires_legacy_bash()
    result = _load_file_under_launcher_options(tmp_path, observe="0")
    assert "unbound variable" not in result.stderr, (
        "empty-array expansion aborted the officer credential load under "
        f"`set -euo pipefail` on {BIN_BASH}:\n{result.stderr}"
    )
    assert result.returncode == 0, result.stderr
    # Not just "did not crash" — the credential actually projected.
    assert "NOTION=n-key" in result.stdout, result.stdout


def test_observe_only_still_reaches_the_parser_and_scrubs_remote_credentials(
    tmp_path: Path,
):
    """The flag must not be silently DROPPED by a fix for the empty case.

    ``--observe-only`` is a credential-SCOPING control: with it the parser
    subtracts remote MCP credentials.  A "fix" that expanded the array to
    nothing in both branches would widen the projected credential set while
    every other test stayed green, so this asserts the scoping still bites.

    (This arm also passes against the pre-fix code — the array is non-empty on
    this path, which is exactly why the bug hid.  It guards the *fix*, not the
    original defect.)
    """
    _requires_legacy_bash()
    result = _load_file_under_launcher_options(tmp_path, observe="1")
    assert result.returncode == 0, result.stderr
    assert "NOTION=<unset>" in result.stdout, (
        "observe-only no longer subtracts the remote MCP credential — the "
        f"--observe-only flag is not reaching the parser:\n{result.stdout}"
    )
    assert "TELEGRAM_CTO_TOKEN" in result.stdout


def test_bootstrap_roles_capability_args_survive_an_empty_capability_list():
    """The same shape on the hatch's roster-seeding path.

    ``bootstrap-roles.sh`` validates ``caps`` non-empty before ``seed_role``,
    so the empty case is currently unreachable through the roster reader — this
    executes the file's OWN expansion text with an empty array so the guard is
    proven by execution rather than by reading the source.
    """
    _requires_legacy_bash()
    source = BOOTSTRAP_ROLES.read_text(encoding="utf-8")
    expansions = re.findall(r"^\s*(\S*cap_args\[@\]\S*)\s*\\?$", source, re.MULTILINE)
    assert expansions, (
        "no cap_args expansion found in bootstrap-roles.sh — this test is "
        "pinned to a code shape that moved; re-derive it from the file"
    )
    for expansion in expansions:
        probe = f"""
          set -euo pipefail
          cap_args=()
          count() {{ printf 'argc=%s\\n' "$#"; }}
          count {expansion}
        """
        result = subprocess.run(
            [BIN_BASH, "-c", probe], text=True, capture_output=True, check=False
        )
        assert result.returncode == 0, (
            f"{expansion} aborts on an empty array under `set -euo pipefail`:\n"
            f"{result.stderr}"
        )
        # Zero args, not one empty string: an empty positional would reach the
        # org-runtime CLI as an unrecognized argument.
        assert "argc=0" in result.stdout, result.stdout


# --------------------------------------------------------------------------
# End-to-end property: can an officer actually boot?
# --------------------------------------------------------------------------


def _sandbox_repo(tmp_path: Path, root: Path = ROOT) -> Path:
    """Materialise the shipped WORKING TREE under ``root`` into an isolated copy.

    The working tree (not ``HEAD``) is the right source here: launchd executes
    the live checkout, so that is the thing whose bootability this asserts.
    In a checkout only ``git ls-files`` paths are copied — no ``.git``, no
    untracked debris; in a gitless export (the delivered egg) the same set is
    reached by walking, since the export *is* the tracked tree.

    The copy is always gitless, which makes it a usable ``root`` for a second
    pass — that is how the walk path gets exercised on a git-having host.
    """
    sandbox = tmp_path / "repo"
    for src in _tree_files(root):
        dst = sandbox / src.relative_to(root)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return sandbox


def _relative_files(base: Path) -> set[str]:
    return {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()}


def _require_boot_tools() -> None:
    for tool in ("python3.12", "jq"):
        if shutil.which(tool) is None:
            pytest.skip(f"{tool} not on PATH — officer boot assembly needs it")


def _dry_run_boot(sandbox: Path, scratch: Path) -> subprocess.CompletedProcess:
    """Run proof-c1 against ``sandbox`` and hand back the raw result."""
    # A dotenv must exist or the launcher skips credential projection entirely
    # (the `if [ -f "cabinet/.env" ]` arm) and never enters the affected code.
    (sandbox / "cabinet" / ".env").write_text("TELEGRAM_BOT_TOKEN=dry-run-only\n")
    # Egress enforcement is an orthogonal runtime gate that wants a live proxy
    # attested on the host; a hatch arms it before proof-c1 runs. Standing that
    # up here would test the proxy, not the shell. Neutralised in the SANDBOX
    # copy only — the tracked config is untouched.
    (sandbox / "instance" / "config" / "egress.yml").write_text(
        "enforce: false\nallow_product: false\nallow_hosts: []\n"
    )

    home = scratch / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "LANG": "en_US.UTF-8",
        "TMPDIR": str(scratch),
        "PYTHONDONTWRITEBYTECODE": "1",
        "CABINET_ROOT": str(sandbox),
        "CABINET_SOURCE_REPO": str(sandbox),
    }
    return subprocess.run(
        [BIN_BASH, str(sandbox / "cabinet" / "scripts" / "start-officer-mac.sh"),
         "cos", "--dry-run"],
        text=True,
        capture_output=True,
        check=False,
        env=env,
        cwd=str(sandbox),
    )


def _assert_officer_booted(result: subprocess.CompletedProcess) -> None:
    assert "unbound variable" not in result.stderr, (
        f"officer boot died on an empty-array expansion:\n{result.stderr}"
    )
    assert result.returncode == 0, (
        f"officer boot assembly failed (exit {result.returncode}):\n"
        f"--- stderr ---\n{result.stderr}\n--- stdout ---\n{result.stdout}"
    )
    # It assembled a real claude invocation, not an empty string.
    assert "claude --model" in result.stdout, result.stdout


def test_officer_boot_command_assembles_under_bin_bash(tmp_path: Path):
    """The property the launcher exists to deliver: an officer can boot.

    ``start-officer-mac.sh <officer> --dry-run`` is the hatch's own proof-c1
    step ("dry render: officer boot command assembly (zero side effects)"). It
    writes nothing to the live cache, starts no tmux, touches no Redis and
    boots nothing — it assembles the command and exits.  Against the pre-fix
    library this exits 2 at credential projection.
    """
    _requires_legacy_bash()
    _require_boot_tools()
    sandbox = _sandbox_repo(tmp_path)
    _assert_officer_booted(_dry_run_boot(sandbox, tmp_path))


def test_the_sandbox_copies_the_same_tree_without_git(tmp_path: Path):
    """The sandbox must materialise from a GITLESS tree — the delivered egg.

    Deliberately NOT gated on ``_requires_legacy_bash``: unlike every other
    test here, this defect is interpreter-independent, so this arm is the one
    that stays awake on CI (ubuntu, bash 5) where the rest honestly skip. That
    matters — the git-only listing shipped precisely because no ubuntu job
    could see it.

    It also pins the walk against the git listing file-for-file, so portability
    cannot be bought with lost coverage: an over-broad ``_WALK_PRUNE`` shows up
    here as a missing file, not as a quietly smaller scan.
    """
    from_git = _sandbox_repo(tmp_path / "from-git")
    assert not (from_git / ".git").exists(), "a tracked-files copy must be gitless"
    assert _git_tracked_files(from_git) is None, (
        "the copy still answers as a git repository, so the walk path was "
        "never exercised"
    )

    from_walk = _sandbox_repo(tmp_path / "from-walk", root=from_git)

    assert _relative_files(from_walk) == _relative_files(from_git)
    # Non-vacuity: two identical EMPTY copies would satisfy the line above.
    assert (from_walk / "cabinet" / "scripts" / "start-officer-mac.sh").is_file()
    assert (from_walk / "cabinet" / "scripts" / "lib" / "officer-env.sh").is_file()


def test_officer_boot_command_assembles_from_a_gitless_export(tmp_path: Path):
    """proof-c1 on the artifact a STRANGER actually receives.

    The egg has no ``.git``; a listing that requires one cannot even stage the
    sandbox, so the boot property goes untested exactly where nobody has a
    checkout to fall back on.
    """
    _requires_legacy_bash()
    _require_boot_tools()
    egg = _sandbox_repo(tmp_path / "egg")          # gitless by construction
    sandbox = _sandbox_repo(tmp_path / "boot", root=egg)   # staged by the walk
    _assert_officer_booted(_dry_run_boot(sandbox, tmp_path / "boot"))


def test_start_officer_mac_uses_the_shell_options_these_guards_assume():
    """If the launcher stops using ``set -u`` the sensors above go quiet.

    That would not be a bug in itself, but it would silently retire this
    module's teeth, so it is asserted rather than assumed.
    """
    assert re.search(
        r"^set -euo pipefail$", START_OFFICER_MAC.read_text(encoding="utf-8"), re.MULTILINE
    ), (
        "start-officer-mac.sh no longer runs `set -euo pipefail`; re-derive "
        "whether this module still guards anything"
    )
