# Checkpoint review — fix/config-write-portability

## What changed and why

Fifteen `sed -i` config writes in the dashboard, seven more in `create-officer.sh`,
two bare `timeout` calls, a `grep -P` inside a test assertion and a `date -d`
with no BSD leg had all shipped, and **none of them ever ran on the only machine
this system is deployed to**. BSD `sed` takes the in-place suffix as a mandatory
argument; macOS ships neither `timeout` nor `gtimeout`; BSD `grep` has no `-P`;
BSD `date` has no `-d`. Every one was probed on this box.

They were invisible because the shell transport used to answer
`{ stdout: 'mock: command executed' }` for commands it declined to run. That
sentinel died in PR #334 (`3a61bb0f`), which is what exposed this.

## The evidence

- All four `sed -i` shapes the app used: exit 1, `invalid command code`, file
  byte-identical. Photographed.
- 13 of 16 new arms in `src/lib/config-write.e2e.test.ts` RED against
  `origin/master` on this Mac, every failure carrying the literal sed error;
  16/16 green after. The same arms pass on GNU userland before AND after, which
  is why the assertion is the file rather than the exit status — and why no CI
  job could ever have caught this.
- The BUILT app (`next build` → `next start`, `NODE_ENV=production`, real login,
  real Server Actions, sandboxed `CABINET_ROOT` + `CABINET_ENV_PATH`): the config
  write lands, the env write lands, and a field the file does not have returns
  `product.yml has no product.mount_path field, so nothing was changed` while
  leaving the file untouched. Photographed.
- The portability fence goes RED on each of its six rules when the exact defect
  it names is re-introduced, and RED when an allowlist row goes stale.
- Full dashboard suite: 3224 passed, 1 skipped. `tsc --noEmit` clean.
  `check-layer-separation.sh`: no new violations.

## Risk

- `lib/config-write.ts` is new and is now the only writer for `product.yml`,
  the project YAMLs and `cabinet/.env`. It preserves plain YAML style so
  `stability: 0.7` stays a float; it validates the candidate document with the
  same `yaml.load` the READER uses, so it cannot refuse a file the app reads.
- Behaviour change, deliberate: a field that is not in the file is now an ERROR
  rather than a silent success. That is the other half of the same defect (GNU
  `sed` exits 0 on zero matches) and is covered by an arm.
- The config/env writers no longer go through `dockerExec`, so they would have
  dropped out of the no-store refusal. `assertRuntimeWritesAllowed` keeps that
  decision in one place and the existing sweep (`unexecuted-command.test.ts`,
  15 tests) still passes unchanged.

## Deliberately NOT fixed here

- `suspend` / `resume` commit the row and answer `{ok:true}` with the container
  start/stop still a `// TODO`. Honesty needs either a real container transport
  or a changed status code — an API-contract decision, not a patch.
- `lib/library.ts` fire-and-forgets `redis-cli` at `REDIS_HOST` (the compose
  service name) rather than the configured `REDIS_URL`, so the cross-system
  mirror always fails on this deployment and `createRecord` returns the same
  value either way.
- The `/posture` page renders a failed probe as the badge `guardian` rather than
  as unmeasured.

All three are named in `lib/docker.ts`'s scope docstring so the next reader
finds them.
