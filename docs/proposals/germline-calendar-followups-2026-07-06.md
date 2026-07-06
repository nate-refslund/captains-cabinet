# Germline patch — calendar follow-ups (fast delete reverse + real-sharees gate)

**Date:** 2026-07-06
**Branch:** feat/fidelity-harness-design
**Applies to (GERMLINE — orchestrator applies, officers must not edit):**
- `framework/frontdoor/action_undo.py` — `_inv_calendar_delete` fast-path dispatcher
- `framework/frontdoor/action_exec.py` — `_exec_calendar_event` real-sharees pre-write gate

Both patches are **surgical** (one function body / one inserted block). The
non-germline halves they depend on are ALREADY committed on this branch:
`framework/frontdoor/calendar_delete.py` (fast delete), the `calinfo` /
`assert_calendar_private_for_actfirst` surface in `calendar_read.py`, and the
consolidated helper's `delete` + `calinfo` subcommands.

**CRITICAL — the two patches are ASYMMETRIC; do NOT apply them together blindly
(adversarial-review finding #3):**
- **PATCH 1 degrades gracefully.** With an old / unbuilt / write-only helper the
  fast delete raises → the reverse falls back to the proven AppleScript delete and
  still works. Safe to apply at any time (its VALUE — the sub-second path — is
  unproven until the `uid == calendarItemExternalIdentifier` live round-trip in
  the runbook confirms it; until then it simply falls back).
- **PATCH 2 does NOT degrade gracefully.** The moment it is applied it runs
  `calinfo` on EVERY act-first write. An old helper answers exit 64; a
  rebuilt-but-not-yet-regranted helper answers exit 3 — BOTH → `CalendarShareError`
  → **every act-first calendar write refuses** (a total, fail-closed outage of the
  just-unfrozen feature). So PATCH 2 must be applied **only after** a *verified*
  `bin/cabinet-calread calinfo Home` returns `found:true, writable:true,
  shared:false, shared_signal:none` (exit 0) — NOT merely after "rebuild done".

Recommended: apply the whole wave in the runbook's order, and treat the germline
patches as a single step AFTER the rebuild + re-grant + a green `calinfo Home`.

---

## PATCH 1 — `action_undo._inv_calendar_delete` → fast EventKit delete, AppleScript fallback

Broadens the reverse to try the fast confirmed-only EventKit delete first and
fall through to the proven AppleScript `whose uid is` delete on ANY fast-path
failure (verdict correction: catch `Exception`, not just `CalendarDeleteError`,
so a missing/broken `calendar_delete` module — ImportError — also degrades to the
authoritative path instead of bubbling to `reversal_failed`). `_calendar_delete_script`
is KEPT verbatim as the fallback. `INVERSE_OPS` mapping + `inverse_for` UNCHANGED.

### BEFORE (exact, `framework/frontdoor/action_undo.py`)

```python
def _inv_calendar_delete(args: dict, *, monday_post: Callable = None,
                         osascript: Callable, **_) -> Dict[str, Any]:
    """Reverse a calendar event: delete by UID in the named calendar. Empty
    uid/calendar (a crash row) is a safe no-op."""
    uid = args.get("uid")
    cal = args.get("calendar")
    if not uid or not cal:
        return {"ok": True, "skipped": "no uid/calendar (crash/unexecuted row) — nothing to reverse"}
    res = osascript(["osascript", "-e", _calendar_delete_script(), str(cal), str(uid)])
    if "ok" in (res or ""):
        return {"ok": True, "detail": res}
    return {"ok": False, "error": "calendar delete returned " + repr(res)}
```

### AFTER (exact replacement)

```python
def _inv_calendar_delete(args: dict, *, monday_post: Callable = None,
                         osascript: Callable, **_) -> Dict[str, Any]:
    """Reverse a calendar event: delete by UID in the named calendar. Empty
    uid/calendar (a crash row) is a safe no-op.

    FAST PATH (2026-07-06): try the consolidated signed EventKit helper's
    confirmed-only ``delete`` subcommand first (calendar_delete.delete_event —
    fullAccess BEFORE any lookup, then re-query to CONFIRM removal), which is
    sub-second vs the AppleScript ``whose uid is`` scan's 14-45s. On ANY fast-path
    failure — a CalendarDeleteError (0-match / recurrence / unconfirmed / helper
    exit-3 write-only), a missing/broken module (ImportError), or any unexpected
    exception — fall through to the AUTHORITATIVE AppleScript delete, which keys
    on the SAME uid space the writer stored. delete_event returns ONLY on a
    CONFIRMED delete, so a raise always means 'not confirmed'; re-deleting an
    already-gone event via AppleScript is idempotent ('ok'/'ok:absent'). Success
    is returned only on a confirmed delete from EITHER path; if both fail the
    reverse reports ok:False → reversal_failed → manual_cleanup, never a false
    success (the SAFETY-CRITICAL undo-honesty invariant)."""
    uid = args.get("uid")
    cal = args.get("calendar")
    if not uid or not cal:
        return {"ok": True, "skipped": "no uid/calendar (crash/unexecuted row) — nothing to reverse"}
    try:
        # Lazy import — the reverse module never hard-depends on the fast-path
        # module at load time; an absent/broken calendar_delete degrades here.
        from framework.frontdoor import calendar_delete
        confirmed = calendar_delete.delete_event(str(cal), str(uid), runner=osascript)
        return {"ok": True, "detail": confirmed, "via": "eventkit-fast"}
    except Exception:
        pass  # ANY fast-path failure → the authoritative AppleScript fallback
    res = osascript(["osascript", "-e", _calendar_delete_script(), str(cal), str(uid)])
    if "ok" in (res or ""):
        return {"ok": True, "detail": res}
    return {"ok": False, "error": "calendar delete returned " + repr(res)}
```

### Why fail-closed holds
- Helper absent/not-built / write-only / denied → `delete_event` raises → AppleScript fallback; if AppleScript is ALSO denied it raises → `ok:False` → `reversal_failed` + `manual_cleanup` (loud, artifact stands).
- `uid != calendarItemExternalIdentifier` → helper exits 4 (0-match) → fallback keys on the true stored uid space.
- Recurrence / remove-throw / unconfirmed re-query → helper exits 5/6 → fallback.
- Garbled/empty helper stdout on exit 0 → not `ok:true` → `CalendarDeleteError` → fallback.
- The fast path is the SAME signed full-access helper (not a bare script), so the write-only "lookup returns [] → phantom success" trap cannot fire (fullAccess acquired BEFORE any lookup; confirmed re-query before printing ok).

### Existing test that stays green
`test_calendar_reverse_deletes_by_uid_argv` (its fake osa returns `"ok"` for every
cmd → `json.loads("ok")` fails → `CalendarDeleteError` → falls back to AppleScript,
whose call is what `seen["cmd"]` captures; `"delete ev" in seen["cmd"][2]` and the
uid/cal-as-argv assertions still hold). No change required.

### Co-required NEW tests to ADD with this patch (`framework/frontdoor/tests/test_action_undo.py`)
Runner keyed on cmd[0]/cmd[1] to distinguish the fast helper from AppleScript:

```python
def test_calendar_reverse_fast_path_confirmed(tmp_path, monkeypatch):
    """Fast helper returns confirmation JSON → ok:True via eventkit-fast, and the
    AppleScript delete is NEVER invoked."""
    seen = {"as": 0, "fast": 0}
    def osa(cmd):
        if len(cmd) > 1 and cmd[1] == "delete":     # the fast helper delete
            seen["fast"] += 1
            return '{"ok":true,"deleted":1}'
        seen["as"] += 1                              # AppleScript path
        return "ok"
    _journal_executed("pidcf", 1, "reminder_create", "calendar",
                      created={"uid": "UID-1", "calendar": "Home"})
    res = au.reverse("pidcf", monday_post=lambda *a: {}, osascript=osa, redis_del=_no_op_del)
    assert res["ok"] is True and res["reversed"][0]["step"] == 1
    assert seen["fast"] == 1 and seen["as"] == 0     # AppleScript not used


def test_calendar_reverse_falls_back_to_applescript(tmp_path):
    """Fast helper raises (write-only/denied sim: non-zero exit) → AppleScript
    fallback runs and confirms → ok:True."""
    seen = {}
    def osa(cmd):
        if len(cmd) > 1 and cmd[1] == "delete":
            raise RuntimeError("helper exited 3 (write-only)")
        seen["cmd"] = cmd
        return "ok"
    _journal_executed("pidcb", 1, "reminder_create", "calendar",
                      created={"uid": "UID-2", "calendar": "Home"})
    res = au.reverse("pidcb", monday_post=lambda *a: {}, osascript=osa, redis_del=_no_op_del)
    assert res["ok"] is True
    assert "delete ev" in seen["cmd"][2]             # AppleScript source ran
    assert "UID-2" in seen["cmd"] and "Home" in seen["cmd"]


def test_calendar_reverse_both_paths_fail_is_manual_cleanup(tmp_path):
    """Fast helper raises AND AppleScript returns non-'ok' → ok:False,
    reversal_failed + manual_cleanup, never a false success."""
    def osa(cmd):
        if len(cmd) > 1 and cmd[1] == "delete":
            raise RuntimeError("exit 3")
        return "err:denied"                          # AppleScript automation denied
    _journal_executed("pidbf", 1, "reminder_create", "calendar",
                      created={"uid": "UID-3", "calendar": "Home"})
    res = au.reverse("pidbf", monday_post=lambda *a: {}, osascript=osa, redis_del=_no_op_del)
    assert res["ok"] is False and res.get("manual_cleanup")
```

---

## PATCH 2 — `action_exec._exec_calendar_event` real-sharees pre-write gate (F1)

Inserts an act-first-only call to the positive-allow-list share-scope gate
AFTER the cheap germline name-denylist and BEFORE the `due = ...` parse (so the
name-denylist refuses a literally-named shared calendar before the helper spawns,
the real-signal gate runs next, and the double-book gather stays last). Same
injected `osascript` runner as the gather → one mock seam, fails closed via the
identical propagate path (`CalendarShareError` subclasses `CalendarReadError`).

### BEFORE (exact, `framework/frontdoor/action_exec.py`, the block at ~line 786-789)

```python
    if act_first and cal.strip().lower() in _SHARED_CALENDAR_NAMES:
        raise RuntimeError("act-first calendar writes refuse a shared/subscribed/"
                           "delegated calendar (refusing %r)" % cal)
    due = (payload.get("due_iso") or "").strip()
```

### AFTER (exact replacement)

```python
    if act_first and cal.strip().lower() in _SHARED_CALENDAR_NAMES:
        raise RuntimeError("act-first calendar writes refuse a shared/subscribed/"
                           "delegated calendar (refusing %r)" % cal)
    # [F1 2026-07-06] Real-sharees pre-write gate: after the cheap germline
    # name-denylist (above) and BEFORE the double-book gather, POSITIVELY clear
    # the target calendar as the Captain's own private, un-shared, writable
    # calendar via the signed helper's real EventKit attributes (calinfo). Raises
    # CalendarShareError (a CalendarReadError subclass) on any shared signal /
    # non-writability / duplicate-title ambiguity / allowlist miss / unobtainable
    # or partial report → the act-first card fails closed with NO write (same
    # propagate path as the double-book gather). Same injected osascript runner as
    # the gather + write, so it is one mock-testable seam. The irreducible EventKit
    # blind spot (a writable calDAV calendar shared to others reports
    # shared_signal='none') is covered by CABINET_CAL_PRIVATE + the name-denylist.
    if act_first:
        from framework.frontdoor import calendar_read as _cr
        _cr.assert_calendar_private_for_actfirst(cal, osascript=osascript)
    due = (payload.get("due_iso") or "").strip()
```

### Co-required test updates (`framework/frontdoor/tests/test_action_exec.py`)
ALREADY PRE-STAGED on this branch (inert until this patch lands): the three
act-first calendar osa mocks (`_lands_on_configured_home`, `_refuses_double_book`,
`_failclosed_on_gather_read_error`) now answer `cmd[1]=="calinfo"` with the
module-level `_CLEAN_CALINFO` object, and `test_act_first_calendar_refuses_shared_work`
is left unchanged (it proves the name-denylist refuses "Work" BEFORE calinfo runs).

### Co-required NEW tests to ADD with this patch:

```python
def test_act_first_calendar_refuses_shared_signal(monkeypatch):
    """A calinfo report with a shared signal REFUSES the act-first write (ok=False)
    and the write cmd (ok:...:) is never issued."""
    monkeypatch.delenv("ACTION_LANE_REMINDER_BACKEND", raising=False)
    monkeypatch.setenv("ACTION_LANE_CALENDAR", "Home")
    monkeypatch.setattr(ax, "_load_act_first_surfaces", lambda: _surfaces())
    wrote = {"n": 0}
    def osa(cmd):
        if len(cmd) > 1 and cmd[1] == "calinfo":
            return ('{"calendar":"Home","found":true,"ambiguous":false,'
                    '"writable":true,"shared":true,"shared_signal":"read_only",'
                    '"type":"calDAV"}')
        if len(cmd) > 1 and cmd[1] == "read":
            return "[]"
        wrote["n"] += 1
        return "ok:Home:U1"
    r = ax.deliver_action(
        "pcf1", act_first=True,
        redis_get=_ks_getter([{"kind": "reminder_create",
                               "payload": {"title": "t", "due_iso": "2026-07-06T09:00"}}]),
        monday_post=MondaySpy(), osascript=osa, redis_incr=lambda k, t: None)
    assert r["ok"] is False and wrote["n"] == 0


def test_act_first_calendar_failclosed_on_calinfo_raise(monkeypatch):
    """If the calinfo gate cannot obtain a report (helper raise), the act-first
    write FAILS CLOSED (no write)."""
    monkeypatch.delenv("ACTION_LANE_REMINDER_BACKEND", raising=False)
    monkeypatch.setenv("ACTION_LANE_CALENDAR", "Home")
    monkeypatch.setattr(ax, "_load_act_first_surfaces", lambda: _surfaces())
    def osa(cmd):
        if len(cmd) > 1 and cmd[1] == "calinfo":
            raise RuntimeError("helper exited 3 (write-only)")
        return "ok:Home:U1"
    r = ax.deliver_action(
        "pcf2", act_first=True,
        redis_get=_ks_getter([{"kind": "reminder_create",
                               "payload": {"title": "t", "due_iso": "2026-07-06T09:00"}}]),
        monday_post=MondaySpy(), osascript=osa, redis_incr=lambda k, t: None)
    assert r["ok"] is False
```

---

## Apply order
1. Rebuild the ONE consolidated helper + re-grant Full Access (runbook step 1).
2. **Verify the grant landed**: `bin/cabinet-calread calinfo Home` must return
   `{... "found":true,"writable":true,"shared":false,"shared_signal":"none" ...}`
   (exit 0), and `bin/cabinet-calread probe` must print `fullAccess`. If either
   fails, STOP — applying PATCH 2 now would refuse every calendar write.
3. Apply PATCH 1 + PATCH 2 to the two germline files.
4. Add the co-required NEW tests (both files) and run
   `python3.12 -m pytest framework/frontdoor/tests -q` → expect green.
5. Run the validation_gated live round-trips (runbook steps 3-6), STARTING with
   the `uid == calendarItemExternalIdentifier` create→delete round-trip (review
   finding #6 — the single most load-bearing check; if the fast delete exits 4 it
   is a real finding, not a bug: it means the fast path always falls back).

## Known residual (adversarial-review finding #2 — NOT closed by this wave)
The AppleScript fallback `_calendar_delete_script` returns `"ok"` even when its
`whose uid is` loop matched 0 events, so a reverse whose stored uid no longer
resolves (e.g. iCloud rewrote the event uid after creation) reports success while
the event may still stand. This is **pre-existing** (the shipped reverse already
had it) and **irreducible** for any uid-keyed delete — the real fix is
EventKit-native CREATE so the undo keys on a stable `eventIdentifier` (a larger,
separate germline change). The fast path IS confirm-or-loud (re-query); the
fallback is not. Documented so the wave does not overclaim confirm-or-loud.
