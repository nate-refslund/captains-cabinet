#!/bin/bash
# cabinet/scripts/captain-rules/index.sh — Spec 042 retrieval index builder
#
# Parses shared/interfaces/captain-{patterns,intents}.md, extracts the
# author-curated <!-- index: ... --> metadata blocks, and emits
# shared/interfaces/captain-rules-index.yaml.
#
# Determinism (Spec 042 AC #2): entries sorted by id ASC, fields emitted in
# fixed order. Re-running on unchanged input produces byte-identical output.
#
# Native: bash entrypoint + Python stdlib parser (no PyYAML, no deps).
# Reversibility: rm this file + delete the YAML output → patterns + intents
# fall back to always-loaded behavior. No state to migrate.
#
# Usage:
#   bash cabinet/scripts/captain-rules/index.sh
#   INDEX_OUT=/tmp/test.yaml bash cabinet/scripts/captain-rules/index.sh

set -eu

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(git -C "$SELF_DIR" rev-parse --show-toplevel 2>/dev/null || echo /opt/founders-cabinet)}"
SRC_PATTERNS="$REPO_ROOT/shared/interfaces/captain-patterns.md"
SRC_INTENTS="$REPO_ROOT/shared/interfaces/captain-intents.md"
OUT="${INDEX_OUT:-$REPO_ROOT/shared/interfaces/captain-rules-index.yaml}"

if [ ! -f "$SRC_PATTERNS" ] && [ ! -f "$SRC_INTENTS" ]; then
  echo "[index] no source files found at $SRC_PATTERNS or $SRC_INTENTS" >&2
  exit 1
fi

exec python3 - "$SRC_PATTERNS" "$SRC_INTENTS" "$OUT" <<'PYEOF'
import sys, os, re

sources = sys.argv[1:-1]
out_path = sys.argv[-1]

# Field emit order (Spec 042 §Indexer schema).
ORDER = ['section', 'title', 'trigger_words', 'scope', 'added', 'added_by', 'excerpt']

BLOCK_RE = re.compile(r'<!--\s+index:\s*\n(.*?)\n-->', re.DOTALL)
KV_RE = re.compile(r'^(\w+):\s*(.*)$')
BARE_SCALAR_RE = re.compile(r'^[A-Za-z0-9_/\-.]+$')


REQUIRED = ['id', 'section', 'title', 'trigger_words', 'scope', 'added', 'added_by', 'excerpt']

# A `## ` heading in a source file is expected to carry an <!-- index: --> block
# UNLESS the author explicitly opts it out with an <!-- no-index --> marker
# anywhere in that heading's body (e.g. the `## People` facts block, which holds
# concrete memories, not retrieval rules). The coverage check below fails loudly
# when an indexable heading has no block — this is the structural guard against
# the drift that produced the stale/empty index (BUG 1, 2026-06-25): a file full
# of patterns silently producing fewer entries than headings.
HEADING_RE = re.compile(r'^##\s+(?!#)(.*)$', re.MULTILINE)
NOINDEX_RE = re.compile(r'<!--\s*no-index\s*-->', re.IGNORECASE)


def check_block_coverage(path):
    """Fail (exit 2) if any `## ` heading lacks both an index block and a
    no-index opt-out. Catches authors who add a pattern without its index block,
    so the generated index can never silently drift out of sync with the file."""
    if not os.path.exists(path):
        return
    src = os.path.basename(path)
    with open(path) as f:
        text = f.read()
    # Slice the file into [heading, body-until-next-heading] segments.
    headings = list(HEADING_RE.finditer(text))
    uncovered = []
    for i, h in enumerate(headings):
        title = h.group(1).strip()
        body_start = h.end()
        body_end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[body_start:body_end]
        if NOINDEX_RE.search(body):
            continue  # explicit opt-out (facts/memory block, not a rule)
        if not BLOCK_RE.search(body):
            line = text.count('\n', 0, h.start()) + 1
            uncovered.append((line, title))
    if uncovered:
        sys.stderr.write(
            f"[index] FATAL: {len(uncovered)} heading(s) in {src} have no "
            f"<!-- index: --> block and no <!-- no-index --> opt-out:\n"
        )
        for line, title in uncovered:
            sys.stderr.write(f"[index]   {src}:{line}  ## {title}\n")
        sys.stderr.write(
            "[index] Every pattern/intent heading must carry an index block so it "
            "propagates to officers (see cabinet/scripts/captain-rules/README.md). "
            "For a non-rule heading (a facts/memory block), add an HTML comment "
            "<!-- no-index --> in its body to opt out.\n"
        )
        sys.exit(2)


def parse_blocks(path):
    src = os.path.basename(path)
    if not os.path.exists(path):
        return
    with open(path) as f:
        text = f.read()
    for m in BLOCK_RE.finditer(text):
        fields = {'source': src}
        block_start = text.count('\n', 0, m.start()) + 1
        for offset, line in enumerate(m.group(1).splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            kv = KV_RE.match(stripped)
            if kv:
                fields[kv.group(1)] = kv.group(2).strip()
            else:
                # Stray continuation line — multi-line YAML isn't supported in V1.
                # Refuse loudly so authors fix the source rather than silently dropping content.
                sys.stderr.write(
                    f"[index] FATAL: stray line in block at {src}:{block_start}+{offset}: {stripped!r}\n"
                    f"[index] Multi-line YAML is not supported. Keep each field on a single line.\n"
                )
                sys.exit(2)
        # Skip empty-id blocks: a block with `id:` (empty) sets the field to "" and would
        # produce a corrupt full_ref. Demand a non-empty id.
        if not fields.get('id'):
            sys.stderr.write(f"[index] FATAL: block at {src}:{block_start} has no id\n")
            sys.exit(2)
        missing = [k for k in REQUIRED if not fields.get(k)]
        if missing:
            sys.stderr.write(
                f"[index] FATAL: block id={fields['id']} at {src}:{block_start} missing required fields: {missing}\n"
            )
            sys.exit(2)
        fields['full_ref'] = f"shared/interfaces/{src}#{fields['id']}"
        yield fields


def natural_id_key(rec):
    """Sort key that handles A1/A2/.../A10 correctly (numeric tail), with full
    string as the secondary key so I-W-001/I-W-002 still sort lexicographically."""
    rid = rec['id']
    m = re.match(r'^([^0-9]*)(\d+)$', rid)
    if m:
        return (m.group(1), int(m.group(2)), rid)
    return (rid, 0, rid)


def yaml_value(key, value):
    """Emit a value verbatim (when author already supplied YAML form) or quote a plain string."""
    v = value.strip()
    if key == 'trigger_words':
        # Author supplies a YAML list literal like ["a", "b", "c"].
        return v
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        return v
    if BARE_SCALAR_RE.match(v):
        return v
    esc = v.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{esc}"'


records = []
for src in sources:
    check_block_coverage(src)   # fail loudly on a heading missing its index block
    records.extend(parse_blocks(src))

records.sort(key=natural_id_key)

# Detect duplicate IDs — they would silently shadow each other downstream.
seen = {}
for r in records:
    if r['id'] in seen:
        sys.stderr.write(f"[index] FATAL: duplicate id {r['id']} in {seen[r['id']]} and {r['source']}\n")
        sys.exit(2)
    seen[r['id']] = r['source']

with open(out_path, 'w') as f:
    f.write("# captain-rules-index.yaml\n")
    f.write("# Auto-generated by cabinet/scripts/captain-rules/index.sh — do NOT hand-edit.\n")
    f.write("# Source: shared/interfaces/captain-{patterns,intents}.md\n")
    f.write("# Re-run cabinet/scripts/captain-rules/index.sh after any source-file edit\n")
    f.write("# (pre-commit hook enforces freshness).\n")
    f.write("\n")
    f.write(f"# {len(records)} entries\n")
    f.write("entries:\n")
    for rec in records:
        f.write(f"  - id: {rec['id']}\n")
        f.write(f"    source: {rec['source']}\n")
        for key in ORDER:
            if key in rec:
                f.write(f"    {key}: {yaml_value(key, rec[key])}\n")
        f.write(f"    full_ref: {rec['full_ref']}\n")

print(f"[index] wrote {len(records)} entries -> {out_path}", file=sys.stderr)
PYEOF
