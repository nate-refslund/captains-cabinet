#!/usr/bin/env python3.12
"""VISION JUDGE orchestrator — pairwise protocol in code, judgment via agents.

`build` takes candidate frame(s) and emits a RUN BUNDLE for an LLM runner
(the cabinet pattern: the protocol is code, the judgment happens in agents at
call time):

    runs/<run_id>/tasks.json   runner-facing task list: blinded image pairs +
                               the rubric + answer contract. NO ground truth.
    runs/<run_id>/images/      opaque-named copies of every frame in play
                               (corpus bytes sha256-verified against the
                               tracked manifest before staging).
    runs/<run_id>/key.json     the answer key (kinds, sides, identities).
                               The runner must never read it.
    runs/<run_id>/run.json     params, seed, corpus provenance, counts.

Pair construction: candidate vs sampled corpus positives, candidate vs
sampled corpus negatives, plus the HIDDEN calibration set (every corpus
positive x negative — see calibration.py). Left/right is randomized per pair
(seeded RNG, reproducibility not cryptography) to kill position bias, and
all tasks are shuffled together so calibration pairs are indistinguishable
from candidate pairs. Every pair asks the same question:

    "Which reads more like a finished, warm, professional pixel-game scene
     — LEFT or RIGHT, and why in one line?"

`ingest` reads the filled results and computes verdicts:

    calibration gate   accuracy >= 0.90 on the hidden set, else the run is
                       VOID (stamped, exit 1) — the D5 move: an uncalibrated
                       judge's candidate answers are noise, not signal.
    win-rate vs negatives   sanity floor — must be ~1.0 (default floor 1.0:
                       losing even once to a Captain-rejected frame
                       disqualifies; --neg-floor for larger corpora).
    win-rate vs positives   the real signal — the candidate's standing
                       against the approved bar.
    verdict            reject   below the negative floor
                       promote  at/above --promote-bar (default 0.5) vs
                                positives
                       iterate  clears negatives but not yet the bar
    notes              every one-line "why" from losses (and wins vs
                       positives) collected per candidate — the actionable
                       feedback loop.

Exit codes: build 0/2; ingest 0 = calibrated verdicts computed (whatever the
verdicts), 1 = VOID (uncalibrated or incomplete; a VOID verdicts.json is
still written and stamped), 2 = unusable invocation / malformed results.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):  # direct script execution (PEP 366 re-anchor)
    import importlib.util

    _pkg_dir = Path(__file__).resolve().parent
    if "world_aesthetic_judge" not in sys.modules:
        _spec = importlib.util.spec_from_file_location(
            "world_aesthetic_judge", _pkg_dir / "__init__.py",
            submodule_search_locations=[str(_pkg_dir)])
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules["world_aesthetic_judge"] = _mod
        try:
            _spec.loader.exec_module(_mod)
        except BaseException:
            sys.modules.pop("world_aesthetic_judge", None)
            raise
    __package__ = "world_aesthetic_judge"

from . import _corpus, calibration  # noqa: E402

TASKS_SCHEMA = "cabinet.world.judge-tasks/v1"
KEY_SCHEMA = "cabinet.world.judge-key/v1"
RUN_SCHEMA = "cabinet.world.judge-run/v1"
RESULTS_SCHEMA = "cabinet.world.judge-results/v1"
VERDICTS_SCHEMA = "cabinet.world.judge-verdicts/v1"

QUESTION = ("Which reads more like a finished, warm, professional "
            "pixel-game scene — LEFT or RIGHT, and why in one line?")

DEFAULT_NEG_FLOOR = 1.0     # "~1.0": any loss to a known-bad frame is fatal
DEFAULT_PROMOTE_BAR = 0.5   # holds its own against the approved corpus
_EPS = 1e-9

INSTRUCTIONS = [
    "You are the vision judge for Cabinet World frames. Read the rubric "
    "below first and hold all three lenses while judging.",
    "For EACH task: view both images (paths relative to this run "
    "directory), then answer the task's question with LEFT or RIGHT plus a "
    "one-line why naming the deciding criterion. No ties.",
    "Some pairs are hidden calibration pairs; you cannot tell which. Judge "
    "every pair with full care — a run that misranks the hidden set is "
    "VOID.",
    "Do not read key.json, run.json, or anything besides tasks.json and "
    "images/*. Filenames are opaque by design; judge only the pixels.",
    "Write your answers to results.json in this run directory, exactly in "
    "results_format, answering every task exactly once.",
    "Then compute verdicts with: python3.12 "
    "cabinet/scripts/world-aesthetic/judge/judge_protocol.py ingest "
    "--run <this directory> --results <this directory>/results.json",
]


class ProtocolError(ValueError):
    pass


# -------------------------------------------------------------------- build

def _load_rubric() -> str:
    return (_corpus.JUDGE_DIR / "rubric.md").read_text()


def _validate_candidates(paths: list[Path]) -> list[dict]:
    png = _corpus.png_codec()
    out = []
    for i, p in enumerate(paths, start=1):
        p = Path(p)
        if not p.exists():
            raise ProtocolError(f"candidate not found: {p}")
        try:
            png.read_size(p)  # cheap PNG-magic + header sanity
        except Exception as e:
            raise ProtocolError(f"candidate is not a readable PNG: "
                                f"{p} ({e})") from e
        out.append({"id": f"cand-{i}", "file": str(p), "path": p,
                    "sha256": _corpus.sha256_of(p)})
    return out


def _sample(entries: list[dict], k: int, rng: random.Random) -> list[dict]:
    if k and 0 < k < len(entries):
        return sorted(rng.sample(entries, k), key=lambda e: e["id"])
    return entries


def _sides(first_is_left: bool) -> tuple[str, str]:
    return ("LEFT", "RIGHT") if first_is_left else ("RIGHT", "LEFT")


def build_run(candidates: list[Path],
              corpus_dir: Path = _corpus.CORPUS_DIR,
              out_root: Path = _corpus.RUNS_DIR,
              seed: int | None = None,
              pos_samples: int = 0, neg_samples: int = 0,
              cal_max_pairs: int = 0) -> tuple[Path, dict]:
    """Assemble a blinded pairwise run bundle. Returns (run_dir, run_meta)."""
    if not candidates:
        raise ProtocolError("at least one --candidate is required")
    if seed is None:
        seed = random.SystemRandom().getrandbits(32)
    rng = random.Random(seed)
    run_hex = f"{rng.getrandbits(16):04x}"  # drawn first: fixed rng sequence

    corpus_dir = Path(corpus_dir)
    positives = _corpus.corpus_entries("positive", corpus_dir)
    negatives = _corpus.corpus_entries("negative", corpus_dir)
    if not positives or not negatives:
        raise ProtocolError(
            f"corpus needs at least one positive and one negative "
            f"(have {len(positives)}/{len(negatives)}) — see "
            f"corpus/manifest.json + build_corpus.py")
    for e in positives + negatives:
        _corpus.verify_entry(e)  # integrity gate: manifest sha256 must match

    cands = _validate_candidates([Path(c) for c in candidates])
    pos_opp = _sample(positives, pos_samples, rng)
    neg_opp = _sample(negatives, neg_samples, rng)
    cal_pairs = calibration.build_pairs(positives, negatives, rng,
                                        max_pairs=cal_max_pairs)

    # Assemble raw tasks (kind + sources + key facts), sides randomized.
    raw: list[dict] = []
    for pair in cal_pairs:
        pos_side, neg_side = _sides(rng.random() < 0.5)
        raw.append({
            "kind": "calibration",
            "sides": {pos_side: pair["positive"], neg_side: pair["negative"]},
            "key": {"kind": "calibration", "positive_side": pos_side,
                    "positive_id": pair["positive"]["id"],
                    "negative_id": pair["negative"]["id"]},
        })
    for cand in cands:
        for cls, opponents in (("positive", pos_opp), ("negative", neg_opp)):
            for opp in opponents:
                cand_side, opp_side = _sides(rng.random() < 0.5)
                raw.append({
                    "kind": "candidate",
                    "sides": {cand_side: cand, opp_side: opp},
                    "key": {"kind": "candidate", "candidate_side": cand_side,
                            "candidate_id": cand["id"],
                            "opponent_class": cls,
                            "opponent_id": opp["id"]},
                })
    rng.shuffle(raw)  # calibration pairs hide among candidate pairs

    # Run dir + blinded staging (opaque names; sources deduped).
    run_id = (f"jr-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{run_hex}")
    run_dir = Path(out_root) / run_id
    images_dir = run_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=False)

    sources: dict[str, dict] = {}
    for cand in cands:
        sources[str(cand["path"])] = {"role": "candidate",
                                      "ref": cand["id"],
                                      "sha256": cand["sha256"]}
    for e in positives + negatives:
        sources[str(e["path"])] = {"role": e["class"], "ref": e["id"],
                                   "sha256": e["sha256"]}
    staged: dict[str, str] = {}
    used_names: set[str] = set()
    for src in sorted(sources):
        while True:
            name = f"img-{rng.getrandbits(32):08x}.png"
            if name not in used_names:
                break
        used_names.add(name)
        shutil.copyfile(src, images_dir / name)
        staged[src] = f"images/{name}"

    width = max(3, len(str(len(raw))))
    tasks, key_tasks = [], {}
    for i, t in enumerate(raw, start=1):
        task_id = f"t-{i:0{width}d}"
        left_src = t["sides"]["LEFT"]
        right_src = t["sides"]["RIGHT"]
        left = staged[str(left_src["path"])]
        right = staged[str(right_src["path"])]
        tasks.append({"id": task_id, "left": left, "right": right,
                      "question": QUESTION})
        key_tasks[task_id] = t["key"]

    tasks_doc = {
        "schema": TASKS_SCHEMA,
        "run_id": run_id,
        "question": QUESTION,
        "instructions": INSTRUCTIONS,
        "rubric": _load_rubric(),
        "results_format": {
            "schema": RESULTS_SCHEMA,
            "run_id": run_id,
            "answers": [{"task_id": tasks[0]["id"] if tasks else "t-001",
                         "choice": "LEFT|RIGHT",
                         "why": "one line naming the deciding criterion"}],
        },
        "results_path": "results.json",
        "tasks": tasks,
    }
    key_doc = {
        "schema": KEY_SCHEMA,
        "run_id": run_id,
        "images": {rel: sources[src] | {"source": src}
                   for src, rel in staged.items()},
        "tasks": key_tasks,
    }
    counts = {
        "calibration": len(cal_pairs),
        "candidate_vs_positive": len(cands) * len(pos_opp),
        "candidate_vs_negative": len(cands) * len(neg_opp),
        "total": len(raw),
    }
    run_doc = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "created_at": _corpus.utcnow_iso(),
        "seed": seed,
        "params": {"pos_samples": pos_samples, "neg_samples": neg_samples,
                   "cal_max_pairs": cal_max_pairs},
        "corpus": {
            "manifest": str(corpus_dir / "manifest.json"),
            "manifest_sha256":
                _corpus.sha256_of(corpus_dir / "manifest.json"),
            "n_positive": len(positives), "n_negative": len(negatives),
            "opponents_positive": [e["id"] for e in pos_opp],
            "opponents_negative": [e["id"] for e in neg_opp],
        },
        "candidates": [{"id": c["id"], "file": c["file"],
                        "sha256": c["sha256"]} for c in cands],
        "counts": counts,
    }
    _corpus.atomic_write_json(run_dir / "tasks.json", tasks_doc)
    _corpus.atomic_write_json(run_dir / "key.json", key_doc)
    _corpus.atomic_write_json(run_dir / "run.json", run_doc)
    return run_dir, run_doc


# ------------------------------------------------------------------- ingest

def parse_results(obj, known_ids: set[str], run_id: str) -> dict[str, dict]:
    """Validate a filled results doc -> {task_id: {choice, why}}.

    Malformed results (wrong shape, unknown/duplicate ids, junk choices,
    mismatched run_id) raise ProtocolError — a protocol violation is a
    broken runner, never scored as judgment.
    """
    if not isinstance(obj, dict) or not isinstance(obj.get("answers"), list):
        raise ProtocolError('results must be {"answers": [...]}')
    if obj.get("run_id") not in (None, run_id):
        raise ProtocolError(f"results run_id {obj.get('run_id')!r} does not "
                            f"match run {run_id!r}")
    answers: dict[str, dict] = {}
    for row in obj["answers"]:
        if not isinstance(row, dict):
            raise ProtocolError(f"bad answer row: {row!r}")
        tid = row.get("task_id")
        if tid not in known_ids:
            raise ProtocolError(f"unknown task_id in results: {tid!r}")
        if tid in answers:
            raise ProtocolError(f"duplicate task_id in results: {tid!r}")
        choice = str(row.get("choice", "")).strip().upper()
        if choice not in ("LEFT", "RIGHT"):
            raise ProtocolError(f"bad choice for {tid}: "
                                f"{row.get('choice')!r} (want LEFT|RIGHT)")
        answers[tid] = {"choice": choice,
                        "why": str(row.get("why", "")).strip()}
    return answers


def verdict_for(win_rate_neg: float, win_rate_pos: float,
                neg_floor: float = DEFAULT_NEG_FLOOR,
                promote_bar: float = DEFAULT_PROMOTE_BAR) -> str:
    """promote / iterate / reject from the two win-rates.

    Negatives are the sanity gate (must be ~1.0); positives are the bar.
    """
    if win_rate_neg < neg_floor - _EPS:
        return "reject"
    if win_rate_pos >= promote_bar - _EPS:
        return "promote"
    return "iterate"


def aggregate_candidates(key_tasks: dict[str, dict],
                         answers: dict[str, dict],
                         candidates: list[dict],
                         neg_floor: float = DEFAULT_NEG_FLOOR,
                         promote_bar: float = DEFAULT_PROMOTE_BAR
                         ) -> list[dict]:
    """Win-rates + verdict + collected notes per candidate."""
    stats = {c["id"]: {"meta": c,
                       "n_pos": 0, "w_pos": 0, "n_neg": 0, "w_neg": 0,
                       "loss_neg": [], "loss_pos": [], "win_pos": []}
             for c in candidates}
    for tid, k in key_tasks.items():
        if k["kind"] != "candidate":
            continue
        st = stats.get(k["candidate_id"])
        if st is None:
            raise ProtocolError(f"key references unknown candidate "
                                f"{k['candidate_id']!r}")
        ans = answers.get(tid)
        if ans is None:
            raise ProtocolError(f"missing answer for {tid} at aggregation "
                                f"(completeness gate should have voided)")
        won = ans["choice"] == k["candidate_side"]
        note = {"opponent": k["opponent_id"], "why": ans["why"]}
        if k["opponent_class"] == "negative":
            st["n_neg"] += 1
            st["w_neg"] += won
            if not won:
                st["loss_neg"].append(note)
        else:
            st["n_pos"] += 1
            st["w_pos"] += won
            (st["win_pos"] if won else st["loss_pos"]).append(note)

    out = []
    for cid in sorted(stats):
        st = stats[cid]
        if st["n_neg"] == 0 or st["n_pos"] == 0:
            raise ProtocolError(f"candidate {cid} has no pairs vs "
                                f"{'negatives' if st['n_neg'] == 0 else 'positives'}")
        rate_neg = st["w_neg"] / st["n_neg"]
        rate_pos = st["w_pos"] / st["n_pos"]
        out.append({
            "candidate_id": cid,
            "file": st["meta"]["file"],
            "n_vs_negative": st["n_neg"],
            "wins_vs_negative": st["w_neg"],
            "win_rate_vs_negative": rate_neg,
            "n_vs_positive": st["n_pos"],
            "wins_vs_positive": st["w_pos"],
            "win_rate_vs_positive": rate_pos,
            "verdict": verdict_for(rate_neg, rate_pos, neg_floor,
                                   promote_bar),
            "notes": {
                "losses_vs_negatives": st["loss_neg"],
                "losses_vs_positives": st["loss_pos"],
                "wins_vs_positives": st["win_pos"],
            },
        })
    return out


def _void_candidates(candidates: list[dict]) -> list[dict]:
    return [{"candidate_id": c["id"], "file": c["file"], "verdict": "void"}
            for c in candidates]


def ingest_run(run_dir: Path, results_path: Path,
               neg_floor: float = DEFAULT_NEG_FLOOR,
               promote_bar: float = DEFAULT_PROMOTE_BAR,
               threshold: float = calibration.CALIBRATION_THRESHOLD,
               out_path: Path | None = None) -> tuple[dict, int]:
    """Compute verdicts from a filled run. Returns (verdicts_doc, exit_code).

    Raises ProtocolError (exit 2 at the CLI) for malformed bundles/results;
    returns exit 1 with a stamped VOID doc for incomplete or uncalibrated
    runs; exit 0 when calibrated verdicts were computed.
    """
    run_dir = Path(run_dir)
    docs = {}
    for name in ("run.json", "tasks.json", "key.json"):
        p = run_dir / name
        if not p.exists():
            raise ProtocolError(f"run bundle missing {name}: {run_dir}")
        try:
            docs[name] = json.loads(p.read_text())
        except json.JSONDecodeError as e:
            raise ProtocolError(f"unreadable {name}: {e}") from e
    run_doc, tasks_doc, key_doc = (docs["run.json"], docs["tasks.json"],
                                   docs["key.json"])
    key_tasks: dict[str, dict] = key_doc["tasks"]
    task_ids = {t["id"] for t in tasks_doc["tasks"]}
    if task_ids != set(key_tasks):
        raise ProtocolError("run bundle corrupt: tasks.json and key.json "
                            "disagree on task ids")

    results_path = Path(results_path)
    if not results_path.exists():
        raise ProtocolError(f"results file not found: {results_path}")
    try:
        results_obj = json.loads(results_path.read_text())
    except json.JSONDecodeError as e:
        raise ProtocolError(f"unreadable results: {e}") from e
    answers = parse_results(results_obj, task_ids, run_doc["run_id"])

    cal_key = [{"task_id": tid} | k for tid, k in sorted(key_tasks.items())
               if k["kind"] == "calibration"]
    cal = calibration.score(cal_key, answers, threshold=threshold)

    doc = {
        "schema": VERDICTS_SCHEMA,
        "run_id": run_doc["run_id"],
        "created_at": _corpus.utcnow_iso(),
        "params": {"neg_floor": neg_floor, "promote_bar": promote_bar,
                   "calibration_threshold": threshold},
        "calibration": cal,  # stamped into EVERY outcome, void or not
    }
    missing = sorted(task_ids - set(answers))
    if missing:
        doc["status"] = "void_incomplete"
        doc["missing_answers"] = missing
        doc["candidates"] = _void_candidates(run_doc["candidates"])
        code = 1
    elif not cal["passed"]:
        # The D5 gate: an uncalibrated judge voids the whole run.
        doc["status"] = "void_uncalibrated"
        doc["candidates"] = _void_candidates(run_doc["candidates"])
        code = 1
    else:
        doc["status"] = "ok"
        doc["candidates"] = aggregate_candidates(
            key_tasks, answers, run_doc["candidates"],
            neg_floor=neg_floor, promote_bar=promote_bar)
        code = 0
    _corpus.atomic_write_json(out_path or (run_dir / "verdicts.json"), doc)
    return doc, code


# ---------------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="judge_protocol.py",
        description="Pairwise vision-judge protocol for Cabinet World "
                    "frames (build task bundles, ingest agent results).")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="emit a blinded pairwise run bundle")
    b.add_argument("--candidate", action="append", required=True,
                   help="candidate frame PNG (repeatable)")
    b.add_argument("--pos-samples", type=int, default=0,
                   help="corpus positives per candidate (0 = all)")
    b.add_argument("--neg-samples", type=int, default=0,
                   help="corpus negatives per candidate (0 = all)")
    b.add_argument("--cal-max-pairs", type=int, default=0,
                   help="cap the hidden calibration cross product (0 = all)")
    b.add_argument("--seed", type=int, default=None,
                   help="RNG seed (default: fresh; recorded in run.json)")
    b.add_argument("--out-root", default=str(_corpus.RUNS_DIR))
    b.add_argument("--corpus-dir", default=str(_corpus.CORPUS_DIR))

    i = sub.add_parser("ingest", help="compute verdicts from filled results")
    i.add_argument("--run", required=True, help="run bundle directory")
    i.add_argument("--results", required=True, help="filled results.json")
    i.add_argument("--neg-floor", type=float, default=DEFAULT_NEG_FLOOR)
    i.add_argument("--promote-bar", type=float, default=DEFAULT_PROMOTE_BAR)
    i.add_argument("--calibration-threshold", type=float,
                   default=calibration.CALIBRATION_THRESHOLD)
    i.add_argument("--out", default="",
                   help="verdicts path (default <run>/verdicts.json)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "build":
            run_dir, run_doc = build_run(
                [Path(c) for c in args.candidate],
                corpus_dir=Path(args.corpus_dir),
                out_root=Path(args.out_root),
                seed=args.seed,
                pos_samples=args.pos_samples,
                neg_samples=args.neg_samples,
                cal_max_pairs=args.cal_max_pairs)
            c = run_doc["counts"]
            print(f"run bundle: {run_dir}")
            print(f"tasks: {c['total']} "
                  f"(calibration {c['calibration']}, "
                  f"vs-positive {c['candidate_vs_positive']}, "
                  f"vs-negative {c['candidate_vs_negative']}) "
                  f"seed {run_doc['seed']}")
            print(f"hand the runner: {run_dir / 'tasks.json'} "
                  f"(runner reads ONLY tasks.json + images/)")
            return 0
        if args.cmd == "ingest":
            doc, code = ingest_run(
                Path(args.run), Path(args.results),
                neg_floor=args.neg_floor, promote_bar=args.promote_bar,
                threshold=args.calibration_threshold,
                out_path=Path(args.out) if args.out else None)
            cal = doc["calibration"]
            print(f"status: {doc['status']}  calibration "
                  f"{cal['correct']}/{cal['n_pairs']} "
                  f"({cal['accuracy']:.3f}, floor {cal['threshold']})")
            for cand in doc["candidates"]:
                if doc["status"] == "ok":
                    print(f"  {cand['candidate_id']}: {cand['verdict']}  "
                          f"vs-neg {cand['wins_vs_negative']}/"
                          f"{cand['n_vs_negative']}  "
                          f"vs-pos {cand['wins_vs_positive']}/"
                          f"{cand['n_vs_positive']}")
                else:
                    print(f"  {cand['candidate_id']}: {cand['verdict']}")
            return code
        raise ProtocolError(f"unknown command {args.cmd!r}")
    except (ProtocolError, _corpus.CorpusError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
