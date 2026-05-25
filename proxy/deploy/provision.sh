#!/usr/bin/env bash
# proxy/deploy/provision.sh — FW-121 refslund.ai backend provisioning (run on the Hetzner VPS).
#
# Idempotent + fail-closed. Installs Docker, creates the non-root audit user, lays out the
# bind-mounted audit dirs, validates secrets (presence-only — NEVER echoes values), applies the
# append-only attribute (AC#7), installs+enables the systemd reboot-survival unit, and brings the
# stack up. Spec basis: 050 L16 (Docker), 051 §Topology, 052 CTO#2/#3 + AC#7.
#
# USAGE (as root, from the deploy dir on the VPS):
#   sudo DEPLOY_DIR=/opt/refslund-backend ./provision.sh
# Prereqs the operator must place first (NOT created here — they carry secrets):
#   - .env                    (from the README "Environment" table; chmod 600)
#   - origin-certs/origin.pem + origin-certs/origin.key   (Cloudflare Origin CA, *.refslund.ai)
set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/opt/refslund-backend}"
AUDIT_UID=10001
ENV_FILE="$DEPLOY_DIR/.env"
CERT_DIR="$DEPLOY_DIR/origin-certs"
LOG_ROOT="$DEPLOY_DIR/data/logs"
REQUIRED_VARS="ANTHROPIC_API_KEY LITELLM_MASTER_KEY AUDIT_API_KEY"

log()  { printf '[provision] %s\n' "$*"; }
die()  { printf '[provision] FATAL: %s\n' "$*" >&2; exit 1; }

# ── 0. Preflight ──────────────────────────────────────────────────────────────
[ "$(id -u)" -eq 0 ] || die "must run as root (Docker install, useradd, chattr, systemd)."
[ -f "$DEPLOY_DIR/docker-compose.yml" ] || die "no docker-compose.yml in $DEPLOY_DIR — wrong DEPLOY_DIR?"
command -v curl >/dev/null 2>&1 || die "curl required."

# ── 1. Docker (engine + compose v2 plugin) ──────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  log "installing Docker via get.docker.com ..."
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
log "laying out $LOG_ROOT (audit SSOT + proxy-audit) ..."
mkdir -p "$LOG_ROOT/audit" "$LOG_ROOT/proxy-audit"
chown -R "$AUDIT_UID:$AUDIT_UID" "$LOG_ROOT"
chmod -R 0750 "$LOG_ROOT"

# ── 4. Secrets — validate PRESENCE only (never echo a value) ────────────────────
[ -f "$ENV_FILE" ] || die "$ENV_FILE missing — create it from the README Environment table (chmod 600)."
chmod 600 "$ENV_FILE"
# Load into this process env to presence-check; values are never printed (only missing NAMES).
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
chmod 600 "$CERT_DIR/origin.key" "$CERT_DIR/origin.pem"
chown root:root "$CERT_DIR/origin.key" "$CERT_DIR/origin.pem"

# ── 6. Append-only SSOT (AC#7 — SECONDARY defense; app-layer is PRIMARY, CTO#3) ─
# NOTE: the FW-100 erasure flow must `chattr -a` → pseudonymize → `chattr +a` under root, since
# pseudonymization rewrites blanked fields in place (append-only would otherwise block it).
if command -v chattr >/dev/null 2>&1; then
  if chattr +a "$LOG_ROOT/audit" 2>/dev/null; then
    log "append-only (chattr +a) set on $LOG_ROOT/audit"
  else
    log "WARN: chattr +a failed (non-ext4/overlay fs?) — app-layer append-only still enforced by the audit-server"
  fi
else
  log "WARN: chattr unavailable — app-layer append-only still enforced (CTO#3 primary)"
fi

# ── 7. systemd reboot-survival unit ─────────────────────────────────────────────
log "installing + enabling refslund-backend.service ..."
cp "$DEPLOY_DIR/refslund-backend.service" /etc/systemd/system/refslund-backend.service
systemctl daemon-reload
systemctl enable refslund-backend.service >/dev/null 2>&1 || true

# ── 8. Build + bring up via systemd ─────────────────────────────────────────────
log "building images ..."
( cd "$DEPLOY_DIR" && docker compose build )
log "starting stack via systemd ..."
systemctl restart refslund-backend.service

log "done. Verify: 'systemctl status refslund-backend', 'docker compose ps', and the Cloudflare"
log "origin health (proxy.refslund.ai/health/liveliness, audit.refslund.ai/health)."
