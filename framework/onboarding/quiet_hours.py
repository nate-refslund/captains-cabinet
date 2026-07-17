"""framework.onboarding.quiet_hours — the interview's quiet-hours question.

Captain insight (2026-07-17): a silent default is an invisible feature —
nobody discovers a quiet time exists by not being pinged. So the cabinet-init
interview PRESENTS the default and asks for a ruling instead of assuming:
"Quiet hours are 21:00–07:00: outside pings are held for the morning briefing
except infrastructure pages and security alerts. Keep, change, or disable?"

``render_question`` builds that sentence from the LIVE framework default
(framework/attention/charter-default.yml, via the charter loader) — never a
hardcoded copy, so a changed default changes the question. A malformed
default raises instead of rendering an invented window (fail-closed, the
charter loader's own law).

``apply_answer`` materializes the Captain's ruling through the charter
system's OWN override path — ``framework.attention.charter.amend()`` into
the deployment charter resolved by ``charter.instance_path()`` (the
framework.env seam; this module never spells the config path itself):

* ``keep``    → writes NOTHING (the framework default already rules). If a
                deployment override already carries a DIFFERENT window,
                keep REFUSES loudly — a prior ruling is never silently
                reverted by a re-run of the interview.
* ``change``  → a new window, strict 24h HH:MM only; ``start == end`` is
                refused (that is what ``disable`` is for); re-running the
                same window is an honest no-op, never an idle version bump.
* ``disable`` → the zero-length window (``start == end``), which the
                attention gate's ``_in_quiet_hours`` structurally never
                matches — no schema change, no special case downstream.

Every write rides ``amend()``: the full result is schema-validated BEFORE
any write (fail-closed on invalid), replaced atomically, and a provenance
row lands in the comms-charter amendments ledger with
``{trust: chair, via: cabinet-init-interview}`` and a fixed-template why
string (validated tokens only). The interview's conversational text NEVER
reaches this module: the CLI accepts only the fixed verb enum plus two
regex-validated times, so free text cannot ride into the charter or a
shell. ``floor_classes`` are always carried unchanged from the amend base —
this question can neither widen the quiet-hours floor (the §4.10.4 chair
asymmetry) nor quietly re-widen a floor a Captain previously narrowed.

No network, no subprocess, no secrets; the only write is charter.amend's
own atomic write into the deployment charter.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from framework.attention import charter

_TIME_RE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
_CHOICES = ("keep", "change", "disable")
_DISABLED_WINDOW = ("00:00", "00:00")
_PROVENANCE = {"trust": "chair", "via": "cabinet-init-interview"}

# Human labels for the floor classes the shipped default carries; an unknown
# slug renders verbatim (honest and still readable) rather than being
# dropped — the question must name every class that may pierce quiet hours.
_FLOOR_LABELS = {
    "infra-page": "infrastructure pages",
    "security-alert": "security alerts",
}


def _read_mapping(path: Path) -> dict:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise charter.CharterError(f"charter at {path} is not a mapping")
    return doc


def _default_charter(default_path: Path | str | None = None) -> dict:
    """The framework-default charter, VALIDATED — a malformed default raises
    (fail-closed) so the question can never present an invented window."""
    if default_path is not None:
        doc = _read_mapping(Path(default_path))
    else:
        doc = {k: v for k, v in charter.load_default().items() if k != "_source"}
    charter.validate_charter(doc)
    return doc


def _window(doc: dict) -> tuple[str, str]:
    qh = doc.get("quiet_hours") or {}
    return str(qh.get("start")), str(qh.get("end"))


def _floor(doc: dict) -> list[str]:
    qh = doc.get("quiet_hours") or {}
    return [str(c) for c in (qh.get("floor_classes") or [])]


def _floor_phrase(floor: list[str]) -> str:
    labels = [_FLOOR_LABELS.get(slug, slug) for slug in floor]
    if not labels:
        return "with no exceptions"
    joined = labels[0] if len(labels) == 1 else \
        ", ".join(labels[:-1]) + " and " + labels[-1]
    return f"except {joined}"


def _existing_override(path: Path) -> tuple[dict | None, bool]:
    """(valid override doc | None, invalid-file-present) at ``path``.
    Mirrors amend()'s own base resolution: an unreadable or schema-invalid
    file counts as ABSENT (it is already inert — fail-closed), but its
    presence is reported so receipts and the rendered question stay honest."""
    if not path.exists():
        return None, False
    try:
        doc = _read_mapping(path)
        charter.validate_charter(doc)
        return doc, False
    except (charter.CharterError, OSError, yaml.YAMLError):
        return None, True


def render_question(default_path: Path | str | None = None,
                    charter_path: Path | str | None = None) -> str:
    """The interview question, rendered from the CURRENT framework default —
    present the default, then ask. Never hardcoded: if the shipped default
    changes, the question follows. Appends an honest note when the
    deployment already carries an override so a re-run interview cannot
    trick the Captain into a silent revert."""
    default = _default_charter(default_path)
    start, end = _window(default)
    if start == end:
        q = (f"Quiet hours are disabled in this build's default "
             f"(zero-length window {start}–{end}). Keep, or change "
             f"(set a window like 21:00–07:00)?")
    else:
        q = (f"Quiet hours are {start}–{end}: outside pings are held for "
             f"the morning briefing {_floor_phrase(_floor(default))}. "
             f"Keep, change, or disable?")
    path = Path(charter_path) if charter_path else charter.instance_path()
    override, invalid = _existing_override(path)
    if override is not None:
        o_start, o_end = _window(override)
        if (o_start, o_end) != (start, end):
            state = ("disabled (zero-length window)" if o_start == o_end
                     else f"{o_start}–{o_end}")
            q += (f"\n(Note: this deployment already carries a charter "
                  f"override — its quiet hours are {state}; 'keep' refuses "
                  f"rather than reverting it, so answer change/disable to "
                  f"move it.)")
    elif invalid:
        q += ("\n(Note: an existing deployment charter override is INVALID "
              "and inert — the framework default rules until change/disable "
              "replaces it.)")
    return q


def _validated_time(label: str, value) -> str:
    v = str(value if value is not None else "").strip()
    if not _TIME_RE.match(v):
        raise charter.CharterError(
            f"{label} must be 24h HH:MM (e.g. 21:00), got {value!r} — "
            f"refused, nothing written")
    return v


def apply_answer(choice, start=None, end=None, *,
                 charter_path: Path | str | None = None) -> dict:
    """Materialize one interview answer. ``choice`` is the FIXED VERB ENUM
    keep|change|disable — anything else refuses; conversational free text is
    the interviewer's to hold, never this function's input. Returns a
    receipt dict; raises CharterError (a ValueError) on any refusal, always
    BEFORE anything is written."""
    verb = str(choice if choice is not None else "").strip().lower()
    if verb not in _CHOICES:
        raise charter.CharterError(
            f"choice must be one of {', '.join(_CHOICES)} (fixed verb "
            f"enum), got {choice!r} — refused, nothing written")

    path = Path(charter_path) if charter_path else charter.instance_path()
    default = _default_charter()
    d_window = _window(default)
    override, invalid = _existing_override(path)
    base = override if override is not None else default
    b_start, b_end = _window(base)
    floor = _floor(base)  # ALWAYS carried unchanged — never widened here

    def receipt(written: bool, version=None, window=None, note: str = "") -> dict:
        return {"choice": verb, "written": written, "version": version,
                "window": window, "floor_classes": floor,
                "path": str(path), "note": note}

    if verb == "keep":
        if override is not None and (b_start, b_end) != d_window:
            state = "disabled" if b_start == b_end else f"{b_start}–{b_end}"
            raise charter.CharterError(
                f"a deployment charter override already rules quiet hours "
                f"({state}); 'keep' will not silently revert it — answer "
                f"change/disable to move it, or leave it standing")
        if override is not None:
            note = ("existing override already matches the default window "
                    "— nothing written")
        elif invalid:
            note = ("framework default rules (an invalid override file is "
                    "present and inert) — nothing written")
        else:
            note = "framework default stands — nothing written"
        return receipt(False, window={"start": d_window[0], "end": d_window[1]},
                       note=note)

    if verb == "change":
        if start is None or end is None:
            raise charter.CharterError(
                "change needs both start and end (24h HH:MM) — refused, "
                "nothing written")
        new_start = _validated_time("start", start)
        new_end = _validated_time("end", end)
        if new_start == new_end:
            raise charter.CharterError(
                "start == end is the zero-length (disabled) window — "
                "answer disable instead of change, so the intent is "
                "explicit; refused, nothing written")
        target = (new_start, new_end)
        why = (f"cabinet-init interview: Captain set quiet hours "
               f"{new_start}–{new_end} (was {b_start}–{b_end})")
    else:  # disable
        target = _DISABLED_WINDOW
        why = (f"cabinet-init interview: Captain disabled quiet hours "
               f"(zero-length window; was {b_start}–{b_end})")

    if override is not None and (b_start, b_end) == target:
        return receipt(False, version=int(base.get("version") or 1),
                       window={"start": target[0], "end": target[1]},
                       note="already rules — honest no-op, no version bump")
    if override is None and target == d_window:
        note = ("the framework default already provides exactly this "
                "window — nothing written")
        if invalid:
            note += " (an invalid override file is present and inert)"
        return receipt(False, window={"start": target[0], "end": target[1]},
                       note=note)

    version = charter.amend(
        {"quiet_hours": {"start": target[0], "end": target[1],
                         "floor_classes": floor}},
        why, dict(_PROVENANCE), charter_path=path)
    note = "override written via charter.amend (amendment-ledger row appended)"
    if invalid:
        note += " — replaced a previously INVALID (inert) override file"
    return receipt(True, version=version,
                   window={"start": target[0], "end": target[1]}, note=note)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="framework.onboarding.quiet_hours",
        description="Interview quiet-hours question: render it from the "
                    "live framework default, and materialize the Captain's "
                    "keep/change/disable answer through charter.amend.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("question",
                       help="render the question from the live framework default")
    q.add_argument("--default-path", default=None,
                   help="alternate charter-default file (tests/previews)")
    a = sub.add_parser("apply",
                       help="materialize one answer (fixed verb enum only)")
    a.add_argument("--choice", required=True, choices=list(_CHOICES),
                   help="the Captain's answer, mapped to the fixed enum")
    a.add_argument("--start", default=None, help="24h HH:MM (change only)")
    a.add_argument("--end", default=None, help="24h HH:MM (change only)")
    a.add_argument("--charter-path", default=None,
                   help="alternate deployment charter target (tests)")
    ns = ap.parse_args(argv)
    try:
        if ns.cmd == "question":
            print(render_question(default_path=ns.default_path))
        else:
            print(json.dumps(
                apply_answer(ns.choice, ns.start, ns.end,
                             charter_path=ns.charter_path),
                ensure_ascii=False, indent=2))
    except charter.CharterError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
