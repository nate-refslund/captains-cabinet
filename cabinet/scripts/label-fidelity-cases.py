#!/usr/bin/env python3.12
"""label-fidelity-cases.py — the Captain's labeling loop for F1-scored
fidelity cases (Design C v0, judge-calibration-pairing-proposal 2026-07-11 §3).

WHY: the judge-calibration flywheel's 0.80-agreement gate could never arm —
the fidelity-case verdict_judge stream (weekly F1 label mine) had NO human-
side writer anywhere in the repo, so collect_pairs() intersected two disjoint
subject sets and returned 0 pairs forever. This CLI is that missing writer:
it presents recently scored cases to the Captain and emits his
confirmed/wrong verdicts as fidelity-case-labeled consequence rows with
subject = case_id — the native pairing key — so every already-banked
verdict_judge scored row becomes pairable retroactively.

WHAT THIS TOOL DOES **NOT** DO (stated in the banner too):
  * It does NOT flip may_demote. judge_verdicts_may_demote() stays fail-
    closed until a fresh >=0.80 proof over >=MIN_PAIRS pairs exists AND the
    gate-arming itself is separately ruled by the Captain (HANDBACK #13).
    This tool only supplies calibration DATA.
  * It does NOT write anything until the Captain interactively answers.
    INERT BY CONSTRUCTION: --dry-run lists the would-be sample and writes
    nothing; interactive mode REFUSES to run when stdin is not a TTY, so no
    cron/agent/pipe can ever mint verdict_human rows through it.

FAILURE-MODE MITIGATIONS (proposal §3, each load-bearing):
  1. Promotion-fuel isolation — label rows ride the DEDICATED lane
     "judge-calibration" (hard-coded in fidelity_events.LABEL_LANE, not a
     flag), so a confirmed label fuels only a cell no acting lane consults.
  2. Anti-anchoring — the judge's verdict and every judge-derived field
     (review.verdict, intent_verdict, decision_verdict, intent_composite,
     outcome.evidence, endorsement) are HIDDEN from the presentation. The
     Captain labels blind; agreement is measured, never manufactured.
  3. Selection bias — the sample is stratified-random over the (hidden)
     judge-verdict strata with proportional allocation, never
     "suspected disagreements only". Presentation order is shuffled so
     ordering leaks nothing either.
  4. Sim exclusion — emit_case_labeled refuses in a sim process; SIE-7
     drops sim rows at read time anyway (belt + braces).

HONEST PRESENTATION LIMIT (v0): the F1 batch does not persist the officer's
decision TEXT (only a chain hash), so for already-banked rows this CLI can
show the case (person/channel/thread tail + the Captain's real historical
reply, rebuilt leak-safe via the retrodiction extractor when available) but
NOT the officer's draft. The prompt says so per case; when the Captain cannot
render a verdict from what is shown, `skip` writes nothing. Persisting
decision text for future batches is a separate follow-up.

Deterministic and OFFLINE: reads only the local consequence ledger (via the
symlink-fenced raw reader) and, best-effort, the local vault through the
retro seam. No LLM, no network, no credentials.

Usage:
  python3.12 cabinet/scripts/label-fidelity-cases.py --dry-run        # inspect
  python3.12 cabinet/scripts/label-fidelity-cases.py                  # label
  python3.12 cabinet/scripts/label-fidelity-cases.py --sample 12 --seed 7
  python3.12 cabinet/scripts/label-fidelity-cases.py --relabel        # allow re-label

After a session, run cabinet/scripts/judge-calibration.py to measure the new
pairs (the daily 05:35 service does it on cadence anyway).

Exit codes: 0 = ok (labels emitted, or dry-run listed, or nothing to do);
            2 = refused (non-TTY interactive) / bad invocation.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Any, Callable, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework import env  # noqa: E402
from framework.fidelity.fidelity_events import (  # noqa: E402
    LABEL_ACTION,
    LABEL_LANE,
    emit_case_labeled,
)
from framework.fidelity.judge_calibration import (  # noqa: E402
    DEFAULT_SINCE,
    MIN_PAIRS,
    iter_raw_rows,
)

SCORED_ACTION = "fidelity-case-scored"
_SCOREABLE = ("confirmed", "wrong")

BANNER = f"""\
================================================================================
 label-fidelity-cases — Captain labels for judge calibration (Design C v0)
--------------------------------------------------------------------------------
 * Writes NOTHING until you answer a case. skip/quit never write.
 * Your verdicts land as consequence rows: action={LABEL_ACTION},
   review.source=verdict_human, lane={LABEL_LANE} (dedicated — promotion-fuel
   isolated), subject=<case_id> (pairs natively with the judge's scored rows).
 * The judge's verdict on each case is HIDDEN (anti-anchoring).
 * may_demote stays False. This tool only supplies calibration data; arming
   the demotion gate is a separate Captain decision (HANDBACK #13) that
   requires >= {MIN_PAIRS} pairs at >= 0.80 agreement AND an explicit ruling.
 * v0 limit: the officer's decision text was not persisted by the F1 batch —
   you see the case + your real historical reply. skip what you cannot judge.
================================================================================
"""

# Judge-derived row fields that must NEVER reach the presentation (anti-
# anchoring, mitigation 2). Kept as a module constant so the test suite pins
# the exact redaction set.
REDACTED_FIELDS = ("review", "outcome", "intent_verdict", "decision_verdict",
                   "intent_composite", "endorsement")


# ---------------------------------------------------------------------------
# candidate collection (read-only)
# ---------------------------------------------------------------------------

def collect_candidates(
    rows: Optional[list[dict[str, Any]]] = None,
    since: Optional[str] = DEFAULT_SINCE,
) -> tuple[list[dict[str, Any]], set]:
    """(candidates, already_labeled_subjects).

    Candidates: the LATEST fidelity-case-scored row per subject carrying a
    scoreable verdict_judge verdict, scored ts >= since. already_labeled:
    subjects that already carry a scoreable verdict_human row (any action) —
    those are excluded from the default sample (pairable already) unless
    --relabel. Rows come sim-filtered + ts-sorted from iter_raw_rows."""
    if rows is None:
        rows = iter_raw_rows()
    scored: dict = {}
    labeled: set = set()
    for ev in rows:
        review = ev.get("review") or {}
        verdict = review.get("verdict")
        source = review.get("source")
        subject = ev.get("subject") or ""
        if not subject or verdict not in _SCOREABLE:
            continue
        if ev.get("action") == SCORED_ACTION and source == "verdict_judge":
            if since is not None and ev.get("ts", "") < since:
                continue
            scored[subject] = ev  # rows are ts-sorted: last wins
        elif source == "verdict_human":
            labeled.add(subject)
    # Deterministic base order (subject-sorted) — the rng does the shuffling.
    return [scored[s] for s in sorted(scored)], labeled


def stratified_sample(candidates: list[dict[str, Any]], n: int,
                      rng: random.Random) -> list[dict[str, Any]]:
    """Stratified-random sample over the (hidden) judge-verdict strata,
    proportional allocation with >=1 per non-empty stratum (largest-remainder
    for the leftovers), then a full shuffle so presentation order reveals
    nothing about strata (mitigations 2+3)."""
    if n <= 0 or n >= len(candidates):
        sample = list(candidates)
        rng.shuffle(sample)
        return sample
    strata: dict = {}
    for row in candidates:
        strata.setdefault((row.get("review") or {}).get("verdict"),
                          []).append(row)
    total = len(candidates)
    names = sorted(strata)  # deterministic iteration under a fixed seed
    quotas = {}
    remainders = []
    used = 0
    for name in names:
        exact = n * len(strata[name]) / total
        q = max(1, int(exact))
        q = min(q, len(strata[name]))
        quotas[name] = q
        used += q
        remainders.append((exact - int(exact), name))
    # Largest-remainder distribution of any leftover slots (or trim overshoot
    # from the biggest stratum — min-1 guarantees can overshoot tiny n).
    remainders.sort(reverse=True)
    i = 0
    while used < n and i < len(remainders) * 2:
        name = remainders[i % len(remainders)][1]
        if quotas[name] < len(strata[name]):
            quotas[name] += 1
            used += 1
        i += 1
    while used > n:
        biggest = max(names, key=lambda s: quotas[s])
        if quotas[biggest] <= 1:
            break
        quotas[biggest] -= 1
        used -= 1
    sample: list[dict[str, Any]] = []
    for name in names:
        sample.extend(rng.sample(strata[name], quotas[name]))
    rng.shuffle(sample)
    return sample


# ---------------------------------------------------------------------------
# presentation (judge verdict hidden)
# ---------------------------------------------------------------------------

def load_case_content(case_ids: list[str]) -> dict:
    """Best-effort {case_id: retro case dict} via the leak-safe retrodiction
    extractor (local vault read only). Absent lib / any failure -> {} and the
    CLI presents ledger metadata only. Never raises."""
    try:
        from framework.fidelity.retro import extract_cases, retro_available
        if not retro_available():
            return {}
        wanted = set(case_ids)
        out = {}
        for rc in extract_cases(n_cases=600):
            cid = rc.get("case_id")
            if cid in wanted:
                out[cid] = rc
        return out
    except Exception:  # noqa: BLE001 — presentation aid only, never fatal
        return {}


def _clip(text: str, n: int) -> str:
    text = (text or "").strip().replace("\r", "")
    return text if len(text) <= n else text[: n - 1] + "…"


def present_case(row: dict[str, Any], content: Optional[dict] = None) -> str:
    """The case as shown to the Captain. MUST NOT contain any judge-derived
    field (REDACTED_FIELDS) — review verdict, intent fields, judge evidence
    and endorsement are all withheld (anti-anchoring, mitigation 2)."""
    actor = row.get("actor") or {}
    lines = [
        f"case      : {row.get('subject')}",
        f"scored on : {(row.get('ts') or '')[:10]}   "
        f"officer: {actor.get('id') or '?'}   lane: {row.get('lane') or '?'}",
    ]
    if content:
        who = content.get("person") or content.get("slug") or "?"
        lines.append(f"person    : {who}   channel: "
                     f"{content.get('channel') or '?'}   "
                     f"cutoff: {(content.get('reply_ts') or '')[:16]}")
        thread = content.get("thread_before") or []
        if thread:
            lines.append("--- thread before cutoff (last 6) ---")
            for m in thread[-6:]:
                sender = env.captain_name() if m.get("direction") == "sent" else (
                    (m.get("who") or "").split("<")[0].strip()
                    or m.get("person") or who)
                lines.append(f"  [{(m.get('date') or '')[:16]}] {sender}: "
                             f"{_clip(m.get('text') or '', 300)}")
        lines.append("--- your ACTUAL reply (historical ground truth) ---")
        lines.append(f"  {_clip(content.get('real_reply') or '', 600)}")
    else:
        lines.append("(case content unavailable — retro extractor absent or "
                     "the case id was not reproduced from the vault)")
    lines.append("--- officer decision text: NOT PERSISTED by the F1 batch "
                 "(v0 limit) ---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# the interactive loop
# ---------------------------------------------------------------------------

PROMPT = ("verdict — did the org's handling of this case deserve your "
          "endorsement?\n  [c]onfirmed / [w]rong / [s]kip / [q]uit > ")


def main(argv: Optional[list] = None,
         input_fn: Callable[[str], str] = input,
         emit_fn: Callable[..., dict] = emit_case_labeled,
         isatty: Optional[bool] = None,
         out=None) -> int:
    out = out or sys.stdout
    ap = argparse.ArgumentParser(
        description="Interactive Captain labeling of F1-scored fidelity "
                    "cases (judge-calibration human-side writer; Design C v0)."
    )
    ap.add_argument("--since", default=DEFAULT_SINCE,
                    help=f"only cases scored at/after this ISO date "
                         f"(default {DEFAULT_SINCE})")
    ap.add_argument("--sample", type=int, default=12,
                    help="stratified-random sample size (default 12; "
                         "0 = all candidates)")
    ap.add_argument("--seed", type=int, default=None,
                    help="RNG seed for a reproducible sample (default: "
                         "nondeterministic)")
    ap.add_argument("--relabel", action="store_true",
                    help="include cases that already carry a human label "
                         "(a new label supersedes on the human side)")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what WOULD be presented; write nothing, "
                         "prompt nothing")
    args = ap.parse_args(argv)

    print(BANNER, file=out)

    candidates, labeled = collect_candidates(since=args.since)
    if not args.relabel:
        candidates = [c for c in candidates if c.get("subject") not in labeled]
    if not candidates:
        print("Nothing to label: no unlabeled fidelity-case-scored rows "
              f"since {args.since}.", file=out)
        return 0

    rng = random.Random(args.seed)
    sample = stratified_sample(candidates, args.sample, rng)
    n_strata = len({(c.get('review') or {}).get('verdict') for c in candidates})
    print(f"{len(candidates)} labelable case(s) since {args.since} "
          f"({len(labeled)} subject(s) already human-labeled"
          f"{', included' if args.relabel else ', excluded'}); "
          f"sampled {len(sample)} across {n_strata} hidden judge-verdict "
          f"stratum/strata.\n", file=out)

    if args.dry_run:
        print("DRY RUN — nothing will be written. Would present:", file=out)
        for i, row in enumerate(sample, 1):
            actor = row.get("actor") or {}
            print(f"  {i:2d}. {row.get('subject')}  "
                  f"scored {(row.get('ts') or '')[:10]}  "
                  f"officer {actor.get('id') or '?'}  "
                  f"lane {row.get('lane') or '?'}", file=out)
        return 0

    if isatty is None:
        isatty = sys.stdin.isatty()
    if not isatty:
        print("REFUSED: stdin is not a TTY. Human labels must come from a "
              "live Captain session — no pipe/cron/agent may mint "
              "verdict_human rows. Use --dry-run to inspect.", file=out)
        return 2

    content_by_id = load_case_content([r.get("subject") for r in sample])
    n_confirmed = n_wrong = n_skipped = 0
    for i, row in enumerate(sample, 1):
        case_id = row.get("subject")
        officer = (row.get("actor") or {}).get("id") or "unknown"
        print(f"\n=== case {i}/{len(sample)} "
              f"{'=' * max(1, 50 - len(str(i)) - len(str(len(sample))))}",
              file=out)
        print(present_case(row, content_by_id.get(case_id)), file=out)
        while True:
            try:
                ans = input_fn(PROMPT).strip().lower()
            except (EOFError, KeyboardInterrupt):
                ans = "q"
            if ans in ("c", "confirmed"):
                emit_fn(case_id, "confirmed", officer)
                n_confirmed += 1
                break
            if ans in ("w", "wrong"):
                emit_fn(case_id, "wrong", officer)
                n_wrong += 1
                break
            if ans in ("s", "skip"):
                n_skipped += 1
                break
            if ans in ("q", "quit"):
                print(_summary(n_confirmed, n_wrong, n_skipped), file=out)
                return 0
            print("  answer c / w / s / q", file=out)

    print(_summary(n_confirmed, n_wrong, n_skipped), file=out)
    return 0


def _summary(n_confirmed: int, n_wrong: int, n_skipped: int) -> str:
    n = n_confirmed + n_wrong
    return (f"\nSession done: {n} label(s) written "
            f"({n_confirmed} confirmed / {n_wrong} wrong), "
            f"{n_skipped} skipped.\n"
            f"Measure pairs: python3.12 cabinet/scripts/judge-calibration.py "
            f"--json --no-write\n"
            f"(may_demote remains False regardless — gate arming is "
            f"HANDBACK #13, Captain-only.)")


if __name__ == "__main__":
    sys.exit(main())
