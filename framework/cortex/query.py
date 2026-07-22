"""The as-of temporal query API — "what did we believe, as of when, on what
evidence" over the shadow bitemporal projection.

COG-2 UNIT 2. Plan: docs/plans/cognitive-core-phase-2-contract-2026-07-22.md
§5.5 / §5.6 (query law, contradiction + unknown), §5.2 (K vs supersession
authority), §7.4 (scope fence), §8 sim 2 + sim 3.

TWO AXES (§4): a query fences on observation_time (transaction time) and/or
source_time (valid time), inclusive-≤ (leak predicate ts > cutoff, C-F8).
Absent observation_time is EXCLUDED from an observation-fenced answer (§5.2
A-M5), included only in an unfenced (observation=None) query.

DERIVED STATE IS RE-DERIVED PER CUTOFF (C-F7): status / superseded_by /
contradicts are recomputed over the sub-history observation_time ≤ cutoff via
engine.resolve_relationships — NEVER read back from the stored full-history
status. So an answer at an early cutoff shows a belief as `asserted` even though
a later correction eventually superseded it. Closure holds by construction:
re-derivation only links beliefs within the fenced sub-history.

NEVER-A-SCORE — the SHAPE guard (§5.6 (2), G-F3): the API returns ONLY the full
tuple (value?, source_trust, provenance, status, conflict_set); confidence is
carried INSIDE that tuple, always paired with source_trust — there is NO
bare-scalar confidence accessor. A standing ratchet (test_cog2_contradiction.py)
fails the suite if this module ever grows one.

THE UNKNOWN / PURGED / DENIED TRIAD (§5.6, C-F11) is explicit:
  * zero-evidence subject       -> AsOfResult.is_unknown() (status "unknown")
  * subject whose only belief is source_purged -> a status-bearing view (NEVER
    unknown — purged ≠ ignorant)
  * missing / unresolvable / foreign scope -> ScopeError (HARD ERROR — denial
    never masquerades as ignorance, never empty-success)

Documented MUTANT SEAMS (kwargs) let the sims prove each negative control bites:
  fence_axis="source_time" (temporal leak), rederive=False (stored-final-status
  server), scope_mode="lenient" (denial-as-ignorance), unknown_mode="default"
  (fabricated answer), and the fold-shared lineage="merged"/"correlation".

SHADOW: pure over an in-memory Belief list; the store loader is read-only; no
authority write, no event, no clock, no environment read. Serve-time store-hash
binding (C-F15) is a later COG-2 unit.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from framework.cortex import belief as _belief
from framework.cortex import engine as _engine

# Explicit zero-evidence sentinel (§5.6). NEVER a default/quality value.
UNKNOWN = "unknown"

# Canonical stored-timestamp shape (mirrors envelope.py _UTC_SECOND_RE). A cutoff
# MUST match this — a legal-but-non-canonical ISO string (e.g. "+00:00" instead of
# "Z", or fractional seconds) or garbage would fence OPEN (silently exclude/include
# the wrong boundary), so a non-canonical cutoff is a HARD ERROR, not a silent
# mis-fence. The denial-never-masquerades discipline applies to cutoffs too.
_CANON_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# Scope tokens that are structurally not a resolvable local scope (mirrors the
# envelope v2 sentinel vocabulary; kept local so query.py imports no validator).
_SCOPE_SENTINELS = frozenset({"", "*", "default", "global", "none", "null", "unknown"})


class ScopeError(Exception):
    """A query whose scope is missing, unresolvable, or foreign (§7.4). A HARD
    ERROR — denial is never returned as an empty/unknown success."""


@dataclass(frozen=True)
class BeliefView:
    """The as-of query's per-belief result shape (§5.6) — ALWAYS the full tuple
    (value?, source_trust, provenance, status, conflict_set), never a bare
    scalar. `confidence` is carried here bundled with `source_trust`; it is never
    exposed by any standalone accessor (the never-a-score latch). `conflict_set`
    holds the belief_ids this belief coexists-and-conflicts with; look each up
    among the same answer's `views` for its per-side provenance + confidence."""
    belief_id: str
    subject_key: str
    dimension: str
    status: str
    value: Optional[dict]
    claim_completeness: str
    source_time: Optional[str]
    observation_time: Optional[str]
    confidence: Optional[int]
    source_trust: dict
    provenance: dict
    supersedes: tuple[str, ...] = field(default_factory=tuple)
    superseded_by: Optional[str] = None
    conflict_set: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AsOfResult:
    """One as-of answer for one subject (+ optional dimension). `views` are the
    CURRENT beliefs (the re-derived heads) within the cutoff — empty iff unknown;
    two-or-more iff contradicted. `evidence_ids` is the fenced sub-history the
    answer was derived from (the closure set: every belief_id any view links to
    resolves within it)."""
    subject_key: str
    dimension: Optional[str]
    status: str
    views: tuple[BeliefView, ...]
    evidence_ids: frozenset[str]

    def is_unknown(self) -> bool:
        return self.status == UNKNOWN


# A fabricated answer the unknown_mode="default" MUTANT returns instead of an
# explicit unknown — the never-default negative control.
_DEFAULT_VIEW = BeliefView(
    belief_id="", subject_key="", dimension="", status=_belief.STATUS_ASSERTED,
    value=None, claim_completeness=_belief.COMPLETENESS_INLINE, source_time=None,
    observation_time=None, confidence=None, source_trust={}, provenance={})


def _scope_ok(scope) -> bool:
    if not isinstance(scope, dict):
        return False
    cab = scope.get("cabinet_id")
    return isinstance(cab, str) and cab not in _SCOPE_SENTINELS


def _unknown(subject_key: str, dimension: Optional[str], unknown_mode: str) -> AsOfResult:
    if unknown_mode == "default":
        # MUTANT: invent a default belief for a zero-evidence subject.
        return AsOfResult(subject_key, dimension, _belief.STATUS_ASSERTED,
                          (_DEFAULT_VIEW,), frozenset())
    return AsOfResult(subject_key, dimension, UNKNOWN, (), frozenset())


def _axis_value(b: _belief.Belief, fence_axis: str) -> Optional[str]:
    if fence_axis == "source_time":
        # MUTANT (temporal leak): fence the observation cutoff on VALID time —
        # a later-observed correction whose valid time is old leaks into the past.
        return b.source_time
    return b.observation_time                       # CORRECT: transaction time


def _fence(beliefs: list, *, observation: Optional[str], source: Optional[str],
           fence_axis: str) -> list:
    """Keep beliefs within both cutoffs (inclusive-≤; leak predicate ts > cutoff,
    C-F8). An observation cutoff excludes absent-observation_time beliefs (§5.2
    A-M5); an unfenced (None) observation keeps them."""
    kept = []
    for b in beliefs:
        if observation is not None:
            ts = _axis_value(b, fence_axis)
            if ts is None or ts > observation:
                continue
        if source is not None:
            if b.source_time is None or b.source_time > source:
                continue
        kept.append(b)
    return kept


def _as_item(b: _belief.Belief) -> dict:
    return {"belief_id": b.belief_id, "subject_key": b.subject_key,
            "dimension": b.dimension, "provenance": b.provenance,
            "observation_time": b.observation_time}


def _view(b: _belief.Belief, sup_by: dict, sup: dict, con: dict, *,
          rederive: bool) -> BeliefView:
    purged = b.claim_completeness == _belief.COMPLETENESS_PURGED
    status = (_engine.derive_status(purged=purged, superseded_by=sup_by[b.belief_id],
                                    contradicts=con[b.belief_id])
              if rederive else b.status)           # rederive=False MUTANT: stored status
    return BeliefView(
        belief_id=b.belief_id, subject_key=b.subject_key, dimension=b.dimension,
        status=status, value=b.claim, claim_completeness=b.claim_completeness,
        source_time=b.source_time, observation_time=b.observation_time,
        confidence=b.confidence, source_trust=dict(b.source_trust),
        provenance=dict(b.provenance), supersedes=tuple(sup[b.belief_id]),
        superseded_by=sup_by[b.belief_id], conflict_set=tuple(con[b.belief_id]))


def as_of(beliefs: Iterable[_belief.Belief], subject_key: str, *, scope,
          dimension: Optional[str] = None, observation: Optional[str] = None,
          source: Optional[str] = None, fence_axis: str = "observation",
          rederive: bool = True, scope_mode: str = "strict",
          unknown_mode: str = "explicit", supersession_order: str = "source",
          lineage: str = "producer") -> AsOfResult:
    """Answer "as of the given cutoff(s), in the given scope, what is believed
    about subject_key" — returning the current head(s) as full BeliefViews, an
    explicit unknown, or a HARD ERROR for an unresolvable scope."""
    beliefs = list(beliefs)

    # 0. INPUT fence: a caller cutoff MUST be canonical YYYY-MM-DDTHH:MM:SSZ. A
    # legal-but-non-canonical ISO ("...+00:00") or garbage would fence OPEN against
    # the canonical stored timestamps — hard-error, never a silent mis-fence.
    for _label, _cut in (("observation", observation), ("source", source)):
        if _cut is not None and not _CANON_TS_RE.match(_cut):
            raise ValueError(
                f"{_label} cutoff {_cut!r} is not a canonical "
                "YYYY-MM-DDTHH:MM:SSZ timestamp (a non-canonical cutoff fences "
                "open — pin it or hard-error)")

    # 1. SCOPE gate (§7.4) — denial is a HARD ERROR, never empty-success.
    if not _scope_ok(scope):
        if scope_mode == "lenient":                # MUTANT: denial-as-ignorance
            return _unknown(subject_key, dimension, unknown_mode)
        raise ScopeError("query scope is missing or unresolvable "
                         "(a scoped store is never queried unscoped)")
    cabinet_id = scope["cabinet_id"]

    subject_beliefs = [b for b in beliefs if b.subject_key == subject_key
                       and (dimension is None or b.dimension == dimension)]
    in_scope = [b for b in subject_beliefs
                if b.provenance.get("cabinet_id") == cabinet_id]
    if subject_beliefs and not in_scope:
        # the subject exists ONLY in a foreign cabinet — a mismatch, HARD ERROR
        # (never silently coerced to unknown — that would leak cross-cabinet
        # existence as ignorance).
        if scope_mode == "lenient":                # MUTANT: denial-as-ignorance
            return _unknown(subject_key, dimension, unknown_mode)
        raise ScopeError(f"subject {subject_key!r} is not in cabinet "
                         f"{cabinet_id!r} (cross-cabinet, fail closed)")

    # 2. zero-evidence subject => EXPLICIT unknown (§5.6).
    if not in_scope:
        return _unknown(subject_key, dimension, unknown_mode)

    # 3. temporal fence (both axes).
    fenced = _fence(in_scope, observation=observation, source=source,
                    fence_axis=fence_axis)
    if not fenced:
        return _unknown(subject_key, dimension, unknown_mode)

    # 4. RE-DERIVE status/links over the fenced sub-history (C-F7) — the head
    # selection and links are always re-derived; rederive=False only swaps the
    # per-view STATUS label to the stored full-history one (the mutant).
    sup_by, sup, con = _engine.resolve_relationships(
        [_as_item(b) for b in fenced], supersession_order=supersession_order,
        lineage=lineage)
    evidence_ids = frozenset(b.belief_id for b in fenced)

    heads = [b for b in fenced if sup_by[b.belief_id] is None]
    views = tuple(sorted((_view(b, sup_by, sup, con, rederive=rederive)
                          for b in heads), key=lambda v: v.belief_id))

    # Result-level status is CONTRADICTION-driven, not head-COUNT-driven: multiple
    # current heads are usually distinct DIMENSIONS/facets of one subject (queried
    # with dimension=None — the outbox emits status + occurrence per task), each its
    # own asserted head; that is not a contradiction. A contradiction is a view that
    # carries a conflict_set (independent-lineage incompatible claims on ONE
    # dimension). Multi-dimension aggregation rule (pinned): source_purged iff EVERY
    # facet is purged, else asserted (>=1 live facet).
    if not views:
        status = UNKNOWN
    elif any(v.conflict_set for v in views):
        status = _belief.STATUS_CONTRADICTED
    elif len(views) == 1:
        status = views[0].status
    else:
        _facet_statuses = {v.status for v in views}
        status = (_belief.STATUS_SOURCE_PURGED
                  if _facet_statuses == {_belief.STATUS_SOURCE_PURGED}
                  else _belief.STATUS_ASSERTED)
    return AsOfResult(subject_key=subject_key, dimension=dimension, status=status,
                      views=views, evidence_ids=evidence_ids)


def load_beliefs(jsonl_path) -> list:
    """Read a stored beliefs.jsonl into Belief objects (the serve path, read-
    only). Serve-time store-hash binding (C-F15) is a later COG-2 unit — this
    loader trusts a store the caller has already verified."""
    return [_belief.belief_from_row(row)
            for row in _engine.read_beliefs_jsonl(jsonl_path)]
