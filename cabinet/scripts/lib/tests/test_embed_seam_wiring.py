"""Wiring tests for the embed-seam follow-up (R4, 2026-07-15).

Migration 046-embedding-meta.sql shipped DORMANT in the Lane A landing
(960d4c4d): nothing applied it and nothing called memory_embedding_stamp(),
so the cabinet-doctor dims-drift probe skipped forever. This file pins the
follow-up wiring (as reworked by the 2026-07-15 review):

  1. 046 rides BOTH apply lists (cabinet-bootstrap.sh schema_apply_list +
     load-preset.sh Neon loop), ordered after 045, never parked in the
     bootstrap omissions list.
  2. memory_embedding_stamp --if-absent is called fail-soft right after the
     DDL lands in both scripts. IF-ABSENT is load-bearing (review P2):
     load-preset runs at EVERY officer start, so an unconditional upsert
     would re-stamp a config flip and silently erase the doctor's DIMS DRIFT
     WARN — deploys must never overwrite an existing row. The bare-upsert
     mode remains the re-stamp primitive for the future re-embed organ / a
     captain closing drift after a verified full backfill. The stamp passes
     provider/model/dims through the parameterized psql -v seam (values
     never interpolated into SQL).
  3. EMBED_* resolution is DETERMINISTIC on both sides (review P3 pair):
     memory.sh resolves the stamped triple caller-env > cabinet/.env >
     default regardless of whether the NEON/CABINET_ID back-fill sourced
     .env, and cabinet-doctor resolves its compare side (ES_PROVIDER/
     ES_MODEL/ES_DIMS) through the SAME chain — stamp-time and probe-time
     can no longer disagree on a .env-configured seam.
  4. The doctor dims-drift probe is explicit tri-state: OK on match, WARN on
     drift, SKIP (clean, informative) when unstamped / unreachable / no
     connection — it was SILENT in all three skip cases before the wiring,
     so the SKIP asserts here fail against the pre-wiring tree (teeth).

No network, no Neon, no Voyage — syntax checks, contract greps, and
functional runs against stub psql binaries in tmp_path.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

# Captured at import (collection) time, BEFORE any test runs:
# test_library_mcp_client patches the global subprocess.Popen and the patch
# can leak into later-alphabetical modules — restore the real one around our
# spawns so a leaked FakePopen can't fail these tests.
_REAL_POPEN = subprocess.Popen

SCRIPTS_DIR = Path(__file__).resolve().parents[2]  # cabinet/scripts
REPO_ROOT = SCRIPTS_DIR.parents[1]
MEMORY_SH = SCRIPTS_DIR / "lib" / "memory.sh"
LOAD_PRESET_SH = SCRIPTS_DIR / "load-preset.sh"
BOOTSTRAP_SH = SCRIPTS_DIR / "cabinet-bootstrap.sh"
DOCTOR_SH = SCRIPTS_DIR / "cabinet-doctor.sh"
MIGRATION_REL = "cabinet/sql/046-embedding-meta.sql"


def _bash_n(path: Path) -> None:
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        proc = subprocess.run(
            ["bash", "-n", str(path)], capture_output=True, text=True
        )
    finally:
        subprocess.Popen = patched
    assert proc.returncode == 0, f"bash -n {path.name} failed: {proc.stderr}"


def _run_bash(script: str, env: dict) -> "subprocess.CompletedProcess[str]":
    """Run a bash snippet with the REAL Popen (see _REAL_POPEN note above)."""
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        return subprocess.run(
            ["bash", "-c", script],
            capture_output=True, text=True,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), **env},
        )
    finally:
        subprocess.Popen = patched


def test_bash_syntax_load_preset_sh():
    _bash_n(LOAD_PRESET_SH)


def test_bash_syntax_cabinet_bootstrap_sh():
    _bash_n(BOOTSTRAP_SH)


def test_bash_syntax_cabinet_doctor_sh():
    _bash_n(DOCTOR_SH)


def test_bash_syntax_memory_sh():
    _bash_n(MEMORY_SH)


# =========================================================================
# 1. Apply lists — 046 rides both, ordered after 045, never in omissions
# =========================================================================

def _bootstrap_heredoc(fn_name: str) -> list[str]:
    text = BOOTSTRAP_SH.read_text()
    m = re.search(
        rf"{fn_name}\(\)\s*\{{\s*\n\s*cat <<'LIST'\n(.*?)\nLIST", text, re.S
    )
    assert m, f"could not locate {fn_name}() heredoc in cabinet-bootstrap.sh"
    return [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]


def _load_preset_neon_list() -> list[str]:
    text = LOAD_PRESET_SH.read_text()
    blocks = re.findall(r"for schema in \\\n(.*?); do", text, re.S)
    assert len(blocks) >= 2, "expected Neon + cabinet-pg schema loops"
    # First loop in the file is the Neon list.
    return re.findall(r'"\$CABINET_ROOT/(cabinet/sql/[^"]+)"', blocks[0])


def test_migration_046_exists_on_disk():
    sql = (REPO_ROOT / MIGRATION_REL).read_text()
    assert "CREATE TABLE IF NOT EXISTS cabinet_embedding_meta" in sql
    assert "CHECK (id = 1)" in sql  # singleton row contract


def test_bootstrap_apply_list_includes_046_after_045():
    entries = _bootstrap_heredoc("schema_apply_list")
    assert MIGRATION_REL in entries, "046 missing from schema_apply_list (dormant again)"
    assert (
        entries.index(MIGRATION_REL)
        == entries.index("cabinet/sql/045-org-runtime-slice.sql") + 1
    ), "046 must directly follow 045 (list tail, mirroring load-preset.sh)"


def test_bootstrap_omissions_list_never_swallows_046():
    """Negative control: parking 046 in schema_local_pg_omissions would
    silence the self-check WARN without applying the DDL — forbidden."""
    omitted = _bootstrap_heredoc("schema_local_pg_omissions")
    assert "046-embedding-meta.sql" not in omitted


def test_load_preset_neon_list_includes_046_after_045():
    paths = _load_preset_neon_list()
    assert MIGRATION_REL in paths, "046 missing from load-preset Neon loop (dormant again)"
    assert (
        paths.index(MIGRATION_REL)
        == paths.index("cabinet/sql/045-org-runtime-slice.sql") + 1
    )


def test_load_preset_local_pg_loop_does_not_gain_046():
    """046 targets the Neon store; the LOCAL cabinet-postgres loop must not
    apply it (the doctor probes the Neon row)."""
    text = LOAD_PRESET_SH.read_text()
    blocks = re.findall(r"for schema in \\\n(.*?); do", text, re.S)
    local_paths = re.findall(r'"\$CABINET_ROOT/(cabinet/sql/[^"]+)"', blocks[1])
    assert MIGRATION_REL not in local_paths


def test_load_preset_neon_list_subset_of_bootstrap_list():
    """Drift invariant: load-preset.sh mirrors bootstrap's ordering source of
    truth — an entry added to load-preset but not schema_apply_list would
    diverge fresh hatches from existing estates."""
    bootstrap_entries = set(_bootstrap_heredoc("schema_apply_list"))
    for p in _load_preset_neon_list():
        assert p in bootstrap_entries, f"{p} in load-preset but not bootstrap apply list"


# =========================================================================
# 2. Stamp wiring — called fail-soft in both scripts, right after the DDL,
#    ALWAYS in --if-absent mode (deploys never overwrite provenance)
# =========================================================================

def test_stamp_wired_in_load_preset_neon_branch():
    text = LOAD_PRESET_SH.read_text()
    # Subshell-sourced from the lib (no copy-pasted SQL, no env leak), and
    # the deploy path must use --if-absent (review P2: load-preset runs at
    # every officer start — a bare upsert here would erase real drift).
    call = re.search(
        r'if \( source "\$CABINET_ROOT/cabinet/scripts/lib/memory\.sh"'
        r"[^\n]*&& \\\n\s*memory_embedding_stamp --if-absent",
        text,
    )
    assert call, "stamp must run via subshell-sourced memory.sh in --if-absent mode"
    # The CALL sits inside the Neon branch: after the 046 list entry, before
    # the keyless-else arm (comments may mention the names earlier). Anchor on
    # the else-arm's stable ACTION phrase, not the env-var name — the fresh-hatch
    # #57 fix reworded the lead-in to name both env AND cabinet/.env as sources.
    assert (
        text.index("046-embedding-meta.sql")
        < call.start()
        < text.index("skipping Neon schema application")
    )
    # Fail-soft: a stamp failure WARNs, never exits.
    assert "WARN: failed to stamp cabinet_embedding_meta" in text


def test_stamp_wired_in_bootstrap_step_apply_schemas():
    text = BOOTSTRAP_SH.read_text()
    assert "memory_embedding_stamp --if-absent" in text
    # Bootstrap's Neon var is NEON_DATABASE_URL — the stamp subshell must map
    # it onto the lib's NEON_CONNECTION_STRING, PIN the hatched estate
    # (CABINET_ROOT re-exported to the new checkout so memory.sh's .env
    # resolution reads the NEW cabinet's seam, never the host framework's;
    # CABINET_ID mirrors what bootstrap wrote into the new .env), NEUTRALIZE
    # any deployer-shell EMBED_* override (a hatch must record what the
    # estate itself resolves), and source the NEW cabinet's checkout of the
    # lib (not the running repo's). Every line is load-bearing.
    assert re.search(
        r'if \( export NEON_CONNECTION_STRING="\$NEON_DATABASE_URL"; \\\n'
        r'\s*export CABINET_ROOT="\$cabinet_dir" CABINET_ID="\$CABINET_SLUG"; \\\n'
        r"\s*unset EMBED_PROVIDER EMBED_MODEL EMBED_DIMS; \\\n"
        r'\s*source "\$cabinet_dir/cabinet/scripts/lib/memory\.sh"'
        r"[^\n]*&& \\\n\s*memory_embedding_stamp --if-absent",
        text,
    ), (
        "stamp subshell must export NEON_CONNECTION_STRING, pin "
        "CABINET_ROOT/CABINET_ID to the hatched estate, unset deployer "
        "EMBED_* and call --if-absent"
    )
    assert "WARN: failed to stamp cabinet_embedding_meta" in text
    # Dry-run plan names the stamp so --dry-run output tracks the real path.
    assert 'dry "Would stamp cabinet_embedding_meta' in text


def test_deploy_callsites_never_use_upsert_mode():
    """Negative control (review P2 mutant): re-wiring either deploy script to
    the bare-upsert mode would make every officer restart re-bless a config
    flip and erase the doctor's DIMS DRIFT WARN. Every executable line that
    invokes memory_embedding_stamp in the deploy scripts must carry
    --if-absent."""
    for script in (LOAD_PRESET_SH, BOOTSTRAP_SH):
        for lineno, line in enumerate(script.read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "memory_embedding_stamp" in stripped:
                assert "--if-absent" in stripped, (
                    f"{script.name}:{lineno} calls memory_embedding_stamp "
                    f"without --if-absent (drift gate would self-erase): {stripped}"
                )


def _write_capture_psql(tmp_path):
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    psql = stub_dir / "psql"
    psql.write_text(
        "#!/bin/bash\n"
        f"printf '%s\\n' \"$@\" > '{tmp_path}/psql_args'\n"
        f"cat > '{tmp_path}/psql_sql'\n"
    )
    psql.chmod(0o755)
    return stub_dir


def test_stamp_if_absent_functional_never_overwrites(tmp_path):
    """--if-absent mode: parameterized psql -v args, CREATE TABLE IF NOT
    EXISTS self-sufficiency, and ON CONFLICT (id) DO NOTHING — the mutant
    that reintroduces DO UPDATE into the deploy mode fails here."""
    stub_dir = _write_capture_psql(tmp_path)
    proc = _run_bash(
        f'source "{MEMORY_SH}" && memory_embedding_stamp --if-absent',
        env={
            "NEON_CONNECTION_STRING": "postgresql://placeholder",
            "CABINET_ID": "testcab",
            "EMBED_PROVIDER": "acme",
            "EMBED_MODEL": "acme-embed-9",
            "EMBED_DIMS": "512",
            "PATH": f"{stub_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        },
    )
    assert proc.returncode == 0, proc.stderr
    args = (tmp_path / "psql_args").read_text().splitlines()
    for pair in ("provider=acme", "model=acme-embed-9", "dims=512"):
        assert pair in args, f"psql -v {pair} missing: {args}"
    sql = (tmp_path / "psql_sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS cabinet_embedding_meta" in sql
    assert "INSERT INTO cabinet_embedding_meta" in sql
    assert "ON CONFLICT (id) DO NOTHING" in sql
    assert "DO UPDATE" not in sql, "deploy mode must never overwrite an existing stamp"
    assert ":'provider'" in sql and ":'model'" in sql
    # Security contract: values ride -v args ONLY — never the SQL text.
    assert "acme" not in sql
    assert "DELETE" not in sql.upper()  # provenance is insert-only here


def test_stamp_bare_mode_is_the_upsert_restamp_primitive(tmp_path):
    """Bare (no-arg) mode stays ON CONFLICT (id) DO UPDATE — the re-stamp
    primitive reserved for the future re-embed organ / a captain closing a
    drift WARN after a verified full backfill. Same parameterized seam."""
    stub_dir = _write_capture_psql(tmp_path)
    proc = _run_bash(
        f'source "{MEMORY_SH}" && memory_embedding_stamp',
        env={
            "NEON_CONNECTION_STRING": "postgresql://placeholder",
            "CABINET_ID": "testcab",  # both set → back-fill never sources .env
            "EMBED_PROVIDER": "acme",
            "EMBED_MODEL": "acme-embed-9",
            "EMBED_DIMS": "512",
            "PATH": f"{stub_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        },
    )
    assert proc.returncode == 0, proc.stderr
    args = (tmp_path / "psql_args").read_text().splitlines()
    for pair in ("provider=acme", "model=acme-embed-9", "dims=512"):
        assert pair in args, f"psql -v {pair} missing: {args}"
    sql = (tmp_path / "psql_sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS cabinet_embedding_meta" in sql
    assert "INSERT INTO cabinet_embedding_meta" in sql
    assert "ON CONFLICT (id) DO UPDATE" in sql
    assert ":'provider'" in sql and ":'model'" in sql
    # Security contract: values ride -v args ONLY — never the SQL text.
    assert "acme" not in sql
    assert "DELETE" not in sql.upper()  # provenance is upsert-only


def test_stamp_unknown_mode_refuses_loudly(tmp_path):
    """Fixed mode vocabulary: a typo'd flag returns 2 with a loud stderr and
    psql is NEVER invoked — it must not silently fall through to the upsert
    re-stamp."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    psql = stub_dir / "psql"
    psql.write_text(f"#!/bin/bash\ntouch '{tmp_path}/psql_was_called'\n")
    psql.chmod(0o755)

    proc = _run_bash(
        f'source "{MEMORY_SH}"; memory_embedding_stamp --if-absnet',
        env={
            "NEON_CONNECTION_STRING": "postgresql://placeholder",
            "CABINET_ID": "testcab",
            "PATH": f"{stub_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        },
    )
    assert proc.returncode == 2
    assert "unknown mode" in proc.stderr
    assert not (tmp_path / "psql_was_called").exists()


def test_stamp_refuses_without_connection(tmp_path):
    """Negative control: no NEON_CONNECTION_STRING resolvable → return 1,
    loud stderr, and psql NEVER invoked (no blind DB touch) — both modes."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    psql = stub_dir / "psql"
    psql.write_text(f"#!/bin/bash\ntouch '{tmp_path}/psql_was_called'\n")
    psql.chmod(0o755)

    for mode in ("", " --if-absent"):
        proc = _run_bash(
            f'source "{MEMORY_SH}"; memory_embedding_stamp{mode}',
            env={
                "CABINET_ROOT": str(tmp_path),  # no cabinet/.env here → no back-fill
                "CABINET_ID": "testcab",
                "PATH": f"{stub_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            },
        )
        assert proc.returncode == 1, f"mode '{mode}': {proc.stderr}"
        assert "cannot stamp cabinet_embedding_meta" in proc.stderr
        assert not (tmp_path / "psql_was_called").exists()


# =========================================================================
# 2b. Seam resolution determinism (review P3) — caller env > cabinet/.env >
#     default, IDENTICAL whether or not the NEON/CABINET_ID back-fill runs
# =========================================================================

_SEAM_ENV_FILE = "EMBED_PROVIDER=acme\nEMBED_MODEL=acme-embed-9\nEMBED_DIMS=777\n"


def _seam_fixture(tmp_path):
    cabroot = tmp_path / "cabroot"
    (cabroot / "cabinet").mkdir(parents=True, exist_ok=True)
    (cabroot / "cabinet" / ".env").write_text(_SEAM_ENV_FILE)
    return cabroot


def _stamp_args(tmp_path, extra_env):
    stub_dir = _write_capture_psql(tmp_path)
    env = {
        "NEON_CONNECTION_STRING": "postgresql://placeholder",
        "PATH": f"{stub_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        **extra_env,
    }
    proc = _run_bash(f'source "{MEMORY_SH}" && memory_embedding_stamp', env=env)
    assert proc.returncode == 0, proc.stderr
    return (tmp_path / "psql_args").read_text().splitlines()


def test_seam_env_file_honored_when_backfill_skipped(tmp_path):
    """TEETH for review P3: with NEON_CONNECTION_STRING and CABINET_ID both
    set, the conditional back-fill never sources cabinet/.env — pre-fix the
    stamp silently recorded the compiled defaults (dims=1024) while the
    doctor could read 777 from the same .env. The explicit grep fallback
    must resolve the .env seam regardless."""
    cabroot = _seam_fixture(tmp_path)
    args = _stamp_args(
        tmp_path,
        {"CABINET_ID": "testcab", "CABINET_ROOT": str(cabroot)},
    )
    for pair in ("provider=acme", "model=acme-embed-9", "dims=777"):
        assert pair in args, f"psql -v {pair} missing (env-file seam ignored): {args}"


def test_seam_env_file_honored_when_backfill_runs(tmp_path):
    """Parity pin: same fixture with CABINET_ID unset (the back-fill DOES
    source .env) must resolve the identical seam — stamp-time resolution is
    deterministic w.r.t. which unrelated vars the caller exported."""
    cabroot = _seam_fixture(tmp_path)
    args = _stamp_args(tmp_path, {"CABINET_ROOT": str(cabroot)})
    for pair in ("provider=acme", "model=acme-embed-9", "dims=777"):
        assert pair in args, f"psql -v {pair} missing: {args}"


def test_seam_caller_env_beats_env_file(tmp_path):
    """TEETH for the clobber facet of review P3: pre-fix, when the back-fill
    ran (CABINET_ID unset) the set -a source silently REPLACED a caller-set
    EMBED_DIMS with the .env value. Caller env must always win; unset vars
    still fall back to .env."""
    cabroot = _seam_fixture(tmp_path)
    args = _stamp_args(
        tmp_path,
        {"CABINET_ROOT": str(cabroot), "EMBED_DIMS": "512"},
    )
    assert "dims=512" in args, f"caller-set EMBED_DIMS clobbered by .env: {args}"
    assert "dims=777" not in args
    # Unset members of the triple still resolve from the .env file.
    assert "provider=acme" in args and "model=acme-embed-9" in args


def test_seam_resolution_structural_pins():
    """Structural belt: the back-fill restores pre-set EMBED_* like it does
    NEON/CABINET_ID, and the grep fallback covers exactly the stamped
    triple."""
    text = MEMORY_SH.read_text()
    assert "_mem_pre_eprov" in text and "_mem_pre_edims" in text
    assert 'grep -E "^${_mem_evar}="' in text
    assert "EMBED_PROVIDER EMBED_MODEL EMBED_DIMS" in text


def test_env_example_documents_seam_home():
    """cabinet/.env.example is the seam's documented home (review P3): a
    fresh captain must find the triple here, shipped COMMENTED-OUT so the
    compiled defaults hold until deliberately overridden (an active empty
    `EMBED_DIMS=` line would be harmless but reads as configuration), with
    the no-auto-re-embed consequence spelled out next to it."""
    text = (REPO_ROOT / "cabinet" / ".env.example").read_text()
    for var in ("EMBED_PROVIDER", "EMBED_MODEL", "EMBED_DIMS"):
        assert re.search(rf"^# {var}=", text, re.M), (
            f".env.example lost the commented {var} seam line (review P3: "
            "the seam had no plumbed home)"
        )
        assert not re.search(rf"^{var}=", text, re.M), (
            f"{var} must ship commented-out, not as an active assignment"
        )
    assert "re-embed" in text, "seam block must document the re-embed consequence"


# =========================================================================
# 3. Doctor dims-drift probe — explicit tri-state (fixture-driven), with the
#    configured side resolving env > cabinet/.env > default (review P3)
# =========================================================================

def _run_probe(tmp_path, *, env_extra=None, env_file=None, with_conn=True,
               stub_out=None, stub_rc="0"):
    """Extract the embed-seam block from cabinet-doctor.sh (ES_* resolution
    through the dims-drift arms) and run it under a harness: stubbed
    ok/warn/skip/dead, fixture REPO_ROOT (cabinet/.env content injectable),
    stub psql controlled via PSQL_STUB_OUT / PSQL_STUB_RC."""
    text = DOCTOR_SH.read_text()
    start = text.index('ES_PROVIDER="${EMBED_PROVIDER:-}"')
    end = text.index("unset ES_NEON ES_META_RAW ES_META_DIMS", start)
    snippet = text[start:end]

    fixture_root = tmp_path / "repo"
    (fixture_root / "cabinet").mkdir(parents=True, exist_ok=True)
    env_path = fixture_root / "cabinet" / ".env"
    if env_file is not None:
        env_path.write_text(env_file)
    elif env_path.exists():
        env_path.unlink()
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    psql = stub_dir / "psql"
    psql.write_text(
        '#!/bin/bash\nprintf \'%s\' "${PSQL_STUB_OUT:-}"\n'
        'exit "${PSQL_STUB_RC:-0}"\n'
    )
    psql.chmod(0o755)

    harness = (
        "set -u\n"
        'ok(){ echo "OK $1"; }\n'
        'warn(){ echo "WARN $1"; }\n'
        'skip(){ echo "SKIP $1"; }\n'
        'dead(){ echo "DEAD $1"; }\n'
        f'REPO_ROOT="{fixture_root}"\n'
        + snippet
    )
    env = {
        "PATH": f"{stub_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "PSQL_STUB_RC": stub_rc,
    }
    if stub_out is not None:
        env["PSQL_STUB_OUT"] = stub_out
    if with_conn:
        env["NEON_CONNECTION_STRING"] = "postgresql://placeholder"
    if env_extra:
        env.update(env_extra)
    proc = _run_bash(harness, env=env)
    assert proc.returncode == 0, f"probe harness failed: {proc.stderr}"
    return proc.stdout


def _drift_lines(out):
    """The dims-drift arms only — the snippet also emits the VOYAGE-key
    header line (OK/WARN), which these tests scope out."""
    return [
        ln for ln in out.strip().splitlines()
        if "dims-drift" in ln or "stamped dims" in ln
    ]


def test_doctor_probe_green_on_dims_match(tmp_path):
    out = _run_probe(tmp_path, stub_out="1024\n")
    assert _drift_lines(out) == [
        "OK embed-seam — store stamped dims=1024 matches configured EMBED_DIMS"
    ], out


def test_doctor_probe_amber_on_dims_drift(tmp_path):
    out = _run_probe(tmp_path, stub_out="512\n")
    lines = _drift_lines(out)
    assert len(lines) == 1, out
    assert "WARN embed-seam — DIMS DRIFT: store stamped dims=512 but EMBED_DIMS=1024" in lines[0]
    assert "re-embed backfill" in lines[0]
    # Mutant guard: drift must never read as healthy or be skipped.
    assert "matches configured" not in out
    assert "SKIP" not in out


def test_doctor_probe_skip_when_not_yet_stamped(tmp_path):
    """psql exit 0 + no row (empty output) = table applied but never stamped.
    Pre-wiring the probe was SILENT here — the explicit SKIP is the follow-up
    contract (this assert fails against the pre-wiring doctor)."""
    out = _run_probe(tmp_path, stub_out="", stub_rc="0")
    lines = _drift_lines(out)
    assert len(lines) == 1, out
    assert "SKIP embed-seam dims-drift — store reachable but not yet stamped" in lines[0]
    assert "load-preset.sh run stamps it" in lines[0]
    assert not any(ln.startswith(("OK ", "WARN ")) for ln in lines)


def test_doctor_probe_skip_when_store_unreachable(tmp_path):
    out = _run_probe(tmp_path, stub_out="", stub_rc="2")
    lines = _drift_lines(out)
    assert len(lines) == 1, out
    assert "SKIP embed-seam dims-drift — store unreachable" in lines[0]
    assert not any(ln.startswith(("OK ", "WARN ")) for ln in lines)


def test_doctor_probe_skip_clean_without_connection(tmp_path):
    """No NEON_CONNECTION_STRING in env and none in the fixture repo's
    cabinet/.env → one clean SKIP line, never OK/WARN/DEAD (a DB-less hatch
    is a valid deliberate state)."""
    out = _run_probe(tmp_path, with_conn=False)
    lines = _drift_lines(out)
    assert len(lines) == 1, out
    assert lines[0].startswith(
        "SKIP embed-seam dims-drift — no NEON_CONNECTION_STRING resolvable"
    )


def test_doctor_probe_configured_side_reads_env_file(tmp_path):
    """TEETH for review P3: the launchd doctor job carries no EMBED_* env, so
    a seam configured in cabinet/.env must drive the compare — pre-fix the
    probe compared against the compiled default (1024), turning this OK case
    into a spurious permanent DIMS DRIFT."""
    out = _run_probe(tmp_path, env_file="EMBED_DIMS=777\n", stub_out="777\n")
    assert _drift_lines(out) == [
        "OK embed-seam — store stamped dims=777 matches configured EMBED_DIMS"
    ], out
    assert "DIMS DRIFT" not in out
    # And a store still stamped with the old dims must WARN against the
    # .env-configured value (pre-fix: default-vs-default masked real drift).
    out = _run_probe(tmp_path, env_file="EMBED_DIMS=777\n", stub_out="1024\n")
    lines = _drift_lines(out)
    assert len(lines) == 1, out
    assert "DIMS DRIFT: store stamped dims=1024 but EMBED_DIMS=777" in lines[0]


def test_doctor_probe_env_beats_env_file(tmp_path):
    """Process env stays the strongest layer of the resolution chain."""
    out = _run_probe(
        tmp_path,
        env_extra={"EMBED_DIMS": "512"},
        env_file="EMBED_DIMS=777\n",
        stub_out="512\n",
    )
    assert _drift_lines(out) == [
        "OK embed-seam — store stamped dims=512 matches configured EMBED_DIMS"
    ], out
    out = _run_probe(
        tmp_path,
        env_extra={"EMBED_DIMS": "512"},
        env_file="EMBED_DIMS=777\n",
        stub_out="777\n",
    )
    lines = _drift_lines(out)
    assert len(lines) == 1 and "stamped dims=777 but EMBED_DIMS=512" in lines[0], out


def test_doctor_probe_header_resolves_provider_model_from_env_file(tmp_path):
    """The section header line must report the .env-configured provider and
    model (pre-fix it always printed the compiled defaults), and the key
    VALUE must never be printed."""
    out = _run_probe(
        tmp_path,
        env_file=(
            'VOYAGE_API_KEY="stub-key-abc"\n'
            "EMBED_PROVIDER=acme\nEMBED_MODEL=acme-embed-9\nEMBED_DIMS=777\n"
        ),
        stub_out="777\n",
    )
    assert "provider=acme model=acme-embed-9 dims=777" in out, out
    assert "stub-key-abc" not in out  # key value never printed
    assert _drift_lines(out) == [
        "OK embed-seam — store stamped dims=777 matches configured EMBED_DIMS"
    ], out


def test_doctor_probe_never_prints_connection_string(tmp_path):
    """Secret discipline: the DSN must never appear in any probe line — env
    conn and .env-file conn alike."""
    for kwargs in (
        {"stub_out": "1024\n"},
        {"stub_out": "512\n"},
        {"stub_out": "", "stub_rc": "0"},
        {"stub_out": "", "stub_rc": "2"},
        {
            "with_conn": False,
            "env_file": "NEON_CONNECTION_STRING=postgresql://u:pw@h/db\n",
            "stub_out": "1024\n",
        },
    ):
        out = _run_probe(tmp_path, **kwargs)
        assert "postgresql://" not in out
    # The .env-file conn case must actually reach the probe (not skip).
    assert _drift_lines(out) == [
        "OK embed-seam — store stamped dims=1024 matches configured EMBED_DIMS"
    ], out


def test_doctor_probe_old_silent_shape_gone():
    """The pre-wiring guard (silent skip: probe only when conn AND psql both
    present, no else arms) must not resurface, and the configured side keeps
    its cabinet/.env fallback for the full seam triple."""
    text = DOCTOR_SH.read_text()
    assert 'if [ -n "$ES_NEON" ] && command -v psql' not in text
    assert "silently skipped" not in text
    # Tri-state arms present.
    assert "store reachable but not yet stamped" in text
    assert "store unreachable or cabinet_embedding_meta absent" in text
    assert "no NEON_CONNECTION_STRING resolvable" in text
    # Configured-side .env fallback present for all three seam vars
    # (review P3 — removing any of these regresses to env-only resolution).
    for var in ("EMBED_PROVIDER", "EMBED_MODEL", "EMBED_DIMS"):
        assert f"grep -E '^{var}='" in text, f"doctor lost .env fallback for {var}"
