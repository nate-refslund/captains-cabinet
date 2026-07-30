#!/usr/bin/env python3.12
"""Agnosticism advisor — an LLM lens on the ONE layer-separation question no
grep can answer: does this change teach the framework about a specific tool,
industry, role, organisation, product or person?

ADVISORY. It never runs in CI, never produces a status check, and never decides
whether anything merges. It reads code and LABELS it; a human or the
orchestrator decides. The division is the one this repo already ratified —
`cabinet/scripts/world-aesthetic/judge/` carries the judgment half beside
deterministic gates, and the scoring pins say it twice ("only verdict_human
promotes"). An LLM verdict may create WORK; it may never create PERMISSION.

WHY AN LLM HERE AND NOWHERE ELSE
The deterministic half of layer separation is already built and stays
authoritative: `cabinet/scripts/check-layer-separation.sh` catches
framework->instance imports and path coupling, and
`framework/tests/test_no_launcher_hardcode.py` is a shrink-only ratchet over a
list of banned literals. Both answer "does this text contain a token I already
know to ban?" Neither can answer "is this noun specific?", and by construction
neither ever will: that ratchet's Arm 1 patterns are SYNTHETIC placeholders
(`Testburg` / `bakery` / `testburg.example`) precisely so the shipped source
names nobody real, and its real-token half lives in an untracked, gitignored
`instance/config/publish-scan-patterns.local`.

NARROWED 2026-07-30, and only narrowed. That ratchet's Arm 2 now DERIVES its
vendor vocabulary from the tree, and its Arm 3 derives the OPERATOR'S OWN
identity from what the repository and its instance layer declare (licence
holder, owner handle, declared `captain_name`) — so a new vendor label, and the
launching operator's real name, are no longer invisible. Everything else still
is: a colleague, a customer, a counterparty, an industry verb, a role name, a
unit or a cadence carries no token any tracked sensor can derive. A brand-new
real-world proper noun that is not the operator's own arriving in `framework/`
today remains invisible to every tracked sensor, and the ban-list IS the answer
being sought — exactly the shape of question a grep cannot answer and a reader
can.

WHERE THIS MUST NEVER GO. Not a required status check, not a CI job, and not
in front of any question a deterministic check can answer — a digest, a set
comparison, a secret scan, a syntax check, a ratchet. If a deterministic check
is merely hard to write, that is an argument for writing it. A required check
must be reproducible from bytes alone; this is not, and pretending otherwise
would convert a proof into an opinion.

THE THREE WAYS AN LLM LENS ROTS, AND WHAT IS DONE ABOUT EACH
1. It becomes a rubber stamp. Answered by `--calibrate`: a planted corpus with
   recorded ground truth, scored BLIND (fixtures are presented under opaque
   ids, so the judge cannot read the answer off a path). Missing one planted
   violation VOIDs the run. Flagging the clean set VOIDs it too — checked in
   BOTH directions, because a judge that flags everything is as useless as one
   that flags nothing, and a one-directional floor leaves the other free to
   rot. A stub that answers "agnostic" to everything and a stub that answers
   "instance-specific" to everything both VOID; both are pinned as tests.
2. It flakes. The model id is pinned, the rubric and corpus are hashed into a
   digest recorded with every verdict, output is schema-constrained JSON,
   `--votes N` takes a majority, and verdicts are cached by
   (rubric digest, content hash) so a re-read replays rather than re-decides.
   Residual non-determinism costs a re-read, because the lane is advisory.
3. It judges its own judge. Any run whose input set touches the advisor, the
   rubric or the corpus ABSTAINS with an explicit message rather than
   producing a verdict on the thing that produced it.

USAGE (local, before opening a PR — never in a workflow):
    python3.12 cabinet/scripts/agnosticism-advisor.py --calibrate
    python3.12 cabinet/scripts/agnosticism-advisor.py --diff origin/master

Auth is OAuth only, through `framework/fidelity/oauth_llm.py`: a `claude -p`
headless agent billing the Max pool, with NO ANTHROPIC_API_KEY. That is the
whole reason this is affordable to run on every change and unaffordable to run
in hosted CI, where it would need a credential this repo deliberately does not
have.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

_REPO = Path(__file__).resolve().parents[2]
CORPUS_DIR = Path(__file__).resolve().parent / "agnosticism-corpus"
MANIFEST = CORPUS_DIR / "manifest.yml"

# Pinned. An unpinned model turns every verdict into a different judge's
# opinion and makes the calibration record meaningless.
MODEL = "claude-opus-5"

# The advisor's own surface. A run whose inputs touch any of these ABSTAINS.
SELF_PATHS = (
    "cabinet/scripts/agnosticism-advisor.py",
    "cabinet/scripts/agnosticism-corpus/*",
    "cabinet/scripts/tests/test_agnosticism_advisor.py",
)

# The layer that must stay agnostic. `instance/` is where specifics belong.
SCOPE_PREFIXES = ("framework/", "cabinet/")
SCOPE_SUFFIXES = (".py", ".sh", ".md", ".yml", ".yaml", ".ts", ".tsx")

AGNOSTIC = "agnostic"
SPECIFIC = "instance-specific"
ERROR = "error"

RUBRIC = """\
You are a layer-separation reviewer for a REUSABLE agent framework.

The framework layer must serve any operator, any organisation, any product and
any domain. Anything specific to ONE operator, organisation, product, vendor,
industry, jurisdiction or named person belongs in the instance layer, which is
configured per deployment and never shipped as part of the framework.

You are shown one file from the framework layer. Answer exactly one question:

  Does this text teach the framework about a SPECIFIC tool, industry, role,
  organisation, product, jurisdiction or person?

Answer "instance-specific" when the text hardcodes, or reasons from, a
particular real-world entity: a company or its mail/web domain, a product or
lane name, a person's name, an external tracker/board/chat id, one industry's
document types or business rules, one jurisdiction's regulatory fields, one
organisation's job titles, or a niche vendor SDK used to do the operator's
business work.

Answer "agnostic" otherwise. In particular these are NOT violations:

  * Generic technical vocabulary: algorithms, data structures, protocols,
    standard-library and language names, abstract concepts, generic taxonomies.
  * INFRASTRUCTURE THE FRAMEWORK ITSELF RUNS ON — its datastore, queue,
    database, test runner, version control, CI system, language runtime. The
    framework is allowed to know what it is built out of. It is not allowed to
    know who is using it.
  * Resolver seams that read identity from configuration instead of naming it.
  * Clearly SYNTHETIC placeholder identities used as demo or test fixtures
    (obvious stand-ins that name nobody real). These are the sanctioned way to
    write an example, and flagging them is a false positive.

Judge the text in front of you. Do not speculate about code you cannot see, and
do not flag a file merely because it is domain-adjacent — the question is
whether the framework has been TAUGHT the specific entity.

Some inputs are hidden calibration items with a recorded answer, and you cannot
tell which; file names may be opaque. Judge every input on its content alone.

Return JSON only:
  {"verdict": "agnostic" | "instance-specific",
   "nouns": [<the specific entities you found, [] when agnostic>],
   "why": "<one sentence>"}
"""

_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": [AGNOSTIC, SPECIFIC]},
        "nouns": {"type": "array", "items": {"type": "string"}},
        "why": {"type": "string"},
    },
    "required": ["verdict"],
}


@dataclass
class Verdict:
    name: str
    verdict: str
    nouns: list[str] = field(default_factory=list)
    why: str = ""
    votes: list[str] = field(default_factory=list)

    @property
    def flagged(self) -> bool:
        return self.verdict == SPECIFIC


# --------------------------------------------------------------------------
# Rubric / corpus digest — recorded with every verdict so a verdict produced
# under a different rubric can never be mistaken for one produced under this.
# --------------------------------------------------------------------------


def _corpus_bytes() -> bytes:
    parts: list[bytes] = [RUBRIC.encode(), MODEL.encode()]
    if MANIFEST.exists():
        parts.append(MANIFEST.read_bytes())
    for path in sorted(CORPUS_DIR.rglob("*.txt")):
        parts.append(path.relative_to(CORPUS_DIR).as_posix().encode())
        parts.append(path.read_bytes())
    return b"\x00".join(parts)


def rubric_digest() -> str:
    return hashlib.sha256(_corpus_bytes()).hexdigest()


def load_manifest() -> dict[str, Any]:
    import yaml  # local import: the deterministic tests need no yaml at import

    data = yaml.safe_load(MANIFEST.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError("corpus manifest is not a mapping")
    return data


# --------------------------------------------------------------------------
# The LLM seam.
# --------------------------------------------------------------------------


def _default_llm(payload: str, system: str, model: str) -> dict[str, Any] | None:
    if str(_REPO) not in sys.path:
        sys.path.insert(0, str(_REPO))
    from framework.fidelity.oauth_llm import oauth_json_llm

    return oauth_json_llm(payload, system, model=model, schema=_SCHEMA)


LLM = Callable[[str, str, str], "dict[str, Any] | None"]


def review_text(
    name: str,
    text: str,
    *,
    llm: LLM | None = None,
    model: str = MODEL,
    votes: int = 1,
    cache: "VerdictCache | None" = None,
) -> Verdict:
    """One labelled verdict. An unparseable answer is ERROR, never AGNOSTIC —
    'nothing came back' must not read as 'nothing found'."""
    call = llm or (lambda p, s, m: _default_llm(p, s, m))
    if cache is not None:
        hit = cache.get(text)
        if hit is not None:
            return Verdict(name, hit["verdict"], hit.get("nouns", []),
                           hit.get("why", ""), hit.get("votes", []))

    cast: list[str] = []
    detail: dict[str, Any] = {}
    for _ in range(max(1, votes)):
        payload = f"FILE: {name}\n\n<<<BEGIN\n{text}\nEND>>>\n"
        out = call(payload, RUBRIC, model)
        if isinstance(out, dict) and out.get("verdict") in (AGNOSTIC, SPECIFIC):
            cast.append(str(out["verdict"]))
            if out["verdict"] == SPECIFIC or not detail:
                detail = out

    if not cast:
        return Verdict(name, ERROR, [], "no parseable verdict returned", [])

    majority = SPECIFIC if cast.count(SPECIFIC) * 2 > len(cast) else (
        AGNOSTIC if cast.count(AGNOSTIC) * 2 > len(cast) else cast[0]
    )
    nouns = [str(n) for n in (detail.get("nouns") or [])] if majority == SPECIFIC else []
    v = Verdict(name, majority, nouns, str(detail.get("why", "")), cast)
    if cache is not None:
        cache.put(text, {"verdict": v.verdict, "nouns": v.nouns, "why": v.why,
                         "votes": v.votes})
    return v


class VerdictCache:
    """Keyed by (rubric digest, content hash). A re-read replays; a
    re-decision is impossible without changing the rubric or the bytes."""

    def __init__(self, root: Path, digest: str | None = None):
        self.root = Path(root)
        self.digest = digest or rubric_digest()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, text: str) -> Path:
        key = hashlib.sha256(f"{self.digest}\x00{text}".encode()).hexdigest()
        return self.root / f"{key}.json"

    def get(self, text: str) -> dict[str, Any] | None:
        p = self._path(text)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, ValueError, OSError):
            return None
        return data if isinstance(data, dict) else None

    def put(self, text: str, data: dict[str, Any]) -> None:
        try:
            self._path(text).write_text(json.dumps(data))
        except OSError:
            pass


# --------------------------------------------------------------------------
# Calibration — the non-vacuity proof, scored blind, in both directions.
# --------------------------------------------------------------------------


@dataclass
class Calibration:
    void: bool
    reasons: list[str]
    caught: int
    planted: int
    false_positives: int
    clean: int
    rows: list[tuple[str, str, str]]  # (fixture, expected, got)
    digest: str


def _blind_name(rel: str) -> str:
    """Opaque, stable, and carries no hint of the recorded answer."""
    return "item-" + hashlib.sha256(rel.encode()).hexdigest()[:10] + ".txt"


def calibrate(
    *,
    llm: LLM | None = None,
    model: str = MODEL,
    votes: int = 1,
    manifest: dict[str, Any] | None = None,
    cache: VerdictCache | None = None,
) -> Calibration:
    man = manifest if manifest is not None else load_manifest()
    bad = list(man.get("known_bad") or [])
    good = list(man.get("known_good") or [])
    tpr_floor = float(man.get("min_true_positive_rate", 1.0))
    fp_max = int(man.get("max_false_positives", 0))

    reasons: list[str] = []
    rows: list[tuple[str, str, str]] = []

    if not bad or not good:
        # DEGENERATE END. An empty planted set makes the true-positive rate
        # vacuously 1.0 and every stub judge passes. An empty clean set does
        # the same for the false-positive floor.
        return Calibration(
            True,
            [f"corpus is degenerate: {len(bad)} planted, {len(good)} clean — "
             "a calibration that scores nothing proves nothing"],
            0, len(bad), 0, len(good), rows, rubric_digest(),
        )

    caught = 0
    for entry in bad:
        rel = str(entry.get("file"))
        text = (CORPUS_DIR / rel).read_text()
        v = review_text(_blind_name(rel), text, llm=llm, model=model,
                        votes=votes, cache=cache)
        rows.append((rel, SPECIFIC, v.verdict))
        if v.flagged:
            caught += 1

    false_positives = 0
    for entry in good:
        rel = str(entry.get("file"))
        text = (CORPUS_DIR / rel).read_text()
        v = review_text(_blind_name(rel), text, llm=llm, model=model,
                        votes=votes, cache=cache)
        rows.append((rel, AGNOSTIC, v.verdict))
        if v.verdict != AGNOSTIC:
            false_positives += 1

    tpr = caught / len(bad)
    if tpr < tpr_floor:
        reasons.append(
            f"missed {len(bad) - caught}/{len(bad)} planted violations "
            f"(true-positive rate {tpr:.2f} < floor {tpr_floor:.2f})"
        )
    if false_positives > fp_max:
        reasons.append(
            f"flagged {false_positives}/{len(good)} clean fixtures "
            f"(max {fp_max}) — a judge that flags everything is not a judge"
        )
    return Calibration(bool(reasons), reasons, caught, len(bad),
                       false_positives, len(good), rows, rubric_digest())


# --------------------------------------------------------------------------
# Sweep.
# --------------------------------------------------------------------------


def in_scope(rel: str) -> bool:
    return rel.startswith(SCOPE_PREFIXES) and rel.endswith(SCOPE_SUFFIXES)


def touches_self(paths: Iterable[str]) -> bool:
    return any(
        any(fnmatch.fnmatch(p, pat) for pat in SELF_PATHS) for p in paths
    )


def changed_paths(base: str, repo: Path = _REPO) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            cwd=repo, capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    return [line for line in (out.stdout or "").splitlines() if line.strip()]


def sweep(
    paths: Sequence[str],
    *,
    llm: LLM | None = None,
    model: str = MODEL,
    votes: int = 1,
    repo: Path = _REPO,
    cache: VerdictCache | None = None,
) -> list[Verdict]:
    results: list[Verdict] = []
    for rel in paths:
        p = repo / rel
        if not p.is_file():
            continue
        try:
            text = p.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        results.append(review_text(rel, text, llm=llm, model=model,
                                   votes=votes, cache=cache))
    return results


# --------------------------------------------------------------------------
# CLI.
# --------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None, *, llm: LLM | None = None) -> int:
    ap = argparse.ArgumentParser(description="Agnosticism advisor (ADVISORY ONLY)")
    ap.add_argument("--calibrate", action="store_true",
                    help="score the planted corpus; VOID (exit 1) on rot")
    ap.add_argument("--diff", metavar="BASE",
                    help="review framework/cabinet files changed vs BASE")
    ap.add_argument("--paths", nargs="*", default=None)
    ap.add_argument("--votes", type=int, default=1)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    cache = VerdictCache(Path(args.cache_dir)) if args.cache_dir else None

    if args.calibrate:
        cal = calibrate(llm=llm, model=args.model, votes=args.votes, cache=cache)
        if args.json:
            print(json.dumps({
                "void": cal.void, "reasons": cal.reasons,
                "caught": cal.caught, "planted": cal.planted,
                "false_positives": cal.false_positives, "clean": cal.clean,
                "digest": cal.digest,
                "rows": [{"fixture": f, "expected": e, "got": g}
                         for f, e, g in cal.rows],
            }, indent=2))
        else:
            for fixture, expected, got in cal.rows:
                mark = "ok " if expected == got else "MISS"
                print(f"  {mark}  {fixture:44s} expected={expected:17s} got={got}")
            print(f"\ncaught {cal.caught}/{cal.planted} planted, "
                  f"{cal.false_positives}/{cal.clean} clean flagged, "
                  f"rubric {cal.digest[:12]}")
            print("VOID: " + "; ".join(cal.reasons) if cal.void else "CALIBRATED")
        return 1 if cal.void else 0

    paths = list(args.paths or [])
    if args.diff:
        paths = changed_paths(args.diff)
    scoped = [p for p in paths if in_scope(p)]

    if touches_self(paths):
        print("ABSTAIN — this change touches the advisor, its rubric or its "
              "corpus; a judge does not grade the thing that produced it. "
              "Re-run --calibrate and have the change reviewed by hand.")
        return 0

    if not scoped:
        print("no framework/ or cabinet/ files in scope — nothing to review")
        return 0

    results = sweep(scoped, llm=llm, model=args.model, votes=args.votes,
                    cache=cache)
    flagged = [v for v in results if v.flagged]
    errored = [v for v in results if v.verdict == ERROR]
    if args.json:
        print(json.dumps({
            "digest": rubric_digest(), "model": args.model,
            "reviewed": len(results),
            "findings": [{"file": v.name, "verdict": v.verdict,
                          "nouns": v.nouns, "why": v.why} for v in results],
        }, indent=2))
    else:
        for v in flagged:
            print(f"  FLAG  {v.name}\n        nouns: {', '.join(v.nouns) or '-'}"
                  f"\n        {v.why}")
        for v in errored:
            print(f"  ERR   {v.name} — {v.why}")
        print(f"\nreviewed {len(results)} file(s): {len(flagged)} flagged, "
              f"{len(errored)} unreadable, rubric {rubric_digest()[:12]}")
        print("ADVISORY — these are findings, not a gate. Nothing here blocks "
              "a merge.")
    # ALWAYS 0. This lane creates work, never permission.
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
