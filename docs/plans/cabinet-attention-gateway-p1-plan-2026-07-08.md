# Attention Gateway P1 — Situation Identity + Canonical-Ref Dedup: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kill cross-run duplicate action cards by giving every proposal a mechanical situation identity (canonical refs extracted from evidence strings), so "same evidence = same situation" fires no matter how the LLM re-words subjects or annotates refs.

**Architecture:** New pure module `framework/attention/situation.py` (ref extraction + situation keys). One ~6-line compare-time change in `framework/acting/action_lane.py` (germline — carried as a patch file, applied to the branch; the Captain's merge is the apply): canonicalize BOTH the covered-evidence set and each proposal's evidence, drop on canonical overlap (in addition to the existing exact-string check — strictly more dedup, zero data-shape change). `run_action_lane.py` needs NO change (it already passes raw ledger ref strings; canonicalization happens at compare time on both sides). Ledger row shape unchanged in P1.

**Tech Stack:** Python 3.12 stdlib only (re, hashlib). pytest for tests. No new dependencies.

## Global Constraints

- Framework layer: no captain-specific literals, no `/Users/nate` paths, no screenpipe imports (`test_no_launcher_hardcode.py`, `test_no_screenpipe_in_core.py` must stay green).
- No axis branches (`test_axes_contract.py` AST linter must stay green).
- `framework/acting/action_lane.py` is germline: its diff is authored as `patches/p1-action-lane-canonical-dedup.patch` in the repo and applied with `git apply` on this branch only; never edited on the live checkout.
- Germline lockstep: NO new files enter the germline lists in P1 (`test_germline_lockstep_consistency.py` unchanged).
- `propose_actions` stays pure and replay-deterministic: `canonical_refs` is pure stdlib, no I/O, no clock.
- Evidence display strings shown to the Captain are unchanged — canonicalization is compare-time only.
- Python: match repo style (module docstring explaining WHY, type hints, no external deps). Commits: `attention-gateway: <what>` + Claude trailer, hooks NOT bypassed.

## File Structure

```
framework/attention/__init__.py                          (new, package marker)
framework/attention/situation.py                         (new, ~120 lines: canonical_refs, situation_key, situations_overlap)
framework/attention/tests/__init__.py                    (new, empty)
framework/attention/tests/test_situation.py              (new: unit corpus — the REAL observed evidence spellings)
framework/attention/tests/test_p1_acceptance_replay.py   (new: the 2026-07-07 feed corpus collapses 18 cards → ≤8 situations)
framework/acting/tests/test_action_lane_canonical_dedup.py (new: integration through propose_actions)
patches/p1-action-lane-canonical-dedup.patch             (new: the germline diff, applied on-branch)
docs/plans/cabinet-attention-gateway-spec-2026-07-08.md  (modify: §8 P1 row — lane_dedup wiring not needed, note why)
```

---

### Task 1: `framework/attention/situation.py` — canonical refs + situation keys

**Files:**
- Create: `framework/attention/__init__.py`
- Create: `framework/attention/situation.py`
- Create: `framework/attention/tests/__init__.py`
- Test: `framework/attention/tests/test_situation.py`

**Interfaces:**
- Consumes: nothing (pure stdlib).
- Produces: `canonical_refs(evidence: Iterable[str] | None) -> frozenset[str]`; `situations_overlap(a: Iterable[str], b: Iterable[str]) -> bool` (takes RAW evidence strings, canonicalizes internally); `situation_key(evidence: Iterable[str], subject: str = "") -> str`.

- [ ] **Step 1: Write the failing unit tests (real observed corpus)**

```python
"""Unit corpus for framework.attention.situation — every multi-spelling group
below was OBSERVED verbatim on the Captain's feed 2026-07-07/08 (the 24-cards-
for-8-situations incident). These are the exact strings the old verbatim
evidence-overlap check failed to match."""
import pytest

from framework.attention.situation import (
    canonical_refs, situation_key, situations_overlap)

# The five observed spellings of the document-signing commitment evidence.
SIGNING_VARIANTS = [
    "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — 'Fredag den 10 juli klokken 14:50, Rådhuset'; reminder_set: false",
    "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — 'town hall, Friday 10 July 14:50, document signing'",
    "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — Lena har booket tid hos rådhuset til underskrivelse af dokumenterne fredag d. 10. juli kl. 14:50",
    "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — Lena booked town hall Friday 10 July 14:50; fulfilled_date 2026-06-22",
    "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — 'booket tid hos rådhuset … Fredag den 10 juli klokken 14:50'; reminder_set: false",
]


def test_signing_variants_all_share_canonical_refs():
    canon = [canonical_refs([v]) for v in SIGNING_VARIANTS]
    for c in canon:
        assert "6-Commitments/owed_to_nate/cmt-fca6836e2844.md" in c
        assert "cmt-fca6836e2844" in c
    for i in range(len(canon)):
        for j in range(len(canon)):
            assert canon[i] & canon[j], (i, j)


def test_ref_prefix_and_cross_directory_same_commitment():
    # Observed: same commitment cited via owed_by AND owed_to paths, one with
    # a literal 'ref=' prefix. The bare cmt id must bridge them.
    a = canonical_refs(["ref=6-Commitments/owed_by_captain/cmt-d45d00936ac1.md"])
    b = canonical_refs(["6-Commitments/owed_to_nate/cmt-d45d00936ac1.md — colleague-D returning 2026-07-27"])
    assert "cmt-d45d00936ac1" in a and "cmt-d45d00936ac1" in b
    assert a & b


def test_bare_vs_annotated_path():
    bare = "6-Commitments/owed_to_nate/cmt-8ab5d6355d15.md"
    annotated = "6-Commitments/owed_to_nate/cmt-8ab5d6355d15.md — due 2026-07-08, reminder_set: false, status: open"
    assert canonical_refs([bare]) & canonical_refs([annotated])


def test_multi_ref_string_yields_every_ref():
    s = ("6-Commitments/owed_to_nate/cmt-540d7a19bffd.md — Grace answered, "
         "6-Commitments/owed_to_nate/cmt-781c7a756d51.md — same topic, fulfilled 2026-07-06, "
         "6-Commitments/owed_to_nate/cmt-0ac4d1192cae.md — Grace's suggestion")
    c = canonical_refs([s])
    assert {"cmt-540d7a19bffd", "cmt-781c7a756d51", "cmt-0ac4d1192cae"} <= c
    assert "6-Commitments/owed_to_nate/cmt-781c7a756d51.md" in c


def test_ampersand_and_dated_decision_paths():
    c = canonical_refs([
        "5-Reflections/Decisions/2026-07-06-Four-proofs-required-before-commercialization-substrate-API-key-SDK-unit.md — four proof gates listed",
        "9-Codebases/Toolbox/commits.md — commits cc49aa2920 and 151890fc0c flagged ⚠️ no Monday id",
    ])
    assert "5-Reflections/Decisions/2026-07-06-Four-proofs-required-before-commercialization-substrate-API-key-SDK-unit.md" in c
    assert "9-Codebases/Toolbox/commits.md" in c


def test_different_files_do_not_overlap():
    a = canonical_refs(["9-Codebases/Toolbox/commits.md — commits cc49aa2920"])
    b = canonical_refs(["9-Codebases/stepnetwork-dk/commits.md — commits 6a4ff7a4a5"])
    assert not (a & b)


def test_prose_only_yields_empty_and_never_overlaps():
    prose = canonical_refs(["the Captain mentioned this in passing yesterday"])
    assert prose == frozenset()
    assert not situations_overlap(
        ["the Captain mentioned this in passing yesterday"],
        ["the Captain mentioned this in passing yesterday"])


def test_correlation_uuid_monday_and_url_forms():
    c = canonical_refs([
        "cabinet-proposal-id:0f3a9b2c4d5e6f70",
        "event 6E945A46-ECCB-435C-A927-19A8B5252EA0 created",
        "monday:5091706356 moved to Done",
        "see https://Example.com/Path?x=1 for details",
    ])
    assert "cabinet-proposal-id:0f3a9b2c4d5e6f70" in c
    assert "6e945a46-eccb-435c-a927-19a8b5252ea0" in c
    assert "monday:5091706356" in c
    assert "https://example.com/Path?x=1" in c


def test_normalization_slashes_quotes_and_truncation():
    a = canonical_refs(["`6-Commitments//owed_to_nate/cmt-fca6836e2844.md`"])
    assert "6-Commitments/owed_to_nate/cmt-fca6836e2844.md" in a
    # Inputs are hard-capped so a hostile mega-string cannot balloon the set.
    huge = "x" * 500_000
    assert canonical_refs([huge]) == frozenset()


def test_non_string_and_none_inputs_are_safe():
    assert canonical_refs(None) == frozenset()
    assert canonical_refs([None, 42, {"path": "y"}]) == frozenset()


def test_situation_key_stable_and_ref_order_free():
    k1 = situation_key([SIGNING_VARIANTS[0]])
    k2 = situation_key([SIGNING_VARIANTS[0]])
    assert k1 == k2 and k1.startswith("sit-")
    # same canonical set, different raw spelling -> same key
    assert situation_key([SIGNING_VARIANTS[1]]) == k1


def test_situation_key_falls_back_to_subject_slug_when_refless():
    k = situation_key(["pure prose"], subject="Order Product Mastery Book!")
    assert k == "slug:order-product-mastery-book"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3.12 -m pytest framework/attention/tests/test_situation.py -q`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'framework.attention'`

- [ ] **Step 3: Write the implementation**

```python
"""framework.attention.situation — mechanical situation identity.

WHY (2026-07-08 feed incident): every dedup key in the acting lanes was LLM
prose — subject slugs re-worded per run, evidence refs annotated per run
("path — <fresh paraphrase>") — so 'same evidence = same situation' never
fired and one document-signing reminder became 6+ cards and 2 duplicate calendar
events. This module extracts the STABLE ids embedded in those strings
(vault paths, commitment ids, correlation ids, event UUIDs, monday ids,
URLs) so identity comparison is deterministic prose-free set overlap.

Pure stdlib, no I/O, no clock — safe inside the replay-deterministic
propose step (spec: docs/plans/cabinet-attention-gateway-spec-2026-07-08.md §4.1).
"""
from __future__ import annotations

import hashlib
import re
from typing import Iterable

# Per-string and per-call hard caps: canonicalization runs on LLM/captured
# text, so a hostile mega-string must cost O(cap), not O(input).
_MAX_STR = 10_000
_MAX_ITEMS = 64

# Vault-relative markdown paths. Deliberately NO spaces in the class: the
# evidence annotation separator (" — ") and OCR artifacts would otherwise
# glue prose into the path. A space-bearing filename loses its prefix here;
# the id patterns below (cmt-/uuid/monday) still carry identity for those.
_MD_PATH = re.compile(r"[\w()&.\-/]+\.md")
_CMT_ID = re.compile(r"\bcmt-[0-9a-f]{6,}\b")
_CORR_ID = re.compile(r"\bcabinet-proposal-id:[0-9a-f]{8,}\b")
_UUID = re.compile(
    r"\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b")
_MONDAY = re.compile(r"\bmonday:(\d{6,})\b")
_URL = re.compile(r"https?://[^\s<>\"'`]+")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _norm_path(p: str) -> str:
    p = re.sub(r"/{2,}", "/", p).lstrip("=")
    while p.startswith("./"):
        p = p[2:]
    return p.strip("/")


def _norm_url(u: str) -> str:
    m = re.match(r"(https?)://([^/]+)(.*)", u, re.IGNORECASE)
    if not m:
        return u
    scheme, host, rest = m.groups()
    return f"{scheme.lower()}://{host.lower()}{rest.rstrip('.,;:)')}"


def canonical_refs(evidence: "Iterable | None") -> frozenset:
    """Extract the stable-id set from raw evidence strings.

    Non-string items and over-cap input are skipped, never raised on: this
    runs on model output inside the propose step and must be total."""
    out: set = set()
    if evidence is None:
        return frozenset(out)
    for item in list(evidence)[:_MAX_ITEMS]:
        if not isinstance(item, str):
            continue
        s = item.strip().strip("`\"'")[:_MAX_STR]
        if not s:
            continue
        for m in _MD_PATH.findall(s):
            p = _norm_path(m)
            # a bare filename with no directory carries no vault identity
            if "/" in p:
                out.add(p)
        out.update(x.lower() for x in _CMT_ID.findall(s))
        out.update(x.lower() for x in _CORR_ID.findall(s))
        out.update(x.lower() for x in _UUID.findall(s))
        out.update(f"monday:{x}" for x in _MONDAY.findall(s))
        out.update(_norm_url(x) for x in _URL.findall(s))
    return frozenset(out)


def situations_overlap(a: "Iterable | None", b: "Iterable | None") -> bool:
    """True when two raw evidence bundles share ANY stable id.

    Empty canonical sets never overlap (prose-only evidence carries no
    identity — fail toward presenting, per the lane dedup doctrine)."""
    ca = canonical_refs(a)
    if not ca:
        return False
    return bool(ca & canonical_refs(b))


def situation_key(evidence: "Iterable | None", subject: str = "") -> str:
    """Stable situation id: hash of the sorted canonical ref-set; slug
    fallback for genuinely ref-less items (matches action_lane.slugify)."""
    refs = canonical_refs(evidence)
    if refs:
        digest = hashlib.sha1("\n".join(sorted(refs)).encode("utf-8")).hexdigest()
        return f"sit-{digest[:16]}"
    slug = _SLUG_RE.sub("-", (subject or "").lower()).strip("-")[:80]
    return f"slug:{slug}"
```

`framework/attention/__init__.py`:

```python
"""framework.attention — the Captain-attention discipline (spec 2026-07-08).

P1 ships situation identity (situation.py). Later phases add the feed
journal, gateway, charter, and learned budgets per the spec."""
```

`framework/attention/tests/__init__.py`: empty file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3.12 -m pytest framework/attention/tests/test_situation.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add framework/attention/
git commit -m "attention-gateway P1: situation identity — canonical refs, overlap, keys

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0141Y3vXipPQTR4jBgypRpC2"
```

---

### Task 2: Canonical overlap in `propose_actions` (germline patch) + integration test

**Files:**
- Create: `patches/p1-action-lane-canonical-dedup.patch`
- Modify (via `git apply`, on-branch only): `framework/acting/action_lane.py:462-498`
- Test: `framework/acting/tests/test_action_lane_canonical_dedup.py`

**Interfaces:**
- Consumes: `canonical_refs`, `situations_overlap` from Task 1.
- Produces: `propose_actions(...)` drops a proposal when `canonical_refs(proposal.evidence) & canonical_refs(covered_evidence)` is non-empty (drop reason `"evidence-overlap-canonical"`), in ADDITION to the existing verbatim intersection (reason `"evidence-overlap"` unchanged).

- [ ] **Step 1: Write the failing integration test**

```python
"""propose_actions must drop re-worded duplicates via canonical-ref overlap.

Drives the REAL pure core with a fixture llm; covered_evidence carries a
PRIOR run's annotated evidence string (as read back from ledger refs), the
new proposal cites the same commitment with a different annotation and a
fresh subject_hint — the exact 2026-07-07 document-signing pattern."""
import json

from framework.acting import action_lane


def _llm_returning(proposals):
    def llm(system, user):
        return json.dumps({"proposals": proposals})
    return llm


PRIOR_RUN_EVIDENCE = ("6-Commitments/owed_to_nate/cmt-fca6836e2844.md — "
                      "'Fredag den 10 juli klokken 14:50, Rådhuset'; reminder_set: false")

REWORDED_PROPOSAL = {
    "situation": "Document signing Friday needs a calendar block.",
    "subject_hint": "papers-signing-town-hall-fresh-wording",   # drifted slug
    "lane": "personal",
    "urgency": "ping-now",
    "confidence": 0.9,
    "injection_suspect": False,
    "direction_fit": {"direction": "personal"},
    "evidence": ["6-Commitments/owed_to_nate/cmt-fca6836e2844.md — Lena booked town hall"],
    "steps": [{"kind": "reminder_create", "title": "Document signing",
               "payload": {"title": "t", "due_iso": "2026-07-10T14:50:00+02:00"}}],
}

UNRELATED_PROPOSAL = {
    "situation": "EC connection details arrive today and need a chase block.",
    "subject_hint": "chase-ec-connection-details",
    "lane": "polads",
    "urgency": "batch",
    "confidence": 0.8,
    "injection_suspect": False,
    "direction_fit": {"direction": "personal"},
    "evidence": ["6-Commitments/owed_to_nate/cmt-8ab5d6355d15.md — due 2026-07-08"],
    "steps": [{"kind": "reminder_create", "title": "Chase EC",
               "payload": {"title": "t", "due_iso": "2026-07-08T13:00:00Z"}}],
}


def _run(covered, proposals, log):
    return action_lane.propose_actions(
        "SIGNAL BUNDLE (fixture)", as_of="2026-07-08T10:00:00Z",
        llm=_llm_returning(proposals), decided_subjects=set(),
        open_subjects=set(), budget_left=8,
        covered_evidence=frozenset(covered), directions=None,
        suppress_log=log.append)


def test_reworded_duplicate_dropped_by_canonical_overlap():
    log = []
    out = _run([PRIOR_RUN_EVIDENCE], [REWORDED_PROPOSAL, UNRELATED_PROPOSAL], log)
    assert [p.subject for p in out] == ["chase-ec-connection-details"]
    assert any("evidence-overlap-canonical" in line for line in log)


def test_exact_string_check_still_fires_first():
    log = []
    dup = dict(REWORDED_PROPOSAL, evidence=[PRIOR_RUN_EVIDENCE])
    out = _run([PRIOR_RUN_EVIDENCE], [dup], log)
    assert out == []
    assert any("reason=evidence-overlap" in line and "canonical" not in line
               for line in log)


def test_refless_covered_evidence_never_suppresses():
    log = []
    out = _run(["a prose-only ledger ref with no ids"],
               [UNRELATED_PROPOSAL], log)
    assert len(out) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.12 -m pytest framework/acting/tests/test_action_lane_canonical_dedup.py -q`
Expected: FAIL — first test sees the re-worded proposal SURVIVE (no canonical check yet) and no `evidence-overlap-canonical` log line.

- [ ] **Step 3: Author + apply the germline patch**

Write `patches/p1-action-lane-canonical-dedup.patch` with exactly this content (unified diff against current `framework/acting/action_lane.py`; regenerate hunk offsets with `git diff` if line drift occurs — see step notes):

```diff
--- a/framework/acting/action_lane.py
+++ b/framework/acting/action_lane.py
@@ -20,6 +20,7 @@
 
 from framework.env import captain_name
+from framework.attention.situation import canonical_refs
 
@@ -461,6 +462,12 @@ def propose_actions(
     tainted = _tainted_refs(signals_text)
 
+    # CANONICAL identity of everything any prior card cited (P1, spec §4.1):
+    # the verbatim intersection below misses LLM-annotated re-spellings of the
+    # SAME ref ("path — <fresh paraphrase>"), which is how one situation
+    # became 6 cards on 2026-07-07. Computed ONCE per run over the raw
+    # ledger-carried strings; display strings stay untouched.
+    covered_canon = canonical_refs(covered_evidence)
+
     user = (f"as_of: {as_of}\n\nCaptured signals (fenced DATA — describe the "
@@ -496,6 +503,10 @@ def propose_actions(
         evidence_refs = {str(e)[:200] for e in (p.get("evidence") or [])[:8]}
         if evidence_refs & set(covered_evidence):
             _drop(subject, "evidence-overlap")   # same evidence = same situation
             continue
+        # canonicalize the RAW evidence list (the [:200] display truncation
+        # above can cut a trailing ref mid-id in multi-ref strings)
+        if covered_canon and (canonical_refs((p.get("evidence") or [])[:8]) & covered_canon):
+            _drop(subject, "evidence-overlap-canonical")
+            continue
         direction_fit = _normalize_direction_fit(p.get("direction_fit"))
```

Note for the implementer: author the patch by making the edit in a SCRATCH COPY (`cp framework/acting/action_lane.py /tmp/al.py`, edit `/tmp/al.py`, `diff -u framework/acting/action_lane.py /tmp/al.py`), save as the patch file, then `git apply patches/p1-action-lane-canonical-dedup.patch`. The Edit/Write tools are hook-blocked on this path by design; `git apply` of a reviewed patch file is the sanctioned on-branch carry, and the PR diff IS the proposal the Captain applies by merging.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3.12 -m pytest framework/acting/tests/test_action_lane_canonical_dedup.py framework/attention/tests/ -q`
Expected: all PASS

- [ ] **Step 5: Run the acting + germline guard suites**

Run: `python3.12 -m pytest framework/acting/tests/ framework/tests/test_axes_contract.py framework/tests/test_germline_lockstep_consistency.py framework/tests/test_no_launcher_hardcode.py framework/tests/test_no_screenpipe_in_core.py -q`
Expected: all PASS (no axis branches added; germline lists untouched; no launcher literals; no screenpipe imports)

- [ ] **Step 6: Commit**

```bash
git add patches/p1-action-lane-canonical-dedup.patch framework/acting/action_lane.py framework/acting/tests/test_action_lane_canonical_dedup.py
git commit -m "attention-gateway P1: canonical-ref dedup in propose_actions (germline patch, on-branch)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0141Y3vXipPQTR4jBgypRpC2"
```

---

### Task 3: Acceptance replay — the 2026-07-07 observed corpus collapses

**Files:**
- Test: `framework/attention/tests/test_p1_acceptance_replay.py`
- Modify: `docs/plans/cabinet-attention-gateway-spec-2026-07-08.md` (§8 P1 row)

**Interfaces:**
- Consumes: `situations_overlap` from Task 1.
- Produces: the spec's P1 acceptance proof, pinned as a test.

- [ ] **Step 1: Write the failing acceptance test**

```python
"""P1 acceptance (spec §8): the REAL card corpus observed on the Captain's
feed 2026-07-07 10:03Z → 2026-07-08 03:25Z collapses to its true situation
count under canonical-ref grouping. Each entry is (card_slug, [evidence
strings verbatim from the feed])."""
from framework.attention.situation import situations_overlap

OBSERVED_CARDS = [
    ("create-tracking-tasks-for-all-four-commercialization-proof-gates",
     ["5-Reflections/Decisions/2026-07-06-Four-proofs-required-before-commercialization-substrate-API-key-SDK-unit.md — four proof gates listed",
      "5-Reflections/Decisions/2026-07-06-Consumer-subscription-substrate-is-contractually-dead.md — API-key SDK is only durable substrate"]),
    ("calendar-block-document-signing-at-town-hall-fri-10-july-14-50",
     ["6-Commitments/owed_to_nate/cmt-fca6836e2844.md — 'Fredag den 10 juli klokken 14:50, Rådhuset'; reminder_set: false"]),
    ("toolbox-commits-cc49aa29-151890fc-missing-monday-ids",
     ["9-Codebases/Toolbox/commits.md — commits cc49aa2920 and 151890fc0c flagged ⚠️ no Monday id"]),
    ("papers-signing-town-hall-fri-10-july-14-50",
     ["6-Commitments/owed_to_nate/cmt-fca6836e2844.md — 'town hall, Friday 10 July 14:50, document signing'"]),
    ("advertiser-sign-off-on-publisher-filled-details-decision-not-recorded",
     ["6-Commitments/owed_to_nate/cmt-540d7a19bffd.md — Grace answered whether advertiser must sign off on publisher-filled targeting/delivery details",
      "6-Commitments/owed_to_nate/cmt-781c7a756d51.md — same topic, fulfilled 2026-07-06",
      "6-Commitments/owed_to_nate/cmt-0ac4d1192cae.md — Grace's suggestion on advertiser sign-off in licensing/agreement flow"]),
    ("product-brain-architecture-md-is-empty-template-both-live-products-undocumented",
     ["product-brain/architecture.md — status: template, all placeholders unfilled",
      "9-Codebases/Toolbox/deployment.md — live prod stack documented in deployment digest but not in product-brain",
      "9-Codebases/Dev-Tasks-Plugin/deployment.md — same"]),
    ("document-signing-at-town-hall-friday-10-july-14-50",
     ["6-Commitments/owed_to_nate/cmt-fca6836e2844.md — Lena har booket tid hos rådhuset til underskrivelse af dokumenterne fredag d. 10. juli kl. 14:50",
      "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — reminder_set: false"]),
    ("reminder-document-signing-at-town-hall-friday-10-july-14-50",
     ["6-Commitments/owed_to_nate/cmt-fca6836e2844.md — Lena booked town hall Friday 10 July 14:50; fulfilled_date 2026-06-22"]),
    ("toolbox-commits-missing-monday-ids-trace-gap",
     ["9-Codebases/Toolbox/commits.md — commits cc49aa2920 and 151890fc0c both flagged ⚠️ no Monday id"]),
    ("document-signing-town-hall-fri-10-jul-14-50-calendar-block-needed",
     ["6-Commitments/owed_to_nate/cmt-fca6836e2844.md — 'booket tid hos rådhuset … Fredag den 10 juli klokken 14:50'; reminder_set: false"]),
    ("chase-just-political-advertising-portals-connection-details-due-2026-07-08",
     ["6-Commitments/owed_to_nate/cmt-8ab5d6355d15.md"]),
    ("polads-encode-advertiser-sign-off-policy-publisher-fills-advertiser-optional",
     ["6-Commitments/owed_to_nate/cmt-b54c519f5c3e.md"]),
    ("order-product-mastery-book-for-office-colleague-b-due-before-colleague-d-returns-2026-07-27",
     ["ref=6-Commitments/owed_by_captain/cmt-d45d00936ac1.md"]),
    ("capture-polads-liability-decision-advertiser-confirmation-of-publisher-filled-fi",
     ["ref=6-Commitments/owed_to_nate/cmt-b54c519f5c3e.md"]),
    ("chase-just-political-advertising-portals-connection-details-due-8-jul",
     ["6-Commitments/owed_to_nate/cmt-8ab5d6355d15.md — due 2026-07-08, reminder_set: false, status: open"]),
    ("commits-missing-monday-ids-traceability-gap-in-stepnetwork-dk-toolbox",
     ["9-Codebases/stepnetwork-dk/commits.md — commits 6a4ff7a4a5, 01bb6b18fc",
      "9-Codebases/Toolbox/commits.md — commits 151890fc0c, cc49aa2920"]),
    ("commits-missing-monday-item-ids-traceability-gap",
     ["9-Codebases/Toolbox/commits.md — commits cc49aa2920, 151890fc0c flagged ⚠️ no Monday id",
      "9-Codebases/stepnetwork-dk/commits.md — commits 01bb6b18fc, 6a4ff7a4a5 flagged ⚠️ no Monday id"]),
    ("track-and-execute-census-keyframe-writer-as-first-e0-build-task",
     ["5-Reflections/Decisions/2026-07-07-Census-keyframe-writer-is-the-first-E0-build-task.md"]),
    ("fill-polads-architecture-doc-before-ec-integration-lands",
     ["product-brain/architecture.md", "product-brain/README.md",
      "6-Commitments/owed_to_nate/cmt-dead64477e1e.md"]),
    ("ec-dg-just-connection-details-due-today-chase-if-not-received",
     ["6-Commitments/owed_to_nate/cmt-dead64477e1e.md — status:open, due 2026-07-08",
      "6-Commitments/owed_to_nate/cmt-66b9806f4e9c.md — status:open, due 2026-07-08",
      "6-Commitments/owed_to_nate/cmt-8ab5d6355d15.md — status:open, due 2026-07-08"]),
    ("book-order-product-mastery-for-colleague-b-reminder-before-colleague-d-returns-27-jul",
     ["6-Commitments/owed_by_captain/cmt-d45d00936ac1.md — status:open, due 2026-07-27, reminder_set:false",
      "6-Commitments/owed_to_nate/cmt-d45d00936ac1.md — colleague-D returning 2026-07-27"]),
    ("styria-sign-off-answer-update-polads-advertiser-publisher-liability-spec",
     ["6-Commitments/owed_to_nate/cmt-b54c519f5c3e.md — fulfilled 2026-07-07, Grace answered: publisher fills targeting/delivery, optional advertiser confirmation"]),
    ("stepnetwork-dk-commits-missing-monday-ids-traceability-gap",
     ["9-Codebases/stepnetwork-dk/commits.md"]),
]


def _group_by_overlap(cards):
    parent = list(range(len(cards)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(cards)):
        for j in range(i + 1, len(cards)):
            if situations_overlap(cards[i][1], cards[j][1]):
                parent[find(i)] = find(j)
    groups = {}
    for i in range(len(cards)):
        groups.setdefault(find(i), []).append(cards[i][0])
    return list(groups.values())


def test_observed_feed_collapses_to_true_situation_count():
    groups = _group_by_overlap(OBSERVED_CARDS)
    # 23 presented cards -> a handful of real situations (spec §8: <=8).
    assert len(groups) <= 8, groups

    by_slug = {slug: g for g in groups for slug in g}
    # All five same-day signing spellings land in ONE group.
    signing_group = by_slug["calendar-block-document-signing-at-town-hall-fri-10-july-14-50"]
    assert len([s for s in signing_group if "signing" in s]) >= 5
    # The EC chase pair + the triple-commitment variant collapse together.
    assert (by_slug["chase-just-political-advertising-portals-connection-details-due-2026-07-08"]
            is by_slug["ec-dg-just-connection-details-due-today-chase-if-not-received"])
    # Both book cards collapse despite owed_by/owed_to + ref= spelling drift.
    assert (by_slug["order-product-mastery-book-for-office-colleague-b-due-before-colleague-d-returns-2026-07-27"]
            is by_slug["book-order-product-mastery-for-colleague-b-reminder-before-colleague-d-returns-27-jul"])


def test_first_card_would_have_suppressed_every_followup():
    """Chronological replay: with canonical dedup live, each situation's FIRST
    card covers every later re-spelling (covered set grows run by run)."""
    covered: set = set()
    presented = []
    for slug, evidence in OBSERVED_CARDS:
        if situations_overlap(evidence, covered):
            continue
        presented.append(slug)
        covered.update(evidence)
    assert len(presented) <= 8, presented
    assert sum("signing" in s for s in presented) == 1
```

- [ ] **Step 2: Run test to verify current state**

Run: `python3.12 -m pytest framework/attention/tests/test_p1_acceptance_replay.py -q`
Expected: PASS immediately if Task 1 is correct (this test exercises only Task 1 code — its failure mode is a wrong grouping, which is the point of pinning it). If it fails, the extraction rules are wrong: fix `situation.py`, not the corpus.

- [ ] **Step 3: Sync the spec (docs-track-code)**

In `docs/plans/cabinet-attention-gateway-spec-2026-07-08.md` §8, replace the P1 row's "canonical refs wired into `propose_actions` dedup, `lane_dedup`, ledger refs" with "canonical refs wired into `propose_actions` dedup (compare-time, both sides; `lane_dedup`/ledger-row changes proved unnecessary — covered_evidence already carries every open+decided card's raw refs, canonicalized at compare time)".

- [ ] **Step 4: Run the full framework suite**

Run: `python3.12 -m pytest framework/ -q -x --ignore=framework/dashboard 2>&1 | tail -5`
Expected: everything green (count varies with repo; zero failures).

- [ ] **Step 5: Commit**

```bash
git add framework/attention/tests/test_p1_acceptance_replay.py docs/plans/cabinet-attention-gateway-spec-2026-07-08.md
git commit -m "attention-gateway P1: acceptance replay — 23 observed cards collapse to ≤8 situations

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0141Y3vXipPQTR4jBgypRpC2"
```
