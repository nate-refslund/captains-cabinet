#!/usr/bin/env python3.12
"""self-improvement-journal — read and REVERT what the armed learning loop
applied to the cabinet itself.

WHY THIS EXISTS (Captain ruling 2026-07-26): the Captain armed the
self-improvement loop's auto-apply (`REPORT_ONLY=0` on the
`self-improvement-loop` services.yml row) over the recommendation to sequence
it, with the risk stated. He accepted a window; this tool is what makes the
window OBSERVABLE and CLOSEABLE rather than merely fast:

  (a) every auto-applied change is individually reversible and logged — what
      changed, why, and the evidence it cited — with a ONE-COMMAND revert of
      any single application;
  (b) `--weekly-section` renders the Captain-facing line that the weekly
      shadow-dividend report carries (cabinet/cron/cog3-captain-report.sh), so
      the window is inspected weekly instead of assumed.

THE JOURNAL is cabinet/logs/self-improvement-applications.jsonl — one
append-only row per application, written by
framework.learning.self_improvement_loop._journal_application. It is an
OPERATOR surface, not a second source of truth: the org event ledger
(role_capability_added / role_authority_changed / skill_promoted) and
instance/roles/lineage.yml remain the durable record. A row carries the exact
inverse in `undo`, which is the only thing this CLI executes.

WHAT THE LOOP CAN ACTUALLY MUTATE (measured 2026-07-26, before arming):
  * role capability lists                     instance/roles/active/<slug>.yml
  * a role's DESCRIPTIVE authority_level      same file — read by officers as
    roster context (cabinet/scripts/lib/officer-boot.sh:143), NOT by the
    enforcement plane; the machine authority answer stays the
    matrix x posture x lane resolution, which this loop cannot reach
  * skill-draft status flips                  memory/skills/evolved/*.md
                                              (sovereign posture only)
  * proposal-YAML status stamps               instance/roles/proposals/*.yml
CODE IS OUT OF REACH BY CONSTRUCTION: _is_code_diff_proposal routes every
code_change / code_diff proposal (and anything carrying a non-empty `diff`) to
framework.learning.gate.ratify, which produces an evidence pack and applies
NOTHING. Germline apply stays a Captain-manual ceremony.

Usage:
  self-improvement-journal.py --list [--since-days N]
  self-improvement-journal.py --show <application_id>
  self-improvement-journal.py --undo <application_id> [--dry-run]
  self-improvement-journal.py --weekly-section [--now <ISO8601Z>] [--days N]

Exit codes: 0 ok · 1 nothing matched / revert refused · 2 usage or IO error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

JOURNAL_REL = "cabinet/logs/self-improvement-applications.jsonl"


def _cabinet_root() -> Path:
    return Path(os.environ.get("CABINET_ROOT", _REPO_ROOT))


def _journal_path() -> Path:
    return _cabinet_root() / JOURNAL_REL


def _load_rows() -> list[dict]:
    path = _journal_path()
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # a torn tail line is skipped, never fatal
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _effective(rows: list[dict]) -> list[dict]:
    """Fold revert rows onto their originals — the last word per id wins."""
    by_id: dict[str, dict] = {}
    for row in rows:
        aid = str(row.get("application_id") or "")
        if not aid:
            continue
        if row.get("reverts"):
            target = by_id.get(str(row["reverts"]))
            if target is not None:
                target["reverted"] = True
                target["reverted_at"] = row.get("applied_at")
        by_id.setdefault(aid, row)
    return list(by_id.values())


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _one_line(row: dict) -> str:
    change = row.get("change") or {}
    if row.get("kind") == "capability_added":
        what = f"capability {change.get('capability')!r} added to role {row.get('role_slug')}"
    elif row.get("kind") == "authority_change":
        what = (f"role {row.get('role_slug')} authority_level "
                f"{change.get('authority_level_before')!r} -> "
                f"{change.get('authority_level_after')!r}")
    elif row.get("kind") == "skill_validated":
        what = f"skill draft {row.get('role_slug')} promoted to status: validated"
    else:
        what = f"{row.get('kind')} on {row.get('role_slug')}"
    state = " [REVERTED]" if row.get("reverted") else ""
    return f"{row.get('application_id')}  {row.get('applied_at')}  {what}{state}"


# ---------------------------------------------------------------------------
# Revert
# ---------------------------------------------------------------------------

def _append(row: dict) -> None:
    path = _journal_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row, default=str) + "\n")


def _undo(row: dict, dry_run: bool) -> tuple[bool, str]:
    undo = row.get("undo") or {}
    op = undo.get("op")
    if op in ("capability_removed", "authority_change"):
        slug = undo.get("role_slug")
        if not slug:
            return False, "undo row carries no role_slug"
        if op == "capability_removed":
            changes = {"capability": undo.get("capability")}
            desc = (f"revert of {row.get('application_id')}: removed "
                    f"capability {undo.get('capability')!r}")
        else:
            if undo.get("authority_level") is None:
                return False, ("no pre-image authority_level recorded — this "
                               "application predates the journal; revert by hand")
            changes = {"authority_level": undo.get("authority_level")}
            desc = (f"revert of {row.get('application_id')}: authority_level "
                    f"restored to {undo.get('authority_level')!r}")
        if dry_run:
            return True, f"[dry-run] would adapt_role({slug}, {op}, {changes})"
        from framework.roles.lifecycle import adapt_role
        adapt_role(slug, adaptation_type=op, description=desc, changes=changes,
                   evidence=f"self-improvement-journal --undo {row.get('application_id')}",
                   rationale="Captain-ordered reversibility safeguard (2026-07-26 arming ruling)",
                   approved_by="self_improvement_journal")
        return True, desc
    if op == "skill_status":
        path = Path(str(undo.get("skill_path") or ""))
        want = str(undo.get("status") or "draft")
        if not path.is_file():
            return False, f"skill file missing at {path}"
        text = path.read_text()
        lines = text.splitlines(keepends=True)
        out, done = [], False
        for line in lines:
            if not done and line.startswith("status:"):
                out.append(f"status: {want}\n")
                done = True
            else:
                out.append(line)
        if not done:
            return False, "no `status:` line in the skill frontmatter"
        if dry_run:
            return True, f"[dry-run] would set status: {want} in {path}"
        path.write_text("".join(out))
        return True, f"status: {want} restored in {path}"
    return False, f"no revert handler for undo op {op!r}"


# ---------------------------------------------------------------------------
# Weekly Captain-facing section (safeguard (b))
# ---------------------------------------------------------------------------

def _weekly_section(now: datetime, days: int) -> str:
    rows = _effective(_load_rows())
    cutoff = now - timedelta(days=days)
    # Revert rows are bookkeeping, never applications: counting them would
    # inflate "what the loop applied to itself" with the undos of itself.
    recent = [r for r in rows
              if r.get("kind") != "revert"
              and (_parse_ts(r.get("applied_at")) or now) >= cutoff]
    live = [r for r in recent if not r.get("reverted")]
    reverted = [r for r in recent if r.get("reverted")]

    out = ["## Self-improvement — applied to itself",
           "",
           f"_Window: the last {days} days, to {now.strftime('%Y-%m-%d')}. "
           "Source: cabinet/logs/self-improvement-applications.jsonl. "
           "The loop's auto-apply has been ARMED since the Captain's "
           "2026-07-26 ruling; this section is the window he asked to keep "
           "open._",
           ""]
    if not recent:
        out += ["**Nothing.** The learning loop applied no changes to the "
                "cabinet in this window.",
                "",
                "(An empty section is the loop running and finding nothing "
                "worth applying — not the loop being off. Its 6-hourly job "
                "log is the liveness surface.)"]
        return "\n".join(out) + "\n"

    out += [f"**{len(live)} change(s) stand; {len(reverted)} were reverted.** "
            "Any single one can be undone with "
            "`python3.12 cabinet/scripts/self-improvement-journal.py --undo <id>`.",
            ""]
    for row in sorted(recent, key=lambda r: str(r.get("applied_at"))):
        out.append(f"- {_one_line(row)}")
        why = row.get("rationale") or "(no rationale recorded)"
        ev = row.get("evidence") or "(no evidence recorded)"
        out.append(f"  - why: {why}")
        out.append(f"  - evidence cited: {ev}")
    out.append("")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Read and revert armed self-improvement applications")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="list applications")
    g.add_argument("--show", metavar="ID", help="print one application as JSON")
    g.add_argument("--undo", metavar="ID", help="revert one application")
    g.add_argument("--weekly-section", action="store_true",
                   help="render the Captain-facing weekly markdown section")
    ap.add_argument("--since-days", type=int, default=0,
                    help="--list: only applications newer than N days")
    ap.add_argument("--days", type=int, default=7,
                    help="--weekly-section: window length (default 7)")
    ap.add_argument("--now", default=None,
                    help="--weekly-section: declared timestamp (default: now)")
    ap.add_argument("--dry-run", action="store_true",
                    help="--undo: print the inverse, change nothing")
    args = ap.parse_args(argv)

    if args.weekly_section:
        now = _parse_ts(args.now) or datetime.now(timezone.utc)
        sys.stdout.write(_weekly_section(now, max(1, args.days)))
        return 0

    rows = _effective(_load_rows())
    if args.list:
        if args.since_days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=args.since_days)
            rows = [r for r in rows
                    if (_parse_ts(r.get("applied_at")) or cutoff) >= cutoff]
        if not rows:
            print(f"no applications recorded in {_journal_path()}")
            return 0
        for row in sorted(rows, key=lambda r: str(r.get("applied_at"))):
            print(_one_line(row))
        return 0

    target_id = args.show or args.undo
    match = next((r for r in rows if r.get("application_id") == target_id), None)
    if match is None:
        print(f"no application {target_id!r} in {_journal_path()}", file=sys.stderr)
        return 1

    if args.show:
        print(json.dumps(match, indent=2, sort_keys=True, default=str))
        return 0

    if match.get("reverted"):
        print(f"{target_id} is already reverted — refusing (re-applying is a "
              f"new decision, not an undo)", file=sys.stderr)
        return 1
    ok, detail = _undo(match, args.dry_run)
    if not ok:
        print(f"revert refused: {detail}", file=sys.stderr)
        return 1
    if not args.dry_run:
        _append({
            "application_id": f"{target_id}-revert",
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "reverts": target_id,
            "kind": "revert",
            "role_slug": match.get("role_slug"),
            "change": {"detail": detail},
            "rationale": "Captain-ordered reversibility safeguard (2026-07-26)",
        })
    print(detail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
