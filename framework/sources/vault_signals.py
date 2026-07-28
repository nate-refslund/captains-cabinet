"""framework/sources/vault_signals.py — the Flavor-A vault gather TABLE + walk.

CG-2 extract-pack (2026-07-07, egg row R004a): the acting lane's signal-gather
section table (the vault-directory literals) and its file-walk helpers moved
here OUT of the germline framework/acting/run_action_lane.py, so the judged
acting plane carries no personal-vault layout knowledge. run_action_lane's
``gather_signals`` calls ``collect_sections`` for its legacy (flag-OFF) path —
behavior byte-identical to the pre-extract inline code — and routes to the
PersonalSource seam when ``CABINET_GATHER_VIA_SOURCE=1`` (dark by default).

Contract (unchanged from the inline original):
gather reads vault .md files and NEVER calls a live API — so the
retrodiction/sim harness can replay the exact same gather at a historical
as_of deterministically (the fencing the whole learning plane rests on). New
sections (health.md, 3-People/_radar, 7-Opportunities) may be ABSENT until
their scout/snapshot lanes land — every section degrades to empty, never an
error. Excerpts are provenance-fenced by the caller (SEC-4 discipline: signal
text is world-description, never instructions).

P3b (2026-07-07): sections carry a SOURCE. "vault" (the default) resolves
under the caller's vault as before; "corpus" resolves under the ORG's OWN
knowledge corpus — the cabinet vault, ``<repo>/vault`` (plan-B B4.14:
architecture / decisions / incidents / deploy notes, written by officers via
normal file writes; Captain-ratified 2026-07-16 as the default vault — see
vault/README.md for the rename history and the resolver's legacy aliases).
This is the clean-room fix: on org boxes vault_dir() fail-closes to "" and
every vault section is empty, so without a corpus source the lane gathered
ZERO sections. An empty ``corpus_dir`` ⇒ corpus sections skip (fail-closed,
same degrade as an absent vault folder); both non-empty ⇒ vault sections are
UNCHANGED and corpus blocks ride alongside (additive). Corpus refs are
namespaced "vault/<relpath>" so evidence refs stay unambiguous across sources
(pre-rename ledger rows keep their old ref prefix as provenance — refs are
per-run evidence handles, never rewritten). Same file-only contract, same
_recent_files mtime fencing (as_of ceiling + window), same caps/chars bounds.
"""
from __future__ import annotations

import datetime as dt
import re
from collections import namedtuple
from pathlib import Path
from typing import Any

from framework.acting.action_lane import neutralize_fence_shapes
from framework.env import vault_dir

# The operational gather window (hours) — the lane's default recency fence.
WINDOW_H = 72


def default_vault() -> Path:
    """The deployment's vault root (fail-open to ~/vault like the original
    module-level VAULT constant — an absent dir simply gathers nothing)."""
    return Path(vault_dir() or str(Path.home() / "vault"))


# (label, subpath, filenames, window_h, cap, chars, ff_filter, group_by_product,
#  source)
#   filenames=None        → rglob every *.md under subpath (recency-windowed)
#   filenames=[...]        → only those basenames under subpath/*/ (per-product dirs)
#   window_h=None          → UNWINDOWED (all ages, still <= as_of — never leak future)
#   ff_filter={k: pred}    → keep a file only if its YAML head[k] satisfies pred(v)
#   group_by_product=True  → cap counts PRODUCTS (all their named files), not files
#   source="vault"|"corpus" → root: the vault (default) | the org corpus dir
_Section = namedtuple(
    "_Section",
    "label subpath filenames window_h cap chars ff_filter group_by_product source")


def _sec(label: str, subpath: str, *, filenames=None, window_h: "int | None" = WINDOW_H,
         cap: int = 5, chars: int = 700, ff_filter=None,
         group_by_product: bool = False, source: str = "vault") -> "_Section":
    return _Section(label, subpath, filenames, window_h, cap, chars, ff_filter,
                    group_by_product, source)


def _ff_truthy(v: Any) -> bool:
    return v is True or str(v).strip().lower() == "true"


def _ff_new_or_investigating(v: Any) -> bool:
    return str(v).strip().lower() in ("new", "investigating")


# Profiles are independent tables (so e.g. health carries the alert:true filter
# under OPERATIONAL but is unfiltered — "all health" — under STRATEGIC).
PROFILES = {
    "operational": [
        _sec("OPEN COMMITMENT", "6-Commitments", cap=8, chars=700),
        _sec("MEETING", "2-Meetings", cap=5, chars=1200),
        _sec("DECISION", "5-Reflections/Decisions", cap=4, chars=700),
        _sec("PRODUCT HEALTH", "9-Codebases", filenames=["health.md"],
             cap=3, chars=600, ff_filter={"alert": _ff_truthy}),
        _sec("PEOPLE", "3-People/_radar", cap=3, chars=500),
        _sec("CODE", "9-Codebases", filenames=["commits.md", "deployment.md"],
             cap=2, chars=800, group_by_product=True),
        # P3b: recent org-corpus changes (newest 4 within the operational
        # window) — the live lane's perception of the org's OWN knowledge.
        _sec("CORPUS", "", cap=4, chars=700, source="corpus"),
    ],
    "strategic": [
        _sec("OPPORTUNITY", "7-Opportunities", window_h=None, cap=6, chars=700,
             ff_filter={"status": _ff_new_or_investigating}),
        _sec("PRODUCT HEALTH", "9-Codebases", filenames=["health.md"],
             window_h=None, cap=8, chars=600),
        _sec("CODE", "9-Codebases", filenames=["commits.md", "deployment.md"],
             cap=2, chars=800, group_by_product=True),
        _sec("RETRO", "5-Reflections/Weekly-Trends", window_h=None, cap=1, chars=900),
        # P3b: the grander view — newest 6 corpus notes of ANY age (still
        # <= as_of; the ceiling never leaks future files into a replay).
        _sec("CORPUS", "", window_h=None, cap=6, chars=800, source="corpus"),
    ],
}


def _read_frontmatter(text: str) -> dict:
    """Parse ONLY the leading `---`..`---` YAML head (yaml.safe_load, minimal
    line-parse fallback). Never executes anything — the head is data."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text or "", re.DOTALL)
    if not m:
        return {}
    block = m.group(1)
    try:
        import yaml
        d = yaml.safe_load(block)
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    out: dict = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _ff_match(p: Path, ff_filter: "dict | None") -> bool:
    if not ff_filter:
        return True
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    fm = _read_frontmatter(text)
    return all(pred(fm.get(key)) for key, pred in ff_filter.items())


def _mtime(p: Path) -> "dt.datetime | None":
    try:
        return dt.datetime.fromtimestamp(p.stat().st_mtime, tz=dt.timezone.utc)
    except OSError:
        return None


def _recent_files(folder: Path, *, as_of: dt.datetime, window_h: "int | None",
                  cap: int, ff_filter: "dict | None" = None) -> list:
    """Newest-first *.md under folder, fenced to (as_of - window_h, as_of].
    window_h=None drops the lower bound (unwindowed) but keeps the as_of ceiling
    so a replay never leaks a file newer than its clock. ff_filter (if any) is
    applied newest-first, reading only until `cap` matches are found."""
    if not folder.exists():
        return []
    lo = (as_of - dt.timedelta(hours=window_h)) if window_h is not None else None
    cands = []
    for p in folder.rglob("*.md"):
        if "_noise" in p.parts:
            continue
        m = _mtime(p)
        if m is None or m > as_of or (lo is not None and m < lo):
            continue
        cands.append((m, p))
    cands.sort(reverse=True)
    out = []
    for _, p in cands:
        if not _ff_match(p, ff_filter):
            continue
        out.append(p)
        if len(out) >= cap:
            break
    return out


def _named_files(root: Path, names: list, *, as_of: dt.datetime,
                 window_h: "int | None", cap: int, ff_filter: "dict | None" = None,
                 group_by_product: bool = False) -> list:
    """The named files (e.g. health.md, commits.md) under each product dir
    root/*/. group_by_product ⇒ cap counts PRODUCTS (newest-first by their newest
    matching file), each contributing all its named files; else cap counts files.
    Same as_of/window fencing + ff_filter as _recent_files."""
    if not root.exists():
        return []
    lo = (as_of - dt.timedelta(hours=window_h)) if window_h is not None else None
    found = []
    for prod in sorted(root.iterdir()):
        if not prod.is_dir():
            continue
        for name in names:
            p = prod / name
            if not p.exists():
                continue
            m = _mtime(p)
            if m is None or m > as_of or (lo is not None and m < lo):
                continue
            if not _ff_match(p, ff_filter):
                continue
            found.append((m, prod.name, p))
    found.sort(reverse=True)                      # newest first
    if not group_by_product:
        return [p for _, _, p in found[:cap]]
    accepted: list = []
    out = []
    for _, prodname, p in found:
        if prodname not in accepted:
            if len(accepted) >= cap:
                continue
            accepted.append(prodname)
        out.append(p)
    return out


def _excerpt(p: Path, chars: int) -> str:
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    # drop our own graph block + fences; the LLM needs prose, not plumbing
    text = re.sub(r"<!-- graph:links -->.*?<!-- /graph:links -->", "", text,
                  flags=re.DOTALL)
    return text.strip()[:chars]


def _relpath(p: Path, vault: Path) -> str:
    # whitespace-collapsed: this string is interpolated into the bundle's fence
    # HEADER, and a path carrying a newline (POSIX permits one) would end that
    # line early and let its own remainder open a forged second header — the
    # metadata-side twin of the body forgery neutralize_fence_shapes() closes.
    try:
        return " ".join(str(p.relative_to(vault)).split())
    except ValueError:
        return " ".join(p.name.split())


def collect_sections(as_of: dt.datetime, *, window_h: int = WINDOW_H,
                     profile: str = "operational", vault: "Path | None" = None,
                     corpus_dir: str = "",
                     include: "tuple | None" = None) -> list:
    """The fenced evidence parts for a profile — ``[(path, fenced_text), …]``
    exactly as run_action_lane's pre-extract inline loop produced them (the
    caller applies cid-echo suppression + joins). FILE-ONLY (no API).
    ``corpus_dir`` roots source="corpus" sections; empty ⇒ those sections skip
    (fail-closed). ``include`` optionally restricts to a subset of section
    sources (e.g. ``("corpus",)`` for the via-source path, which replaces the
    vault walk but keeps the org-corpus perception)."""
    vault = vault if vault is not None else default_vault()
    sections = PROFILES.get(profile, PROFILES["operational"])
    parts = []                                    # (path, fenced-text) — path for logging
    for sec in sections:
        if include is not None and sec.source not in include:
            continue
        # P3b: a "corpus" section roots at the org's own corpus (the cabinet
        # vault, env.org_vault_dir()) instead of the personal vault.
        # Unresolved ("" on a box with no corpus) ⇒ the section is simply
        # empty — the same fail-closed degrade as an absent vault folder,
        # never an error. Refs are namespaced "vault/…" so an evidence ref
        # never collides with a personal-vault-relative path.
        if sec.source == "corpus":
            if not corpus_dir:
                continue
            base, ref_prefix = Path(corpus_dir), "vault/"
        else:
            base, ref_prefix = vault, ""
        root = base / sec.subpath if sec.subpath else base
        # a section using the module default window honors the caller's override;
        # a section with its own window (incl. None = unwindowed) keeps it.
        eff_window = window_h if sec.window_h == WINDOW_H else sec.window_h
        if sec.filenames:
            files = _named_files(root, sec.filenames, as_of=as_of,
                                 window_h=eff_window, cap=sec.cap,
                                 ff_filter=sec.ff_filter,
                                 group_by_product=sec.group_by_product)
        else:
            files = _recent_files(root, as_of=as_of, window_h=eff_window,
                                  cap=sec.cap, ff_filter=sec.ff_filter)
        for p in files:
            # SEC-5 2026-07-28: an excerpt is attacker-writable text and must not
            # be able to type a fence header of its own — see the reproduction in
            # action_lane.neutralize_fence_shapes' header. The one other producer
            # of this bundle (run_action_lane._fence_block) calls the same helper.
            body = neutralize_fence_shapes(_excerpt(p, sec.chars))
            if body:
                parts.append(
                    (p, f"--- {sec.label} ref={ref_prefix}{_relpath(p, base)} ---\n{body}"))
    return parts

# D13 inbound-provenance prefix table (vault layout): evidence refs under
# these areas are raw email/Teams captured content. The acting lane's D13
# fence CONSUMES this table (run_action_lane._INBOUND_REF_PREFIXES) — the
# judgment lives in the germline lane; only the layout knowledge lives here.
# NARROWING HERE IS INERT: the lane unions this table with the schg-locked
# action_lane.D13_INBOUND_FLOOR, so an edit in this unlocked module can only
# ADD inbound areas (widen the fence), never remove the floor's.
INBOUND_REF_PREFIXES = ("3-People/", "2-Meetings/", "4-Interactions/")
