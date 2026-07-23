#!/usr/bin/env python3.12
"""cog3-shadow-dividend.py — the R3 weekly shadow-dividend report (BACKLOG
:1561, COG-4 contract §18 WR lane): a READ-ONLY CLI that turns the shadow
objectives graph into a plain-English weekly report the Captain can feel —
orphans, instrument-vs-outcome divergences, pending human verdicts — proving
the substrate's dividend before any authority flip.

SERVE-SURFACE ONLY (the R1 discipline): every graph byte this report renders
arrives through the PUBLIC serve surface — `serve_graph` / `serve_objective` /
`recommend` (+ the bijective `to_captain_word` table, the ONE Captain
vocabulary — no second drifting enum). The row store is NEVER opened here; the
manifest is read from serve_graph's bound return only. Cortex integrity rides
inside the surface (its one bound loader verifies the sibling store), so a
tampered rows store, a counterfactual manifest, or a mixed-epoch cortex store
raises `ServeRefused` — and this CLI REFUSES LOUDLY (exit 2): no report is
written, the last-report state file is left byte-untouched, and stderr says
why. A missing graph is operator error (exit 3), never a silent empty report.

PURITY (the cog3-staleness idiom, A-m8): `--now` is a DECLARED canonical
timestamp argument — no environment clock read, no env-var read, no network,
no shelling out. Given fixed inputs (cache + state + now), the report bytes
are deterministic (sorted iteration everywhere; no hash-seed dependence).

WHERE THINGS LAND (existing conventions, cited):
  * report → `shared/interfaces/cognitive/shadow-dividend-<date>.md` — beside
    the R1 verdict-inbox artifact on the SAME repo-internal captain-facing
    runtime surface: shared/interfaces/ (.gitignore `shared/interfaces/**/*.md`
    "Shared interface content (populated by officers at runtime)"; precedent:
    governance-review transcripts `shared/interfaces/governance-reviews/*.md`,
    `shared/interfaces/attention-queue.json`, evidence-shadow-findings.jsonl).
    Written atomically (tmp + os.replace — the attention queue.write_artifacts
    idiom). Delivery to phone/World is out of scope here: this produces the
    ARTIFACT on the repo-internal surface only.
  * last-report state → `cabinet/cache/shadow-dividend/state.json` — the
    per-component runtime-cache convention (.gitignore `cabinet/cache/*` +
    `!cabinet/cache/.gitkeep`; precedent: `cabinet/cache/objectives/` =
    cog3-rebuild.py's default graph cache, `cabinet/cache/scheduler/` = the
    COG-4 contract §14.1 scheduler runtime dir). Holds ONLY the last report's
    graph_rows_hash + counts — enough to say what changed, nothing more.

Usage:
    cog3-shadow-dividend.py --now <YYYY-MM-DDTHH:MM:SSZ>
        [--cache DIR] [--out-dir DIR] [--state-dir DIR]

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; R3 rider (Captain GO 2026-07-22/23,
BACKLOG :1561), WR lane of the COG-4 contract §18.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The CLI sits outside the framework/objectives import pin (§6.5 allowlist
# covers cog3-*.py). ONLY the public serve surface + the bijective vocabulary
# table are imported — never graph/model internals, never the cortex directly.
from framework.objectives.query import (  # noqa: E402
    ServeRefused, recommend, serve_graph, serve_objective, to_captain_word)

# Same canonical-timestamp discipline as the serve/build surfaces (mirrored by
# VALUE, the house idiom — the cortex regex is private).
_CANON_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

_DEFAULT_CACHE = _REPO_ROOT / "cabinet" / "cache" / "objectives"
_DEFAULT_OUT = _REPO_ROOT / "shared" / "interfaces" / "cognitive"
_DEFAULT_STATE = _REPO_ROOT / "cabinet" / "cache" / "shadow-dividend"

_STATE_SCHEMA = "shadow-dividend-state/v1"
_STATE_NAME = "state.json"

# Internal state tokens rendered ONLY through to_captain_word (the bijection).
_TESTED = "intervention_supported"
_OBSERVED = "observationally_supported"
_HYPOTHESIZED = "hypothesized"
_REFUTED = "falsified"

# Plain-English glosses for the Captain vocabulary words (display only — the
# words themselves come from the ONE bijective table).
_GLOSS = {
    "tested": "a person confirmed it worked",
    "observed": "the numbers moved as hoped, but no person has confirmed",
    "hypothesized": "still an unproven idea",
    "refuted": "a person said it did not work",
    "unknown": "nothing proven either way yet",
}

_TOP_N = 10


# ===========================================================================
# Serve-surface readings (all graph access lives here)
# ===========================================================================

def _is_edge(record: dict) -> bool:
    return ("edge_id" in record or "relation" in record
            or "source_node_id" in record)


def _slug(subject_key: str) -> str:
    """Render a subject_key for the Captain: drop the `<kind>/` prefix."""
    return subject_key.split("/", 1)[1] if "/" in subject_key else subject_key


def _gather(cache_dir: Path) -> dict:
    """One bound serve pass → everything the report renders. Raises ServeRefused
    on any integrity limb (the caller turns that into the loud refusal) and
    FileNotFoundError when no graph exists at all."""
    served = serve_graph(str(cache_dir))
    records = served["records"]
    manifest = served["manifest"]

    nodes = [r for r in records if not _is_edge(r)]
    edges = [r for r in records if _is_edge(r)]
    causal = [e for e in edges if "state" in e and "target_kind" in e]
    node_by_id = {n["node_id"]: n for n in nodes}

    def _name_of(node_id: str) -> str:
        """A Captain-readable name for a node: an intervention renders as
        "<action> on <subject>" (from its recorded matcher); everything else
        renders its authored slug; a node the graph never named is said so
        honestly — never a raw internal id."""
        node = node_by_id.get(node_id)
        if node is None:
            return "an item the map has no name for"
        matchers = node.get("join_spec")
        if node.get("kind") == "intervention" and matchers:
            first = matchers[0]
            if len(first) >= 3:
                return f"{first[1]} on {first[2]}"
        return _slug(node["subject_key"])

    objectives = sorted((n for n in nodes if n.get("kind") == "objective"),
                        key=lambda n: n["subject_key"])

    # "Priority" ordering — the graph carries NO authored priority field, so the
    # report uses a stated mechanical proxy: how many other objectives lean on
    # this one (depends_on in-degree), ties by name. The report SAYS SO.
    in_degree: dict = {}
    for e in edges:
        if e.get("relation") == "depends_on":
            in_degree[e["target_node_id"]] = in_degree.get(e["target_node_id"], 0) + 1
    ranked = sorted(
        objectives,
        key=lambda n: (-in_degree.get(n["node_id"], 0), n["subject_key"]))

    # Per-objective answers through the per-objective serve surface (state +
    # flags) and the recommendation surface (the effective gate) — both bound.
    top = []
    for node in ranked[:_TOP_N]:
        answer = serve_objective(str(cache_dir), node["subject_key"])
        rec = recommend(str(cache_dir), node["subject_key"])
        top.append({
            "subject_key": node["subject_key"],
            "leaned_on_by": in_degree.get(node["node_id"], 0),
            "word": to_captain_word(answer.state),
            "flags": sorted(answer.flags),
            "effective_allowed": bool(rec.get("effective")),
        })

    causal_by_word: dict = {}
    for e in causal:
        word = to_captain_word(e["state"])
        causal_by_word[word] = causal_by_word.get(word, 0) + 1

    def _edge_line(e: dict) -> str:
        dim = e.get("dimension")
        about = f" (about {dim})" if dim else ""
        return (f"{_name_of(e['source_node_id'])} → "
                f"{_name_of(e['target_node_id'])}{about}")

    tested_edges = sorted(_edge_line(e) for e in causal if e["state"] == _TESTED)
    observed_edges = sorted(_edge_line(e) for e in causal if e["state"] == _OBSERVED)
    refuted_edges = sorted(_edge_line(e) for e in causal if e["state"] == _REFUTED)
    # Awaiting a human verdict = every causal link a person's confirmed/wrong
    # call could still move (the promotion law: human verdicts are the ONLY fuel
    # to "tested"/"refuted") — i.e. everything not already tested or refuted.
    awaiting = sorted(
        (f"{_edge_line(e)} — currently {to_captain_word(e['state'])}"
         + (" — the evidence disagrees with itself"
            if "contested" in (e.get("flags") or []) else "")
         + (" — the numbers moved AGAINST expectation"
            if "direction_contested" in (e.get("flags") or []) else ""))
        for e in causal if e["state"] not in (_TESTED, _REFUTED))

    orphans = sorted(_slug(n["subject_key"]) for n in objectives
                     if "orphaned" in (n.get("flags") or []))

    divergences = []
    for d in manifest.get("divergence_report", []) or []:
        divergences.append({
            "instrument": _name_of(d["instrument_node"]),
            "outcome": _name_of(d["outcome_node"]),
            "dimension": d.get("dimension"),
            "instrument_direction": d["instrument_direction"],
            "outcome_direction": d["outcome_direction"],
        })
    divergences.sort(key=lambda d: (d["instrument"], d["outcome"]))

    cycles = manifest.get("cycles") or []

    return {
        "manifest": manifest,
        "graph_rows_hash": manifest.get("graph_rows_hash"),
        "bound_cutoff": manifest.get("bound_cutoff"),
        "node_count": manifest.get("node_count", len(nodes)),
        "edge_count": manifest.get("edge_count", len(edges)),
        "objective_count": len(objectives),
        "causal_count": len(causal),
        "causal_by_word": causal_by_word,
        "top": top,
        "tested_edges": tested_edges,
        "observed_edges": observed_edges,
        "refuted_edges": refuted_edges,
        "awaiting": awaiting,
        "orphans": orphans,
        "divergences": divergences,
        "cycle_count": len(cycles),
    }


# ===========================================================================
# Last-report state (what changed since)
# ===========================================================================

def _counts_of(g: dict) -> dict:
    return {
        "objectives": g["objective_count"],
        "links": g["causal_count"],
        "tested": g["causal_by_word"].get("tested", 0),
        "observed": g["causal_by_word"].get("observed", 0),
        "refuted": g["causal_by_word"].get("refuted", 0),
        "awaiting_verdict": len(g["awaiting"]),
        "orphans": len(g["orphans"]),
        "divergences": len(g["divergences"]),
    }


def _load_state(state_dir: Path):
    path = state_dir / _STATE_NAME
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None                    # unreadable prior state = honest first report
    return state if isinstance(state, dict) else None


def _atomic_write(path: Path, text: str) -> None:
    """Same-directory tmp + os.replace (the queue.write_artifacts idiom)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _save_state(state_dir: Path, now: str, g: dict) -> None:
    state = {
        "schema": _STATE_SCHEMA,
        "report_date": now,
        "graph_rows_hash": g["graph_rows_hash"],
        "counts": _counts_of(g),
    }
    _atomic_write(state_dir / _STATE_NAME,
                  json.dumps(state, sort_keys=True, indent=2) + "\n")


# ===========================================================================
# R1 cross-reference (the verdict-inbox artifact, if present)
# ===========================================================================

def _find_verdict_inbox(out_dir: Path):
    """The R1 inbox artifact lands on the SAME captain surface (this out_dir).
    Presence is checked by name pattern; a parseable JSON list adds a count;
    anything unreadable degrades to presence-only. Absence is reported honestly
    — never invented."""
    if not out_dir.is_dir():
        return None
    candidates = sorted(p for p in out_dir.iterdir()
                        if p.is_file() and p.name.startswith("verdict-inbox"))
    if not candidates:
        return None
    path = candidates[0]
    count = None
    if path.suffix == ".json":
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            for key in ("items", "pending", "top", "verdicts"):
                if isinstance(doc, dict) and isinstance(doc.get(key), list):
                    count = len(doc[key])
                    break
            if count is None and isinstance(doc, list):
                count = len(doc)
        except (OSError, ValueError):
            count = None
    return {"name": path.name, "count": count}


# ===========================================================================
# The report (Captain register: plain English, no internal jargon)
# ===========================================================================

def _direction_words(direction: str) -> str:
    # the movement vocabulary the build records for a watched subject's head
    return {"increase": "moving up", "decrease": "moving down",
            "maintain": "holding steady"}.get(direction, str(direction))


def _render(now: str, g: dict, prior, inbox) -> str:
    date = now[:10]
    lines: list = []
    add = lines.append

    add(f"# Weekly shadow report — the objectives map ({date})")
    add("")
    add("The objectives map runs in shadow: it watches and learns, and it")
    add("cannot act on its own. This report is what the watching earned this")
    add("week.")
    add("")

    # --- what it believes now ---------------------------------------------
    add("## What the map believes right now")
    add("")
    if g["objective_count"] == 0:
        add("The map is empty — no objectives have been given to it yet.")
    else:
        add(f"It tracks {g['objective_count']} objective(s) and "
            f"{g['causal_count']} cause-and-effect link(s).")
        if g["causal_count"]:
            words = []
            for word in ("tested", "observed", "hypothesized", "refuted", "unknown"):
                n = g["causal_by_word"].get(word, 0)
                if n:
                    words.append(f"{n} {word} ({_GLOSS[word]})")
            add("Of those links: " + "; ".join(words) + ".")
        add("")
        add("Top objectives — ordered by how many other objectives lean on")
        add("each one, because the map has no hand-set priorities yet:")
        add("")
        for i, t in enumerate(g["top"], 1):
            extras = []
            if t["leaned_on_by"]:
                extras.append(f"{t['leaned_on_by']} other objective(s) lean on it")
            if "orphaned" in t["flags"]:
                extras.append("it lost its anchor — see below")
            suffix = f" — {'; '.join(extras)}" if extras else ""
            add(f"{i}. {_slug(t['subject_key'])} — {t['word']} "
                f"({_GLOSS[t['word']]}){suffix}")
    needs = []
    for orphan in g["orphans"]:
        needs.append(f"{orphan} no longer points at any direction you have set "
                     "— the direction it was tied to was edited away. "
                     "Re-anchor it or retire it.")
    if g["cycle_count"]:
        needs.append(f"{g['cycle_count']} loop(s) found where objectives depend "
                     "on each other in a circle — worth untangling.")
    if needs:
        add("")
        add("Needs your attention:")
        for line in needs:
            add(f"- {line}")
    add("")

    # --- what changed ------------------------------------------------------
    add("## What changed since the last report")
    add("")
    if prior is None:
        add("This is the first report — nothing to compare against yet.")
    elif prior.get("graph_rows_hash") == g["graph_rows_hash"]:
        add(f"Nothing has changed since the last report "
            f"({str(prior.get('report_date', ''))[:10]}).")
    else:
        add(f"Since the last report ({str(prior.get('report_date', ''))[:10]}):")
        before = prior.get("counts") or {}
        after = _counts_of(g)
        labels = [("objectives", "objectives"), ("links", "cause-and-effect links"),
                  ("tested", "tested"), ("observed", "observed"),
                  ("refuted", "refuted"), ("awaiting_verdict", "waiting on a verdict"),
                  ("orphans", "objectives without an anchor"),
                  ("divergences", "number-vs-result disagreements")]
        moved = False
        for key, label in labels:
            b, a = before.get(key), after.get(key)
            if isinstance(b, int) and b != a:
                add(f"- {label}: {b} → {a}")
                moved = True
        if not moved:
            add("- the map's content changed, but none of the headline counts "
                "moved.")
    add("")

    # --- divergences -------------------------------------------------------
    add("## Where the numbers and the results disagree")
    add("")
    if g["divergences"]:
        for d in g["divergences"]:
            about = f" (both about {d['dimension']})" if d.get("dimension") else ""
            add(f"- {d['instrument']} is {_direction_words(d['instrument_direction'])} "
                f"while {d['outcome']} is {_direction_words(d['outcome_direction'])}"
                f"{about}. The number we watch is telling a different story than "
                "the result we care about — worth a look.")
    else:
        add("None found — no watched number is telling a different story "
            "than its result.")
    add("")

    # --- recommendations ---------------------------------------------------
    add("## What it would recommend")
    add("")
    add("The map may only say “this worked” where a person confirmed")
    add("the result — it never upgrades anything on its own.")
    add("")
    if g["tested_edges"]:
        add("It stands behind these — confirmed by a person:")
        for line in g["tested_edges"]:
            add(f"- {line}")
    else:
        add("Right now it stands behind nothing — no link has a person's "
            "confirmation yet, so it would surface no “this worked” "
            "recommendation at all.")
    if g["observed_edges"]:
        add("")
        add("Watching, but NOT claiming success yet:")
        for line in g["observed_edges"]:
            add(f"- {line}")
    if g["refuted_edges"]:
        add("")
        add("Confirmed NOT to have worked — stop leaning on these:")
        for line in g["refuted_edges"]:
            add(f"- {line}")
    add("")
    effective_any = (any(t["effective_allowed"] for t in g["top"])
                     if g["top"] else bool(g["tested_edges"]))
    add("(Checked through the map's official recommendation surface: it "
        + ("permits" if effective_any else "refuses")
        + " a “worked” claim right now.)")
    add("")

    # --- awaiting human verdicts ------------------------------------------
    add("## Waiting on a human verdict")
    add("")
    if g["awaiting"]:
        add(f"{len(g['awaiting'])} link(s) can only move when a person says")
        add("“confirmed” or “wrong”:")
        add("")
        for line in g["awaiting"]:
            add(f"- {line}")
    else:
        add("Nothing is waiting on a verdict right now.")
    add("")
    if inbox is not None:
        counted = (f" ({inbox['count']} item(s) ranked there)"
                   if inbox.get("count") is not None else "")
        add(f"Your verdict inbox is beside this report: {inbox['name']}"
            f"{counted} — it ranks which answers unlock the most.")
    else:
        add("The verdict-inbox report is not here yet; until it is, these "
            "items wait in this report.")
    add("")

    # --- the honesty paragraph --------------------------------------------
    add("## What this report cannot claim")
    add("")
    cutoff = str(g.get("bound_cutoff") or "")[:10]
    add("This layer only watches — nothing in it has acted, and nothing")
    add("here proves the map would choose well if it could act. Every state")
    add(f"above was computed when the map was last built (evidence up to "
        f"{cutoff or 'an unrecorded date'}); anything that happened since is "
        "not in here.")
    add("“Observed” means the numbers moved — it does not prove")
    add("the cause, and this report will not pretend it does. Only a person's")
    add("confirmed-or-wrong call ever makes something “tested” or")
    add("“refuted”; no machine judgment is treated as one, and none")
    add("of the counts above manufacture certainty the evidence lacks.")
    add("The ordering of objectives is mechanical (how many things lean on")
    add("each one), not your priorities — the map cannot know those until")
    add("you set them. If anything above looks wrong, the map is wrong: say")
    add("so, and the next build will carry your correction.")
    add("")
    return "\n".join(lines)


# ===========================================================================
# main
# ===========================================================================

def run(now: str, cache: str, out_dir: str, state_dir: str) -> dict:
    cache_dir = Path(cache)
    out_path = Path(out_dir)
    state_path = Path(state_dir)

    g = _gather(cache_dir)                     # may raise ServeRefused (loud, above)
    prior = _load_state(state_path)
    inbox = _find_verdict_inbox(out_path)

    report = _render(now, g, prior, inbox)
    report_file = out_path / f"shadow-dividend-{now[:10]}.md"
    _atomic_write(report_file, report)
    _save_state(state_path, now, g)

    return {
        "report_path": str(report_file),
        "first_report": prior is None,
        "changed": (None if prior is None
                    else prior.get("graph_rows_hash") != g["graph_rows_hash"]),
        "awaiting_verdicts": len(g["awaiting"]),
        "verdict_inbox_present": inbox is not None,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="R3 weekly shadow-dividend report (read-only, serve-surface only)")
    parser.add_argument("--now", required=True,
                        help="declared canonical report timestamp (never a clock read)")
    parser.add_argument("--cache", default=str(_DEFAULT_CACHE),
                        help="objectives cache dir (default cabinet/cache/objectives)")
    parser.add_argument("--out-dir", default=str(_DEFAULT_OUT),
                        help="captain surface dir (default shared/interfaces/cognitive)")
    parser.add_argument("--state-dir", default=str(_DEFAULT_STATE),
                        help="last-report state dir (default cabinet/cache/shadow-dividend)")
    args = parser.parse_args(argv)

    if not _CANON_TS_RE.match(args.now):
        print(f"cog3-shadow-dividend: --now {args.now!r} is not canonical "
              "YYYY-MM-DDTHH:MM:SSZ — refusing to guess the report date",
              file=sys.stderr)
        return 3

    try:
        summary = run(args.now, args.cache, args.out_dir, args.state_dir)
    except ServeRefused as exc:
        # The R1 refusal discipline: a tampered/counterfactual/mixed-epoch graph
        # is REFUSED loudly — no report, no state update, no soft-pedaling.
        print("REFUSED — the objectives map failed its integrity check and "
              f"this report will not pretend otherwise: {exc}", file=sys.stderr)
        print("No report was written; the last-report state was left untouched.",
              file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"cog3-shadow-dividend: no objectives map found under "
              f"{args.cache!r} ({exc}) — build it first with "
              "cog3-rebuild.py; an absent map is operator error, never a blank "
              "report", file=sys.stderr)
        return 3

    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
