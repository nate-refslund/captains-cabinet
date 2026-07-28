"""Behavioural tests for the memory layer's two honesty seams (2026-07-28).

Both arms come from a live exercise of the cabinet on a REAL document corpus
(157 repo docs embedded whole-file through the shipped backfill + worker):

1. ``memory_empty_reason`` — ten of ten natural-language questions returned
   "No results found." while the answering document sat in the pool the whole
   time, because a question-shaped query against a long whole-file embedding
   peaks near 0.30-0.42 and the default vec floor is 0.45. The floor verdict
   and an genuinely empty store printed the SAME line, so a total recall
   failure was indistinguishable from a quiet day.

2. caller-set ``VOYAGE_API_KEY`` — the credential was the one member of the
   embed seam missing from memory.sh's caller-wins restore list, so a harness
   that exported a deliberately bad key to simulate a provider outage was
   silently still talking to the live provider and reported success.

These drive the real bash functions in a throwaway CABINET_ROOT. No network,
no Neon, no Voyage: ``memory_empty_reason`` is pure, and the key-precedence
arm only inspects variable state after sourcing.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

_REAL_POPEN = subprocess.Popen

MEMORY_SH = Path(__file__).resolve().parents[2] / "lib" / "memory.sh"


def _bash(script: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        return subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True,
            cwd=str(cwd) if cwd else None, timeout=60,
        )
    finally:
        subprocess.Popen = patched


def _root(tmp_path: Path, env_body: str = "") -> Path:
    """A throwaway CABINET_ROOT holding only cabinet/.env — memory.sh reads
    nothing else at source time."""
    (tmp_path / "cabinet").mkdir(parents=True, exist_ok=True)
    (tmp_path / "cabinet" / ".env").write_text(env_body, encoding="utf-8")
    return tmp_path


def _call(root: Path, args: str, pre: str = "") -> subprocess.CompletedProcess:
    return _bash(
        f'set -uo pipefail; export CABINET_ROOT="{root}"; {pre} '
        f'source "{MEMORY_SH}"; memory_empty_reason {args}'
    )


# --- arm 1: the floor verdict is distinguishable from an empty store -------

def test_empty_store_says_the_store_is_empty(tmp_path):
    out = _call(_root(tmp_path), "0 0.45 'anything'").stdout
    assert "0 searchable rows" in out, out
    # It must NOT blame the floor when there was nothing to floor out.
    assert "floor" not in out.split("nothing to recall")[0], out


def test_floor_verdict_names_the_floor_the_count_and_the_knob(tmp_path):
    out = _call(_root(tmp_path), "186 0.45 'how do I undo something'").stdout
    assert "186 row(s) were in scope" in out, out
    assert "0.45" in out, out                    # the floor that discarded them
    assert "NONE cleared" in out, out            # a verdict, not an absence
    assert "--min-score" in out, out             # the knob that widens it


def test_unknown_row_count_still_reports_the_floor(tmp_path):
    out = _call(_root(tmp_path), "'' 0.45 'q'").stdout
    assert "row count unavailable" in out, out
    assert "0.45" in out, out


def test_floor_falls_back_to_the_env_default_when_unset(tmp_path):
    out = _call(_root(tmp_path), "42 '' 'q'",
                pre="export CABINET_MEMORY_MIN_SCORE=0.31;").stdout
    assert "0.31" in out, out


def test_reason_is_pure_and_never_fails(tmp_path):
    """Junk arguments degrade to a message, never a non-zero exit — the
    caller is already on its error path when it asks."""
    for args in ("", "'not-a-number' 'junk' ''", "-5 0.45 ''"):
        p = _call(_root(tmp_path), args)
        assert p.returncode == 0, (args, p.stderr)
        assert p.stdout.strip(), args


# --- arm 2: a caller-set embed credential survives the .env back-fill ------

def _key_after_source(root: Path, exported: str | None) -> str:
    pre = f'export VOYAGE_API_KEY="{exported}";' if exported is not None else ""
    p = _bash(
        f'set -uo pipefail; export CABINET_ROOT="{root}"; {pre} '
        f'source "{MEMORY_SH}"; printf "%s" "${{VOYAGE_API_KEY:-}}"'
    )
    return p.stdout


def test_caller_set_voyage_key_wins_over_dotenv(tmp_path):
    root = _root(tmp_path, "VOYAGE_API_KEY=dotenv-key-value\n")
    assert _key_after_source(root, "caller-key-value") == "caller-key-value"


def test_dotenv_key_still_backfills_when_caller_sets_none(tmp_path):
    """The back-fill itself must be preserved — a keyless caller still gets
    the deployment's key, which is the whole point of the .env read."""
    root = _root(tmp_path, "VOYAGE_API_KEY=dotenv-key-value\n")
    assert _key_after_source(root, None) == "dotenv-key-value"


def test_deliberately_bad_caller_key_is_not_healed_by_dotenv(tmp_path):
    """The outage-drill case: a harness that exports a bad key must KEEP it,
    or the drill silently exercises the live provider and reports success."""
    root = _root(tmp_path, "VOYAGE_API_KEY=real-live-key\n")
    assert _key_after_source(root, "sk-invalid-outage-simulation") == \
        "sk-invalid-outage-simulation"


def test_documented_seam_vars_keep_their_caller_wins_contract(tmp_path):
    """Control arm: the credential now behaves like the seam triple already
    did — if this regresses, the restore block was rewritten wrongly."""
    root = _root(tmp_path, "EMBED_MODEL=dotenv-model\nVOYAGE_API_KEY=dotenv-key\n")
    p = _bash(
        f'set -uo pipefail; export CABINET_ROOT="{root}"; '
        f'export EMBED_MODEL=caller-model VOYAGE_API_KEY=caller-key; '
        f'source "{MEMORY_SH}"; printf "%s|%s" "$EMBED_MODEL" "$VOYAGE_API_KEY"'
    )
    assert p.stdout == "caller-model|caller-key", p.stdout
