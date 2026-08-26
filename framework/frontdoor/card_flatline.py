"""framework.frontdoor.card_flatline — the proactive-card CHANNEL-FLATLINE alarm.

WHY THIS EXISTS (Captain-Seat dry run, 2026-07-26 — dry-run finding 2). The
proactive-card channel ran at ~146 cards/week, then emitted ZERO for seven
consecutive days, and NOTHING said so. Briefings kept flowing the whole time,
so from the Captain's seat the org looked alive while one of its two
captain-facing channels was dead. The emission series that recorded the
collapse (``shared/interfaces/falsifier-series.jsonl``) was already being READ
twice a day by the digest — ``proactive_cards_7d`` was parsed and then dropped
on the floor by the renderer. The number was there; no one asked it a question.

THE QUESTION THIS MODULE ASKS, once per silent episode:

    the proactive-card channel has been silent since <date> — deliberate?

and nothing else. It never proposes, never acts, never scores anybody. It
rides correspondence that is already going out (the twice-daily digest's
📈 LOOP section, and the briefing card's headline when the deployment runs in
card mode) — it adds NO send of its own, because an alarm about noise that is
itself noise has already lost the argument.

FOUR NON-ALARMS, each a way a naive detector becomes the thing it was built to
prevent — never-active (a fresh hatch reads zero from birth, and a channel that
never spoke has not gone silent), quiet-org (no cards AND no acts is a dead
fleet, whose finding belongs to the fleet floors, not here), deliberate (a
disabled producer row or a declared absence), and unmeasured (a missing count
is not a zero; a stale series is not a verdict). ``evaluate``'s docstring gives
the state table, ``docs/runbooks/card-flatline-alarm.md`` the operator's view.

ONCE PER EPISODE, WITH NO DURABLE STORE. The verdict is a pure function of the
series plus the CURRENT gates, so there is nothing to carry across a deploy and
nothing that can rot. ``announce`` is true only on the row where the silence
CROSSES ``FLATLINE_MIN_HOURS``; later rows of the same run stay ``flatline``
with ``announce=False`` — still true, already asked. **Recovery is the whole
cooldown:** one row with a card in it ends the run, so the next silence is a new
episode and crosses again. ``ANNOUNCE_FRESH_HOURS`` bounds delivery from the
series date, so a producer that dies right after a crossing row lets the line
age out instead of pinning it on the Captain's screen forever.

The FLEET half is deliberately the opposite:
``cabinet/scripts/card-flatline-probe.py`` prints the same verdict as a doctor
token EVERY run for as long as the channel is dark. That split also covers the
one case the pure function cannot see — a deliberate window ENDING mid-silence
suppresses the one-time line (gates are read as of now, not as of each row),
and the doctor keeps reporting BREACH until cards come back.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-21
ownership-on-GO ruling, on the Captain's GO of 2026-07-27 for the queued
Captain-Seat follow-ups.
"""
from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

#: A channel-silence bar in HOURS, not rows: the series is daily, but a box
#: that slept through a day must not silently shorten the window. 48h is two
#: full series days of zero — long enough that a single quiet weekend day
#: cannot trip it, short enough to beat the seven-day episode that paid for
#: this module.
FLATLINE_MIN_HOURS = 48

#: Beyond this the series itself is the broken thing and no card verdict can
#: be read off it. 3 days = two missed daily runs plus slack.
SERIES_STALE_DAYS = 3

#: How long a CROSSING row stays deliverable to the Captain, measured from the
#: series date at 00:00Z. See the module docstring — this is what keeps a dead
#: producer from pinning the question on his screen.
ANNOUNCE_FRESH_HOURS = 26

#: Fleet-manifest rows whose absence legitimately zeroes this channel.
#: ``framework/acting/run_action_lane.py`` is the ONE writer of
#: ``action == "action-card"`` consequence rows (the number the series counts);
#: the surfaces merely render what it minted.
CARD_PRODUCER_ROWS = ("action-lane",)

#: The exact Captain-facing sentence, in ONE place. Both delivery seams (the
#: digest's LOOP section and the briefing card's headline) call render_line, so
#: the two surfaces cannot describe the same silence two different ways.
LINE_TEMPLATE = ("the proactive-card channel has been silent since {date} "
                 "— deliberate?")

_SERIES_REL = ("shared", "interfaces", "falsifier-series.jsonl")
_SERVICES_REL = ("cabinet", "services.yml")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _repo_root() -> Path:
    """Resolved per call, not at import: launchd, tests and scratch instances
    all retarget via CABINET_ROOT."""
    root = os.environ.get("CABINET_ROOT", "").strip()
    return Path(root) if root else Path(__file__).resolve().parents[2]


def series_path() -> Path:
    """The ONE emission series (``cabinet/scripts/falsifier-report.py``
    SERIES_PATH). Kept here as well as in tell_digest so a caller that has no
    digest in hand still cannot invent a second location.

    ``CABINET_FALSIFIER_SERIES`` retargets it. That knob is why the root
    conftest can point every pytest run at a path inside its session sandbox
    that is never created: an in-test resolve then returns the honest
    "no series" rather than reading — and judging — a live deployment's real
    emission history."""
    explicit = os.environ.get("CABINET_FALSIFIER_SERIES", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    return _repo_root().joinpath(*_SERIES_REL)


def _parse_date(value: Any) -> "dt.date | None":
    s = str(value or "").strip()
    if not _DATE_RE.match(s):
        return None
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def _int_or_none(value: Any) -> "int | None":
    """An honest reading of a counter field. None (missing / null / garbage) is
    UNMEASURED and must never be read as 0 — that conflation is exactly how a
    detector invents a silence that never happened."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _labels_total(row: Dict[str, Any]) -> int:
    labels = row.get("labels_7d")
    if not isinstance(labels, dict):
        return 0
    total = 0
    for key in ("verdict", "outcome_resolved"):
        got = _int_or_none(labels.get(key))
        if got and got > 0:
            total += got
    return total


def _normalize(series: Any) -> List[Dict[str, Any]]:
    """Series rows with a usable date, oldest first, one row per date (the
    producer is idempotent per date, but a hand-appended duplicate must not
    double-count a day). The LAST row for a date wins."""
    by_date: Dict[dt.date, Dict[str, Any]] = {}
    for raw in (series or []):
        if not isinstance(raw, dict):
            continue
        day = _parse_date(raw.get("date"))
        if day is None:
            continue
        row = dict(raw)
        row["_date"] = day
        row["_cards"] = _int_or_none(raw.get("proactive_cards_7d"))
        by_date[day] = row
    return [by_date[d] for d in sorted(by_date)]


def _verdict(state: str, **extra: Any) -> Dict[str, Any]:
    """Every verdict carries the SAME key set, so a consumer's one test is
    ``v["announce"]`` / ``v["state"]`` and never a missing key."""
    out: Dict[str, Any] = {
        "state": state,
        "announce": False,
        "silent_since": None,
        "silent_hours": None,
        "latest_date": None,
        "latest_cards": None,
        "reasons": [],
    }
    out.update(extra)
    return out


def evaluate(series: Any, *, now: "dt.datetime | None" = None,
             gates: "Dict[str, Any] | None" = None) -> Dict[str, Any]:
    """The whole detector: series (+ current gates) → one verdict dict.

    PURE. No file read, no clock beyond ``now``, no import of anything it
    watches — ``series`` and ``gates`` are both injected, so every arm of the
    test suite is a fixture and the production callers pass the live reads.

    ``state`` is one of:

      ``no-series``    nothing has been written yet (a fresh box) — measured
                       absence, never an alarm and never a crash.
      ``stale``        the newest row is older than SERIES_STALE_DAYS; the
                       series producer is the broken thing.
      ``unmeasured``   the newest row carries no ``proactive_cards_7d``.
      ``active``       cards are flowing.
      ``never-active`` zero for the whole series, with no live row before it.
      ``quiet``        silent, but the whole org stopped acting too.
      ``deliberate``   silent, and a gate says so (see ``read_gates``).
      ``silent``       silent and unexplained, but still under the bar.
      ``flatline``     silent, unexplained, over the bar. ``announce`` is True
                       on the crossing row only.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = _normalize(series)
    if not rows:
        return _verdict("no-series")

    latest = rows[-1]
    latest_date = latest["_date"]
    common = {"latest_date": latest_date.isoformat(),
              "latest_cards": latest["_cards"]}

    age_days = (now.date() - latest_date).days
    if age_days > SERIES_STALE_DAYS:
        return _verdict("stale", age_days=age_days, **common)

    if latest["_cards"] is None:
        return _verdict("unmeasured", **common)
    if latest["_cards"] > 0:
        return _verdict("active", **common)

    # The trailing run of ZERO rows. An unmeasured row BREAKS it: silence can
    # only be claimed across days that were actually measured.
    run: List[Dict[str, Any]] = []
    idx = len(rows) - 1
    while idx >= 0 and rows[idx]["_cards"] == 0:
        run.append(rows[idx])
        idx -= 1
    run.reverse()
    baseline = rows[idx] if idx >= 0 else None

    silent_since = run[0]["_date"]
    silent_hours = (latest_date - silent_since).days * 24
    common.update({"silent_since": silent_since.isoformat(),
                   "silent_hours": silent_hours})

    # (1) never-active — the channel was never alive, so nothing went silent.
    if not any(r["_cards"] is not None and r["_cards"] > 0 for r in rows[:idx + 1]):
        return _verdict("never-active", **common)

    # (2) quiet org — no acts, no new stamped rows, no labels across the run.
    if not _org_active(run, baseline, latest):
        return _verdict("quiet", **common)

    # (3) deliberate — a gate explains the silence.
    gates = gates if isinstance(gates, dict) else {}
    reasons = [str(r) for r in (gates.get("reasons") or [])]
    if gates.get("deliberate"):
        return _verdict("deliberate", reasons=reasons, **common)

    if silent_hours < FLATLINE_MIN_HOURS:
        return _verdict("silent", **common)

    # (4) the crossing test — the ONE row per episode that asks the question.
    # ``prev`` is the newest row of this run that is not the latest; the run
    # has at least two rows here, because silent_hours >= 48 needs a span.
    prev_hours = (run[-2]["_date"] - silent_since).days * 24
    crossing = prev_hours < FLATLINE_MIN_HOURS
    fresh_h = (now - dt.datetime.combine(
        latest_date, dt.time(0, 0), tzinfo=dt.timezone.utc)).total_seconds() / 3600.0
    return _verdict("flatline",
                    announce=bool(crossing and 0 <= fresh_h <= ANNOUNCE_FRESH_HOURS),
                    crossing=crossing,
                    announce_age_hours=round(fresh_h, 2),
                    **common)


def _org_active(run: List[Dict[str, Any]], baseline: "Dict[str, Any] | None",
                latest: Dict[str, Any]) -> bool:
    """Did the org keep working while the card channel was dark?

    Three independent signals, any one of which is enough — all of them read
    off the series' OWN fields, so the check costs no extra read and cannot
    drift from what the producer measured:

      * ``stamped_rows_total`` grew since the last live row (new stamped
        consequence rows landed),
      * some run row recorded an act (``acted_7d``),
      * some run row recorded a label (``labels_7d``).

    All three flat ⇒ the fleet stopped, and the card silence is a symptom
    somebody else owns."""
    if baseline is not None:
        base_total = _int_or_none(baseline.get("stamped_rows_total"))
        last_total = _int_or_none(latest.get("stamped_rows_total"))
        if base_total is not None and last_total is not None and last_total > base_total:
            return True
    for row in run:
        acted = _int_or_none(row.get("acted_7d"))
        if acted and acted > 0:
            return True
        if _labels_total(row) > 0:
            return True
    return False


# ---------------------------------------------------------------------------
# the gates — why a zero can be legitimate RIGHT NOW
# ---------------------------------------------------------------------------

def _services_disabled_rows(text: str, names: "tuple[str, ...]") -> List[str]:
    """Names among ``names`` whose fleet row carries ``disabled: true``.

    A deliberately narrow stdlib parse, the same shape the watchdog registry
    and the apoptosis sweep already use on this file: row keys sit at EXACTLY
    four-space indent, and a trailing YAML comment is stripped BEFORE matching
    — rows annotate inline (``disabled: true   # ABSENCE-DISABLE (cos …)``),
    and a parser that misses that reads a parked service as live."""
    found: List[str] = []
    cur: "str | None" = None
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r"^  - name:\s*([A-Za-z0-9._-]+)\s*$", line)
        if m:
            cur = m.group(1)
            continue
        if cur is None or cur not in names:
            continue
        km = re.match(r"^    ([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if km and km.group(1) == "disabled":
            val = km.group(2).split("#", 1)[0].strip().lower()
            if val in ("true", "yes", "1") and cur not in found:
                found.append(cur)
    return found


# Who is being spared the question. The Captain's declared absence is a reason
# not to BOTHER HIM; it was never a reason to stop watching the fleet, and
# until 2026-08-26 it did both — one flag turned the standing fleet check green
# for the whole of an absence, so a failure that began while he was away was
# only discovered on his return. The absence is the worst moment to stop
# looking, which is what made it worth splitting rather than tolerating.
AUDIENCE_CAPTAIN = "captain"
AUDIENCE_FLEET = "fleet"


def read_gates(*, root: "Path | None" = None,
               audience: str = AUDIENCE_CAPTAIN) -> Dict[str, Any]:
    """The reasons this channel is legitimately quiet RIGHT NOW. Never raises.

    Two gates, both about the PRODUCER rather than about the reader: the
    ``action-lane`` fleet row carrying ``disabled: true`` (an ABSENCE-DISABLE
    annotation or a staging park), and the Captain's own declared ``away``.

    THE AUDIENCE DECIDES WHICH ONES SILENCE THE QUESTION.

      ``captain``  both gates. Asking him whether his own declared absence was
                   deliberate is the loud failure this ordering exists to
                   prevent, and it stays prevented.
      ``fleet``    the producer-row gate ALONE. A parked producer is a real
                   reason the channel is quiet; the Captain being away is not —
                   the fleet does not stop working when he stops reading.

    ``reasons`` stays COMPLETE for both. The away reason is still reported to
    the fleet audience, it simply no longer votes: a caller must be able to see
    every fact, and hiding one to change a verdict is how a gate becomes
    unauditable.

    Each reason is independent and best-effort: a gate that cannot be read
    contributes nothing (it does not manufacture an excuse)."""
    root = root or _repo_root()
    reasons: List[str] = []

    try:
        manifest = Path(root).joinpath(*_SERVICES_REL)
        if manifest.exists():
            for name in _services_disabled_rows(
                    manifest.read_text(encoding="utf-8"), CARD_PRODUCER_ROWS):
                reasons.append(f"the {name} fleet row is disabled in "
                               f"cabinet/services.yml")
    except Exception:  # noqa: BLE001 — an unreadable manifest is no excuse
        pass

    # DELIBERATELY NOT A GATE: ``env.allow_sends()``. It reports whether THIS
    # process may send, and this process is the doctor or the briefing — not
    # the action lane that mints the cards. A gate that measures the observer
    # instead of the observed is the sensor failure this whole unit exists to
    # correct, and it would also have parked the alarm permanently green on
    # every box where the probe runs outside the runtime.

    # Everything above this line is a PRODUCER reason: the thing that makes
    # cards is switched off. Those silence the question for everyone.
    producer_reasons = list(reasons)

    try:
        from framework import env as _env
        reading = _env.captain_availability() or {}
        minutes = reading.get("minutes_per_day")
        if reading.get("mode") == "away" or (isinstance(minutes, int) and minutes == 0):
            reasons.append("the captain declared himself away")
    except Exception:  # noqa: BLE001
        pass

    # The return shape does NOT gain an `audience` key. A caller already knows
    # what it asked for, and every existing assertion compares this dict
    # exactly -- widening it would have broken them for no information anyone
    # lacked. Caught by the acceptance criterion rather than by a rerun.
    deciding = producer_reasons if audience == AUDIENCE_FLEET else reasons
    return {"deliberate": bool(deciding), "reasons": reasons}


# ---------------------------------------------------------------------------
# renderers
# ---------------------------------------------------------------------------

def render_line(verdict: "Dict[str, Any] | None") -> str:
    """The Captain-facing sentence, or "" — silence costs nothing.

    Rendered ONLY on ``announce``. Every other state (including a standing
    ``flatline`` whose question was already asked) renders empty, because the
    second copy of a question the Captain has already seen is noise, and noise
    is the thing this alarm exists to detect."""
    if not isinstance(verdict, dict) or not verdict.get("announce"):
        return ""
    since = verdict.get("silent_since")
    if not since:
        return ""
    return LINE_TEMPLATE.format(date=since)


def probe_token(verdict: "Dict[str, Any] | None") -> str:
    """ONE classified token line for cabinet-doctor (the house probe grammar:
    a single word plus inert key=value facts, never prose the doctor has to
    parse). Unlike ``render_line`` this keeps reporting for as long as the
    channel is dark — the fleet-facing half is standing, only the Captain's
    question is once-per-episode."""
    if not isinstance(verdict, dict):
        return "ERROR reason=no-verdict"
    state = str(verdict.get("state") or "")
    since = verdict.get("silent_since")
    hours = verdict.get("silent_hours")
    date = verdict.get("latest_date")
    if state == "no-series":
        return "NOSERIES"
    if state == "stale":
        return f"STALE age_days={verdict.get('age_days')} date={date}"
    if state == "unmeasured":
        return f"UNMEASURED date={date}"
    if state == "active":
        return f"OK cards_7d={verdict.get('latest_cards')} date={date}"
    if state == "never-active":
        return f"NEVERACTIVE date={date}"
    if state == "quiet":
        return f"QUIET since={since} hours={hours}"
    if state == "deliberate":
        why = "; ".join(str(r) for r in (verdict.get("reasons") or [])) or "unstated"
        return f"NOSYNC since={since} why={why}"
    if state == "silent":
        return f"SILENT since={since} hours={hours}"
    if state == "flatline":
        return (f"BREACH since={since} hours={hours} "
                f"announced={1 if verdict.get('announce') else 0}")
    return f"ERROR reason=unknown-state:{state or 'none'}"
