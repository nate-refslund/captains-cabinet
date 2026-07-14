# Germline amendment — enforcement-backbone fixes (2026-07-14)

Amendment doc (germline etiquette: a CG-class germline change carries an amendment
doc under docs/proposals/) for the six enforcement fixes landing on master ahead of
the supervised unlock ceremony (CEREMONY-RUNBOOK-2026-07-14.md in cabinet-meta).
Provenance: the Opus enforcement re-audit (designs/enforcement-reaudit-2026-07-14.md)
+ the 2026-07-14 foundation bug-hunt. Captain-authorized 2026-07-14 (incl. cua grant
+ the P3 hardening).

## The six fixes (all in germline schg files; verified apply-clean + golden 26/26)
1. **B (cache-poison, P1 — CT-1/MCP-1/CT-3/CT-4):** pre-tool-use.sh — the four
   fixed-path + mtime-`-nt` /tmp caches (§9 MCP-scope, §10 peers-trust, spend/
   telegram-whitelist, slug) become unpredictable per-invocation mktemp files
   (write→read→unlink), so a same-uid officer can neither pre-plant nor race them
   to self-grant scope. Both authority gates fail CLOSED on build failure.
2. **G1 (symlink traversal, P1, NEW):** pre-tool-use.sh §5 — add os.path.realpath
   resolution before the germline membership test, fail-closed on unresolvable, so
   a symlinked directory component can no longer reach the schg-EXEMPT
   captain-vetoes.yml (self-un-demotion). Residual: §5b/§5c Bash-redirect variant
   tracked separately.
3. **Redaction misses (P2):** post-tool-use.sh — two perl rules add the `bot<token>`
   Telegram API-URL form + `scheme://user:PASS@host` URL-userinfo credentials
   (Neon/Upstash) to the redaction pass; password span only, host stays legible.
4. **pre-captain-dm portability (P2, memory-learning-6):** portable `_now_ms` +
   BSD-first `stat -f` so the voice cache + cost log work on macOS.
5. **cua scope grant (P2, mcp-config-1):** mcp-scope.yml — grant cua + cua-driver in
   the §9 scope for `cos` (the sole drives_computer holder) so computer-use calls
   are no longer blocked call-time. Captain-authorized.
6. **P3 outage default-DENY:** pre-tool-use.sh — the unreachable-Redis branch
   becomes default-DENY (explicit read/observe allowlist + WebFetch/WebSearch added
   to the deny set + a `*)` fail-closed arm), so empty/unknown TOOL_NAME + native
   egress no longer fall open during a control-plane outage. Captain-authorized.

## CG ledger
CG-class germline amendment; land the ledger row on the next ledger pass (A13
parity). These fixes reach master here; they become LIVE only when the ceremony
syncs the schg-locked live hook files to master + relocks.

## Verification (on the applied tree, origin/master + all 6)
golden-eval suite 26/26; germline-readonly.sh 61/0 (incl. G1 gate); FW adversary
fw042 86/0, fw051 pass, fw056 29/0, fw044 61/0; bash -n clean on all 3 hooks; each
diff git-apply-clean independently.
