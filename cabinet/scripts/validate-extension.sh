#!/usr/bin/env bash
# validate-extension.sh — the captain-instance half of the axes contract
# (axes spec docs/plans/cabinet-axes-spec-2026-07-05.md §6.4).
#
# Usage:
#   bash cabinet/scripts/validate-extension.sh <extension-dir>
#
# Three gates, all fail-closed (non-zero exit at the first failure); the
# extend-cabinet skill routes every captain extension through this before a
# loader may bind it, and loaders skip anything that fails here (+ file a
# need):
#
#   1. MANIFEST  — <ext>/manifest.yml|.yaml|.json must exist, be the real
#                  file (os.path.realpath containment — a symlinked or
#                  traversal manifest is refused), and validate against
#                  framework/schemas/extension-manifest.schema.json
#                  (jsonschema when available, else a hand-rolled
#                  interpreter of exactly the schema features used — the
#                  system python ships no jsonschema).
#   2. PATHS     — every entrypoint must realpath-resolve INSIDE the
#                  extension dir and exist; absolute paths, "../" traversal
#                  and symlink escapes are refused.
#   3. AXIS LINT — framework/tests/test_axes_contract.py --scan <ext> with
#                  the EMPTY allowlist: extensions RECEIVE resolved axis
#                  values; they never read or branch on axis config.
#
# Read-only: this script never writes anything, and never executes manifest
# content (yaml.safe_load / json only).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCHEMA="$REPO_ROOT/framework/schemas/extension-manifest.schema.json"
LINTER="$REPO_ROOT/framework/tests/test_axes_contract.py"

usage() {
  echo "usage: bash cabinet/scripts/validate-extension.sh <extension-dir>" >&2
  exit 2
}

[ $# -eq 1 ] || usage
EXT_DIR="$1"
[ -d "$EXT_DIR" ] || { echo "validate-extension: FAIL — not a directory: $EXT_DIR" >&2; exit 1; }

# Prefer the repo's test interpreter (has PyYAML); fall back to system python3.
PY="$(command -v python3.12 || command -v python3 || true)"
[ -n "$PY" ] || { echo "validate-extension: FAIL — no python3 interpreter found" >&2; exit 1; }

# --- gates 1 + 2: manifest schema + entrypoint path containment -------------
"$PY" - "$EXT_DIR" "$SCHEMA" <<'PY'
import json
import os
import re
import sys

ext_dir, schema_path = sys.argv[1], sys.argv[2]
real_ext = os.path.realpath(ext_dir)


def fail(msg):
    sys.stderr.write("validate-extension: FAIL — %s\n" % msg)
    sys.exit(1)


def contained(path, root):
    rp = os.path.realpath(path)
    return rp == root or rp.startswith(root + os.sep)


# Locate the manifest (lexists so a dangling/symlinked manifest is SEEN and
# refused rather than skipped — fail-closed).
manifest_path = None
for name in ("manifest.yml", "manifest.yaml", "manifest.json"):
    cand = os.path.join(ext_dir, name)
    if os.path.lexists(cand):
        manifest_path = cand
        break
if manifest_path is None:
    fail("no manifest.yml/.yaml/.json in %s" % ext_dir)
if os.path.islink(manifest_path) or not contained(manifest_path, real_ext):
    fail("manifest is a symlink or resolves outside the extension dir — refused")
if not os.path.isfile(manifest_path):
    fail("manifest is not a regular file")

try:
    with open(manifest_path, "r") as fh:
        text = fh.read()
    if manifest_path.endswith(".json"):
        manifest = json.loads(text)
    else:
        try:
            import yaml
        except ImportError:
            fail("PyYAML unavailable in %s — use manifest.json or run under "
                 "python3.12" % sys.executable)
        manifest = yaml.safe_load(text)
except SystemExit:
    raise
except Exception as exc:
    fail("manifest unparseable: %s" % exc)

try:
    with open(schema_path, "r") as fh:
        schema = json.load(fh)
except Exception as exc:
    fail("manifest schema unreadable at %s: %s" % (schema_path, exc))


def hand_validate(instance, sch, where="manifest"):
    """Interpreter for exactly the schema features extension-manifest uses
    (type object/array/string, required, additionalProperties, properties,
    enum, pattern [re.search — jsonschema semantics], minLength, minItems,
    minProperties). Kept behind the jsonschema fast path below."""
    errs = []
    typ = sch.get("type")
    if typ == "object":
        if not isinstance(instance, dict):
            return ["%s: expected object" % where]
        props = sch.get("properties", {})
        for req in sch.get("required", []):
            if req not in instance:
                errs.append("%s: missing required key '%s'" % (where, req))
        addl = sch.get("additionalProperties")
        extra = sorted(set(instance) - set(props))
        if addl is False and extra:
            errs.append("%s: unknown keys %s" % (where, extra))
        if "minProperties" in sch and len(instance) < sch["minProperties"]:
            errs.append("%s: needs at least %d entries"
                        % (where, sch["minProperties"]))
        for key, sub in props.items():
            if key in instance:
                errs.extend(hand_validate(instance[key], sub,
                                          "%s.%s" % (where, key)))
        if isinstance(addl, dict):
            for key in extra:
                errs.extend(hand_validate(instance[key], addl,
                                          "%s.%s" % (where, key)))
        return errs
    if typ == "array":
        if not isinstance(instance, list):
            return ["%s: expected array" % where]
        if "minItems" in sch and len(instance) < sch["minItems"]:
            errs.append("%s: needs at least %d items" % (where, sch["minItems"]))
        items = sch.get("items")
        if isinstance(items, dict):
            for i, val in enumerate(instance):
                errs.extend(hand_validate(val, items, "%s[%d]" % (where, i)))
        return errs
    if typ == "string":
        if not isinstance(instance, str):
            return ["%s: expected string" % where]
        if "minLength" in sch and len(instance) < sch["minLength"]:
            errs.append("%s: shorter than minLength %d"
                        % (where, sch["minLength"]))
        if "pattern" in sch and re.search(sch["pattern"], instance) is None:
            errs.append("%s: %r does not match pattern %s"
                        % (where, instance, sch["pattern"]))
        if "enum" in sch and instance not in sch["enum"]:
            errs.append("%s: %r not in %s" % (where, instance, sch["enum"]))
        return errs
    if "enum" in sch and instance not in sch["enum"]:
        errs.append("%s: %r not in enum" % (where, instance))
    return errs


try:
    import jsonschema
except ImportError:
    errors = hand_validate(manifest, schema)
else:
    try:
        jsonschema.validate(manifest, schema)
        errors = []
    except jsonschema.ValidationError as exc:
        errors = ["manifest%s: %s" % (
            "".join("[%r]" % p for p in exc.absolute_path), exc.message)]
if errors:
    fail("manifest invalid: %s" % "; ".join(str(e) for e in errors[:5]))

# Entrypoint path safety — traversal/symlink refusal + existence.
for cap in sorted(manifest.get("entrypoints") or {}):
    rel = manifest["entrypoints"][cap]
    if os.path.isabs(rel):
        fail("entrypoints.%s: absolute path refused (%s)" % (cap, rel))
    joined = os.path.join(ext_dir, rel)
    if not contained(joined, real_ext):
        fail("entrypoints.%s: resolves outside the extension dir "
             "(traversal/symlink) — refused (%s)" % (cap, rel))
    if not os.path.isfile(joined):
        fail("entrypoints.%s: file does not exist (%s)" % (cap, rel))

sys.stdout.write("validate-extension: manifest OK (%s)\n"
                 % os.path.basename(manifest_path))
PY

# --- gate 3: the axis linter, strict (empty allowlist) ----------------------
"$PY" "$LINTER" --scan "$EXT_DIR" || {
  echo "validate-extension: FAIL — axis-contract linter violations in $EXT_DIR (axes are data; extensions receive resolved axis values)" >&2
  exit 1
}

echo "validate-extension: OK — $EXT_DIR"
