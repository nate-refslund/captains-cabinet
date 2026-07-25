# FW-019 checkpoint review — feat/captain-contact-liveness (cp1)

Base: `138a253236fd79be519a0771f59ab1aeb1e664c7` (master).
Requirement of record: `DESIGN-REQ-captain-contact-liveness-2026-07-25.md` (D1, D4-cheap, X).

## The question this branch answers

Can a cabinet notice it has stopped talking to its Captain? On master: **no.** It
can notice that *machinery* stopped. Every health signal is produced and consumed
inside the same failure domain, so the system can only report on itself.

## Premise check against master (not the archived runtime tree)

Each defect verified to exist on the base SHA before any code was written.

| Premise | Verdict on master | Evidence |
|---|---|---|
| Manifest carries zero officer rows; doctor merges the roster, watchdog does not | **TRUE** | `grep -c 'kind: officer' cabinet/services.yml` = 0; `cabinet/scripts/cabinet-doctor.sh:200` merges `lib_roster.officer_service_rows`; `framework/watchdog/registry.py:1000` derives `officer_labels` from manifest rows only |
| Freshness floor returns nothing for `keepalive` | **TRUE** | `framework/watchdog/registry.py:739` — `return None  # keepalive / unknown schedule` |
| Delivery check asserts producer-side artifacts | **TRUE** | `registry.py:431` reads the Chair-stamped marker; `registry.py:456` `sent = bool(send.get("sent"))`; slot-scoped, never elapsed-scoped |
| A "last Captain message" key is defined and never read; holds an id | **TRUE** | defined `registry.py:248`, zero readers; the only read is `channel.py:208`'s own private copy for reply threading; written as `str(message_id)` at `officer-inbound-poller.py:951` |
| Findings truncated to first eight in append order, not-loaded appended last | **TRUE** | `registry.py:1119` `shown = problems[:8]`, not-loaded loop at `:1112` runs after the exit-status loop |
| Send succeeds with no live consumer; wake's result discarded; undelivered page still sets a cooldown | **TRUE** | `triggers.sh:182-188` rc0 on XADD; wake fully detached at `triggers.sh:106/153` with `tmux has-session … || exit 0` at `:112`; `check.py:225` returns True on clean stderr; `check.py:337-342` sets a 3h cooldown (`COOLDOWN_S`, `check.py:76`) on that basis |

**One correction to the requirement doc.** It reasons that the officer hole is
closed by mirroring the roster into the watchdog. That is right in principle but
`cabinet/services.yml:100-113` asserts the opposite — "zero rows here is already
a covered case, not a gap" — reasoning from the `com.cabinet.officer.` prefix
exclusion. That inference is false (an exclusion is not coverage), so the doc's
finding stands; the manifest comment is the thing that is wrong.

## What landed

**D4-cheap (built first — D1 has nothing truthful to fire on without it).**
`trigger_consumer_state` in `cabinet/scripts/lib/triggers.sh` reports
`live|absent|unknown` with no side effects; `trigger_send` exports
`TRIGGER_SEND_DELIVERY`. **Return code, stderr and durability semantics are
byte-identical** — an absent consumer is not a send failure, and changing rc
would break every callsite. `check.py::trigger_chair` records the state on a
`getattr`-defaulted side channel and `route_failure` withholds the cooldown when
it is `absent`, so an unread page re-escalates next sweep instead of buying three
hours of silence. `unknown` deliberately preserves prior behaviour: a detector
that cannot see must not invent a verdict.

**D1 outbound.** `framework/liveness/deadman.py` — stdlib-only, inert by default,
instance-scoped, non-raising; the HTTP call is inlined rather than importing the
probe helpers, because the probes are themselves watched services. Fired from
`channel.py::_send_impl` at the confirmed-delivery return, unreachable from
blocked-dev, killswitch-refused, and partial-multipart paths.

**D1 inbound + the blocked check.** `record_captain_contact` in the poller writes
the ISO-8601 sibling `cabinet:last-captain-msg-at` beside the untouched id key and
emits the inbound heartbeat. `registry.py` gains `verify_captain_inbound_contact`
plus the recency gate the watchdog's author described and could not write.

**X.** Findings carry a causal severity and are stably sorted before truncation,
so the line naming the cause survives a broad outage. Message text unchanged.

## Deliberately not done, and why

* **Officer roster mirror (scope item 4) — REVERTED, handback.** Closing it
  requires comparing launchctl against a declared set (a booted-out label simply
  vanishes). Doing so contradicts three existing fixtures that assert
  `res.ok is True` while modelling a fleet whose rostered officers carry no
  LaunchAgents: `test_cron_unrostered_officer_label_not_flagged`,
  `test_cron_running_job_prior_exit_status_ignored`,
  `test_cron_disabled_row_fully_excluded`. Reported rather than resolved by
  editing them — the fixtures may encode a real topology. Reasoning is recorded
  in-place at the scan site.
* **`captain-inbound-contact` ships STAGED DARK.** Enabling it changes the
  enabled-row count, which `test_full_run_with_fake_probe_routes_only_failures`
  and `test_watchdog_this_deployment_enables_original_rows_phase4_dark` pin at 5.
  Appended at the end of the catalog so `catalog[:5]` keeps its meaning; arming
  is one uncommented line, exactly as the Phase-4 evidence rows do it.
* D2 generalised keepalive heartbeats, D3's external sink, full consumer-lag
  assertion — out of scope, not half-built.

## Doctrine

The no-direct-to-Captain alert tier (`registry.py:69-71`, P-Alerts-To-Chair) is
**not** overturned. Operational alerts still route to the Chair. What is added is
an *absence* detector living outside the lane, whose alarm is raised by an
off-machine watcher, not by the cabinet. No new alert tier exists inside the
cabinet.

## Verification (re-measured baseline, not a quoted number)

| Battery | Master baseline | This branch |
|---|---|---|
| `pytest framework/` | 1 failed, 6433 passed, 25 skipped | 1 failed, **6489** passed, 25 skipped |
| `pytest cabinet/scripts/tests` | 3401 passed, 12 skipped | **3412** passed, 12 skipped |
| `test-triggers.sh` | 47 pass / 0 fail | **55** pass / 0 fail |
| layer separation | new=0 | new=0 |
| clean-room foundation | 24 passed | 24 passed |
| golden evals | 29/29 | 29/29 |
| docs-track-code | GREEN (0 findings) | GREEN (0 findings) |
| ledger status parity | GREEN | GREEN |
| architecture census | PASS | PASS (zero headroom) |

The single `framework/` failure is **pre-existing on master and environment-local**:
`test_retro_shim` pins `claude-sonnet-4-6` while this machine's
`~/.screenpipe/pipes/retrodiction/lib.py` now says `claude-sonnet-5`. CI has no
such file. Unchanged by this branch, not touched.

Architecture budget raised the sanctioned way — two `temporary_allowances` rows at
**exact measured** totals (+2 modules, +386 non-comment lines), matching the
zero-headroom `observed == max` law. No maximum was relaxed.

## Non-vacuity (both directions, cache purged)

Every new arm was run against the pre-change source:

* `test_contact_liveness.py` vs master `registry.py`+`check.py` → **12 failed, 6 passed**; the 6 are deliberate no-regression controls that must pass on both sides.
* `test_channel_contact_heartbeat.py` vs master `channel.py` → **2 failed** (the two firing arms), 7 passed (the silence/fail-direction arms, which hold on both sides).
* `test_inbound_poller_captain_contact.py` vs master poller → **11 failed**.
* new `test-triggers.sh` arms vs master `triggers.sh` → `trigger_consumer_state: command not found`, `TRIGGER_SEND_DELIVERY: unbound variable`.
* `test_deadman.py` (new module, so absence-failure is weak evidence) → four targeted **mutations** of the load-bearing guards, each reddening exactly its own arm: drop the instance guard → 1 failed; drop the scheme guard → 4 failed; drop the slug guard → 5 failed; fire despite a not-ready resolve → 19 failed.

## Residual risk

The local inbound check shares a failure domain with most of what it watches and
is documented as the *second* leg, never the detector. The primary is the
off-machine dead-man, which is **inert until an operator configures it** — this
branch ships the mechanism and a template, not an activation. Until a watcher is
registered, the literal question still has no live answer in production.
