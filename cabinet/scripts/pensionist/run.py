"""Pensionist test runner (captain-surface spec §7) — screenshots → vision
model → rubric.

For every PNG in ``shots/`` the runner asks a vision model (the ``claude``
CLI) the three rubric questions and grades the answers:

  FAIL — the model cannot answer all three, or its answer leans on a banned
         term that appears ON the card (the card forced the vocabulary);
  WARN — the answer uses a banned term the card did not force;
  PASS — three plain-word answers, no banned vocabulary.

Manual/release gate: needs the ``claude`` CLI (vision) on PATH. The
deterministic teeth (pytest/vitest jargon linters, render_tg's lint) run in
CI; this harness is the human-comprehension gate rerun on surface changes.

Usage:
    python3.12 cabinet/scripts/pensionist/run.py [--shots DIR] [--out DIR]
                                                 [--model MODEL]

Exit codes: 0 all pass (warns allowed) · 1 any FAIL · 3 claude CLI missing.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[3]
sys.path.insert(0, str(_REPO))

from framework.attention import plain as plainlaw  # noqa: E402

_QUESTIONS = (
    "1. What is being asked of me?",
    "2. What happens if I press each button?",
    "3. What happens if I ignore it?",
)

_PROMPT = """You are a 70-year-old pensioner with no software background.
Read the screenshot at {path} — it shows one or more decision cards.

For EACH card you can see, answer in plain everyday words:
{questions}

Rules: answer only from what the picture shows. If you cannot tell what a
card is asking, or what a button will do, say exactly "I cannot tell" for
that question. Do not guess technical meanings.

Return STRICT JSON only, no prose around it:
{{"cards": [{{"title": "<card headline>",
             "asked_of_me": "…", "buttons": "…", "if_ignored": "…",
             "could_not_tell": false}}]}}
"""


def _banned_hits(text: str) -> list:
    return sorted({v["term"] for v in plainlaw.lint(text or "")})


def _extract_json(raw: str) -> "dict | None":
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        doc = json.loads(m.group(0))
    except ValueError:
        return None
    return doc if isinstance(doc, dict) else None


def grade(answers: dict, *, forced_terms: "set | None" = None) -> dict:
    """Grade one shot's parsed answers. ``forced_terms`` = banned terms that
    appear ON the card (the card's own sin, not the model's)."""
    forced = forced_terms or set()
    verdict, notes = "PASS", []
    cards = answers.get("cards") or []
    if not cards:
        return {"verdict": "FAIL", "notes": ["no card explained"]}
    for c in cards:
        if not isinstance(c, dict):
            return {"verdict": "FAIL", "notes": ["malformed answer"]}
        fields = [str(c.get(k) or "") for k in
                  ("asked_of_me", "buttons", "if_ignored")]
        if c.get("could_not_tell") or not all(fields) \
                or any("i cannot tell" in f.lower() for f in fields):
            verdict = "FAIL"
            notes.append(f"{c.get('title')!r}: unanswerable in plain words")
            continue
        hits = set()
        for f in fields:
            hits.update(_banned_hits(f))
        forced_hits = hits & forced
        if forced_hits:
            verdict = "FAIL"
            notes.append(f"{c.get('title')!r}: card forced banned terms "
                         f"{sorted(forced_hits)}")
        elif hits and verdict != "FAIL":
            verdict = "WARN" if verdict == "PASS" else verdict
            notes.append(f"{c.get('title')!r}: model used {sorted(hits)} "
                         f"unforced")
    return {"verdict": verdict, "notes": notes}


def main(argv: "list | None" = None) -> int:
    ap = argparse.ArgumentParser(prog="pensionist-test")
    ap.add_argument("--shots", default=str(_HERE.parent / "shots"))
    ap.add_argument("--out", default=str(_HERE.parent / "out"))
    ap.add_argument("--model", default=None,
                    help="claude CLI --model override")
    args = ap.parse_args(argv)

    claude = shutil.which("claude")
    if not claude:
        print("SKIP: `claude` CLI not on PATH — the pensionist test is a "
              "manual/release gate and cannot run here.", file=sys.stderr)
        return 3

    shots = sorted(Path(args.shots).glob("*.png"))
    if not shots:
        print(f"FAIL: no shots in {args.shots}", file=sys.stderr)
        return 1
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    results, worst = [], 0
    for shot in shots:
        prompt = _PROMPT.format(path=shot,
                                questions="\n".join(_QUESTIONS))
        cmd = [claude, "-p", prompt]
        if args.model:
            cmd += ["--model", args.model]
        try:
            raw = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=300).stdout
        except subprocess.TimeoutExpired:
            results.append({"shot": shot.name, "verdict": "FAIL",
                            "notes": ["vision call timed out"]})
            worst = max(worst, 1)
            continue
        parsed = _extract_json(raw or "")
        if parsed is None:
            res = {"verdict": "FAIL", "notes": ["no JSON answer"]}
        else:
            res = grade(parsed)
            res["answers"] = parsed
        res["shot"] = shot.name
        results.append(res)
        if res["verdict"] == "FAIL":
            worst = max(worst, 1)
        print(f"{res['verdict']:4}  {shot.name}"
              + (f"  — {'; '.join(res['notes'])}" if res["notes"] else ""))

    report = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "results": results}
    (outdir / "pensionist-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"report: {outdir / 'pensionist-report.json'}")
    return 1 if worst else 0


if __name__ == "__main__":
    raise SystemExit(main())
