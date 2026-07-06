# SOURCE-ADAPTER BOUNDARY — the personal-sensing seam (E4 · D2 design) — 2026-07-05

**Status:** RATIFIABLE SPEC — design only, no code. This is the foundation
plan for the NEXT (bigger) build; nothing here is implemented in this lane.

**Ruling realized:** FOUNDATION-FIRST (captain-decisions.md, 2026-07-05) —
`framework/` is the universal base for **any** captain and **either** flavor;
this deployment (captain **Nate**, Flavor-A / screenpipe brain) is the first
instance and proving ground, not the product. The DE-NATE sweep
(`docs/plans/de-nate-foundation-2026-07-05.md`) parameterized the captain
*name*; it deliberately LEFT the screenpipe / vault / `BrainAdapter` *data
coupling* in place and **flagged it** (that doc §4, category-5 flags: vault
structure, board ids, product repos, `~/.screenpipe` state). This spec is the
plan that discharges those flags: a source-adapter seam so a clean-room /
Flavor-B deployment binds a different — or null — personal-sensing backend
without editing `framework/`.

**Anchoring in the axes contract (already ratified).** The seam is not a new
concept — `docs/plans/cabinet-axes-spec-2026-07-05.md` §6 already reserves the
slot: *"every extension — channel adapter, **source adapter**, skill, MCP —
ships a small manifest … Extensions receive resolved axis values; they never
read axis config"* (§6.4), and the axis table says **flavor selects "evidence
supply"** (§2, line 21) while **deployment_target selects "source/actuator
bindings"** (§2, line 15). `.claude/rules/axes-contract.md` §1 lists
"channel/source adapters" among the sanctioned pluggable BACKENDS. This spec
is the concrete realization of that reserved backend: the Flavor-A screenpipe
brain becomes an **instance-bound source adapter** selected by flavor/target,
and framework CORE depends on the interface, never on screenpipe.

**Branch / worktree:** `feat/instance-extract`
(`.claude/worktrees/instance-extract`, base `fa6c3032`). **Germline note:**
two of the coupled files are germline board-id carriers
(`framework/frontdoor/action_exec.py`, `framework/frontdoor/actfirst_canary.py`)
and `framework/authority/classifier.py` is germline; their migration lands via
the Captain amendment, surgically. This lane edits none of them.

---

## 1 · Scope & non-goals

**In scope — the personal-sensing seam.** The read-side surface framework CORE
uses to *observe* the captain's world: vault/brain search, person intel, open
commitments, drafting lessons, voice profile, and the captain-model priors
(the `nate_model`-equivalent). This is exactly the "gather-then-decide" input
side the brain-bridge rule governs (`.claude/rules/brain-bridge.md`: "the vault
is Nate-truth — read first").

**Adjacent, cross-referenced, NOT redefined here:**
- **The dispatch / actuator half** (`queue_draft`, `email_lib`,
  `teams_graph_lib`) — the OUTBOUND seam. It stays behind `env.allow_sends()`
  and the brain-bridge `queue_draft`-only gate. §4 defines a sibling
  `PersonalDispatch` Protocol so a null/org deployment can bind it too, but
  its authority semantics are untouched — external recipients stay per-item
  Captain-approved in every posture (ACT-AND-DRAFT).
- **The retrodiction SCORING engine** (`framework/fidelity/retro.py`) — an
  EVALUATION seam, not a SENSING seam. It already has its own shim +
  `retro_available()` predicate + a planned A2.1 vendoring. It is the *design
  precedent* for the null adapter (§4.3), and it shares the clean-room job, but
  its scoring functions (`score_case`, `judge_decision`, …) are out of the
  `PersonalSource` interface. §5 Phase 4 folds it into the same pattern.
- **Charset normalization** (`framework/acting/voice_charset.py`) — ALREADY
  decoupled (vendored 2026-07-02, zero screenpipe deps). It is proof the
  decoupling works and needs no adapter; it drops out of the census in §3.

**Non-goals.** No new authority. No change to the leak-guard fence
(`gather_cutoff_context` content-ts exclusion-by-default stays exactly where it
is, ABOVE the adapter — see §6 fidelity row). No rename of external
brain-artifact identifiers inside the adapter (`nate_model`, `me_signal`,
`voice.md` stay verbatim, per DE-NATE §3 — only the *interface method name* is
launcher-neutral).

---

## 2 · The problem, precisely

`grep -rln 'screenpipe|obsidian|OBSIDIAN_VAULT|BrainAdapter' framework/ --include=*.py`
(minus tests) = **28 files** across acting / frontdoor / fidelity / watchdog /
probes / triggers / learning / authority / autoreply. Framework CORE reaches
the captain's estate three ways, all of which a clean-room / Flavor-B box lacks:

1. **Hard imports of screenpipe `_shared/` libs** — `draft_lib`,
   `commitments_lib`, `context_lib`, `me_signal`, `sp_lib`, `product_ops_lib`,
   `email_lib`, `teams_graph_lib` — resolved by `sys.path.insert` of
   `~/.screenpipe/pipes` + `~/.screenpipe/pipes/_shared`.
2. **Runtime path literals** — `~/.screenpipe/state/*`, `~/.screenpipe/pipes/*`,
   `OBSIDIAN_VAULT_PATH` → `~/obsidian/screenpipe-brain`, `~/Obsidian/…`.
3. **A partial abstraction that already exists but lives in the wrong layer** —
   `framework/fidelity/officer_runner.py::BrainAdapter` (injectable, 7 methods)
   and `framework/acting/screenpipe_adapter.py` (the acting gather→draft
   front-end). These are the *right shape* but are (a) inside `framework/`, (b)
   named after Flavor-A (`screenpipe_adapter`), and (c) default to real
   screenpipe imports. They are the seed of the interface, not the interface.

The fix is a proper seam: **`framework/sources/`** owns a launcher-neutral
Protocol + a resolver + a null adapter; **`instance/flavor-a/sources/`** owns
the screenpipe implementation. Framework CORE imports `framework.sources`,
never screenpipe.

---

## 3 · The 28-file coupling census — direct vs transitive

Classified by evidence (`import` of a screenpipe lib / `BrainAdapter` = DIRECT;
a `~/.screenpipe`|vault runtime path but no brain-data consumption = PATH-ONLY;
the token only in a comment/docstring/brain-artifact-string = INERT).

### Tier 1 — DIRECT couplers (13): consume brain DATA via hard imports / `BrainAdapter`

These MUST route through `framework.sources.get_source()` after migration.

| File | Subsystem | How it couples | Migration |
|---|---|---|---|
| `fidelity/officer_runner.py` | fidelity | **Defines `BrainAdapter`** (7 methods); lazy-imports `context_lib`, `draft_lib`, `commitments_lib`, `me_signal`; `OBSIDIAN_VAULT_PATH` read | **becomes the Flavor-A adapter body**, re-homed to `instance/flavor-a/sources/` |
| `acting/screenpipe_adapter.py` | acting | **The acting adapter**: `draft_lib`, `commitments_lib`, `product_ops_lib`, `context_lib`, `sp_lib`; `~/.screenpipe` paths | **becomes the Flavor-A adapter's acting surface**, re-homed to `instance/flavor-a/` |
| `fidelity/decision_cell.py` | fidelity | `from …officer_runner import BrainAdapter`; `OBSIDIAN_VAULT_PATH`; `~/.screenpipe/state` case store | swap `BrainAdapter()` → `get_source()`; state path → resolver/config |
| `fidelity/_vault_gather_runner.py` | fidelity | subprocess sidecar; `import context_lib`; `~/.screenpipe/pipes/retrodiction` | re-home with the adapter (it IS the adapter's py3.12 search sidecar) |
| `fidelity/measure_intent.py` | fidelity | `from …officer_runner import gather_cutoff_context`; `sys.path` `_shared`+`pipes` | import from the seam; drop the `sys.path` bootstrap (adapter owns it) |
| `acting/run_action_lane.py` | acting | imports `screenpipe_adapter`; `VAULT = ~/Obsidian/screenpipe-brain`; `_shared/.env` | consume `get_source()`; VAULT + env → resolver/config |
| `acting/run_draft_lane.py` | acting | `sys.path` `_shared`; imports `screenpipe_adapter`; `queue_draft` | consume `get_source()` (read) + `PersonalDispatch` (send) |
| `frontdoor/morning_synthesis.py` | frontdoor | imports `screenpipe_adapter` (`gather`, should-reply gate) | consume `get_source()` |
| `frontdoor/binder_wire.py` | frontdoor | lazy `from …screenpipe_adapter import normalize_voice` | `normalize_voice` is charset-only → point at vendored `voice_charset` (no adapter needed) |
| `frontdoor/chair_drafts.py` | frontdoor | `draft_lib`; **`email_lib`/`teams_graph_lib` send libs**; `_shared` | read via `get_source()`; **send via `PersonalDispatch`** (stays gated) |
| `frontdoor/daily_recap.py` | frontdoor | `sp_lib` (Monday GraphQL), `commitments_lib`; `OBSIDIAN_VAULT_PATH` daily-note write | read via `get_source()`; **vault WRITE via `PersonalDispatch.append_note`** (obsidian-sync hash-match invariant — §6) |
| `autoreply/wiring.py` | autoreply | imports screenpipe `agent_reasoning` lib via `_shared` `sys.path` | reasoning-log write → `PersonalDispatch.log_reasoning` |
| `fidelity/retro.py` | fidelity | the retrodiction SCORING shim; `~/.screenpipe/pipes/retrodiction` | **parallel seam** (EvaluationEngine, §1) — already shimmed; Phase 4 |

### Tier 2 — PATH-ONLY couplers (5): a `~/.screenpipe` state/credential/watched path, no brain-data consumption

| File | Subsystem | Path | Migration |
|---|---|---|---|
| `frontdoor/action_exec.py` | frontdoor | `MONDAY_API_KEY` from `~/.screenpipe/pipes/_shared/.env` | env/credential resolver; **germline (board-id)** → amendment |
| `frontdoor/actfirst_canary.py` | frontdoor | `_SHARED_ENV = ~/.screenpipe/pipes/_shared/.env` | env/credential resolver; **germline (board-id)** → amendment |
| `fidelity/benchmark.py` | fidelity | `~/.screenpipe/state/autonomy_outcomes.jsonl` (env-overridable) | outcomes path → resolver/config |
| `fidelity/run_e2e_smoke.py` | fidelity | `~/.screenpipe/pipes/embeddings/lib.py` presence probe | probe via `get_source().available()` |
| `watchdog/registry.py` | watchdog | `SCREENPIPE_STATE_DIR = ~/.screenpipe/state` (watched dir) | watched-target config; degrades to "nothing to watch" on Flavor-B |

### Tier 3 — INERT (10): the token is comment/docstring/brain-artifact-string only — NO runtime coupling

No migration needed; several are already-correct de-couplings kept as
documentation. Listed so the census is exhaustive and the ratchet allowlist is
honest.

| File | Why it appears | Action |
|---|---|---|
| `acting/voice_charset.py` | docstring records the 2026-07-02 vendoring (ZERO deps) | none — already decoupled |
| `watchdog/check.py` | comment: "no screenpipe libs" (NEGATIVE coupling) | none |
| `authority/veto.py` | comment: delegates to injected `send_backend` (`queue_draft`) | none — already injected |
| `fidelity/consequence.py` | comment: external screenpipe emit path | none |
| `fidelity/oauth_llm.py` | comment: screenpipe-memories `CLAUDE.md` ref | none |
| `fidelity/officer_prompt.py` | `"nate_model patterns"` prompt LABEL (brain-artifact, kept) | none — DE-NATE §3 keep |
| `learning/experience.py` | comment: clean-room ratchet reference | none |
| `probes/runner.py` | comment: env from `_shared/.env` (loaded elsewhere) | none |
| `triggers/registry.py` | comment: the screenpipe `reminders` pipe it superseded | none |
| `frontdoor/run_briefing.py` | comment: replaced the screenpipe morning-brief DM | none |

**Totals:** 13 direct + 5 path-only + 10 inert = 28. The migration surface is
**13 files** (Tier 1); **5** are trivial config/env reparents (Tier 2, 2 of
them germline); **10** are no-ops. The end-state ratchet allowlist (§7) is
**empty** — no `framework/**` file names screenpipe.

---

## 4 · The interface — `framework/sources/`

### 4.1 `PersonalSource` — the read/sensing Protocol (methods from REAL usage)

Derived verbatim from `BrainAdapter`'s 7 methods (`officer_runner.py:319-452`)
plus the acting-lane verbs (`screenpipe_adapter.py`). Launcher-neutral names;
the Flavor-A adapter maps each to today's screenpipe call (shown in the
comment). A `Protocol` (structural) so the Flavor-A adapter, a null adapter,
and a future org adapter all satisfy it without inheritance.

```python
# framework/sources/base.py  — stdlib + typing only; NO screenpipe import
from typing import Optional, Protocol, runtime_checkable

@runtime_checkable
class PersonalSource(Protocol):
    """The captain's personal-sensing surface. Framework CORE depends on THIS,
    never on screenpipe. Flavor-A binds the screenpipe adapter; a clean-room /
    Flavor-B box binds NullPersonalSource or an org source."""

    def available(self) -> bool: ...
        # cheap liveness probe (mirror retro.retro_available()); False ⇒ degrade

    # --- OBSERVE / SEARCH (leak-scoped retrieval) --------------------------
    def search(self, handle: str, *, topic: Optional[str] = None) -> dict: ...
        # → {"hits": [{text, path|ref|heading, content_ts, ...}], "topic_terms": ...}
        # Flavor-A: context_lib.gather(handle, sources=["vault"], topic=topic)
        #           (today = BrainAdapter.gather_vault; Tier-1 vault ONLY)

    def find_reply_candidates(self, *, since: Optional[str] = None) -> list: ...
        # threads awaiting the captain's reply (acting-lane find_threads)

    # --- PERSON INTEL ------------------------------------------------------
    def person_intel(self, slug: str) -> str: ...
        # dossier markdown.  Flavor-A: draft_lib.person_intel(slug)

    # --- COMMITMENTS -------------------------------------------------------
    def open_commitments(self, direction: str) -> list: ...
        # owed_by / owed_to, open only.  Flavor-A: commitments_lib.load_all(...)

    # --- IDENTITY PRIORS (PRIVATE — inform HOW to draft, never emitted) -----
    def voice_profile(self) -> str: ...
        # Flavor-A: draft_lib.voice_profile()  (voice.md)
    def model_patterns(self) -> str: ...
        # launcher-neutral name; Flavor-A: me_signal.nate_model("patterns")
        # PATTERNS layer only (never core/memory — leak gotcha, officer_runner.py:405)
    def drafting_lessons(self, before_ts: str) -> str: ...
        # date-filtered STRICTLY before before_ts.  Flavor-A: retro.lessons_before(...)

    # --- RAW NOTE READ (vault-jailed) --------------------------------------
    def read_note(self, path: str) -> str: ...
        # path-validated, vault-jailed read.  Flavor-A: OBSIDIAN_VAULT_PATH read
```

**Method-origin table (the correctness ledger — every method traces to real code):**

| Interface method | Today's call site | Flavor-A backing |
|---|---|---|
| `search` | `BrainAdapter.gather_vault` (`officer_runner.py:346`); `screenpipe_adapter.gather` | `context_lib.gather(sources=["vault"])` |
| `find_reply_candidates` | `screenpipe_adapter.find_threads` | `draft_lib` thread discovery |
| `person_intel` | `BrainAdapter.person_intel` (`:371`) | `draft_lib.person_intel` |
| `open_commitments` | `BrainAdapter.open_commitments` (`:377`) | `commitments_lib.load_all` |
| `voice_profile` | `BrainAdapter.voice_profile` (`:399`) | `draft_lib.voice_profile` |
| `model_patterns` | `BrainAdapter.nate_model_patterns` (`:405`) | `me_signal.nate_model("patterns")` |
| `drafting_lessons` | `BrainAdapter.drafting_lessons` (`:414`) | `retro.lessons_before` |
| `read_note` | `BrainAdapter.read_note` (`:436`) | `OBSIDIAN_VAULT_PATH` jailed read |

### 4.2 `PersonalDispatch` — the write/actuator Protocol (kept gated, cross-ref only)

Separate Protocol so the WRITE side is bindable/nullable too, but its authority
semantics are unchanged (brain-bridge.md governs; `env.allow_sends()` gates).

```python
class PersonalDispatch(Protocol):
    def queue_draft(self, *args, **kw): ...      # the ONLY outbound path (gated)
    def deliver(self, *args, **kw): ...          # email_lib/teams_graph_lib egress (post-approval)
    def append_note(self, rel: str, body: str): ...  # vault WRITE (append_agent_inbox / daily-note)
    def log_reasoning(self, **kw): ...           # agent_reasoning write
```

External recipients stay per-item Captain-approved in every posture. A null
deployment binds a `NullPersonalDispatch` whose `queue_draft`/`deliver` no-op
(or raise a clear "no dispatch configured"), and the acting loop degrades to
draft-capture-only — exactly today's dev/test behavior when `allow_sends()` is
False.

### 4.3 `NullPersonalSource` — fail-closed generic default (mirrors `retro._RetroUnavailable`)

```python
# framework/sources/null.py
class NullPersonalSource:
    def available(self) -> bool: return False
    def search(self, handle, *, topic=None): return {"hits": [], "topic_terms": None}
    def find_reply_candidates(self, *, since=None): return []
    def person_intel(self, slug): return ""
    def open_commitments(self, direction): return []
    def voice_profile(self): return ""
    def model_patterns(self): return ""
    def drafting_lessons(self, before_ts): return ""
    def read_note(self, path): raise FileNotFoundError("no personal source configured")
```

Generic, empty, never crashes, never leaks another launcher's data — the same
fail-closed doctrine as `env.captain_name()` → `"Captain"` and the axes contract
→ `guardian`. A Flavor-B org deployment that wants real sensing binds an *org*
source (machine probes / repo signals) implementing the SAME Protocol; one that
wants none keeps `NullPersonalSource` and every gather returns thin, honest
empties (the officer sees "(no admissible context)" lines, never a crash).

### 4.4 The resolver + the layer-separation-safe loader (the crux)

```python
# framework/sources/__init__.py
_cache = None
def get_source() -> "PersonalSource":
    """The bound personal source for this deployment — the FOUNDATION resolver,
    mirror of env.captain_name(). Reads the adapter binding from
    instance/config/sources.yml; importlib-loads it; caches; fail-closes to
    NullPersonalSource on any absence / parse-fail / import-fail."""
    global _cache
    if _cache is not None: return _cache
    _cache = _load_bound_source() or NullPersonalSource()
    return _cache
```

**Why this does NOT violate `check-layer-separation.sh` (Corridor's hard rule).**
Framework may not statically `from instance import …` NOR carry the bare path
token `"instance"` in a `Path(...) / "instance"` construction. Two existing
framework files already load instance config without tripping the gate, and the
resolver copies them exactly:

- **`env.py`** (`captain_name`, `:87`) reads
  `root / "instance/config/platform.yml"` — a **single joined string literal**
  `"instance/config/platform.yml"`, NOT the token `"instance"` and NOT
  `/ "instance" /`. The gate greps for the exact quoted token `"instance"`; a
  joined path string does not match. `get_source()` reads
  `"instance/config/sources.yml"` the identical way.
- **`retro.py`** (`:68-76`) `importlib.util.spec_from_file_location` on an
  env-configured path — a **dynamic** import of a path-named module. The gate
  only catches STATIC `import instance` / `from instance`. `get_source()`
  `importlib.import_module`s the **config-named** dotted module
  (e.g. `sources.yml: adapter: flavor_a.screenpipe_source:ScreenpipeSource`)
  after adding the adapter dir to `sys.path` via the joined-string literal
  `"instance/flavor-a"`. Framework never names the instance module statically;
  the module name is DATA in instance config.

So the binding is: **config (in `instance/`) names the adapter; framework
dynamically loads it.** This is precisely the axes-contract §6.4 loader
pattern ("extensions receive resolved values; the loader hands them over") and
the extension-manifest mechanism already shipped
(`framework/schemas/extension-manifest.schema.json` +
`cabinet/scripts/validate-extension.sh`). The Flavor-A adapter ships a
`manifest.yml` (kind: `source`, `undo_contract`, `axis_compat`) and passes
`validate-extension.sh` like any other extension.

### 4.5 File layout

**AS REALIZED (PASS 1 + PASS 2) — a deviation from the original sketch, which
named an `instance/flavor-a/sources/` subdir.** The adapter home is
`instance/flavor-a/flavor_a/` — an importable package dir (the resolver adds
`instance/flavor-a` to `sys.path`, so the binding module dotted-name is
`flavor_a.<mod>`, matching `sources.yml`), and the WRITE side landed as a
SIBLING `PersonalDispatch` adapter reached via `get_dispatch()`, not folded into
the source. `sources.yml` therefore carries BOTH an `adapter:` (read) and a
`dispatch:` (write) binding.

```
framework/sources/
  __init__.py        # get_source() + get_dispatch() resolvers + caches
                     #   (read instance/config/sources.yml; fail-close to Null*)
  base.py            # PersonalSource + PersonalDispatch Protocols (stdlib only)
  null.py            # NullPersonalSource / NullPersonalDispatch (fail-closed)
  tests/             # resolver + Null hermetic tests
instance/flavor-a/flavor_a/
  __init__.py
  manifest.yml           # kind: source; axis_compat: {flavor: [personal]}
  screenpipe_source.py   # ScreenpipeSource — the re-homed BrainAdapter body;
                         #   owns the screenpipe READ imports & paths
  acting.py              # the acting gather→draft surface (ex-screenpipe_adapter)
  screenpipe_dispatch.py # ScreenpipeDispatch — the WRITE/egress adapter
                         #   (email_lib/teams_graph_lib send, Monday client,
                         #   vault daily-note write); owns the screenpipe WRITE deps
  _vault_gather_runner.py  # the py3.12 vault-search sidecar, moved with it
  tests/                 # adapter internals + acting + dispatch tests
instance/config/
  sources.yml        # adapter:  flavor_a.screenpipe_source:ScreenpipeSource
                     # dispatch: flavor_a.screenpipe_dispatch:ScreenpipeDispatch
                     #   (either absent ⇒ its Null* ; the whole binding is DATA)
```

---

## 5 · Phased migration — keep the RUNNING Flavor-A org unbroken

**Safety invariant (the correctness proof, mirroring DE-NATE §1).** On Nate's
live instance `get_source()` returns `ScreenpipeSource`, whose every method
**delegates to the SAME** `draft_lib` / `commitments_lib` / `BrainAdapter` code
that runs today. So every call returns a BYTE-IDENTICAL result and every
existing test stays green with no assertion weakened. **A red test = behavior
changed, not the goal.** Where a test constructs `BrainAdapter()` directly, it
is repointed to `get_source()` / the injectable seam the same way — never by
weakening the assertion.

**Phase 0 — Baseline the ratchets (no behavior change).** Land both §7 ratchets
in REPORT/baseline mode capturing today's 13+5 couplers. Nothing migrates yet;
the baseline simply freezes the surface so it can only shrink.

**Phase 1 — Define the seam, shim-first (adapter WRAPS today's code).** Create
`framework/sources/` (Protocols + `get_source()` + `Null*`). Create
`instance/flavor-a/sources/screenpipe_source.py` that, in its first cut, is a
**thin delegator**: it imports and calls the EXISTING `BrainAdapter` +
`screenpipe_adapter` functions unchanged. `get_source()` binds it on this
deployment (via `sources.yml`), `NullPersonalSource` elsewhere. **No caller
uses it yet** ⇒ zero runtime change, full suite green. This is the
`retro.retro_available()` pattern applied to sensing: the seam exists and is
proven before anything depends on it.

**Phase 2 — Migrate callers, COLDEST → HOTTEST, one file per step. [DONE —
PASS 2, byte-identical; one tail remains, see PASS-2 status below.]** Each step
swaps a direct `import draft_lib` / `BrainAdapter()` for `get_source()`, keeps
output byte-identical, runs that file's tests, and ratchets both §7 baselines
DOWN by one. Order by §6 risk:
1. **fidelity first** (`decision_cell`, `measure_intent`, `officer_runner`
   internals) — the injectable seam ALREADY exists
   (`BrainAdapter(context_lib=, server=, vault_search=)`), so this is mostly a
   re-home + rename, lowest risk. The leak fence is untouched (it sits above
   the adapter).
2. **watchdog / benchmark / smoke / Tier-2 paths** — cold; config reparents.
3. **acting** (`run_action_lane`, `run_draft_lane`, `screenpipe_adapter`,
   `morning_synthesis`, `binder_wire`) — HOT (live draft lane). Migrate behind
   the byte-identical invariant + the draft-lane's own tests; `binder_wire`'s
   `normalize_voice` repoints to the vendored `voice_charset` (no adapter).
4. **frontdoor egress** (`chair_drafts`, `daily_recap`) — HOTTEST (send libs +
   the obsidian-sync hash-match). Read side → `get_source()`; write side →
   `PersonalDispatch`, preserving `allow_sends()` gating and the byte-identical
   daily-note render (§6).

**Phase 3 — Flip the default + empty the allowlist. [DONE — PASS 2 / SRC-5
P2-FLIP.]** Once every Tier-1 caller
routes through `get_source()`, the Flavor-A adapter's screenpipe imports live
WHOLLY in `instance/flavor-a/`. The §7 no-screenpipe-in-core allowlist shrinks
to **empty**; `framework/**` names screenpipe nowhere. Flavor-B / clean-room
binds `NullPersonalSource` (or an org source) via `sources.yml` and the entire
framework runs with no `~/.screenpipe`, no vault, no crash — proven by a
clean-room CI job that runs the suite with `sources.yml` absent.

**Phase 4 — Fold the parallel seams. [PENDING — the retrodiction scoring
seam.]** Migrate the retrodiction SCORING engine (`retro.py`, already shimmed +
A2.1-flagged) and the germline board-id env paths (`action_exec`,
`actfirst_canary`) into the same instance-bound pattern — the board-id moves
ride the Captain amendment, surgically. (The `action_exec` / `actfirst_canary`
credential-PATH reparent to `env.shared_env_path()` already shipped in PASS 2
and is Captain-ratified via
`docs/proposals/germline-amendment-source-adapter-2026-07-05.md`; what remains
here is the `retro.py` scoring engine vendoring.)

**PASS-2 realized status (SRC-5 / P2-FLIP, 2026-07-06).** Phases 0–1 shipped in
PASS 1 (both ratchets baselined + the `framework/sources/` seam —
`get_source()` / `get_dispatch()` + `Null*` — shim-first). PASS 2 migrated every
Tier-1/Tier-2 caller off screenpipe and FLIPPED the ratchets:
`_ALLOWLISTED_FILES` is EMPTY with `_ALLOWLIST_BASELINE_MAX = 0`; the
`check-layer-separation.sh` `FRAMEWORK_IMPORTS_SCREENPIPE` +
`FRAMEWORK_PATH_SCREENPIPE` rule classes are live on the shrink-only
`.layer-separation-baseline`; the `clean-room-source` CI job proves framework
CORE imports + runs with `sources.yml` absent and `~/.screenpipe` unreadable
(`get_source()`→`NullPersonalSource`); and golden eval
`memory/golden-evals/eval-021-source-boundary.md` pins all of it. The acting
HOT-lane PATH reparent (`run_action_lane.py` + `run_draft_lane.py` →
`framework.env.vault_dir()` / `shared_env_path()`) **is DONE** (integrator, at
apply time — `run_draft_lane`'s vestigial screenpipe sys.path insert removed;
`run_action_lane`'s `VAULT` → `vault_dir()` and `_load_env` `.env` →
`shared_env_path()`, byte-identical on macOS's case-insensitive FS). The static
ratchet allowlist is now **EMPTY** and green, the clean-room job passes, and
`framework/**` names screenpipe nowhere — PASS 2 is fully realized and merged to
live (`4429fbba`).

---

## 6 · Hot-path risk assessment per subsystem

| Subsystem | Heat | What runs on it | Risk | Mitigation |
|---|---|---|---|---|
| **acting** (`run_*_lane`, `screenpipe_adapter`, `morning_synthesis`, `binder_wire`) | 🔥 HOT | the LIVE draft lane — gather→draft→propose against real threads on a timer; latency + correctness sensitive; adjacent to outbound | **HIGH** — a broken `search`/`gather` = no drafts or wrong drafts | shim-first + byte-identical; migrate last; draft-lane tests gate each step; `find_reply_candidates` preserves the noise-filter + should-reply gate exactly |
| **frontdoor · egress** (`chair_drafts`, `daily_recap`) | 🔥 HOTTEST | post-approval send via `email_lib`/`teams_graph_lib`; `daily_recap` writes the vault daily note **byte-identical to obsidian-sync** (hash-match ⇒ skip) | **HIGH** — a send regression is externally visible; a daily-note render drift breaks the obsidian-sync convergence | send stays behind `PersonalDispatch` + `allow_sends()` (unchanged); pin the daily-note render with a golden hash test BEFORE moving it |
| **fidelity** (`officer_runner/BrainAdapter`, `decision_cell`, `_vault_gather_runner`, `measure_intent`) | ♨ WARM | eval/scoring harness — not real-time outbound, but the **leak-guard is SAFETY-CRITICAL** | **MEDIUM**, but LOWEST migration risk — the injectable seam already exists; it is a re-home + rename | keep `gather_cutoff_context`'s content-ts exclusion-by-default fence ABOVE the adapter (unchanged); the adapter only supplies raw hits, the fence still runs in-process |
| **fidelity · scoring** (`retro.py`) | ♨ WARM | retrodiction scoring engine (separate seam) | **LOW** — already shimmed, `retro_available()` degrades cleanly | Phase 4; the model for `Null*` |
| **watchdog** (`check`, `registry`) | ❄ COLD | watches `~/.screenpipe/state`; degrades to "nothing to watch" | **LOW** | watched-dir → config; Flavor-B watches its own targets or none |
| **probes / triggers / learning / authority / autoreply / Tier-2 paths** | ❄ COLD | mostly comment refs + `benchmark`/`smoke` state paths + one `agent_reasoning` write (`autoreply/wiring`) | **LOW** | config reparent; reasoning write → `PersonalDispatch.log_reasoning` |

**Cross-cutting risk — the py3.9/3.12 boundary.** The vault vector search cannot
run in-process under the framework interpreter (system py3.9.6, no loadable
sqlite vector extension), which is why `BrainAdapter` shells out to
`_vault_gather_runner.py` under py3.12 (`officer_runner.py:281-316`). The
adapter, not framework CORE, must keep owning that subprocess seam — it moves to
`instance/flavor-a/` intact. Framework CORE only ever sees the returned dict.

---

## 7 · Clean-room ratchet extension — "core imports the interface, not screenpipe"

The DE-NATE build shipped `test_no_launcher_hardcode.py` (bare `Nate` / path)
as the sister of `test_axes_contract.py` (axis branches). This seam adds the
THIRD ratchet in the same family, plus a rule class on the existing layer gate.
Both are shrink-only baseline ratchets so the RUNNING org is never broken by the
guard while migration is in flight.

### 7.1 Extend `cabinet/scripts/check-layer-separation.sh` — new rule class

Add `FRAMEWORK_IMPORTS_SCREENPIPE` (and `FRAMEWORK_PATH_SCREENPIPE`) alongside
today's `FRAMEWORK_IMPORTS_INSTANCE` etc., using the SAME baseline mechanism
(`.layer-separation-baseline`, comm-23 vs current, only-shrinks, Captain
approval to grow):

- **Import rule:** `framework/**/*.py` matching
  `^\s*(import|from)\s+(draft_lib|commitments_lib|context_lib|me_signal|sp_lib|product_ops_lib|email_lib|teams_graph_lib|agent_reasoning)\b`
  (comment/docstring-filtered, as the script already does for `instance`).
- **Path rule:** runtime lines constructing `~/.screenpipe` or
  `screenpipe-brain`/`OBSIDIAN_VAULT_PATH` (excluding comments).
- **Baseline seed = the 13 Tier-1 + 5 Tier-2 files** from §3. Each Phase-2
  migration removes one; when the baseline reaches **empty**, framework core is
  clean. The Tier-3 inert files never enter the baseline (comment-only, already
  filtered).

### 7.2 New `framework/tests/test_no_screenpipe_in_core.py` — the strong ratchet

The sister of `test_no_launcher_hardcode.py`, same proven engine
(stdlib-only, `import pytest`-guarded so it runs under system py3.9, read-ONLY
text-walk, `os.path.realpath` symlink-escape refused, hermetic scanner-engine
tests with injected allowlists). It goes RED on any `framework/**/*.py`
(skipping `tests/`, `__pycache__`, `test_*`) that imports a screenpipe `_shared`
lib OR carries a `~/.screenpipe` / vault path literal, UNLESS covered by a
**shrink-only allowlist**:

- `_ALLOWLISTED_FILES` — the not-yet-migrated Tier-1/2 files, each with a
  justification + a `TODO(SRC)` and a target phase. Seeded at 18, driven to 0.
- `_TEMPORARY_RESIDUALS` frozenset + `_TEMP_BASELINE_MAX` (starts at 18, target
  0) — the identical forcing-function the launcher ratchet uses: a file that no
  longer imports screenpipe MUST have its entry deleted (self-test
  `test_temporary_entries_still_needed`), so the ratchet tightens as lanes
  migrate. A NEW screenpipe import in a migrated file is CI-red, not an
  allowlist addition.
- **End state:** allowlist EMPTY. The doctrine in one line — *the only code in
  the repo that may name screenpipe lives in `instance/flavor-a/`, never in
  `framework/`.* `framework/sources/` names the Protocol; the adapter names
  screenpipe; the resolver binds them by config.

### 7.3 Golden eval + docs

- Add `memory/golden-evals/eval-0NN-source-boundary.md` pinning both ratchets +
  the empty-allowlist end state (sibling to `eval-020-axes-contract.md`).
- CLAUDE.md's launcher-agnostic paragraph gains one clause: *framework CORE
  reaches the captain's estate only through `framework.sources.get_source()`;
  a screenpipe import in `framework/**` is CI-red* — the prose half of the
  ratchet, mirroring the captain_name() clause already there.
- A **clean-room CI job** runs `pytest framework/` + `lib` + gates with
  `instance/config/sources.yml` absent and `~/.screenpipe` unreadable, proving
  the null path is green (the real "another captain can run it" test).

---

## 8 · Ratification asks & open questions

1. **Ratify the seam name + home.** `framework/sources/` (Protocol) +
   `instance/flavor-a/sources/` (adapter) + `instance/config/sources.yml`
   (binding). Confirm `flavor-a` as the instance sub-dir convention (first use;
   sets precedent for `flavor-b`).
2. **Ratify the two-Protocol split** (`PersonalSource` read / `PersonalDispatch`
   write) vs one combined interface. Recommendation: split — the read side is
   nullable/org-swappable freely; the write side carries authority semantics
   that must stay pinned.
3. **`model_patterns` naming.** Interface method is launcher-neutral
   (`model_patterns`); the Flavor-A adapter internally calls
   `me_signal.nate_model("patterns")` (brain-artifact kept verbatim, DE-NATE §3).
   Confirm no `captain_model` invention.
4. **Germline board-id files** (`action_exec`, `actfirst_canary`) migrate via
   the Captain amendment, surgically — confirm they ride the same amendment as
   the axes/de-nate germline subset rather than a standalone unlock.
5. **Org source (Flavor-B) shape** is explicitly deferred — this spec only
   guarantees the SEAM + the null default. What an org machine-probe source
   supplies (repo signals, CI/deploy/probe evidence) is the axes-spec "org:
   machine-probe-weighted evidence supply" and is a separate build.

**Work-item sizing (for the next build's parallelization map):**

| ID | Item | Size |
|---|---|---|
| SRC-0 | `framework/sources/` package (Protocols + resolver + Null*) + `sources.yml` schema | **S** |
| SRC-1 | `instance/flavor-a/sources/` adapter (re-home `BrainAdapter` + acting surface + sidecar) + manifest | **M** |
| SRC-2 | Migrate fidelity callers (seam already injectable) | **S** |
| SRC-3 | Migrate acting + frontdoor hot paths (byte-identical + golden daily-note hash) | **L** |
| SRC-4 | Tier-2 config/env reparents (+ germline board-id via amendment) | **M** |
| SRC-5 | Two ratchets (layer-sep rule class + `test_no_screenpipe_in_core.py`) + golden eval + clean-room CI job | **M** |
| SRC-6 | Phase 4: fold `retro.py` scoring seam (A2.1 vendoring) | **M** |

Marginal cost of a NEW flavor's source after this build: one adapter module +
one `sources.yml` line + one manifest — no `framework/` fork. That is the whole
point of the seam.
