# Task-adapter authoring kit

How ANY external tracker (Jira, Linear, Asana, GitHub Issues, or one that
does not exist yet) gets a Cabinet task-sync adapter — the request flow for
a captain, the build flow for an officer, and the machine gates that keep a
half-built adapter from ever lying to the fleet. Product- and
captain-agnostic by construction: nothing here names a specific deployment.

Surfaces this runbook owns (Docs-Must-Track-Code — update together):

| Surface | Path |
|---|---|
| Contract + registry | `cabinet/scripts/task_adapters/base.py` (`TaskAdapter`, `ADAPTER_REGISTRY`) |
| Scaffold to copy | `cabinet/scripts/task_adapters/_template.py` |
| Working model | `cabinet/scripts/task_adapters/reference_inmemory.py` |
| Conformance suite | `cabinet/scripts/task_adapters/conformance.py` (+ `conformance_fixtures.py`) |
| CI teeth | `cabinet/scripts/task_adapters/tests/test_conformance.py` |
| Sync runner | `cabinet/scripts/task_sync_runner.py` via `cabinet/cron/task-sync.sh` |
| Drift falsifier | `cabinet/scripts/task-sync-drift-falsifier.py` (incl. its `_LINKED_KIND_BY_DESTINATION` map — every new tracker adds its row, see §2 step 6) |
| Fleet rows | `cabinet/services.yml` (`task-sync` 900s, `task-sync-drift` nightly 04:20) |
| Doctor probe | `cabinet/scripts/cabinet-doctor.sh` check 12 (`--probe`) |

## 1. Captain requests a tracker

A captain never writes adapter code. The request is one config intent:

1. Say the word (any surface that reaches the org — chair DM, intake, a
   backlog line): *"sync tasks for project X to <tracker>"*.
2. The org checks `ADAPTER_REGISTRY` in `base.py`:
   * **Registered + `implemented=True`** → ops wires config only (step 3).
   * **Registered + `implemented=False`** → the skeleton exists; an officer
     runs §2 to finish it. The runner will NOT fake it meanwhile: skeleton
     pulls raise `NotImplementedError` and are logged as errors, and
     `health_check()` stays `False` by contract.
   * **Not registered** (new tracker) → an officer runs §2 from the
     template.
   * **Monday** → plugin-routed, deliberately: the factory refuses with the
     dev-tasks-plugin pointer. Do not rebuild a Monday adapter.
3. Config lands in `instance/config/projects/<slug>.yml` (instance layer —
   never in framework files):

   ```yaml
   tasks:
     system: <registry-slug>        # e.g. github-issues
     auth_env: TRACKER_API_TOKEN    # optional RENAME of the env VAR
     config:                        # adapter-specific, see its docstring
       repo: owner/name
   ```

   Credentials: the VALUE goes in `cabinet/.env` under the named var —
   config carries NAMES only. A token pasted into YAML is ignored by
   `auth_token()` (conformance check C5 pins that) and is a leak to scrub.
4. Nothing else to schedule: the `task-sync` services row already runs
   every 15 min (loud-degrade no-op until a tasks block exists) and the
   nightly `task-sync-drift` falsifier starts sampling the new mirror
   automatically. `bash cabinet/cron/task-sync.sh --health` is the smoke
   test.

## 2. Officer builds the adapter

1. **Copy the scaffold**: `cp _template.py <system>.py` inside
   `cabinet/scripts/task_adapters/`. Every method's docstring carries its
   contract (upsert-by-`canonical_id`, canonical-wins, idempotent delete,
   link writes the external half). Keep them honest while unfinished:
   `NotImplementedError`, `health_check() → False`.
2. **Register immediately** — an unregistered adapter module is a red CI
   (the module scan in `test_conformance.py`). Add an `AdapterSpec` row to
   `ADAPTER_REGISTRY` with `implemented=False` while building.
3. **Security contract** (base.py header, conformance-enforced):
   * tracker text is UNTRUSTED — subprocess argv lists only (text as a
     single element), no `shell=True`, no `os.system` (C6 AST-scans your
     module), never interpolated into SQL/jq, never eval'd;
   * creds ONLY from env; never in logs, repr, or exception text (C5
     plants sentinels and greps everything you emit).
4. **Rate limits**: raise `RateLimitedError` from your transport on
   429-class replies and route calls through `self._with_backoff(...)` —
   C4 verifies growing, capped, BOUNDED retries on an injected fake clock.
5. **Write the conformance fixture** in `conformance_fixtures.py`: fake
   your transport at its narrowest seam, in-process (the reference adapter
   injects a tracker double; the gh fixture patches the module's
   `subprocess.run` with an argv-level emulator — no network in tests).
   Implement `read_external` / `tamper_external` / `arm_rate_limit`. If
   your transport cannot DETECT out-of-band edits, say why in
   `conflict_detection_note` (visible debt) — canonical-wins overwrite is
   still mandatory.
6. **Map the drift falsifier**: add `<registry-slug> → <officer_tasks.
   linked_kind>` to `_LINKED_KIND_BY_DESTINATION` in
   `cabinet/scripts/task-sync-drift-falsifier.py`. The nightly drift check
   REFUSES to guess: an unmapped destination whose canonical rows carry a
   `linked_kind` is a loud `error` verdict (exit 1, doctor AMBER) — never a
   cross-tracker comparison that would manufacture false presence drift
   and a false captain card.
7. **Flip the switch**: set `implemented=True` + `conformance_fixture=`
   your fixture path, then:

   ```
   python3.12 -m pytest cabinet/scripts/task_adapters/tests -q
   ```

   CI runs the same suite (`Cabinet task-adapter tests` step). Red until
   C1–C6 all pass; the `_template` negative control and the in-memory
   reference positive control keep the suite itself honest.
8. **Docs track the code**: adapter docstring (config keys, mapping
   table), this runbook's table if surfaces moved, same commit.

## 3. What watches it in production

* **`task-sync` row** (900s): `task_sync_runner` pull cycle. No tasks
  block / plugin-routed → ONE `INFO … clean no-op` line, exit 0 — the
  loud-degrade IS the healthy state on adapter-less deployments.
* **`task-sync-drift` row** (nightly 04:20): samples N canonical rows
  (`officer_tasks` via one constant read-only SELECT, or the
  `TASK_SYNC_DRIFT_CANONICAL_JSON` seam) against `adapter.pull()`, appends
  one verdict line to `cabinet/logs/task-sync-drift.jsonl` (runtime,
  gitignored). All-NoOp fleet → honest `no-adapters-configured`, exit 0.
  `canonical-unreadable` (exit 0) means NOT CONFIGURED only — no psql/conn
  string and no seam on the box; a CONFIGURED canonical store whose read
  FAILS (rotated credential, dead DB, garbage output) is `error`, exit 1,
  doctor AMBER: credential rot must never park the watchdog green.
* **Doctor check 12** (07:10): reads the latest verdict via `--probe`.
  Escalation ladder:
  1. first `drift` verdict → doctor AMBER + self-heal hint — run
     `bash cabinet/cron/task-sync.sh`, then
     `python3.12 cabinet/scripts/task-sync-drift-falsifier.py`; a passing
     line clears the AMBER the same day;
  2. drift again on the next distinct date → the FALSIFIER files one
     captain card through the attention gateway and stamps `escalated` on
     the line. The doctor never sends anything (read-only by contract);
     same-day re-runs never escalate — they are the self-heal attempt.

## 4. Retiring an adapter

Flip its registry row to `implemented=False` only if the implementation is
actually being torn down (the skeleton checks then re-arm); removing a
tracker from a project is just deleting the `tasks:` block — the runner
degrades to the clean no-op on the next 15-min tick. Never delete the
registry row of a shipped adapter without superseding notes in the module
docstring (same discipline as services.yml rows).
