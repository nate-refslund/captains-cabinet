"""Flywheel step 1 — harvest human corrections into a FROZEN regression corpus.

WHY (fresh review 2026-07-04 §6.2, "failure-to-eval flywheel"): every Captain
veto/edit/skip/undo lands on the consequence ledger as prose-adjacent lifecycle
rows and is then never replayed — corrections are spent once and forgotten.
This module turns that correction stream into a growing, frozen, replayable
regression corpus so the F1/eval cadence can gate changes on task-level
non-regression ("no case regresses AND >=1 improves" —
framework/fidelity/regression_gate.py owns that predicate).

WHAT A CASE IS (task contract): {input situation, the human verdict, the cell}.
  * situation  — a leak-safe REPLAY REFERENCE (ts/actor/lane/action/subject/
    refs), NOT embedded content. The ledger itself deliberately stores no draft
    bodies (framework/acting/loop.py::proposal_event — "the ledger records the
    decision lifecycle, not the message (leak-safe)"), so the corpus inherits
    exactly that posture: replay resolves subject/refs through the harness's
    as-of-cutoff gather, the same way the F1 fidelity harness rebuilds cases.
  * human_verdict — kind (edit|skip|veto|undo|human_wrong) + the raw decision/
    review fields + the human-readable evidence string.
  * cell — (actor, lane, action_type) EXACTLY as graduation math keys it
    (framework/fidelity/consequence.py::compute_ratios:674-679, including the
    UNSTAMPED_ACTION_TYPE sentinel for unstamped/legacy rows) so a frozen case
    always joins back to the trust cell it should discipline.

WHAT COUNTS AS A HUMAN CORRECTION (dated decision 2026-07-05, derived from the
live emitters — framework/acting/loop.py::_VERDICT:31-37 and
framework/frontdoor/binder_wire.py::_ACTED_VERDICTS:158-171):
  * proposal.decision == "edited"   -> kind "edit"  (Captain rewrote the draft)
  * proposal.decision == "rejected" -> kind "skip"  (Captain skipped/refused the
    proposal; loop.py maps the `skip:` reply to decision=rejected)
  * review.verdict == "wrong" AND review.source == "verdict_human" -> kind by
    the binder's evidence prefix: "captain-undo" -> undo; "captain veto" ->
    veto; "captain edited" -> edit; anything else -> human_wrong.
  Proposal decisions need no review.source: a decided proposal is structurally
  human (only the Captain decides proposals — loop.outcome_event is reachable
  only from a routed Captain reply). A `wrong` verdict WITHOUT verdict_human
  attribution is EXCLUDED (fail-closed): verdict_judge / system / unattributed
  wrongs are machine or unproven opinions, never human ground truth — the same
  asymmetry compute_ratios applies to promotion fuel (consequence.py:697-708).
  `approved`/`confirmed`/`expired`/`unknown` rows are not corrections and are
  not harvested (the corpus is the CORRECTION suite, per review §6.2).

FROZEN CONTRACT: a written case file is IMMUTABLE. Re-harvesting must be
idempotent + deterministic — same ledger, byte-identical corpus; new ledger
rows only APPEND new cases. If a regeneration ever disagrees with an existing
frozen file (an append-only violation upstream, or a serialization change
here) the frozen file WINS and the conflict is surfaced loudly (exit 3 in the
CLI) — it is never silently rewritten. Determinism mechanics: no timestamps
anywhere in corpus output; canonical json (sort_keys, indent=2, ensure_ascii);
manifest fingerprint = sha256 over the sorted case-id list.

STORAGE: framework/fidelity/regression_corpus/ (repo tree). Deliberately NOT
memory/golden-evals/ — that dir is germline schg-locked
(cabinet/scripts/germline-lock.sh DIRS) and a growing corpus needs appends;
this dir is the UNLOCKED sibling per the 2026-07-05 lane task.

READ PATH: framework.fidelity.consequence.read_ledger() ONLY — deduped
last-write-wins (a superseding outcome/acted event is the row's final human
word, which is exactly what a correction corpus should freeze), sim-quarantined
(SIE-7 rows can never seed live regression cases), symlink-fenced, and honoring
CABINET_EVENT_LOG_DIR — no second path-resolution rule lives here.

System Python is 3.9.6 — stdlib only, `from __future__ import annotations` for
the modern annotation syntax (matching consequence.py).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from framework.fidelity.consequence import UNSTAMPED_ACTION_TYPE, read_ledger

# Corpus schema version. Bump ONLY with a documented migration story — frozen
# case files are immutable, so a format bump means new files coexist with old
# ones and load_corpus (regression_gate.py) must accept both or migrate.
CASE_FORMAT = 1

# Default corpus location: the UNLOCKED dir next to this module (see module
# docstring — NOT memory/golden-evals, which is schg-locked).
DEFAULT_CORPUS_DIR = Path(__file__).resolve().parent / "regression_corpus"

# The correction kinds this corpus recognizes (module docstring has the
# per-kind provenance). Order matters nowhere at runtime — classification is
# rule-based below — but tests assert the vocabulary stays closed.
CORRECTION_KINDS = ("edit", "skip", "veto", "undo", "human_wrong")

# Evidence prefixes stamped by the ONE acted-verdict builder
# (framework/frontdoor/binder_wire.py::_ACTED_VERDICTS:158-166). Matched with
# startswith on the outcome.evidence string; the builder may append ": <why>"
# so equality would be wrong. If binder_wire ever renames these strings the
# corpus classifies such rows as the honest fallback kind "human_wrong" —
# degraded label sharpness, never a dropped or fabricated correction.
_EVIDENCE_KIND_PREFIXES = (
    ("captain-undo", "undo"),
    ("captain veto", "veto"),
    ("captain edited", "edit"),
)


class CorpusWriteConflict(Exception):
    """A regenerated case disagrees with its already-frozen file. The frozen
    file has been kept verbatim (frozen wins); the caller must surface this —
    it means the ledger mutated (append-only violation) or the serialization
    changed. Raised only by write_corpus(strict=True); the default collects
    conflicts into the summary instead so a batch harvest reports ALL of them."""


# ---------------------------------------------------------------------------
# extraction — ledger row -> correction case
# ---------------------------------------------------------------------------

def _actor_id(event: dict[str, Any]) -> str:
    """Flatten actor to 'kind:id' exactly as compute_ratios does
    (consequence.py:674) so the corpus cell joins the graduation cell."""
    actor = event.get("actor") or {}
    return f"{actor.get('kind')}:{actor.get('id')}"


def _classify_kind(event: dict[str, Any]) -> Optional[str]:
    """Return the correction kind for a ledger row, or None if the row is not
    a human correction (approved / expired / pending / machine-wrong / sim).

    Rule order (dated decision 2026-07-05, see module docstring):
      1. sim rows never classify (defense in depth on top of read_ledger's
         live-mode sim-drop — a quarantined row must not seed a live case).
      2. proposal.decision edited/rejected -> edit/skip (structurally human).
      3. review.verdict 'wrong' + review.source 'verdict_human' -> kind by the
         binder evidence prefix (undo/veto/edit), else human_wrong.
      4. anything else -> None (not a correction).
    """
    if event.get("sim"):
        return None

    decision = (event.get("proposal") or {}).get("decision")
    if decision == "edited":
        return "edit"
    if decision == "rejected":
        return "skip"

    review = event.get("review") or {}
    if review.get("verdict") == "wrong" and review.get("source") == "verdict_human":
        evidence = str((event.get("outcome") or {}).get("evidence") or "")
        for prefix, kind in _EVIDENCE_KIND_PREFIXES:
            if evidence.startswith(prefix):
                return kind
        return "human_wrong"

    return None


def case_id_for(event: dict[str, Any], kind: str) -> str:
    """Deterministic case id: 'case-' + sha256 of the ledger identity tuple +
    kind, truncated to 16 hex chars.

    The identity tuple (actor, action, subject, ts) is the ledger's own
    supersede identity (consequence.py::_identity:473-486), so ONE decided
    proposal / acted card yields ONE case no matter how many times the harvest
    re-runs. Kind participates so a hypothetical row that legitimately carries
    two correction facets can never silently collide. 16 hex chars = 64 bits —
    collision-safe at any plausible corpus size.

    Hash input is the JSON list serialization, NOT a delimiter join (checkpoint
    review 2026-07-05): a subject containing the delimiter could otherwise make
    two distinct identity tuples hash identically — an unambiguous framing per
    field closes that class entirely, and the scheme is frozen from the first
    committed corpus onward (changing it later would orphan every frozen case).
    """
    material = json.dumps([
        _actor_id(event),
        event.get("action", ""),
        event.get("subject", ""),
        event.get("ts", ""),
        kind,
    ], ensure_ascii=True)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"case-{digest}"


def _build_case(event: dict[str, Any], kind: str) -> dict[str, Any]:
    """Assemble the frozen case dict = {situation, human_verdict, cell}.

    Every field is copied (never aliased) from the ledger row; the situation is
    a replay REFERENCE only (no message content exists on the ledger to embed —
    leak-safe by upstream construction, see module docstring)."""
    proposal = event.get("proposal") or {}
    review = event.get("review") or {}
    outcome = event.get("outcome") or {}
    action_type = event.get("action_type")  # may be absent/None (unstamped)
    actor = event.get("actor") or {}

    return {
        "case_format": CASE_FORMAT,
        "case_id": case_id_for(event, kind),
        # The graduation cell this correction disciplines — keyed EXACTLY like
        # compute_ratios (actor flattened, unstamped rows under the visible
        # sentinel so they can never conflate into a measured cell).
        "cell": {
            "actor": _actor_id(event),
            "lane": event.get("lane"),
            "action_type": action_type or UNSTAMPED_ACTION_TYPE,
        },
        # Replay reference: enough to re-gather the situation as-of ts through
        # the harness (subject/refs are the join keys; content is NOT stored).
        "situation": {
            "ts": event.get("ts"),
            "actor": {"kind": actor.get("kind"), "id": actor.get("id")},
            "lane": event.get("lane"),
            "action": event.get("action"),
            "action_type": action_type,
            "subject": event.get("subject"),
            "refs": list(event.get("refs") or []),
            "proposal_required": proposal.get("required"),
        },
        # The frozen human word on this situation.
        "human_verdict": {
            "kind": kind,
            "proposal_decision": proposal.get("decision"),
            "decided_at": proposal.get("decided_at"),
            "review_verdict": review.get("verdict"),
            "review_source": review.get("source"),
            "reviewed_at": review.get("reviewed_at"),
            # The binder/loop evidence string — the human-readable WHY that a
            # future replay-judge shows next to a regression.
            "evidence": outcome.get("evidence"),
        },
    }


def extract_corrections(
    ledger: Optional[list[dict[str, Any]]] = None,
    since: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Harvest ALL human-correction cases from the consequence ledger.

    `ledger` is a test seam (pre-read rows); production passes nothing and
    reads via read_ledger(since=since) — the deduped/sim-fenced canonical
    path, so each supersede family contributes exactly its FINAL state.
    Returns cases sorted by case_id (deterministic output order regardless of
    ledger file iteration order)."""
    rows = ledger if ledger is not None else read_ledger(since=since)
    cases: dict[str, dict[str, Any]] = {}
    for ev in rows:
        if not isinstance(ev, dict):
            continue  # fail-safe: junk rows never crash the harvest
        kind = _classify_kind(ev)
        if kind is None:
            continue
        case = _build_case(ev, kind)
        # Same identity+kind twice in one harvest (possible only when a caller
        # passes a NON-deduped ledger): last one wins, mirroring read_ledger's
        # last-write-wins so both paths agree.
        cases[case["case_id"]] = case
    return [cases[k] for k in sorted(cases)]


# ---------------------------------------------------------------------------
# corpus IO — frozen write + deterministic manifest
# ---------------------------------------------------------------------------

def _canonical_json(obj: Any) -> str:
    """The ONE serialization for corpus files. sort_keys + fixed indent +
    ensure_ascii → byte-identical output across runs/machines/locales, which is
    what makes idempotency checkable with a string compare."""
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def _atomic_write(path: Path, text: str) -> None:
    """tmp-in-same-dir + os.replace so a crash can never leave a torn case
    file (Corridor invariant: state updates are atomic)."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-corpus-")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, str(path))
    except BaseException:
        # best-effort cleanup; the exception propagates (no silent swallow).
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def corpus_fingerprint(case_ids: list[str]) -> str:
    """sha256 over the sorted id list — the manifest's change-detection handle.
    Ids only (not file bodies): the bodies are frozen, so the id set IS the
    corpus identity."""
    joined = "\n".join(sorted(case_ids))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def write_corpus(
    cases: list[dict[str, Any]],
    corpus_dir: Optional[Path] = None,
    strict: bool = False,
) -> dict[str, Any]:
    """Write harvested cases into the frozen corpus. Idempotent + append-only.

    Per case file cases/<case_id>.json:
      * absent            -> written (atomic).
      * present, identical-> untouched (idempotent no-op).
      * present, DIFFERENT-> FROZEN WINS: file untouched, id recorded under
        'conflicts' (strict=True raises CorpusWriteConflict instead). A
        conflict is an integrity alarm — see CorpusWriteConflict docstring.

    manifest.json is rewritten every run but is deterministic (sorted ids,
    kind counts, fingerprint; NO timestamps) so an unchanged corpus yields a
    byte-identical manifest. The manifest indexes EVERYTHING on disk (existing
    frozen cases + this harvest), so partial harvests (--since) never shrink it.

    Returns {"written": [...], "unchanged": [...], "conflicts": [...],
             "total_on_disk": int, "manifest": <manifest dict>}.
    """
    corpus_dir = Path(corpus_dir) if corpus_dir is not None else DEFAULT_CORPUS_DIR
    cases_dir = corpus_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    unchanged: list[str] = []
    conflicts: list[str] = []

    for case in cases:
        cid = case["case_id"]
        path = cases_dir / f"{cid}.json"
        payload = _canonical_json(case)
        if path.exists():
            try:
                existing = path.read_text()
            except OSError:
                # Unreadable frozen file: NEVER overwrite what we cannot
                # verify — treat as conflict (fail-safe, frozen wins).
                existing = None
            if existing == payload:
                unchanged.append(cid)
                continue
            if strict:
                raise CorpusWriteConflict(
                    f"{cid}: regenerated case differs from frozen file {path}"
                )
            conflicts.append(cid)
            continue
        _atomic_write(path, payload)
        written.append(cid)

    # Manifest over the FULL on-disk corpus (not just this harvest's slice).
    all_ids = sorted(p.stem for p in cases_dir.glob("case-*.json"))
    kind_counts: dict[str, int] = {}
    for cid in all_ids:
        try:
            body = json.loads((cases_dir / f"{cid}.json").read_text())
            kind = (body.get("human_verdict") or {}).get("kind") or "unknown"
        except (OSError, json.JSONDecodeError, AttributeError):
            kind = "unreadable"  # visible, never silently dropped
        kind_counts[kind] = kind_counts.get(kind, 0) + 1

    manifest = {
        "format": CASE_FORMAT,
        "case_count": len(all_ids),
        "case_ids": all_ids,
        "kinds": {k: kind_counts[k] for k in sorted(kind_counts)},
        "fingerprint": corpus_fingerprint(all_ids),
    }
    _atomic_write(corpus_dir / "manifest.json", _canonical_json(manifest))

    return {
        "written": written,
        "unchanged": unchanged,
        "conflicts": conflicts,
        "total_on_disk": len(all_ids),
        "manifest": manifest,
    }
