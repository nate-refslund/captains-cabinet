#!/usr/bin/env python3.12
"""Capture→action lane runner — the live shell around action_lane's pure core.

Pivot of run_draft_lane.py per the 2026-07-03 Captain ruling: same singleton
lock, same ·pid· card + cabinet:action:<pid> store + consequence-ledger
proposal, ACTION payloads instead of reply drafts. Propose-only: every card
awaits the Captain's approve/edit:/skip: through the (fixed) binder; approves execute
via framework.frontdoor.action_exec.

Signals v1 (read-only, newest-first, fenced to a recency window): open
commitments, fresh meeting notes, fresh decisions — the section table + vault
layout live in framework/sources/vault_signals.py since the CG-2 extract
(2026-07-07). The gather step is `as_of`-shaped so the retrodiction harness
can drive the same path with a historical clock.

Ask budget (germline batch 2026-07-04 — supersedes the 2026-07-03 "no
attention quota" note that used to live here): presented asks are throttled at
the card-emit seam to the plist-ratified contract
(cabinet/launchd/com.cabinet.action-lane.plist: "≤2 action cards per run
(≤5/day Redis budget)") — until this batch that budget existed only as
documentation. A withheld card writes NOTHING (no ledger row / Redis record /
Telegram), so it re-proposes naturally while its evidence stays fresh. Acted
(act-first) cards are tells with undo handles, not asks — they ride the
estate/per-kind caps (actfirst_canary) and never consume the ask budget.
MAX_PER_RUN stays the technical anti-runaway bound on proposal GENERATION.
Open cards older than ~36h auto-expire graduation-neutrally (see
_expire_stale_cards). The quality bar still lives in the proposer prompt
(genuine need + SOLVE-shaped chains).

Run: python3.12 framework/acting/run_action_lane.py [--dry-run]
  --dry-run: gather + propose + print the would-be cards; no Telegram, no
  ledger, no Redis writes. The eyeball gate before the scheduled lane.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from framework.acting import action_lane, lane_dedup as ld  # noqa: E402
from framework.attention import acted_overlay  # noqa: E402  # P2 world-grounding
from framework.env import vault_dir, shared_env_path, product_brain_dir  # noqa: E402
from framework.acting.loop import (  # noqa: E402
    expire_event, pending_proposals, proposal_event, proposal_id)
from framework.fidelity.consequence import emit_consequence, read_ledger  # noqa: E402
from framework.frontdoor import actfirst_canary  # noqa: E402  # cid-echo suppression (TI-7)
from framework.sources import vault_signals  # noqa: E402  # CG-2 gather extract
# TI-3 act-first gate seams (all already committed): the executor act-first path,
# the reversal-eligibility perimeter, the veto registry, the receipt surface.
# _canonical_sha/_surfaces_path are consumed (never redefined) so the TOCTOU
# fingerprint and the confidence-floor knob share the executor's exact bytes —
# one hash function, one config file, no drift.
from framework.frontdoor import action_undo, veto_registry, tell_surface  # noqa: E402
from framework.frontdoor.action_exec import (  # noqa: E402
    deliver_action, _canonical_sha, _surfaces_path)


# COVERED-EVIDENCE WINDOW (P1 hardening, adversarial review 2026-07-08): the
# covered set used to read the ALL-TIME ledger, so one long-decided card
# citing a rolling per-product digest file (the commits/deployment digests)
# muted every FUTURE situation grounded in that file forever — the exact
# false-positive direction the attention-gateway spec names as the bad one.
# Only cards younger than this many days suppress; a re-worded duplicate can
# therefore re-appear after the window (bounded annoyance — P4 standing
# cards absorb it), while a genuinely new same-file situation is muted at
# most this long. <=0 disables the window (all-time, the old behavior).
# Fail-SAFE parse: an unparsable/non-finite env value falls back to the
# default rather than crashing the lane at import (a bad knob must not kill
# the lane) or silently disarming dedup (inf → empty covered set via the
# except; nan → window off — both quiet failure modes, review cp1 Low-1).
def _covered_window_days() -> float:
    raw = os.environ.get("CABINET_COVERED_EVIDENCE_WINDOW_D", "14")
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return 14.0
    import math
    return val if math.isfinite(val) else 14.0


COVERED_WINDOW_D = _covered_window_days()


def _covered_since() -> "str | None":
    """The covered window's inclusive ISO floor (None = all-time). Shared by
    covered_evidence_refs and the P2 acted-overlay so both planes read the
    same clock."""
    if COVERED_WINDOW_D <= 0:
        return None
    return (dt.datetime.now(dt.timezone.utc)
            - dt.timedelta(days=COVERED_WINDOW_D)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")


def covered_evidence_refs() -> frozenset:
    """Evidence refs carried by prior action cards inside the covered window
    (open or decided) — the stable dedup identity across runs (LLM subject
    slugs drift; refs don't). Windowed per COVERED_WINDOW_D above."""
    refs: set = set()
    try:
        for ev in read_ledger(since=_covered_since()):
            act = ev.get("action") or ""
            # 'action-card' = a presented proposal row; 'acted:<kind>' = an
            # unattended act row. ACTED-EVENT IDENTITY FIX (germline batch
            # 2026-07-05): acted rows moved off 'action-card' onto the canonical
            # acted:<kind> identity and carry the proposal's evidence refs
            # (appended in action_exec._emit_acted_consequence), so BOTH must feed
            # cross-run dedup or an acted situation would re-propose.
            if act == "action-card" or act.startswith("acted:"):
                refs.update(r for r in (ev.get("refs") or []) if isinstance(r, str))
    except Exception:
        pass   # fail-open here is safe: slug dedup still applies
    return frozenset(refs)

# Captain-ratified directions.yml (mission/instruments/bets/not_goals per lane) —
# injected into the proposer prompt + used to validate every card's direction_fit.
DIRECTIONS_PATH = Path(__file__).resolve().parents[2] / "instance" / "config" / "directions.yml"
LOCK_PATH = "/tmp/cabinet-action-lane.lock"
# MAX_PER_RUN is a technical anti-runaway bound on proposal GENERATION only (a
# berserk LLM must not flood 20 cards in one tick). It deliberately exceeds the
# ask budget below: when act-first is live, acted cards (which are NOT asks)
# can consume the surplus while presented asks stay throttled.
MAX_PER_RUN = 8
# ASK BUDGET — scope: PRESENTED asks only (cards landing on the Captain's Telegram
# awaiting a verdict); acted act-first cards are tells bounded by the
# estate/per-kind caps in actfirst_canary instead.
#
# FIELD-TEST OVERRIDE (the Captain, 2026-07-05 — feedback_field_test_disturb_max):
# the Cabinet's operating phase is FIELD-TEST — "surface EVERYTHING, no ≤5/day
# throttle, no quieting" — so the org runs hard, generates real labels (incl.
# the first negatives), and reveals where it needs improvement. Since the lane
# is act-first (not propose-first), more surfacing ≠ more asking — it is more
# VISIBILITY into what the org already did. So these caps are lifted to
# non-binding: they no longer withhold a card a real workload produces. They
# are NOT removed — the counter still runs (ask-volume/day is exactly the
# field-test signal we want) and the high ceilings remain a berserk-loop
# backstop (a wedged LLM still can't fire thousands of Telegrams). This is a
# PHASE choice ("for now"); re-tighten toward disturb-less once acceptance/undo
# rates are known. Supersedes the ratified plist "≤2/run, ≤5/day" contract —
# the plist comment + docs/plans/cabinet-two-flavor-autonomy-recommendation-
# 2026-07-04.md:313 are updated in this same change (docs-track-code).
MAX_PRESENT_PER_RUN = 8     # field-test: == MAX_PER_RUN, so generation is the only bound
DAY_ASK_BUDGET = 200        # field-test: ~8/h — never binds a real day; berserk-loop backstop only
# 48h TTL on the day counter: outlives its UTC day across a late run, then
# self-expires — the same lifetime actfirst_canary.CAP_KEY_TTL_S uses.
ASK_KEY_TTL_S = 172800
# CARD EXPIRY (germline batch 2026-07-04): an open action card older than this
# with no verdict auto-expires (see _expire_stale_cards). 36h mirrors the draft
# lane's PROPOSAL_MAX_AGE_H default (run_draft_lane.py:41) so both lanes share
# one staleness doctrine; env-overridable for the same reason the draft lane's
# is; <=0 disables the sweep.
CARD_MAX_AGE_H = float(os.environ.get("ACTION_CARD_MAX_AGE_H", "36"))
WINDOW_H = vault_signals.WINDOW_H   # 72h — single source since CG-2 extract
LLM_MODEL = "claude-sonnet-4-6"
_lock_fh = None

# CANONICAL ACTOR (germline batch 2026-07-04): the officer actor id is the BARE
# role ("cos"), NEVER "officer:cos". The ledger/graduation plane flattens actor
# to "kind:id" (graduation._cell_rows / consequence.compute_ratios), so the old
# double-prefixed literal produced cells keyed "officer:officer:cos" that the
# act-first gate — which composes "officer:"+role → "officer:cos" — could never
# match: every demotion-evidence row was invisible to the gate query. ONE
# module constant now feeds both emit sites (dry-run + live) AND the gate's
# cell composition (_graduation_demoted), so the identities can never drift
# apart again. run_draft_lane.py:237 already uses the bare form.
_ACTOR = {"kind": "officer", "id": "cos"}

# --- LANE CELL-KEY NORMALIZATION (germline batch 2026-07-05) -----------------
# The graduation cell key is (actor, lane, action_type). The lane component was
# LLM free-text off the proposer, so ONE conceptual lane arrived under many
# spellings across runs — the live ledger showed 5 spellings across 26 rows
# ('Commitments', 'Commitments / Delivery', 'captain', 'polads-ceo', ...). That
# FRAGMENTS verdict accumulation: two undos of the "same" lane land in two
# different cells and never cluster, so the 2-wrong demotion never fires and the
# 20-sample graduation floor is unreachable per cell. Fix: collapse the lane to
# the instance context enum (instance/config/contexts/*.yml slugs) at proposal
# ingestion AND at the gate's cell composition (_graduation_demoted), so the
# emitters and the gate key the EXACT same cell. Deterministic (no LLM) and
# fail-safe (config unreadable ⇒ a stable per-input slugification, never a fresh
# string per run). Idempotent, so applying it at both seams can never disagree.
CONTEXTS_DIR = Path(__file__).resolve().parents[2] / "instance" / "config" / "contexts"
# The stable catch-all cell for a lane matching no context slug. "adhoc" is a
# REAL context slug (Captain-dropped / unclassified work), a FIXED constant —
# never a per-run string — so every unmatched lane still clusters into ONE cell.
_LANE_NORM_DEFAULT = "adhoc"
_context_slugs_cache: "frozenset | None" = None


def _context_slugs() -> frozenset:
    """The instance context slugs (the lane enum), read once per run from
    instance/config/contexts/*.yml. Minimal `slug:` line parse (no yaml dep, and
    robust to a partially-written file) — the first top-level `slug:` scalar per
    file wins; a file without one is skipped. An unreadable dir ⇒ empty set (the
    caller then slugifies deterministically instead)."""
    global _context_slugs_cache
    if _context_slugs_cache is not None:
        return _context_slugs_cache
    slugs: set = set()
    try:
        for f in sorted(CONTEXTS_DIR.glob("*.yml")):
            try:
                for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                    s = line.strip()
                    if s.startswith("slug:"):
                        val = s.split(":", 1)[1].strip().strip('"').strip("'").lower()
                        if val:
                            slugs.add(val)
                        break
            except OSError:
                continue
    except OSError:
        pass
    _context_slugs_cache = frozenset(slugs)
    return _context_slugs_cache


def _slugify_lane(raw: str) -> str:
    """Deterministic kebab slug of a raw lane, with the officer-role suffixes
    stripped ('polads-ceo' -> 'polads', 'comms-officer' -> 'comms'). Stable per
    input (same raw ⇒ same slug every run) — the fallback when the context enum
    can't be read, so lanes still de-fragment by spelling."""
    s = re.sub(r"[^a-z0-9]+", "-", str(raw or "").lower()).strip("-")
    for suf in ("-ceo", "-officer", "-lane"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    return s or _LANE_NORM_DEFAULT


def _normalize_lane(raw: "str | None") -> str:
    """Collapse a free-text lane to ONE stable cell key. Deterministic, no LLM:
      1. exact slug match (whole normalized string) → that slug;
      2. exact token match (any '/'-, space-, dash-split token is a slug) →
         that slug (longest slug first, deterministic);
      3. containment fuzzy (a slug contains / is contained by a token, min length
         4 both sides to avoid short-substring noise, longest slug first) → so
         'polads-ceo' / 'PolAds delivery' → 'polads', 'cabinet' →
         'captains-cabinet';
      4. no match → the STABLE default ('adhoc'), never a fresh string.
    When the context enum can't be read, degrade to _slugify_lane (still stable
    per input). Idempotent: _normalize_lane(_normalize_lane(x)) == that value, so
    applying it at BOTH the emit seam and the gate can never disagree."""
    slugs = _context_slugs()
    s = str(raw or "").strip().lower()
    if not slugs:
        return _slugify_lane(s)
    if not s:
        return _LANE_NORM_DEFAULT
    if s in slugs:
        return s
    tokens = [t for t in re.split(r"[^a-z0-9]+", s) if t]
    ordered = sorted(slugs, key=lambda x: (-len(x), x))   # longest slug first
    for slug in ordered:
        if slug in tokens:
            return slug
    for slug in ordered:
        if len(slug) < 4:
            continue
        for t in tokens:
            if len(t) >= 4 and (slug in t or t in slug):
                return slug
    return _LANE_NORM_DEFAULT


# --- TI-3 act-first gate (2026-07-04 trust-inversion) ------------------------
# DEFAULT OFF. The entire earn-demotion posture stays DARK until the Captain
# flips it — mirrors the authority-enforcing flip (env override OR a flag file
# so a live flip/revert needs no code change and no restart). Nothing below
# runs unless _act_first_on(); with it off, main() behaves byte-identically to
# the propose-only lane.
ACT_FIRST_FLAG_FILE = Path(__file__).resolve().parents[2] / "instance" / "config" / "act-first-enabled"
MAX_AUTO_EXEC_STEPS = 2   # a card auto-executes at most this many steps [RT-A4]
# The declared instance knob's fail-safe twin: any problem reading the real
# value degrades HERE, never to 0 — a broken knob must tighten the act-first
# gate, not silently widen it.
CONFIDENCE_FLOOR_DEFAULT = 0.65

# --- SOV-4 posture routing (D10, sovereign build spec 2026-07-04) -------------
# The matrix wire lives ONLY inside the armed act-first branch: the flag stays
# the Captain's act switch, posture-config presence switches the armed branch's
# routing from the hardcoded chain rule to matrix-verdict routing. No
# posture.yml ⇒ _load_posture_ctx() is None ⇒ today's exact code path,
# byte-identical (P3). Guardian-table routing == today's mechanical outcome for
# every stampable action_type × state except demote, which NARROWS to propose
# (§0: demote always narrows — evidence beats posture; the legacy chain is
# graduation-blind, so this is the wire's one deliberate correction).
#
# The lane's routing allow-set. auto_with_veto_window / classifier are NOT
# members: verdicts must not promise unbuilt machinery at this lane (D3) — they
# propose. standing_grant is handled by its own dormant branch (never here).
ACT_VERDICTS = frozenset({"act_with_undo", "auto", "notify_after"})

# D13 inbound-provenance fence: evidence refs under the inbound vault areas
# are raw email/Teams captured content — cards derived from them NEVER act
# first, in any posture (the injection classifier is probabilistic; provenance
# is not). The prefix table is vault-layout knowledge and lives in
# vault_signals (CG-2 extract) — the FENCE stays here in the judged lane, and
# its judgment DATA keeps a germline floor (action_lane.D13_INBOUND_FLOOR):
# the effective set is adapter-table ∪ floor, so the officer-writable adapter
# can only WIDEN the fence, never narrow it below the locked floor.
_INBOUND_REF_PREFIXES = tuple(sorted(
    set(vault_signals.INBOUND_REF_PREFIXES) | set(action_lane.D13_INBOUND_FLOOR)))


def _act_first_on() -> bool:
    return (os.environ.get("CABINET_ACT_FIRST") == "1"
            or ACT_FIRST_FLAG_FILE.exists())


def _load_posture_ctx() -> "dict | None":
    """The D10 matrix-routing context, or None ⇒ today's exact code path.

    None on: posture kernel absent/unimportable, no instance posture.yml
    (posture_config_present() — a corrupt file still counts PRESENT: it routes
    through the matrix wire where resolve_posture says guardian), or any
    matrix/gate-lib load failure. The absent path is SILENT (byte-identical
    stdout, P3); a present-but-broken world degrades LOUDLY to the legacy path
    (== guardian behavior). resolve_verdict/risk_of/read_cell_state come from
    framework/authority/policy_engine (CG-14 pull-down: package import,
    the old cabinet/scripts/lib path-insert is retired) — ONE
    gate implementation, no function move."""
    try:
        from framework.authority import posture as posture_mod
        if not posture_mod.posture_config_present():
            return None
    except Exception:
        return None                    # pre-posture world — stay silent
    try:
        from framework.authority import policy_engine  # noqa: E402 — CG-14
        from framework.authority.matrix import load_matrix, matrix_policy
        policy = matrix_policy(load_matrix())   # fail-closed validator inside
        return {
            "policy": policy,
            "resolve_posture": posture_mod.resolve_posture,
            "risk_of": policy_engine.risk_of,
            "resolve_verdict": policy_engine.resolve_verdict,
            "read_cell_state": policy_engine.read_cell_state,
        }
    except Exception as e:
        # posture.yml EXISTS but the wire cannot stand — degrade loudly to the
        # legacy chain (mechanically == guardian), never fail the run.
        print(f"posture: routing ctx unavailable ({e}) — legacy path (guardian)")
        return None


def _route_verdict(pctx: dict, prop, action_type: "str | None"):
    """(verdict, posture, risk_class) for one card under the matrix wire (D10).

    Posture is resolved per card so FI-1 `lanes:` overrides apply. Fail-safe:
    an unstamped card or unmapped action_type has no risk_class ⇒ verdict None
    ⇒ the caller proposes (same fall-through the officer gate uses)."""
    posture = pctx["resolve_posture"](prop.lane)
    if not action_type:
        return None, posture, None
    policy = pctx["policy"]
    risk_class = pctx["risk_of"](action_type, policy.get("risk_classes"))
    if risk_class is None:
        return None, posture, None
    state = pctx["read_cell_state"]("cos", prop.lane, action_type)
    verdict = pctx["resolve_verdict"](
        policy.get("verdicts"), risk_class, state,
        posture=posture, postures=policy.get("postures"))
    return verdict, posture, risk_class


def _max_auto_steps(posture: "str | None") -> int:
    """The per-card auto-exec step budget: legacy constant (2) with no posture,
    else the FI-1 kernel's answer (guardian FORCED 2 / sovereign posture.yml-
    tunable, default 5). Guarded to the legacy constant — a broken kernel must
    tighten the budget, never widen it."""
    if posture is None:
        return MAX_AUTO_EXEC_STEPS
    try:
        from framework.authority.posture import max_auto_steps
        return int(max_auto_steps(posture))
    except Exception:
        return MAX_AUTO_EXEC_STEPS


def _card_provenance(p) -> str:
    """"inbound" when the card is derived from untrusted inbound capture
    (email/Teams) — an explicit `provenance` stamp on the proposal, or any
    evidence ref under the raw-capture vault areas. Everything else is
    "internal". Over-matching only costs a propose (fail-safe, D13)."""
    if getattr(p, "provenance", "") == "inbound":
        return "inbound"
    for ref in (getattr(p, "evidence", ()) or ()):
        if str(ref).lstrip("/").startswith(_INBOUND_REF_PREFIXES):
            return "inbound"
    return "internal"


def _file_lane_need(kind: str, *, risk_class=None, action_type=None, lane=None,
                    why: str, unblocks: str = "", scope_hint=None) -> None:
    """Best-effort FI-3 NEED from the lane — the kernel's needs_enabled()
    short-circuit keeps the default world bit-identical, and a filing failure
    never blocks (or reorders) the chain. NEVER raises."""
    try:
        from framework.authority import needs
        needs.file_need(kind, risk_class=risk_class, action_type=action_type,
                        lane=lane, why=why, unblocks=unblocks,
                        filed_by="run_action_lane", scope_hint=scope_hint)
    except Exception:
        pass


def _standing_grant_probe(risk_class: "str | None", action_type: "str | None",
                          lane: "str | None") -> dict:
    """D2 at the acting lane — DORMANT v1 (FI-2): no scope-enforcing ceiling
    executor exists, so this NEVER acts and never record_use()s even on a
    grant hit; it probes coverage and files the standing_grant NEED on a miss
    so the chain proceeds (proposes) while the Captain sees the gap."""
    try:
        from framework.authority import grants
        res = grants.check(risk_class, action_type, lane=lane, context=None)
    except Exception as e:
        return {"granted": False, "reason": f"grants kernel unavailable: {e}"}
    if not res.get("granted"):
        _file_lane_need(
            "standing_grant", risk_class=risk_class, action_type=action_type,
            lane=lane,
            why=(f"acting lane blocked {risk_class}/{action_type} "
                 f"(lane {lane}): {res.get('reason')}"),
            unblocks=(f"sovereign standing-grant auto for {action_type} once a "
                      f"scope-enforcing executor lands"))
    return res


def _confidence_floor() -> float:
    """The instance ``confidence_floor`` from act-first-surfaces.yml — the same
    Captain-owned file the executor's board gate loads (one knob, one file, no
    second config to drift). Closes the checkpoint flip-condition "phantom
    safety knob" (1 declaration, 0 reads): a 0.1-confidence card clearing the
    mechanical gates must NOT act. FAIL-SAFE: absent/corrupt file, missing key,
    or an invalid value (non-numeric, ≤0, >1, NaN) degrades to the 0.65
    default — never to 0."""
    try:
        import yaml   # deferred — mirrors action_exec._load_act_first_surfaces
        data = yaml.safe_load(_surfaces_path().read_text())
        floor = float(data.get("confidence_floor") if isinstance(data, dict) else None)
        if 0.0 < floor <= 1.0:
            return floor
    except Exception:
        pass
    return CONFIDENCE_FLOOR_DEFAULT


def _backend_for_step(step) -> str:
    """The backend a step will execute on — mirrors the executor's own routing
    so the gate's act_first_eligible pre-check agrees with what will run."""
    kind = getattr(step, "kind", None) or (step.get("kind") if isinstance(step, dict) else "")
    if kind in ("monday_task_create", "monday_task_update"):
        return "monday"
    if kind == "reminder_create":
        return os.environ.get("ACTION_LANE_REMINDER_BACKEND", "calendar")
    return kind or "?"   # delegate_work / investigation_run → op "none" → ineligible


def _card_board(p) -> "str | None":
    """The Monday board a card touches (for veto + allowlist matching), from the
    first monday step carrying a board_id. None for non-Monday cards."""
    for s in p.steps:
        pl = getattr(s, "payload", None) or {}
        b = str(pl.get("board_id") or "").strip()
        if b:
            return b
    return None


def _card_act_first_eligible(p, action_type,
                             floor: float = CONFIDENCE_FLOOR_DEFAULT,
                             max_steps: int = MAX_AUTO_EXEC_STEPS) -> "tuple[bool, str]":
    """(eligible, reason) — the mechanical chain rule [RT-A4/B6]. A card
    auto-executes ONLY if it is not injection-suspect, not inbound-derived
    (D13 — provenance beats the probabilistic injection screen, any posture),
    carries a valid stamped action_type, meets the confidence floor, has
    ≤``max_steps`` steps, and EVERY step has a registered inverse
    (act_first_eligible). Any miss ⇒ propose_only (fail-safe). ``floor``/
    ``max_steps`` default to the constants so the helper stays deterministic
    under test; main() passes the yml-/posture-resolved values."""
    if getattr(p, "injection_suspect", False):
        return False, "injection_suspect"
    if _card_provenance(p) == "inbound":
        return False, "inbound provenance — never act-first (D13)"
    if not action_type:
        return False, "unstamped action_type"
    try:
        conf = float(p.confidence)
    except (TypeError, ValueError, AttributeError):
        conf = 0.0   # unverifiable confidence never clears the floor
    if not conf >= floor:   # NaN-safe: nan >= x is False ⇒ blocked, not waved through
        return False, "confidence below floor"
    if len(p.steps) > max_steps:
        return False, f"chain has {len(p.steps)}>{max_steps} steps"
    for s in p.steps:
        if not action_undo.act_first_eligible(getattr(s, "kind", ""), _backend_for_step(s)):
            return False, f"step {getattr(s, 'kind', '?')} has no registered inverse"
    return True, ""


# RECONCILE 2026-07-05: kept both HEAD (_graduation_demoted demote-wire +
# mandatory normalized lane kwarg) + sovereign (posture kwarg threading to the
# cap peek) — _act_first_gates_ok now takes BOTH lane (positional, required,
# fail-closed on None) and posture (keyword-only, None = byte-identical
# guardian behavior). Demote still blocks regardless of posture (evidence
# beats posture) and every check stays fail-closed.
def _graduation_demoted(action_type, lane) -> "tuple[bool, str]":
    """(demoted, reason) — fail-closed read of the graduation cell state for
    THIS lane's actor. DEMOTE-WIRE (germline batch 2026-07-04): demotion is the
    earn-demotion doctrine's PRIMARY brake — a cell the graduation engine
    demoted (>=2 wrong verdicts in the last 10 scored, or a single B2.8-proven
    fabrication; graduation.evaluate step 2) must actually STOP acting. Before
    this batch nothing in the acting path READ that state, so evidence-driven
    demotion was computed but never enforced. Only state=='demote' blocks:
    unmeasured / propose_only / eligible do NOT (the act_with_undo@unmeasured
    trust-inversion posture — trust is lost on evidence, never pre-earned).
    The cell key composes the SAME "kind:id" flatten graduation._cell_rows
    uses, from the one canonical _ACTOR, so the gate and the emitters can never
    disagree on identity again (the "officer:officer:cos" severing this batch
    fixed). FAIL-CLOSED: an unreadable ledger/matrix — or a failed import —
    blocks; an unverifiable brake must never widen action."""
    # N3 (checkpoint review lane-germline-0705-cp1): a None lane cannot key the
    # real per-lane cell — reading the None-lane cell would MISS a demotion that
    # lives on the actual lane (fail-open). An unspecified lane at a gating
    # decision is undeterminable → fail closed.
    if lane is None:
        return True, "lane unspecified (fail-closed)"
    # LANE CELL-KEY NORMALIZATION (germline batch 2026-07-05): key the SAME
    # normalized cell the emitters write (ingestion already normalizes p.lane, so
    # this is idempotent — but the gate must never depend on that: normalizing
    # here guarantees the gate reads the exact cell the demotion evidence lives
    # in, even if a raw lane ever reaches this call).
    lane = _normalize_lane(lane)
    try:
        # Lazy import: a broken graduation plane degrades to "blocked" at gate
        # time instead of crashing the whole propose-only lane at import time.
        from framework.fidelity import graduation
        cell = ("{}:{}".format(_ACTOR["kind"], _ACTOR["id"]), lane, action_type)
        state = (graduation.evaluate(cell) or {}).get("state")
    except Exception:
        return True, "graduation state unreadable (fail-closed)"
    if state == "demote":
        return True, "cell demoted (wrong-cluster/fabrication evidence)"
    return False, ""


def _act_first_gates_ok(action_type, board, kind, lane, *,
                        posture: "str | None" = None) -> "tuple[bool, str]":
    """(ok, reason) — the fail-closed runtime gates on a per-card basis: Captain
    veto, graduation demotion, kind freeze (breaker), silence breaker,
    per-kind/day caps. Every check fails CLOSED (an unreachable Redis /
    unreadable registry/ledger ⇒ block ⇒ the card falls through to
    propose_only), so an anomalous state never widens action. ``lane`` keys the
    graduation cell (actor, lane, action_type) and is REQUIRED (N3, checkpoint
    review 2026-07-05): a defaulted/None lane would read the wrong cell and miss
    a real per-lane demotion, so it is now mandatory and _graduation_demoted
    fails closed on None. ``posture`` threads to the cap peek (D11 — None is
    byte-identical; sovereign alarms at the base cap and blocks only at the
    ×hard_multiplier hard-stop). The demote check is POSTURE-INVARIANT: no
    posture makes a demoted cell act (evidence beats posture)."""
    try:
        if veto_registry.is_vetoed(action_type, board=board):
            return False, "captain veto"
    except Exception:
        return False, "veto check errored (fail-closed)"
    # DEMOTE-WIRE (germline 2026-07-04): the evidence brake, checked right
    # after the Captain's word (veto) and before the mechanical breakers —
    # veto/freeze/silence/caps guarded the estate, but a demoted cell could
    # still act because no gate consulted graduation state.
    demoted, dreason = _graduation_demoted(action_type, lane)
    if demoted:
        return False, dreason
    if actfirst_canary.is_frozen(kind):
        return False, "kind frozen (breaker/undo-rate)"
    if actfirst_canary.is_silenced(kind):
        return False, "kind silenced (30 acts, no human touch)"
    if not actfirst_canary.cap_check(kind, posture=posture).get("ok", False):
        return False, "per-day cap reached"
    return True, ""


def _prior_acted_types() -> frozenset:
    """action_types that have EVER acted (a prior acted ledger row carrying an
    outcome) — for the receipt's first-ever-cell instant-tell rule. Reads the
    canonical acted:<kind> rows (ACTED-EVENT IDENTITY FIX, germline batch
    2026-07-05) plus the legacy 'action-card' acted rows so history from before
    the fix still counts — else every post-fix first act would spuriously
    instant-tell (a real cell read as first-ever)."""
    types: set = set()
    try:
        for ev in read_ledger():
            act = ev.get("action") or ""
            if (act.startswith("acted:") or act == "action-card") \
                    and (ev.get("outcome") or {}).get("status"):
                at = ev.get("action_type")
                if at:
                    types.add(at)
    except Exception:
        pass
    return frozenset(types)


def _emit_receipt(p, pid, cid, action_type, result, *, first_ever, now) -> None:
    """Send an instant act-then-tell receipt on the HQ Chair channel when
    tell_surface.instant_tell_rules fires; otherwise the act is batch-eligible
    and rides the next digest (nothing sent here). NEVER raises — a receipt
    failure must not disturb an act that already landed + journaled."""
    try:
        content = p.situation + "\n" + "\n".join(f"- {s.title}" for s in p.steps)
        row = {
            "pid": pid, "cid": cid, "kind": action_type, "subject": p.subject,
            "lane": p.lane, "urgency": p.urgency, "first_ever_cell": first_ever,
            "content": content, "created": now,
            "payload": (getattr(p.steps[0], "payload", {}) if p.steps else {}),
            "executed": result.get("executed"),
        }
        msg = tell_surface.receipt(row, now=dt.datetime.now(dt.timezone.utc))
        if msg:
            _tg(msg)
    except Exception as e:
        print(f"act-first: receipt emit failed (act already landed + journaled): {e}")


def _acquire_lock() -> bool:
    global _lock_fh
    _lock_fh = open(LOCK_PATH, "w")
    try:
        fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _load_env() -> None:
    envs = [Path(__file__).resolve().parents[2] / "cabinet" / ".env"]
    _shared = shared_env_path()
    if _shared:
        envs.append(Path(_shared).expanduser())
    for env in envs:
        try:
            for line in env.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    v = v.strip().strip('"').strip("'")
                    # an EMPTY value never claims the key — cabinet/.env ships
                    # ANTHROPIC_API_KEY= blank (officers run on subscription)
                    # and must not shadow the real key in _shared/.env
                    if v:
                        os.environ.setdefault(k.strip(), v)
        except OSError:
            pass


def _redis(*args: str) -> str:
    host = os.environ.get("REDIS_HOST", "localhost")
    out = subprocess.run(["redis-cli", "-h", host, *args],
                         capture_output=True, text=True, timeout=10).stdout.strip()
    return "" if out in ("", "(nil)") else out


def load_directions() -> "dict | None":
    """Parse the Captain-ratified directions.yml (yaml.safe_load only) for
    injection into the proposer prompt + direction_fit validation. A missing or
    broken file degrades to None — the proposer then skips direction_fit
    enforcement rather than dropping every card (graceful degradation)."""
    try:
        import yaml
        data = yaml.safe_load(DIRECTIONS_PATH.read_text())
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _suppress_log(line: str) -> None:
    """Sink for the proposer's dedup/skip decisions — one line each to the
    launchd log so no drop is silent (SEC-4 RT-A12)."""
    print(line)


def _llm(system: str, user: str) -> str:
    """Raw-text Anthropic call (the core parses its own JSON). Key from env;
    never logged.

    SECRETS-ARGV (germline batch 2026-07-04): the API key and the request body
    used to ride the curl ARGV (`-H "x-api-key: …"` / `-d '{…}'`) — readable by
    ANY local process via `ps` for the full call duration (up to 180s), and the
    body embeds vault-derived signal text (private). Now the key goes through a
    0600 temp header file (`curl -H @<file>`, supported since curl 7.55;
    tempfile.mkstemp creates 0600 by construction, unlinked in `finally` so it
    lives only for the call) and the body rides stdin (`-d @-` + subprocess
    ``input=``). Only non-secret headers stay on argv."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""
    body = {"model": LLM_MODEL, "max_tokens": 4096, "system": system,
            "messages": [{"role": "user", "content": user}]}
    hfd, hpath = tempfile.mkstemp(prefix="cabinet-llm-hdr-")   # 0600 by default
    try:
        with os.fdopen(hfd, "w") as hf:
            hf.write(f"x-api-key: {api_key}\n")
        r = subprocess.run(
            ["curl", "-s", "--max-time", "180", "https://api.anthropic.com/v1/messages",
             "-H", f"@{hpath}",
             "-H", "anthropic-version: 2023-06-01",
             "-H", "content-type: application/json",
             "-d", "@-"],
            input=json.dumps(body),
            capture_output=True, text=True, timeout=185)
    finally:
        # The key file must not outlive the call — even on timeout/raise.
        try:
            os.unlink(hpath)
        except OSError:
            pass
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return ""
    return "".join(c.get("text", "") for c in (d.get("content") or [])
                   if c.get("type") == "text")


# ---------------------------------------------------------------------------
# Signals (read-only gather; as_of-shaped for future replay)
#
# PRO-4 (2026-07-04): a PROFILE-driven section table. OPERATIONAL is the live
# lane's perception (commitments / meetings / decisions + product health /
# people radar / code); STRATEGIC is the grander-lane view (opportunities +
# all health + code + retro + directions). CG-2 EXTRACT (2026-07-07, egg row
# R004a): the section TABLE + file-walk — the personal-vault directory
# layout — moved to framework/sources/vault_signals.py; this lane keeps only
# the dispatch + presentation. The legacy (flag-OFF, default) path calls the
# extracted walk with identical arguments — behavior byte-identical to the
# pre-extract inline code (pinned by test_gather_v2 / test_gather_corpus /
# test_gather_via_source parity).
#
# CABINET_GATHER_VIA_SOURCE=1 (DARK by default — CG-2 lands dark, canaries
# one tick, then relocks): gather routes through the bound PersonalSource
# seam instead of the direct vault walk — open_commitments() rows plus
# leak-scoped, content_ts-fenced search() context, presented in the SAME
# fenced-block channel; org-corpus sections ride along unchanged (they are
# org-side perception, not the captain's vault). FAIL-CLOSED: a broken or
# absent source gathers EMPTY — it never fabricates and never silently falls
# back to the vault walk (a fallback would defeat the seam's leak scoping).
# ---------------------------------------------------------------------------

def _gather_via_source() -> bool:
    return os.environ.get("CABINET_GATHER_VIA_SOURCE", "") == "1"


def _fence_block(label: str, ref: str, body: str, chars: int = 700) -> str:
    body = (body or "").strip()[:chars]
    return f"--- {label} ref={ref} ---\n{body}" if body else ""


def _source_parts(as_of: dt.datetime, *, window_h: int, profile: str,
                  corpus_dir: str) -> list:
    """PersonalSource-mediated evidence parts (the flag-ON path).

    Commitments via ``open_commitments()`` (both contract directions, capped
    like the legacy commitments section); per-commitment vault context via the
    leak-scoped ``search(handle, topic=…)`` — hits are content_ts-fenced to
    ``<= as_of`` and hits WITHOUT a content_ts are DROPPED (absent means
    unfenceable, never assumed-past — the replay fence holds). Honest empty on
    any source failure."""
    try:
        from framework.sources import get_source
        src = get_source()
        if not src.available():
            return []
    except Exception as e:  # noqa: BLE001 — fail-closed, never fabricate
        print(f"gather: source unavailable ({e}) — empty gather (flag-on)")
        return []
    parts: list = []
    try:
        rows = list(src.open_commitments("owed_by_captain") or [])
        rows += list(src.open_commitments("owed_to_captain") or [])
    except Exception as e:  # noqa: BLE001
        print(f"gather: open_commitments failed ({e}) — section empty")
        rows = []
    seen_refs: set = set()
    for row in rows[:8]:
        if not isinstance(row, dict):
            continue
        ref = str(row.get("path") or row.get("id") or row.get("slug")
                  or "commitment")
        body = " · ".join(
            str(row[k]) for k in ("text", "person", "due", "direction", "status")
            if row.get(k))
        blk = _fence_block("OPEN COMMITMENT", ref, body)
        if blk:
            parts.append((ref, blk))
            seen_refs.add(ref)
        handle = str(row.get("person") or row.get("slug") or "").strip()
        topic = str(row.get("text") or "").strip()
        if not handle or not topic:
            continue
        try:
            hits = (src.search(handle, topic=topic) or {}).get("hits") or []
        except Exception:  # noqa: BLE001 — one bad search never sinks the gather
            continue
        kept = 0
        for h in hits:
            if kept >= 2 or not isinstance(h, dict):
                continue
            cts = h.get("content_ts")
            if not cts:
                continue                  # unfenceable — never assume past
            try:
                ts = dt.datetime.fromisoformat(str(cts).replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=dt.timezone.utc)
            if ts > as_of:
                continue                  # future hit — the replay fence holds
            href = str(h.get("path") or h.get("ref") or h.get("heading") or handle)
            if href in seen_refs:
                continue
            blk = _fence_block("CONTEXT", href, str(h.get("text") or ""))
            if blk:
                parts.append((href, blk))
                seen_refs.add(href)
                kept += 1
    # Org-corpus perception rides along unchanged (org-side, not the vault).
    parts.extend(vault_signals.collect_sections(
        as_of, window_h=window_h, profile=profile, corpus_dir=corpus_dir,
        include=("corpus",)))
    return parts


def _directions_block() -> str:
    """The Captain-ratified directions.yml, verbatim (STRATEGIC only) — read from
    the instance config, still file-only, no API."""
    try:
        txt = DIRECTIONS_PATH.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return ""
    return f"--- DIRECTIONS ref={DIRECTIONS_PATH.name} ---\n{txt[:2000]}" if txt else ""


def gather_signals(as_of: dt.datetime, *, window_h: int = WINDOW_H,
                   profile: str = "operational", vault: "Path | None" = None,
                   suppress_cids=frozenset()) -> str:
    """The fenced evidence bundle for a profile.

    Flag OFF (default): the extracted vault walk
    (``framework.sources.vault_signals.collect_sections``) — FILE-ONLY (no
    API) so the sim harness replays it deterministically; v1 fencing =
    file-recency window ending at as_of. New folders may be absent → their
    section is simply empty. Corpus sections root at env.product_brain_dir()
    (the org's product-brain corpus); empty resolver ⇒ empty section (P3b).
    Behavior is byte-identical to the pre-CG-2 inline implementation.

    Flag ON (``CABINET_GATHER_VIA_SOURCE=1``, dark): ``_source_parts`` — the
    PersonalSource seam supplies commitments + leak-scoped context in the same
    fenced-block channel; corpus sections unchanged.

    ``suppress_cids`` drops any excerpt carrying one of OUR OWN acted
    correlation ids (an act→capture→act echo — TI-7); empty (the default) is a
    no-op, so the pre-flip lane and the sim harness are unchanged. The live
    lane passes ``actfirst_canary.own_acted_cids()`` once acting begins."""
    corpus_dir = product_brain_dir() or ""
    if _gather_via_source():
        parts = _source_parts(as_of, window_h=window_h, profile=profile,
                              corpus_dir=corpus_dir)
    else:
        parts = vault_signals.collect_sections(
            as_of, window_h=window_h, profile=profile, vault=vault,
            corpus_dir=corpus_dir)
    # TI-7 cid-echo suppression: never re-feed our own re-captured acts to the
    # proposer. No-op when suppress_cids is empty (pre-flip / sim replay).
    kept = actfirst_canary.filter_cid_echoes(
        parts, suppress_cids, text_of=lambda t: t[1], log=_suppress_log)
    blocks = [fenced for _, fenced in kept]
    if profile == "strategic":
        dirs = _directions_block()
        if dirs:
            blocks.append(dirs)
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Present
# ---------------------------------------------------------------------------

def _tg(text: str) -> None:
    # HQ CHAIR channel ONLY (Captain ruling 2026-07-03: cabinet cards go to the
    # HQ Chair bot, never the Screenpipe bot). TELEGRAM_COS_TOKEN is the Chair's
    # bot — the same one the cos-inbound poller polls, so replies BIND. There is
    # deliberately NO fallback to TELEGRAM_BOT_TOKEN: that is the Screenpipe
    # bot, whose updates never reach the binder (the first 5 live cards landed
    # there and could not be verdicted).
    # ONE DOOR (P3, attention-gateway spec §4.4/§13): route through the gated
    # front-door channel — killswitch/allow_sends, token scrub, 4096 chunking,
    # transport retry, feed-journal row. Same env contract as before
    # (TELEGRAM_COS_TOKEN + CAPTAIN_TELEGRAM_ID; the poller binds replies).
    # ANY non-sent status RAISES — including blocked-dev (review cp3 H1/H2:
    # a production process missing CABINET_ENV=runtime must fail LOUDLY, not
    # silently blackhole cards while ledger rows record them as presented;
    # dev sessions likewise must not pretend to present). Dry-run never
    # reaches this function.
    from framework.frontdoor import channel
    res = channel.send(text, feed_meta={"kind": "action-card"})
    if res.get("status") == "blocked-dev":
        raise RuntimeError("channel send refused (blocked-dev): set "
                           "CABINET_ENV=runtime for live sends")
    if not res.get("sent"):
        raise RuntimeError(f"channel send failed: {str(res)[:200]}")


def _store_action(pid: str, prop: action_lane.ActionProposal, cid: str = "") -> None:
    steps = [{"kind": s.kind, "title": s.title, "payload": s.payload}
             for s in prop.steps]
    rec = {"cid": cid, "lane": prop.lane, "subject": prop.subject,
           "situation": prop.situation,
           "steps": steps,
           # TOCTOU pin (executor-integrity quartet, checkpoint flip-condition
           # #1): fingerprint the steps at STORE time with the executor's OWN
           # hash (_canonical_sha), so deliver_action's re-check — which reads
           # rec["steps_sha256"] and re-hashes rec["steps"] — refuses any record
           # whose steps were swapped in Redis between card time and execution.
           # Stamped on BOTH paths deliberately: the Captain-approve path (live
           # today, hours between store and execute) is the longer TOCTOU window.
           "steps_sha256": _canonical_sha(steps),
           "evidence": list(prop.evidence),
           "confidence": prop.confidence, "urgency": prop.urgency}
    _redis("SET", f"cabinet:action:{pid}", json.dumps(rec), "EX", "604800")


def _ask_budget_ok(presented_this_run: int) -> "tuple[bool, str]":
    """(ok, reason) — the ask throttle, checked at the card-emit seam BEFORE any
    side effect. Under the FIELD-TEST OVERRIDE (2026-07-05; see the ASK BUDGET
    constants block) the caps are lifted to non-binding (MAX_PRESENT_PER_RUN=8,
    DAY_ASK_BUDGET=200) so the phase surfaces everything a real workload
    produces; this leg remains as the berserk-loop backstop + ask-volume counter
    (telemetry), not a routine throttle.

    Two legs: (1) per-run — ≤MAX_PRESENT_PER_RUN presented this run (checked
    first so a run-capped card never burns day-budget); (2) per-day —
    INCR-then-compare on the UTC-day Redis counter, EX ASK_KEY_TTL_S. INCR-
    then-compare deliberately mirrors actfirst_canary.incr_and_check: a
    withheld ask still consumed its count (conservative — never over-sends, at
    worst slightly under-sends, bounded by the per-run leg). The singleton lock
    makes concurrent lane runs impossible, so there is no INCR race within the
    lane. FAIL-CLOSED: any Redis problem withholds — safe because a withheld
    card writes NO ledger row, so covered_evidence_refs() does not cover it and
    it re-proposes on a later run while its evidence window (72h) is fresh; and
    coherent, because a presented card without a stored Redis record could
    never be approve-executed anyway."""
    if presented_this_run >= MAX_PRESENT_PER_RUN:
        return False, f"per-run present cap {MAX_PRESENT_PER_RUN} reached"
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    key = f"cabinet:action:asks:{day}"
    try:
        n = int(_redis("INCR", key) or 0)
        _redis("EXPIRE", key, str(ASK_KEY_TTL_S))
    except Exception as e:
        return False, f"ask counter unavailable — fail-closed ({e})"
    if n > DAY_ASK_BUDGET:
        return False, f"day ask budget {DAY_ASK_BUDGET} exhausted ({n} asked today)"
    return True, ""


def _expire_stale_cards(now: dt.datetime) -> int:
    """CARD-EXPIRY (germline batch 2026-07-04) — close every open action card
    older than CARD_MAX_AGE_H that never got a verdict, so stale asks stop
    dangling forever.

    Before this batch action cards NEVER expired (unlike the draft lane —
    run_draft_lane.py._auto_expire_self_replied): an unanswered card stayed an
    ⚡AWAITING line in every digest (tell_surface derives those from pending
    proposals) AND held a live executable record in Redis for its full 7-day
    TTL. Doctrine (.claude/rules/courses-of-action.md §3): stale proposals
    auto-expire into the briefing — they are not re-pinged and must not pile up.

    Per expired card:
      * emit loop.expire_event — the SAME superseding closure the draft lane
        uses: decision='expired', review.verdict='unknown', source='system'.
        Graduation-NEUTRAL by construction: unknown verdicts are excluded from
        every scored denominator (graduation._divergent_in_last10 counts only
        confirmed/wrong), so an expiry can never register as a demotion.
        decided_at = the card's OWN ts (the suppression clock — a genuinely-new
        same-subject situation arriving before the sweep must not be judged
        already-handled; the draft lane's UAT-TEST-#3-miss rationale,
        loop.expire_event docstring); reviewed_at = the real expiry moment
        (the audit clock).
      * best-effort DEL of cabinet:action:<pid> — the TTL alignment: the
        AWAITING line (ledger-derived, dies with the expire event) and the
        executable record die TOGETHER instead of the record outliving its
        card by ~5.5 days. Mirrors the executor's own DEL-on-delivered
        (action_exec.py:1179). Safe under a racing late approve: the binder's
        handle_response refuses any already-decided proposal BEFORE dispatch
        (loop.py), so a missing record is unreachable — the DEL is defense-in-
        depth, not the guard. Ordered ledger-first: a DEL without the expire
        event would orphan a still-open card, so the DEL only runs after the
        emit landed.

    Best-effort throughout: an unreadable ledger skips the whole sweep; a
    per-card failure logs and continues (one line per expiry — SEC-4, no
    silent drops). Only rows with action=='action-card' are touched —
    draft-reply proposals belong to the draft lane's own sweep. An unparseable
    ts never expires (conservative: we cannot prove the card is old — same
    stance as the draft lane's backstop). Returns the count expired."""
    if CARD_MAX_AGE_H <= 0:
        return 0
    try:
        open_props = pending_proposals()
    except Exception as e:
        print(f"card-expiry: skipped (ledger unreadable: {e})")
        return 0
    expired = 0
    for prop in open_props:
        if prop.get("action") != "action-card":
            continue
        when = ld.parse_dt(prop.get("ts"))
        if when is None or (now - when).total_seconds() < CARD_MAX_AGE_H * 3600:
            continue
        try:
            ev = expire_event(prop,
                              reviewed_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                              decided_at=prop.get("ts"))
            emit_consequence(**ev)
            expired += 1
            print(f"card-expiry: expired open card -> {prop.get('subject')} "
                  f"(> {CARD_MAX_AGE_H:g}h, no verdict; graduation-neutral)")
            # H5 (command-center 2026-07-10): expiry is ROUTING, not a
            # verdict — journal the demotion as a first-class feed row so
            # the war-room census + P6 attention cells read it natively
            # (the situations view re-types bare ledger expiries anyway;
            # this is the source-side record). Best-effort, never blocks.
            try:
                from framework.attention.feed import append_event
                from framework.attention.situation import (
                    situation_key as _sit_key)
                append_event({
                    "direction": "in", "kind": "demote",
                    "situation_key": _sit_key(
                        [r for r in (prop.get("refs") or [])
                         if isinstance(r, str)],
                        str(prop.get("subject") or "")),
                    "demote_reason": "card-expiry",
                })
            except Exception:
                pass
        except Exception as e:
            print(f"card-expiry: failed for {prop.get('subject')}: {e}")
            continue
        try:
            _redis("DEL", f"cabinet:action:{proposal_id(prop)}")
        except Exception:
            pass   # unreachable-anyway record ages out on its own 7d TTL
    return expired


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not _acquire_lock():
        print("done: another action-lane run holds the lock")
        return 0
    _load_env()

    now = dt.datetime.now(dt.timezone.utc)
    budget = MAX_PER_RUN

    # CARD-EXPIRY sweep FIRST (germline 2026-07-04) — the draft lane's ordering
    # rationale (run_draft_lane.py main): expired cards must drop out of
    # pending_proposals BEFORE open_subjects is read below, so a stale card
    # stops suppressing a fresh same-subject proposal this very tick. Skipped
    # on --dry-run: the eyeball gate stays write-free (no ledger, no Redis) as
    # its docstring promises.
    if not args.dry_run:
        _expire_stale_cards(now)

    # cid-echo suppression (TI-7): when act-first is live, drop signals derived
    # from the lane's OWN recent acted cards so an act can't loop act→capture→act.
    # Dormant (empty set) when act-first is off — gather behaves exactly as before.
    _echo = actfirst_canary.own_acted_cids() if _act_first_on() else frozenset()
    signals = gather_signals(now, suppress_cids=_echo)
    if not signals.strip():
        print("done: no fresh signals in window")
        return 0

    # P2 acted-state overlay (attention-gateway spec §8): what the cabinet
    # already EXECUTED, from the ledger's acted rows × the undo journal.
    # Rendered into the signals so the proposer sees acted/reversed state
    # (gather-then-decide), and passed canonically to the propose core for
    # the mechanical already-acted drop + reversed-refs un-covering. Build
    # failure ⇒ world state UNKNOWN: cards still propose (fail toward
    # presenting) but act-first is DISARMED below — never auto-act on an
    # unverifiable world.
    # named acted_view, NOT `acted` — the act-first loop below reuses `acted`
    # as its per-run counter (review cp2 Low-2 shadowing landmine).
    acted_view = None
    try:
        acted_view = acted_overlay.load_acted(since=_covered_since() or "")
    except Exception as e:
        print(f"acted-overlay: unavailable ({e}) — world state UNKNOWN this run")
    if acted_view is not None:
        signals += acted_overlay.render_overlay(acted_view)

    decided = set(ld.decided_subjects().keys())
    open_subjects = {  # any pending proposal's subject, action or draft
        (p.get("subject") or "") for p in pending_proposals() if isinstance(p, dict)}

    # W4 lessons-splice (agi-wires dead-wire #4): the SIE-1 correction ledger
    # finally gets a reader — Captain corrections become standing proposer
    # instructions instead of evaporating. Best-effort: a missing ledger is
    # [] by load_lessons' own contract, and ANY read error degrades to []
    # with a printed notice (the correction loop is an amplifier, never a
    # gate on the lane).
    try:
        from framework.frontdoor.action_lessons import load_lessons
        lessons = load_lessons()
    except Exception as e:
        print(f"action-lessons: unavailable ({e}) — proposing without lessons")
        lessons = []

    proposals = action_lane.propose_actions(
        signals, as_of=now.strftime("%Y-%m-%dT%H:%M:%SZ"), llm=_llm,
        decided_subjects=decided, open_subjects=open_subjects,
        budget_left=budget, covered_evidence=covered_evidence_refs(),
        acted_refs=(acted_view or {}).get("live_canonical") or frozenset(),
        reversed_refs=(acted_view or {}).get("reversed_canonical") or frozenset(),
        directions=load_directions(), lessons=lessons,
        suppress_log=_suppress_log)

    # LANE CELL-KEY NORMALIZATION (germline batch 2026-07-05): collapse every
    # proposal's LLM free-text lane to the stable context-enum cell key BEFORE
    # anything reads p.lane — so the ledger prop/acted rows, the rendered card,
    # the stored Redis record + journal rows, AND the gate all key the identical
    # graduation cell (see _normalize_lane). Done before the dry-run branch so the
    # eyeball gate shows exactly the cell that will accumulate.
    proposals = [dataclasses.replace(p, lane=_normalize_lane(p.lane))
                 for p in proposals]

    if args.dry_run:
        print(f"DRY RUN — {len(proposals)} card(s) would present:\n")
        for p in proposals:
            # _ACTOR (bare "cos") — the old inline "officer:cos" literal here
            # double-prefixed the graduation cell key; see the constant's WHY.
            prop_ev = proposal_event(actor=_ACTOR,
                                     lane=p.lane, subject=p.subject,
                                     ts=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                     action="action-card")
            print(action_lane.render_card(p, proposal_id(prop_ev)))
            print("\n" + "=" * 60 + "\n")
        return 0

    # TI-3 act-first setup (DARK unless flipped). Rebuild the veto cache once at
    # lane start; a rebuild failure means the registry is unreadable → act-first
    # OFF this run (fail-closed — an unverifiable veto set never widens action).
    act_first = _act_first_on()
    if act_first:
        try:
            veto_registry.rebuild_cache()
        except Exception as e:
            print(f"act-first: veto cache rebuild errored ({e}) — acting disabled this run")
        if not veto_registry.veto_cache_ready():
            print("act-first: veto cache not ready — acting disabled this run (propose-only)")
            act_first = False
        # P2 world-grounding floor: an unverifiable acted-state means the lane
        # cannot prove it is not about to duplicate a standing artifact —
        # cards still PROPOSE (fail toward presenting), acting is off.
        if act_first and acted_view is None:
            print("act-first: acted-overlay unavailable — world state unknown; "
                  "acting disabled this run (propose-only)")
            act_first = False
    prior_acted = _prior_acted_types() if act_first else frozenset()
    # yml-resolved once per run (fail-safe default on any read problem); never
    # read flag-off — the dark lane touches nothing the propose-only lane didn't.
    conf_floor = _confidence_floor() if act_first else CONFIDENCE_FLOOR_DEFAULT
    # SOV-4 matrix wire (D10): loaded once per run, ONLY inside the armed
    # branch. None (no posture.yml / kernel absent / load failure) ⇒ every
    # card takes today's exact chain below, byte-identically.
    pctx = _load_posture_ctx() if act_first else None

    presented = acted = 0
    # _ACTOR (bare "cos"): this literal was the LIVE half of the double-prefix
    # bug — every ledger row it emitted flattened to "officer:officer:cos" and
    # was invisible to the gate's "officer:cos" cell query (see the constant).
    actor = _ACTOR
    for p in proposals:
        ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # B2.1 cid (strategy-report corrected rec 2, 2026-07-03): without a
        # minted correlation id every card is unjoinable to probe outcomes and
        # lands unattributable — the wire the graduation engine starves without.
        from framework.probes import correlation
        cid = correlation.mint()
        prop_ev = proposal_event(actor=actor, lane=p.lane, subject=p.subject,
                                 ts=ts, action="action-card",
                                 refs=[correlation.ref_for(cid)] + list(p.evidence))
        # action_type stamping (graduation wire). Guarded by the shared enum:
        # only a mapping whose target EXISTS in classifier.ACTION_TYPES is
        # stamped, so no invalid type is ever emitted. Chains stamp only when
        # ALL steps agree on one type (honest cell accounting). Gated on the
        # armed posture [closes refuter KILLED #1(b)]: post-GERM-2 the enum
        # maps creates, so an unconditioned stamp wrote flag-off ledger rows
        # carrying action_type — bytes the audited pre-TI-3 propose-only lane
        # never wrote, silently accumulating graduation-cell history while the
        # Captain believed the posture inert. Earning starts AT the flip, never
        # dark; flag-on keeps stamping both acted and propose-fallthrough rows.
        at = action_lane.chain_action_type(p)
        if at and act_first:
            prop_ev["action_type"] = at
        pid = proposal_id(prop_ev)

        # --- ACT-FIRST branch (earn-demotion). A card auto-executes ONLY when it
        # clears the mechanical chain rule AND every fail-closed runtime gate; the
        # executor's own act-first perimeter (board allowlist, tripwire, caps) is
        # the final authority and can still downgrade. Ordering is journal-first-
        # by-construction: deliver_action write-ahead-journals each step (48h undo
        # handle) BEFORE its mutation, so the act is always reversible even if the
        # post-act ledger emit is lost. Any miss anywhere → fall through to propose.
        #
        # SOV-4 (D10): with a posture ctx, the matrix verdict routes FIRST —
        # {act_with_undo, auto, notify_after} enter the same mechanical chain
        # (inverse-per-step KEPT), {propose_only, always_gated, anything else}
        # propose, standing_grant probes grants+needs and proposes (dormant v1).
        # pctx None ⇒ route_allows == act_first ⇒ today's exact chain.
        did_act = False
        verdict, card_posture = None, None
        route_allows = act_first
        if act_first and pctx is not None:
            verdict, card_posture, risk_class = _route_verdict(pctx, p, at)
            if verdict == "standing_grant":
                res = _standing_grant_probe(risk_class, at, p.lane)
                route_allows = False
                print(f"matrix verdict standing_grant -> {p.subject}: ceiling "
                      f"proposes in v1 ({str(res.get('reason'))[:120]})")
            elif verdict not in ACT_VERDICTS:
                route_allows = False
                print(f"matrix verdict {verdict or 'unmapped'} -> {p.subject}: propose")
        if route_allows:
            elig, ereason = _card_act_first_eligible(
                p, at, floor=conf_floor, max_steps=_max_auto_steps(card_posture))
            kind_key = actfirst_canary.kind_key(at) if at else ""
            # RECONCILE 2026-07-05: kept both HEAD (lane=p.lane) + sovereign
            # (posture=card_posture). lane=p.lane keys the DEMOTE-WIRE's
            # graduation cell (actor, lane, action_type) — the same triple the
            # emitted ledger rows carry, so the evidence this card generates is
            # the evidence its next run is gated on. posture=card_posture
            # threads the SOV-4 routed posture into the cap peek (None ⇒
            # guardian, byte-identical); demote blocks in every posture.
            gates_ok, greason = (_act_first_gates_ok(at, _card_board(p), kind_key,
                                                     lane=p.lane,
                                                     posture=card_posture)
                                 if elig else (False, ereason))
            if elig and gates_ok:
                _store_action(pid, p, cid=cid)
                result = deliver_action(pid, act_first=True, posture=card_posture)
                if result.get("ok"):
                    # ACTED-EVENT IDENTITY FIX (germline batch 2026-07-05): the
                    # per-step acted consequence rows are now emitted INSIDE
                    # deliver_action (action_exec._emit_acted_consequence), off the
                    # exact enriched journal row — on the canonical acted:<kind>
                    # identity the binder + reconcile sweep supersede on. The old
                    # card-level dict(prop_ev) emit under 'action-card' is GONE: it
                    # never matched the consumers' recomputed identity, so it left
                    # a permanent outcome:unknown orphan AND each verdict minted a
                    # second row (2 rows/act double-count). Nothing to emit here
                    # now — the executor owns the acted row (unknown→verdict in
                    # place). Only the caps counter + receipt remain lane-side.
                    try:
                        actfirst_canary.incr_and_check(kind_key, posture=card_posture)
                    except Exception:
                        pass
                    _emit_receipt(p, pid, cid, at, result,
                                  first_ever=(at not in prior_acted), now=ts)
                    prior_acted = prior_acted | {at}
                    did_act = True
                    acted += 1
                    print(f"ACTED (act-first) -> {p.subject} ({p.lane}, {at})")
                else:
                    # executor's perimeter downgraded, or a step failed → propose.
                    print(f"act-first downgraded -> {p.subject}: "
                          f"{result.get('gate') or result.get('error')}")
            else:
                print(f"act-first ineligible -> {p.subject}: {ereason or greason}")
                if (verdict == "auto"
                        and "no registered inverse" in (ereason or "")):
                    # D10: an auto verdict the mechanical chain cannot honor is
                    # a capability gap, not a human-wait — file it and propose.
                    _file_lane_need(
                        "capability", action_type=at, lane=p.lane,
                        why=(f"matrix verdict auto for {at} but the chain has "
                             f"no registered inverse: {ereason}"),
                        unblocks=f"act-first for {at} once an inverse is registered")

        if not did_act:
            # ASK-BUDGET seam: the ask throttle (field-test override 2026-07-05:
            # non-binding 8/run, 200/day — backstop + telemetry only) is checked
            # BEFORE any side effect — a
            # withheld card writes NOTHING (no ledger row, no Redis record, no
            # Telegram), so covered_evidence never covers it and it re-proposes
            # naturally on a later run while its evidence stays fresh. Acted
            # cards above never reach this seam (tells, not asks). Logged per
            # card (SEC-4 RT-A12: no silent drops).
            budget_ok, breason = _ask_budget_ok(presented)
            if not budget_ok:
                print(f"ask-budget: withheld card -> {p.subject} ({breason}; "
                      f"re-proposes while evidence is fresh)")
                continue
            card = action_lane.render_card(p, pid)   # marker-stripped inside
            emit_consequence(**prop_ev)              # ledger FIRST (fail-closed order)
            _store_action(pid, p, cid=cid)
            _tg(card)
            presented += 1
            print(f"presented action card -> {p.subject} ({p.lane}, conf={p.confidence:.2f})")
    if act_first:
        print(f"done: presented {presented} card(s), acted {acted} card(s)")
    else:
        # exact pre-TI-3 summary bytes [closes refuter KILLED #1(a)]: a dark or
        # degraded run reports as the propose-only lane it behaviorally is.
        print(f"done: presented {presented} action card(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
