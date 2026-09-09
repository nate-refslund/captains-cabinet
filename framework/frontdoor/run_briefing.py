"""framework.frontdoor.run_briefing — one pass of the recurring unified briefing.

Scheduled by launchd (cabinet/scripts/run-frontdoor-briefing.sh). Pulls real
signals into the durable intake (morning_synthesis) and runs the send path
(run_frontdoor.run_send_path) → ONE unified message to the Captain on the single
channel, replacing the personal-source morning-brief DM that the cutover silenced.

PM augmentation: the wrapper sets ``CABINET_RUN_MODE=PM`` for the evening run
(hour ≥ 17). In PM mode, AFTER the normal synthesis enqueue, we also enqueue the
comprehensive daily recap (framework.frontdoor.daily_recap) — a neutral
synthesis over the get_source() surfaces that folds the long-form recap into
this same unified briefing (its Monday Reflections + vault-note legs were
deleted with egg row R023; boards archived 2026-07-05). The AM run
(CABINET_RUN_MODE unset / "AM") is unchanged. The recap is best-effort: a
failure logs into the result and never blocks the briefing send.

Send-only + gated end-to-end: run_send_path delegates to channel.send, which is
hard-gated on framework.env.allow_sends() (a dev/test session composes but does
NOT send). No reply handling here — the interactive reply→orchestration is the
LLM-Chair capstone.

LOCAL-FIRST genesis receipt (Perfect Cabinet Wave A, Captain 2026-07-09): with
``--local-render`` (or ``run_briefing(local_render=True)``) ONE briefing is
composed from the LOCAL genesis surfaces (framework.onboarding.genesis: the
org-PROPOSED outcome cards, the focus letter, the research-brief status),
written to ``instance/memory/first-briefing-<UTC date>.md`` and printed —
never sent. In this mode the synthesis/recap/digest legs and the Redis intake
are DELIBERATELY not touched: a genesis instance has no LIVE estate to gather
(the DERIVED estate — what the cabinet READ — reaches the cards through
genesis, not through these legs), and a scratch-instance run on a developer
Mac must never consume the LIVE
``cabinet:frontdoor:intake`` consumer-group items (a drain marks them
delivered). The normal path — and the Telegram send through channel.py +
allow_sends — is byte-identical to before and still used when configured.
``--now`` makes the run-immediately contract explicit for wrappers (the module
has no in-code schedule window; launchd owns the cadence).
"""
from __future__ import annotations

import os

from framework import env
from framework.frontdoor import (composer, daily_recap, morning_synthesis,
                                 run_frontdoor, tell_digest)

# Instance-memory layout the frontdoor writes into, declared as a single named
# REL constant — the same convention as framework.onboarding.genesis's
# FIRST_BRIEFING_DIR_REL / LIBRARY_DIR_REL. Keeps the instance-path dependency
# named and greppable in one place rather than scattered Path segments.
_BRIEFINGS_DIR_REL = "instance/memory/briefings"


def _is_pm() -> bool:
    """True when the wrapper flagged this as the evening (PM) run.

    The launchd wrapper sets CABINET_RUN_MODE=PM for hour ≥ 17, else AM. We
    accept any case and treat ONLY an explicit "PM" as PM (default/unset → AM)
    so a missing env never accidentally fires the recap in the morning."""
    return os.environ.get("CABINET_RUN_MODE", "").strip().upper() == "PM"


def _default_digest() -> dict:
    """Production TI-5 digest call: gather the 📈 LOOP readout (per-card-kind
    approve/edit/skip/expired rates + undo-rate trend + latest falsifier-series
    line — lane instrument, 2026-07-05) and enqueue the digest with it.

    Lives HERE, not in tell_digest, because enqueue_digest deliberately never
    auto-gathers the readout (its live-ledger/series reads would make fixtured
    callers non-hermetic — tell_digest.py module header). gather_loop_readout
    never raises (fail-safe: readout absent on error, digest never blocked)."""
    return tell_digest.enqueue_digest(readout=tell_digest.gather_loop_readout())


def _default_needs_you() -> "dict | None":
    """Compose + enqueue the war-room 'Needs you (N)' section from the live
    census. Returns the enqueue receipt, or None when nothing pends (an
    empty shelf renders as silence, not an empty header)."""
    from framework.attention import queue as attention_queue
    from framework.attention import queue_card
    item = queue_card.briefing_needs_you_item(attention_queue.build_queue())
    if item is None:
        return None
    from framework.frontdoor import intake
    return {"needs_you": True, "id": intake.enqueue(item)}


# ---------------------------------------------------------------------------
# Briefing-as-card (ONE-VOICE-RESET, Captain interview 2026-07-11)
#
# When the deployment arms `briefing_card` (instance/config/comms-surface.yml
# or CABINET_BRIEFING_CARD=1 — framework.comms.surface.config), the briefing
# stops sending the composed long body as a (1/N)-chunked Telegram wall:
#
#   * the drain/compose leg still runs UNCHANGED (durable intake, dedup,
#     recover_pending), but its send seam ARCHIVES the composed body to
#     instance/memory/briefings/<UTC stamp>.md — content preserved as DATA
#     (synthesis, PM recap, TI-5 digest text with its undo indexes, every
#     personal-source pipe item). Items are ACKed only after the archive write
#     succeeds (loss-safe: unarchived content stays pending on the stream).
#     The `cabinet:digest:<date>` undo manifest is persisted by the digest
#     leg exactly as before, so `undo <n>` replies keep binding.
#   * ONE briefing card goes out instead (briefing_card.maybe_send → gateway
#     → charter class `briefing` → direct send, edit-in-place per slot):
#     plain headline + "N decisions ready" + the Triage control. Decisions
#     themselves ride the paced single-decision cards, never the briefing.
#   * the "Needs you (N)" intake section is skipped — the same numbers render
#     on the card and the pinned overview (one list, several skins).
#
# The classic text path is byte-identical when the knob is off. The knob is
# ON by default since 2026-07-26 (Captain ratified it 2026-07-11; the value
# had lived only in the instance file the egg deletes) — off is now opt-out.
# ---------------------------------------------------------------------------

def _briefing_card_mode() -> bool:
    """True when briefing-as-card is armed. Fail-closed to the classic text
    path on any config error (a broken knob must not lose the briefing)."""
    try:
        from framework.comms.surface import config as _scfg
        return bool(_scfg.load().get("briefing_card"))
    except Exception:
        return False


def _briefings_dir():
    """The archive home: <repo>/instance/memory/briefings (CABINET_ROOT wins,
    else file-relative — the same root convention the rest of frontdoor uses)."""
    from pathlib import Path
    root = os.environ.get("CABINET_ROOT", "").strip()
    base = Path(root) if root else Path(__file__).resolve().parents[2]
    return base / _BRIEFINGS_DIR_REL


def _archive_briefing_body(text: str) -> str:
    """Write the composed briefing body to a per-run archive file, atomically
    (tmp + os.replace). Returns the path. RAISES on failure — the caller's
    send seam then reports sent=False so the drained items stay PENDING on
    the intake stream (never ACK content that is not durably on disk)."""
    from datetime import datetime, timezone
    d = _briefings_dir()
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    path = d / f"briefing-{stamp}.md"
    body = (f"# Briefing body — {stamp} (archived, not sent)\n\n"
            "This is the data the briefing card summarized. It used to be a "
            "multi-part Telegram message; since 2026-07-11 it lands here and "
            "the card carries the headline.\n\n---\n\n" + text + "\n")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)
    return str(path)


def _archive_send_fn(sink: dict):
    """The card-mode send seam for run_send_path: archive instead of send.
    Mirrors channel.send's calling convention. sent=True ONLY after a
    successful archive write, so ACK semantics stay loss-safe."""
    def _send(text, *, http_post=None):  # http_post ignored — no network here
        try:
            path = _archive_briefing_body(text)
        except Exception as e:  # noqa: BLE001 — report, keep items pending
            return {"status": "error", "sent": False,
                    "error": f"archive failed: {type(e).__name__}: {e}"[:300]}
        sink["archive_path"] = path
        return {"status": "archived", "sent": True, "archive_path": path}
    return _send


def _flatline_notice() -> str:
    """The channel-flatline question for the CARD headline, or "".

    Card mode archives the composed body instead of sending it, so the digest's
    📈 LOOP line — where this question normally rides — never reaches the
    Captain on a card-mode deployment (and the knob is on by default). The
    headline is the one thing that does. ONE engine-minted sentence, no item
    payload text, no marker char; ``tell_digest.flatline_notice`` owns the
    once-per-episode rule and the wording, so the two surfaces cannot drift.
    Fail-open: an alarm must never cost the briefing card."""
    try:
        return tell_digest.flatline_notice()
    except Exception:  # noqa: BLE001
        return ""


#: The update path's three receipts, read back below. `state.json` cannot carry
#: a REFUSAL: a bundle whose diff touches the constitutional set is refused
#: before anything is written and leaves a receipt and nothing else, so the
#: outcome the Captain most needs to hear about is the one outcome the state
#: file has never known about. Registered in framework/events/emitter.py and
#: declared against this module in the cognitive-architecture contract.
_UPDATE_RECEIPT_TYPES = (
    "cabinet_update_applied",
    "cabinet_update_refused",
    "cabinet_update_rolled_back",
)


def _update_receipts(days: int = 30) -> list:
    """Every update receipt in the recent window, oldest first."""
    import datetime as _dt

    from framework.events.emitter import replay

    since = (_dt.datetime.now(_dt.timezone.utc)
             - _dt.timedelta(days=days)).isoformat()
    return replay(since=since, event_types=list(_UPDATE_RECEIPT_TYPES))


# THE REFUSAL RESOLVER, PER BUNDLE, ON EVERY CHANNEL (A5.17).
#
# A verdict about a bundle is written down three times by one call — its own
# marker under `.updates/refusals/`, a ledger receipt, and `state.json` — and
# any one of them can be the only survivor: the state document is REPLACED
# whole by every other writer (including an older updater copy that never knew
# the field), the state write itself can fail, and an install whose emitter
# predates the update path refuses the event kind outright (A5.16). So there is
# ONE resolved refusal and both surfaces consume only that. The card gets it
# from `cabinet-update.sh status --json`; this side resolves it here, because a
# briefing may never hang on a subprocess and `framework/` does not import from
# `cabinet/`. The twin is `update_bundle.resolve_update_surface` and the two are
# pinned against each other, row for row, by the oracle both sides drive.
#
# CURRENCY IS PER BUNDLE, AT ANY LEDGER DEPTH. Round 5 rejected the version
# this replaces because its currency was GLOBAL: it took the newest refusal
# receipt in the window and, when that record named another bundle or no bundle
# at all, threw the rest of the channel away. `refuse_busy` writes exactly such
# a record on every lock contention — `record_refusal "" busy` when a rollback
# loses the lock — so a constitutional verdict on the bundle in the inbox was
# blanked by a note about a moment, and BOTH surfaces then said "an update is
# ready to take — tap Apply" over bytes this box had already turned down.
#
# TWO CLASSES (A5.17.1). A VERDICT is about the bundle's bytes and binds its
# sha until a strictly newer apply or rollback names that sha. A TIMING NOTE
# (`busy`, or any record naming no bundle) is about no bundle at all: it never
# resolves, never supersedes and is never superseded.
#
# TIME IS THE RECORD'S OWN (A5.17.3), never the ledger's insertion time — a
# record held for an older emitter is replayed by the next apply and inserted
# days late, which under insertion order makes a stale refusal newer than the
# update that overtook it. Position in the ledger is not an input at all.
_REFUSAL_FIELDS = ("bundle", "reason", "paths", "ts", "door")
_RECORD_TIME_FIELD = "recorded_at"
_REFUSALS_REL = ".updates/refusals"


def _update_state(base) -> dict:
    """The updater's state document, or {} — the one reader for it here."""
    import json
    try:
        return json.loads((base / ".updates" / "state.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _is_verdict(bundle, reason) -> bool:
    """A verdict is about bytes; `busy` and any empty sha are about a moment."""
    return bool(str(bundle or "")) and str(reason or "") != "busy"


def _refusal_marker(base, bundle: str) -> dict:
    """One bundle's durable verdict, or {}."""
    import json
    if not bundle:
        return {}
    try:
        record = json.loads(
            (base / _REFUSALS_REL / (bundle + ".json")).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return record if isinstance(record, dict) else {}


def _refusal_markers(base) -> list:
    """Every marker on disk. Used only when nothing is waiting."""
    directory = base / _REFUSALS_REL
    records = []
    try:
        names = sorted(p.name for p in directory.iterdir() if p.name.endswith(".json"))
    except Exception:  # noqa: BLE001
        return []
    for name in names:
        record = _refusal_marker(base, name[: -len(".json")])
        if record.get("bundle"):
            records.append(record)
    return records


def _legacy_state_verdict(state: dict) -> dict:
    """The pre-marker state document's verdict — `last_refusal` first, then the
    top-level `phase: refused` copy. Admitted ONLY where there is no marker
    store at all (A5.17.5): an install that refused something before this leg
    existed, and nothing else."""
    record = state.get("last_refusal")
    if isinstance(record, dict) and _is_verdict(record.get("bundle"),
                                                record.get("reason")):
        return dict(record)
    if state.get("phase") == "refused" and _is_verdict(state.get("bundle"),
                                                       state.get("reason")):
        return {field: state.get(field) for field in _REFUSAL_FIELDS}
    return {}


def _record_time(row: dict) -> str:
    """A record's OWN time, with the ledger's insertion stamp as the last
    resort for rows written before that field existed."""
    payload = row.get("payload") or {}
    return str(payload.get(_RECORD_TIME_FIELD) or row.get("created_at") or "")


def _receipt_about(row: dict, bundle: str) -> bool:
    """A5.17.4 — `to_sha` is B, or a ROLLBACK whose `from_sha` is B: the
    updater writes a rollback with `from_sha` = the bundle it undid."""
    payload = row.get("payload") or {}
    if str(payload.get("to_sha") or "") == bundle:
        return True
    return (row.get("event_type") == "cabinet_update_rolled_back"
            and str(payload.get("from_sha") or "") == bundle)


def _receipt_refusal(row: dict) -> dict:
    payload = row.get("payload") or {}
    return {"bundle": str(payload.get("to_sha") or ""),
            "reason": str(payload.get("reason") or ""),
            "paths": [str(entry) for entry in (payload.get("locked_paths") or [])],
            "ts": _record_time(row),
            "door": str(payload.get("door") or "")}


def _state_event(state: dict) -> dict:
    """The state document's OWN last event, when it is an apply or a rollback —
    the second channel such a fact arrives on, and the only one an install
    whose emitter refuses the event kind has at all."""
    phase = str(state.get("phase") or "")
    if phase not in ("applied", "rolled_back"):
        return {}
    return {"kind": phase, "to_sha": str(state.get("to_sha") or ""),
            "from_sha": str(state.get("from_sha") or ""),
            "ts": str(state.get("finished_at") or state.get("ts") or "")}


def _state_event_about(event: dict, bundle: str) -> bool:
    if event.get("to_sha") == bundle:
        return True
    return event.get("kind") == "rolled_back" and event.get("from_sha") == bundle


def _newest(items):
    """Newest wins; ties go to the state channel, then to CONTENT — never to
    position, which is not an input."""
    import json
    return max(items, key=lambda item: (item[0], item[1],
                                        json.dumps(item[2], sort_keys=True)))


def _verdict_candidates(base, state: dict, rows: list, bundle: str = "") -> list:
    """Every verdict about `bundle` (or about anything, when it is empty), as
    `(time, rank, record, source)`. Rank 1 is the state channel."""
    markers = ([record for record in (_refusal_marker(base, bundle),) if record]
               if bundle else _refusal_markers(base))
    out = []
    for record in markers:
        if _is_verdict(record.get("bundle"), record.get("reason")):
            out.append((str(record.get("ts") or ""), 1, dict(record), "state"))
    if not markers and not (base / _REFUSALS_REL).is_dir():
        legacy = _legacy_state_verdict(state)
        if legacy and (not bundle or str(legacy.get("bundle") or "") == bundle):
            out.append((str(legacy.get("ts") or ""), 1, legacy, "state"))
    for row in rows:
        if row.get("event_type") != "cabinet_update_refused":
            continue
        if bundle and not _receipt_about(row, bundle):
            continue
        payload = row.get("payload") or {}
        if _is_verdict(payload.get("to_sha"), payload.get("reason")):
            out.append((_record_time(row), 0, _receipt_refusal(row), "receipt"))
    return out


def _supersede_times(base, state: dict, rows: list, bundle: str = "") -> list:
    """When an apply or a rollback happened, on either channel. A verdict is
    superseded only by one of these that is STRICTLY newer: a relock landing in
    the same second has not proved the bytes acceptable."""
    times = []
    for row in rows:
        if row.get("event_type") == "cabinet_update_refused":
            continue
        if bundle and not _receipt_about(row, bundle):
            continue
        times.append(_record_time(row))
    event = _state_event(state)
    if event and (not bundle or _state_event_about(event, bundle)):
        times.append(event["ts"])
    return [when for when in times if when]


def _resolve_refusal(base, state: dict, rows: list, bundle: str = "") -> tuple:
    """current(B) when a bundle is named (A5.17.5); otherwise the newest
    standing verdict anywhere, and only while it is still the last thing that
    happened (A5.17.6)."""
    candidates = _verdict_candidates(base, state, rows, bundle)
    if not candidates:
        return {}, ""
    when, _rank, record, source = _newest(candidates)
    if any(stop > when for stop in _supersede_times(base, state, rows, bundle)):
        return {}, ""
    return record, source


def _rollback_about(base, state: dict, rows: list, bundle: str) -> dict:
    """The newest record about B, when that record is a rollback FROM B.

    A5.17.7: this box took these bytes, its own health gate went red, and it
    put them back — with the bundle still in the inbox. Not a refusal (Apply
    stays, a retry is legitimate) and not "ready" either."""
    import json
    if not bundle:
        return {}
    facts = [(when, 1, {}) for when, _rank, _rec, _src
             in _verdict_candidates(base, state, rows, bundle)]
    for row in rows:
        if row.get("event_type") == "cabinet_update_refused":
            continue
        if not _receipt_about(row, bundle):
            continue
        payload = row.get("payload") or {}
        rolled = (row.get("event_type") == "cabinet_update_rolled_back"
                  and str(payload.get("from_sha") or "") == bundle)
        facts.append((_record_time(row), 0,
                      {"bundle": bundle, "reason": str(payload.get("reason") or ""),
                       "ts": _record_time(row)} if rolled else {}))
    event = _state_event(state)
    if event and _state_event_about(event, bundle):
        rolled = event["kind"] == "rolled_back" and event["from_sha"] == bundle
        facts.append((event["ts"], 0,
                      {"bundle": bundle, "reason": str(state.get("reason") or ""),
                       "ts": event["ts"]} if rolled else {}))
    if not facts:
        return {}
    return max(facts, key=lambda fact: (fact[0], fact[1],
                                        json.dumps(fact[2], sort_keys=True)))[2]


def _update_resolved_refusal(base, waiting_sha: str = "") -> "tuple[dict, str]":
    """The ONE refusal record this module reads, and the channel it came from.

    Deliberately the same statement as `status --json` makes to the card: the
    verdict standing on the WAITING bundle, or — when nothing waits — the
    newest verdict that nothing has overtaken."""
    state = _update_state(base)
    try:
        rows = _update_receipts()
    except Exception:  # noqa: BLE001
        rows = []
    return _resolve_refusal(base, state, rows, waiting_sha)


# A5.15/A5.17 — THE REFUSAL SPEAKS, AND THE RESOLUTION HAS ALREADY SCOPED IT.
#
# Until 2026-09-08 an update refusal wrote nothing down, so the only way this
# line could learn about one was the ledger — and the ledger is exactly what an
# install cut before the update path existed refuses to write (A5.16). Both
# channels were silent on the same event on the first real apply, and the
# sentence the Captain would have read was "an update is ready to take — tap
# Apply", over a bundle that had already been turned down.
#
# The four rules that grew out of rounds 1-4 (no record; an apply in flight
# outranks it; nothing waiting means it speaks only while it is still the last
# thing that happened; something waiting means it must be a verdict on THOSE
# bytes) are now properties of the RESOLUTION rather than of a reader: the
# resolver is asked about the waiting bundle, so an answer about another bundle
# or about a moment cannot come back. What is left here is the one rule a
# resolution cannot carry — an apply IN FLIGHT is the live state, and a refusal
# recorded before the retry that is running now is a note about a request.
def _refusal_speaks(record: dict, phase: str) -> bool:
    """Does the resolved refusal speak in this state?"""
    if not str((record or {}).get("bundle") or ""):
        return False
    return phase != "applying"


def _update_refusal_line(base, waiting_sha: str = "") -> str:
    record, _source = _update_resolved_refusal(base, waiting_sha)
    phase = str(_update_state(base).get("phase") or "")
    if not _refusal_speaks(record, phase):
        return ""
    bundle = str(record.get("bundle") or "")
    paths = [str(entry) for entry in (record.get("paths") or [])]
    if paths:
        return ("Update refused — %d constitutional file%s; needs the Captain (%s)"
                % (len(paths), " differs" if len(paths) == 1 else "s differ", bundle[:8]))
    return ("Update refused — %s (%s)"
            % (record.get("reason") or "the updater would not take it", bundle[:8]))


def _rollback_line(rollback: dict) -> str:
    """A5.17.7, and IDENTICAL on the card. The round-5 review declared this a
    per-surface difference of shape — the briefing said it, the card said
    "Update ready" and kept Apply — and the A5.17 gate retired that: a bundle
    this box took and put back is not the same fact as a bundle nobody has
    tried, on either door. Apply is kept on both."""
    return ("Update rolled back — %s; still waiting (%s)"
            % (rollback.get("reason") or "it did not come up healthy",
               str(rollback.get("bundle") or "")[:8]))


def _update_notice(root: "str | None" = None) -> str:
    """ONE briefing line about the bytes this Cabinet is running, or "".

    An installed Cabinet is an unpacked export with no version control in it,
    so nothing on the box could ever say "a better version of me is sitting in
    the inbox". The home card says it on the web door; this is the same
    sentence on the door the Captain already reads every day.

    Counts and a short commit only — never a changelog line, which is authored
    text from somewhere else and has no business on a card surface. Reads the
    updater's own files directly rather than shelling to its CLI: this runs
    inside the briefing pass, and a briefing must never be able to hang on a
    subprocess.

    Fail-open in the strong sense: any error, and any install with no updater
    at all, yields "" — an unaskable question is answered with silence, never
    with "you are up to date".

    A REFUSAL LEADS, and an apply in flight leads both (A5.15/A5.17): neither
    may ever read as "ready to take"."""
    import json
    from pathlib import Path

    try:
        base = Path(root or os.environ.get("CABINET_ROOT")
                    or Path(__file__).resolve().parents[2])
        inbox = base / ".updates" / "inbox"
        egg = base / "egg-manifest.json"
        installed = (json.loads(egg.read_text(encoding="utf-8")).get("source_commit") or ""
                     if egg.is_file() else "")
        waiting = []
        for manifest in (sorted(inbox.glob("*.manifest.json")) if inbox.is_dir() else []):
            doc = json.loads(manifest.read_text(encoding="utf-8"))
            sha = doc.get("source_sha") or ""
            if sha and sha != installed and (inbox / (sha + ".tar.gz")).is_file():
                waiting.append((doc.get("built_at") or "", sha, len(doc.get("files") or {})))
        waiting_sha = max(waiting)[1] if waiting else ""
        state = _update_state(base)
        try:
            rows = _update_receipts()
        except Exception:  # noqa: BLE001
            rows = []
        # The refusal leads: the bundle sitting in the inbox is usually the one
        # that was refused, and "ready to take" over it is a sentence that is
        # wrong once per refusal, for ever.
        record, _source = _resolve_refusal(base, state, rows, waiting_sha)
        if _refusal_speaks(record, str(state.get("phase") or "")):
            return _update_refusal_line(base, waiting_sha)
        # A5.16 — a ledger FAULT, which is not the same thing as a ledger one
        # version behind. Both hold the record on disk; only the second is
        # filed by the next update, and round 1 told the Captain that both
        # were. A full disk announced as a version number is a fault nobody
        # ever goes back to look at, so it leads the waiting bundle: the
        # records of what this box did are not being written down.
        fault = str(state.get("ledger_error") or "")
        if fault:
            return ("Update records are not reaching the ledger — ledger fault: %s"
                    % fault)
        # An apply IN FLIGHT is the live state and outranks the bundle in the
        # inbox — that bundle is usually the very one being taken, and "ready
        # to take — tap Apply" over a running apply invites a second one. This
        # arm sat last until 2026-09-09, i.e. after the waiting-bundle arm,
        # which made "An update is being taken right now" unreachable whenever
        # anything was in the inbox: the only time it can be reached is the
        # only time it was not. It stays BELOW the ledger fault because this is
        # a one-line surface and that fault is the sentence nobody goes back to
        # look at; the card, which has room for both, shows the fault beside
        # whatever its headline says.
        if state.get("phase") == "applying":
            return "An update is being taken right now"
        if waiting:
            _, sha, count = max(waiting)
            # A bundle this box already took and PUT BACK is not a bundle
            # nobody has tried. Not a refusal — Apply stays on both surfaces,
            # because retrying a health-gate failure is legitimate — and the
            # sentence is the card's, word for word (A5.17.7).
            rollback = _rollback_about(base, state, rows, sha)
            if rollback:
                return _rollback_line(rollback)
            return ("An update is ready to take (%s, %d files) — open the home page "
                    "and tap Apply" % (sha[:8], count))
        if state.get("phase") == "applied" and state.get("to_sha"):
            return "Updated to %s: %s changes" % (
                str(state["to_sha"])[:8], state.get("changed", 0))
        if state.get("phase") == "rolled_back":
            return ("An update was rolled back: %s"
                    % (state.get("reason") or "it did not come up healthy"))
    except Exception:  # noqa: BLE001
        return ""
    return ""


# A gap of kind `authority` or `information` names a permission nobody here can
# grant itself and a fact nobody here can look up. Both are recorded
# SURFACE-ONLY — never proposed, never DM'd (capability_gaps.py
# STRUCTURAL_KINDS) — so before this line the whole delivery path for them was
# a page the Captain had to think to visit. A3.3: the card says it too.
#
# COUNTS ONLY, never the need text: gap rows are written by whatever hit the
# wall, and the card surface does not carry payload text from elsewhere (the
# same rule `_plain_headline` states for pipe items). The third kind, `skill`,
# is deliberately absent: a missing holder resolves itself the moment a role
# appears and is not something to ask him for.
#
# Fail-open in the strong sense: any error, and any install whose ledger this
# cannot read, yields "" — silence, never "nothing needs you", which is the one
# sentence a surface that cannot count must never produce.
def _gaps_notice() -> str:
    """ONE briefing line about gaps only the Captain can close, or ""."""
    try:
        from framework.learning.capability_gaps import STATUS_OPEN, project_gaps

        authority = 0
        information = 0
        for gap in project_gaps():
            if gap.get("status") != STATUS_OPEN:
                continue
            if gap.get("kind") == "authority":
                authority += 1
            elif gap.get("kind") == "information":
                information += 1
    except Exception:  # noqa: BLE001
        return ""
    if authority and information:
        return ("%d thing%s waiting on a permission only you can give and %d on a "
                "fact only you have — see the gaps page"
                % (authority, " is" if authority == 1 else "s are", information))
    if authority:
        return ("%d thing%s waiting on a permission only you can give — see the "
                "gaps page" % (authority, " is" if authority == 1 else "s are"))
    if information:
        return ("%d thing%s waiting on a fact only you have — see the gaps page"
                % (information, " is" if information == 1 else "s are"))
    return ""


def _plain_headline(gather: dict, digest: "dict | None") -> str:
    """One plain sentence for the card: counts only, NEVER item payload text
    (untrusted pipe content must not ride the card surface — the full body
    lives in the archive file). Honest on an archive failure: content that
    did not land on disk is reported as still queued, not as kept.

    Plus, when it fires, the channel-flatline question (``_flatline_notice``)
    — the one captain-facing line that would otherwise land only in the
    archived body nobody reads."""
    n = int(gather.get("drained") or 0)
    if n and gather.get("sent"):
        head = f"Gathered {n} update{'s' if n != 1 else ''} into today's notes (kept on file)"
    elif n:
        head = (f"Gathered {n} update{'s' if n != 1 else ''} — saving them hit "
                "an error, so they stay queued for the next round")
    else:
        head = "Nothing new to gather this round"
    acted = 0
    if isinstance(digest, dict):
        try:
            acted = int(digest.get("acted") or 0)
        except (TypeError, ValueError):
            acted = 0
    if acted:
        head += (f". {acted} thing{'s were' if acted != 1 else ' was'} done for "
                 f"you — reply `undo <n>` to reverse one")
    head += "."
    notice = _flatline_notice()
    if notice:
        head += f" ⚠️ {notice}"
    update = _update_notice()
    if update:
        head += f" {update}."
    gaps = _gaps_notice()
    if gaps:
        head += f" {gaps}."
    return head


def _default_briefing_card(headline: str) -> dict:
    """Live card send: briefing_card.maybe_send (re-checks the knob, builds
    the live census, rides the gateway/charter like every officer card)."""
    from framework.comms.surface import briefing_card
    return briefing_card.maybe_send(headline)


def _run_local_render(*, genesis_fn=None, now: str | None = None) -> dict:
    """The LOCAL-FIRST genesis receipt: compose ONE briefing from the local
    genesis surfaces and WRITE it — never send, never touch Redis.

    Items come from ``genesis_fn`` (default:
    ``framework.onboarding.genesis.genesis_intake_items`` — the org-PROPOSED
    outcome cards + focus letter + research-brief status, file reads only).
    The composed markdown lands atomically at
    ``<root>/instance/memory/first-briefing-<UTC date>.md`` (root honors
    ``CABINET_ROOT``, so scratch instances are targeted by env). channel.py is
    never called; the result mirrors run_send_path's shape with
    ``sent: False`` + ``local_render: True`` + ``receipt_path``. Honest empty:
    zero genesis items still write the receipt, saying so plainly."""
    from datetime import datetime, timezone

    from framework.onboarding import genesis  # lazy: only the local path needs it

    gather = genesis_fn or genesis.genesis_intake_items
    items = list(gather() or [])
    text = composer.compose(items, max_per_tier=None)  # the first briefing shows ALL cards

    utcnow = datetime.now(timezone.utc)
    date = utcnow.strftime("%Y-%m-%d")
    stamp = now or utcnow.strftime("%Y-%m-%dT%H:%M:%SZ")
    # Path knowledge lives with the genesis surfaces (layer-sep FINAL-C):
    # onboarding owns WHERE the receipt lands; this module composes the text.
    path = genesis.first_briefing_path(date)
    body = (
        f"# First briefing — {date} (LOCAL-FIRST receipt)\n\n"
        f"- composed: {stamp} on this machine, from local genesis surfaces only\n"
        "- sent: no — the Telegram channel engages post-hatch when configured "
        "(channel.py + allow_sends untouched)\n"
        # The receipt says how to ratify, and the answer is the tap — never
        # "open this file and move the row", which no operator can do from a
        # phone and which the tap replaced.
        "- propose-only: every outcome card below is a DRAFT "
        "(captain_ratified: false); " + genesis.RATIFY_HINT + "\n\n"
        + (text if text else
           "(honest empty — no genesis items were staged; run the genesis "
           "proposal step: python3.12 -m framework.onboarding.genesis)")
        + "\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)

    return {
        "synthesis": {"skipped": "local-render (no live estate; the DERIVED "
                                 "estate reaches the cards through genesis)"},
        "recap": None,
        "digest": {"skipped": "local-render"},
        "send": {
            "drained": len(items), "item_ids": [], "text": text,
            "sent": False, "send": None, "acked": 0, "recovered": 0,
            "allow_sends": env.allow_sends(), "local_render": True,
            "receipt_path": str(path),
        },
    }


def run_briefing(
    *,
    hours: int = 72,
    limit: int = 8,
    enqueue_fn=None,
    send_fn=None,
    drain_fn=None,
    ack_fn=None,
    pending_fn=None,
    recap_fn=None,
    digest_fn=None,
    needs_you_fn=None,
    run_mode: str | None = None,
    local_render: bool = False,
    genesis_fn=None,
    card_mode: bool | None = None,
    card_send_fn=None,
) -> dict:
    """Enqueue a fresh synthesis (+ the PM daily recap + the TI-5 digest +
    the war-room "Needs you (N)" section), then run one send pass.

    Returns ``{'synthesis': <enqueue result>, 'recap': <recap result|None>,
    'digest': <tell_digest result>, 'needs_you': <enqueue receipt|None>,
    'send': <run_send_path result>}``.

    PM-only recap: when this is the evening run (``run_mode == 'PM'``, else the
    CABINET_RUN_MODE env), the daily recap is enqueued AFTER the synthesis so it
    rides the same unified briefing. ``recap`` is None on the AM run.

    TI-5 digest (BOTH runs — the twice-daily act-then-tell surface): the
    ACTED/AWAITING/WATCHING/SELF digest is enqueued before the send pass so it
    rides this same unified briefing, and its ``cabinet:digest:<date>`` manifest
    is persisted first so `undo <n>` / `👍 <n>` replies bind the moment the text
    lands (checkpoint 2026-07-04 Tier-0 #6 — the Captain's ruled flip prerequisite;
    plugs the binder no-pid label leak). The default digest also carries the
    📈 LOOP readout (acceptance/undo rates + falsifier series — see
    ``_default_digest``). Best-effort: a digest failure logs into
    the result and never blocks the briefing. Kill-switch CABINET_TELL_DIGEST=0.

    LOCAL-FIRST genesis receipt: ``local_render=True`` short-circuits to
    ``_run_local_render`` — the briefing is composed from the local genesis
    surfaces (``genesis_fn`` seam; default
    framework.onboarding.genesis.genesis_intake_items), written to
    ``instance/memory/first-briefing-<UTC date>.md`` and returned, with the
    synthesis/recap/digest legs and the Redis intake deliberately untouched
    (module docstring has the why). All other seams are ignored in that mode;
    the normal path below is unchanged.

    BRIEFING-AS-CARD (ONE-VOICE-RESET 2026-07-11): when armed (`briefing_card`
    knob; ``card_mode`` seam overrides), the composed body is ARCHIVED (send
    seam → instance/memory/briefings/, ACK only after the write) and ONE
    briefing card goes out via briefing_card.maybe_send. In that mode the
    result's ``send`` leg reports the CARD delivery — its ``sent`` is True
    only when the card reached the Captain (the launchd wrapper's delivered-
    marker grep keys off exactly that), the raw drain/compose receipt moves
    to ``gather`` (with its own ``sent`` key REMOVED so no other "sent": true
    can satisfy the wrapper), and the needs-you enqueue is skipped (the same
    numbers render on the card + the pinned overview). Knob off = the classic
    path below, byte-identical.

    Seams: ``enqueue_fn`` overrides the synthesis enqueue; ``recap_fn`` overrides
    the daily-recap enqueue; ``digest_fn`` overrides the TI-5 digest enqueue;
    ``run_mode`` forces AM/PM; ``send_fn`` / ``drain_fn`` / ``ack_fn`` forward to
    run_send_path; ``card_mode`` / ``card_send_fn`` override the briefing-card
    knob and card transport — all for tests (no real network / Redis / brain).
    The token never appears in the result (channel.send scrubs; run_send_path
    only re-surfaces the scrubbed dict).
    """
    if local_render:
        return _run_local_render(genesis_fn=genesis_fn)

    enqueue = enqueue_fn or morning_synthesis.enqueue_synthesis
    syn = enqueue(hours=hours, limit=limit)

    is_pm = (run_mode.strip().upper() == "PM") if run_mode is not None else _is_pm()
    recap = None
    if is_pm:
        recap_enqueue = recap_fn or daily_recap.enqueue_daily_recap
        try:
            recap = recap_enqueue()
        except Exception as e:  # best-effort: never block the briefing send
            recap = {"recap": False, "error": str(e)[:300]}

    # TI-5: the act-then-tell digest rides BOTH the 07:30 and 19:30 briefings.
    # Enqueued BEFORE the send pass so this run's drain composes it in. The
    # default path (_default_digest) also carries the 📈 LOOP readout; the
    # digest_fn seam is unchanged and takes no readout.
    digest_enqueue = digest_fn or _default_digest
    try:
        digest = digest_enqueue()
    except Exception as e:  # best-effort: never block the briefing send
        digest = {"digest": False, "error": str(e)[:300]}

    # Briefing-as-card? Resolve ONCE per run (seam wins, else the knob).
    as_card = _briefing_card_mode() if card_mode is None else bool(card_mode)

    # War-room census: the "Needs you (N)" briefing section (command-center
    # §4C) — ONE intake item from the same census every skin renders
    # (SURFACE-PARITY), enqueued before the send pass so this run composes
    # it. Silent when nothing pends. ``needs_you_fn`` seam for tests;
    # best-effort — a census failure never blocks the briefing. In card mode
    # it is SKIPPED: the identical numbers render on the briefing card and
    # the pinned overview, so an intake copy would only duplicate the list
    # into the archive.
    needs_you = None
    if as_card:
        needs_you = {"needs_you": False,
                     "skipped": "briefing-card mode — the numbers render on "
                                "the card + the pinned overview"}
    else:
        try:
            enqueue_item = needs_you_fn or _default_needs_you
            needs_you = enqueue_item()
        except Exception as e:
            needs_you = {"needs_you": False, "error": str(e)[:300]}

    # recover_pending=True is the fix for the single-voice comms-awareness gap:
    # surface.py (every 5 min) reads the intake with ">" and surfaces ONLY
    # ping-now in real time, leaving batch/fyi items delivered-but-unacked in the
    # consumer group's PEL "for the briefing to compose". Those items are then no
    # longer ">"-visible, so a plain briefing drain saw nothing and the batch/fyi
    # backlog — comms-officer FYIs, relevant-but-no-reply messages — surfaced
    # NEVER. The briefing is the designated place batch/fyi reaches the Captain, so it
    # recovers that pending backlog, composes it into the one voice, sends, and
    # ACKs. (surface.py is unchanged: still real-time ping-now only.)
    # Card mode: the drain/compose leg keeps running (durable intake, dedup,
    # recover_pending) but its send seam ARCHIVES the body instead of posting
    # a chunked wall. An explicit test-provided send_fn still wins.
    sink: dict = {}
    effective_send_fn = send_fn
    if as_card and effective_send_fn is None:
        effective_send_fn = _archive_send_fn(sink)

    send = run_frontdoor.run_send_path(
        send_fn=effective_send_fn, drain_fn=drain_fn, ack_fn=ack_fn,
        pending_fn=pending_fn, recover_pending=True)

    if not as_card:
        return {"synthesis": syn, "recap": recap, "digest": digest,
                "needs_you": needs_you, "send": send}

    # ONE briefing card (status + "N decisions ready — Triage"). Best-effort:
    # a card failure is reported honestly (sent=False → the wrapper does not
    # stamp a delivered briefing) but never raises.
    try:
        send_card = card_send_fn or _default_briefing_card
        card = send_card(_plain_headline(
            send, digest if isinstance(digest, dict) else None))
    except Exception as e:  # noqa: BLE001
        card = {"status": "error", "sent": False, "error": str(e)[:300]}
    card = card if isinstance(card, dict) else {"status": "invalid", "sent": False}
    # gate.submit (the live tools.send_card spine) returns {decision, result}
    # — the delivery truth is the inner result; a seam-provided flat dict is
    # used as-is. Keep the gate's routing reason when the card did NOT send,
    # so a quiet-routed/suppressed card is diagnosable from the run output.
    card_decision = card.get("decision") if isinstance(card.get("decision"), dict) else {}
    if isinstance(card.get("result"), dict):
        card = card["result"]

    # Honest delivered-marker: in card mode the ONLY "sent" key in the whole
    # result is the CARD's (the gather leg's own sent/send keys are dropped —
    # its outcome is the "archived" fields), so the launchd wrapper's
    # '"sent": true' grep can never be satisfied by the archive leg.
    gather = {k: v for k, v in send.items() if k not in ("sent", "send", "text")}
    return {
        "synthesis": syn, "recap": recap, "digest": digest,
        "needs_you": needs_you,
        "gather": gather,
        "send": {
            "mode": "briefing-card",
            "sent": bool(card.get("sent")),
            "card_status": str(card.get("status") or ""),
            "card_message_ids": list(card.get("message_ids") or []),
            **({} if card.get("sent") else {"card_why": str(
                card.get("error") or card_decision.get("reason") or "")[:200]}),
            "gathered": send.get("drained"),
            "recovered": send.get("recovered"),
            "acked": send.get("acked"),
            "archive_path": sink.get("archive_path"),
        },
    }


def _parse_args(argv=None):
    """CLI flags (additive; a ZERO-ARG invocation — the launchd wrapper's call —
    behaves exactly as before these flags existed).

    --now           run one briefing pass immediately. The module already runs
                    immediately when invoked (launchd owns the cadence; there
                    is no in-code schedule window) — the flag makes that
                    contract explicit for wrappers like first-briefing.sh.
    --local-render  the LOCAL-FIRST genesis receipt: compose from the local
                    genesis surfaces, write instance/memory/
                    first-briefing-<UTC date>.md, print to stdout — never send,
                    never touch Redis (see _run_local_render).
    """
    import argparse
    ap = argparse.ArgumentParser(prog="framework.frontdoor.run_briefing")
    ap.add_argument("--now", action="store_true",
                    help="run one briefing pass immediately (explicit "
                         "run-now contract; bypasses any wrapper scheduling)")
    ap.add_argument("--local-render", action="store_true", dest="local_render",
                    help="compose locally from genesis surfaces and write "
                         "instance/memory/first-briefing-<UTC date>.md instead "
                         "of sending (no Redis, no Telegram)")
    return ap.parse_args(argv)


if __name__ == "__main__":  # pragma: no cover — invoked by the launchd wrapper
    import json
    args = _parse_args()
    out = run_briefing(local_render=args.local_render)
    printable = {
        "synthesis": out["synthesis"],
        "recap": {k: v for k, v in (out["recap"] or {}).items()
                  if k not in ("item", "preview")} if out["recap"] else None,
        "digest": {k: v for k, v in (out["digest"] or {}).items()
                   if k != "manifest"},
        "send": {k: v for k, v in out["send"].items() if k != "text"},
    }
    print(json.dumps(printable, indent=2, default=str))
    if args.local_render:
        # Shell-consumable receipt handle (first-briefing.sh parses this line),
        # then the composed briefing itself — "print to stdout instead of send".
        print(f"FIRST_BRIEFING_RECEIPT={out['send']['receipt_path']}")
        if out["send"]["text"]:
            print("\n--- first briefing (local render, NOT sent) ---\n")
            print(out["send"]["text"])
