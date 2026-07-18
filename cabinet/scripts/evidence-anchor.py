#!/usr/bin/env python3.12
"""evidence-anchor.py — daily external anchoring for the evidence plane.

Evidence program Phase 1, items 5+6 (design of record 2026-07-16; Captain
decision D3 = BOTH surfaces). Every run, in order:

  1. Appends the day's digest-anchor event (checksums of the org-events day
     file, the consequence-ledger day file, and the trigger-archive manifest)
     to the evidence trial ``evt-digest-anchor-<yyyymmdd>`` — the weaker
     breadth ledgers become tamper-evident inside the signed store.
  2. Collects a content-free anchor record of the store's tamper-evidence
     surface (trial tip hashes, verifier watermarks, control digest,
     purge-receipt manifest, Captain-label digests).
  3. Checks the live store against the LAST exported record — a store copy
     restored to an earlier state is caught here, which is exactly what the
     in-store verifier cannot prove (its documented anti-rollback residual).
  4. Exports the record to the Captain-owned surfaces: one JSONL line
     appended + committed in the private meta repo (``anchor_dir``), and a
     plain-English Telegram receipt via the ONE sanctioned front-door
     channel (``framework/frontdoor/channel.py`` — recipient and token are
     owned by the channel/runtime env; this script hardcodes neither).

Credless-safe: every unconfigured surface skips cleanly (exit 0). Config is
``instance/config/evidence-anchor.yml`` (see the committed ``.example``).

Read-only over the store except the sanctioned digest-anchor append; never
reads ``.signing-key``; never runs the verifier (verify advances watermarks —
a side effect a read-only anchor job must not have); never pushes the meta
repo (its own sync policy owns that).

Exit codes: 0 ok/skips · 1 evidence append failed · 2 integrity findings.
Scheduled via cabinet/services.yml row ``evidence-anchor`` (staged; enabled
at the Phase-1 ceremony).

``--recount-labels`` (HP-3, opt-in — the daily run is byte-identical
without it): prove the Captain label journal append-only against the FULL
anchor history and cross-join it with the store (forged/removed journal
rows, unjournaled in-store labels, channel-claim divergence). Read-only;
exit 0 clean / 2 findings.

Usage:
  python3.12 cabinet/scripts/evidence-anchor.py [--dry-run] [--json]
      [--store PATH] [--check [FILE]] [--recount-labels [FILE]]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.evidence_anchor import (  # noqa: E402
    LABELS_JOURNAL_BASENAME,
    build_digest_detail,
    check_anchor,
    collect_anchor,
    digest_trial_id,
    informational_changes,
    receipt_text,
    recount_labels,
)

ANCHOR_FILE_NAME = "evidence-anchors.jsonl"
# Captain-label surfaces anchored by default when present (HP-3: label
# digests land off-store daily and the --recount-labels verb re-counts the
# journal against this anchored history — tamper-EVIDENT; until HP-1
# isolates the signing key a same-OS-user can still forge store events and
# the un-anchored journal tail together, and root can forge everything).
# Repo-relative; instance config may override with `captain_label_files`.
DEFAULT_LABEL_FILES = (
    "shared/interfaces/captain-vetoes.yml",
    "shared/interfaces/captain-decisions.md",
    "shared/interfaces/captain-patterns.md",
    "shared/interfaces/captain-intents.md",
    # Phase 3 (2026-07-17): per-label digests + session markers written by the
    # weekly governance review (cabinet/scripts/governance-review.py) — the
    # actual label journal HP-3's re-count proves append-only. Content-free
    # lines: trial ids, event ids/hashes, verdicts, channel attestation;
    # never note text.
    "shared/interfaces/governance-labels.jsonl",
)


def _load_config(repo_root: Path) -> dict:
    """Instance bindings; absent/unparseable config = all surfaces skipped."""
    path = repo_root / "instance" / "config" / "evidence-anchor.yml"
    if not path.is_file():
        return {}
    try:
        import yaml  # local: keep the job alive even if PyYAML is missing

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001 — a broken config must not kill anchoring
        print(f"evidence-anchor: WARN unreadable instance config ({exc}); "
              "external surfaces skipped", file=sys.stderr)
        return {}


def _resolve_dir(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(os.path.expandvars(str(value))).expanduser()


def _label_files(repo_root: Path, config: dict) -> dict[str, Path]:
    raw = config.get("captain_label_files")
    names = [str(item) for item in raw] if isinstance(raw, list) else list(DEFAULT_LABEL_FILES)
    resolved: dict[str, Path] = {}
    for item in names:
        path = Path(os.path.expandvars(item)).expanduser()
        if not path.is_absolute():
            path = repo_root / path
        resolved[path.name] = path
    return resolved


def _event_log_dir() -> Path:
    """Mirror framework/events/emitter.py + fidelity/consequence.py exactly:
    the digest must checksum the SAME files those emitters write."""
    explicit = os.environ.get("CABINET_EVENT_LOG_DIR")
    if explicit:
        return Path(explicit).expanduser()
    return Path(os.path.expanduser("~/Library/Application Support/cabinet/events"))


def _trigger_archive_dir() -> Path:
    """Mirror cabinet/scripts/exhaust-archive.py:archive_dir() exactly."""
    env = os.environ.get("CABINET_EXHAUST_ARCHIVE_DIR")
    base = Path(env).expanduser() if env else Path.home() / ".cabinet" / "archive"
    return base / "triggers"


def _last_record(anchor_file: Path) -> dict | None:
    """Last valid JSON object line of the exported anchor journal."""
    records = _all_records(anchor_file)
    return records[-1] if records else None


def _all_records(anchor_file: Path) -> list[dict]:
    """EVERY valid JSON object line of the exported anchor journal, oldest
    first — the full history the HP-3 label re-count verifies against
    (--check needs only the last record; the append-only proof needs all)."""
    try:
        if anchor_file.is_symlink() or not anchor_file.is_file():
            return []
        lines = anchor_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: list[dict] = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            value = json.loads(raw)
        except ValueError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _git(repo_dir: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo_dir), *argv],
        capture_output=True, text=True, timeout=60, check=False,
    )


def _export_to_repo(anchor_dir: Path, record: dict, *, git_commit: bool, run_date: str) -> dict:
    """Append one canonical JSON line and (best-effort) commit ONLY that file.
    The write is the durable part; a git failure degrades loud, not fatal."""
    anchor_dir.mkdir(parents=True, exist_ok=True)
    anchor_file = anchor_dir / ANCHOR_FILE_NAME
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    with open(anchor_file, "a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
    status = {"file": str(anchor_file), "committed": False}
    if not git_commit:
        return status
    try:
        inside = _git(anchor_dir, "rev-parse", "--is-inside-work-tree")
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            print("evidence-anchor: WARN anchor_dir is not inside a git work "
                  "tree; wrote the file without committing", file=sys.stderr)
            return status
        _git(anchor_dir, "add", "--", str(anchor_file))
        digest = str(record.get("record_digest") or "")[:12]
        commit = _git(
            anchor_dir, "commit",
            "-m", f"evidence-anchor: {run_date} {digest}",
            "--", str(anchor_file),
        )
        status["committed"] = commit.returncode == 0
        if commit.returncode != 0:
            print(f"evidence-anchor: WARN anchor commit failed: "
                  f"{(commit.stderr or commit.stdout).strip()[:200]}", file=sys.stderr)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"evidence-anchor: WARN anchor commit failed: {exc}", file=sys.stderr)
    return status


def _send_receipt(text: str) -> str:
    """Ride the ONE sanctioned Telegram door. Credless-safe: presence-check
    the channel's own env names first (values never printed), so an
    unconfigured deployment skips without a network attempt."""
    has_token = bool(os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_COS_TOKEN"))
    has_captain = bool(os.environ.get("CAPTAIN_TELEGRAM_ID"))
    if not has_token or not has_captain:
        return "skipped-unconfigured"
    try:
        from framework.frontdoor import channel

        response = channel.send(text)
    except Exception as exc:  # noqa: BLE001 — the receipt must never kill the anchor run
        print(f"evidence-anchor: WARN telegram receipt failed: {exc}", file=sys.stderr)
        return "failed"
    if isinstance(response, dict):
        if response.get("sent"):
            return "sent"
        return str(response.get("status") or "failed")
    return "failed"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evidence-anchor")
    parser.add_argument("--store", type=Path, default=None,
                        help="Evidence store root (default instance/evidence/v1)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Collect + check only; no append, export, or send")
    parser.add_argument("--json", action="store_true", help="Print the full summary as JSON")
    parser.add_argument("--check", nargs="?", const="", metavar="FILE", default=None,
                        help="Check-only: verify the live store against the last "
                             "record in FILE (default: the configured anchor file)")
    parser.add_argument("--recount-labels", nargs="?", const="", metavar="FILE",
                        default=None,
                        help="HP-3 re-count: prove the Captain label journal "
                             "append-only against the FULL anchor history in "
                             "FILE (default: the configured anchor file) and "
                             "cross-join it with the store. Read-only; exit 2 "
                             "on findings. Unused = the run is unchanged.")
    args = parser.parse_args(argv)

    repo_root = _REPO_ROOT
    config = _load_config(repo_root)
    store = args.store or (repo_root / "instance" / "evidence" / "v1")
    anchor_dir = _resolve_dir(config.get("anchor_dir"))
    labels = _label_files(repo_root, config)
    now = datetime.now(timezone.utc)
    run_date = now.strftime("%Y-%m-%d")
    # Digest the COMPLETED day (yesterday UTC): its files no longer grow, so
    # the recorded checksums are final and any later edit is tamper.
    ledger_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    if args.recount_labels is not None:
        source = Path(args.recount_labels) if args.recount_labels else (
            anchor_dir / ANCHOR_FILE_NAME if anchor_dir else None
        )
        records = _all_records(source) if source else []
        journal = labels.get(LABELS_JOURNAL_BASENAME)
        result = recount_labels(journal, records, store_root=store)
        if source is None:
            result["notes"] = list(result.get("notes") or []) + [
                "anchor_history_unconfigured"]
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["ok"] else 2

    if args.check is not None:
        source = Path(args.check) if args.check else (
            anchor_dir / ANCHOR_FILE_NAME if anchor_dir else None
        )
        previous = _last_record(source) if source else None
        result = check_anchor(store, previous)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["ok"] else 2

    summary: dict = {
        "run_date": run_date,
        "ledger_date": ledger_date,
        "store_present": Path(store).is_dir(),
        "digest_event": "skipped",
        "exported": [],
        "skipped": [],
        "findings": [],
        "telegram": "skipped",
    }

    # 1) Digest-anchor trial FIRST, so today's export covers its fresh tip.
    exit_code = 0
    if not summary["store_present"]:
        summary["digest_event"] = "skipped-no-store"
    elif args.dry_run:
        summary["digest_event"] = "skipped-dry-run"
    else:
        event_dir = _event_log_dir()
        detail = build_digest_detail(
            ledger_date=ledger_date,
            org_events_file=event_dir / f"events-{ledger_date}.jsonl",
            consequence_file=event_dir / f"consequence-events-{ledger_date}.jsonl",
            trigger_archive_dir=_trigger_archive_dir(),
        )
        try:
            from framework.evidence_anchor import append_digest_trial

            append_digest_trial(store, detail, run_date=run_date)
            summary["digest_event"] = digest_trial_id(run_date)
        except Exception as exc:  # noqa: BLE001 — keep anchoring even when the store is wedged
            summary["digest_event"] = f"failed:{exc}"
            print(f"evidence-anchor: WARN digest-anchor append failed: {exc}",
                  file=sys.stderr)
            exit_code = 1

    # 2) Collect, 3) check against the last exported record.
    record = collect_anchor(store, label_files=labels)
    previous = _last_record(anchor_dir / ANCHOR_FILE_NAME) if anchor_dir else None
    check = check_anchor(store, previous, current=record)
    notes = informational_changes(previous, record)
    summary["findings"] = check["findings"]
    summary["record_digest"] = record["record_digest"]

    # 4) Export both surfaces (each credless-safe).
    if args.dry_run:
        summary["skipped"] = ["meta-repo (dry-run)", "telegram (dry-run)"]
    else:
        if anchor_dir is None:
            summary["skipped"].append("meta-repo (anchor_dir unset)")
        else:
            export = _export_to_repo(
                anchor_dir, record,
                git_commit=bool(config.get("git_commit", True)),
                run_date=run_date,
            )
            summary["exported"].append(
                "meta-repo" + ("" if export["committed"] else " (uncommitted)")
            )
        if not config.get("telegram", True):
            summary["skipped"].append("telegram (disabled)")
        else:
            text = receipt_text(
                record, check,
                run_date=run_date,
                digest_event=str(summary["digest_event"]),
                exported=summary["exported"],
                skipped=summary["skipped"],
                notes=notes,
            )
            summary["telegram"] = _send_receipt(text)
            if summary["telegram"] not in {"sent"}:
                summary["skipped"].append(f"telegram ({summary['telegram']})")

    if check["findings"]:
        kinds = ", ".join(sorted({f["kind"] for f in check["findings"]}))
        print(f"evidence-anchor: FATAL integrity finding(s) vs last anchor: {kinds}",
              file=sys.stderr)
        exit_code = 2

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    else:
        print(
            f"evidence-anchor: date={run_date} trials={len(record['trials'])} "
            f"digest_event={summary['digest_event']} findings={len(check['findings'])} "
            f"exported={','.join(summary['exported']) or 'none'} "
            f"telegram={summary['telegram']}"
        )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
