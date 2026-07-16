#!/usr/bin/env python3.12
"""memory-distill.py — deterministic per-topic captain-law digest (lane BC,
memwave3 2026-07-15: grow by distillation, not accretion).

WHY: the captain-law ledgers (shared/interfaces/captain-{decisions,patterns,
intents}.md) are append-only and growing; the boot hook injects only
`tail -40` of each, so older law is boot-invisible. This organ distills the
FULL ledgers into one compact per-topic index that a (Captain-gated)
boot-pack patch injects in full, ahead of the tail-40 sections.

TWO FILES, ONE GATE (review → promote):
  * default run writes shared/interfaces/captain-law-digest.proposal.md —
    the REVIEW surface. It is never boot-injected.
  * --apply (after Captain review — standing handback) re-renders from the
    ledgers, REFUSES unless the on-disk proposal byte-matches that fresh
    render (post-review ledger drift or a tampered proposal both abort),
    then writes the PROMOTED boot surface
    shared/interfaces/captain-law-digest.md and queues per-topic memory
    rows. The boot hook reads ONLY the promoted file, so nothing reaches
    boot context without the reviewed gate. Post-ceremony the promoted path
    is write-guarded as captain-law plane (pre-tool-use.sh §5/§5c +
    officer-sandbox.sh deny) — this script, run from an unsandboxed
    Captain/CoS context, is its only sanctioned writer.
  * --check compares the promoted digest's recorded per-ledger sha256s to
    the live ledgers (READ-ONLY staleness tell; cabinet-doctor probes it,
    the cross-officer retro acts on it). Exit: 0 fresh / 3 stale /
    4 no promoted digest (boot-pack not in use) / 2 nothing to distill.

DELIBERATELY NO LLM (choice + justification, recorded here):
  * there is no house LLM-call helper in cabinet/scripts (officer sessions
    ARE the LLM layer; the only `claude` invocations are session spawners);
  * ledger content is UNTRUSTED data — an LLM summarization pass over it is
    a prompt-injection → memory-poisoning channel (crafted ledger text could
    steer the summary that later boots every officer);
  * the digest must be IDEMPOTENT and provably lossless (tests pin both) —
    a deterministic index preserves the Captain's own words verbatim, which
    is also what makes it reviewable as a proposal.

TRUST MODEL (non-negotiable): every row this script queues is
source_type=captain_law_summary with metadata trust=reflection — NEVER
trust=captain. A derived summary must never masquerade as Captain law; the
full ledgers remain the authoritative surfaces.

PROPOSAL-ONLY BY DEFAULT: the default run writes the .proposal.md review
file and STOPS — the Captain reviews it (standing handback). BOTH the
promoted boot file and the cabinet_memory rows happen ONLY behind the
explicit --apply flag; law summarization must not self-ratify, and a file
labeled PROPOSAL must never be the live boot channel.

Security discipline:
  * ledger content flows ONLY as argv into memory_queue_embed (which builds
    the payload with jq --arg) — never interpolated into shell program text;
  * no secrets are read or echoed here (cabinet/.env is sourced inside
    lib/memory.sh exactly as every other enqueuer);
  * writes = TWO runtime files (proposal always, promoted only under
    --apply; both gitignored via the shared/interfaces/**/*.md rule) via
    atomic tmp+rename, plus Redis queue XADDs under --apply. No SQL, no
    DELETE — the memory store is supersede-only and the worker upserts.

DETERMINISM: output contains NO wall-clock content (provenance = source
sha256s + counts), so re-running on unchanged ledgers is byte-identical —
the proposal the Captain reviewed is provably the content --apply promotes.

Usage:
  python3.12 cabinet/scripts/memory-distill.py           # write review proposal
  python3.12 cabinet/scripts/memory-distill.py --apply   # promote + queue rows
  python3.12 cabinet/scripts/memory-distill.py --check   # staleness tell (RO)
  (CABINET_ROOT env overrides the repo-root autodetect; tests use tmp trees)

Tests: cabinet/scripts/tests/test_memory_distill.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(os.environ.get("CABINET_ROOT")
                  or Path(__file__).resolve().parents[2])

# The three captain-law ledgers, in fixed digest order. Paths are FIXED
# (never caller-supplied — same no-traversal stance as append-interface.sh).
LEDGERS = ("captain-decisions.md", "captain-patterns.md", "captain-intents.md")

DIGEST_NAME = "captain-law-digest.md"            # PROMOTED boot surface (--apply only)
PROPOSAL_NAME = "captain-law-digest.proposal.md"  # review surface (default run)
SOURCE_TYPE = "captain_law_summary"
TRUST = "reflection"  # NEVER "captain" — a summary is not law (see header)

# Soft boot-context budget: the digest is injected whole at session start.
SIZE_WARN_BYTES = 32_000
DETAIL_MAX = 200  # chars of the entry's first detail line kept in the index

_DATE_RE = re.compile(r"20\d{2}-\d{2}-\d{2}")
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9-]{2,}")
# Generic-english + cabinet-generic vocabulary that would smear every entry
# into one bucket. DELIBERATELY no product or person tokens here (layer
# separation: framework code never hardcodes an instance) — product words
# remain groupable topics because they arrive from the DATA, not from code.
_STOPWORDS = frozenset("""
the a an and or for of to in on is are was were be been being vs via with
without not no never always until unless per as at by from into over under
its it this that these those do does did done don dont up down out off we
our you your they their than then when while before after between against
each all any both more most other some such only own same so too very can
cannot could would will shall may might must just should now new use used
uses using keep keeps kept stay stays one two three first second next last
what which who whom whose where how why also still yet even ever again
captain cabinet officer officers decision decisions pattern patterns intent
intents rule rules law note notes loop ledger entry entries file files
""".split())


# ---------------------------------------------------------------------------
# Parsing (mirrors post-file-write-memory.sh pfwm_queue_captain_decisions:
# an entry begins at every line starting '## '; preamble before the first
# H2 is skipped; '### officer-note' appends are counted but NOT distilled —
# they are trust:officer observations, not Captain law)
# ---------------------------------------------------------------------------

def parse_ledger(text: str, ledger: str) -> tuple[list[dict], int]:
    """Return ([entry, ...], officer_note_count) for one ledger's text.

    entry = {ledger, line_no, heading, date, title, detail}
    """
    officer_notes = sum(1 for line in text.splitlines()
                        if line.startswith("### officer-note"))
    entries: list[dict] = []
    current: dict | None = None
    body: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if line.startswith("## "):
            if current is not None:
                current["detail"] = _first_detail(body)
                entries.append(current)
            heading = line[3:].strip()
            m = _DATE_RE.search(heading)
            date = m.group(0) if m else "undated"
            title = _DATE_RE.sub("", heading)
            title = re.sub(r"[—–-]\s*$|^\s*[—–-]", "", title.strip()).strip()
            title = re.sub(r"\(\s*\)", "", title).strip() or heading
            current = {"ledger": ledger, "line_no": line_no,
                       "heading": heading, "date": date, "title": title}
            body = []
        elif current is not None:
            body.append(line)
    if current is not None:
        current["detail"] = _first_detail(body)
        entries.append(current)
    return entries, officer_notes


def _first_detail(body: list[str]) -> str:
    """First substantive body line: prefer the ledgers' own lead fields
    (Decision/Rule/Pattern slug/Inferred goal/Why), else the first non-empty
    non-comment line. Markdown bold stripped; truncated to DETAIL_MAX."""
    preferred = re.compile(
        r"^- \*\*(Decision|Rule|Pattern slug|Inferred goal|Why)[:]?\*\*", re.I)
    fallback = ""
    for line in body:
        s = line.strip()
        if s.startswith("### officer-note"):
            break  # officer-note region (until next H2) is never a detail
        if not s or s.startswith("<!--"):
            continue
        if preferred.match(s):
            return _clean_detail(s)
        if not fallback:
            fallback = s
    return _clean_detail(fallback)


def _clean_detail(s: str) -> str:
    s = s.replace("**", "").lstrip("- ").strip()
    s = re.sub(r"[\t\r\n]+", " ", s)
    if len(s) > DETAIL_MAX:
        s = s[:DETAIL_MAX].rstrip() + "…"
    return s


# ---------------------------------------------------------------------------
# Topic derivation — deterministic, data-driven (no taxonomy in code)
# ---------------------------------------------------------------------------

def title_tokens(title: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(title.lower())
            if t not in _STOPWORDS and not _DATE_RE.fullmatch(t)
            and not t.isdigit()]


def assign_topics(entries: list[dict]) -> None:
    """Mutates each entry with entry['topic']: the entry's title token with
    the highest corpus frequency (tie → lexicographically smallest). Entries
    with no usable token get 'misc'. Fully deterministic."""
    freq: dict[str, int] = {}
    for e in entries:
        for t in set(title_tokens(e["title"])):
            freq[t] = freq.get(t, 0) + 1
    for e in entries:
        toks = title_tokens(e["title"])
        if not toks:
            e["topic"] = "misc"
            continue
        # Highest corpus frequency wins; ties resolve to the lexicographically
        # smallest token (scan sorted, strictly-greater replaces) — stable.
        best = None
        for t in sorted(set(toks)):
            if best is None or freq[t] > freq[best]:
                best = t
        e["topic"] = best or "misc"


# ---------------------------------------------------------------------------
# Digest rendering (no wall clock — byte-identical re-runs)
# ---------------------------------------------------------------------------

def render_digest(per_ledger: dict[str, dict], entries: list[dict],
                  promoted: bool = False) -> str:
    """Render the digest markdown. Proposal form (default) and promoted form
    differ ONLY in the H1 banner + provenance comment — Sources and topic
    sections are byte-identical, so the Captain-reviewed proposal is provably
    the same content --apply promotes. Both forms are clockless."""
    lines: list[str] = []
    if promoted:
        lines.append("# Captain Law Digest — per-topic index")
        lines.append("")
        lines.append("<!-- generated by cabinet/scripts/memory-distill.py --apply — deterministic")
        lines.append("     distillation of the captain-law ledgers, PROMOTED after Captain review")
        lines.append("     (standing handback; --apply refuses without a matching reviewed")
        lines.append("     proposal). An INDEX, not law — the full ledgers remain authoritative.")
        lines.append("     Boot-injected in full by session-start.sh (Captain-gated patch) and")
        lines.append("     write-guarded as captain-law plane — regenerate via memory-distill.py,")
        lines.append("     never hand-edit. Runtime/untracked (shared/interfaces/**/*.md rule).")
        lines.append("     No wall-clock content: re-runs on unchanged ledgers are byte-identical. -->")
    else:
        lines.append("# Captain Law Digest — per-topic index (PROPOSAL)")
        lines.append("")
        lines.append("<!-- generated by cabinet/scripts/memory-distill.py — deterministic")
        lines.append("     distillation of the captain-law ledgers. PROPOSAL ONLY: this file is")
        lines.append("     the REVIEW surface — it is never boot-injected and is NOT law; the")
        lines.append("     full ledgers remain authoritative. Promotion to the boot surface")
        lines.append("     (captain-law-digest.md) + embedding into cabinet memory happen only")
        lines.append("     via memory-distill.py --apply after Captain review (rows land as")
        lines.append("     captain_law_summary, trust=reflection — never captain). Runtime/")
        lines.append("     untracked (gitignored via the shared/interfaces/**/*.md rule).")
        lines.append("     No wall-clock content: re-runs on unchanged ledgers are byte-identical. -->")
    lines.append("")
    lines.append("## Sources")
    lines.append("")
    for ledger in LEDGERS:
        info = per_ledger.get(ledger)
        if info is None:
            lines.append(f"- {ledger} — absent, skipped")
            continue
        lines.append(
            f"- {ledger} — {info['n_entries']} entries distilled, "
            f"{info['officer_notes']} officer-notes (trust:officer, not law; "
            f"not distilled), sha256:{info['sha256']}")
    lines.append("")

    topics: dict[str, list[dict]] = {}
    for e in entries:
        topics.setdefault(e["topic"], []).append(e)
    ordered = sorted(topics.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    for topic, group in ordered:
        lines.append(f"## {topic} ({len(group)})")
        lines.append("")
        for e in group:  # already in (ledger order, line order)
            ref = f"{e['ledger']}:L{e['line_no']}"
            detail = f" — {e['detail']}" if e["detail"] else ""
            lines.append(f"- {e['date']} — {e['title']} [{ref}]{detail}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_topic_section(topic: str, group: list[dict]) -> str:
    """One topic's markdown — the unit queued under --apply."""
    out = [f"## Captain law digest — topic: {topic} ({len(group)} entries)", ""]
    for e in group:
        ref = f"{e['ledger']}:L{e['line_no']}"
        detail = f" — {e['detail']}" if e["detail"] else ""
        out.append(f"- {e['date']} — {e['title']} [{ref}]{detail}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Queue seam (--apply only) — same argv-only pattern as transcript-digest.py:
# content passes as positional args into memory_queue_embed, which builds the
# payload with jq --arg. NEVER interpolated into the command string.
# ---------------------------------------------------------------------------

def queue_topic(root: Path, topic: str, content: str, n_entries: int,
                digest_sha: str, writer: str) -> bool:
    meta = {
        "trust": TRUST,           # constant "reflection" — see module header
        "writer": writer,
        "via": "memory-distill",
        "topic": topic,
        "entries": n_entries,
        "digest_sha256": digest_sha,
    }
    assert meta["trust"] != "captain"  # structural: summaries are never law
    slug = re.sub(r"[^a-z0-9-]+", "-", topic.lower()).strip("-") or "misc"
    cmd = [
        "bash", "-c",
        'source "$0/cabinet/scripts/lib/memory.sh" && '
        'memory_queue_embed "$1" "$2" "$3" "$4" "$5" "$6" "$7"',
        str(root),
        SOURCE_TYPE,
        f"cls-{slug}",   # stable id → re-apply upserts, never duplicates
        writer,
        "",              # sender
        content,
        json.dumps(meta),
        "",              # source_ts: honestly absent (spans dates) → queue time
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=30)
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def resolve_writer() -> str:
    for var in ("CLAUDE_OFFICER", "OFFICER_NAME", "CABINET_OFFICER"):
        v = os.environ.get(var, "").strip()
        if v:
            return v
    return "memory-distill"


# ---------------------------------------------------------------------------
# Atomic write + staleness tell (--check)
# ---------------------------------------------------------------------------

def _write_atomic(interfaces: Path, name: str, text: str) -> Path:
    """tmp+rename inside the same dir — readers never see a torn file."""
    out_path = interfaces / name
    fd, tmp = tempfile.mkstemp(dir=str(interfaces), prefix=f".{name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, out_path)  # atomic within the same dir
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return out_path


# One Sources line per ledger: "- <ledger> — … sha256:<hex>" or
# "- <ledger> — absent, skipped" (group 2 = None).
_SOURCE_LINE_RE = re.compile(
    r"^- (captain-[a-z-]+\.md) — (?:absent, skipped$|.*sha256:([0-9a-f]{64})$)")


def _recorded_source_shas(text: str) -> dict[str, str | None]:
    recorded: dict[str, str | None] = {}
    for line in text.splitlines():
        m = _SOURCE_LINE_RE.match(line)
        if m:
            recorded[m.group(1)] = m.group(2)
    return recorded


def check_freshness(interfaces: Path) -> int:
    """--check: READ-ONLY staleness tell for the PROMOTED boot surface.

    The digest records each source ledger's sha256 in its Sources section;
    the ledgers keep growing after promotion, and entries that scroll out of
    the boot tail-40 while the digest predates them are boot-invisible — the
    exact detection-without-closure gap this organ exists to close. Compare
    recorded vs live hashes: 0 fresh / 3 stale / 4 no promoted digest
    (boot-pack not in use — a sanctioned state, incl. the kill switch).
    cabinet-doctor maps 3 to WARN/AMBER; the cross-officer retro's Part 5
    regenerates the proposal for Captain review when this reports stale.
    """
    digest_path = interfaces / DIGEST_NAME
    if not digest_path.is_file():
        print(f"memory-distill: --check — no promoted digest at {digest_path} "
              "(boot-pack not in use)", file=sys.stderr)
        return 4
    recorded = _recorded_source_shas(
        digest_path.read_text(encoding="utf-8", errors="replace"))
    stale: list[str] = []
    for ledger in LEDGERS:
        path = interfaces / ledger
        live = (hashlib.sha256(path.read_bytes()).hexdigest()
                if path.is_file() else None)
        if recorded.get(ledger) != live:
            stale.append(ledger)
    if stale:
        print("memory-distill: --check STALE — promoted digest out of date vs "
              f"live ledger(s): {', '.join(stale)}. Regenerate the proposal "
              "(default run), Captain review, then --apply.", file=sys.stderr)
        return 3
    print("memory-distill: --check fresh — recorded ledger hashes match live",
          file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true",
                      help="Promote the Captain-reviewed proposal to the boot "
                           "surface (%s) AND queue per-topic digest rows into "
                           "cabinet_memory (source_type=%s, trust=%s). REFUSES "
                           "(exit 3) unless the on-disk proposal byte-matches "
                           "a fresh render of the live ledgers — review first "
                           "(standing handback), re-run default on drift."
                           % (DIGEST_NAME, SOURCE_TYPE, TRUST))
    mode.add_argument("--check", action="store_true",
                      help="READ-ONLY staleness tell: compare the promoted "
                           "digest's recorded ledger sha256s to the live "
                           "ledgers. Exit 0 fresh / 3 stale / 4 not in use.")
    args = ap.parse_args(argv)

    interfaces = _REPO_ROOT / "shared" / "interfaces"
    if not interfaces.is_dir():
        print(f"memory-distill: no interfaces dir at {interfaces} — nothing to distill",
              file=sys.stderr)
        return 2

    if args.check:
        return check_freshness(interfaces)

    per_ledger: dict[str, dict] = {}
    entries: list[dict] = []
    for ledger in LEDGERS:
        path = interfaces / ledger
        if not path.is_file():
            continue
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        led_entries, officer_notes = parse_ledger(text, ledger)
        per_ledger[ledger] = {
            "n_entries": len(led_entries),
            "officer_notes": officer_notes,
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        entries.extend(led_entries)

    if not per_ledger:
        print(f"memory-distill: no captain-law ledgers under {interfaces} — "
              "nothing to distill (digest not written)", file=sys.stderr)
        return 2

    assign_topics(entries)
    proposal = render_digest(per_ledger, entries, promoted=False)

    if not args.apply:
        # PROPOSAL-ONLY default: write the review surface and STOP — no
        # promoted file, no embed, no queue. The boot channel is untouched.
        out_path = _write_atomic(interfaces, PROPOSAL_NAME, proposal)
        size = len(proposal.encode("utf-8"))
        print(f"memory-distill: wrote {out_path} ({size} bytes, "
              f"{len(entries)} entries) — PROPOSAL (not law, not boot-injected; "
              "Captain review pending, then --apply)", file=sys.stderr)
        if size > SIZE_WARN_BYTES:
            print(f"memory-distill: WARN digest exceeds boot-context budget "
                  f"({size} > {SIZE_WARN_BYTES} bytes) — consider ledger curation",
                  file=sys.stderr)
        return 0

    # --apply — REVIEW-FRESHNESS GATE: the on-disk proposal must byte-match a
    # fresh render of the live ledgers. Catches BOTH review-rot (ledgers grew
    # after the Captain read it) and a tampered proposal file (any hand-edit
    # diverges from the deterministic render). Nothing is written or queued
    # on refusal — the boot surface only ever carries reviewed content.
    prop_path = interfaces / PROPOSAL_NAME
    if not prop_path.is_file():
        print(f"memory-distill: --apply REFUSED — no proposal at {prop_path}. "
              "Run the default pass first; the Captain reviews it, then --apply.",
              file=sys.stderr)
        return 3
    on_disk = prop_path.read_text(encoding="utf-8", errors="replace")
    if on_disk != proposal:
        print("memory-distill: --apply REFUSED — on-disk proposal does not "
              "match a fresh render of the live ledgers (ledgers changed since "
              "review, or the proposal was edited). Re-run the default pass "
              "and have the Captain re-review.", file=sys.stderr)
        return 3

    promoted = render_digest(per_ledger, entries, promoted=True)
    digest_sha = hashlib.sha256(promoted.encode("utf-8")).hexdigest()
    out_path = _write_atomic(interfaces, DIGEST_NAME, promoted)
    size = len(promoted.encode("utf-8"))
    print(f"memory-distill: promoted {out_path} ({size} bytes, "
          f"{len(entries)} entries, sha256:{digest_sha[:12]}…) — boot surface "
          "updated after Captain review", file=sys.stderr)
    if size > SIZE_WARN_BYTES:
        print(f"memory-distill: WARN digest exceeds boot-context budget "
              f"({size} > {SIZE_WARN_BYTES} bytes) — consider ledger curation",
              file=sys.stderr)

    # Queue one row per topic (stable ids → worker upserts).
    writer = resolve_writer()
    topics: dict[str, list[dict]] = {}
    for e in entries:
        topics.setdefault(e["topic"], []).append(e)
    ok = failed = 0
    for topic, group in sorted(topics.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        section = render_topic_section(topic, group)
        if queue_topic(_REPO_ROOT, topic, section, len(group), digest_sha, writer):
            ok += 1
        else:
            failed += 1
    print(f"memory-distill: --apply queued {ok} topic rows "
          f"({failed} failed) as {SOURCE_TYPE}/trust={TRUST}", file=sys.stderr)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
