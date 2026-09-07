"""THE TAP — one proposed card becomes a ratified responsibility.

ONE WRITER, THREE DOORS. Ratification used to be a sentence in a file header
telling the operator to open a YAML file and move a row by hand, which is a
no-terminal-law violation and the reason a Cabinet could propose work it could
never be given. This module is the only code that writes the two outcome
files; every door (terminal, web, chat) calls ``ratify()`` and none of them
composes YAML of its own. That is checkable, and it is checked.

WHAT A TAP DOES, in one lock:

  * validate the row's PROJECTION against ``framework/schemas/outcome.schema.json``
    — the projection, not the row, because a real genesis row carries
    ``what``/``why``/``lane``/``derived_from``/``proposed_by``/``proof_expected``/
    ``proposed_digest`` and the schema's item is ``additionalProperties: false``.
    Validating the whole row would refuse every card the org has ever
    proposed. The projection is the schema's own item key set, so the check
    cannot drift away from the schema it names;
  * COPY the row into the live outcomes file with ``status: active``, and
  * MARK the proposed row ``status: ratified`` — never delete it. The proposal
    is the record of what was asked for; the copy is what the org agreed to;
  * emit ``captain_outcome_ratified`` with the door and the principal.

ATTRIBUTION IS NOT AUTHENTICATION. The terminal door runs as the same uid as
every officer, so a terminal tap is recorded as ``operator`` — never
``captain``. Only the web and chat doors, which authenticate a session or a
verified sender, carry the ``captain`` actor. That distinction is the whole
value of the record: a ledger that calls every act "captain" records nothing.

WHAT THIS MUST NOT DO. It does not compile, route, assign or start anything;
it never edits ``measurable_criteria``; it never writes a ``deployment`` key
(an absent gate compiles everywhere, which is what a freshly ratified outcome
wants); and it names no product, person or vendor — the door kinds are
``terminal | web | chat`` and the adapter's name, if any, rides in
``principal``.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from framework.onboarding import genesis

#: The LIVE mission file — the only outcomes file the compiler reads.
OUTCOMES_REL = "instance/config/outcomes.yml"
#: Cross-process mutex for the read+write+emit critical section.
LOCK_REL = "instance/config/.outcomes.lock"

#: The doors, agnostic by construction. A vendor noun never enters this module
#: or the ledger; which adapter carried a chat tap rides in ``principal``.
DOORS = ("terminal", "web", "chat")

#: Doors that AUTHENTICATE the Captain (a session cookie, a verified sender).
#: The terminal door is attribution only — same uid as every officer.
_CAPTAIN_DOORS = frozenset({"web", "chat"})
ACTOR_CAPTAIN = "captain"
ACTOR_OPERATOR = "operator"

EVENT_TYPE = "captain_outcome_ratified"

#: Exit codes for the terminal door.
EXIT_OK = 0
EXIT_NOT_FOUND = 3
EXIT_INVALID_ROW = 4
EXIT_REFUSED = 5

#: Keys the tap stamps on the copied row.
RATIFIED_BY_KEY = "ratified_by"
RATIFIED_VIA_KEY = "ratified_via"
RATIFIED_AT_KEY = "ratified_at"
RATIFIED_FROM_DIGEST_KEY = "ratified_from_digest"
EDITED_SINCE_PROPOSED_KEY = "edited_since_proposed"

_OUTCOMES_HEADER = """\
# instance/config/outcomes.yml — the LIVE mission file.
#
# The mission compiler reads THIS file by name and compiles every row with
# status: active. Rows arrive here one way: a Captain tap on a proposed card
# (framework/outcomes/ratify.py), which copies the row, stamps who ratified it
# through which door, and marks the proposal ratified rather than deleting it.
"""


class RatifyError(Exception):
    """A refusal that carries its status word, so every door reports the same
    four outcomes rather than each inventing its own."""

    def __init__(self, status: str, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


# ---------------------------------------------------------------------------
# Schema projection — see the module docstring for why this is a projection.
# ---------------------------------------------------------------------------
def _schema_path() -> Path:
    """The framework's own outcome schema, resolved against THIS package.

    Deliberately not resolved against the deployment root: the schema is code
    that ships with the framework, and a scratch root carrying only an
    instance overlay must still validate.
    """
    return Path(__file__).resolve().parents[1] / "schemas" / "outcome.schema.json"


def _load_schema() -> dict:
    try:
        data = json.loads(_schema_path().read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _item_schema(schema: dict) -> dict:
    try:
        item = schema["properties"]["outcomes"]["items"]
    except Exception:
        return {}
    return item if isinstance(item, dict) else {}


def schema_item_keys() -> frozenset:
    """The schema's outcome-item key set — the projection's definition.

    Read out of the schema document rather than written down here, so adding a
    key to the schema widens the projection in the same commit and the two can
    never disagree.
    """
    props = _item_schema(_load_schema()).get("properties")
    return frozenset(props.keys()) if isinstance(props, dict) else frozenset()


def projection(row: dict) -> dict:
    """The part of a proposal row the outcome schema describes."""
    keys = schema_item_keys()
    return {k: v for k, v in row.items() if k in keys}


def _minimal_validate(item: dict) -> None:
    """Same required keys, types and enums as the schema, with no dependency.

    The house pattern (framework/attention/charter.py): jsonschema when it is
    importable, this when it is not — never a silent pass. ``validated_by`` in
    the result says which ran, so a degraded validator can never be mistaken
    for the authoritative one.
    """
    item_schema = _item_schema(_load_schema())
    required = item_schema.get("required") or ["id", "name", "measurable_criteria"]
    for key in required:
        if key not in item:
            raise RatifyError("invalid_row", "row is missing required key '%s'" % key)
    if not isinstance(item.get("id"), str) or not item["id"]:
        raise RatifyError("invalid_row", "row 'id' must be a non-empty string")
    if not isinstance(item.get("name"), str) or not item["name"]:
        raise RatifyError("invalid_row", "row 'name' must be a non-empty string")
    criteria = item.get("measurable_criteria")
    if not isinstance(criteria, list) or not criteria:
        raise RatifyError(
            "invalid_row", "row 'measurable_criteria' must be a non-empty list")
    status_enum = ((item_schema.get("properties") or {}).get("status") or {}).get("enum")
    if status_enum and item.get("status") is not None and item["status"] not in status_enum:
        raise RatifyError("invalid_row", "row 'status' is not one of %s" % (status_enum,))


def validate_projection(row: dict) -> str:
    """Validate the row's projection; raise ``RatifyError('invalid_row', …)``.

    Returns the validator that actually ran ('jsonschema' | 'minimal')."""
    item = projection(row)
    schema = _load_schema()
    try:
        import jsonschema  # type: ignore
    except Exception:
        _minimal_validate(item)
        return "minimal"
    if not schema:
        _minimal_validate(item)
        return "minimal"
    try:
        jsonschema.validate({"outcomes": [item]}, schema)
    except Exception as exc:
        message = getattr(exc, "message", None) or str(exc)
        raise RatifyError("invalid_row", "schema violation: %s" % message) from exc
    return "jsonschema"


# ---------------------------------------------------------------------------
# Roots, locks, files.
# ---------------------------------------------------------------------------
def _base(root: Optional[Path]) -> Path:
    return Path(root) if root else genesis.cabinet_root()


def _is_repo_root(base: Path) -> bool:
    """True when this root is a git worktree.

    The live checkout's ``instance/config/outcomes.yml`` is TRACKED, so a tap
    against the repo would commit a deployment's mission state into source
    control and hand it to every other checkout that pulls the branch. A tap
    there is almost always a mis-pointed CABINET_ROOT; ``--allow-repo`` is the
    one place someone says otherwise, out loud.
    """
    return (base / ".git").exists()


def _leading_comment_block(raw: str, default: str) -> str:
    """The file's existing leading comment block, so an operator's own note
    survives a rewrite; ``default`` when the file carries none."""
    head: List[str] = []
    for line in raw.splitlines():
        if line.startswith("#") or not line.strip():
            head.append(line)
        else:
            break
    if any(ln.startswith("#") for ln in head):
        return "\n".join(head).strip() + "\n"
    return default


def _dump(doc: dict) -> str:
    import yaml  # local: keep the module import-light

    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)


def _load_doc(path: Path) -> Tuple[dict, str]:
    """(parsed doc, raw text). An unreadable or non-mapping file raises."""
    if not path.exists():
        return {}, ""
    import yaml  # local: keep the module import-light

    raw = path.read_text(encoding="utf-8")
    try:
        doc = yaml.safe_load(raw)
    except Exception as exc:
        raise RatifyError("invalid_row", "%s does not parse: %s" % (path.name, exc))
    if doc is None:
        doc = {}
    if not isinstance(doc, dict):
        raise RatifyError("invalid_row", "%s is not a mapping" % path.name)
    return doc, raw


# ---------------------------------------------------------------------------
# The read model the doors render.
# ---------------------------------------------------------------------------
def list_ratifiable(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Every proposed card a tap could ratify, newest file order preserved."""
    doc = genesis.load_proposals_doc(_base(root))
    rows = doc.get("outcomes")
    out: List[Dict[str, Any]] = []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("captain_ratified") or row.get("status") != "draft":
            continue
        out.append({
            "id": str(row.get("id") or ""),
            "name": str(row.get("name") or ""),
            "what": str(row.get("what") or ""),
            "why": str(row.get("why") or ""),
            "proof_expected": str(row.get("proof_expected") or ""),
            "proposed_digest": str(row.get(genesis.ROW_DIGEST_KEY) or ""),
        })
    return out


# ---------------------------------------------------------------------------
# The tap.
# ---------------------------------------------------------------------------
def actor_for(door: str) -> str:
    """The literal actor a door may claim.

    A terminal tap runs as the officer uid; calling it ``captain`` would be a
    claim the door cannot support. Only an authenticated door carries the
    Captain's name.
    """
    return ACTOR_CAPTAIN if door in _CAPTAIN_DOORS else ACTOR_OPERATOR


def _prior_event(proposal_id: str) -> Optional[dict]:
    """A ``captain_outcome_ratified`` already on the ledger for this proposal.

    The repair half of the kill-mid-way invariant: files land atomically one at
    a time, so a process killed between the copy and the emit leaves ratified
    files and no receipt. The next call finds no prior event and emits it.
    """
    from framework.events import emitter

    try:
        rows = emitter.replay(event_types=[EVENT_TYPE])
    except Exception:
        return None
    for row in reversed(rows):
        payload = row.get("payload") or {}
        if str(payload.get("proposal_id") or "") == proposal_id:
            return row
    return None


def _emit(actor: str, payload: dict) -> Optional[str]:
    from framework.events import emitter

    event = emitter.emit(EVENT_TYPE, actor=actor, payload=payload)
    return str(event.get("id") or "") or None


def ratify(proposal_id: str, *, door: str, principal: str,
           root: Optional[Path] = None, now: Optional[str] = None,
           allow_repo: bool = False) -> Dict[str, Any]:
    """Ratify one proposed card. The single writer of both outcome files.

    Returns ``{"status": "ratified"|"already_ratified"|"not_found"|
    "invalid_row"|"refused", "outcome_id", "event_id", "path",
    "edited_since_proposed", "reason"}``. Never raises for an expected refusal
    — a door renders the status.
    """
    base = _base(root)
    result: Dict[str, Any] = {
        "status": "refused", "outcome_id": None, "event_id": None,
        "path": str(base / OUTCOMES_REL), "edited_since_proposed": False,
        "reason": "", "door": door, "principal": principal,
    }
    pid = str(proposal_id or "").strip()
    if not pid:
        result["reason"] = "no proposal id"
        return result
    if door not in DOORS:
        result["reason"] = "unknown door %r (expected one of %s)" % (door, ", ".join(DOORS))
        return result
    # A door that cannot name a principal refuses. An unattributed ratification
    # is the thing this whole unit exists to stop being possible.
    if not str(principal or "").strip():
        result["reason"] = "door %s named no principal" % door
        return result
    if _is_repo_root(base) and not allow_repo:
        result["reason"] = (
            "%s is a git worktree and its outcomes file is tracked — refusing to "
            "ratify into source control (pass --allow-repo if this really is the "
            "deployment root)" % base
        )
        return result

    lock_path = base / LOCK_REL
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            return _ratify_locked(base, pid, door=door, principal=principal,
                                  now=now, result=result)
        except RatifyError as err:
            result["status"] = err.status
            result["reason"] = err.reason
            return result
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _ratify_locked(base: Path, pid: str, *, door: str, principal: str,
                   now: Optional[str], result: Dict[str, Any]) -> Dict[str, Any]:
    proposals_path = base / genesis.PROPOSALS_REL
    outcomes_path = base / OUTCOMES_REL
    actor = actor_for(door)
    ts = genesis._utc_now_iso(now)

    proposals_doc, proposals_raw = _load_doc(proposals_path)
    rows = proposals_doc.get("outcomes")
    if not isinstance(rows, list):
        raise RatifyError("not_found", "no proposed cards at %s" % proposals_path)

    row = None
    for candidate in rows:
        if isinstance(candidate, dict) and str(candidate.get("id") or "") == pid:
            row = candidate
            break
    if row is None:
        raise RatifyError("not_found", "no proposed card with id %r" % pid)

    recorded_digest = str(row.get(genesis.ROW_DIGEST_KEY) or "")
    edited = bool(recorded_digest) and recorded_digest != genesis._row_digest(row)
    result["outcome_id"] = pid
    result["edited_since_proposed"] = edited

    # Build the row that WOULD LAND, then validate that — not the proposal as
    # it sits. Two reasons, both measured: the marked proposal carries
    # `status: ratified`, a staging word the outcome vocabulary does not have,
    # so validating the source row would refuse every second call; and the
    # keys this act stamps are exactly the ones the schema extension exists to
    # describe, so validating before stamping would never check them.
    ratified_row = dict(row)
    ratified_row["status"] = "active"
    ratified_row["captain_ratified"] = True
    ratified_row[RATIFIED_BY_KEY] = actor
    ratified_row[RATIFIED_VIA_KEY] = door
    ratified_row[RATIFIED_AT_KEY] = ts
    ratified_row[RATIFIED_FROM_DIGEST_KEY] = recorded_digest
    ratified_row[EDITED_SINCE_PROPOSED_KEY] = edited
    # `deployment` is never written: an absent gate compiles everywhere, and
    # inventing one here would pin a fresh responsibility to a cabinet id
    # nobody chose.
    result["validated_by"] = validate_projection(ratified_row)

    # --- the live file -----------------------------------------------------
    outcomes_doc, outcomes_raw = _load_doc(outcomes_path)
    live_rows = outcomes_doc.get("outcomes")
    if live_rows is None:
        live_rows = []
    if not isinstance(live_rows, list):
        raise RatifyError("invalid_row", "%s 'outcomes' is not a list" % OUTCOMES_REL)

    already = any(
        isinstance(r, dict) and str(r.get("id") or "") == pid and r.get("captain_ratified")
        for r in live_rows
    )

    if not already:
        replaced = False
        for index, existing in enumerate(live_rows):
            if isinstance(existing, dict) and str(existing.get("id") or "") == pid:
                live_rows[index] = ratified_row
                replaced = True
                break
        if not replaced:
            live_rows.append(ratified_row)
        outcomes_doc["outcomes"] = live_rows
        header = _leading_comment_block(outcomes_raw, _OUTCOMES_HEADER)
        body = header + _dump(outcomes_doc)
        if body != outcomes_raw:
            genesis._atomic_write(outcomes_path, body)

    # --- the proposal, marked rather than deleted --------------------------
    row["status"] = "ratified"
    row["captain_ratified"] = True
    header, _healed = genesis.rewrite_stale_proposals_header(
        genesis._preserved_header(proposals_raw))
    proposals_body = header + _dump(proposals_doc)
    if proposals_body != proposals_raw:
        genesis._atomic_write(proposals_path, proposals_body)

    # --- the receipt -------------------------------------------------------
    # Emit unless this exact tap already has one. Two states each need a
    # receipt and neither is "a second identical call": a live row that was
    # written without its event (killed between the two atomic writes — the
    # repair half of the kill invariant), and a row someone removed from the
    # live file and is now ratifying again, which is a new act whatever the
    # ledger remembers. Only already-ratified-AND-recorded is a true no-op.
    prior = _prior_event(pid)
    if already and prior is not None:
        result["status"] = "already_ratified"
        result["event_id"] = str(prior.get("id") or "") or None
        result["reason"] = "already ratified"
        return result

    criteria = row.get("measurable_criteria")
    payload = {
        "outcome_id": pid,
        "proposal_id": pid,
        "door": door,
        "principal": principal,
        "proposed_digest": recorded_digest,
        "edited_since_proposed": edited,
        "criteria_count": len(criteria) if isinstance(criteria, list) else 0,
        "root": str(base),
    }
    result["event_id"] = _emit(actor, payload)
    result["status"] = "already_ratified" if already else "ratified"
    if already:
        result["reason"] = "already ratified (receipt repaired)"
    return result


# ---------------------------------------------------------------------------
# The terminal door.
# ---------------------------------------------------------------------------
_STATUS_EXIT = {
    "ratified": EXIT_OK,
    "already_ratified": EXIT_OK,
    "not_found": EXIT_NOT_FOUND,
    "invalid_row": EXIT_INVALID_ROW,
    "refused": EXIT_REFUSED,
}


def _default_principal() -> str:
    """Who the terminal door is, in one string it can actually support."""
    for key in ("CABINET_PRINCIPAL", "SUDO_USER", "USER", "LOGNAME"):
        value = os.environ.get(key)
        if value:
            return value
    try:
        return "uid:%d" % os.getuid()
    except Exception:
        return "uid:unknown"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="framework.outcomes.ratify",
        description="Ratify one proposed outcome card (the tap).")
    parser.add_argument("proposal_id", nargs="?",
                        help="id of the proposed card to ratify")
    parser.add_argument("--door", default="terminal", choices=list(DOORS),
                        help="which door this tap came through")
    parser.add_argument("--principal", default=None,
                        help="the door's identity string, recorded on the event")
    parser.add_argument("--root", default=None,
                        help="deployment root (defaults to CABINET_ROOT)")
    parser.add_argument("--allow-repo", action="store_true",
                        help="ratify even when the root is a git worktree")
    parser.add_argument("--list", action="store_true",
                        help="print the ratifiable cards and exit")
    parser.add_argument("--json", action="store_true",
                        help="print the result as one JSON object")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else None

    if args.list:
        rows = list_ratifiable(root)
        if args.json:
            print(json.dumps(rows, ensure_ascii=False))
        else:
            for row in rows:
                print("%s  %s" % (row["id"], row["name"]))
            if not rows:
                print("no proposed cards awaiting a tap")
        return EXIT_OK

    if not args.proposal_id:
        parser.error("a proposal id is required (or --list)")

    result = ratify(args.proposal_id, door=args.door,
                    principal=args.principal or _default_principal(),
                    root=root, allow_repo=args.allow_repo)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        line = "%s %s" % (result["status"], result.get("outcome_id") or "")
        if result.get("reason"):
            line += " — %s" % result["reason"]
        print(line.strip())
    return _STATUS_EXIT.get(str(result["status"]), EXIT_REFUSED)


if __name__ == "__main__":  # pragma: no cover — CLI entry
    sys.exit(main())
