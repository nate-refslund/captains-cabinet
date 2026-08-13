"""A value in cabinet/.env can never EXECUTE when a script `source`s the file.

WHAT THIS GUARDS. cabinet/.env is written by setup-env.sh / provision-local-
postgres.sh / telegram-capture-chat-id.sh (`set_env_key`) and then bash-`source`d
by 30+ scripts, several under `set -a`. A value of `FOO=$(rm -rf ~)` written raw
EXECUTES at assignment on the next source — command substitution runs before the
value is ever read. The fix single-quotes anything that is not provably literal
(the `_env_quote` helper the three writer-scripts share); this pins that the REAL
helper bytes, on the deployment's own bash, turn every hostile shape into inert
text AND round-trip a legitimate value unchanged.

This runs the ACTUAL functions extracted from the scripts — not a re-implementation
— on `/bin/bash` (macOS 3.2, the deployment target), and asserts against what bash
does on `source`, which is the only thing that can tell an inert value from an
executing one.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
SETUP_ENV = SCRIPTS_DIR / "setup-env.sh"
PROVISION_PG = SCRIPTS_DIR / "provision-local-postgres.sh"
TG_CAPTURE = SCRIPTS_DIR / "telegram-capture-chat-id.sh"
WRITER_SCRIPTS = [SETUP_ENV, PROVISION_PG, TG_CAPTURE]

MIN_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def _extract_helpers(script: Path) -> str:
    """The `_env_quote` + `_env_unquote` block, verbatim, from a writer script.

    Both are consecutive top-level functions; the block runs from the
    `_env_quote() {` line through the second column-0 `}` that closes
    `_env_unquote`."""
    lines = script.read_text().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("_env_quote() {"))
    closes = 0
    for j in range(start, len(lines)):
        if lines[j] == "}":
            closes += 1
            if closes == 2:
                return "\n".join(lines[start : j + 1]) + "\n"
    raise AssertionError(f"could not extract the helper block from {script}")


HELPERS = _extract_helpers(SETUP_ENV)


def _bash(script_body: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/bash", "-c", script_body],
        capture_output=True,
        text=True,
        env={"PATH": MIN_PATH},
        timeout=60,
    )


def test_the_three_writers_share_byte_identical_helpers():
    """A divergent copy is how a security fix rots. All three must match."""
    bodies = {s.name: _extract_helpers(s) for s in WRITER_SCRIPTS}
    ref = HELPERS
    for name, body in bodies.items():
        assert body == ref, f"{name} has a divergent _env_quote/_env_unquote block"


# Shapes that, written raw into `KEY=<here>` and sourced, execute or break the
# line. `MARKER` is a placeholder the harness rewrites to a real temp path.
HOSTILE = [
    "$(touch MARKER)",
    "`touch MARKER`",
    "pre$(touch MARKER)post",
    "x; touch MARKER",
    "x && touch MARKER",
    "x | touch MARKER",
    "x > MARKER",
    "(touch MARKER)",
    "a touch MARKER",          # unquoted space splits the assignment word
    "${HOME}",
    "~root/x",
    "v\"$(touch MARKER)\"",     # a value that itself contains a double-quoted subst
]

LEGIT = [
    "70012345:AAE-token_x.y/z",
    "-10012345",
    "postgresql://u:p@h/db",
    "postgresql://u:p%40ss@h:5432/db?sslmode=require&x=1",
    "O'Brien",
    "a'b'c",
    "has a space",
    "café-☕-Ünïcode",
    "",
]


@pytest.mark.parametrize("shape", HOSTILE, ids=lambda s: s[:24])
def test_hostile_value_is_inert_on_source(shape, tmp_path):
    marker = tmp_path / "PWNED"
    value = shape.replace("MARKER", str(marker))
    env_file = tmp_path / ".env"
    # Quote via the REAL helper, write KEY=<quoted>, then source in a real bash.
    body = f"""
set -euo pipefail
{HELPERS}
q="$(_env_quote {_sq(value)})"
printf 'K=%s\\n' "$q" > {_sq(str(env_file))}
set -a; source {_sq(str(env_file))}; set +a
printf '%s' "$K"
"""
    r = _bash(body)
    assert r.returncode == 0, r.stderr
    assert not marker.exists(), f"sourcing .env executed the payload: {shape}"
    assert r.stdout == value, f"value did not round-trip: {r.stdout!r} != {value!r}"


@pytest.mark.parametrize("value", LEGIT, ids=lambda s: (s or "<empty>")[:24])
def test_legit_value_round_trips_through_quote_and_unquote(value, tmp_path):
    env_file = tmp_path / ".env"
    body = f"""
set -euo pipefail
{HELPERS}
q="$(_env_quote {_sq(value)})"
printf 'K=%s\\n' "$q" > {_sq(str(env_file))}
# 1) what bash assigns on source
set -a; source {_sq(str(env_file))}; set +a
printf '%s\\n' "$K"
# 2) what the hand-parser (_env_unquote) reads from the stored text
raw="$(grep -E '^K=' {_sq(str(env_file))} | head -1)"
_env_unquote "${{raw#K=}}"
"""
    r = _bash(body)
    assert r.returncode == 0, r.stderr
    sourced, unquoted = r.stdout.split("\n", 1)
    unquoted = unquoted.rstrip("\n")
    assert sourced == value, f"source: {sourced!r} != {value!r}"
    assert unquoted == value, f"unquote: {unquoted!r} != {value!r}"


def test_plain_value_stays_bare_no_consumer_churn(tmp_path):
    """The common case must be byte-identical to today so the many `cut -d= -f2-`
    readers of plain keys are unaffected."""
    env_file = tmp_path / ".env"
    body = f"""
{HELPERS}
printf 'TOKEN=%s\\n' "$(_env_quote '70012345:AAE-token')"
printf 'EMPTY=%s\\n' "$(_env_quote '')"
"""
    r = _bash(body)
    assert r.returncode == 0, r.stderr
    assert "TOKEN=70012345:AAE-token\n" in r.stdout, "a plain value must stay bare"
    assert "EMPTY=\n" in r.stdout, "an empty value must stay bare (KEY=)"


def test_defaults_env_sources_cleanly_and_runs_nothing(tmp_path):
    """End-to-end: the wizard's own --defaults output must source without
    executing anything or erroring."""
    root = tmp_path / "root"
    (root / "cabinet").mkdir(parents=True)
    template = (SCRIPTS_DIR.parent / ".env.example").read_text()
    (root / "cabinet" / ".env.example").write_text(template)
    env = {"PATH": MIN_PATH, "HOME": str(root), "CABINET_ROOT": str(root)}
    gen = subprocess.run(
        ["/bin/bash", str(SETUP_ENV), "--defaults"],
        capture_output=True, text=True, env=env, timeout=60,
    )
    assert gen.returncode == 0, gen.stdout + gen.stderr
    marker = tmp_path / "MUST_NOT_EXIST"
    env_file = root / "cabinet" / ".env"
    r = _bash(
        f"set -a; source {_sq(str(env_file))}; set +a; echo ok"
    )
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout
    assert not marker.exists()


def _sq(s: str) -> str:
    """POSIX single-quote a Python string for safe interpolation into a bash -c
    body (mirrors the shell helper under test, kept independent of it)."""
    return "'" + s.replace("'", "'\\''") + "'"
