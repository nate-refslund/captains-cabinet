# Declared residuals register

**LIVING surface** (undated by design, like `EXECUTION-STATUS.md` was before it
froze). One row per residual the program has DECLARED but not closed.

Machine-pinned by `cabinet/scripts/tests/test_declared_residuals_register.py`:
a row cannot outlive its declaration in the tree, and a declaration cannot
appear in the tree without a row. Neither half is advisory.

**Provenance:** authored per the 2026-07-07 full-autonomy grant.

## Why this file exists

Honest scope statements are the program's strongest habit: a fix lands, and the
author states plainly which channel is closed and which is not. Those
statements are load-bearing — and until now they lived only where they were
written: a lib docstring, a frozen review artifact, a dated PARK marker, an
orchestrator board outside this repo. A residual declared in three places and
registered in none is one refactor away from becoming a silent assumption. The
next phase's frozen review panel is meant to INHERIT these, not rediscover
them.

This register is the single place a panel, an integrator, or a fresh Captain
reads to learn what the program knows it has not closed.

## Home — why `docs/plans/`

- `shared/interfaces/` is **fail-closed at egg export**: `t_interfaces_header_only`
  (`cabinet/scripts/egg-export.sh:184-195`) fails the export on any file outside
  the four-name allowlist. Landing the register there would break packaging and
  force an edit to `cabinet/scripts/egg-export-manifest.txt` — a file bound by
  the frozen COG-4 review digest.
- `docs/plans/` needs no manifest change: `t_plans_archive`
  (`cabinet/scripts/egg-export.sh:198-210`) keeps three named normative specs
  and archives everything else (R145), so this register stays with the source
  instance automatically — correct, since it names instance-specific hosts,
  ledger rows and Captain windows.

The pin test therefore carries the **double-key export tolerance** already used
by `cabinet/scripts/ledger-status-parity.sh:76-88`: register absent AND
`docs/plans/ARCHIVED-NOTE.md` present ⇒ skip loud (an export cut); register
absent WITHOUT the archive marker ⇒ hard fail (source rot).

## Marker convention — surveyed, not invented

Survey over the tree at `a1357829` (whole repo, case-sensitive):

| candidate form | occurrences | verdict |
|---|---|---|
| `DECLARED RESIDUAL` | 0 | not in use — rejected |
| `HONEST SCOPE` | 0 | not in use — rejected |
| `known limitation` / `KNOWN LIMITATION` | 0 | not in use — rejected |
| `RESIDUAL` (uppercase word token) | **8 sites in 6 files** | **ADOPTED** |
| `RETIREMENT CONDITION` (uppercase) | 56 | adopted as the row FIELD name |
| `PARKED` / PARK marker | 4 dated `docs/plans` markers | adopted as a declaration form |
| `residual` (lowercase, prose) | 208 in 88 files | rejected as a marker (see limits) |

The uppercase token appears in three qualifier forms — bare `RESIDUAL:`,
`HONEST RESIDUAL:`, `KNOWN RESIDUAL` — so the convention is the **word token**,
not a fixed prefix:

```
(?<![A-Za-z0-9_])RESIDUALS?(?![A-Za-z0-9_])
```

The lookarounds are load-bearing: they exclude identifiers that merely contain
the word (`_TEMPORARY_RESIDUALS` in `framework/tests/test_no_launcher_hardcode.py`,
`RESIDUAL_NOTE` in `cabinet/scripts/evidence-tamper-drill.py`), which are
mechanisms, not declarations.

`RETIREMENT CONDITION` is the repo's existing name for "what closes this" (56
uses, e.g. `cabinet/scripts/tests/test_cog5_league_ast_pin.py:22`), so this
register's retirement field carries that name rather than a new one.

## Sweep surface

The pin test sweeps **tracked** files under `framework/`, `cabinet/`,
`instance/`, `shared/` (git-tracked when a work tree is available, filesystem
walk otherwise), excluding:

- `shared/interfaces/reviews/` — an append-only archive of FROZEN review
  artifacts; the COG-4 one is digest-bound (`cabinet/scripts/cognitive-phase4-review-scope.py`),
  so its bytes may not be reworded to satisfy a sweep. Rows may still CITE it.
- `cabinet/scripts/tests/test_declared_residuals_register.py` — the file that
  defines the marker cannot be a subject of it (the self-exclusion idiom
  `framework/tests/test_no_launcher_hardcode.py` uses for its own pattern list).
- `docs/` — narrative planning prose. Rows CITE docs (the PARK markers below);
  the sweep does not police prose.

Everything in the sweep surface is bidirectionally bound: a marker there must
have a row, and a row citing there must sit on a marker line.

## How to add a row

1. Declare the residual where the code lives, using the word token —
   `# RESIDUAL: <what stays open>`.
2. Add a `### RES-nnn` block below with every field filled.
3. Both in the SAME commit. The pin test fails the commit that does only one.

Retiring a row: land the fix, delete the marker from the code, flip
`**Status:**` to `retired`, and say in `**Retirement:**` what landed. The pin
test refuses a `retired` row whose marker is still in the tree.

## Rows

### RES-001 — Spending-cap SOURCE files are officer-writable

- **Phase:** hardening loop — hook-enforcement audit C17 (2026-07-12), Finding B
- **Status:** open
- **Closed:** the `/tmp` enforcement-CACHE poisoning vector in the pre-tool-use hook. The cap is recomputed from source YAML on every call into an unpredictable per-invocation `mktemp` file (random name, `O_EXCL`, 0600, written-read-deleted in-process), so no persistent trusted state remains for a same-UID officer to pre-plant or race.
- **Open:** `instance/config/platform.yml` and `framework/defaults/spending-limits.yml` are themselves officer-writable — not schg-locked, not matched by the hook's `GERM_PATH_RE` — so a determined officer can still edit the SOURCE cap.
- **Why open:** the declaration names it a SEPARATE finding needing its own captain-gated ledger row; source integrity for the spend/peers/contexts configs is a distinct exposure from the cache vector this patch closed. Closing it means putting two config files under the immutable-flag boundary, which only a Captain sudo window can do.
- **Declared at:** `cabinet/scripts/hooks/pre-tool-use.sh:388`
- **Anchor:** `RESIDUAL (SEPARATE finding`
- **Retirement:** a Captain unlock window brings `instance/config/platform.yml` and `framework/defaults/spending-limits.yml` under the schg set (`cabinet/scripts/germline-lock.sh` FILES[]) and into the hook's `GERM_PATH_RE`. In the SAME commit: delete this declaration block from `cabinet/scripts/hooks/pre-tool-use.sh`, and flip this row to `retired`.

### RES-002 — Captain's personal CLAUDE.md body still loads into officer sessions

- **Phase:** AUD-1 (CLAUDE_CONFIG_DIR officer isolation, 2026-07-07)
- **Status:** open
- **Closed:** officers boot from a dedicated config home with OAuth intact (`CLAUDE_SECURESTORAGE_CONFIG_DIR` set-to-empty federates the keychain item instead of duplicating it); the 58KB `@screenpipe-memories.md` dossier import does NOT load (external-includes gate unapproved in the fresh home); no credential or config assignment is typed into tmux pane history.
- **Open:** the ~3KB BODY of the Captain's personal `~/.claude/CLAUDE.md` still loads via Claude Code's cwd ANCESTOR walk, because the repo lives under `$HOME`.
- **Why open:** `CLAUDE_CONFIG_DIR` cannot gate an ancestor walk, and `CLAUDE_CODE_DISABLE_CLAUDE_MDS` was rejected — it would kill the repo's own cabinet-law `CLAUDE.md` too. The two real fixes are outside this layer.
- **Declared at:** `cabinet/scripts/start-officer-mac.sh:474`
- **Anchor:** `KNOWN RESIDUAL (documented in the AUD-1 ledger row)`
- **Retirement:** either (a) the Captain moves personal content behind imports on a non-ancestor path, or (b) an upstream ancestor-walk opt-out ships — both named in the AUD-1 note (`docs/plans/operative-egg-ledger-2026-07-07.yml`, row `AUD-1`). Whichever lands: delete this declaration block from `cabinet/scripts/start-officer-mac.sh`, update the AUD-1 note, and flip this row to `retired` in the SAME commit.

### RES-003 — hatch tracked-platform.yml guard is clean-room-scoped only

- **Phase:** hardening C11 (2026-07-11), Brief 1
- **Status:** open
- **Closed:** a `--clean-room` hatch run inside a git work tree whose `instance/config/platform.yml` is tracked with a real deployment config (>50 lines) is REFUSED, exit 64 — with the throwaway-export escape (`git archive HEAD | tar -x`) and an explicit `HATCH_ALLOW_TRACKED_INSTANCE=1` override documented in place.
- **Open:** a plain, NON-clean-room hatch run from such a checkout still rewrites the tracked `platform.yml` in place.
- **Why open:** the declaration states the scope decision outright — in-scope containment per hardening Brief 1 was clean-room only. It is a deliberate scope boundary, not an oversight.
- **Declared at:** `cabinet/scripts/hatch.sh:61`
- **Anchor:** `KNOWN RESIDUAL SEAM (2026-07-11 verify`
- **Retirement:** the guard is lifted out of the clean-room branch so every hatch path refuses to rewrite a tracked `platform.yml` (or hatch stops writing tracked instance config at all). In the SAME commit: delete this declaration block from `cabinet/scripts/hatch.sh`, extend the hatch regression suite with a non-clean-room arm, and flip this row to `retired`.

### RES-004 — egress raw-socket containment has no Linux/Docker equivalent

- **Phase:** egress boundary (framework default; coverage-vs-residual in `docs/runbooks/egress-allowlist.md`)
- **Status:** open
- **Closed:** on macOS, proxy env vars catch curl, python-requests and every MCP/client that honours them, and a Seatbelt rule denies direct external TCP/UDP so raw-socket bypasses fail at the kernel boundary. The guard is fail-closed: if the proxy cannot be installed or verified it errors non-zero and installs NOTHING.
- **Open:** Linux/Docker has no Seatbelt equivalent at this layer, so raw sockets there need a host/container network policy; existing sessions require a restart to pick the boundary up; localhost services remain outside the officer boundary.
- **Why open:** there is no in-process, kernel-level equivalent this layer can install on Linux/Docker — the containment must come from the host or container runtime, which the cabinet does not own.
- **Declared at:** `framework/defaults/egress.yml:33`
- **Anchor:** `HONEST RESIDUAL: Linux/Docker has no Seatbelt equivalent`
- **Retirement:** a Linux/container network policy ships with the deployment path AND `cabinet/scripts/egress-guard.sh` verifies it (its current `residual:` advisory line, `:1227`, becomes an assertion). In the SAME commit: delete this declaration block from `framework/defaults/egress.yml`, update the coverage-vs-residual section of `docs/runbooks/egress-allowlist.md`, and flip this row to `retired`.

### RES-005 — calendar undo reports ok on a 0-match AppleScript delete

- **Phase:** front-door undo — EventKit fast-path consolidation (2026-07-07)
- **Status:** open
- **Closed:** the fast path (`calendar_delete.delete_event`) returns only on a CONFIRMED delete and raises otherwise; on ANY fast-path failure the AUTHORITATIVE AppleScript delete runs against the same uid space; if BOTH fail the reverse reports `ok:False` → `reversal_failed` → `manual_cleanup`, never a false success. That is the safety-critical undo-honesty invariant, and it holds.
- **Open:** the AppleScript fallback returns `'ok'` on a 0-MATCH — the uid no longer resolves (e.g. iCloud rewrote it) — so "nothing to delete" is reported as "deleted".
- **Why open:** the declaration calls it pre-existing and irreducible for a uid-keyed delete: a uid-keyed reverse cannot distinguish "already gone" from "never findable under this uid". Closing it needs a different identity, not a better check.
- **Declared at:** `framework/frontdoor/action_undo.py:581`
- **Anchor:** `RESIDUAL: the AppleScript fallback returns 'ok' on a`
- **Retirement:** EventKit-native CREATE lands so events carry a stable `eventIdentifier` and the reverse keys on it rather than a uid. In the SAME commit: delete this declaration block from `framework/frontdoor/action_undo.py`, and flip this row to `retired`.

### RES-006 — an uncalibrated judge can still feed cluster demotion

- **Phase:** judge-calibration gate — cross-lane wire, closure wave (2026-07-05)
- **Status:** open
- **Closed:** the sharpest tooth. An uncalibrated machine judge cannot wield the `DIRECT_DEMOTE_REF` single-row direct demote that graduation B2.9 consumes; the `verdict_judge` row is still emitted (gating the emit entirely would deadlock calibration forever), and the gate is fail-closed — it never raises and reads False on any error or missing proof, so an unreadable calibration state suppresses the marker.
- **Open:** an uncalibrated judge's plain `wrong` verdict can still contribute to graduation's soft ≥2-in-10 CLUSTER demotion, because that count is source-blind in the graduation layer.
- **Why open:** the graduation layer is schg-locked, and fully gating this needs a graduation-side `verdict_judge`-source filter there — deferred to a germline wave. The declaration also states why it is tolerable meanwhile: it is the SAFE direction (a spurious demote only makes a cell propose-only), so the residual is low-risk, not silent.
- **Declared at:** `framework/probes/verifier.py:61`
- **Anchor:** `(the safe direction). RESIDUAL`
- **Retirement:** a germline window adds the graduation-side `verdict_judge`-source filter to the cluster-demotion count. In the SAME commit: delete this declaration block from `framework/probes/verifier.py`, and flip this row to `retired`.

### RES-007 — COG-4 shadow-log replay window (binds the FUTURE cutover amendment)

- **Phase:** COG-4 — frozen phase review, finding P1 (NOTE)
- **Status:** open
- **Closed:** everything that matters in shadow. Replay refusal is real for a single process (`idempotency_replay`, panel double-run probe); row-carried idempotency keys are never trusted (the key is re-derived); the log itself cannot corrupt — `append_shadow_log` takes an `O_EXCL` lock, writes an `O_EXCL` tmp, fsyncs and `os.replace`s, and losers fail LOUD.
- **Open:** `replay_keys` are READ before that lock is taken (`cabinet/scripts/cog4-dispatch-shadow.py:858-863`, versus the lock at `:625-658`), so two dispatchers racing one log could each record `would_dispatch` for the SAME idempotency key.
- **Why open:** zero effect surface exists this phase — nothing dispatched in shadow reaches the world, so a doubled `would_dispatch` RECORD is the entire blast radius. The review disposition is explicit: not ship-blocking in shadow, and it binds the future cutover amendment rather than this phase.
- **Declared at:** `shared/interfaces/reviews/cognitive-core-phase-4-review.md:233`
- **Anchor:** `Shadow-log replay window`
- **Retirement:** the cutover amendment REQUIRES read+check+append under one lock, and `cog4-dispatch-shadow.py` (or its cutover successor) implements it, before any dispatch becomes real. In the SAME commit as that amendment landing: flip this row to `retired` and record the implementing commit here. Until then this row is the carrier — the review artifact is digest-bound and frozen, so it cannot be updated in place.
- **Note:** this residual is declared in a FROZEN review artifact and has no in-code marker. Registering it here is the only reason it survives a refactor of the dispatcher.

### RES-008 — COG-4 W1 u3: officer-plist instance leakage NOT cleaned up (PARKED)

- **Phase:** COG-4 W1 u3 — parked 2026-07-23 (contract §9.1, in-contract park)
- **Status:** open
- **Closed:** nothing was silently skipped. The unit produced a dated PARK marker with the full blast-radius analysis, a byte-verified dependency map, and a corrected path forward; no officer plist was deleted, moved or regenerated, and no live-runtime, germline or launchd file was touched.
- **Open:** three concrete-slug officer plists remain committed in the framework tree — `cabinet/launchd/com.cabinet.officer.{cos,cos-inbound,comms-officer}.plist` — instance leakage against the 2026-07-14 roster-derivation doctrine (`com.cabinet.officer.template.plist` is the legitimate template and stays).
- **Why open:** deleting the checked-in cos-inbound plist would BRICK the Captain's receive path. `cabinet/scripts/start-officer-mac.sh:357` suppresses `--channels` iff the repo-tracked `com.cabinet.officer.<officer>-inbound.plist` exists; delete it and the next cos restart flips to `--channels` → a second `getUpdates` poller on the Chair bot token → Telegram 409. Prior art for the same dependency: ledger row R067.
- **Declared at:** `docs/plans/cog4-w1-u3-officer-plist-cleanup-PARKED-2026-07-23.md:1`
- **Anchor:** `officer-plist instance-leakage cleanup`
- **Retirement:** re-point the `start-officer-mac.sh` inbound check at the INSTALLED poller under `~/Library/LaunchAgents/` FIRST, then relocate `cos`/`cos-inbound`/`comms-officer` to the instance/deploy surface and verify `deploy-mac.sh` renders officers from template + roster. In the SAME commit: supersede `docs/plans/cog4-w1-u3-officer-plist-cleanup-PARKED-2026-07-23.md` in place with a dated note (PARK markers are superseded, never deleted), and flip this row to `retired`.

### RES-009 — COG-4 W3 u3: cortex serve-binding not routed through the kernel (PARKED)

- **Phase:** COG-4 W3 u3 — park marker 2026-07-24 (contract §6.4)
- **Status:** open
- **Closed:** six of the seven kernel disciplines DID adopt, byte-compatibly, with `test_cog2_*` green 283/283 — canonical bytes + digest, the content-excluded identity law, the parameterized chained rows-hash, the manifest envelope, the atomic write, and the leaf JSONL row reader.
- **Open:** the ~14-line verified-single-read SERVE-BINDING wrapper. `framework/cortex/query.py::_verified_rows` stays cortex-local and does not route through `kernel.verified_single_read`.
- **Why open:** a corpus contradiction the builder may not resolve. Routing the serve through the kernel bypasses `engine.read_beliefs_jsonl`, so the immutable TOCTOU test's `monkeypatch` never fires (`calls["n"] == 0`) and the test REDs. The test is correct — it pins a real property — and the corpus is immutable (§13); the blocker is the kernel's un-parameterized reader, whose bytes are u1-owned. Byte-compat is NOT the blocker: the served bytes are identical either way.
- **Declared at:** `docs/plans/cog4-w3-u3-cortex-serve-adoption-park-2026-07-24.md:1`
- **Anchor:** `PARK marker: cortex verified-single-read SERVE-BINDING adoption`
- **Retirement:** `kernel.verified_single_read` gains an optional `read_rows` callable (default `kernel.read_jsonl_rows`), and cortex's `_verified_rows` adopts the binding by passing `read_rows=_engine.read_beliefs_jsonl` — the monkeypatch fires again and both byte-compat and the F4 pin hold. In the SAME commit: supersede `docs/plans/cog4-w3-u3-cortex-serve-adoption-park-2026-07-24.md` in place with a dated note, and flip this row to `retired`.

### RES-010 — COG-4 W3 u4: objectives kernel adoption not performed (PARKED)

- **Phase:** COG-4 W3 u4 — parked 2026-07-24 (contract §6.4 second instantiation)
- **Status:** open
- **Closed:** nothing objectives-side changed — zero `framework/objectives` bytes, only the dated marker. The kernel is independently proven: the scheduler (u1) is the third instantiation and blocks nothing downstream.
- **Open:** `framework/objectives/{model,graph,query}.py` keep their own `canonical_bytes`/`digest`/rows-chain/manifest/serve rather than routing through `framework.projection.kernel`.
- **Why open:** two IMMUTABLE corpus artifacts contradict each other on the objectives boundary. The C2 module gate SANCTIONS the import (`cabinet/config/boundary-manifest.yml` ROW 6 allowlists `framework/objectives/*`), while the COG-3 objectives SYMBOL pin FORBIDS it (`cabinet/scripts/tests/lib_cog3_import_ast.py:124-134` permits only stdlib, internal, or seven enumerated `framework.cortex.query` symbols) and is bound "byte-untouched and never weakens". Resolving a corpus contradiction is the integrator's call, not a builder's.
- **Declared at:** `docs/plans/cog4-w3-u4-objectives-kernel-adoption-PARKED-2026-07-24.md:1`
- **Anchor:** `objectives kernel adoption: PARKED (2026-07-24)`
- **Retirement:** EITHER the integrator amends the objectives symbol pin by exactly `framework.projection` and nothing else (leaving the cortex 7-symbol restriction, the transitive-closure test and the defaults-only `as_of` pin intact), then unparks and re-runs the unit — noting the empty-graph rows-hash gotcha the marker records; OR the park is accepted as PERMANENT debt, in which case this row is flipped to `retired` with that ruling recorded, since the duplicated routines are already byte-parity-pinned and carry zero correctness cost. Either way: supersede the marker in place with a dated note in the SAME commit.

### RES-011 — COG-4 W4 u1: organ manifests are NOT schema-validated (PARKED, Captain-gated)

- **Phase:** COG-4 W4 u1 — parked 2026-07-24 (contract §4.5; germline window unopened)
- **Status:** captain-gated
- **Closed:** the structural surface landed and is honest about itself. `framework/organs/registry.py` performs STRUCTURAL reads with honest errors only and its docstring disclaims schema validation BY NAME; the W4 u1 battery passes the W2 corpus reference validator and N-d consistency; the suite-level `state_ownership` disjointness sweep is live and validator-independent.
- **Open:** everything requiring the CG-33 germline amendment to be APPLIED to the schg-locked extension gate pair (`framework/schemas/extension-manifest.schema.json` + `cabinet/scripts/validate-extension.sh`): real schema-validated organ manifests and any §4.2 schema-validity claim; the validate-extension.sh ORGAN BLOCK verification unit; the AX organ-block extension over the REAL schema.
- **Why open:** the germline paths are schg-locked and the immutable flag is NEVER worked around — a recorded handback beats a workaround. The window needs a Captain sudo ceremony (ledger row CG-33, HANDBACKS item 19; reply "apply organ-packaging" authorizes it). Nothing here is a build failure; it is an unopened authority window.
- **Declared at:** `docs/plans/cog4-w4-u1-organ-schema-validation-PARKED-2026-07-24.md:1`
- **Anchor:** `organ SCHEMA VALIDATION parked (germline window unopened)`
- **Retirement:** the Captain window lands the CG-33 edit (schema `kind` enum gains `organ` + the fourteen fields + the undo-grammar superset; the .sh gains the integer branch and ORGAN BLOCK; same-day relock; §4 battery green). Then (1) the W2 corpus vacuity arm retires per its own in-file RETIREMENT CONDITION, (2) a follow-up unit binds organ-manifest validation to the REAL `validate-extension.sh` on both paths and lands the AX organ-block checks — the registry KEEPS its structural-read posture and never becomes a second validator, (3) the marker is superseded in place with a dated note, and this row flips to `retired`. All in the SAME commit as (3).

## Absorption — COG-5 W2 adds its rows AT LANDING

The in-flight COG-5 W2 wave carries its own declared residuals on UNLANDED
branches (a fabricated-evidence custody channel; a `pwd`-fallback home-reach
vector). This register does NOT reach into branches, and those rows are NOT
here.

**The W2 landing integrator adds them, in the landing commit**, starting at
`RES-012`. Two things make that a forcing function rather than a hope:

- if the landed declarations carry the word token, the sweep sees them
  immediately and the pin test goes RED until each has a row;
- if they do not, the integrator must still register them — a residual declared
  in prose is exactly the failure mode this file exists to stop. Reword the
  declaration to the token in the same commit and both halves bind.

## Legacy exemptions — shrink-only

Two marker sites in the sweep surface are NOT residuals and carry no row:
`cabinet/scripts/egg-export-manifest.txt:233` and `:653`, both reading
`RESIDUAL SCRUB` — they describe scrub rules already EXECUTED (2026-07-21), not
open channels. They are exempted by exact `path:line` in the pin test with a
hard maximum, so the list can shrink and never grow. Rewording them out of the
sweep is blocked for a good reason: that file is inside the frozen COG-4 review
digest scope, and touching it would force a re-bind ceremony.

## Known limits of this register — stated, not hidden

- **Lowercase prose declarations are NOT covered.** 208 lowercase uses of
  "residual" span 88 files. Most describe channels already CLOSED, or
  threat-model facts explicitly "accepted and stated". A few are genuinely open
  and unregistered — `cabinet/mcp-server/server.py:537` ("residual gap tracked
  for the Captain as a big-rock") is the clearest. They are not registered here
  because promoting one requires per-item byte verification, and a row asserting
  more than the code declares is worse than no row. Remediation for any of them
  is mechanical and one commit: reword the declaration to the word token, add a
  row.
- **`RETIREMENT CONDITION` vacuity guards are deliberately NOT registered.**
  There are 56, almost all in the COG-4/COG-5 test corpora. They are a
  different class: each one already trips RED the moment its target lands, so
  it CANNOT rot silently — it is its own forcing function. Duplicating them
  here would add churn and collide with in-flight corpus surgery without adding
  a single guarantee.
- **This register pins declarations, not truth.** It proves a declared residual
  still exists where it says it does and has a stated way to die. It cannot
  prove the declaration was accurate when written. Rows above were each
  re-verified against the bytes at `a1357829`; a later reader should do the
  same before relying on one.
