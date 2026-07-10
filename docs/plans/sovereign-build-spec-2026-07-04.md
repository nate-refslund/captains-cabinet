# Sovereign Posture — Merged Build Spec (synthesis of record)

**Date:** 2026-07-04 · **Worktree:** `<live checkout>/.claude/worktrees/sovereign-posture` · **Branch:** `feat/sovereign-posture` @ 01015e5c
**Live-checkout constraint:** a SECOND agent is improving the guardian track on `feat/fidelity-harness-design` in the live checkout. Build is **ADDITIVE-FIRST** — new modules wherever possible, surgical edits to shared germline files, each named in a `conflict_risk` note so rebase-before-merge can sequence overlaps. Germline edits are authored as worktree commits AND exported as diffs into the ONE amendment package; they land at the Captain's unlock window, not by racing the guardian agent's live commits.
**Merge order of record (ALIGNMENT ranking, BOUNDLESS ceiling grafted):** CONSTITUTION kernel is the spine → RUNTIME ops conformed to kernel APIs → INTELLIGENCE fidelity/gate layer post-kill-list. ONE combined amendment, ONE apply token (`apply sovereign posture`), ONE unlock window.
**Corridor:** each constituent design ran `analyzePlan` clean; every implementation lane MUST run `analyzePlan` on its concrete diff before generating code (the rule belongs at code-generation time, per lane).

---

## §0 — DOCTRINE (one paragraph)

Posture is a **selection dimension of the ONE authority matrix**, never a second enforcement story. Verdict *semantics* for both postures live in the germline floor `framework/policies/authority-matrix.yml`; posture *selection* lives in Captain-locked `instance/config/posture.yml`; ceiling *grants* live in Captain-locked `instance/config/standing-grants.yml`. **Guardian = today's root `verdicts` table, byte-identical**, and is the fail-safe answer to every ambiguity (absent/corrupt/unlocked/mismatched config, unknown posture, import failure, Redis outage). Sovereign removes every human-wait that is not (a) integrity substrate, (b) Captain-owned personal outbound (ACT-NOT-DRAFT), or (c) a missing standing grant — and a missing grant never asks per-item: it files a NEED and the chain continues. **Demote always narrows: evidence beats posture.**

---

## §1 — FROZEN INTERFACES (lanes CONSUME, never redefine)

### FI-1 · `instance/config/posture.yml` (closed-key schema; germline + schg)
```yaml
version: 1
status: ruled
ruled_at: 2026-07-05T00:00:00Z
basis: "<verbatim Captain directive essence>"
deployment: mini-bakery        # MUST equal CABINET_ID env (default "main"); mismatch ⇒ treated absent ⇒ guardian
flavor: org                    # org | personal   (personal ⇒ external_comms grants REFUSED by grants loader — structural ACT-NOT-DRAFT)
posture: sovereign             # guardian | sovereign
lanes: {bakery: sovereign}     # OPTIONAL per-lane override
caps: {hard_multiplier: 10}    # runaway mechanical hard-stop = per-kind/day cap × this; freeze-on-hit
max_auto_exec_steps: 5         # sovereign only; guardian forced 2
```
Closed set `{version,status,ruled_at,basis,deployment,flavor,posture,lanes,caps,max_auto_exec_steps}`. **Unknown key ⇒ corrupt ⇒ guardian + deduped need.** `resolve_posture()` returns `sovereign` IFF: present ∧ schema-valid ∧ `deployment==CABINET_ID` ∧ `is_locked(schg)` (`os.stat().st_flags & stat.SF_IMMUTABLE`, non-Darwin ⇒ False). Env `CABINET_POSTURE=guardian` narrows anywhere (emergency drop-brake); env `CABINET_POSTURE=sovereign` is **IGNORED** (never widens). **NO `CABINET_POSTURE_UNLOCKED_OK` env override** (killed — REDTEAM/ALIGNMENT critical): tests inject `is_locked` and point `CABINET_ROOT` at a tmp tree they own.

### FI-2 · `instance/config/standing-grants.yml` (germline + schg) + tamper model
```yaml
version: 1
grants:
  - {id: GRANT-<slug>, deployment: mini-bakery, risk_class: external_comms, action_types: [external_email],
     lanes: [bakery], scope: {recipient_allowlist: ["*@example.com"], max_eur_per_day: 0, vendor_allowlist: []},
     rate: {max_per_day: 10}, expires: 2026-10-03, granted_by: "Captain (Ada)", granted_at: 2026-07-05T..Z,
     basis: "NEED-1a2b3c4d", revoked: false}
```
`load_grants`: absent/unparseable/**NOT-schg-locked ⇒ `[]` + deduped need**. `check(risk_class, action_type, *, lane, root, now) -> {granted, grant_id, reason}` enforces ALL of: deployment==CABINET_ID ∧ `risk_class ∈ matrix.hard_ceiling` (else drop+need) ∧ action_type ∈ action_types ∧ lane match ∧ not expired (≤90d horizon at grant time) ∧ not revoked (file flag OR Redis tombstone `cabinet:grant:revoked:<id>`; **Redis unreachable ⇒ treated revoked**) ∧ rate not exhausted (`cabinet:grant:count:<id>:<date>`, unreadable ⇒ not granted) ∧ `veto_registry.is_vetoed` false ∧ **class hard-scope predicate holds** (recipient∈allowlist / amount≤max_eur_per_day / vendor∈allowlist). **Flavor=personal ⇒ external_comms grants dropped fail-closed + need** (structural ACT-NOT-DRAFT — the captain's personal surfaces stay queue_draft-only in every posture). Order: killswitch > veto/tombstone > grant(+hard-scope) > need. **v1 dormancy note:** no ceiling *executor* exists today and the acting-lane ACTION_TYPE_MAP stamps NO ceiling action_types → the `standing_grant` path is **inert at the acting lane in v1**; the mechanism ships but a ceiling class only auto-fires once a scope-enforcing executor for it lands with its own tests (REDTEAM: never resolve a ceiling to allow without an enforcing executor).

### FI-3 · ONE needs-ledger — `framework/authority/needs.py` (germline FILES+hook; DATA is SKIP-class)
Kills the three-way split. Ledger `shared/interfaces/needs-ledger.jsonl`, **O_APPEND, last-write-wins per id** (no read-modify-write race — the reason veto_registry.next_id was rejected for the hook path).
- `need_id(kind,risk_class,action_type,lane) = "NEED-"+sha256(f"{kind}|{risk_class}|{action_type}|{lane}|{CABINET_ID}").hexdigest()[:8]` (content-fingerprint = free dedup + unguessable-enough).
- `file_need(kind, *, risk_class=None, action_type=None, lane=None, why, unblocks="", proposed_grant_line=None, cost_of_delay="medium", cost_note=None, filed_by, cid=None, root=None) -> str|None` — **never raises, ~ms, single append.** Re-file bumps `count`/`last_seen`. Auto-composes the **NARROWEST** `proposed_grant_line` for `kind=standing_grant` (single recipient/board/lane from the blocked step — never `lane:'*'`, never empty `action_types`). Denied-and-suppressed ⇒ no-op. `cost_of_delay=="blocking"` (kinds `standing_grant|credential`) ⇒ ALSO `intake.enqueue(urgency_tier="ping-now")`.
- `list_open(now)` — inline 30d-expiry sweep on read; compacted; every field `_no_marker`-safe. `mark(need_id, status, *, by, reason=None)` — status ∈ **`{open, approved_pending_apply, granted, denied, snoozed, expired, superseded}`**; deny stamps 90d suppression. `cross_check_grants(check_fn)` closes covered `standing_grant` needs.
- `needs_enabled()` = `resolve_posture()=="sovereign" OR CABINET_NEEDS_WIRED=1 OR instance/config/needs-wired` — every filing seam short-circuits false ⇒ bit-identical default.
- Kind vocab `{access,credential,decision,standing_grant,resource,hardware,capability,unfreeze}`. Emits via `emitter.py`: `need_filed,need_granted,need_denied,need_snoozed,need_expired,need_escalated`.

### FI-4 · Binder grant/deny/snooze/rearm grammar (hex ids)
`_NEED_RE = r'^\s*(grant|deny|later|snooze)\s+need[-_ ]?([0-9a-f]{8})\b(?:\s*[:—-]\s*(.*))?$'` (matches the fingerprint id — RUNTIME's digit-only pattern is replaced). `_REARM_RE = r'^\s*rearm\s+([a-z0-9_.-]{1,40})\b'`. Collision-free vs `_APPROVE_RE/_CONFIRM_LEAD_RE/_UNDO_RE/_NEVER_RE/_LIFT_RE/_VETO_CONFIRM_RE`. Armed on `captain_verified AND CABINET_NEEDS_WIRED=1`, routed in the veto-command slot, **fail-closed passthrough (handled=False) on unknown/stale id**. `grant` ⇒ `mark(approved_pending_apply)` + receipt rendering the **machine-effective scope in plain language** ("this grants: ANY external email to `*@example.com`, lane bakery, ≤10/day, until 2026-10-03") + the one paste `sudo bash cabinet/scripts/grant-apply.sh NEED-<hex>`. `deny[: reason]` ⇒ `mark(denied)`+90d suppress. `later|snooze` ⇒ `mark(snoozed)`+7d. `rearm <kind>` ⇒ synchronous scoped canary → green `unfreeze` else stays frozen with reason.

### FI-5 · Runaway multiplier + `framework/policies/immutable-core.yml`
`caps.hard_multiplier` **default 10** (posture.yml-tunable). At per-kind/day cap ⇒ guardian **block** / sovereign **alarm+proceed**; at `cap × hard_multiplier` ⇒ **`freeze(kind,"runaway hard-stop")` + block in BOTH postures**. **Unreadable Redis counter ⇒ block in BOTH postures** (INT-13's alarm+proceed carve-out killed). `immutable-core.yml` (lives under `framework/policies/` ⇒ auto-covered by germline DIRS + schg) is THE single source of Ring-0 paths; a **lockstep-consistency meta-test** drives all four germline lists (`pre-tool-use.sh §5 case`, `§5b GERM_PATH_RE`, `base-safety.yml`, `germline-lock.sh FILES`) off `immutable-core.yml ∪ the new-file set` and diffs them — the single mechanism for every germline-list addition (SOV-C8).

---

## §2 — MERGED ARCHITECTURE DECISIONS (judge fixes applied inline)

**D1 Posture tables, not overlays.** Floor gains top-level `postures:` policy key with a FULL `verdicts` table per non-default posture (`sovereign` only in v1). Guardian ≡ root table; validator **rejects** a `postures.guardian` key. Full tables are auditable whole and kill the widening-merge bug class.

**D2 `standing_grant` verdict — ceiling rows only.** Auto IFF a Captain-signed, schg-locked, unexpired, unrevoked grant with a **satisfied hard-scope predicate** exists; else file NEED + gate this step while the chain proceeds. FIX-6 shape survives (ceiling rows single-`"*"` wildcard, verdict ∈ `{always_gated, standing_grant}`, `auto` structurally impossible). Root/guardian table may NOT contain `standing_grant`.

**D3 Sovereign non-ceiling semantics** (exact table §2.1). `act_with_undo` where inverses exist; `notify_after` for consequence-bearing irreversibles (the tell IS the audit); `auto` for high-volume local reversibles. **No `auto_with_veto_window`, no `classifier`** — verdicts must not promise unbuilt machinery (rejects INT-13 W3 deploy_nonprod=classifier; deploy_nonprod=`notify_after` until `classify_deploy` is actually wired as its own item).

**D4 Gate allow-set `{auto, notify_after}`.** `notify_after` at the officer gate = allow **AND enqueue a real tell** (ALIGNMENT fix — the gate returns None so no acted_row exists; SOV-3 emits an `org_event` the SOV-6 digest renders; test asserts a sovereign notify_after allow produces a rendered digest line, else the cell stays propose in v1). `act_with_undo` still blocks at the officer gate and routes to the acting lane (undo-integrity, not human-wait). Guardian tables contain no `notify_after` ⇒ widening is sovereign-only, guardian byte-parity pinned.

**D5 Signing = filesystem, not crypto.** Captain signature = ruling header + macOS `schg` (root-only) + hook coverage. No HMAC (a same-uid key is worthless; a root key daemon is deferred v2). Runtime attestation `os.stat().st_flags & SF_IMMUTABLE`.

**D6 Fail-safe polarity per file.** posture.yml absent/corrupt/unlocked/mismatch ⇒ **guardian**. standing-grants.yml absent/corrupt/unlocked ⇒ **empty**. Env may only NARROW. (No dev widen-flag — killed.)

**D7 Grants change ONLY via `sudo grant-apply.sh` in an unlock window (RUNTIME R1 wins).** Binder `grant NEED-x` ⇒ `approved_pending_apply` + one pasted sudo command. **KILLED: the Telegram silence-seal root grant-writer** (INTELLIGENCE §3.4/INT-8) — it turns the Captain's Telegram session into a network-reachable authority-minting credential and breaches Decision B / its own Ring-0. `grant-apply.sh`: root re-exec guard → load NEED → refuse unless `approved_pending_apply` → refuse scope-mismatch vs recorded need scope → refuse ceiling class without `ceiling_ack` → `germline-lock.sh unlock` → append → validate via `grants.py --validate` (abort+restore on fail) → commit → lock → `mark(granted)` → receipt. Optional `unlock --only <file>` so grant windows don't de-posture the whole estate (BOUNDLESS medium). Zero-paste root grant-writer stays a separately-ratified v2 question.

**D8 `load_policies` refuses layered matrix override + the runtime gate validates the merged floor.** Preset/instance layer with `type: authority_matrix` or name `authority-matrix` ⇒ WARN+skip (framework floor wins). PLUS (REDTEAM HIGH): the runtime gate calls the SAME validator as CI (`no_ceiling_or_prod_auto` + `_validate_postures`) on the merged winner and **fails CLOSED (propose-only) on validation failure or missing floor** (never fail-open); AND `instance/config/policies/` joins the germline/schg set. CI asserts runtime-loader and validated-loader return identical verdicts for the shipped floor.

**D9 Posture never enters graduation.** No posture param in `graduation.evaluate`, not in the cell key, no posture-keyed bars. Bars define PROOF; posture defines what unproven states UNLOCK (EARN-DEMOTION precedent). `read_cell_state` unchanged.

**D10 Acting lane reads the matrix at runtime, gated on posture-config presence.** No posture.yml ⇒ today's exact code path, byte-identical. posture.yml present (even `guardian`) ⇒ per-card routing consults `resolve_verdict` via the established `cabinet/scripts/lib` path-insert (ONE implementation, no function move). Guardian-table routing == today's mechanical outcome for every stampable action_type × state (proven P4).

**D11 Caps → alarms in sovereign; 10× mechanical hard-stop freezes the kind.** Guardian keeps blocking caps (today's bytes). Sovereign: at cap ⇒ alarm+proceed; at `cap×hard_multiplier` ⇒ freeze+block. Unreadable counter blocks in BOTH. Evidence brakes (undo-rate breaker, veto, canary, silence→content-audit) unchanged. **KILLED: INT-13 unbounded MAX_PER_RUN soft-target** — MAX_PER_RUN=8 stays in BOTH postures (standing Captain anti-runaway ruling; never fires honestly = integrity, not human-wait). MAX_AUTO_EXEC_STEPS → posture (2 guardian / 5 sovereign).

**D12 Silence breaker keeps a CONTENT-review forcing function in sovereign (REDTEAM critical fix; resolves the R4-vs-INT13 contradiction).** After N untouched acts on a kind: force **(a) a synthetic canary (mechanism proof, RUNTIME R4) AND (b) an LLM adversarial audit of the ACTUAL content of the last N acts** (REDTEAM — a create/reverse probe and "sends succeeded" cannot detect wrong content). Red audit or red canary ⇒ propose_only + ping-now + freeze. INTELLIGENCE's "sends-failing ⇒ pause" is retained as an ADDITIONAL integrity trigger (acts invisible), never the sole substitute. Pure "told-and-silent = consent" is deleted.

**D13 Inbound-provenance cards are NEVER act-first eligible, any posture (REDTEAM medium).** `injection_suspect` is self-attested by the (possibly compromised) proposer; sovereign amplifies a classifier miss into an immediate act. Cards derived from untrusted inbound (email/Teams captured content) carry a `provenance=inbound` stamp and are propose/draft-gate only regardless of posture; a second independent classifier pass runs in the executor perimeter (not the proposer) before any sovereign act.

**D14 `officer_dispatch`/`delegate_work` stay HELD in v1 (REDTEAM cascade fix).** A dispatch that makes another agent act is not reversible by undoing the dispatch row. `investigation_run` (internal, stoppable, read-shaped) drops its hold in sovereign; **`officer_dispatch`/`delegate_work` do NOT** — filed as a follow-up "cascade-aware dispatch" once downstream reversibility is proven. This partially overrides INT-11.

**D15 Sovereign self-improvement: EVIDENCE runs now, germline CODE auto-apply stays DARK (REDTEAM critical fix).** `gate.ratify` (produces evidence, applies nothing) + `run_gate_review` (verdict_gate cell fuel) + skill auto-promotion (Ring-2 file, no root) + posture-aware `can_install` ship LIVE-capable. **`gate-apply.sh` + `com.cabinet.gate-apply` root daemon ship DARK** and are NOT loaded by any setup script. **KILLED: running the S1/S2/S3 pytest suite as root** — the daemon does sandboxed UNPRIVILEGED verify (drop-to-nobody / vercel-sandbox microVM) pinned to a bundle content-hash; root does ONLY a non-executing, hash-matched `git -c core.hooksPath=/dev/null apply` reading `immutable-core.yml` + revert plan from the LOCKED live tree (never the bundle). Until that sandbox harness exists + the Captain explicitly `sudo launchctl load`s the daemon, germline apply stays Captain-manual even in sovereign (directive f already exempts the immutable core; we extend the exemption to the apply lane itself).

**D16 verdict_gate machine promotion — sovereign-only, EARN-DEMOTION-safe (INT-4, approved).** `_REVIEW_SOURCES += "verdict_gate"`. `compute_ratios`: `confirmed` counts from `verdict_human` OR (`verdict_gate` AND `resolve_posture()=="sovereign"` via lazy import ⇒ ImportError/exception ⇒ guardian ⇒ bit-identical today). `wrong` from any source unchanged. `verdict_gate` stamped only for acted rows clearing the full machine bar: `ttl_ok` ∧ no undo ∧ no veto on the cell ∧ canary+falsifier green in window ∧ **cell not within `cooldown_days` of a demote** (ALIGNMENT anti-flap fix). Posture read at compute time ⇒ a sovereign→guardian flip only ever REDUCES confirmed counts (pinned by test).

**D17 Personal-agent reframe — harness objective, not graduation (INT-1/2/3).** Third `OUTCOME_RUBRIC` judge pass in `scorer.py`: anonymized CANDIDATE A/B (clone_draft vs real_reply, assigned by `sha256(case_id)` parity), judged ONLY against reconstructed intent; reuse `_grounding_ok`/`_topic_overlap` guards verbatim; AGB (as-good-or-better) is the headline, decision-match a diagnostic. **Default `identity_mode='clone'` until the first AGB baseline is cut** (ALIGNMENT — flipping to 'agent' silently changes shard outputs, breaching the A/A invariant); stamp `identity_mode` into every rec; segment cusum baselines per identity. `graduation.py` untouched.

### §2.1 — `postures.sovereign.verdicts` (exact, added under the same policy; root `verdicts` byte-untouched)
```yaml
    postures:
      sovereign:
        verdicts:
          reversible:        { graduated: auto, eligible: auto, propose_only: auto, unmeasured: auto, demote: propose_only }
          pm_write:          { graduated: act_with_undo, eligible: act_with_undo, propose_only: act_with_undo, unmeasured: act_with_undo, demote: propose_only }
          calendar_write:    { graduated: act_with_undo, eligible: act_with_undo, propose_only: act_with_undo, unmeasured: act_with_undo, demote: propose_only }
          internal_comms:    { graduated: notify_after, eligible: notify_after, propose_only: notify_after, unmeasured: notify_after, demote: propose_only }
          deploy_nonprod:    { graduated: notify_after, eligible: notify_after, propose_only: notify_after, unmeasured: notify_after, demote: propose_only }
          external_comms:    { "*": standing_grant }
          deploy_prod:       { "*": standing_grant }
          spend:             { "*": standing_grant }
          secrets:           { "*": standing_grant }
          network_write:     { "*": standing_grant }
          credentials_grant: { "*": standing_grant }
```
Demote ⇒ propose_only everywhere (posture-invariant; validator asserts `table[rc]["demote"] == root[rc]["demote"]` for every non-ceiling rc).

### §2.2 — REJECTED judge fixes (with argument)
- **REJECT INT-13 "unreadable counter ⇒ alarm+proceed."** A Redis outage degrades the killswitch/veto/freeze planes too; proceeding uncounted compounds a partial failure. Fail-closed in BOTH postures.
- **REJECT INT-13 MAX_PER_RUN soft-target + W9 act-at-≥0.5-confidence.** MAX_PER_RUN=8 is a standing anti-runaway ruling that never fires honestly (integrity, not human-wait). Floor stays 0.65; sovereign fallback = re-gather-once → drop-with-FYI (never park on a human, never lower the bar).
- **REJECT INT grant-seal silence-window (all classes).** See D7. Superseded by RUNTIME R1.
- **REJECT INT auto-thaw of Captain-caused freezes.** Auto-thaw restricted to `source=machine` freeze rows at 3-greens+7d-clean; captain-caused freezes thaw only via the `rearm` verb (Captain judgment supplements; 1 synchronous green suffices). Freeze rows gain a `source: machine|captain` tag.
- **REJECT the deployments-map posture.yml schema (RUNTIME §0.1) and `grant_for()` API.** Kernel's closed-key single-deployment schema (FI-1, extended with `caps.hard_multiplier`+`max_auto_exec_steps`) and `check()`/`record_use` are the contract; RUNTIME/INT rewrite call sites.

---

## §3 — HUMAN-WAIT DISPOSITION (final rulings; guardian keeps ALL byte-identical)

| Wait | Sovereign disposition |
|---|---|
| reversible propose_only below graduated | **auto** (lane journals where inverses exist) |
| pm_write / calendar_write | **act_with_undo** at all non-demote states (== guardian; undo = integrity) |
| internal_comms below graduated | **notify_after** (+ real tell wired, D4); `officer_dispatch` stays HELD (D14) |
| deploy_nonprod below eligible | **notify_after** (classifier deferred, D3) |
| six hard ceilings always_gated | **standing_grant**: auto IFF signed+locked+unexpired+unrevoked grant w/ hard-scope; else NEED+proceed. Never unconditional auto. Inert at acting lane v1 (FI-2) |
| external_comms on the captain's personal surfaces | **KEEP** (ACT-NOT-DRAFT; grants loader structurally refuses flavor=personal external_comms) |
| unmeasured-cannot-auto | **superseded for non-ceilings** (Captain-ratified, eval-014); stays for ceilings + root/guardian forever |
| daily caps 40/20 | **alarms** + 10× freeze hard-stop; unreadable ⇒ block both postures |
| MAX_AUTO_EXEC_STEPS=2 | **5** (posture.yml); every step still inverse+journal |
| MAX_PER_RUN=8 | **KEEP both postures** (anti-runaway ruling) |
| frozen kind permanent | **KILLED permanence**: `unfreeze` primitive (last-op-wins mirror + canary-receipt); machine-origin auto-thaw, captain-origin via `rearm` |
| silence breaker 30-untouched | **content-audit + canary** (D12), not consent-by-silence |
| mission_propose / investigation_run holds | sovereign auto-adopts non-ceiling mission graphs (notify_after); investigation_run hold drops; officer_dispatch/delegate_work stay held (D14) |
| capability install captain-approval | posture-aware `can_install` (sovereign + non-ceiling + Gate evidence); **ceiling-touch veto stays absolute** |
| skill promotion via CoS loop | validation-evals-green ⇒ auto-promote (notify_after) |
| germline amendments Captain-applied | Evidence Gate + DARK root apply lane EXCEPT Ring-0 (Captain-only forever) — germline CODE apply stays Captain-manual until sandbox+daemon (D15) |
| Fable-unavailable ⇒ judgment stops | file `kind=resource` need; route non-judgment work onward; never idle |
| killswitch / journal-or-downgrade / TOCTOU / tripwire / inverse-required / veto / demote-on-evidence | **KEEP all** — integrity substrate, never fires in honest hot path |

Net sovereign hot path: zero per-item human approvals. Every surviving wait is killswitch/undo-integrity, Captain-owned personal outbound, or a missing standing grant (auto-files a need and proceeds).

---

## §4 — IMPLEMENTATION LANES (9)

> Every lane: run Corridor `analyzePlan` on the concrete diff before coding; keep guardian bit-identical with no posture config; new invariants get NEW evals; `conflict_risk` names EVERY existing shared file the lane edits (rebase-before-merge depends on it).

### SOV-1 · KERNEL CORE — posture/grants/needs modules (mostly additive)
**Files (NEW):** `framework/authority/posture.py`, `framework/authority/grants.py`, `framework/authority/needs.py`, `instance/config/posture.yml.example`, `instance/config/standing-grants.yml.example`. **Edit (shared):** `framework/events/emitter.py` (`VALID_EVENT_TYPES += need_* / cap_alarm / kind_unfrozen` — append-only).
**Detail:** Implement FI-1..FI-4 exactly. posture.py mirrors lane.py FIX-4 purity + action_exec loader semantics, zero policy_engine imports. grants.py fail-closed loader + `check()`/`record_use` with hard-scope predicates and flavor=personal external_comms refusal. needs.py O_APPEND JSONL, content-fingerprint ids, lifecycle verbs, `needs_enabled()` short-circuit. `conflict_risk`: emitter.py only (append to a list — LOW).
**Tests:** posture truth-table (absent/corrupt/unknown-key/mismatch/lane-override/env-narrow-only/is_locked-injectable); grants (empty/corrupt/unlocked ⇒ [], schema line-drop, match predicate, hard-scope enforce, flavor-personal refusal, tombstone+Redis-down⇒revoked, rate/expiry); needs (id determinism+dedup, concurrent-append tolerance, lifecycle transitions, never-raises, `<50ms` hook-latency smoke, `needs_enabled` false ⇒ no-op).
**depends_on:** []

### SOV-2 · MATRIX — posture axis + validator (germline data+validator)
**Files (edit, germline):** `framework/policies/authority-matrix.yml` (add §2.1 `postures.sovereign` block + doctrine comment; root `verdicts` byte-untouched), `framework/authority/matrix.py`.
**Detail:** matrix.py: `VERDICTS += "standing_grant"`; `POSTURES=frozenset({"sovereign"})`; `_POLICY_KEYS += "postures"` (OPTIONAL, back-compat); `_validate_verdicts(..., posture_table=False)` (root: standing_grant forbidden; posture table: ceiling rows single-`"*"` ∈ {always_gated,standing_grant}, non-ceilings all 5 states minus standing_grant); `_validate_postures` (keys ⊆ POSTURES, guardian-key raises, demote-invariance vs root); `no_ceiling_or_prod_auto` sweeps `postures.*`. `conflict_risk`: authority-matrix.yml + matrix.py (germline — guardian agent may touch; MEDIUM; additive key minimizes collision).
**Tests:** rejection cases (postures.guardian, standing_grant in root / on non-ceiling posture row, auto in posture ceiling row, demote drift, unknown posture key, missing state); shipped floor self-validates; FIX-6/FIX-7 swept per posture; legacy loader still ingests.
**depends_on:** []

### SOV-3 · GATE — resolve_verdict posture params + ceiling branch + floor-only refusal + validate-on-load (germline)
**Files (edit, germline):** `cabinet/scripts/lib/policy_engine.py`, `cabinet/scripts/policy-shadow.py`.
**Detail:** `resolve_verdict` gains keyword-only `posture=None, postures=None` (3 positional callers/tests untouched; unknown/malformed ⇒ root table). `_eval_authority_matrix`: fail-safe module imports of `resolve_posture`/`grants`/`needs`; move `lane=resolve_lane()` above the ceiling short-circuit; resolve posture once; ceiling branch per D2 (sovereign ⇒ `grants.check` ⇒ attributed allow + `record_use`, else `needs.file_need` + GATED-sovereign message; **guardian messages BYTE-IDENTICAL**); step-4 allow-set `{auto, notify_after}` + notify_after tell-emit (D4) + misplaced-standing_grant defense. `load_policies` refuses preset/instance authority_matrix (WARN) AND runs `no_ceiling_or_prod_auto`+`_validate_postures` on the merged floor, **fail-closed** (D8). policy-shadow mirrors; record += `posture,grant_id,need_id`. `conflict_risk`: policy_engine.py + policy-shadow.py (hottest germline gate files; HIGH — coordinate rebase; edits localized to named line ranges).
**Tests:** P1 frozen guardian truth-table (no-kwargs / posture="guardian" / inert-postures-present all equal); sovereign resolve sweep; ceiling branch with injectable grants/needs (granted⇒None, else message carries NEED id, guardian strings exact); notify_after allow emits a tell; load_policies refusal + fail-closed validation; existing truth-table tests GREEN UNCHANGED.
**depends_on:** [SOV-1, SOV-2]

### SOV-4 · ACTING — posture routing + caps posture-param + mission auto-adopt + inbound-provenance gate (germline)
**Files (edit, germline):** `framework/acting/run_action_lane.py`, `framework/frontdoor/action_exec.py`.
**Detail:** run_action_lane `_load_posture_ctx()` at lane start: `posture.posture_config_present()` false ⇒ None ⇒ **today's exact path byte-identical** (incl. the `done: presented N action card(s)` summary); present ⇒ matrix_policy + `resolve_verdict`/`risk_of` via path-insert; per-card routing (D10): `{act_with_undo,auto,notify_after}` ⇒ existing mechanical chain (inverse-per-step KEPT; auto-verdict kind lacking inverse ⇒ propose + `kind=capability` need); `{propose_only,always_gated}` ⇒ propose; `standing_grant` ⇒ grants.check (dormant v1). Inbound-provenance stamp ⇒ never act-first eligible (D13). action_exec: `_caps_would_exceed` posture-param (D11); `KINDS_REQUIRE_EXPLICIT_APPROVE`/`_step_held_reason` posture-aware (mission_propose non-ceiling graphs adopt in sovereign; investigation_run hold drops; **officer_dispatch/delegate_work stay held**, D14); `_gate_chain` files `kind=access|credential` needs on denylist/missing-cred; `MAX_AUTO_EXEC_STEPS`→`_max_auto_steps(posture)` (2/5); MAX_PER_RUN=8 unchanged. All filing `try/except` — never blocks an act. `conflict_risk`: run_action_lane.py + action_exec.py (germline acting; HIGH — SINGLE OWNER of action_exec.py across all lanes to avoid split-brain).
**Tests:** P3 sentinel (absent posture ⇒ matrix/grants/needs raise-if-imported untouched); P4 guardian+file-present parity (5 action_types × 5 states == legacy); sovereign routing; caps alarm/hard-stop/fail-closed per posture; inbound card never act-first; mission auto-adopt non-ceiling only, officer_dispatch held; existing lane corpus green.
**depends_on:** [SOV-1, SOV-2, SOV-3]

### SOV-5 · BRAKES — caps→alarms + unfreeze + silence→content-audit + freeze-origin (germline)
**Files (edit, germline):** `framework/frontdoor/actfirst_canary.py`, `framework/frontdoor/action_undo.py`.
**Detail:** actfirst_canary `cap_check`/`incr_and_check` posture-param (guardian bytes unchanged; sovereign cap⇒alarm+`cap_alarm` once/kind/day, `cap×10`⇒freeze+block; unreadable⇒block both); `run_silence_breaker` sovereign ⇒ force synthetic canary + **LLM content-audit of last N acts** (D12), freeze on red-either; `run_canary` mints a green-canary receipt token + accepts `kind=` scoping; `run_thaw(kind)` requires 3 greens+7d-clean, **machine-origin only** auto (captain-origin via rearm). action_undo `unfreeze(kind, reason, *, canary_receipt, source, now)` appends `op:'unfreeze'` mirror row + best-effort Redis DEL; `_kind_in_mirror` → **last-op-wins per kind**; refuse unfreeze without a ≤24h green receipt; `freeze(...)` gains `source: machine|captain` tag + best-effort `file_need(kind='unfreeze')` (injected callable, import-guarded — no needs hard-dep at module load). `conflict_risk`: actfirst_canary.py + action_undo.py (germline brakes; HIGH — SINGLE OWNER of both across lanes; SOV-8's canary reuse imports, does not edit).
**Tests:** guardian byte-identity; sovereign cap alarm/hard-stop/freeze; silence ⇒ canary+content-audit (mock LLM), freeze on red content; unfreeze last-op-wins across Redis+mirror, receipt required, stale-receipt refused; captain-origin not auto-thawed; freeze files unfreeze need once; action_undo imports with needs absent.
**depends_on:** [SOV-1]

### SOV-6 · FRONTDOOR — needs digest leg + binder verbs + grant-apply.sh + attention dedup
**Files (edit, germline):** `framework/frontdoor/tell_surface.py` (needs leg, additive `needs_rows=None` param — byte-identical default). **Files (edit, free):** `framework/frontdoor/tell_digest.py` (`gather_needs_rows` + **feature-detect 4-vs-5-arg** `build_digest` call so it merges before OR after the tell_surface diff), `framework/frontdoor/binder_wire.py` (FI-4 verbs, dark behind `CABINET_NEEDS_WIRED`), `framework/frontdoor/attention_drain.py` (NEED-tagged/ask-shaped dedup + tier demote). **Files (NEW):** `cabinet/scripts/grant-apply.sh`.
**Detail:** `🙋 NEEDS` section between WATCHING and SELF (NEED-<hex> ids only, never bare integers; all `_no_marker`; `approved_pending_apply` rows show the sudo one-liner; footer grant/deny/later/rearm grammar only when needs present). Binder grant renders **machine-effective scope in plain language** (poisoned-need fix) + narrowest default. grant-apply.sh per D7. `conflict_risk`: tell_surface.py (germline — SINGLE OWNER of the needs leg; RUNTIME/INT duplicate diffs killed); tell_digest.py/binder_wire.py/attention_drain.py (free); grant-apply.sh new. MEDIUM.
**Tests:** empty-needs digest byte-identical to today (golden); NEED-id-never-integer property; TI-5 producer-crash ⇒ briefing still sends; binder each verb happy + stale-hex-id passthrough + full existing-verb collision corpus; `grant NEED-ffffffff` can never approve a proposal; grant-apply refusal paths (scope-mismatch, ceiling-without-ack, validator-fail restores) via non-root test mode.
**depends_on:** [SOV-1, SOV-5]

### SOV-7 · FIDELITY — outcome judge + AGB report + personal-agent identity + verdict_gate
**Files (edit):** `framework/fidelity/scorer.py` (Ring-1), `framework/fidelity/measure_intent.py`, `framework/fidelity/officer_prompt.py` (Ring-1), `framework/fidelity/officer_runner.py`, `framework/fidelity/consequence.py` (germline Ring-0). **Files (NEW):** `framework/fidelity/intent_report.py`.
**Detail:** INT-1 OUTCOME_RUBRIC pass 3 (anonymized A/B, grounding/topic guards verbatim, `retro.JUDGE_SYSTEM` pristine); CaseScore + measure_intent `outcome_verdict`; intent_report AGB headline / decision-match diagnostic. INT-3 `build_agent_eval_system` (clone kept verbatim as diagnostic arm; **default `identity_mode='clone'`** until first AGB baseline; stamp identity into recs). INT-4/D16 consequence `verdict_gate` (sovereign-gated, lazy resolve_posture ⇒ guardian bit-identical; wrong-from-any-source; not-within-cooldown condition; posture-flip-only-reduces test). `conflict_risk`: consequence.py (germline Ring-0 — hot; MEDIUM-HIGH; edit localized to `_REVIEW_SOURCES` + `compute_ratios`), scorer/officer_prompt/officer_runner/measure_intent (Ring-1). Rides the bootstrap merge.
**Tests:** A/B determinism+balance; forced-incomparable/forced-worse guards; no-intent path byte-identical (F1); verdict_gate ignored guardian / counted sovereign / wrong both; posture→guardian flip only reduces confirmed; clone-default identity; existing ratio + scorer tests green.
**depends_on:** [SOV-1]

### SOV-8 · SELF-IMPROVE (evidence live, code-apply DARK) — gate + apply-watch + standing pull + grant seeker
**Files (NEW):** `framework/learning/gate.py`, `framework/learning/apply_watch.py`, `cabinet/scripts/gate-apply.sh`, `cabinet/launchd/com.cabinet.gate-apply.plist` (DARK), `framework/missions/standing_pull.py`, `framework/learning/grant_seeker.py`, `docs/runbooks/gate-apply-runbook.md`. **Files (edit, Ring-1):** `framework/learning/self_improvement_loop.py`, `framework/learning/capability_gaps.py`, `framework/learning/skill_induction.py`, `framework/missions/supervisor.py`.
**Detail:** gate.ratify S0-S5 (scope-refuse-Ring-0 via immutable-core.yml, full pytest+golden-evals, falsifier corpus, ceiling probes swept both postures, variant archive, verdict) + `run_gate_review` (D16 fuel). apply_watch 72h auto-rollback (root-daemon-evaluated). gate-apply.sh sandboxed-unprivileged-verify + hooks-disabled root apply, **DARK** (D15). standing_pull R1-R5 ranked sources → `shared/interfaces/standing-missions.yml` (never touches Captain `outcomes.yml`); supervisor second compile-source when sovereign; loop routes code-diffs through gate.ratify (never `_apply_proposal`); can_install posture-aware (ceiling-touch veto absolute); skill auto-promote on evals-green. grant_seeker rank/render/`--argue-lanes` (flavor-A flip case). `conflict_risk`: self_improvement_loop.py/capability_gaps.py/skill_induction.py/supervisor.py (Ring-1; MEDIUM). **action_exec.py mission-adopt branch is OWNED by SOV-4** (this lane provides standing_pull/supervisor logic only). **Prerequisite artifact:** `immutable-core.yml` (authored in SOV-9) must land first.
**Tests:** S0 refuses Ring-0 diff + files need; stage short-circuit; run_gate_review stamps only 5-condition rows; gate-apply refuses unlocked posture / Ring-0 diff / forged pack, runs verify unprivileged (grep asserts no root pytest, hooksPath=/dev/null), plist NOT loaded by any setup script (dark grep); standing_pull never writes outcomes.yml; guardian A/A on loop.
**depends_on:** [SOV-1, SOV-7]

### SOV-9 · GOVERNANCE + AMENDMENT — immutable-core, lockstep meta-test, golden evals, docs, the ONE package
**Files (NEW):** `framework/policies/immutable-core.yml`, `memory/golden-evals/eval-016-posture-guardian-parity.md`, `eval-017-sovereign-ceiling-grant-or-need.md`, `eval-018-posture-env-cannot-widen.md`, `eval-019-immutable-core-gate-refusal.md`, `docs/proposals/germline-amendment-sovereign-posture-2026-07-05.md`, `framework/authority/tests/test_guardian_parity.py`, `framework/tests/test_germline_lockstep_consistency.py`. **Files (edit, germline):** `cabinet/scripts/hooks/pre-tool-use.sh` (§5 case + §5b GERM_PATH_RE), `framework/policies/base-safety.yml` (+ enforcer-triad lag closure), `cabinet/scripts/germline-lock.sh` (FILES += new germline files; SKIP += needs-ledger.jsonl), `.claude/rules/courses-of-action.md` (§2 posture-conditional reword, staged), `memory/golden-evals/eval-011..015` (amend never-UNCONDITIONAL-auto + eval-014 rot fix), `framework/authority/tests/test_golden_evals_a0.py`. **Files (edit, free):** `cabinet/loop-prompts/{<lane>-ceo,comms-officer}.txt`, `.claude/skills/cabinet-init/SKILL.md` §4, `cabinet/scripts/generate-instance.py`, `docs/mac-mini-deploy-runbook.md`, `docs/mac-mini-setup.md`, `cabinet/services.yml`, `cabinet/scripts/health-check.sh`.
**Detail:** immutable-core.yml Ring-0 enumeration drives the lockstep meta-test (FI-5). Golden evals per §6. Amendment package per §5. courses-of-action §2 posture-conditional (germline diff staged). comms-officer act-not-draft repair ships as its OWN commit citing the 2026-07-03 ruling (ALIGNMENT — not smuggled inside the posture package); lane-CEO posture wording lands with the flip commit + "no posture.yml = guardian, today's rules" fallback sentence. generate-instance renders posture.yml from a flavor answer (default guardian; flavor-B/mini ⇒ sovereign) under existing marker/idempotence guardrails. `conflict_risk`: pre-tool-use.sh, base-safety.yml, germline-lock.sh, courses-of-action.md, generate-instance.py, cabinet-init SKILL.md, runbooks, golden-evals/*, services.yml, health-check.sh (many germline — but mostly STAGED into the amendment, applied at unlock, so lower LIVE-merge race than SOV-3/4/5; HIGH by count).
**Tests:** lockstep meta-test (every FILES entry in §5+§5b+base-safety); guardian byte-identity suite (build_digest goldens, verb corpus, gate truth-table, caps, attention mapping all == recorded pre-change goldens); eval-016..019 enforcing pytests; amended evals' pytests updated same-commit; full suite green with `CABINET_POSTURE` unset AND `=sovereign`; doc-lint (apply token, all staged diffs referenced, decisions entries parse, rollback names every germline file).
**depends_on:** [SOV-1, SOV-2, SOV-3, SOV-4, SOV-5, SOV-6, SOV-7, SOV-8] (authors immutable-core.yml FIRST as an early sub-task, since SOV-8 reads it).

---

## §5 — THE ONE COMBINED GERMLINE AMENDMENT

`docs/proposals/germline-amendment-sovereign-posture-2026-07-05.md`, apply token **`apply sovereign posture`**, mirroring the trust-inversion precedent:
- **Status: AWAITING CAPTAIN** + apply-phrase; **SUPERSEDES:** cabinet-init §4 "posture NOT negotiable at init" (→ guardian at init; sovereign is a post-init Captain ratification), evals 011-015 wording (never-UNCONDITIONAL-auto; guardian unchanged), eval-014 unmeasured-cannot-auto letter (explicitly ratified: root/guardian + ceiling invariant forever; sovereign non-ceiling supersession), courses-of-action §2 "ONLY relaxation"; **Precondition:** none (additive + dark; independent of the authority-enforcing flip and act-first state).
- **§0** one-paragraph summary. **Per-file exact diffs.** Germline edits: authority-matrix.yml, matrix.py, policy_engine.py, policy-shadow.py, run_action_lane.py, action_exec.py, actfirst_canary.py, action_undo.py, tell_surface.py, consequence.py, pre-tool-use.sh, base-safety.yml (incl. enforcer-triad lag closure), germline-lock.sh, courses-of-action.md §2, golden evals 011-019. NEW germline: posture.py, grants.py, needs.py, gate.py, apply_watch.py, immutable-core.yml, grant-apply.sh, posture.yml, standing-grants.yml. Non-germline companions: examples, tests, tell_digest/binder_wire/attention_drain, fidelity+learning+missions modules, generate-instance.py, cabinet-init SKILL, loop-prompts, runbooks, services.yml, health-check.sh.
- **What it does NOT do:** no ceiling becomes unconditional auto; no guardian byte changes; no graduation/bars change; no ACT-NOT-DRAFT change on flavor A (grants loader structurally refuses personal-surface external_comms); no live behavior until a posture.yml exists; no runtime-writable grants; no root pytest / no Telegram-sealed grant writer; germline CODE auto-apply stays DARK until sandbox+explicit daemon load.
- **§ CI proofs P1-P7 in the SAME commit.** **§6 APPLY-GATE evidence pack:** P1-P6 green; sovereign scratch-CABINET_ID dry-run transcript (probe ⇒ need ⇒ grant line in unlock window ⇒ attributed allow ⇒ tombstone ⇒ block); P7 manual attestation (`chflags noschg posture.yml` ⇒ resolve_posture ⇒ guardian, relock); `germline-lock.sh status` shows new files locked; lockstep meta-test green.
- **§7 paste-ready `captain-decisions.md` entries** (Style-B): "## SOVEREIGN POSTURE (2026-07-05, Captain-ruled)" (directive verbatim essence, Why, Supersedes, Mechanics) + "## R1 — no Telegram-auto-grant" + **Decision-B BACKFILL** (filesystem-lock ruling absent from the ledger; 2026-06-24 backfill precedent). **Appendix** file|change|germline table. **One-revert rollback** (revert the germline files + `rm instance/config/posture.yml`; absent ⇒ inert).
- **Apply ritual (one sitting):** `sudo bash cabinet/scripts/germline-lock.sh unlock` → rebase-before-merge vs `feat/fidelity-harness-design` (sequence germline overlaps by `conflict_risk`) → `git merge feat/sovereign-posture` → create instance posture/grants files → commit → `sudo bash cabinet/scripts/germline-lock.sh lock` → `status`/`verify`.

---

## §6 — NEW / AMENDED GOLDEN EVALS
- **Amend 011/012/013/015:** guardian text UNCHANGED; add "## Sovereign posture": ceiling resolves `standing_grant`; no matching signed+locked+unexpired+unrevoked grant with satisfied hard-scope ⇒ block + deduped NEED; matching grant ⇒ allow attributed to `grant_id` + rate-counted + hard-scope enforced; flavor=personal external_comms ⇒ refused. Failure += allow-without-grant_id, grant-from-unlocked-file, grant-past-hard-scope.
- **Fix eval-014** (same commit, own section): stub prose refresh + pm_write/calendar_write act_with_undo reality; ratify: unmeasured-cannot-auto is (a) root/guardian invariant forever, (b) ceiling invariant every posture; sovereign non-ceiling unmeasured→auto is a Captain-ratified supersession.
- **eval-016 posture-guardian-parity:** absent/corrupt/unlocked/mismatch ⇒ resolution + block strings byte-identical to pre-posture goldens.
- **eval-017 sovereign-ceiling-grant-or-need:** empty grants ⇒ six probes block + needs (dedup on re-probe); matching locked grant ⇒ attributed allow; tombstone/expiry/hard-scope-violation ⇒ block; behavioral assertion "ceilings never resolve unconditional auto in ANY posture" (replaces the weak literal-`auto`-string check).
- **eval-018 posture-env-cannot-widen:** `CABINET_POSTURE=sovereign` alone ⇒ guardian; unlocked standing-grants.yml ⇒ empty; officer Write/Edit/bash writes to posture/grants ⇒ hook-blocked.
- **eval-019 immutable-core-gate-refusal:** gate.ratify refuses a Ring-0-touching diff; root daemon refuses a forged pack / unlocked posture; verify runs unprivileged-sandboxed (no root pytest, hooksPath=/dev/null).

---

## §7 — BACKWARD-COMPAT PROOF OBLIGATIONS (all land in the amendment commit)
P1 resolve_verdict guardian truth-table (3 variants equal). P2 gate byte-parity fixture (first commit vs unmodified code, kept green). P3 lane legacy path (posture absent ⇒ new modules raise-if-imported untouched; summary bytes unchanged). P4 guardian+file-present lane parity (5×5 == legacy). P5 load_policies floor-only + fail-closed validate. P6 full suite green + `test_undo_capability_parity` extended per-posture. P7 lock/attestation manual step. **Plus:** guardian byte-identity suite (SOV-9) run with `CABINET_POSTURE` unset AND `=sovereign`; the A/A test asserting zero behavioral diff with no posture config.

---

## §8 — CAPTAIN HANDOFF (ordered, Captain-only)
1. **Ratify §9 open questions** (eval wording never-UNCONDITIONAL-auto; ceiling expiry 90d vs per-class; hard_multiplier=10; officer_dispatch stays held; first flavor-A lanes to argue; v2 root grant-writer deferred; gate-apply daemon stays dark until sandbox).
2. Review the ONE amendment package + apply token `apply sovereign posture`.
3. `sudo bash cabinet/scripts/germline-lock.sh unlock`.
4. **Rebase-before-merge** vs the guardian agent's `feat/fidelity-harness-design` — sequence germline-file overlaps using each lane's `conflict_risk` (SOV-3/4/5/7/9 touch the hottest files); resolve, then `git merge feat/sovereign-posture`.
5. **Flavor B (Mini):** create `instance/config/posture.yml` (`posture: sovereign, deployment: <mini-id>, flavor: org`) + `standing-grants.yml` (`grants: []`) BEFORE lock. **Flavor A (MacBook):** optionally create `posture.yml` (`posture: guardian, flavor: personal`) to turn on the matrix-wire (proven identical, P4); flip specific `lanes:` to sovereign later in an unlock window.
6. Commit the instance files.
7. `sudo bash cabinet/scripts/germline-lock.sh lock` → `status`/`verify` (confirm posture.yml, standing-grants.yml, posture.py, grants.py, needs.py, gate.py, apply_watch.py, grant-apply.sh, immutable-core.yml all locked).
8. When ready, set `CABINET_NEEDS_WIRED=1` in the generated cos-inbound plist to arm the grant/deny/rearm binder verbs (dark → live).
9. **Do NOT** `sudo launchctl load com.cabinet.gate-apply` — germline CODE auto-apply stays dark until the unprivileged sandbox harness is built and you explicitly load it.
10. Killswitch drill; run `python -m framework.learning.grant_seeker --argue-lanes` to get the flavor-A sovereign-flip case in the first needs digest.

---

## §9 — OPEN QUESTIONS (Captain ratification)
1. **Eval-wording:** 011-015/014 "never auto" → "never UNCONDITIONAL auto" (guardian byte-identical; sovereign ceiling allow must cite a signed grant id). One letter-not-spirit change, covered by the apply token — confirm.
2. **Ceiling expiry:** `expires` REQUIRED ≤90d for all six classes (renewal auto-files a need) — confirm 90d flat or per-class (e.g. spend 30d).
3. **Runaway multiplier:** default `caps.hard_multiplier=10` (posture.yml-tunable) so the mechanical hard-stop never fires in honest operation — confirm or set 3.
4. **officer_dispatch/delegate_work stay HELD in v1** (cascade not cleanly reversible); investigation_run hold drops — confirm, or greenlight a cascade-aware-dispatch follow-up.
5. **First flavor-A sovereign lanes** the first needs-digest should argue for (guess: first-lane pm/calendar + internal_comms) — pure preference.
6. **v2 privileged writers** (root grant-writer AND germline code-apply daemon): both stay DARK/deferred, requiring a separate Captain amendment + a proven unprivileged-sandbox verify harness before either is armed — confirm the deferral.
