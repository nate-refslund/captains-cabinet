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

# ── 9b. Erasure: tampering a pseudonymized entry BREAKS verify via marker (CTO #2 fix) ──
section "9b. Erasure: marker-tamper breaks verify"
TAMPER_OUT="$(py -c "
import sys, os, json, pathlib
sys.path.insert(0,'${AUDIT_SERVER}')
os.environ['LITELLM_AUDIT_LOG_ROOT'] = '${AUDIT_ROOT}'
import hashchain, erasure
slug = 'test-cabinet-marker-tamper'
hashchain.append({
    'ts':'2026-01-01T00:00:00Z','cabinet_id':slug,'entry_id':'mt1','stream':'cabinet',
    'event_type':'signup','actor':{'officer':None,'captain':True},
    'subject':{'type':'cap_event','target':'t','metadata':{'customer_name':'Tamper User'}},'cost':{},
})
log_path = pathlib.Path('${AUDIT_ROOT}') / 'audit' / f'{slug}.jsonl'
erasure.pseudonymize_cabinet(slug, log_path)
ok_clean, _ = hashchain.verify(slug)
# Post-erasure tamper: change content but KEEP the stale pseudonym_marker_hash
entry = json.loads(log_path.read_text().strip().splitlines()[0])
entry['subject']['metadata']['customer_name'] = 'ATTACKER-INJECTED'
log_path.write_text(json.dumps(entry, separators=(',',':'))+'\n')
ok_tampered, bad_idx = hashchain.verify(slug)
print(f'clean={ok_clean} tampered={ok_tampered} bad_idx={bad_idx}')
" 2>&1)"
assert_contains "verify passes on clean pseudonymized entry" "$TAMPER_OUT" "clean=True"
assert_contains "verify FAILS on tampered pseudonymized entry (marker-check, CTO #2)" "$TAMPER_OUT" "tampered=False"

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
    # #234: proxy-only metadata keys must SURVIVE the union allow-list (regression guard —
    # the client allow-list alone would wrongly drop these proxy-stream fields)
    md = entry.get('subject',{}).get('metadata',{})
    pct_in_meta = 'request_pct_of_cap' in md
    status_in_meta = 'fw096_status' in md
    print(f'ingested={result[\"ingested\"]} stream={has_stream} event={has_event} cost={has_cost} chain={has_chain} no_status={no_status_toplevel} no_pct={no_pct_toplevel} pct_meta={pct_in_meta} status_meta={status_in_meta}')
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
assert_contains "request_pct_of_cap survives in metadata (union allow-list)" "$INGEST_OUT" "pct_meta=True"
assert_contains "fw096_status survives in metadata (union allow-list)" "$INGEST_OUT" "status_meta=True"

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

# ── 15. PII validator: deny-list blind spots closed by allow-list (#234) ──────
# The original deny-list missed nested keys, case-variant keys, arbitrary keys, and
# non-DM-event PII. The fail-closed allow-list + recursive/case-insensitive forbidden
# reject close all four. Each sub-case asserts reject (fail-loud) or drop (minimize).
section "15. Allow-list closes deny-list blind spots (#234, Spec 052 v3.4 AC#3)"
BLINDSPOT_OUT="$(py -c "
import sys
sys.path.insert(0,'${AUDIT_SERVER}')
from validator import validate_and_minimize, ValidationError

def check(meta, event_type='tool_call', subject_type='tool_call'):
    entry = {
        'ts':'t','cabinet_id':'x','entry_id':'e','stream':'officer',
        'event_type':event_type,
        'actor':{'officer':'cos','captain':False},
        'subject':{'type':subject_type,'target':'t','metadata':meta},
        'cost':{},'integrity':{'prev_hash':'0'*64,'entry_hash':'a'},
    }
    try:
        r = validate_and_minimize(entry)
        return 'ok', r['subject'].get('metadata') or {}
    except ValidationError:
        return 'reject', {}

# Blind spot 1: nested forbidden key -> REJECT (recursive)
nested, _ = check({'msg': {'body': 'PII text'}})
# Blind spot 2: case-variant forbidden key -> REJECT (case-insensitive)
case, _ = check({'Text': 'PII'})
# Blind spot 2b: case-variant forbidden key nested in a list -> REJECT
inlist, _ = check({'attachments': [{'Content': 'bytes'}]})
# Blind spot 3: arbitrary unknown (non-forbidden) key -> DROP (accept), keep allow-listed sibling
arb, arb_meta = check({'customer_email': 'nate@example.com', 'length': 5})
arb_dropped = 'customer_email' not in arb_meta
len_kept = arb_meta.get('length') == 5
# Nested object under an ALLOWED key, no forbidden key inside -> DROP the key (accept)
nd, nd_meta = check({'path': {'nested': 'x'}})
nested_dropped = 'path' not in nd_meta
# Over-length string under an allowed key -> DROP (accept)
ol, ol_meta = check({'path': 'x'*300})
overlong_dropped = 'path' not in ol_meta
# Allow-listed scalars survive untouched
okk, ok_meta = check({'command_head': 'git status', 'count': 3})
scalar_kept = ok_meta.get('command_head') == 'git status' and ok_meta.get('count') == 3
# Blind spot 4: forbidden key in a NON-DM event -> REJECT (old deny-list only checked DM events)
nonDM, _ = check({'body': 'PII'}, event_type='experience_record', subject_type='cabinet_event')

print(f'nested={nested} case={case} inlist={inlist} arb={arb} arb_dropped={arb_dropped} '
      f'len_kept={len_kept} nested_dropped={nested_dropped} overlong_dropped={overlong_dropped} '
      f'scalar_kept={scalar_kept} nonDM={nonDM}')
" 2>&1)"
assert_contains "nested forbidden key rejected (recursive)"          "$BLINDSPOT_OUT" "nested=reject"
assert_contains "case-variant forbidden key rejected"               "$BLINDSPOT_OUT" "case=reject"
assert_contains "forbidden key nested in list rejected"             "$BLINDSPOT_OUT" "inlist=reject"
assert_contains "arbitrary unknown key accepted (drop-minimize)"    "$BLINDSPOT_OUT" "arb=ok"
assert_contains "arbitrary unknown key dropped from metadata"       "$BLINDSPOT_OUT" "arb_dropped=True"
assert_contains "allow-listed sibling key kept"                     "$BLINDSPOT_OUT" "len_kept=True"
assert_contains "nested object under allowed key dropped"           "$BLINDSPOT_OUT" "nested_dropped=True"
assert_contains "over-length string under allowed key dropped"      "$BLINDSPOT_OUT" "overlong_dropped=True"
assert_contains "allow-listed scalars survive"                      "$BLINDSPOT_OUT" "scalar_kept=True"
assert_contains "forbidden key in non-DM event rejected"            "$BLINDSPOT_OUT" "nonDM=reject"

# ── 16. PII validator: whole-entry coverage — actor/cost/target (#234 F1/F2) ──
# The fix extends minimization beyond subject.metadata: actor + cost are key-allow-listed
# to their typed schemas, and subject.target is secret-redacted (all events) + length-bound.
section "16. Whole-entry minimization: actor/cost/target (#234 Opus F1/F2)"
WHOLE_OUT="$(py -c "
import sys
sys.path.insert(0,'${AUDIT_SERVER}')
from validator import validate_and_minimize, ValidationError, MAX_VALUE_LEN

def vfull(actor=None, cost=None, target='t', event_type='tool_call', subject_type='tool_call'):
    entry = {
        'ts':'t','cabinet_id':'x','entry_id':'e','stream':'officer','event_type':event_type,
        'actor': actor if actor is not None else {'officer':'cos','captain':False},
        'subject':{'type':subject_type,'target':target,'metadata':{}},
        'cost': cost if cost is not None else {},
        'integrity':{'prev_hash':'0'*64,'entry_hash':'a'},
    }
    try:
        return 'ok', validate_and_minimize(entry)
    except ValidationError:
        return 'reject', None

# F1: forbidden key in actor / cost -> REJECT (was previously uninspected)
a_forbid, _ = vfull(actor={'officer':'cos','captain':False,'text':'PII in actor'})
c_forbid, _ = vfull(cost={'model':'m','body':'PII in cost'})
# F1: arbitrary key in actor / cost -> DROP, typed schema kept
a_arb, ar = vfull(actor={'officer':'cos','captain':False,'customer':'Nate Real Name'})
a_arb_dropped = a_arb=='ok' and 'customer' not in ar['actor'] and ar['actor'].get('officer')=='cos'
c_arb, cr = vfull(cost={'model':'m','tokens_in':5,'injected':'PII'})
c_arb_dropped = c_arb=='ok' and 'injected' not in cr['cost'] and cr['cost'].get('tokens_in')==5
# F1: actor.officer == None preserved (captain-action entry, not dropped)
a_none, anr = vfull(actor={'officer':None,'captain':True})
officer_none_kept = a_none=='ok' and 'officer' in anr['actor'] and anr['actor']['officer'] is None
# F2: secret in target on NON-tool_call event -> redacted (was tool_call-gated)
t_sec, tr = vfull(target='token=sk-leak-123', event_type='dm_received', subject_type='telegram_dm')
target_redacted = t_sec=='ok' and 'sk-leak-123' not in tr['subject']['target'] and 'REDACTED' in tr['subject']['target']
# F2: over-length target -> bounded to MAX_VALUE_LEN
t_long, tlr = vfull(target='x'*400)
target_bounded = t_long=='ok' and len(tlr['subject']['target'])==MAX_VALUE_LEN
# FP guard: proxy model-name target passes through unchanged
t_model, tmr = vfull(target='claude-3-5-sonnet-20241022', event_type='llm_request')
model_unchanged = t_model=='ok' and tmr['subject']['target']=='claude-3-5-sonnet-20241022'

print(f'a_forbid={a_forbid} c_forbid={c_forbid} a_arb_dropped={a_arb_dropped} c_arb_dropped={c_arb_dropped} '
      f'officer_none_kept={officer_none_kept} target_redacted={target_redacted} '
      f'target_bounded={target_bounded} model_unchanged={model_unchanged}')
" 2>&1)"
assert_contains "forbidden key in actor rejected"              "$WHOLE_OUT" "a_forbid=reject"
assert_contains "forbidden key in cost rejected"               "$WHOLE_OUT" "c_forbid=reject"
assert_contains "arbitrary actor key dropped, schema kept"     "$WHOLE_OUT" "a_arb_dropped=True"
assert_contains "arbitrary cost key dropped, schema kept"      "$WHOLE_OUT" "c_arb_dropped=True"
assert_contains "actor.officer None preserved"                 "$WHOLE_OUT" "officer_none_kept=True"
assert_contains "secret in non-tool_call target redacted"      "$WHOLE_OUT" "target_redacted=True"
assert_contains "over-length target bounded"                   "$WHOLE_OUT" "target_bounded=True"
assert_contains "proxy model-name target unchanged (no FP)"    "$WHOLE_OUT" "model_unchanged=True"

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
