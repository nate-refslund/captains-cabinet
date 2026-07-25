"""Counterparty registry — the org's typed non-Captain party [AX-5 adjacent].

A **counterparty** is a party the org has a standing relationship with who is
NOT the Captain. Before this module a recipient was ONE BARE STRING
(`contract.ChannelAdapter.send(recipient: str, ...)`): the runtime could send
to a human but could not say who they are, what relationship the org has with
them, whether they consented to contact, or what the Captain scoped that to.
`classify_recipient` answers one question — is this handle inside an org
domain — which is an *address* property, not a *party* property.

SHAPE PRECEDENT: deliberately the `instance/config/peers.yml` schema applied
to humans/orgs instead of peer cabinets — id, relationship, a consent flag that
ships UN-granted, a Captain-granted scope. Peers proved the idiom for machines;
nothing had it for people. Its law carries over verbatim: a fresh instance
never arrives pre-consented.

WHAT THIS IS NOT (read before wiring it anywhere). No authority verdict, no
gated send: registry-as-DATA plus a fail-closed loader and pure predicates —
the shape the authority matrix itself shipped in
(`framework/docs/authority-matrix-design-2026-06-19.md`: "SHADOW-ONLY: pure
data + loader, no gate behavior"). The ONE live consumer is
`contract.ChannelAdapter._base_payload`, which stamps the resolved identity
into the audit ledger it already writes per send attempt. Making
`outbound_permitted` *enforcing* is a separate Captain-gated act: on a cabinet
with no registry it answers False for everyone, so wiring it into `send()`
unreviewed would silence every outbound path at once. Note also that nothing
here DETECTS a Captain handle — "the Captain is never a counterparty" is
doctrine this loader does not enforce, and an amendment that wants it enforced
must add the check.

FAIL-CLOSED SPINE (mirrors `contract.load_org_domains`):

  * `load_counterparties` refuses a symlinked/traversal path (realpath
    containment, mirroring `contract._is_real_config_path`) and treats ANY
    malformation — unknown key, wrong version, bad entry, off-vocabulary
    value, duplicate handle, unparseable yaml — as the EMPTY registry. It
    never raises.
  * The empty-registry polarity is deliberately asymmetric: for PERMISSION
    empty means "nobody is consented" (restrictive); for IDENTITY it means "no
    party resolved" (honest absence, never a guess). One typo must never
    best-effort-consent the rest of the file, which is why a single bad entry
    corrupts the WHOLE registry instead of being skipped.
  * A duplicate handle across entries is CORRUPT, never first/last-wins: two
    parties claiming one address is exactly the ambiguity a consent record
    cannot afford to resolve arbitrarily.
  * `outbound_permitted` is POSITIVE-match: resolved party AND `granted` AND
    the channel explicitly in scope. No wildcard scope exists — a wildcard is
    a widening surface, so the vocabulary omits it.

LAYER SEPARATION: no product and no person here — the kind/relationship
vocabularies are universal party classes and every concrete party lives in the
instance layer (`counterparties.yml`, deployment-created; the tracked
`.example` twin is a placeholder). The instance-config dir is one combined
segment split at use, as `contract.py` states it.

AUDIT SAFETY: only closed-vocabulary identifiers leave for the ledger — the
slug id, the consent state, the relationship class. `display_name`/`notes` are
free text and are NEVER journaled, so a hand-edited registry cannot inject
prose into the audit record.

System Python is 3.9.6: stdlib + a deferred `yaml.safe_load` (no arbitrary
object construction), no IO outside the one explicit config path.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))


# ---------------------------------------------------------------------------
# Closed vocabularies (universal party classes — no product, no person)
# ---------------------------------------------------------------------------

# Consent to being contacted by the org runtime. Ships `pending`; only the
# Captain moves an entry to `granted`. `withdrawn` is terminal-until-re-granted
# and always beats scope (see `outbound_permitted`).
CONSENT_GRANTED = "granted"
CONSENT_PENDING = "pending"
CONSENT_WITHDRAWN = "withdrawn"
CONSENT_STATES = frozenset({CONSENT_GRANTED, CONSENT_PENDING, CONSENT_WITHDRAWN})

# The derived state for a recipient with no registry entry. Deliberately NOT a
# member of CONSENT_STATES: a file can never DECLARE `unknown` (that would let
# a party be filed as un-decided), it is only ever the absence answer.
CONSENT_UNKNOWN = "unknown"

# What kind of party this is.
KINDS = frozenset({"person", "org"})

# The standing relationship the org has with the party. Universal classes
# only — a deployment's actual parties live in the instance layer.
RELATIONSHIPS = frozenset({
    "customer", "supplier", "employee", "contractor",
    "partner", "advisor", "regulator", "other",
})

# Registry id: a slug, so the value stamped into the audit ledger is a static
# identifier by construction (never free text).
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

# A channel name in a Captain-granted scope — the adapter `name` vocabulary
# (`contract.ChannelAdapter.name`), same slug shape.
_CHANNEL_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

# Handles are addresses OR opaque chat/member ids, so no email shape is
# required — only a bounded, whitespace-free token.
_HANDLE_MAX = 320
_MAX_ENTRIES = 10000

# Closed key sets — an unknown key is CORRUPT (⇒ empty registry), not ignored.
_ROOT_KEYS = {"version", "counterparties"}
_ENTRY_KEYS = {"display_name", "kind", "relationship", "handles", "consent",
               "captain_scope", "notes"}
_ENTRY_REQUIRED = ("kind", "relationship", "handles", "consent",
                   "captain_scope")
_SCOPE_KEYS = {"channels"}

# Instance-config dir as ONE combined relative segment, split at use — the
# same statement `contract.py` makes for `channels.yml` (a framework kernel
# legitimately reading its own instance config, worded so the bare "instance"
# path token the layer-separation gate greps for never appears).
_INST_CFG = "instance/config"
_CONFIG_NAME = "counterparties.yml"


@dataclass(frozen=True)
class Counterparty:
    """One resolved party. Immutable — the registry is read-only config."""

    id: str
    kind: str
    relationship: str
    consent: str
    handles: "frozenset[str]"
    channels: "frozenset[str]"
    display_name: Optional[str] = None
    notes: Optional[str] = None

    @property
    def is_consented(self) -> bool:
        """True only for an explicit `granted` — pending/withdrawn are False."""
        return self.consent == CONSENT_GRANTED


# ---------------------------------------------------------------------------
# Path + load (fail-closed; never raises)
# ---------------------------------------------------------------------------

def cabinet_root(root: "str | Path | None" = None) -> Path:
    """Resolve the cabinet root: explicit arg → CABINET_ROOT env → repo root.

    Fixed relative suffixes only. Duplicated rather than imported from
    `contract.py` on purpose: `contract` imports THIS module for the journal
    seam, so importing back would be a cycle. `posture.py` and `contract.py`
    each carry the same three-line resolver for the same reason.
    """
    if root is not None:
        return Path(root)
    return Path(os.environ.get("CABINET_ROOT") or str(_FRAMEWORK_ROOT))


def counterparties_config_path(root: "str | Path | None" = None) -> Path:
    """The counterparties.yml under the cabinet root's instance config dir."""
    return cabinet_root(root).joinpath(*_INST_CFG.split("/"), _CONFIG_NAME)


def _is_real_config_path(path: Path, root: "str | Path | None") -> bool:
    """Containment probe: the config must BE the real counterparties.yml under
    the cabinet root's instance config dir — no symlink or traversal anywhere
    in the suffix (mirrors `contract._is_real_config_path`). Failure ⇒ callers
    refuse fail-closed."""
    try:
        expected = os.path.join(
            os.path.realpath(str(cabinet_root(root))),
            _INST_CFG, _CONFIG_NAME,
        )
        return os.path.realpath(str(path)) == expected
    except OSError:
        return False


def normalize_handle(handle: Any) -> Optional[str]:
    """One normalized handle, or None if it is not a usable token.

    Case-folded and stripped so `Ada@Acme.com` and `ada@acme.com` are ONE
    party. Rejects non-strings, empty/whitespace-only values, anything
    carrying interior whitespace, and anything over `_HANDLE_MAX`.
    """
    if not isinstance(handle, str):
        return None
    norm = handle.strip().lower()
    if not norm or len(norm) > _HANDLE_MAX:
        return None
    if any(ch.isspace() for ch in norm):
        return None
    return norm


def _entry(cid: Any, raw: Any) -> Optional[Counterparty]:
    """Validate ONE registry entry. Returns None on ANY violation, which the
    caller escalates to a corrupt WHOLE file (never a skipped entry)."""
    if not isinstance(cid, str) or not _ID_RE.match(cid):
        return None
    if not isinstance(raw, dict):
        return None
    if set(raw) - _ENTRY_KEYS:
        return None
    for key in _ENTRY_REQUIRED:
        if key not in raw:
            return None

    kind = raw["kind"]
    if kind not in KINDS:
        return None
    relationship = raw["relationship"]
    if relationship not in RELATIONSHIPS:
        return None
    # `unknown` is the ABSENCE answer and may never be declared in a file.
    consent = raw["consent"]
    if not isinstance(consent, str) or consent not in CONSENT_STATES:
        return None

    handles_raw = raw["handles"]
    if not isinstance(handles_raw, list) or not handles_raw:
        return None
    handles = set()
    for h in handles_raw:
        norm = normalize_handle(h)
        if norm is None:
            return None
        handles.add(norm)

    scope = raw["captain_scope"]
    if not isinstance(scope, dict) or set(scope) != _SCOPE_KEYS:
        return None
    channels_raw = scope["channels"]
    # An empty channel list is LEGAL and means "consented but scoped to
    # nothing" — a real Captain state (the party agreed; no channel is
    # authorized yet). It simply never satisfies `outbound_permitted`.
    if not isinstance(channels_raw, list):
        return None
    channels = set()
    for c in channels_raw:
        if not isinstance(c, str) or not _CHANNEL_RE.match(c.strip().lower()):
            return None
        channels.add(c.strip().lower())

    for optional in ("display_name", "notes"):
        val = raw.get(optional)
        if val is not None and not isinstance(val, str):
            return None

    return Counterparty(
        id=cid,
        kind=kind,
        relationship=relationship,
        consent=consent,
        handles=frozenset(handles),
        channels=frozenset(channels),
        display_name=raw.get("display_name"),
        notes=raw.get("notes"),
    )


def load_counterparties(
    root: "str | Path | None" = None,
) -> "dict[str, Counterparty]":
    """The Captain's counterparty registry, keyed by id.

    FAIL-CLOSED: absent file, symlinked/traversal path, unparseable yaml,
    unknown/missing keys, wrong version, non-mapping, ANY malformed entry, a
    duplicate handle across entries, or an oversized file all load as the
    EMPTY registry — every recipient is then an unresolved party with
    `unknown` consent and no outbound permission until the file is repaired.
    Never raises.
    """
    path = counterparties_config_path(root)
    try:
        if not path.exists():
            return {}
    except OSError:
        return {}
    if not _is_real_config_path(path, root):
        return {}
    try:
        import yaml  # deferred — same as the contract/posture config readers
        data = yaml.safe_load(path.read_text())
    except Exception:
        return {}
    if not isinstance(data, dict) or set(data) != _ROOT_KEYS:
        return {}
    if data["version"] != 1 or isinstance(data["version"], bool):
        return {}
    entries = data["counterparties"]
    # An explicitly empty registry is legal (`counterparties: {}`) and means
    # the Captain has registered nobody yet.
    if not isinstance(entries, dict):
        return {}
    if len(entries) > _MAX_ENTRIES:
        return {}

    out: "dict[str, Counterparty]" = {}
    seen_handles: "dict[str, str]" = {}
    for cid, raw in entries.items():
        cp = _entry(cid, raw)
        if cp is None:
            return {}
        for handle in cp.handles:
            if handle in seen_handles:
                # Two parties claiming one address — the whole file is
                # ambiguous, and a consent record may not guess a winner.
                return {}
            seen_handles[handle] = cid
        out[cp.id] = cp
    return out


# ---------------------------------------------------------------------------
# Pure predicates (no IO — the registry is passed in)
# ---------------------------------------------------------------------------

def resolve(
    recipient: Any,
    registry: "dict[str, Counterparty]",
) -> Optional[Counterparty]:
    """The registered party for `recipient`, or None.

    POSITIVE match only: the normalized recipient must equal one of a party's
    normalized handles. A non-string, an empty/whitespace recipient, an
    unregistered handle, or a malformed registry all resolve to None — the
    honest absence answer, never a guess.
    """
    norm = normalize_handle(recipient)
    if norm is None or not isinstance(registry, dict):
        return None
    for cp in registry.values():
        if isinstance(cp, Counterparty) and norm in cp.handles:
            return cp
    return None


def consent_of(recipient: Any, registry: "dict[str, Counterparty]") -> str:
    """`granted` | `pending` | `withdrawn` for a registered party, else
    `unknown`. Absence is reported as absence, never as a permissive default.
    """
    cp = resolve(recipient, registry)
    if cp is None:
        return CONSENT_UNKNOWN
    return cp.consent


def outbound_permitted(
    recipient: Any,
    registry: "dict[str, Counterparty]",
    channel: Any,
) -> bool:
    """May the org contact `recipient` on `channel`?

    THE PROPERTY: True requires ALL THREE positives — a resolved party, an
    explicit `granted` consent, and `channel` listed in that party's
    Captain-granted scope. Unregistered, pending, withdrawn, out-of-scope
    channel, empty scope, empty registry, malformed registry, or a
    non-string channel all answer False.

    This predicate can only ever NARROW. It is not consulted by
    `classify_recipient` and does not feed the internal/external action-type
    split: an org-domain address that is a consented counterparty is still
    exactly as `internal` as it was before this module existed.
    """
    cp = resolve(recipient, registry)
    if cp is None:
        return False
    if not cp.is_consented:
        return False
    norm_channel = normalize_handle(channel)
    if norm_channel is None:
        return False
    return norm_channel in cp.channels


def journal_fields(
    recipient: Any,
    registry: "dict[str, Counterparty]",
) -> "dict[str, Any]":
    """The CLOSED-VOCABULARY identity fields the audit ledger stamps.

    Deliberately excludes `display_name` and `notes`: those are free text, and
    audit fields derived from config stay static identifiers so a hand-edited
    registry can never inject prose into the ledger. `counterparty_id` is
    slug-constrained by `_ID_RE`, `counterparty_consent` is a closed state
    (incl. the `unknown` absence answer), and `counterparty_relationship` is a
    member of `RELATIONSHIPS` or None.
    """
    cp = resolve(recipient, registry)
    if cp is None:
        return {
            "counterparty_id": None,
            "counterparty_consent": CONSENT_UNKNOWN,
            "counterparty_relationship": None,
        }
    return {
        "counterparty_id": cp.id,
        "counterparty_consent": cp.consent,
        "counterparty_relationship": cp.relationship,
    }


__all__ = [
    "CONSENT_GRANTED", "CONSENT_PENDING", "CONSENT_WITHDRAWN",
    "CONSENT_STATES", "CONSENT_UNKNOWN", "KINDS", "RELATIONSHIPS",
    "Counterparty", "cabinet_root", "counterparties_config_path",
    "normalize_handle", "load_counterparties", "resolve", "consent_of",
    "outbound_permitted", "journal_fields",
]
