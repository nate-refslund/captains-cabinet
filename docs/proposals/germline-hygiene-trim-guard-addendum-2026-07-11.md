# Germline amendment (staged dark) — consumption-aware trim guard in framework/attention/hygiene.py

**Date:** 2026-07-11 · **Author:** hardening loop (orchestrator, per the
2026-07-07 full-autonomy grant; design option (b) self-ratified, provenance
in captain-decisions 2026-07-11) · **Ledger row:** CG-23 · **Target:**
`framework/attention/hygiene.py` `trim_forwarded_streams` (schg-locked,
germline-lock.sh:69) · **Ceremony:** rides the HANDBACK #10 unlock window
(with the kill-switch fail-closed fix and the posture/trust-ladder relock).

## Why

2026-07-11 investigation (drain-fix, wf_6f12918e-04d + the preceding
diagnosis agent): H2's XDEL-on-forward (042e94a8) deletes stream entries
for ALL consumer groups, starving the live `ceo-reader-<project>` plane
(created at push, captain-attention.sh:97,140; consumed by post-tool-use.sh
§3b in single_ceo mode — the portfolio preset). The non-germline half (the
drainer's two XDEL call sites) is guarded on master; this amendment closes
the remaining group-blind XDEL in the 300s hygiene sweeper. Until it lands,
the CEO-plane contract remains breakable on the sweeper path — known,
recorded, accepted for the interim.

## Verification already performed (shadow tree, not the live file)

Diff applies cleanly (`patch -p1` --check); compiles; framework/attention +
framework/frontdoor suites green WITH the patch under both redis-py and CLI
backends (1225 passed, 1 pre-existing env skip); functional probe on real
Redis: live-PEL entry NOT trimmed, delivered+ACKed trimmed, vestigial group
does not block, probe-error path skips (fail safe).

## Known residual (explicitly NOT covered here)

`hygiene.supersede_stream_entry` (H4 path, hygiene.py:296-334) still XDELs
the SUPERSEDED entry group-blind. Supersede forwards replacement content by
design, but a live CEO PEL copy of the superseded card is destroyed.
Tracked as its own backlog row; needs its own ruling (may be
working-as-intended for supersede semantics).

## The staged diff (verbatim; also at the ceremony operator's copy)

```diff
--- a/framework/attention/hygiene.py
+++ b/framework/attention/hygiene.py
@@ -236,7 +236,19 @@
     """XDEL captain-attention stream entries already forwarded to the intake
     (H2: forwarded items live on in the intake/briefing — the stream copy is
     queue growth). Uses the drain's own forwarded-marker set, so an entry is
-    only trimmed once its content provably reached the front door."""
+    only trimmed once its content provably reached the front door.
+
+    Consumption-aware (2026-07-11 finding): forwarded is necessary but NOT
+    sufficient — captain-attention.sh creates ``ceo-reader-<project>`` at
+    push time (:97,140) and post-tool-use.sh §3b (:292-322) consumes it in
+    single_ceo mode, so a LIVE consumer group may still be owed the entry.
+    Every XDEL is therefore gated on ``ad._safe_to_trim`` (the same guard
+    as the drain's own call sites): a live group still owes the entry
+    (beyond its last-delivered-id under numeric (ms,seq) compare, or in its
+    PEL) → skip; never-read groups are vestigial and never block (the
+    stranded-card cleanup survives); probe errors skip the entry (fail
+    safe — it retries on the next 300s sweep). The CEO-plane delivery
+    contract outranks queue growth."""
     from framework.frontdoor import attention_drain as ad
 
     if backend is None:
@@ -270,6 +282,11 @@
             try:
                 if not ad._already_forwarded(backend, marker):
                     continue
+                # Consumption-aware guard (2026-07-11): never XDEL an entry
+                # another LIVE consumer group (ceo-reader-<project>) still
+                # owes. Guard-no / probe error → leave it for the next sweep.
+                if not ad._safe_to_trim(backend, stream, entry_id):
+                    continue
                 if ad._is_redispy(backend):
                     backend._c.xdel(stream, entry_id)
                 else:

```
