# Real-Mac egress supervisor drill — post-commit

**Date:** 2026-07-15
**Commit:** `64a931a2892b443dc5b923b2287a2680102f1ffd`
**Disposable label:** `com.cabinet.egress-proxy.codex-64a931a2`
**Disposable fixed port:** `64061`
**Live standard label:** absent before and after the drill
**Live officers / kill switch:** officers remained stopped; Captain halt stayed active

## Results

- `apply` returned ENFORCING and a separate caller immediately returned green
  `runtime-state`.
- Launchd PID, PID marker, and ready owner matched at `86453`; ready marker was
  `READY 64061 PID 86453`.
- Installed plist, PID, ready, env, and proxy log were all owned by `nate` and
  mode `0600`.
- `SIGKILL 86453` was recovered by KeepAlive on the same port as PID `87225`;
  runtime attestation returned green on poll attempt 2.
- Manual `bootout` removed PID/ready markers. An immediate rebootstrap was
  intentionally attempted too early and launchctl refused it with exit 5 while
  the old registration was still retiring. No env/runtime was falsely claimed.
  After `launchctl print` reached canonical absence exit 113, bootstrap
  succeeded and green attestation returned on poll attempt 2 as PID `88503`.
- Guard `stop` returned success, `launchctl print` returned 113, and the plist,
  PID, ready, and env markers were absent. After 11 seconds (past the 10-second
  throttle), the label was still absent and PID `88503` was dead: no respawn.
- HEAD-based egg export from the same commit shipped 1,702 files plus manifest
  and passed every expect-present/expect-absent assertion.

## Honest interpretation

The immediate rebootstrap refusal is correct launchd behavior and validates why
the guard's stop path polls until canonical exit 113 before removing/replacing
ownership. The successful retry after 113 is the production recovery contract.
No standard Cabinet job, live config, or officer session was used by this drill.

## Remaining release condition

After this commit is merged and deployed into the live checkout, run and record
`runtime-state` again **after** the Captain germline relock. Only then may the
72-hour observe-only clock start.
