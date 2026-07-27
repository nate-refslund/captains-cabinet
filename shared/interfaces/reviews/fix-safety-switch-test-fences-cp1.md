# Checkpoint review — fix/safety-switch-test-fences — cp1

Reviewed-Scope-Digest: 6e6a113099c7c5dfec6abf5a5f4005da51caf20a7d29806099129a6075d6c848

## What this changes and why

PR #243 fenced the Python tests that could arm the Captain's emergency stop, and
its docstring named what it could not see: shell tests, raw `redis-cli` writes,
and every other safety switch. Four siblings were reported there and are closed
here. Each was reproduced first, on disposable servers (ports 27311/27412) and a
throwaway checkout. **6379 was never written to.**

| # | sibling | verdict | fix |
|---|---|---|---|
| 1 | `test_tamper_drill.py:323,335` | **reproduced** | tmp pseudo-root + `lib_freeze_fence` |
| 2 | `fw042-v37-adversary.sh:28` (+6 siblings) | **reproduced** | hermetic `fixtures/redis-cli` on PATH; hardcoded write deleted |
| 3 | `test-escalation.sh --live` | **mechanism REFUTED, worse defect found** | pre-flight refusal + endpoint derived from the reader |
| 4 | `CABINET_EVALS_REDIS_DISPOSABLE=1` | **reproduced** | the declaration must now be a property of the ENDPOINT |

## 1. The tamper drill deleted a genuine Captain freeze

`framework.evidence_freeze.freeze` is first-freeze-wins. With a real freeze
armed, the test's own `freeze(_REPO_ROOT, ...)` was a no-op, its
`set_by == "pytest"` assertion failed — and `finally: _thaw(_REPO_ROOT)` lifted
`uchg` and unlinked the **Captain's** marker, bypassing `captain_clear`, the
token-gated unfreeze the marker itself names as the only way out.

Reproduced in a throwaway clone: marker written `set_by="captain"` with `uchg`
set; one single-test pytest run later, `is_frozen` → False, marker gone. Post-fix
the same scenario leaves it byte-identical and the suite is 11/11 green.

`marker_path()` takes an explicit root and reads NO environment variable, by
design (A10 posture) — so there is no knob to redirect and adding one would
weaken the property that docstring claims. The fix is a throwaway root:
`lib_freeze_fence.pseudo_root()` copies the drill (a symlink `.resolve()`s
straight back to the real checkout and would re-aim every write at it) and links
`framework/`, so `Path(__file__).resolve().parents[2]` lands in tmp.

Isolation is proven, not assumed: `assert_isolated` asks the REAL resolvers
where they would write — `evidence_freeze.marker_path` for library calls, and
the drill's own `freeze-status` verb for subprocess calls — and refuses on any
mismatch. `derive_channels` reads the resolver's source and refuses if it has
grown an env channel, so "it takes no env var" cannot silently stop being true.

Assertions about the real checkout became change-detecting (`fingerprint`
before/after). `assert not is_frozen(real_root)` was the wrong sensor: it
asserts the state of a box the test does not own and false-reds where a Captain
freeze is legitimately armed.

## 2. Seven shell harnesses addressed a control plane they do not own

`redis-cli -h redis -p 6379 DEL <key>` — `cabinet:killswitch` in fw042, the CTO
review-gate keys in fw041/043/044/045/051-adversary/051-baseline.

Measured, both halves matter:

- the `redis` hostname does not resolve on this fleet (`gaierror`), so the line
  was a **silent no-op** — rc=1 into `/dev/null`, 0.03s. The arrange step every
  probe depends on had never once run, and the hook under test read whatever
  plane the ambient `REDIS_HOST`/`REDIS_PORT` named — the LIVE one on an officer
  box. Proven: the same probe returns exit 2 or exit 0 purely as a function of
  the ambient plane's switch state.
- where `redis` DOES resolve — the docker network `cabinet/Dockerfile.watchdog`
  builds — it is a live emergency-stop clear. Reproduced against a disposable
  server with resolution simulated by a PATH shim: `active` → cleared.

Fix: the house dialect already used by `evidence-pathnorm.sh` and
`germline-readonly.sh` — `fixtures/redis-cli` (a reachable stub with no keys) on
PATH for every probe, and the hardcoded write deleted. "Key absent" is exactly
the state that `DEL` was reaching for. All seven still pass (rc=0).

The other six are the CTO review-gate family: fail-closed direction, lower
severity, fixed here because the defect and the fix are identical and leaving
them would have left the guard's rule needing an exception list.

## 3. `test-escalation.sh` — the reported mechanism is refuted

**Dissent, on the record.** The reported defect was "the writer uses `REDIS_URL`
while its reader prefers `REDIS_HOST`/`REDIS_PORT`, so they can address
different servers". Measured with two disposable servers, they **cannot**: lines
10-11 unconditionally overwrite `REDIS_HOST`/`REDIS_PORT` from `REDIS_URL`, and
`killswitch-read.sh` is *sourced into that same shell*, so `_ks_endpoint` reads
the overwritten values back. Writer and reader agreed in every arm tried.

Two real defects were found instead, and both are worse:

1. **It clears a genuine Captain stop.** With the switch armed at the endpoint it
   resolves, step 1 reports the mismatch (❌) and the script **carries on**;
   step 6's unconditional `DEL` clears the real emergency stop. Exit 1 at the
   end — damage already done. Same class as sibling 1: a drill that silently
   undoes a Captain decision.
2. **It can test a server the fleet does not use.** With an armed stop on the
   `REDIS_HOST`/`REDIS_PORT` endpoint — what every officer plist exports — the
   pre-fix script reported **9/9 passed** while addressing the `REDIS_URL`
   server entirely. A fully green escalation drill proving nothing about the
   fleet's actual control plane.

Fix: a pre-flight that REFUSES `--live` (exit 64) unless the switch reads
provably CLEAR — covering ACTIVE, UNVERIFIABLE (NOAUTH/NOPERM/WRONGTYPE/LOADING)
and a missing reader — and the endpoint now comes from `_ks_endpoint` itself
rather than a second URL parser, so writer and reader cannot diverge by
construction rather than by accident of shell scoping. Verified: armed → refused
with the stop preserved; clear → 9/9 as before; armed on the reader's endpoint →
now seen and refused.

**Residual, stated:** `--live` still uses raw `SET`/`DEL` rather than
`kill-switch.sh`, so it does not exercise the marker channel or emit flip
events. That is a fidelity gap, not a safety one, now that the pre-flight
refuses over an armed stop.

## 4. The escape hatch now has to prove its premise

`CABINET_EVALS_REDIS_DISPOSABLE=1` was taken on trust — `return 0`, no check.
An env var is a claim about the caller's INTENT, not a property of the server,
and it travels: exported once, inherited by a child, copied from a CI recipe
into a laptop's `.env`. Reproduced: with the flag set and the endpoint holding an
armed `cabinet:killswitch` plus live fleet state (`cabinet:officer:expected:*`,
`cabinet:triggers:*`), `evals_redis_sandbox_start` returned 0 and the suite's
`SET`/`DEL` shape cleared the stop.

**Ruling: kept, but the endpoint must now agree.** Deleting it was the
alternative and it fails on the facts — the GitHub runner image has `redis-cli`
but no `redis-server`, so with no hatch the suite could not sandbox and CI could
not run the evals at all. Three arms before it may return 0:

1. the endpoint answers PING — an endpoint nobody can reach cannot be proven to
   be anything;
2. `cabinet:killswitch` is ABSENT — the suite `SET`s and unconditionally `DEL`s
   it, and the 2026-07-15 lockdown found inactive on 07-16 is this exact shape;
3. the endpoint itself carries `cabinet:evals:disposable`. Provisioning a
   throwaway means declaring it AT the throwaway, so the claim cannot arrive by
   inheritance from another shell.

CI sets the marker on its service container in one step, in the two jobs that
declare disposability. `fw-002-spending-limits.sh` sources the same helper
rather than keeping a second copy that drifts.

**Honest limit:** (3) is a convention, not a cryptographic proof. Someone who
deliberately writes that marker onto a live control plane has declared it
disposable and this code believes them. What it removes is the ACCIDENT.

Matrix, fixed vs pre-fix (`rc`): no marker 1/0 · marker + armed stop 1/0 ·
marker + clear 0/0 (the CI shape, unaffected) · unreachable 1/– · flag unset
0/0 (still spawns its own ephemeral redis).

## The guard, and what it still cannot see

`test_safety_switch_test_fence.py` extends coverage to the two things the
predecessor's guard was structurally blind to.

**The rule is about the endpoint, not the key.** A key list is the drift that
caused the original incident and would have covered fw042 while leaving its six
identical siblings open. So: *a test may not address a redis endpoint by
hardcoded literal* — loopback on a port the test chose is a sandbox; a named
host, or the live port as a bare literal, is somebody else's server.

The freeze rule is about the ARGUMENT — a write verb handed something that
resolves to a real checkout — because `framework/tests/` cannot import a
`cabinet/` test library without breaking layer separation, so "must import the
fence" cannot be the repo-wide rule. A second, stricter arm requires the fence
inside `cabinet/`. Writing that rule found two further freeze writers
(`framework/tests/test_evidence_phase4_seams.py`,
`test_evidence_recompute.py`); both pass tmp roots and are safe as they stand.

Non-vacuity, verified at `ff011924` with caches purged — all five substantive
arms RED, naming the exact lines (`323`, `335`) and all seven shell files; the
two green ones are the synthetic detector arms, which must pass in both trees
because they test the detector rather than the tree:

- structural endpoint arm — names all 7 harnesses with line numbers;
- structural real-root arm — names `ef.freeze(_REPO_ROOT, ...)` and `_thaw(_REPO_ROOT)`;
- structural fence arm — names `test_tamper_drill.py`;
- behavioural freeze arm — "A TEST DELETED AN ARMED JUDGING FREEZE";
- behavioural shell arm — "A SHELL TEST CLEARED AN ARMED EMERGENCY STOP", while
  the harness itself printed PASS on every probe.

Both behavioural arms **poison the environment deliberately**, because on a
fresh checkout and a clean env — every CI runner — neither defect can fire: no
freeze is armed to destroy, and the `redis` hostname does not resolve. The
shell arm shims the resolver so the hardcoded hostname resolves, which is the
watchdog container's real deployment, not a contrivance.

**WHAT IT DOES NOT SEE** (in the docstring too):

- runtime-composed endpoints — a host/port assembled from variables reads as a
  variable; only the behavioural arm catches those, and only for what it runs;
- only fw042 runs behaviourally (~20s); the six CTO-gate harnesses are
  structural-only, because running all seven costs minutes in a unit-test job;
- other safety switches — observe-only, captain-vetoes, the act-first kind
  freeze — have no arm here;
- the dashboard TypeScript suite is not scanned;
- `test-escalation.sh --live` writes the real switch BY DESIGN and is fenced by
  its own pre-flight, not by this guard;
- executable lines only — a full-line comment naming a literal endpoint is
  prose, and the comments explaining this fix would otherwise trip the guard
  that polices them.

## Proof that 6379 was never written

Read-only snapshot before any work: `DBSIZE` 60, `cabinet:killswitch` absent,
sorted `KEYS *` sha256 `99387f78dc39e7d0...`. Every reproduction ran against
27311/27412, both started by this session with `--save '' --appendonly no`. The
live fleet writes its own keys continuously, so the after-snapshot is compared
by attribution, not by expecting an identical number — see the closing section
of the PR body for the after-reading and its explanation.
