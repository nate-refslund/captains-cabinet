#!/usr/bin/env bash
# cabinet/tests/test-audit-checkpoint.sh — Spec 052 WORM checkpoint (Phase 1) regression harness.
#
# Covers checkpoint.py emit logic, OPAQUE-id-keyed (AC #13): empty-dir no-op, per-cabinet latest
# entry_hash + count + chain verify, tamper-surfacing, the OPAQUE-id keying (published files keyed
# by opaque id, NEVER the slug), FAIL-CLOSED skip of unmapped + malformed-opaque + non-slug-named
# cabinets, the UNSIGNED Phase-1 marker, the APPEND-ONLY git mirror's immutable history, the benign
# empty-commit path, and the NO-SLUG-ANYWHERE privacy invariant over every published artifact.
#
# HERMETIC: $TMP for all I/O; no network, no production paths, no Redis. Git ops run in a $TMP repo.
# Usage: bash cabinet/tests/test-audit-checkpoint.sh  (exit 0 = all pass)
set -u

_THIS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
CABINET_ROOT="$(cd "$(dirname "$_THIS")/../.." && pwd)"
AUDIT_SERVER="${CABINET_ROOT}/proxy/audit-server"

PASS=0; FAIL=0; FAILURES=""
pass(){ PASS=$((PASS+1)); }
fail(){ FAIL=$((FAIL+1)); FAILURES="${FAILURES}  FAIL: $1\n"; printf '  FAIL: %s\n' "$1"; }
section(){ printf '\n── %s\n' "$1"; }
assert_eq(){ if [ "$2" = "$3" ]; then pass; else fail "$1: got [$2] want [$3]"; fi; }
assert_contains(){ if printf '%s' "$2" | grep -qF "$3"; then pass; else fail "$1: [$2] should contain [$3]"; fi; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
ROOT="${TMP}/logs"; mkdir -p "${ROOT}/audit"
PUB="${TMP}/checkpoints"; GIT="${TMP}/checkpoints-git"; MAP="${ROOT}/cabinet-id-map.json"

py(){ LITELLM_AUDIT_LOG_ROOT="$ROOT" AUDIT_CHECKPOINT_DIR="$PUB" AUDIT_CHECKPOINT_GIT_DIR="$GIT" \
      AUDIT_CHECKPOINT_ID_MAP="$MAP" PYTHONPATH="$AUDIT_SERVER" python3 "$@"; }

# The slug->opaque-id map the FW-098 install would write. unmapped-cab is deliberately ABSENT
# (fail-closed test); malformed-map-cab maps to a NON-slug value (fail-closed test).
py -c "
import json, pathlib
pathlib.Path('$MAP').write_text(json.dumps({
  'valid-cab':'opq-valid-1', 'tamper-cab':'opq-tamper-1', 'git-cab':'opq-git-1',
  'malformed-map-cab':'NOT_A_SLUG_UPPER'
}))
"

# ── 0. parse-clean ────────────────────────────────────────────────────────────
section "0. checkpoint.py parse-clean"
assert_eq "checkpoint.py parses" \
  "$(py -c "import ast; ast.parse(open('${AUDIT_SERVER}/checkpoint.py').read()); print('ok')" 2>&1)" "ok"

# ── 1. empty audit dir → no published cabinets, snapshot still written ──
section "1. empty audit dir: no-op sweep + snapshot written"
EMPTY_OUT="$(py -c "
import json, pathlib, checkpoint
res = checkpoint.emit_all()
man = json.loads((pathlib.Path('${PUB}')/'latest.json').read_text())
print('published='+str(res['published']), 'manifest_n='+str(len(man['cabinets'])))
" 2>&1)"
assert_contains "empty dir → nothing published" "$EMPTY_OUT" "published=[]"
assert_contains "latest.json still written (empty manifest)" "$EMPTY_OUT" "manifest_n=0"

# ── 2. mapped valid cabinet → published keyed by OPAQUE id, NO slug anywhere in the record ──
section "2. mapped cabinet: opaque-keyed publish, slug never published (AC #13)"
OUT="$(py -c "
import sys; sys.path.insert(0,'${AUDIT_SERVER}')
import json, pathlib, hashchain, checkpoint
for i in range(3):
    hashchain.append({'ts':'2026-01-01T00:00:0%dZ'%i,'cabinet_id':'valid-cab','entry_id':'e%d'%i,
        'stream':'proxy','event_type':'llm_request','actor':{'officer':'cos','captain':False},
        'subject':{'type':'tool_call','target':'m','metadata':{}},
        'cost':{'model':'m','tokens_in':i,'tokens_out':i,'cost_raw_usd':0.0,'cost_marked_up_usd':0.0}})
res = checkpoint.emit_all()
last=''
for ln in (pathlib.Path('${ROOT}')/'audit'/'valid-cab.jsonl').read_text().splitlines():
    if ln.strip(): last = json.loads(ln)['integrity']['entry_hash']
opq = pathlib.Path('${PUB}')/'opq-valid-1.json'
slugfile = pathlib.Path('${PUB}')/'valid-cab.json'
cp = json.loads(opq.read_text()) if opq.exists() else {}
man = json.loads((pathlib.Path('${PUB}')/'latest.json').read_text())
man_blob = json.dumps(man)
print('published_slug='+str('valid-cab' in res['published']),
      'opaque_file='+str(opq.exists()), 'no_slug_file='+str(not slugfile.exists()),
      'pubid='+str(cp.get('cabinet_public_id')), 'no_slug_field='+str('cabinet_id' not in cp),
      'count='+str(cp.get('entry_count')), 'valid='+str(cp.get('chain_valid')),
      'hashmatch='+str(cp.get('latest_entry_hash')==last),
      'signed='+str(cp.get('signed')), 'phase='+str(cp.get('phase')),
      'manifest_no_slug='+str('valid-cab' not in man_blob))
" 2>&1)"
assert_contains "cabinet published (internal slug list)"   "$OUT" "published_slug=True"
assert_contains "published file keyed by OPAQUE id"        "$OUT" "opaque_file=True"
assert_contains "NO slug-named file in served dir"         "$OUT" "no_slug_file=True"
assert_contains "record carries cabinet_public_id"         "$OUT" "pubid=opq-valid-1"
assert_contains "record has NO slug cabinet_id field"      "$OUT" "no_slug_field=True"
assert_contains "entry_count=3"                            "$OUT" "count=3"
assert_contains "chain_valid=True"                         "$OUT" "valid=True"
assert_contains "latest_entry_hash matches SSOT tail"      "$OUT" "hashmatch=True"
assert_contains "UNSIGNED (Phase 1)"                       "$OUT" "signed=False"
assert_contains "phase=1"                                  "$OUT" "phase=1"
assert_contains "latest.json contains NO slug"             "$OUT" "manifest_no_slug=True"

# ── 3. tamper detection surfaced (chain_valid=false + slug in broken — internal/operator) ──
section "3. tampered chain surfaced as broken"
TAMP_OUT="$(py -c "
import sys; sys.path.insert(0,'${AUDIT_SERVER}')
import json, pathlib, hashchain, checkpoint
for i in range(2):
    hashchain.append({'ts':'2026-01-01T00:00:0%dZ'%i,'cabinet_id':'tamper-cab','entry_id':'t%d'%i,
        'stream':'proxy','event_type':'llm_request','actor':{'officer':'cos','captain':False},
        'subject':{'type':'tool_call','target':'m','metadata':{}},
        'cost':{'model':'m','tokens_in':i,'tokens_out':i,'cost_raw_usd':0.0,'cost_marked_up_usd':0.0}})
p = pathlib.Path('${ROOT}')/'audit'/'tamper-cab.jsonl'
lines = p.read_text().splitlines()
e0 = json.loads(lines[0]); e0['cost']['tokens_in'] = 9999; lines[0] = json.dumps(e0)
p.write_text(chr(10).join(lines)+chr(10))
res = checkpoint.emit_all()
cp = json.loads((pathlib.Path('${PUB}')/'opq-tamper-1.json').read_text())
print('valid='+str(cp['chain_valid']), 'in_broken='+str('tamper-cab' in res['broken']))
" 2>&1)"
assert_contains "tampered chain → chain_valid=False" "$TAMP_OUT" "valid=False"
assert_contains "tampered cabinet in broken[] (operator)" "$TAMP_OUT" "in_broken=True"

# ── 4. FAIL-CLOSED: a valid cabinet with NO map entry is SKIPPED — never published ──
section "4. fail-closed: unmapped cabinet skipped (no public output, no slug leak)"
UNMAP_OUT="$(py -c "
import sys; sys.path.insert(0,'${AUDIT_SERVER}')
import json, pathlib, hashchain, checkpoint
hashchain.append({'ts':'2026-01-01T00:00:00Z','cabinet_id':'unmapped-cab','entry_id':'u0',
    'stream':'proxy','event_type':'llm_request','actor':{'officer':'cos','captain':False},
    'subject':{'type':'tool_call','target':'m','metadata':{}},
    'cost':{'model':'m','tokens_in':1,'tokens_out':1,'cost_raw_usd':0.0,'cost_marked_up_usd':0.0}})
res = checkpoint.emit_all()
pub = pathlib.Path('${PUB}')
slug_file = (pub/'unmapped-cab.json').exists()
leak = any('unmapped-cab' in f.read_text() for f in pub.glob('*.json'))
print('not_published='+str('unmapped-cab' not in res['published']),
      'no_slug_file='+str(not slug_file), 'no_leak='+str(not leak))
" 2>&1)"
assert_contains "unmapped cabinet NOT published"             "$UNMAP_OUT" "not_published=True"
assert_contains "no slug-named file for unmapped"            "$UNMAP_OUT" "no_slug_file=True"
assert_contains "unmapped slug appears in NO published file" "$UNMAP_OUT" "no_leak=True"

# ── 5. fail-closed: malformed opaque-id value in the map is skipped ──
section "5. fail-closed: malformed opaque-id (non-slug value) skipped"
MAL_OUT="$(py -c "
import sys; sys.path.insert(0,'${AUDIT_SERVER}')
import json, pathlib, hashchain, checkpoint
hashchain.append({'ts':'2026-01-01T00:00:00Z','cabinet_id':'malformed-map-cab','entry_id':'m0',
    'stream':'proxy','event_type':'llm_request','actor':{'officer':'cos','captain':False},
    'subject':{'type':'tool_call','target':'m','metadata':{}},
    'cost':{'model':'m','tokens_in':1,'tokens_out':1,'cost_raw_usd':0.0,'cost_marked_up_usd':0.0}})
res = checkpoint.emit_all()
pub = pathlib.Path('${PUB}')
mal_file = (pub/'NOT_A_SLUG_UPPER.json').exists()
print('not_published='+str('malformed-map-cab' not in res['published']),
      'no_malformed_file='+str(not mal_file))
" 2>&1)"
assert_contains "malformed-opaque cabinet NOT published" "$MAL_OUT" "not_published=True"
assert_contains "no file built from a malformed opaque id" "$MAL_OUT" "no_malformed_file=True"

# ── 6. non-slug SSOT filename skipped (reuses #237 is_valid_cabinet_id) ──
section "6. non-slug SSOT filename skipped"
NS_OUT="$(py -c "
import sys; sys.path.insert(0,'${AUDIT_SERVER}')
import json, pathlib, checkpoint
bad = pathlib.Path('${ROOT}')/'audit'/'BAD-Cabinet.jsonl'
bad.write_text(json.dumps({'cabinet_id':'BAD-Cabinet','integrity':{'entry_hash':'deadbeef'}})+chr(10))
res = checkpoint.emit_all()
print('skipped='+str('BAD-Cabinet' not in res['published']))
" 2>&1)"
assert_contains "non-slug filename not published" "$NS_OUT" "skipped=True"

# ── 7. git mirror: APPEND-ONLY immutable ledger keyed by OPAQUE id + a commit per checkpoint ──
section "7. git mirror append-only (opaque-keyed) + commit per checkpoint"
GIT_OUT="$(py -c "
import sys; sys.path.insert(0,'${AUDIT_SERVER}')
import subprocess, json, pathlib, hashchain, checkpoint
G='${GIT}'
subprocess.run(['git','init','-q',G], check=True)
for i in range(2):
    hashchain.append({'ts':'2026-02-01T00:00:0%dZ'%i,'cabinet_id':'git-cab','entry_id':'g%d'%i,
        'stream':'proxy','event_type':'llm_request','actor':{'officer':'cos','captain':False},
        'subject':{'type':'tool_call','target':'m','metadata':{}},
        'cost':{'model':'m','tokens_in':i,'tokens_out':i,'cost_raw_usd':0.0,'cost_marked_up_usd':0.0}})
checkpoint.emit_all()
c1 = int(subprocess.run(['git','-C',G,'rev-list','--count','HEAD'],capture_output=True,text=True).stdout.strip())
ledger = pathlib.Path(G)/'opq-git-1.checkpoints.jsonl'
slug_ledger = (pathlib.Path(G)/'git-cab.checkpoints.jsonl').exists()
l1 = len(ledger.read_text().splitlines()) if ledger.exists() else -1
hashchain.append({'ts':'2026-02-01T00:00:09Z','cabinet_id':'git-cab','entry_id':'g2',
    'stream':'proxy','event_type':'llm_request','actor':{'officer':'cos','captain':False},
    'subject':{'type':'tool_call','target':'m','metadata':{}},
    'cost':{'model':'m','tokens_in':9,'tokens_out':9,'cost_raw_usd':0.0,'cost_marked_up_usd':0.0}})
checkpoint.emit_all()
c2 = int(subprocess.run(['git','-C',G,'rev-list','--count','HEAD'],capture_output=True,text=True).stdout.strip())
lines = ledger.read_text().splitlines()
counts = [json.loads(x)['entry_count'] for x in lines]
sig = subprocess.run(['git','-C',G,'log','-1','--format=%G?'],capture_output=True,text=True).stdout.strip()
print('opaque_ledger='+str(ledger.exists()), 'no_slug_ledger='+str(not slug_ledger),
      'c1='+str(c1),'c2='+str(c2),'l1='+str(l1),'counts='+str(counts),'sig='+sig)
" 2>&1)"
assert_contains "ledger keyed by OPAQUE id"                "$GIT_OUT" "opaque_ledger=True"
assert_contains "NO slug-named ledger"                     "$GIT_OUT" "no_slug_ledger=True"
assert_contains "first checkpoint commits to git mirror"   "$GIT_OUT" "c1=1"
assert_contains "second checkpoint adds a commit"          "$GIT_OUT" "c2=2"
assert_contains "ledger APPENDS (progression 2 -> 3)"      "$GIT_OUT" "counts=[2, 3]"
assert_contains "commit is UNSIGNED (Phase 1, %G? = N)"    "$GIT_OUT" "sig=N"

# ── 8. empty-commit path benign (stdout 'nothing to commit' not misread as failure) ──
section "8. empty-commit path benign"
EC_OUT="$(py -c "
import sys; sys.path.insert(0,'${AUDIT_SERVER}')
import io, glob, os, logging, subprocess, pathlib, checkpoint
G='${GIT}'
before = int(subprocess.run(['git','-C',G,'rev-list','--count','HEAD'],capture_output=True,text=True).stdout.strip())
buf = io.StringIO(); h = logging.StreamHandler(buf)
lg = logging.getLogger('checkpoint'); lg.addHandler(h); lg.setLevel(logging.INFO)
for f in glob.glob(str(pathlib.Path('${ROOT}')/'audit'/'*.jsonl')): os.remove(f)
checkpoint.emit_all()
after = int(subprocess.run(['git','-C',G,'rev-list','--count','HEAD'],capture_output=True,text=True).stdout.strip())
log = buf.getvalue()
print('no_new_commit='+str(after==before),
      'no_false_warning='+str('commit failed' not in log),
      'noop_info='+str('unchanged since last checkpoint' in log))
" 2>&1)"
assert_contains "empty-commit creates no spurious commit"    "$EC_OUT" "no_new_commit=True"
assert_contains "empty-commit logs NO false 'commit failed'" "$EC_OUT" "no_false_warning=True"
assert_contains "empty-commit logged as benign no-op"        "$EC_OUT" "noop_info=True"

# ── 9. NO-SLUG-ANYWHERE invariant: no test slug appears in ANY published artifact (AC #13) ──
section "9. privacy invariant: no slug in any served file or git ledger"
LEAK_OUT="$(
  hits=0
  for slug in valid-cab tamper-cab git-cab unmapped-cab malformed-map-cab; do
    if grep -rqF "$slug" "$PUB" "$GIT" 2>/dev/null; then echo "LEAK: $slug"; hits=$((hits+1)); fi
    # also the git COMMIT MESSAGES (zlib-compressed in .git/objects, so grep -r misses them)
    if [ -d "$GIT/.git" ] && git -C "$GIT" log --format=%B 2>/dev/null | grep -qF "$slug"; then echo "LEAK(commit-msg): $slug"; hits=$((hits+1)); fi
  done
  echo "slug_leaks=${hits}"
)"
assert_contains "ZERO test slugs in any published artifact" "$LEAK_OUT" "slug_leaks=0"

# ── 10. collision guard: two slugs -> SAME opaque id => BOTH skipped (anchor never clobbered) ──
section "10. opaque-id collision: colliding cabinets fail-closed-skipped"
COLL_OUT="$(py -c "
import sys; sys.path.insert(0,'${AUDIT_SERVER}')
import json, pathlib, hashchain, checkpoint
# fresh map with a COLLISION: cab-x and cab-y both map to opq-dup
pathlib.Path('${MAP}').write_text(json.dumps({'cab-x':'opq-dup','cab-y':'opq-dup'}))
for s,n in [('cab-x',5),('cab-y',2)]:
    for i in range(n):
        hashchain.append({'ts':'2026-03-01T00:00:0%dZ'%(i%10),'cabinet_id':s,'entry_id':s+str(i),
            'stream':'proxy','event_type':'llm_request','actor':{'officer':'cos','captain':False},
            'subject':{'type':'tool_call','target':'m','metadata':{}},
            'cost':{'model':'m','tokens_in':i,'tokens_out':i,'cost_raw_usd':0.0,'cost_marked_up_usd':0.0}})
res = checkpoint.emit_all()
dup_file = (pathlib.Path('${PUB}')/'opq-dup.json').exists()
print('x_skipped='+str('cab-x' not in res['published']),
      'y_skipped='+str('cab-y' not in res['published']),
      'no_dup_file='+str(not dup_file))
" 2>&1)"
assert_contains "colliding cab-x fail-closed skipped" "$COLL_OUT" "x_skipped=True"
assert_contains "colliding cab-y fail-closed skipped" "$COLL_OUT" "y_skipped=True"
assert_contains "no clobbered opq-dup file published" "$COLL_OUT" "no_dup_file=True"

# ── Summary ─────────────────────────────────────────────────────────────────────
printf '\n════════════════════════════════════\n'
printf '  PASS: %d   FAIL: %d   TOTAL: %d\n' "$PASS" "$FAIL" "$((PASS + FAIL))"
if [ "$FAIL" -gt 0 ]; then printf '\nFailed assertions:\n'; printf '%b' "$FAILURES"; printf '\n'; fi
printf '════════════════════════════════════\n'
[ "$FAIL" -eq 0 ]
