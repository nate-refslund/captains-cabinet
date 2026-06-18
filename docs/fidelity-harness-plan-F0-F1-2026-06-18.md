# Fidelity Harness F0–F1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax.

**Goal:** Build the cabinet-native Fidelity Harness substrate (F0: schema-validating consequence-event emitter + ledger reader with graduation ratios) and the reply-cell evaluator (F1: blind, leak-guarded officer-runner + retrodiction-reuse scorer) so the cabinet can measure how faithfully an officer reproduces Nate's real decisions.

**Architecture:** A cabinet-native `framework/fidelity/` module that imports/ports the screenpipe retrodiction scoring engine rather than re-deriving it, and emits the existing normalized `consequence-event` shape so graduation math reads one ledger. Two tiers run in concert: F0 ships the dependency-free emitter + reader (the shared substrate every actor writes to), and F1 drives a production officer blind on held-out cases and scores its decision against ground truth. Every LLM call (the decision judge included) reaches Claude over the OAuth `claude -p` headless path — there is no `ANTHROPIC_API_KEY`.

**Tech Stack:** Python 3.9.6 (system, `from __future__ import annotations` + PEP 604 unions, stdlib-only — no `jsonschema`), pytest (sibling `tests/` dirs, `python3 -m pytest`), the screenpipe retrodiction lib reused via an import shim (`extract_cases`/`score_case`/`judge_decision`/`cusum`/`author_centroid`/`aggregate`/`mechanics_flags`), Voyage embeddings (`voyage-4-large`, STYLE channel only), OAuth `claude -p` headless invocation for the decision judge + baseline draft, and the append-only consequence-event JSONL ledger.

## Global Constraints

- **Reuse the retrodiction engine, do not rebuild it.** `extract_cases`, `score_case`, `judge_decision`, `score_draft`, `cusum`, `author_centroid`, `aggregate`, `mechanics_flags` are imported through `framework/fidelity/retro.py` — never re-derived.
- **Judge via OAuth `claude -p` — NO `ANTHROPIC_API_KEY`.** The decision judge and baseline draft route through `framework/fidelity/oauth_llm.py` (`claude -p` headless, billing the Max pool via `CLAUDE_CODE_OAUTH_TOKEN`); `ANTHROPIC_API_KEY` is actively stripped from the subprocess env.
- **Voyage is for STYLE only.** Voyage embeddings feed the cosine STYLE channel inside `score_case`; the DECISION channel is the tone-blind LLM judge and MECHANICS is deterministic.
- **The anti-leakage cutoff guard is mandatory and must be built + tested.** No officer-under-test sees anything timestamped `>= cutoff_ts`; any breach hard-fails the case and emits a leak event. The guard ships with full unit coverage in F1.3.
- **Consequence-events validate against `framework/schemas/consequence-event.schema.json`.** Validation is hand-rolled in pure Python against that exact schema (`additionalProperties: false` everywhere + the three documented cross-field invariants) because system Python 3.9.6 has no `jsonschema`.
- **Privacy fence: `nate_model` / voice / `0-Self` never egress.** They may inform HOW a draft or centroid is built but must never appear in a score row, consequence event, commit, doc, or any artifact that leaves this machine.
- **System-Python target + test layout + commit trailer.** Target system Python 3.9.6 with `from __future__ import annotations`; tests live in sibling `framework/fidelity/tests/`, run via `python3 -m pytest <path>`; every commit ends with:
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01LLg211Y8u2kHCkn5v9pEMQ
  ```

---

## Task 1 — `framework/fidelity/` module scaffold + schema-validating consequence emitter

**Files:**
- Create: `/Users/nate/captains-cabinet/framework/fidelity/__init__.py` (empty package marker)
- Create: `/Users/nate/captains-cabinet/framework/fidelity/consequence.py`
- Create: `/Users/nate/captains-cabinet/framework/fidelity/tests/__init__.py` (empty)
- Test: `/Users/nate/captains-cabinet/framework/fidelity/tests/test_consequence.py`

**Interfaces:**
- Consumes: `framework/schemas/consequence-event.schema.json` (read at import time, parsed to a dict); `os.environ["CABINET_EVENT_LOG_DIR"]`; `datetime`, `json` (stdlib only — `jsonschema` is NOT installed on system Python 3.9.6, so validation is hand-rolled against this one schema).
- Produces:
  - `class ConsequenceValidationError(ValueError)` — raised when an event violates the schema or the cross-field invariants.
  - `validate_consequence(event: dict[str, Any]) -> None` — raises `ConsequenceValidationError` on any violation; returns `None` on success. Enforces: required top-level keys (`ts, actor, lane, action, subject`); `additionalProperties:false` at root + every nested object; `actor.kind ∈ {pipe,officer,crew}` + `actor.id` non-empty; `lane` is `str|None`; `proposal.required` present+bool; `proposal.decision ∈ {approved,edited,rejected,expired,None}`; `outcome.status ∈ {ok,failed,unknown}`; `review.verdict ∈ {confirmed,wrong,unknown}`; plus the three documented cross-field rules (`outcome.evidence` MUST be `None` iff `status=='unknown'`; `lesson_ref` only non-null when `verdict=='wrong'`; `proposal.decision` may be non-null only when `proposal.required` is `True`).
  - `emit_consequence(*, ts, actor, lane, action, subject, refs=None, proposal=None, outcome=None, review=None) -> dict[str, Any]` — assembles the event (defaulting `refs` to `[]`, dropping `None`-valued optional objects), validates it, appends one line to `$CABINET_EVENT_LOG_DIR/consequence-events-YYYY-MM-DD.jsonl` (UTC date), and returns the validated event dict. JSONL only — no Postgres, no Store mirror.
  - `_consequence_log_dir() -> Path` — mirrors `framework/events/emitter.py:_event_log_dir()` (`CABINET_EVENT_LOG_DIR` → default `~/Library/Application Support/cabinet/events`).
  - `SCHEMA: dict[str, Any]` — module-level parsed schema (loaded once from `Path(__file__).resolve().parent.parent / "schemas" / "consequence-event.schema.json"`).

> **Ledger-collision fix (blocker):** `framework/events/emitter.py` already writes `events-YYYY-MM-DD.jsonl` to the same default dir. The consequence ledger uses a DISTINCT filename family — `consequence-events-YYYY-MM-DD.jsonl` — so the two never collide, and the reader (Task 2) globs `consequence-events-*.jsonl` only. A regression test confirms the reader ignores a co-located org_events-shaped row (string `actor`).

**Steps:**

- [ ] **1. Write the failing test for module import + schema load.** Create `/Users/nate/captains-cabinet/framework/fidelity/tests/test_consequence.py`:

   ```python
   """Tests for the F0 consequence-event emitter + ledger reader."""

   from __future__ import annotations

   import json
   import os
   import sys
   from pathlib import Path

   import pytest

   sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

   from framework.fidelity.consequence import (
       SCHEMA,
       ConsequenceValidationError,
       validate_consequence,
       emit_consequence,
       _consequence_log_dir,
   )


   @pytest.fixture(autouse=True)
   def event_log_dir(tmp_path, monkeypatch):
       """Isolate the consequence ledger to a tmp dir; no DB in tests."""
       monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
       monkeypatch.delenv("DATABASE_URL", raising=False)
       return tmp_path


   def _act_event(**overrides):
       """A minimal valid 'Act'-phase consequence event (gate pending)."""
       base = {
           "ts": "2026-06-18T08:00:00+00:00",
           "actor": {"kind": "officer", "id": "cos"},
           "lane": "polads",
           "action": "drafted-reply",
           "subject": "thread-abc",
           "refs": ["msg-1"],
           "proposal": {"required": True, "decision": None, "decided_at": None},
       }
       base.update(overrides)
       return base


   class TestSchemaLoad:
       def test_schema_is_the_real_consequence_schema(self):
           assert SCHEMA["title"] == "Consequence Event"
           assert SCHEMA["required"] == ["ts", "actor", "lane", "action", "subject"]
           assert SCHEMA["additionalProperties"] is False

       def test_log_dir_honors_env(self, event_log_dir):
           assert _consequence_log_dir() == Path(os.environ["CABINET_EVENT_LOG_DIR"])
   ```

   Run it and show it fails because the module does not exist yet:

   ```
   python3 -m pytest framework/fidelity/tests/test_consequence.py::TestSchemaLoad -q
   ```
   Expected: `ModuleNotFoundError: No module named 'framework.fidelity'` (collection error, 0 passed).

- [ ] **2. Minimal implementation: package markers + schema load + log-dir resolver.** Create `/Users/nate/captains-cabinet/framework/fidelity/__init__.py` (empty file) and `/Users/nate/captains-cabinet/framework/fidelity/tests/__init__.py` (empty file). Create `/Users/nate/captains-cabinet/framework/fidelity/consequence.py` with exactly:

   ```python
   """F0 — consequence-event emitter + ledger reader (shared fidelity infra).

   Emits the normalized `consequence-event` shape
   (framework/schemas/consequence-event.schema.json) to an append-only JSONL
   ledger, validating every event against the real schema first. Graduation
   math reads ONLY this ledger (see docs/consequence-ledger.md). This module is
   the first consumer per docs/fidelity-harness-design-2026-06-18.md §5.

   Storage mirrors framework/events/emitter.py BUT uses a DISTINCT filename
   family so the two ledgers never collide in the shared dir: one file per UTC
   day at $CABINET_EVENT_LOG_DIR/consequence-events-YYYY-MM-DD.jsonl,
   json.dumps(event, default=str) + newline, append-only. (events/emitter.py
   owns events-YYYY-MM-DD.jsonl in the same dir.) Enrichment (decision/outcome/
   review landing later) is a SUPERSEDING event with the same
   (actor, action, subject, ts) identity tuple; the reader takes the last write
   per identity (last-write-wins).

   System Python is 3.9.6 with no `jsonschema` dependency, so validation is
   hand-rolled against this ONE schema (additionalProperties:false everywhere +
   the three documented cross-field invariants).
   """

   from __future__ import annotations

   import json
   import os
   from datetime import datetime, timezone
   from pathlib import Path
   from typing import Any


   _SCHEMA_PATH = (
       Path(__file__).resolve().parent.parent
       / "schemas"
       / "consequence-event.schema.json"
   )
   SCHEMA: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text())


   class ConsequenceValidationError(ValueError):
       """Raised when a consequence event violates the schema or its invariants."""


   def _consequence_log_dir() -> Path:
       """Resolve the JSONL consequence-ledger directory.

       Mirrors framework/events/emitter.py:_event_log_dir(): CABINET_EVENT_LOG_DIR
       wins; default is the durable per-user location (NOT /tmp, which is wiped).
       """
       return Path(os.environ.get(
           "CABINET_EVENT_LOG_DIR",
           os.path.expanduser("~/Library/Application Support/cabinet/events"),
       ))
   ```

   Run and show PASS:

   ```
   python3 -m pytest framework/fidelity/tests/test_consequence.py::TestSchemaLoad -q
   ```
   Expected: `2 passed`.

- [ ] **3. Commit.**
   ```
   git add framework/fidelity/__init__.py framework/fidelity/consequence.py framework/fidelity/tests/__init__.py framework/fidelity/tests/test_consequence.py
   git commit -m "feat(fidelity): F0 module scaffold + consequence schema load

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01LLg211Y8u2kHCkn5v9pEMQ"
   ```

- [ ] **4. Write the failing test for `validate_consequence` happy path + required-field + additionalProperties + enum enforcement.** Append to `test_consequence.py`:

   ```python
   class TestValidateStructure:
       def test_minimal_act_event_passes(self):
           assert validate_consequence(_act_event()) is None

       def test_full_lifecycle_event_passes(self):
           ev = _act_event(
               proposal={"required": True, "decision": "approved",
                         "decided_at": "2026-06-18T08:05:00+00:00"},
               outcome={"status": "ok", "evidence": "sent-msg-xyz"},
               review={"verdict": "confirmed", "reviewed_at":
                       "2026-06-18T09:00:00+00:00", "lesson_ref": None},
           )
           assert validate_consequence(ev) is None

       def test_lane_may_be_null(self):
           assert validate_consequence(_act_event(lane=None)) is None

       @pytest.mark.parametrize("missing", ["ts", "actor", "lane", "action", "subject"])
       def test_missing_required_field_raises(self, missing):
           ev = _act_event()
           del ev[missing]
           with pytest.raises(ConsequenceValidationError, match=missing):
               validate_consequence(ev)

       def test_unknown_top_level_field_raises(self):
           with pytest.raises(ConsequenceValidationError, match="additional"):
               validate_consequence(_act_event(surprise="boom"))

       def test_unknown_actor_field_raises(self):
           ev = _act_event(actor={"kind": "officer", "id": "cos", "rank": "admiral"})
           with pytest.raises(ConsequenceValidationError, match="actor"):
               validate_consequence(ev)

       def test_unknown_proposal_field_raises(self):
           ev = _act_event(proposal={"required": True, "veto": False})
           with pytest.raises(ConsequenceValidationError, match="proposal"):
               validate_consequence(ev)

       def test_bad_actor_kind_raises(self):
           ev = _act_event(actor={"kind": "alien", "id": "ufo"})
           with pytest.raises(ConsequenceValidationError, match="actor.kind"):
               validate_consequence(ev)

       def test_bad_proposal_decision_raises(self):
           ev = _act_event(proposal={"required": True, "decision": "aproved"})
           with pytest.raises(ConsequenceValidationError, match="proposal.decision"):
               validate_consequence(ev)

       def test_bad_outcome_status_raises(self):
           ev = _act_event(outcome={"status": "broke", "evidence": "x"})
           with pytest.raises(ConsequenceValidationError, match="outcome.status"):
               validate_consequence(ev)

       def test_bad_review_verdict_raises(self):
           ev = _act_event(review={"verdict": "right"})
           with pytest.raises(ConsequenceValidationError, match="review.verdict"):
               validate_consequence(ev)
   ```

   Run and show FAIL:
   ```
   python3 -m pytest framework/fidelity/tests/test_consequence.py::TestValidateStructure -q
   ```
   Expected: `ImportError: cannot import name 'validate_consequence'` at the top-level import → collection error, 0 passed.

- [ ] **5. Minimal implementation: structural validator (incl. enum rejection).** Append to `consequence.py`:

   ```python
   _ACTOR_KINDS = {"pipe", "officer", "crew"}
   _PROPOSAL_DECISIONS = {"approved", "edited", "rejected", "expired", None}
   _OUTCOME_STATUSES = {"ok", "failed", "unknown"}
   _REVIEW_VERDICTS = {"confirmed", "wrong", "unknown"}

   # Allowed keys per object (additionalProperties:false everywhere).
   _ROOT_KEYS = {"ts", "actor", "lane", "action", "subject",
                 "refs", "proposal", "outcome", "review"}
   _ROOT_REQUIRED = ("ts", "actor", "lane", "action", "subject")
   _ACTOR_KEYS = {"kind", "id"}
   _PROPOSAL_KEYS = {"required", "decision", "decided_at"}
   _OUTCOME_KEYS = {"status", "evidence"}
   _REVIEW_KEYS = {"verdict", "reviewed_at", "lesson_ref"}


   def _reject_extra(obj: dict[str, Any], allowed: set[str], where: str) -> None:
       extra = set(obj) - allowed
       if extra:
           raise ConsequenceValidationError(
               f"{where}: additional properties not allowed: {sorted(extra)}"
           )


   def validate_consequence(event: dict[str, Any]) -> None:
       """Validate a consequence event against the real schema + invariants.

       Raises ConsequenceValidationError on any violation; returns None on pass.
       Hand-rolled because system Python 3.9.6 has no jsonschema dependency.
       Enforces additionalProperties:false at every level + the three documented
       cross-field invariants (see docs/consequence-ledger.md).
       """
       if not isinstance(event, dict):
           raise ConsequenceValidationError("event must be an object")

       for key in _ROOT_REQUIRED:
           if key not in event:
               raise ConsequenceValidationError(f"missing required field: {key}")
       _reject_extra(event, _ROOT_KEYS, "root")

       # ts / action / subject: non-empty strings
       for key in ("ts", "action", "subject"):
           val = event[key]
           if not isinstance(val, str) or not val:
               raise ConsequenceValidationError(f"{key} must be a non-empty string")

       # lane: string | null
       if event["lane"] is not None and not isinstance(event["lane"], str):
           raise ConsequenceValidationError("lane must be a string or null")

       # actor
       actor = event["actor"]
       if not isinstance(actor, dict):
           raise ConsequenceValidationError("actor must be an object")
       for key in ("kind", "id"):
           if key not in actor:
               raise ConsequenceValidationError(f"actor: missing required field: {key}")
       _reject_extra(actor, _ACTOR_KEYS, "actor")
       if actor["kind"] not in _ACTOR_KINDS:
           raise ConsequenceValidationError(
               f"actor.kind must be one of {sorted(_ACTOR_KINDS)}"
           )
       if not isinstance(actor["id"], str) or not actor["id"]:
           raise ConsequenceValidationError("actor.id must be a non-empty string")

       # refs: array of strings (optional)
       if "refs" in event:
           refs = event["refs"]
           if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
               raise ConsequenceValidationError("refs must be an array of strings")

       # proposal (optional)
       if "proposal" in event:
           prop = event["proposal"]
           if not isinstance(prop, dict):
               raise ConsequenceValidationError("proposal must be an object")
           if "required" not in prop:
               raise ConsequenceValidationError("proposal: missing required field: required")
           _reject_extra(prop, _PROPOSAL_KEYS, "proposal")
           if not isinstance(prop["required"], bool):
               raise ConsequenceValidationError("proposal.required must be a boolean")
           if prop.get("decision") not in _PROPOSAL_DECISIONS:
               raise ConsequenceValidationError(
                   "proposal.decision must be one of "
                   f"{sorted(d for d in _PROPOSAL_DECISIONS if d)} or null"
               )

       # outcome (optional)
       if "outcome" in event:
           outc = event["outcome"]
           if not isinstance(outc, dict):
               raise ConsequenceValidationError("outcome must be an object")
           if "status" not in outc:
               raise ConsequenceValidationError("outcome: missing required field: status")
           _reject_extra(outc, _OUTCOME_KEYS, "outcome")
           if outc["status"] not in _OUTCOME_STATUSES:
               raise ConsequenceValidationError(
                   f"outcome.status must be one of {sorted(_OUTCOME_STATUSES)}"
               )

       # review (optional)
       if "review" in event:
           rev = event["review"]
           if not isinstance(rev, dict):
               raise ConsequenceValidationError("review must be an object")
           if "verdict" not in rev:
               raise ConsequenceValidationError("review: missing required field: verdict")
           _reject_extra(rev, _REVIEW_KEYS, "review")
           if rev["verdict"] not in _REVIEW_VERDICTS:
               raise ConsequenceValidationError(
                   f"review.verdict must be one of {sorted(_REVIEW_VERDICTS)}"
               )

       _validate_invariants(event)


   def _validate_invariants(event: dict[str, Any]) -> None:
       """The three cross-field rules the schema enum/required cannot express."""
       prop = event.get("proposal")
       if prop is not None:
           # decision may be non-null only when an approval gate exists.
           if prop.get("required") is False and prop.get("decision") is not None:
               raise ConsequenceValidationError(
                   "proposal.decision must be null when proposal.required is false"
               )

       outc = event.get("outcome")
       if outc is not None:
           status = outc.get("status")
           evidence = outc.get("evidence")
           if status == "unknown" and evidence is not None:
               raise ConsequenceValidationError(
                   "outcome.evidence must be null when status is 'unknown'"
               )
           if status in ("ok", "failed") and not evidence:
               raise ConsequenceValidationError(
                   f"outcome.evidence must be present when status is '{status}'"
               )

       rev = event.get("review")
       if rev is not None:
           if rev.get("verdict") != "wrong" and rev.get("lesson_ref") is not None:
               raise ConsequenceValidationError(
                   "review.lesson_ref must be null unless verdict is 'wrong'"
               )
   ```

   Run and show PASS:
   ```
   python3 -m pytest framework/fidelity/tests/test_consequence.py::TestValidateStructure -q
   ```
   Expected: `14 passed` (3 + 5 parametrized + 2 unknown-field + 4 enum).

- [ ] **6. Commit.**
   ```
   git add framework/fidelity/consequence.py framework/fidelity/tests/test_consequence.py
   git commit -m "feat(fidelity): F0 structural validator for consequence events

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01LLg211Y8u2kHCkn5v9pEMQ"
   ```

- [ ] **7. Write the failing test for the three cross-field invariants.** Append to `test_consequence.py`:

   ```python
   class TestInvariants:
       def test_evidence_must_be_null_when_unknown(self):
           ev = _act_event(outcome={"status": "unknown", "evidence": "leaked"})
           with pytest.raises(ConsequenceValidationError, match="evidence"):
               validate_consequence(ev)

       def test_evidence_required_when_ok(self):
           ev = _act_event(outcome={"status": "ok", "evidence": None})
           with pytest.raises(ConsequenceValidationError, match="evidence"):
               validate_consequence(ev)

       def test_evidence_required_when_failed(self):
           ev = _act_event(outcome={"status": "failed"})
           with pytest.raises(ConsequenceValidationError, match="evidence"):
               validate_consequence(ev)

       def test_unknown_outcome_with_null_evidence_passes(self):
           ev = _act_event(outcome={"status": "unknown", "evidence": None})
           assert validate_consequence(ev) is None

       def test_decision_must_be_null_when_not_required(self):
           ev = _act_event(proposal={"required": False, "decision": "approved"})
           with pytest.raises(ConsequenceValidationError, match="decision"):
               validate_consequence(ev)

       def test_below_bar_action_required_false_passes(self):
           ev = _act_event(proposal={"required": False, "decision": None})
           assert validate_consequence(ev) is None

       def test_lesson_ref_only_when_wrong(self):
           ev = _act_event(review={"verdict": "confirmed",
                                   "lesson_ref": "lessons.md#anchor"})
           with pytest.raises(ConsequenceValidationError, match="lesson_ref"):
               validate_consequence(ev)

       def test_lesson_ref_allowed_when_wrong(self):
           ev = _act_event(review={"verdict": "wrong",
                                   "lesson_ref": "lessons.md#anchor"})
           assert validate_consequence(ev) is None
   ```

   Run and confirm GREEN (the invariants were implemented in step 5; these lock them against regression):
   ```
   python3 -m pytest framework/fidelity/tests/test_consequence.py::TestInvariants -q
   ```
   Expected: `8 passed`. (If any fails, fix `_validate_invariants` until green before committing.)

- [ ] **8. Commit.**
   ```
   git add framework/fidelity/tests/test_consequence.py
   git commit -m "test(fidelity): F0 cross-field invariant coverage for consequence schema

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01LLg211Y8u2kHCkn5v9pEMQ"
   ```

- [ ] **9. Write the failing test for `emit_consequence` (validate-then-append JSONL, distinct filename family).** Append to `test_consequence.py`:

   ```python
   class TestEmit:
       def test_emit_returns_validated_event(self, event_log_dir):
           ev = emit_consequence(
               ts="2026-06-18T08:00:00+00:00",
               actor={"kind": "officer", "id": "cos"},
               lane="polads",
               action="drafted-reply",
               subject="thread-abc",
               refs=["msg-1"],
               proposal={"required": True, "decision": None, "decided_at": None},
           )
           assert ev["action"] == "drafted-reply"
           assert ev["actor"] == {"kind": "officer", "id": "cos"}

       def test_emit_defaults_refs_to_empty_list(self, event_log_dir):
           ev = emit_consequence(
               ts="2026-06-18T08:00:00+00:00",
               actor={"kind": "pipe", "id": "commitment-ledger"},
               lane=None,
               action="auto-closed-commitment",
               subject="cmt-1",
           )
           assert ev["refs"] == []

       def test_emit_omits_none_optional_objects(self, event_log_dir):
           ev = emit_consequence(
               ts="2026-06-18T08:00:00+00:00",
               actor={"kind": "pipe", "id": "x"},
               lane=None, action="a", subject="s",
           )
           assert "proposal" not in ev
           assert "outcome" not in ev
           assert "review" not in ev

       def test_emit_writes_to_consequence_events_file(self, event_log_dir):
           emit_consequence(
               ts="2026-06-18T08:00:00+00:00",
               actor={"kind": "officer", "id": "cos"},
               lane="polads", action="drafted-reply", subject="t1",
           )
           emit_consequence(
               ts="2026-06-18T08:01:00+00:00",
               actor={"kind": "officer", "id": "cos"},
               lane="polads", action="drafted-reply", subject="t2",
           )
           files = list(Path(event_log_dir).glob("consequence-events-*.jsonl"))
           assert len(files) == 1
           # must NOT collide with the org_events ledger filename family
           assert not list(Path(event_log_dir).glob("events-2*.jsonl"))
           with open(files[0]) as f:
               lines = [json.loads(l) for l in f if l.strip()]
           assert len(lines) == 2
           assert {l["subject"] for l in lines} == {"t1", "t2"}

       def test_emit_rejects_invalid_event_before_writing(self, event_log_dir):
           with pytest.raises(ConsequenceValidationError):
               emit_consequence(
                   ts="2026-06-18T08:00:00+00:00",
                   actor={"kind": "alien", "id": "ufo"},  # bad kind
                   lane=None, action="a", subject="s",
               )
           assert list(Path(event_log_dir).glob("consequence-events-*.jsonl")) == []
   ```

   Run and show FAIL:
   ```
   python3 -m pytest framework/fidelity/tests/test_consequence.py::TestEmit -q
   ```
   Expected: `ImportError: cannot import name 'emit_consequence'` → collection error, 0 passed.

- [ ] **10. Minimal implementation: `emit_consequence` + JSONL writer (distinct filename).** Append to `consequence.py`:

   ```python
   def _write_to_log(event: dict[str, Any]) -> None:
       """Append one consequence event to the daily JSONL ledger (UTC date).

       Filename family is consequence-events-* (NOT events-*) so this ledger
       never collides with the org_events ledger written by events/emitter.py
       into the same CABINET_EVENT_LOG_DIR.
       """
       log_dir = _consequence_log_dir()
       log_dir.mkdir(parents=True, exist_ok=True)
       log_file = log_dir / (
           "consequence-events-"
           + datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".jsonl"
       )
       with open(log_file, "a") as f:
           f.write(json.dumps(event, default=str) + "\n")


   def emit_consequence(
       *,
       ts: str,
       actor: dict[str, Any],
       lane: str | None,
       action: str,
       subject: str,
       refs: list[str] | None = None,
       proposal: dict[str, Any] | None = None,
       outcome: dict[str, Any] | None = None,
       review: dict[str, Any] | None = None,
   ) -> dict[str, Any]:
       """Validate then append-write ONE consequence event to the JSONL ledger.

       Keyword-only by design: the schema field set is wide and order-free, and
       every caller (F1 fidelity_events builder, live officers via the brain
       bridge, surviving pipes) must name fields explicitly. `refs` defaults to
       []. The three optional objects (proposal/outcome/review) are emitted only
       when provided — a None section is dropped, not written as null, so the
       ledger carries exactly the lifecycle phase the caller has reached.
       Enrichment appends a SUPERSEDING event with the same
       (actor, action, subject, ts) identity; the reader takes the last write.
       """
       event: dict[str, Any] = {
           "ts": ts,
           "actor": actor,
           "lane": lane,
           "action": action,
           "subject": subject,
           "refs": list(refs) if refs is not None else [],
       }
       if proposal is not None:
           event["proposal"] = proposal
       if outcome is not None:
           event["outcome"] = outcome
       if review is not None:
           event["review"] = review

       validate_consequence(event)  # raises before any write
       _write_to_log(event)
       return event
   ```

   Run and show PASS:
   ```
   python3 -m pytest framework/fidelity/tests/test_consequence.py::TestEmit -q
   ```
   Expected: `5 passed`.

- [ ] **11. Commit.**
   ```
   git add framework/fidelity/consequence.py framework/fidelity/tests/test_consequence.py
   git commit -m "feat(fidelity): F0 emit_consequence — validate-then-append JSONL ledger (distinct filename)

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01LLg211Y8u2kHCkn5v9pEMQ"
   ```

---

## Task 2 — Consequence ledger reader: identity dedup + three graduation ratios per `(actor, lane, action-class)`

**Files:**
- Modify: `/Users/nate/captains-cabinet/framework/fidelity/consequence.py` (add reader functions)
- Test: `/Users/nate/captains-cabinet/framework/fidelity/tests/test_consequence.py` (add reader test classes)

**Interfaces:**
- Consumes: the JSONL ledger written by `emit_consequence` (`$CABINET_EVENT_LOG_DIR/consequence-events-*.jsonl`); the identity tuple convention `(actor, action, subject, ts)` (last-write-wins, append-only — no supersession field). `actor` in the identity tuple is the full `{"kind","id"}` object, compared as `kind:id`.
- Produces:
  - `_identity(event: dict[str, Any]) -> tuple[str, str, str, str]` — returns `(actor.kind + ":" + actor.id, action, subject, ts)` as the dedup key. Tolerates a malformed string `actor` (returns `"None:None"` rather than crashing) so a co-located org_events-shaped row can never raise.
  - `read_ledger(since: str | None = None) -> list[dict[str, Any]]` — reads all `consequence-events-*.jsonl` in the log dir, skips rows that are not valid consequence events (e.g. an org_events row with a string `actor`), sorts events by `ts` (lexicographic ISO ascending, stable on file then line order for equal ts), collapses by identity keeping the LAST write, optional `since` filter (`ts >= since`, inclusive), returns the deduped events. Missing dir → `[]`.
  - `class GraduationRatios` — a `@dataclass` holding the raw counts per cell (`approved/edited/rejected/ok/failed/confirmed/wrong` + `sample_count`). The three ratios are exposed as computed `@property` accessors (`approval_unchanged_rate`, `outcome_held_rate`, `review_confirmed_rate`, each `float | None`), NOT dataclass fields — a field and a same-named property cannot coexist. Each rate is `None` when its denominator is 0 (an unmeasured cell — never silently `0.0`/`1.0`, per design §"No-silent-caps").
  - `compute_ratios(since: str | None = None, ledger: list[dict[str, Any]] | None = None) -> dict[tuple[str, str | None, str], GraduationRatios]` — keyed by `(actor_id, lane, action)` where `actor_id = actor.kind + ":" + actor.id` and `lane` may be `None`. For each deduped event in the cell: approval-unchanged numerator = `decision=='approved'`, denominator = `decision ∈ {approved,edited,rejected}` (pending/`expired`/absent proposal excluded); outcome-held numerator = `status=='ok'`, denominator = `status ∈ {ok,failed}` (`unknown`/absent excluded); review-confirmed numerator = `verdict=='confirmed'`, denominator = `verdict ∈ {confirmed,wrong}` (`unknown`/absent excluded). `sample_count` = number of deduped events in the cell. Calling with an explicit `ledger=` skips the file read.

**Steps:**

- [ ] **1. Write the failing test for `_identity` + last-write-wins dedup + org_events-row immunity.** Append to `test_consequence.py`:

   ```python
   from framework.fidelity.consequence import (
       _identity,
       read_ledger,
       compute_ratios,
       GraduationRatios,
   )


   class TestReadLedgerDedup:
       def test_identity_tuple_shape(self):
           ev = _act_event()
           assert _identity(ev) == (
               "officer:cos", "drafted-reply", "thread-abc",
               "2026-06-18T08:00:00+00:00",
           )

       def test_empty_log_returns_empty(self, event_log_dir):
           assert read_ledger() == []

       def test_enrichment_supersedes_same_identity(self, event_log_dir):
           emit_consequence(
               ts="2026-06-18T08:00:00+00:00",
               actor={"kind": "officer", "id": "cos"},
               lane="polads", action="drafted-reply", subject="thread-abc",
               proposal={"required": True, "decision": None, "decided_at": None},
           )
           emit_consequence(
               ts="2026-06-18T08:00:00+00:00",
               actor={"kind": "officer", "id": "cos"},
               lane="polads", action="drafted-reply", subject="thread-abc",
               proposal={"required": True, "decision": "approved",
                         "decided_at": "2026-06-18T08:05:00+00:00"},
               outcome={"status": "ok", "evidence": "sent-xyz"},
           )
           events = read_ledger()
           assert len(events) == 1  # collapsed to last write
           assert events[0]["proposal"]["decision"] == "approved"
           assert events[0]["outcome"]["status"] == "ok"

       def test_distinct_identities_not_collapsed(self, event_log_dir):
           emit_consequence(
               ts="2026-06-18T08:00:00+00:00",
               actor={"kind": "officer", "id": "cos"},
               lane="polads", action="drafted-reply", subject="t1",
           )
           emit_consequence(
               ts="2026-06-18T08:00:00+00:00",
               actor={"kind": "officer", "id": "cos"},
               lane="polads", action="drafted-reply", subject="t2",
           )
           assert len(read_ledger()) == 2

       def test_since_filter_inclusive(self, event_log_dir):
           emit_consequence(
               ts="2026-06-18T07:00:00+00:00",
               actor={"kind": "pipe", "id": "x"}, lane=None,
               action="a", subject="old",
           )
           emit_consequence(
               ts="2026-06-18T09:00:00+00:00",
               actor={"kind": "pipe", "id": "x"}, lane=None,
               action="a", subject="new",
           )
           events = read_ledger(since="2026-06-18T08:00:00+00:00")
           assert [e["subject"] for e in events] == ["new"]

       def test_ignores_colocated_org_events_row(self, event_log_dir):
           # A valid consequence row...
           emit_consequence(
               ts="2026-06-18T08:00:00+00:00",
               actor={"kind": "officer", "id": "cos"},
               lane="polads", action="drafted-reply", subject="t1",
           )
           # ...and a hand-written org_events-shaped row (string actor) that
           # could only co-exist if the filenames collided. The reader must
           # skip it, not crash on actor.get('kind').
           bad = ('{"id":"e1","event_type":"mission_created",'
                  '"actor":"captain","payload":{},"created_at":'
                  '"2026-06-18T08:00:00+00:00"}')
           f = list(Path(event_log_dir).glob("consequence-events-*.jsonl"))[0]
           with open(f, "a") as fh:
               fh.write(bad + "\n")
           events = read_ledger()
           assert len(events) == 1
           assert events[0]["subject"] == "t1"
   ```

   Run and show FAIL:
   ```
   python3 -m pytest framework/fidelity/tests/test_consequence.py::TestReadLedgerDedup -q
   ```
   Expected: `ImportError: cannot import name '_identity'` → collection error, 0 passed.

- [ ] **2. Minimal implementation: `_identity` + `read_ledger`.** Add to the import block near the top of `consequence.py`:
   ```python
   from dataclasses import dataclass
   ```
   Then append to `consequence.py`:
   ```python
   def _is_consequence_row(event: Any) -> bool:
       """True only for a row shaped like a consequence event (dict actor with a
       kind). Lets read_ledger skip a co-located org_events row (string actor)
       defensively, even though the distinct filename family makes a real
       collision impossible."""
       return (
           isinstance(event, dict)
           and isinstance(event.get("actor"), dict)
           and "action" in event
           and "subject" in event
       )


   def _identity(event: dict[str, Any]) -> tuple[str, str, str, str]:
       """The last-write-wins identity tuple: (actor, action, subject, ts).

       actor is flattened to 'kind:id' so the full actor object participates in
       the identity exactly as docs/consequence-ledger.md specifies. Enrichment
       events carry the SAME tuple as the original; the reader keeps the last.
       """
       actor = event.get("actor")
       if isinstance(actor, dict):
           actor_id = f"{actor.get('kind')}:{actor.get('id')}"
       else:
           actor_id = f"{actor}:"  # defensive — non-dict actor never collides
       return (actor_id, event.get("action", ""), event.get("subject", ""),
               event.get("ts", ""))


   def read_ledger(since: str | None = None) -> list[dict[str, Any]]:
       """Read the consequence ledger, deduped by identity (last-write-wins).

       Reads every consequence-events-*.jsonl in $CABINET_EVENT_LOG_DIR, skips
       any non-consequence row, sorts chronologically by ts (ISO strings sort
       lexicographically), collapses each identity tuple to its LAST write, and
       returns the surviving events. `since` keeps only events with ts >= since
       (inclusive). Missing dir → []. The JSONL is the guaranteed record; this is
       the single read path graduation math uses.
       """
       log_dir = _consequence_log_dir()
       if not log_dir.exists():
           return []

       rows: list[dict[str, Any]] = []
       for log_file in sorted(log_dir.glob("consequence-events-*.jsonl")):
           with open(log_file) as f:
               for line in f:
                   line = line.strip()
                   if not line:
                       continue
                   try:
                       ev = json.loads(line)
                   except json.JSONDecodeError:
                       continue
                   if _is_consequence_row(ev):
                       rows.append(ev)

       # Stable sort by ts so last-write-wins respects chronology; equal-ts
       # writes keep file+line read order (a later enrichment line still wins).
       rows.sort(key=lambda e: e.get("ts", ""))

       collapsed: dict[tuple[str, str, str, str], dict[str, Any]] = {}
       for ev in rows:
           collapsed[_identity(ev)] = ev  # later assignment overwrites earlier

       events = list(collapsed.values())
       if since is not None:
           events = [e for e in events if e.get("ts", "") >= since]
       events.sort(key=lambda e: e.get("ts", ""))
       return events
   ```

   Run and show PASS:
   ```
   python3 -m pytest framework/fidelity/tests/test_consequence.py::TestReadLedgerDedup -q
   ```
   Expected: `6 passed`.

- [ ] **3. Commit.**
   ```
   git add framework/fidelity/consequence.py framework/fidelity/tests/test_consequence.py
   git commit -m "feat(fidelity): F0 ledger reader with last-write-wins identity dedup

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01LLg211Y8u2kHCkn5v9pEMQ"
   ```

- [ ] **4. Write the failing test for `compute_ratios` (three ratios per cell + unmeasured = None).** Append to `test_consequence.py`:

   ```python
   class TestComputeRatios:
       def _emit_decided(self, ts, subject, decision, status, verdict,
                         actor=None, lane="polads", action="drafted-reply"):
           actor = actor or {"kind": "officer", "id": "cos"}
           outcome = None
           if status is not None:
               outcome = {"status": status,
                          "evidence": None if status == "unknown" else "ev"}
           review = None
           if verdict is not None:
               review = {"verdict": verdict}
           emit_consequence(
               ts=ts, actor=actor, lane=lane, action=action, subject=subject,
               proposal={"required": True, "decision": decision,
                         "decided_at": "2026-06-18T08:05:00+00:00"
                         if decision else None},
               outcome=outcome, review=review,
           )

       def test_approval_unchanged_rate(self, event_log_dir):
           # 2 approved, 1 edited, 1 rejected → 2/4 = 0.5
           self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", None, None)
           self._emit_decided("2026-06-18T08:01:00+00:00", "b", "approved", None, None)
           self._emit_decided("2026-06-18T08:02:00+00:00", "c", "edited", None, None)
           self._emit_decided("2026-06-18T08:03:00+00:00", "d", "rejected", None, None)
           cell = compute_ratios()[("officer:cos", "polads", "drafted-reply")]
           assert cell.sample_count == 4
           assert cell.approval_unchanged_rate == 0.5
           assert cell.approved == 2 and cell.edited == 1 and cell.rejected == 1

       def test_pending_and_expired_excluded_from_approval_denominator(self, event_log_dir):
           self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", None, None)
           self._emit_decided("2026-06-18T08:01:00+00:00", "b", "expired", None, None)
           self._emit_decided("2026-06-18T08:02:00+00:00", "c", None, None, None)  # pending
           cell = compute_ratios()[("officer:cos", "polads", "drafted-reply")]
           assert cell.approval_unchanged_rate == 1.0  # 1 approved / 1 decided

       def test_outcome_held_rate(self, event_log_dir):
           # 3 ok, 1 failed, 1 unknown → 3/4 = 0.75 (unknown excluded)
           self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", "ok", None)
           self._emit_decided("2026-06-18T08:01:00+00:00", "b", "approved", "ok", None)
           self._emit_decided("2026-06-18T08:02:00+00:00", "c", "approved", "ok", None)
           self._emit_decided("2026-06-18T08:03:00+00:00", "d", "approved", "failed", None)
           self._emit_decided("2026-06-18T08:04:00+00:00", "e", "approved", "unknown", None)
           cell = compute_ratios()[("officer:cos", "polads", "drafted-reply")]
           assert cell.outcome_held_rate == 0.75
           assert cell.ok == 3 and cell.failed == 1

       def test_review_confirmed_rate(self, event_log_dir):
           # 1 confirmed, 1 wrong, 1 unknown → 1/2 = 0.5
           self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", "ok", "confirmed")
           self._emit_decided("2026-06-18T08:01:00+00:00", "b", "approved", "ok", "wrong")
           self._emit_decided("2026-06-18T08:02:00+00:00", "c", "approved", "ok", "unknown")
           cell = compute_ratios()[("officer:cos", "polads", "drafted-reply")]
           assert cell.review_confirmed_rate == 0.5
           assert cell.confirmed == 1 and cell.wrong == 1

       def test_unmeasured_cell_rates_are_none(self, event_log_dir):
           emit_consequence(
               ts="2026-06-18T08:00:00+00:00",
               actor={"kind": "pipe", "id": "x"}, lane=None,
               action="auto-closed-commitment", subject="cmt-1",
           )
           cell = compute_ratios()[("pipe:x", None, "auto-closed-commitment")]
           assert cell.approval_unchanged_rate is None
           assert cell.outcome_held_rate is None
           assert cell.review_confirmed_rate is None
           assert cell.sample_count == 1

       def test_cells_split_by_actor_lane_action(self, event_log_dir):
           self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", None, None,
                              actor={"kind": "officer", "id": "cos"}, lane="polads")
           self._emit_decided("2026-06-18T08:01:00+00:00", "b", "approved", None, None,
                              actor={"kind": "officer", "id": "cto"}, lane="stephie")
           self._emit_decided("2026-06-18T08:02:00+00:00", "c", "approved", None, None,
                              actor={"kind": "officer", "id": "cos"}, lane="polads",
                              action="triaged-board")
           cells = compute_ratios()
           assert ("officer:cos", "polads", "drafted-reply") in cells
           assert ("officer:cto", "stephie", "drafted-reply") in cells
           assert ("officer:cos", "polads", "triaged-board") in cells
           assert len(cells) == 3

       def test_dedup_applied_before_counting(self, event_log_dir):
           self._emit_decided("2026-06-18T08:00:00+00:00", "a", None, None, None)
           self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", "ok", "confirmed")
           cell = compute_ratios()[("officer:cos", "polads", "drafted-reply")]
           assert cell.sample_count == 1
           assert cell.approval_unchanged_rate == 1.0
           assert cell.outcome_held_rate == 1.0
           assert cell.review_confirmed_rate == 1.0

       def test_compute_accepts_explicit_ledger(self, event_log_dir):
           self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", "ok", "confirmed")
           ledger = read_ledger()
           cells = compute_ratios(ledger=ledger)
           assert cells[("officer:cos", "polads", "drafted-reply")].sample_count == 1
   ```

   Run and show FAIL:
   ```
   python3 -m pytest framework/fidelity/tests/test_consequence.py::TestComputeRatios -q
   ```
   Expected: `ImportError: cannot import name 'compute_ratios'` (or `GraduationRatios`) → collection error, 0 passed.

- [ ] **5. Minimal implementation: `GraduationRatios` + `compute_ratios`.** Append to `consequence.py`:

   ```python
   @dataclass
   class GraduationRatios:
       """The three graduation ratios for one (actor, lane, action) cell.

       The raw counts are dataclass FIELDS; the three rates are computed
       @property accessors (float | None) over them — a field and a same-named
       property cannot coexist. A rate is None when its denominator is 0 — an
       UNMEASURED dimension. Per docs/fidelity-harness-design-2026-06-18.md
       §"No-silent-caps", an unmeasured cell must read as a visible None, never a
       silent 0.0/1.0.
       """
       approved: int = 0
       edited: int = 0
       rejected: int = 0
       ok: int = 0
       failed: int = 0
       confirmed: int = 0
       wrong: int = 0
       sample_count: int = 0

       @property
       def approval_unchanged_rate(self) -> float | None:
           denom = self.approved + self.edited + self.rejected
           return (self.approved / denom) if denom else None

       @property
       def outcome_held_rate(self) -> float | None:
           denom = self.ok + self.failed
           return (self.ok / denom) if denom else None

       @property
       def review_confirmed_rate(self) -> float | None:
           denom = self.confirmed + self.wrong
           return (self.confirmed / denom) if denom else None


   def compute_ratios(
       since: str | None = None,
       ledger: list[dict[str, Any]] | None = None,
   ) -> dict[tuple[str, str | None, str], GraduationRatios]:
       """Compute the three graduation ratios per (actor, lane, action) cell.

       The consequence ledger is the ONLY input (no per-source special-casing).
       Events are read deduped via read_ledger() unless an explicit `ledger` is
       passed. Per cell:
         - approval-unchanged = approved / (approved + edited + rejected)
         - outcome-held       = ok / (ok + failed)
         - review-confirmed   = confirmed / (confirmed + wrong)
       Pending/expired proposals, unknown outcomes, and unknown verdicts are
       excluded from their denominators (not counted as failures).
       """
       events = ledger if ledger is not None else read_ledger(since=since)

       cells: dict[tuple[str, str | None, str], GraduationRatios] = {}
       for ev in events:
           actor = ev.get("actor") or {}
           actor_id = f"{actor.get('kind')}:{actor.get('id')}"
           key = (actor_id, ev.get("lane"), ev.get("action", ""))
           cell = cells.setdefault(key, GraduationRatios())
           cell.sample_count += 1

           decision = (ev.get("proposal") or {}).get("decision")
           if decision == "approved":
               cell.approved += 1
           elif decision == "edited":
               cell.edited += 1
           elif decision == "rejected":
               cell.rejected += 1

           status = (ev.get("outcome") or {}).get("status")
           if status == "ok":
               cell.ok += 1
           elif status == "failed":
               cell.failed += 1

           verdict = (ev.get("review") or {}).get("verdict")
           if verdict == "confirmed":
               cell.confirmed += 1
           elif verdict == "wrong":
               cell.wrong += 1

       return cells
   ```

   Run and show PASS:
   ```
   python3 -m pytest framework/fidelity/tests/test_consequence.py::TestComputeRatios -q
   ```
   Expected: `8 passed`.

- [ ] **6. Run the whole F0 suite to confirm the module is green end-to-end.**
   ```
   python3 -m pytest framework/fidelity/tests/test_consequence.py -q
   ```
   Expected: `43 passed` (2 + 14 + 8 + 6 + 8 + 5).

- [ ] **7. Commit.**
   ```
   git add framework/fidelity/consequence.py framework/fidelity/tests/test_consequence.py
   git commit -m "feat(fidelity): F0 graduation ratios per (actor,lane,action) cell

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01LLg211Y8u2kHCkn5v9pEMQ"
   ```

---

## Task 3 — wire F0 into docs (docs-track-code rule)

**Files:**
- Modify: `/Users/nate/captains-cabinet/docs/consequence-ledger.md` (mark the emitter/reader as built; name the module + entry points + the distinct filename)
- Modify: `/Users/nate/captains-cabinet/docs/fidelity-harness-design-2026-06-18.md` (gap-list item 4 to past tense; component §5 realized interface; F0 phasing build-status)
- Test: none (doc-only change; verified by grep, not pytest)

**Interfaces:**
- Consumes: nothing at runtime — this is the mandatory same-change doc sync (CLAUDE.md §"Docs Must Track the Code").
- Produces: docs that name the real artifacts: module `framework/fidelity/consequence.py`; functions `emit_consequence(...)`, `validate_consequence(...)`, `read_ledger(...)`, `compute_ratios(...)`; class `GraduationRatios`; the distinct ledger filename `consequence-events-YYYY-MM-DD.jsonl`.

**Steps:**

- [ ] **1. Read the two docs to locate the exact lines.** Read `/Users/nate/captains-cabinet/docs/consequence-ledger.md` in full (esp. the "Storage and access" section) and read `/Users/nate/captains-cabinet/docs/fidelity-harness-design-2026-06-18.md` lines 50-56 (gap-list item 4), 143-149 (component §5), and 263-267 (F-internal phasing). The current stale phrasings are: line ~53-54 "but has no\n   emitter. F builds it"; line ~147 "`emit(event)`; validates against the JSON schema; append-only JSONL + (optionally) Postgres"; line ~265 "`consequence.py` emitter + ledger reader (shared infra; unblocks all)".

- [ ] **2. Edit design-doc gap-list item 4 (lines ~52-55) to past tense** — this is the source of the stale "has no emitter / F builds it" claim. Replace the text:
   ```
   schema exists (`framework/schemas/consequence-event.schema.json`) but has no
      emitter. F builds it (shared infra; F is the first consumer) so graduation
      math is single-source.
   ```
   with:
   ```
   schema exists (`framework/schemas/consequence-event.schema.json`); the emitter
      is built in `framework/fidelity/consequence.py` (shared infra; F is the
      first consumer) so graduation math is single-source.
   ```

- [ ] **3. Edit design-doc component §5 (lines ~147-148) to record the realized interface.** Replace:
   ```
   - **Interface:** `emit(event)`; validates against the JSON schema; append-only
     JSONL + (optionally) Postgres, mirroring `framework/events/emitter.py`.
   ```
   with:
   ```
   - **Interface (built):** `emit_consequence(**fields)` + `validate_consequence(event)`
     + `read_ledger(since)` + `compute_ratios(since) -> {(actor,lane,action): GraduationRatios}`
     in `framework/fidelity/consequence.py`. Append-only JSONL only, distinct
     filename family `consequence-events-YYYY-MM-DD.jsonl` (never collides with
     events/emitter.py's `events-*.jsonl` in the same dir). Validation is
     hand-rolled (no `jsonschema` dep on system Python 3.9.6); Postgres deferred
     until a consumer needs it.
   ```

- [ ] **4. Edit design-doc F0 phasing line (line ~265).** Replace:
   ```
   - **F0** — `consequence.py` emitter + ledger reader (shared infra; unblocks all).
   ```
   with:
   ```
   - **F0** — `consequence.py` emitter + ledger reader (shared infra; unblocks all)
     — **built**: `framework/fidelity/consequence.py`
     (`emit_consequence`/`validate_consequence`/`read_ledger`/`compute_ratios`,
     `GraduationRatios`).
   ```

- [ ] **5. Edit `docs/consequence-ledger.md` "Storage and access" section** to point at the now-built module: name `framework/fidelity/consequence.py`, the distinct filename family `consequence-events-YYYY-MM-DD.jsonl`, the `(actor, action, subject, ts)` last-write-wins reader `read_ledger`, and the three-ratio reader `compute_ratios` (→ `GraduationRatios`). Keep the existing identity-tuple + `additionalProperties:false` text intact (the code implements it). Add, under the bullets, one line: `> Built: `framework/fidelity/consequence.py` — `emit_consequence` validates (hand-rolled, no jsonschema dep) then appends to `consequence-events-YYYY-MM-DD.jsonl`; `read_ledger` + `compute_ratios` are the graduation read path.`

- [ ] **6. Grep to prove no stale "no emitter" claim survives (multiline-tolerant) and the new names resolve.**
   ```
   grep -rzoP 'has no\s+emitter' docs/ ; \
   grep -rn "F builds it" docs/ ; \
   grep -rn "framework/fidelity/consequence.py\|emit_consequence\|compute_ratios" docs/
   ```
   Expected: the first two greps print nothing (zero stale claims — note `has no emitter` wraps a newline in the source, so the `-z` multiline flag is required); the third grep shows the new references in both edited docs.

- [ ] **7. Commit (docs in the same lineage as the code they describe).**
   ```
   git add docs/consequence-ledger.md docs/fidelity-harness-design-2026-06-18.md
   git commit -m "docs(fidelity): F0 emitter+reader built — sync consequence-ledger + design refs

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01LLg211Y8u2kHCkn5v9pEMQ"
   ```

> **F0 boundary the plan deliberately holds:** F0 ships ONLY `framework/fidelity/consequence.py` (emitter + reader). It does NOT touch `framework/events/emitter.py`'s `VALID_EVENT_TYPES` — the `fidelity_case_evaluated` / `fidelity_case_leak_detected` org-event types are an F1 concern (Task 7), distinct from the consequence ledger built here. Postgres/Store mirroring is intentionally excluded: the consequence ledger is JSONL-only by design (§5; the optional Postgres path is deferred until a consumer needs it, keeping F0 dependency-free and test-isolated). No officer logic, no scorer, no Voyage, no `claude -p` — those land in F1.


---

## Task 4 — `retro` shim: import the screenpipe retrodiction engine into `framework/fidelity/`

**Files:**
- Create: `/Users/nate/captains-cabinet/framework/fidelity/retro.py` (explicit-spec import shim that loads the retrodiction lib by file path and re-exports the reused symbols — we import/port, never re-derive `score_case`/`judge_decision`/`cusum`/`score_draft`/`extract_cases`)
- Test: `/Users/nate/captains-cabinet/framework/fidelity/tests/test_retro_shim.py`

> Package markers `framework/fidelity/__init__.py` and `framework/fidelity/tests/__init__.py` already exist from Task 1 — do not recreate them.

**Interfaces:**
- Consumes: `~/.screenpipe/pipes/retrodiction/lib.py` symbols — `extract_cases`, `score_case`, `judge_decision`, `score_draft`, `author_centroid`, `aggregate`, `cusum`, `mechanics_flags`, `parse_json_block`, `lessons_before`, `parse_conversations`, `cosine`, and constants `JUDGE_SYSTEM`, `BASELINE_SYSTEM`, `RETRO_ADDENDUM`, `LLM_MODEL`. The lib's own bootstrap inserts `_PIPES` + `_shared` on `sys.path`, so importing it transitively pulls `sp_lib`, `commitments_lib`, `draft_lib`.
- Produces: `framework.fidelity.retro` module re-exporting those names; module-level `RETRO_PIPE_DIR: Path` (resolved retrodiction dir, override via `CABINET_RETRO_PIPE_DIR`) and `retro_available() -> bool`.

> **Import-hardening (minor fix):** load `lib.py` via an explicit `importlib.util.spec_from_file_location("retrodiction_lib", RETRO_PIPE_DIR / "lib.py")` rather than a bare `import lib`. A bare `import lib` would register the screenpipe module as `sys.modules['lib']` for the whole test process and could be shadowed by (or shadow) any other top-level `lib` on `sys.path` during a combined `pytest framework/` run. The explicit spec gives it the unique name `retrodiction_lib`. The lib's own `sys.path` bootstrap (for `sp_lib`/`commitments_lib`) still runs at module load, which is what we want.

> **Python-version constraint (minor fix):** `framework/fidelity` transitively imports the screenpipe retrodiction lib (and `retro.py`, `scorer.py`, `benchmark.py`, `run_f1.py` all depend on it). That lib is authored for Python 3.12 but currently imports cleanly under the framework's 3.9.6 because of `from __future__ import annotations`. This is a real constraint, not luck: the lib MUST remain importable under the framework interpreter. The shim test below includes `test_retro_lib_imports_under_framework_python` so any future 3.10+-only construct upstream fails loudly at the F1 boundary, not mid-batch.

**Steps:**

- [ ] **1. Write the failing test.** Create `/Users/nate/captains-cabinet/framework/fidelity/tests/test_retro_shim.py`:

   ```python
   from __future__ import annotations

   import pytest

   from framework.fidelity import retro


   class TestRetroShim:
       def test_reexports_scoring_symbols(self):
           for name in (
               "extract_cases", "score_case", "judge_decision", "score_draft",
               "author_centroid", "aggregate", "cusum", "mechanics_flags",
               "parse_json_block", "lessons_before", "parse_conversations",
               "cosine",
           ):
               assert hasattr(retro, name), f"retro shim missing {name}"
               assert callable(getattr(retro, name)), f"{name} not callable"

       def test_reexports_constants(self):
           assert isinstance(retro.JUDGE_SYSTEM, str) and retro.JUDGE_SYSTEM
           assert isinstance(retro.BASELINE_SYSTEM, str) and retro.BASELINE_SYSTEM
           assert isinstance(retro.RETRO_ADDENDUM, str) and retro.RETRO_ADDENDUM
           assert retro.LLM_MODEL == "claude-sonnet-4-6"

       def test_judge_system_is_decision_only(self):
           # The decision-only contract is the sacred reuse boundary (style is
           # scored via Voyage, not the judge). Lock the marker phrasing.
           assert "IGNORE style" in retro.JUDGE_SYSTEM
           assert "MODEL-DRAFTED reply" in retro.JUDGE_SYSTEM

       def test_retro_available_true_when_pipe_present(self):
           assert retro.retro_available() is True
           assert retro.RETRO_PIPE_DIR.joinpath("lib.py").exists()

       def test_retro_lib_imports_under_framework_python(self):
           # Guards the 3.9.6 import boundary: a future 3.10+-only construct in
           # the upstream lib must fail HERE, not mid-batch. Touch a real symbol.
           assert callable(retro.extract_cases)
           assert isinstance(retro.cosine([1.0, 0.0], [1.0, 0.0]), float)
   ```

- [ ] **2. Run it, show expected FAIL (module does not exist yet):**

   ```
   python3 -m pytest framework/fidelity/tests/test_retro_shim.py -q
   ```
   Expected: `ModuleNotFoundError: No module named 'framework.fidelity.retro'` → collection error, 0 passed.

- [ ] **3. Minimal implementation.** Create `/Users/nate/captains-cabinet/framework/fidelity/retro.py`:

   ```python
   """Thin shim that imports the screenpipe retrodiction scoring engine into the
   Cabinet's framework namespace.

   The fidelity harness REUSES retrodiction's leak-safe scoring logic
   (extract_cases / score_case / judge_decision / cusum / score_draft /
   author_centroid / aggregate / mechanics_flags) — it does NOT re-derive it
   (docs/fidelity-harness-design-2026-06-18.md §25-37). This module is the single
   import seam; the rest of framework/fidelity/ imports from
   `framework.fidelity.retro`, never from a hardcoded screenpipe path.

   The lib is loaded via an EXPLICIT importlib spec (unique module name
   'retrodiction_lib') so it can never shadow or be shadowed by another
   top-level `lib` on sys.path during a combined `pytest framework/` run. The
   lib's own bootstrap (inserting _PIPES/_shared on sys.path for sp_lib /
   commitments_lib / draft_lib) still runs at load.

   IMPORTANT (3.9.6 boundary): this module transitively imports the retrodiction
   lib, which must remain importable under the framework interpreter (system
   Python 3.9.6). test_retro_shim.py asserts this so an upstream 3.10+-only
   construct fails loudly at the F1 boundary, not mid-batch.
   """

   from __future__ import annotations

   import importlib.util
   import os
   import sys
   from pathlib import Path

   # Resolve the retrodiction pipe dir. Override via CABINET_RETRO_PIPE_DIR for
   # tests / non-default installs; default to the canonical screenpipe location.
   RETRO_PIPE_DIR = Path(
       os.environ.get(
           "CABINET_RETRO_PIPE_DIR",
           str(Path.home() / ".screenpipe" / "pipes" / "retrodiction"),
       )
   ).expanduser()
   _SHARED_DIR = RETRO_PIPE_DIR.parent / "_shared"


   def retro_available() -> bool:
       """True iff the retrodiction lib is importable from RETRO_PIPE_DIR."""
       return (RETRO_PIPE_DIR / "lib.py").exists()


   # Put the pipe dir + its _shared deps on sys.path (idempotent) so the lib's
   # transitive imports (sp_lib, commitments_lib, draft_lib) resolve.
   for _p in (str(RETRO_PIPE_DIR), str(_SHARED_DIR), str(RETRO_PIPE_DIR.parent)):
       if _p not in sys.path and Path(_p).exists():
           sys.path.insert(0, _p)

   _spec = importlib.util.spec_from_file_location(
       "retrodiction_lib", str(RETRO_PIPE_DIR / "lib.py")
   )
   if _spec is None or _spec.loader is None:  # pragma: no cover - install guard
       raise ImportError(f"retrodiction lib not found at {RETRO_PIPE_DIR / 'lib.py'}")
   _retro = importlib.util.module_from_spec(_spec)
   sys.modules["retrodiction_lib"] = _retro
   _spec.loader.exec_module(_retro)

   # Re-export the reused surface (import/port — do NOT rebuild these).
   extract_cases = _retro.extract_cases
   score_case = _retro.score_case
   judge_decision = _retro.judge_decision
   score_draft = _retro.score_draft
   author_centroid = _retro.author_centroid
   aggregate = _retro.aggregate
   cusum = _retro.cusum
   mechanics_flags = _retro.mechanics_flags
   parse_json_block = _retro.parse_json_block
   lessons_before = _retro.lessons_before
   parse_conversations = _retro.parse_conversations
   cosine = _retro.cosine

   JUDGE_SYSTEM = _retro.JUDGE_SYSTEM
   BASELINE_SYSTEM = _retro.BASELINE_SYSTEM
   RETRO_ADDENDUM = _retro.RETRO_ADDENDUM
   LLM_MODEL = _retro.LLM_MODEL

   __all__ = [
       "RETRO_PIPE_DIR", "retro_available",
       "extract_cases", "score_case", "judge_decision", "score_draft",
       "author_centroid", "aggregate", "cusum", "mechanics_flags",
       "parse_json_block", "lessons_before", "parse_conversations", "cosine",
       "JUDGE_SYSTEM", "BASELINE_SYSTEM", "RETRO_ADDENDUM", "LLM_MODEL",
   ]
   ```

- [ ] **4. Run it, show expected PASS:**

   ```
   python3 -m pytest framework/fidelity/tests/test_retro_shim.py -q
   ```
   Expected: `5 passed`.

- [ ] **5. Commit:**

   ```
   git add framework/fidelity/retro.py framework/fidelity/tests/test_retro_shim.py
   git commit -m "feat(fidelity): F1 retro shim — explicit-spec import of retrodiction engine into framework.fidelity

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01LLg211Y8u2kHCkn5v9pEMQ"
   ```


---

## Task 5 — OAuth `claude -p` headless LLM call (replaces `ANTHROPIC_API_KEY` curl)

**Files:**
- Create: `/Users/nate/captains-cabinet/framework/fidelity/oauth_llm.py`
- Test: `/Users/nate/captains-cabinet/framework/fidelity/tests/test_oauth_llm.py`

**Interfaces:**
- Consumes: the `claude` CLI on PATH (headless print mode); env `CLAUDE_CODE_OAUTH_TOKEN` (GitHub Actions / headless) — NEVER `ANTHROPIC_API_KEY`. Reuses `framework.fidelity.retro.parse_json_block`.
- Produces:
  - `oauth_raw_llm(payload, system, max_tokens=1500, model="claude-sonnet-4-6") -> str | None` — drop-in for retrodiction's `raw_llm` (same `(payload, system)` arg shape) but routes via `claude -p`.
  - `oauth_json_llm(payload, system, max_tokens=400, model="claude-sonnet-4-6") -> dict | None` — drop-in for `cl.call_llm` (returns parsed JSON or None); this is the `llm=` callable passed to `judge_decision`.
  - `_build_argv(system: str, model: str) -> list[str]` (testable command builder).
  - `class OAuthUnavailableError(RuntimeError)`.

**Steps:**

- [ ] **1. Write the failing test.** Create `/Users/nate/captains-cabinet/framework/fidelity/tests/test_oauth_llm.py`:

   ```python
   from __future__ import annotations

   import json
   import subprocess

   import pytest

   from framework.fidelity import oauth_llm


   class TestArgv:
       def test_builds_claude_print_argv_no_api_key(self):
           argv = oauth_llm._build_argv("SYS PROMPT", "claude-sonnet-4-6")
           assert argv[0] == "claude"
           assert "-p" in argv
           assert "--append-system-prompt" in argv
           assert "SYS PROMPT" in argv
           assert "--model" in argv
           assert "claude-sonnet-4-6" in argv

       def test_argv_never_references_anthropic_api_key(self):
           argv = oauth_llm._build_argv("SYS", "claude-sonnet-4-6")
           assert all("ANTHROPIC_API_KEY" not in a for a in argv)


   class TestRawLlm:
       def test_returns_stdout_text(self, monkeypatch):
           def fake_run(argv, **kw):
               assert argv[0] == "claude"
               assert "ANTHROPIC_API_KEY" not in kw.get("env", {})
               return subprocess.CompletedProcess(argv, 0, stdout="hello reply", stderr="")
           monkeypatch.setattr(oauth_llm.subprocess, "run", fake_run)
           out = oauth_llm.oauth_raw_llm("payload", "system")
           assert out == "hello reply"

       def test_returns_none_on_nonzero_exit(self, monkeypatch):
           def fake_run(argv, **kw):
               return subprocess.CompletedProcess(argv, 1, stdout="", stderr="quota")
           monkeypatch.setattr(oauth_llm.subprocess, "run", fake_run)
           assert oauth_llm.oauth_raw_llm("p", "s") is None

       def test_returns_none_on_timeout(self, monkeypatch):
           def fake_run(argv, **kw):
               raise subprocess.TimeoutExpired(argv, 185)
           monkeypatch.setattr(oauth_llm.subprocess, "run", fake_run)
           assert oauth_llm.oauth_raw_llm("p", "s") is None

       def test_returns_none_when_cli_missing(self, monkeypatch):
           def fake_run(argv, **kw):
               raise FileNotFoundError("claude not on PATH")
           monkeypatch.setattr(oauth_llm.subprocess, "run", fake_run)
           assert oauth_llm.oauth_raw_llm("p", "s") is None


   class TestJsonLlm:
       def test_parses_json_verdict(self, monkeypatch):
           verdict = {"verdict": "match", "rationale": "same call",
                      "what_diverged": "", "real_decision": "ok", "draft_decision": "ok"}
           monkeypatch.setattr(oauth_llm, "oauth_raw_llm",
                               lambda p, s, max_tokens=400, model="claude-sonnet-4-6":
                               "```json\n" + json.dumps(verdict) + "\n```")
           out = oauth_llm.oauth_json_llm("payload", "system")
           assert out == verdict

       def test_returns_none_when_unparseable(self, monkeypatch):
           monkeypatch.setattr(oauth_llm, "oauth_raw_llm",
                               lambda p, s, max_tokens=400, model="claude-sonnet-4-6": "not json")
           assert oauth_llm.oauth_json_llm("p", "s") is None
   ```

- [ ] **2. Run it, show expected FAIL:**

   ```
   python3 -m pytest framework/fidelity/tests/test_oauth_llm.py -q
   ```
   Expected: `ModuleNotFoundError: No module named 'framework.fidelity.oauth_llm'` → collection error, 0 passed.

- [ ] **3. Minimal implementation.** Create `/Users/nate/captains-cabinet/framework/fidelity/oauth_llm.py`:

   ```python
   """OAuth-only headless Claude call for the fidelity harness.

   The locked architecture (docs/fidelity-harness-design-2026-06-18.md §59-72)
   reaches Claude via the OAuth/Code path everywhere — the judge runs as a
   `claude -p` headless agent billing the Max pool (CLAUDE_CODE_OAUTH_TOKEN in
   CI). There is NO ANTHROPIC_API_KEY. This module is the drop-in replacement for
   retrodiction's curl+x-api-key raw_llm / call_llm, preserving the
   (payload, system) call shape so JUDGE_SYSTEM and judge_decision are reused
   verbatim.
   """

   from __future__ import annotations

   import os
   import subprocess
   from typing import Any

   from framework.fidelity.retro import parse_json_block

   _DEFAULT_MODEL = "claude-sonnet-4-6"
   _TIMEOUT_S = 185


   class OAuthUnavailableError(RuntimeError):
       """Raised when neither an interactive OAuth login nor
       CLAUDE_CODE_OAUTH_TOKEN is available for headless invocation."""


   def _build_argv(system: str, model: str) -> list[str]:
       """Construct the `claude -p` headless argv. The system prompt is appended
       (never a positional); the user payload is piped on stdin by the caller. No
       API-key flag is ever added — auth is OAuth (token in env or logged-in
       session)."""
       return [
           "claude", "-p",
           "--model", model,
           "--append-system-prompt", system,
           "--output-format", "text",
       ]


   def oauth_raw_llm(payload: str, system: str, max_tokens: int = 1500,
                     model: str = _DEFAULT_MODEL) -> str | None:
       """Plain-text Claude call via `claude -p` (OAuth). Drop-in for
       retrodiction.raw_llm — same (payload, system) shape. Returns text or None.
       max_tokens is accepted for signature parity; `claude -p` manages its own
       output budget."""
       argv = _build_argv(system, model)
       # Inherit env so CLAUDE_CODE_OAUTH_TOKEN (CI) or the local OAuth session is
       # used. Strip ANTHROPIC_API_KEY so a stray key can never silently bill the
       # pay-as-you-go path instead of the Max pool.
       env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
       try:
           r = subprocess.run(
               argv, input=payload, capture_output=True, text=True,
               timeout=_TIMEOUT_S, env=env,
           )
       except (subprocess.TimeoutExpired, FileNotFoundError):
           return None
       if r.returncode != 0:
           return None
       out = (r.stdout or "").strip()
       return out or None


   def oauth_json_llm(payload: str, system: str, max_tokens: int = 400,
                      model: str = _DEFAULT_MODEL) -> dict[str, Any] | None:
       """JSON Claude call via OAuth. Drop-in for cl.call_llm — pass as the `llm=`
       arg to retrodiction.judge_decision. Returns the parsed dict or None."""
       text = oauth_raw_llm(payload, system, max_tokens=max_tokens, model=model)
       return parse_json_block(text)
   ```

- [ ] **4. Run it, show expected PASS:**

   ```
   python3 -m pytest framework/fidelity/tests/test_oauth_llm.py -q
   ```
   Expected: `8 passed`.

- [ ] **5. Commit:**

   ```
   git add framework/fidelity/oauth_llm.py framework/fidelity/tests/test_oauth_llm.py
   git commit -m "feat(fidelity): F1 OAuth claude -p headless LLM — drop-in for retrodiction raw_llm/call_llm, no ANTHROPIC_API_KEY

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01LLg211Y8u2kHCkn5v9pEMQ"
   ```

---

## Task 6 — Case model + anti-leakage cutoff guard (the sacred boundary)

**Files:**
- Create: `/Users/nate/captains-cabinet/framework/fidelity/types.py` (`Case`, `OfficerDecision` dataclasses)
- Create: `/Users/nate/captains-cabinet/framework/fidelity/leakguard.py` (cutoff filter + post-decision leak scan + `LeakageDetectedError`)
- Test: `/Users/nate/captains-cabinet/framework/fidelity/tests/test_leakguard.py`

**Interfaces:**
- Consumes: a retrodiction case dict `{case_id, reply_key, slug, person, channel, language, reply_ts, subject, n_prior, thread_before, real_reply}` (from `retro.extract_cases`); `thread_before` message dicts `{slug, person, date, direction, who, source, to, cc, text}`.
- Produces:
  - `@dataclass Case` with fields `case_id, lane, decision_type, situation_ref, ground_truth, endorsement, cutoff_ts, source, held_out` plus `slug, person, channel, language, thread_before, real_reply`, classmethod `from_retro_case(rc, lane="send-1to1-reply", decision_type="reply") -> Case` (sets `cutoff_ts = rc["reply_ts"]`, `ground_truth = {"real_reply": rc["real_reply"]}`, `held_out = True`), and `to_retro_case() -> dict` (projects back to the dict shape `score_case`/`judge_decision` expect).
  - `@dataclass OfficerDecision` with `decision: dict | str, rationale: str, chain: list[dict]`.
  - `filter_mcp_result(result, cutoff_ts) -> Any` — recursively redacts any dict/list item whose `ts`/`date`/`edit_date`/`reply_ts`/`created_at` is `>= cutoff_ts` (lexicographic ISO compare). Logs each redaction to stderr. **Note: this is the F4 brain-bridge hook — it is fully built + unit-tested here but is NOT wired into `run_case` in F1 (no live MCP chain exists in F1; the live F1 guards are `assert_thread_pre_cutoff` (pre) + `scan_for_leaks` (post)).**
  - `assert_thread_pre_cutoff(thread_before, cutoff_ts) -> None` — raises `LeakageDetectedError` if any message `date >= cutoff_ts` (mirrors retrodiction `test_cutoff_no_post_reply_leakage`; equal-ts is a leak).
  - `scan_for_leaks(decision_text, thread_before, cutoff_ts) -> list[str]` — flags any ISO timestamp `>= cutoff_ts` in the decision text; returns leaked signal strings or `[]`.
  - `class LeakageDetectedError(RuntimeError)`.

**Steps:**

- [ ] **1. Write the failing test.** Create `/Users/nate/captains-cabinet/framework/fidelity/tests/test_leakguard.py`:

   ```python
   from __future__ import annotations

   import pytest

   from framework.fidelity import leakguard
   from framework.fidelity.types import Case, OfficerDecision

   CUTOFF = "2026-06-10T12:00:00+00:00"


   def _retro_case():
       return {
           "case_id": "abc1234567",
           "reply_key": "msgraph|MID1",
           "slug": "ulrik",
           "person": "Ulrik",
           "channel": "msgraph",
           "language": "da",
           "reply_ts": CUTOFF,
           "subject": "Re: lon",
           "n_prior": 3,
           "thread_before": [
               {"slug": "ulrik", "person": "Ulrik", "date": "2026-06-09T08:00:00+00:00",
                "direction": "received", "who": "Ulrik <u@x>", "source": "msgraph",
                "to": "", "cc": "", "text": "kan vi snakke lon?"},
           ],
           "real_reply": "Ja, lad os tage det fredag.",
       }


   class TestCaseModel:
       def test_from_retro_case_sets_cutoff_and_ground_truth(self):
           c = Case.from_retro_case(_retro_case())
           assert c.cutoff_ts == CUTOFF
           assert c.ground_truth == {"real_reply": "Ja, lad os tage det fredag."}
           assert c.lane == "send-1to1-reply"
           assert c.decision_type == "reply"
           assert c.held_out is True
           assert c.channel == "msgraph" and c.slug == "ulrik"

       def test_to_retro_case_roundtrips_scoring_keys(self):
           c = Case.from_retro_case(_retro_case())
           rc = c.to_retro_case()
           assert rc["case_id"] == "abc1234567"
           assert rc["reply_ts"] == CUTOFF
           assert rc["channel"] == "msgraph"
           assert rc["real_reply"] == "Ja, lad os tage det fredag."
           assert rc["thread_before"] == c.thread_before

       def test_officer_decision_shape(self):
           d = OfficerDecision(decision="draft text", rationale="why", chain=[])
           assert d.decision == "draft text"
           assert d.chain == []


   class TestFilterMcpResult:
       def test_redacts_items_at_or_after_cutoff(self):
           result = {"hits": [
               {"date": "2026-06-09T08:00:00+00:00", "text": "before"},
               {"date": "2026-06-10T12:00:00+00:00", "text": "AT cutoff — leak"},
               {"date": "2026-06-11T09:00:00+00:00", "text": "after — leak"},
           ]}
           out = leakguard.filter_mcp_result(result, CUTOFF)
           kept = out["hits"]
           assert len(kept) == 1
           assert kept[0]["text"] == "before"

       def test_redacts_by_edit_date_and_reply_ts_keys(self):
           result = [
               {"edit_date": "2026-06-11T00:00:00+00:00", "v": "leak"},
               {"reply_ts": "2026-06-09T00:00:00+00:00", "v": "ok"},
           ]
           out = leakguard.filter_mcp_result(result, CUTOFF)
           assert len(out) == 1 and out[0]["v"] == "ok"

       def test_passes_through_timestampless_items(self):
           result = {"voice": "tone notes with no timestamp"}
           assert leakguard.filter_mcp_result(result, CUTOFF) == result


   class TestThreadCutoffAssertion:
       def test_clean_thread_passes(self):
           leakguard.assert_thread_pre_cutoff(_retro_case()["thread_before"], CUTOFF)

       def test_equal_ts_is_a_leak(self):
           msgs = [{"date": CUTOFF, "text": "equal-ts leak"}]
           with pytest.raises(leakguard.LeakageDetectedError):
               leakguard.assert_thread_pre_cutoff(msgs, CUTOFF)

       def test_after_ts_is_a_leak(self):
           msgs = [{"date": "2026-06-11T00:00:00+00:00", "text": "after"}]
           with pytest.raises(leakguard.LeakageDetectedError):
               leakguard.assert_thread_pre_cutoff(msgs, CUTOFF)


   class TestScanForLeaks:
       def test_flags_post_cutoff_timestamp_in_decision_text(self):
           text = "I will reply, scheduling for 2026-06-11T09:00:00+00:00 as discussed."
           leaks = leakguard.scan_for_leaks(text, _retro_case()["thread_before"], CUTOFF)
           assert any("2026-06-11" in s for s in leaks)

       def test_clean_decision_text_no_leaks(self):
           text = "Ja, lad os finde en tid."
           assert leakguard.scan_for_leaks(text, _retro_case()["thread_before"], CUTOFF) == []
   ```

- [ ] **2. Run it, show expected FAIL:**

   ```
   python3 -m pytest framework/fidelity/tests/test_leakguard.py -q
   ```
   Expected: `ModuleNotFoundError: No module named 'framework.fidelity.types'` → collection error, 0 passed.

- [ ] **3. Minimal implementation.** Create `/Users/nate/captains-cabinet/framework/fidelity/types.py`:

   ```python
   """Dataclasses for the fidelity harness (Case, OfficerDecision).

   Case mirrors docs/fidelity-harness-design-2026-06-18.md §96-98 plus the
   retrodiction-derived context needed to drive + score the reply cell.
   OfficerDecision is the captain-facing capture from officer_runner (§121-125).
   """

   from __future__ import annotations

   from dataclasses import dataclass, field
   from typing import Any


   @dataclass
   class Case:
       case_id: str
       lane: str
       decision_type: str
       situation_ref: str
       ground_truth: dict[str, Any]
       endorsement: str
       cutoff_ts: str
       source: str
       held_out: bool
       # retrodiction-derived context for the reply cell
       slug: str = ""
       person: str = ""
       channel: str = ""
       language: str = ""
       thread_before: list[dict] = field(default_factory=list)
       real_reply: str = ""

       @classmethod
       def from_retro_case(cls, rc: dict, lane: str = "send-1to1-reply",
                           decision_type: str = "reply") -> "Case":
           """Build a Case from a retrodiction extract_cases() dict. cutoff_ts is
           the held-out reply timestamp — the sacred anti-leakage boundary."""
           return cls(
               case_id=rc["case_id"],
               lane=lane,
               decision_type=decision_type,
               situation_ref=rc.get("reply_key", rc["case_id"]),
               ground_truth={"real_reply": rc["real_reply"]},
               endorsement="unknown",
               cutoff_ts=rc["reply_ts"],
               source="retrodiction",
               held_out=True,
               slug=rc.get("slug", ""),
               person=rc.get("person", ""),
               channel=rc.get("channel", ""),
               language=rc.get("language", ""),
               thread_before=rc.get("thread_before", []),
               real_reply=rc["real_reply"],
           )

       def to_retro_case(self) -> dict:
           """Project back to the dict shape retrodiction's score_case/judge expect."""
           return {
               "case_id": self.case_id,
               "reply_key": self.situation_ref,
               "slug": self.slug,
               "person": self.person,
               "channel": self.channel,
               "language": self.language,
               "reply_ts": self.cutoff_ts,
               "thread_before": self.thread_before,
               "real_reply": self.real_reply,
           }


   @dataclass
   class OfficerDecision:
       decision: dict | str
       rationale: str
       chain: list[dict] = field(default_factory=list)
   ```

   Create `/Users/nate/captains-cabinet/framework/fidelity/leakguard.py`:

   ```python
   """Anti-leakage guard — the sacred boundary
   (docs/fidelity-harness-design-2026-06-18.md §214-225).

   The officer-under-test must see NOTHING timestamped >= cutoff_ts. The brain
   bridge has no cutoff parameter today, so the guard is implemented OUTSIDE the
   MCP. F1 uses two LIVE guards: (1) assert the reconstructed thread is strictly
   pre-cutoff, and (2) post-scan the officer's decision text for leaked
   post-cutoff signals. filter_mcp_result is the THIRD guard, built + tested here
   but reserved for F4 when the live brain chain is wired (F1 has no live MCP
   chain). Any breach hard-fails the case — we never silently score a leaked case
   (§238).
   """

   from __future__ import annotations

   import re
   import sys
   from typing import Any

   # Keys whose value is a timestamp we compare against the cutoff.
   _TS_KEYS = ("ts", "date", "edit_date", "reply_ts", "created_at", "resolved_ts")
   _ISO_RE = re.compile(
       r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:?\d{2}|Z)?"
   )


   class LeakageDetectedError(RuntimeError):
       """A post-cutoff timestamp or held-out artifact crossed the guard. The
       case is hard-failed and never scored."""


   def _item_ts(item: dict) -> str | None:
       for k in _TS_KEYS:
           v = item.get(k)
           if isinstance(v, str) and _ISO_RE.match(v):
               return v
       return None


   def filter_mcp_result(result: Any, cutoff_ts: str) -> Any:
       """Recursively drop any dict/list item whose timestamp is >= cutoff_ts.
       ISO timestamps sort lexicographically, so string compare is correct for
       same-offset UTC. Logs each redaction to stderr for the audit trail.

       F4 hook: this is the live-MCP-result redactor. F1 does NOT call it
       (no live brain chain); F1's live guards are assert_thread_pre_cutoff +
       scan_for_leaks."""
       if isinstance(result, dict):
           ts = _item_ts(result)
           if ts is not None and ts >= cutoff_ts:
               print(f"[leakguard] redacted post-cutoff item ts={ts} >= {cutoff_ts}",
                     file=sys.stderr)
               return None
           return {k: filter_mcp_result(v, cutoff_ts) for k, v in result.items()}
       if isinstance(result, list):
           out = []
           for item in result:
               filtered = filter_mcp_result(item, cutoff_ts)
               if filtered is None:
                   continue
               out.append(filtered)
           return out
       return result


   def assert_thread_pre_cutoff(thread_before: list[dict], cutoff_ts: str) -> None:
       """Hard-fail if any reconstructed message is timestamped >= cutoff_ts.
       Equal-ts is a leak (mirrors retrodiction test_cutoff_no_post_reply_leakage)."""
       for m in thread_before:
           d = m.get("date") or ""
           if d and d >= cutoff_ts:
               raise LeakageDetectedError(
                   f"thread message dated {d} >= cutoff {cutoff_ts} (case is leaked)")


   def scan_for_leaks(decision_text: str, thread_before: list[dict],
                      cutoff_ts: str) -> list[str]:
       """Post-decision scan: flag any ISO timestamp in the officer's output that
       is >= cutoff_ts (the officer cannot legitimately know a post-cutoff time).
       Returns leaked signal strings or [] if clean."""
       leaks: list[str] = []
       for ts in _ISO_RE.findall(decision_text or ""):
           if ts >= cutoff_ts:
               leaks.append(ts)
       return leaks
   ```

- [ ] **4. Run it, show expected PASS:**

   ```
   python3 -m pytest framework/fidelity/tests/test_leakguard.py -q
   ```
   Expected: `12 passed`.

- [ ] **5. Commit:**

   ```
   git add framework/fidelity/types.py framework/fidelity/leakguard.py framework/fidelity/tests/test_leakguard.py
   git commit -m "feat(fidelity): F1 Case/OfficerDecision model + sacred anti-leakage cutoff guard

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01LLg211Y8u2kHCkn5v9pEMQ"
   ```


---

## Task 7 — Register the two fidelity org-event types in the emitter (snake_case)

**Files:**
- Modify: `/Users/nate/captains-cabinet/framework/events/emitter.py` (add `fidelity_case_evaluated`, `fidelity_case_leak_detected` to `VALID_EVENT_TYPES` + `_AGGREGATE_MAP`)
- Test: `/Users/nate/captains-cabinet/framework/fidelity/tests/test_event_types.py`

> **Naming fix (minor):** the org-event `event_type` is snake_case (`fidelity_case_evaluated`, `fidelity_case_leak_detected`) to match every existing `VALID_EVENT_TYPES` entry and the snake_case convention. `_resolve_aggregate` does `event_type.split("_", 1)[0]` for unmapped types — a kebab-case type would yield a nonsensical aggregate prefix. We add both types to `_AGGREGATE_MAP` so `aggregate_type='fidelity'` is meaningful, keyed on `case_id`. The consequence-event `action` field (a different field, on the consequence ledger) keeps kebab-case `fidelity-case-evaluated` / `fidelity-case-leak-detected` — that is correct and unchanged.

**Interfaces:**
- Consumes: `framework.events.emitter.VALID_EVENT_TYPES: frozenset[str]`, `_AGGREGATE_MAP: dict`, `emit(event_type, actor, payload=None, parent_id=None) -> dict`.
- Produces: two newly-valid org-event types (emit no longer raises `ValueError`), each mapped to `("fidelity", "case_id")`.

**Steps:**

- [ ] **1. Write the failing test.** Create `/Users/nate/captains-cabinet/framework/fidelity/tests/test_event_types.py`:

   ```python
   from __future__ import annotations

   import pytest

   from framework.events import emitter


   @pytest.fixture(autouse=True)
   def event_log_dir(tmp_path, monkeypatch):
       monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
       monkeypatch.delenv("DATABASE_URL", raising=False)


   class TestFidelityEventTypes:
       def test_case_evaluated_is_valid(self):
           assert "fidelity_case_evaluated" in emitter.VALID_EVENT_TYPES

       def test_leak_detected_is_valid(self):
           assert "fidelity_case_leak_detected" in emitter.VALID_EVENT_TYPES

       def test_emit_case_evaluated_does_not_raise(self):
           ev = emitter.emit("fidelity_case_evaluated", actor="chair",
                             payload={"case_id": "abc1234567"})
           assert ev["event_type"] == "fidelity_case_evaluated"
           assert ev["id"]

       def test_aggregate_resolves_to_fidelity_case(self):
           agg_type, agg_id = emitter._resolve_aggregate(
               "fidelity_case_evaluated", {"case_id": "abc1234567"})
           assert agg_type == "fidelity"
           assert agg_id == "abc1234567"

       def test_emit_unknown_fidelity_type_still_raises(self):
           with pytest.raises(ValueError):
               emitter.emit("fidelity_bogus", actor="chair", payload={})
   ```

- [ ] **2. Run it, show expected FAIL:**

   ```
   python3 -m pytest framework/fidelity/tests/test_event_types.py -q
   ```
   Expected: `test_case_evaluated_is_valid` + `test_leak_detected_is_valid` + `test_aggregate_resolves_to_fidelity_case` FAIL (AssertionError); `test_emit_case_evaluated_does_not_raise` FAILS with ValueError. Roughly `4 failed, 1 passed`.

- [ ] **3. Minimal implementation.** In `/Users/nate/captains-cabinet/framework/events/emitter.py`, add the two types to the `VALID_EVENT_TYPES` frozenset (place a new block right after the `# Measurement` block that ends with `"eval_failed",`):

   ```python
       # Fidelity harness (F) — officer-under-test evaluation + leak guard
       "fidelity_case_evaluated",      # blind officer decision captured for a held-out case
       "fidelity_case_leak_detected",  # anti-leakage breach → case hard-failed, never scored
   ```

   And add both to `_AGGREGATE_MAP` (so the prefix-split fallback is never hit):

   ```python
       "fidelity_case_evaluated":     ("fidelity",    "case_id"),
       "fidelity_case_leak_detected": ("fidelity",    "case_id"),
   ```

- [ ] **4. Run it, show expected PASS:**

   ```
   python3 -m pytest framework/fidelity/tests/test_event_types.py -q
   ```
   Expected: `5 passed`.

- [ ] **5. Commit:**

   ```
   git add framework/events/emitter.py framework/fidelity/tests/test_event_types.py
   git commit -m "feat(events): register fidelity_case_evaluated + fidelity_case_leak_detected (snake_case + aggregate map)

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01LLg211Y8u2kHCkn5v9pEMQ"
   ```

---

## Task 8 — `fidelity_events`: consequence-event builders + dual-emit for fidelity cases

> **Ownership-conflict fix (major):** F0 owns `framework/fidelity/consequence.py` (the generic consequence emitter/reader). This F1 task does NOT create a second `consequence.py`; it creates `framework/fidelity/fidelity_events.py` — a thin fidelity-specific BUILDER that constructs the two consequence-event payloads and emits them through BOTH ledgers: the consequence ledger (F0's `emit_consequence`, which validates) and the org-event ledger (the F0-substrate `framework.events.emitter.emit`, for org-runtime drill-down).
>
> **jsonschema-removal fix (blocker):** there is NO `import jsonschema` anywhere. Validation reuses F0's hand-rolled `framework.fidelity.consequence.validate_consequence` (raises `ConsequenceValidationError`). `emit_consequence` already validates internally, so a separate validate step is only exposed for the build-then-inspect tests.

**Files:**
- Create: `/Users/nate/captains-cabinet/framework/fidelity/fidelity_events.py`
- Test: `/Users/nate/captains-cabinet/framework/fidelity/tests/test_fidelity_events.py`

**Interfaces:**
- Consumes: `framework.fidelity.consequence.emit_consequence` + `validate_consequence` + `ConsequenceValidationError` (F0); `framework.events.emitter.emit` (F0 substrate / org-event ledger); `framework.fidelity.types.OfficerDecision`.
- Produces:
  - `build_case_evaluated(case_id, officer, lane, decision, evidence) -> dict` — a consequence-event dict with `actor={"kind":"officer","id":officer}`, `lane`, `action="fidelity-case-evaluated"` (kebab on the consequence ledger), `subject=case_id`, `refs=[case_id]`, `proposal={"required": False}`, `outcome={"status":"ok","evidence":evidence}`, `review={"verdict":"unknown"}`, `ts` ISO-UTC.
  - `build_case_leaked(case_id, officer, lane, signals) -> dict` — `action="fidelity-case-leak-detected"`, `subject=case_id`, `refs=[case_id]`, `proposal={"required": False}`, `outcome={"status":"failed","evidence": "leaked: " + ", ".join(signals)}`, `review={"verdict":"unknown"}`.
  - `validate_event(event) -> None` — delegates to F0's `validate_consequence` (raises `ConsequenceValidationError` on drift). Exposed so a built dict can be inspected before emit in tests.
  - `emit_case_evaluated(case_id, officer, lane, decision, evidence) -> dict` and `emit_case_leaked(case_id, officer, lane, signals) -> dict` — build the consequence-event, send it through F0's `emit_consequence` (validates + appends to the consequence ledger), ALSO emit the matching snake_case org-event via `events.emitter.emit` with the consequence dict as payload, and return the consequence dict.

> **The `ts` vs org-emitter `created_at` seam:** the consequence-event schema's `ts` is the domain timestamp. The org emitter wraps its own envelope `{id, event_type, actor, payload, parent_id, created_at}` and takes the consequence dict as its `payload`. `emit_consequence` writes the consequence dict to the consequence ledger (with validation); the org-event is a parallel drill-down record. The consequence ledger is the graduation read path; the org-event ledger is the org-runtime audit trail.

**Steps:**

- [ ] **1. Write the failing test.** Create `/Users/nate/captains-cabinet/framework/fidelity/tests/test_fidelity_events.py`:

   ```python
   from __future__ import annotations

   from pathlib import Path

   import pytest

   from framework.fidelity import fidelity_events
   from framework.fidelity.consequence import ConsequenceValidationError
   from framework.fidelity.types import OfficerDecision


   @pytest.fixture(autouse=True)
   def event_log_dir(tmp_path, monkeypatch):
       monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
       monkeypatch.delenv("DATABASE_URL", raising=False)
       return tmp_path


   class TestBuilders:
       def test_case_evaluated_is_valid(self):
           d = OfficerDecision(decision="draft", rationale="why", chain=[])
           ev = fidelity_events.build_case_evaluated(
               "abc1234567", "chair", "send-1to1-reply", d, evidence="chainhash:deadbeef")
           fidelity_events.validate_event(ev)  # must not raise
           assert ev["actor"] == {"kind": "officer", "id": "chair"}
           assert ev["action"] == "fidelity-case-evaluated"
           assert ev["subject"] == "abc1234567"
           assert ev["proposal"] == {"required": False}
           assert ev["outcome"]["status"] == "ok"
           assert ev["outcome"]["evidence"] == "chainhash:deadbeef"
           assert ev["review"]["verdict"] == "unknown"
           assert ev["refs"] == ["abc1234567"]

       def test_case_leaked_is_valid_and_failed(self):
           ev = fidelity_events.build_case_leaked(
               "abc1234567", "chair", "send-1to1-reply", ["2026-06-11T09:00:00+00:00"])
           fidelity_events.validate_event(ev)
           assert ev["action"] == "fidelity-case-leak-detected"
           assert ev["outcome"]["status"] == "failed"
           assert "2026-06-11" in ev["outcome"]["evidence"]

       def test_additional_property_rejected(self):
           ev = fidelity_events.build_case_evaluated(
               "x1", "chair", "lane", OfficerDecision("d", "r", []), evidence="e")
           ev["bogus"] = 1
           with pytest.raises(ConsequenceValidationError):
               fidelity_events.validate_event(ev)


   class TestEmit:
       def test_emit_case_evaluated_writes_consequence_ledger(self, event_log_dir):
           d = OfficerDecision(decision="draft", rationale="why", chain=[])
           out = fidelity_events.emit_case_evaluated(
               "abc1234567", "chair", "send-1to1-reply", d, evidence="h:1")
           assert out["action"] == "fidelity-case-evaluated"
           cfiles = list(Path(event_log_dir).glob("consequence-events-*.jsonl"))
           assert cfiles, "no consequence ledger file written"
           ofiles = list(Path(event_log_dir).glob("events-2*.jsonl"))
           assert ofiles, "no org-event ledger file written"

       def test_emit_case_leaked_status_failed(self, event_log_dir):
           out = fidelity_events.emit_case_leaked(
               "abc1234567", "chair", "send-1to1-reply", ["leaksig"])
           assert out["outcome"]["status"] == "failed"
   ```

- [ ] **2. Run it, show expected FAIL:**

   ```
   python3 -m pytest framework/fidelity/tests/test_fidelity_events.py -q
   ```
   Expected: `ModuleNotFoundError: No module named 'framework.fidelity.fidelity_events'` → collection error, 0 passed.

- [ ] **3. Minimal implementation.** Create `/Users/nate/captains-cabinet/framework/fidelity/fidelity_events.py`:

   ```python
   """Fidelity consequence-event builders + dual-emit (F0 consumer).

   Builds the two F1 consequence-event records — blind case evaluation and
   anti-leakage hard-fail — and emits them through BOTH ledgers so graduation
   math (consequence ledger) and org-runtime drill-down (org-event ledger) stay
   in sync. This is NOT the F0 emitter: it is a thin fidelity-specific BUILDER on
   top of it.

   - Consequence ledger: framework.fidelity.consequence.emit_consequence
     (validates hand-rolled — NO jsonschema dep — then appends to
     consequence-events-*.jsonl). The graduation read path.
   - Org-event ledger: framework.events.emitter.emit with the snake_case event
     type (fidelity_case_evaluated / fidelity_case_leak_detected) and the
     consequence dict as payload. The org-runtime audit trail.
   """

   from __future__ import annotations

   from datetime import datetime, timezone
   from typing import Any

   from framework.events.emitter import emit as _emit_org_event
   from framework.fidelity.consequence import (
       emit_consequence,
       validate_consequence,
   )
   from framework.fidelity.types import OfficerDecision


   def _now() -> str:
       return datetime.now(timezone.utc).isoformat()


   def validate_event(event: dict[str, Any]) -> None:
       """Validate a fidelity consequence-event dict via F0's hand-rolled
       validator. Raises ConsequenceValidationError on drift (unknown field, bad
       enum, broken invariant)."""
       validate_consequence(event)


   def build_case_evaluated(case_id: str, officer: str, lane: str,
                            decision: OfficerDecision, evidence: str) -> dict[str, Any]:
       """Consequence-event for a blind officer decision captured on a held-out
       case. proposal.required=False (eval is below the approval bar);
       outcome.status='ok' with evidence (the decision-chain hash); review
       pending. action is kebab-case on the consequence ledger."""
       return {
           "ts": _now(),
           "actor": {"kind": "officer", "id": officer},
           "lane": lane,
           "action": "fidelity-case-evaluated",
           "subject": case_id,
           "refs": [case_id],
           "proposal": {"required": False},
           "outcome": {"status": "ok", "evidence": evidence},
           "review": {"verdict": "unknown"},
       }


   def build_case_leaked(case_id: str, officer: str, lane: str,
                         signals: list[str]) -> dict[str, Any]:
       """Consequence-event for an anti-leakage hard-fail. outcome.status='failed'
       with the leaked signals as evidence; the case is never scored."""
       return {
           "ts": _now(),
           "actor": {"kind": "officer", "id": officer},
           "lane": lane,
           "action": "fidelity-case-leak-detected",
           "subject": case_id,
           "refs": [case_id],
           "proposal": {"required": False},
           "outcome": {"status": "failed", "evidence": "leaked: " + ", ".join(signals)},
           "review": {"verdict": "unknown"},
       }


   def _emit_both(consequence_event: dict[str, Any], officer: str,
                  org_event_type: str) -> dict[str, Any]:
       """Append to the consequence ledger (validates) + mirror to the org-event
       ledger for drill-down. Returns the consequence dict."""
       emit_consequence(
           ts=consequence_event["ts"],
           actor=consequence_event["actor"],
           lane=consequence_event["lane"],
           action=consequence_event["action"],
           subject=consequence_event["subject"],
           refs=consequence_event["refs"],
           proposal=consequence_event["proposal"],
           outcome=consequence_event["outcome"],
           review=consequence_event["review"],
       )
       _emit_org_event(org_event_type, actor=officer, payload=consequence_event)
       return consequence_event


   def emit_case_evaluated(case_id: str, officer: str, lane: str,
                           decision: OfficerDecision, evidence: str) -> dict[str, Any]:
       """Build + dual-emit a fidelity-case-evaluated event."""
       ev = build_case_evaluated(case_id, officer, lane, decision, evidence)
       return _emit_both(ev, officer, "fidelity_case_evaluated")


   def emit_case_leaked(case_id: str, officer: str, lane: str,
                        signals: list[str]) -> dict[str, Any]:
       """Build + dual-emit a fidelity-case-leak-detected event."""
       ev = build_case_leaked(case_id, officer, lane, signals)
       return _emit_both(ev, officer, "fidelity_case_leak_detected")
   ```

- [ ] **4. Run it, show expected PASS:**

   ```
   python3 -m pytest framework/fidelity/tests/test_fidelity_events.py -q
   ```
   Expected: `5 passed`.

- [ ] **5. Commit:**

   ```
   git add framework/fidelity/fidelity_events.py framework/fidelity/tests/test_fidelity_events.py
   git commit -m "feat(fidelity): F1 fidelity_events builder — consequence + org-event dual-emit (reuses F0 validate, no jsonschema)

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01LLg211Y8u2kHCkn5v9pEMQ"
   ```


---

## Task 9 — `officer_runner.run_case`: drive the officer blind, capture decision, no side effects, hard-fail on leak

**Files:**
- Create: `/Users/nate/captains-cabinet/framework/fidelity/officer_runner.py`
- Test: `/Users/nate/captains-cabinet/framework/fidelity/tests/test_officer_runner.py`

**Interfaces:**
- Consumes: `framework.fidelity.types.Case` / `OfficerDecision`; `framework.fidelity.oauth_llm.oauth_raw_llm`; `framework.fidelity.leakguard` (`assert_thread_pre_cutoff`, `scan_for_leaks`, `LeakageDetectedError`); `framework.fidelity.fidelity_events.emit_case_evaluated` / `emit_case_leaked`; `framework.fidelity.officer_prompt.build_eval_system` / `format_situation` (Task 10).
- Produces:
  - `EVAL_MODE_RULES: str` — the non-negotiable eval-mode + no-side-effects + cutoff system addendum.
  - `run_case(case, officer_role, llm=oauth_raw_llm, emit_events=True) -> OfficerDecision` — assert thread pre-cutoff (hard-fail + emit leak if breached), build the eval system prompt, call the officer (OAuth `claude -p`), capture the draft as `OfficerDecision.decision`, scan output for leaks (hard-fail + emit leak if breached), emit `fidelity-case-evaluated`, return the decision. Raises `LeakageDetectedError` on any breach.

> **The eval path (ground finding):** F1 invokes the officer via `claude -p` headless with the role definition + eval rules as the system prompt and the case piped as the user message; the runner captures stdout as the draft. The brain bridge is NOT live-wired in F1 (no cutoff param exists yet — F4 adds it). F1's officer drafts from the situation text under the eval prompt; the leak guard wraps both ends (pre-thread assertion + post-output scan). `llm` is injectable so tests run without invoking the real CLI. `filter_mcp_result` is intentionally NOT called here — it is the F4 hook (see Task 6).

**Steps:**

- [ ] **1. Write the failing test.** Create `/Users/nate/captains-cabinet/framework/fidelity/tests/test_officer_runner.py`:

   ```python
   from __future__ import annotations

   from pathlib import Path

   import pytest

   from framework.fidelity import officer_runner, leakguard
   from framework.fidelity.types import Case, OfficerDecision


   @pytest.fixture(autouse=True)
   def event_log_dir(tmp_path, monkeypatch):
       monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
       monkeypatch.delenv("DATABASE_URL", raising=False)
       return tmp_path


   CUTOFF = "2026-06-10T12:00:00+00:00"


   def _case():
       return Case.from_retro_case({
           "case_id": "abc1234567",
           "reply_key": "msgraph|MID1",
           "slug": "ulrik", "person": "Ulrik", "channel": "msgraph",
           "language": "da", "reply_ts": CUTOFF, "subject": "Re: lon",
           "n_prior": 3,
           "thread_before": [
               {"slug": "ulrik", "person": "Ulrik",
                "date": "2026-06-09T08:00:00+00:00", "direction": "received",
                "who": "Ulrik <u@x>", "source": "msgraph", "to": "", "cc": "",
                "text": "kan vi snakke lon?"},
           ],
           "real_reply": "Ja, lad os tage det fredag.",
       })


   class TestRunCase:
       def test_captures_draft_as_decision(self):
           fake = lambda payload, system, max_tokens=1500, model="claude-sonnet-4-6": \
               "Ja, lad os finde en tid i naeste uge."
           dec = officer_runner.run_case(_case(), "chair", llm=fake)
           assert isinstance(dec, OfficerDecision)
           assert dec.decision == "Ja, lad os finde en tid i naeste uge."
           assert dec.chain == []  # no live MCP chain in F1

       def test_eval_system_prompt_carries_eval_mode_and_cutoff(self):
           seen = {}
           def fake(payload, system, max_tokens=1500, model="claude-sonnet-4-6"):
               seen["system"] = system
               seen["payload"] = payload
               return "ok"
           officer_runner.run_case(_case(), "chair", llm=fake)
           assert "EVALUATION MODE" in seen["system"]
           assert "captured, not executed" in seen["system"]
           assert CUTOFF in seen["system"]
           # the held-out reply is never in the prompt
           assert "Ja, lad os tage det fredag." not in seen["system"]
           assert "Ja, lad os tage det fredag." not in seen["payload"]

       def test_thread_leak_hard_fails_and_emits(self, event_log_dir):
           c = _case()
           c.thread_before = [{"date": CUTOFF, "direction": "received",
                               "who": "x", "source": "msgraph", "text": "equal-ts leak"}]
           with pytest.raises(leakguard.LeakageDetectedError):
               officer_runner.run_case(c, "chair",
                                       llm=lambda *a, **k: "should never run")
           cfiles = list(Path(event_log_dir).glob("consequence-events-*.jsonl"))
           assert cfiles, "leak event not emitted"
           assert "fidelity-case-leak-detected" in cfiles[0].read_text()

       def test_output_leak_hard_fails(self):
           fake = lambda *a, **k: "Sure, meeting set for 2026-06-11T09:00:00+00:00."
           with pytest.raises(leakguard.LeakageDetectedError):
               officer_runner.run_case(_case(), "chair", llm=fake)

       def test_clean_case_emits_case_evaluated(self, event_log_dir):
           officer_runner.run_case(_case(), "chair",
                                   llm=lambda *a, **k: "Ja, fredag passer fint.")
           cfiles = list(Path(event_log_dir).glob("consequence-events-*.jsonl"))
           assert "fidelity-case-evaluated" in cfiles[0].read_text()

       def test_emit_events_false_skips_ledger(self, event_log_dir):
           officer_runner.run_case(_case(), "chair",
                                   llm=lambda *a, **k: "Ja.", emit_events=False)
           assert not list(Path(event_log_dir).glob("consequence-events-*.jsonl"))
   ```

- [ ] **2. Run it, show expected FAIL (missing officer_runner — and transitively officer_prompt, built in Task 10):**

   ```
   python3 -m pytest framework/fidelity/tests/test_officer_runner.py -q
   ```
   Expected: `ModuleNotFoundError: No module named 'framework.fidelity.officer_runner'` → collection error, 0 passed.

- [ ] **3. Minimal implementation.** Create `/Users/nate/captains-cabinet/framework/fidelity/officer_runner.py`:

   ```python
   """Officer-under-test runner (F's core,
   docs/fidelity-harness-design-2026-06-18.md §116-126).

   For one held-out Case, drive a production officer to decide BLIND — context
   reconstructed as-of cutoff_ts — in eval mode with NO side effects (drafts are
   captured, never queued/sent; no board writes). The anti-leakage guard wraps
   both ends: the reconstructed thread must be strictly pre-cutoff, and the
   officer's output is scanned for post-cutoff leakage. Any breach hard-fails the
   case and emits a fidelity-case-leak-detected event — we never silently score a
   leaked case (§238).

   F1 has no live MCP chain, so leakguard.filter_mcp_result (the live-result
   redactor) is NOT called here — that is the F4 hook. F1's live guards are the
   pre-thread assertion + the post-output scan.
   """

   from __future__ import annotations

   import hashlib

   from framework.fidelity import leakguard
   from framework.fidelity.fidelity_events import emit_case_evaluated, emit_case_leaked
   from framework.fidelity.oauth_llm import oauth_raw_llm
   from framework.fidelity.officer_prompt import build_eval_system, format_situation
   from framework.fidelity.types import Case, OfficerDecision

   EVAL_MODE_RULES = """

   # EVALUATION MODE (held-out blind test)
   You are in EVALUATION MODE. Your drafts, board updates, and commitments will be
   reviewed, not executed — proceed as if they will be sent, but they are NOT. The
   Cabinet will grade your decision. Your actions are captured, not executed. Do
   NOT call queue_draft, do NOT write to any board, do NOT send anything.

   You have NO knowledge of events at or after {cutoff_ts}. Do not consult or
   reference anything timestamped at or after that moment (search results, vault
   notes, commitments, decisions). This is a blind evaluation.

   Return ONLY the reply text Nate would have sent at that moment — no JSON, no
   commentary, no subject line."""


   def _decision_evidence(decision: OfficerDecision) -> str:
       h = hashlib.sha1(str(decision.decision).encode("utf-8", "replace")).hexdigest()[:16]
       return f"chainhash:{h}"


   def run_case(case: Case, officer_role: str, llm=oauth_raw_llm,
                emit_events: bool = True) -> OfficerDecision:
       """Drive the officer blind on one Case; return the captured OfficerDecision.
       Hard-fails (LeakageDetectedError) + emits a leak event on any cutoff
       breach."""
       # 1. PRE-execution guard: reconstructed thread must be strictly pre-cutoff.
       try:
           leakguard.assert_thread_pre_cutoff(case.thread_before, case.cutoff_ts)
       except leakguard.LeakageDetectedError as e:
           if emit_events:
               emit_case_leaked(case.case_id, officer_role, case.lane, [str(e)])
           raise

       # 2. Build the eval prompt (role def + eval rules + cutoff); drive blind.
       system = build_eval_system(case, officer_role) + \
           EVAL_MODE_RULES.format(cutoff_ts=case.cutoff_ts)
       user_msg = format_situation(case)
       draft = llm(user_msg, system) or ""

       decision = OfficerDecision(
           decision=draft,
           rationale="(captured from blind eval session)",
           chain=[],
       )

       # 3. POST-execution scan: output must carry no post-cutoff signal.
       leaks = leakguard.scan_for_leaks(draft, case.thread_before, case.cutoff_ts)
       if leaks:
           if emit_events:
               emit_case_leaked(case.case_id, officer_role, case.lane, leaks)
           raise leakguard.LeakageDetectedError(
               f"officer output leaked post-cutoff signals: {leaks}")

       # 4. Capture: emit the evaluated event (no side effects beyond the ledger).
       if emit_events:
           emit_case_evaluated(case.case_id, officer_role, case.lane, decision,
                               evidence=_decision_evidence(decision))
       return decision
   ```

- [ ] **4. Run it, show expected FAIL on the not-yet-built `officer_prompt` dependency (built in Task 10):**

   ```
   python3 -m pytest framework/fidelity/tests/test_officer_runner.py -q
   ```
   Expected: `ModuleNotFoundError: No module named 'framework.fidelity.officer_prompt'` → collection error, 0 passed. (This is the expected mid-state; Task 10 builds the dependency, then this suite goes green.)

- [ ] **5. Defer the commit to Task 10** (the import is mutual). After Task 10 lands, re-run and commit both together — see Task 10 step 5.

---

## Task 10 — `officer_prompt`: assemble the role-def eval system prompt + cutoff-safe situation text

**Files:**
- Create: `/Users/nate/captains-cabinet/framework/fidelity/officer_prompt.py`
- Test: `/Users/nate/captains-cabinet/framework/fidelity/tests/test_officer_prompt.py`

**Interfaces:**
- Consumes: `framework.fidelity.types.Case`; the officer role definition file at `.claude/agents/<role>.md` — the runtime-populated charter dir set by `load-preset.sh` as `$CABINET_ROOT/.claude/agents` (resolved relative to repo root via `CABINET_ROOT` env, default the repo root two levels up from `framework/`).
- Produces:
  - `role_definition(officer_role) -> str` — read the role def md; return its text, or a minimal fallback header if the file is absent (never crash the eval).
  - `build_eval_system(case, officer_role) -> str` — role definition + a one-line decision-type context block (`lane`, `decision_type`, counterparty). The held-out reply is NEVER included.
  - `format_situation(case, last_cap=1500, cap=600) -> str` — oldest-first, per-message `[date source] who: text` lines (cap 600 chars, last message 1500), strictly the `thread_before` only, with a leading `# HELD-OUT SITUATION (decide as-of {cutoff_ts})` header. Never includes `real_reply`.

**Steps:**

- [ ] **1. Write the failing test.** Create `/Users/nate/captains-cabinet/framework/fidelity/tests/test_officer_prompt.py`:

   ```python
   from __future__ import annotations

   import pytest

   from framework.fidelity import officer_prompt
   from framework.fidelity.types import Case

   CUTOFF = "2026-06-10T12:00:00+00:00"


   def _case():
       return Case.from_retro_case({
           "case_id": "abc1234567", "reply_key": "k", "slug": "ulrik",
           "person": "Ulrik", "channel": "msgraph", "language": "da",
           "reply_ts": CUTOFF, "subject": "Re: lon", "n_prior": 2,
           "thread_before": [
               {"slug": "ulrik", "person": "Ulrik",
                "date": "2026-06-08T08:00:00+00:00", "direction": "sent",
                "who": "Nate", "source": "msgraph", "to": "", "cc": "",
                "text": "Hej, vi tager den i naeste uge."},
               {"slug": "ulrik", "person": "Ulrik",
                "date": "2026-06-09T08:00:00+00:00", "direction": "received",
                "who": "Ulrik <u@x>", "source": "msgraph", "to": "", "cc": "",
                "text": "kan vi snakke lon paa fredag?"},
           ],
           "real_reply": "Ja, fredag passer.",
       })


   class TestRoleDefinition:
       def test_missing_role_returns_fallback_not_crash(self):
           out = officer_prompt.role_definition("nonexistent-role-xyz")
           assert isinstance(out, str) and "nonexistent-role-xyz" in out


   class TestBuildEvalSystem:
       def test_includes_lane_and_decision_type(self):
           s = officer_prompt.build_eval_system(_case(), "chair")
           assert "send-1to1-reply" in s
           assert "reply" in s

       def test_never_includes_held_out_reply(self):
           s = officer_prompt.build_eval_system(_case(), "chair")
           assert "Ja, fredag passer." not in s


   class TestFormatSituation:
       def test_oldest_first_and_both_messages_present(self):
           s = officer_prompt.format_situation(_case())
           i_first = s.index("naeste uge")
           i_last = s.index("snakke lon")
           assert i_first < i_last  # oldest-first

       def test_carries_cutoff_header(self):
           s = officer_prompt.format_situation(_case())
           assert CUTOFF in s
           assert "HELD-OUT SITUATION" in s

       def test_never_includes_held_out_reply(self):
           s = officer_prompt.format_situation(_case())
           assert "Ja, fredag passer." not in s

       def test_sent_messages_labelled_nate(self):
           s = officer_prompt.format_situation(_case())
           assert "Nate:" in s
   ```

- [ ] **2. Run it, show expected FAIL:**

   ```
   python3 -m pytest framework/fidelity/tests/test_officer_prompt.py -q
   ```
   Expected: `ModuleNotFoundError: No module named 'framework.fidelity.officer_prompt'` → collection error, 0 passed.

- [ ] **3. Minimal implementation.** Create `/Users/nate/captains-cabinet/framework/fidelity/officer_prompt.py`:

   ```python
   """Eval-mode prompt assembly for the officer-under-test.

   Builds the system prompt (officer role definition + decision-type context) and
   the cutoff-safe situation text from a Case's thread_before. The held-out reply
   (case.real_reply) is NEVER included anywhere in the prompt — that is the ground
   truth the officer must reconstruct blind."""

   from __future__ import annotations

   import os
   import re
   from pathlib import Path

   from framework.fidelity.types import Case

   _REPO_ROOT = Path(
       os.environ.get("CABINET_ROOT", str(Path(__file__).resolve().parents[2]))
   )
   _AGENTS_DIR = _REPO_ROOT / ".claude" / "agents"


   def role_definition(officer_role: str) -> str:
       """Read .claude/agents/<role>.md (the runtime-populated officer charter
       dir, set by load-preset.sh as $CABINET_ROOT/.claude/agents). If absent
       (eval running before the preset is loaded), return a minimal header —
       never crash the eval."""
       f = _AGENTS_DIR / f"{officer_role}.md"
       if f.exists():
           return f.read_text(errors="replace")
       return (f"# Officer: {officer_role}\n"
               "You are a Cabinet officer making a decision under the "
               "courses-of-action rule. (Role definition file not found; deciding "
               "from charter conventions.)")


   def build_eval_system(case: Case, officer_role: str) -> str:
       """Role definition + a decision-type context block. No held-out reply."""
       ctx = (f"\n\n# DECISION CONTEXT\nlane: {case.lane}\n"
              f"decision_type: {case.decision_type}\n"
              f"counterparty: {case.person} (channel: {case.channel}, "
              f"language: {case.language})")
       return role_definition(officer_role) + ctx


   def _clean(text: str) -> str:
       body = re.sub(r"<!--[^>]*-->", "", text or "")
       return re.sub(r"_\([^)]*\)_", "", body).strip()


   def format_situation(case: Case, last_cap: int = 1500, cap: int = 600) -> str:
       """Oldest-first situation text from thread_before only. Sent → 'Nate:',
       received → the sender's display name. The last message keeps more body."""
       msgs = case.thread_before
       lines = [f"# HELD-OUT SITUATION (decide as-of {case.cutoff_ts})",
                "The conversation below ends just before Nate replied. Draft the "
                "reply Nate would have sent at that moment.\n"]
       for i, m in enumerate(msgs):
           who = "Nate" if m.get("direction") == "sent" else \
               (m.get("who") or "").split("<")[0].strip() or case.person
           body = _clean(m.get("text") or "")
           limit = last_cap if i == len(msgs) - 1 else cap
           lines.append(f"[{(m.get('date') or '')[:16]} {m.get('source', '')}] "
                        f"{who}: {body[:limit]}")
       return "\n".join(lines)
   ```

- [ ] **4. Run it, show expected PASS, then re-run the runner suite (its dependency now exists):**

   ```
   python3 -m pytest framework/fidelity/tests/test_officer_prompt.py -q
   python3 -m pytest framework/fidelity/tests/test_officer_runner.py -q
   ```
   Expected: officer_prompt `7 passed`; officer_runner `6 passed`.

- [ ] **5. Commit both modules together (mutual import).**

   ```
   git add framework/fidelity/officer_prompt.py framework/fidelity/tests/test_officer_prompt.py framework/fidelity/officer_runner.py framework/fidelity/tests/test_officer_runner.py
   git commit -m "feat(fidelity): F1 officer_runner (blind, no-side-effects, hard-fail-on-leak) + officer_prompt (cutoff-safe situation)

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01LLg211Y8u2kHCkn5v9pEMQ"
   ```

---

## Task 11 — `scorer.score`: reuse retrodiction `score_case` (STYLE via Voyage, DECISION via OAuth judge, MECHANICS)

**Files:**
- Create: `/Users/nate/captains-cabinet/framework/fidelity/scorer.py`
- Test: `/Users/nate/captains-cabinet/framework/fidelity/tests/test_scorer.py`

**Interfaces:**
- Consumes: `framework.fidelity.retro` (`score_case`, `judge_decision`, `JUDGE_SYSTEM`); `framework.fidelity.oauth_llm.oauth_json_llm` (the OAuth judge callable; keeps `JUDGE_SYSTEM` intact); `framework.fidelity.types.Case` / `OfficerDecision`. Voyage embeddings stay the default `embedder` inside `score_case` (STYLE channel only).
- Produces:
  - `@dataclass CaseScore` with `case_id, style_win, decision_verdict, mechanics_flags, endorsement_adjusted, composite, raw`.
  - `judge_with_oauth(case_dict, clone_draft) -> dict` — calls `retro.judge_decision(case_dict, clone_draft, llm=oauth_json_llm)` so the judge runs via OAuth `claude -p`, not `ANTHROPIC_API_KEY`. Returns the verdict dict.
  - `score(case, officer_decision, baseline_draft, centroids, embedder=None, judge=None) -> CaseScore` — projects the Case back to the retro dict, runs the OAuth judge, injects the verdict via `judge_result=` into `retro.score_case` (so `score_case` does no key-based LLM call), computes `composite` (`1.0` match / `0.5` partial / `0.0` divergent|error), sets `endorsement_adjusted=False` for F1 (`endorsement="unknown"` ⇒ score vs actual; F4 wires the endorsed direction).

> Per the ground finding: `retro.score_case` returns `row["judge"]["verdict"]` (one of match/partial/divergent/error/skipped), `row["style_win"]` (bool) and `row["mechanics"]` (list). `judge_decision`'s default `llm` is `cl.call_llm` (returns a parsed dict), so `oauth_json_llm` (returns a dict) is the correct injection.

**Steps:**

- [ ] **1. Write the failing test.** Create `/Users/nate/captains-cabinet/framework/fidelity/tests/test_scorer.py`:

   ```python
   from __future__ import annotations

   import pytest

   from framework.fidelity import scorer, retro
   from framework.fidelity.types import Case, OfficerDecision

   CUTOFF = "2026-06-10T12:00:00+00:00"


   def _case():
       return Case.from_retro_case({
           "case_id": "abc1234567", "reply_key": "k", "slug": "ulrik",
           "person": "Ulrik", "channel": "msgraph", "language": "da",
           "reply_ts": CUTOFF, "subject": "s", "n_prior": 2,
           "thread_before": [
               {"slug": "ulrik", "person": "Ulrik",
                "date": "2026-06-09T08:00:00+00:00", "direction": "received",
                "who": "Ulrik <u@x>", "source": "msgraph", "to": "", "cc": "",
                "text": "kan vi snakke fredag?"},
           ],
           "real_reply": "Ja, fredag passer fint.",
       })


   # deterministic fake embedder: identical text -> identical vector -> cosine 1.0
   def _fake_embedder(texts):
       def vec(t):
           return [float(len(t or "")), 1.0, 0.0]
       return [vec(t) for t in texts]


   class TestJudgeWithOauth:
       def test_routes_judge_through_oauth(self, monkeypatch):
           captured = {}
           def fake_oauth_json(payload, system, max_tokens=400, model="claude-sonnet-4-6"):
               captured["system"] = system
               return {"verdict": "match", "rationale": "same call",
                       "what_diverged": "", "real_decision": "ja", "draft_decision": "ja"}
           monkeypatch.setattr(scorer, "oauth_json_llm", fake_oauth_json)
           out = scorer.judge_with_oauth(_case().to_retro_case(), "Ja, fredag.")
           assert out["verdict"] == "match"
           assert "IGNORE style" in captured["system"]  # JUDGE_SYSTEM kept intact


   class TestScore:
       def test_match_composite_is_one(self, monkeypatch):
           monkeypatch.setattr(scorer, "judge_with_oauth",
                               lambda cd, draft: {"verdict": "match", "rationale": "",
                                                  "what_diverged": "", "real_decision": "",
                                                  "draft_decision": ""})
           dec = OfficerDecision(decision="Ja, fredag passer fint.", rationale="", chain=[])
           centroids = {"msgraph": _fake_embedder(["x"])[0]}
           cs = scorer.score(_case(), dec, baseline_draft="Sure, sounds good.",
                             centroids=centroids, embedder=_fake_embedder)
           assert cs.decision_verdict == "match"
           assert cs.composite == 1.0
           assert cs.endorsement_adjusted is False
           assert isinstance(cs.mechanics_flags, list)

       def test_partial_composite_is_half(self, monkeypatch):
           monkeypatch.setattr(scorer, "judge_with_oauth",
                               lambda cd, draft: {"verdict": "partial", "rationale": "",
                                                  "what_diverged": "scope", "real_decision": "",
                                                  "draft_decision": ""})
           dec = OfficerDecision(decision="Maaske fredag?", rationale="", chain=[])
           cs = scorer.score(_case(), dec, baseline_draft="x",
                             centroids={"msgraph": _fake_embedder(["x"])[0]},
                             embedder=_fake_embedder)
           assert cs.composite == 0.5

       def test_divergent_composite_is_zero(self, monkeypatch):
           monkeypatch.setattr(scorer, "judge_with_oauth",
                               lambda cd, draft: {"verdict": "divergent", "rationale": "",
                                                  "what_diverged": "diff", "real_decision": "",
                                                  "draft_decision": ""})
           dec = OfficerDecision(decision="Nej, det kan jeg ikke.", rationale="", chain=[])
           cs = scorer.score(_case(), dec, baseline_draft="x",
                             centroids={"msgraph": _fake_embedder(["x"])[0]},
                             embedder=_fake_embedder)
           assert cs.composite == 0.0

       def test_style_win_when_clone_closer_than_baseline(self, monkeypatch):
           monkeypatch.setattr(scorer, "judge_with_oauth",
                               lambda cd, draft: {"verdict": "match", "rationale": "",
                                                  "what_diverged": "", "real_decision": "",
                                                  "draft_decision": ""})
           dec = OfficerDecision(decision="Ja, fredag passer fint.", rationale="", chain=[])
           cs = scorer.score(_case(), dec,
                             baseline_draft="A totally different long baseline answer here.",
                             centroids={"msgraph": _fake_embedder(["x"])[0]},
                             embedder=_fake_embedder)
           assert cs.style_win is True
   ```

- [ ] **2. Run it, show expected FAIL:**

   ```
   python3 -m pytest framework/fidelity/tests/test_scorer.py -q
   ```
   Expected: `ModuleNotFoundError: No module named 'framework.fidelity.scorer'` -> collection error, 0 passed.

- [ ] **3. Minimal implementation.** Create `/Users/nate/captains-cabinet/framework/fidelity/scorer.py`:

   ```python
   """Endorsement-aware scorer (docs/fidelity-harness-design-2026-06-18.md §127-141).

   Wraps retrodiction's three-channel score_case: STYLE (Voyage cosine vs the
   recency-weighted voice centroid - text decisions only), DECISION-MATCH (the
   tone-blind judge, run here via OAuth `claude -p` keeping JUDGE_SYSTEM intact),
   MECHANICS (deterministic flags). F1 covers the reply cell with endorsement
   'unknown' => scored vs the actual reply; F4 wires the endorsed-direction
   adjustment. The privacy fence holds: nate_model/voice inform the centroid +
   clone draft but are never emitted into a score row."""

   from __future__ import annotations

   from dataclasses import dataclass, field
   from typing import Any

   from framework.fidelity import retro
   from framework.fidelity.oauth_llm import oauth_json_llm
   from framework.fidelity.types import Case, OfficerDecision

   _COMPOSITE = {"match": 1.0, "partial": 0.5, "divergent": 0.0, "error": 0.0,
                 "skipped": 0.0}


   @dataclass
   class CaseScore:
       case_id: str
       style_win: bool
       decision_verdict: str
       mechanics_flags: list[str]
       endorsement_adjusted: bool
       composite: float
       raw: dict[str, Any] = field(default_factory=dict)


   def judge_with_oauth(case_dict: dict, clone_draft: str) -> dict:
       """Run retrodiction's decision judge via OAuth `claude -p`, keeping
       JUDGE_SYSTEM (decision-only) intact. Returns the verdict dict."""
       return retro.judge_decision(case_dict, clone_draft, llm=oauth_json_llm)


   def score(case: Case, officer_decision: OfficerDecision, baseline_draft: str,
             centroids: dict, embedder=None, judge=None) -> CaseScore:
       """Score one officer decision vs ground truth across the three channels."""
       judge = judge or judge_with_oauth
       clone_draft = officer_decision.decision if isinstance(
           officer_decision.decision, str) else str(officer_decision.decision)
       rc = case.to_retro_case()

       # DECISION via OAuth judge; inject as judge_result so score_case does no
       # ANTHROPIC_API_KEY call.
       verdict = judge(rc, clone_draft)
       row = retro.score_case(rc, clone_draft, baseline_draft, centroids,
                              judge=False, embedder=embedder, judge_result=verdict)

       decision_verdict = row["judge"]["verdict"]
       # F1: endorsement 'unknown' -> score vs actual, no adjustment.
       endorsement_adjusted = case.endorsement in ("regretted", "constrained")
       return CaseScore(
           case_id=case.case_id,
           style_win=bool(row["style_win"]),
           decision_verdict=decision_verdict,
           mechanics_flags=row["mechanics"],
           endorsement_adjusted=endorsement_adjusted,
           composite=_COMPOSITE.get(decision_verdict, 0.0),
           raw=row,
       )
   ```

- [ ] **4. Run it, show expected PASS:**

   ```
   python3 -m pytest framework/fidelity/tests/test_scorer.py -q
   ```
   Expected: `5 passed`.

- [ ] **5. Commit:**

   ```
   git add framework/fidelity/scorer.py framework/fidelity/tests/test_scorer.py
   git commit -m "feat(fidelity): F1 scorer — reuse retrodiction score_case, OAuth decision judge, Voyage STYLE only

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01LLg211Y8u2kHCkn5v9pEMQ"
   ```

---

## Task 12 — `benchmark.build_cases`: held-out reply cases over the `send-1to1-reply` universe

> **Naming fix (major):** the locked design §95-99 names this component `benchmark.py` with `build_cases(lane, decision_type, n, window)`. The plan uses exactly that file + entry point (NOT `bench_reply.py` / `build_reply_cases`). For F1 the only supported `(lane, decision_type)` is `("send-1to1-reply", "reply")`, which dispatches to the retrodiction extractor; any other pair raises `NotImplementedError` (those cells land in F3). `connectors/monday_activitylog.py` is deliberately deferred to F3 (the triage decision-type) — Task 14 records that deferral in the design doc.
>
> **Count fix (major):** the validation universe is the `send-1to1-reply` lane in `autonomy_outcomes.jsonl` = **266 rows** (NOT 176). `validation_count` returns that universe size. F1 does NOT join/pair the (truncated) autonomy rows; it rebuilds full leak-safe cases from `3-People/*/conversations.md` via the extractor and uses the autonomy count only to size/sanity-check the universe. Prose, docstrings, README, and commits all say "266-row universe; F1 validates a held-out sample" — the "176 paired" phrasing is gone everywhere.

**Files:**
- Create: `/Users/nate/captains-cabinet/framework/fidelity/benchmark.py`
- Test: `/Users/nate/captains-cabinet/framework/fidelity/tests/test_benchmark.py`

**Interfaces:**
- Consumes: `framework.fidelity.retro.extract_cases` (rebuilds full `thread_before` from `3-People/*/conversations.md` — NOT the cut-off `autonomy_outcomes.jsonl` text); the `autonomy_outcomes.jsonl` path (default `~/.screenpipe/state/autonomy_outcomes.jsonl`, override via `CABINET_AUTONOMY_OUTCOMES`) for the `send-1to1-reply` row count.
- Produces:
  - `_SUPPORTED: set[tuple[str, str]] = {("send-1to1-reply", "reply")}`.
  - `load_autonomy_rows(path=None, lane="send-1to1-reply") -> list[dict]` — reads the JSONL, returns rows whose `lane == lane` (the 266; their text is cut-off and must NOT be scored).
  - `validation_count(path=None, lane="send-1to1-reply") -> int` — count of `send-1to1-reply` rows (the universe size, ~266).
  - `build_cases(lane="send-1to1-reply", decision_type="reply", n=24, window=None, people_dir=None) -> list[Case]` — for the supported `(lane, decision_type)`, calls `retro.extract_cases(n_cases=n, people_dir=people_dir)` and maps each to `Case.from_retro_case(rc, lane=lane, decision_type=decision_type)`. `window` is accepted for design-interface parity (reserved for time-windowed extraction in later cells). Unsupported `(lane, decision_type)` → `NotImplementedError`.

**Steps:**

- [ ] **1. Write the failing test.** Create `/Users/nate/captains-cabinet/framework/fidelity/tests/test_benchmark.py`:

   ```python
   from __future__ import annotations

   import json
   from pathlib import Path

   import pytest

   from framework.fidelity import benchmark
   from framework.fidelity.types import Case


   def _write_outcomes(tmp_path) -> Path:
       rows = [
           {"ts": "2026-06-07T21:05:48+00:00", "lane": "send-1to1-reply",
            "action_id": "backfill-sent|MID1", "mode": "shadow", "source": "backfill",
            "would_text": "cut...", "nate_text": "cut...", "match": False},
           {"ts": "2026-06-07T21:05:49+00:00", "lane": "send-1to1-reply",
            "action_id": "backfill-sent|MID2", "mode": "shadow", "source": "backfill",
            "would_text": "cut...", "nate_text": "cut...", "match": True},
           {"ts": "2026-06-07T21:05:50+00:00", "lane": "some-other-lane",
            "action_id": "x", "mode": "shadow", "source": "backfill",
            "would_text": "t", "nate_text": "t", "match": False},
       ]
       p = tmp_path / "autonomy_outcomes.jsonl"
       p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
       return p


   class TestAutonomyUniverse:
       def test_filters_to_lane(self, tmp_path):
           p = _write_outcomes(tmp_path)
           rows = benchmark.load_autonomy_rows(path=p)
           assert len(rows) == 2
           assert all(r["lane"] == "send-1to1-reply" for r in rows)

       def test_validation_count_is_universe_size(self, tmp_path):
           p = _write_outcomes(tmp_path)
           assert benchmark.validation_count(path=p) == 2

       def test_missing_file_is_zero(self, tmp_path):
           assert benchmark.validation_count(path=tmp_path / "nope.jsonl") == 0


   class TestBuildCases:
       def test_maps_retro_cases_to_case_objects(self, monkeypatch):
           fake_rc = {
               "case_id": "c1", "reply_key": "k", "slug": "ulrik", "person": "Ulrik",
               "channel": "msgraph", "language": "da",
               "reply_ts": "2026-06-10T12:00:00+00:00", "subject": "s", "n_prior": 2,
               "thread_before": [{"date": "2026-06-09T00:00:00+00:00",
                                  "direction": "received", "who": "Ulrik <u@x>",
                                  "source": "msgraph", "text": "hej"}],
               "real_reply": "Ja.",
           }
           monkeypatch.setattr(benchmark.retro, "extract_cases",
                               lambda n_cases=24, people_dir=None: [fake_rc])
           cases = benchmark.build_cases(n=1)
           assert len(cases) == 1
           c = cases[0]
           assert isinstance(c, Case)
           assert c.lane == "send-1to1-reply"
           assert c.decision_type == "reply"
           assert c.cutoff_ts == "2026-06-10T12:00:00+00:00"
           assert c.real_reply == "Ja."

       def test_empty_extract_yields_no_cases(self, monkeypatch):
           monkeypatch.setattr(benchmark.retro, "extract_cases",
                               lambda n_cases=24, people_dir=None: [])
           assert benchmark.build_cases(n=0) == []

       def test_unsupported_cell_raises(self):
           with pytest.raises(NotImplementedError):
               benchmark.build_cases(lane="triage", decision_type="triage", n=1)
   ```

- [ ] **2. Run it, show expected FAIL:**

   ```
   python3 -m pytest framework/fidelity/tests/test_benchmark.py -q
   ```
   Expected: `ModuleNotFoundError: No module named 'framework.fidelity.benchmark'` -> collection error, 0 passed.

- [ ] **3. Minimal implementation.** Create `/Users/nate/captains-cabinet/framework/fidelity/benchmark.py`:

   ```python
   """Held-out case builder (the F1 benchmark - design §95-99).

   The validation universe is the send-1to1-reply lane in autonomy_outcomes.jsonl
   (~266 rows). Those rows are CUT-OFF in their text fields, so F1 does NOT score
   their text. It rebuilds full paired cases from 3-People/*/conversations.md via
   retrodiction.extract_cases (leak-safe, full thread_before) and uses the
   autonomy rows only to SIZE/sanity-check the universe (ground finding: rebuild
   from conversations.md, not from the cut-off rows).

   F1 supports exactly the reply cell ('send-1to1-reply', 'reply'); other
   (lane, decision_type) pairs raise NotImplementedError and land in F3
   (Monday activity-log connector for triage, etc.)."""

   from __future__ import annotations

   import json
   import os
   from pathlib import Path

   from framework.fidelity import retro
   from framework.fidelity.types import Case

   _SUPPORTED: set[tuple[str, str]] = {("send-1to1-reply", "reply")}

   _DEFAULT_OUTCOMES = Path(
       os.environ.get(
           "CABINET_AUTONOMY_OUTCOMES",
           str(Path.home() / ".screenpipe" / "state" / "autonomy_outcomes.jsonl"),
       )
   ).expanduser()


   def load_autonomy_rows(path: Path | None = None,
                          lane: str = "send-1to1-reply") -> list[dict]:
       """Return the autonomy_outcomes rows for the given lane (metadata only -
       text fields are cut-off and must NOT be scored)."""
       p = path or _DEFAULT_OUTCOMES
       if not p.exists():
           return []
       rows = []
       for line in p.read_text(errors="replace").splitlines():
           line = line.strip()
           if not line:
               continue
           try:
               r = json.loads(line)
           except json.JSONDecodeError:
               continue
           if r.get("lane") == lane:
               rows.append(r)
       return rows


   def validation_count(path: Path | None = None,
                        lane: str = "send-1to1-reply") -> int:
       """Size of the validation universe for the lane (the ~266-row count)."""
       return len(load_autonomy_rows(path=path, lane=lane))


   def build_cases(lane: str = "send-1to1-reply", decision_type: str = "reply",
                   n: int = 24, window=None, people_dir: Path | None = None) -> list[Case]:
       """Build held-out Cases for the (lane, decision_type) cell.

       F1: reconstructs full threads from conversations.md (leak-safe) via the
       retrodiction extractor, mapped onto the Case model. `window` is accepted
       for design-interface parity (reserved for time-windowed extraction in
       later cells). Unsupported cells raise NotImplementedError."""
       if (lane, decision_type) not in _SUPPORTED:
           raise NotImplementedError(
               f"F1 supports only {sorted(_SUPPORTED)}; "
               f"({lane!r}, {decision_type!r}) lands in F3.")
       rcs = retro.extract_cases(n_cases=n, people_dir=people_dir)
       return [Case.from_retro_case(rc, lane=lane, decision_type=decision_type)
               for rc in rcs]
   ```

- [ ] **4. Run it, show expected PASS:**

   ```
   python3 -m pytest framework/fidelity/tests/test_benchmark.py -q
   ```
   Expected: `6 passed`.

- [ ] **5. Commit:**

   ```
   git add framework/fidelity/benchmark.py framework/fidelity/tests/test_benchmark.py
   git commit -m "feat(fidelity): F1 benchmark.build_cases — held-out reply cases over the 266-row send-1to1-reply universe

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01LLg211Y8u2kHCkn5v9pEMQ"
   ```

---

## Task 13 — `run_f1` end-to-end batch: drive → score → aggregate → assert clone beats the 0.083 baseline, emit per case

**Files:**
- Create: `/Users/nate/captains-cabinet/framework/fidelity/run_f1.py` (orchestration: build cases → centroid → run_case → baseline draft → score → aggregate → baseline-gate)
- Test: `/Users/nate/captains-cabinet/framework/fidelity/tests/test_run_f1.py`

**Interfaces:**
- Consumes: `benchmark.build_cases`; `retro.author_centroid`, `retro.BASELINE_SYSTEM`; `officer_runner.run_case`; `scorer.score`; `oauth_llm.oauth_raw_llm` (for the baseline generic-assistant draft); `officer_prompt.format_situation` (for the baseline payload); `leakguard.LeakageDetectedError`.
- Produces:
  - `BASELINE_MATCH_RATE: float = 0.083` (the generic-assistant baseline F must beat).
  - `run_batch(officer_role="cos", n_cases=24, people_dir=None, runner=run_case, scorer_fn=score, baseline_llm=oauth_raw_llm, emit_events=True) -> dict` — for each case: drive the officer blind (`runner`), draft a baseline reply (generic assistant via `baseline_llm` + `BASELINE_SYSTEM`), `scorer_fn(...)`, collect rows; aggregate decision-match rate; return `{n_scored, n_leaked, decision_match_rate, partial_rate, divergent_rate, style_win_rate, mechanics_fail_rate, beats_baseline, baseline, scores}`. Leaked cases (`LeakageDetectedError`) are counted in `n_leaked`, excluded from scoring (never silently scored).
  - `assert_beats_baseline(result) -> None` — raises `AssertionError` if `decision_match_rate <= BASELINE_MATCH_RATE` (the bootstrap-validation gate).

**Steps:**

- [ ] **1. Write the failing test.** Create `/Users/nate/captains-cabinet/framework/fidelity/tests/test_run_f1.py`:

   ```python
   from __future__ import annotations

   import pytest

   from framework.fidelity import run_f1, leakguard
   from framework.fidelity.types import Case, OfficerDecision
   from framework.fidelity.scorer import CaseScore


   @pytest.fixture(autouse=True)
   def event_log_dir(tmp_path, monkeypatch):
       monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
       monkeypatch.delenv("DATABASE_URL", raising=False)


   CUTOFF = "2026-06-10T12:00:00+00:00"


   def _case(cid):
       return Case.from_retro_case({
           "case_id": cid, "reply_key": cid, "slug": "ulrik", "person": "Ulrik",
           "channel": "msgraph", "language": "da", "reply_ts": CUTOFF,
           "subject": "s", "n_prior": 2,
           "thread_before": [{"date": "2026-06-09T00:00:00+00:00",
                              "direction": "received", "who": "Ulrik <u@x>",
                              "source": "msgraph", "text": "hej"}],
           "real_reply": "Ja.",
       })


   class TestRunBatch:
       def test_clone_beats_baseline_when_mostly_match(self, monkeypatch):
           cases = [_case(f"c{i}") for i in range(5)]
           monkeypatch.setattr(run_f1, "build_cases",
                               lambda lane="send-1to1-reply", decision_type="reply",
                               n=24, window=None, people_dir=None: cases)
           runner = lambda case, role, emit_events=True: OfficerDecision("Ja.", "", [])
           baseline_llm = lambda payload, system, max_tokens=1500, model="claude-sonnet-4-6": "Generic."
           verdicts = ["match", "match", "match", "match", "divergent"]
           it = iter(verdicts)
           def scorer_fn(case, dec, baseline_draft, centroids, embedder=None, judge=None):
               v = next(it)
               return CaseScore(case.case_id, True, v, [], False,
                                {"match": 1.0, "partial": 0.5, "divergent": 0.0}[v], {})
           monkeypatch.setattr(run_f1, "author_centroid",
                               lambda exclude_keys=None: {"msgraph": [1.0]})
           res = run_f1.run_batch(runner=runner, scorer_fn=scorer_fn,
                                  baseline_llm=baseline_llm)
           assert res["n_scored"] == 5
           assert res["n_leaked"] == 0
           assert res["decision_match_rate"] == pytest.approx(0.8)
           assert res["beats_baseline"] is True
           assert res["baseline"] == 0.083

       def test_leaked_cases_excluded_not_scored(self, monkeypatch):
           cases = [_case("c0"), _case("c1")]
           monkeypatch.setattr(run_f1, "build_cases",
                               lambda lane="send-1to1-reply", decision_type="reply",
                               n=24, window=None, people_dir=None: cases)
           monkeypatch.setattr(run_f1, "author_centroid",
                               lambda exclude_keys=None: {"msgraph": [1.0]})
           def runner(case, role, emit_events=True):
               if case.case_id == "c1":
                   raise leakguard.LeakageDetectedError("leak")
               return OfficerDecision("Ja.", "", [])
           scorer_fn = lambda case, dec, baseline_draft, centroids, embedder=None, judge=None: \
               CaseScore(case.case_id, True, "match", [], False, 1.0, {})
           res = run_f1.run_batch(runner=runner, scorer_fn=scorer_fn,
                                  baseline_llm=lambda *a, **k: "g")
           assert res["n_scored"] == 1
           assert res["n_leaked"] == 1
           assert res["decision_match_rate"] == 1.0

       def test_assert_beats_baseline_raises_when_below(self):
           with pytest.raises(AssertionError):
               run_f1.assert_beats_baseline({"decision_match_rate": 0.05})

       def test_assert_beats_baseline_passes_when_above(self):
           run_f1.assert_beats_baseline({"decision_match_rate": 0.5})  # no raise
   ```

- [ ] **2. Run it, show expected FAIL:**

   ```
   python3 -m pytest framework/fidelity/tests/test_run_f1.py -q
   ```
   Expected: `ModuleNotFoundError: No module named 'framework.fidelity.run_f1'` -> collection error, 0 passed.

- [ ] **3. Minimal implementation.** Create `/Users/nate/captains-cabinet/framework/fidelity/run_f1.py`:

   ```python
   """F1 end-to-end batch over the reply cell
   (docs/fidelity-harness-design-2026-06-18.md §266-268).

   Build held-out reply cases -> blind-drive the officer (leak-guarded, no side
   effects) -> draft a generic-assistant baseline -> score (OAuth judge, Voyage
   STYLE) -> aggregate the decision-match rate -> assert the clone beats the 0.083
   generic-assistant baseline. Leaked cases are counted and EXCLUDED (never
   silently scored). One fidelity-case-evaluated consequence event is emitted per
   scored case (inside run_case via fidelity_events)."""

   from __future__ import annotations

   from framework.fidelity import leakguard
   from framework.fidelity.benchmark import build_cases
   from framework.fidelity.officer_prompt import format_situation
   from framework.fidelity.officer_runner import run_case
   from framework.fidelity.oauth_llm import oauth_raw_llm
   from framework.fidelity.retro import BASELINE_SYSTEM, author_centroid
   from framework.fidelity.scorer import score

   BASELINE_MATCH_RATE = 0.083  # retrodiction generic-assistant baseline


   def _rate(rows: list, verdict: str) -> float:
       if not rows:
           return 0.0
       return sum(1 for r in rows if r.decision_verdict == verdict) / len(rows)


   def _baseline_payload(case) -> str:
       """The generic-assistant baseline sees the same situation text (no voice /
       no intel) - that contrast is what makes the scores meaningful."""
       return format_situation(case)


   def run_batch(officer_role: str = "cos", n_cases: int = 24, people_dir=None,
                 runner=run_case, scorer_fn=score, baseline_llm=oauth_raw_llm,
                 emit_events: bool = True) -> dict:
       """Drive -> score -> aggregate over the reply cell."""
       cases = build_cases(n=n_cases, people_dir=people_dir)
       centroids = author_centroid(exclude_keys={c.situation_ref for c in cases})

       scores, n_leaked = [], 0
       for case in cases:
           try:
               decision = runner(case, officer_role, emit_events=emit_events)
           except leakguard.LeakageDetectedError:
               n_leaked += 1  # hard-failed + leak event already emitted in run_case
               continue
           baseline_draft = baseline_llm(_baseline_payload(case), BASELINE_SYSTEM) or ""
           cs = scorer_fn(case, decision, baseline_draft, centroids)
           scores.append(cs)

       mechanics_fail = (sum(1 for s in scores if s.mechanics_flags) / len(scores)
                         if scores else 0.0)
       style_win = (sum(1 for s in scores if s.style_win) / len(scores)
                    if scores else 0.0)
       match_rate = _rate(scores, "match")
       return {
           "n_scored": len(scores),
           "n_leaked": n_leaked,
           "decision_match_rate": round(match_rate, 4),
           "partial_rate": round(_rate(scores, "partial"), 4),
           "divergent_rate": round(_rate(scores, "divergent"), 4),
           "style_win_rate": round(style_win, 4),
           "mechanics_fail_rate": round(mechanics_fail, 4),
           "beats_baseline": match_rate > BASELINE_MATCH_RATE,
           "baseline": BASELINE_MATCH_RATE,
           "scores": [s.__dict__ for s in scores],
       }


   def assert_beats_baseline(result: dict) -> None:
       """Bootstrap-validation gate: fail if the clone does not beat the
       generic-assistant baseline."""
       rate = result["decision_match_rate"]
       assert rate > BASELINE_MATCH_RATE, (
           f"clone decision_match_rate {rate} <= baseline {BASELINE_MATCH_RATE}")


   if __name__ == "__main__":
       import json
       import sys

       role = sys.argv[1] if len(sys.argv) > 1 else "cos"
       n = int(sys.argv[2]) if len(sys.argv) > 2 else 24
       result = run_batch(officer_role=role, n_cases=n)
       print(json.dumps({k: v for k, v in result.items() if k != "scores"}, indent=2))
       assert_beats_baseline(result)
       print(f"OK - clone beats baseline: "
             f"{result['decision_match_rate']} > {result['baseline']} "
             f"(n_scored={result['n_scored']}, n_leaked={result['n_leaked']})")
   ```

- [ ] **4. Run it, show expected PASS, then run the full F1 fidelity suite:**

   ```
   python3 -m pytest framework/fidelity/tests/test_run_f1.py -q
   python3 -m pytest framework/fidelity/tests/ -q
   ```
   Expected: run_f1 `4 passed`; the full `framework/fidelity/tests/` suite green (F0 consequence 43 + retro shim 5 + oauth 8 + leakguard 12 + event_types 5 + fidelity_events 5 + officer_prompt 7 + officer_runner 6 + scorer 5 + benchmark 6 + run_f1 4 = `106 passed`). (Exact count may shift if you add coverage; all must pass.)

- [ ] **5. Commit:**

   ```
   git add framework/fidelity/run_f1.py framework/fidelity/tests/test_run_f1.py
   git commit -m "feat(fidelity): F1 run_batch — drive→score→aggregate, beats-0.083-baseline gate, per-case consequence emit

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01LLg211Y8u2kHCkn5v9pEMQ"
   ```

---

## Task 14 — Live bootstrap validation against the `send-1to1-reply` universe + docs-track-code sync

**Files:**
- Create: `/Users/nate/captains-cabinet/framework/fidelity/README.md` (module purpose, the F1 surface, the file layout, how to run the live bootstrap, the reuse boundary + privacy fence + the 3.9.6 import constraint)
- Modify: `/Users/nate/captains-cabinet/docs/fidelity-harness-design-2026-06-18.md` (mark F1 as built; record the realized file layout incl. the `benchmark.py` name + `connectors/` deferred to F3; append a "Build status" note under the F-internal phasing) — keep the dated design snapshot's prose intact otherwise
- Test (manual/live gate, not a unit test): run `run_f1.run_batch` against the real vault + OAuth judge and confirm the bootstrap-validation gate

**Interfaces:**
- Consumes: real `~/.screenpipe/pipes/retrodiction/` + `3-People/*/conversations.md` + `~/.screenpipe/state/autonomy_outcomes.jsonl`; OAuth `claude -p` (requires `CLAUDE_CODE_OAUTH_TOKEN` or a logged-in session) and `VOYAGE_API_KEY` for the STYLE channel.
- Produces: a confirmed live run where `decision_match_rate > 0.083` over a 24-case held-out sample of the reply cell, proving the officer-runner produces sane scores before any gate trusts it.

**Steps:**

- [ ] **1. Run the live bootstrap (expected FAIL-loud first if OAuth/Voyage not configured):**

   ```
   python3 -m framework.fidelity.run_f1 cos 24
   ```
   Expected behaviour: if `claude -p` is unauthenticated, judge verdicts come back `error` → `decision_match_rate == 0.0` → `assert_beats_baseline` raises with the explicit message. That is the correct fail-loud signal (OAuth/quota exhaustion never silently passes).

- [ ] **2. Configure the live path (one-time): ensure `CLAUDE_CODE_OAUTH_TOKEN` (or a logged-in `claude` session) and `VOYAGE_API_KEY` are present, then re-run:**

   ```
   python3 -m framework.fidelity.run_f1 cos 24
   ```
   Expected: JSON summary with `decision_match_rate > 0.083`, `beats_baseline: true`, `baseline: 0.083`, and `n_leaked == 0` (no anti-leakage hard-fails on the clean held-out sample), ending with the `OK - clone beats baseline: ...` line. This proves the reply cell end-to-end against the `send-1to1-reply` validation universe (~266 rows; this run scores a 24-case held-out sample of it).

- [ ] **3. Write the module README.** Create `/Users/nate/captains-cabinet/framework/fidelity/README.md` documenting:
   - **The F1 surface + file layout:** `consequence.py` (F0 emitter/reader), `retro.py` (shim), `oauth_llm.py`, `leakguard.py`, `types.py`, `fidelity_events.py`, `officer_runner.py`, `officer_prompt.py`, `scorer.py`, `benchmark.py`, `run_f1.py`. Note that `connectors/monday_activitylog.py` is DEFERRED to F3 (the triage decision-type).
   - **The reuse boundary:** import the retrodiction engine via `retro.py`, never rebuild `score_case`/`judge_decision`/`cusum`/`score_draft`/`extract_cases`/`author_centroid`/`aggregate`/`mechanics_flags`.
   - **The sacred anti-leakage protocol:** thread-pre-cutoff assertion + post-output scan are the live F1 guards; `filter_mcp_result` is the F4 hook. Any breach hard-fails + emits `fidelity-case-leak-detected`; leaked cases are never scored.
   - **The privacy fence:** `nate_model` / voice / `0-Self` inform scoring (centroid, clone draft) but NEVER egress into a score row, consequence event, commit, or doc.
   - **The OAuth constraint:** judge + baseline route through `claude -p` (OAuth/Max pool); there is NO `ANTHROPIC_API_KEY` (it is stripped from the subprocess env).
   - **The 3.9.6 import constraint:** `framework/fidelity` transitively imports the retrodiction lib, which MUST remain importable under system Python 3.9.6 (asserted in `test_retro_shim.py`).
   - **The exact live-bootstrap command:** `python3 -m framework.fidelity.run_f1 cos 24` (validates the clone beats the 0.083 generic-assistant baseline over a held-out sample of the 266-row `send-1to1-reply` universe).

- [ ] **4. Sync the design doc F1 build-status.** In `/Users/nate/captains-cabinet/docs/fidelity-harness-design-2026-06-18.md`, edit the F1 phasing line (around line 266-267). Replace:
   ```
   - **F1** — `officer_runner.py` + `scorer.py` over the **reply** cell; validate vs
     the 176 paired set + baseline.
   ```
   with:
   ```
   - **F1** — `officer_runner.py` + `scorer.py` over the **reply** cell; validate vs
     a held-out sample of the **send-1to1-reply** universe (~266 rows) + the 0.083
     baseline. **Built**: `framework/fidelity/{retro,oauth_llm,leakguard,types,
     fidelity_events,officer_runner,officer_prompt,scorer,benchmark,run_f1}.py`
     (held-out case builder is `benchmark.build_cases`; `connectors/` for the
     triage decision-type is deferred to F3). Live bootstrap:
     `python3 -m framework.fidelity.run_f1 cos 24`.
   ```
   Also fix the bootstrap-validation note (around line 259-261). Replace `run F against the existing **176 paired** autonomy_outcomes.jsonl rows` with `run F against a held-out sample of the **send-1to1-reply** universe (~266 autonomy_outcomes.jsonl rows; cases rebuilt leak-safe from conversations.md)`.

- [ ] **5. Grep for stale references per the docs-track-code rule.**
   ```
   grep -rn "176 paired\|bench_reply\|build_reply_cases" docs/ framework/fidelity/README.md ; \
   grep -rn "framework/fidelity" docs/ framework/fidelity/README.md
   ```
   Expected: the first grep prints nothing (zero stale "176 paired" or old-name references); the second grep shows only real, current files (`benchmark.py`, `run_f1.py`, etc.).

- [ ] **6. Commit:**

   ```
   git add framework/fidelity/README.md docs/fidelity-harness-design-2026-06-18.md
   git commit -m "feat(fidelity): F1 live bootstrap + README + design-doc build-status sync

   Validated officer_runner + scorer over the reply cell against a held-out
   sample of the send-1to1-reply universe (~266 rows); clone beats the 0.083
   generic-assistant baseline. Docs tracked per docs-as-you-build.

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01LLg211Y8u2kHCkn5v9pEMQ"
   ```

> **F1 boundaries the plan deliberately holds:** F1 ships the reply cell only. It does NOT wire the live brain bridge (no cutoff param — F4), does NOT build `connectors/monday_activitylog.py` or other decision-types (F3), does NOT add `aggregate.py`/`graduation.py`/drift (F2), and does NOT apply the endorsed-direction scoring adjustment (F4 — F1 scores vs the actual reply with `endorsement="unknown"`). `filter_mcp_result` is built + tested but inert in the F1 runtime path (F4 hook).

