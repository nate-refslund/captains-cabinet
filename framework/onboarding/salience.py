"""salience — rank what RECURS across connected sources, then ask which one matters.

THE QUESTION THIS ANSWERS, and the one it does not. An operator arrives with
531 boards, 56 repositories, 20 databases and 58 hostings. "Read all of it" was
REFUTED by decisive experiment (``framework.onboarding.research``: of four
findings, one needed more than one file and ZERO needed more than one system),
so this module never reads content. It reads NAMES AND COUNTS, ranks what
recurs, and hands the operator a short list to point at. Ranking is not ingest:
the expensive, risky, revocable part is DEPTH, and depth is spent only where
the operator points.

NO TAXONOMY. Nowhere below is there a list of entity kinds — no product, no
project, no client, no campaign, no case. The primitive is a ``row``:
``(connector, name, updated)``. Whatever string recurs across the most
connectors, most recently, is the candidate. For one operator those strings are
products; for a salesperson they are clients; for a librarian they are
collections. The mechanism must not know which, and the operator supplies the
noun BY ANSWERING — never by configuring. A kind-list here would be correct for
exactly one estate and wrong for the next one, which is why three
hand-maintained lists were deleted from this program in a single week.

WHY THE FLOORS ARE MEASURED, NEVER WRITTEN DOWN. Naive recurrence ranks noise
first, and the noise is estate-specific: the employer's own name recurs
everywhere because everything belongs to it; a tracker's template words
("Subitems of ...") recur because the tracker put them there; a scaffolding
prefix recurs because a generator put it there. A hand list of stopwords would
encode ONE estate into the framework. So every floor below is derived from the
rows themselves:

* ``_FURNITURE_SHARE`` — a token in more than a quarter of ONE connector's rows
  is that connector's furniture, whatever the word is.
* ``_CONCENTRATION`` — a token whose occurrences are overwhelmingly inside a
  single system is that system's structure, not a thing that spans systems.
* identity DEMOTION, never deletion — a token matching an account, owner or
  workspace name the connectors themselves reported is demoted, because the
  operator's own name is genuine noise AND may also be a genuine target. Both
  are true of the same string: an estate whose owner is "step network" also
  contains the product "stepnetwork.dk". A delete floor erases the second to
  suppress the first; only a demotion keeps both facts.

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

#: The escape hatch's option id. It is not a candidate: it is the admission
#: that the ranking may be wrong, and it carries a text field so the answer can
#: name something the sweep never ranked.
ESCAPE_OPTION_ID = "other"

# --- floors, all applied to MEASURED quantities -----------------------------

#: Tokens shorter than this are ranked out. Not a stopword list: a length rule
#: is estate-independent, and every short token is disclosed as floored.
_MIN_TOKEN_LEN = 4
#: A token in more than this share of ONE connector's rows is that connector's
#: furniture. Measured, not declared — the word is irrelevant.
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


def tokenize(name: Any) -> list[str]:
    """Split a name into ranking tokens, plus the compounds of adjacent pairs.

    The compounds are not decoration. A name written ``step-network-website``
    and a name written ``stepnetwork.dk`` refer to the same thing, and a
    word-only tokenizer cannot see it: it produces ``step`` and ``network``
    (which are the ESTATE's own name, ranked first and third by pure noise) and
    never produces ``stepnetwork`` at all. Emitting the adjacent-pair compound
    is mechanical, needs no dictionary, and is what lets the specific token beat
    its own generic fragments.

    Tokens shorter than ``_MIN_TOKEN_LEN`` are dropped here; digits are kept,
    because a case number or a vessel id is a perfectly good recurring token in
    an estate this module is not allowed to know the shape of.
    """
    text = str(name or "").lower()
    parts = [p for p in _TOKEN_SPLIT_RE.split(text) if p]
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if len(part) >= _MIN_TOKEN_LEN and part not in seen:
            seen.add(part)
            out.append(part)
    for left, right in zip(parts, parts[1:]):
        joined = left + right
        if len(joined) >= _MIN_TOKEN_LEN and joined not in seen:
            seen.add(joined)
            out.append(joined)
    return out


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


def _apply_floors(
    index: Mapping[str, set[int]],
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, set[int]], list[dict[str, Any]]]:
    """Drop the two measured noise classes and say which token went for which
    reason. Returns the surviving index and the floored rows."""
    connector_totals: dict[str, int] = {}
    for row in rows:
        connector_totals[row["connector"]] = connector_totals.get(row["connector"], 0) + 1
    kept: dict[str, set[int]] = {}
    floored: list[dict[str, Any]] = []
    for token, positions in index.items():
        per_connector: dict[str, int] = {}
        for position in positions:
            connector = rows[position]["connector"]
            per_connector[connector] = per_connector.get(connector, 0) + 1
        furniture = [
            connector
            for connector, count in per_connector.items()
            if connector_totals[connector] >= _FURNITURE_MIN_ROWS
            and count / connector_totals[connector] > _FURNITURE_SHARE
        ]
        if furniture:
            floored.append({
                "token": token, "reason": "connector_furniture",
                "connector": sorted(furniture)[0], "total": len(positions),
            })
            continue
        total = len(positions)
        top = max(per_connector.values())
        if total >= _CONCENTRATION_MIN_TOTAL and top / total > _CONCENTRATION:
            floored.append({
                "token": token, "reason": "single_system_structure",
                "connector": max(per_connector, key=lambda c: per_connector[c]),
                "total": total,
            })
            continue
        kept[token] = positions
    floored.sort(key=lambda r: (-r["total"], r["token"]))
    return kept, floored


def _cluster(index: Mapping[str, set[int]]) -> list[list[str]]:
    """Merge tokens covering nearly the same rows.

    Two words that always appear together are ONE candidate; ranking them
    separately splits a candidate's evidence in half and pushes both down. The
    merge is by row-set overlap, so it needs no notion of what either word
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


def _merge_aliases(groups: list[list[str]],
                   index: Mapping[str, set[int]],
                   aliases: Iterable[Iterable[Any]]) -> list[list[str]]:
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
    """
    labelled = [(_label(group, index), list(group)) for group in groups]
    for alias in aliases or ():
        wanted: set[str] = set()
        for item in alias or ():
            wanted.update(tokenize(item))
        hit = [row for row in labelled if row[0] in wanted]
        if len(hit) < 2:
            continue
        union = sorted({t for _, group in hit for t in group})
        labelled = [row for row in labelled if row not in hit]
        labelled.append((_label(union, index), union))
    return [group for _, group in labelled]


def rank(
    rows: Iterable[Mapping[str, Any]],
    *,
    identities: Iterable[Any] = (),
    aliases: Iterable[Iterable[Any]] = (),
    now: str | None = None,
) -> dict[str, Any]:
    """Rank the estate's recurring names. Read-only, content-free, no network.

    ``score = connectors² × recency × (1 + min(rows, 20)/20) × identity``

    Recurrence across connectors is squared because it is the ENTIRE signal the
    Captain named — a name in four systems is categorically different from a
    name in two, while a name appearing 400 times in one system is a list.
    Volume is damped and capped for the same reason. Recency multiplies only
    where the clock was admitted.
    """
    normalized = normalize_rows(rows)
    clocks = admissible_clocks(normalized)
    now_dt = _parse_iso(now) or datetime.now(timezone.utc)
    index = _token_index(normalized)
    kept, floored = _apply_floors(index, normalized)
    identity = _identity_tokens(identities)

    clusters: list[dict[str, Any]] = []
    for members in _merge_aliases(_cluster(kept), kept, aliases):
        positions: set[int] = set()
        for token in members:
            positions |= kept[token]
        connectors = sorted({normalized[p]["connector"] for p in positions})
        if len(connectors) < _MIN_CONNECTORS:
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
        volume = 1.0 + min(len(positions), _VOLUME_CAP) / _VOLUME_CAP
        score = (len(connectors) ** 2) * recency * volume * demotion
        per_connector: dict[str, list[str]] = {}
        for position in sorted(positions, key=lambda p: normalized[p]["name"]):
            row = normalized[position]
            per_connector.setdefault(row["connector"], []).append(row["name"])
        clusters.append({
            "label": _label(members, kept),
            "tokens": list(members),
            "connectors": connectors,
            "rows": len(positions),
            "per_connector": {c: len(n) for c, n in sorted(per_connector.items())},
            "examples": {c: n[:3] for c, n in sorted(per_connector.items())},
            "freshest": freshest.strftime("%Y-%m-%dT%H:%M:%SZ") if freshest else None,
            "recency_weight": recency,
            "recency_measured": freshest is not None,
            "identity_match": matched_identity,
            "demoted": bool(matched_identity),
            "score": round(score, 4),
        })
    clusters.sort(key=lambda c: (-c["score"], -len(c["connectors"]), c["label"]))
    connector_rows: dict[str, int] = {}
    for row in normalized:
        connector_rows[row["connector"]] = connector_rows.get(row["connector"], 0) + 1
    return {
        "schema": SALIENCE_SCHEMA,
        "clusters": clusters,
        "floored": floored,
        "clocks": clocks,
        "coverage": {
            "connectors": sorted(connector_rows),
            "rows_by_connector": dict(sorted(connector_rows.items())),
            "rows": len(normalized),
            "tokens": len(index),
            "tokens_after_floors": len(kept),
            "clusters_ranked": len(clusters),
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

    A credentialed sweep is deliberately NOT here. On a deployment whose egress
    ceiling is closed (``sweep_ceiling``) it could not make one request, and a
    client that writes by accident is a class of damage a read-only ranker
    should not be able to cause. It hands rows in; it does not live here.
    """
    rows: list[dict[str, Any]] = []
    identities: list[str] = []
    supplied = state.get("salience_rows") if isinstance(state, Mapping) else None
    if isinstance(supplied, Mapping):
        rows.extend(normalize_rows(supplied.get("rows") or ()))
        identities.extend(
            str(i) for i in (supplied.get("identities") or ()) if str(i).strip()
        )
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
    germline-locked, so a cabinet cannot widen its own reach. This deployment's
    is ``enforce: true`` with an EMPTY allow list, which means a connector sweep
    would 403 on every request — and a sweep that plans requests it cannot make
    is an interview whose answers go nowhere.

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
    floored = ranking.get("floored") or []
    if floored:
        shown = ", ".join(str(f["token"]) for f in floored[:4])
        bits.append(
            f"{len(floored)} recurring word(s) were ranked out as filing "
            f"structure rather than things ({shown})"
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


def offer(
    ranking: Mapping[str, Any],
    *,
    top: int = 3,
    not_reached: Sequence[str] = (),
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
        "not_reached": not_reached_line(ranking, not_reached, shown=len(clusters)),
        "ranked": len(ranking.get("clusters") or ()),
    }
