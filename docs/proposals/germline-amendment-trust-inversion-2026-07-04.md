# Germline amendment proposal — trust inversion (`act_with_undo`) — 2026-07-04

**Status:** AWAITING CAPTAIN. Germline files
(`framework/authority/classifier.py`, `framework/authority/matrix.py`,
`framework/policies/authority-matrix.yml`, `.claude/rules/courses-of-action.md`)
are Captain-applied only. Reply **"apply act_with_undo"** and the session applies
exactly the diffs below, adds the CI proofs in the SAME commit, records the
ruling + supersession note in `captain-decisions.md`, and re-runs the golden
evals.

**SUPERSEDES** `docs/proposals/germline-amendment-task-create-2026-07-03.md` in
full (grand plan §3, CAPTAIN MOMENT 2). That doc proposed adding `task_create`
to the existing `reversible` class with no verdict-table change; this amendment
subsumes it — `task_create` lands in the new `pm_write` class under the new
`act_with_undo` verdict, not `reversible`. Do NOT apply the task_create doc
separately; applying this one closes it.

**Precondition (Moment 1 must have landed first):** the critical path is
`UNDO-1 → SEC-3 → TI-3 → MOMENT 2`. This amendment assumes CAPTAIN MOMENT 1
already applied — specifically the `investigation_run` enum + its `reversible`
mapping (propose-first), the gh-hole closures, and the graduation recency-clock
fix. This diff does NOT touch `investigation_run`; if M1 added it to
`reversible`, it stays there untouched.

---

## 0 · What this changes, in one paragraph

Realizes the EARN-DEMOTION posture (captain-decisions.md, 2026-07-03/04) as
germline data. It adds one new verdict — `act_with_undo` — and two new risk
classes — `pm_write` (Monday task creates + board-status writes) and
`calendar_write` (Cabinet-calendar event creates). For those classes trust
starts GRANTED: **every** confidence state resolves to `act_with_undo`, and only
`demote` falls to `propose_only`. This is the inversion — normally `unmeasured →
propose_only`; here `unmeasured → act_with_undo`, because the action carries a
registered inverse and is reversed on evidence, not gated pending graduation.
`board_status` MOVES out of `reversible` into `pm_write` (its ledger cells are
keyed `(actor, lane, action_type)`, so its accumulated history follows the
`action_type` string, undisturbed). `officer_dispatch` becomes a first-class
`internal_comms` member (a distinct cell from real internal messages) so
delegate dispatch stamps a graduable cell while staying propose-first. The six
hard ceilings are byte-identical. Rolling this back is one revert (the two
classes → `propose_only`) plus the flag off; nothing is destroyed.

**Germline surface (4 files) — why `matrix.py` is in it.**
`framework/authority/matrix.py` holds the authoritative `RISK_CLASSES` and
`VERDICTS` frozensets (matrix.py:59–69). The fail-closed validator asserts
`set(risk_classes) == RISK_CLASSES`, `set(verdicts) == RISK_CLASSES`, and every
cell verdict `∈ VERDICTS` (matrix.py:249, 327, 337). Adding `pm_write` /
`calendar_write` / `act_with_undo` to the YAML **alone** makes `load_matrix()`
raise `MatrixValidationError`. So "VERDICTS += act_with_undo" is literally an
edit to the matrix.py frozenset. The YAML change and the matrix.py change are
one indivisible amendment.

---

## 1 · `ACTION_TYPE_MAP` — no diff needed (already staged, dormant)

`framework/acting/action_lane.py:516` already carries every target this
amendment needs:

```python
ACTION_TYPE_MAP = {
    "monday_task_update": "board_status",
    "monday_task_create": "task_create",
    "reminder_create":    "calendar_event_create",
    "delegate_work":      "officer_dispatch",
    "investigation_run":  "investigation_run",
}
```

These entries were landed ahead of the germline amendment on purpose:
`step_action_type()` (action_lane.py:545) is **enum-guarded** — a mapping whose
target is not yet in `classifier.ACTION_TYPES` returns `None`, so
`task_create` / `calendar_event_create` / `officer_dispatch` emit nothing today.
**The classifier enum addition in §2 is what activates them.** No edit to
`ACTION_TYPE_MAP` is part of this amendment; §5 adds a CI guard that every
`ACTION_TYPE_MAP` value is a real enum member (no dormant-forever typo).

> Resolved ambiguity: the grand plan and task list "ACTION_TYPE_MAP:
> delegate_work→officer_dispatch, reminder_create→calendar_event_create" as part
> of the amendment. They are already present in code; the amendment's job is to
> admit the enums so they stop being dormant. Documented here rather than
> re-added.

---

## 2 · `framework/authority/classifier.py` — diff

### 2a · Enum surface — add the three members; move `board_status`

```diff
-# reversible risk_class members
 _REVERSIBLE = {
-    "task_status_move", "board_status", "label", "tier2_note",
-    "draft_only", "local_edit",
+    "task_status_move", "label", "tier2_note",
+    "draft_only", "local_edit",
 }
+# pm_write — reversible-with-undo (act_with_undo class) [GERM-2]. board_status
+# MOVES here out of _REVERSIBLE; the ledger cell key is (actor, lane,
+# action_type), so the string is unchanged and its history follows it.
+_PM_WRITE = {"task_create", "board_status"}
+# calendar_write — reversible-with-undo (act_with_undo class) [GERM-2].
+_CALENDAR_WRITE = {"calendar_event_create"}
 # comms
-_INTERNAL_COMMS = {"internal_message", "internal_email"}
+# officer_dispatch is internal_comms but a DISTINCT cell from internal_message
+# (RT-B4) — a delegate dispatch is org-internal machine handoff, never an
+# outbound colleague message; it stamps its own graduable cell and stays
+# propose-first (internal_comms's graduated verdict is dormant per M1).
+_INTERNAL_COMMS = {"internal_message", "internal_email", "officer_dispatch"}
```

```diff
 ACTION_TYPES = frozenset(
     _REVERSIBLE
+    | _PM_WRITE
+    | _CALENDAR_WRITE
     | _INTERNAL_COMMS
     | _EXTERNAL_COMMS
     | _DEPLOY
     | _SPEND
     | _SECRETS
     | _NETWORK_WRITE
     | _CREDENTIALS_GRANT
     | {AMBIGUOUS}
 )
```

`CEILING_ACTION_TYPES` is **untouched** — `pm_write` / `calendar_write` are NOT
ceilings. `_risk_rank()` (action_lane.py:525) reads only the ceiling + comms +
deploy + spend groups, so the new pm/calendar members correctly default to the
reversible-floor rank (0) for the max-restrictive card stamp — exactly what its
comment at action_lane.py:530 already anticipates. `officer_dispatch` joining
`_INTERNAL_COMMS` gives it rank 10 (internal_comms), matching its risk class.

### 2b · MCP dispatch — full-match Monday carve-outs ABOVE the `mcp_post` rule [RT-B2]

New pure helper (add near the other `_classify_mcp` predicates):

```python
# The Monday GraphQL mutation fields we recognize. The create pair is the ONLY
# act-first-eligible set; everything else is a status write (board_status) or a
# ceiling. Fixed vocabulary — an unrecognized mutation field forces the ceiling.
_MONDAY_CREATE_OPS = frozenset({"create_item", "create_update"})
_MONDAY_STATUS_OPS = frozenset({
    "change_column_value", "change_multiple_column_values",
    "change_simple_column_value", "change_item_column_values",
})
_MONDAY_KNOWN_OPS = frozenset({
    "create_item", "create_update", "create_subitem", "create_board",
    "create_group", "create_column", "duplicate_item", "archive_item",
    "delete_item", "delete_update", "move_item_to_board", "move_item_to_group",
    "change_column_value", "change_multiple_column_values",
    "change_simple_column_value", "change_item_column_values",
})
_MONDAY_OP_RE = re.compile(r"\b(" + "|".join(sorted(_MONDAY_KNOWN_OPS)) + r")\b")


def _monday_mutation_ops(tool_name: str, tool_input: dict[str, Any]) -> "set[str] | None":
    """The SET of Monday mutation ops a call performs, or None if it is not a
    Monday mutation. Two shapes: (1) a named per-op MCP tool
    (mcp__..._monday_com__create_item) -> {that op}; (2) a generic API tool
    (all_monday_api / all_api_write) or a Bash/curl GraphQL POST carrying a
    query/body string -> every op the body mentions (fixed vocabulary). Reads
    (get_*/search/board_insights) and non-Monday tools -> None."""
    tn = tool_name.lower()
    if "monday" not in tn and "monday" not in str(tool_input.get("query", "")).lower():
        # A raw curl to api.monday.com still lands here via the Bash path (see
        # _classify_bash) — this MCP helper only fires for monday-named tools.
        if "monday" not in tn:
            return None
    # (1) named per-op tool: the op is the tool-name suffix.
    for op in _MONDAY_KNOWN_OPS:
        if tn.endswith("__" + op) or tn.endswith("_" + op):
            return {op}
    # (2) generic API / body-bearing tool: scan the query/variables body.
    body = " ".join(str(tool_input.get(k, "")) for k in ("query", "body", "graphql", "mutation"))
    if body.strip():
        found = set(_MONDAY_OP_RE.findall(body))
        return found            # possibly empty -> fail-closed to ceiling below
    return None
```

Insert this block in `_classify_mcp` **immediately above** the existing
`board / task status` rule (which is itself already above `mcp_post`):

```diff
+    # --- GERM-2: Monday mutations — FULL-MATCH carve-outs [RT-B2] ----------
+    # Placed ABOVE mcp_post (order matters): a PURE create maps to the
+    # reversible-with-undo task_create; a pure status write to board_status;
+    # ANY other or MIXED Monday mutation (a create batched with a delete, a
+    # people/assignee op, an unknown field, or an unparseable body) does NOT
+    # earn the softer class — it falls to the network_write ceiling. An
+    # attacker cannot smuggle a dangerous op inside a "create" batch to soften
+    # the verdict.
+    ops = _monday_mutation_ops(tool_name, tool_input)
+    if ops is not None:
+        if ops and ops <= _MONDAY_CREATE_OPS:
+            return "task_create"
+        if ops and ops <= _MONDAY_STATUS_OPS:
+            return "board_status"
+        return "mcp_post"        # mixed / unknown / empty -> ceiling (fail-closed)
+
     # --- board / task status (reversible) ---------------------------------
-    if ("monday" in tn or "board" in tn) and (
+    # (residual: non-Monday board tools; Monday handled above.)
+    if "board" in tn and "monday" not in tn and (
         "change_item_column" in tn or "column_value" in tn or "status" in tn
     ):
         return "board_status"
```

The `<=` subset test is the full-match gate: `{create_item, create_update}` and
any subset → `task_create`; a single extra element makes the subset test fail →
`mcp_post`. The `ops and` guard rejects the empty set (a mutation tool whose
body did not parse) into the ceiling, never into a create.

### 2c · Bash dispatch — calendar carve-out (byte-match the lane template) [RT-B2]

The lane writes calendar events through one exact AppleScript template
(`action_exec._exec_calendar_event`, action_exec.py:614). The apply commit
extracts that string verbatim into a new **zero-dependency leaf** module
`framework/frontdoor/calendar_template.py`:

```python
# framework/frontdoor/calendar_template.py  (NEW — single source of the lane's
# calendar-event AppleScript, imported by BOTH the executor and the classifier
# so "byte-match the lane template" is literally true and can never drift).
CALENDAR_EVENT_SCRIPT = (
    'on run argv\n'
    ...            # the exact body currently inlined at action_exec.py:614-661
    'end parseIso')
```

`_exec_calendar_event` changes its `script = ( ... )` literal to
`script = CALENDAR_EVENT_SCRIPT` (behavior-identical; a CI drift test asserts the
executor uses the constant). Then in `classifier._classify_bash`, immediately
before the final `return "local_edit"`:

```diff
+    # --- GERM-2: calendar write (calendar_write / external_comms) [RT-B2] --
+    # An osascript Calendar write. Attendee/invitee-bearing -> external_comms
+    # ceiling: inviting a human SENDS mail (a dedicated CI test pins this). A
+    # write byte-matching the lane executor's event template -> the
+    # reversible-with-undo calendar_event_create; any OTHER Calendar osascript
+    # stays AMBIGUOUS (propose-defaulting) — only the lane's own template acts.
+    if "osascript" in low and "calendar" in low:
+        if re.search(r"\battendee|\binvitee|make new attendee", low):
+            return "external_message"
+        from framework.frontdoor.calendar_template import CALENDAR_EVENT_SCRIPT
+        if CALENDAR_EVENT_SCRIPT in command:
+            return "calendar_event_create"
+        return AMBIGUOUS
+
     # --- everything else local / reversible / no-egress -------------------
     return "local_edit"
```

> Resolved ambiguity: the spec says non-template calendar writes go to
> "ceiling." A propose-defaulting `AMBIGUOUS` is the honest, fail-safe outcome —
> the action is neither a recognized reversible-with-undo class nor one of the
> six positive execution-surface ceilings, and `AMBIGUOUS` resolves to
> `propose_only`. The only TRUE hard-ceiling calendar case is attendee-bearing →
> `external_comms` (always_gated). Net effect matches intent: nothing but the
> lane's own byte-identical template ever acts unattended.
>
> Resolved ambiguity: the classifier module docstring says "only stdlib is
> used." The calendar carve-out adds one framework-internal import of a pure
> string constant (no transitive deps — `calendar_template.py` imports nothing).
> The apply commit relaxes the docstring to "stdlib + one framework leaf
> template constant." The import is call-time (inside the function) so module
> load stays cycle-free (`calendar_template` is a leaf; the executor imports it
> too, never the reverse).

**Defense-in-depth note.** The classifier is content-blind and path-blind by
design; it only *types* an action. It does not by itself grant an unattended
write. Even a byte-matching officer call classified `calendar_event_create` is
demoted to `propose_only` by the TI-3 journal-path attestation (§5, PATH parity)
unless it executed through the journaled lane. The byte-match is the type
signal; TI-3 attestation is the authorization.

---

## 3 · `framework/authority/matrix.py` + `authority-matrix.yml` — diff

### 3a · `matrix.py` — the vocab frozensets (REQUIRED, see §0)

```diff
 RISK_CLASSES = frozenset({
-    "reversible", "internal_comms", "external_comms",
+    "reversible", "pm_write", "calendar_write",
+    "internal_comms", "external_comms",
     "deploy_nonprod", "deploy_prod", "spend",
     "secrets", "network_write", "credentials_grant",
 })

 VERDICTS = frozenset({
-    "auto", "auto_with_veto_window", "notify_after",
+    "auto", "act_with_undo", "auto_with_veto_window", "notify_after",
     "propose_only", "always_gated", "classifier",
 })
```

No other matrix.py change: `pm_write` / `calendar_write` are non-ceiling, so
they must cover all five confidence states (the validator enforces this at
matrix.py:358) — the YAML rows below satisfy it. They are absent from
`hard_ceiling`, so the FIX-7 six-member coverage is unchanged.

### 3b · `authority-matrix.yml` — `risk_classes`

```diff
     risk_classes:
       reversible:
-        action_types: [task_status_move, board_status, label, tier2_note, draft_only, local_edit]
+        action_types: [task_status_move, label, tier2_note, draft_only, local_edit]
+      pm_write:                                                       # act_with_undo (reversible-with-undo)
+        action_types: [task_create, board_status]
+      calendar_write:                                                 # act_with_undo (reversible-with-undo)
+        action_types: [calendar_event_create]
       internal_comms:
-        action_types: [internal_message, internal_email]
+        action_types: [internal_message, internal_email, officer_dispatch]
       external_comms:                                                 # HARD CEILING: external_comms
         action_types: [external_message, external_email]
```

> If Moment 1 has already added `investigation_run` to `reversible`, it REMAINS
> there — this diff only removes `board_status` from that line and leaves every
> other reversible member untouched. Apply the removal, not a whole-line
> replace, if the live file differs.

The validator asserts every mappable `action_type` is mapped exactly once
(matrix.py:272, 278). `board_status` now appears only under `pm_write`;
`task_create` / `calendar_event_create` / `officer_dispatch` (newly enum'd in
§2) each get their single home here. Coverage stays exact.

### 3c · `authority-matrix.yml` — `verdicts` (the inversion)

Insert directly after the `reversible:` verdict block:

```diff
       reversible:
         graduated: auto
         eligible: propose_only
         propose_only: propose_only
         unmeasured: propose_only
         demote: propose_only
+      pm_write:                          # EARN-DEMOTION: trust granted, lost on evidence
+        graduated: act_with_undo
+        eligible: act_with_undo
+        propose_only: act_with_undo
+        unmeasured: act_with_undo
+        demote: propose_only
+      calendar_write:
+        graduated: act_with_undo
+        eligible: act_with_undo
+        propose_only: act_with_undo
+        unmeasured: act_with_undo
+        demote: propose_only
       internal_comms:
         graduated: auto_with_veto_window      # + notify_after implied (the notification IS the veto handle)
         eligible: propose_only
         propose_only: propose_only
         unmeasured: propose_only
         demote: propose_only
```

`internal_comms` verdicts are UNCHANGED — `officer_dispatch` inherits them. Its
`graduated → auto_with_veto_window` cell is DORMANT by the M1 captain-decisions
ruling (send lane CI-pinned disarmed), so `officer_dispatch` is propose-first in
practice: the "same propose-first bar" the spec names. Its distinct cell key
(§5, RT-B4) keeps its graduation accounting separate from real internal messages
forever.

The six hard-ceiling rows (`external_comms`, `deploy_prod`, `spend`, `secrets`,
`network_write`, `credentials_grant`), `hard_ceiling`, `ceiling_frozenset_map`,
`veto_window_minutes`, `deploy`, `bars`, and `cooldown_days` are **byte-identical
— NO change**. In particular `network_write` remains the always-gated ceiling;
only the *classifier* now types a PURE Monday create as `pm_write` before it can
reach `mcp_post`.

> Resolved ambiguity — graduation bars for the act-first classes. `bars` and
> `cooldown_days` require only a `default` entry (matrix.py:384, 401); the new
> classes are intentionally NOT given their own bars. They act from `unmeasured`
> already, so graduation is not their promotion mechanism — demotion is governed
> at runtime by the TI-7 kind-breaker (undo-rate 7d/25%/≥8), the cell cluster
> rule (≥2 wrong in last-10), the canary, and the silence breaker, none of which
> live in the matrix `bars`. Leaving `bars`/`cooldown_days` untouched keeps the
> demoted-cell `default` cooldown (14d) applying uniformly.

### 3d · Runtime undo parameters live OFF the germline matrix (resolved decision)

The grand plan's CAPTAIN MOMENT 2 also names a germline `undo:` payload-gate
block (allowlist ref, `attendee_free`, `ttl 48h`, breaker `7d/25%/8`) and
`act-first-surfaces.yml`. Those are **runtime parameters, not matrix schema**,
and the matrix policy validator is `additionalProperties:false` at the policy
level (matrix.py:84) — bolting an `undo:` key onto the matrix would force a
`_POLICY_KEYS |= {"undo"}` + a bespoke `_validate_undo()` and widen the germline
diff. This amendment therefore keeps the matrix change to the verdict/class
vocabulary only, and locates the undo parameters where they already live:

- `UNDO_WINDOW_H = 48`, pointer TTL, journal retention — shipped constants in
  `framework/frontdoor/action_undo.py` (UNDO-1).
- kind breaker `7d / 25% / ≥8`, estate/kind caps, silence breaker — shipped in
  the TI-7 runtime (Wave 2).
- board allowlist + `attendee_free` + per-board 90d attestation —
  `instance/config/act-first-surfaces.yml`, seeded from the TI-0 cascade audit
  (the ratified allowlist is a founder action at apply, §6).

If the Captain prefers these pinned INTO the germline matrix for a single
Captain-readable surface, that is a one-line `_POLICY_KEYS` + `_validate_undo()`
addition — offered as an alternative, not taken by default, to keep the germline
change minimal and the validator unextended.

---

## 4 · `.claude/rules/courses-of-action.md` — proposed edit

Germline — proposed, never applied by an officer. Two edits, both citing the
2026-07-03/04 EARN-DEMOTION ruling and the 2026-07-04 Monday-notifications
refinement in `shared/interfaces/captain-decisions.md`.

### 4a · §2 — per-step gate carve-out for act_with_undo classes

Append to the second bullet of "## 2. Courses of action":

```diff
 - **ONE proposal card per situation**, carrying the whole chain with a
   **per-step gate** (the Captain can approve, edit, or skip each step
   independently). Never split one situation across multiple pings, and
   never propose step 1 while silently planning the rest.
+
+  **Exception — reversible-with-undo steps (`pm_write` / `calendar_write`).**
+  Per the EARN-DEMOTION ruling (captain-decisions.md, 2026-07-03/04), a step
+  whose action_type is in an `act_with_undo` class does not wait on a
+  pre-approval gate: it ACTS immediately (write-ahead journaled, executed,
+  told after) and its **per-step gate BECOMES a per-step undo handle on the
+  receipt** — the Captain reverses it with `undo [n]` inside the 48h window
+  instead of approving it beforehand. Every gated step in the SAME chain
+  (anything outbound, deploy, spend, `officer_dispatch`, or any hard-ceiling
+  step) still carries its ordinary pre-approval per-step gate; a mixed chain
+  keeps both — acted steps show as done-with-undo, gated steps as awaiting.
+  This is the ONLY relaxation; the investigation bar (§1) and one-card
+  discipline are unchanged.
```

### 4b · §3 — digest wording for acted steps

Add a bullet under "## 3. Proposal hygiene":

```diff
 - **Stale proposals auto-expire into the briefing.** ...
+- **Acted steps are told, not asked.** A reversible-with-undo step that already
+  acted is reported in the digest's ✅ ACTED section — one line rendering the
+  EXACT written content (what a colleague will actually see), its receipt id,
+  and its `undo [n]` handle. It is never phrased as a question and never
+  re-pinged. A cell's acted lines quiet to a weekly rollup only after ≥3
+  explicit Captain 👍 confirmations on that cell (TTL survival alone never
+  quiets it). Monday's own native task notifications are harmless and internal
+  (captain-decisions.md, 2026-07-04) and are not themselves an outbound step.
```

---

## 5 · CI proofs — added in the SAME apply commit ("Docs Must Track the Code")

Concrete stubs/updates. Test-file paths are real; assertions are apply-ready.

**FIX-1 · enum parity** — `framework/authority/tests/test_classifier.py`
- Extend `TestEnumSurface.test_all_design_action_types_present`: add
  `"task_create", "calendar_event_create", "officer_dispatch"` to the `expected`
  set (still asserted `expected <= ACTION_TYPES`).
- New `test_action_type_map_targets_are_enum_members`:
  ```python
  from framework.acting.action_lane import ACTION_TYPE_MAP
  def test_action_type_map_targets_are_enum_members():
      # No dormant-forever typo: every stamped target is a real enum member.
      assert set(ACTION_TYPE_MAP.values()) <= set(ACTION_TYPES)
  ```
- New carve-out behavior tests:
  ```python
  def test_pure_monday_create_is_task_create():
      assert classify_action("mcp__claude_ai_monday_com__create_item",
                             {"board_id": "5091706356", "item_name": "x"}) == "task_create"
      assert classify_action("mcp__x_monday_com__all_api_write",
                             {"query": "mutation { create_item(...) { id } create_update(...) { id } }"}) == "task_create"
  def test_batched_monday_mutation_is_ceiling_not_create():   # [RT-B2]
      assert classify_action("mcp__x_monday_com__all_api_write",
             {"query": "mutation { create_item(...){id} change_column_value(...){id} }"}) == "mcp_post"
      assert classify_action("mcp__x_monday_com__all_api_write",
             {"query": "mutation { create_item(...){id} delete_item(...){id} }"}) == "mcp_post"
  def test_monday_status_write_is_board_status():
      assert classify_action("mcp__claude_ai_monday_com__change_item_column_values",
                             {"board_id": "5091706356"}) == "board_status"
  def test_calendar_template_is_calendar_event_create():
      from framework.frontdoor.calendar_template import CALENDAR_EVENT_SCRIPT
      cmd = "osascript -e " + repr(CALENDAR_EVENT_SCRIPT) + " Cabinet 'T' '' 2026-07-05T09:00"
      assert classify_action("Bash", {"command": cmd}) == "calendar_event_create"
  def test_attendee_calendar_is_external_comms():             # [RT-B2] dedicated
      cmd = "osascript -e 'tell application \"Calendar\" ... make new attendee ...'"
      assert classify_action("Bash", {"command": cmd}) == "external_message"
  def test_non_template_calendar_is_propose_defaulting():
      cmd = "osascript -e 'tell application \"Calendar\" to make new event'"
      assert classify_action("Bash", {"command": cmd}) == AMBIGUOUS
  ```

**undo-capability parity — TYPE and PATH** [RT-B2] — new
`framework/frontdoor/tests/test_undo_capability_parity.py`
- TYPE: every `act_with_undo`-classed action_type has a registered, non-`none`
  inverse. Map action_type → executor kind, assert `act_first_eligible` /
  `inverse_for(...).op != "none"`:
  ```python
  from framework.frontdoor import action_undo as U
  AWU_TYPE_TO_KIND = {                       # act_with_undo type -> lane kind (+ backend)
      "task_create":           ("monday_task_create", "monday"),
      "board_status":          ("monday_task_update", "monday"),
      "calendar_event_create": ("reminder_create",    "calendar"),
  }
  def test_every_act_with_undo_type_has_a_real_inverse():
      for at, (kind, backend) in AWU_TYPE_TO_KIND.items():
          assert U.act_first_eligible(kind, backend) is True
          assert U.inverse_for(kind, backend, {}, {}, {})["op"] != "none"
  def test_officer_dispatch_has_no_inverse_and_is_not_act_first():
      # internal_comms, not act_with_undo — must have NO act-first inverse.
      assert U.act_first_eligible("delegate_work", "delegate") is False
  ```
- PATH: an `act_with_undo` verdict is honored ONLY through the journaled lane
  executor; an officer's raw pm_write/calendar_write call resolves `propose_only`
  (asserts PATH coverage, not just type coverage). Written against the TI-3
  resolver (landed before Moment 2 on the critical path):
  ```python
  def test_act_with_undo_requires_journal_attestation():
      from framework.acting import run_action_lane as R      # TI-3
      assert R.resolve_verdict(action_type="task_create", journal_attested=False) == "propose_only"
      assert R.resolve_verdict(action_type="task_create", journal_attested=True)  == "act_with_undo"
  ```
  (If TI-3's public seam differs at apply time, bind to its real attestation
  entrypoint; the invariant — unattested pm_write/calendar_write ⇒ propose_only —
  is the assertion that must hold.)

**act_with_undo never on a ceiling class** — `framework/authority/tests/test_matrix.py`
```python
def test_act_with_undo_never_on_a_ceiling_row(loaded):
    pol = loaded
    for rc in pol["hard_ceiling"]:
        assert "act_with_undo" not in set(pol["verdicts"][rc].values())
    assert "pm_write" not in pol["hard_ceiling"]
    assert "calendar_write" not in pol["hard_ceiling"]
```

**officer_dispatch ≠ internal_message cell key** [RT-B4] — new
`framework/fidelity/tests/test_officer_dispatch_cell_key.py`
```python
from framework.fidelity.consequence import compute_ratios
def test_officer_dispatch_and_internal_message_are_distinct_cells():
    ledger = [
        {"ts": "2026-07-04T10:00:00Z", "actor": {"kind":"officer","id":"officer:cos"},
         "lane": "cos", "action": "acted:delegate_work", "subject": "s1",
         "action_type": "officer_dispatch", "outcome": {"status":"unknown"}},
        {"ts": "2026-07-04T10:01:00Z", "actor": {"kind":"officer","id":"officer:cos"},
         "lane": "cos", "action": "queue_draft", "subject": "s2",
         "action_type": "internal_message", "outcome": {"status":"unknown"}},
    ]
    cells = compute_ratios(ledger=ledger)
    assert ("officer:cos", "cos", "officer_dispatch") in cells
    assert ("officer:cos", "cos", "internal_message") in cells
    assert ("officer:cos","cos","officer_dispatch") != ("officer:cos","cos","internal_message")
```

**consequence schema mirror** — `framework/fidelity/consequence.py:82` already
does `_ACTION_TYPES = set(ACTION_TYPES) | {None}` (imported from the classifier),
so the three new enums validate on acted events with NO diff. Guard it:
```python
def test_consequence_action_types_track_classifier():
    from framework.fidelity.consequence import _ACTION_TYPES
    from framework.authority.classifier import ACTION_TYPES
    assert set(ACTION_TYPES) <= _ACTION_TYPES
```

**FIX-6 / FIX-7 re-proof** — `framework/authority/tests/test_matrix_ci.py`
unchanged; re-run to prove no ceiling/prod cell is `auto` and the ceiling still
covers all six `HARD_CEILING_TOUCHES`. Also update these existing
`test_matrix.py` assertions to the new shape:
- `test_floor_covers_all_nine_risk_classes` → **eleven** classes (add
  `pm_write`, `calendar_write` to its `expected`).
- `test_all_verdict_values_in_enum` — passes once `VERDICTS` gains
  `act_with_undo`; the new rows' values are all in-enum.
- `test_non_ceiling_rows_cover_all_confidence_states` — the two new rows cover
  all five states (satisfied).
- `test_no_action_type_mapped_to_two_risk_classes` — `board_status` now in
  `pm_write` only (satisfied).

**calendar template drift guard** — `framework/frontdoor/tests/`
```python
def test_executor_uses_the_single_source_calendar_template():
    import inspect, framework.frontdoor.action_exec as AE
    from framework.frontdoor.calendar_template import CALENDAR_EVENT_SCRIPT
    assert "CALENDAR_EVENT_SCRIPT" in inspect.getsource(AE._exec_calendar_event)
```

**Golden evals** — full suite re-run; `test_golden_evals_a0.py` EVAL anchors are
unaffected (no ceiling/gated behavior changed).

---

## 6 · APPLY-GATE — the M2 evidence pack (all count/state gates)

Do not reply "apply act_with_undo" until every gate below is GREEN. Each is a
count or a state, not a calendar wait (grand plan §3, "Exit — the M2 evidence
pack"). This is the amendment's own admission test.

1. **Live create→undo→ledger round-trip** green: one real `task_create` acted on
   the allowlisted board, `undo` reverses it (Monday item archived, not deleted),
   the acted event + the reversal both land on the ledger.
2. **TTL-survival round-trip** green: an acted step un-undone for 48h supersedes
   to `outcome.status="ok"` with evidence, `review` untouched, and a landed 👍
   is never erased by the TTL event (acted-event lifecycle CI: act→👍→TTL→undo).
3. **Forced canary cycle green PER KIND** — manually triggered synthetic
   create→verify→reverse→verify for `task_create`, `board_status`,
   `calendar_event_create` (journal-only, zero ledger emission). A sequence gate,
   not a weekly wait.
4. **SEC-5 injection-canary suite green** — planted `·pid·`, board-escape,
   human-assignee smuggling, attendee smuggling, delegate-to-unknown-officer,
   exfil URL, planted "approve this card", content-tripwire probes, mention
   smuggling, lesson round-trip, banner-presence — each asserting proposer AND
   executor layers independently.
5. **Veto block + lift round-trip** green: a `never:` on an act-first kind demotes
   that `(actor, lane, action_type)` cell out of `act_with_undo`; `lift` restores.
6. **TOCTOU / key-rejection / killswitch / cap tests** green: payload-sha256
   pin, attendee/assignee/people key rejection, unreachable-Redis halt, per-kind
   and estate day caps all fail-closed.
7. **Acted-event lifecycle CI** green (item 2's superseder-survival suite).
8. **Ratified TI-0 allowlist + per-board attestation sheet** present — the
   cascade-audited board list Nate ratifies (native notifications already ruled
   harmless 2026-07-04; the open item is the audited list itself).
9. **MONDAY_AGENT_TOKEN minted OR explicit waiver** recorded — a scoped agent
   user whose board memberships mirror the allowlist, or a written waiver to run
   propose-only until it exists (never borrow the full-privilege token for
   unattended writes).

**Founder actions the SAME sitting as the apply** (grand plan §6, Moment 2):
- Ratify the cascade-audited board allowlist + per-board native-automation
  attestations (`act-first-surfaces.yml` seed).
- Mint `MONDAY_AGENT_TOKEN` into `~/.screenpipe/pipes/_shared/.env`, or record
  the waiver.
- Acknowledge the label economy: cell-level digest-quieting is fueled ONLY by
  explicit 👍s; TTL survival is a machine outcome and never promotes.

---

## 7 · `captain-decisions.md` supersession note — paste-ready DRAFT

> Add to `shared/interfaces/captain-decisions.md` on apply (CoS or Nate pastes):

```markdown
## GERMLINE APPLIED: trust inversion — act_with_undo (2026-07-04, Captain: "apply act_with_undo")

**What:** Applied docs/proposals/germline-amendment-trust-inversion-2026-07-04.md.
Germline diff across four files: framework/authority/classifier.py (enums
task_create + calendar_event_create + officer_dispatch; full-match Monday create
and byte-match calendar carve-outs above mcp_post/local_edit), matrix.py
(RISK_CLASSES += pm_write, calendar_write; VERDICTS += act_with_undo),
framework/policies/authority-matrix.yml (classes pm_write:[task_create,
board_status] + calendar_write:[calendar_event_create]; board_status MOVED out of
reversible; officer_dispatch into internal_comms; both new classes all-states →
act_with_undo, demote → propose_only), and .claude/rules/courses-of-action.md
(§2 per-step-undo-handle carve-out + §3 acted-steps-are-told wording).

**Supersedes:** docs/proposals/germline-amendment-task-create-2026-07-03.md IN
FULL and its "apply task_create" ruling — task_create now lands in pm_write under
act_with_undo, not in reversible. That proposal is closed by this apply.

**Realizes:** the EARN-DEMOTION posture (this file, 2026-07-03/04) + the
Monday-native-notifications refinement (2026-07-04). Reversible-with-undo cells
start TRUSTED (act_with_undo at every confidence state) and are demoted on
evidence only. The six hard ceilings are byte-identical; Nate still owns all
outbound comms (act-not-draft stands). officer_dispatch is a distinct
internal_comms cell (RT-B4), propose-first (its graduated verdict stays dormant
per the M1 send-lane ruling).

**Gate met before apply:** the M2 evidence pack (create→undo→ledger + TTL-survival
round-trips, per-kind canary cycle, SEC-5 suite, veto block+lift, TOCTOU/cap/
killswitch, acted-event lifecycle) all green; TI-0 allowlist ratified;
MONDAY_AGENT_TOKEN minted / waived. Same-sitting founder actions recorded.

**Rollback:** one revert of the four germline files (pm_write/calendar_write →
propose_only, or the classes removed) + flag off. Journal, receipts, lessons,
canaries all remain useful under propose-first; nothing is destroyed.

**Captain:** Nate. **Reply:** "apply act_with_undo".
```

---

### Appendix — files this amendment touches at apply

| file | change | germline |
|---|---|---|
| `framework/authority/classifier.py` | enums + Monday/calendar carve-outs | yes |
| `framework/authority/matrix.py` | `RISK_CLASSES`, `VERDICTS` frozensets | yes |
| `framework/policies/authority-matrix.yml` | classes + verdict rows + board_status move | yes |
| `.claude/rules/courses-of-action.md` | §2 + §3 edits | yes |
| `framework/frontdoor/calendar_template.py` | NEW leaf constant (extract from executor) | no |
| `framework/frontdoor/action_exec.py` | use `CALENDAR_EVENT_SCRIPT` constant | no |
| `framework/acting/action_lane.py` | none (`ACTION_TYPE_MAP` already staged) | no |
| `framework/fidelity/consequence.py` | none (enum auto-mirrors via import) | no |
| `framework/**/tests/*` | CI proofs (§5) | no |

Reply **"apply act_with_undo"** to apply exactly the above.
