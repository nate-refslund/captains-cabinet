"""framework.onboarding.genesis — the genesis half of onboarding (ONBOARD-1/2).

At hatch end the org produces its FIRST RECEIPT locally (Captain decision
2026-07-09, Perfect Cabinet Wave A: first receipt = LOCAL-FIRST — proofs + a
first briefing carrying org-PROPOSED outcome cards; Telegram is a post-receipt
errand). This module supplies the two genesis organs behind that receipt:

ONBOARD-1 — ``propose_outcome_cards`` / ``run_genesis_proposal``: the org
PROPOSES 2–4 outcome cards derived from the DERIVED ESTATE (what the cabinet
READ — ``framework.onboarding.estate``) and the cabinet-init answers (lanes,
org shape, and — when the purpose-first interview recorded one — the
``mission:`` block) + the focus letter (``instance/config/onboarding-focus.md``,
a first-class Phase-0 artifact since onboarding-vision-2026-07-14; still
tolerated absent).

THE ESTATE IS A FIRST-CLASS INPUT BESIDE THE ANSWERS FILE (Captain ruling
2026-07-26, ordering inversion). Before it, cards were composed ONLY from the
answers, so a ``--defaults`` hatch derived them from a placeholder lane named
"First Lane" and the first real briefing scored 1 of 3 with — the Captain's
word — irrelevant cards. Now: declared lanes still win (they are the Captain's
own ratified statement), estate ENTITIES fill the remaining subject slots with
their citations, and when there is neither, one leftover-question card asks the three
questions that are un-derivable by construction — which sources are yours to
grant, what actually matters this week, what must this never be touched — plus
the human-shaped seed question for an operator who has connected nothing. What
never appears again is "tell us what your company is": a developer inside a
large company has no answer to it, and the correct product behaviour is not to
ask it.

ALTITUDE CONDITIONS THE PROOF LINE, and this is the point of carrying it at
all. ``mission.altitude`` (contributor | project | team | function | company)
is the operator's rung. At function/company altitude a card's proof is a
shipped, closed, deployed change. At contributor/project/team altitude that
proof is unreachable BY ORG CHART, not by cabinet quality — the six ceiling
classes belong to the employer — so the proof becomes proposal-shaped: a
written proposal citing evidence the operator could not previously assemble,
delivered to whoever owns the decision, and the decision it changed. The
promise at low altitude is expanded REACH and PROPOSAL QUALITY, never expanded
permission. An ABSENT altitude derives byte-identical cards to the
pre-altitude behaviour — unknown is a first-class answer.
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

THE BRIEFING READS WHAT RECALL HOLDS (2026-07-28, measured). Until this,
NOTHING in the genesis chain ever called ``framework.sources.get_source()``:
cards came from the answers file and the derived estate only. An agent ran the
genuine hatch path and scored the resulting briefing 1 of 3 — "read it, no
value" — while recall on that same box was live and its notes held a live
incident spread across three files that no card mentioned. ``probe_recall``
now asks the bound seam about each declared subject and hands the hits to
``propose_outcome_cards`` as DATA (the function stays pure, exactly as it does
for ``estate``), so a card can quote the operator's own sentence, cite the
file#heading it came from with its derived date, and name the terms two of
their files share. Deterministic string work throughout — no LLM, no network,
no writes — and when recall holds nothing the cards are byte-identical to the
pre-recall derivation, because an unearned citation is the defect this exists
to remove. ``CABINET_GENESIS_RECALL=0`` skips the probe.

``genesis_intake_items`` renders all of these surfaces (plus the focus letter)
as composer-shaped intake items for the local first briefing
(``framework.frontdoor.run_briefing --now --local-render``), including a
``genesis-recall`` provenance card that states whether recall was live, unbound
or unconsulted — the negative cases are the load-bearing ones.

``merge_proposals`` (onboarding design 2026-07-14 Phase 1) is the
MERGE-BY-CARD-ID writer other organs use to ADD cards to the staging file
after genesis: existing rows (Captain-edited or not) are preserved verbatim,
only NEW ids are appended — the merge complement to ``write_proposals``'s
write-once protection, same propose-only file, same draft-only rows.

No Redis, no Telegram, no network beyond the single gated CLI invocation.
Env knobs (names-in-env doctrine; malformed values fall back, never crash):
``CABINET_GENESIS_BRIEF_TIMEOUT`` (CLI budget, default 90s),
``CABINET_GENESIS_NET_HOST``/``_PORT`` (preflight target, default
api.anthropic.com:443 — override for Bedrock/Vertex/proxy CLIs), and
``CABINET_GENESIS_RECALL=0`` (skip the recall probe entirely).
Secrets doctrine: prompts and written files carry NAMES only (the answers file
is already secret-shape-refused upstream by generate-instance.py).
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ANSWERS_REL = "instance/config/cabinet-init.answers.yml"
FOCUS_REL = "instance/config/onboarding-focus.md"
PROPOSALS_REL = "instance/config/outcomes-proposed.yml"
# The recall BINDING this deployment resolved — named so the briefing can point
# an operator at the one file that decides what recall reads.
SOURCES_REL = "instance/config/sources.yml"
LIBRARY_DIR_REL = "instance/memory/library"
BRIEF_REL = LIBRARY_DIR_REL + "/genesis-research-brief.md"
FIRST_BRIEFING_DIR_REL = "instance/memory"

GENERATED_MARKER = "generated-by: framework.onboarding.genesis"
IOU_LINE = "research brief queued — will be produced when officers wake"

# Default egress for the network preflight — the brief's only dependency.
# CABINET_GENESIS_NET_HOST/_PORT override it (see _net_target) for CLIs
# pointed at Bedrock/Vertex/proxy endpoints. Names-in-env, never values here.
_NET_HOST = "api.anthropic.com"
_NET_PORT = 443

_MAX_LANE_CARDS = 2   # 2 subject cards + 2 org cards = the 2–4 band's ceiling
_DEFAULT_BRIEF_TIMEOUT = 90

# The rungs where the six ceiling classes (external comms, prod deploy, spend,
# secrets, network write, credential grant) are NOT the operator's to grant,
# because they belong to their employer. A card whose proof needs one of them
# is unreachable there through no fault of the cabinet, so the proof changes
# shape rather than the operator being handed a bar set by org chart.
_LOW_ALTITUDES = frozenset({"contributor", "project", "team"})


def cabinet_root() -> Path:
    """Deployment root: ``CABINET_ROOT`` env (scratch instances point here),
    else this checkout (mirrors ``framework.env._cabinet_root`` semantics; kept
    local so onboarding stays import-light)."""
    env_root = os.environ.get("CABINET_ROOT")
    return Path(env_root) if env_root else Path(__file__).resolve().parents[2]


def first_briefing_path(date: str) -> Path:
    """Where the LOCAL-FIRST genesis receipt lands: the first-briefing
    markdown on the instance memory surface (Captain ruling 2026-07-09,
    Perfect Cabinet Wave A). Path knowledge lives HERE beside the other
    genesis instance surfaces (layer-separation FINAL-C: frontdoor composes
    the text; onboarding owns where genesis artifacts live)."""
    return cabinet_root() / FIRST_BRIEFING_DIR_REL / f"first-briefing-{date}.md"


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


def _mission_fields(answers: dict) -> tuple[str | None, str | None, list[str]]:
    """The purpose-first interview's ``mission:`` block (Phase 2,
    onboarding-vision-2026-07-14 §4), tolerantly read: absent/malformed →
    all-empty (missionless answers MUST derive byte-identical cards to
    today — the block only ever ADDS conditioning, never restructures).
    Returns (purpose, success_90d, never_touch) as flattened, length-capped
    excerpts — pure string work, no I/O, no LLM (the design forbids TTFR
    creep inside the hatch chain)."""
    mission = answers.get("mission")
    if not isinstance(mission, dict):
        return None, None, []
    purpose = _focus_excerpt(str(mission.get("purpose") or "") or None, 160)
    success = _focus_excerpt(str(mission.get("success_90d") or "") or None, 160)
    raw_never = mission.get("never_touch")
    never = []
    if isinstance(raw_never, list):
        never = [" ".join(str(n).split()) for n in raw_never if str(n).strip()]
    return purpose, success, never[:3]


def _low_altitude(answers: dict) -> bool:
    """True when the operator declared a rung whose action space is bounded by
    org chart. Absent/unknown → False, i.e. exactly today's cards."""
    from framework.onboarding import estate as _estate  # local: import-light
    return (_estate.altitude_of(answers) or "") in _LOW_ALTITUDES


def _subject_proof(name: str, repos: list, low: bool) -> str:
    """The proof line for a subject card, at the operator's altitude."""
    if low:
        return (
            "A written proposal about " + name + " that cites evidence "
            "assembled across what you already read"
            + (f" (incl. {repos[0]})" if repos else "")
            + ", delivered to whoever owns the decision — plus what they "
            "decided. Reach and proposal quality, not permission you do not "
            "hold."
        )
    return (
        "A closed task in the lane's task system linked to the shipped "
        "change" + (f" in {repos[0]}" if repos else "")
        + ", plus the action's receipt (what/why/undo) in the org journal."
    )


def _estate_subject_cards(estate: dict, taken: set, seen_ids: set, *,
                          purpose: str | None, low: bool, limit: int,
                          recall: dict | None = None) -> list[dict]:
    """Subject cards derived from what the cabinet READ, each carrying the
    citation that produced it. Entities whose slug already came from a
    declared lane are skipped: the Captain's own declaration wins over a
    derivation of the same thing."""
    cards: list[dict] = []
    for ent in (estate.get("entities") or []):
        if len(cards) >= limit:
            break
        if not isinstance(ent, dict):
            continue
        slug = str(ent.get("id") or "").strip()
        name = str(ent.get("name") or slug).strip()
        if not (slug or name) or slug in taken:
            continue
        taken.add(slug)
        subject = _recall_subject(recall, slug, name)
        cites = [str(c.get("path")) for c in (ent.get("evidence") or [])
                 if isinstance(c, dict) and c.get("path")]
        why = (f"I found {name or slug} by reading your world, not by asking: "
               + (f"{', '.join(cites[:2])} " if cites else "")
               + f"under the folder you granted (path: {ent.get('relative_path') or '.'}). "
               "Correct me if this is not a thing you work on.")
        why += _recall_why(subject)
        if purpose:
            why += f' The mission it serves: "{purpose}"'
        base_id = f"proposed-{slug or 'entity'}-first-proof"
        card_id, n = base_id, 2
        while card_id in seen_ids:
            card_id, n = f"{base_id}-{n}", n + 1
        seen_ids.add(card_id)
        cards.append({
            "id": card_id,
            "name": _recall_card_name(
                name or slug, subject,
                f"First verifiable improvement in {name or slug}"),
            "lane": slug or None,
            # STAYS "estate" EVEN WHEN RECALL ENRICHED IT (fixed 2026-07-28).
            # This card exists because the ESTATE named the entity; recall only
            # added quotes and cites, and `recall_refs` below already records
            # that (it is what the briefing's recall item counts). Overwriting
            # the field dropped the estate's own provenance count to zero, so
            # genesis_intake_items told the operator "No card above derives
            # from it: the proposals on file were written before this estate
            # existed. Re-run genesis" about a card written from that estate in
            # that same run — an ordering story told about a card that has no
            # ordering problem, i.e. the exact defect the recall item was
            # corrected for, one surface over. Reproduced before the fix.
            "derived_from": "estate",
            "what": _subject_what(name or slug, low, subject,
                                  evidence_derived=True),
            "why": why,
            "proof_expected": _subject_proof(name or slug, [], low),
            **({"recall_refs": list(subject.get("refs") or [])}
               if subject and subject.get("refs") else {}),
        })
    return cards


def recall_state(recall: dict | None) -> str:
    """ONE sentence naming which of four states the recall seam is in.

    "you granted no folder", "the folder you named is gone", "it is bound and
    holds nothing", "it could not be reached" — four states with four different
    fixes, which a bare ``available: false`` collapses into one. Empty string
    when recall is LIVE (there is then nothing to explain). Single source: the
    residual card and the briefing's provenance card both render it, so the two
    surfaces cannot drift into telling the operator different things."""
    if not isinstance(recall, dict) or not recall.get("consulted"):
        reason = (recall or {}).get("error") if isinstance(recall, dict) else None
        return f"not consulted this run ({reason})" if reason else "not consulted this run"
    if recall.get("error") and not recall.get("available"):
        return f"could not be reached ({recall['error']})"
    if recall.get("available"):
        return ""
    binding = recall.get("binding") or {}
    if binding and not binding.get("declared"):
        return ("bound to NOTHING — no folder has been granted, so it answers "
                "nothing rather than guessing. Declare sources.notes_root in "
                + ANSWERS_REL + " and re-run "
                "cabinet/scripts/generate-instance.py, or export "
                "CABINET_LOCAL_SOURCE_ROOT")
    if binding.get("declared") and not binding.get("exists"):
        return f"pointed at {binding.get('root')}, which does not exist"
    return "bound but holding nothing readable yet"


def _residual_card(estate: dict | None, low: bool,
                   recall: dict | None = None) -> dict:
    """The card that replaces "tell us what your company is".

    Three questions, and every one of them is un-derivable BY CONSTRUCTION —
    the answer is not in any data the cabinet could read. Plus the seed
    question for the operator who has connected nothing at all, because a
    cabinet with no sources must still never be a dead end.

    It also states the RECALL binding's real state, because "I have nothing to
    say about your world" and "I am not pointed at your world" are different
    sentences with different fixes, and only one of them is the operator's to
    act on."""
    read_anything = bool((estate or {}).get("sources"))
    opening = (
        "I read what you granted and found nothing I could honestly call a "
        "product or project of yours."
        if read_anything else
        "I have not read anything of yours yet, so I am not going to guess "
        "what you work on."
    )
    return {
        "id": "proposed-read-your-world",
        "name": "Point me at your world — then I stop asking and start reading",
        "lane": None,
        "derived_from": "residual",
        "what": (
            "Grant one read-only First Window (a folder, a repo checkout, a "
            "docs tree) and let discovery derive your lanes: "
            "bash cabinet/scripts/formation.sh — proposals land in "
            "instance/config/lanes-proposed.yml for you to ratify. Nothing "
            "is activated, nothing is sent, nothing is written back."
        ),
        "why": (
            opening + " Three things I cannot derive from any data, so I ask "
            "them and nothing else: (1) which of these sources are yours to "
            "grant? (2) of what I show you, what actually matters to you this "
            "week? (3) what must I never touch? If you would rather start by "
            "talking: tell me what you do and how I can best serve you — a "
            "few words is enough to go find the rest."
            + (" At your altitude the answer is reach, not permission: I can "
               "assemble context nobody at your level holds, and I will never "
               "claim authority that is not yours to give." if low else "")
            + (f" Recall is {recall_state(recall)}." if recall_state(recall) else "")
        ),
        "proof_expected": (
            "instance/onboarding/formation/derived-estate.yml exists with at "
            "least one source, and instance/config/lanes-proposed.yml carries "
            "a lane you ratified into "
            "instance/config/cabinet-init.answers.yml."
        ),
    }


# ---------------------------------------------------------------------------
# RECALL — the briefing READS what recall already holds (2026-07-28).
#
# MEASURED, and this is the whole reason the block exists: an agent ran the
# genuine hatch path and scored the resulting first briefing 1 of 3 — "read it,
# no value". Recall itself WORKED on that same box (available() True; three
# probes returned dated, cited hits), and its notes folder held a live incident
# whose pieces sat in three different files — a latency regression traceable to
# a migration cutover, a rollback window closing the same week an error budget
# ran out. The briefing referenced NONE of it, because nothing in the genesis
# chain ever called get_source(). Cards were composed from the answers file and
# the derived estate only, so the best the org could say about a lane was that
# the operator had declared it.
#
# WHAT THIS DOES: derives probes from what the operator DECLARED (lanes,
# mission, focus letter, estate entities), asks the BOUND recall seam for each,
# and hands the hits back as DATA. ``propose_outcome_cards`` stays PURE — it
# receives this dict exactly the way it already receives ``estate`` — so the
# no-I/O contract the hatch chain depends on is unchanged, and every card that
# cites a note can be checked against a file the operator can open.
#
# NO LLM, NO NETWORK, NO WRITES. The join is term overlap across DISTINCT
# files, the dates are the hits' own ``content_ts`` (derived or absent, never
# mtime), and the quotes are verbatim excerpts of the operator's own text. A
# card that cites nothing checkable is worse than no card, so nothing here ever
# asserts a relationship the citations do not already show.
# ---------------------------------------------------------------------------
_MAX_RECALL_PROBES = 4      # subjects asked about — the card band is 2–4 anyway
_MAX_RECALL_HITS = 8        # hits examined per subject
_MAX_RECALL_FILES = 3       # DISTINCT files named on a card — the join unit
_MAX_QUOTE = 200            # chars of the operator's own words, verbatim
_MIN_JOIN_FILES = 2         # a "join" needs at least two DIFFERENT files
_MAX_JOIN_TERMS = 4
_MIN_JOIN_TERM_LEN = 4

# Terms that co-occur in any two English notes and therefore say nothing about
# what those notes share. Deliberately small and literal: a bigger list would
# start suppressing real domain words, and the failure mode of THIS surface is
# a card that claims a connection the operator cannot see.
_JOIN_STOPWORDS = frozenset({
    "about", "after", "again", "against", "already", "also", "another", "any",
    "because", "been", "before", "being", "between", "both", "but", "came",
    "can", "cannot", "come", "could", "did", "does", "done", "down", "during",
    "each", "even", "ever", "every", "first", "for", "from", "get", "give",
    "going", "had", "has", "have", "here", "how", "into", "issue", "its",
    "just", "keep", "know", "last", "like", "made", "make", "many", "may",
    "more", "most", "much", "must", "need", "next", "not", "note", "notes",
    "now", "off", "one", "only", "other", "our", "out", "over", "own", "put",
    "same", "see", "shall", "should", "since", "some", "still", "such", "take",
    "than", "that", "the", "their", "them", "then", "there", "these", "they",
    "thing", "things", "this", "those", "through", "time", "today", "too",
    "took", "under", "until", "upon", "use", "used", "using", "very", "want",
    "was", "way", "week", "well", "were", "what", "when", "where", "which",
    "while", "who", "why", "will", "with", "work", "would", "year", "yet",
    "you", "your",
})

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")


def _flatten(text: str, limit: int) -> str:
    """One line of the operator's own words, control characters stripped and
    length-capped. VERBATIM otherwise — the value of a quote is that it can be
    checked against the file, and a paraphrase cannot be."""
    flat = " ".join(str(text or "").split())
    flat = "".join(ch for ch in flat if ch.isprintable())
    return flat[:limit].rstrip() + ("…" if len(flat) > limit else "")


def _body_of(hit: dict) -> str:
    """The hit's body WITHOUT the heading the citation already names.

    Adapters chunk as ``heading + "\\n" + body``, so the heading is inside
    ``text`` as well as beside it. Every operator-facing use of a hit's words
    must run through here: the heading is the cabinet's own chunk boundary
    label, not the operator's material, and rendering it as theirs is the
    defect the frontmatter strip (``local._strip_frontmatter``) was landed for
    one layer down."""
    text = str(hit.get("text") or "")
    heading = str(hit.get("heading") or "").strip()
    if heading and text.lstrip().startswith(heading):
        text = text.lstrip()[len(heading):]
    return text


def _quote_of(hit: dict) -> str:
    """The operator's own sentence, without the heading the citation already
    names. A raw flatten reads "What we know The billing migration moved…" —
    the heading twice, and fewer of their actual words inside the cap."""
    return _flatten(_body_of(hit), _MAX_QUOTE)


def _cite(hit: dict) -> str:
    """``path#heading (dated YYYY-MM-DD)`` — the handle the operator opens.

    An absent ``content_ts`` renders "(undated)" rather than a guess: the local
    adapter refuses to derive a date from mtime, and inventing one here would
    put a fabricated timestamp on a card the operator is asked to trust."""
    ref = str(hit.get("ref") or hit.get("path") or "?")
    ts = str(hit.get("content_ts") or "")
    return f"{ref} (dated {ts[:10]})" if ts else f"{ref} (undated)"


def _query_terms(text: str) -> set:
    return {w.lower() for w in _WORD_RE.findall(text or "")}


# CALLERS PASS ONLY THE HITS THE CARD WILL CITE (fixed 2026-07-28, reproduced
# through the real adapter and the real `first-briefing.sh --local` chain). This
# used to be called with all `_MAX_RECALL_HITS` (8) hits while the card names at
# most `_MAX_RECALL_FILES` (3) of them, so on any corpus answering from four or
# more files the "Shared wording:" clause could name a term appearing in NONE of
# the files printed beside it — measured: three cited notes about widget
# alignment, invoice numbering and onboarding copy, captioned "Shared wording:
# kubernetes", a word living only in two older notes the card never showed. The
# operator finds that out the moment they do what the card tells them and open
# the three files, which is the unearned-claim defect this whole surface exists
# to remove, appearing on the surface itself.
def _join_terms(cited: list, query: str) -> list:
    """Terms shared by at least ``_MIN_JOIN_FILES`` of the DISTINCT files this
    card CITES, minus the query's own terms and the stopwords.

    This is the join, and it is deliberately weak on purpose: it reports that
    several of the operator's notes use the same words — checkable by opening
    the very files named beside it, which is why the scope is the CITED set and
    not the wider hit list. It never claims causality; they make that call."""
    asked = _query_terms(query)
    per_file: dict = {}
    for hit in cited:
        path = str(hit.get("path") or hit.get("ref") or "")
        # BODY ONLY (fixed 2026-07-28, measured through the real
        # `first-briefing.sh --local` chain on an Obsidian vault). This used to
        # be `heading + " " + text` — and since adapters chunk as
        # `heading + "\n" + body`, that counted the heading TWICE. Three daily
        # notes cited as `1-Daily/<date>.md#Summary` therefore rendered
        # "Shared wording: verification, network, summary, active": `summary`
        # is the markdown heading the citation already prints beside it, shared
        # by every note that has one, and present in NONE of their bodies. The
        # operator is being told the cabinet's own chunk label is their own
        # recurring wording — the same machinery-as-material defect the
        # frontmatter strip removed one layer down.
        blob = _body_of(hit)
        terms = {t for t in _query_terms(blob)
                 if len(t) >= _MIN_JOIN_TERM_LEN
                 and t not in _JOIN_STOPWORDS and t not in asked
                 and not t.isdigit()}
        per_file.setdefault(path, set()).update(terms)
    counts: dict = {}
    for terms in per_file.values():
        for term in terms:
            counts[term] = counts.get(term, 0) + 1
    shared = [t for t, n in counts.items() if n >= _MIN_JOIN_FILES]
    shared.sort(key=lambda t: (-counts[t], -len(t), t))
    return shared[:_MAX_JOIN_TERMS]


def recall_probes(answers: dict, focus_text: str | None = None, *,
                  estate: dict | None = None) -> list[dict]:
    """The subjects worth asking recall about, derived from what the operator
    DECLARED — never invented. ``[{'key', 'label', 'query'}]``, deduped by key,
    capped at ``_MAX_RECALL_PROBES``.

    Declared lanes first (the Captain's own statement), then estate entities
    (what the cabinet read). An operator who declared nothing and granted
    nothing yields NO probes: there is nothing to ask about, and a probe
    invented here would be the guessing this whole direction removes."""
    purpose, success, _never = _mission_fields(answers)
    tail = " ".join(x for x in (purpose, success,
                                _focus_excerpt(focus_text, 120)) if x)
    out: list[dict] = []
    seen: set = set()

    def _add(key: str, label: str, extra: str = "") -> None:
        key = (key or label or "").strip().lower()
        if not key or key in seen or len(out) >= _MAX_RECALL_PROBES:
            return
        seen.add(key)
        out.append({"key": key, "label": label,
                    "query": " ".join(x for x in (label, extra) if x).strip()})

    for lane in (answers.get("lanes") or []):
        if isinstance(lane, dict):
            slug = str(lane.get("slug") or "").strip()
            name = str(lane.get("name") or slug).strip()
            if slug or name:
                _add(slug or name, name or slug,
                     " ".join(str(r) for r in (lane.get("repos") or [])))
    for ent in ((estate or {}).get("entities") or []):
        if isinstance(ent, dict):
            slug = str(ent.get("id") or "").strip()
            name = str(ent.get("name") or slug).strip()
            if slug or name:
                _add(slug or name, name or slug)
    # The mission/focus text is a probe of its own ONLY when it is all there
    # is: it is a sentence, not a subject, and it would otherwise dilute every
    # subject query it was appended to.
    if not out and tail:
        _add("mission", _flatten(tail, 80))
    return out


def _recall_enabled() -> bool:
    """``CABINET_GENESIS_RECALL=0`` skips the probe entirely.

    The one kill-switch, and it exists because a CONFIGURED org box's
    ``search()`` shells out to the memory backend: an operator who needs the
    hatch receipt to depend on nothing but local files can turn the probe off
    and still get a briefing (composed from the answers and the estate, exactly
    as before this landed). Any other value, including absent, means on."""
    return (os.environ.get("CABINET_GENESIS_RECALL", "") or "").strip() != "0"


def probe_recall(answers: dict, focus_text: str | None = None, *,
                 estate: dict | None = None, source=None,
                 root: Path | None = None) -> dict:
    """Ask the BOUND recall seam about each derived probe. I/O lives here.

    Returns ``{'consulted', 'adapter', 'available', 'binding', 'probes',
    'subjects', 'hits_total', 'error'}``. NEVER RAISES: recall is an input to
    the first receipt, not a dependency of it, so a broken or unbound seam
    degrades to ``available: False`` with the reason recorded — the briefing
    then says so in the operator's own terms instead of silently composing
    cards that cite nothing.

    ``source`` is the test seam; the default is ``framework.sources.get_source()``,
    i.e. whatever THIS deployment actually bound.

    ROOT GUARD: ``get_source()`` resolves its binding from ``CABINET_ROOT``, so
    it answers for THAT deployment and no other. When ``root`` names a
    different tree (a scratch instance, a hermetic test root) the seam is NOT
    consulted — probing the live checkout's binding on behalf of a scratch
    instance would attribute one deployment's recall to another. Pass
    ``source=`` to probe a specific one."""
    result = {"consulted": False, "adapter": "", "available": False,
              "binding": {}, "probes": [], "subjects": [], "hits_total": 0,
              "error": None}
    probes = recall_probes(answers, focus_text, estate=estate)
    result["probes"] = [p["label"] for p in probes]
    if source is None and not _recall_enabled():
        result["error"] = "skipped: CABINET_GENESIS_RECALL=0"
        return result
    if source is None and root is not None:
        try:
            same = Path(root).resolve() == cabinet_root().resolve()
        except OSError:
            same = False
        if not same:
            result["error"] = ("skipped: the bound recall seam answers for "
                               "CABINET_ROOT, not this root")
            return result
    try:
        if source is None:
            from framework import sources as _sources  # local: import-light
            source = _sources.get_source()
        result["consulted"] = True
        result["adapter"] = (f"{type(source).__module__}:"
                             f"{type(source).__name__}")
        status = getattr(source, "binding_status", None)
        if callable(status):
            got = status()
            result["binding"] = got if isinstance(got, dict) else {}
        result["available"] = bool(source.available())
    except Exception as e:  # noqa: BLE001 — recall never blocks the receipt
        result["error"] = f"{type(e).__name__}: {e}"[:200]
        return result
    if not result["available"]:
        return result

    for probe in probes:
        try:
            found = source.search(probe["query"]) or {}
            hits = [h for h in (found.get("hits") or []) if isinstance(h, dict)]
        except Exception as e:  # noqa: BLE001 — one bad probe never kills the rest
            result["error"] = result["error"] or f"{type(e).__name__}: {e}"[:200]
            continue
        if not hits:
            continue
        kept = hits[:_MAX_RECALL_HITS]
        # ONE ENTRY PER FILE, NEWEST FIRST. Two headings out of the same note
        # are one source, and listing both reads as a join that is not there;
        # and the useful order is TIME, not retrieval score — "these notes of
        # yours span these weeks and were never read together" is the finding,
        # while score order buries the live one behind whichever page repeats
        # the query terms most (measured: an ownership footnote outranked the
        # latency regression it was a footnote to).
        by_file: dict = {}
        for hit in kept:
            path = str(hit.get("path") or hit.get("ref") or "")
            if path and path not in by_file:
                by_file[path] = hit
        ordered = sorted(
            by_file.values(),
            key=lambda h: (str(h.get("content_ts") or ""),
                           float(h.get("base_score") or 0.0)),
            reverse=True)[:_MAX_RECALL_FILES]
        dates = sorted({str(h.get("content_ts") or "")[:10]
                        for h in ordered if h.get("content_ts")})
        result["subjects"].append({
            "key": probe["key"],
            "label": probe["label"],
            "query": probe["query"],
            "files": [str(h.get("path") or h.get("ref") or "") for h in ordered],
            "cites": [_cite(h) for h in ordered],
            "dates": list(reversed(dates)),
            "span": (f"{dates[0]} … {dates[-1]}"
                     if len(dates) > 1 else (dates[0] if dates else "")),
            # ``ordered``, never ``kept``: the shared wording must be checkable
            # in the files this card actually prints (see _join_terms' header).
            "shared_terms": _join_terms(ordered, probe["query"]),
            "quote": _quote_of(ordered[0]) if ordered else "",
            "top_cite": _cite(ordered[0]) if ordered else "",
            "refs": [str(h.get("ref") or h.get("path") or "") for h in ordered],
        })
        result["hits_total"] += len(kept)
    return result


def _recall_subject(recall: dict | None, slug: str, name: str) -> dict | None:
    """The probed subject matching this card's lane/entity, or None."""
    if not isinstance(recall, dict):
        return None
    for key in ((slug or "").strip().lower(), (name or "").strip().lower()):
        if not key:
            continue
        for subject in (recall.get("subjects") or []):
            if isinstance(subject, dict) and str(subject.get("key")) == key:
                return subject
    return None


def _subject_what(name: str, low: bool, subject: dict | None = None, *,
                  evidence_derived: bool = False) -> str:
    """The WHAT line for a subject card, at the operator's altitude and over
    whatever recall actually holds.

    ALTITUDE REACHES THE WHAT, not only the proof (fixed 2026-07-28). The
    declared-lane line used to end "task → change → verified deploy/close" at
    EVERY rung — the exact authority an IC does not hold, i.e. the altitude
    failure the PROOF line had already been corrected for, reappearing one
    layer down and gating the card on a permission that belongs to the
    operator's employer."""
    close = ("write the one-page finding and take it to whoever owns the "
             "decision" if low else
             "write the one-page finding, then ship the change it argues for")
    if subject and len(subject.get("files") or []) >= _MIN_JOIN_FILES:
        shared = subject.get("shared_terms") or []
        span = subject.get("span") or ""
        return (
            f"Read these notes of yours side by side"
            + (f" ({span})" if span else "")
            + ", newest first: "
            + "; ".join(subject.get("cites") or [])
            + (f". Shared wording: {', '.join(shared)}" if shared else "")
            + f". Then {close}."
        )
    if subject and subject.get("top_cite"):
        return (f"Start from what you already wrote about {name} — "
                f"{subject['top_cite']} — then {close}.")
    if evidence_derived:
        # Already altitude-neutral: it names the evidence, not a deploy.
        return (f"One reviewed, Captain-approved improvement in {name} traced "
                f"end-to-end from the evidence that surfaced it.")
    if low:
        return (f"One reviewed, Captain-approved improvement in {name} traced "
                f"end-to-end: evidence → written proposal → the decision it "
                f"changed.")
    return (f"One reviewed, Captain-approved improvement in {name} traced "
            f"end-to-end: task → change → verified deploy/close.")


def _recall_card_name(name: str, subject: dict | None, fallback: str) -> str:
    """Name the card after WHAT WAS FOUND, not after the thing the operator
    already knows they declared. A headline that counts their own notes and
    dates them is checkable at a glance; "First verifiable improvement in X"
    is true of every deployment ever hatched."""
    files = (subject or {}).get("files") or []
    if len(files) < _MIN_JOIN_FILES:
        return fallback
    span = (subject or {}).get("span") or ""
    return (f"{name}: {len(files)} of your own notes"
            + (f" ({span})" if span else "")
            + ", never read together")


def _recall_why(subject: dict | None) -> str:
    """The sentence that makes a card checkable: the operator's own words, with
    the file and date beside them. Empty when recall held nothing — an
    unearned citation is the defect this whole unit exists to remove."""
    if not subject or not subject.get("quote"):
        return ""
    return (f' I did not ask you for this, I read it: "{subject["quote"]}" '
            f'— {subject.get("top_cite") or "?"}.')


# ---------------------------------------------------------------------------
# ONBOARD-1 — the org PROPOSES outcome cards (propose-only, never activating).
# ---------------------------------------------------------------------------
def propose_outcome_cards(answers: dict, focus_text: str | None = None, *,
                          estate: dict | None = None,
                          recall: dict | None = None) -> list[dict]:
    """PURE derivation: the derived estate + cabinet-init answers (+ optional
    focus letter) → 2–4 proposed outcome cards.

    Card anatomy (the hatching design's proposal-card lines): ``what`` /
    ``why`` / ``proof_expected``, plus ``status: draft`` and
    ``captain_ratified: False`` — ALWAYS. Derivation is deterministic. Up to
    ``_MAX_LANE_CARDS`` SUBJECT cards fill first from the declared lanes (the
    Captain's own statement wins), then from the estate's entities; when
    neither yields one, a single leftover-question card asks the three
    un-derivable questions. Then the two org cards (Library grounding,
    Captain decision loop). So 2 lanes → 4 cards, 1 lane → 3, 0 lanes and no
    estate entities → 3 (residual + the two org cards). Returns [] when
    answers carry no cabinet id at all (nothing to key a proposal to — honest
    empty).

    MISSION-CONDITIONED (Phase 2, onboarding-vision-2026-07-14 §4): when the
    answers carry the interview's ``mission:`` block, the cards quote the
    stated purpose / 90-day bar / never-touch list, and ``mission.altitude``
    reshapes every proof line AND every subject WHAT line — still PURE
    deterministic string derivation (no LLM anywhere near the hatch chain).
    Missionless answers with a declared lane derive exactly today's cards.

    RECALL-CONDITIONED (2026-07-28): ``recall`` is a ``probe_recall`` result —
    what the deployment's BOUND recall seam actually holds about each subject,
    passed in as DATA exactly like ``estate`` so this function stays pure. A
    subject recall answered for gets a card composed from the operator's own
    notes: their words quoted, every file cited with its derived date, and the
    terms two or more of those files share named. Without it (``recall=None``,
    or a seam that answered nothing) the cards are byte-identical to the
    pre-recall derivation — an unearned citation would be the exact defect this
    surface exists to remove."""
    cabinet = answers.get("cabinet") or {}
    cabinet_id = str(cabinet.get("id") or "").strip()
    if not cabinet_id:
        return []

    excerpt = _focus_excerpt(focus_text)
    focus_lower = (focus_text or "").lower()
    purpose, success_90d, never_touch = _mission_fields(answers)
    low = _low_altitude(answers)
    cards: list[dict] = []

    seen_ids: set[str] = set()
    taken_slugs: set[str] = set()
    lanes = [ln for ln in (answers.get("lanes") or []) if isinstance(ln, dict)]
    for lane in lanes[:_MAX_LANE_CARDS]:
        slug = str(lane.get("slug") or "").strip()
        name = str(lane.get("name") or slug).strip()
        if not (slug or name):
            continue
        taken_slugs.add(slug)
        repos = [str(r) for r in (lane.get("repos") or []) if str(r).strip()]
        subject = _recall_subject(recall, slug, name)
        why = f"You staked {name or slug} as a lane at genesis"
        if repos:
            why += f" (repos: {', '.join(repos)})"
        why += "."
        why += _recall_why(subject)
        if focus_lower and (
            (slug and slug in focus_lower) or (name and name.lower() in focus_lower)
        ):
            why += " Your focus letter names this lane."
        if purpose:
            why += f' The mission it serves: "{purpose}"'
        # ids are keys downstream (ratification moves rows by id) — duplicate
        # lane slugs in the answers must still yield unique card ids.
        base_id = f"proposed-{slug or name.lower().replace(' ', '-')}-first-proof"
        card_id, n = base_id, 2
        while card_id in seen_ids:
            card_id, n = f"{base_id}-{n}", n + 1
        seen_ids.add(card_id)
        cards.append({
            "id": card_id,
            # A card that names what recall found beats one that names the
            # lane the operator already knows they declared.
            "name": _recall_card_name(
                name or slug, subject,
                f"First verifiable improvement shipped in the "
                f"{name or slug} lane"),
            "lane": slug or None,
            "derived_from": "recall" if subject else "answers",
            "what": _subject_what(name or slug, low, subject),
            "why": why,
            "proof_expected": _subject_proof(name or slug, repos, low),
            # ONLY WHEN EARNED — a card that cited nothing carries no refs key
            # at all, so a no-recall derivation stays byte-identical to the
            # pre-recall one and an empty list can never read as a citation.
            **({"recall_refs": list(subject.get("refs") or [])}
               if subject and subject.get("refs") else {}),
        })

    if len(cards) < _MAX_LANE_CARDS and isinstance(estate, dict):
        cards.extend(_estate_subject_cards(
            estate, taken_slugs, seen_ids, purpose=purpose, low=low,
            limit=_MAX_LANE_CARDS - len(cards), recall=recall))
    if not cards:
        cards.append(_residual_card(estate, low, recall))

    cards.append({
        "id": "proposed-library-grounding",
        "name": "The Library grounds the org: ratified company/market/product brief",
        "lane": None,
        "derived_from": "system",
        "what": (
            "The genesis research brief is reviewed by the Captain, corrected "
            "where wrong, and ratified into the Library as the org's baseline "
            "understanding of its products and market."
        ),
        "why": (
            "Gather-then-decide is org doctrine: an org that acts before it "
            "understands invents work."
            + (f' The mission it must ground: "{purpose}"' if purpose else "")
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
        "derived_from": "system",
        "what": (
            "At least one org-proposed outcome from this first briefing is "
            "ratified, edited, or rejected by the Captain, and the org visibly "
            "acts on that ruling."
        ),
        "why": (
            "The hatch posture is propose-first; the governance loop exists "
            "only once a proposal has round-tripped through the Captain."
            + (f' Your stated 90-day bar: "{success_90d}"' if success_90d else "")
            + (" Standing constraint you stated — the org never touches: "
               + "; ".join(never_touch) + "." if never_touch else "")
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
                   focus_present: bool, estate_present: bool = False,
                   recall_present: bool = False) -> dict:
    cabinet = answers.get("cabinet") or {}
    derived = [ANSWERS_REL] + ([FOCUS_REL] if focus_present else [])
    if estate_present:
        from framework.onboarding import estate as _estate  # local: import-light
        derived.append(_estate.ESTATE_REL)
    if recall_present:
        # Not a path: the recall seam is a BINDING, and naming it as one keeps
        # the provenance list honest about what produced these rows.
        derived.append("recall:" + SOURCES_REL)
    outcomes = []
    for card in cards:
        refs = [str(r) for r in (card.get("recall_refs") or []) if str(r).strip()]
        outcomes.append({
            "id": card["id"],
            "name": card["name"],
            "status": "draft",
            "captain_ratified": False,
            "lane": card.get("lane"),
            # Provenance the Captain can act on: "answers" is his own
            # declaration, "estate" is something I read and can cite,
            # "recall" is something his OWN notes already said, "residual" is
            # a question only he can answer.
            "derived_from": card.get("derived_from", "answers"),
            "what": card["what"],
            "why": card["why"],
            "proof_expected": card["proof_expected"],
            # So a Captain-ratified copy moved into outcomes.yml is already
            # outcome.schema.json-shaped (id/name/measurable_criteria).
            "measurable_criteria": [card["proof_expected"]],
            # Only when EARNED: the durable list of note refs this row was
            # composed from. Absent means no note was cited, and the briefing
            # says so rather than implying one.
            **({"recall_refs": refs} if refs else {}),
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
                    focus_present: bool = False, force: bool = False,
                    estate_present: bool = False,
                    recall_present: bool = False) -> dict:
    """Write the propose-only staging file. Write-once: an existing file is
    NEVER overwritten unless ``force`` (the Captain may have edited drafts) —
    the briefing composes from the file either way."""
    base = Path(root) if root else cabinet_root()
    path = base / PROPOSALS_REL
    if path.exists() and not force:
        return {"status": "kept-existing", "path": str(path), "written": False}
    import yaml  # local: keep the module import-light
    doc = _proposals_doc(cards, answers or {}, now=_utc_now_iso(now),
                         focus_present=focus_present,
                         estate_present=estate_present,
                         recall_present=recall_present)
    body = _PROPOSALS_HEADER.format(marker=GENERATED_MARKER)
    body += yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)
    _atomic_write(path, body)
    return {"status": "written", "path": str(path), "written": True}


def load_proposals_doc(root: Path | None = None) -> dict:
    """The parsed outcomes-proposed.yml document, read-only. Absent or
    unparseable → ``{}`` (honest empty — callers never guess at drafts)."""
    base = Path(root) if root else cabinet_root()
    path = base / PROPOSALS_REL
    if not path.is_file():
        return {}
    try:
        import yaml  # local: keep the module import-light
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def merge_proposals(cards: list[dict], root: Path | None = None, *,
                    answers: dict | None = None, now: str | None = None,
                    focus_present: bool = False) -> dict:
    """MERGE-BY-CARD-ID writer for the propose-only staging file (onboarding
    design 2026-07-14 Phase 1; Phase 3's strategy passes ride it too).

    ``write_proposals`` is write-once because the Captain may have edited the
    drafts — a blind append/overwrite would clobber those edits. This writer
    preserves EVERY existing row's body verbatim (existing card ids win,
    including any Captain-added keys) and appends only cards whose id is NEW,
    each stamped with a per-row ``proposed_at``. The top-of-file comment block
    of an existing file is preserved as-is (Captain comments survive); an
    absent file degrades to ``write_proposals``. An existing file that does
    not parse as the expected shape is NEVER rewritten — honest refusal
    (``status: unmergeable-existing``), not a clobber. Propose-only exactly
    like write_proposals: merged rows are ``status: draft`` +
    ``captain_ratified: false`` in the file the mission compiler structurally
    never reads."""
    base = Path(root) if root else cabinet_root()
    path = base / PROPOSALS_REL
    ts = _utc_now_iso(now)
    if not path.exists():
        res = write_proposals(cards, base, answers=answers, now=ts,
                              focus_present=focus_present)
        res.update(added=len(cards) if res["written"] else 0, merged=False)
        return res

    import yaml  # local: keep the module import-light
    try:
        raw = path.read_text(encoding="utf-8")
        doc = yaml.safe_load(raw)
    except Exception:
        doc, raw = None, ""
    rows = doc.get("outcomes") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        return {"status": "unmergeable-existing", "path": str(path),
                "written": False, "added": 0, "merged": False}

    existing_ids = {str(r.get("id")) for r in rows if isinstance(r, dict)}
    new_cards = [c for c in cards if str(c.get("id")) not in existing_ids]
    if not new_cards:
        return {"status": "no-new-cards", "path": str(path),
                "written": False, "added": 0, "merged": True}

    shaped = _proposals_doc(new_cards, answers or {}, now=ts,
                            focus_present=focus_present)["outcomes"]
    for row in shaped:
        row["proposed_at"] = ts
    doc["outcomes"] = rows + shaped
    doc["last_merged_at"] = ts

    # Preserve the existing leading comment block (Captain comments survive);
    # only a file with no comment head gets the standard header stamped.
    head_lines = []
    for line in raw.splitlines():
        if line.startswith("#") or not line.strip():
            head_lines.append(line)
        else:
            break
    header = ("\n".join(head_lines).strip() + "\n") if any(
        ln.startswith("#") for ln in head_lines
    ) else _PROPOSALS_HEADER.format(marker=GENERATED_MARKER)
    body = header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True,
                                   width=100)
    _atomic_write(path, body)
    return {"status": "merged", "path": str(path), "written": True,
            "added": len(shaped), "merged": True}


def run_genesis_proposal(root: Path | None = None, *, now: str | None = None,
                         source=None) -> dict:
    """ONBOARD-1 orchestration: answers (+ focus + estate + RECALL) → cards →
    staging file.

    Returns ``{'status', 'path', 'cards': n, 'recall': <probe result>}``.
    ``status='no-answers'`` when the cabinet-init answers are absent/empty (a
    broken tree at hatch time — callers fail loudly rather than staging an
    empty proposal).

    THE RECALL PROBE LIVES HERE, beside the estate load, for the same reason:
    this is the orchestration layer that is allowed to do I/O, and
    ``propose_outcome_cards`` stays pure by receiving the result as data.
    ``source`` is the test seam forwarded to ``probe_recall``."""
    base = Path(root) if root else cabinet_root()
    answers = load_answers(base)
    if not answers:
        return {"status": "no-answers", "path": None, "cards": 0, "recall": {}}
    focus = load_focus_text(base)
    from framework.onboarding import estate as _estate  # local: import-light
    derived = _estate.load_estate(base)
    usable, _reason = _estate.estate_is_usable(
        derived, (answers.get("cabinet") or {}).get("id"))
    estate = derived if usable else None
    recall = probe_recall(answers, focus, estate=estate, source=source,
                          root=base)
    cards = propose_outcome_cards(answers, focus, estate=estate, recall=recall)
    if not cards:
        return {"status": "no-cards", "path": None, "cards": 0, "recall": recall}
    res = write_proposals(cards, base, answers=answers, now=now,
                          focus_present=focus is not None,
                          estate_present=estate is not None,
                          recall_present=bool(recall.get("subjects")))
    return {"status": res["status"], "path": res["path"], "cards": len(cards),
            "recall": recall}


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


# ---------------------------------------------------------------------------
# OPERATOR-CONTEXT ISOLATION for the genesis research brief.
#
# `claude -p` is a FULL Claude Code agent, not a bare completion: it
# auto-discovers (a) PROJECT context — CLAUDE.md, .remember/, SessionStart
# hooks, walking UP from its cwd — and (b) USER-GLOBAL context —
# ~/.claude/CLAUDE.md plus the personal memory imports it @-includes.
#
# MEASURED 2026-07-26, before this fix: a clean-room hatch of the PUBLIC egg,
# for a lane whose only name is the placeholder "First Lane" and which carries
# no product metadata whatsoever, produced a brief naming the operator's real
# employer and four real products that exist NOWHERE in the egg tree — and it
# said so in its own words: "Inference from this deployment's ambient captain
# context (not from lane config)". The artifact is then promoted as "the org's
# baseline understanding of its products and market" and indexed into org
# memory (source_type: research_brief), so every hatched cabinet silently
# absorbed its operator's private notes as org truth.
#
# Both tiers are closed here, with the shape framework/fidelity/oauth_llm.py
# already proved on this codebase (same two-tier leak, same repair):
#   (a) PROJECT tier -> run from a CLEAN temp cwd. This is the ONLY lever that
#       closes the ancestor walk: the instance root normally sits UNDER $HOME,
#       so the walk reaches ~/.claude/CLAUDE.md from there. Nothing in the
#       prompt needs the instance cwd — build_brief_prompt() is self-contained.
#   (b) USER-GLOBAL tier -> `--setting-sources project,local` drops the `user`
#       source (~/.claude/CLAUDE.md + memory + user settings).
#
# HOME IS DELIBERATELY LEFT INTACT, and a throwaway CLAUDE_CONFIG_DIR is
# deliberately NOT used. Claude Code suffixes the OAuth keychain service name
# with sha256(config-dir)[0:8] when CLAUDE_CONFIG_DIR is set, so a fresh config
# home boots "Not logged in" (cabinet/scripts/start-officer-mac.sh documents
# this; bin/cabinet-review.sh carries the same caveat about itself). Genesis
# converts a non-zero rc into a written IOU, so that would not surface as an
# error — it would silently and permanently downgrade the research organ to
# "research brief queued". `--bare` is unusable for the same reason: it never
# reads OAuth or the keychain. CLAUDE_CONFIG_DIR also cannot gate an ancestor
# walk at all (declared residual RES-002), so it would not even fix the leak.
# Fixed-argv CLI invocation — never a shell string (Corridor pattern).
def _default_run(argv: list[str], *, timeout: int, cwd: str, env=None):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env)


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

    Success path: the local ``claude`` CLI on a FIXED argv (no shell, short
    timeout), isolated from the operator per the OPERATOR-CONTEXT ISOLATION note
    above ``_default_run``, writes its REAL output to ``instance/memory/library/
    genesis-research-brief.md`` with ``status: delivered`` provenance. ANY
    failure — missing binary, network down, non-zero exit (e.g. unauthenticated
    CLI), timeout, empty output — writes the honest IOU note (``IOU_LINE``:
    "research brief queued — will be produced when officers wake") with the
    failure named (names-not-values). Idempotent: a delivered brief is never
    overwritten; an IOU is retried/upgraded on a later run. Seams (tests):
    ``run_fn(argv, timeout=, cwd=, env=)`` replaces the subprocess;
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
    # OPERATOR-CONTEXT ISOLATION — see the note above _default_run. All three
    # levers are load-bearing and none alone suffices: `--setting-sources`
    # without `user` drops the user-global tier; an EMPTY temp cwd (never the
    # instance root, which sits under $HOME) closes the CLAUDE.md ancestor walk
    # plus .remember/hooks; the env filter stops a stray key billing
    # pay-as-you-go. HOME is left INTACT — the keychain/OAuth is HOME-anchored.
    argv = [resolved, "-p", prompt, "--setting-sources", "project,local"]
    clean_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    run = run_fn or _default_run
    budget = timeout if timeout is not None else _brief_timeout()
    try:
        proc = run(argv, timeout=budget, env=clean_env, cwd=tempfile.mkdtemp(prefix="genesis-clean-"))
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
    rows = load_proposals_doc(base).get("outcomes")
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def genesis_intake_items(root: Path | None = None, now: str | None = None, *,
                         source=None) -> list[dict]:
    """Read the genesis surfaces (proposals file, focus letter, research brief,
    derived estate, RECALL) into canonical intake items for
    ``composer.compose``. Honest empties: absent surfaces yield NO items.

    RECALL (2026-07-28) is the one surface here that is not a file read: it
    asks the deployment's bound seam what it holds, and reports the answer —
    live, unbound, or not consulted — with the citations any card claims. The
    probe is root-guarded and kill-switchable (``probe_recall``); ``source``
    is its test seam.

    When (and only when) a real genesis briefing is rendering — i.e. at least
    one surface produced an item — ONE extra ``genesis-contribute`` FYI card
    is appended: the contribute/fund ask (contribution design 2026-07-10),
    asked once at genesis and never again."""
    base = Path(root) if root else cabinet_root()
    ts = _utc_now_iso(now)
    focus_text = load_focus_text(base)
    items: list[dict] = []

    proposal_rows = _load_proposal_rows(base)
    for row in proposal_rows:
        name = str(row.get("name") or row.get("id") or "").strip()
        if not name:
            continue
        # LITERAL COUPLING: cabinet/scripts/first-briefing.sh's receipt gate
        # greps 'Proposed outcome:' — reword BOTH sides in the same commit.
        refs = [str(r) for r in (row.get("recall_refs") or []) if str(r).strip()]
        summary = (
            f"📜 Proposed outcome: {name}\n"
            f"WHAT: {row.get('what') or '—'}\n"
            f"WHY: {row.get('why') or '—'}\n"
            f"PROOF-expected: {row.get('proof_expected') or '—'}\n"
            # The operator can open every one of these. A card citing nothing
            # checkable is worse than no card, so the refs ride the card body
            # rather than sitting only in the staging file.
            + (f"FROM YOUR NOTES: {', '.join(refs)}\n" if refs else "")
            + f"Status: draft — propose-only, captain_ratified: false "
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

    from framework.onboarding import estate as _estate  # local: import-light
    derived = _estate.load_estate(base)
    if derived.get("schema") == _estate.SCHEMA:
        srcs = [s for s in (derived.get("sources") or []) if isinstance(s, dict)]
        ents = derived.get("entities") or []
        # READ THE CANONICAL RECORD'S OWN FIELDS. ``access_record`` writes
        # ``refusals`` as a MAPPING class->count and pre-totals it into
        # ``refusals_total``; the earlier list-of-dicts sum iterated the
        # mapping's KEYS, so ``isinstance(r, dict)`` was never true and the
        # count was structurally 0 for every sweep — the auditability this
        # line exists to provide, silently disabled. Same class of bug one
        # field over: the record's key is ``source_root``, not ``root``, so
        # the provenance always fell back to the label.
        refusals = sum(int(s.get("refusals_total") or 0) for s in srcs)
        roots = ", ".join(str(s.get("source_root") or s.get("label") or "?")
                          for s in srcs[:2])
        # Do NOT claim the cards derive from the estate unless one actually
        # does. Nothing in the shipped chain runs formation.sh before the
        # first briefing, and ``write_proposals`` is write-once, so the
        # ordinary ordering yields cards written BEFORE this estate existed.
        # Claiming the citation anyway is the unearned-negative defect this
        # unit was built to remove, reappearing one surface up.
        from_estate = sum(1 for r in proposal_rows
                          if str(r.get("derived_from") or "") == "estate")
        # PROVENANCE, not a claim: what was read, from where, under which
        # ownership class, and how many entries were REFUSED. A silent skip
        # destroys auditability, so the count is shown even when it is 0.
        body = (f"🗺️ Derived estate: {len(srcs)} source(s), {len(ents)} "
                f"entity(ies), {refusals} refused entr(ies)"
                + (f" — {roots}" if roots else " — nothing granted yet")
                + f". Ownership: {', '.join(sorted({str(s.get('ownership')) for s in srcs})) or 'n/a'} "
                  "(asked, never inferred; anything not `self` proposes "
                  "read-only). Record: " + _estate.ESTATE_REL)
        items.append({
            "source": "onboarding-genesis", "kind": "genesis-estate",
            "ts": ts, "urgency_tier": "fyi",
            "payload": {"summary": body},
            "context": {"why": ("what the cabinet READ — the cards above are "
                                "derived from it, with citations")
                        if from_estate else
                        ("what the cabinet READ. No card above derives from "
                         "it: the proposals on file were written before this "
                         "estate existed. Re-run genesis to derive cards "
                         "from what was read.")},
        })

    # RECALL PROVENANCE — the surface that made the false positive visible.
    # Same discipline as the estate item above: state what the binding IS, what
    # it answered, and whether any card on file actually derives from it. The
    # negative cases are the load-bearing ones: a briefing that says nothing
    # about recall is indistinguishable from one whose recall was answering out
    # of the framework's own shipped documentation, which is what a personal
    # hatch did until 2026-07-28.
    answers_for_recall = load_answers(base)
    if answers_for_recall:
        recall = probe_recall(answers_for_recall, focus_text,
                              estate=(derived if derived.get("schema")
                                      == _estate.SCHEMA else None),
                              source=source, root=base)
        from_recall = sum(1 for r in proposal_rows if r.get("recall_refs"))
        cited = sorted({str(ref) for r in proposal_rows
                        for ref in (r.get("recall_refs") or []) if str(ref)})
        state = recall_state(recall)          # "" ⇒ live (see recall_state)
        if state:
            body = (f"🧠 Recall: {state}. Adapter: "
                    f"{recall.get('adapter') or 'unresolved'} ({SOURCES_REL}).")
            why = ("nothing above cites your own material, and that has to be "
                   "SAID. Until 2026-07-28 an undeclared folder silently "
                   "resolved to this repo's own vault/ docs and reported "
                   "working recall — so a briefing that stays QUIET about "
                   "recall is exactly what a wrong answer looked like, "
                   "whatever the reason for the silence is")
        else:
            answered = recall.get("subjects") or []
            body = (f"🧠 Recall: live — {recall.get('adapter')} answered "
                    f"{recall.get('hits_total')} hit(s) across "
                    f"{len(answered)} of "
                    f"{len(recall.get('probes') or [])} subject(s) "
                    f"({', '.join(recall.get('probes') or []) or 'none derived'})."
                    + (f" Cited above: {', '.join(cited)}." if cited else "")
                    # A probe that failed mid-sweep still leaves the seam
                    # available, so the live line would otherwise report a
                    # partial answer as a complete one.
                    + (f" One or more probes failed: {recall['error']}."
                       if recall.get("error") else ""))
            # THREE live sub-states, and conflating the last two is the same
            # unearned-claim defect one surface over. Found by a real
            # clean-room hatch 2026-07-28: an org box whose backend held
            # nothing was told "the proposals on file were written before this
            # run", blaming an ORDERING problem for an EMPTY one. Nothing is
            # cited because there was nothing to cite, and the honest sentence
            # is the one that says so.
            if from_recall:
                why = ("what your own material already held — the cards above "
                       "are composed from it, every claim citing a file and a "
                       "date you can open")
            elif not answered:
                why = ("recall is bound and reachable but held NOTHING on the "
                       "subjects you declared, so no card cites it. That is an "
                       "empty answer, not a stale one — nothing above is "
                       "waiting on a re-run")
            else:
                why = ("recall answered, but NO card above derives from it: "
                       "the proposals on file were written before this run. "
                       "Re-run genesis to compose cards from what it holds")
        items.append({
            "source": "onboarding-genesis", "kind": "genesis-recall",
            "ts": ts, "urgency_tier": "fyi",
            "payload": {"summary": body},
            "context": {"why": why},
        })

    if (base / FOCUS_REL).is_file():
        items.append({
            "source": "onboarding-genesis", "kind": "genesis-focus",
            "ts": ts, "urgency_tier": "fyi",
            "payload": {"summary": f"🧭 Your focus letter is on file ({FOCUS_REL}) "
                                   "— the proposals above are anchored to it"},
            "context": {"why": "the first letter carries bearing, not tasks"},
        })

    # Contribute + fund FYI — the contribution design's SINGLE placement
    # (DESIGN-contribution-donations-2026-07-10 §4): one card in the genesis
    # briefing, asked once, never nagged, no onboarding-time asks. Appended
    # only when a real genesis briefing is rendering (bare roots stay honestly
    # empty). Propose-only by construction: fyi tier is information — nothing
    # acts on it, and it never carries the receipt-gate's outcome-card literal.
    if items:
        items.append({
            "source": "onboarding-genesis", "kind": "genesis-contribute",
            "ts": ts, "urgency_tier": "fyi",
            "payload": {"summary": (
                "🤝 If this cabinet earns its keep, two ways to give back. "
                "Contribute: file issues/PRs — bash cabinet/scripts/"
                "cabinet-feedback.sh builds a leak-scrubbed diagnostic bundle "
                "and, only with your explicit consent, opens it as a prefilled "
                "issue ('good first issue' labels mark starter work). Fund: "
                "https://opencollective.com/captains-cabinet — public spend "
                "ledger (placeholder until the collective is live; how costs "
                "are metered and mirrored: docs/TRANSPARENCY.md). "
                "Propose-only ask — asked once at genesis, never again; "
                "ignore it freely."
            )},
            "context": {"why": "the ONE contribute/fund ask — asked once at "
                               "genesis, never nagged; FYI only, nothing acts "
                               "on it"},
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
