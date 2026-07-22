"""framework.objectives.states — the ORDERED, TOTAL edge-state transition
function and the canonical structural-failure type (COG-3 contract rev-1 §5.2).

Epistemic state is DERIVED AT COMPILE, never stored (the C-F7 re-derivation idiom
lifted one level): a pure function of an edge's bound cortex belief-VIEWS at the
build cutoff. Evaluated over SERVED claim bytes only (BeliefView.value) — NO
fidelity import (§6.4): the discriminator is the consequence domain's own
`review.{verdict,source}` vocabulary, carried whole in the served row.

This module imports NO cortex symbol: BeliefView instances arrive as plain
objects and are read by attribute (value/subject_key/belief_id/provenance/
conflict_set/claim_completeness). The only internal import is the digest dialect
(model.digest) used to RECOMPUTE the consequence identity for the verified-join.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; U1 (the derivation core).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from framework.objectives import model

# --- the derived internal states (§5.2) — the ONLY tokens the function yields ---
STATE_HYPOTHESIZED = "hypothesized"                       # P1 / P4 / P6
STATE_FALSIFIED = "falsified"                             # P2
STATE_INTERVENTION_SUPPORTED = "intervention_supported"  # P3
STATE_OBSERVATIONALLY_SUPPORTED = "observationally_supported"  # P5
STATE_UNKNOWN = "unknown"                                 # answer-level (never stored)

FLAG_CONTESTED = "contested"                     # P1
FLAG_DIRECTION_CONTESTED = "direction_contested"  # P4

# The frozen graph-owned promotion-fuel constant (§6.4): human verdicts ONLY —
# the Captain's or any other person's, surfaced via internal/external comms; never
# a machine/LLM (verdict_judge / verdict_gate / system / absent are fail-closed
# inert). The §3 drift-tripwire test binds this to consequence.py:126's
# _REVIEW_SOURCES so a domain vocabulary change surfaces in CI.
HUMAN_VERDICT_SOURCE = "verdict_human"

_CONSEQUENCE_PREFIX = "consequence/"
_PURGED_COMPLETENESS = "purged"        # framework.cortex.belief.COMPLETENESS_PURGED
_PURGED_STATUS = "source_purged"       # framework.cortex.belief.STATUS_SOURCE_PURGED
_CONSEQUENCE_STREAM_RANK = 1           # engine.RANK_TABLE["consequence"] — the verified-join stream


@dataclass(frozen=True)
class EdgeState:
    """The derived state of one causal edge: the internal state token + the set of
    answer FLAGS surfaced beside it (never extra states)."""
    state: str
    flags: frozenset = field(default_factory=frozenset)


class BuildFailure(Exception):
    """The canonical structural-failure type (§4.2/§5.1(3)): a binding whose
    subject_key is out of admissible_subjects, or an evidence ref that does not
    resolve in the as_of closure. Never a silent skip — an edge cannot cite
    topically-unrelated or dangling evidence in ANY state."""


def _is_purged(view) -> bool:
    """A source_purged view is inert in EVERY predicate (neither support nor
    refutation) — visible in lineage, excluded here."""
    return (getattr(view, "claim_completeness", None) == _PURGED_COMPLETENESS
            or getattr(view, "status", None) == _PURGED_STATUS)


def _review_of(view):
    """The `review` sub-object of the served claim, or None (observation/bare)."""
    value = getattr(view, "value", None)
    return value.get("review") if isinstance(value, dict) else None


def _verified_join(view, join_spec) -> bool:
    """verified-join(b) (§5.2b): the view is a consequence-stream head (stream_rank
    == 1) AND (i) the recorder digest recomputed from the claim's own
    (actor 'kind:id', action, subject, ts) identity equals the <identity-digest>
    suffix of its subject_key AND (ii) that (actor,action,subject) is in the edge's
    join_spec. The join is MACHINE-CHECKED from the served bytes, never declared.

    The two limbs fail DIFFERENTLY (§5.2b): a limb-(i) mismatch is a FORGED
    subject/claim pairing — the claim is not the row its subject names — a
    structural BuildFailure, never a silent demotion to direction fuel. A limb-(ii)
    mismatch is HONEST evidence about a DIFFERENT intervention — merely non-verified
    (returns False; the corpus's mismatched-join cells cap it at P5, never raise)."""
    provenance = getattr(view, "provenance", None) or {}
    if provenance.get("stream_rank") != _CONSEQUENCE_STREAM_RANK:
        return False
    value = getattr(view, "value", None)
    if not isinstance(value, dict):
        return False
    subject_key = getattr(view, "subject_key", "") or ""
    if not subject_key.startswith(_CONSEQUENCE_PREFIX):
        return False
    actor = value.get("actor")
    if isinstance(actor, dict):
        actor_id = f"{actor.get('kind')}:{actor.get('id')}"
    else:
        actor_id = f"{actor}:"                       # mirrors consequence._identity
    action = value.get("action", "")
    subject = value.get("subject", "")
    ts = value.get("ts", "")
    # limb (i): the subject_key must NAME the row it carries — a forged pairing is
    # a STRUCTURAL build failure (§5.2b), never a silent demotion to direction fuel.
    recomputed = model.digest([actor_id, action, subject, ts])
    if subject_key[len(_CONSEQUENCE_PREFIX):] != recomputed:
        raise BuildFailure(
            f"forged consequence identity: subject_key {subject_key!r} does not "
            f"name its own (actor,action,subject,ts) row (recomputed {recomputed!r})"
            " — a claim that is not the row its subject names is a structural build "
            "failure (§5.2b limb i)")
    # limb (ii): the claim's identity must be an expected matcher of THIS edge — a
    # miss here is honest evidence about a different intervention (non-verified).
    return (actor_id, action, subject) in set(join_spec)


def _direction(view, expected_effect):
    """The adapter-pinned movement reading of a claim (§5.2 direction predicates):
    'supporting' | 'contradicting' | None (direction-inert, ruling R-B).
      * a review-bearing claim reads FROM the verdict: confirmed -> supporting,
        wrong -> contradicting (the coupling P5's machine/absent-source-confirm cap
        requires);
      * an observed_effect claim reads directly: supporting iff the effect is the
        expected effect OR the neutral 'maintain' (the consistent-OR-NEUTRAL
        clause), contradicting otherwise;
      * a verified-join-eligible BARE consequence record (neither review nor
        observed_effect) has NO reading — execution-happened is not effect-evidence
        (else activity volume mints support — Goodhart by the back door)."""
    value = getattr(view, "value", None)
    if not isinstance(value, dict):
        return None
    review = value.get("review")
    if isinstance(review, dict):
        verdict = review.get("verdict")
        if verdict == "confirmed":
            return "supporting"
        if verdict == "wrong":
            return "contradicting"
        return None
    if "observed_effect" in value:
        effect = value.get("observed_effect")
        if effect == expected_effect or effect == "maintain":
            return "supporting"
        return "contradicting"
    return None


def derive_edge_state(edge, bound_views, cutoff) -> EdgeState:
    """The §5.2 ordered TOTAL function (first matching rule wins,
    P1 > P2 > P3 > P4 > P5 > P6). `edge` exposes the EdgeSpec attributes
    (authored / expected_effect / assumptions / admissible_subjects / join_spec /
    evidence_bindings); `bound_views` are the real BeliefViews the bindings
    resolved to; `cutoff` is the canonical build cutoff the views were fenced at.

    Raises BuildFailure for a structural binding violation (out-of-admissible or
    dangling), evaluated over EVERY authored binding BEFORE any state is derived."""
    # answer-level explicit `unknown` — no edge authored (never stored, §5.2).
    if not getattr(edge, "authored", True):
        return EdgeState(STATE_UNKNOWN, frozenset())

    # structural guards (§4.2/§5.1(3)) — over every AUTHORED binding.
    served_ids = {getattr(view, "belief_id", None) for view in bound_views}
    admissible_subjects = frozenset(edge.admissible_subjects)
    for ref in edge.evidence_bindings:
        if ref.subject_key not in admissible_subjects:
            raise BuildFailure(
                f"binding subject_key {ref.subject_key!r} is not in the edge's "
                "admissible_subjects — an edge cannot cite topically-unrelated "
                "evidence (§4.2 C-M3a)")
        if ref.belief_id not in served_ids:
            raise BuildFailure(
                f"dangling evidence binding {ref.belief_id!r}: it does not resolve "
                "in the as_of closure (§5.1(3), never a silent empty set)")

    # stray-view guard: every bound view must be NAMED by an authored binding — an
    # injected view no binding cites is unvalidated evidence, a structural build
    # failure (§4.2/§5.1(3)). A zero-binding edge with empty bound_views still
    # derives P6: the loop simply does not run.
    binding_subjects = {ref.subject_key for ref in edge.evidence_bindings}
    for view in bound_views:
        if getattr(view, "subject_key", None) not in binding_subjects:
            raise BuildFailure(
                f"stray bound view {getattr(view, 'subject_key', None)!r}: no "
                "authored binding of this edge names it (§4.2/§5.1(3))")

    join_spec = tuple(edge.join_spec)
    expected_effect = edge.expected_effect
    # an assumption is real only if a non-empty string survives strip — a
    # placeholder like ("",) can never UNLOCK P3/P5 promotion (§4.2 honesty).
    assumptions_present = any(
        isinstance(a, str) and a.strip() for a in edge.assumptions)

    any_conflict = False
    any_human_confirm = False
    any_human_wrong = False
    any_machine_contested = False
    any_supporting = False
    any_contradicting = False

    for view in bound_views:
        if _is_purged(view):
            continue                                 # inert in every predicate
        if getattr(view, "conflict_set", None):
            any_conflict = True
        review = _review_of(view)
        if isinstance(review, dict) and _verified_join(view, join_spec):
            verdict = review.get("verdict")
            source = review.get("source")
            if verdict == "confirmed" and source == HUMAN_VERDICT_SOURCE:
                any_human_confirm = True             # the ONLY promotion fuel
            elif verdict == "wrong" and source == HUMAN_VERDICT_SOURCE:
                any_human_wrong = True               # the ONLY refutation fuel
            elif verdict == "wrong":
                any_machine_contested = True         # demotion-grade, never refute
        reading = _direction(view, expected_effect)
        if reading == "supporting":
            any_supporting = True
        elif reading == "contradicting":
            any_contradicting = True

    # P1: contested ground beats EVERYTHING (a bound conflict_set, OR two human
    # verdicts disagreeing) — certainty is never manufactured, in either direction.
    if any_conflict or (any_human_confirm and any_human_wrong):
        return EdgeState(STATE_HYPOTHESIZED, frozenset({FLAG_CONTESTED}))
    # P2: falsified — a human-wrong on a verified join (the SAME bar as promotion).
    if any_human_wrong:
        return EdgeState(STATE_FALSIFIED, frozenset())
    # P3: intervention_supported — the FULL triple (human-confirm + verified-join +
    # non-empty assumptions). Reachable by EXACTLY this rule.
    if any_human_confirm and assumptions_present:
        return EdgeState(STATE_INTERVENTION_SUPPORTED, frozenset())
    # P4: hypothesized+direction_contested — observation/machine judgment WEAKENS an
    # edge back to hypothesis but never mints falsified (the mirror of :108).
    if any_contradicting or any_machine_contested:
        return EdgeState(STATE_HYPOTHESIZED, frozenset({FLAG_DIRECTION_CONTESTED}))
    # P5: observationally_supported — the CAP for all non-human-verdict evidence,
    # gated by non-empty assumptions (ruling R-A: assumptions gate P3 AND P5).
    if any_supporting and assumptions_present:
        return EdgeState(STATE_OBSERVATIONALLY_SUPPORTED, frozenset())
    # P6: an authored assertion with no admissible above-hypothesized support.
    return EdgeState(STATE_HYPOTHESIZED, frozenset())
