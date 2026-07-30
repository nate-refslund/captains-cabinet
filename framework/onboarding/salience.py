"""salience — rank what RECURS across connected sources, then ask which one matters.

THE QUESTION THIS ANSWERS, and the one it does not. An operator arrives with
531 boards, 56 repositories, 20 databases and 58 hostings. "Read all of it" was
REFUTED by decisive experiment (``framework.onboarding.research``: of four
findings, one needed more than one file and ZERO needed more than one system),
so this module never reads content. It reads NAMES AND COUNTS, ranks what
recurs, and hands the operator a short list to point at. Ranking is not ingest:
the expensive, risky, revocable part is DEPTH, and depth is spent only where
the operator points — ENFORCED, not asserted. This sentence shipped while an
operator could answer one target and open a window on any other folder with
nothing objecting; ``journey._window_binding`` is the control that now makes it
true, and ``journey.WINDOW_RELATIONS`` is what they may say instead.

NO TAXONOMY. Nowhere below is there a list of entity kinds — no product, no
project, no client, no campaign, no case. The primitive is a ``row``:
``(connector, name, updated)``. Whatever string recurs across the most
connectors, most recently, is the candidate. For one operator those strings are
products; for a salesperson they are clients; for a librarian they are
collections. The mechanism must not know which, and the operator supplies the
noun BY ANSWERING — never by configuring. A kind-list here would be correct for
exactly one estate and wrong for the next one, which is why three
hand-maintained lists were deleted from this program in a single week.

WHY EVERY NOISE RULE IS MEASURED, NEVER WRITTEN DOWN. Naive recurrence ranks noise
first, and the noise is estate-specific: the employer's own name recurs
everywhere because everything belongs to it; a tracker's template words
("Subitems of ...") recur because the tracker put them there; a scaffolding
prefix recurs because a generator put it there. A hand list of stopwords would
encode ONE estate into the framework. So every measurement below is derived
from the rows themselves:

* ``_FURNITURE_SHARE`` — a token in more than a quarter of ONE connector's rows
  is that connector's furniture, whatever the word is.
* ``_CONCENTRATION`` — a token whose occurrences are overwhelmingly inside a
  single system is that system's structure, not a thing that spans systems.
* identity DEMOTION — a token matching an account, owner or workspace name the
  connectors themselves reported is demoted, because the operator's own name is
  genuine noise AND may also be a genuine target. Both are true of the same
  string: measured on a real estate, the owner's name was also the name of one
  of its live targets — think an owner called "north bay" whose busiest thing is
  northbay.example.

NOTHING IS DELETED, and that took three attempts to get right. The first two
measurements above began life as FLOORS that dropped the token, and a floor that
drops is a silent loss: the candidate stops existing, nothing downstream can
report it, and an operator reading a clean-looking shortlist has no way to know
their answer was removed before the ranking began. Measured on a live estate,
that is exactly what happened — the code connector names every row
``<org>/<thing>``, so the org token sat in 93% of that connector's rows, the
furniture floor deleted it, and the org was also the name of the estate's
busiest live site. An identity EXEMPTION was added to patch the hole and did not
close it: the exemption only fires for strings the connectors happened to report
about themselves, and the org that owns 52 of 56 repositories was not one of
them.

So the floors are now DISCOUNTS. A token's occurrences inside the connector that
explains them stop counting as evidence of importance; the token keeps its span
and every occurrence the structure does NOT explain, and both numbers are
reported. On the same live estate the org token keeps 8 occurrences across three
other connectors and ranks on those — demoted from what its 60 raw occurrences
would have bought, deleted by nothing. A candidate whose every occurrence is
explained scores on span alone and sorts where that puts it; a token that never
spanned two systems was never a candidate, and says so in ``not_candidates``
rather than vanishing.

WHAT NAMES CANNOT DO, AND WHO DOES IT INSTEAD. One entity wears a different word
in each system it lives in. Measured: the entity spanning the most connectors on
a live estate was ranked as FIVE separate candidates, at ranks 6, 11, 21, 33 and
34, because its tracker calls it one word and its repository, database and
hosting call it another that shares no stem with the first. No string function
joins those. A stemming or fuzzy-match table would join them for one estate and
mis-join the next, which is a hand-maintained list in disguise — this program
has deleted three of those. So :func:`rank` emits the candidate names UNMODIFIED
(:func:`join_proposal`) and takes an optional ``join`` judgment that reads them
and answers which are one thing. The module validates that an answer only names
candidates it actually produced, and records that the union was judged.

THE OPERATOR IS THE OTHER JUDGE, and theirs is the answer that has to survive.
:func:`merge_ask` puts the question on the offer itself — every ranked candidate
is nameable there, not only the shown three, because the twin of the top
candidate was measured at ranks 11 and 33 — and :func:`learn_merge` keeps the
answer, so the next ranking after the next sweep already knows it. An answer that
changes only the shortlist in front of the operator is a filter, not learning,
and re-asking a settled question is the same defect as asking one the estate
could have answered. Overlapping answers are unioned
(:func:`_closed_alias_groups`) because identity is transitive; nothing anywhere
compares two names to decide it.

HOW ANYONE KNOWS THIS WORKS. :func:`check` grades a ranking against answers the
OPERATOR supplies — never a list living in here, which would be right for one
estate and a fiction for the next. It reports, per answer, the rank it reached
or the reason it could not be reached at all, and the difference between those
two is the entire point: "ranked eleventh" is a shortlist that needs scrolling,
"not a candidate" is a correct answer that was lost.

WHY RECENCY IS REFUSED PER CONNECTOR. "Freshest wins" assumes the clock
measures use. Measured on a real estate, two of four connectors' timestamps
were control-plane metadata: one resolved three distinct values across twenty
rows, another was a config mtime. A ranking function multiplying by that number
is a sensor pointed at something other than the control — the failure class
this program has found ten ways. So :func:`admissible_clocks` REFUSES a clock
that does not discriminate, the affected clusters score at a neutral band, and
the refusal is disclosed in the offer rather than silently averaged in.

WHAT A RANKING IS. An assertion. If it offers three candidates and the right
answer was the fourth, that is a confident wrong. :func:`offer` therefore
REFUSES to build an ask without a coverage block, always carries an escape
hatch that takes a typed name, and always states what was NOT reached — an
unearned clean negative is the defect, not the long sentence.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

SALIENCE_SCHEMA = "cabinet.salience-ranking/v1"
SALIENCE_ROW_SCHEMA = "cabinet.salience-rows/v1"
SALIENCE_OFFER_SCHEMA = "cabinet.salience-offer/v1"
SALIENCE_JOIN_SCHEMA = "cabinet.salience-join-proposal/v1"
SALIENCE_CHECK_SCHEMA = "cabinet.salience-check/v1"
SALIENCE_MERGE_SCHEMA = "cabinet.salience-merges/v1"

#: The escape hatch's option id. It is not a candidate: it is the admission
#: that the ranking may be wrong, and it carries a text field so the answer can
#: name something the sweep never ranked.
ESCAPE_OPTION_ID = "other"

# --- the measured quantities every discount and demotion is derived from ----

#: Tokens shorter than this never become ranking tokens. Not a stopword list: a
#: length rule is estate-independent and knows no words. This one IS a floor and
#: not a discount, and the difference is that it applies before there is anything
#: to discount — a two-character fragment is not a candidate that lost, it is a
#: substring that was never a name.
#:
#: ITS SCOPE IS THE RANKING, and reading it as "the words in a name" is the
#: mistake it has already caused once: see :func:`name_tokens`.
_MIN_TOKEN_LEN = 4
#: A token in more than this share of ONE connector's rows is that connector's
#: furniture, and its occurrences INSIDE that connector are explained by it.
#: Measured, not declared — the word is irrelevant.
_FURNITURE_SHARE = 0.25
#: ...but only once that connector has enough rows for a share to MEAN
#: anything. Below this, every token is in "most" of the rows and the floor
#: would delete the entire connector — a real defect, found by running the
#: ranker on a two-row source. Not a tuning knob: it is the sample size below
#: which the measurement does not exist.
_FURNITURE_MIN_ROWS = 8
#: With at least this many occurrences, a token this concentrated in one
#: connector is that system's structure rather than a cross-system entity.
_CONCENTRATION = 0.85
_CONCENTRATION_MIN_TOTAL = 8
#: Two tokens covering nearly the same rows are one candidate wearing two
#: words. Merged rather than ranked twice.
_CLUSTER_JACCARD = 0.6
#: An identity token is DEMOTED by this factor, never dropped. See the module
#: docstring: the same string can be both the operator's own name and a real
#: target, and only a demotion keeps both facts.
_IDENTITY_DEMOTION = 0.4
#: A candidate must span at least this many connectors. Recurrence across
#: systems is the entire signal; one system is a list, not a signal.
_MIN_CONNECTORS = 2
#: Volume is damped and capped: the largest object in an estate is usually a
#: dump (a contacts table, a ticket archive), and an uncapped count would rank
#: the dumps.
_VOLUME_CAP = 20

#: Recency bands, in days, applied only to clocks that passed
#: :func:`admissible_clocks`.
_RECENCY_BANDS = ((7, 1.0), (30, 0.6), (180, 0.3))
_RECENCY_FLOOR = 0.1
#: What a cluster scores when no admissible clock touched it. Deliberately the
#: middle band: an unknown age must neither win nor lose against a measured one.
_RECENCY_UNKNOWN = 0.6

#: A clock discriminates when it resolves more distinct days than this share of
#: its rows, and when at least half its rows carry a timestamp at all. Both
#: numbers are relative to the connector, so a small connector is not failed for
#: being small nor a large one passed for being large.
_CLOCK_DISTINCT_SHARE = 0.05
_CLOCK_MIN_DISTINCT = 3
_CLOCK_MIN_COVERAGE = 0.5

_TOKEN_SPLIT_RE = re.compile(r"[^0-9a-z]+")
_ISO_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})"
    r"(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?)?$"
)


class SalienceError(Exception):
    """A ranking or an offer that would assert more than it measured."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --- primitives -------------------------------------------------------------


def name_tokens(name: Any) -> list[str]:
    """The words a name is made of, plus the compounds of adjacent pairs.

    NO RANKING FLOOR. This answers "which words does this name contain", and
    :func:`tokenize` is this list above ``_MIN_TOKEN_LEN``. The two questions
    have different right answers and collapsing them cost an operator every
    window they could open: ``journey._window_binding`` compares an ANSWER
    against a FOLDER NAME, derived both sides with the ranking tokenizer, and an
    operator who answered a short word, an acronym or an initialism — two or
    three letters, a short name in any language — got an empty set of wanted
    words. An empty
    set intersects nothing, so every window they proposed was refused, including
    the folder named after their own answer, and the refusal told them that
    folder did not carry the name it was literally spelled with. Shortlist
    candidates are ranked labels and clear the floor by construction, so the
    happy path never showed it.

    The floor is right where it lives. A two-character fragment is not a
    candidate that lost, it is a substring that was never a name — but a
    three-letter ANSWER is a name, because the operator typed it and meant it.
    One implementation with the floor named at the ranking's own door is what
    keeps those two facts from drifting apart again; two tokenizers with two
    floors would drift the same way in a month.

    The compounds are not decoration. A name written ``north-bay-website`` and a
    name written ``northbay.example`` refer to the same thing, and a word-only
    tokenizer cannot see it: it produces ``north`` and ``bay`` (which on the
    estate this was measured against were the OWNER's own name, ranked first and
    third by pure noise) and never produces ``northbay`` at all. Emitting the
    adjacent-pair compound
    is mechanical, needs no dictionary, and is what lets the specific token beat
    its own generic fragments.

    Digits are kept, because a case number or a vessel id is a perfectly good
    recurring name in an estate this module is not allowed to know the shape of.
    """
    text = str(name or "").lower()
    parts = [p for p in _TOKEN_SPLIT_RE.split(text) if p]
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if part not in seen:
            seen.add(part)
            out.append(part)
    for left, right in zip(parts, parts[1:]):
        joined = left + right
        if joined not in seen:
            seen.add(joined)
            out.append(joined)
    return out


def tokenize(name: Any) -> list[str]:
    """The RANKING vocabulary: :func:`name_tokens` above ``_MIN_TOKEN_LEN``.

    Everything that scores, clusters, discounts, demotes, merges or grades reads
    this one and only this one — :func:`check` says so outright, because an
    oracle that credits the ranking with a word the ranking could not itself
    have produced is an instrument that reports success. Output is unchanged by
    the split above: a compound short enough to be dropped is shorter than both
    its parts, so no filtered part can ever have masked a surviving compound.
    """
    return [token for token in name_tokens(name) if len(token) >= _MIN_TOKEN_LEN]


def _parse_iso(value: Any) -> datetime | None:
    """Parse a timestamp, or refuse it. A timestamp that does not parse is
    ABSENT, never today: guessing now() for an unreadable clock would make the
    dead-clock refusal below unreachable."""
    text = str(value or "").strip()
    match = _ISO_RE.match(text)
    if not match:
        return None
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    hour = int(match.group(4) or 0)
    minute = int(match.group(5) or 0)
    second = int(match.group(6) or 0)
    try:
        return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    except ValueError:
        return None


def normalize_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The row vocabulary, and the only thing this module ever consumes.

    A row is ``{"connector": str, "name": str, "updated": iso | None}``. Rows
    missing a connector or a name are DROPPED and counted, never repaired:
    a repaired row is a fabricated one, and the count is what tells the operator
    the sweep was lossy.
    """
    out: list[dict[str, Any]] = []
    for row in rows or ():
        if not isinstance(row, Mapping):
            continue
        connector = str(row.get("connector") or "").strip()
        name = str(row.get("name") or "").strip()
        if not connector or not name:
            continue
        out.append({
            "connector": connector,
            "name": name,
            "updated": str(row["updated"]).strip() if row.get("updated") else None,
        })
    return out


def admissible_clocks(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Which connectors' timestamps may be used as recency, and why.

    THE SENSOR CHECK. A clock earns admission by DISCRIMINATING: it must resolve
    more distinct days than a twentieth of its rows (floor of three), and at
    least half its rows must carry a timestamp at all. A control-plane field
    that stamps every row within one week of every other fails both ways, and
    failing it is the point — multiplying a score by a constant is not a
    ranking, it is a rename.

    Every connector is reported, admitted or not, with the numbers that decided
    it, so the refusal is auditable and lands in the offer's not-reached line.
    """
    by_connector: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_connector.setdefault(row["connector"], []).append(row)
    verdicts: dict[str, dict[str, Any]] = {}
    for connector, group in sorted(by_connector.items()):
        stamped = [r for r in group if _parse_iso(r.get("updated")) is not None]
        days = {
            _parse_iso(r["updated"]).date().isoformat()  # type: ignore[union-attr]
            for r in stamped
        }
        coverage = len(stamped) / len(group) if group else 0.0
        needed = max(_CLOCK_MIN_DISTINCT, int(len(group) * _CLOCK_DISTINCT_SHARE))
        if coverage < _CLOCK_MIN_COVERAGE:
            reason = "clock_absent_on_most_rows"
        elif len(days) <= needed:
            reason = "clock_does_not_discriminate"
        else:
            reason = None
        verdicts[connector] = {
            "admitted": reason is None,
            "reason": reason,
            "rows": len(group),
            "stamped": len(stamped),
            "distinct_days": len(days),
            "distinct_days_needed": needed + 1,
        }
    return verdicts


def _recency_weight(freshest: datetime | None, now: datetime) -> float:
    if freshest is None:
        return _RECENCY_UNKNOWN
    age_days = max((now - freshest).total_seconds() / 86400.0, 0.0)
    for limit, weight in _RECENCY_BANDS:
        if age_days <= limit:
            return weight
    return _RECENCY_FLOOR


def _identity_tokens(identities: Iterable[Any]) -> set[str]:
    """Identity tokens, tokenized exactly like a name.

    These come FROM the connectors — the account name, the repository owners,
    the workspace titles each API reports about itself. They are an input, not a
    constant, because "the operator's own name" is a different string for every
    operator and the framework must never carry one.
    """
    out: set[str] = set()
    for item in identities or ():
        out.update(tokenize(item))
    return out


# --- the ranking ------------------------------------------------------------


def _token_index(rows: Sequence[Mapping[str, Any]]) -> dict[str, set[int]]:
    index: dict[str, set[int]] = {}
    for position, row in enumerate(rows):
        for token in tokenize(row["name"]):
            index.setdefault(token, set()).add(position)
    return index


def _explained(
    index: Mapping[str, set[int]],
    rows: Sequence[Mapping[str, Any]],
    identity: Iterable[str] = (),
) -> tuple[dict[str, set[int]], list[dict[str, Any]]]:
    """Which of a token's occurrences one connector's filing structure explains.

    NOTHING IS REMOVED HERE, and the previous version of this function removed
    two whole classes; the module header records what that cost. Both
    measurements are unchanged — a token in more than a quarter of one
    connector's rows is that connector's furniture; a token whose occurrences
    are overwhelmingly inside one connector is that connector's structure — but
    the verdict is no longer "this token does not exist". It is "these
    particular occurrences are accounted for", and the token carries on with the
    ones that are not.

    A token the connectors named as the estate's own is exempt outright. It is
    already demoted for being that, its recurrence everywhere is the expected
    consequence of owning everything, and discounting it a second time for the
    same fact would count one property twice.

    Returns ``(explained, notes)`` — a per-token set of explained positions
    (possibly empty) and one auditable note per token that had any.
    """
    exempt = {str(token) for token in identity or ()}
    connector_totals: dict[str, int] = {}
    for row in rows:
        connector_totals[row["connector"]] = connector_totals.get(row["connector"], 0) + 1
    explained: dict[str, set[int]] = {}
    notes: list[dict[str, Any]] = []
    for token, positions in index.items():
        if token in exempt:
            continue
        per_connector: dict[str, set[int]] = {}
        for position in positions:
            per_connector.setdefault(rows[position]["connector"], set()).add(position)
        total = len(positions)
        accounted: set[int] = set()
        reasons: dict[str, str] = {}
        for connector, hits in per_connector.items():
            if (connector_totals[connector] >= _FURNITURE_MIN_ROWS
                    and len(hits) / connector_totals[connector] > _FURNITURE_SHARE):
                accounted |= hits
                reasons[connector] = "connector_furniture"
            elif total >= _CONCENTRATION_MIN_TOTAL and len(hits) / total > _CONCENTRATION:
                accounted |= hits
                reasons[connector] = "single_system_structure"
        if not accounted:
            continue
        explained[token] = accounted
        leading = sorted(reasons, key=lambda c: (-len(per_connector[c]), c))[0]
        notes.append({
            "token": token, "reason": reasons[leading], "connector": leading,
            "total": total, "explained": len(accounted),
            "unexplained": total - len(accounted),
        })
    notes.sort(key=lambda r: (-r["explained"], r["token"]))
    return explained, notes


def _cluster(index: Mapping[str, set[int]]) -> list[list[str]]:
    """Merge tokens covering nearly the same rows.

    Two words that always appear together are ONE candidate; ranking them
    separately splits a candidate's evidence in half and pushes both down. The
    merge is by row-set overlap, so it never has to know what either word
    means — which is what keeps this agnostic.
    """
    tokens = sorted(index, key=lambda t: (-len(index[t]), t))
    parent = {t: t for t in tokens}

    def find(token: str) -> str:
        while parent[token] != token:
            parent[token] = parent[parent[token]]
            token = parent[token]
        return token

    for i, left in enumerate(tokens):
        for right in tokens[i + 1:]:
            a, b = index[left], index[right]
            union = len(a | b)
            if union and len(a & b) / union >= _CLUSTER_JACCARD:
                parent[find(right)] = find(left)
    groups: dict[str, list[str]] = {}
    for token in tokens:
        groups.setdefault(find(token), []).append(token)
    return [sorted(members) for members in groups.values()]


def _label(members: Sequence[str], index: Mapping[str, set[int]]) -> str:
    """The most SPECIFIC member names the cluster: fewest rows first (a narrow
    word beats the generic word it sits inside), then a real word over a
    synthesised compound, then the longer string."""
    return sorted(members, key=lambda t: (len(index[t]), -len(t), t))[0]


def _labelled(groups: Sequence[Sequence[str]],
              index: Mapping[str, set[int]]) -> list[tuple[str, list[str]]]:
    """Name every group once, so a later union can keep a name instead of
    re-deriving one from the fragments it just absorbed."""
    return [(_label(group, index), list(group)) for group in groups]


def _closed_alias_groups(labelled: Sequence[tuple[str, Sequence[str]]],
                         aliases: Iterable[Iterable[Any]]) -> list[list[str]]:
    """Every answer reduced to the candidates it names, then UNIONED.

    REDUCTION IS A SET INTERSECTION against the ranking's own labels, never a
    string comparison, and that is what keeps this path free of the four things
    the module refuses — a stem table, an edit distance, a translation table, a
    shipped alias list. An answer can only pick out words the ranking itself
    produced, so the junk in a typed sentence ("...which the repos CALL...")
    reduces to nothing. Fewer than two survivors joins nothing and is dropped: a
    typed name matching one candidate is a target, not a merge.

    TWO ANSWERS ABOUT ONE THING ARE ONE ANSWER, and skipping the union loses the
    second one. A merge keeps ONE of the names it joined (see
    :func:`_merge_aliases`), so an operator who says "a is b" and later "b is c"
    leaves the second answer pointed at a label the first consumed — and the
    ranking silently drops the merge they just taught. Closing the answers into
    connected components first makes the result independent of which name each
    union kept and of the order the answers arrived in. It is transitive because
    IDENTITY is transitive, not because two strings resembled each other.
    """
    labels = set(name for name, _ in labelled)
    components: list[set[str]] = []
    for alias in aliases or ():
        named: set[str] = set()
        for item in alias or ():
            named.update(tokenize(item))
        named &= labels
        if len(named) < 2:
            continue
        overlapping = [c for c in components if c & named]
        for component in overlapping:
            named |= component
        components = [c for c in components if c not in overlapping]
        components.append(named)
    return [sorted(component) for component in components]


def _merge_aliases(labelled: Sequence[tuple[str, Sequence[str]]],
                   index: Mapping[str, set[int]],
                   aliases: Iterable[Iterable[Any]]) -> list[tuple[str, list[str]]]:
    """Fold clusters the OPERATOR said are one thing into one cluster.

    THE ONE THING NAMES CANNOT DO. Measured on a real estate, the single entity
    spanning the most connectors was scored as two three-connector candidates,
    because its tracker calls it one word and its repository, database and
    hosting call it another. No string function joins them: the row sets do not
    overlap, the words share no stem, and one is not an abbreviation of the
    other. Structure does not join them either — they are two separate
    repositories.

    So the merge is not derived, it is ANSWERED. When the operator names the
    other word for it, that answer comes back in here and the next ranking
    treats them as one. This is the Captain's "the operator supplies the noun by
    answering" made mechanical — and what is learned is an IDENTITY, not a type:
    nothing here records what KIND of thing it is, which is what keeps the
    mechanism agnostic.

    ONLY LABELS MERGE, and that restriction was paid for. Matching an alias
    against every token in a cluster let one common word inside a typed sentence
    ("...which the repos CALL...") pull in an unrelated cluster whose rows
    happened to contain that word, and the junk cluster ranked second. An
    operator can only join things the ranking already NAMED to them; a typed
    word matching nothing is a target, not a merge, and is handled as one.
    Reduction to those labels, and the union of answers that overlap, happen in
    :func:`_closed_alias_groups` — which is where the reason lives.
    """
    labelled = [(name, list(group)) for name, group in labelled]
    for wanted in _closed_alias_groups(labelled, aliases):
        hit = [row for row in labelled if row[0] in wanted]
        if len(hit) < 2:
            continue
        union = sorted({t for _, group in hit for t in group})
        labelled = [row for row in labelled if row not in hit]
        # THE UNION KEEPS ONE OF THE NAMES IT JOINED, and re-deriving the label
        # from scratch does not. `_label` prefers the RAREST member so a narrow
        # word beats the generic word it sits inside, which is right inside a
        # cluster the row sets built and wrong across candidates a judgment
        # joined: the rarest token in the union is by construction the smallest
        # fragment of the entity, so the union of five names for one thing came
        # back labelled with the two-row scrap nobody calls it. The biggest of
        # the joined candidates names the union — most of the estate uses that
        # word for it — and ties break alphabetically so the result is stable.
        widest = min(hit, key=lambda row: (-len({p for t in row[1] for p in index[t]}),
                                           row[0]))
        labelled.append((widest[0], union))
    return labelled


# --- what the operator taught, kept ------------------------------------------
#
# An answer that changes only the shortlist in front of the operator is not
# learning, it is a filter. The merge has to OUTLIVE the answer that taught it —
# the next answer, the next sweep, the next session — or the loop re-asks a
# question the operator already settled, which is the "never ask what it could
# have looked up" failure one turn later. So the answers accumulate, and this is
# the store shape they accumulate in. It lives here rather than in the caller
# because it is the ranker's own vocabulary being kept: label groups, nothing
# else. No kind, no type, no noun — an identity and when it was learned.


def learn_merge(store: Any, group: Iterable[Any], *, now: str,
                answer: str = "", source: str = "named") -> dict[str, Any]:
    """Append one "these are the same thing" to the store. Never overwrites.

    DEDUPED BY THE SET, not by the row. Two answers naming the same pair are one
    fact learned twice — an operator re-confirming a merge is not a second merge
    — and appending both would grow the store without bound across sessions on a
    loop that re-offers the same estate. A group naming fewer than two things is
    refused entry: it joins nothing, and a row that can never fire is noise in a
    record the next reader has to trust.
    """
    rows: list[dict[str, Any]] = []
    if isinstance(store, Mapping):
        for row in store.get("groups") or ():
            if isinstance(row, Mapping) and row.get("labels"):
                rows.append(dict(row))
    labels = sorted({str(item).strip() for item in group or () if str(item).strip()})
    if len(labels) >= 2 and not any(
        sorted({str(x) for x in row.get("labels") or ()}) == labels for row in rows
    ):
        rows.append({
            "labels": labels,
            "learned_at": str(now),
            "answer": str(answer),
            "source": str(source),
        })
    return {"schema": SALIENCE_MERGE_SCHEMA, "groups": rows}


def learned_merges(store: Any) -> list[list[str]]:
    """The stored answers, in the shape :func:`rank` takes as ``aliases``.

    Reading is deliberately forgiving — a row whose ``labels`` are unusable is
    skipped, not raised on. This store is read on every render of the operator's
    card, and a card that refuses to draw because one historical row is
    malformed would take the whole surface down to protect an ordering.
    """
    groups: list[list[str]] = []
    if not isinstance(store, Mapping):
        return groups
    for row in store.get("groups") or ():
        if not isinstance(row, Mapping):
            continue
        labels = [s for s in (str(i).strip() for i in row.get("labels") or ()) if s]
        if len(labels) >= 2:
            groups.append(labels)
    return groups


def _assemble(
    groups: Sequence[tuple[str, Sequence[str]]],
    index: Mapping[str, set[int]],
    explained: Mapping[str, set[int]],
    normalized: Sequence[Mapping[str, Any]],
    clocks: Mapping[str, Mapping[str, Any]],
    identity: set[str],
    now_dt: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Turn token groups into scored candidates, and say what fell short.

    ``score = connectors² × recency × (1 + min(unexplained, 20)/20) × identity``

    Recurrence across connectors is squared because it is the ENTIRE signal the
    Captain named — a name in four systems is categorically different from a
    name in two, while a name appearing 400 times in one system is a list.
    Volume is damped, capped, and counted over the occurrences one connector's
    filing structure does NOT already account for, which is where the discount
    lands: a candidate that is 93% filing structure is ranked on the other 7%
    rather than removed. Recency multiplies only where the clock was admitted.

    THE SPAN IS COUNTED OVER THE STANDING OCCURRENCES, and that follows from
    what the discount means rather than from tuning. A candidate's claim is
    "this name recurs ACROSS systems"; a system whose own filing explains every
    occurrence there is not evidence for that claim, so it does not vote in the
    span either. Measured: leaving explained occurrences in the span put one
    tracker's filing word at rank 4 of 51 on three connectors, two of which
    contributed two rows between them. The raw span is reported beside it.

    A group standing in fewer than ``_MIN_CONNECTORS`` connectors is not a
    candidate — recurrence across systems is the whole signal, and a name in one
    system is a list. It goes into the second return value with its numbers
    rather than disappearing, because "never spanned two systems" and "ranked
    last" are different facts and an operator looking for a missing answer needs
    to know which one happened.
    """
    clusters: list[dict[str, Any]] = []
    short: list[dict[str, Any]] = []
    for label, members in groups:
        positions: set[int] = set()
        accounted: set[int] = set()
        for token in members:
            positions |= index[token]
            accounted |= explained.get(token, set())
        accounted &= positions
        standing_positions = positions - accounted
        connectors = sorted({normalized[p]["connector"] for p in standing_positions})
        if len(connectors) < _MIN_CONNECTORS:
            short.append({
                "label": label, "tokens": sorted(members),
                "connectors": sorted({normalized[p]["connector"] for p in positions}),
                "connectors_standing": connectors,
                "rows": len(positions), "rows_standing": len(standing_positions),
                "reason": ("spans_one_connector" if not accounted
                           else "one_system_explains_where_it_recurs"),
            })
            continue
        freshest: datetime | None = None
        for position in positions:
            row = normalized[position]
            if not clocks.get(row["connector"], {}).get("admitted"):
                continue
            stamp = _parse_iso(row.get("updated"))
            if stamp and (freshest is None or stamp > freshest):
                freshest = stamp
        recency = _recency_weight(freshest, now_dt)
        matched_identity = sorted(set(members) & identity)
        demotion = _IDENTITY_DEMOTION if matched_identity else 1.0
        standing = len(standing_positions)
        volume = 1.0 + min(standing, _VOLUME_CAP) / _VOLUME_CAP
        score = (len(connectors) ** 2) * recency * volume * demotion
        per_connector: dict[str, list[str]] = {}
        for position in sorted(positions, key=lambda p: normalized[p]["name"]):
            row = normalized[position]
            per_connector.setdefault(row["connector"], []).append(row["name"])
        clusters.append({
            "label": label,
            "tokens": sorted(members),
            "connectors": sorted({normalized[p]["connector"] for p in positions}),
            "connectors_standing": connectors,
            "rows": len(positions),
            "rows_standing": standing,
            "rows_explained": len(accounted),
            "per_connector": {c: len(n) for c, n in sorted(per_connector.items())},
            "examples": {c: n[:3] for c, n in sorted(per_connector.items())},
            "freshest": freshest.strftime("%Y-%m-%dT%H:%M:%SZ") if freshest else None,
            "recency_weight": recency,
            "recency_measured": freshest is not None,
            "identity_match": matched_identity,
            "demoted": bool(matched_identity) or bool(accounted),
            "score": round(score, 4),
        })
    clusters.sort(key=lambda c: (-c["score"], -len(c["connectors"]), c["label"]))
    short.sort(key=lambda c: (-c["rows"], c["label"]))
    return clusters, short


def join_proposal(clusters: Sequence[Mapping[str, Any]],
                  *, names_per_connector: int = 4) -> dict[str, Any]:
    """The candidates and the estate's own words for them, UNMODIFIED.

    This is the whole input judgment needs and the whole input it is allowed to
    have. Every name is passed through exactly as the connector reported it —
    no stemming, no lowering, no normalising — because the joinable evidence
    lives in the surface form: one system writes a name solid, another writes it
    hyphenated, a third abbreviates it, and a fourth prefixes the year. A
    tokenizer sees six unrelated strings there and a reader sees one thing.

    It carries no scores and no counts beyond how many names were withheld. A
    judge shown a score is being told the answer it was asked to check.
    """
    per = max(int(names_per_connector), 1)
    candidates = []
    for cluster in clusters:
        names: list[str] = []
        withheld = 0
        for connector, shown in (cluster.get("examples") or {}).items():
            total = (cluster.get("per_connector") or {}).get(connector, len(shown))
            names.extend(str(n) for n in list(shown)[:per])
            withheld += max(total - min(len(shown), per), 0)
        candidates.append({
            "label": str(cluster.get("label") or ""),
            "names": names,
            "names_withheld": withheld,
            "connectors": list(cluster.get("connectors") or ()),
        })
    return {
        "schema": SALIENCE_JOIN_SCHEMA,
        "question": "Which of these candidates are the same thing under "
                    "different names? Answer with groups of labels, or nothing.",
        "candidates": candidates,
    }


def _judged_joins(join: Any, clusters: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Ask judgment which candidates are one thing, and refuse what it invents.

    A judge that answers with a label the ranking never produced has not read
    the estate, and accepting that answer would let an unbounded string arrive
    in the ranking's own vocabulary. Such a group is REFUSED and recorded,
    never silently dropped: a judgment that misfired is a fact about the loop
    and the next reader is owed it. A group naming fewer than two candidates
    joins nothing and is refused the same way.
    """
    if not callable(join):
        raise SalienceError("join_not_callable", "A join must be something to ask.")
    offered = {str(c.get("label") or "") for c in clusters}
    try:
        answer = join(join_proposal(clusters))
    except Exception as exc:
        # A JUDGMENT THAT DIED IS AN ABSENT ONE, not a dead ranking. Judgment
        # here is optional by construction — the module's own default is no join
        # at all, and the ranking is honest without one, split candidates and
        # all. Letting the exception out would mean an unreachable model, a
        # timeout or a parse error takes down the operator's whole offer to
        # improve its ordering, which is a worse outcome than the ordering it
        # was asked to improve. Recorded by TYPE only: a judge's failure text is
        # not this module's to carry into an operator-facing surface.
        return [{"labels": [], "accepted": False, "reason": "judgment_unavailable",
                 "error": type(exc).__name__}]
    out: list[dict[str, Any]] = []
    for group in answer or ():
        if isinstance(group, (str, bytes)) or not isinstance(group, Iterable):
            out.append({"labels": [], "accepted": False, "reason": "not_a_group"})
            continue
        labels = [str(item) for item in group]
        unknown = sorted({label for label in labels if label not in offered})
        if unknown:
            out.append({"labels": labels, "accepted": False,
                        "reason": "names_a_candidate_that_was_never_ranked",
                        "unknown": unknown})
        elif len(set(labels)) < 2:
            out.append({"labels": labels, "accepted": False,
                        "reason": "joins_nothing"})
        else:
            out.append({"labels": sorted(set(labels)), "accepted": True})
    return out


def rank(
    rows: Iterable[Mapping[str, Any]],
    *,
    identities: Iterable[Any] = (),
    aliases: Iterable[Iterable[Any]] = (),
    join: Any = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Rank the estate's recurring names. Read-only, content-free, no network.

    ``join`` is the seam where JUDGMENT joins what names cannot. It is handed
    :func:`join_proposal`'s payload — every candidate's label and the estate's
    own names for it, UNMODIFIED — and answers with groups of labels that are
    one thing. Nothing in here compares two strings to decide that, and nothing
    in here may: a stem table or an edit distance is a hand-maintained list
    wearing an algorithm, correct for the estate it was tuned on. Absent a
    ``join`` the ranking stands exactly as the names left it, split candidates
    and all, and the operator's answer through the escape hatch is the same
    union arriving by a different route.
    """
    normalized = normalize_rows(rows)
    clocks = admissible_clocks(normalized)
    now_dt = _parse_iso(now) or datetime.now(timezone.utc)
    index = _token_index(normalized)
    identity = _identity_tokens(identities)
    explained, discounted = _explained(index, normalized, identity)

    groups = _merge_aliases(_labelled(_cluster(index), index), index, aliases)
    clusters, short = _assemble(groups, index, explained, normalized, clocks,
                                identity, now_dt)
    judged: list[dict[str, Any]] = []
    if join is not None:
        judged = _judged_joins(join, clusters)
        accepted = [row["labels"] for row in judged if row["accepted"]]
        if accepted:
            groups = _merge_aliases(groups, index, accepted)
            clusters, short = _assemble(groups, index, explained, normalized,
                                        clocks, identity, now_dt)
    connector_rows: dict[str, int] = {}
    for row in normalized:
        connector_rows[row["connector"]] = connector_rows.get(row["connector"], 0) + 1
    return {
        "schema": SALIENCE_SCHEMA,
        "clusters": clusters,
        "discounted": discounted,
        "not_candidates": short,
        "joined": judged,
        "clocks": clocks,
        "coverage": {
            "connectors": sorted(connector_rows),
            "rows_by_connector": dict(sorted(connector_rows.items())),
            "rows": len(normalized),
            "tokens": len(index),
            "tokens_discounted": len(discounted),
            "clusters_ranked": len(clusters),
            "below_span": len(short),
        },
    }


# --- where the rows come from -----------------------------------------------


def rows_from_state(state: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Rows this journey can build WITHOUT asking for one new permission.

    Two providers, and neither of them opens anything:

    * ``salience_rows`` — a rows block someone already lawfully produced. A
      credentialed connector sweep is one producer; an operator-supplied export
      is another; the local probes below are a third. The ranker cannot tell
      them apart and must not: keeping the row a plain triple is what stops this
      module from growing an API client per system, each written against a
      production estate it may only read.
    * the connector registry this journey already probed — every source that
      ANSWERED becomes a row, so a bare local hatch still gets a real (small)
      ranking rather than an empty one dressed up as a survey.

    A credentialed sweep is deliberately NOT here — a client that writes by
    accident is a class of damage a read-only ranker should not be able to
    cause. It hands rows in; it does not live here. Its producer is
    ``framework.onboarding.research.sweep_connectors``, run by the journey's
    ``gather_connectors`` action, which writes ``salience_rows`` (rows +
    identities + not_reached) onto state — so this function reads a lawfully
    produced block and still cannot tell a credentialed sweep from an operator
    export, which is the property that keeps a per-system client out of here.
    """
    rows: list[dict[str, Any]] = []
    identities: list[str] = []
    supplied = state.get("salience_rows") if isinstance(state, Mapping) else None
    if isinstance(supplied, Mapping):
        raw = list(supplied.get("rows") or ())
        rows.extend(normalize_rows(raw))
        identities.extend(
            str(i) for i in (supplied.get("identities") or ()) if str(i).strip()
        )
        # THE OWNER FIELD IS AN IDENTITY STRING TOO, and leaving it out cost a
        # correct answer. A connector's identity call asks the CREDENTIAL who it
        # is; the owner stamped on each row says who the estate belongs to, and
        # measured on a live estate those were different words — the credential
        # answered with a person and 52 of 56 repositories were owned by an
        # organisation whose name never entered the demotion set at all. Both
        # are "what this estate calls itself", which is all demotion asks; and
        # both come FROM the connectors, so no list is being maintained here.
        # It stays out of attribution, where the same string means nothing:
        # see framework.onboarding.research.operator_identity.
        #
        # DEDUPED, because this reads one entry PER ROW: the live estate stamps
        # 665 rows with four distinct owners, and an undeduped list would hand
        # every caller 665 strings to carry, log or disclose for four facts.
        # Order is kept so the result is stable to read and to diff.
        seen = {str(i) for i in identities}
        for row in raw:
            if not isinstance(row, Mapping):
                continue
            for actor in (row.get("actors") or ()):
                text = str(actor).strip()
                if text and text not in seen:
                    seen.add(text)
                    identities.append(text)
    probes = state.get("connector_probes") if isinstance(state, Mapping) else None
    for probe in (probes or {}).get("connected", ()) if isinstance(probes, Mapping) else ():
        if not isinstance(probe, Mapping):
            continue
        kind = str(probe.get("kind") or "").strip()
        name = str(probe.get("name") or "").strip()
        if not kind or not name or kind == "web":
            continue
        # ``repo:foo`` / ``tracker_export:a/b.csv`` — the connector is the kind,
        # the name is what follows it, so a path's basename is the thing named.
        tail = name.split(":", 1)[1] if ":" in name else name
        rows.append({"connector": kind, "name": tail.rsplit("/", 1)[-1], "updated": None})
    return rows, identities


def sweep_ceiling(root: Any) -> dict[str, Any]:
    """May a credentialed sweep leave this machine at all? FAIL-CLOSED.

    ``instance/config/egress.yml`` is the Captain-owned live switch and it is
    germline-locked, so a cabinet cannot widen its own reach. Under the shipped
    default (``enforce: false``) a sweep proceeds; under enforcement with an
    EMPTY allow list it would 403 on every request — the posture this deployment
    carried until 2026-07-29 — and a sweep that plans requests it cannot make is
    an interview whose answers go nowhere.

    So the ceiling is consulted BEFORE any credentialed provider runs, and a
    closed ceiling is reported as a not-reached reason in the offer rather than
    discovered as a wall of failures. The verdict is
    ``framework.onboarding.research._probe_web``'s, read through its public
    probe so there is exactly one reading of that file in the tree.
    """
    from framework.onboarding import research  # local: keep this module light

    verdict = research._probe_web(root)
    return {
        "permitted": bool(verdict.get("connected")),
        "reason": verdict.get("reason"),
        "evidence": verdict.get("evidence"),
    }


# --- the oracle -------------------------------------------------------------


def check(ranking: Mapping[str, Any],
          answers: Iterable[Any],
          *, top: int = 3) -> dict[str, Any]:
    """Grade a ranking against answers THE OPERATOR gave. Read-only, no network.

    THE ANSWER KEY IS AN ARGUMENT, and that is the entire design. A key living
    inside this module would be right for the one estate it was copied from and
    a fiction everywhere else — the same defect as a stopword list, arriving as
    a test fixture instead of a constant. So the oracle asks a question any
    estate can answer: the operator names what actually matters to them, and
    this reports where the mechanism put it. Nothing here knows what a good
    answer looks like; it knows only whether the ranking reached the answer it
    was handed. Run it on a synthesised estate and the planted entity is the
    key; run it on a live one and the operator's own words are.

    THE DISTINCTION IT EXISTS TO DRAW is between an answer that ranked low and
    an answer that could not be ranked at all. The first is a shortlist the
    operator scrolls; the second is a correct answer the mechanism lost, and
    every version of this ranker that deleted rather than demoted produced the
    second while looking exactly like the first from the outside.

    Matching uses :func:`tokenize` — the ranker's OWN vocabulary and nothing
    else. No stemming, no edit distance, no near-miss allowance: the oracle may
    only credit the ranking with a word the ranking could itself have produced,
    or it becomes an instrument that grades generously and reports success.
    """
    if not isinstance(ranking, Mapping) or ranking.get("schema") != SALIENCE_SCHEMA:
        raise SalienceError("ranking_invalid", "That is not a salience ranking.")
    cut = max(int(top), 0)
    clusters = list(ranking.get("clusters") or ())
    short = list(ranking.get("not_candidates") or ())
    graded: list[dict[str, Any]] = []
    for answer in answers or ():
        text = str(answer or "").strip()
        wanted = set(tokenize(text))
        row: dict[str, Any] = {"answer": text, "tokens": sorted(wanted)}
        if not wanted:
            row.update(verdict="unrankable_name", position=None,
                       why="nothing in this name survives the length rule")
            graded.append(row)
            continue
        found = next(
            ((i, c) for i, c in enumerate(clusters, 1) if wanted & set(c["tokens"])),
            None,
        )
        if found:
            position, cluster = found
            row.update(
                position=position,
                label=cluster["label"],
                matched=sorted(wanted & set(cluster["tokens"])),
                connectors=list(cluster["connectors"]),
                rows=cluster["rows"],
                rows_standing=cluster.get("rows_standing", cluster["rows"]),
                demoted=bool(cluster.get("demoted")),
                verdict="offered" if position <= cut else "below_the_cut",
                why=("in the shortlist the operator sees" if position <= cut
                     else f"ranked {position} of {len(clusters)}; the operator "
                          f"reaches it only past the cut"),
            )
        else:
            near = next((s for s in short if wanted & set(s["tokens"])), None)
            if near:
                row.update(verdict="not_a_candidate", position=None,
                           label=near["label"], connectors=list(near["connectors"]),
                           rows=near["rows"],
                           why="its words recur inside one system only, and "
                               "recurrence across systems is the whole signal")
            else:
                row.update(verdict="never_seen", position=None,
                           why="no name read by the sweep carries any of its words")
        graded.append(row)
    offered = [r for r in graded if r["verdict"] == "offered"]
    reached = [r for r in graded if r["verdict"] in ("offered", "below_the_cut")]
    lost = [r for r in graded if r["verdict"] not in ("offered", "below_the_cut")]
    if not graded:
        verdict = "nothing_to_check"
    elif lost:
        verdict = "lost"
    elif len(offered) == len(graded):
        verdict = "all_offered"
    else:
        verdict = "reached_but_below_the_cut"
    return {
        "schema": SALIENCE_CHECK_SCHEMA,
        "top": cut,
        "ranked": len(clusters),
        "answers": graded,
        "offered": len(offered),
        "reached": len(reached),
        "lost": len(lost),
        "deepest": max((r["position"] for r in reached), default=None),
        "verdict": verdict,
    }


# --- the ask ----------------------------------------------------------------


def _evidence_line(cluster: Mapping[str, Any]) -> str:
    """One auditable sentence per candidate: the NAMES that produced it.

    A score the operator cannot check is not evidence. Names are, and they are
    also what lets the operator see instantly that a candidate is a coincidence
    of words rather than a thing.
    """
    parts = []
    for connector, names in (cluster.get("examples") or {}).items():
        count = (cluster.get("per_connector") or {}).get(connector, len(names))
        shown = ", ".join(names)
        extra = f" (+{count - len(names)} more)" if count > len(names) else ""
        parts.append(f"{connector}: {shown}{extra}")
    line = " · ".join(parts)
    if cluster.get("freshest"):
        line += f" · newest {cluster['freshest'][:10]}"
    elif not cluster.get("recency_measured"):
        line += " · age unknown (no usable clock on these sources)"
    return line


def not_reached_line(
    ranking: Mapping[str, Any],
    extra: Sequence[str] = (),
    *,
    shown: int | None = None,
) -> str:
    """What the sweep did NOT reach — the sentence that makes the offer honest.

    A ranking presented without it reads as a survey of everything, and an
    operator who believes that will not use the escape hatch when the right
    answer is missing. Refused clocks, floored tokens, the candidates below the
    cut and caller-supplied gaps all land here in plain words.

    THE CUT IS DISCLOSED BECAUSE IT IS SMALL. The picker holds four options, so
    three candidates and an escape hatch is the whole surface — and measured on
    a real estate the operator's own answers landed at ranks 1, 4 and 8 of 47.
    An offer that shows three of forty-seven without saying so is asserting that
    the other forty-four were considered and rejected, which nobody did.
    """
    coverage = ranking.get("coverage") or {}
    bits: list[str] = []
    total = len(ranking.get("clusters") or ())
    if shown is not None and total > shown:
        bits.append(
            f"I ranked {total} candidate(s) and am showing the top {shown} — "
            f"ranks {shown + 1}-{total} are there if none of these is it"
        )
    rows_by = coverage.get("rows_by_connector") or {}
    if rows_by:
        bits.append(
            "Ranked names only, never contents: "
            + ", ".join(f"{count} from {c}" for c, count in rows_by.items())
        )
    discounted = ranking.get("discounted") or []
    if discounted:
        listed = ", ".join(str(f["token"]) for f in discounted[:4])
        bits.append(
            f"{len(discounted)} recurring word(s) count for less because one "
            f"system's own filing explains most of where they appear ({listed}) "
            f"— none of them was removed"
        )
    short = ranking.get("not_candidates") or []
    if short:
        bits.append(
            f"{len(short)} name(s) recur inside a single system only, so "
            f"nothing here ranks them against anything"
        )
    dead = [c for c, v in (ranking.get("clocks") or {}).items() if not v.get("admitted")]
    if dead:
        bits.append(
            "no usable last-touched clock on " + ", ".join(sorted(dead))
            + ", so nothing there is ranked by how recent it is"
        )
    bits.extend(str(item) for item in extra if str(item).strip())
    if not bits:
        return ""
    return "What I did not reach: " + "; ".join(bits) + "."


def merge_ask(ranking: Mapping[str, Any], learned: Any = ()) -> dict[str, Any]:
    """The second question, and the only one a matcher provably cannot answer.

    "Which of these should I open first?" assumes the candidates are distinct
    things. Measured, they are not: one entity stood as FIVE candidates at ranks
    6, 11, 21, 33 and 34 because each system writes it differently. An offer that
    asks only the first question hands the operator a shortlist they can see is
    wrong and no way to say so.

    EVERY RANKED CANDIDATE IS NAMEABLE HERE, not just the shown three, and that
    is the whole reason this block exists separately from the options. The twin
    of the candidate at the top routinely sits below the cut — at ranks 11 and 33
    in the measured case — so a merge restricted to what is on screen cannot
    reach the split it exists to fix.

    WHAT IS ALREADY LEARNED IS ECHOED BACK, because the alternative is asking a
    question the operator already answered. It is also the only place the merge
    is VISIBLE: once two candidates are one, the second name is no longer in the
    ranking, and without this line the operator cannot tell whether their answer
    took or was dropped.
    """
    candidates = [
        {
            "id": str(cluster.get("label") or ""),
            "label": str(cluster.get("label") or ""),
            "connectors": list(cluster.get("connectors") or ()),
        }
        for cluster in (ranking.get("clusters") or ())
    ]
    return {
        "field": "same_as",
        "question": "Are any two of these the same thing under different names? "
                    "Name them together and I will treat them as one from now on.",
        "candidates": candidates,
        "learned": [
            {"labels": list(group)}
            for group in (learned or ())
            if len(list(group)) >= 2
        ],
    }


def offer(
    ranking: Mapping[str, Any],
    *,
    top: int = 3,
    not_reached: Sequence[str] = (),
    learned: Any = (),
) -> dict[str, Any]:
    """Turn a ranking into the ask: candidates, evidence, and an escape hatch.

    REFUSES an empty coverage block. An offer built from a ranking that never
    recorded what it read would present a clean negative nobody earned, which is
    the failure this program keeps finding in its own sensors; so the degenerate
    input raises rather than returning a confident-looking empty list.

    The escape hatch is not decoration and is never omitted: measured on a real
    estate, the correct answer can sit outside the top three, and an offer with
    no way to say "none of these" converts that into a wrong answer the operator
    had to accept.

    ``merge`` carries the second question — see :func:`merge_ask`. It is part of
    the offer rather than a separate surface because an affordance the operator
    is never shown is not an escape hatch, it is a parameter.
    """
    if not isinstance(ranking, Mapping) or ranking.get("schema") != SALIENCE_SCHEMA:
        raise SalienceError("ranking_invalid", "That is not a salience ranking.")
    coverage = ranking.get("coverage")
    if not isinstance(coverage, Mapping) or not coverage.get("connectors"):
        raise SalienceError(
            "coverage_missing",
            "I will not offer candidates without recording what I read.",
        )
    clusters = list(ranking.get("clusters") or ())[: max(int(top), 0)]
    options = [
        {
            "id": cluster["label"],
            "label": cluster["label"],
            "why": _evidence_line(cluster),
            "connectors": list(cluster["connectors"]),
            "rows": cluster["rows"],
            "aliases": list(cluster["tokens"]),
        }
        for cluster in clusters
    ]
    options.append({
        "id": ESCAPE_OPTION_ID,
        "label": "None of these — I will name it",
        "why": "The ranking can be wrong; a name you type beats a name I guessed.",
        "input": "seed",
    })
    return {
        "schema": SALIENCE_OFFER_SCHEMA,
        "prompt": "Of everything I found, which should I go deep on first?",
        "options": options,
        "merge": merge_ask(ranking, learned),
        "not_reached": not_reached_line(ranking, not_reached, shown=len(clusters)),
        "ranked": len(ranking.get("clusters") or ()),
    }
