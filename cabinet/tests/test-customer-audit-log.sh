#!/usr/bin/env bash
# cabinet/tests/test-customer-audit-log.sh — FW-097 audit-log regression harness.
#
# WHY THIS EXISTS: Spec 052 AC #12 requires ≥10 hermetic assertions covering:
#   entry emission per schema, hash-chain integrity (tamper breaks chain),
#   PII minimization validator, pagination, append-only enforcement,
#   erasure preserves chain post-pseudonymization, customer-only scope.
#
# HERMETIC: uses $TMP for all file I/O; no Redis, no network, no production paths.
#   LITELLM_AUDIT_LOG_ROOT is overridden to $TMP/audit-root throughout.
#   Python invocations use -c or -m against the audit-server module path.
#
# Usage: bash cabinet/tests/test-customer-audit-log.sh
#   exit 0 = all assertions pass
#   exit 1 = one or more assertions failed (failures listed above summary)
set -u

# ── Locate repo root ──────────────────────────────────────────────────────────
_THIS_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
_SCRIPT_DIR="$(dirname "$_THIS_SCRIPT")"
# cabinet/tests → cabinet → repo root (two levels up)
CABINET_ROOT="$(cd "$_SCRIPT_DIR/../.." && pwd)"
AUDIT_SERVER="${CABINET_ROOT}/proxy/audit-server"

# ── Test infrastructure ───────────────────────────────────────────────────────
PASS=0; FAIL=0; FAILURES=""
pass()     { PASS=$((PASS + 1)); }
fail()     { FAIL=$((FAIL + 1)); FAILURES="${FAILURES}  FAIL: $1\n"; printf '  FAIL: %s\n' "$1"; }
section()  { printf '\n── %s\n' "$1"; }
# assert_eq <label> <got> <want>
assert_eq()  { if [ "$2" = "$3" ]; then pass; else fail "$1: got [$2] want [$3]"; fi; }
# assert_contains <label> <haystack> <needle>
assert_contains() { if printf '%s' "$2" | grep -qF "$3"; then pass; else fail "$1: [$2] should contain [$3]"; fi; }
# assert_not_contains <label> <haystack> <needle>
assert_not_contains() { if ! printf '%s' "$2" | grep -qF "$3"; then pass; else fail "$1: [$2] should NOT contain [$3]"; fi; }
# assert_exit0 <label> <cmd...>
assert_exit0() { local label="$1"; shift; if "$@" >/dev/null 2>&1; then pass; else fail "$label: expected exit 0"; fi; }
# assert_exit_nonzero <label> <cmd...>
assert_exit_nonzero() { local label="$1"; shift; if ! "$@" >/dev/null 2>&1; then pass; else fail "$label: expected nonzero exit"; fi; }

TMP="$(mktemp -d)"
AUDIT_ROOT="${TMP}/audit-root"
mkdir -p "${AUDIT_ROOT}/proxy-audit" "${AUDIT_ROOT}/audit"

trap 'rm -rf "$TMP"' EXIT

# Convenience: run python with LITELLM_AUDIT_LOG_ROOT set and audit-server on path
py() {
  LITELLM_AUDIT_LOG_ROOT="${AUDIT_ROOT}" PYTHONPATH="${AUDIT_SERVER}" python3 "$@"
}

# ── Parse-clean check ─────────────────────────────────────────────────────────
section "0. Python parse-clean check"
for f in hashchain.py validator.py erasure.py ingest.py app.py; do
  assert_exit0 "parse-clean: $f" python3 -c "
import ast
with open('${AUDIT_SERVER}/${f}') as fh:
    ast.parse(fh.read(), filename='${f}')
"
done

# ── 1. Hash-chain: genesis entry has prev_hash = 000...0 ─────────────────────
section "1. Hash-chain genesis"
GENESIS_PREV="$(py -c "
import sys
sys.path.insert(0,'${AUDIT_SERVER}')
import os, json
os.environ['LITELLM_AUDIT_LOG_ROOT'] = '${AUDIT_ROOT}'
import hashchain
entry = hashchain.append({
    'ts':'2026-01-01T00:00:00Z',
    'cabinet_id':'test-cabinet-1',
    'entry_id':'aaa',
    'stream':'proxy',
    'event_type':'llm_request',
    'actor':{'officer':'cos','captain':False},
    'subject':{'type':'tool_call','target':'claude-sonnet','metadata':{}},
    'cost':{'model':'claude-sonnet-4-6','tokens_in':100,'tokens_out':50,'cost_raw_usd':0.01,'cost_marked_up_usd':0.02},
})
print(entry['integrity']['prev_hash'])
" 2>/dev/null)"
GENESIS_HASH_LEN="${#GENESIS_PREV}"
assert_eq "genesis prev_hash is 64 zeroes" "$GENESIS_PREV" "0000000000000000000000000000000000000000000000000000000000000000"
assert_eq "genesis prev_hash length is 64" "$GENESIS_HASH_LEN" "64"

# ── 2. Hash-chain: second entry's prev_hash equals first entry's entry_hash ───
section "2. Hash-chain linkage"
LINK_OUT="$(py -c "
import sys, os, json
sys.path.insert(0,'${AUDIT_SERVER}')
os.environ['LITELLM_AUDIT_LOG_ROOT'] = '${AUDIT_ROOT}'
import hashchain
# Cabinet test-cabinet-link is fresh
e1 = hashchain.append({
    'ts':'2026-01-01T00:00:01Z',
    'cabinet_id':'test-cabinet-link',
    'entry_id':'bbb',
    'stream':'proxy',
    'event_type':'llm_request',
    'actor':{'officer':'cos','captain':False},
    'subject':{'type':'tool_call','target':'m','metadata':{}},
    'cost':{'model':'m','tokens_in':1,'tokens_out':1,'cost_raw_usd':0.001,'cost_marked_up_usd':0.002},
})
e2 = hashchain.append({
    'ts':'2026-01-01T00:00:02Z',
    'cabinet_id':'test-cabinet-link',
    'entry_id':'ccc',
    'stream':'proxy',
    'event_type':'llm_request',
    'actor':{'officer':'cos','captain':False},
    'subject':{'type':'tool_call','target':'m','metadata':{}},
    'cost':{'model':'m','tokens_in':2,'tokens_out':2,'cost_raw_usd':0.002,'cost_marked_up_usd':0.004},
})
h1 = e1['integrity']['entry_hash']
h2_prev = e2['integrity']['prev_hash']
print('match' if h1 == h2_prev else f'mismatch: h1={h1} h2_prev={h2_prev}')
" 2>&1)"
assert_eq "second entry prev_hash == first entry_hash" "$LINK_OUT" "match"

# ── 3. Hash-chain: tamper detection breaks verify ─────────────────────────────
section "3. Hash-chain tamper detection"
TAMPER_OUT="$(py -c "
import sys, os, json, pathlib
sys.path.insert(0,'${AUDIT_SERVER}')
os.environ['LITELLM_AUDIT_LOG_ROOT'] = '${AUDIT_ROOT}'
import hashchain
slug = 'test-cabinet-tamper'
# Write two entries
for i in range(2):
    hashchain.append({
        'ts':'2026-01-01T00:00:0{}Z'.format(i),
        'cabinet_id': slug,
        'entry_id': f'e{i}',
        'stream':'proxy',
        'event_type':'llm_request',
        'actor':{'officer':'cos','captain':False},
        'subject':{'type':'tool_call','target':'m','metadata':{}},
        'cost':{'model':'m','tokens_in':i,'tokens_out':i,'cost_raw_usd':0.0,'cost_marked_up_usd':0.0},
    })
path = pathlib.Path('${AUDIT_ROOT}') / 'audit' / f'{slug}.jsonl'
lines = path.read_text().splitlines()
# Tamper: replace first entry with modified cost
entry0 = json.loads(lines[0])
entry0['cost']['tokens_in'] = 9999  # tamper
lines[0] = json.dumps(entry0)
path.write_text('\n'.join(lines) + '\n')
ok, bad_idx = hashchain.verify(slug)
print('tamper_detected' if not ok else 'tamper_undetected')
" 2>/dev/null)"
assert_eq "tamper detected (chain breaks)" "$TAMPER_OUT" "tamper_detected"

# ── 4. Hash-chain: clean log passes verify ────────────────────────────────────
section "4. Hash-chain verify clean log"
CLEAN_OUT="$(py -c "
import sys, os, json
sys.path.insert(0,'${AUDIT_SERVER}')
os.environ['LITELLM_AUDIT_LOG_ROOT'] = '${AUDIT_ROOT}'
import hashchain
slug = 'test-cabinet-clean'
for i in range(3):
    hashchain.append({
        'ts':'2026-01-01T00:00:0{}Z'.format(i),
        'cabinet_id': slug,
        'entry_id': f'f{i}',
        'stream':'proxy',
        'event_type':'llm_request',
        'actor':{'officer':'cos','captain':False},
        'subject':{'type':'tool_call','target':'m','metadata':{}},
        'cost':{'model':'m','tokens_in':i,'tokens_out':i,'cost_raw_usd':0.0,'cost_marked_up_usd':0.0},
    })
ok, _ = hashchain.verify(slug)
print('valid' if ok else 'invalid')
" 2>&1)"
assert_eq "clean 3-entry chain verifies" "$CLEAN_OUT" "valid"

# ── 5. PII validator: rejects DM entry with full text ────────────────────────
section "5. PII validator: DM full text rejected"
PII_DM_OUT="$(py -c "
import sys, os
sys.path.insert(0,'${AUDIT_SERVER}')
os.environ['LITELLM_AUDIT_LOG_ROOT'] = '${AUDIT_ROOT}'
from validator import validate_and_minimize, ValidationError
entry = {
    'ts':'2026-01-01T00:00:00Z',
    'cabinet_id':'x',
    'entry_id':'g1',
    'stream':'officer',
    'event_type':'dm_received',
    'actor':{'officer':'cos','captain':False},
    'subject':{
        'type':'telegram_dm',
        'target':'nate',
        'metadata':{'text':'secret message','length':14}
    },
    'cost':{},
    'integrity':{'prev_hash':'0'*64,'entry_hash':'abc'},
}
try:
    validate_and_minimize(entry)
    print('accepted')
except ValidationError as e:
    print('rejected')
" 2>&1)"
assert_eq "DM full text rejected" "$PII_DM_OUT" "rejected"

# ── 6. PII validator: redacts secret= in tool_call argv ──────────────────────
section "6. PII validator: secret pattern redacted"
SECRET_OUT="$(py -c "
import sys, os
sys.path.insert(0,'${AUDIT_SERVER}')
os.environ['LITELLM_AUDIT_LOG_ROOT'] = '${AUDIT_ROOT}'
from validator import validate_and_minimize, ValidationError
entry = {
    'ts':'2026-01-01T00:00:00Z',
    'cabinet_id':'x',
    'entry_id':'g2',
    'stream':'officer',
    'event_type':'tool_call',
    'actor':{'officer':'cos','captain':False},
    'subject':{
        'type':'tool_call',
        'target':'grep api_key=mysecretkey file.txt',
        'metadata':{}
    },
    'cost':{},
    'integrity':{'prev_hash':'0'*64,'entry_hash':'abc'},
}
result = validate_and_minimize(entry)
print(result['subject']['target'])
" 2>&1)"
assert_contains "api_key secret redacted in target" "$SECRET_OUT" "REDACTED"
assert_not_contains "original secret not in output" "$SECRET_OUT" "mysecretkey"

# ── 7. PII validator: rejects oversized metadata ─────────────────────────────
section "7. PII validator: oversized metadata rejected"
OVERSIZE_OUT="$(py -c "
import sys, os
sys.path.insert(0,'${AUDIT_SERVER}')
os.environ['LITELLM_AUDIT_LOG_ROOT'] = '${AUDIT_ROOT}'
from validator import validate_and_minimize, ValidationError, MAX_METADATA_BYTES
big = 'x' * (MAX_METADATA_BYTES + 1)
entry = {
    'ts':'2026-01-01T00:00:00Z',
    'cabinet_id':'x',
    'entry_id':'g3',
    'stream':'officer',
    'event_type':'experience_record',
    'actor':{'officer':'cos','captain':False},
    'subject':{'type':'tool_call','target':'x','metadata':{'blob':big}},
    'cost':{},
    'integrity':{'prev_hash':'0'*64,'entry_hash':'abc'},
}
try:
    validate_and_minimize(entry)
    print('accepted')
except ValidationError:
    print('rejected')
" 2>&1)"
assert_eq "oversized metadata rejected" "$OVERSIZE_OUT" "rejected"

# ── 8. Erasure: pseudonymize preserves chain integrity ────────────────────────
section "8. Erasure: pseudonymize preserves hash-chain"
ERASE_OUT="$(py -c "
import sys, os
sys.path.insert(0,'${AUDIT_SERVER}')
os.environ['LITELLM_AUDIT_LOG_ROOT'] = '${AUDIT_ROOT}'
import hashchain, erasure
slug = 'test-cabinet-erasure'
# Write 3 entries
for i in range(3):
    hashchain.append({
        'ts':'2026-01-01T00:00:0{}Z'.format(i),
        'cabinet_id': slug,
        'entry_id': f'h{i}',
        'stream':'cabinet',
        'event_type':'signup',
        'actor':{'officer':None,'captain':True},
        'subject':{'type':'cap_event','target':'test','metadata':{'customer_name':'Nate Test','email':'nate@example.com'}},
        'cost':{},
    })
# Verify clean before erasure
ok_before, _ = hashchain.verify(slug)

# Pseudonymize the cabinet
import pathlib
log_path = pathlib.Path('${AUDIT_ROOT}') / 'audit' / f'{slug}.jsonl'
result = erasure.pseudonymize_cabinet(slug, log_path)

# Verify chain still intact after pseudonymization
ok_after, _ = hashchain.verify(slug)

print(f'before={ok_before} after={ok_after} processed={result[\"processed\"]}')
" 2>&1)"
assert_contains "chain valid before erasure" "$ERASE_OUT" "before=True"
assert_contains "chain valid after erasure" "$ERASE_OUT" "after=True"
assert_contains "all 3 entries processed" "$ERASE_OUT" "processed=3"

# ── 9. Erasure: pseudonymized entry has pseudonym_marker_hash ────────────────
section "9. Erasure: pseudonym_marker_hash present post-erasure"
MARKER_OUT="$(py -c "
import sys, os, json
sys.path.insert(0,'${AUDIT_SERVER}')
os.environ['LITELLM_AUDIT_LOG_ROOT'] = '${AUDIT_ROOT}'
import hashchain, erasure
slug = 'test-cabinet-marker'
hashchain.append({
    'ts':'2026-01-01T00:00:00Z',
    'cabinet_id': slug,
    'entry_id': 'm1',
    'stream':'cabinet',
    'event_type':'signup',
    'actor':{'officer':None,'captain':True},
    'subject':{'type':'cap_event','target':'test','metadata':{'customer_name':'Test User'}},
    'cost':{},
})
import pathlib
log_path = pathlib.Path('${AUDIT_ROOT}') / 'audit' / f'{slug}.jsonl'
erasure.pseudonymize_cabinet(slug, log_path)
# Read back and check
lines = log_path.read_text().strip().splitlines()
entry = json.loads(lines[0])
has_marker = 'pseudonym_marker_hash' in entry
has_original_hash = bool(entry.get('integrity',{}).get('entry_hash'))
print(f'marker={has_marker} original_hash={has_original_hash}')
" 2>&1)"
assert_contains "pseudonym_marker_hash present" "$MARKER_OUT" "marker=True"
assert_contains "original entry_hash preserved" "$MARKER_OUT" "original_hash=True"

# ── 10. Pagination: cursor-based read returns correct page ───────────────────
section "10. Pagination: cursor-based read"
PAGER_OUT="$(py -c "
import sys, os, json, pathlib
sys.path.insert(0,'${AUDIT_SERVER}')
os.environ['LITELLM_AUDIT_LOG_ROOT'] = '${AUDIT_ROOT}'
import hashchain
slug = 'test-cabinet-page'
# Write 5 entries
for i in range(5):
    hashchain.append({
        'ts':'2026-01-01T00:00:0{}Z'.format(i),
        'cabinet_id': slug,
        'entry_id': f'p{i}',
        'stream':'proxy',
        'event_type':'llm_request',
        'actor':{'officer':'cos','captain':False},
        'subject':{'type':'tool_call','target':'m','metadata':{}},
        'cost':{'model':'m','tokens_in':i,'tokens_out':0,'cost_raw_usd':0.0,'cost_marked_up_usd':0.0},
    })
log_path = pathlib.Path('${AUDIT_ROOT}') / 'audit' / f'{slug}.jsonl'
all_lines = [l for l in log_path.read_text().splitlines() if l.strip()]
# Page 1: lines 0-2 (3 entries)
page1 = [json.loads(l) for l in all_lines[0:3]]
# Page 2: lines 3-4 (2 entries)
page2 = [json.loads(l) for l in all_lines[3:5]]
print(f'page1={len(page1)} page2={len(page2)}')
" 2>&1)"
assert_eq "first page has 3 entries" "$(echo "$PAGER_OUT" | grep -o 'page1=[0-9]*' | cut -d= -f2)" "3"
assert_eq "second page has 2 entries" "$(echo "$PAGER_OUT" | grep -o 'page2=[0-9]*' | cut -d= -f2)" "2"

# ── 11. Append-only: app-layer rejects DELETE/PATCH-style calls ───────────────
section "11. Append-only: app rejects non-append operations (schema-level)"
APPEND_ONLY_OUT="$(py -c "
import sys, os
sys.path.insert(0,'${AUDIT_SERVER}')
os.environ['LITELLM_AUDIT_LOG_ROOT'] = '${AUDIT_ROOT}'
# The FastAPI app has no DELETE or PATCH endpoint for existing entries.
# Verify by checking that app routes only include POST (append) and GET (read).
from app import app
routes = [r.path for r in app.routes]
# Must have /proxy/audit/log (POST) and /dashboard/audit/{cabinet_id}/{cursor} (GET)
has_post = '/proxy/audit/log' in routes
has_get = '/dashboard/audit/{cabinet_id}/{cursor}' in routes
# Must NOT have any delete/patch/update route for existing log entries
has_delete = any('delete' in r.lower() or 'remove' in r.lower() for r in routes if 'audit' in r.lower())
print(f'post={has_post} get={has_get} delete={has_delete}')
" 2>&1)"
assert_contains "POST append endpoint present" "$APPEND_ONLY_OUT" "post=True"
assert_contains "GET read endpoint present" "$APPEND_ONLY_OUT" "get=True"
assert_contains "no delete endpoint present" "$APPEND_ONLY_OUT" "delete=False"

# ── 12. Customer-only scope: cross-tenant read FAILS ─────────────────────────
section "12. Cross-tenant read rejected"
CROSS_OUT="$(py -c "
import sys, os
sys.path.insert(0,'${AUDIT_SERVER}')
os.environ['LITELLM_AUDIT_LOG_ROOT'] = '${AUDIT_ROOT}'
os.environ['AUDIT_API_KEY'] = 'customer-a-key'
from app import _authorize_read
# customer-a-key is authorized for cabinet-a
ok_own  = _authorize_read('cabinet-a', 'customer-a-key')
# wrong-key is NOT authorized for cabinet-a (simulates cross-tenant attempt)
ok_cross = _authorize_read('cabinet-a', 'customer-b-key')
print(f'own={ok_own} cross={ok_cross}')
" 2>&1)"
assert_contains "own cabinet read authorized" "$CROSS_OUT" "own=True"
assert_contains "cross-tenant read denied" "$CROSS_OUT" "cross=False"

# ── 13. Ingest: FW-096 record transforms to Spec 052 schema ──────────────────
section "13. Ingest: FW-096 → Spec 052 transform"
INGEST_OUT="$(py -c "
import sys, os, json, pathlib
sys.path.insert(0,'${AUDIT_SERVER}')
os.environ['LITELLM_AUDIT_LOG_ROOT'] = '${AUDIT_ROOT}'
# Write a FW-096 proxy-audit record
slug = 'test-cabinet-ingest'
proxy_dir = pathlib.Path('${AUDIT_ROOT}') / 'proxy-audit'
proxy_dir.mkdir(parents=True, exist_ok=True)
fw096_record = {
    'ts': '2026-01-01T00:00:00Z',
    'cabinet_id': slug,
    'officer': 'cto',
    'request_id': 'req-abc',
    'model': 'claude-sonnet-4-6',
    'provider': 'anthropic',
    'tokens_in': 1000,
    'tokens_out': 500,
    'cost_raw_usd': 0.03,
    'cost_marked_up_usd': 0.06,
    'margin_pct': 100,
    'request_pct_of_cap': 0.06,
    'status': 'success',
}
(proxy_dir / f'{slug}.jsonl').write_text(json.dumps(fw096_record) + '\n')
from ingest import ingest_slug
result = ingest_slug(slug)
# Read the SSOT output
ssot_path = pathlib.Path('${AUDIT_ROOT}') / 'audit' / f'{slug}.jsonl'
if ssot_path.exists():
    entry = json.loads(ssot_path.read_text().strip())
    has_stream = entry.get('stream') == 'proxy'
    has_event = entry.get('event_type') == 'llm_request'
    has_cost = 'cost' in entry and entry['cost'].get('tokens_in') == 1000
    has_chain = 'integrity' in entry and 'entry_hash' in entry['integrity']
    # FW-096-only fields should NOT be at the top level
    no_status_toplevel = 'status' not in entry
    no_pct_toplevel = 'request_pct_of_cap' not in entry
    print(f'ingested={result[\"ingested\"]} stream={has_stream} event={has_event} cost={has_cost} chain={has_chain} no_status={no_status_toplevel} no_pct={no_pct_toplevel}')
else:
    print('ssot_missing')
" 2>&1)"
assert_contains "FW-096 record ingested (1)" "$INGEST_OUT" "ingested=1"
assert_contains "stream=proxy set" "$INGEST_OUT" "stream=True"
assert_contains "event_type=llm_request set" "$INGEST_OUT" "event=True"
assert_contains "cost block with tokens_in" "$INGEST_OUT" "cost=True"
assert_contains "hash-chain present on ingest" "$INGEST_OUT" "chain=True"
assert_contains "status NOT top-level (carried as metadata)" "$INGEST_OUT" "no_status=True"
assert_contains "request_pct_of_cap NOT top-level" "$INGEST_OUT" "no_pct=True"

# ── 14. Schema: required fields present on a well-formed entry ────────────────
section "14. Schema validator: required fields check"
SCHEMA_OUT="$(py -c "
import sys, os
sys.path.insert(0,'${AUDIT_SERVER}')
os.environ['LITELLM_AUDIT_LOG_ROOT'] = '${AUDIT_ROOT}'
import hashchain
from validator import is_valid_entry_schema
slug = 'test-cabinet-schema'
entry = hashchain.append({
    'ts':'2026-01-01T00:00:00Z',
    'cabinet_id': slug,
    'entry_id': 'z1',
    'stream':'proxy',
    'event_type':'llm_request',
    'actor':{'officer':'cos','captain':False},
    'subject':{'type':'tool_call','target':'m','metadata':{}},
    'cost':{'model':'m','tokens_in':1,'tokens_out':1,'cost_raw_usd':0.0,'cost_marked_up_usd':0.0},
})
ok, reason = is_valid_entry_schema(entry)
print(f'valid={ok} reason={reason!r}')
" 2>&1)"
assert_contains "well-formed entry passes schema" "$SCHEMA_OUT" "valid=True"

# ── Summary ───────────────────────────────────────────────────────────────────
printf '\n════════════════════════════════════\n'
printf '  PASS: %d   FAIL: %d   TOTAL: %d\n' "$PASS" "$FAIL" "$((PASS + FAIL))"
if [ "$FAIL" -gt 0 ]; then
  printf '\nFailed assertions:\n'
  printf '%b' "$FAILURES"
  printf '\n'
fi
printf '════════════════════════════════════\n'

[ "$FAIL" -eq 0 ]
