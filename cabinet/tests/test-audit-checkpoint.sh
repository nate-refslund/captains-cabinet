#!/usr/bin/env bash
# cabinet/tests/test-audit-checkpoint.sh — Spec 052 WORM checkpoint (Phase 1) regression harness.
#
# Covers checkpoint.py emit logic: empty-dir no-op, per-cabinet latest entry_hash + count + chain
# verify, tamper-surfacing (chain_valid=false), the non-slug SSOT-filename guard (#237 validator
# reuse), the UNSIGNED Phase-1 marker, and the APPEND-ONLY git mirror's immutable commit history.
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
PUB="${TMP}/checkpoints"; GIT="${TMP}/checkpoints-git"

py(){ LITELLM_AUDIT_LOG_ROOT="$ROOT" AUDIT_CHECKPOINT_DIR="$PUB" AUDIT_CHECKPOINT_GIT_DIR="$GIT" \
      PYTHONPATH="$AUDIT_SERVER" python3 "$@"; }

# ── 0. parse-clean ────────────────────────────────────────────────────────────
section "0. checkpoint.py parse-clean"
assert_eq "checkpoint.py parses" \
  "$(py -c "import ast; ast.parse(open('${AUDIT_SERVER}/checkpoint.py').read()); print('ok')" 2>&1)" "ok"

# ── 1. empty audit dir → no cabinets, snapshot still written (graceful, no git yet) ──
section "1. empty audit dir: no-op sweep + snapshot written"
EMPTY_OUT="$(py -c "
import json, pathlib, checkpoint
res = checkpoint.emit_all()
man = json.loads((pathlib.Path('${PUB}')/'latest.json').read_text())
print('cabinets='+str(res['cabinets']), 'manifest_n='+str(len(man['cabinets'])))
" 2>&1)"
assert_contains "empty dir → no cabinets" "$EMPTY_OUT" "cabinets=[]"
assert_contains "latest.json still written (empty manifest)" "$EMPTY_OUT" "manifest_n=0"

# ── 2. single valid cabinet → latest hash/count/valid + UNSIGNED Phase-1 marker ──
section "2. single valid cabinet checkpoint"
OUT="$(py -c "
import sys; sys.path.insert(0,'${AUDIT_SERVER}')
import json, pathlib, hashchain, checkpoint
for i in range(3):
    hashchain.append({'ts':'2026-01-01T00:00:0%dZ'%i,'cabinet_id':'good-cabinet','entry_id':'e%d'%i,
        'stream':'proxy','event_type':'llm_request','actor':{'officer':'cos','captain':False},
        'subject':{'type':'tool_call','target':'m','metadata':{}},
        'cost':{'model':'m','tokens_in':i,'tokens_out':i,'cost_raw_usd':0.0,'cost_marked_up_usd':0.0}})
res = checkpoint.emit_all()
last=''
for ln in (pathlib.Path('${ROOT}')/'audit'/'good-cabinet.jsonl').read_text().splitlines():
    if ln.strip(): last = json.loads(ln)['integrity']['entry_hash']
cp  = json.loads((pathlib.Path('${PUB}')/'good-cabinet.json').read_text())
man = json.loads((pathlib.Path('${PUB}')/'latest.json').read_text())
print('cabinets='+','.join(res['cabinets']), 'broken='+str(res['broken']),
      'count='+str(cp['entry_count']), 'valid='+str(cp['chain_valid']),
      'hashmatch='+str(cp['latest_entry_hash']==last),
      'in_manifest='+str(any(c['cabinet_id']=='good-cabinet' for c in man['cabinets'])),
      'signed='+str(cp['signed']), 'phase='+str(cp['phase']))
" 2>&1)"
assert_contains "good-cabinet checkpointed"            "$OUT" "cabinets=good-cabinet"
assert_contains "no broken chains"                     "$OUT" "broken=[]"
assert_contains "entry_count=3"                        "$OUT" "count=3"
assert_contains "chain_valid=True"                     "$OUT" "valid=True"
assert_contains "latest_entry_hash matches SSOT tail"  "$OUT" "hashmatch=True"
assert_contains "cabinet present in latest.json"       "$OUT" "in_manifest=True"
assert_contains "checkpoint UNSIGNED (Phase 1)"        "$OUT" "signed=False"
assert_contains "phase=1"                              "$OUT" "phase=1"

# ── 3. tamper detection surfaced (chain_valid=false + in broken[]) ──
section "3. tampered chain surfaced as broken"
TAMP_OUT="$(py -c "
import sys; sys.path.insert(0,'${AUDIT_SERVER}')
import json, pathlib, hashchain, checkpoint
for i in range(2):
    hashchain.append({'ts':'2026-01-01T00:00:0%dZ'%i,'cabinet_id':'tamper-cabinet','entry_id':'t%d'%i,
        'stream':'proxy','event_type':'llm_request','actor':{'officer':'cos','captain':False},
        'subject':{'type':'tool_call','target':'m','metadata':{}},
        'cost':{'model':'m','tokens_in':i,'tokens_out':i,'cost_raw_usd':0.0,'cost_marked_up_usd':0.0}})
p = pathlib.Path('${ROOT}')/'audit'/'tamper-cabinet.jsonl'
lines = p.read_text().splitlines()
e0 = json.loads(lines[0]); e0['cost']['tokens_in'] = 9999; lines[0] = json.dumps(e0)  # tamper
p.write_text(chr(10).join(lines)+chr(10))
res = checkpoint.emit_all()
cp = json.loads((pathlib.Path('${PUB}')/'tamper-cabinet.json').read_text())
print('valid='+str(cp['chain_valid']), 'in_broken='+str('tamper-cabinet' in res['broken']))
" 2>&1)"
assert_contains "tampered chain → chain_valid=False" "$TAMP_OUT" "valid=False"
assert_contains "tampered cabinet listed in broken[]" "$TAMP_OUT" "in_broken=True"

# ── 4. non-slug SSOT filename skipped (reuses #237 is_valid_cabinet_id) ──
section "4. non-slug SSOT filename skipped"
NS_OUT="$(py -c "
import sys; sys.path.insert(0,'${AUDIT_SERVER}')
import json, pathlib, checkpoint
# A populated file whose STEM is not a slug (uppercase) — must be skipped by the slug guard,
# NOT merely by emptiness (it has a real entry_hash, so emptiness is not the reason).
bad = pathlib.Path('${ROOT}')/'audit'/'BAD-Cabinet.jsonl'
bad.write_text(json.dumps({'cabinet_id':'BAD-Cabinet','integrity':{'entry_hash':'deadbeef'}})+chr(10))
res = checkpoint.emit_all()
skipped = 'BAD-Cabinet' not in res['cabinets']
no_json = not (pathlib.Path('${PUB}')/'BAD-Cabinet.json').exists()
print('skipped='+str(skipped), 'no_json='+str(no_json))
" 2>&1)"
assert_contains "non-slug filename not checkpointed" "$NS_OUT" "skipped=True"
assert_contains "no checkpoint json for non-slug"    "$NS_OUT" "no_json=True"

# ── 5. git mirror: APPEND-ONLY immutable ledger + a commit per checkpoint ──
section "5. git mirror append-only + commit per checkpoint"
GIT_OUT="$(py -c "
import sys; sys.path.insert(0,'${AUDIT_SERVER}')
import subprocess, json, pathlib, hashchain, checkpoint
G='${GIT}'
subprocess.run(['git','init','-q',G], check=True)
for i in range(2):
    hashchain.append({'ts':'2026-02-01T00:00:0%dZ'%i,'cabinet_id':'git-cabinet','entry_id':'g%d'%i,
        'stream':'proxy','event_type':'llm_request','actor':{'officer':'cos','captain':False},
        'subject':{'type':'tool_call','target':'m','metadata':{}},
        'cost':{'model':'m','tokens_in':i,'tokens_out':i,'cost_raw_usd':0.0,'cost_marked_up_usd':0.0}})
checkpoint.emit_all()
c1 = int(subprocess.run(['git','-C',G,'rev-list','--count','HEAD'],capture_output=True,text=True).stdout.strip())
ledger = pathlib.Path(G)/'git-cabinet.checkpoints.jsonl'
l1 = len(ledger.read_text().splitlines())
hashchain.append({'ts':'2026-02-01T00:00:09Z','cabinet_id':'git-cabinet','entry_id':'g2',
    'stream':'proxy','event_type':'llm_request','actor':{'officer':'cos','captain':False},
    'subject':{'type':'tool_call','target':'m','metadata':{}},
    'cost':{'model':'m','tokens_in':9,'tokens_out':9,'cost_raw_usd':0.0,'cost_marked_up_usd':0.0}})
checkpoint.emit_all()
c2 = int(subprocess.run(['git','-C',G,'rev-list','--count','HEAD'],capture_output=True,text=True).stdout.strip())
lines = ledger.read_text().splitlines()
counts = [json.loads(x)['entry_count'] for x in lines if json.loads(x)['cabinet_id']=='git-cabinet']
# unsigned: HEAD has no PGP signature line
sig = subprocess.run(['git','-C',G,'log','-1','--format=%G?'],capture_output=True,text=True).stdout.strip()
print('c1='+str(c1),'c2='+str(c2),'l1='+str(l1),'l2='+str(len(lines)),
      'counts='+str(counts),'sig='+sig)
" 2>&1)"
assert_contains "first checkpoint commits to git mirror"        "$GIT_OUT" "c1=1"
assert_contains "second checkpoint adds a commit"               "$GIT_OUT" "c2=2"
assert_contains "ledger 1 line after first checkpoint"          "$GIT_OUT" "l1=1"
assert_contains "ledger APPENDS (progression captured: 2 → 3)"  "$GIT_OUT" "counts=[2, 3]"
assert_contains "commit is UNSIGNED (Phase 1, %G? = N)"          "$GIT_OUT" "sig=N"

# ── 6. empty-commit path is benign: no false 'commit failed', no spurious commit (MEDIUM fix) ──
section "6. empty-commit path benign (stdout 'nothing to commit' not misread as failure)"
EC_OUT="$(py -c "
import sys; sys.path.insert(0,'${AUDIT_SERVER}')
import io, glob, os, logging, subprocess, pathlib, checkpoint
G='${GIT}'
before = int(subprocess.run(['git','-C',G,'rev-list','--count','HEAD'],capture_output=True,text=True).stdout.strip())
buf = io.StringIO(); h = logging.StreamHandler(buf)
lg = logging.getLogger('checkpoint'); lg.addHandler(h); lg.setLevel(logging.INFO)
# Remove every SSOT file -> 0 cabinets -> git add -A stages nothing -> 'nothing to commit' (STDOUT).
for f in glob.glob(str(pathlib.Path('${ROOT}')/'audit'/'*.jsonl')): os.remove(f)
checkpoint.emit_all()
after = int(subprocess.run(['git','-C',G,'rev-list','--count','HEAD'],capture_output=True,text=True).stdout.strip())
log = buf.getvalue()
print('no_new_commit='+str(after==before),
      'no_false_warning='+str('commit failed' not in log),
      'noop_info='+str('unchanged since last checkpoint' in log))
" 2>&1)"
assert_contains "empty-commit creates no spurious commit"        "$EC_OUT" "no_new_commit=True"
assert_contains "empty-commit logs NO false 'commit failed'"     "$EC_OUT" "no_false_warning=True"
assert_contains "empty-commit logged as benign no-op (info)"     "$EC_OUT" "noop_info=True"

# ── Summary ─────────────────────────────────────────────────────────────────────
printf '\n════════════════════════════════════\n'
printf '  PASS: %d   FAIL: %d   TOTAL: %d\n' "$PASS" "$FAIL" "$((PASS + FAIL))"
if [ "$FAIL" -gt 0 ]; then printf '\nFailed assertions:\n'; printf '%b' "$FAILURES"; printf '\n'; fi
printf '════════════════════════════════════\n'
[ "$FAIL" -eq 0 ]
