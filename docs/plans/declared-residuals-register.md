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

Survey over the **tracked tree at `a1357829`**, case-sensitive. Counts are
`git grep`-measured, not `grep -r`: BSD `grep -I` in a non-UTF-8 locale
classifies this repo's em-dash-heavy markdown as binary and silently skips 19
files — the first pass of this very survey undercounted because of it, which is
why the reproduction command is recorded here.

Reproduce: `git grep -o -e '<form>' a1357829 -- . | wc -l`

| candidate form | occurrences / files | verdict |
|---|---|---|
| `DECLARED RESIDUAL` | 0 / 0 | not in use — rejected |
| `HONEST SCOPE` | 0 / 0 | not in use — rejected |
| `known limitation` / `KNOWN LIMITATION` | 0 / 0 | not in use — rejected |
| `RESIDUAL` (uppercase word token) | **21 / 11** | **ADOPTED** |
| `RETIREMENT CONDITION` (uppercase) | 42 / 24 | adopted as the row FIELD name |
| `PARKED` / PARK marker | 4 dated `docs/plans` markers | adopted as a declaration form |
| `residual` (lowercase, prose) | 239 / 107 | rejected as a marker (see limits) |

The 21 word-token sites split three ways, and only the first group is bound by
the gate:

- **8 sites / 7 files in the SWEEP SURFACE** — the code and config declarations.
  Every one has a row below (minus the two legacy exemptions). (Written as
  6 files in the first cut; re-measured at landing — see the correction below.)
- **11 sites / 2 files in the operative ledger + plan pair** — see "known
  limits"; that pair is a coordination surface with its own status/owner fields
  and its own A13 parity gate.
- **2 sites / 2 files in frozen review artifacts** (`feat-config-rot-cp1.md:95`,
  `feat-relaunch-scrub2-cp1.md:92`; the second is a wave NAME, not a
  declaration). At `db180092` this is 9 / 4 — `feat-cog5-w2-t3-boundary-escape-cp1.md:147`
  landed with W2, and 6 of the 9 are this register's OWN review artifact.

The uppercase token appears in several qualifier forms — bare `RESIDUAL:`,
`HONEST RESIDUAL:`, `KNOWN RESIDUAL`, and (added by later waves, see the
re-measure below) `DECLARED RESIDUAL`, `DOCUMENTED RESIDUAL`, `RESIDUAL
HONESTY` — so the convention is the **word token**, not a fixed prefix:

```
(?<![A-Za-z0-9_])RESIDUALS?(?![A-Za-z0-9_])
```

The lookarounds are load-bearing: they exclude identifiers that merely contain
the word (`_TEMPORARY_RESIDUALS` in `framework/tests/test_no_launcher_hardcode.py`,
`RESIDUAL_NOTE` in `cabinet/scripts/evidence-tamper-drill.py`), which are
mechanisms, not declarations.

#### RE-MEASURED AT LANDING — `db180092`

The survey above is anchored at `a1357829` and stays there, because it is the
evidence for the CHOICE of marker. The tree it measured no longer exists, so the
live numbers are restated here rather than left to rot. Same method, same
regex, whole tracked tree:

| | `a1357829` | `db180092` (+ this register) |
|---|---|---|
| word-token sites / files | 21 / 11 | **53 / 20** |
| — in the SWEEP SURFACE | 8 / **7** (see correction) | **15 / 12** |
| — operative ledger + plan pair | 11 / 2 | 11 / 2 (unchanged) |
| — frozen review artifacts | 2 / 2 | 9 / 4 (6 are this branch's own artifact) |
| — this register + its pin test | n/a | 18 / 2 (self-excluded by construction) |
| `RETIREMENT CONDITION` | 42 / 24 | 71 / 33 |
| `residual` (lowercase, prose) | 239 / 107 | 291 / 119 |

**Correction to the original survey.** The `a1357829` sweep-surface FILE count
was written as 6 and is 7 — `egg-export-manifest.txt` carries two of the eight
sites, and counting it once was dropped somewhere between the sites tally and
the files tally. The site count (8) was right, and no row, cite or assertion
depended on the file count. It reconciles now: 11 files total = 7 sweep + 2
operative + 2 frozen. Recorded rather than quietly overwritten, because "this
register pins declarations, not truth" cuts both ways — the survey is a
measurement and measurements get re-run.

Two verdicts in the table above were CORRECT AT THE TIME and are now wrong as
statements about the live tree — recorded here because a silently stale
rejection is exactly the rot this file exists to catch:

- `DECLARED RESIDUAL` was 0/0 and rejected as not-in-use. It is now the most
  common qualifier in new code (6 / 5). Rejecting it as a fixed PREFIX was
  still right: the word-token regex catches it unchanged, which is the whole
  argument for choosing the token over a phrase.
- `HONEST SCOPE` was 0/0 and rejected. It is now 12 / 4, adopted by COG-5 W2 as
  a docstring SECTION name (`make_vector`'s block, which `RES-013` and
  `RES-014` cite). It marks a scope discussion, not a single residual, so it is
  still not the marker — but it is a good place to look for unregistered ones.

The sweep surface grew 8 → 15. The two legacy exemptions were already in the 8;
all seven new sites are declarations, and they are exactly what `RES-012`
..`RES-015` register. That growth is what forced this landing to absorb them.

`RETIREMENT CONDITION` is the repo's existing name for "what closes this" (42
uses across 24 files, e.g. `cabinet/scripts/tests/test_cog5_league_ast_pin.py:22`),
so this register's retirement field carries that name rather than a new one.

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
- `docs/` — narrative planning prose, including the operative ledger + plan
  pair. Rows CITE docs (the PARK markers below); the sweep does not police
  prose. The ledger exclusion is a deliberate call, not an oversight: every
  parallel wave appends rows to it, so a sweep there would fight in-flight
  waves for the same bytes every session, and its rows already carry `status`
  and an owner plus the A13 parity gate. See "known limits".

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
- **Declared at:** `cabinet/scripts/hooks/pre-tool-use.sh:656`
- **Anchor:** `RESIDUAL (SEPARATE finding`
- **Retirement:** a Captain unlock window brings `instance/config/platform.yml` and `framework/defaults/spending-limits.yml` under the schg set (`cabinet/scripts/germline-lock.sh` FILES[]) and into the hook's `GERM_PATH_RE`. In the SAME commit: delete this declaration block from `cabinet/scripts/hooks/pre-tool-use.sh`, and flip this row to `retired`.

### RES-002 — Captain's personal CLAUDE.md body still loads into officer sessions

- **Phase:** AUD-1 (CLAUDE_CONFIG_DIR officer isolation, 2026-07-07)
- **Status:** open
- **Closed:** officers boot from a dedicated config home with OAuth intact (`CLAUDE_SECURESTORAGE_CONFIG_DIR` set-to-empty federates the keychain item instead of duplicating it); the 58KB `@screenpipe-memories.md` dossier import does NOT load (external-includes gate unapproved in the fresh home); no credential or config assignment is typed into tmux pane history.
- **Open:** the ~3KB BODY of the Captain's personal `~/.claude/CLAUDE.md` still loads via Claude Code's cwd ANCESTOR walk, because the repo lives under `$HOME`.
- **Why open:** `CLAUDE_CONFIG_DIR` cannot gate an ancestor walk, and `CLAUDE_CODE_DISABLE_CLAUDE_MDS` was rejected — it would kill the repo's own cabinet-law `CLAUDE.md` too. The two real fixes are outside this layer.
- **Declared at:** `cabinet/scripts/start-officer-mac.sh:497`
- **Anchor:** `KNOWN RESIDUAL (documented in the AUD-1 ledger row)`
- **Retirement:** either (a) the Captain moves personal content behind imports on a non-ancestor path, or (b) an upstream ancestor-walk opt-out ships — both named in the AUD-1 note (`docs/plans/operative-egg-ledger-2026-07-07.yml`, row `AUD-1`). Whichever lands: delete this declaration block from `cabinet/scripts/start-officer-mac.sh`, update the AUD-1 note, and flip this row to `retired` in the SAME commit.

### RES-003 — hatch tracked-platform.yml guard is clean-room-scoped only

- **Phase:** hardening C11 (2026-07-11), Brief 1
- **Status:** open
- **Closed:** a `--clean-room` hatch run inside a git work tree whose `instance/config/platform.yml` is tracked with a real deployment config (>50 lines) is REFUSED, exit 64 — with the throwaway-export escape (`git archive HEAD | tar -x`) and an explicit `HATCH_ALLOW_TRACKED_INSTANCE=1` override documented in place.
- **Open:** a plain, NON-clean-room hatch run from such a checkout still rewrites the tracked `platform.yml` in place.
- **Why open:** the declaration states the scope decision outright — in-scope containment per hardening Brief 1 was clean-room only. It is a deliberate scope boundary, not an oversight.
- **Declared at:** `cabinet/scripts/hatch.sh:69`
- **Anchor:** `KNOWN RESIDUAL SEAM (2026-07-11 verify`
- **Retirement:** the guard is lifted out of the clean-room branch so every hatch path refuses to rewrite a tracked `platform.yml` (or hatch stops writing tracked instance config at all). In the SAME commit: delete this declaration block from `cabinet/scripts/hatch.sh`, extend the hatch regression suite with a non-clean-room arm, and flip this row to `retired`.

### RES-004 — egress raw-socket containment has no Linux/Docker equivalent

- **Phase:** egress boundary (framework default; coverage-vs-residual in `docs/runbooks/egress-allowlist.md`)
- **Status:** open
- **Closed:** on macOS, proxy env vars catch curl, python-requests and every MCP/client that honours them, and a Seatbelt rule denies direct external TCP/UDP so raw-socket bypasses fail at the kernel boundary. The guard is fail-closed: if the proxy cannot be installed or verified it errors non-zero and installs NOTHING.
- **Open:** Linux/Docker has no Seatbelt equivalent at this layer, so raw sockets there need a host/container network policy; existing sessions require a restart to pick the boundary up; localhost services remain outside the officer boundary.
- **Why open:** there is no in-process, kernel-level equivalent this layer can install on Linux/Docker — the containment must come from the host or container runtime, which the cabinet does not own.
- **Declared at:** `framework/defaults/egress.yml:37`
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
- **Declared at:** `shared/interfaces/reviews/cognitive-core-phase-4-review.md:630`
- **Anchor:** `Shadow-log replay window`
- **Retirement:** the cutover amendment REQUIRES read+check+append under one lock, and `cog4-dispatch-shadow.py` (or its cutover successor) implements it, before any dispatch becomes real. In the SAME commit as that amendment landing: flip this row to `retired` and record the implementing commit here. Until then this row is the carrier — the review artifact is digest-bound and frozen, so it cannot be updated in place.
- **Note:** this residual is declared in a FROZEN review artifact and has no in-code marker. Registering it here is the only reason it survives a refactor of the dispatcher. The cite moved `:233` → `:320` at this register's landing: two re-bind ceremonies (`fcad8e47`, `598868ed`) inserted an 88-line block at `:70`, ABOVE the findings table, leaving the P1 row byte-identical but 87 lines lower. Expect the same re-point at each future re-bind — the row is not drifting, the file is growing above it. This is the pin working: a frozen artifact cannot be updated in place, so the cite is the only thing that can move. Re-pointed `:362` → `:434` on 2026-07-27 by the attention-well-spent landing (`fix/attention-silence-ratchet`), whose census-allowance row forced TWO re-bind ceremonies — one for the branch itself and a second when the branch merged master ac56ce78, which had left COG-4 BLOCK by landing its own contract rows without discharging the ceremony. The two inserted 39 and 33 net lines into the digest-note preamble ABOVE the findings table, so the P1 row is again byte-identical and 72 lines lower. Third and fourth occurrences, same cause, exactly as this note predicted; the cite is re-pointed once, to the final position. Re-pointed `:454` → `:466` on 2026-07-27 by the propose/gate landing (`fix/propose-means-propose`), whose digest re-bind added a 12-line note ABOVE the findings table — plus a second re-bind when the branch merged master `1f13d49d`, which had re-bound the same digest for `feat/census-set-pins`. Fifth occurrence, same cause. The P1 row is again byte-identical and 12 lines lower. Re-pointed `:477` → `:485` on 2026-07-27 by the three-entry-modes landing (`feat/onboarding-entry-modes`), whose allowance row forced a re-bind and then a second one on merging master `6e50570f` — the propose/gate landing had re-bound the same digest — adding 8 net lines of re-bind note ABOVE the findings table. Sixth occurrence, same cause, exactly as this note has predicted every time. The P1 row is byte-identical and 8 lines lower. Re-pointed again `:485` → `:494` in the same landing when it merged master `8095ded9` (the hook-redos digest re-bind) and recorded a merge re-bind note of its own: 9 more lines above the findings table. Seventh occurrence. Re-pointed `:494` → `:501` in the same landing on its second master merge (source-ownership-class + killswitch-test-fence), 7 more lines of merge re-bind note above the findings table. Eighth and ninth occurrences (`:494` → `:501` → `:509`), the third master merge being personal-preset-live; the cite is re-pointed once, to the final position. Re-pointed `:543` → `:569` on 2026-07-28 by the iso interaction layer landing (`iso-port-composition` PR #223), whose merge of master `6ec81460` carried further digest re-bind notes ABOVE the findings table: 26 more lines. **Tenth occurrence, same cause, and the note has now predicted every one of them.** The P1 row is again byte-identical and 26 lines lower. That this is the tenth is itself the finding: a cite that must be hand-re-pointed on every merge is a maintenance tax the register pays forever, and the honest fix is to pin the declaration by its ANCHOR TEXT rather than by a line number — the test already searches for the anchor, so the line number adds nothing but breakage. Filed rather than done here, because changing the register's cite format is not in this branch's scope. CONCURRENTLY, and independently, re-pointed `:543` → `:577` by the evidence-append-quadratic landing (`fix/evidence-append-quadratic`), whose census-allowance row forced a re-bind and then a merge re-bind: 34 more net lines of note above the findings table. Two landings in flight at once, each correct about its own tree and each wrong about the other's, so the merge of the two re-points to neither number — `:616` is re-derived by grep over the MERGED artifact, which now carries both sides' notes. That is the eleventh occurrence and the second inside one day. It also settles the fix master's note filed above: pin the declaration by ANCHOR TEXT, not by a line number. The test already searches for the anchor, so the number buys nothing and costs a hand re-point per merge; still filed rather than done here, because changing the register's cite format is a change to the register and not to either of these branches.

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

### RES-012 — arena home confinement is expanduser-only; the `pwd` fallback still leaks the real home

- **Phase:** COG-5 W2 — sim-7 credential-file reach instrument (residual is W3-owned)
- **Status:** open
- **Closed:** the confinement mechanism is stated and proven, not assumed. HOME-UNSET provably does NOT confine — `Path.home()` calls `os.path.expanduser('~')`, which reads `os.environ['HOME']` first and falls back to `pwd.getpwuid(os.getuid()).pw_dir` when HOME is ABSENT, so scrubbing HOME leaves home resolving to the REAL home. The confined posture is therefore an EXPLICIT `HOME` override pointing INTO the arena workdir. Both arms bite: the unconfined mutant reaches every one of the four §4.4 planted classes and the detector names all four; the confined arm finds nothing while credentials ARE planted in a sibling harness home, so the empty finding set is a real discrimination. Twin safety fences refuse if the resolved home is the real `pwd` home or lies outside the caller-declared scratch root, and the instruments only ever stat PLANTED fixture files.
- **Open:** a candidate calling `pwd.getpwuid()` directly still learns the real home path. The override confines `expanduser`-based resolution and nothing else.
- **Why open:** closing it needs an OS-level fence, which is the W3 `framework/evolution/sandbox.py` harness — a surface that has not landed. Until it does, the probe REPORTS `pwd_home` and the corpus never claims full confinement.
- **Declared at:** `cabinet/scripts/tests/lib_cog5_boundary_fixtures.py:192`, `cabinet/scripts/tests/test_cog5_arena_escape.py:202`
- **Anchor:** `DECLARED RESIDUAL (honest, W3-owned): a HOME override confines`
- **Retirement:** `framework/evolution/sandbox.py` lands (W3) and the sim-7 escape battery runs THROUGH the real harness, fencing home reach at the OS layer. That landing already REDs `test_sandbox_absent_companion` in `cabinet/scripts/tests/test_cog5_arena_escape.py`, whose failure text names this residual by name — so the forcing function exists independently of this row. In the SAME commit: delete BOTH declaration blocks, retire that vacuity companion pair, and flip this row to `retired`.

### RES-013 — a self-consistent fabricated replay map still reads as MACHINE custody

- **Phase:** COG-5 W2 — sim-4 X6 derivation custody, fresh-context finding N1
- **Status:** open
- **Closed:** both channels the vector layer actually owns. The LABEL channel: there is structurally no derivation parameter — `assert_no_derivation_parameter` proves it over the real constructor signature, and a mutant constructor that DOES take one is shown to let a caller stamp `machine:replay_map` on the judge's number. The VALUE channel: a MACHINE dim carrying MACHINE evidence takes its number FROM that evidence, the caller's claim never enters the vector, and a declared number disagreeing with its own evidence stamps `DERIVATION_VALUE_MISMATCH`, which sits outside `MACHINE_DERIVATIONS` and dies at the floor exactly like a judge-sourced one.
- **Open:** the EVIDENCE OBJECT is still the caller's. The stamp follows that object's TYPE, so a machine-SHAPED fabrication — a one-row `{"case-001": True}` map — earns `machine:replay_map` with no label forgery anywhere, and a fabricated map that AGREES with its own declared value still reads as machine custody.
- **Why open:** binding a replay map to the identity of the frozen corpus that produced it is an UPSTREAM obligation — it belongs at the replay stage that mints the map, not at the vector layer — and contract §9.1 ratifies no such clause here. The declaration is explicit that the older, wider claim ("a caller can never NAME machine custody for a number it did not measure") was FALSE as written and was cut back to what the bytes deliver.
- **Declared at:** `cabinet/scripts/tests/lib_cog5_scoring_fixtures.py:508`, `cabinet/scripts/tests/test_cog5_sim_scoring.py:339`
- **Anchor:** `ratifies no such clause here. DECLARED RESIDUAL`
- **Retirement:** a round binds replay maps to the identity of the frozen corpus at the stage that mints them, so a fabricated map can no longer earn `machine:replay_map`. `test_declared_residual_self_consistent_fabricated_evidence` flips by construction at that moment — its own message says so. In the SAME commit: delete the `HONEST SCOPE` (1) paragraph from `make_vector`, retire that pin arm and the scope note in `test_the_constructor_wall_no_caller_may_name_a_derivation`, and flip this row to `retired`.

### RES-014 — the machine-value law is FIXTURE-TIER and cannot re-run at W6

- **Phase:** COG-5 W2 — sim-4 X6 value channel, §9.1 pack boundary
- **Status:** open
- **Closed:** what DOES re-run at W6 against the real surface is named exactly, so nobody mistakes the gap for total absence: `assert_machine_floors_machine_derived` (the stamps), `assert_no_derivation_parameter` (the label channel, over the real constructor's signature) and `assert_derivation_refused` (the joint).
- **Open:** `assert_machine_values_measured_from_evidence` holds at CONSTRUCTION only, because construction is the only place the evidence exists. It cannot re-derive a landed `scorers.py` pack's numbers.
- **Why open:** a §9.1 pack carries `{value, kind, derivation}` and NOT its evidence, so re-running the law at W6 would need the pack to carry its evidence — an obligation §9.1 does not ratify. The declaration puts it in the same class as the keyed seal deliberately NOT shipped for the label channel: a known, stated tier boundary rather than an oversight.
- **Declared at:** `cabinet/scripts/tests/lib_cog5_scoring_fixtures.py:516`
- **Anchor:** `(the pack carrying its evidence). DECLARED RESIDUAL of`
- **Retirement:** §9.1 is amended so a pack carries its evidence (or an evidence digest the vector layer can re-measure against), and `assert_machine_values_measured_from_evidence` joins the W6 re-run set over the real `scorers.py` surface. In the SAME commit: delete the `HONEST SCOPE` (2) paragraph from `make_vector`, and flip this row to `retired`.

### RES-015 — the boundary import gate leaves a named undetectable set, including DECIDABLE forms not wired

- **Phase:** COG-2 boundary engine — dynamic-form widening of `cabinet/scripts/cog2-import-gate.py`
- **Status:** open
- **Closed:** the dynamic-form BINDING surface, measured rather than asserted. Constant-foldable arguments, aliased import hooks in any binding order, the same three binding shapes on the builtin from either exporting module, and the two-argument relative form are all caught. Non-vacuity is accounted in the declaration: grafted onto the pre-fix engine (`766a98c3`, caches purged) the file collects 823 arms and 148 FAIL, all 148 of them added arms with no pre-existing arm regressing; against the fixed engine all 823 pass. `TestDocumentedResidual` pins the boundary from the other side — a genuinely runtime-computed argument must NOT be reported, because a scanner that guessed there would be lying.
- **Open:** the engine docstring's named set. (a) a module name computed at runtime — a variable, parameter, call result, `%`/`.format()`/`.join()` assembly, table or env lookup, interpolated f-string field; (b) an attribute walk that never names a module as a string — getattr chains, `sys.modules[...]` indexing, `__dict__` traversal; (c) STILL-DECIDABLE forms deliberately not resolved: the builtin's `fromlist` and `level` parameters (both spellings), an alias chain deeper than one hop, a hook reached without a name binding (mapping subscript or getattr walk), and a concatenation nested past `_FOLD_MAX_DEPTH`.
- **Why open:** (a) and (b) are not decidable without executing the program — runtime detection is the RUNTIME layer's job, not this gate's. (c) is a deliberate line, and the declaration gives the reason: the subscript/getattr surface is open-ended (any mapping or attribute expression can yield the hook) while a name binding is a closed, enumerable set. `fromlist`/`level` are simply not wired yet, and the declaration calls closing any of (c) a mechanical follow-up.
- **Declared at:** `cabinet/scripts/tests/test_boundary_dynamic_forms.py:71`, `cabinet/scripts/tests/test_boundary_dynamic_forms.py:705`
- **Anchor:** `RESIDUAL HONESTY. The engine docstring documents what remains undetectable`
- **Retirement:** a follow-up wires the decidable (c) forms — at minimum `fromlist`/`level` on both `__import__` spellings, since `_import_from_targets` already computes the importing file's own package for the static form. In the SAME commit, per the declaration's own rule that the residual text and its tests move together: shrink the engine's residual list in `cabinet/scripts/cog2-import-gate.py`, move the matching `TestDocumentedResidual` arms, and either narrow this row's Open field to what genuinely remains undecidable or flip it to `retired` if nothing does.

### RES-016 — the emergency stop still rides ONE channel, so a pre-armed clearing loop still wins

- **Phase:** emergency-stop fail-closed fix (2026-07-25 adversarial audit), defect 2
- **Status:** captain-gated
- **Closed:** the stop no longer fails OPEN. Every reader now goes through one helper (`cabinet/scripts/hooks/killswitch-read.sh`) that reports CLEAR only on a definitive AUTHENTICATED read — a nonce-framed round trip a live server must echo — so NOAUTH, NOPERM, WRONGTYPE, LOADING, an unrecognised value, a silent `redis-cli` and a refused connection are all INDETERMINATE, and INDETERMINATE halts exactly like ACTIVE while being reported distinctly. The reader ALSO honours a second, filesystem stop channel (`instance/config/estop`, or `CABINET_ESTOP_MARKER`), and `kill-switch.sh deactivate` clears it.
- **Open:** nothing ARMS the second channel automatically. `kill-switch.sh activate` writes only the Redis key, so the audit's pre-armed loop — `while :; do redis-cli DEL cabinet:killswitch; sleep 1; done` — still clears the stop within a second of every arming. The mechanism that defeats it is built and test-pinned (`cabinet/scripts/tests/test_killswitch_fail_closed.py::test_stop_survives_a_del_loop_clearing_the_redis_key` arms both channels by hand and proves the loop cannot clear them); it is not switched on.
- **Why open:** arming a durable filesystem latch changes the emergency stop's CONTRACT rather than fixing a bug, and `cabinet/scripts/killswitch-watchdog.py` exists precisely to re-arm a switch that an unattributed raw `DEL` cleared — with a latch, that scenario stops being reachable through Redis alone, and the watchdog's tested semantics change with it. A latch is also a global side effect: when `activate` wrote the marker, every suite that arms the switch without a matching `deactivate` left the repo reading STOPPED for every later run. That is a governance decision and an operational one, not something to slip inside a fail-closed patch.
- **Declared at:** `cabinet/scripts/kill-switch.sh:42`
- **Anchor:** `DECLARED RESIDUAL (RES-016)`
- **Retirement:** a Captain ruling arms the second channel. In the SAME commit: `kill-switch.sh activate` writes the marker BEFORE the Redis SET (so the stop is never half-armed) and reports each channel separately; `killswitch-watchdog.py` reads the REDIS channel alone (it polices that channel, and the shared helper grows a redis-only mode for it); every suite that arms the switch gets an isolated `CABINET_ESTOP_MARKER` so the latch cannot leak between tests; and this row flips to `retired`. HONEST LIMIT even then: a same-uid adversary can remove the marker too, so this raises cost rather than closing the class — genuinely closing it needs a channel the officer's uid cannot write (a root-owned path, or a Seatbelt deny-write on the marker in the officer profile).

### RES-017 — a deploy drops the E-stop filesystem channel for the incoming release

- **Phase:** state-persistence preflight landing (2026-07-26), merge with the emergency-stop fail-closed fix
- **Status:** open
- **Closed:** the marker is accounted for rather than silently discarded, and it is deliberately NOT carried. `cabinet/config/state-persistence-policy.yml` declares `instance/config/estop` disposable with the measured reason: `killswitch-read.sh` treats the path's existence in ANY form as not-CLEAR and a SYMLINK specifically as INDETERMINATE (`stop marker present but not a regular file`), so symlinking it into `<runtime_root>/shared/` would arm the emergency stop permanently on every release — and `kill-switch.sh deactivate`'s `rm -f "$ESTOP_MARKER"` removes the LINK while the shared/ copy survives, so the next provision would re-create an unclearable halt. Verified by driving `_ks_marker_verdict` directly (absent -> CLEAR, symlink -> INDETERMINATE) and by `rm -f` on a link leaving its target intact.
- **Open:** a release is a fresh `git worktree`, so the marker does not cross a deploy. Once RES-016 is closed and `activate` arms the filesystem channel, the incoming release starts with that channel CLEAR while the Redis channel stays ACTIVE — so inside that window the pre-armed `while :; do redis-cli DEL cabinet:killswitch; done` loop RES-016's second channel exists to defeat wins again.
- **Why open:** the fix is not a persistence row — every persistence mechanism available here is a symlink, and a symlink at this path is strictly worse than the gap (a permanent, unclearable fleet-wide halt). It needs a provision-time re-arm step that reads the Redis verdict and writes a REAL marker file into the new release when the stop is armed, which is a change to the emergency stop's operational contract and therefore belongs with the RES-016 ruling rather than ahead of it. Nothing is lost today: `activate` does not write the marker at all, so the channel this row is about is not yet armed.
- **Declared at:** `cabinet/config/state-persistence-policy.yml:163`
- **Anchor:** `RESIDUAL, stated rather than hidden`
- **Retirement:** the RES-016 Captain ruling arms the second channel AND `runtime-provision.sh` gains a provision-time re-arm: after linking, read the emergency-stop verdict through `cabinet/scripts/hooks/killswitch-read.sh` and, when it is ACTIVE, write a real (never symlinked) marker file into the new slot before the release can be promoted, with a test arm proving a deploy performed under an armed stop leaves the new release reading ACTIVE on BOTH channels. In the SAME commit: delete this declaration from `cabinet/config/state-persistence-policy.yml`, replace it with a statement of what now carries the arm, and flip this row to `retired`.

### RES-018 — the Bash locality proof is a CLASSIFICATION, not containment

- **Phase:** bash-egress fail-closed (2026-07-27), the third comms-ceiling wall audit
- **Status:** open
- **Closed:** a Bash command no longer becomes `local_edit` by default. `framework/authority/classifier.py:_is_provably_local` requires a positive no-egress proof — every binary the shell parser resolves must sit in a set that can neither open a socket nor execute another program, `git` resolves per-subcommand (with `-c`/`--config-env`/`--exec-path` disqualifying outright), and the shell's own `/dev/tcp`,`/dev/udp` primitive is refused on the raw text. Everything else resolves `AMBIGUOUS`, which has no risk class and therefore proposes. Measured before/after: `sendmail`, `mail`, a `smtplib` one-liner, an `osascript` Messages send, a GET webhook, `nc`, `ssh`, `scp`, `swaks`, `git send-email`, `open mailto:`, `wget`, `node -e fetch`, `dig`, and every quoting/wrapper/variable evasion tried, all went from ALLOW in guardian and sovereign to blocked in every posture.
- **Note:** SECOND ROUND, recorded because the first version of this claim was wrong — an adversarial review defeated the first version of this proof with a generic prefix, restoring 20 of the 22 pinned commands to `local_edit`. All four causes were in the SHARED shell parser (`extract_invoked_binaries`), not in the allowlist: a leading redirect whose target basename was an allowlisted name became the command word (`2>/tmp/echo sendmail -t`); a statement the parser could not resolve returned `[]` and was absorbed by an allowlisted sibling (`ls && bash /tmp/exfil.sh`); `\n` was not a statement separator, so every multi-line command was analysed by its first line only; and an inline `VAR=VAL` prefix was silently skipped, so `PATH=/tmp/evil ls` and `GIT_EXTERNAL_DIFF=/tmp/x git diff` rebound what an allowlisted name resolved to. Each is fixed at the parser and pinned. THE SAME TWO GAPS ALSO DEFEATED THE LIVE-ENFORCING PLANE, which is the more serious finding and was pre-existing on master: `binary_block` and `destructive_rm` are in `policy-shadow.py:_LEGACY_ENFORCING_TYPES` and DO block today, yet `2>/tmp/ls sudo rm -rf /tmp/x` and `ls\nrm -rf /` were both ALLOWED. Both now block, with arms in `framework/authority/tests/test_policy_engine.py`. THIRD ROUND (2026-07-27), and this one was found by MEASUREMENT rather than by attack. Replaying the matrix over 39,797 real recorded Bash commands showed the proof was being decided, 34.4% of the time, by a token that is not a program: **347 distinct** non-program tokens were reaching the resolver as command words, and the neighbouring "only real binaries" bucket was optimistic for the same reason (its 609 tokens included `A`, `ACK`, `ALLOW`, `AND`, `API`). Root causes, all in the shared lexer and each now pinned by an arm that fails against the pre-change parser: `&` was a statement separator even inside the redirection `2>&1`, so the digit `1` was the command word of 14,943 records — the single largest cause; the double-quote scanner ended a span at a `"` nested inside `$( )`, desynchronising everything after it; `${VAR:-default}` was split as a brace group; comments were never stripped; every heredoc body was re-parsed as shell even when `cat`, an interpreter, `read` or `git commit -F -` consumed it; and `$(( ))` arithmetic, the `{}` of `find -exec`, `case` patterns and `for` loop variables all became command words. After the fix: **1** non-program token in 1 record. THE SAME DEFECT WAS A LIVE FAIL-OPEN, which is the more serious half: because a `$( )` inside a double-quoted string was invisible, 498 recorded commands were classified provably-LOCAL while invoking `redis-cli`, `gh` or `launchctl`, and `echo "$(sendmail -t)"` was provably local on master. The direction was verified over the whole corpus rather than argued: 573 commands moved block→allow and **every one** of them resolves exclusively to `_LOCAL_ONLY_BINARIES` members plus `git` at a local verb; `is_destructive_rm` lost nothing and gained nothing on 67,346 records.
- **Open:** this decides a VERDICT at a pre-tool-use classification gate; it opens no socket and closes none. Three reaches it does not have. (1) The authority matrix is shadow-consumed — `cabinet/scripts/policy-shadow.py` excludes `authority_matrix` from `_LEGACY_ENFORCING_TYPES`, so today the honest verdict is computed and not enforced. MEASURED 2026-07-27 (`docs/authority-matrix-enforcement-dryrun-2026-07-27.md`, instrument `cabinet/scripts/authority-matrix-dryrun.py`): that exclusion is load-bearing, not caution. Replaying the matrix over 80,307 real officer tool calls refuses 52,658 of the 69,655 that run today — 75.60% — of which 71.5% is this residual's own `AMBIGUOUS` fail-safe meeting a classifier whose allowlist has no `python`, `sed`, `awk`, `find`, `xargs`, `gh`, `pytest`, `npm` and no git WRITE verb. So the propose-only verdicts this row calls "not enforced" cannot simply be switched on: the same fail-closed default that makes the locality proof honest makes it unusable as a gate until the classifier has a vocabulary for developer tooling. (2) Containment is the egress jail plus the Seatbelt profile, and the profile is `(allow default)` with no `appleevent-send` or `mach-lookup` deny (`cabinet/scripts/lib/officer-sandbox.sh:65,135-144,232-240`), so an `osascript` Mail/Messages send remains EXECUTABLE at full egress enforcement even while it classifies propose-only here; local mail submission via a spool write is likewise untouched by the proxy, by the TCP/UDP deny, and by the UDS deny. (3) Only Bash calls reaching this gate are seen — a subprocess spawned by an already-allowed command, a launchd service outside the officer's sandbox, and every non-Bash path are outside it. Two narrower residues inside the proof itself: a `_LOCAL_ONLY_BINARIES` member with an exec or network escape nobody knew about would be trusted (the membership rule and its machine-checked arm exist to keep that set small, not to make it provably complete), and `git`'s local verbs still run repo-supplied config, so a hostile checkout is not modelled.
- **Why open:** the classification layer is the wrong place to stop execution and cannot be made into the right one — static analysis of a shell string cannot decide whether `python3 foo.py` sends mail. The two available containment moves are both outside this fix: denying Apple Events in the sandbox profile would break the SANCTIONED `osascript` Calendar/Reminders transport (`framework/frontdoor/action_exec.py:802-1047`) and so needs a ruling on which Apple Events are sanctioned, not a guess; and the profile is germline, macOS-only, and unverifiable on the Ubuntu CI runners, so a change there would ship with no sensor. `docs/runbooks/egress-allowlist.md:220-224` already names the missing companion — a Bash-layer gate in `pre-tool-use.sh` — as a germline ceremony item.
- **Declared at:** `framework/authority/classifier.py:631`
- **Anchor:** `RESIDUAL — what this does NOT do`
- **Retirement:** BOTH halves land. (a) The sandbox profile gains an `appleevent-send` deny with an explicit destination allowlist for the sanctioned Calendar/Reminders transport, plus a mail-submission deny, with an arm that runs the generated profile under `sandbox-exec` and proves an unsanctioned Apple Event is refused. (b) The Captain flips `authority_matrix` into the enforcing set, discharging the flip preconditions already recorded at `framework/authority/policy_engine.py:1195-1209` AND the four the 2026-07-27 dry run added (`docs/authority-matrix-enforcement-dryrun-2026-07-27.md` §7: classifier vocabulary for developer tooling, ceiling-classifier precision, the raw-Edit/Write journaling precondition, and the intent question about enforcement filing needs / consuming standing-grant budget), re-measured with `authority-matrix-dryrun.py` until the newly-blocked delta is defensible — at which point the propose-only verdicts here become live blocks. In the SAME commit as the second: delete this declaration from `framework/authority/classifier.py`, restate what now carries the containment, and flip this row to `retired`.

### RES-019 — the `perl -i` and `sed -i` write patterns still backtrack polynomially

- **Phase:** hook-redos (2026-07-27) — sibling sweep of the `sed` catastrophic-backtracking fix
- **Status:** open
- **Closed:** the EXPONENTIAL axis of the `sed` entry of `policy_engine._WRITE_PATTERNS` — the quote-tiling and in-span separator ambiguities, which together cost 2**(quote pairs) and s**(spans). 52 of 80,307 recorded officer calls exceeded 1.5s and 110 bytes was enough to exceed 5s; both are now single-parse, and every pump on those two axes answers in under 5ms (a 1,065-byte shape that took over 6s now takes 0.005s). A fail-closed evaluation timeout was added to `cabinet/scripts/policy-shadow.py` in the same landing, so ANY write pattern that cannot answer inside its budget now blocks with a named reason instead of hanging the hook forever.
- **Open:** TWO things. (a) The `sed` entry is still CUBIC on a third, untouched axis: the split point of the in-place-flag alternation between the two `_STMT_RUN`s, multiplied by `re.search` restarting at every `sed` occurrence. Measured degree ~3 on both interpreters, and NOT a regression — master is within 3% at every size (`'sed -i x '`x312 = 2,813 bytes: 0.98s staged vs 1.00s master; 4,865 bytes: 5.30s vs 5.29s). It is a smaller exposure than the exponential that was closed (2.8KB for 1s, versus 110 bytes for 5s) but it is larger than the siblings in (b), and the fix did not touch it. (b) The `perl` entry (index 7) of the same list. `[^\s]*` and the following `[^;&|]*` overlap on every non-space non-separator character, so their split point is free, and `re.search` restarts at each `perl` occurrence. Measured degree ~4 on both interpreters: 601 bytes costs 2.5s, 1.2KB exceeds 5s. Three lesser siblings share the shape and were measured too — the brace expander at `policy_engine.py:693` (quadratic, needs ~80KB) and the `_regex_decision` fallback's rm and write-verb patterns (cubic/quadratic, fallback path only, need 2KB-120KB).
- **Why open:** POLYNOMIAL, not exponential, and the pump shapes (`perl-i` repeated) are adversarial rather than a shape an officer types by accident — so it is a materially smaller exposure than the one closed, and the timeout bounds it at the budget. The obvious repair was tried and REJECTED on evidence: atomic-emulating the free star with the 3.9-compatible `(?=(X))\1` idiom (the hook's `python3` is 3.9.6, which has no `(?>...)`) made `perl-i/workspace/a/` stop matching — it silently NARROWED an enforcing safety rule. A correct rewrite needs its own equivalence proof, exactly as the sed one did, and shipping a guessed one in the same pass would repeat the mistake this landing already made once.
- **Declared at:** `framework/authority/policy_engine.py:1411`
- **Anchor:** `KNOWN RESIDUAL (RES-019)`
- **Retirement:** BOTH open items are closed — the `perl` pattern rewritten single-parse, and the `sed` flag-alternation/multiple-occurrence axis bounded — each with a two-directional language-equality proof and a pumped wall-clock arm (the `TestWritePatternBacktracking` pattern), or `bash_write_to_path` stops matching command TEXT and matches a parsed invocation instead, which removes every one of these axes at once and is the preferred fix. In the SAME commit: delete this declaration block from `framework/authority/policy_engine.py` and flip this row to `retired`.

### RES-020 — the Stop-hook context guard tests a dead twin, and passes

- **Phase:** enforcement-plane dependency preflight (2026-07-28), sibling finding
- **Status:** open
- **Closed:** nothing about THIS guard — the row exists so it stops being tribal knowledge. Two adjacent things did move: golden EVAL-008's target was re-pointed from `cabinet/scripts/hooks/stop-hook.sh` to the live `cabinet/scripts/hooks/session-stop.sh` on 2026-07-26, and `cabinet/scripts/hooks/README.md` no longer names the dead twin as the Stop hook. Neither is a claim about EVAL-008's current health: two independent reviews of this row disagreed on whether that eval passes, because it depends on a reachable control plane, and its result was identical on master and patched in both. Whatever EVAL-008 does today, it does it on master too.
- **Open:** `memory/golden-evals/framework/fw-a14-stop-guard.sh` still drives `cabinet/scripts/hooks/stop-hook.sh`, which `.claude/settings.json` wires to NO hook event. Measured 2026-07-28: 10/10 arms PASS against it. The guard runs every 6h in the live self-improvement validation gate, so it reports healthy, on schedule, about a file that never executes — while the live Stop hook (`session-stop.sh`), which writes the per-turn cost the spending caps read, has no coverage in this guard at all.
- **Why open:** re-pointing is not a one-line retarget. The guard's contracts are written against `stop-hook.sh` internals — at minimum the context-percentage threshold arms, which the live hook does not implement — so several arms must be re-derived from `session-stop.sh`'s actual signals before the target can move, and a wiring-drift assertion has to land with them or the same drift recurs silently. That is its own change with its own review surface, and folding it into a fail-closed patch is how the previous attempt at this pair went red.
- **Declared at:** `memory/golden-evals/framework/fw-a14-stop-guard.sh:42`
- **Anchor:** `RESIDUAL (RES-020)`
- **Retirement:** `SRC_HOOK` points at `cabinet/scripts/hooks/session-stop.sh`; every arm is re-derived from that hook's real signals (any arm asserting a threshold the live hook does not have is replaced, not deleted, by one asserting the signal that does exist); a wiring-drift arm reads `.claude/settings.json` and fails if Stop no longer resolves to the file under test; and the guard is demonstrated non-vacuous by failing against a deliberately broken copy of the live hook. In the SAME commit: delete this declaration from `memory/golden-evals/framework/fw-a14-stop-guard.sh` and flip this row to `retired`.

### RES-021 — the toolchain preflight catches a broken shim, not a probe-aware one

- **Phase:** enforcement-plane dependency preflight (2026-07-28), adversarial review of the fix itself
- **Status:** open
- **Closed:** `cabinet/scripts/hooks/pre-tool-use.sh` no longer fails open on a toolchain it cannot trust. A missing `cat jq grep sed awk tr date perl` refuses instead of allowing (measured on `8ffeae51`: with `jq` off PATH, 24 of 24 payloads that block on a healthy toolchain were ALLOWED, exit 0, zero bytes on stderr). A binary shadowed by a shell function or alias — the `BASH_ENV` route — is refused, because the resolution must be an absolute path. A shim that is merely BROKEN is refused: silent, failing, truncating, passing its input through, or answering with garbage, each pinned by an arm in `cabinet/tests/hook-regression/dependency-preflight.sh`. An unparseable `tool_name` is refused rather than allowed. And a parse cross-check requires the tool name jq returns to appear in the raw bytes jq was handed, which defeats the simplest substituting shim.
- **Open:** a shim that RECOGNISES the probe. The probe strings are fixed literals in the hook, so a `jq` that answers them honestly and lies only about `.tool_name` passes every check here; measured during review of this very change, it leaked 23 of 32 payloads. The parse cross-check raises the cost but is not a wall — the officer authors the payload, so pairing the shim with a command that embeds the substituted name defeats it. The precondition is real and already flagged in the launcher itself: `cabinet/scripts/start-officer-mac.sh:827` runs officers with `PATH="$HOME/.local/bin:$PATH"`, an officer-writable directory ahead of every system directory.
- **Why open:** the two genuine closures are both outside this block, and one of them was built and rejected during this change. (a) Resolving the enforcement toolchain by absolute path from a root-owned location touches every `jq`/`grep`/`sed`/`awk`/`tr`/`perl` call site in a 2600-line germline file. (b) Removing the writable directory from the launcher's PATH is a change to another germline file with its own blast radius on officer tooling. A third option — refusing when a dependency resolves through a directory this uid can write — was implemented and reverted: it refuses every synthetic PATH a hermetic harness can construct, so shipping it would have replaced a tested control with an untested one, which is the exact defect class this change exists to remove.
- **Declared at:** `cabinet/scripts/hooks/pre-tool-use.sh:96`
- **Anchor:** `RESIDUAL (RES-021)`
- **Retirement:** either (a) the hook resolves each enforcement binary once, from a root-owned directory, and every later call site uses that absolute path — with an arm proving a shim planted earlier on PATH is not consulted; or (b) `cabinet/scripts/start-officer-mac.sh` stops placing an officer-writable directory ahead of the system directories, with an arm asserting the launched PATH contains no directory writable by the officer's uid. Whichever lands, the `ADAPT-1` arm in `cabinet/tests/hook-regression/dependency-preflight.sh` is extended to a shim that answers every probe honestly AND embeds the substituted name in the payload, and must be refused. In the SAME commit: delete this declaration from `cabinet/scripts/hooks/pre-tool-use.sh` and flip this row to `retired`.

## Absorption — how a wave's residuals get here (COG-5 W2 done)

The rule this section originally stated as a future obligation has now been
executed once, so it is recorded as precedent rather than as a plan.

**What happened.** This register was authored at `a1357829`, when COG-5 W2 was
still on unlanded branches; it predicted two W2 residuals (a fabricated-evidence
custody channel, a `pwd`-fallback home-reach vector) and assigned them to the W2
landing integrator starting at `RES-012`. W2 landed FIRST — the register was the
last branch of that group to land — so absorption happened at THIS landing
instead, against `db180092`. Seven new marker sites were in the sweep surface and
the pin test was RED until all seven had rows.

**What that produced.** Four rows for seven sites, because two pairs are one
residual declared twice (mechanism + its test-side restatement): `RES-012`
(both predicted-`pwd` sites), `RES-013` (both fabricated-evidence sites),
`RES-014` and `RES-015`. `RES-014` and `RES-015` were NOT predicted — `RES-015`
comes from a different wave entirely (the widened boundary engine). That is the
point: the sweep found what the prediction missed.

**The standing rule for every future wave.** Two things make it a forcing
function rather than a hope:

- if the landed declarations carry the word token, the sweep sees them
  immediately and the pin test goes RED until each has a row;
- if they do not, the integrator must still register them — a residual declared
  in prose is exactly the failure mode this file exists to stop. Reword the
  declaration to the token in the same commit and both halves bind.

Order does not matter. Whichever lands last pays, and the gate names the exact
`path:line` it is missing.

## Legacy exemptions — shrink-only

Two marker sites in the sweep surface are NOT residuals and carry no row: the
two `RESIDUAL SCRUB` comment blocks in `cabinet/scripts/egg-export-manifest.txt`
— they describe scrub rules already EXECUTED (2026-07-21), not open channels.
They are exempted by exact `path:line` in the pin test (`LEGACY_EXEMPT` in
`cabinet/scripts/tests/test_declared_residuals_register.py`, with a hard
maximum) so the list can shrink and never grow. **The line numbers live only in
that test, deliberately:** any row added to the manifest above a marker shifts
its cite, and the test's own comment records each re-anchor with its cause
(233→235 by the egg egress-default flip, 235→242 by the captain-availability
dial, 242→248 by the captain-dates store). Quoting them here as well made this
paragraph rot silently on the first such shift. Rewording the markers out of the sweep is blocked for a good reason:
that file is inside the frozen COG-4 review digest scope, and changing marker
TEXT would force a re-bind ceremony (adding unrelated manifest rows does not).

## Known limits of this register — stated, not hidden

- **Lowercase prose declarations are NOT covered.** 239 lowercase uses of
  "residual" span 107 files (291 / 119 at `db180092` — the class grew, the
  limit did not change). Most describe channels already CLOSED, or
  threat-model facts explicitly "accepted and stated". A few are genuinely open
  and unregistered — `cabinet/mcp-server/server.py:537` ("residual gap tracked
  for the Captain as a big-rock") is the clearest. They are not registered here
  because promoting one requires per-item byte verification, and a row asserting
  more than the code declares is worse than no row. Remediation for any of them
  is mechanical and one commit: reword the declaration to the word token, add a
  row.
- **The operative ledger + plan pair carries 11 unregistered token sites.**
  Found by the corrected survey and named here rather than left buried. They
  are NOT rows because each already sits inside a ledger entry whose own
  `status` field is authoritative and whose owner is named — asserting a status
  here that I have not byte-verified would be exactly the over-claim this file
  forbids. The open-looking ones, for whoever picks them up:
  `operative-egg-ledger-2026-07-07.yml:1034` (a posture-presets comment still
  names the Captain; dir is schg, routed to a handback) · `:1698` (whether CC
  2.1.202 emits a Notification on real model-fallback engagement — needs one
  observed live page) · `:2782` (**the same exposure as RES-001, stated wider**:
  `platform.yml`/`peers.yml`/`contexts/*.yml` are officer-writable sources
  needing their own lock — RES-001 states only what the CODE declares, which is
  the narrower pair) · `:2843` (Captain first-name tokens + the real Chair bot
  handle, recorded for follow-up rows) · `:2871` (on the R163 flag-(e)
  worklist) · `:3194` and `operative-egg-plan-2026-07-07.md:921` (the same
  finding: pre-existing DB-backed `/api/library/*` routes stay live beside the
  zero-DB graph, routed to the SEARCH lane) · `:3220` (library building art,
  runbook-tracked). `operative-egg-plan-2026-07-07.md:980` reads open but
  `ledger:3243` records it RESOLVED (ceremony executed 2026-07-18), and
  `ledger:1689` is RES-002 restated. Promoting any of these is one commit:
  verify the ledger row's status, then add a row here.
- **`RETIREMENT CONDITION` vacuity guards are deliberately NOT registered.**
  The token appears 42 times / 24 files at `a1357829` and 71 / 33 at
  `db180092`, almost all in the COG-4/COG-5 test corpora, and most uses are
  such a guard. (This bullet read "there are 56" — the pre-correction `grep -I`
  number that the survey table already fixed to 42 and this line kept. Same
  undercount, second home; corrected at landing.) They are a different class:
  each one already trips RED the moment its target lands, so it CANNOT rot
  silently — it is its own forcing function. Duplicating them here would add
  churn and collide with in-flight corpus surgery without adding a single
  guarantee.
- **This register pins declarations, not truth.** It proves a declared residual
  still exists where it says it does and has a stated way to die. It cannot
  prove the declaration was accurate when written. `RES-001`..`RES-011` were
  each re-verified against the bytes at `a1357829` and their cites re-checked
  at `db180092`; `RES-012`..`RES-015` were verified against `db180092`. A later
  reader should do the same before relying on one — and note that this landing
  found two arithmetic errors in the register's own survey, so "re-verified"
  means re-measured, not re-read.
