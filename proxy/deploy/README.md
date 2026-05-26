# FW-121 — refslund.ai backend deploy stack

Net-new deploy automation for the refslund.ai SaaS backend (LiteLLM proxy + the FW-097 audit substrate). Runs on a **Hetzner Frankfurt EU-resident VPS** (captain-decisions 2026-05-25 — GDPR EU-residency, no US-parent) behind **Cloudflare**. Spec basis: **Spec 050 L16** (Docker baseline), **Spec 051 §Topology**, **Spec 052 CTO#2/#3 + AC#7**.

> **Status: deploy-gated.** Buildable + reviewable now; *validates* at VPS-provision (**#191**, Captain founder-action). Nothing is live until the VPS exists. Hardened against 1 Opus deploy-security round (3 HIGH folded — see "Security review").

## Architecture

```
officer cabinets ─┐                         Cloudflare (public TLS)
                  │  https://proxy.refslund.ai/v1   │   https://audit.refslund.ai
                  └──────────────► Cloudflare ──────┴──────────► Hetzner VPS origin :443
                                                                       │ (Caddy, Full-strict origin cert)
                                                      ┌────────────────┼─────────────────┐
                                                      ▼                                  ▼
                                              litellm:4000 (FW-096)            audit-server:8000 (FW-097)
                                                      │  writes proxy-audit/             │ reads+APPENDS audit/
                                                      ▼                                  ▼
                                                redis:6379 (cap-state)     ingest (loop): proxy-audit/ → audit/ SSOT
```

| Service | Image | Role |
|---|---|---|
| `litellm` | `ghcr.io/berriai/litellm:main-stable` (⚠ pin digest at deploy) | proxy.refslund.ai/v1; cap + margin; FW-096 audit callback |
| `audit-server` | built (`Dockerfile.audit-server`) | FW-097 GDPR audit log; POST `/proxy/audit/log` + GET `/dashboard/audit/...`; **non-root** uid 10001 |
| `ingest` | same image, loop cmd | FW-096 proxy-audit → Spec 052 hash-chained SSOT, every `INGEST_INTERVAL`s |
| `redis` | `redis:7.4-alpine` | per-cabinet daily-cap state (auth-required, survives restart) |
| `caddy` | `caddy:2.8-alpine` | LOCAL origin reverse-proxy (Cloudflare owns public TLS; `auto_https off`) |

All services: `restart: unless-stopped`, `no-new-privileges`, `cap_drop: ALL` (caddy keeps only `NET_BIND_SERVICE`), bounded json-file logging.

## Canonical layout (on the VPS)

The compose runs from `proxy/deploy/`; provision.sh + the systemd unit both resolve to that same dir, so paths never drift. Clone the repo to `/opt/refslund-backend`:

```
/opt/refslund-backend/proxy/
  config.yaml  audit_logger.py  audit-server/  .dockerignore
  deploy/                         ← DEPLOY_DIR (compose runs here; provision.sh + systemd target it)
    docker-compose.yml  Caddyfile  Dockerfile.audit-server  provision.sh  …
    .env                          ← operator-created (chmod 600)
    origin-certs/origin.{pem,key} ← operator-placed (Cloudflare Origin CA)
    data/logs/{audit,proxy-audit} ← provision.sh (bind mount, append-only cron)
```

**Secret isolation (H1):** litellm mounts ONLY `../config.yaml` + `../audit_logger.py` (the 2 files its callback needs) — never the whole `proxy/` tree — so `.env` / `origin-certs/` are unreadable inside the litellm container. `proxy/.dockerignore` keeps them (and `*.pem`/`*.key`/`data/`) out of the audit-server build context too.

## Environment (`.env`, chmod 600 — operator-created, presence-validated by provision.sh)

| Var | Req | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | server-side provider key — NEVER leaves refslund.ai |
| `LITELLM_MASTER_KEY` | ✅ | proxy admin API (mints/rotates per-cabinet virtual keys) |
| `AUDIT_API_KEY` | ✅ | FW-097 audit-server Bearer auth; distinct from `LLM_PROXY_KEY` (CTO#5) |
| `REDIS_PASSWORD` | ✅ | redis `requirepass` (cap-state auth, L1); litellm redis client must use it |
| `LITELLM_MARGIN_PCT` | — | markup % (default 100 = 2×). **Private value.** |
| `LITELLM_CAP_USD` | — | per-cabinet daily cap (default 50.0; must match `config.yaml`) |
| `DATABASE_URL` | — | optional Postgres for LiteLLM key/team storage |
| `INGEST_INTERVAL` | — | seconds between ingest cycles (default 60) |
| `AUDIT_CHECKPOINT_REMOTE` | — | **WORM public mirror** push URL w/ deploy token (e.g. `https://x-access-token:TOKEN@github.com/ORG/refslund-cabinet-checkpoints.git`). Empty/unset → checkpoints commit LOCALLY only (the off-box anchor is inert until set). Founder-action: create the **public** repo + a write-scoped deploy token. |

> `REDIS_HOST`/`REDIS_PORT` are set in `docker-compose.yml` (internal) — do **not** put them in `.env`.

## Deploy runbook (on the VPS, as root)

1. Clone the repo to `/opt/refslund-backend` (so the deploy dir is `/opt/refslund-backend/proxy/deploy`).
2. `cd /opt/refslund-backend/proxy/deploy`; create `.env` from the table above (`chmod 600`).
3. Place the **Cloudflare Origin CA** cert at `origin-certs/origin.{pem,key}` (dashboard → SSL/TLS → Origin Server, host `*.refslund.ai`). Set Cloudflare SSL mode to **Full (strict)**.
4. `sudo ./provision.sh` — installs Docker, creates the non-root `audit` user, lays out `data/logs`, installs the append-only cron, templates+enables the systemd unit, builds, starts.
5. Verify: `systemctl status refslund-backend`, `docker compose ps` (from the deploy dir), and the Cloudflare-fronted health endpoints (`proxy.refslund.ai/health/liveliness`, `audit.refslund.ai/health`).

## Security notes

- **Non-root audit-server (CTO#3):** runs as `audit` (uid 10001) via the Dockerfile `USER` + compose `user:`; app-layer append-only is PRIMARY.
- **Append-only (AC#7, H3):** a root cron (`/etc/cron.d/refslund-audit-append-only`) marks each `audit/*.jsonl` SSOT file `chattr +a` every 5 min — **NOT** the directory (dir-`+a` would block new-cabinet file creation) and **NOT** `.cursors/` (truncating writes). Append-mode writers (`hashchain.append`) are unaffected. New files have a ≤5-min unprotected window covered by the app-layer guard. **FW-100 erasure** must `chattr -a` → pseudonymize → `chattr +a` under root. Likewise, any host-side relocation/cleanup of `audit/*.jsonl` needs `chattr -a` first, and **decommissioning** must remove `/etc/cron.d/refslund-audit-append-only` (it re-applies `+a` every 5 min otherwise).
- **Secret handling:** `.env` chmod 600; `provision.sh` presence-checks only (never prints values); origin key `chmod 600 root:root`; secret isolation from the litellm container per "Secret isolation (H1)" above.
- **Network:** only Caddy publishes `:80/:443`; litellm/audit-server/redis are `expose:`-only (intra-bridge). Redis requires `REDIS_PASSWORD` (L1). All services drop caps + `no-new-privileges`.
- **Audit log root wiring:** litellm reads `LITELLM_AUDIT_LOG_ROOT` as the proxy-audit dir; audit-server/ingest read it as the parent — both into the same bind-mounted `./data/logs` (FW-096 vs FW-097 conventions).

## WORM off-box checkpoint (Spec 052 CTO#4/#7, AC#13)

The `checkpoint` sidecar runs `checkpoint-loop.sh` daily at **00:05 UTC** (non-root `audit` user, same image as audit-server): it reads each cabinet's SSOT and publishes the latest per-cabinet `entry_hash` + count + chain-validity to two sinks, **keyed by an OPAQUE per-cabinet id — never the slug** (AC#13):
- **Served snapshot** at `data/logs/checkpoints/` → Caddy file_servers it read-only at **`https://refslund.ai/audit-checkpoints/`** (`latest.json` + per-`opaque-id.json`). A customer/auditor matches their browser-recomputed hash against it.
- **Append-only git mirror** at `data/logs/checkpoints-git/` → pushed to the **public, immutable** `refslund-cabinet-checkpoints` repo (the off-box tamper anchor). **Phase-1 commits are UNSIGNED** (CTO#7; Phase-2 adds offline Captain PGP — the VPS never holds the key).

**Same-filesystem constraint (CPO PR-2 item 1 — do NOT violate):** the served dir, its `.checkpoint-scratch` sibling, and the git mirror all live under the single `./data/logs` bind-mount so the atomic-write `os.replace` stays atomic. If you ever mount `AUDIT_CHECKPOINT_DIR` on its OWN volume (separate fs from its parent), `os.replace` becomes cross-device and `checkpoint.py` **fails LOUD** (logged `EXDEV` error, no torn write) rather than silently corrupting — the fix is to keep them co-located. Do not split the volume.

**FAIL-CLOSED privacy (AC#13):** a cabinet is published ONLY if the FW-098 install wrote its slug→opaque-id mapping to `data/logs/cabinet-id-map.json` (JSON `{slug: opaque-hex}`); an unmapped / malformed / identity (`opaque==slug`) entry is SKIPPED — a bare slug is **never** published to the permanent public sink.

**Founder-action (blocks the public push, NOT the build/deploy):** create the **public** GitHub repo `refslund-cabinet-checkpoints` + a write-scoped deploy token, then set `AUDIT_CHECKPOINT_REMOTE` in `.env`. Until then the sidecar commits the mirror LOCALLY only; the served snapshot still publishes via Caddy.

## Erasure runbook (GDPR Art 17) — exact invocation for THIS deploy

The SSOT lives at `<DEPLOY_DIR>/data/logs/audit/<slug>.jsonl` (e.g. `/opt/refslund-backend/proxy/deploy/data/logs/audit/`). `customer-erasure.sh` DEFAULTS to the dev path (`/opt/founders-cabinet/proxy/logs`), so you **MUST** pass this deploy's paths — otherwise it runs against an EMPTY dir and writes a `status: completed` receipt while the real PII-bearing SSOT is untouched (a **silent Art-17 false-success**). Run as root (for the `chattr -a`→pseudonymize→`chattr +a` cycle):

```
sudo CABINET_ROOT=/opt/refslund-backend \
     LITELLM_AUDIT_LOG_ROOT=/opt/refslund-backend/proxy/deploy/data/logs \
     bash /opt/refslund-backend/cabinet/scripts/customer-erasure.sh <slug> --confirm
```

Verify the receipt's `status: completed` corresponds to a non-empty `processed` count AND that the hash-chain re-verifies post-pseudonymization. (M-DPO-1, DPO-substitute pass.)

## Deploy-time checklist (do NOT skip)

- [ ] **Pin the LiteLLM image to a `@sha256` digest** after confirming `config.yaml` parses against that version (M3; redis/caddy/python already pinned). Re-pin `requirements.txt` to a hash-lockfile after first build.
- [ ] Confirm the LiteLLM Redis client uses `REDIS_PASSWORD` + the budget↔redis wiring survives restart for the pinned version.
- [ ] **HARD GATE — set `config.yaml log_requests: false` before the pilot** (M-DPO-2; `config.yaml` is FW-096/CPO scope → flag CPO to confirm, do NOT silently flip in the deploy PR). With it ON, LiteLLM can persist customer prompt content (PII) to litellm stdout → the docker json-log, OUTSIDE the erasure-governed SSOT — breaking **Art 5(1)(c)** minimization AND **Art 17** erasure (`customer-erasure.sh` only touches `audit/*.jsonl`, never the docker log). The compose `logging:` caps bound DISK (Art 5(1)(e)) but NOT minimization/erasure-coverage. The FW-096 audit callback gets usage metadata independently of this flag, so `false` is the safe default. If kept ON, the docker json-log path MUST be added to the erasure runbook + proven body-free for the pinned litellm version.
- [ ] Cloudflare SSL = **Full (strict)**; Origin cert covers `*.refslund.ai`.
- [ ] `AUDIT_LOG_ENDPOINT` on customer cabinets points at `https://audit.refslund.ai/proxy/audit/log`.
- [ ] **WORM checkpoint (Spec 052):** create the public `refslund-cabinet-checkpoints` repo + a write-scoped deploy token; set `AUDIT_CHECKPOINT_REMOTE` in `.env`. After first run, confirm `https://refslund.ai/audit-checkpoints/latest.json` serves opaque-keyed JSON AND — once a cabinet has logged — that `cabinets[]` is **non-empty** with every `cabinet_public_id` **≠ its slug** (a missing/misconfigured `cabinet-id-map.json` otherwise leaves the anchor silently inert: fail-closed publishes nothing rather than a slug). Confirm the daily 00:05 push lands a commit. Keep `AUDIT_CHECKPOINT_DIR` on the same fs as `./data/logs` (same-fs constraint above).

## Security review (1 Opus deploy-security round — folds)

- **H1 (HIGH, folded):** the litellm code mount (`../:/app/proxy:ro`) exposed `.env` + `origin-certs/origin.key` inside the litellm container. → narrowed to the 2 imported files + added `proxy/.dockerignore`.
- **H2 (HIGH, folded):** provision.sh/systemd vs compose path layouts were mutually exclusive. → canonical `proxy/deploy/` layout; provision.sh DEPLOY_DIR = its own dir; systemd unit path templated.
- **H3 (HIGH, folded):** `chattr +a` on the audit *dir* + `.cursors/` under `audit/` broke new-cabinet logging + cursor dedup. → per-file append-only cron; dir + `.cursors/` stay writable.
- **L1/L2/M2/M3 (folded):** redis auth; `no-new-privileges`+`cap_drop`+`user:`; bounded logging; pinned redis/caddy/python.
- **Follow-ups (filed, NOT in this PR):** **M1** — `app.py` GET endpoint joins `cabinet_id` into a path without slug-validation (traversal risk; FW-097 scope, endpoint not yet live) → harden + test before go-live. **M2** — `config.yaml log_requests` (FW-096 scope). **M4** — replace `get.docker.com | sh` with a GPG-pinned distro package.
- **R2 (fold verification) pending** before PR.
