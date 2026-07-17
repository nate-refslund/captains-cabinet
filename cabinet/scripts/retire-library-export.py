#!/usr/bin/env python3
"""retire-library-export.py — one-shot Library → vault archive export.

Library retirement (Captain-ratified 2026-07-16, closes memory-study Q4/C7):
the Library's second vector store is retired. This script archives every
library_records row (joined to library_spaces for foldering) as a vault
markdown note so the content lives where the rest of cabinet knowledge
lives. The exported notes are picked up by the EXISTING post-file-write /
memory-reconcile machinery for indexing — this script deliberately contains
NO embedding code and NO DB writes.

Behavior contract:
  * Runs only with DATABASE_URL present (NEON_CONNECTION_STRING accepted as
    the repo-conventional fallback — cabinet/.env provides it). Missing both
    → LOUD skip on stderr, exit 0, psql never invoked.
  * Read-only: a single fixed SELECT (no interpolation of ANY variable data
    into SQL), sent through psql with default_transaction_read_only=on.
  * Export target resolves defensively: <root>/vault/ if that directory
    exists (post-rename tree), else <root>/product-brain/ — the archive
    lands in <target>/library-archive/. Root = $CABINET_ROOT else
    script-relative (this file lives at cabinet/scripts/).
  * Idempotent: deterministic filenames (lib-<id>-<title-slug>.md inside
    <space-slug>-s<space_id>/), full overwrite; stale filename variants of
    the same record id are pruned before writing.
  * UNTRUSTED content discipline: titles/space names/markdown are officer-
    and import-authored data. They ride a JSON transport out of psql, YAML
    frontmatter values are JSON-serialized (valid YAML double-quoted
    scalars — no YAML injection), filenames come from a [a-z0-9-] slug
    whitelist, and every write path is containment-checked against the
    archive root. content_markdown is written to the note BODY verbatim,
    as data — never executed, never interpolated into shell/SQL.

Frontmatter per note: title, created, updated, provenance
(library_record:<id>), space, space_id, version, status, labels,
created_by_officer, superseded, deleted, schema_data (when non-empty).

Usage:
  DATABASE_URL=postgres://… cabinet/scripts/retire-library-export.py
  … --target /explicit/dir     # tests / manual override

See docs/runbooks/library-retirement-2026-07-16.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

# Fixed, read-only SQL. No variable of any provenance is ever concatenated
# into this string. superseded rows and soft-deletes (superseded_by = id)
# are exported too — the archive is the faithful full corpus; flags in the
# frontmatter let readers filter.
EXPORT_SQL = (
    "SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json)::text FROM ("
    " SELECT r.id, r.space_id, s.name AS space_name, r.title,"
    "        r.content_markdown, r.schema_data, r.labels, r.version,"
    "        r.superseded_by, COALESCE(r.status, '') AS status,"
    "        r.created_by_officer, r.created_at::text AS created_at,"
    "        r.updated_at::text AS updated_at"
    " FROM library_records r"
    " JOIN library_spaces s ON s.id = r.space_id"
    " ORDER BY r.id"
    ") t;"
)

_SLUG_RE = re.compile(r"[a-z0-9]+")


def slugify(text, max_len):
    """Whitelist slug: lowercase [a-z0-9] runs joined by '-'. Untrusted text
    in, filesystem-safe fragment out. Empty string when nothing survives."""
    if not isinstance(text, str):
        return ""
    runs = _SLUG_RE.findall(text.lower())
    slug = "-".join(runs)
    return slug[:max_len].rstrip("-")


def yaml_value(value):
    """Serialize a frontmatter value safely. json.dumps output is valid YAML
    (YAML is a JSON superset): strings become double-quoted scalars with all
    control chars/quotes escaped, so untrusted titles cannot inject keys."""
    return json.dumps(value, ensure_ascii=False)


def resolve_root():
    env_root = os.environ.get("CABINET_ROOT", "").strip()
    if env_root:
        return os.path.realpath(env_root)
    # cabinet/scripts/retire-library-export.py → repo root is two dirs up.
    here = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
    return os.path.dirname(os.path.dirname(here))


def resolve_target(root):
    """vault/ wins when it exists (vault-rename lane landed); else
    product-brain/ (pre-rename tree). Defensive by design — coordinate via
    integrator, never assume the rename's landing order."""
    vault = os.path.join(root, "vault")
    if os.path.isdir(vault):
        return os.path.join(vault, "library-archive")
    return os.path.join(root, "product-brain", "library-archive")


def fetch_records(db_url):
    """Run the fixed read-only SELECT through psql. Returns list of dicts.
    The DSN is passed as an argv element (never a shell string) and never
    printed."""
    env = dict(os.environ)
    ro = "-c default_transaction_read_only=on"
    existing = env.get("PGOPTIONS", "").strip()
    env["PGOPTIONS"] = (existing + " " + ro).strip() if existing else ro

    proc = subprocess.run(
        [
            "psql", db_url,
            "-X", "-q", "-A", "-t",
            "-v", "ON_ERROR_STOP=1",
            "-c", EXPORT_SQL,
        ],
        capture_output=True, text=True, env=env,
    )
    if proc.returncode != 0:
        # psql stderr does not echo the DSN; safe to surface for diagnosis.
        sys.stderr.write("retire-library-export: psql failed (rc=%d):\n%s\n"
                         % (proc.returncode, proc.stderr.strip()))
        raise SystemExit(1)
    raw = proc.stdout.strip()
    if not raw:
        return []
    try:
        rows = json.loads(raw)
    except ValueError as exc:
        sys.stderr.write("retire-library-export: could not parse psql JSON "
                         "output: %s\n" % exc)
        raise SystemExit(1)
    if not isinstance(rows, list):
        sys.stderr.write("retire-library-export: unexpected JSON shape "
                         "(wanted list)\n")
        raise SystemExit(1)
    return rows


def note_for(record):
    """Build (space_dirname, filename, note_text) for one record dict.
    All values are treated as untrusted data."""
    rec_id = int(record["id"])          # bigint — refuse non-numeric loudly
    space_id = int(record["space_id"])
    title = record.get("title") or ""
    space_name = record.get("space_name") or ""
    content = record.get("content_markdown")
    if content is None:
        content = ""
    labels = record.get("labels") or []
    if not isinstance(labels, list):
        labels = []
    superseded_by = record.get("superseded_by")
    deleted = superseded_by is not None and int(superseded_by) == rec_id
    superseded = superseded_by is not None and not deleted
    schema_data = record.get("schema_data")

    space_slug = slugify(space_name, 40)
    space_dir = ("%s-s%d" % (space_slug, space_id)) if space_slug else ("s%d" % space_id)
    title_slug = slugify(title, 60)
    filename = ("lib-%d-%s.md" % (rec_id, title_slug)) if title_slug else ("lib-%d.md" % rec_id)

    lines = ["---"]
    lines.append("title: %s" % yaml_value(title))
    lines.append("created: %s" % yaml_value(record.get("created_at") or ""))
    lines.append("updated: %s" % yaml_value(record.get("updated_at") or ""))
    lines.append("provenance: %s" % yaml_value("library_record:%d" % rec_id))
    lines.append("space: %s" % yaml_value(space_name))
    lines.append("space_id: %d" % space_id)
    lines.append("version: %d" % int(record.get("version") or 1))
    lines.append("status: %s" % yaml_value(record.get("status") or ""))
    lines.append("labels: %s" % yaml_value([str(l) for l in labels]))
    lines.append("created_by_officer: %s" % yaml_value(record.get("created_by_officer") or ""))
    lines.append("superseded: %s" % ("true" if superseded else "false"))
    lines.append("deleted: %s" % ("true" if deleted else "false"))
    if isinstance(schema_data, dict) and schema_data:
        lines.append("schema_data: %s" % json.dumps(schema_data, ensure_ascii=False, sort_keys=True))
    lines.append("---")
    lines.append("")
    frontmatter = "\n".join(lines) + "\n"
    # Body: content_markdown UNTOUCHED, as data.
    return space_dir, filename, frontmatter + content


def export(records, archive_root):
    archive_root = os.path.realpath(archive_root)
    os.makedirs(archive_root, exist_ok=True)
    written = 0
    pruned = 0
    for record in records:
        space_dir, filename, note = note_for(record)
        rec_id = int(record["id"])
        dir_path = os.path.join(archive_root, space_dir)
        os.makedirs(dir_path, exist_ok=True)

        target = os.path.join(dir_path, filename)
        # Containment check — slug whitelist already prevents traversal, but
        # verify structurally: the resolved path must stay inside the archive.
        resolved = os.path.realpath(target)
        if os.path.commonpath([resolved, archive_root]) != archive_root:
            sys.stderr.write("retire-library-export: refusing out-of-tree "
                             "path for record %d\n" % rec_id)
            raise SystemExit(1)

        # Prune stale filename variants for the same record id (title edits
        # between runs) so re-runs converge on exactly one note per record.
        prefix = "lib-%d-" % rec_id
        exact = "lib-%d.md" % rec_id
        try:
            siblings = os.listdir(dir_path)
        except OSError:
            siblings = []
        for sib in siblings:
            if sib == filename:
                continue
            if sib.startswith(prefix) and sib.endswith(".md") or sib == exact:
                os.unlink(os.path.join(dir_path, sib))
                pruned += 1

        with open(resolved, "w", encoding="utf-8", newline="") as fh:
            fh.write(note)
        written += 1
    return written, pruned


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export library_records to the vault archive (read-only, idempotent).")
    parser.add_argument("--target", help="explicit archive directory (default: <root>/vault/library-archive or <root>/product-brain/library-archive)")
    args = parser.parse_args(argv)

    db_url = os.environ.get("DATABASE_URL", "").strip() or \
        os.environ.get("NEON_CONNECTION_STRING", "").strip()
    if not db_url:
        sys.stderr.write(
            "retire-library-export: SKIP — DATABASE_URL not set (and no "
            "NEON_CONNECTION_STRING fallback). Nothing exported, nothing "
            "touched. Set DATABASE_URL and re-run.\n")
        return 0

    archive_root = args.target or resolve_target(resolve_root())
    records = fetch_records(db_url)
    written, pruned = export(records, archive_root)
    sys.stdout.write(
        "retire-library-export: %d record(s) archived to %s (%d stale "
        "variant(s) pruned). Re-run safe: deterministic filenames, full "
        "overwrite.\n" % (written, archive_root, pruned))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
