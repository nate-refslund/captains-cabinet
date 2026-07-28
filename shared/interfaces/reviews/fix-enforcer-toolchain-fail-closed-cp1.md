# Checkpoint review — fix/enforcer-toolchain-fail-closed cp1

Reviewed-Scope-Digest: 738f52f4f8ce2c0ca31abefd1ec3b42e54a024693500f42c8a62f29223c7ddf1

Base: origin/master `8ffeae51e8e24d597e50175021aa25d56235c5ca`
Scope: 10 staged paths, 910 LOC churn.

## The defect

`cabinet/scripts/hooks/pre-tool-use.sh` — the sole PreToolUse authorizer (the
other four PreToolUse hooks carry zero `exit 2` paths) — parses its payload with
`cat | jq` and every gate dispatches on the result. With a required binary off
PATH the parse collapses to empty, no `case`/`if` arm matches, and control
reaches the script's closing `exit 0` = ALLOW.

Measured against `8ffeae51` on a curated PATH, 24 payloads that block on a
healthy toolchain:

| binary removed | payloads leaked (of 24) |
|---|---|
| `jq` | 24 |
| `cat` | 24 |
| `grep` | 16 |
| `perl` | 4 |
| `awk` | 1, plus the spend cap |
| `date` | the spend cap |
| `sed`, `tr` | 0 today, only because §1's kill-switch frame parser also uses them and fails closed first |

Leaked payloads include `sudo rm -rf /`, a `Write` to a germline path, a Bash
append to the Captain-law plane, `chflags noschg` on the hook itself, a
production deploy, a secret read, and an out-of-scope MCP call — all exit 0,
zero bytes on stderr.

Spend cap, measured separately against a scratch Redis with $999,000 recorded
against a $75 cap: `date` absent and `awk` absent both ALLOW; the control
(complete toolchain) blocks.

Not leaking, swept and deliberately excluded: `cut head wc sort uniq od dd
mktemp realpath readlink stat dirname basename tee expr python3`. `python3` and
`mktemp` degrade toward the hardcoded framework caps (a tightening).
`redis-cli` is excluded because §1 already fails closed on its absence with
reads left open (EVAL-001c).

Weaponised form: `cabinet/scripts/start-officer-mac.sh:827` launches officers
with `PATH="$HOME/.local/bin:$PATH"` — officer-writable, ahead of every system
dir. A two-line `jq` that exits 0 and prints nothing allowed 24/24; a `grep`
that always exits 1 allowed 16/24.

## The fix

1. Dependency preflight at the top of `pre-tool-use.sh`: presence (bash builtins
   only), absolute-path resolution (an exported shell function via `BASH_ENV`
   otherwise substitutes itself), and functional probes that run each binary.
   Fails closed with the binary named.
2. Malformed-payload guard: an unparseable `tool_name` is refused.
3. Parse cross-check: the parsed tool name must appear in the raw bytes the
   parser was handed. Cost-raiser, not a wall — declared as RES-021.
4. Lighter preflight in `post-tool-use.sh` (a silently empty audit trail is
   worse than a missing one, and it feeds the spend ledger).
5. `cabinet/tests/hook-regression/dependency-preflight.sh` — 52 arms, wired into
   `run-hook-regression.sh` (a CI-blocking step).
6. `check-deps.sh` records both hooks' sets verbatim; README documents the gate
   and what it does not close; RES-020 and RES-021 registered; the stale CG-17
   line cite re-anchored.

## Independent review

Two fresh-context reviewers, own clones of `origin/master`, patch applied, each
re-running the batteries themselves. **Both returned `reject` on the first
round.** Every blocker is fixed in the reviewed bytes:

| # | Blocker | Fix |
|---|---|---|
| B-1 | Harness wrote 7 keys to the LIVE control plane (one stream, no TTL) under a phantom officer the dashboard then rendered, and appended phantom lines to the real `memory/logs/` audit trail | every run pinned to `$DEAD_PORT` + `CABINET_LOG_DIR` into scratch; arm `HERM-1` refuses to run any other arm until the port is proven closed via bash `/dev/tcp`. Live keys removed. |
| B-2 | Negative controls only asserted a signature was absent, so the harness stayed green while §1 refused every call | `NEG-0` asserts a benign Read is genuinely ALLOWED (exit 0) |
| B-3 | A probe-aware `jq` (real except `.tool_name`) passed every probe and leaked 23/32; the comment claimed the shim channel was closed | claim surface rewritten to say exactly what is and is not caught; parse cross-check added; `ADAPT-1` arm; **RES-021** registered with both real closures named |
| B-4 | `check-deps.sh` described the post-hook set as "the pre-hook's minus perl" — false | both sets recorded verbatim; `WIRE-4` arm pins the post-hook list |
| B-5 | Chain probe had three identity stages (`cat`, `awk '{print}'`, `perl -pe 's/ok/ok/'`) — a passthrough shim satisfied it | every verifiable stage now transforms (A→a→b→B→ok); `LIE-awk-pass`, `LIE-perl-pass`, `LIE-cat-trunc` arms added |
| B-6 | Latency claim "13.5 ms / 2.7%" was the probe timed in isolation | re-measured end to end: +21 ms on a 446 ms hook (+4.7%), +29 ms on a 204 ms hook (+14%) |
| B-7 | `ABS-*`/`LIE-*` iterated a hardcoded dep list, blind to a dependency ADDED to the hook | list derived from the hook itself |

A fourth candidate control — refusing when a dependency resolves through a
directory this uid can write — was implemented and **reverted**: it refuses
every synthetic PATH a hermetic harness can construct, so it would have replaced
a tested control with an untested one. Recorded in RES-021.

## Non-vacuity

The harness re-proves its own detection power on every run (`MUT-0/1/2`: it
strips the preflight from a copy of the live hook and requires the copy to
leak, plus a control proving the environment can produce a refusal at all).

Against pre-change hooks, `__pycache__` purged, `PYTHONDONTWRITEBYTECODE=1`:
**PASS 10 / FAIL 32**. Against the patched tree: **PASS 52 / FAIL 0**.

## Verification re-run on the staged bytes

| command | result |
|---|---|
| `bash -n` on all 6 touched shell files | pass |
| `shellcheck --severity=error --shell=bash` hooks + scripts + new harness | clean |
| `run-hook-regression.sh` | 19/19 harnesses ALL GREEN (new harness 52/0) |
| `run-golden-evals.sh` | 32/32 ALL PASSED |
| `docs-track-code-sweep.sh` | GREEN (files=64 findings=0) |
| `check-layer-separation.sh` | OK, new=0 |
| `ledger-status-parity.sh` | 1 finding (COG-5 stale), **identical on pristine master** — pre-existing, owned elsewhere |
| `pytest cabinet/scripts/tests` | 4950 passed, 34 skipped |
| `pytest framework/tests framework/authority/tests` | green (incl. germline lockstep 371, no-launcher-hardcode 21, amendment-doc-lint) |
| `pytest .../test_declared_residuals_register.py` | 9 passed |
| verdict diff, 30 varied payloads pre- vs post-patch | 0 changed |

Known pre-existing reds reproduced identically on master and not attributable
here: `framework/fidelity/tests/test_retro_shim.py::test_reexports_constants`
(model-id drift) and the COG-5 ledger staleness marker.

## Still open, named not relabelled

- **RES-021** — a probe-aware shim. Registered with both closures.
- **RES-020** — `fw-a14-stop-guard.sh` still drives the dead `stop-hook.sh`
  (10/10 green about a file wired to no event). Registered, untouched.
- **RES-016** — the emergency stop's single channel. Untouched by this change;
  the preflight sits above §1 and changes nothing about how the stop is armed.
- Germline: this changes germline CONTENT, not the germline SET. The landed
  bytes do not reach the live schg-locked tree until a Captain unlock/relock.

VERDICT: approve.
