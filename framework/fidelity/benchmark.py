"""Held-out case builder (the F1 benchmark - design §95-99).

The validation universe is the send-1to1-reply lane in autonomy_outcomes.jsonl
(~266 rows). Those rows are CUT-OFF in their text fields, so F1 does NOT score
their text. It rebuilds full paired cases from 3-People/*/conversations.md via
retrodiction.extract_cases (leak-safe, full thread_before) and uses the
autonomy rows only to SIZE/sanity-check the universe (ground finding: rebuild
from conversations.md, not from the cut-off rows).

F1 supports exactly the reply cell ('send-1to1-reply', 'reply'); other
(lane, decision_type) pairs raise NotImplementedError and land in F3
(Monday activity-log connector for triage, etc.)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from framework.fidelity import retro
from framework.fidelity.officer_prompt import intent_and_context
from framework.fidelity.types import Case

_SUPPORTED: set[tuple[str, str]] = {("send-1to1-reply", "reply")}

_DEFAULT_OUTCOMES = Path(
    os.environ.get(
        "CABINET_AUTONOMY_OUTCOMES",
        str(Path.home() / ".screenpipe" / "state" / "autonomy_outcomes.jsonl"),
    )
).expanduser()


def load_autonomy_rows(path: Path | None = None,
                       lane: str = "send-1to1-reply") -> list[dict]:
    """Return the autonomy_outcomes rows for the given lane (metadata only -
    text fields are cut-off and must NOT be scored)."""
    p = path or _DEFAULT_OUTCOMES
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("lane") == lane:
            rows.append(r)
    return rows


def validation_count(path: Path | None = None,
                     lane: str = "send-1to1-reply") -> int:
    """Size of the validation universe for the lane (the ~266-row count)."""
    return len(load_autonomy_rows(path=path, lane=lane))


def build_cases(lane: str = "send-1to1-reply", decision_type: str = "reply",
                n: int = 24, window=None, people_dir: Path | None = None) -> list[Case]:
    """Build held-out Cases for the (lane, decision_type) cell.

    F1: reconstructs full threads from conversations.md (leak-safe) via the
    retrodiction extractor, mapped onto the Case model. `window` is accepted
    for design-interface parity (reserved for time-windowed extraction in
    later cells). Unsupported cells raise NotImplementedError."""
    if (lane, decision_type) not in _SUPPORTED:
        raise NotImplementedError(
            f"F1 supports only {sorted(_SUPPORTED)}; "
            f"({lane!r}, {decision_type!r}) lands in F3.")
    rcs = retro.extract_cases(n_cases=n, people_dir=people_dir)
    cases = [Case.from_retro_case(rc, lane=lane, decision_type=decision_type)
             for rc in rcs]
    return [_enrich_intent(c) for c in cases]


def _enrich_intent(case: Case) -> Case:
    """Cache the reconstructed as-of-cutoff intent on the Case (design §5, §1.6).

    The intent is a PURE function of the pre-cutoff thread: it is computed by
    ``officer_prompt.intent_and_context``, which reads ``case.thread_before``
    ONLY and NEVER ``case.real_reply`` (the held-out ground truth). Real-world
    facts the situation implicates (the house, the lawn size) enter the harness
    only through the leak-guarded ``gather_cutoff_context`` path at officer time
    (§2) — they are NOT baked into the benchmark intent here.

    Enrichment is LAZY/fill-if-empty: an already-populated ``case.intent`` (a
    refreshed benchmark) is preserved, and if it is still empty at score time
    ``scorer.score`` recomputes it the same way. The cached value lives on the
    in-memory Case object only; nothing here writes it to the embeddings/brain
    index, so — like the held-out set — it stays out of the index and the clone
    cannot memorize it (parent §274-276)."""
    if not case.intent:
        case.intent = intent_and_context(case)["reconstructed_intent"]
    return case
