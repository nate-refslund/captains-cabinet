#!/usr/bin/env bash
# proxy/deploy/provision.sh — FW-121 refslund.ai backend provisioning (run on the Hetzner VPS).
#
# Idempotent + fail-closed. Installs Docker, creates the non-root audit user, lays out the
# bind-mounted audit dirs, validates secrets (presence-only — NEVER echoes values), installs an
# append-only cron (AC#7), templates+installs the systemd reboot-survival unit, and brings the
# stack up. Spec basis: 050 L16 (Docker), 051 §Topology, 052 CTO#2/#3 + AC#7.
#
# DEPLOY_DIR defaults to THIS script's own dir (the compose dir, proxy/deploy/) so its paths can
# never drift from the compose's relative paths (resolves the H2 layout contradiction). Canonical
# on-VPS location: /opt/refslund-backend/proxy/deploy (clone the repo to /opt/refslund-backend).
#
# USAGE (as root, from the deploy dir):  sudo ./provision.sh
# Operator prereqs (NOT created here — they carry secrets, kept under DEPLOY_DIR):
#   - .env                       (from the README Environment table; chmod 600)
#   - origin-certs/origin.pem + origin-certs/origin.key   (Cloudflare Origin CA, *.refslund.ai)
set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
AUDIT_UID=10001
ENV_FILE="$DEPLOY_DIR/.env"
CERT_DIR="$DEPLOY_DIR/origin-certs"
LOG_ROOT="$DEPLOY_DIR/data/logs"
UNIT_SRC="$DEPLOY_DIR/refslund-backend.service"
UNIT_DST="/etc/systemd/system/refslund-backend.service"
CRON_FILE="/etc/cron.d/refslund-audit-append-only"
REQUIRED_VARS="ANTHROPIC_API_KEY LITELLM_MASTER_KEY AUDIT_API_KEY REDIS_PASSWORD"

log() { printf '[provision] %s\n' "$*"; }
die() { printf '[provision] FATAL: %s\n' "$*" >&2; exit 1; }

# ── 0. Preflight ──────────────────────────────────────────────────────────────
[ "$(id -u)" -eq 0 ] || die "must run as root (Docker install, useradd, chattr cron, systemd)."
[ -f "$DEPLOY_DIR/docker-compose.yml" ] || die "no docker-compose.yml in $DEPLOY_DIR — run from proxy/deploy/."
[ -f "$DEPLOY_DIR/../config.yaml" ]      || die "../config.yaml not reachable — proxy/ subtree layout wrong."
command -v curl >/dev/null 2>&1 || die "curl required."

# ── 1. Docker (engine + compose v2 plugin) ──────────────────────────────────────
# M4 (tracked hardening): the get.docker.com convenience script is an unpinned root pipe-to-shell.
# Phase-1 acceptable; the follow-up is the distro apt repo with a GPG-verified pinned docker-ce.
if ! command -v docker >/dev/null 2>&1; then
  log "installing Docker via get.docker.com (see M4 hardening note) ..."
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null 2>&1 || true
docker compose version >/dev/null 2>&1 || die "docker compose v2 plugin missing after install."

# ── 2. Non-root audit user (uid must match the Dockerfile's audit uid) ──────────
if ! id -u audit >/dev/null 2>&1; then
  log "creating non-root audit user (uid $AUDIT_UID) ..."
  groupadd -r -g "$AUDIT_UID" audit 2>/dev/null || true
  useradd  -r -u "$AUDIT_UID" -g "$AUDIT_UID" -s /usr/sbin/nologin audit 2>/dev/null || true
fi

# ── 3. Audit dirs (bind-mounted into the containers) ────────────────────────────
# .cursors lives UNDER audit/ (FW-097 ingest.py) and takes TRUNCATING writes, so it must never be
# append-only — the append-only cron (step 6) targets audit/*.jsonl FILES only, never the dir/.cursors.
log "laying out $LOG_ROOT (audit SSOT + proxy-audit) ..."
mkdir -p "$LOG_ROOT/audit/.cursors" "$LOG_ROOT/proxy-audit" \
         "$LOG_ROOT/checkpoints" "$LOG_ROOT/checkpoints-git"   # WORM checkpoint served-dir + git mirror (Spec 052)
chown -R "$AUDIT_UID:$AUDIT_UID" "$LOG_ROOT"
chmod -R 0750 "$LOG_ROOT"
# The checkpoint sidecar (runs as audit) git-inits checkpoints-git + wires the public 'origin'
# remote from AUDIT_CHECKPOINT_REMOTE on first start — no root/su git needed here.

# ── 4. Secrets — validate PRESENCE only (never echo a value) ────────────────────
[ -f "$ENV_FILE" ] || die "$ENV_FILE missing — create it from the README Environment table (chmod 600)."
chmod 600 "$ENV_FILE"
set -a; # shellcheck disable=SC1090
. "$ENV_FILE"; set +a
missing=""
for v in $REQUIRED_VARS; do
  [ -n "${!v:-}" ] || missing="$missing $v"
done
[ -z "$missing" ] || die "required env var(s) empty in $ENV_FILE:$missing"
log "secrets present (values not displayed)."

# ── 5. Cloudflare Origin CA cert (Full-strict origin leg) ───────────────────────
if [ ! -s "$CERT_DIR/origin.pem" ] || [ ! -s "$CERT_DIR/origin.key" ]; then
  die "Cloudflare Origin cert missing: place origin.pem + origin.key in $CERT_DIR
       (Cloudflare dashboard → SSL/TLS → Origin Server → Create Certificate, host *.refslund.ai)."
fi
chown root:root "$CERT_DIR/origin.key" "$CERT_DIR/origin.pem"
chmod 600 "$CERT_DIR/origin.key" "$CERT_DIR/origin.pem"

# ── 6. Append-only SSOT (AC#7 — SECONDARY; app-layer is PRIMARY, CTO#3) ─────────
# H3 fix: chattr +a per-FILE on audit/*.jsonl via a root cron — NOT on the audit/ directory.
# Dir-level +a blocks new-cabinet file creation + the .cursors truncating writes; per-file +a makes
# each existing SSOT log append-only while leaving the dir + .cursors writable. New files get +a on
# the next cron tick (<=5min unprotected window; the app-layer append-only is the PRIMARY guard).
# NOTE: the FW-100 erasure flow must chattr -a → pseudonymize → chattr +a under root.
log "installing append-only cron ($CRON_FILE) ..."
cat > "$CRON_FILE" <<CRONEOF
# FW-121 AC#7 append-only (SECONDARY defense; app-layer PRIMARY per CTO#3). Marks each audit SSOT
# *.jsonl file append-only every 5 min. NOT the audit/ dir (would block new-cabinet creation) and
# NOT .cursors (truncating writes). Append-mode writers (hashchain.append) are unaffected by +a.
*/5 * * * * root /usr/bin/find $LOG_ROOT/audit -maxdepth 1 -type f -name '*.jsonl' -exec chattr +a {} + 2>/dev/null
CRONEOF
chmod 644 "$CRON_FILE"
# run once now for any pre-existing files
if command -v chattr >/dev/null 2>&1; then
  find "$LOG_ROOT/audit" -maxdepth 1 -type f -name '*.jsonl' -exec chattr +a {} + 2>/dev/null \
    && log "append-only applied to existing audit/*.jsonl" \
    || log "WARN: chattr +a failed (non-ext4/overlay?) — app-layer append-only still enforced (CTO#3)"
else
  log "WARN: chattr unavailable — app-layer append-only still enforced (CTO#3 primary)"
fi

# ── 7. systemd reboot-survival unit (template the compose dir → no hardcoded-path drift, H2) ─
log "installing + enabling refslund-backend.service (compose dir = $DEPLOY_DIR) ..."
[ -f "$UNIT_SRC" ] || die "$UNIT_SRC missing."
sed "s#__COMPOSE_DIR__#$DEPLOY_DIR#g" "$UNIT_SRC" > "$UNIT_DST"
systemctl daemon-reload
systemctl enable refslund-backend.service >/dev/null 2>&1 || true

# ── 8. Build + bring up via systemd ─────────────────────────────────────────────
log "building images ..."
( cd "$DEPLOY_DIR" && docker compose build )
log "starting stack via systemd ..."
systemctl restart refslund-backend.service

log "done. Verify: 'systemctl status refslund-backend', 'docker compose ps' (from $DEPLOY_DIR),"
log "and the Cloudflare origin health (proxy.refslund.ai/health/liveliness, audit.refslund.ai/health)."
