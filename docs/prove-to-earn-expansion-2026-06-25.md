# Prove-to-Earn Expansion — Self-Proposal, Account Flow, Trust Ladder (2026-06-25)

**Status:** designed + partially built (mechanisms that are SAFE to build now).
**Author:** Chair (cos).
**Scope:** Cabinet framework (`framework/` + `docs/`). Extends the existing
prove-to-earn / graduated-autonomy framework — does **not** duplicate it.

---

## 0. The hard lines (these do NOT change)

Encoded in `shared/interfaces/captain-patterns.md →
autonomy-boundary-accounts-and-self-guards`, and structurally enforced by the
germline guard in `cabinet/scripts/hooks/pre-tool-use.sh` (line ~936, exit 2):

1. The Chair **NEVER self-edits** `cabinet/mcp-scope.yml`, germline files
   (`framework/policies/`, `framework/authority/*.py`, `.claude/rules/`,
   `instance/config/autonomy.yml`, the golden-evals), or the pre-tool-use hook.
   That is self-privilege-escalation — a guard that self-removes is not a guard.
2. The Chair **NEVER enters credentials/OTPs or creates accounts itself.**

Everything in this expansion **PREPARES + SURFACES** for Nate's one-tap
approval. Nate applies the actual scope edit / supplies the credential. We build
mechanisms that **surface**, never mechanisms that **self-grant** or
**auto-enter credentials**. The germline guard means even a bug cannot cross
line 1: an attempt to `Edit`/`Write`/`sed -i` `mcp-scope.yml` is blocked by the
hook regardless of what any module computes.

---

## 1. What the existing prove-to-earn framework IS (study, don't duplicate)

The cabinet already has a **two-layer** graduated-autonomy framework. The
expansion layers on top of both; it re-implements neither.

### Layer A — the self-extension loop (capability gaps)
`framework/learning/capability_gaps.py` + the `capability-gap` skill.

- An officer hits a wall → `record_gap(need, kind, evidence, touches)` (or the
  loop infers a recurring workaround). Event-sourced: state is a replay of
  `capability_gap_*` events (`recorded → classified → proposed → approved /
  declined → resolved`). No new table.
- `classify()` buckets a gap into **procedure | tool | integration** (safe
  default: the *propose* kind, never *auto*).
- `route_open_gaps()` (called by `self_improvement_loop.py`) routes by kind:
  - **procedure** → `auto_skilling` (draft skill → eval gate → promote). Human
    never asked.
  - **tool / integration** → `propose_gap()` (status → `pending_captain`) +
    best-effort `notify_fn`. **Nothing installs.**
- `can_install(gap_id, touches)` is the **fail-closed install gate**: True only
  when a live `capability_gap_approved` event exists for that gap **and** it
  touches nothing on the hard ceiling. Any exception/missing data/ambiguity →
  False.
- `HARD_CEILING_TOUCHES = {secrets, spending, external_comms, production,
  network_write, credentials_grant}` — the code-level backstop, mirrored from
  `autonomy.yml.example → hard_ceiling`. A missing/broken `autonomy.yml` cannot
  weaken it (the file can only *widen* the ceiling).
- `AutonomyPolicy` (from `instance/config/autonomy.yml`) carries a **coarse,
  count-based graduation knob**: `graduation.enabled` +
  `auto_after_clean_approvals` (e.g. after 10 clean `tool` approvals, `tool →
  auto`). **Currently disabled** by default and never wired to a real promotion
  decision — it's a stub the expansion replaces with an explicit ladder.

### Layer B — the per-cell trust gate (fidelity → authority)
`framework/fidelity/graduation.py` + `framework/authority/matrix.py` +
`framework/policies/authority-matrix.yml`.

- The unit of trust is a **cell** = `(officer_actor_id, lane, action_type)`,
  e.g. `("officer:cos", "polads", "internal_message")`.
- `graduation.evaluate(cell) -> {state, evidence}` is the **single confidence
  source**. States, in order:
  - `unmeasured` — no data / denominator 0. **Fail-safe** (never silently auto).
  - `propose_only` — measured but below the bar.
  - `eligible` — meets sample floor + match bar, but the recency-clean streak
    has not matured. **Proven-but-not-yet-auto.**
  - `graduated` — clears the FULL bar (samples, match_rate, last-10 divergent,
    recency-clean). The only state that lets the gate auto.
  - `demote` — a fresh wrong-verdict cluster (≥2 divergent in last 10) drops the
    cell. Ramp-down designed as carefully as ramp-up.
- The **bar** is read from `authority-matrix.yml → bars` (per `risk_class`),
  never hardcoded. Fitness = `outcome_held_rate × review_confirmed_rate` (a
  positive signal, not a gameable correction-count).
- `matrix.py` maps `risk_class × confidence_state → verdict` (`auto`,
  `auto_with_veto_window`, `notify_after`, `propose_only`, `always_gated`,
  `classifier`). The **hard ceiling** rows (`external_comms`, `deploy_prod`,
  `spend`, `secrets`, `network_write`, `credentials_grant`) are
  `always_gated` for **every** confidence state — F can never lift them. This is
  validated fail-closed in CI (no prod/ceiling cell may resolve to `auto`).

### The surfacing path (already built)
`framework/frontdoor/intake.py` → `surface.py` → `channel.py`.
- `intake.enqueue({source, kind, ts, payload:{summary}, urgency_tier})` — a
  durable Redis-Streams card (`cabinet:frontdoor:intake`).
- `surface.drain_and_surface()` (every ~5 min): `ping-now` → DM Nate now;
  `batch`/`fyi` → stay pending for the next briefing (one-voice).
- This is the **one-tap intake card** every proposal in this expansion rides.

**Conclusion:** the existing framework already has (1) a gap → propose →
fail-closed-install loop, (2) a per-cell ramp-up/ramp-down trust gate, (3) a
durable Captain-surfacing channel. What it is **missing** — and what this
expansion adds — is:
- a **first-class MCP/plugin self-proposal** that bundles the *exact scope diff
  line* + *test evidence* into a one-tap card (today's `route_open_gaps` emits a
  prose proposal with no concrete diff and no wired surfacing);
- an **account-creation flow** that drives a signup to the credential field and
  surfaces "credential needed" (no such flow exists);
- an **explicit, Captain-authored trust ladder** with named rungs that replaces
  the coarse `auto_after_clean_approvals` stub, layered over the per-cell
  `graduation.evaluate()`.

---

## 2. Component 1 — MCP/plugin self-proposal flow

**Goal:** the Chair, having evaluated + tested a new MCP/plugin, surfaces a
ONE-TAP approval to Nate carrying the exact `mcp-scope.yml` diff (the line to
add) + any account step + the test evidence — as a front-door intake card.
**Nate applies the scope line.** We build the proposal-preparation + surfacing;
Nate applies the edit.

### Module: `framework/learning/self_proposal.py`

`prepare_mcp_proposal(...)` does four things, all read-only over privileged
state:

1. **Computes the exact scope diff** — `compute_scope_diff(server, officers,
   mcp_scope_path)` reads `cabinet/mcp-scope.yml` and returns the precise YAML
   line(s) Nate would add (e.g. add `make` to `cos.mcps:`), as a **string for
   review**. It NEVER writes the file. (If `mcp__make` is the call surface, the
   server token is `make`.) If the server is already in scope for all requested
   officers, it returns "already in scope — no edit needed."
2. **Bundles the test evidence** — the proof the Chair gathered that the MCP/
   plugin works (what was tested, the observed result). This is the "prove" in
   prove-to-earn for a *capability*, distinct from the per-cell behavioral
   proof.
3. **Flags ceiling touches** — reuses `capability_gaps.infer_touches()`. If the
   MCP touches a hard-ceiling category (e.g. a write-capable Make scenario =
   `network_write`), the card is tagged **Captain-required, never auto** and the
   approach text says so. This mirrors the `can_install` defense-in-depth.
4. **Surfaces** — builds a canonical intake item and `intake.enqueue()`s it,
   then `emit("self_proposal_prepared", ...)` for audit. Default
   `urgency_tier = batch` (rides the next briefing's decision queue) unless the
   caller marks it `ping-now`.

The card body (one-tap shape) contains, in order:
- **What** — the MCP/plugin + one-line why it's wanted.
- **Scope line** — the exact line(s) to add to `cabinet/mcp-scope.yml`, fenced.
- **Account step** — if the MCP needs an account/API key, the credential step
  (handed to Nate; see Component 2). Else "no account step."
- **Test evidence** — what the Chair verified.
- **Ceiling** — `none` or the touched categories + "Captain-required, never
  auto."
- **Apply** — literal instruction: *"To grant: add the scope line above to
  `cabinet/mcp-scope.yml` and reload. The Chair does not self-edit this file."*

**What Nate does:** taps approve → applies the one scope line himself (the only
privileged step), supplies any credential, reloads. The Chair never touches
`mcp-scope.yml`.

### Relationship to the existing gap loop
`prepare_mcp_proposal` is the **concrete surfacing** the gap loop lacked. A
`tool`/`integration` gap that the Chair has now *tested* graduates from the
prose `propose_gap()` proposal into a self-proposal card with a real diff. The
two compose: `prepare_mcp_proposal(gap_id=...)` stamps the `gap_id` so the
`capability_gap_approved` event still gates `can_install` for the CTO build step
(if code must be built). For a pure scope-grant of an *already-installed* MCP
(the common case — the MCP exists, only the scope line is missing), no
`can_install` build is needed; the scope line IS the grant.

---

## 3. Component 2 — Account-creation flow

**Goal:** document/script the flow where the Chair drives a signup up to the
credential/OTP field, surfaces "credential needed" to Nate, then continues. The
credential step stays Nate's.

### Dependency (genuine residual)
This flow drives a browser. It depends on the Chair having **`claude-in-chrome`
scope** — **currently NOT granted** in `cabinet/mcp-scope.yml`. Granting it is
itself a Component-1 self-proposal (the Chair surfaces the `claude-in-chrome`
scope line; Nate applies it). Until then, the account flow is **documented +
skeletoned**, not live.

### The flow (driver = `cabinet/scripts/prepare-account-flow.sh` + doc)
A signup is a sequence of steps; exactly one class of step is Nate's. The Chair:
1. **Reads the flow recipe** from `instance/config/account-flows.yml` (Captain-
   authored: the service, the signup URL, which fields the Chair fills, and the
   **credential boundary** — the field(s) that are Nate's: password choice,
   email OTP, 2FA code, payment).
2. **Drives the browser** (via `claude-in-chrome`, once scoped) filling only the
   non-credential fields (name, org, non-secret config) up to the credential
   boundary.
3. **STOPS at the boundary** and surfaces a **"credential needed"** intake card
   (`ping-now`, because a half-finished signup is time-sensitive): what service,
   which field, and "enter it in the open browser tab; reply `done` to
   continue."
4. **Resumes** after Nate signals done (or after Nate enters the value directly
   in the browser), completing the non-credential remainder.
5. **Never** reads, stores, types, or logs the credential. The value lives only
   in the browser tab Nate controls. The Chair's `record_run` / `log_reasoning`
   note the step occurred, never the secret.

### Why the credential stays Nate's
Account creation + credential entry is one of the two un-toggleable hard lines.
The Chair handles everything *around* the credential (the tedious form-filling,
the resume), which is the actual time-sink; Nate supplies only the secret. This
maximizes autonomy while holding the line.

### Config: `instance/config/account-flows.yml.example`
A recipe per service: `signup_url`, `chair_fills` (safe fields), `captain_supplies`
(credential boundary fields), `resume_after`, optional `touches` (e.g. a paid
signup → `spending`, which makes the whole flow Captain-gated end-to-end).

---

## 4. Component 3 — Trust ladder (explicit rungs)

**Goal:** extend the existing graduated-autonomy with explicit rungs
(capabilities graduate as they prove out; **Nate sets the rungs**). Build/
document the ladder + the prove→graduate mechanism.

### Why a new layer (not a rewrite)
- `graduation.evaluate(cell)` already answers *"has this exact cell proven out?"*
  (the `unmeasured → … → graduated` machine).
- `authority-matrix.yml` already answers *"given a confidence state, what
  verdict?"* per `risk_class`.
- What is **missing** is a **Captain-readable map of named rungs** — "what does
  the Chair earn, and in what order, as cells prove out?" — that Nate authors
  and tunes, sitting *above* the per-cell machine. The coarse
  `auto_after_clean_approvals` stub in `autonomy.yml` is the placeholder this
  replaces.

### Module: `framework/learning/trust_ladder.py` + `instance/config/trust-ladder.yml`

`trust-ladder.yml` (Captain-authored; `.example` shipped) defines an **ordered
list of rungs**. The rung *vocabulary* is the one the grand plan already named
(`docs/grand-plan-captain-agent-2026-06-21.md` §autonomy-ladder) — this layer
does not invent a competing set, it makes that ladder *configurable + earnable*:

| Grand-plan rung | Meaning | Matrix verdict it corresponds to |
|---|---|---|
| `would-like-to` | propose-first (waits for approval) | `propose_only` |
| `intend-to` | veto-window (announces, acts unless vetoed) | `auto_with_veto_window` |
| `ive-done` | auto-when-proven, reversible (acts, reports after) | `auto` / `notify_after` |
| `ive-been-doing` | fully graduated (acts, reports periodically) | `auto` |

Each rung in the config:
- `name` — one of the grand-plan rung ids above (climb is **per lane**).
- `grants` — the `(lane, action_type)` cells (or `risk_class`) the rung unlocks.
- `requires` — the proof bar to *earn* this rung, expressed as **already-
  graduated cells**: every cell in `grants` must be `graduated` per
  `graduation.evaluate()` (optionally with a min count / min recency-clean —
  read from the same `authority-matrix.yml` bars, never a second bar).
- `ceiling` (computed, not authored) — if any granted cell's `action_type` maps
  to a hard-ceiling `risk_class`, the rung is **un-earnable by auto-grant**:
  it can be *proposed* but the grant stays Nate's forever (matches the matrix
  `always_gated` rows). This is enforced in code, not just config.

`trust_ladder.py`:
- `load_ladder()` — `yaml.safe_load`, fail-closed to a single `R0-propose-
  everything` rung (the safe default) if the file is missing/broken. Mirrors
  `load_autonomy()`.
- `current_rung()` — replays `trust_rung_granted` events to find the highest
  rung Nate has actually granted. Default = `R0`.
- `evaluate_ladder()` — for each rung above the current one, asks
  `graduation.evaluate()` for every cell in `grants`. A rung is **earned** when
  all its cells are `graduated`. Returns `{earned: [...], pending: [...],
  blocked_by_ceiling: [...]}`.
- `propose_next_rung()` — for the lowest earned-but-not-granted rung, surfaces a
  **one-tap rung-graduation card** via `intake.enqueue` (the proof per cell +
  "approve to grant rung Rx"). For a ceiling rung, the card says "Captain-only
  grant — the ladder will never auto-advance past this." Emits
  `trust_rung_proposed`.
- **There is NO auto-grant path in code.** Even a non-ceiling rung is *proposed*,
  not self-applied, in the conservative default — because granting a rung edits
  effective authority, and the Chair does not widen its own authority silently.
  (A future `auto_grant_nonceiling: true` knob in `trust-ladder.yml` could let
  Nate opt specific non-ceiling rungs into auto-advance; **off by default**, and
  ceiling rungs ignore it.)

### The prove → graduate mechanism, end to end
1. The Chair acts; the consequence ledger records outcomes + review verdicts per
   cell (existing F machinery).
2. `graduation.evaluate(cell)` ramps the cell `propose_only → eligible →
   graduated` as the bar is met (existing).
3. `trust_ladder.evaluate_ladder()` notices a rung's cells are all `graduated`.
4. `propose_next_rung()` surfaces a one-tap card: *"Rung R1 (reversible-auto)
   earned — cells X, Y, Z all graduated with N clean samples. Approve to grant."*
5. Nate taps approve → records a `trust_rung_granted` event (a Captain action,
   via a small `org-runtime.py trust grant <rung>` verb / the dashboard).
   `current_rung()` advances.
6. The granted rung's cells now resolve to their matrix `auto` verdict (the
   matrix already does this once the cell is `graduated` AND the rung is live).
7. A `demote` on any granted cell (≥2 divergent) **both** drops the cell (matrix
   falls back to `propose_only`) **and** flags the rung for review — ramp-down.

### Where Nate sets the rungs
`instance/config/trust-ladder.yml` is Captain-authored (germline? **no** — it's
instance config, editable, like `autonomy.yml`'s *instance* copy). Nate writes
the rungs, the cells each grants, and (optionally) per-rung min-sample
overrides. He never has to touch the per-cell machine or the matrix.

---

## 5. What is SAFE to build now vs. residual

### Built now (this change)
- `docs/prove-to-earn-expansion-2026-06-25.md` (this doc).
- `framework/learning/self_proposal.py` — proposal preparation + surfacing
  (computes the scope diff string, bundles evidence, enqueues the intake card,
  emits the audit event). **No germline writes.**
- `framework/learning/trust_ladder.py` — the ladder config loader + `evaluate_
  ladder()` + `propose_next_rung()` surfacing. **No auto-grant in code.**
- `instance/config/trust-ladder.yml.example`, `instance/config/
  account-flows.yml.example` — example configs (not the live files; Nate copies
  + tunes).
- `cabinet/scripts/prepare-account-flow.sh` — the account-flow driver skeleton
  (drives to the credential boundary, surfaces "credential needed"). Browser
  steps are gated on `claude-in-chrome` scope and degrade to a clear "scope not
  granted — surfacing the manual step" message until then.
- Tests under `framework/learning/tests/`.

### NOT built (would cross a hard line) — deliberately omitted
- Any code path that writes `cabinet/mcp-scope.yml`, `framework/policies/`,
  `framework/authority/*.py`, `.claude/rules/`, `autonomy.yml`, or the hook.
  (The germline guard would block it anyway; we don't even attempt it.)
- Any auto-grant of a trust rung (even non-ceiling, in the default).
- Any credential read/store/type/log. The account flow stops at the boundary.

### Genuine residuals (need Nate / a future grant)
1. **`claude-in-chrome` scope** — Component 2's browser driving is inert until
   Nate grants the Chair `claude-in-chrome` in `mcp-scope.yml` (itself a
   Component-1 self-proposal). **Residual: Nate's one-line scope grant.**
2. **Nate authors the rungs** — `trust-ladder.yml` ships only as `.example`.
   The live ladder is empty (defaults to `R0-propose-everything`) until Nate
   writes his rungs. **Residual: Nate's rung-setting.**
3. **The `trust grant <rung>` Captain verb** — recording a `trust_rung_granted`
   event is a Captain action surface (dashboard button / `org-runtime.py` verb).
   This change adds the projection (`current_rung()`) and the event name; wiring
   the Captain-facing grant button/verb is a small follow-up. **Residual: the
   one-tap grant control.** (Until it exists, Nate grants by editing the YAML +
   emitting the event manually, which the doc shows.)
4. **`mcp-scope.yml` self-edit stays Nate's by design** — not a gap to close; a
   hard line. Documented so no future officer "fixes" it.

---

## 6. Safety invariants (carried from the existing framework)

- **Fail-closed config loads** — every new YAML loader (`load_ladder`,
  account-flow recipes) uses `yaml.safe_load` and degrades to the *conservative*
  default on any error (missing file, parse error, bad shape), never an
  autonomy-widening one. Mirrors `load_autonomy()`.
- **Hard ceiling is code-level** — `trust_ladder` and `self_proposal` both reuse
  `capability_gaps.HARD_CEILING_TOUCHES` / `infer_touches()`; a ceiling touch
  forces Captain-required regardless of any config.
- **Surface, never self-grant** — every output is an `intake.enqueue` card +ан
  audit event. No module in this expansion has a write path to a privileged
  file or an auto-grant of authority.
- **Audit everything** — `self_proposal_prepared`, `trust_rung_proposed`,
  `trust_rung_granted` events feed the existing reasoning-review / org-event
  audit, so the prove-to-earn expansion is as replayable as the rest of the
  cabinet.
