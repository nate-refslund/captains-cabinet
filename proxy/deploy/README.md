# FW-121 — refslund.ai backend deploy stack

Net-new deploy automation for the refslund.ai SaaS backend (the LiteLLM proxy + the FW-097 audit substrate). Runs on a **Hetzner Frankfurt EU-resident VPS** (captain-decisions 2026-05-25 07:13 UTC — GDPR EU-residency, no US-parent) behind **Cloudflare**. Spec basis: **Spec 050 L16** (Docker baseline), **Spec 051 §Topology**, **Spec 052 CTO#2/#3 + AC#7**.

> **Status: deploy-gated.** Buildable + reviewable now; *validates* at VPS-provision (**#191**, Captain founder-action). Nothing is live until the VPS exists. **One blocked file:** `Dockerfile.audit-server` is held by a Layer-1 gate (`*"Dockerfile"*` → CoS) — see "Known blocker" below.

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
| `litellm` | `ghcr.io/berriai/litellm:main-stable` | proxy.refslund.ai/v1; per-cabinet cap + margin; FW-096 audit callback |
| `audit-server` | built (`Dockerfile.audit-server`) | FW-097 GDPR audit log; POST `/proxy/audit/log` + GET `/dashboard/audit/...`; **non-root** |
| `ingest` | same image, loop cmd | FW-096 proxy-audit stream → Spec 052 hash-chained SSOT, every `INGEST_INTERVAL`s |
| `redis` | `redis:7-alpine` | per-cabinet daily-cap state (survives restart) |
| `caddy` | `caddy:2-alpine` | LOCAL origin reverse-proxy (Cloudflare owns public TLS; `auto_https off`) |

## Environment (`.env`, chmod 600 — created by the operator, validated by `provision.sh`)

`provision.sh` refuses to start if any **required** var is empty. Secrets are server-side only (Spec 051 AC#5) and never echoed.

| Var | Req | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | server-side provider key — NEVER leaves refslund.ai |
| `LITELLM_MASTER_KEY` | ✅ | proxy admin API (mints/rotates per-cabinet virtual keys) |
| `AUDIT_API_KEY` | ✅ | FW-097 audit-server Bearer auth; distinct from `LLM_PROXY_KEY` (CTO#5) |
| `LITELLM_MARGIN_PCT` | — | markup % (default 100 = 2×). **Private value.** |
| `LITELLM_CAP_USD` | — | per-cabinet daily cap (default 50.0; must match `config.yaml`) |
| `DATABASE_URL` | — | optional Postgres for LiteLLM key/team storage (blank = in-memory + Redis) |
| `INGEST_INTERVAL` | — | seconds between ingest cycles (default 60) |

> `REDIS_HOST`/`REDIS_PORT` are set in `docker-compose.yml` (internal) — do **not** put them in `.env`.

## Deploy runbook (on the VPS, as root)

1. Copy this repo's `proxy/` subtree to `/opt/refslund-backend` (compose, scripts, `audit-server/`, `config.yaml`, `audit_logger.py`).
2. Create `/opt/refslund-backend/.env` from the table above (`chmod 600`).
3. Place the **Cloudflare Origin CA** cert at `origin-certs/origin.pem` + `origin-certs/origin.key` (dashboard → SSL/TLS → Origin Server → Create Certificate, host `*.refslund.ai`). Set Cloudflare SSL mode to **Full (strict)**.
4. `sudo DEPLOY_DIR=/opt/refslund-backend ./provision.sh` — installs Docker, creates the non-root `audit` user, lays out `data/logs`, `chattr +a` the SSOT, installs+enables the systemd unit, builds, and starts the stack.
5. Verify: `systemctl status refslund-backend`, `docker compose ps`, and the Cloudflare-fronted health endpoints (`proxy.refslund.ai/health/liveliness`, `audit.refslund.ai/health`).

## Security notes

- **Non-root audit-server (CTO#3):** the FW-097 process runs as the unprivileged `audit` user (uid 10001); app-layer append-only is the PRIMARY enforcement.
- **Append-only (AC#7):** `chattr +a` on `data/logs/audit` is the SECONDARY defense. **Interaction with FW-100 erasure:** pseudonymization rewrites blanked fields in place, which `+a` blocks — the erasure flow must `chattr -a` → pseudonymize → `chattr +a` under root. The running (non-root) audit-server only ever appends, so it is unaffected.
- **Audit log root wiring:** `litellm` reads `LITELLM_AUDIT_LOG_ROOT` as the proxy-audit dir (`/data/logs/proxy-audit`); `audit-server`+`ingest` read it as the *parent* (`/data/logs`). Both point into the same bind-mounted `./data/logs` — different levels, by design (FW-096 vs FW-097 conventions).
- **Secrets:** `.env` chmod 600; `provision.sh` presence-checks (never prints values); margin + provider keys are server-side only.

## Deploy-time validation checklist (do NOT skip — `config.yaml` flags version drift)

- [ ] **Pin the LiteLLM image to a digest** after confirming `proxy/config.yaml` (team_settings / callbacks / `--num_workers`) parses against that version.
- [ ] Confirm the **Redis↔budget** wiring for the pinned LiteLLM version (cap-state must survive restart — `restart: unless-stopped` + Docker boot policy can otherwise reset an in-memory budget).
- [ ] Re-pin `requirements.txt` to exact versions (lockfile) after the first successful build.
- [ ] Cloudflare SSL = **Full (strict)**; Origin cert covers `*.refslund.ai`.
- [ ] `AUDIT_LOG_ENDPOINT` on customer cabinets points at `https://audit.refslund.ai/proxy/audit/log`.

## Known blocker (surfaced to CoS)

`Dockerfile.audit-server` is blocked by the Layer-1 pre-tool-use gate (`*"Dockerfile"*` → CoS-only). That gate's arm is unanchored (its sibling `*"cabinet/docker-compose"*` IS `cabinet/`-anchored), so it over-matches this CTO-owned product-deploy Dockerfile. Pending CoS: either author the Dockerfile, or anchor the gate's Dockerfile arm to `cabinet/`. The compose `audit-server.build` references it; the stack is otherwise complete. (Same gate also over-matched `.env.example`, so the secret contract lives in the Environment table above instead.)
