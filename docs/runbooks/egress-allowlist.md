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
cabinet/scripts/egress-guard.sh stop       # stop runtime proxy/env; policy unchanged
```

The generic framework default is **allow all**, and since the Captain's
2026-07-26 ruling a freshly hatched egg ships that same allow-all posture in
its `instance/config/egress.yml` — enforcement is strictly **opt-in**, one
command (`egress-guard.sh enable`). *This* deployment now matches that default:
`enforce: false`, `allow_product: true`. It previously pinned an enforcing
72-hour dogfood posture with an EMPTY allow list; that window expired, the
ruling of 2026-07-29 ("network is allow-all by default") settled it, and an
empty allow list under enforcement 403s every outbound request — including the
read-only connector sweep onboarding now runs. `apply` **fails closed** if it
cannot attest the proxy.

Egress is a **reachability** ceiling, never a permission to act. Nothing about
this posture widens a write or a send: `framework.env.allow_sends()`, the comms
charter and recipient gates, the front-door killswitch and vetoes, the
authority matrix, and the connector lane's own mechanical read-only assertion
(`framework.onboarding.research.assert_read_only` — GET, or a GraphQL read
document, no other verb reachable, no redirect followed) all still hold.

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
allowed (`acme.example` also covers `xtest.acme.example`). **No** captain- or
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

On macOS, `apply` safely renders the tracked
`cabinet/launchd/com.cabinet.egress-proxy.template.plist`, installs it at
`~/Library/LaunchAgents/com.cabinet.egress-proxy.plist`, and bootstraps the
proxy itself into the user launchd domain. This ownership boundary is
load-bearing: a proxy merely backgrounded by a one-shot officer LaunchAgent is
killed with that wrapper's process group when the wrapper exits, even under
`nohup`. The persistent job survives caller exit, is restarted by launchd after
a crash, and returns at login. `stop`/disable boots it out and removes the
installed plist, preventing a disabled policy from returning later.
Linux/Docker retains the detached-child path and still requires its external
process/network supervisor.

The macOS job is deliberately registered in `gui/$(id -u)`. Run `apply` as
the logged-in console user (including over SSH only while that user's GUI
domain exists). A headless/pre-login host has no such domain: `bootstrap`
fails closed and officers must remain stopped. `launchctl print` exit 113 is
the only canonical "service absent" result; other query failures are treated
as unknown ownership, not success. A future truly headless deployment needs a
separately reviewed system-domain design, not a flag change.

macOS requires a fixed `proxy_port` from 1–65535. An OS-chosen port (`0`) is
valid only for the legacy child/test mode: after a crash or login restart it
could change while already-configured officers still point at the old port.

Before reuse, the guard attests that runtime state files and the installed
plist are owned regular files (never symlinks), the installed plist exactly
matches the tracked template plus resolved paths/policy, launchd's job PID
equals the atomically published proxy PID/ready markers, the live command names
the reviewed proxy with the exact arguments, and the allowlist and proxy env
match resolved policy.
Before either launch path opens it, the guard also requires `proxy.log` to be a
user-owned regular file and normalises it to mode `0600`; a symlinked log fails
closed rather than letting the supervisor append through an attacker-chosen
path.

`EGRESS_CONNECT_PORTS` is validated and canonicalised as an explicit list of
ports in the range 1–65535; empty, malformed, or mixed-validity values fail
instead of being partially ignored. The backend independently rejects the
same invalid forms.

**Fail-closed.** If a new proxy cannot be installed or verified, the guard
prints `FAIL-CLOSED …`, exits non-zero, and publishes no new proxy env. If an
old owner cannot be safely stopped, its PID/ready/env markers deliberately
remain as dirty forensic evidence; they do not attest against changed policy,
so new officer launch still fails. The guard never silently leaves egress open
when a captain asked to enforce. A boot/launchd caller must treat a non-zero
`apply` as fatal (do not launch officers with egress believed-restricted-but-
actually-open).

`status` is an operational assertion, not a cosmetic report: it returns
nonzero when enforcement is requested but any runtime artifact, process,
supervisor, or fixed port fails attestation. Run `apply` and `status`
sequentially under the normal launcher path; a concurrent status read during
an apply/stop transition can observe the intentionally unpublished env and
return transiently nonzero.

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
- **Same-UID installed-plist window.** Repository source and template are
  germline-locked, and every launcher attests the rendered plist exactly. The
  installed user LaunchAgent remains writable by the same host user, so a
  same-UID attacker could alter it between login execution and the next
  attestation. This is detected and officer launch fails closed, but preventing
  pre-attestation execution needs a root/system ownership design.
- **PID identity TOCTOU.** Child-mode teardown compares exact argv fields and
  state-file paths before signalling, but a narrow process-exit/PID-reuse race
  remains on hosts without a supervisor identity. macOS launchd teardown uses
  the exact service label and does not trust the PID file.
- **Fixed-port crash loop.** If another process persistently occupies the
  configured port, KeepAlive retries under launchd's throttle while runtime
  attestation stays red. The reviewed plist uses `Umask=0077`; verify the
  installed plist and proxy log are user-only, inspect only host-level error
  text, free the port, then re-`apply`. Never widen or randomise the port as a
  recovery shortcut.

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
2. **Add your MCP/tool hosts.** Edit `instance/config/egress.yml` (a hatched
   egg already has one, carrying the allow-all default; on a checkout without
   it, copy `instance/config/egress.yml.example`) and uncomment/add the hosts
   you use (table below). Anything not listed is refused when enforcement is
   on. Do this BEFORE step 3 — enabling with an empty list leaves only the
   Anthropic + Telegram floor reachable.
3. **Turn it on.** `cabinet/scripts/egress-guard.sh enable` — it sets
   `enforce: true` and installs the proxy in one step. On an already-locked
   deployment do it in a Captain unlock window and relock the same day. If
   config is already true, `egress-guard.sh apply` reconciles runtime without
   changing policy.
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
  not newly claimed — safe, but officers stay stopped. A prior env/marker may
  remain only when its owner could not be safely reconciled; that is evidence,
  not a green runtime. Fix the cause (port in use? invalid template? python
  missing?), then re-run. Keep a fixed port on macOS; `proxy_port: 0` is
  intentionally rejected.
- **macOS says the proxy is not supervisor-owned.** Inspect
  `launchctl print gui/$(id -u)/com.cabinet.egress-proxy`, then re-run `apply`.
  Also run `plutil -lint ~/Library/LaunchAgents/com.cabinet.egress-proxy.plist`
  and compare it with the tracked template contract. Do not hand-edit the
  installed plist; `apply` owns it.
  Do not substitute a shell-backgrounded proxy: it will die when the one-shot
  launcher exits and the next officer boot will correctly fail closed.
- **`status` exits nonzero.** Treat it as a gate failure, even though it still
  prints diagnostic state. If an `apply` is actively reconciling, wait for that
  command to finish and retry once; repeated failure is real drift.
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
