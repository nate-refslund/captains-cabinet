"""Leak audit + schema parity for the Testburg demo fixture (PC-B demo kit).

Two binding contracts over ``cabinet/fixtures/testburg/`` (see its README):

1. LEAK AUDIT — the fixture is the PUBLIC demo estate; no real-value pattern
   may appear anywhere under it, in file contents OR file names. The banned
   list below (``BANNED_PATTERNS``) is the authoritative one the fixture
   README points at; it is case-insensitive and includes a digit-run guard
   for telegram-chat-id-shaped numbers. Plain-substring semantics on
   purpose: ordinary words containing a banned name (the participle of
   "desig·n·ate", say) are rejected too — reword the fixture, never relax
   the pattern.

2. SCHEMA PARITY THROUGH THE REAL READERS — chronicle rows must satisfy the
   REAL ingest module's guards (``cabinet/scripts/world-chronicle.py``:
   ``assert_scrubbed``, ``ident_ok``, ``_TS_RE``, ``chronicle_path_for``
   partitioning, verb grammar) and every ``src: undo`` record must be BYTE
   REPRODUCIBLE by running ``normalize_undo`` over the journal line its ref
   points at. Journal rows must load through the product readers
   (``action_undo._read_journal`` last-write-wins collapse +
   ``acted_overlay.load_journal_rows``) and re-validate with
   ``action_undo._validate_row``; their inverse ops must equal what
   ``inverse_for`` derives for the row's (kind, backend).

The Wave-B receipt-field contract (why / cost attributed+unattributed /
active+expired+undone states / exactly one ``demo: true`` row) is asserted
against the FIXED story clock (2026-07-10T08:00Z), never the wall clock —
the fixture stays deterministic forever.
"""
from __future__ import annotations

import importlib.util as _ilu
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "cabinet" / "fixtures" / "testburg"
if str(REPO) not in sys.path:          # defensive: rootdir conftest usually
    sys.path.insert(0, str(REPO))      # puts the repo root here already

from framework.attention import acted_overlay  # noqa: E402
from framework.frontdoor import action_undo    # noqa: E402

_SCRIPT = REPO / "cabinet" / "scripts" / "world-chronicle.py"
_spec = _ilu.spec_from_file_location("world_chronicle", _SCRIPT)
wch = _ilu.module_from_spec(_spec)
sys.modules["world_chronicle"] = wch
_spec.loader.exec_module(wch)

# ── the leak-audit contract ──────────────────────────────────────────────────
# Case-insensitive plain substrings: the captain's given/family names, the
# employer/product domains, colleague first names, the corp account slug —
# plus the home-directory prefix and a digit-run guard (telegram chat ids).
BANNED_PATTERNS = [
    "nate", "refslund", "stepnetwork", "jfmedier", "polads", "stephie",
    "kristoffer", "ulrik", "solveig", "maria", "naref", "/users/nate",
]
_DIGIT_RUN = re.compile(r"[0-9]{9,}")

STORY_NOW = "2026-07-10T08:00:00Z"     # the fixture's fixed clock (README)

_CHRONICLE_VERBS = (
    set(wch.VERB_MAP.values())
    | {"undo.journaled", "consequence.proposed", "consequence.acted",
       "tool.call"}
    | {"mail.family", "captain.family", "gap.family", "role.family",
       "org.other"}
)


def _fixture_files() -> list[Path]:
    files = [p for p in sorted(FIXTURE.rglob("*"))
             if p.is_file() and "__pycache__" not in p.parts]
    assert files, f"fixture missing or empty: {FIXTURE}"
    return files


def _chronicle_files() -> list[Path]:
    files = sorted((FIXTURE / "world").glob("chronicle-*.jsonl"))
    assert len(files) == 3, "the story is three chronicle days"
    return files


def _journal_rows() -> list[dict]:
    """The fixture journal through the REAL reader (collapse included)."""
    rows = []
    for f in sorted((FIXTURE / "undo").glob("undo-journal-*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


# ── 1. the leak audit ────────────────────────────────────────────────────────

class TestLeakAudit:
    def test_fixture_exists_and_is_labeled(self):
        readme = FIXTURE / "README.md"
        assert readme.is_file(), "the fixture must carry its README contract"
        text = readme.read_text(encoding="utf-8")
        assert "synthetic" in text.lower() and "demo" in text.lower()
        assert "BANNED_PATTERNS" in text, "README must point at this audit"

    def test_no_real_value_patterns_in_contents(self):
        hits = []
        for f in _fixture_files():
            text = f.read_text(encoding="utf-8", errors="replace")
            low = text.lower()
            for pat in BANNED_PATTERNS:
                if pat in low:
                    hits.append(f"{f.relative_to(FIXTURE)}: contains {pat!r}")
            m = _DIGIT_RUN.search(text)
            if m:
                hits.append(f"{f.relative_to(FIXTURE)}: digit run {m.group(0)!r}"
                            " (telegram-id shaped)")
        assert not hits, "leak audit failed:\n" + "\n".join(hits)

    def test_no_real_value_patterns_in_paths(self):
        hits = []
        for f in _fixture_files():
            rel = str(f.relative_to(FIXTURE)).lower()
            for pat in BANNED_PATTERNS:
                if pat in rel:
                    hits.append(f"{rel}: path contains {pat!r}")
            # YYYY-MM-DD date tokens are the one sanctioned digit shape in
            # fixture names; strip them, then flag ANY remaining 9+ digit
            # run once hyphens are joined — an id split by hyphens
            # ("…-123456789.md") is still id-shaped and must not pass.
            undated = re.sub(r"\d{4}-\d{2}-\d{2}", "", rel)
            if _DIGIT_RUN.search(undated.replace("-", "")):
                hits.append(f"{rel}: path carries an id-shaped digit run")
        assert not hits, "leak audit failed on paths:\n" + "\n".join(hits)

    def test_emails_are_example_dot_com_only(self):
        """Synthetic e-mail addresses are allowed ONLY in the markdown story
        surfaces and only at example.com; the chronicle can never carry any
        (assert_scrubbed drops records with e-mail shapes)."""
        email = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
        for f in _fixture_files():
            text = f.read_text(encoding="utf-8", errors="replace")
            for addr in email.findall(text):
                assert addr.lower().endswith("example.com"), (
                    f"{f.relative_to(FIXTURE)}: non-example.com address {addr}")


# ── 2. chronicle schema parity ───────────────────────────────────────────────

class TestChronicleParity:
    def test_rows_parse_and_pass_the_real_guards(self):
        for f in _chronicle_files():
            for line in f.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                assert rec.get("v") == wch.SCHEMA_VERSION
                for key in ("src", "verb", "kind", "actor", "ts", "ref", "iid"):
                    assert key in rec, f"{f.name}: record missing {key}"
                assert rec["src"] in {"org_events", "consequence", "undo",
                                      "toollog"}
                assert rec["verb"] in _CHRONICLE_VERBS
                assert wch.ident_ok(rec["actor"]), rec["actor"]
                assert wch.ident_ok(rec["kind"]), rec["kind"]
                assert wch._TS_RE.match(rec["ts"]), rec["ts"]
                assert wch.assert_scrubbed(rec), f"{f.name}: scrub gate hit"
                attrs = rec.get("attrs", {})
                assert isinstance(attrs, dict)
                for k, v in attrs.items():
                    assert wch.ident_ok(str(v)), f"attr {k}={v!r}"

    def test_partition_matches_source_date(self):
        """Every record sits in the file chronicle_path_for would choose —
        including the reversal record whose SOURCE ts predates its ingest
        day (the partition-by-source-date property of the live writer)."""
        for f in _chronicle_files():
            for line in f.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                assert wch.chronicle_path_for(rec).name == f.name

    def test_iids_are_monotonic_and_contiguous(self):
        iids = []
        per_file_order = True
        for f in _chronicle_files():
            prev = None
            for line in f.read_text(encoding="utf-8").splitlines():
                iid = json.loads(line)["iid"]
                iids.append(iid)
                if prev is not None and iid <= prev:
                    per_file_order = False
                prev = iid
        assert per_file_order, "within a file, append order = ingest order"
        assert sorted(iids) == list(range(1, len(iids) + 1)), (
            "iids must be the contiguous monotonic ingest sequence")

    def test_undo_records_reproduce_from_journal_lines(self):
        """Byte-level parity: every src=undo record equals normalize_undo()
        over the exact journal line its ref points at."""
        blobs = {p.name: p.read_bytes()
                 for p in (FIXTURE / "undo").glob("undo-journal-*.jsonl")}
        checked = 0
        for f in _chronicle_files():
            for line in f.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                if rec["src"] != "undo":
                    continue
                fname, off = rec["ref"].rsplit(":", 1)
                blob = blobs[fname]
                start = int(off)
                end = blob.index(b"\n", start)
                src_line = blob[start:end].decode("utf-8")
                rebuilt = wch.normalize_undo(src_line, rec["ref"])
                expect = {k: v for k, v in rec.items() if k != "iid"}
                assert rebuilt == expect, f"undo record at {rec['ref']} drifted"
                checked += 1
        assert checked >= 8, "all journal lines should surface in the chronicle"


# ── 3. undo-journal parity through the product readers ───────────────────────

class TestJournalParity:
    @pytest.fixture()
    def collapsed(self, monkeypatch) -> list[dict]:
        monkeypatch.setenv("CABINET_UNDO_DIR", str(FIXTURE / "undo"))
        return action_undo._read_journal()

    def test_collapse_and_validate(self, collapsed):
        raw = _journal_rows()
        assert len(raw) == 8, "8 physical lines (two same-jid pairs)"
        assert len(collapsed) == 6, "6 logical rows after last-write-wins"
        for row in collapsed:
            action_undo._validate_row(row)

    def test_acted_overlay_reader_agrees(self, collapsed):
        overlay_rows = acted_overlay.load_journal_rows(base=FIXTURE / "undo")
        assert {r["jid"] for r in overlay_rows} == {r["jid"] for r in collapsed}

    def test_pairs_collapse_to_final_state(self, collapsed):
        by_jid = {r["jid"]: r for r in collapsed}
        r1 = by_jid["jid-tb-r1-cos-checklist"]
        assert r1["created"].get("path"), "enrichment line must win for R1"
        assert r1["executed_at"], "enrichment carries executed_at"
        r2 = by_jid["jid-tb-r2-cpo-statusmove"]
        assert r2["status"] == "reversed" and r2["reversed_at"], (
            "reversal line must win for R2")

    def test_inverse_ops_match_the_registry(self, collapsed):
        """Real rows carry the inverse inverse_for() derives for their
        (kind, backend); the seeded demo row carries op "none" + a demo
        reason — a demo receipt NEVER claims an undo that is not registered
        (emit-demo-receipt.sh doctrine)."""
        for row in collapsed:
            if row.get("demo") is True:
                assert row["inverse"]["op"] == "none"
                assert "demo" in row["inverse"]["args"].get("reason", "")
                continue
            derived = action_undo.inverse_for(row["kind"], row["backend"],
                                              {}, {}, {})
            assert row["inverse"]["op"] == derived["op"], (
                f"{row['jid']}: inverse op drifted from inverse_for()")
            assert action_undo.act_first_eligible(row["kind"], row["backend"]), (
                f"{row['jid']}: acted row must be act-first eligible")

    def test_receipt_fields_cover_the_grammar(self, collapsed):
        """Wave-B receipt grammar THROUGH the real grammar module
        (framework/frontdoor/action_language.py): why present on every row,
        both attributed and honestly-unattributed costs, one demo row."""
        from framework.frontdoor import action_language as al

        # why — on every row, human-sentence shaped, via the real reader.
        for row in collapsed:
            why = al.why_of(row)
            assert isinstance(why, str) and len(why) > 20, (
                f"{row['jid']}: receipt why missing/too thin")
        # cost — attributed rows validate through _valid_cost; unattributed
        # rows OMIT the field (honest absence) and render "unattributed".
        attributed = [r for r in collapsed if al.cost_of(r) is not None]
        unattributed = [r for r in collapsed if al.cost_of(r) is None]
        assert len(attributed) >= 2 and len(unattributed) >= 2
        for r in attributed:
            assert al.cost_line(r).startswith("cost: ~$"), r["jid"]
        for r in unattributed:
            assert "cost" not in r, (
                f"{r['jid']}: an unattributed row omits the field entirely — "
                "a malformed dict would fail closed, but the fixture models "
                "the honest absence")
            assert al.cost_line(r) == "cost: unattributed"
        # demo — exactly one seeded row, self-declaring in its why.
        demo_rows = [row for row in collapsed if "demo" in row]
        assert len(demo_rows) == 1 and demo_rows[0]["demo"] is True
        assert "demo" in demo_rows[0]["why"].lower()

    def test_states_active_expired_undone(self, collapsed):
        undone = [r for r in collapsed if r["status"] == "reversed"]
        executed = [r for r in collapsed if r["status"] == "executed"]
        assert len(undone) == 1 and undone[0]["reversed_at"]
        active = [r for r in executed if r["ttl_expires_at"] > STORY_NOW]
        expired = [r for r in executed if r["ttl_expires_at"] <= STORY_NOW]
        assert active and expired, (
            "the story needs both an active and an expired undo window "
            f"at the fixed story clock {STORY_NOW}")


# ── 4. the story surfaces exist and are demo-labeled ─────────────────────────

class TestStorySurfaces:
    def test_queued_draft(self):
        draft = FIXTURE / "drafts" / "newsletter-issue-1.md"
        text = draft.read_text(encoding="utf-8")
        assert "status: queued" in text and "demo_fixture: true" in text
        assert "QUEUED DRAFT" in text, "the draft must label itself unsent"

    def test_two_tier2_notes(self):
        notes = sorted((FIXTURE / "notes" / "tier2").rglob("*.md"))
        assert len(notes) == 2
        for n in notes:
            text = n.read_text(encoding="utf-8")
            assert "demo_fixture: true" in text
            assert text.startswith("---"), "tier2 notes carry frontmatter"

    def test_first_briefing(self):
        briefing = FIXTURE / "briefing" / "first-briefing-2026-07-07.md"
        text = briefing.read_text(encoding="utf-8")
        assert "LOCAL-FIRST receipt" in text
        assert "captain_ratified: false" in text, "propose-only cards"
        assert "demo fixture" in text.lower(), "briefing must self-label"

    def test_note_hashes_are_real(self):
        """The journal's wrote_sha256 fingerprints are true hashes of the
        shipped notes — the fixture is internally consistent."""
        import hashlib
        by_jid = {}
        for row in _journal_rows():
            by_jid[row["jid"]] = row      # last line wins, like the reader
        pairs = [
            ("jid-tb-r1-cos-checklist",
             FIXTURE / "notes" / "tier2" / "cos" / "2026-07-08-bakery-site-launch.md"),
            ("jid-tb-r4-cro-audience",
             FIXTURE / "notes" / "tier2" / "cro" / "2026-07-09-newsletter-audience-research.md"),
        ]
        for jid, note in pairs:
            want = hashlib.sha256(note.read_bytes()).hexdigest()
            assert by_jid[jid]["created"]["wrote_sha256"] == want, (
                f"{jid}: wrote_sha256 no longer matches {note.name} — "
                "re-run cabinet/fixtures/testburg/generate.py")
