# Germline amendment — launchd owns enforced egress

**Status:** proposed from the 72-hour observe-only preflight. Apply through the
Captain unlock/relock ceremony only after CI and the real Mac lifetime drill
are green.

## Finding

`egress-guard.sh apply` previously started the proxy with `nohup ... &`. That
works under an ordinary interactive shell and in hermetic unit tests, but the
production caller is a one-shot LaunchAgent (`start-officer-mac.sh`). macOS
launchd tears down that job's remaining process group when the wrapper exits,
so the proxy died after a successful `apply`. Runtime attestation then failed
closed on the next dry-run/officer boot. No officer escaped the allowlist, but
the claimed 72-hour enforced posture could not remain available.

The defect was reproduced with a real `KeepAlive=false` one-shot launchd job:
`apply` reported ENFORCING, the wrapper exited 0, and `runtime-state` then
returned `FAIL-CLOSED — attested proxy is not live/ready`. A control probe in
which launchd owned `egress-proxy.py` directly remained alive and attested.

## Amendment

- On Darwin, `egress-guard.sh apply` renders the tracked egress LaunchAgent
  template with `plistlib`, atomically installs it in `~/Library/LaunchAgents`,
  and uses `launchctl bootstrap` to make `com.cabinet.egress-proxy` the direct
  user-domain owner of the reviewed Python proxy command.
- The LaunchAgent is `KeepAlive` + `RunAtLoad` with a fixed proxy port, so it
  survives caller exit, restarts after a crash, and returns at login without
  changing the endpoint already projected into officer environments.
- Runtime attestation requires the exact installed template contract, the
  supervisor job PID, atomically published PID/ready markers, command,
  allowlist, and proxy environment.
- Repeated officer boots reuse the matching supervised process instead of
  flapping it.
- `stop`/disable share the same reconciliation lock and reconcile both
  ownership forms regardless of the newly requested mode: boot out an exact
  launchd service first, then stop any exact-argv orphan/legacy child. Runtime
  markers are removed only after full success and remain as dirty evidence on
  a refused/unknown stop, so a second stop cannot falsely report clean.
- Proxy PID/ready markers use fsync + atomic replace and carry the owning PID;
  graceful shutdown removes only its own markers, never a restart successor's.
- Linux/Docker keeps the prior detached-child mode. Its external supervisor
  and raw-socket network policy remain honest deployment requirements.
- Tests force child mode for hermetic legacy coverage and add a fake-launchctl
  lifecycle test for render/bootstrap, exact plist/job/PID attestation,
  idempotence, policy-change bootout-before-bootstrap, child↔launchd ownership
  transitions, disable, and safe stop. CONNECT ports are strict at both guard
  and backend boundaries; process matching compares argv fields and fixed-port
  ready drift fails attestation.

## Adversarial checkpoint and drill evidence

Fable 5 checkpoint CP1 requested changes for cross-mode ownership, marker
retention after refused stops, accidental hook globs, CONNECT-port validation,
substring PID matching, fixed-port drift, launch-mode errors, template
substitution, and operational residuals. The implementation resolves those
items and adds direct regression probes; CP2 re-review remains a merge gate.

Two production-faithful real-Mac drills (under unique disposable labels) have
already proved caller-exit survival, SIGKILL restart to a new PID on the same
fixed port, bootout/bootstrap recovery, explicit stop, installed-plist removal,
and no respawn after the 10-second throttle window. The second recorded PID
sequence was `28112 → 28490 → 28555`; its plist was removed and the job stayed
absent. A final post-commit drill must additionally record strict file modes,
then clean the disposable label before live deployment.

## Germline surface and ceremony

The amendment changes the already-registered immutable guard and proxy, adds
the launchd template to the immutable core/host lock/hook deny-list in
lockstep, and adds the template to the portable egg manifest. The same commit
updates contract tests and this runbook; policy shape and default-off posture
remain unchanged.

After merge on the halted live checkout:

1. Keep the verified kill switch active and all Cabinet LaunchAgents stopped.
2. `sudo bash cabinet/scripts/germline-lock.sh unlock`
3. Reconcile the live checkout to the merged commit without dropping instance
   state.
4. Run shell syntax/shellcheck, the egress suite, and the real one-shot launchd
   lifetime + crash-restart drill.
5. `sudo bash cabinet/scripts/germline-lock.sh lock`
6. `bash cabinet/scripts/germline-lock.sh verify` and `status`

The dogfood clock must not start until `runtime-state`, officer dry-runs, raw
socket denial, proxy allow/block probes, and post-relock immutability are all
recorded green.
