#!/usr/bin/env bash
# proxy/deploy/ingest-loop.sh — FW-121: periodic FW-097 ingest sidecar loop.
#
# Runs ingest.py (transforms the FW-096 proxy-audit JSONL stream → the Spec 052 hash-chained
# SSOT under audit/) every INGEST_INTERVAL seconds. ingest_all() already catches per-slug errors,
# so one bad cycle never aborts the loop; the outer `|| echo` is belt-and-suspenders.
set -u

cd /app/audit-server || { echo "[ingest-loop] FATAL: /app/audit-server missing" >&2; exit 1; }
INTERVAL="${INGEST_INTERVAL:-60}"
echo "[ingest-loop] start; interval=${INTERVAL}s root=${LITELLM_AUDIT_LOG_ROOT:-<default>}"

while true; do
  python ingest.py || echo "[ingest-loop] cycle error (continuing)" >&2
  sleep "$INTERVAL"
done
