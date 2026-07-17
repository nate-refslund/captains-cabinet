"""Library retirement — retire-library-export.py contract tests.

The export is the data-preservation half of the Library retirement
(Captain-ratified 2026-07-16): every library_records row becomes a vault
markdown note. These tests pin the contract with a stub psql on PATH (no
network, no Neon):

  1. Idempotency — two runs over the same fixture produce byte-identical
     trees; a title change between runs converges (stale filename variant
     pruned, exactly one note per record id).
  2. Frontmatter integrity + injection control — record content is
     UNTRUSTED: YAML-breaking titles ("---", "injected: true", quotes),
     shell metacharacters ($(...), backticks), and HTML stay DATA — the
     frontmatter fence never gains injected keys and the body is byte-
     identical to content_markdown.
  3. Path safety — traversal-shaped titles/space names cannot escape the
     archive root (slug whitelist).
  4. Loud skip — without DATABASE_URL/NEON_CONNECTION_STRING the script
     exits 0, prints SKIP, and NEVER invokes psql.
  5. Read-only seam — psql runs under PGOPTIONS default_transaction_read_only=on
     and receives the fixed SELECT (never any record content in the SQL).
  6. Target resolution — vault/ wins when present, else product-brain/
     (vault-rename lane may or may not have landed).

Run: python3.12 -m pytest cabinet/scripts/tests/test_retire_library_export.py -q
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "cabinet/scripts/retire-library-export.py"

HOSTILE_CONTENT = (
    "# Heading\n"
    "---\n"
    "injected_in_body: true\n"
    "$(rm -rf /) `touch /tmp/pwned` \\x00-ish\n"
    "<script>alert(1)</script>\n"
    "'; DROP TABLE library_records; --\n"
    "line with \"double quotes\" and 'singles'\n"
)

FIXTURE = [
    {
        "id": 1,
        "space_id": 7,
        "space_name": "Ops / Weird Space!!",
        "title": 'Evil "title" --- \ninjected: true',
        "content_markdown": HOSTILE_CONTENT,
        "schema_data": {"k": "v $(boom)"},
        "labels": ["a", "b"],
        "version": 2,
        "superseded_by": None,
        "status": "approved",
        "created_by_officer": "cos",
        "created_at": "2026-07-01 10:00:00+02",
        "updated_at": "2026-07-02 11:00:00+02",
    },
    {
        "id": 2,
        "space_id": 7,
        "space_name": "Ops / Weird Space!!",
        "title": "../../../etc/passwd",
        "content_markdown": "traversal-shaped title stays data",
        "schema_data": {},
        "labels": [],
        "version": 1,
        "superseded_by": 3,
        "status": "",
        "created_by_officer": None,
        "created_at": "2026-07-01 10:00:00+02",
        "updated_at": "2026-07-01 10:00:00+02",
    },
    {
        "id": 3,
        "space_id": 9,
        "space_name": "Second Space",
        "title": "Soft deleted row",
        "content_markdown": "",
        "schema_data": {},
        "labels": ["x"],
        "version": 1,
        "superseded_by": 3,  # self-pointer = soft delete convention
        "status": "draft",
        "created_by_officer": "cto",
        "created_at": "2026-07-03 09:00:00+02",
        "updated_at": "2026-07-03 09:00:00+02",
    },
]


def _write_stub_psql(tmp_path: Path, fixture_file: Path) -> Path:
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    psql = stub_dir / "psql"
    psql.write_text(
        "#!/bin/bash\n"
        f"printf '%s\\n' \"$@\" >> '{tmp_path}/psql_args'\n"
        f"printf '%s' \"${{PGOPTIONS:-}}\" > '{tmp_path}/psql_pgoptions'\n"
        f"cat '{fixture_file}'\n"
    )
    psql.chmod(0o755)
    return stub_dir


def _run(tmp_path: Path, fixture, target: Path = None, extra_env=None,
         cabinet_root: Path = None, expect_rc=0):
    fixture_file = tmp_path / "fixture.json"
    # psql -t -A prints the aggregate as ONE line — mirror that shape.
    fixture_file.write_text(json.dumps(fixture), encoding="utf-8")
    stub_dir = _write_stub_psql(tmp_path, fixture_file)
    env = {
        "PATH": f"{stub_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "DATABASE_URL": "postgresql://stub-only-never-dialed",
        "HOME": str(tmp_path),
    }
    if cabinet_root is not None:
        env["CABINET_ROOT"] = str(cabinet_root)
    if extra_env:
        env.update(extra_env)
        for key, val in list(env.items()):
            if val is None:
                env.pop(key)
    argv = [sys.executable, str(SCRIPT)]
    if target is not None:
        argv += ["--target", str(target)]
    proc = subprocess.run(argv, capture_output=True, text=True, env=env)
    assert proc.returncode == expect_rc, (
        f"rc={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}")
    return proc


def _tree_bytes(root: Path):
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = path.read_bytes()
    return out


# =========================================================================
# 1. Idempotency
# =========================================================================

def test_two_runs_are_byte_identical(tmp_path):
    target = tmp_path / "archive"
    _run(tmp_path, FIXTURE, target=target)
    first = _tree_bytes(target)
    assert first, "export produced no files"
    _run(tmp_path, FIXTURE, target=target)
    assert _tree_bytes(target) == first


def test_title_change_converges_to_one_note_per_id(tmp_path):
    target = tmp_path / "archive"
    _run(tmp_path, FIXTURE, target=target)
    changed = json.loads(json.dumps(FIXTURE))
    changed[0]["title"] = "Renamed Title"
    _run(tmp_path, changed, target=target)
    notes_for_1 = [p.name for p in target.rglob("lib-1-*.md")] + \
                  [p.name for p in target.rglob("lib-1.md")]
    assert notes_for_1 == ["lib-1-renamed-title.md"], notes_for_1


# =========================================================================
# 2. Frontmatter integrity + injection control
# =========================================================================

def _note_for_id_1(target: Path) -> str:
    matches = list(target.rglob("lib-1-*.md"))
    assert len(matches) == 1, matches
    return matches[0].read_text(encoding="utf-8")


def test_hostile_content_stays_data(tmp_path):
    target = tmp_path / "archive"
    _run(tmp_path, FIXTURE, target=target)
    note = _note_for_id_1(target)

    # Body is content_markdown VERBATIM (byte-identical tail).
    assert note.endswith(HOSTILE_CONTENT)

    # Frontmatter fence: first block delimited by the first two '---' lines.
    lines = note.split("\n")
    assert lines[0] == "---"
    close = lines[1:].index("---") + 1
    fm_lines = lines[1:close]

    # The YAML-breaking title stays INSIDE the quoted title value — no
    # injected key appears as its own frontmatter line.
    assert not any(ln.startswith("injected:") for ln in fm_lines)
    title_line = [ln for ln in fm_lines if ln.startswith("title: ")][0]
    # Round-trip: the value is a JSON string (valid YAML double-quoted scalar)
    assert json.loads(title_line[len("title: "):]) == FIXTURE[0]["title"]
    prov_line = [ln for ln in fm_lines if ln.startswith("provenance: ")][0]
    assert json.loads(prov_line[len("provenance: "):]) == "library_record:1"
    assert "created: " in note and "version: 2" in note
    # Frontmatter itself contains no raw shell metachars from the title/body
    fm_text = "\n".join(fm_lines)
    assert "$(rm" not in fm_text and "<script>" not in fm_text


def test_superseded_and_deleted_flags(tmp_path):
    target = tmp_path / "archive"
    _run(tmp_path, FIXTURE, target=target)
    note2 = next(target.rglob("lib-2-*.md")).read_text(encoding="utf-8")
    assert "superseded: true" in note2 and "deleted: false" in note2
    note3 = next(target.rglob("lib-3-*.md")).read_text(encoding="utf-8")
    assert "deleted: true" in note3 and "superseded: false" in note3


# =========================================================================
# 3. Path safety
# =========================================================================

def test_traversal_title_confined_to_archive(tmp_path):
    target = tmp_path / "archive"
    _run(tmp_path, FIXTURE, target=target)
    # Slug whitelist flattens "../../../etc/passwd" — no file escapes target.
    outside = [p for p in tmp_path.rglob("*.md")
               if target not in p.parents]
    assert outside == [], outside
    note2 = list(target.rglob("lib-2-*.md"))
    assert len(note2) == 1
    assert note2[0].name == "lib-2-etc-passwd.md"
    # Space foldering: untrusted space name slugged + id-suffixed.
    assert note2[0].parent.name == "ops-weird-space-s7"


# =========================================================================
# 4. Loud skip without DATABASE_URL
# =========================================================================

def test_skip_without_database_url_never_invokes_psql(tmp_path):
    proc = _run(
        tmp_path, FIXTURE, target=tmp_path / "archive",
        extra_env={"DATABASE_URL": None, "NEON_CONNECTION_STRING": None},
        expect_rc=0,
    )
    assert "SKIP" in proc.stderr
    assert not (tmp_path / "psql_args").exists(), "psql must not run on skip"
    assert not (tmp_path / "archive").exists()


def test_neon_connection_string_fallback_accepted(tmp_path):
    proc = _run(
        tmp_path, FIXTURE, target=tmp_path / "archive",
        extra_env={"DATABASE_URL": None,
                   "NEON_CONNECTION_STRING": "postgresql://stub-fallback"},
    )
    assert "SKIP" not in proc.stderr
    assert (tmp_path / "psql_args").exists()


# =========================================================================
# 5. Read-only seam
# =========================================================================

def test_psql_invoked_read_only_with_fixed_select(tmp_path):
    _run(tmp_path, FIXTURE, target=tmp_path / "archive")
    pgoptions = (tmp_path / "psql_pgoptions").read_text()
    assert "default_transaction_read_only=on" in pgoptions
    args = (tmp_path / "psql_args").read_text()
    assert "ON_ERROR_STOP=1" in args
    sql = [ln for ln in args.splitlines() if "SELECT" in ln]
    assert sql and "library_records" in sql[0] and "json_agg" in sql[0]
    # The fixed SQL is SELECT-only — no write verbs.
    upper = sql[0].upper()
    for verb in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER "):
        assert verb not in upper


# =========================================================================
# 6. Target resolution (vault/ preferred, product-brain/ fallback)
# =========================================================================

def test_target_resolution_product_brain_then_vault(tmp_path):
    root = tmp_path / "root"
    (root / "product-brain").mkdir(parents=True)
    _run(tmp_path, FIXTURE, cabinet_root=root)
    assert (root / "product-brain" / "library-archive").is_dir()
    assert not (root / "vault").exists()

    (root / "vault").mkdir()
    _run(tmp_path, FIXTURE, cabinet_root=root)
    assert (root / "vault" / "library-archive").is_dir()
