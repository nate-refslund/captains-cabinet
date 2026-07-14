"""framework.comms.surface.overview_card — the standing overview pin
(``pin_mode: overview``, Captain-ratified 2026-07-10).

ONE live standing card — "⚑ N need you" + the top item names when N≤5 —
edited in place as the census changes; the card itself IS the pin. This is
the ratified replacement for pin-as-single-item (see
framework/docs/captain-surface-pin-recommendation-2026-07-10.md): one
message, one truth, zero pin-swap notification churn (edits are silent).

Pure renderer: census dict → ``send_card`` kwargs. Identity is the constant
engine-owned anchor ``thread:comms-surface-pin-overview`` — the same anchor
on every re-render, so the gate's standing-card dedup edits the one message
in place forever. Item names ride as step TITLES (the gate's default render
gives each its own line; the free-``situation`` line is capped at 200 chars).

The card is a GLANCE surface: it deliberately carries NO ``·pid·`` marker
(same law as the retired queue card — a summary card with many bindable
items would collide with the binder's last-marker heuristic) and no decision
buttons; decisions live on each item's own card / the dashboard.

"Why only you" sentences (the partial-refusal ruling's per-item one-liners)
are instance RUNTIME data, not census data: an optional map at
``$CABINET_ATTENTION_DIR/why-captain.json`` (``{item_id: plain sentence}``).
Read fail-closed — absent/corrupt file ⇒ names only. All free text is
scrubbed (no ``·`` — marker-hygiene law — no newlines, hard caps).
"""
from __future__ import annotations

import json
from datetime import datetime

from framework.attention import plain as plainlaw
from framework.comms.surface import config as _cfg
from framework.comms.surface import links as _links

#: Constant identity anchor — the gate keys the ONE standing card off this.
EVIDENCE = ["thread:comms-surface-pin-overview"]
KIND = "triage-nudge"          # existing charter class: route direct-now
SUBJECT_DARK = plainlaw.COPY["masthead_dark"]            # "Nothing needs you."

WHYS_FILE = "why-captain.json"
# Step-title budget: the gate's default render caps a step title at 120
# chars, so name(66) + " — "(3) + why(51) = 120 — nothing truncates mid-
# sentence downstream (review 2026-07-10 finding #3).
_NAME_CAP = 66
_WHY_CAP = 51
_TOP_NAMES_MAX = 5             # ratified: top names render only when N ≤ 5


def _scrub(text, cap: int) -> str:
    """One-line, marker-free, capped — every free-text fragment on the card."""
    s = " ".join(str(text or "").replace("·", "").split())
    return s[:cap].strip()


def load_whys(path=None) -> dict:
    """The optional item_id → "why only you" map. {} on absent/corrupt file
    (fail-closed); values scrubbed on read, never trusted raw. A value that
    trips the plain-language linter is DROPPED — runtime data gets no bypass
    around the law the renderer's own copy obeys (review finding #5)."""
    p = path or (_cfg.attention_dir() / WHYS_FILE)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        out = {}
        for k, v in data.items():
            if not (isinstance(v, str) and v.strip()):
                continue
            s = _scrub(v, _WHY_CAP)
            if s and not plainlaw.lint(s):
                out[str(k)] = s
        return out
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _open_decisions(census: dict) -> list:
    from framework.comms.surface import decision_card as _dc
    return [c for c in census.get("decisions") or []
            if isinstance(c, dict) and _dc.is_decision(c)]


def count_of(census: dict) -> int:
    """The honest room count: the census' own captain-pending tally, floored
    by what the Decisions shelf actually shows (never a phantom count)."""
    decisions = _open_decisions(census)
    n = census.get("pending_captain_items")
    if isinstance(n, (int, float)) and int(n) >= 0:
        return max(int(n), len(decisions))
    return len(decisions)


def subject_of(n: int) -> str:
    if n <= 0:
        return SUBJECT_DARK
    word = plainlaw.COPY["masthead_need_one"] if n == 1 \
        else plainlaw.COPY["masthead_need_many"]
    return f"⚑ {n} {word}"


def render(census: dict, *, now: "datetime | None" = None,
           cfg: "dict | None" = None, whys: "dict | None" = None) -> dict:
    """The full ``send_card`` kwargs for the ONE standing overview card."""
    cfg = cfg or _cfg.load()
    whys = load_whys() if whys is None else whys
    decisions = _open_decisions(census)
    n = count_of(census)

    steps: list = []
    if 0 < n <= _TOP_NAMES_MAX:
        for card in decisions[:_TOP_NAMES_MAX]:
            title = _scrub(card.get("what"), _NAME_CAP) \
                or plainlaw.COPY["no_title"]
            why = whys.get(str(card.get("id") or ""))
            if why:
                title = f"{title} — {why}"
            steps.append({"title": title})

    if n <= 0:
        situation = plainlaw.COPY["masthead_dark_sub"]
    elif n <= _TOP_NAMES_MAX:
        situation = ("Each one has its own message — decide there. "
                     "This pinned list updates by itself.")
    else:
        situation = (f"The first {_TOP_NAMES_MAX} have their own messages; "
                     "open the list for the rest.")
    url = _links.queue_url(cfg)
    if url and n > 0:
        line = _links.details_line(url)
        if line and len(situation) + len(line) + 1 <= 200:
            situation = f"{situation} {line}"

    return {
        "subject": subject_of(n),
        "situation": situation,
        "kind": KIND,
        "lane": None,
        "evidence": list(EVIDENCE),
        "steps": steps,
        "state": "open",           # the standing card never goes terminal —
                                   # its all-clear face IS the n=0 render
        "deadline_iso": None,
        "pid_marker": None,        # glance surface: never bindable
        "buttons": None,
    }
