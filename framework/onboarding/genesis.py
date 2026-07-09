"""framework.onboarding.genesis — the genesis half of onboarding (ONBOARD-1/2).

At hatch end the org produces its FIRST RECEIPT locally (Captain decision
2026-07-09, Perfect Cabinet Wave A: first receipt = LOCAL-FIRST — proofs + a
first briefing carrying org-PROPOSED outcome cards; Telegram is a post-receipt
errand). This module supplies the two genesis organs behind that receipt:

ONBOARD-1 — ``propose_outcome_cards`` / ``run_genesis_proposal``: the org
PROPOSES 2–4 outcome cards derived from the cabinet-init answers (lanes, org
shape) + the optional focus letter (``instance/config/onboarding-focus.md``).
PROPOSE-ONLY by construction: every card is ``status: draft`` +
``captain_ratified: false`` and lands in ``instance/config/outcomes-proposed.yml``
— a filename the mission compiler structurally never reads (its filename gate
reads only ``instance/config/outcomes.yml``), so nothing can activate itself.
Cards carry WHAT / WHY / PROOF-expected lines per the hatching design
(docs/plans/world-onboarding-hatching-2026-07-09.md §4.2; interview
seed-outcomes are superseded — the org earns proposals by deriving them).

ONBOARD-2 — ``research_brief``: a genesis company/market/product brief into the
Library's genesis shelf (``instance/memory/library/genesis-research-brief.md``)
WHEN the local ``claude`` CLI is present, authenticated, and the network is up
— invoked via a FIXED argv (never a shell string), short timeout, graceful
failure. On ANY failure it writes an HONEST IOU note ("research brief queued —
will be produced when officers wake") instead of fake content. A delivered
brief is honestly labeled model-knowledge (no live web at genesis); officers
refresh it with sourced research when they wake.

``genesis_intake_items`` renders both surfaces (plus the focus letter) as
composer-shaped intake items for the local first briefing
(``framework.frontdoor.run_briefing --now --local-render``).

No Redis, no Telegram, no network beyond the single gated CLI invocation.
Env knobs (names-in-env doctrine; malformed values fall back, never crash):
``CABINET_GENESIS_BRIEF_TIMEOUT`` (CLI budget, default 90s) and
``CABINET_GENESIS_NET_HOST``/``_PORT`` (preflight target, default
api.anthropic.com:443 — override for Bedrock/Vertex/proxy CLIs).
Secrets doctrine: prompts and written files carry NAMES only (the answers file
is already secret-shape-refused upstream by generate-instance.py).
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ANSWERS_REL = "instance/config/cabinet-init.answers.yml"
FOCUS_REL = "instance/config/onboarding-focus.md"
PROPOSALS_REL = "instance/config/outcomes-proposed.yml"
LIBRARY_DIR_REL = "instance/memory/library"
BRIEF_REL = LIBRARY_DIR_REL + "/genesis-research-brief.md"

GENERATED_MARKER = "generated-by: framework.onboarding.genesis"
IOU_LINE = "research brief queued — will be produced when officers wake"

# Default egress for the network preflight — the brief's only dependency.
# CABINET_GENESIS_NET_HOST/_PORT override it (see _net_target) for CLIs
# pointed at Bedrock/Vertex/proxy endpoints. Names-in-env, never values here.
_NET_HOST = "api.anthropic.com"
_NET_PORT = 443

_MAX_LANE_CARDS = 2   # 2 lane cards + 2 org cards = the 2–4 band's ceiling
_DEFAULT_BRIEF_TIMEOUT = 90


def cabinet_root() -> Path:
    """Deployment root: ``CABINET_ROOT`` env (scratch instances point here),
    else this checkout (mirrors ``framework.env._cabinet_root`` semantics; kept
    local so onboarding stays import-light)."""
    env_root = os.environ.get("CABINET_ROOT")
    return Path(env_root) if env_root else Path(__file__).resolve().parents[2]


def _utc_now_iso(now: str | None = None) -> str:
    return now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write(path: Path, text: str) -> None:
    """tmp + os.replace in the target dir (the generator's own pattern)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def load_answers(root: Path | None = None) -> dict:
    """The cabinet-init answers, read-only. Absent/unparseable → ``{}`` (the
    caller decides how loud to be; the generator owns validation)."""
    base = Path(root) if root else cabinet_root()
    path = base / ANSWERS_REL
    if not path.is_file():
        return {}
    try:
        import yaml  # local: keep the module import-light
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_focus_text(root: Path | None = None) -> str | None:
    """The Captain's focus letter (ONBOARD-1 input), or None when it does not
    exist yet — an honest absence, never a synthesized stand-in."""
    base = Path(root) if root else cabinet_root()
    path = base / FOCUS_REL
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
        return text or None
    except Exception:
        return None


def _focus_excerpt(focus_text: str | None, limit: int = 200) -> str | None:
    if not focus_text:
        return None
    flat = " ".join(focus_text.split())
    return flat[:limit] if flat else None


# ---------------------------------------------------------------------------
# ONBOARD-1 — the org PROPOSES outcome cards (propose-only, never activating).
# ---------------------------------------------------------------------------
def propose_outcome_cards(answers: dict, focus_text: str | None = None) -> list[dict]:
    """PURE derivation: cabinet-init answers (+ optional focus letter) → 2–4
    proposed outcome cards.

    Card anatomy (the hatching design's proposal-card lines): ``what`` /
    ``why`` / ``proof_expected``, plus ``status: draft`` and
    ``captain_ratified: False`` — ALWAYS. Derivation is deterministic: up to
    ``_MAX_LANE_CARDS`` lane cards (declared lane order) + the two org cards
    (Library grounding, Captain decision loop), so 0 lanes → 2 cards,
    1 lane → 3, ≥2 lanes → 4. Returns [] when answers carry no cabinet id at
    all (nothing to key a proposal to — honest empty)."""
    cabinet = answers.get("cabinet") or {}
    cabinet_id = str(cabinet.get("id") or "").strip()
    if not cabinet_id:
        return []

    excerpt = _focus_excerpt(focus_text)
    focus_lower = (focus_text or "").lower()
    cards: list[dict] = []

    seen_ids: set[str] = set()
    lanes = [ln for ln in (answers.get("lanes") or []) if isinstance(ln, dict)]
    for lane in lanes[:_MAX_LANE_CARDS]:
        slug = str(lane.get("slug") or "").strip()
        name = str(lane.get("name") or slug).strip()
        if not (slug or name):
            continue
        repos = [str(r) for r in (lane.get("repos") or []) if str(r).strip()]
        why = f"You staked {name or slug} as a lane at genesis"
        if repos:
            why += f" (repos: {', '.join(repos)})"
        why += "."
        if focus_lower and (
            (slug and slug in focus_lower) or (name and name.lower() in focus_lower)
        ):
            why += " Your focus letter names this lane."
        proof = (
            "A closed task in the lane's task system linked to the shipped "
            "change" + (f" in {repos[0]}" if repos else "")
            + ", plus the action's receipt (what/why/undo) in the org journal."
        )
        # ids are keys downstream (ratification moves rows by id) — duplicate
        # lane slugs in the answers must still yield unique card ids.
        base_id = f"proposed-{slug or name.lower().replace(' ', '-')}-first-proof"
        card_id, n = base_id, 2
        while card_id in seen_ids:
            card_id, n = f"{base_id}-{n}", n + 1
        seen_ids.add(card_id)
        cards.append({
            "id": card_id,
            "name": f"First verifiable improvement shipped in the {name or slug} lane",
            "lane": slug or None,
            "what": (
                f"One reviewed, Captain-approved improvement in {name or slug} "
                "traced end-to-end: task → change → verified deploy/close."
            ),
            "why": why,
            "proof_expected": proof,
        })

    cards.append({
        "id": "proposed-library-grounding",
        "name": "The Library grounds the org: ratified company/market/product brief",
        "lane": None,
        "what": (
            "The genesis research brief is reviewed by the Captain, corrected "
            "where wrong, and ratified into the Library as the org's baseline "
            "understanding of its products and market."
        ),
        "why": (
            "Gather-then-decide is org doctrine: an org that acts before it "
            "understands invents work."
            + (" Your focus letter is the first thing it reads." if excerpt else "")
        ),
        "proof_expected": (
            "A Library record (genesis shelf: instance/memory/library/) marked "
            "captain-reviewed, cited by the officers' first proposals."
        ),
    })
    cards.append({
        "id": "proposed-captain-loop",
        "name": "The Captain decision loop is proven end-to-end",
        "lane": None,
        "what": (
            "At least one org-proposed outcome from this first briefing is "
            "ratified, edited, or rejected by the Captain, and the org visibly "
            "acts on that ruling."
        ),
        "why": (
            "The hatch posture is propose-first; the governance loop exists "
            "only once a proposal has round-tripped through the Captain."
            + (f' Your focus letter opens: "{excerpt}"' if excerpt else "")
        ),
        "proof_expected": (
            f"instance/config/outcomes.yml carries ≥1 row keyed to {cabinet_id} "
            "with captain_ratified: true (or a recorded rejection in the "
            "decisions ledger), plus the follow-up action's receipt."
        ),
    })

    for card in cards:
        card["status"] = "draft"
        card["captain_ratified"] = False
        card["proposed_by"] = "onboarding-genesis"
    return cards


def _proposals_doc(cards: list[dict], answers: dict, *, now: str,
                   focus_present: bool) -> dict:
    cabinet = answers.get("cabinet") or {}
    derived = [ANSWERS_REL] + ([FOCUS_REL] if focus_present else [])
    outcomes = []
    for card in cards:
        outcomes.append({
            "id": card["id"],
            "name": card["name"],
            "status": "draft",
            "captain_ratified": False,
            "lane": card.get("lane"),
            "what": card["what"],
            "why": card["why"],
            "proof_expected": card["proof_expected"],
            # So a Captain-ratified copy moved into outcomes.yml is already
            # outcome.schema.json-shaped (id/name/measurable_criteria).
            "measurable_criteria": [card["proof_expected"]],
        })
    return {
        "schema": "cabinet.outcomes-proposed/v1",
        "deployment": str(cabinet.get("id") or ""),
        "proposed_by": "onboarding-genesis",
        "proposed_at": now,
        "derived_from": derived,
        "outcomes": outcomes,
    }


_PROPOSALS_HEADER = """\
# instance/config/outcomes-proposed.yml — org-PROPOSED outcome cards (genesis).
# {marker} (ONBOARD-1)
#
# PROPOSE-ONLY: every row is status: draft + captain_ratified: false. The
# mission compiler reads ONLY instance/config/outcomes.yml (filename gate), so
# nothing in this file can activate itself. To ratify a card: review it, edit
# freely, then move the row into instance/config/outcomes.yml with
# status: active + captain_ratified: true. To reject: delete the row (a note
# in the decisions ledger beats silence).
"""


def write_proposals(cards: list[dict], root: Path | None = None, *,
                    answers: dict | None = None, now: str | None = None,
                    focus_present: bool = False, force: bool = False) -> dict:
    """Write the propose-only staging file. Write-once: an existing file is
    NEVER overwritten unless ``force`` (the Captain may have edited drafts) —
    the briefing composes from the file either way."""
    base = Path(root) if root else cabinet_root()
    path = base / PROPOSALS_REL
    if path.exists() and not force:
        return {"status": "kept-existing", "path": str(path), "written": False}
    import yaml  # local: keep the module import-light
    doc = _proposals_doc(cards, answers or {}, now=_utc_now_iso(now),
                         focus_present=focus_present)
    body = _PROPOSALS_HEADER.format(marker=GENERATED_MARKER)
    body += yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)
    _atomic_write(path, body)
    return {"status": "written", "path": str(path), "written": True}


def run_genesis_proposal(root: Path | None = None, *, now: str | None = None) -> dict:
    """ONBOARD-1 orchestration: answers (+ focus) → cards → staging file.

    Returns ``{'status', 'path', 'cards': n}``. ``status='no-answers'`` when
    the cabinet-init answers are absent/empty (a broken tree at hatch time —
    callers fail loudly rather than staging an empty proposal)."""
    base = Path(root) if root else cabinet_root()
    answers = load_answers(base)
    if not answers:
        return {"status": "no-answers", "path": None, "cards": 0}
    focus = load_focus_text(base)
    cards = propose_outcome_cards(answers, focus)
    if not cards:
        return {"status": "no-cards", "path": None, "cards": 0}
    res = write_proposals(cards, base, answers=answers, now=now,
                          focus_present=focus is not None)
    return {"status": res["status"], "path": res["path"], "cards": len(cards)}


# ---------------------------------------------------------------------------
# ONBOARD-2 — genesis research brief into the Library (or an honest IOU).
# ---------------------------------------------------------------------------
def build_brief_prompt(answers: dict) -> str:
    """The research-brief prompt — NAMES ONLY from the answers (lane names,
    repo refs, org shape, cabinet id). Never env values, never addresses."""
    cabinet = answers.get("cabinet") or {}
    lanes = [ln for ln in (answers.get("lanes") or []) if isinstance(ln, dict)]
    lane_lines = []
    for lane in lanes:
        name = str(lane.get("name") or lane.get("slug") or "").strip()
        repos = ", ".join(str(r) for r in (lane.get("repos") or []) if str(r).strip())
        lane_lines.append(f"- {name}" + (f" (repos: {repos})" if repos else ""))
    lanes_block = "\n".join(lane_lines) or "- (no product lanes declared yet)"
    return (
        "You are the research organ of a newly hatched autonomous AI cabinet "
        f"(deployment id: {cabinet.get('id') or 'unknown'}, org shape: "
        f"{cabinet.get('org_shape') or 'unknown'}). Write a concise "
        "company/market/product research brief (~600 words, markdown) for the "
        "product lanes below.\n\nLanes:\n" + lanes_block + "\n\n"
        "Cover per lane: what the product most plausibly is, the market it "
        "sits in, adjacent competitors worth watching, and the 3 most valuable "
        "open research questions the officers should answer first.\n"
        "OUTPUT RULES: reply with the brief text itself — do not attempt to "
        "write files or use tools.\n"
        "HONESTY RULES: you have no live web access — mark every inference as "
        "such, say 'unknown' where you do not know, and NEVER invent specific "
        "facts (figures, customers, funding) about these particular products."
    )


def _brief_timeout() -> int:
    """The CABINET_GENESIS_BRIEF_TIMEOUT env knob. Malformed or non-positive
    values fall back to the default — this module's posture is honest IOU on
    failure, never a traceback over a bad knob."""
    raw = os.environ.get("CABINET_GENESIS_BRIEF_TIMEOUT")
    if raw is None:
        return _DEFAULT_BRIEF_TIMEOUT
    try:
        val = int(raw)
    except ValueError:
        return _DEFAULT_BRIEF_TIMEOUT
    return val if val > 0 else _DEFAULT_BRIEF_TIMEOUT


def _net_target() -> tuple[str, int]:
    """Preflight target: CABINET_GENESIS_NET_HOST/_PORT env override (for CLIs
    configured against Bedrock/Vertex/proxy endpoints) over the defaults.
    Malformed/empty values fall back — a bad knob must never crash genesis."""
    host = (os.environ.get("CABINET_GENESIS_NET_HOST") or "").strip() or _NET_HOST
    try:
        port = int(os.environ.get("CABINET_GENESIS_NET_PORT", "") or _NET_PORT)
    except ValueError:
        port = _NET_PORT
    return host, port


def _default_net_check(timeout: float = 4.0) -> bool:
    try:
        socket.create_connection(_net_target(), timeout=timeout).close()
        return True
    except OSError:
        return False


def _default_run(argv: list[str], *, timeout: int, cwd: str):
    """Fixed-argv CLI invocation — never a shell string (Corridor pattern)."""
    return subprocess.run(argv, capture_output=True, text=True,
                          timeout=timeout, cwd=cwd)


def _brief_text(status: str, body: str, *, now: str, reason: str | None = None) -> str:
    fm = [
        "---",
        "schema: cabinet.genesis-brief/v1",
        f"status: {status}",
        f"{GENERATED_MARKER} (ONBOARD-2)",
        f"generated_at: {now}",
        "source: claude-cli-model-knowledge  # no live web at genesis; officers"
        " refresh with sourced research when they wake",
    ]
    if reason:
        fm.append(f"reason: {reason}")
    fm.append("---")
    return "\n".join(fm) + "\n\n" + body.rstrip() + "\n"


def _existing_brief_status(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        head = path.read_text(encoding="utf-8")[:400]
    except Exception:
        return None
    for line in head.splitlines():
        if line.startswith("status:"):
            return line.split(":", 1)[1].strip()
    return None


def research_brief(root: Path | None = None, *, run_fn=None, net_check_fn=None,
                   claude_path: str | None = "auto", timeout: int | None = None,
                   now: str | None = None) -> dict:
    """ONBOARD-2: attempt the genesis research brief; honest IOU otherwise.

    Success path: the local ``claude`` CLI invoked with the FIXED argv
    ``[claude, '-p', prompt]`` (no shell, short timeout, cwd = the instance
    root) writes its REAL output to ``instance/memory/library/
    genesis-research-brief.md`` with ``status: delivered`` provenance. ANY
    failure — missing binary, network down, non-zero exit (e.g.
    unauthenticated CLI), timeout, empty output — writes the honest IOU note
    (``IOU_LINE``: "research brief queued — will be produced when officers
    wake") with the failure named (names-not-values). Idempotent: a delivered
    brief is never overwritten; an IOU is retried/upgraded on a later run.

    Seams (tests): ``run_fn(argv, timeout=, cwd=)`` replaces the subprocess;
    ``net_check_fn()`` replaces the socket preflight; ``claude_path`` pins the
    binary ('auto' → shutil.which('claude'); None/'' → treated as missing).
    """
    base = Path(root) if root else cabinet_root()
    path = base / BRIEF_REL
    ts = _utc_now_iso(now)

    existing = _existing_brief_status(path)
    if existing == "delivered":
        return {"status": "already-delivered", "path": str(path), "written": False}

    def _iou(reason: str) -> dict:
        body = f"# Genesis research brief — IOU\n\n{IOU_LINE}.\n\n(reason: {reason})\n"
        _atomic_write(path, _brief_text("iou-queued", body, now=ts, reason=reason))
        return {"status": "iou", "path": str(path), "reason": reason, "written": True}

    answers = load_answers(base)
    if not answers:
        return _iou("cabinet-init answers not found — nothing to research yet")

    resolved = shutil.which("claude") if claude_path == "auto" else claude_path
    if not resolved:
        return _iou("claude CLI not found on PATH")

    net_ok = net_check_fn if net_check_fn is not None else _default_net_check
    if not net_ok():
        return _iou("network unreachable")

    prompt = build_brief_prompt(answers)
    argv = [resolved, "-p", prompt]
    run = run_fn or _default_run
    budget = timeout if timeout is not None else _brief_timeout()
    try:
        proc = run(argv, timeout=budget, cwd=str(base))
    except subprocess.TimeoutExpired:
        return _iou(f"claude CLI timed out after {budget}s")
    except OSError as e:
        return _iou(f"claude CLI failed to start ({e.__class__.__name__})")

    if getattr(proc, "returncode", 1) != 0:
        return _iou(f"claude CLI exited non-zero (rc={getattr(proc, 'returncode', '?')}"
                    " — likely unauthenticated)")
    out = (getattr(proc, "stdout", "") or "").strip()
    if not out:
        return _iou("claude CLI produced no output")

    title = "# Genesis research brief\n\n"
    _atomic_write(path, _brief_text("delivered", title + out, now=ts))
    return {"status": "delivered", "path": str(path), "written": True}


# ---------------------------------------------------------------------------
# The briefing gather — genesis surfaces → composer-shaped intake items.
# ---------------------------------------------------------------------------
def _load_proposal_rows(base: Path) -> list[dict]:
    path = base / PROPOSALS_REL
    if not path.is_file():
        return []
    try:
        import yaml  # local: keep the module import-light
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rows = doc.get("outcomes") if isinstance(doc, dict) else None
        return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    except Exception:
        return []


def genesis_intake_items(root: Path | None = None, now: str | None = None) -> list[dict]:
    """Read the genesis surfaces (proposals file, focus letter, research brief)
    into canonical intake items for ``composer.compose``. File reads only —
    no Redis, no network. Honest empties: absent surfaces yield NO items."""
    base = Path(root) if root else cabinet_root()
    ts = _utc_now_iso(now)
    items: list[dict] = []

    for row in _load_proposal_rows(base):
        name = str(row.get("name") or row.get("id") or "").strip()
        if not name:
            continue
        # LITERAL COUPLING: cabinet/scripts/first-briefing.sh's receipt gate
        # greps 'Proposed outcome:' — reword BOTH sides in the same commit.
        summary = (
            f"📜 Proposed outcome: {name}\n"
            f"WHAT: {row.get('what') or '—'}\n"
            f"WHY: {row.get('why') or '—'}\n"
            f"PROOF-expected: {row.get('proof_expected') or '—'}\n"
            f"Status: draft — propose-only, captain_ratified: false "
            f"(draft row: {PROPOSALS_REL}, id: {row.get('id') or '?'})"
        )
        items.append({
            "source": "onboarding-genesis", "kind": "outcome-proposal",
            "ts": ts, "urgency_tier": "batch",
            "payload": {"summary": summary},
            "context": {"why": "org-proposed at genesis (ONBOARD-1) — ratify, "
                               "edit, or reject; nothing activates itself"},
        })

    brief_status = _existing_brief_status(base / BRIEF_REL)
    if brief_status == "delivered":
        items.append({
            "source": "onboarding-genesis", "kind": "genesis-brief",
            "ts": ts, "urgency_tier": "fyi",
            "payload": {"summary": f"📚 Genesis research brief is on the Library's "
                                   f"genesis shelf: {BRIEF_REL} (model-knowledge "
                                   "at genesis; officers refresh it with sourced "
                                   "research when they wake)"},
            "context": {"why": "ONBOARD-2 delivered"},
        })
    elif brief_status == "iou-queued":
        items.append({
            "source": "onboarding-genesis", "kind": "genesis-brief",
            "ts": ts, "urgency_tier": "fyi",
            "payload": {"summary": f"📚 {IOU_LINE} (IOU on file: {BRIEF_REL})"},
            "context": {"why": "ONBOARD-2 honest IOU — no fake content"},
        })

    if (base / FOCUS_REL).is_file():
        items.append({
            "source": "onboarding-genesis", "kind": "genesis-focus",
            "ts": ts, "urgency_tier": "fyi",
            "payload": {"summary": f"🧭 Your focus letter is on file ({FOCUS_REL}) "
                                   "— the proposals above are anchored to it"},
            "context": {"why": "the first letter carries bearing, not tasks"},
        })
    return items


def main(argv: list[str] | None = None) -> int:  # pragma: no cover — thin CLI
    """CLI: run ONBOARD-1 (propose) then ONBOARD-2 (brief attempt).

        python3.12 -m framework.onboarding.genesis [--propose-only]

    Exit 3 when the cabinet-init answers are missing (broken tree at hatch
    time — fail loudly, don't stage an empty proposal)."""
    import argparse
    import json
    import sys

    ap = argparse.ArgumentParser(prog="framework.onboarding.genesis")
    ap.add_argument("--propose-only", action="store_true",
                    help="run ONBOARD-1 only (skip the research-brief attempt)")
    args = ap.parse_args(argv)

    proposal = run_genesis_proposal()
    if proposal["status"] == "no-answers":
        print(f"genesis: {ANSWERS_REL} missing/empty — run cabinet-init + "
              "generate-instance first", file=sys.stderr)
        return 3
    result = {"proposal": proposal}
    if not args.propose_only:
        result["brief"] = research_brief()
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys
    sys.exit(main())
