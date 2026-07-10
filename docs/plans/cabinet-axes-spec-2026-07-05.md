# Cabinet Axes — 3 Autonomy Levels × 2 Flavors × 3 Deployment Targets (spec of record, 2026-07-05)

**Status:** Captain-directed (captain-decisions.md 2026-07-05 "THREE AUTONOMY LEVELS × FLAVORS × DEPLOYMENTS" + "EXTERNAL-COMMS GRANTABILITY IS INSTANCE-SCOPED"). Builds directly on the merged sovereign build (`94bb353f`) and the foundation-first ruling. Germline edits ride ONE amendment (apply token `apply cabinet axes`); nothing here hot-patches the live runtime.

---

## §0 · Doctrine

The cabinet is configured along **three orthogonal axes**, all DATA consumed through resolvers and tables — never code branches:

| Axis | Values | What it decides | Config carrier |
|---|---|---|---|
| `autonomy_level` | `earn_up` \| `guardian` \| `sovereign` | which verdict a (risk_class × confidence) cell resolves to | `instance/config/posture.yml` (Captain-locked) |
| `flavor` | `personal` \| `org` | identity: what it senses, what it optimizes, which grant classes the CAPTAIN chooses to expose | `posture.yml` `flavor:` |
| `deployment_target` | `macbook` \| `mac_mini` \| `docker` | topology: attestation backend, service manager, source/actuator bindings, credential isolation | `posture.yml` `deployment_target:` |

**Presets are the UX; axes are the architecture.** Three shipped presets give the pick-one-of-three experience: `personal-macbook`, `org-macmini`, `org-docker`. Any axis combination is valid; presets are just pre-filled points.

One sentence per axis-doctrine:
- *Level* is a **selection over the ONE authority matrix** (the sovereign build's mechanism, extended from 2 postures to 3).
- *Flavor* selects **evidence supply and optimization target** (personal: captain-verdict-weighted, outcome-first per AGB; org: machine-probe-weighted), never authority semantics.
- *Target* selects **backends** (attestation, scheduler, adapters), never authority semantics.

## §1 · The three autonomy levels (postures)

All three share the verdict vocabulary, `graduation.evaluate()`, the undo plane, the killswitch, the needs ledger, and the six-ceiling structure. Only the tables differ.

### L1 · `earn_up` (leader-leader; the cautious captain's start)
- **Semantics:** everything below the ceilings starts `propose_only`; cells climb on PROVEN outcomes through the rung ladder `would-like-to → intend-to → ive-done → ive-been-doing` (mapping `propose_only → auto_with_veto_window → notify_after → auto`). Climb is per-lane, one rung at a time, **surfaced as a one-tap card** — the Captain grants the rung (`trust_rung_granted`), the system never self-promotes. Ceilings `always_gated`.
- **Implementation:** `postures.earn_up.verdicts` table + resurrect `framework/learning/trust_ladder.py` (recoverable at `d0548359`; deleted-as-default by `0a9dda6e`, which stays correct) as the rung map + climb-card surface. Re-add `trust_rung_proposed/granted` to `VALID_EVENT_TYPES`.
- **Validator rule (new):** the `earn_up` table may only **narrow** vs the root table (guardian) — machine-checked cell-by-cell. This makes earn_up selectable WITHOUT attestation (narrowing is always safe).

### L2 · `guardian` (earn-demotion; the DEFAULT — today's root table, byte-identical)
- Trust granted day-one for reversible classes (act-with-undo, journaled, told after); trust LOST on evidence (undo-rate, veto) — never pre-earned. Ceilings `always_gated`. Absent/corrupt/unlocked posture config ⇒ guardian. Unchanged.

### L3 · `sovereign` (boundless; shipped 2026-07-05)
- As merged: reversible→`auto`, pm/calendar→`act_with_undo`, internal/deploy_nonprod→`notify_after`, ceilings→`standing_grant` (act only under a Captain-signed locked grant, else file `NEED-<hex>` and proceed). Evidence Gate + Ring-0 for self-improvement. Unchanged.

### Level switching (init + any time later)
- **cabinet-init** asks the level (default guardian) and writes `posture.yml`.
- **Downgrade (narrowing) — instant, from anywhere:** `CABINET_POSTURE=earn_up|guardian` env, a binder verb (`posture guardian`), or the dashboard may narrow at ANY time without unlock — narrowing is fail-safe by construction (env-narrow-only already shipped; extend the same rule to earn_up).
- **Upgrade (widening) — attested ritual ONLY:** `sovereign` (and `guardian` from `earn_up`… no — guardian is the unattested default; only `sovereign` widens beyond it) requires the locked-file ritual: unlock → edit `posture.yml` → lock. A dashboard/chat "go sovereign" button is a **forge vector** and is structurally refused: the resolver honors sovereign only from an ATTESTED (locked, deployment-matched) file. The dashboard may *render* posture and *offer the downgrade*; for upgrade it prints the ritual.

## §2 · Flavors (identity axis) — with the external-comms correction

- `personal`: senses the captain's world (their sources), optimizes outcomes on the captain's behalf (AGB judging), label supply = captain verdicts + TTL/undo evidence.
- `org`: senses product telemetry, optimizes product outcomes, label supply = machine probes first.
- **CORRECTION (Captain, 2026-07-05):** external_comms grantability is **NOT flavor-structural**. Remove grants.py's `flavor=personal ⇒ external_comms refused` gate (AX-3). Replacement: **`never_grant:`** — an instance-level, Captain-locked list in `posture.yml`:
  ```yaml
  never_grant: [external_comms]   # the first captain's personal instance; ANY class list, any captain, any flavor
  ```
  Loader semantics: a grant row whose class ∈ never_grant is dropped (fail-closed) + files a `kind=decision` need ONCE (not a grant-request need — asking for a never-grant is noise). Empty/absent list = all six classes grantable in sovereign. The first-instance deployment keeps today's exact behavior via config; the framework stops encoding one captain's policy.

## §3 · Deployment targets (topology axis)

The load-bearing discovery: **the schg attestation is macOS-only** — `chflags schg` / `SF_IMMUTABLE` does not exist on Linux/docker. Since posture/grants attestation is the trust anchor (Decision B), each target declares an **attestation backend**:

| Target | Attestation backend | Boundary mechanism | Scheduler | Notes |
|---|---|---|---|---|
| `macbook` | `schg` | `chflags schg` (root-only clear) | launchd | shared with the captain's daily machine; personal sources available |
| `mac_mini` | `schg` | same | launchd | dedicated host, clean-room credentials |
| `docker` | `ro_mount` | germline + posture/grants mounted **read-only from the host** (`-v …:ro`); the container cannot remount at any privilege | container init + cron | arguably the STRONGEST boundary; unlock ritual happens host-side |

- `framework/authority/posture.py` gains a pluggable `is_locked()` backend keyed on `deployment_target` (`schg` = today's st_flags check; `ro_mount` = write-probe + `/proc/mounts` ro flag; both fail-closed to guardian). `germline-lock.sh` grows a `--backend ro-mount` no-op mode with host-side instructions.
- Docker preset ships: Dockerfile + compose with the ro-mounts, a container `services` manifest rendered from the same `cabinet/services.yml` (one manifest, two renderers: plists / cron+supervisor), and the clean-room test (§6.2) as its CI gate.
- The extinct `/opt/founders-cabinet` docker deployment is the ancestor here; this revives it as a first-class target on the modern kernel.

## §4 · Channel adapters (optional plugins; Captain-ruled 2026-07-05)

`framework/channels/` — uniform contract per adapter:
```
send(recipient, body, thread_id) -> artifact_id     # journaled
classify(recipient) -> internal|external            # per instance org-domain config, feeds the classifier's internal/external action_types
undo_contract: none | delete_window(seconds)        # Slack/Discord/Teams/Google Chat messages are deletable → pseudo-undo; email = none
capabilities: [send, receive, edit, delete, react]
```
- Shipped adapters (roadmap order): Teams + Outlook (exist today behind first-instance-specific paths — refactor onto the contract), Slack, Gmail, Google Chat, Discord.
- Instances bind adapters in `extensions.yml`; an adapter with `undo_contract: none` can never make its action_type act-first-eligible regardless of posture (inverse-required rule already enforces this).
- Every adapter ships with a mock for the arena/sim harness (no live sends in experiments — evolution-engine spec invariant).

## §5 · The first captain's two live deployments (concrete)

| | MacBook (this machine) | Mac Mini |
|---|---|---|
| preset | `personal-macbook` | `org-macmini` |
| flavor / target | personal / macbook | org / mac_mini |
| level | **guardian** now; lanes argued → flip via ritual | **sovereign** at deploy |
| never_grant | `[external_comms]` (ACT-AND-DRAFT, the captain's policy) | `[]` (grants decide) |
| attestation | schg (ARMED, verified 2026-07-05) | schg at deploy |

The third preset (`org-docker`) ships for future captains/servers; no live deployment yet.

## §6 · THE AXES CONTRACT — enforcement for ALL future work (foundation + captain extensions)

The question this answers: *how do we make "axes are data, never branches" physically hold for foundation developers AND for captains extending their own instance?* Six layers, each mechanical:

1. **The axis linter (CI, the workhorse): `framework/tests/test_axes_contract.py`.** AST-walks `framework/` and rejects any comparison/branch on `posture`/`autonomy_level`/`flavor`/`deployment_target` values **outside a germline-pinned allowlist** (the sanctioned resolver/table/backend modules: posture.py, matrix.py, grants.py, the attestation backends, arena config). `if posture == "sovereign"` anywhere else in framework/ = CI red. Allowlist additions ride germline amendments — widening the branching surface is a Captain act.
2. **Clean-room job (foundation-first ratchet, already E4):** full framework suite on a bare instance — no personal sources, no screenpipe, no vault — parametrized per deployment_target stub. A feature that only works on one target or one captain's machine fails CI.
3. **Axis-matrix invariant suite:** the membrane invariants (ceilings never unconditional-auto; demote always narrows; guardian byte-parity; never_grant refused; earn_up-only-narrows; upgrade-requires-attestation) run **parametrized across all 3×2×3 = 18 combos**. They're table lookups — the full sweep costs seconds and makes cross-axis coupling impossible to land silently.
4. **Extension manifest validation (the captain-instance half):** every extension — channel adapter, source adapter, skill, MCP — ships a small manifest: `action_types` + risk classes it emits, `undo_contract`, axis-compat (default: all). Extensions **receive resolved axis values; they never read axis config themselves** (the linter also walks `instance/` extensions when `validate-extension` runs). `cabinet/scripts/validate-extension.sh` = manifest schema + axis linter over the extension's files; the extend-cabinet skill routes every captain through it; loaders skip manifest-invalid extensions fail-closed + file a need. A captain literally cannot wire in an axis-branching extension without seeing it refused.
5. **Doctrine layer (for LLM authors):** new germline rule `.claude/rules/axes-contract.md` — the contract in prose, loaded by every officer/agent session (foundation devs and captain instances alike), mirrored in CLAUDE.md. New golden eval **eval-020-axes-contract**: asserts the linter exists, is green, and the allowlist matches immutable-core.
6. **Filesystem (the backstop):** the axis kernel — posture.py, the matrix tables, the linter + its allowlist, `axes-contract.md` — joins the germline lock set (immutable-core-driven, lockstep meta-test extended). The contract can't be quietly edited out by the very agents it governs.

Layers 1–3 bind the foundation; 4 binds captains; 5 binds LLM workers; 6 binds everyone. Same numbers the Captain should expect in review: **one** posture resolver, **one** matrix, **18** parametrized invariant combos, **zero** axis branches outside the allowlist.

## §7 · Maintenance & further development — costs, effects, pitfalls

**Marginal cost of a new level/flavor/target after this build:** one table (or backend) + one validator rule + one preset + the parametrized suites pick it up automatically. No code forks. That is the whole point of axes-as-data.

**Effects on development velocity:** slightly slower to *start* a feature (you must express behavior as tables/adapters, not an `if`), significantly faster to *keep* 18 configurations correct (the suites prove them all per commit). Foundation-first is enforced, not aspired to.

**Pitfalls (named, each with its counter already in this spec):**
- *Combinatorial explosion* → axes are inputs (linter, §6.1) + invariants parametrized once (§6.3), never 18 hand-written suites.
- *Live-switch privilege escalation* → upgrade requires attestation (§1); dashboards may only narrow.
- *schg portability on docker* → attestation backends (§3); never assume Darwin in framework code (clean-room job catches it).
- *never_grant vs needs noise* → never-grant classes file `kind=decision` once, not recurring grant-request needs (§2).
- *earn_up regression to default* → default-with-no-config is guardian, pinned by the existing byte-parity evals; earn_up is opt-in only.
- *Adapter sprawl* → one channel contract (§4); an adapter without a manifest doesn't load.
- *The three-stream reconciliation debt* (sovereign ∪ doctrine-wave ∪ evolution-addendum opinions on consequence.py/stamping/scheduling) → still owed BEFORE evolution-engine E0; this spec adds no fourth opinion (it touches none of those files).

**Is any of it a bad idea?** One honest caution: **don't ship earn_up as a heavily-marketed co-equal default.** It exists for captains who need it (your own first directive), but every rung-climb card is human-wait by design — the foundation's benchmark deployments (and its pitch) should live on guardian/sovereign. earn_up is the on-ramp, not the destination.

## §8 · Build lanes (next build wave, ONE amendment: `apply cabinet axes`)

| Lane | Scope | Size |
|---|---|---|
| AX-1 | posture.py 3-level enum + narrow-only selection rules + `postures.earn_up` table + validator (earn_up-narrows rule) | S |
| AX-2 | trust_ladder resurrection as earn_up surface (rung map, climb cards, events re-registered) | M |
| AX-3 | grants.py: remove flavor-structural external gate; `never_grant:` loader + decision-need; first-instance config line | S (germline) |
| AX-4 | deployment_target + attestation backends (schg / ro_mount) + docker preset (Dockerfile, compose ro-mounts, cron renderer from services.yml) | M |
| AX-5 | channel-adapter contract + Teams/Outlook refactor onto it + one greenfield adapter (Slack) + sim mocks | M-L |
| AX-6 | axes contract: linter + 18-combo invariant suite + validate-extension.sh + manifest schema + `.claude/rules/axes-contract.md` + eval-020 + lock-set additions | M |
| AX-7 | presets ×3 + cabinet-init level/flavor/target interview + dashboard posture tile (render + narrow-only) + docs | S-M |

Ordering: AX-1/AX-6 first (contract before content), AX-3 with AX-1 (same germline window), AX-2/AX-4/AX-5/AX-7 parallel behind them. Evolution-engine E0 (reward hygiene) remains sequenced AFTER the three-stream reconciliation; the axes build is independent of it and can go first.
