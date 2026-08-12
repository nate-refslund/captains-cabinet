# Checkpoint review — feat/first-run-password (cp1)

## What changed

A fresh Cabinet no longer boots with a random `DASHBOARD_PASSWORD` that
setup-env.sh generated and the login page told a non-technical operator to
recover with a Terminal command. Instead:

1. **First run = the operator chooses their own password.** With no password
   set, `/login` renders a "create a password" screen (choose + confirm, a
   plain 12-char floor). Submitting writes it to the SAME store the verifier
   reads and lands the operator on the dashboard.
2. **First-run lock.** Until a password exists, every gated route and mutating
   API is redirected to `/login`; the create action is the sole pre-auth path
   and is itself first-run-only and localhost-only.
3. **Terminal-free reset.** The login "Forgot?" block no longer mentions a
   terminal; a forgotten password is reset by double-clicking
   `Reset Cabinet Password.command`, which clears the stored password and
   returns the dashboard to first-run. `dashboard-password.sh` becomes the
   reset/inspect helper (`--reset` / `--copy`).

## Storage + verification parity (matched exactly, NOT a new secret path)

`DASHBOARD_PASSWORD` in `cabinet/.env`, **plaintext**, unchanged. It is
plaintext by necessity, not laziness: the same value is the HMAC key that signs
the `cabinet_session` cookie (`lib/auth.sign` / `middleware.verify` /
`verdict.hmacHex`), so it cannot be one-way hashed without breaking session
signing. The create action writes via the existing `lib/config-write.writeEnvValue`
(the same function `actions/env.updateEnvVar` uses; preserves 0600) and then
sets `process.env.DASHBOARD_PASSWORD` live. Verification is the untouched
`checkPassword` / `verifySession`. No parallel secret was introduced.

Middleware is pinned to `runtime: 'nodejs'` so it shares the live `process.env`
with the Node server action — a just-chosen password is honoured immediately,
with no dashboard restart, and an Edge sandbox cannot serve a stale env snapshot.
Build verified (`next build`, standalone, compiles the middleware as
Proxy/Node). This also closes a latent inconsistency: a password rotated via the
integrations editor was previously invisible to an Edge middleware until restart.

## Adversarial pass on the first-run lock — can the no-password window be exploited?

The window is "hatch finished, no password chosen yet". Threats and why each is closed:

- **Drive a gated route with no auth.** In production `resolveSecret()` returns
  `null` when `DASHBOARD_PASSWORD` is unset/`changeme`, so middleware's
  `secret` is null and every gated path 307s to `/login`. Pinned by
  `middleware.test.ts` → *first-run lock* (a protected API `/api/tasks`,
  `/api/world/stream`, `/api/library/search` and `/` all refused; only `/login`
  passes). Mutating server ACTIONS don't ride middleware, but they already gate
  on `requireDashboardAuth` → `verifySession`, which is `false` with no secret
  (existing `actions-auth.test.ts` sweep, unchanged).
- **Overwrite the password to seize the door.** `createPassword` refuses if a
  real password exists in the live process OR in the durable file
  (`hasRealPassword` on both), so it is inert the instant one is set. Pinned:
  *first-run ONLY — never overwrite* (both arms).
- **Set the password from another device during the window.** `createPassword`
  refuses any request carrying a proxy header (`x-forwarded-for` /
  `x-forwarded-host` / `x-real-ip`) or a non-loopback `Host` — i.e. anything
  through `tailscale serve` or a LAN bind. Defence in depth over the 127.0.0.1
  bind. Pinned: *local machine only* + `isLocalRequest` unit arms.
- **Inject via the chosen password itself.** `cabinet/.env` is `source`d by bash
  at dashboard/officer start; a value with a space, `$()`, backtick or `;`
  would break or EXECUTE on restart. The charset gate rejects everything but
  `[A-Za-z0-9._,:@%^+=-]`. Pinned with live payloads (`pw$(touch …)`, backtick,
  `;`, quotes) in both `first-run.test.ts` and `create-password.test.ts`.
- **Reset abused by a locked-out remote attacker.** Reset is NOT a web endpoint;
  it is a local file op (double-click on the box) that clears `cabinet/.env`
  and restarts the dashboard. It cannot be reached from a web session.
- **Static bleed-through.** `/login` is `force-dynamic`, so `firstRun` is
  evaluated per request, never baked at build (a build with no password would
  otherwise pin the create screen onto a configured instance).

Residual, named: the double-clickable reset is a `.command`, which opens a
Terminal window that Launch Services runs; the operator types nothing and does
one double-click, and all interaction is native `osascript` dialogs. "No typed
command, no terminal to open yourself" holds; a literal zero-Terminal-window
reset would need a signed `.app` (the optional companion), which a default
install may not have built — so the always-present `.command` was chosen.

## Class-11 four questions, applied to the new sensors

1. **Does each arm FAIL against pre-change code?** The login grep arm asserts
   the ABSENCE of `Terminal`/`bash`/`cabinet/scripts`/`dashboard-password`/`--copy`
   — the old `page.test.ts` asserted their PRESENCE, so it flips red↔green across
   the change (verified: old page.tsx contained `bash cabinet/scripts/...`). The
   setup-env arm asserts `DASHBOARD_PASSWORD=` is EMPTY after `--defaults`; the
   pre-change script generated a ≥20-char value, so the arm fails on old code.
   The first-run-lock middleware arm asserts a 307 with `DASHBOARD_PASSWORD`
   unset; pre-change behaviour is identical here (the lock pre-existed) — this
   arm pins the property the flow now depends on rather than a code delta, and
   is labelled as such.
2. **The degenerate end.** `hasRealPassword`: empty string, unset, and
   `changeme` all → false (the first-run state), arm'd explicitly. `isLocalRequest`:
   absent Host → false (arm'd). `validateChosenPassword`: empty/short → refused.
   `dashboard-password.sh --reset`: key absent → APPENDS `DASHBOARD_PASSWORD=`
   (arm'd) rather than silently no-op'ing; loose perms → refuses BEFORE touching
   the dashboard (arm asserts the launchctl shim was never called).
3. **What the test env guarantees that prod does not.** The Python reset arms
   SHIM `launchctl` (a real `kickstart` would bounce the developer's own live
   dashboard) and assert the restart targets exactly `com.cabinet.dashboard`.
   The failure branch is exercised by a shim exiting 1 — so the honest "reopen
   the dashboard" path (the CI/Linux reality, where launchctl is absent) is
   covered, not assumed. `create-password.test.ts` mutates `process.env`
   directly (not `vi.stubEnv`) because the action does, and cleans it in
   afterEach/afterAll so no state leaks to sibling suites.
4. **Sensor wired to the live artifact.** The login grep arm reads every
   `*.tsx`/`*.ts` (minus tests) in the real `login/` dir, so a forbidden word in
   a sibling component or a comment is caught, not just `page.tsx`.
   `create-password.test.ts` drives the REAL `checkPassword`/`config-write`
   (only the session mint, redirect and headers are mocked), and asserts the
   password from the FILE, not from a mock return — the same discipline the
   existing env sweep uses.

## Not done here (named)

- The integrations env-editor can still set `DASHBOARD_PASSWORD` to a
  shell-unsafe value (pre-existing; generated values dodged it). Out of scope;
  worth a follow-up charset guard on that one key.
- `hatch.sh` app-feel wording is owned by a parallel builder; its clipboard
  handover now hits the honest "no password yet → create screen" fallback its
  own tests already cover. Docs describing that flow were corrected here.

Reviewed-Scope-Digest: 37d0afbf94fd48ea62e2dd069bdef0c675722cda9e8ad094651247a5e75241e4
