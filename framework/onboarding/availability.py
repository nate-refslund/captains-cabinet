"""framework.onboarding.availability — the interview's availability question.

THE DIAL (Captain ruling 2026-07-26). Nothing in this cabinet ever asked how
much of the captain's day it was entitled to, and it showed: twice-daily
briefings ran straight through a declared month-long absence, and 146 proactive
cards chased 2 approvals. So onboarding now ASKS — once, in one sentence — and
the answer becomes a first-class instance value that the Captain-Seat Review
judges cost against and the comms surface paces from. **The org fits the
declared budget, never the reverse.**

Same insight as the quiet-hours question one bullet above it (Captain
2026-07-17): a silent default is an invisible feature. Nobody discovers that
the cabinet can run at ten-minutes-a-day by never being asked.

``render_question`` builds the sentence from the LIVE mode table
(``framework.env.AVAILABILITY_MODES``) — never a hardcoded copy of the prose or
the bands, so changing a band changes the question. It also reports what the
deployment ALREADY resolves (``framework.env.captain_availability()``) so a
re-run interview cannot talk a captain into silently reverting his own later
ruling.

``apply_answer`` materializes ONE answer into the cabinet-init ANSWERS file
(``framework.env.cabinet_init_answers_path()`` — the framework→instance seam;
this module never spells the config path). The answers file is the generator's
input: ``cabinet/scripts/generate-instance.py`` validates ``captain.availability``
against this same enum and stamps ``captain_availability_minutes_per_day`` /
``captain_availability_mode`` into ``instance/config/platform.yml``. That is
deliberately the ONLY write path here — platform.yml is a marker-managed
generator output, so a second writer poking at it would fight the generator.

* ``skip``  → writes NOTHING. Availability stays UNKNOWN, which is a legal,
              documented state ("the org does not know how much of the captain
              it is entitled to"). An HONEST ABSENCE plus the phone verb beats
              a placeholder that pretends to be an answer — that placeholder is
              the named failure of the 1/3-scored briefing.
* the four availability verbs → the answer is recorded; the generator turns it
              into the platform key on the next run.

A LATER ruling always wins without touching this file: the phone verb
(``cabinet/scripts/lib/captain_availability.py``) appends to the adjustment
store, which the resolver reads AHEAD of the platform key. So re-running the
interview after the captain has re-dialled from his phone cannot silently
demote him — and ``render_question`` says so out loud when it detects it.

The interview's conversational text NEVER reaches this module: the CLI accepts
only the fixed verb enum, so free text cannot ride into config or a shell.
No network, no subprocess, no secrets; the only write is one atomic replace of
the answers file.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml

from framework import env

#: The fixed verb enum. The four availability verbs come from the LIVE mode
#: table minus ``away`` (a captain does not onboard as away — he sets that from
#: his phone when he leaves), plus ``skip`` (leave it unknown).
_ONBOARDING_MODES = tuple(m for m in env.availability_modes() if m != "away")
_CHOICES = _ONBOARDING_MODES + ("skip",)

#: Answers-file location of the recorded verb: ``captain.availability``.
_ANSWERS_SECTION = "captain"
_ANSWERS_KEY = "availability"


class AvailabilityError(ValueError):
    """A refused answer or an unusable answers file. Nothing is written."""


def _labels() -> "list[str]":
    """The human labels for the onboarding verbs, from the LIVE table."""
    return [f"{name} ({label.split('—', 1)[-1].strip()})"
            for name, _minutes, label in env.AVAILABILITY_MODES
            if name in _ONBOARDING_MODES]


def render_question() -> str:
    """The interview question, rendered from the CURRENT mode table — present
    the options, then ask. Appends an honest note when the deployment already
    resolves an availability, so a re-run cannot quietly revert a later
    ruling."""
    opts = _labels()
    q = ("How much time a day do you have for the cabinet? Whatever you say "
         "is the budget the org fits into — it decides how much reaches you, "
         "how often, and what may demand an answer rather than just telling "
         "you. Options: " + "; ".join(opts) +
         ". Or skip, and it stays unknown until you set it from your phone "
         "(\"availability 20m\").")
    try:
        current = env.captain_availability()
    except Exception:  # noqa: BLE001 — the question must render regardless
        current = None
    if current and current.get("minutes_per_day") is not None:
        q += (f"\n(Note: this deployment already declares "
              f"{env.render_availability(current)}"
              + (f", set {current['set_at']}" if current.get("set_at") else "")
              + ". A later phone ruling outranks whatever the interview "
                "records, so answering here cannot silently demote it — "
                "re-dial from your phone if you want it changed.)")
    return q


def _read_answers(path: Path) -> dict:
    """The answers mapping at ``path``, or ``{}`` when the file is absent.

    A file that exists but is not a YAML mapping REFUSES loudly: overwriting a
    file we cannot read would destroy an interview's work, and this question is
    never important enough to be the thing that does that."""
    if not path.exists():
        return {}
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise AvailabilityError(
            f"answers file at {path} is unreadable ({exc}) — refused, nothing "
            f"written; fix or move the file and re-run") from exc
    if doc is None:
        return {}
    if not isinstance(doc, dict):
        raise AvailabilityError(
            f"answers file at {path} is not a YAML mapping — refused, nothing "
            f"written")
    return doc


def _write_answers(path: Path, doc: dict) -> None:
    """Atomic replace, parent dirs created. Same discipline as every other
    config write in the interview: never a partial file on disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
                   encoding="utf-8")
    os.replace(tmp, path)


def apply_answer(choice, *, answers_path: "Path | str | None" = None) -> dict:
    """Materialize ONE interview answer. ``choice`` is the FIXED VERB ENUM
    (the availability verbs plus ``skip``) — anything else refuses;
    conversational free text is the interviewer's to hold, never this
    function's input. Returns a receipt dict; raises ``AvailabilityError``
    (a ValueError) on any refusal, always BEFORE anything is written."""
    verb = str(choice if choice is not None else "").strip().lower()
    if verb not in _CHOICES:
        raise AvailabilityError(
            f"choice must be one of {', '.join(_CHOICES)} (fixed verb enum), "
            f"got {choice!r} — refused, nothing written")
    path = Path(answers_path) if answers_path else env.cabinet_init_answers_path()

    def receipt(written: bool, note: str) -> dict:
        return {"choice": verb, "written": written, "path": str(path),
                "minutes_per_day": env.availability_minutes_for_mode(verb),
                "note": note}

    if verb == "skip":
        # The honest absence. Deliberately NOT a placeholder number: unknown is
        # a legal state every consumer already handles conservatively.
        return receipt(False,
                       "availability left UNKNOWN — nothing written; the "
                       "captain can set it any time from his phone "
                       "(\"availability 20m\")")

    doc = _read_answers(path)
    section = doc.get(_ANSWERS_SECTION)
    if section is not None and not isinstance(section, dict):
        raise AvailabilityError(
            f"answers file at {path} has a non-mapping '{_ANSWERS_SECTION}:' "
            f"block — refused, nothing written")
    section = dict(section or {})
    previous = section.get(_ANSWERS_KEY)
    if previous == verb:
        return receipt(False, f"answers already record {verb} — honest no-op")
    section[_ANSWERS_KEY] = verb
    doc[_ANSWERS_SECTION] = section
    _write_answers(path, doc)
    note = (f"recorded {_ANSWERS_SECTION}.{_ANSWERS_KEY}={verb}"
            + (f" (was {previous!r})" if previous is not None else "")
            + " — run cabinet/scripts/generate-instance.py to stamp it into "
              "instance/config/platform.yml")
    return receipt(True, note)


#: What the operator is CALLED, and the two constraints on it. The authority is
#: ``cabinet/scripts/generate-instance.py::validate_display_name`` — length and
#: control characters, and deliberately NO alphabet (a name written in any
#: script is a name; see the RES-025 retirement note in salience.py). Restated
#: rather than imported because ``framework/`` never imports ``cabinet/``; the
#: cap is the generator's own, so a name accepted here can never be one the
#: generator then refuses.
_NAME_SECTION = "captain"
_NAME_KEY = "name"
NAME_MAX = 80
_NAME_CONTROL_RE = re.compile("[\\x00-\\x1f\\x7f-\\x9f\\u2028\\u2029]")


def record_captain_name(name, *, answers_path: "Path | str | None" = None) -> dict:
    """Record what the operator is called into ``captain.name``.

    THE SAME WRITE PATH AS THE AVAILABILITY VERB, and that is the whole reason
    it lives here: the answers file's ``captain:`` block gets exactly one writer,
    which reads before it writes, refuses a file it cannot parse rather than
    destroying an interview's work, and replaces atomically. ``platform.yml`` is
    a marker-managed generator output and is NOT touched — the generator stamps
    ``captain_name`` from this file on its next run, so onboarding never fights
    it.

    AN EXISTING NAME IS REPLACED, and the receipt says what it was. A fresh
    hatch writes ``captain.name`` from ``$USER`` before anyone has been asked, so
    refusing to overwrite would mean the operator's own answer to "what is your
    name?" loses to a Unix account. Same-value is an honest no-op.
    """
    # STRIPPED, THEN CHECKED, THEN COLLAPSED — in that order, and the order is
    # the whole point. Collapsing first would turn a two-line paste into one
    # plausible line and store it, so the control-character rule the generator
    # enforces could never fire here: the check would run on a string from which
    # the offending character had just been removed. A name is one line of text;
    # a paste that is two is refused rather than silently repaired.
    text = str(name if name is not None else "").strip()
    if not text:
        raise AvailabilityError("a name is one line of text — refused, nothing written")
    bad = _NAME_CONTROL_RE.search(text)
    if bad:
        raise AvailabilityError(
            f"that name contains a control character (U+{ord(bad.group()):04X}) — "
            f"refused, nothing written")
    if len(text) > NAME_MAX:
        raise AvailabilityError(
            f"that name is {len(text)} characters; the limit is {NAME_MAX} — "
            f"refused, nothing written")
    text = " ".join(text.split())
    path = Path(answers_path) if answers_path else env.cabinet_init_answers_path()
    doc = _read_answers(path)
    section = doc.get(_NAME_SECTION)
    if section is not None and not isinstance(section, dict):
        raise AvailabilityError(
            f"answers file at {path} has a non-mapping '{_NAME_SECTION}:' block "
            f"— refused, nothing written")
    section = dict(section or {})
    previous = section.get(_NAME_KEY)
    if previous == text:
        return {"name": text, "written": False, "previous": previous,
                "note": "answers already record that name — honest no-op"}
    section[_NAME_KEY] = text
    doc[_NAME_SECTION] = section
    _write_answers(path, doc)
    return {"name": text, "written": True, "previous": previous,
            "note": f"recorded {_NAME_SECTION}.{_NAME_KEY}"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="framework.onboarding.availability",
        description="Interview availability question: render it from the live "
                    "mode table, and record the captain's answer into the "
                    "cabinet-init answers file the generator reads.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("question", help="render the question from the live mode table")
    a = sub.add_parser("apply", help="record one answer (fixed verb enum only)")
    a.add_argument("--choice", required=True, choices=list(_CHOICES),
                   help="the captain's answer, mapped to the fixed enum")
    a.add_argument("--answers-path", default=None,
                   help="alternate answers file (tests)")
    ns = ap.parse_args(argv)
    try:
        if ns.cmd == "question":
            print(render_question())
        else:
            print(json.dumps(apply_answer(ns.choice,
                                          answers_path=ns.answers_path),
                             ensure_ascii=False, indent=2))
    except AvailabilityError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
