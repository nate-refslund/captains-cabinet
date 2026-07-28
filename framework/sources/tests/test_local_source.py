"""``framework.sources.local.LocalNotesSource`` — the local-folder recall seam.

WHY THIS ADAPTER EXISTS AT ALL, which is what every arm here is really pinning:
before it, a deployment declaring ``autonomy.flavor: personal`` got no
``instance/config/sources.yml``, so ``get_source()`` fail-closed to
``NullPersonalSource`` — ``available() -> False``, ``search() -> {"hits": []}``
— and the one preset shaped for an operator who does not run a company shipped
with zero recall.

The arms below are ordered by what they would catch:
  * LIVE — a real folder produces real, ranked, cited hits (this is the whole
    point; a passing suite with an empty corpus would prove nothing);
  * BOUND — sources.yml -> get_source() actually returns THIS class, so the
    generator's emission is wired to the resolver rather than merely present;
  * JAILED — traversal and symlink escapes are refused, not followed;
  * BOUNDED — the file cap and byte cap actually bite;
  * HONEST — content_ts is derived or absent, NEVER mtime; an empty or absent
    folder reports unavailable rather than pretending;
  * READ-ONLY BY CONSTRUCTION — the module exposes no write verb at all.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from framework import sources as src_pkg
from framework.sources.base import PersonalSource
from framework.sources.local import (MAX_FILE_BYTES, MAX_FILES,
                                     LocalNotesSource)


@pytest.fixture(autouse=True)
def _isolate():
    """Clean resolver cache + CABINET_ROOT + the adapter's env knob around
    every case, so a bound source never leaks into the rest of the suite."""
    src_pkg._reset_cache()
    saved_root = os.environ.get("CABINET_ROOT")
    saved_local = os.environ.get("CABINET_LOCAL_SOURCE_ROOT")
    saved_modules = set(sys.modules)
    try:
        yield
    finally:
        src_pkg._reset_cache()
        for key, val in (("CABINET_ROOT", saved_root),
                         ("CABINET_LOCAL_SOURCE_ROOT", saved_local)):
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        for name in set(sys.modules) - saved_modules:
            sys.modules.pop(name, None)


def _notes(root: Path) -> Path:
    d = root / "notes"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-07-20-payments.md").write_text(
        "---\ndate: 2026-07-20\n---\n"
        "# Payments retry\n\n"
        "The retry backoff drops idempotency keys after three attempts.\n",
        encoding="utf-8")
    (d / "groceries.md").write_text(
        "# Groceries\n\nmilk, eggs, coffee\n", encoding="utf-8")
    return d


# --------------------------------------------------------------------------
# LIVE — the property the null adapter cannot have
# --------------------------------------------------------------------------
def test_available_and_search_return_real_hits(tmp_path):
    src = LocalNotesSource(root=str(_notes(tmp_path)))
    assert src.available() is True
    hits = src.search("payments", topic="idempotency retry")["hits"]
    assert hits, "a folder containing the query terms returned no hits"
    top = hits[0]
    assert top["path"] == "2026-07-20-payments.md"
    assert top["heading"] == "Payments retry"
    assert "idempotency" in top["text"]
    assert 0.0 < top["base_score"] <= 1.0


def test_ranking_prefers_the_on_topic_note(tmp_path):
    src = LocalNotesSource(root=str(_notes(tmp_path)))
    hits = src.search("payments retry backoff")["hits"]
    assert hits[0]["path"] == "2026-07-20-payments.md"
    assert all(h["path"] != "groceries.md" for h in hits[:1])


def test_query_with_no_match_returns_empty_not_noise(tmp_path):
    """An unmatched query returns NOTHING. Returning the best of a bad set is
    how a recall surface starts leaking unrelated material into a briefing."""
    src = LocalNotesSource(root=str(_notes(tmp_path)))
    assert src.search("quantum tunnelling")["hits"] == []


def test_null_adapter_would_have_failed_this_suite(tmp_path):
    """The pre-change behaviour, pinned as the thing being replaced: the null
    adapter is what a personal deployment resolved to, and it can answer
    nothing about a folder that plainly contains the answer."""
    from framework.sources.null import NullPersonalSource
    null = NullPersonalSource()
    _notes(tmp_path)
    assert null.available() is False
    assert null.search("payments", topic="idempotency retry")["hits"] == []


# --------------------------------------------------------------------------
# BOUND — the emitted config actually reaches the resolver
# --------------------------------------------------------------------------
def test_sources_yml_binding_resolves_to_this_adapter(tmp_path):
    cfg = tmp_path / "instance/config"
    cfg.mkdir(parents=True)
    notes = _notes(tmp_path)
    (cfg / "sources.yml").write_text(
        "adapter: framework.sources.local:LocalNotesSource\n"
        f"local_root: {notes}\n", encoding="utf-8")
    os.environ["CABINET_ROOT"] = str(tmp_path)
    src_pkg._reset_cache()
    bound = src_pkg.get_source()
    assert isinstance(bound, LocalNotesSource)
    assert isinstance(bound, PersonalSource)   # structural Protocol conformance
    assert bound.search("payments")["hits"]


def test_local_root_from_config_is_root_relative(tmp_path):
    """A relative ``local_root`` resolves under CABINET_ROOT — never under the
    process cwd, because a daemon's cwd is not a consented scope."""
    cfg = tmp_path / "instance/config"
    cfg.mkdir(parents=True)
    _notes(tmp_path)
    (cfg / "sources.yml").write_text(
        "adapter: framework.sources.local:LocalNotesSource\n"
        "local_root: notes\n", encoding="utf-8")
    os.environ["CABINET_ROOT"] = str(tmp_path)
    from framework.sources.local import resolve_root
    assert resolve_root() == tmp_path / "notes"


def test_undeclared_root_resolves_to_nothing_not_to_the_cabinets_own_docs(tmp_path):
    """THE CONFIDENT FALSE POSITIVE, pinned (measured 2026-07-28).

    ``resolve_root()`` used to fall back to ``<CABINET_ROOT>/vault`` when
    nothing was declared. ``vault/`` is the CABINET'S OWN shipped
    documentation — ``vault/README.md`` and ``vault/architecture.md`` are
    tracked files in this repo — so a personal hatch that granted no folder got
    ``available() -> True`` and recall answering out of the framework's own
    docs as if they were the operator's notes. Nothing downstream could tell
    that apart from working recall, which is why it is worse than the honest
    empty it replaced.

    This arm reproduces the exact shape: a deployment root that HAS a populated
    ``vault/``, and NO declaration anywhere."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "README.md").write_text(
        "# vault\n\nWhere a document lives in the cabinet.\n", encoding="utf-8")
    (vault / "architecture.md").write_text(
        "# Architecture\n\ncabinet layering\n", encoding="utf-8")
    (tmp_path / "instance/config").mkdir(parents=True)
    (tmp_path / "instance/config/sources.yml").write_text(
        "adapter: framework.sources.local:LocalNotesSource\n", encoding="utf-8")
    os.environ["CABINET_ROOT"] = str(tmp_path)
    os.environ.pop("CABINET_LOCAL_SOURCE_ROOT", None)
    from framework.sources.local import resolve_root
    assert resolve_root() is None, (
        "an undeclared notes folder resolved to a path — the pre-2026-07-28 "
        "fallback bound the cabinet's own vault/ and called it the operator's")
    src_pkg._reset_cache()
    bound = src_pkg.get_source()
    assert isinstance(bound, LocalNotesSource)
    assert bound.available() is False
    assert bound.search("cabinet architecture")["hits"] == []
    assert bound.binding_status() == {
        "declared": False, "root": None, "exists": False, "notes": 0}


def test_binding_status_separates_unset_from_missing_from_empty(tmp_path):
    """Three states, three fixes. Collapsing them into one boolean is what let
    "recall is fine" and "recall is pointed at the wrong thing" read the same."""
    os.environ.pop("CABINET_LOCAL_SOURCE_ROOT", None)
    os.environ["CABINET_ROOT"] = str(tmp_path)
    assert LocalNotesSource().binding_status()["declared"] is False

    gone = LocalNotesSource(root=str(tmp_path / "nope")).binding_status()
    assert gone["declared"] is True and gone["exists"] is False

    empty = tmp_path / "empty"
    empty.mkdir()
    got = LocalNotesSource(root=str(empty)).binding_status()
    assert got["declared"] is True and got["exists"] is True and got["notes"] == 0

    live = LocalNotesSource(root=str(_notes(tmp_path))).binding_status()
    assert live["declared"] and live["exists"] and live["notes"] > 0


def test_read_note_refuses_when_no_root_was_granted(tmp_path):
    """No scope granted is the same refusal as a missing file — a traversal
    attempt against an unbound adapter must not learn that it is unbound."""
    os.environ.pop("CABINET_LOCAL_SOURCE_ROOT", None)
    os.environ["CABINET_ROOT"] = str(tmp_path)
    with pytest.raises(FileNotFoundError):
        LocalNotesSource().read_note("anything.md")


def test_env_override_beats_config(tmp_path):
    cfg = tmp_path / "instance/config"
    cfg.mkdir(parents=True)
    other = tmp_path / "elsewhere"
    other.mkdir()
    (cfg / "sources.yml").write_text("local_root: notes\n", encoding="utf-8")
    os.environ["CABINET_ROOT"] = str(tmp_path)
    os.environ["CABINET_LOCAL_SOURCE_ROOT"] = str(other)
    from framework.sources.local import resolve_root
    assert resolve_root() == other


# --------------------------------------------------------------------------
# JAILED
# --------------------------------------------------------------------------
def test_read_note_refuses_traversal(tmp_path):
    notes = _notes(tmp_path)
    secret = tmp_path / "secret.md"
    secret.write_text("# private\n", encoding="utf-8")
    src = LocalNotesSource(root=str(notes))
    assert src.read_note("2026-07-20-payments.md")
    with pytest.raises(FileNotFoundError):
        src.read_note("../secret.md")


def test_symlink_out_of_the_root_is_skipped_not_followed(tmp_path):
    notes = _notes(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leak.md").write_text(
        "# Leak\n\npayments idempotency secret\n", encoding="utf-8")
    (notes / "link.md").symlink_to(outside / "leak.md")
    src = LocalNotesSource(root=str(notes))
    hits = src.search("payments idempotency")["hits"]
    assert all("link.md" not in h["ref"] for h in hits), (
        "a symlink escaping the declared root was followed")
    with pytest.raises(FileNotFoundError):
        src.read_note("link.md")


def test_hidden_directories_are_never_read(tmp_path):
    notes = _notes(tmp_path)
    git = notes / ".git"
    git.mkdir()
    (git / "COMMIT_EDITMSG.md").write_text(
        "payments idempotency\n", encoding="utf-8")
    src = LocalNotesSource(root=str(notes))
    assert all(".git" not in h["ref"]
               for h in src.search("payments idempotency")["hits"])


# --------------------------------------------------------------------------
# BOUNDED
# --------------------------------------------------------------------------
def test_file_cap_bites(tmp_path):
    notes = tmp_path / "many"
    notes.mkdir()
    for i in range(MAX_FILES + 25):
        (notes / f"n{i:04d}.md").write_text(
            f"# Note {i}\n\npayments idempotency\n", encoding="utf-8")
    src = LocalNotesSource(root=str(notes))
    assert len(src._files()) == MAX_FILES


def test_oversize_file_is_truncated_not_skipped(tmp_path):
    """A file over the byte cap is read TRUNCATED. Degraded recall is honest;
    a silent skip would report "not in your notes" about something that is."""
    notes = tmp_path / "big"
    notes.mkdir()
    (notes / "huge.md").write_text(
        "# Huge\n\npayments\n" + ("filler word " * 40000), encoding="utf-8")
    src = LocalNotesSource(root=str(notes))
    assert src.available() is True
    assert len(src._read(notes / "huge.md")) == MAX_FILE_BYTES
    assert src.search("payments")["hits"]


# --------------------------------------------------------------------------
# HONEST
# --------------------------------------------------------------------------
def test_content_ts_is_derived_or_absent_never_mtime(tmp_path):
    notes = tmp_path / "dated"
    notes.mkdir()
    (notes / "front.md").write_text(
        "---\ndate: 2026-03-04\n---\n# Front\n\nalpha topic\n", encoding="utf-8")
    (notes / "2026-05-06-name.md").write_text(
        "# Named\n\nalpha topic\n", encoding="utf-8")
    (notes / "undated.md").write_text("# Undated\n\nalpha topic\n",
                                      encoding="utf-8")
    os.utime(notes / "undated.md", (1_000_000, 1_000_000))
    src = LocalNotesSource(root=str(notes))
    got = {h["path"]: h["content_ts"] for h in src.search("alpha topic")["hits"]}
    assert got["front.md"] == "2026-03-04T00:00:00Z"
    assert got["2026-05-06-name.md"] == "2026-05-06T00:00:00Z"
    assert got["undated.md"] is None, (
        "an underivable date must stay None — the leak fence drops undated "
        "hits on purpose, and a fabricated timestamp defeats the fence")


def test_absent_or_empty_folder_reports_unavailable(tmp_path):
    assert LocalNotesSource(root=str(tmp_path / "nope")).available() is False
    empty = tmp_path / "empty"
    empty.mkdir()
    assert LocalNotesSource(root=str(empty)).available() is False
    assert LocalNotesSource(root=str(empty)).search("anything")["hits"] == []


def test_everything_a_folder_cannot_answer_stays_empty(tmp_path):
    """A notes directory is not a mailbox, a dossier index or a deploy log.
    Each of these is an honest empty; the tri-state probes are honest UNKNOWN
    (None), never a fabricated boolean."""
    src = LocalNotesSource(root=str(_notes(tmp_path)))
    assert src.find_reply_candidates() == []
    assert src.person_intel("anyone") == ""
    assert src.open_commitments("owed_by_captain") == []
    assert src.briefing_commitments() == []
    assert src.find_threads() == []
    assert src.gather({}) == {}
    assert src.draft_fn({}, {}) == ""
    assert src.deploy_health("app") == {}
    assert src.captain_replied_since("x", None) is None
    assert src.still_awaiting("x") is None


# --------------------------------------------------------------------------
# READ-ONLY BY CONSTRUCTION
# --------------------------------------------------------------------------
def test_module_exposes_no_write_verb(tmp_path):
    """Structural, not policy. Material an operator may legitimately READ at
    work is frequently not material they may CHANGE, and undoing a write to a
    colleague's record does not un-notify the colleague — so the guarantee has
    to be that no write verb exists to be enabled."""
    import framework.sources.local as mod
    write_verbs = ("queue_draft", "deliver", "append_note", "write_daily_note",
                   "log_reasoning", "ensure_signature", "write", "save",
                   "update", "delete")
    src = LocalNotesSource(root=str(_notes(tmp_path)))
    for verb in write_verbs:
        assert not hasattr(src, verb), f"local source grew a write verb: {verb}"
    exported = [n for n in dir(mod) if not n.startswith("_")]
    assert not any("dispatch" in n.lower() for n in exported), (
        "the local adapter must not ship a dispatch class")


# --------------------------------------------------------------------------
# FRONTMATTER IS METADATA, NOT THE OPERATOR'S WORDS
# --------------------------------------------------------------------------
def test_frontmatter_never_becomes_the_operators_own_words(tmp_path):
    """FOUND BY A HOSTILE PASS, 2026-07-28, through the real
    ``first-briefing.sh --local`` chain on the shape this adapter EXISTS for —
    an Obsidian folder, whose ``date:`` frontmatter is the primary
    ``content_ts`` derivation this module documents.

    A headingless note is ONE chunk, so its frontmatter WAS the head of the
    chunk body. Both operator-facing readers then reported machinery as the
    operator's own material: the genesis card's quote line — *"I did not ask
    you for this, I read it"* — rendered ``"--- date: 2026-07-20 title: …
    tags: [notes] status: open --- The storefront widget alignment drifts…"``,
    and ``genesis._join_terms`` captioned three cited notes ``Shared wording:
    status, title, date, open``, key names present in every note outscoring
    (and evicting, at ``_MAX_JOIN_TERMS``) the one real word two of them
    shared.

    THE ARM IS THE PROPERTY: no frontmatter KEY reaches the chunk text, and the
    prose does."""
    notes = tmp_path / "fm"
    notes.mkdir()
    (notes / "2026-07-20-widget.md").write_text(
        "---\ndate: 2026-07-20\ntitle: widget\ntags: [notes]\nstatus: open\n---\n\n"
        "The storefront widget alignment drifts on checkout.\n", encoding="utf-8")
    hits = LocalNotesSource(root=str(notes)).search("storefront checkout")["hits"]
    assert hits, "the note must still be findable by its prose"
    text = hits[0]["text"]
    assert "The storefront widget alignment drifts on checkout." in text
    for key in ("date:", "title:", "tags:", "status:", "---"):
        assert key not in text, (
            f"{key!r} survived into the chunk the operator is quoted from — "
            "the card would report metadata as their own words")
    assert hits[0]["content_ts"] == "2026-07-20T00:00:00Z", (
        "dating reads the RAW text and must be unaffected by the strip")


def test_a_bare_rule_is_not_frontmatter(tmp_path):
    """DEGENERATE END, and the one that decides whether the strip is safe: a
    note OPENING with a thematic break has an unterminated ``---``, and eating
    to end-of-file would silently delete the whole note from recall. Also
    covers the ``...`` YAML terminator and a note that is frontmatter and
    nothing else."""
    notes = tmp_path / "edge"
    notes.mkdir()
    (notes / "rule.md").write_text(
        "---\n\nthe storefront ledger reconciliation ran late.\n", encoding="utf-8")
    (notes / "dots.md").write_text(
        "---\ndate: 2026-02-02\n...\n\nthe storefront ledger arrived.\n",
        encoding="utf-8")
    (notes / "onlyfm.md").write_text(
        "---\ntitle: storefront ledger\n---\n", encoding="utf-8")
    src = LocalNotesSource(root=str(notes))
    got = {h["path"]: h["text"] for h in src.search("storefront ledger")["hits"]}
    assert "reconciliation ran late" in got.get("rule.md", ""), (
        "an unterminated --- is a horizontal rule; the note must survive whole")
    assert got.get("dots.md", "").strip() == "the storefront ledger arrived."
    assert "onlyfm.md" not in got, (
        "a note that is nothing but frontmatter has no prose to recall, and an "
        "empty hit citing a file is a citation that shows nothing")
