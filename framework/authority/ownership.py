"""Per-source ownership class — whose data a source is, and what may be done with it.

WHY THIS PLANE EXISTS.  Connecting an estate to an autonomous cabinet is an
authorization decision.  A founder holds that decision over their own company;
a developer inside a large company does not hold it over their employer's
trackers, drives or mail, and a connect-by-default sweep would make it for
them.  This module is the ONE place the cabinet asks whose data a source is,
and the one place the answer changes behaviour — so that "read-only for
anything not yours" is a property of the code path rather than a setting
somebody can flip.

THE THREE CLASSES.  ``self`` = the operator's own estate; they are the
authority root over it.  ``employer`` = an estate their employer owns and the
operator merely has a seat in.  ``third_party`` = someone else's entirely — a
client, a customer, a counterparty.  The split that matters is
``self`` versus the rest: the moment a source is not the operator's, an act
against it is an act the operator cannot authorize alone.

REFUSE, NEVER DEFAULT.  A source the operator cannot classify is refused, not
quietly filed under the safest-looking class.  A default is the cabinet making
the authorization call after all, and a wrong-but-plausible default ("probably
mine") is exactly the failure this plane exists to stop.  Both directions are
refusals with a code and a reason, and every refusal is recordable.

STRUCTURAL, NOT CONFIGURABLE.  ``writes_permitted`` is a function of the class
alone.  There is no override argument, no environment variable and no config
key that turns a write back on for a non-owned source, because a flag that can
be set is a flag that gets set — usually by the component with the least
context.  Callers that need a write path for a non-owned source do not get one;
they get :class:`OwnershipRefusal`.

THE INGEST CEILING.  Egress has had a ceiling for a long time; ingest has not,
even though a connector sweep is the largest read this system will ever do.
:func:`open_ingest` is that ceiling, and it is deliberately HARDER than the
egress gate: egress asks for per-item approval on non-owned content, ingest
refuses outright until the source is classified and its authority basis is
recorded.

WHAT THIS CANNOT ENFORCE — say it plainly, here and in the docs.  The
framework cannot verify that an attestation is TRUE.  Nothing stops an
operator from classifying an employer's tracker as ``self``.  What it can do
is force the question per source, refuse to proceed without an answer, record
the answer and its basis where the record survives the read, and default
everything not claimed as the operator's own to observe-only and no-egress.
That is the enforceable boundary; claiming more of it would be the same kind
of false comfort as a default.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

OWNERSHIP_SELF = "self"
OWNERSHIP_EMPLOYER = "employer"
OWNERSHIP_THIRD_PARTY = "third_party"

#: The closed class set, in escalating distance from the operator.
OWNERSHIP_CLASSES: tuple[str, ...] = (
    OWNERSHIP_SELF,
    OWNERSHIP_EMPLOYER,
    OWNERSHIP_THIRD_PARTY,
)

#: Everything that is not the operator's own estate.  Derived, never a second
#: hand-maintained list: a fourth class added above is non-owned by default,
#: which is the safe direction for a set that will grow.
NON_OWNED_CLASSES = frozenset(OWNERSHIP_CLASSES) - {OWNERSHIP_SELF}

#: Words an operator plausibly types when they have not actually decided.
#: They are REFUSED rather than mapped, and they carry their own code so the
#: refusal message can say "you have not answered yet" instead of "invalid".
UNDECIDED_TOKENS = frozenset({
    "", "unknown", "unclassified", "unsure", "not_sure", "not sure", "n/a",
    "na", "none", "tbd", "?",
})

MAX_AUTHORITY_BASIS_CHARS = 300

EGRESS_ALLOW = "allow"
EGRESS_RECORD_AND_ALLOW = "record_and_allow"
EGRESS_PER_ITEM_APPROVAL = "per_item_approval"

#: Egress is GRADED, and writes are not. A write to a non-owned system is
#: refused whatever the class, because it changes someone else's record. Egress
#: splits: showing an employee their own view of their employer's repo is the
#: whole product at that altitude, and refusing it would be safety theatre that
#: costs the feature — so `employer` content moves with a RECORD. `third_party`
#: content is a different thing entirely: a client's or customer's data leaving
#: on a channel the operator's counterparty never agreed to is the exposure the
#: adjudication names, so it needs its own approval per item.
EGRESS_BY_CLASS = {
    OWNERSHIP_SELF: EGRESS_ALLOW,
    OWNERSHIP_EMPLOYER: EGRESS_RECORD_AND_ALLOW,
    OWNERSHIP_THIRD_PARTY: EGRESS_PER_ITEM_APPROVAL,
}

ATTESTATION_LIMIT = (
    "The framework cannot verify that this attestation is true. It forces the "
    "question per source, refuses an unclassified source, records the answer "
    "and its basis where the record survives the read, and defaults every "
    "source not claimed as the operator's own to observe-only and no-egress."
)


class OwnershipRefusal(RuntimeError):
    """A refusal carrying a stable machine ``code`` and an operator-readable reason.

    Every refusal in this module raises this type.  Silent skips destroy
    auditability, so a refusal is always something a caller can catch, record
    and show — never a ``None`` return that a caller can read as consent.
    """

    def __init__(self, code: str, message: str, *, detail: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.detail = dict(detail or {})


def require_ownership(raw: Any) -> str:
    """Return the declared class, or refuse.

    Refuses ``None``, a non-string, an undecided token and any string outside
    the closed set.  There is no default branch by construction: every path out
    of this function is either a member of :data:`OWNERSHIP_CLASSES` or a
    raise.
    """
    if raw is None or not isinstance(raw, str) or raw.strip().lower() in UNDECIDED_TOKENS:
        raise OwnershipRefusal(
            "ownership_unclassified",
            "Tell me whose data this is before I read it: mine, my employer's, "
            "or someone else's. I will not guess.",
            detail={"accepted": list(OWNERSHIP_CLASSES)},
        )
    value = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if value not in OWNERSHIP_CLASSES:
        raise OwnershipRefusal(
            "ownership_class_unknown",
            f"{raw!r} is not an ownership class I understand.",
            detail={"accepted": list(OWNERSHIP_CLASSES)},
        )
    return value


def require_authority_basis(raw: Any) -> str:
    """Return the recorded authority basis, or refuse.

    Required for EVERY class, the operator's own included: "it is my laptop" is
    a basis, and writing it down is what makes the record reviewable later.  A
    class without a basis is a claim without a reason, which is the shape of
    an answer given to make a prompt go away.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise OwnershipRefusal(
            "authority_basis_required",
            "Say under what right you are connecting this source (for example: "
            "my own machine; my employer's tracker, read access granted to my "
            "seat; a client's shared drive under our engagement).",
        )
    basis = " ".join(raw.split())
    if len(basis) > MAX_AUTHORITY_BASIS_CHARS:
        raise OwnershipRefusal(
            "authority_basis_too_long",
            f"Keep the authority basis under {MAX_AUTHORITY_BASIS_CHARS} characters.",
        )
    return basis


def writes_permitted(ownership: str) -> bool:
    """True only for the operator's own estate.

    No override parameter, deliberately.  This is the whole structural claim:
    a caller cannot ask for a write against a non-owned source in a way this
    function can say yes to.
    """
    return require_ownership(ownership) == OWNERSHIP_SELF


def require_write_permitted(ownership: str, *, operation: str) -> None:
    """Raise unless the source is the operator's own."""
    declared = require_ownership(ownership)
    if declared == OWNERSHIP_SELF:
        return
    raise OwnershipRefusal(
        "write_refused_non_owned",
        f"{operation} would write to a source classified {declared!r}. Writes "
        "to a source the operator does not own are refused structurally, not "
        "by configuration.",
        detail={"ownership": declared, "operation": operation},
    )


def egress_disposition(ownership: str) -> str:
    """How content from a source of this class may leave — see :data:`EGRESS_BY_CLASS`.

    A class absent from the table would be a silent allow, so the lookup is a
    strict one: an unmapped member raises rather than defaulting.
    """
    declared = require_ownership(ownership)
    try:
        return EGRESS_BY_CLASS[declared]
    except KeyError as exc:  # pragma: no cover — guards a future class addition
        raise OwnershipRefusal(
            "egress_disposition_undeclared",
            f"ownership class {declared!r} has no declared egress disposition; "
            "add one to EGRESS_BY_CLASS rather than letting it default to allow.",
        ) from exc


def source_permissions(ownership: str) -> dict[str, Any]:
    """The permission block a charter records for a source of this class.

    Derived from the class every time it is asked rather than stored, so a
    charter cannot carry a permission block that disagrees with its own
    ownership field.
    """
    declared = require_ownership(ownership)
    owned = declared == OWNERSHIP_SELF
    return {
        "read_only": True,
        "writes_to_source": False,
        "write_capable_adapters": "allowed" if owned else "refused",
        "egress": egress_disposition(declared),
        "structural": True,
    }


def attestation(
    ownership: str,
    authority_basis: str,
    *,
    attested_at: str,
    attested_by: str = "captain",
) -> dict[str, Any]:
    """The recorded attestation, including the honest limit on what it proves."""
    return {
        "ownership": require_ownership(ownership),
        "authority_basis": require_authority_basis(authority_basis),
        "attested_at": attested_at,
        "attested_by": attested_by,
        "verified_by_framework": False,
        "limit": ATTESTATION_LIMIT,
    }


def open_ingest(
    raw_ownership: Any,
    raw_authority_basis: Any,
    *,
    attested_at: str,
    attested_by: str = "captain",
) -> dict[str, Any]:
    """THE INGEST CEILING — classify a source or do not read it at all.

    Harder than the egress gate on purpose.  Egress lets non-owned content
    through with a per-item approval; ingest refuses to start until the class
    and the basis are on record, because the sweep is the largest read this
    system will ever do and a read cannot be taken back.
    """
    declared = require_ownership(raw_ownership)
    basis = require_authority_basis(raw_authority_basis)
    return {
        "ownership": declared,
        "authority_basis": basis,
        "permissions": source_permissions(declared),
        "attestation": attestation(
            declared, basis, attested_at=attested_at, attested_by=attested_by
        ),
    }


def screen_egress(
    items: Sequence[Mapping[str, Any]],
    *,
    approved_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Split outbound items into what may leave and what is refused.

    An item is a mapping carrying at least ``id`` and ``ownership``.  A MISSING
    or unrecognized ownership refuses — the degenerate end of this function is
    a refusal, not a pass, because "no class recorded" is the state every row
    written before this plane existed is in.

    ``screened`` is returned so a caller cannot read an empty result as an
    approval: zero items screened means nothing was checked, which is a
    different fact from "everything checked was allowed".
    """
    approved = {str(i) for i in approved_ids}
    allowed: list[Mapping[str, Any]] = []
    refused: list[dict[str, Any]] = []
    for item in items:
        item_id = str(item.get("id", ""))
        try:
            declared = require_ownership(item.get("ownership"))
        except OwnershipRefusal as exc:
            refused.append({"id": item_id, "reason": exc.code, "ownership": None})
            continue
        if egress_disposition(declared) != EGRESS_PER_ITEM_APPROVAL or item_id in approved:
            allowed.append(item)
            continue
        refused.append({
            "id": item_id,
            "reason": "egress_refused_without_per_item_approval",
            "ownership": declared,
        })
    return {"screened": len(items), "allowed": allowed, "refused": refused}


def require_egress_allowed(
    items: Sequence[Mapping[str, Any]],
    *,
    approved_ids: Iterable[str] = (),
    channel: str,
) -> list[Mapping[str, Any]]:
    """Return the items that may leave on ``channel``, or refuse the whole send.

    Whole-send refusal rather than a silent filter: dropping the refused items
    and sending the rest would produce a brief that reads complete and is not,
    which is the failure mode this program keeps paying for.
    """
    screened = screen_egress(items, approved_ids=approved_ids)
    if screened["refused"]:
        raise OwnershipRefusal(
            "egress_refused_non_owned",
            f"{len(screened['refused'])} of {screened['screened']} items on "
            f"{channel} are not the operator's to send. Each needs its own "
            "approval, or the source needs reclassifying.",
            detail={"channel": channel, "refused": screened["refused"]},
        )
    return list(screened["allowed"])


# ---------------------------------------------------------------------------
# Sensitivity classes — the categories that get someone fired
# ---------------------------------------------------------------------------
#
# The existing scanner catches CREDENTIALS.  Credentials are not the thing that
# ends a career: personnel files, salary data, customer PII, live legal matters
# and unannounced corporate finance are.  Each is a CLASS with its own refusal
# in the manifest, not one more line in a per-file regex, so a refusal can say
# WHICH category it refused and an operator can see the shape of what was left
# behind.
#
# NAME EVIDENCE ONLY, and deliberately narrow.  These patterns read the path,
# never the contents — content classification is not something this plane can
# honestly claim.  Narrow beats broad here: a detector that fires on ordinary
# documents is turned off within a week, and an off detector refuses nothing.
# So `salary` is a class member and bare `contract` is not, even though a
# contract can be sensitive: precision is what keeps the refusals believable.

SENSITIVITY_CREDENTIALS = "credentials"
SENSITIVITY_PERSONNEL = "personnel"
SENSITIVITY_COMPENSATION = "compensation"
SENSITIVITY_CUSTOMER_PII = "customer_pii"
SENSITIVITY_LEGAL = "legal"
SENSITIVITY_CORPORATE_FINANCE = "corporate_finance"

SENSITIVITY_CLASSES: tuple[str, ...] = (
    SENSITIVITY_CREDENTIALS,
    SENSITIVITY_PERSONNEL,
    SENSITIVITY_COMPENSATION,
    SENSITIVITY_CUSTOMER_PII,
    SENSITIVITY_LEGAL,
    SENSITIVITY_CORPORATE_FINANCE,
)

# The credential detector, unchanged in behaviour from the First Window
# scanner that has always carried it — moved here so the whole sensitivity
# vocabulary has ONE home rather than two that can drift apart.
SENSITIVE_NAME_RE = re.compile(
    r"(^|[._-])(\.env|secret|secrets|credential|credentials|token|tokens|"
    r"private[-_]?key|id_rsa|id_ed25519)([._-]|$)", re.I
)
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore"}

_BOUND = r"(?:^|[/._\-\s])"
_ENDS = r"(?:[/._\-\s]|$)"


def _tokens(*alternatives: str) -> re.Pattern[str]:
    return re.compile(_BOUND + "(?:" + "|".join(alternatives) + ")" + _ENDS, re.I)


#: class -> path-name pattern.  Credentials are matched by the historical
#: detector above instead, so they are absent here and handled in
#: :func:`sensitivity_classes`.
SENSITIVITY_PATTERNS: dict[str, re.Pattern[str]] = {
    SENSITIVITY_PERSONNEL: _tokens(
        "personnel", "employee[-_]?(?:file|files|record|records|data)",
        "staff[-_]?(?:file|files|record|records)", "performance[-_]?review",
        "disciplinary", "grievance", "termination[-_]?letter", "hr",
    ),
    SENSITIVITY_COMPENSATION: _tokens(
        "salary", "salaries", "payroll", "compensation", "remuneration",
        "severance", "bonus[-_]?(?:plan|pool|letter)", "equity[-_]?grant",
        "stock[-_]?option", "stock[-_]?options",
    ),
    SENSITIVITY_CUSTOMER_PII: _tokens(
        "pii", "gdpr", "dsar", "subject[-_]?access", "personal[-_]?data",
        "customer[-_]?(?:list|lists|export|records|database)", "cardholder",
        "passport", "ssn", "national[-_]?id",
    ),
    SENSITIVITY_LEGAL: _tokens(
        "litigation", "lawsuit", "subpoena", "nda", "non[-_]?disclosure",
        "settlement[-_]?agreement", "legal[-_]?hold", "privileged",
        "counsel[-_]?memo",
    ),
    SENSITIVITY_CORPORATE_FINANCE: _tokens(
        "merger", "acquisition", "due[-_]?diligence", "term[-_]?sheet",
        "cap[-_]?table", "board[-_]?(?:deck|minutes|pack)", "valuation",
    ),
}


def sensitivity_classes(rel_path: str) -> tuple[str, ...]:
    """Every sensitivity class the path NAME places this file in.

    A path with no evidence returns an empty tuple.  The empty tuple means "no
    class matched", never "checked and safe" — callers phrase their refusal
    records accordingly.
    """
    text = str(rel_path or "")
    if not text:
        return ()
    found: list[str] = []
    lowered = text.lower()
    if (
        SENSITIVE_NAME_RE.search(text)
        or any(SENSITIVE_NAME_RE.search(part) for part in text.split("/"))
        or any(lowered.endswith(suffix) for suffix in SENSITIVE_SUFFIXES)
    ):
        found.append(SENSITIVITY_CREDENTIALS)
    for name in SENSITIVITY_CLASSES:
        pattern = SENSITIVITY_PATTERNS.get(name)
        if pattern is not None and pattern.search(text):
            found.append(name)
    return tuple(found)


def sensitivity_refusal(rel_path: str) -> str | None:
    """The class to refuse this path under, or ``None`` when nothing matched.

    First match in :data:`SENSITIVITY_CLASSES` order, so a file that is both a
    credential and a personnel record refuses under the sharper class and the
    reason stays stable across runs.
    """
    classes = sensitivity_classes(rel_path)
    return classes[0] if classes else None


def access_record(
    *,
    schema: str,
    source_root: str,
    ownership: str,
    authority_basis: str,
    charter_hash: str,
    manifest_hash: str,
    entry_count: int,
    refusals: Mapping[str, int],
    retention: str,
    recorded_at: str,
    purge_receipt: str | None = None,
) -> dict[str, Any]:
    """The per-source sweep record that must SURVIVE the read it describes.

    Carries what a later reviewer needs to answer "what did this thing read,
    whose was it, under what right, and what did it refuse" — and carries the
    refusals by class WITH counts, because a silent skip is indistinguishable
    from a file that was never there.  Content-free by construction: hashes and
    counts, never excerpts, so keeping it after a purge does not keep the data.
    """
    return {
        "schema": schema,
        "source_root": source_root,
        "ownership": require_ownership(ownership),
        "authority_basis": require_authority_basis(authority_basis),
        "charter_hash": charter_hash,
        "manifest_hash": manifest_hash,
        "entry_count": int(entry_count),
        "refusals": {str(k): int(v) for k, v in sorted(refusals.items())},
        "refusals_total": sum(int(v) for v in refusals.values()),
        "retention": retention,
        "recorded_at": recorded_at,
        "purge_receipt": purge_receipt,
        "attestation_limit": ATTESTATION_LIMIT,
    }
