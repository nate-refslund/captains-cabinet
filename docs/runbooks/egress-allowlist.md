# Runbook — enforced egress allowlist (opt-in)

**What this is.** An OPT-IN outbound-network allowlist for the officer runtime.
The Captain's directive was: *"implement the possibility of an enforced egress
allowlist (default allow all)."* This is that control — a real, enable-able
egress jail that changes **nothing** until a captain turns it on.

**Why it exists.** Officers ingest untrusted content (email, web pages, Sentry
issues) *and* hold outbound tools (Bash `curl`/`wget`, web MCPs, python
`requests`). With no egress boundary, one prompt-injected instruction can move
captain-private data off-box. This control lets a captain deny outbound egress
by default and permit only an explicit allowlist. It touches **no germline
path** and installs nothing until enabled.

---

## TL;DR

```sh
cabinet/scripts/egress-guard.sh status     # is it on? what's allowed? proxy up?
cabinet/scripts/egress-guard.sh dry-run    # what WOULD be allowed/blocked (installs nothing)
cabinet/scripts/egress-guard.sh enable     # turn enforcement ON  (+ start the proxy)
cabinet/scripts/egress-guard.sh disable    # turn enforcement OFF (+ tear it down = allow all)
cabinet/scripts/egress-guard.sh apply      # reconcile runtime to egress.yml (boot/launchd verb)
cabinet/scripts/egress-guard.sh stop       # tear down the proxy regardless of config
```

Default state ships as **allow all** (`enforce: false`). Enabling installs a
local allowlisting forward proxy and **fails closed** if it cannot verify it.

---

## How it works

Two config files, framework-default-then-instance-override (instance wins, same
pattern as `framework/defaults/spending-limits.yml`):

- `framework/defaults/egress.yml` — shipped default: `enforce: false` (allow
  all), `allow_product: true`, and a minimal control-plane floor
  (`api.anthropic.com`, `api.telegram.org`).
- `instance/config/egress.yml` — your per-deployment override (copy from
  `instance/config/egress.yml.example`, or let `enable`/`disable` edit the
  `enforce:` line for you). See that `.example` for every knob.

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
`HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` export file the officer launch sources.
No persistent sudo.

**Fail-closed.** If the proxy cannot be installed or verified, the guard prints
`FAIL-CLOSED …`, exits non-zero, and writes **no** proxy env — it never silently
leaves egress open when a captain asked to enforce. A boot/launchd caller must
treat a non-zero `apply` as fatal (do not launch officers with egress believed-
restricted-but-actually-open).

### Wiring officers to the proxy

> ⚠️ **This is a required manual step — it is NOT done for you.** As of this
> deliverable **no** officer launch wrapper, entrypoint, or launchd plist in
> the tree sources `proxy.env`. Until **you** add the one line below to your
> launch wrapper, `enable` starts and verifies the proxy but **constrains
> nothing already running** — an officer launched without it inherits no proxy
> env and reaches the network exactly as before. `enable`/`apply` print a
> `WARNING` on stderr while nothing in the tree sources the file, so a green
> `proxy: RUNNING` is never mistaken for "officers are constrained."

`apply` writes the export file to `<state_dir>/egress/proxy.env` (state dir =
`CABINET_STATE_DIR`, else `state_dir` from `platform.yml`, else `~/.cabinet/state`).
The officer launch must **source** it so the proxy env is inherited:

```sh
# in the officer launch wrapper / entrypoint, before exec'ing the officer:
[ -f "$CABINET_STATE_DIR/egress/proxy.env" ] && . "$CABINET_STATE_DIR/egress/proxy.env"
```

When `enforce: false`, that file is absent → officers inherit no proxy → **allow
all**. `status` prints the exact `proxy_env` path for your deployment.

---

## EXACTLY what it covers — and what it does NOT

Be honest with yourself about the boundary. This is a **proxy-honouring** layer.

### ✅ Covered (caught by the proxy)

- `curl` / `wget` respecting `HTTP_PROXY`/`HTTPS_PROXY` (the default).
- python `requests` / `urllib` / `httpx` (honour proxy env by default).
- Most MCP servers and SDK HTTP clients that honour proxy env vars
  (anthropic, exa, perplexity, brave, vercel, neon, monday, github, …).
- Both plain-HTTP (absolute-URI forwarding) and HTTPS (`CONNECT` tunnel).
  `CONNECT` is additionally restricted to the **HTTPS port (443)** by default,
  so an allowlisted host cannot be turned into a generic TCP tunnel to another
  port (`:22`, `:25`, …). If a deployment genuinely needs another CONNECT port,
  widen it by launching the proxy with `--connect-ports "443,<port>"` (or
  `EGRESS_CONNECT_PORTS`); the default stays 443-only.

### ⚠️ Residual — NOT caught (do not oversell this)

- **Raw sockets.** `nc`, `ssh`, a python `socket.connect()`, or any client that
  dials an IP directly bypasses an HTTP proxy entirely.
- **Proxy-ignoring MCPs/binaries.** A tool that does not read `HTTP_PROXY` (or
  is explicitly told `--noproxy`) is not constrained by this layer.
- **DNS rebinding.** The allowlist matches the *hostname* presented; it does not
  pin the resolved IP, so an allowlisted name that later resolves to a hostile
  IP is still permitted.
- **A client that unsets the env.** Anything running with the proxy env stripped
  (e.g. a subprocess that scrubs its environment) escapes the layer.

### Stronger / complementary controls

- **`pf`/`pfctl` anchor (macOS, sudo).** A kernel-level packet-filter anchor that
  blocks outbound to everything except the allowlist IPs catches raw sockets too.
  It is stronger but needs **sudo** and per-relock discipline (germline etiquette:
  route through a CG ledger row + a Captain unlock window), and it is IP-based, so
  it needs periodic re-resolution of allowlist hostnames. Out of scope for this
  no-sudo proxy layer; note it as the escalation if the residual matters for your
  threat model.
- **`cabinet/scripts/hooks/pre-tool-use.sh` Bash-layer gate (future, germline).**
  A pre-execution inspection of officer Bash that refuses `curl`/`nc`/etc. to a
  non-allowlisted host is the defense-in-depth companion that would close the
  raw-socket gap at the tool layer. It lives on a germline path and is a future
  ceremony item — **not** part of this deliverable.

**Bottom line:** enabling this proxy meaningfully raises the bar for the common
exfil paths (curl + python-requests + most MCPs) with no sudo, but it is **not**
a complete network jail. For irreversible-harm threat models, pair it with the
`pf` anchor and the future Bash-layer gate.

---

## Enabling it (step by step)

1. **Inspect first.** `cabinet/scripts/egress-guard.sh dry-run` — see exactly
   which hosts would be allowed. The shipped floor + your `org_domains` is
   usually **not enough** for a working deployment: your MCPs need their hosts.
2. **Add your MCP/tool hosts.** Copy `instance/config/egress.yml.example` to
   `instance/config/egress.yml` and uncomment/add the hosts you use (table
   below). Anything not listed is refused when enforcement is on.
3. **Turn it on.** `cabinet/scripts/egress-guard.sh enable`. On success it
   prints the proxy address and the `proxy.env` path — and a `WARNING` while
   nothing sources it yet (see next step).
4. **Wire the launch** to source `proxy.env` (see "Wiring officers to the
   proxy"). **This is required and is not wired for you** — as of this
   deliverable no launch/entrypoint/plist in the tree sources `proxy.env`, so
   until you add the one-line source, enabling constrains **nothing already
   running**. The step is done when the `enable`/`apply` `WARNING` stops
   printing.
5. **Verify.** `cabinet/scripts/egress-guard.sh status` shows `enforce: true`,
   the resolved allowlist, and `proxy: RUNNING`. Confirm an officer can still
   reach Claude + Telegram and its own product, and that a probe to an
   unlisted host is refused.
6. **To turn it off:** `cabinet/scripts/egress-guard.sh disable` (returns to
   allow-all and tears the proxy down).

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
- **`status` says `proxy: RUNNING` but a tool still reaches a blocked host.**
  That tool is in the residual set (raw socket / ignores proxy env). See the
  residual section; the proxy layer cannot catch it.

## Verify (contributors)

```sh
bash -n cabinet/scripts/egress-guard.sh
shellcheck -S warning cabinet/scripts/egress-guard.sh
python3 -m py_compile cabinet/scripts/egress-proxy.py
python3 -m pytest cabinet/scripts/tests/test_egress_guard.py
```
