"""framework.hygiene.apoptosis — retention sweep, cache cap, usage reaper.

The compression plan's "gap #2": the cabinet grows organs but nothing ever
dies, so exhaust (cold logs, stale caches, merged worktrees, dormant skills,
parked services) accumulates silently. This organ is the programmed-death
loop — with a BORN-SAFE polarity that is the whole design:

  DIRECT action  — ONLY for trivially-regenerable exhaust:
    * retention sweep: gzip-rotate log files past their configured window.
      The original is archived (compressed into <dir>/archive/) BEFORE any
      removal, and only files whose mtime is older than the window are ever
      considered. The mtime window alone does NOT protect an open-fd-idle
      log — a healthy daemon's .err stream is silent for months while a
      launchd keepalive fd still holds it — so every candidate is probed
      with lsof first: a file any live process holds open is never
      unlinked; it is archived and then TRUNCATED IN PLACE (copytruncate
      semantics — the inode survives, the holder's next write lands in the
      live, watchdog-scanned path, and disk is reclaimed immediately).
      Only provably-unheld files are unlinked, and only after their archive
      verifies. Empty files are skipped outright (nothing to archive).
    * __pycache__ cap: delete byte-code caches under the repo when their
      total size exceeds a cap. Python regenerates them on the next import.

  PROPOSE-ONLY  — for anything irreversible. Findings become one-tap decision
    cards on the Captain's existing front-door intake stream
    (``framework.frontdoor.intake.enqueue`` — the exact surface
    self_proposal / trust_ladder / daily_recap already use). Nothing in this
    class is ever deleted, moved, or demoted by this module:
    * worktree GC candidates (merged / prunable / stale checkouts under
      ``.claude/worktrees``),
    * dormant skills (usage_count 0 / long-unused / passed ``sunset:``),
    * fleet-manifest rows disabled for >60 days,
    * launchd ``*.template.plist`` files never instantiated anywhere.

Safety rails (all enforced in code, all covered by tests):
  * REALPATH JAIL — every destructive file operation resolves its target via
    realpath and requires containment under an allow-listed root (designated
    log dirs for the retention sweep; the repo root for the cache cap).
    Symlinks are never followed and never deleted — a symlink in a swept dir
    is skipped and reported, so a planted link cannot exfiltrate or delete
    anything outside the jail.
  * CONFIG IS INJECTED — the retention config path arrives via the
    ``CABINET_RETENTION_CONFIG`` env var (set by the glue script
    ``cabinet/scripts/apoptosis-sweep.sh``) or an explicit argument. This
    framework module never names the deployment config layer (three-layer
    gate); no config → the retention sweep is a visible no-op, never a guess.
  * FAIL-CLOSED PARSING — a missing/corrupt config or manifest degrades that
    one domain to "nothing to do" with a reported reason; it never widens a
    window and never crashes the sweep.
  * SELF-HEARTBEAT — after a completed sweep one status line is appended to
    ``<log dir>/apoptosis-sweep.log`` (the same per-service log location the
    outcome-watchdog derives freshness floors from via ``cabinet/services.yml``
    — see ``framework/watchdog/registry.py::_service_log_candidates``). A
    crashed or hung sweep never stamps, so the silence of apoptosis itself is
    noticed once the fleet manifest enrolls the service row (a separate,
    deliberate scheduling change — this module schedules nothing).

CLI:  python3 -m framework.hygiene.apoptosis [--dry-run] [--retention-config P]
                                             [--repo-root P]
Entrypoint for code: ``run_sweep()`` — every collaborator (clock, config path,
repo root, card transport) is injectable, so tests run hermetically in tmp
dirs with a fake enqueue and no Redis.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Tunables (env-overridable; conservative defaults).
# ─────────────────────────────────────────────────────────────────────────────
PYCACHE_CAP_MB_DEFAULT = 500      # total __pycache__ bytes allowed before GC
WORKTREE_STALE_DAYS = 45          # last-commit age that flags a worktree
SKILL_DORMANT_DAYS = 45           # usage_count==0 for this long → candidate
SKILL_UNUSED_DAYS = 90            # last_used older than this → candidate
SERVICE_DISABLED_DAYS = 60        # disabled: true older than this → candidate
RECARD_COOLDOWN_DAYS = 7          # identical findings are not re-carded sooner
CARD_EVIDENCE_ROWS = 15           # max evidence rows rendered per card

HEARTBEAT_FILENAME = "apoptosis-sweep.log"
STATE_FILENAME = "apoptosis-state.json"


def _repo_root() -> Path:
    """CABINET_ROOT env, else this file's repo root (framework/hygiene/…
    → parents[2]). Mirrors framework/watchdog/registry.py::_cabinet_root."""
    return Path(os.environ.get("CABINET_ROOT") or Path(__file__).resolve().parents[2])


def _iso(ts: _dt.datetime) -> str:
    return ts.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_date(v) -> Optional[_dt.date]:
    """Best-effort date coercion for yaml/frontmatter values (date, datetime,
    'YYYY-MM-DD…' strings). None when it isn't a date."""
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    m = re.match(r"\s*(\d{4})-(\d{2})-(\d{2})", str(v or ""))
    if not m:
        return None
    try:
        return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# The realpath jail — the ONLY gate destructive file ops pass through.
# ─────────────────────────────────────────────────────────────────────────────
def _contained(path: Path, root: Path) -> bool:
    """True iff realpath(path) is at/under realpath(root). Resolving the FULL
    chain means a symlinked parent dir cannot smuggle a target outside the
    jail past the check."""
    try:
        rp = Path(os.path.realpath(path))
        rr = Path(os.path.realpath(root))
        return rp == rr or rr in rp.parents
    except Exception:
        return False


def _designated_log_roots() -> list[Path]:
    """The repo's two log conventions (hand-made plists + generated plists —
    same pair framework/watchdog/registry.py floors on), plus any extra roots
    from CABINET_HYGIENE_ALLOWED_ROOTS (colon-separated; used by tests and by
    a future log-dir move without a code edit)."""
    roots = [
        Path.home() / ".cabinet" / "logs",
        Path.home() / "Library" / "Logs" / "cabinet",
    ]
    for tok in os.environ.get("CABINET_HYGIENE_ALLOWED_ROOTS", "").split(":"):
        tok = tok.strip()
        if tok:
            roots.append(Path(tok).expanduser())
    return roots


# ─────────────────────────────────────────────────────────────────────────────
# Retention sweep — the first (and only) code consumer of the retention config.
# ─────────────────────────────────────────────────────────────────────────────
def load_retention_config(path: str | os.PathLike | None = None) -> dict:
    """Retention yaml → dict. Path precedence: explicit arg, else the
    CABINET_RETENTION_CONFIG env var (set by the glue script). No path, or a
    missing/corrupt/foreign-shaped file → {} — the sweep then has nothing to
    do and says so, never guessing a window (fail-closed)."""
    p = path or os.environ.get("CABINET_RETENTION_CONFIG")
    if not p:
        return {}
    try:
        import yaml  # deferred — keep import-light, same posture as probes
        data = yaml.safe_load(Path(p).expanduser().read_text())
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — absent/corrupt config = no-op domain
        return {}


_LSOF_PATHS = ("/usr/sbin/lsof", "/usr/bin/lsof")  # fixed candidates — no PATH lookup
_DRAIN_ROUNDS = 8          # bounded post-copy re-reads to catch racing appends
_DRAIN_CHUNK = 1 << 20


def _held_open(path: Path) -> Optional[bool]:
    """Tri-state liveness probe: True → some live process holds *path* open
    (ANY fd counts — unlinking would strand that fd on a deleted inode, so
    the holder's first write after months of silence vanishes and disk is
    never reclaimed), False → provably no holder, None → indeterminate
    (lsof absent or errored; the caller then takes the truncate path, which
    is safe whether or not a holder exists). Fixed argv, no shell,
    read-only. The mtime window alone cannot answer this question: launchd
    StandardOut/StandardErrorPath targets of healthy keepalive daemons sit
    write-idle for 45+ days with a live fd — exactly the files unlink must
    never touch."""
    exe = next((c for c in _LSOF_PATHS if os.path.exists(c)), None)
    if exe is None:
        return None
    try:
        p = subprocess.run([exe, "-F", "pan", "--", str(path)],
                           capture_output=True, text=True, timeout=10)
    except Exception:  # noqa: BLE001 — unknown beats wrong; caller truncates
        return None
    out = (p.stdout or "").strip()
    if p.returncode == 0 and out:
        return True
    if not out and not (p.stderr or "").strip():
        return False  # lsof ran fine and found no holder (its silent rc-1 case)
    return None


def sweep_retention(cfg: dict, *, now: _dt.datetime, dry_run: bool) -> dict:
    """Honor the config's ``hygiene:`` windows for the log/ledger-archive dirs
    it names. Per entry {dir, pattern, days[, archive_days]}:

      * regular, non-empty files matching ``pattern`` whose mtime is older
        than ``days`` are gzip'd into <dir>/archive/; only after the archive
        verifies (exists, non-empty) is the original removed — by ``unlink``
        when the lsof probe (``_held_open``) proves no live process holds it,
        else by ``ftruncate`` on the very fd the copy just read (copytruncate:
        keepalive daemons / tmux wrappers holding the file keep a valid fd,
        their next Traceback lands in the live path the watchdog scans, and
        the fd-based truncate is immune to a path swap between check and
        act). A bounded drain re-read after the copy catches bytes appended
        mid-copy, narrowing the copy/act race to the same residual window
        logrotate's copytruncate accepts. Younger files are never touched;
        empty files are skipped (nothing to archive).
      * compressed archives are deleted ONLY when the entry explicitly names
        ``archive_days`` and the archive's mtime has passed it (the config's
        declared gone-is-gone contract). No ``archive_days`` → kept forever.

    Every entry dir must realpath-resolve under a designated log root; every
    unlink is jail-checked; symlinks are skipped + reported.
    """
    report: dict = {"rotated": [], "deleted_archives": [], "refused": [],
                    "skipped_young": 0, "skipped_empty": 0, "entries": 0}
    hygiene = cfg.get("hygiene") if isinstance(cfg, dict) else None
    if not isinstance(hygiene, dict):
        report["note"] = "no hygiene section in retention config — nothing to do"
        return report
    roots = _designated_log_roots()
    entries: list[tuple[str, dict]] = []
    for section in ("logs", "ledger_archives"):
        block = hygiene.get(section) or []
        if isinstance(block, list):
            entries.extend((section, e) for e in block if isinstance(e, dict))
    report["entries"] = len(entries)

    for section, entry in entries:
        raw_dir = entry.get("dir")
        days = entry.get("days")
        pattern = str(entry.get("pattern") or "*.log")
        if not raw_dir or not isinstance(days, int) or isinstance(days, bool) or days <= 0:
            report["refused"].append(f"{section}: malformed entry (need dir + days>0): {entry!r}")
            continue
        dirp = Path(str(raw_dir)).expanduser()
        jail = next((r for r in roots if _contained(dirp, r)), None)
        if jail is None:
            report["refused"].append(
                f"{section}: dir outside designated log roots — refused: {raw_dir}")
            continue
        if not dirp.is_dir():
            continue  # nothing there yet — not an error

        cutoff = now.timestamp() - days * 86400
        archive_dir = dirp / "archive"
        for f in sorted(dirp.iterdir()):
            if f.is_symlink():
                report["refused"].append(f"symlink skipped (never followed): {f}")
                continue
            if not f.is_file() or not fnmatch.fnmatch(f.name, pattern):
                continue
            try:
                st = f.stat()
            except OSError:
                continue
            if st.st_mtime >= cutoff:
                report["skipped_young"] += 1
                continue
            if st.st_size == 0:
                # Nothing to archive. Open-fd-idle daemon streams (a healthy
                # .err is 0 bytes for months) would otherwise churn a
                # header-only archive every window — and unlinking one would
                # strand its holder's fd on a deleted inode.
                report["skipped_empty"] += 1
                continue
            if not _contained(f, jail):
                report["refused"].append(f"jail escape refused: {f}")
                continue
            stamp = _dt.datetime.fromtimestamp(
                st.st_mtime, _dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            gz = archive_dir / f"{f.name}.{stamp}.gz"
            if dry_run:
                report["rotated"].append(
                    {"file": str(f), "archive": str(gz), "bytes": st.st_size,
                     "dry_run": True})
                continue
            try:
                archive_dir.mkdir(parents=True, exist_ok=True)
                held = _held_open(f)
                # Only a PROVEN-unheld file may be unlinked (launchd reopens
                # interval-job logs per run, so unlink is safe there). A held
                # — or indeterminate — file is truncated in place instead, so
                # live fds keep writing into the scanned path, never into a
                # deleted inode.
                mode = "unlink" if held is False else "truncate"
                with open(f, "rb" if mode == "unlink" else "r+b") as src:
                    with gzip.open(gz, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                        for _ in range(_DRAIN_ROUNDS):
                            tail = src.read(_DRAIN_CHUNK)  # racing appenders
                            if not tail:
                                break
                            dst.write(tail)
                    if gz.is_file() and gz.stat().st_size > 0 and _contained(f, jail):
                        if mode == "unlink":
                            f.unlink()  # removed ONLY after verified archive
                        else:
                            os.ftruncate(src.fileno(), 0)  # fd-based, no path re-lookup
                        report["rotated"].append(
                            {"file": str(f), "archive": str(gz),
                             "bytes": st.st_size, "mode": mode})
                    else:
                        report["refused"].append(
                            f"archive not verified — original kept: {f}")
            except Exception as exc:  # noqa: BLE001 — one bad file never kills the sweep
                report["refused"].append(f"rotate failed ({exc!r}) — original kept: {f}")

        archive_days = entry.get("archive_days")
        if (isinstance(archive_days, int) and not isinstance(archive_days, bool)
                and archive_days >= 0 and archive_dir.is_dir()):
            acutoff = now.timestamp() - archive_days * 86400
            for g in sorted(archive_dir.iterdir()):
                if g.is_symlink() or not g.is_file() or not g.name.endswith(".gz"):
                    continue
                try:
                    if g.stat().st_mtime >= acutoff:
                        continue
                except OSError:
                    continue
                if not _contained(g, jail):
                    report["refused"].append(f"jail escape refused: {g}")
                    continue
                if not dry_run:
                    try:
                        g.unlink()
                    except OSError:
                        continue
                report["deleted_archives"].append(str(g))
    return report


# ─────────────────────────────────────────────────────────────────────────────
# __pycache__ cap — regenerable byte-code caches under the repo.
# ─────────────────────────────────────────────────────────────────────────────
def _dir_size(d: Path) -> int:
    total = 0
    for dp, _dn, fns in os.walk(d):
        for fn in fns:
            try:
                total += (Path(dp) / fn).stat().st_size
            except OSError:
                pass
    return total


def _iter_pycache_dirs(root: Path):
    """__pycache__ dirs under root, NEVER descending into .git, node_modules,
    or .claude/worktrees (other checkouts are not this sweep's to touch)."""
    worktrees_parent = root / ".claude"
    for dirpath, dirnames, _fns in os.walk(root):
        dp = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules")]
        if dp == worktrees_parent and "worktrees" in dirnames:
            dirnames.remove("worktrees")
        if "__pycache__" in dirnames:
            dirnames.remove("__pycache__")  # don't walk inside; sized separately
            yield dp / "__pycache__"


def sweep_pycache(repo_root: Path, *, dry_run: bool,
                  cap_mb: Optional[int] = None) -> dict:
    """When the repo's total __pycache__ size exceeds the cap, delete the cache
    dirs (direct action — Python regenerates them). Only dirs literally named
    __pycache__, never symlinks, realpath-contained under the repo root."""
    if cap_mb is None:
        try:
            cap_mb = int(os.environ.get("CABINET_PYCACHE_CAP_MB",
                                        str(PYCACHE_CAP_MB_DEFAULT)))
        except ValueError:
            cap_mb = PYCACHE_CAP_MB_DEFAULT
    cap_bytes = cap_mb * 1024 * 1024
    dirs = list(_iter_pycache_dirs(repo_root))
    sizes = {d: _dir_size(d) for d in dirs}
    total = sum(sizes.values())
    report: dict = {"total_bytes": total, "cap_bytes": cap_bytes,
                    "deleted": [], "refused": []}
    if total <= cap_bytes:
        return report
    for d in dirs:
        if d.is_symlink() or d.name != "__pycache__" or not _contained(d, repo_root):
            report["refused"].append(f"refused (symlink/name/jail): {d}")
            continue
        if not dry_run:
            shutil.rmtree(d, ignore_errors=True)
        report["deleted"].append({"dir": str(d), "bytes": sizes[d]})
    return report


# ─────────────────────────────────────────────────────────────────────────────
# Read-only scanners → PROPOSE-ONLY findings. None of these mutate anything.
# ─────────────────────────────────────────────────────────────────────────────
def _git(args: list[str], cwd: Path, timeout: int = 15) -> tuple[int, str]:
    """Read-only git subprocess (fixed argv, no shell). Any failure degrades
    to (1, "") — a scanner then simply finds nothing."""
    try:
        p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                           text=True, timeout=timeout)
        return p.returncode, p.stdout
    except Exception:  # noqa: BLE001
        return 1, ""


def scan_worktrees(repo_root: Path, *, now: _dt.datetime,
                   stale_days: int = WORKTREE_STALE_DAYS) -> list[dict]:
    """GC candidates among worktrees under .claude/worktrees: merged into the
    current branch (merge-base --is-ancestor), git-prunable, or stale by
    last-commit age. READ-ONLY — removal is always a card, never an act."""
    rc, out = _git(["worktree", "list", "--porcelain"], repo_root)
    if rc != 0:
        return []
    wts: list[dict] = []
    cur: dict = {}
    for line in out.splitlines():
        if not line.strip():
            if cur:
                wts.append(cur)
                cur = {}
            continue
        key, _, val = line.partition(" ")
        if key == "worktree":
            cur = {"path": val}
        elif key == "HEAD":
            cur["head"] = val
        elif key == "branch":
            cur["branch"] = val
        elif key == "detached":
            cur["detached"] = True
        elif key == "prunable":
            cur["prunable"] = True
    if cur:
        wts.append(cur)

    base = repo_root / ".claude" / "worktrees"
    findings = []
    for wt in wts:
        p = Path(wt.get("path", ""))
        if not _contained(p, base):
            continue  # only the repo's own agent worktrees — nothing else
        head = wt.get("head", "")
        merged = False
        if head:
            rc2, _ = _git(["merge-base", "--is-ancestor", head, "HEAD"], repo_root)
            merged = rc2 == 0
        last_commit: Optional[str] = None
        age_days: Optional[int] = None
        if head:
            rc3, out3 = _git(["log", "-1", "--format=%ct", head], repo_root)
            if rc3 == 0 and out3.strip().isdigit():
                epoch = int(out3.strip())
                last_commit = _dt.datetime.fromtimestamp(
                    epoch, _dt.timezone.utc).strftime("%Y-%m-%d")
                age_days = int((now.timestamp() - epoch) // 86400)
        stale = age_days is not None and age_days > stale_days
        if not (merged or wt.get("prunable") or stale):
            continue
        reasons = []
        if merged:
            reasons.append("HEAD fully merged into current branch")
        if wt.get("prunable"):
            reasons.append("git reports prunable")
        if stale:
            reasons.append(f"last commit {age_days}d ago")
        size_kb: Optional[int] = None
        try:
            du = subprocess.run(["du", "-sk", str(p)], capture_output=True,
                                text=True, timeout=10)
            if du.returncode == 0:
                tok = du.stdout.split("\t", 1)[0].strip()
                size_kb = int(tok) if tok.isdigit() else None
        except Exception:  # noqa: BLE001
            size_kb = None
        findings.append({
            "path": str(p),
            "branch": wt.get("branch") or ("(detached)" if wt.get("detached") else "?"),
            "head": head[:12],
            "merged": merged,
            "prunable": bool(wt.get("prunable")),
            "last_commit": last_commit,
            "size_kb": size_kb,
            "reasons": reasons,
        })
    return findings


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_BODY_MARKERS = (
    ("usage_count", r"\*\*Usage count:\*\*\s*(\d+)"),
    ("last_used", r"\*\*Last used:\*\*\s*([^\n]+)"),
    ("date", r"\*\*Date:\*\*\s*(\d{4}-\d{2}-\d{2})"),
    ("status", r"\*\*Status:\*\*\s*([^\n]+)"),
    ("sunset", r"\*\*Sunset:\*\*\s*([^\n]+)"),
)


def _parse_skill_meta(text: str) -> dict:
    """Skill metadata from YAML frontmatter (authoritative) plus the body-line
    conventions promoted skills actually use (``**Usage count:** 0`` etc.).
    Frontmatter keys win; body markers only fill gaps."""
    meta: dict = {}
    m = _FRONTMATTER_RE.match(text or "")
    if m:
        try:
            import yaml  # deferred
            fm = yaml.safe_load(m.group(1)) or {}
            if isinstance(fm, dict):
                meta.update({str(k).lower(): v for k, v in fm.items()})
        except Exception:  # noqa: BLE001 — bad frontmatter → body markers only
            pass
    for key, rx in _BODY_MARKERS:
        if key not in meta or meta[key] in (None, ""):
            mm = re.search(rx, text or "")
            if mm:
                meta[key] = mm.group(1).strip()
    return meta


def _sunset_state(value, today: _dt.date):
    """('passed'|'pending', date) for date-typed sunsets; ('condition', str)
    for condition strings; None when absent. A passed sunset STRENGTHENS a
    card — it never authorizes deletion."""
    if value in (None, ""):
        return None
    d = _parse_date(value)
    if d is not None:
        return ("passed" if d < today else "pending", d)
    return ("condition", str(value).strip())


def _manifest_sunset(path: Path):
    """Optional ``sunset:`` key from a pack/extension manifest sitting next to
    a skill (manifest.yml|yaml|json). Read-only, degrade to None."""
    for name in ("manifest.yml", "manifest.yaml", "manifest.json"):
        mp = path / name
        if not mp.is_file():
            continue
        try:
            if mp.suffix == ".json":
                data = json.loads(mp.read_text())
            else:
                import yaml  # deferred
                data = yaml.safe_load(mp.read_text())
            if isinstance(data, dict) and data.get("sunset") not in (None, ""):
                return data.get("sunset")
        except Exception:  # noqa: BLE001
            continue
    return None


def scan_skills(repo_root: Path, *, now: _dt.datetime,
                dormant_days: int = SKILL_DORMANT_DAYS,
                unused_days: int = SKILL_UNUSED_DAYS) -> list[dict]:
    """Dormancy candidates across promoted skills (.claude/skills/*/SKILL.md),
    evolved runtime skills (memory/skills/evolved/*.md), and pack manifests
    (.claude-plugin/*.json ``sunset`` keys). PROPOSE-ONLY."""
    today = now.date()
    findings = []
    sources: list[tuple[str, Path]] = []
    sources += [("promoted", p) for p in
                sorted((repo_root / ".claude" / "skills").glob("*/SKILL.md"))]
    sources += [("evolved", p) for p in
                sorted((repo_root / "memory" / "skills" / "evolved").glob("*.md"))]
    for kind, f in sources:
        try:
            meta = _parse_skill_meta(f.read_text())
        except OSError:
            continue
        sunset_val = meta.get("sunset")
        if sunset_val in (None, "") and kind == "promoted":
            # A pack manifest sits at a promoted skill's own dir root; the
            # evolved dir is a flat pool, so a manifest there would ambiguously
            # cover every draft — not consulted.
            sunset_val = _manifest_sunset(f.parent)
        sunset = _sunset_state(sunset_val, today)
        try:
            usage = int(str(meta.get("usage_count")).strip())
        except (TypeError, ValueError):
            usage = None
        created = _parse_date(meta.get("date") or meta.get("created"))
        last_used = _parse_date(meta.get("last_used"))
        reasons = []
        if sunset and sunset[0] == "passed":
            reasons.append(f"sunset passed ({sunset[1].isoformat()})")
        elif sunset and sunset[0] == "condition":
            reasons.append(f"sunset condition declared: {sunset[1]!r}")
        if usage == 0 and created and (today - created).days > dormant_days:
            reasons.append(
                f"usage_count 0 since {created.isoformat()} "
                f"({(today - created).days}d)")
        if last_used and (today - last_used).days > unused_days:
            reasons.append(
                f"last used {last_used.isoformat()} "
                f"({(today - last_used).days}d ago)")
        # A bare pending sunset or condition string alone doesn't flag; it only
        # annotates. Flag when a hard dormancy signal (or passed sunset) exists.
        hard = any(r.startswith(("sunset passed", "usage_count", "last used"))
                   for r in reasons)
        if hard:
            default_name = f.parent.name if kind == "promoted" else f.stem
            findings.append({
                "path": str(f.relative_to(repo_root)),
                "skill_kind": kind,
                "name": str(meta.get("name") or default_name),
                "usage_count": usage,
                "created": created.isoformat() if created else None,
                "last_used": last_used.isoformat() if last_used else None,
                "reasons": reasons,
            })
    # Pack manifests at the repo's plugin root — sunset keys only.
    plugin_dir = repo_root / ".claude-plugin"
    if plugin_dir.is_dir():
        for pj in sorted(plugin_dir.glob("*.json")):
            try:
                data = json.loads(pj.read_text())
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(data, dict):
                continue
            sunset = _sunset_state(data.get("sunset"), today)
            if sunset and sunset[0] == "passed":
                findings.append({
                    "path": str(pj.relative_to(repo_root)),
                    "skill_kind": "pack-manifest",
                    "name": str(data.get("name") or pj.stem),
                    "usage_count": None, "created": None, "last_used": None,
                    "reasons": [f"sunset passed ({sunset[1].isoformat()})"],
                })
    return findings


def _services_rows(text: str) -> list[dict]:
    """Narrow line-parser over the fleet manifest's service rows — the same
    exact-indent discipline as framework/watchdog/registry.py, extended with
    line numbers (needed to date a ``disabled:`` flip via git blame)."""
    rows: list[dict] = []
    cur: Optional[dict] = None
    for lineno, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r"^  - name:\s*([A-Za-z0-9._-]+)\s*$", line)
        if m:
            cur = {"name": m.group(1), "lineno": lineno, "keys": {}}
            rows.append(cur)
            continue
        if cur is None:
            continue
        km = re.match(r"^    ([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if km:
            val = km.group(2).split("#", 1)[0].strip()
            cur["keys"][km.group(1)] = (val, lineno)
    return rows


def _blame_date(repo_root: Path, rel_path: str, lineno: int) -> Optional[_dt.date]:
    """Committer date of one line (read-only git blame). None on any failure —
    an undatable disabled row is SKIPPED, never guessed (evidence-gated)."""
    rc, out = _git(["blame", "-L", f"{lineno},{lineno}", "--porcelain",
                    "--", rel_path], repo_root)
    if rc != 0:
        return None
    m = re.search(r"(?m)^committer-time (\d+)$", out)
    if not m:
        return None
    return _dt.datetime.fromtimestamp(int(m.group(1)), _dt.timezone.utc).date()


def scan_services(repo_root: Path, *, now: _dt.datetime,
                  disabled_days: int = SERVICE_DISABLED_DAYS) -> list[dict]:
    """Fleet-manifest rows that have sat ``disabled: true`` beyond the window.
    Dated by an optional ``disabled_since:`` key on the row, else by git blame
    on the ``disabled:`` line. PROPOSE-ONLY."""
    manifest = repo_root / "cabinet" / "services.yml"
    try:
        text = manifest.read_text()
    except OSError:
        return []
    today = now.date()
    findings = []
    for row in _services_rows(text):
        dis = row["keys"].get("disabled")
        if not dis or dis[0].lower() not in ("true", "yes", "1"):
            continue
        since = _parse_date((row["keys"].get("disabled_since") or ("",))[0])
        if since is None:
            since = _blame_date(repo_root, "cabinet/services.yml", dis[1])
        if since is None:
            continue  # undatable — no evidence, no card row
        age = (today - since).days
        if age <= disabled_days:
            continue
        notes = (row["keys"].get("notes") or ("",))[0]
        if notes in (">", ">-", "|", "|-"):
            notes = ""  # block-scalar marker — the text lives on deeper lines
        findings.append({
            "name": row["name"],
            "lineno": row["lineno"],
            "disabled_since": since.isoformat(),
            "age_days": age,
            "notes": notes[:120],
        })
    return findings


def scan_launchd_templates(repo_root: Path) -> list[dict]:
    """``*.template.plist`` files with NO instantiated sibling anywhere a
    rendered plist could live (the launchd dir itself, its generated/ output,
    or the user's LaunchAgents). PROPOSE-ONLY."""
    tdir = repo_root / "cabinet" / "launchd"
    if not tdir.is_dir():
        return []
    locations = [tdir, tdir / "generated",
                 Path.home() / "Library" / "LaunchAgents"]
    names: set[str] = set()
    for loc in locations:
        if loc.is_dir():
            names.update(p.name for p in loc.glob("*.plist"))
    findings = []
    for t in sorted(tdir.glob("*.template.plist")):
        stem = t.name[: -len(".template.plist")]
        instantiated = any(
            (n == f"{stem}.plist" or n.startswith(f"{stem}."))
            and not n.endswith(".template.plist")
            for n in names)
        if not instantiated:
            findings.append({"template": t.name,
                             "path": str(t.relative_to(repo_root))})
    return findings


# ─────────────────────────────────────────────────────────────────────────────
# Cards — the propose-only surface. Reuses the front-door intake stream.
# ─────────────────────────────────────────────────────────────────────────────
def _fingerprint(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


_DAYCOUNT_RE = re.compile(r"\b\d+d\b")
_VOLATILE_FINDING_KEYS = frozenset({"age_days", "size_kb", "lineno"})


def _finding_identity(f):
    """Stable identity projection of one finding — what the situation IS, not
    how old it is TODAY. The raw findings embed daily-incrementing counters
    (scan_services: ``age_days``; scan_worktrees: du-derived ``size_kb`` and
    'last commit Nd ago' reasons; scan_skills: '(Nd)' day counts), so hashing
    them raw flips the fingerprint every day and _should_card's
    differing-fingerprint branch re-cards the identical situation daily —
    defeating RECARD_COOLDOWN_DAYS. Volatile keys are dropped (``lineno`` too:
    an unrelated manifest edit shifts it), rendered day-counts are masked to
    'Nd', and fixed dates (last_commit, disabled_since, created, last_used)
    stay — they move only when the situation actually changes."""
    if not isinstance(f, dict):
        return f
    ident = {}
    for k, v in f.items():
        if k in _VOLATILE_FINDING_KEYS:
            continue
        if k == "reasons" and isinstance(v, list):
            ident[k] = [_DAYCOUNT_RE.sub("Nd", str(r)) for r in v]
        else:
            ident[k] = v
    return ident


def _card(domain: str, summary: str, findings: list, now: _dt.datetime) -> dict:
    """One canonical intake item (validated by intake.validate_item at enqueue
    time) — the same shape framework/learning/self_proposal.py emits."""
    return {
        "source": "apoptosis",
        "kind": "hygiene-proposal",
        "ts": _iso(now),
        "urgency_tier": "batch",   # rides the next briefing — never a ping
        "payload": {
            "domain": domain,
            "summary": summary,
            "findings": findings,
            # Fingerprint the stable identity, not the raw findings — the raw
            # rows tick daily (age_days / size_kb / rendered day counts) and
            # would defeat the re-card cooldown.
            "fingerprint": _fingerprint([_finding_identity(f) for f in findings]),
            "propose_only": True,
        },
    }


def _rows(lines: list[str]) -> str:
    shown = lines[:CARD_EVIDENCE_ROWS]
    extra = len(lines) - len(shown)
    return "\n".join(shown) + (f"\n  … +{extra} more" if extra > 0 else "")


def _worktree_card(findings: list[dict], now: _dt.datetime) -> dict:
    ev = []
    for f in findings:
        size = f" ~{f['size_kb'] // 1024}MB" if f.get("size_kb") else ""
        ev.append(f"  - {f['path']} — {f['branch']} @ {f['head']}, "
                  f"{'; '.join(f['reasons'])}{size}")
    summary = (
        "🧹 Hygiene proposal — worktree GC (PROPOSE-ONLY; nothing removed)\n"
        f"WHAT: {len(findings)} worktree(s) under .claude/worktrees look done "
        "(merged into the current branch, git-prunable, or stale).\n"
        "EVIDENCE:\n" + _rows(ev) + "\n"
        "REDO (apply, per path): git worktree remove '<path>'  "
        "# refuses if dirty — review before forcing\n"
        "UNDO (recover): branch refs are untouched — "
        "git worktree add '<path>' '<branch>' recreates the checkout.\n"
        "DECIDE: reply remove:<path|all> or keep — nothing happens without "
        "your word.")
    return _card("worktrees", summary, findings, now)


def _skills_card(findings: list[dict], now: _dt.datetime) -> dict:
    ev = [f"  - {f['path']} ({f['skill_kind']}) — {'; '.join(f['reasons'])}"
          for f in findings]
    summary = (
        "🧹 Hygiene proposal — dormant skills / packs (PROPOSE-ONLY; nothing "
        "deleted)\n"
        f"WHAT: {len(findings)} skill/pack artifact(s) show zero or stale "
        "usage (a passed sunset: strengthens the case; it never auto-deletes).\n"
        "EVIDENCE:\n" + _rows(ev) + "\n"
        "REDO (retire, per item): promoted → git rm -r '<dir>'; evolved → "
        "mv '<file>' 'memory/skills/evolved/_retired/<file>'\n"
        "UNDO: promoted → git checkout HEAD -- '<dir>' (or git revert of the "
        "retirement commit); evolved → mv back from _retired/.\n"
        "DECIDE: reply retire:<name|all> or keep — demotion is your call.")
    return _card("skills", summary, findings, now)


def _services_card(service_findings: list[dict], template_findings: list[dict],
                   now: _dt.datetime) -> dict:
    ev = [f"  - services.yml row '{f['name']}' (line {f['lineno']}) — "
          f"disabled since {f['disabled_since']} ({f['age_days']}d)"
          for f in service_findings]
    ev += [f"  - {f['path']} — template never instantiated (no rendered "
           f"plist anywhere)" for f in template_findings]
    n = len(service_findings) + len(template_findings)
    summary = (
        "🧹 Hygiene proposal — parked services / dead templates (PROPOSE-ONLY)\n"
        f"WHAT: {n} fleet artifact(s) look retired in practice: rows disabled "
        ">60d and/or launchd templates never instantiated.\n"
        "EVIDENCE:\n" + _rows(ev) + "\n"
        "REDO (retire): remove the row from cabinet/services.yml / "
        "git rm 'cabinet/launchd/<template>' — in a reviewed commit.\n"
        "UNDO: git checkout HEAD -- cabinet/services.yml (or revert the "
        "retirement commit); re-enable instead = delete the row's "
        "'disabled: true' line.\n"
        "DECIDE: reply retire:<name|all> or keep — the manifest stays fleet "
        "truth until you rule.")
    return _card("services", summary, service_findings + template_findings, now)


def build_cards(findings: dict, *, now: _dt.datetime) -> list[dict]:
    cards = []
    if findings.get("worktrees"):
        cards.append(_worktree_card(findings["worktrees"], now))
    if findings.get("skills"):
        cards.append(_skills_card(findings["skills"], now))
    if findings.get("services") or findings.get("templates"):
        cards.append(_services_card(findings.get("services") or [],
                                    findings.get("templates") or [], now))
    return cards


# ─────────────────────────────────────────────────────────────────────────────
# Re-card cooldown state — identical findings are not re-pinged every run.
# ─────────────────────────────────────────────────────────────────────────────
def _state_path() -> Path:
    d = os.environ.get("CABINET_HYGIENE_STATE_DIR") or str(
        Path.home() / "Library" / "Application Support" / "cabinet")
    return Path(os.path.expanduser(d)) / STATE_FILENAME


def _load_state() -> dict:
    try:
        data = json.loads(_state_path().read_text())
        if isinstance(data, dict) and isinstance(data.get("cards"), dict):
            return data
    except Exception:  # noqa: BLE001
        pass
    return {"cards": {}}


def _save_state(state: dict) -> None:
    try:
        p = _state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, sort_keys=True))
    except Exception:  # noqa: BLE001 — a failed save costs one extra card, never a crash
        pass


def _should_card(state: dict, domain: str, fingerprint: str,
                 now: _dt.datetime) -> bool:
    prev = (state.get("cards") or {}).get(domain) or {}
    if prev.get("fingerprint") != fingerprint:
        return True
    prev_ts = str(prev.get("ts") or "")
    try:
        prev_dt = _dt.datetime.strptime(prev_ts, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=_dt.timezone.utc)
    except ValueError:
        return True
    return (now - prev_dt).days >= RECARD_COOLDOWN_DAYS


def _surface_cards(cards: list[dict], enqueue_fn: Optional[Callable],
                   state: dict, now: _dt.datetime, dry_run: bool) -> list[dict]:
    """Enqueue cards on the front-door intake stream (the existing helper —
    imported, not reinvented). Transport failures degrade gracefully; state
    only records a card as surfaced when the enqueue actually confirmed."""
    enq = enqueue_fn
    if enq is None and not dry_run:
        try:
            from framework.frontdoor import intake
            enq = intake.enqueue
        except Exception:  # noqa: BLE001
            enq = None
    results = []
    for card in cards:
        domain = card["payload"]["domain"]
        fp = card["payload"]["fingerprint"]
        if not _should_card(state, domain, fp, now):
            results.append({"domain": domain, "fingerprint": fp,
                            "suppressed": "cooldown", "enqueued_id": None})
            continue
        enqueued_id = None
        if not dry_run and enq is not None:
            try:
                enqueued_id = enq(card)
            except Exception:  # noqa: BLE001 — never raise on transport
                enqueued_id = None
        if enqueued_id is not None:
            state.setdefault("cards", {})[domain] = {
                "fingerprint": fp, "ts": _iso(now)}
        results.append({"domain": domain, "fingerprint": fp,
                        "suppressed": None, "enqueued_id": enqueued_id,
                        "summary": card["payload"]["summary"]})
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Self-heartbeat — stamped ONLY after a completed sweep (dead-man semantics).
# ─────────────────────────────────────────────────────────────────────────────
def write_heartbeat(report: dict, *, now: _dt.datetime) -> Optional[str]:
    """Append one status line to <log dir>/apoptosis-sweep.log. The location
    matches the per-service log convention the outcome-watchdog floors on, so
    enrolling an 'apoptosis-sweep' row in the fleet manifest (the scheduling
    wave's job) makes staleness of THIS file a paged failure. The line text
    deliberately carries no watchdog error-marker tokens on success."""
    d = Path(os.path.expanduser(
        os.environ.get("CABINET_HYGIENE_LOG_DIR")
        or str(Path.home() / ".cabinet" / "logs")))
    try:
        d.mkdir(parents=True, exist_ok=True)
        p = d / HEARTBEAT_FILENAME
        ret = report.get("retention") or {}
        pyc = report.get("pycache") or {}
        line = (
            f"[{_iso(now)}] apoptosis-sweep: ok "
            f"rotated={len(ret.get('rotated') or [])} "
            f"archives_deleted={len(ret.get('deleted_archives') or [])} "
            f"refused={len(ret.get('refused') or [])} "
            f"pycache_deleted={len(pyc.get('deleted') or [])} "
            f"cards={len([c for c in report.get('cards') or [] if not c.get('suppressed')])} "
            f"errors={len(report.get('errors') or [])} "
            f"dry_run={bool(report.get('dry_run'))}\n")
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(line)
        return str(p)
    except Exception:  # noqa: BLE001 — an unstampable heartbeat is itself the signal
        return None


# ─────────────────────────────────────────────────────────────────────────────
# run_sweep — the one entrypoint.
# ─────────────────────────────────────────────────────────────────────────────
def run_sweep(*, repo_root: str | os.PathLike | None = None,
              retention_config_path: str | os.PathLike | None = None,
              now: Optional[_dt.datetime] = None,
              enqueue_fn: Optional[Callable[[dict], str]] = None,
              dry_run: bool = False) -> dict:
    """One full hygiene pass. Every domain is individually guarded — one bad
    domain degrades with a reported error and the rest of the sweep completes.
    The heartbeat stamps LAST, only when the sweep ran to completion."""
    root = Path(repo_root) if repo_root else _repo_root()
    ts = now or _dt.datetime.now(_dt.timezone.utc)
    report: dict = {"ts": _iso(ts), "repo_root": str(root),
                    "dry_run": dry_run, "errors": []}

    # Direct-action domains (trivially-regenerable exhaust only).
    try:
        cfg = load_retention_config(retention_config_path)
        report["retention"] = sweep_retention(cfg, now=ts, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        report["retention"] = {}
        report["errors"].append(f"retention: {exc!r}")
    try:
        report["pycache"] = sweep_pycache(root, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        report["pycache"] = {}
        report["errors"].append(f"pycache: {exc!r}")

    # Propose-only domains (read-only scans → cards).
    findings: dict = {}
    for name, fn in (
            ("worktrees", lambda: scan_worktrees(root, now=ts)),
            ("skills", lambda: scan_skills(root, now=ts)),
            ("services", lambda: scan_services(root, now=ts)),
            ("templates", lambda: scan_launchd_templates(root))):
        try:
            findings[name] = fn()
        except Exception as exc:  # noqa: BLE001
            findings[name] = []
            report["errors"].append(f"{name}: {exc!r}")
    report["findings"] = findings

    state = _load_state()
    cards = build_cards(findings, now=ts)
    report["cards"] = _surface_cards(cards, enqueue_fn, state, ts, dry_run)
    if not dry_run:
        _save_state(state)

    # Dead-man stamp — LAST, so a crash above never fakes liveness.
    report["heartbeat"] = write_heartbeat(report, now=ts)
    return report


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python3 -m framework.hygiene.apoptosis",
        description="Cabinet hygiene sweep — direct action only for "
                    "regenerable exhaust; propose-only cards for the rest.")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would happen; mutate nothing, send no cards")
    ap.add_argument("--retention-config", default=None,
                    help="retention yaml path (default: CABINET_RETENTION_CONFIG)")
    ap.add_argument("--repo-root", default=None,
                    help="repo root (default: CABINET_ROOT or file-relative)")
    args = ap.parse_args(argv)
    report = run_sweep(repo_root=args.repo_root,
                       retention_config_path=args.retention_config,
                       dry_run=args.dry_run)
    print(json.dumps(report, indent=2, default=str))
    return 1 if report["errors"] else 0


if __name__ == "__main__":  # pragma: no cover — CLI shim
    sys.exit(main())
