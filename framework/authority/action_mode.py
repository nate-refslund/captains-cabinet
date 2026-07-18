"""Autonomy-graded action seam [Captain law 2026-07-17].

THE law this module encodes, verbatim from the ruling: "every autonomous
mutation's mode is a FUNCTION of the posture level — propose-first/earn-trust
→ ASK; act-then-tell → ACT with proven undo + receipt; sovereign → GO;
Ring-0 ALWAYS Captain regardless."

One function answers one question for every organ that mutates anything
autonomously: *in what MODE may this action run right now?*

    action_mode(action, posture=None) -> "propose" | "act_tell" | "go"

`action` is a plain descriptor mapping — `{ring, reversibility, category}`
plus an optional `undo_handle` — describing the MUTATION, never the caller:

    ring          0 | 1 | 2   (0 = constitution/enforcer/judge plane — the
                  immutable-core enumeration; 1 = judged/learning plane;
                  2 = runtime organ surface). Closed set; anything else is
                  unknown.
    reversibility "reversible" | "irreversible". Closed set.
    category      non-empty slug for the mutation class (open vocabulary,
                  EXCEPT the Ring-0 category enumeration below, which
                  force-classifies ring 0 whatever the caller declared).
    undo_handle   optional non-empty string naming a REGISTERED undo (the
                  exact command / ledger ref that reverses the act). Required
                  for act_tell — never for propose/go.

Posture is read through the EXISTING selection kernel —
`framework.authority.posture.resolve_posture` (guardian is the answer to
every ambiguity there) — with `file_needs=False`, so this seam NEVER files
needs, never writes, never logs: pure function + a tiny cached read of
`framework/policies/immutable-core.yml` for the path→ring helper. Callers
pass `posture=` only when they already resolved it (or in tests).

The posture ladder → mode map:

    earn_up   → propose   (earn-trust: ASK)
    guardian  → propose   (propose-first: ASK)
    act_then_tell → act_tell, ONLY with reversibility=="reversible" AND a
                presented registered undo_handle; refused → propose. NOTE:
                today's ladder (posture.POSTURES) does NOT define this level
                — the seam recognizes the token forward-compatibly so the
                law is already wired if the Captain ever adds the rung. No
                runtime surface can reach it until then.
    sovereign → go
    anything else / unresolvable → propose (fail-closed)

RING-0 OVERRIDE (absolute): effective ring 0 → ALWAYS "propose" with
`captain_card=True`, regardless of posture — sovereign included. Ring-0 is
the Captain-only plane, enumerated from existing doctrine:
`framework/policies/immutable-core.yml` (THE single source of Ring-0 paths
— constitution/germline/enforcer/judge plane), the platform-adoption law
GATE 3 (`docs/runbooks/platform-adoption-gating.md`: the claude binary +
officer model routing, Captain-law pinned no-flip-back), and the spend-cap
plane (FW-002 spending limits; `spend` is a hard-ceiling matrix class).
`RING0_CATEGORIES` freezes those domains as category slugs; a category
match forces ring 0 even when the caller claimed ring 1/2 (the seam may
only tighten a caller's claim, never widen it).

The seam NEVER widens anything: its answer is an UPPER BOUND on autonomy.
Every consulting organ keeps its own narrower gates (the authority matrix
floor, soak/hold clocks, Captain vetoes, screens, sandboxes) fully in
force — "go" means "your own law applies", never "skip your own law". A
retrofit through this seam is behavior-preserving-or-tighter by
construction: propose stays propose; only a posture the Captain attested
can ever relax the mode, and never for Ring-0.

The Captain card: `captain_card=True` on a decision means the CALLER must
put a Captain card on the attention surface (e.g. attention-submit) before
anything else — this module files nothing itself (no side effects).

Golden eval: EVAL-026-ACTION-MODE (`cabinet/evals/action-mode/harness.py`,
wired into `cabinet/scripts/run-golden-evals.sh`; eval body staged for the
schg-locked `memory/golden-evals/` dir via
`docs/proposals/germline-amendment-action-mode-eval-2026-07-17.md`).
Tests: `framework/authority/tests/test_action_mode.py`.
"""
from __future__ import annotations

import re
import sys
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, NamedTuple, Optional

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

from framework.authority.posture import (  # noqa: E402
    EARN_UP,
    GUARDIAN,
    SOVEREIGN,
    cabinet_root,
    resolve_posture,
)

# ---------------------------------------------------------------------------
# Vocabulary (closed sets — anything outside them is unknown ⇒ propose)
# ---------------------------------------------------------------------------

PROPOSE = "propose"
ACT_TELL = "act_tell"
GO = "go"
MODES = frozenset({PROPOSE, ACT_TELL, GO})

# Forward-compatible act-then-tell posture token (NOT in posture.POSTURES
# today — see module docstring). Recognized here so the ladder can grow the
# rung without touching this seam.
ACT_THEN_TELL = "act_then_tell"

RINGS = frozenset({0, 1, 2})
REVERSIBILITIES = frozenset({"reversible", "irreversible"})

# Ring-0 category slugs, enumerated from existing doctrine (docstring cites
# each source). FROZEN: widening the Captain-only plane is a Captain act
# (amendment), never a code default — the matrix test + EVAL-026 pin this
# set by equality, so a silent edit in either direction goes red.
RING0_CATEGORIES = frozenset({
    "constitution",            # framework/constitution-base.md + preset addenda
    "germline",                # immutable-core.yml enumeration (schg plane)
    "officer-model-routing",   # Captain-law pinned, no-flip-back (GATE 3)
    "claude-binary",           # the platform binary itself (GATE 3)
    "spend-caps",              # FW-002 / matrix `spend` hard-ceiling plane
})

_MODE_BY_POSTURE = {
    EARN_UP: PROPOSE,
    GUARDIAN: PROPOSE,
    ACT_THEN_TELL: ACT_TELL,   # subject to the undo-handle rule below
    SOVEREIGN: GO,
}


class ActionDecision(NamedTuple):
    """The seam's full answer. `mode` is the law; `captain_card` means the
    caller must surface a Captain card (ring-0 only); `reason` is a stable
    slug for receipts/journals — never prose, never interpolated input."""

    mode: str
    captain_card: bool
    reason: str


# ---------------------------------------------------------------------------
# Descriptor normalization
# ---------------------------------------------------------------------------

_CATEGORY_SEP_RE = re.compile(r"[\s_]+")


def _norm_category(value: Any) -> Optional[str]:
    """Lower-cased, hyphen-joined category slug; None when absent/empty/not
    a string (⇒ unknown ⇒ propose)."""
    if not isinstance(value, str):
        return None
    slug = _CATEGORY_SEP_RE.sub("-", value.strip().lower()).strip("-")
    return slug or None


def _declared_ring(value: Any) -> Optional[int]:
    """The caller's ring claim iff it is a RINGS member (bool is not an int
    here); None ⇒ unknown."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value in RINGS else None


def _norm_reversibility(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    word = value.strip().lower()
    return word if word in REVERSIBILITIES else None


def _has_undo_handle(action: Mapping) -> bool:
    handle = action.get("undo_handle")
    return isinstance(handle, str) and bool(handle.strip())


# ---------------------------------------------------------------------------
# The seam
# ---------------------------------------------------------------------------

def action_decision(
    action: Any,
    posture: Optional[str] = None,
    *,
    root: "str | Path | None" = None,
    resolve_fn: Optional[Callable[[], str]] = None,
) -> ActionDecision:
    """Full decision for one action descriptor under one posture.

    `posture=None` resolves live through `resolve_posture(root=root,
    file_needs=False)` — no needs are ever filed from this seam. `resolve_fn`
    is the hermetic test injection (mirrors `is_locked_fn` in posture.py);
    a raising resolver is ambiguity ⇒ propose. Never raises.
    """
    if not isinstance(action, Mapping):
        return ActionDecision(PROPOSE, False, "invalid-descriptor")

    ring = _declared_ring(action.get("ring"))
    ring_claimed_zero = (
        not isinstance(action.get("ring"), bool) and action.get("ring") == 0
    )
    category = _norm_category(action.get("category"))

    # RING-0 OVERRIDE first — before any other validity question, before
    # posture is even read: a ring-0 claim OR a ring-0 category is
    # Captain-only, whatever else the descriptor says.
    if ring_claimed_zero or (category is not None and category in RING0_CATEGORIES):
        return ActionDecision(PROPOSE, True, "ring-0-captain-only")

    if category is None:
        return ActionDecision(PROPOSE, False, "unknown-category")
    if ring is None:
        return ActionDecision(PROPOSE, False, "unknown-ring")
    reversibility = _norm_reversibility(action.get("reversibility"))
    if reversibility is None:
        return ActionDecision(PROPOSE, False, "unknown-reversibility")

    resolved = posture
    if resolved is None:
        try:
            if resolve_fn is not None:
                resolved = resolve_fn()
            else:
                resolved = resolve_posture(root=root, file_needs=False)
        except Exception:
            return ActionDecision(PROPOSE, False, "posture-resolve-failed")
    if not isinstance(resolved, str) or resolved not in _MODE_BY_POSTURE:
        return ActionDecision(PROPOSE, False, "unknown-posture")

    mode = _MODE_BY_POSTURE[resolved]
    if mode == ACT_TELL:
        # Act-then-tell is only lawful with a PROVEN undo: reversible action
        # + a registered undo handle presented by the caller. Anything less
        # degrades to propose (refuse, never assume).
        if reversibility != "reversible":
            return ActionDecision(PROPOSE, False, "act-tell-refused-irreversible")
        if not _has_undo_handle(action):
            return ActionDecision(PROPOSE, False, "act-tell-refused-no-undo-handle")
        return ActionDecision(ACT_TELL, False, "act-then-tell-with-undo")
    if mode == GO:
        return ActionDecision(GO, False, "posture-sovereign")
    return ActionDecision(PROPOSE, False, f"posture-{resolved}")


def action_mode(
    action: Any,
    posture: Optional[str] = None,
    *,
    root: "str | Path | None" = None,
    resolve_fn: Optional[Callable[[], str]] = None,
) -> str:
    """The mode string alone — the one-call seam. See `action_decision`."""
    return action_decision(
        action, posture, root=root, resolve_fn=resolve_fn
    ).mode


def requires_captain_card(action: Any) -> bool:
    """True iff this descriptor is ring-0 (Captain card required). Posture
    cannot change the answer, so none is read."""
    return action_decision(action, GUARDIAN).captain_card


# ---------------------------------------------------------------------------
# Path → ring helper (the tiny cached config read)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=8)
def _ring0_path_sets(
    root_str: str,
) -> "Optional[tuple[frozenset[str], tuple[str, ...]]]":
    """(exact, dir_prefixes) from framework/policies/immutable-core.yml under
    `root_str`, or None when the enumeration is unreadable/corrupt (callers
    treat None as UNKNOWN, never as not-ring-0). yaml.safe_load only; every
    class in the file counts — gate refusal covers all of them equally."""
    path = Path(root_str) / "framework" / "policies" / "immutable-core.yml"
    try:
        import yaml  # deferred — same as the posture ruling reader
        data = yaml.safe_load(path.read_text())
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    exact: set = set()
    prefixes: list = []
    for key in ("files", "dirs", "runtime_appended", "hook_protected"):
        entries = data.get(key)
        if entries is None:
            continue
        if not isinstance(entries, list):
            return None  # corrupt shape ⇒ the whole enumeration is unreadable
        for entry in entries:
            raw = entry.get("path") if isinstance(entry, dict) else None
            if not isinstance(raw, str) or not raw.strip():
                return None
            raw = raw.strip()
            trailing_dir = raw.endswith("/")
            norm = raw.rstrip("/")
            exact.add(norm)
            if key == "dirs" or trailing_dir:
                prefixes.append(norm + "/")
    return frozenset(exact), tuple(sorted(prefixes))


def ring_for_repo_path(
    relpath: Any,
    root: "str | Path | None" = None,
    default: int = 2,
) -> Optional[int]:
    """Ring classification for a repo-relative POSIX path.

    0 when the path IS an immutable-core entry or sits under an enumerated
    directory (dir-cover); None when the path or the enumeration cannot be
    read (UNKNOWN — the seam maps unknown ring to propose); else `default`.
    Never raises, never writes.
    """
    if not isinstance(relpath, str) or not relpath.strip():
        return None
    rp = relpath.strip().lstrip("/").rstrip("/")
    if not rp or ".." in PurePosixPath(rp).parts:
        return None
    try:
        sets = _ring0_path_sets(str(cabinet_root(root)))
    except Exception:
        return None
    if sets is None:
        return None
    exact, prefixes = sets
    if rp in exact or any(rp.startswith(pre) for pre in prefixes):
        return 0
    return default
