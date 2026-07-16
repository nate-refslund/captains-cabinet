"""Tests for cabinet/scripts/memory-distill.py (lane BC — grow by
distillation, not accretion) + the retro consolidation-step lint.

Hermetic by construction: every run points CABINET_ROOT at a pytest tmp
tree carrying fixture ledgers and a COPY of lib/memory.sh; redis-cli is a
PATH shim that logs its argv (NO real redis, NO psql, NO network). Pins:

  * per-topic sectioning — entries sharing a salient title token group
    under one deterministic topic section;
  * no content loss — EVERY H2 entry of every ledger appears in the digest
    (date + title), counts match, officer-notes are counted-not-distilled;
  * idempotent re-run — byte-identical output, no wall-clock content
    (proposal AND promoted forms);
  * PROPOSAL-ONLY default — the default run writes ONLY the .proposal.md
    review surface: the promoted boot file is NOT written and NOTHING is
    enqueued (negative controls for the self-ratification gate — a mutant
    that writes the boot path or enqueues on default fails here);
  * REVIEW-FRESHNESS GATE — --apply refuses (exit 3, no promoted file, no
    queue) when the proposal is missing, hand-tampered, or stale vs the
    live ledgers; only a byte-fresh reviewed proposal promotes;
  * --apply promotes the boot surface WITHOUT the PROPOSAL banner and
    enqueues captain_law_summary rows with trust=reflection and NEVER
    trust=captain, through the real memory_queue_embed (jq --arg);
  * --check staleness tell — 0 fresh / 3 after a ledger grows / 4 when no
    digest was ever promoted (the cabinet-doctor AMBER probe contract);
  * both digest paths stay untracked (gitignore rule pins the runtime class);
  * retro-step lint — both retro skills AND their doctrine-pack copies
    carry the consolidated_belief terminal step incl. failure-pattern
    emission (fails on the pre-lane skill bodies / stale pack copies);
  * pack parity — the doctrine-pack retro copies are byte-exact canonical
    memory/skills bodies under pack frontmatter (silent copy⇄canonical
    drift was a shipped-pack defect; now it fails loud).

Run: python3.12 -m pytest cabinet/scripts/tests/test_memory_distill.py -q
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "cabinet" / "scripts" / "memory-distill.py"
MEMORY_SH = REPO / "cabinet" / "scripts" / "lib" / "memory.sh"

DECISIONS = """# Captain Decisions — Append-Only Log

Preamble text (never distilled).

<!-- Append entries below this line. -->

## 2026-06-23 — Telegram warroom wiring deferred

- **Decision:** don't wire the telegram warroom group yet.
- **Why:** no fleet posting to a group today.
- **Logged by:** cos · 2026-06-23T07:55Z

## 2026-06-24 — Telegram DM stays the single channel

- **Decision:** DM-only until multi-officer.
- **Logged by:** cos · 2026-06-24T08:00Z

## Paddle VAT handling (2026-06-25)

- **Decision:** advertiser-type-based inclusion.
- **Logged by:** cos · 2026-06-25T09:00Z

### officer-note — appended by cos @ 2026-06-25T10:00:00Z [trust:officer]

An officer observation that must be counted but never distilled as law.
"""

PATTERNS = """# Captain Patterns — Standing Behaviors

Preamble.

## always-thread-replies telegram

- **Rule:** reply in thread.
"""

INTENTS = """# Captain Intents — Inferred Latent Goals

Preamble.

## 2026-07-01 — wants boot context lean

- **Inferred goal:** keep boot injection small but complete.
"""


# --------------------------------------------------------------- helpers ----
def make_root(tmp_path: Path, with_ledgers: bool = True) -> Path:
    root = tmp_path / "cabroot"
    (root / "shared" / "interfaces").mkdir(parents=True)
    lib = root / "cabinet" / "scripts" / "lib"
    lib.mkdir(parents=True)
    shutil.copy(MEMORY_SH, lib / "memory.sh")
    if with_ledgers:
        iface = root / "shared" / "interfaces"
        (iface / "captain-decisions.md").write_text(DECISIONS)
        (iface / "captain-patterns.md").write_text(PATTERNS)
        (iface / "captain-intents.md").write_text(INTENTS)
    return root


def make_redis_shim(tmp_path: Path) -> tuple[Path, Path]:
    """A fake redis-cli that appends its full argv (space-joined; the embed
    payload is a single jq -c line) to $REDIS_SHIM_LOG and exits 0."""
    bindir = tmp_path / "shimbin"
    bindir.mkdir()
    log = tmp_path / "redis-shim.log"
    shim = bindir / "redis-cli"
    shim.write_text('#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$REDIS_SHIM_LOG"\nexit 0\n')
    shim.chmod(0o755)
    return bindir, log


def run_distill(root: Path, *flags: str, shim: tuple[Path, Path] | None = None,
                ) -> subprocess.CompletedProcess:
    env = {**os.environ, "CABINET_ROOT": str(root)}
    # Never let the invoking session's officer identity leak into fixtures.
    for var in ("CLAUDE_OFFICER", "OFFICER_NAME", "CABINET_OFFICER"):
        env.pop(var, None)
    if shim is not None:
        bindir, log = shim
        env["PATH"] = f"{bindir}:{env['PATH']}"
        env["REDIS_SHIM_LOG"] = str(log)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *flags],
        env=env, capture_output=True, text=True, timeout=60)


def proposal_of(root: Path) -> Path:
    return root / "shared" / "interfaces" / "captain-law-digest.proposal.md"


def digest_of(root: Path) -> Path:
    """The PROMOTED boot surface — exists only after a gated --apply."""
    return root / "shared" / "interfaces" / "captain-law-digest.md"


def propose_and_apply(root: Path, shim: tuple[Path, Path] | None = None) -> None:
    assert run_distill(root).returncode == 0
    proc = run_distill(root, "--apply", shim=shim)
    assert proc.returncode == 0, proc.stderr


# ----------------------------------------------------------------- tests ----
def test_topics_extracted_and_grouped(tmp_path):
    root = make_root(tmp_path)
    proc = run_distill(root)
    assert proc.returncode == 0, proc.stderr
    text = proposal_of(root).read_text()
    # 'telegram' appears in 3 entry titles across two ledgers → the dominant
    # deterministic topic; the two Paddle/VAT-free entries land elsewhere.
    assert "## telegram (3)" in text
    # Section carries its members with date + ledger:line refs.
    assert "- 2026-06-23 — Telegram warroom wiring deferred [captain-decisions.md:L" in text
    assert "captain-patterns.md:L" in text


def test_no_content_loss_every_entry_indexed(tmp_path):
    root = make_root(tmp_path)
    assert run_distill(root).returncode == 0
    text = proposal_of(root).read_text()
    for date, title in [
        ("2026-06-23", "Telegram warroom wiring deferred"),
        ("2026-06-24", "Telegram DM stays the single channel"),
        ("2026-06-25", "Paddle VAT handling"),
        ("undated", "always-thread-replies telegram"),
        ("2026-07-01", "wants boot context lean"),
    ]:
        assert f"- {date} — {title}" in text, f"entry lost: {title}"
    # Source coverage lines: counts must match the fixtures exactly.
    assert "- captain-decisions.md — 3 entries distilled, 1 officer-notes" in text
    assert "- captain-patterns.md — 1 entries distilled, 0 officer-notes" in text
    assert "- captain-intents.md — 1 entries distilled, 0 officer-notes" in text
    # Officer notes are counted, labeled non-law, and their text NOT distilled.
    assert "trust:officer, not law" in text
    assert "An officer observation" not in text


def test_idempotent_rerun_byte_identical_and_clockless(tmp_path):
    root = make_root(tmp_path)
    assert run_distill(root).returncode == 0
    first = proposal_of(root).read_bytes()
    assert run_distill(root).returncode == 0
    second = proposal_of(root).read_bytes()
    assert first == second, "re-run on unchanged ledgers must be byte-identical"
    # No wall-clock content (that is WHY it is idempotent).
    assert not re.search(rb"\d{2}:\d{2}:\d{2}", first)


def test_default_is_proposal_only_no_enqueue_no_promotion(tmp_path):
    """NEGATIVE CONTROLS for the self-ratification gate: without --apply the
    distiller must neither touch the embed queue NOR write the promoted boot
    surface. A mutant that enqueues unconditionally — or that writes
    captain-law-digest.md on the default pass (the reviewed defect: the
    'PROPOSAL' file WAS the live boot-injection path) — fails here."""
    root = make_root(tmp_path)
    shim = make_redis_shim(tmp_path)
    proc = run_distill(root, shim=shim)
    assert proc.returncode == 0, proc.stderr
    assert proposal_of(root).is_file(), "proposal digest must still be written"
    assert not digest_of(root).exists(), (
        "default run wrote the PROMOTED boot surface — the review gate is "
        "bypassed (boot channel updated without Captain review)")
    _, log = shim
    assert not log.exists() or log.read_text() == "", (
        "PROPOSAL-ONLY default violated: something was enqueued without --apply")
    assert "(PROPOSAL)" in proposal_of(root).read_text().splitlines()[0]


def test_apply_refuses_without_proposal(tmp_path):
    """--apply cold (nothing reviewed) must refuse: exit 3, no promoted
    file, nothing enqueued."""
    root = make_root(tmp_path)
    shim = make_redis_shim(tmp_path)
    proc = run_distill(root, "--apply", shim=shim)
    assert proc.returncode == 3, proc.stderr
    assert not digest_of(root).exists()
    _, log = shim
    assert not log.exists() or log.read_text() == ""
    assert "REFUSED" in proc.stderr


def test_apply_refuses_tampered_or_stale_proposal(tmp_path):
    """REVIEW-FRESHNESS GATE: a proposal that diverges from a fresh render —
    hand-tampered content or ledgers grown since review — must not promote."""
    root = make_root(tmp_path)
    shim = make_redis_shim(tmp_path)
    assert run_distill(root).returncode == 0
    # (a) hand-tamper the reviewed file
    with proposal_of(root).open("a") as fh:
        fh.write("- 9999-01-01 — forged directive [captain-decisions.md:L1]\n")
    proc = run_distill(root, "--apply", shim=shim)
    assert proc.returncode == 3, proc.stderr
    assert not digest_of(root).exists()
    # (b) regenerate honestly, then grow a ledger AFTER review
    assert run_distill(root).returncode == 0
    with (root / "shared" / "interfaces" / "captain-decisions.md").open("a") as fh:
        fh.write("\n## 2026-07-16 — post-review decision\n\n- **Decision:** new.\n")
    proc = run_distill(root, "--apply", shim=shim)
    assert proc.returncode == 3, proc.stderr
    assert not digest_of(root).exists()
    _, log = shim
    assert not log.exists() or log.read_text() == "", (
        "refused --apply must not enqueue anything")


def test_apply_promotes_and_queues_reflection_trust_topic_rows(tmp_path):
    root = make_root(tmp_path)
    shim = make_redis_shim(tmp_path)
    assert run_distill(root).returncode == 0          # proposal (review surface)
    proc = run_distill(root, "--apply", shim=shim)    # gated promotion
    assert proc.returncode == 0, proc.stderr
    promoted = digest_of(root).read_text()
    # The boot surface is NOT banner-labeled a proposal (reviewed content).
    assert "(PROPOSAL)" not in promoted.splitlines()[0]
    assert "PROMOTED after Captain review" in promoted
    # Same distilled content as the reviewed proposal (banner aside).
    assert "## telegram (3)" in promoted
    assert proposal_of(root).is_file(), "review surface stays in place"
    _, log = shim
    lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
    assert lines, "--apply must enqueue at least one topic row"
    payloads = []
    for ln in lines:
        assert "XADD" in ln and "cabinet:memory:embed_queue" in ln
        payloads.append(json.loads(ln.split(" payload ", 1)[1]))
    promoted_sha = hashlib.sha256(digest_of(root).read_bytes()).hexdigest()
    for p in payloads:
        assert p["source_type"] == "captain_law_summary"
        assert p["source_id"].startswith("cls-")
        assert p["metadata"]["trust"] == "reflection"
        assert p["metadata"]["trust"] != "captain"  # summaries are never law
        assert p["metadata"]["via"] == "memory-distill"
        assert p["metadata"]["digest_sha256"] == promoted_sha
    topics = {p["source_id"] for p in payloads}
    assert "cls-telegram" in topics
    joined = "\n".join(p["content"] for p in payloads)
    assert "Telegram warroom wiring deferred" in joined


def test_promoted_digest_idempotent(tmp_path):
    root = make_root(tmp_path)
    shim = make_redis_shim(tmp_path)
    propose_and_apply(root, shim)
    first = digest_of(root).read_bytes()
    propose_and_apply(root, shim)
    assert digest_of(root).read_bytes() == first
    assert not re.search(rb"\d{2}:\d{2}:\d{2}", first)


def test_check_fresh_stale_absent_cycle(tmp_path):
    """--check contract the cabinet-doctor probe rides: 4 before any
    promotion (silent/skip), 0 right after --apply, 3 once a ledger grows
    past the promoted snapshot (the AMBER 'boot injects outdated law' tell —
    without it the lane silently returns to detection-without-closure)."""
    root = make_root(tmp_path)
    shim = make_redis_shim(tmp_path)
    assert run_distill(root, "--check").returncode == 4      # never promoted
    assert run_distill(root).returncode == 0                 # proposal only…
    assert run_distill(root, "--check").returncode == 4      # …still not in use
    proc = run_distill(root, "--apply", shim=shim)
    assert proc.returncode == 0, proc.stderr
    assert run_distill(root, "--check").returncode == 0      # fresh
    with (root / "shared" / "interfaces" / "captain-patterns.md").open("a") as fh:
        fh.write("\n## new-pattern telegram\n\n- **Rule:** appended after promote.\n")
    proc = run_distill(root, "--check")
    assert proc.returncode == 3, "grown ledger must flip --check to STALE"
    assert "captain-patterns.md" in proc.stderr
    digest_of(root).unlink()                                  # kill switch
    assert run_distill(root, "--check").returncode == 4


def test_check_is_read_only(tmp_path):
    root = make_root(tmp_path)
    shim = make_redis_shim(tmp_path)
    propose_and_apply(root, shim)
    iface = root / "shared" / "interfaces"
    before = {p.name: p.read_bytes() for p in iface.iterdir() if p.is_file()}
    assert run_distill(root, "--check", shim=shim).returncode == 0
    after = {p.name: p.read_bytes() for p in iface.iterdir() if p.is_file()}
    assert before == after, "--check must not write anything"


def test_no_ledgers_exits_2_and_writes_nothing(tmp_path):
    root = make_root(tmp_path, with_ledgers=False)
    proc = run_distill(root)
    assert proc.returncode == 2
    assert not proposal_of(root).exists()
    assert not digest_of(root).exists()


@pytest.mark.parametrize("runtime_file", [
    "shared/interfaces/captain-law-digest.md",
    "shared/interfaces/captain-law-digest.proposal.md",
])
def test_digest_paths_are_untracked_runtime(runtime_file):
    """Both digest surfaces are runtime ledgers — the gitignore class must
    cover them (shared/interfaces/**/*.md). Guards against a rule prune."""
    if not (REPO / ".git").exists():
        pytest.skip("not a git checkout (egg export)")
    proc = subprocess.run(
        ["git", "-C", str(REPO), "check-ignore", "-q", runtime_file],
        capture_output=True, timeout=30)
    assert proc.returncode == 0, f"{runtime_file} must be gitignored"


# ------------------------------------------------- retro-step lint (BC1) ----
# The doctrine-pack copies ship to fresh captains — they must carry the SAME
# terminal consolidation step as the canonical bodies (the reviewed defect:
# packs shipped pre-lane bodies while the suite stayed green).
@pytest.mark.parametrize("skill", [
    "memory/skills/individual-reflection.md",
    "memory/skills/cross-officer-retro.md",
    "packs/doctrine-pack/skills/individual-reflection/SKILL.md",
    "packs/doctrine-pack/skills/cross-officer-retro/SKILL.md",
])
def test_retro_skills_carry_consolidation_terminal_step(skill):
    """Every retro-skill surface must end in the consolidation step:
    distilled beliefs queued as consolidated_belief with trust=reflection,
    explicitly including failure-pattern beliefs. Fails on the pre-lane
    skill bodies AND on stale pack copies."""
    text = (REPO / skill).read_text()
    assert "consolidated_belief" in text, f"{skill}: no consolidation step"
    assert "memory_queue_embed" in text
    assert "failure-pattern" in text, f"{skill}: failure-pattern emission missing"
    assert '--arg trust "reflection"' in text, f"{skill}: trust=reflection not pinned"
    assert '--arg trust "captain"' not in text, (
        f"{skill}: consolidation must NEVER stamp trust=captain")
    assert "NEVER `captain`" in text


@pytest.mark.parametrize("pack_copy,canonical", [
    ("packs/doctrine-pack/skills/individual-reflection/SKILL.md",
     "memory/skills/individual-reflection.md"),
    ("packs/doctrine-pack/skills/cross-officer-retro/SKILL.md",
     "memory/skills/cross-officer-retro.md"),
])
def test_pack_copies_track_canonical_bodies(pack_copy, canonical):
    """Mechanical copy⇄canonical parity: the pack copy is its YAML
    frontmatter block (which MUST keep the apoptosis `sunset:` date) followed
    by the byte-exact canonical body. Any future canonical edit without a
    pack refresh — or vice versa — fails loud instead of shipping stale
    doctrine to pack installers."""
    pack_text = (REPO / pack_copy).read_text()
    assert pack_text.startswith("---\n"), f"{pack_copy}: missing frontmatter"
    fm_end = pack_text.index("\n---\n", 4)
    frontmatter = pack_text[4:fm_end]
    assert "sunset: '2026-10-05'" in frontmatter, (
        f"{pack_copy}: apoptosis sunset frontmatter lost")
    body = pack_text[fm_end + len("\n---\n"):].lstrip("\n")
    assert body == (REPO / canonical).read_text(), (
        f"{pack_copy} body has drifted from {canonical} — refresh the copy "
        "(frontmatter + verbatim canonical body) in the same change")
