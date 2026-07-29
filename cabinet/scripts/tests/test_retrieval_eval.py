"""Retrieval-quality eval locks — recall@k + MRR + ABSTAIN gate for
memory_search (R1 2026-07-12; seed replaced 2026-07-29).

WHAT CHANGED AND WHY. The eval this file guarded reported recall@10 = 1.0000
and MRR = 1.0000 for months — because a harvester derived each query from the
expected document's OWN leading 110 characters. The corpus was being asked to
find itself. Over the same store and the same code, sixteen plainly-worded
questions whose answering document was present returned nothing at all for
seven of them. An eval that cannot fail is not a sensor, and this one was also
the gate standing between the ranking and its fix.

The harvester is deleted. The seed is hand-written questions over documents
THIS REPO SHIPS, so it is portable to any instance that ingested its own docs
and carries nothing private. Three layers:

  * OFFLINE, and this is the anti-regression that matters: every seed query is
    checked AGAINST THE SHIPPED DOCUMENT IT NAMES — the file must exist, and
    the query must not be a copy of its opening text. That is exactly the
    defect that made the old seed unfailable, and it is now mechanically
    refused.

  * OFFLINE: the runner parses and carries the floor + exit-code contract,
    including the ABSTAIN floor — the arm that stops "make retrieval find
    things" from being satisfied by deleting the similarity floor.

  * LIVE GATE (skipped unless Neon is reachable): runs the real
    memory_search path over the seed and enforces all three floors.

Run: python3 -m pytest cabinet/scripts/tests/test_retrieval_eval.py -q
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

# Captured at import time: a sibling test patches the global subprocess.Popen
# and the patch can leak across modules in a whole-repo run — restore the real
# one around our spawns (same guard as test_bootstrap_memory_chain.py).
_REAL_POPEN = subprocess.Popen

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
RUNNER = _SCRIPTS_DIR / "retrieval-eval.sh"
SEED = _SCRIPTS_DIR / "tests/fixtures/retrieval-questions.seed.json"

def _run(cmd, timeout=60, env=None):
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env
        )
    finally:
        subprocess.Popen = patched


def _bash_n(path: Path) -> None:
    p = _run(["bash", "-n", str(path)])
    assert p.returncode == 0, f"bash -n {path.name} failed: {p.stderr}"


# ---------------------------------------------------------------------------
# offline — the scripts parse
# ---------------------------------------------------------------------------

def test_runner_parses():
    _bash_n(RUNNER)


# ---------------------------------------------------------------------------
# offline — the committed seed is well-formed
# ---------------------------------------------------------------------------

def test_seed_is_valid_and_populated():
    data = json.loads(SEED.read_text())
    pairs = data.get("pairs")
    assert isinstance(pairs, list) and len(pairs) >= 15, (
        "seed must carry >=15 query->ref pairs (regression fixture)"
    )
    assert isinstance(data.get("recall_k"), int) and data["recall_k"] >= 1
    for p in pairs:
        assert p.get("query", "").strip(), f"empty query in seed pair: {p}"
        assert p.get("expected_ref", "").strip(), f"empty expected_ref: {p}"


def test_seed_has_no_secret_shaped_queries():
    """Queries are content-derived — guard against a future harvest accidentally
    baking a token/key/connection-string into the committed fixture."""
    data = json.loads(SEED.read_text())
    blob = "\n".join(p.get("query", "") for p in data["pairs"])
    for pat in (r"sk-[A-Za-z0-9]{8}", r"\bBearer\b", r"postgres(?:ql)?://",
                r"password\s*[:=]", r"[A-Za-z0-9_\-]{40,}"):
        assert not re.search(pat, blob, re.I), f"seed query matches secret-shape /{pat}/"


def test_every_expected_document_is_a_file_this_repo_ships():
    """Each expected_ref must resolve to a tracked file. A seed pointing at a
    document nobody ships can never be retrieved on a fresh instance, and the
    eval would red for a reason that has nothing to do with the ranking."""
    data = json.loads(SEED.read_text())
    missing = [p["expected_ref"] for p in data["pairs"]
               if not (_REPO_ROOT / p["expected_ref"]).is_file()]
    assert not missing, f"seed names documents this repo does not ship: {missing}"


#: A query whose content words are mostly drawn from the opening of the very
#: document it must find is the shape that cannot fail. Deliberately loose — a
#: real question about egress DOES contain the word "egress".
_SELF_FIND_MAX = 0.60


def _opening_overlap(ref: str, query: str) -> float:
    """Fraction of the query's content words that appear in the opening of the
    document it names. 0.0 for an empty query (an empty query is caught by the
    seed-well-formed test, not by this one)."""
    opening = set(_opening_words(_REPO_ROOT / ref))
    qwords = re.findall(r"[a-z0-9]{3,}", query.lower())
    if not qwords:
        return 1.0
    return sum(1 for w in qwords if w in opening) / len(qwords)


def _opening_words(path: Path, n: int = 40) -> list:
    """The first n word tokens of a document, lowercased, frontmatter and
    markdown punctuation stripped — the surface the retired harvester used to
    copy verbatim into the query."""
    text = path.read_text(encoding="utf-8", errors="replace")
    words = re.findall(r"[a-z0-9]{3,}", text.lower())
    return words[:n]


def test_no_seed_query_is_a_copy_of_its_document_opening():
    """THE anti-self-find lock, and the reason this file was rewritten.

    The retired harvester built each query from the expected document's own
    leading 110 characters, so the eval reported recall@10 = 1.0000 and
    MRR = 1.0000 while real questions returned nothing — a sensor measuring
    its own reflection. A query is refused here when most of its content words
    are drawn from the opening of the very document it is supposed to find.

    The bar is deliberately loose (a real question about egress DOES contain
    the word "egress"); it fails the SHAPE that cannot fail, not vocabulary
    overlap."""
    data = json.loads(SEED.read_text())
    offenders = [(p["expected_ref"], f"{_opening_overlap(p['expected_ref'], p['query']):.0%}"
                  " of the query's words come from the document's opening")
                 for p in data["pairs"]
                 if _opening_overlap(p["expected_ref"], p["query"]) > _SELF_FIND_MAX]
    assert not offenders, (
        "seed queries are copied from the documents they are meant to find — "
        f"this is the eval-that-cannot-fail shape: {offenders}"
    )


def test_the_self_find_detector_rejects_the_retired_harvester_shape():
    """NEGATIVE CONTROL — without this, the check above passes because it
    measures nothing.

    Rebuild a query the way the deleted harvester did (the document's own
    leading 110 characters, markdown-stripped) and assert the detector refuses
    it. If this ever goes green, the detector has stopped detecting and the
    seed can silently drift back into asking the corpus to find itself."""
    ref = json.loads(SEED.read_text())["pairs"][0]["expected_ref"]
    raw = (_REPO_ROOT / ref).read_text(encoding="utf-8", errors="replace")
    harvester_query = re.sub(r"[#*>`~_\n\t\r]+", " ", raw[:110]).strip()
    assert _opening_overlap(ref, harvester_query) > _SELF_FIND_MAX, (
        "the retired harvester's own query shape is no longer detected as a "
        f"self-find: {harvester_query!r}"
    )


def test_seed_carries_an_abstain_arm():
    """Without unanswerable questions the whole eval is satisfiable by
    DELETING the similarity floor: recall@k goes to 1.0000 and every off-topic
    question is answered out of the nearest unrelated document."""
    data = json.loads(SEED.read_text())
    unanswerable = data.get("unanswerable")
    assert isinstance(unanswerable, list) and len(unanswerable) >= 5, (
        "seed must carry >=5 unanswerable questions (the abstention arm)"
    )
    for q in unanswerable:
        assert q.strip().endswith("?"), f"unanswerable entry is not a question: {q}"


def test_abstain_questions_are_not_answerable_from_the_shipped_docs():
    """The abstain arm is only honest if the corpus really holds nothing on
    those subjects — otherwise it gates on the retrieval failing to find
    something it SHOULD find."""
    data = json.loads(SEED.read_text())
    docs = " ".join(
        (_REPO_ROOT / p["expected_ref"]).read_text(encoding="utf-8", errors="replace").lower()
        for p in data["pairs"])
    for q in data["unanswerable"]:
        # the distinctive noun of each off-corpus question must be absent
        rare = [w for w in re.findall(r"[a-z]{5,}", q.lower())
                if w not in ("should", "which", "there", "where", "would")]
        assert rare, q
        hits = [w for w in rare if w in docs]
        assert len(hits) < len(rare), (
            f"every distinctive word of an 'unanswerable' question appears in "
            f"the shipped docs — it may not be unanswerable: {q} ({hits})")


# ---------------------------------------------------------------------------
# offline — the runner carries the gate contract
# ---------------------------------------------------------------------------

def test_runner_has_floor_and_recall_contract():
    txt = RUNNER.read_text()
    assert "--floor" in txt, "runner lost the --floor gate arg"
    assert re.search(r'^FLOOR="?0', txt, re.M), "runner lost its default floor"
    assert "recall@" in txt, "runner no longer reports recall@k"
    # exit-code contract: pass -> 0, below floor -> 1
    assert "exit 1" in txt and "exit 0" in txt


def test_runner_has_mrr_floor_gate():
    """R1-EVAL-NO-TEETH: recall@k with limit==k is order-blind — a rerank
    sorted worst-first passed the old gate (recall 0.95) while MRR collapsed
    0.925 -> ~0.10. The MRR floor is the order-sensitivity teeth; losing it
    reopens the hole."""
    txt = RUNNER.read_text()
    assert "--mrr-floor" in txt, "runner lost the --mrr-floor gate arg"
    assert re.search(r'^MRR_FLOOR="?0\.5', txt, re.M), (
        "runner lost its default MRR floor (0.50 — baseline ~0.925, "
        "order-inverted ranker ~0.10)"
    )
    assert "MRR_PASS" in txt, "runner no longer gates on MRR in PASS logic"
    # recall HITs must honor the k-cut, or --limit > k silently inflates recall
    assert re.search(r'-le\s+"\$K"', txt), (
        "runner lost the rank<=k cut on recall hits"
    )


# ---------------------------------------------------------------------------
# live gate — self-harvest from the current store, enforce recall floor
# ---------------------------------------------------------------------------

def _env_val(name: str) -> str:
    """Resolve a secret the way memory.sh does: env first, else cabinet/.env
    (regex-extracted, NEVER printed)."""
    v = os.environ.get(name, "").strip()
    if v:
        return v
    envf = _REPO_ROOT / "cabinet/.env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _neon_reachable(conn: str) -> bool:
    if not conn:
        return False
    p = _run(
        ["psql", conn, "-tAc", "SELECT 1;"],
        timeout=20,
        env={**os.environ, "PGCONNECT_TIMEOUT": "10"},
    )
    return p.returncode == 0 and "1" in p.stdout


def test_live_recall_gate_over_the_question_seed():
    """The real memory_search path, the real store, real questions.

    This is the arm that went from 9/16 to 16/16 when the vec floor was
    corrected from its unmeasured 0.45 to the measured default. It is
    store-local: a box with no Neon skips, and CI pins the ranking
    fingerprint instead."""
    conn = _env_val("NEON_CONNECTION_STRING")
    if not _neon_reachable(conn):
        pytest.skip("Neon not reachable — live retrieval gate skipped (keyless/CI safe)")

    child_env = {**os.environ, "CABINET_ROOT": str(_REPO_ROOT),
                 "NEON_CONNECTION_STRING": conn}
    for name in ("VOYAGE_API_KEY", "CABINET_ID"):
        v = _env_val(name)
        if v:
            child_env[name] = v

    # Unmeasurable rather than red: a store that has not ingested this repo's
    # docs holds none of the seed's expected documents, and scoring recall for
    # absent documents would be a sensor pointed at nothing.
    refs = "|".join(p["expected_ref"] for p in json.loads(SEED.read_text())["pairs"])
    q = _run(["psql", conn, "-tAc",
              "SELECT count(*) FROM cabinet_memory WHERE superseded_by IS NULL "
              "AND source_id = ANY(string_to_array($$" + refs + "$$, '|'));"],
             timeout=30, env=child_env)
    present = int((q.stdout or "0").strip() or 0)
    if present == 0:
        pytest.skip("this store holds none of the seed's expected documents")

    # --limit 20 > k=10 keeps the k-cut order-sensitive (a found-but-buried row
    # counts as a recall MISS instead of being invisible). --mrr-floor 0.50 is
    # the ORDER gate: recall@k alone is order-blind at limit==k.
    r = _run(["bash", str(RUNNER), "--pairs", str(SEED), "--floor", "0.60",
              "--mrr-floor", "0.50", "--abstain-floor", "1.00",
              "--limit", "20", "--json"], timeout=600, env=child_env)
    summary = json.loads(r.stdout)
    assert r.returncode == 0, (
        f"retrieval gate FAILED — recall/MRR/abstain below floor: {summary}"
    )
    assert summary["pass"] is True
    assert summary["mrr"] >= 0.50, summary
    assert summary["abstain_total"] >= 5, (
        "the abstain arm must actually have run — without it this gate is "
        "satisfied by deleting the similarity floor"
    )
    assert summary["abstain_rate"] == 1.0, summary
