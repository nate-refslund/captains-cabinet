"""COG-1 W5 — cutover pointer/flip + capture inverse + consumer version-dispatch.

Plan: docs/plans/cognitive-core-phase-1-contract-2026-07-20.md
  §8.4  cutover = one command (pointer flip, atomic, host-global default path)
  §8.5  rollback = the inverse one command (legacy) + disarm capture inverse
  §5.1/§8.4  my-tasks.sh emit_event pointer consult (absent/unreadable -> legacy
             fail-safe; a NO-env-var context observes the flip via the default)
  §12.4 disarm/enable wrap ALTER TABLE officer_tasks DISABLE/ENABLE TRIGGER
        trg_officer_tasks_outbox_capture — the second rehearsed inverse
  §9.1 (11th rig) consumer-compat: a RELAY-EMITTED v2 entry consumed end-to-end
        through task-events-watch's --once drain; the v1-only-revert mutant fails

Tests-first (§12.2 items 8-9): every gate ships with its negative control.
Hermetic by default (the test_task_events_watch.py convention — NO redis/network
for the consumer rig; seam-injected). The DB capture-inverse rehearsal drives the
W2 ephemeral PostgreSQL 17 harness and SKIPS without a major-17 toolchain (S0 pin:
the production work store is 17.10). Run:
  python3.12 -m pytest cabinet/scripts/tests/test_cog1_cutover.py -q
"""
from __future__ import annotations

import importlib.util as _ilu
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
FLIP = REPO / "cabinet" / "scripts" / "cog1-authority-flip.sh"
MY_TASKS = REPO / "cabinet" / "scripts" / "my-tasks.sh"
CONSUMER = REPO / "cabinet" / "scripts" / "task-events-watch.py"


def _load(mod_name: str, path: Path):
    spec = _ilu.spec_from_file_location(mod_name, path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


# The W2 ephemeral PG17 harness (imported by path — the lib_relay_harness idiom).
H = _load("lib_cog1_harness", REPO / "cabinet" / "scripts" / "tests" / "lib_cog1_harness.py")
# The exemplar consumer under test.
tew = _load("task_events_watch", CONSUMER)

# A committed 26-char Crockford ULID + a uuid4-hex correlation id (envelope v2 §4.2).
VALID_ULID = "01J0000000000000000000000A"
UUID4_HEX = "0123456789abcdef0123456789abcdef"


# ---------------------------------------------------------------------------
# flip-script runners
# ---------------------------------------------------------------------------

def run_flip(verb: str, *, pointer: Path | None = None,
             env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    if pointer is not None:
        env["CABINET_COG1_AUTHORITY"] = str(pointer)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(["bash", str(FLIP), verb],
                          capture_output=True, text=True, env=env)


# ===========================================================================
# §8.4/§8.5 — pointer flip semantics (fail-safe default; atomic; NO-env context)
# ===========================================================================

def test_flip_outbox_then_legacy_writes_pointer(tmp_path):
    ptr = tmp_path / "state" / "cog1-authority"  # parent dir absent on purpose
    r = run_flip("outbox", pointer=ptr)
    assert r.returncode == 0, r.stderr
    assert ptr.read_text().strip() == "outbox"
    r = run_flip("legacy", pointer=ptr)  # the §8.5 rollback inverse
    assert r.returncode == 0, r.stderr
    assert ptr.read_text().strip() == "legacy"


def test_flip_is_atomic_no_temp_leftovers(tmp_path):
    ptr = tmp_path / "cog1-authority"
    assert run_flip("outbox", pointer=ptr).returncode == 0
    # atomic rename leaves exactly the pointer file — no mktemp residue.
    leftovers = sorted(p.name for p in ptr.parent.iterdir())
    assert leftovers == ["cog1-authority"], leftovers


def test_flip_creates_missing_state_dir(tmp_path):
    ptr = tmp_path / "a" / "b" / "c" / "cog1-authority"
    r = run_flip("outbox", pointer=ptr)
    assert r.returncode == 0, r.stderr
    assert ptr.read_text().strip() == "outbox"


def test_flip_bad_verb_refuses_and_writes_nothing(tmp_path):
    ptr = tmp_path / "cog1-authority"
    r = run_flip("banana", pointer=ptr)
    assert r.returncode != 0
    assert not ptr.exists(), "a bad verb must never write the pointer"


def test_no_env_var_context_observes_flip_via_default_path(tmp_path):
    # §8.4: officer shells / launchd / cron read the DEFAULT host path with ZERO
    # env dependency. Redirect HOME so the default resolves under tmp; the flip
    # itself carries no CABINET_COG1_AUTHORITY.
    home = tmp_path / "home"
    home.mkdir()
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home)}
    r = subprocess.run(["bash", str(FLIP), "outbox"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    default_ptr = home / ".cabinet" / "state" / "cog1-authority"
    assert default_ptr.read_text().strip() == "outbox"
    # a consumer with NO env var + the same HOME reads the same value.
    read = subprocess.run(
        ["bash", "-c",
         'cat "${CABINET_COG1_AUTHORITY:-$HOME/.cabinet/state/cog1-authority}" 2>/dev/null'],
        capture_output=True, text=True, env=env)
    assert read.stdout.strip() == "outbox"


def test_authority_flip_back_rehearsal(tmp_path):
    # §8.5 / §12.4 runtime inverse #1: outbox -> legacy returns authority to the
    # legacy path; re-running legacy is idempotent (a safe stop state).
    ptr = tmp_path / "state" / "cog1-authority"
    assert run_flip("outbox", pointer=ptr).returncode == 0
    assert ptr.read_text().strip() == "outbox"
    assert run_flip("legacy", pointer=ptr).returncode == 0
    assert ptr.read_text().strip() == "legacy"
    assert run_flip("legacy", pointer=ptr).returncode == 0
    assert ptr.read_text().strip() == "legacy"


# ===========================================================================
# §5.1/§8.4 — my-tasks.sh emit_event pointer consult (byte-minimal, fail-safe)
# ===========================================================================

def _emit_event_consult_line() -> str:
    """The exact authority-pointer consult line inside my-tasks.sh emit_event —
    extracted so the behavioral test below runs the SHIPPED bytes, not a copy
    (the phase-0 _extract_verify_a13 byte-identity discipline)."""
    src = MY_TASKS.read_text(encoding="utf-8")
    m = re.search(r"emit_event\(\)\s*\{(.*?)\n\}", src, re.S)
    assert m, "emit_event() function not found in my-tasks.sh"
    body = m.group(1)
    for line in body.splitlines():
        if "CABINET_COG1_AUTHORITY" in line and "outbox" in line:
            return line.strip()
    raise AssertionError("emit_event has no authority-pointer consult line")


def test_emit_event_consults_pointer_default_and_override():
    line = _emit_event_consult_line()
    # default host-global path + TEST-ONLY env override, both present.
    assert "CABINET_COG1_AUTHORITY:-$HOME/.cabinet/state/cog1-authority" in line
    # skips ONLY on the exact 'outbox' authority value.
    assert '= "outbox"' in line and "return 0" in line


def test_emit_event_guard_logic_is_failsafe(tmp_path):
    # Behavioral: run the SHIPPED consult line with `return 0` swapped for an
    # echo — outbox -> SKIP (relay owns exhaust); absent/unreadable/anything
    # else -> PROCEED (legacy direct emit, the fail-safe).
    line = _emit_event_consult_line()
    probe = line.replace("&& return 0", "&& echo SKIP || echo PROCEED")
    ptr = tmp_path / "cog1-authority"

    def observe(value):
        if value is None:
            if ptr.exists():
                ptr.unlink()
        else:
            ptr.write_text(value)
        env = {"PATH": "/usr/bin:/bin", "CABINET_COG1_AUTHORITY": str(ptr)}
        return subprocess.run(["bash", "-uo", "pipefail", "-c", probe],
                              capture_output=True, text=True, env=env).stdout.strip()

    assert observe("outbox") == "SKIP"
    assert observe("outbox\n") == "SKIP"   # trailing newline stripped by cat/$()
    assert observe(None) == "PROCEED"      # absent pointer -> legacy fail-safe
    assert observe("legacy") == "PROCEED"
    assert observe("") == "PROCEED"        # empty -> legacy
    assert observe("outboxx") == "PROCEED"  # near-miss is NOT a skip


# ===========================================================================
# §12.4 — capture inverse: disarm/enable against the W2 harness DB
# ===========================================================================

def _pg_flip_env(pg) -> dict:
    """Env for the flip script's disarm/enable verbs: psql resolvable +
    NEON_CONNECTION_STRING = THIS scratch cluster (never a live store)."""
    bindir = H.pg17_bindir()
    path = os.environ.get("PATH", "/usr/bin:/bin")
    if bindir is not None:
        path = f"{bindir}:{path}"
    return {"PATH": path, "HOME": str(pg.scratch_home),
            "NEON_CONNECTION_STRING": pg.conninfo()}


@pytest.mark.skipif(not H.harness_available(), reason=H.SKIP_REASON)
def test_disarm_enable_capture_inverse_rehearsal(tmp_path):
    trig = "trg_officer_tasks_outbox_capture"
    with H.EphemeralPG17(tmp_path / "pg") as pg:
        pg.apply_base_chain()
        pg.apply_identity_guc("main")
        pg.apply_047()

        def tgenabled() -> str:
            return pg.one(f"SELECT tgenabled FROM pg_trigger WHERE tgname = '{trig}';")

        assert tgenabled() == "O", "trigger should be armed after 047 apply"
        pg.verb_queue("cos", "seed-1", "cog1")
        assert pg.count("officer_tasks_outbox") == 1
        tasks_before = pg.count("officer_tasks")

        # disarm -> trigger disabled; a verb still WORKS but mints NO outbox row.
        r = run_flip("disarm", env_extra=_pg_flip_env(pg))
        assert r.returncode == 0, r.stderr + r.stdout
        assert tgenabled() == "D", "disarm must DISABLE the capture trigger"
        pg.verb_queue("cos", "seed-2", "cog1")
        assert pg.count("officer_tasks") == tasks_before + 1, "verb must still work"
        assert pg.count("officer_tasks_outbox") == 1, "disarmed trigger minted a row"

        # no data surgery — the pre-disarm outbox row is intact.
        assert pg.count("officer_tasks_outbox", "task_id IS NOT NULL") == 1

        # enable -> capture resumes; the next verb mints again.
        r = run_flip("enable", env_extra=_pg_flip_env(pg))
        assert r.returncode == 0, r.stderr + r.stdout
        assert tgenabled() == "O", "enable must re-ENABLE the capture trigger"
        pg.verb_queue("cos", "seed-3", "cog1")
        assert pg.count("officer_tasks_outbox") == 2, "re-armed trigger did not mint"


@pytest.mark.skipif(not H.harness_available(), reason=H.SKIP_REASON)
def test_disarm_enable_mutant_no_trigger_name(tmp_path):
    # Negative control for the capture inverse: the disarm verb targets the
    # LOAD-BEARING trigger name. Aim it at a NON-existent trigger -> psql errors
    # -> the flip fails loudly (never a silent no-op that leaves capture live).
    with H.EphemeralPG17(tmp_path / "pg") as pg:
        pg.apply_base_chain()
        pg.apply_identity_guc("main")
        pg.apply_047()
        env = _pg_flip_env(pg)
        bad = pg.psql("ALTER TABLE officer_tasks DISABLE TRIGGER trg_wrong_name_mutant;",
                      check=False)
        assert bad.returncode != 0, "a wrong trigger name MUST error (no silent pass)"


@pytest.mark.skipif(not H.harness_available(), reason=H.SKIP_REASON)
def test_disarm_requires_connection(tmp_path):
    # disarm/enable need a work-store connection; absent it, refuse loudly.
    r = run_flip("disarm", env_extra={"PATH": os.environ.get("PATH", "/usr/bin:/bin")})
    assert r.returncode != 0
    assert "NEON_CONNECTION_STRING" in (r.stderr + r.stdout)


# ===========================================================================
# §9.1 (11th rig) — consumer-compat: a RELAY-EMITTED v2 entry drained via --once
# ===========================================================================

def _relay_v2_blocked_entry(rid: str = "1-1") -> tuple[str, dict]:
    """Build the EXACT flat XADD payload the relay dispatches for a block
    transition (new_blocked TRUE -> effective new_status 'blocked'), via the
    relay's own build_dispatch_fields — so the v2 envelope is genuinely
    relay-produced, not a hand-rolled fixture."""
    from framework.outbox import relay
    row = {
        "id": 7, "idempotency_key": "task:42:1000:wip:true", "event_id": None,
        "task_id": 42, "old_status": "wip", "new_status": "wip",
        "old_blocked": False, "new_blocked": True,
        "blocked_reason": "waiting on review", "actor": "cos",
        "context_slug": "cog1", "cabinet_id": "main",
        "correlation_id": UUID4_HEX, "causation_id": None,
        "occurred_at": "2026-07-21T10:00:00Z",
    }
    flat, _env = relay.build_dispatch_fields(
        row, event_id=VALID_ULID, recorded_at="2026-07-21T10:00:05Z")
    return (rid, flat)


def _ledger_rows(root: Path) -> list[dict]:
    p = root / "shared" / "interfaces" / "needs-ledger.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def _wire_consumer_run_once(monkeypatch, tmp_path, entry):
    """Point run_once at a single injected entry (no real redis/XACK) and wire
    a needs-enabled scratch root (the test_task_events_watch.py convention)."""
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    monkeypatch.setenv("CABINET_ID", "testcab")
    monkeypatch.setattr(tew, "_ensure_group", lambda: None)
    acked: list[str] = []
    monkeypatch.setattr(tew, "_xack", lambda rid: acked.append(rid))
    served = {"pending": [entry]}

    def fake_xreadgroup(start: str):
        if start == "0":                       # this consumer's pending, once
            out = served["pending"]
            served["pending"] = []
            return out
        return []                              # '>' new: nothing else

    monkeypatch.setattr(tew, "_xreadgroup", fake_xreadgroup)
    return acked


def test_consumer_accepts_relay_v2_entry_via_once_drain(tmp_path, monkeypatch):
    acked = _wire_consumer_run_once(monkeypatch, tmp_path, _relay_v2_blocked_entry())
    stats = tew.run_once(dry_run=False)
    assert stats["invalid_envelope"] == 0, \
        "relay v2 entry poison-discarded — version dispatch not wired at the consumer"
    assert stats["blocked_cards"] == 1, "blocked_card did not fire end-to-end on the v2 entry"
    assert stats["acked"] == 1 and acked == ["1-1"]
    rows = _ledger_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["filed_by"] == "system:task-events-watch"


def test_v1_only_revert_mutant_poison_discards_v2(tmp_path, monkeypatch):
    # Negative control (§9.1): revert _valid_envelope to the pre-edit v1-only
    # validate() body -> the SAME relay v2 entry is rejected as poison and the
    # card never files. This is exactly what cutover would silently do WITHOUT
    # the version-dispatch edit.
    _wire_consumer_run_once(monkeypatch, tmp_path, _relay_v2_blocked_entry())

    def _v1_only_valid_envelope(fields):
        raw = fields.get("envelope")
        if not isinstance(raw, str) or not raw:
            return False
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            return False
        ok, _reasons = tew.envelope.validate(payload)   # v1-ONLY (the mutant)
        return ok

    monkeypatch.setattr(tew, "_valid_envelope", _v1_only_valid_envelope)
    stats = tew.run_once(dry_run=False)
    assert stats["invalid_envelope"] == 1, \
        "v1-only mutant did NOT reject the v2 entry — the consumer gate has no teeth"
    assert stats["blocked_cards"] == 0
    assert _ledger_rows(tmp_path) == []


def test_consumer_valid_envelope_uses_version_dispatch():
    # Static pin: the shipped _valid_envelope routes through validate_ANY (the
    # §4.1 version doorway), never raw v1 validate(). Guards against a silent
    # revert that the hermetic rig above would still catch, but fails faster.
    src = CONSUMER.read_text(encoding="utf-8")
    m = re.search(r"def _valid_envelope\(fields.*?\n(?=\S|\ndef )", src, re.S)
    body = m.group(0) if m else ""
    assert "validate_any(" in body, "_valid_envelope must call envelope.validate_any"
    assert "envelope.validate(" not in body, \
        "_valid_envelope must NOT call raw v1 validate() (poison-ACKs every v2 entry)"
