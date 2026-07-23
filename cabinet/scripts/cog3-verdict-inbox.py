#!/usr/bin/env python3.12
"""cog3-verdict-inbox.py — R1 THE VERDICT INBOX (masterplan rider, BACKLOG :1559;
phase-4 contract §18 WR lane): a READ-ONLY instrument that finds the pending
claims where ONE human verdict buys the most certainty, ranks them by declared
value-of-information, and writes a plain-English TOP-N verdict-request brief on
the existing captain brief surface.

WHY (fork-2): Captain judgment is the scarcest resource in the org — the graph's
promotion law spends it by DESIGN (states.py: only a human verdict promotes an
edge to intervention_supported or refutes it to falsified; every machine signal
caps at observationally_supported). This instrument points that scarce attention
at the exact edges where it is the ONLY missing input.

READ DISCIPLINE (binding):
  * The objectives graph is read ONLY through the PUBLIC serve surface —
    `framework.objectives.query.serve_graph` — never the raw row store, so
    every C-F15 REFUSE limb guards this instrument too (§5.3/§5.4): a tampered/
    partial row store, a counterfactual manifest, or a mixed-epoch cortex store
    makes the inbox REFUSE LOUDLY (stderr + exit 2) and write NOTHING. Stale or
    unverified advice is never emitted — an absent inbox is honest, a wrong one
    is not.
  * The predictions store (counterfactual.py §4.3) is read ONLY after
    re-deriving its own chained-hash manifest (the same digest dialect the store
    appends with); any mismatch — or a half-present store — REFUSES identically.
  * No clock: `--now` is a DECLARED canonical timestamp (the cog3-staleness.py
    A-m8 idiom); the same inputs always produce byte-identical output.

VALUE-OF-INFORMATION RANKING (declared here AND in the artifact, honestly):
  band 1  state == observationally_supported — the §5.2 P5 ceiling. By
          construction of P5 the edge already holds supporting machine evidence
          AND declared assumptions, and holds NO human verdict (else P2/P3 would
          have fired) — promotion is blocked ONLY by the missing human verdict.
          One yes => intervention_supported; one no => falsified.
  band 2  state == hypothesized + direction_contested flag — the §5.2 P4 demotion:
          machine evidence points AGAINST the claim but machines cannot refute
          (P2 is human-only). A human verdict settles a live disagreement.
  band 3  state == hypothesized, no flags — the §5.2 P6 bare assertion: no
          admissible evidence either way; a human verdict is the first datum.
  Within a band: more OPEN counterfactual forecasts first (each unscored
  prediction on the edge is uncertainty the same verdict resolves), then higher
  target-node degree (how many other graph records reference the edge's target —
  the recommendation-impact proxy this serve surface actually supports), then
  edge_id lexicographic (a fixed total order => deterministic inbox).
  EXCLUDED, honestly: intervention_supported / falsified edges (the human verdict
  already exists), and contested (P1) edges — a new verdict cannot clear a bound
  conflict_set; those owe the Captain cleaner evidence, not a question.

ARTIFACT SURFACE (the repo-conventional captain brief surface — evidence):
  * officers produce briefs to shared/interfaces/research-briefs/
    (cabinet/cron/research-sweep.sh:21) and backlog-refine consumes that dir
    (cabinet/cron/backlog-refine.sh:20);
  * the FW-033 significant-artifact write class pins exactly this dir
    (cabinet/scripts/run-golden-evals.sh EV16, positive example
    research-briefs/2026-04-21.md);
  * shared/interfaces/ is the canonical captain-artifact home
    (framework/frontdoor/veto_registry.py:56) and runtime .md content there is
    deliberately gitignored (.gitignore:173) — briefs are runtime data.
  The inbox therefore writes `shared/interfaces/research-briefs/
  <YYYY-MM-DD>-verdict-inbox.md` (date from --now). No new channel is invented:
  delivery machinery (needs ledger / briefing digest / World) is out of scope —
  this instrument produces the ARTIFACT on the existing surface only.

The artifact body is Captain-register plain English: the bijective Captain
vocabulary (query.to_captain_word — hypothesized/observed/tested/refuted) and no
internal tokens (no state enums, no ids-as-prose, no section signs).

Usage:
    cog3-verdict-inbox.py --now <YYYY-MM-DDTHH:MM:SSZ> [--cache DIR] [--out F]
                          [--top N] [--json]

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; WR rider R1 (BACKLOG :1559 / phase-4
contract §18).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The ONLY substrate imports: the PUBLIC serve surface + the canonical state/flag
# tokens + the recorder digest dialect (for the predictions-manifest re-derive).
# This file is a curated ALLOWLIST_EXACT_OBJECTIVES reader (cog2-import-gate.py).
from framework.objectives import states  # noqa: E402
from framework.objectives.model import digest  # noqa: E402
from framework.objectives.query import (  # noqa: E402
    ServeRefused, serve_graph, to_captain_word)

_DEFAULT_CACHE = _REPO_ROOT / "cabinet" / "cache" / "objectives"
# The existing captain brief surface (evidence in the module docstring) — the
# file name carries the --now date, so one inbox per day, beside dated briefs.
_BRIEF_DIR = _REPO_ROOT / "shared" / "interfaces" / "research-briefs"
_OUT_TEMPLATE = "{date}-verdict-inbox.md"

# Canonical declared-now shape (the graph's own §7.5 cutoff spelling — mirrored
# by VALUE, the same idiom graph.py uses for _CANON_CUTOFF_RE).
_CANON_NOW_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# VOI bands (highest first). Rank values are ORDINAL ONLY — a fixed sort order,
# never a quantity; the artifact declares the same ranking in plain words.
_BAND_ONLY_VERDICT_MISSING = 1     # P5 ceiling: machine-supported, verdict-blocked
_BAND_MACHINE_SAYS_NO = 2          # P4: direction_contested — settle a dispute
_BAND_NO_EVIDENCE_YET = 3          # P6: bare hypothesis — first datum

_EFFECT_PHRASE = {
    "increase": "push {target} up on {dimension}",
    "decrease": "bring {target} down on {dimension}",
    "maintain": "hold {target} steady on {dimension}",
}


class InboxRefused(Exception):
    """The inbox-side REFUSE (predictions-store limbs): same fail-closed shape as
    query.ServeRefused — refuse loudly, write nothing, never stale advice."""


# ===========================================================================
# Verified reads — the serve surface + the chained-hash-bound predictions store
# ===========================================================================

def _load_predictions_verified(cache_dir):
    """Read predictions/predictions.jsonl ONLY after re-deriving its own chained-
    hash manifest (counterfactual.py:_write_predictions_manifest writes both on
    EVERY append, so store-without-manifest — or the reverse — is tampered shape,
    and a chain/count mismatch is a tampered store). Both-absent == honestly
    empty (nothing minted yet). Raises InboxRefused, never serves unverified."""
    pdir = Path(cache_dir) / "predictions"
    store = pdir / "predictions.jsonl"
    manifest_path = pdir / "predictions-manifest.json"
    if not store.exists() and not manifest_path.exists():
        return []
    if not (store.exists() and manifest_path.exists()):
        raise InboxRefused(
            "predictions store is half-present (store XOR manifest) — the append "
            "path writes both on every mint/accuracy append, so this shape is "
            "tampered; refusing to rank against it")
    rows = []
    chain = ""
    for line in store.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows.append(row)
        chain = digest([chain, row])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (not isinstance(manifest, dict)
            or manifest.get("chained_hash") != chain
            or manifest.get("prediction_count") != len(rows)):
        raise InboxRefused(
            "predictions store failed its chained-hash re-derivation (manifest "
            "chained_hash/prediction_count vs the rows on disk) — tampered or "
            "partial store; refusing to rank against it")
    return rows


def _open_forecast_counts(prediction_rows):
    """edge_id -> count of UNSCORED predictions (a prediction record with no
    accuracy record naming its prediction_id). Untrusted fields are used for
    string-equality matching only."""
    scored = {row.get("prediction_id") for row in prediction_rows
              if row.get("record_kind") == "accuracy"}
    counts: dict = {}
    for row in prediction_rows:
        if row.get("record_kind") != "prediction":
            continue
        if row.get("prediction_id") in scored:
            continue
        edge_id = row.get("edge_id")
        if isinstance(edge_id, str):
            counts[edge_id] = counts.get(edge_id, 0) + 1
    return counts


# ===========================================================================
# Candidate assembly + the declared VOI order
# ===========================================================================

def _is_edge(record) -> bool:
    return ("edge_id" in record or "relation" in record
            or "source_node_id" in record)


def _band_of(record):
    """The VOI band of one served causal edge, or None when no human verdict is
    being requested (already-ruled or contested — see the module docstring)."""
    state = record.get("state")
    flags = set(record.get("flags") or [])
    if state in (states.STATE_INTERVENTION_SUPPORTED, states.STATE_FALSIFIED):
        return None                               # the human verdict already exists
    if states.FLAG_CONTESTED in flags:
        return None                               # a verdict cannot clear P1
    if state == states.STATE_OBSERVATIONALLY_SUPPORTED:
        return _BAND_ONLY_VERDICT_MISSING
    if state == states.STATE_HYPOTHESIZED:
        if states.FLAG_DIRECTION_CONTESTED in flags:
            return _BAND_MACHINE_SAYS_NO
        return _BAND_NO_EVIDENCE_YET
    return None                                   # unknown is never stored on edges


def _plain_label(subject_key):
    """A Captain-readable label from a node subject_key: drop a known kind
    prefix, read hyphens as spaces; anything else stays verbatim (work-item
    handles like tasks/101 ARE the Captain's own references)."""
    if not isinstance(subject_key, str) or not subject_key:
        return "(unnamed)"
    prefix, _, rest = subject_key.partition("/")
    if rest and prefix in {"outcome", "objective", "instrument", "direction",
                           "constraint", "intervention"}:
        return rest.replace("-", " ")
    return subject_key


def gather_candidates(served, prediction_rows):
    """Every causal edge still waiting on a human verdict, in DECLARED VOI order
    (see module docstring — band, then open forecasts, then target degree, then
    edge_id). Pure function of the served records + verified prediction rows."""
    records = served["records"]
    label_by_node = {r.get("node_id"): r.get("subject_key")
                     for r in records if not _is_edge(r) and "node_id" in r}
    forecasts = _open_forecast_counts(prediction_rows)

    causal = [r for r in records
              if _is_edge(r) and "state" in r and "target_kind" in r]

    candidates = []
    for record in causal:
        band = _band_of(record)
        if band is None:
            continue
        edge_id = record.get("edge_id", "")
        target_node = record.get("target_node_id")
        degree = 0
        for other in records:
            if not _is_edge(other) or other.get("edge_id", "") == edge_id:
                continue
            if target_node in (other.get("source_node_id"),
                               other.get("target_node_id")):
                degree += 1
        candidates.append({
            "edge_id": edge_id,
            "band": band,
            "state": record.get("state"),
            "captain_state": to_captain_word(record.get("state")),
            "flags": sorted(record.get("flags") or []),
            "open_forecasts": forecasts.get(edge_id, 0),
            "target_degree": degree,
            "source": _plain_label(label_by_node.get(record.get("source_node_id"))),
            "target": _plain_label(label_by_node.get(target_node)),
            "dimension": record.get("dimension"),
            "expected_effect": record.get("expected_effect"),
        })
    candidates.sort(key=lambda c: (c["band"], -c["open_forecasts"],
                                   -c["target_degree"], c["edge_id"]))
    return candidates


def _contested_count(served) -> int:
    return sum(1 for r in served["records"]
               if _is_edge(r) and "state" in r and "target_kind" in r
               and states.FLAG_CONTESTED in set(r.get("flags") or []))


# ===========================================================================
# The Captain-register artifact
# ===========================================================================

def _question_line(candidate) -> str:
    effect = candidate.get("expected_effect")
    phrase = _EFFECT_PHRASE.get(effect, "move {target} as intended on {dimension}")
    did = phrase.format(target=f"“{candidate['target']}”",
                        dimension=candidate.get("dimension") or "the stated measure")
    return f"Did “{candidate['source']}” actually {did}? — yes or no."

# The Captain words for the two verdict outcomes come from the ONE bijective
# vocabulary (query.to_captain_word), so this artifact can never drift from it.
_WORD_TESTED = to_captain_word(states.STATE_INTERVENTION_SUPPORTED)
_WORD_REFUTED = to_captain_word(states.STATE_FALSIFIED)
_WORD_OBSERVED = to_captain_word(states.STATE_OBSERVATIONALLY_SUPPORTED)
_WORD_HYPOTHESIZED = to_captain_word(states.STATE_HYPOTHESIZED)

_BAND_STANDING = {
    _BAND_ONLY_VERDICT_MISSING: (
        "every check the cabinet can run on its own has already passed — "
        "this claim is marked **{observed}**. Your call is the only missing "
        "input."),
    _BAND_MACHINE_SAYS_NO: (
        "the machine evidence currently points the WRONG way, so the claim is "
        "held back as **{hypothesized}**. Your call settles a live "
        "disagreement — the cabinet cannot settle it alone."),
    _BAND_NO_EVIDENCE_YET: (
        "no usable evidence either way yet — the claim is "
        "**{hypothesized}**. Your verdict would be its first real test."),
}

_BAND_YES = {
    _BAND_ONLY_VERDICT_MISSING: (
        "the claim is promoted to **{tested}** — the strongest standing a "
        "claim can earn — and recommendations may rely on it as proven."),
    _BAND_MACHINE_SAYS_NO: (
        "the claim becomes **{tested}** — your judgment outranks the "
        "machine reading — provided its stated assumptions are on record."),
    _BAND_NO_EVIDENCE_YET: (
        "the claim becomes **{tested}**, provided its stated assumptions are on "
        "record; if they are missing it stays {hypothesized}, and we learn the "
        "assumptions were the real blocker."),
}


def render_artifact(candidates, *, now, top, cutoff, contested) -> str:
    """The plain-English verdict-request brief. Deterministic: a pure function
    of (candidates, now, top, cutoff, contested)."""
    date = now.split("T", 1)[0]
    shown = candidates[:top]
    open_total = sum(c["open_forecasts"] for c in candidates)

    lines = [f"# Verdict inbox — {date}", ""]
    if not shown:
        lines += [
            "Nothing needs your verdict right now — every claim the "
            "cabinet tracks is either already ruled on or still gathering "
            "machine evidence.", ""]
    else:
        lines += [
            f"The {len(shown)} call{'s' if len(shown) != 1 else ''} below buy "
            "the most certainty per minute of your attention, best first. Each "
            "is one yes-or-no.", ""]
    for i, c in enumerate(shown, 1):
        fmt = {"observed": _WORD_OBSERVED, "hypothesized": _WORD_HYPOTHESIZED,
               "tested": _WORD_TESTED, "refuted": _WORD_REFUTED}
        title_dim = f" ({c['dimension']})" if c.get("dimension") else ""
        lines.append(f"## {i}. “{c['source']}” → "
                     f"“{c['target']}”{title_dim}")
        lines.append("")
        lines.append(f"- **Look at:** the work item “{c['source']}” "
                     f"and whether “{c['target']}” really moved.")
        lines.append(f"- **The question:** {_question_line(c)}")
        lines.append(f"- **Where it stands:** "
                     f"{_BAND_STANDING[c['band']].format(**fmt)}")
        lines.append(f"- **A yes:** recorded against this work item, "
                     f"{_BAND_YES[c['band']].format(**fmt)}")
        lines.append(f"- **A no:** the claim is marked **{_WORD_REFUTED}** and "
                     "stops counting in the cabinet's favor.")
        if c["open_forecasts"]:
            n = c["open_forecasts"]
            lines.append(f"- **Also riding on this:** {n} open "
                         f"forecast{'s' if n != 1 else ''} the same verdict "
                         "settles.")
        lines.append("")

    lines += [
        "## How these were chosen", "",
        "Every claim still waiting on a human call is ranked, most valuable "
        "first:", "",
        "1. claims where every machine check has already passed and ONLY your "
        "confirmation is missing — one answer finishes them;",
        "2. claims where the machine evidence currently points the wrong way "
        "— one answer settles a live disagreement;",
        "3. claims with no evidence at all yet — your answer is the first "
        "data point.", "",
        "Ties break toward the claim with more open forecasts riding on it, "
        "then the outcome more of the plan hangs off, then a fixed alphabetical "
        "order — so the same facts always produce the same inbox.", "",
        "Not shown: claims you have already ruled on (" + _WORD_TESTED + " or "
        + _WORD_REFUTED + "), and claims whose own evidence is internally "
        "contested — those owe you cleaner evidence from the cabinet, not "
        "a question.", "",
    ]
    waiting = len(candidates)
    tail = (f"Built from the cabinet's knowledge as of {cutoff} · "
            f"inbox generated at {now} · {waiting} claim"
            f"{'s' if waiting != 1 else ''} awaiting a human call "
            f"({len(shown)} shown)")
    if contested:
        tail += (f" · {contested} contested claim"
                 f"{'s' if contested != 1 else ''} excluded — evidence "
                 "cleanup owed by the cabinet")
    if open_total:
        tail += (f" · {open_total} open forecast"
                 f"{'s' if open_total != 1 else ''} riding on claims awaiting "
                 "a call")
    lines += [tail, ""]
    return "\n".join(lines)


# ===========================================================================
# CLI
# ===========================================================================

def run(cache: str, now: str, out, top: int):
    """Serve (REFUSE-guarded) -> verify predictions -> rank -> write. Returns the
    result dict; raises ServeRefused/InboxRefused BEFORE any write."""
    served = serve_graph(cache)                       # the ONE public read path
    prediction_rows = _load_predictions_verified(cache)
    candidates = gather_candidates(served, prediction_rows)
    contested = _contested_count(served)
    cutoff = served["epoch"].get("cutoff") or served["manifest"].get("bound_cutoff")
    artifact = render_artifact(candidates, now=now, top=top, cutoff=cutoff,
                               contested=contested)
    out_path = Path(out) if out else _BRIEF_DIR / _OUT_TEMPLATE.format(
        date=now.split("T", 1)[0])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(artifact, encoding="utf-8")
    return {"generated_at": now, "cache": str(cache), "artifact": str(out_path),
            "cutoff": cutoff, "shown": min(top, len(candidates)),
            "awaiting_total": len(candidates), "contested_excluded": contested,
            "candidates": candidates}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="R1 verdict inbox — VOI-ranked top-N verdict requests")
    parser.add_argument("--cache", default=str(_DEFAULT_CACHE),
                        help="objectives cache dir (graph served, never raw-read)")
    parser.add_argument("--now", required=True,
                        help="declared canonical timestamp YYYY-MM-DDTHH:MM:SSZ "
                             "(never a clock read)")
    parser.add_argument("--out", default=None,
                        help="artifact path (default: the dated brief on "
                             "shared/interfaces/research-briefs/)")
    parser.add_argument("--top", type=int, default=3,
                        help="how many requests the brief carries (default 3)")
    parser.add_argument("--json", action="store_true",
                        help="print the machine-readable ranking as JSON")
    args = parser.parse_args(argv)

    if not _CANON_NOW_RE.match(args.now):
        print(f"cog3-verdict-inbox: non-canonical --now {args.now!r} "
              "(want YYYY-MM-DDTHH:MM:SSZ) — refusing", file=sys.stderr)
        return 2
    if args.top < 1:
        print("cog3-verdict-inbox: --top must be >= 1", file=sys.stderr)
        return 2
    try:
        result = run(args.cache, args.now, args.out, args.top)
    except (ServeRefused, InboxRefused) as exc:
        # REFUSE loudly, write NOTHING: a tampered/counterfactual/mixed-epoch
        # store (or predictions store) must never become captain-facing advice.
        print(f"cog3-verdict-inbox: REFUSED — {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"cog3-verdict-inbox: no built graph at {args.cache!r} "
              f"({exc}) — run cog3-rebuild.py first", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
