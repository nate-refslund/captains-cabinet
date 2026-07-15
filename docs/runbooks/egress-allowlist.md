# Runbook — enforced egress allowlist (opt-in)

**What this is.** An OPT-IN framework outbound-network allowlist. This
deployment has opted in for dogfood.
The Captain's directive was: *"implement the possibility of an enforced egress
allowlist (default allow all)."* This is that control — a real, enable-able
egress jail that changes **nothing** until a captain turns it on.

**Why it exists.** Officers ingest untrusted content (email, web pages, Sentry
issues) *and* hold outbound tools (Bash `curl`/`wget`, web MCPs, python
`requests`). With no egress boundary, one prompt-injected instruction can move
captain-private data off-box. This control lets a captain deny outbound egress
by default and permit only an explicit allowlist. The live instance switch is
Captain-owned immutable policy; widening it requires unlock/edit/relock.

---

## TL;DR

```sh
cabinet/scripts/egress-guard.sh status     # is it on? what's allowed? proxy up?
cabinet/scripts/egress-guard.sh dry-run    # what WOULD be allowed/blocked (installs nothing)
cabinet/scripts/egress-guard.sh enable     # Captain unlock window only
cabinet/scripts/egress-guard.sh disable    # Captain unlock window only
cabinet/scripts/egress-guard.sh apply      # reconcile runtime to egress.yml (boot/launchd verb)
cabinet/scripts/egress-guard.sh stop       # tear down the proxy regardless of config
```

The generic framework default is **allow all**. This deployment pins
`enforce: true`, `allow_product: false`, and no extra hosts, leaving only the
Anthropic + Telegram framework floor. `apply` **fails closed** if it cannot
attest the proxy.

---

## How it works

Two config files, framework-default-then-instance-override (instance wins, same
pattern as `framework/defaults/spending-limits.yml`):

- `framework/defaults/egress.yml` — shipped default: `enforce: false` (allow
  all), `allow_product: true`, and a minimal control-plane floor
  (`api.anthropic.com`, `api.telegram.org`).
- `instance/config/egress.yml` — Captain-owned per-deployment override. Copy
  from the example before locking a new deployment; after locking,
  `enable`/`disable` require the explicit unlock/relock ceremony.

**Merge rules.** `enforce`, `proxy_port`, `allow_product` are scalar — the
instance value replaces the default. `allow_hosts` is **unioned** with the
framework floor, so enabling enforcement can never accidentally sever the
officer↔captain control plane.

**Product hosts, resolved generically.** With `allow_product: true` the guard
adds the captain's OWN domains from `org_domains` in `instance/config/platform.yml`
(else `product.yml` / nested `product.org_domains`) — the exact source
`framework/env.py` `org_domains()` reads. Each domain and its subdomains are
allowed (`polads.eu` also covers `xtest.polads.eu`). **No** captain- or
industry-specific host is hardcoded in the framework; a deployment with no
`org_domains` simply contributes none.

**Enforcement mechanism (only when `enforce: true`).** `apply` starts a small
local forward proxy (`cabinet/scripts/egress-proxy.py`, python3 stdlib, bound to
`127.0.0.1`) that permits HTTP `CONNECT` + HTTP forwarding **only** to the
resolved allowlist and returns `403` for everything else (deny-by-default — a
blocked host is never even resolved or dialed). It then writes an
`HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` export file. Both officer launchers
reconcile the guard and project that file through their reviewed clean-env
parser before boot. On macOS, the launcher also generates a Seatbelt profile
that rejects direct external TCP/UDP and permits localhost, making the verified
proxy the only officer path to a remote host. No persistent sudo.

Before reuse, the guard attests that runtime state files are owned regular
files (never symlinks), the live PID command names the reviewed proxy with the
exact allow/ready paths, and the allowlist and proxy env match resolved policy.

**Fail-closed.** If the proxy cannot be installed or verified, the guard prints
`FAIL-CLOSED …`, exits non-zero, and writes **no** proxy env — it never silently
leaves egress open when a captain asked to enforce. A boot/launchd caller must
treat a non-zero `apply` as fatal (do not launch officers with egress believed-
restricted-but-actually-open).

### Officer wiring and restart semantics

`start-officer-mac.sh` and `start-officer.sh` call `apply`, require success,
read `runtime-state`, and load `<state_dir>/egress/proxy.env` through
`officer-env.py` (never by executing the file as arbitrary shell). Repeated
launches reuse a matching healthy proxy rather than restarting it.

This affects **new officer processes only**. Enabling the config does not
retrofit environment or Seatbelt policy into sessions that are already
running. Restart the officer fleet after enabling, then prove the boundary from
inside a fresh officer session. When `enforce: false`, the proxy env is absent
and the launchers install no network restriction: the shipped default remains
allow-all. `status` prints the exact proxy and env state.

---

## EXACTLY what it covers — and what it does NOT

Coverage differs by deployment target.

### ✅ Covered on every target (allowlisting proxy)

- `curl` / `wget` respecting `HTTP_PROXY`/`HTTPS_PROXY` (the default).
- python `requests` / `urllib` / `httpx` (honour proxy env by default).
- Most MCP servers and SDK HTTP clients that honour proxy env vars
  (anthropic, exa, perplexity, brave, vercel, neon, monday, github, …).
- Both plain-HTTP (absolute-URI forwarding) and HTTPS (`CONNECT` tunnel).
  Plain HTTP discards the caller's `Host` header and rebuilds it from the
  validated URL.
  `CONNECT` is additionally restricted to the **HTTPS port (443)** by default,
  so an allowlisted host cannot be turned into a generic TCP tunnel to another
  port (`:22`, `:25`, …). If a deployment genuinely needs another CONNECT port,
  widen it by launching the proxy with `--connect-ports "443,<port>"` (or
  `EGRESS_CONNECT_PORTS`); the default stays 443-only.

### ✅ Additional macOS boundary (Seatbelt)

- Direct external TCP and UDP are denied for the officer process tree when
  `enforce: true`; raw `nc`, `ssh`, `socket.connect()`, `--noproxy`, and
  proxy-ignoring MCP clients cannot dial a remote address.
- TCP/UDP to localhost remains available for the verified proxy, Redis, and
  other local Cabinet services.

### ⚠️ Honest residuals

- **Linux/Docker raw sockets.** The legacy launcher projects the proxy env but
  has no Seatbelt equivalent. A raw socket or proxy-ignoring client bypasses it
  unless the host/container supplies an egress network policy.
- **Already-running sessions.** They retain their old environment and sandbox
  until restarted.
- **Local-service deputies on macOS.** Localhost is deliberately allowed. An
  exposed local service capable of making arbitrary outbound requests could
  become a confused deputy; do not run untrusted forwarders on localhost and
  keep their own authentication/allowlists enabled.
- **DNS rebinding.** The allowlist matches the *hostname* presented; it does not
  pin the resolved IP, so an allowlisted name that later resolves to a hostile
  IP is still permitted.
- **Opaque TLS after CONNECT.** The proxy validates CONNECT authority but does
  not intercept TLS, so it cannot prove SNI or the HTTP host inside the tunnel.
  An allowlisted shared/CDN endpoint retains a domain-fronting/other-tenant
  residual. TLS interception or destination-specific network policy is needed
  to close it; plain HTTP does not have this gap.
- **Unsandboxed services.** The proxy and other host daemons are outside the
  officer sandbox. Their own input validation is part of the boundary.

### Stronger / complementary controls

- **Container/host network policy.** Required on Linux/Docker when raw-socket
  containment matters. Restrict the officer namespace to localhost/the proxy
  and enforce the destination policy outside the officer process.
- **`pf`/`pfctl` anchor (macOS, sudo).** An optional host-wide second boundary.
  It is broader than per-officer Seatbelt and can cover unsandboxed local
  deputies, but needs sudo, careful IP refresh, and germline ceremony.
- **`cabinet/scripts/hooks/pre-tool-use.sh` Bash-layer gate (future, germline).**
  A pre-execution inspection of officer Bash that refuses `curl`/`nc`/etc. to a
  non-allowlisted host is the defense-in-depth companion that would close the
  raw-socket gap at the tool layer. It lives on a germline path and is a future
  ceremony item — **not** part of this deliverable.

**Bottom line:** macOS officer processes get proxy hostname allowlisting plus a
kernel raw-socket denial. Linux/Docker gets proxy allowlisting only until an
external network policy is installed. Neither claim covers already-running
sessions or arbitrary unsandboxed localhost services.

---

## Enabling it (step by step)

1. **Inspect first.** `cabinet/scripts/egress-guard.sh dry-run` — see exactly
   which hosts would be allowed. The shipped floor + your `org_domains` is
   usually **not enough** for a working deployment: your MCPs need their hosts.
2. **Add your MCP/tool hosts.** Copy `instance/config/egress.yml.example` to
   `instance/config/egress.yml` and uncomment/add the hosts you use (table
   below). Anything not listed is refused when enforcement is on.
3. **Turn it on.** In a Captain unlock window, edit/enable and relock the same
   day. If config is already true, `egress-guard.sh apply` reconciles runtime
   without changing policy.
4. **Restart every officer.** The launchers apply and load enforcement before
   each boot; old sessions cannot be retrofitted.
5. **Verify.** `cabinet/scripts/egress-guard.sh status` shows `enforce: true`,
   the resolved allowlist, and `proxy: RUNNING`. Confirm an officer can still
   reach Claude + Telegram and its own product, and that a probe to an
   unlisted host is refused.
6. **To turn it off:** make a separate Captain unlock/edit/relock decision;
   `disable` returns to allow-all and is intentionally unavailable to officers.

### Common MCP / tool hosts to add

Only add the ones you actually run. Subdomains of a listed host are covered.

| Tool / MCP        | Host to allow             |
|-------------------|---------------------------|
| Claude API (floor)| `api.anthropic.com`       |
| Telegram (floor)  | `api.telegram.org`        |
| GitHub            | `api.github.com`, `api.githubcopilot.com` |
| Exa search        | `api.exa.ai`              |
| Perplexity        | `api.perplexity.ai`       |
| Brave search      | `api.search.brave.com`    |
| Vercel            | `api.vercel.com`          |
| Neon              | `console.neon.tech`       |
| Monday.com        | `api.monday.com`          |

> Your own product hosts are auto-included from `org_domains` while
> `allow_product: true` — you do not list them here.

---

## Troubleshooting

- **`apply`/`enable` exits non-zero with `FAIL-CLOSED`.** The proxy could not
  bind or come up (port in use? bad `proxy_port`? python missing?). Egress was
  **not** restricted and no proxy env was written — safe, but enforcement is
  off. Fix the cause (try `proxy_port: 0` to let the OS pick), then re-run.
- **An officer suddenly can't reach a service.** Its host is not on the
  allowlist. `dry-run` to confirm, add the host to `instance/config/egress.yml`,
  re-`apply`.
- **`status` says `proxy: RUNNING` but an old officer still reaches a blocked
  host.** Restart it. On Linux/Docker, also check whether the client bypasses
  proxy env; that path needs an external network policy. On macOS, a fresh
  officer reaching the host is a release-blocking boundary failure.

## Verify (contributors)

```sh
bash -n cabinet/scripts/egress-guard.sh
shellcheck -S warning cabinet/scripts/egress-guard.sh
python3 -m py_compile cabinet/scripts/egress-proxy.py
python3 -m pytest cabinet/scripts/tests/test_egress_guard.py
```
