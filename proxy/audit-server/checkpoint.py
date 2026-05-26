"""
proxy/audit-server/checkpoint.py — Spec 052 WORM off-box checkpoint (Phase 1, UNSIGNED). CTO #4/#7.

WHY: the per-entry hash-chain (hashchain.py) is tamper-EVIDENT, but only against an attacker who
cannot rewrite the whole chain consistently. A ROOT-level attacker on the Hetzner box CAN re-chain
the SSOT and recompute every entry_hash, leaving no trace. The defense is to publish the latest
per-cabinet entry_hash OFF the box, to sinks the box's root cannot retroactively alter:
  (a) a publicly-readable checkpoint file served at refslund.ai/audit-checkpoints, and
  (b) an append-only public Git mirror (refslund-cabinet-checkpoints) whose immutable commit
      history is the evidential anchor.
A customer/auditor downloads their log, recomputes the chain in the browser (AC #9), and matches
the recomputed latest entry_hash against the published checkpoint. Mismatch => tampering/corruption.

PHASE 1 (this file): UNSIGNED. The daily 00:05 UTC job emits checkpoints + commits the Git mirror
WITHOUT PGP signing — integrity is already independently verifiable via the published hashes + the
Git history's own immutability. PHASE 2 adds Captain PGP co-signing via an OFFLINE hardware token
(the box NEVER holds the Captain key — compromise risk). CTO #7.

SCOPE (PR-1): this module is the emit LOGIC + CLI (`python checkpoint.py`). The daily cron, the
served Caddy route, and the `git push` to the public remote are deploy-wired separately (provision.sh
/ Caddyfile / compose, PR-2). Phase-1 commits to the LOCAL mirror working tree; if the mirror repo
is not yet initialized the commit step is a logged no-op (the served file is still written), so the
logic is testable + deploy-independent. Mirrors the #192 logic/deploy split.

FAIL-SAFE: a broken or unreadable single-cabinet chain never aborts the run — it is recorded with
chain_valid=false (which is itself the alarm) and the sweep continues. Reuses the shared
validator.is_valid_cabinet_id (#237) so a non-slug SSOT filename can never build an escaped path.

PRIVACY (AC #13): the public sinks are keyed by an OPAQUE per-cabinet id (minted at FW-098 install,
read from a slug->opaque-id map the install writes to the data dir), NEVER the human slug — keying
per-slug would publish refslund's enumerable customer list + per-cabinet volume to a PERMANENT
IMMUTABLE public sink (Art 5(1)(c) minimization; a sole-trader slug is personal data). FAIL-CLOSED:
a slug with no map entry is SKIPPED — never publish a bare slug. The internal SSOT stays slug-named.
"""
from __future__ import annotations

import errno
import fcntl
import json
import logging
import os
import pathlib
import subprocess
from datetime import datetime, timezone
from typing import Any

import hashchain
from validator import is_valid_cabinet_id

logger = logging.getLogger(__name__)

# SSOT root — same env the audit-server/ingest read (PARENT of audit/ + proxy-audit/).
_AUDIT_LOG_ROOT = pathlib.Path(
    os.environ.get(
        "LITELLM_AUDIT_LOG_ROOT",
        os.path.join(os.path.dirname(__file__), "..", "logs"),
    )
)
_AUDIT_DIR = _AUDIT_LOG_ROOT / "audit"

# Public served snapshot dir (Caddy file_server -> refslund.ai/audit-checkpoints). Contains ONLY
# the .json snapshots — NEVER the Git repo (so Caddy can never serve a .git/). Kept SEPARATE from
# the mirror dir for exactly that reason.
_CHECKPOINT_PUBLIC_DIR = pathlib.Path(
    os.environ.get("AUDIT_CHECKPOINT_DIR", str(_AUDIT_LOG_ROOT / "checkpoints"))
)
# Append-only Git mirror working tree (NOT served). Deploy (PR-2) `git init`s this + sets the
# public remote + pushes; until then the commit step is a logged no-op.
_CHECKPOINT_GIT_DIR = pathlib.Path(
    os.environ.get("AUDIT_CHECKPOINT_GIT_DIR", str(_AUDIT_LOG_ROOT.parent / "checkpoints-git"))
)

# Unsigned-but-attributable committer identity, set inline so the run does NOT depend on the
# container having any global git config (Phase 2 replaces this with offline PGP co-signing).
_GIT_COMMITTER = ("refslund-checkpoint", "checkpoint@refslund.ai")

# Single-run lock — NON-served (under the root, not the served checkpoints/ subdir) so a slow run
# and the next daily cron tick can never overlap + interleave the append-only ledger writes.
_LOCKFILE = _AUDIT_LOG_ROOT / ".checkpoint.lock"

# Slug -> opaque-id map (AC #13): the FW-098 install writes this JSON into the data dir; checkpoint
# keys ALL public output by the opaque id, NEVER the slug. Missing / unreadable / malformed -> {}
# so every cabinet fail-closed-skips (never publish a bare slug). NON-served (under the root).
_ID_MAP_FILE = pathlib.Path(
    os.environ.get("AUDIT_CHECKPOINT_ID_MAP", str(_AUDIT_LOG_ROOT / "cabinet-id-map.json"))
)

# Non-served scratch dir for atomic-write temp files — kept OUT of the served snapshot dir so a
# transient .tmp can never be served, but as a SIBLING of it (the served dir's parent) so it is
# GUARANTEED on the same filesystem -> os.replace stays atomic even if AUDIT_CHECKPOINT_DIR is
# mounted on its own volume (PR-2 deploy). Derived from the served dir, not the SSOT root.
_SCRATCH_DIR = _CHECKPOINT_PUBLIC_DIR.parent / ".checkpoint-scratch"


def _acquire_lock():
    """Non-blocking exclusive lock; return the open handle (held until closed), or None if another
    run already holds it (in which case this run is skipped — no overlapping emit)."""
    try:
        _AUDIT_LOG_ROOT.mkdir(parents=True, exist_ok=True)
        fh = open(_LOCKFILE, "w")
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fh
    except (OSError, BlockingIOError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_id_map() -> dict[str, str]:
    """Load the slug->opaque-id map the FW-098 install writes (AC #13). Missing / not-an-object /
    unreadable -> {} so EVERY cabinet fail-closed-skips (never publish a bare slug). Never raises."""
    try:
        if not _ID_MAP_FILE.exists():
            logger.warning("checkpoint: id-map %s not found — all cabinets fail-closed-skipped "
                           "(no public output until the install writes the map)", _ID_MAP_FILE)
            return {}
        data = json.loads(_ID_MAP_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            logger.warning("checkpoint: id-map %s is not a JSON object — fail-closed empty", _ID_MAP_FILE)
            return {}
        return {str(k): str(v) for k, v in data.items()}
    except Exception as exc:  # noqa: BLE001 — any map error fails closed (no publish), never crashes
        logger.warning("checkpoint: id-map %s unreadable (%s) — fail-closed empty", _ID_MAP_FILE, exc)
        return {}


def _latest_hash_and_count(slug: str) -> tuple[str, int]:
    """One pass over the SSOT: return (latest entry_hash, entry_count). ('', 0) if no/empty log.

    Counts only lines that carry an integrity.entry_hash (matches what the chain actually links),
    so a trailing blank line or a malformed record does not inflate the count or shift the hash.
    """
    path = _AUDIT_DIR / f"{slug}.jsonl"
    if not path.exists():
        return "", 0
    last = ""
    count = 0
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                h = entry.get("integrity", {}).get("entry_hash")
                if h:
                    last = h
                    count += 1
    except Exception as exc:  # noqa: BLE001 — never abort the sweep on one bad file
        logger.warning("checkpoint: error reading SSOT for %s: %s", slug, exc)
    return last, count


def build_checkpoint(slug: str, id_map: dict[str, str]) -> dict[str, Any] | None:
    """Build the PUBLIC checkpoint record for one cabinet, keyed by its OPAQUE id (AC #13), or None
    if the slug is invalid / unmapped / its opaque id is malformed / it has no entries. The returned
    record carries `cabinet_public_id` ONLY — never the slug — so nothing published leaks the slug."""
    if not is_valid_cabinet_id(slug):
        logger.warning("checkpoint: skipping non-slug cabinet id %r", slug)
        return None
    public_id = id_map.get(slug)
    if not public_id:
        logger.warning("checkpoint: no opaque-id mapping for cabinet %r — SKIPPED "
                       "(fail-closed AC #13; never publish a bare slug)", slug)
        return None
    if not is_valid_cabinet_id(public_id):
        # a poisoned / malformed map entry must never build an escaped public path
        logger.warning("checkpoint: opaque-id %r for cabinet %r is not slug-shaped — SKIPPED "
                       "(fail-closed)", public_id, slug)
        return None
    if public_id == slug:
        # the map MUST anonymize: a public_id identical to the slug is a non-anonymizing (or
        # misconfigured) entry — publishing it would leak the slug to the PERMANENT public sink.
        # The invariant must hold even if the map is wrong, so skip fail-closed.
        logger.warning("checkpoint: opaque-id == slug for cabinet %r — SKIPPED (non-anonymizing "
                       "map entry; fail-closed AC #13)", slug)
        return None
    latest, count = _latest_hash_and_count(slug)
    if count == 0:
        return None  # nothing to anchor yet
    chain_ok, bad_idx = hashchain.verify(slug)
    if not chain_ok:
        logger.error("checkpoint: chain INVALID for %s (first bad index=%s)", slug, bad_idx)
    return {
        "cabinet_public_id": public_id,
        "latest_entry_hash": latest,
        "entry_count": count,
        "chain_valid": bool(chain_ok),
        "chain_bad_index": bad_idx,
        "checkpoint_ts": _utc_now(),
        "phase": 1,
        "signed": False,
    }


def emit_all() -> dict[str, Any]:
    """Sweep every cabinet SSOT -> build checkpoints -> write the public snapshot + append the Git
    mirror. Returns a summary {checkpoint_ts, cabinets:[slug], broken:[slug]}."""
    if not _AUDIT_DIR.exists():
        logger.info("checkpoint: audit dir not found at %s — nothing to checkpoint", _AUDIT_DIR)
        return {"checkpoint_ts": _utc_now(), "published": [], "broken": []}

    lock = _acquire_lock()
    if lock is None:
        logger.warning("checkpoint: another emit run holds the lock — skipping this tick")
        return {"checkpoint_ts": _utc_now(), "published": [], "broken": [], "skipped": "locked"}
    try:
        id_map = _load_id_map()
        built: list[tuple[str, dict[str, Any]]] = []  # (slug, opaque-keyed public record) pairs
        for jsonl in sorted(_AUDIT_DIR.glob("*.jsonl")):
            slug = jsonl.stem
            cp = build_checkpoint(slug, id_map)
            if cp is not None:
                built.append((slug, cp))

        # Collision guard (AC #13 defense): the install MUST mint UNIQUE opaque ids. If it ever
        # mis-mints a duplicate, two cabinets would clobber one served file + interleave one
        # APPEND-ONLY ledger — silent data loss + a false tamper-alarm PERMANENTLY in the immutable
        # WORM anchor. Detect a duplicate public_id across this sweep and fail-closed-skip ALL
        # colliding cabinets (checkpoint is the last line before the immutable sink — never clobber).
        seen: set[str] = set()
        dup_ids: set[str] = set()
        for _slug, cp in built:
            pid = cp["cabinet_public_id"]
            (dup_ids if pid in seen else seen).add(pid)
        if dup_ids:
            logger.error("checkpoint: DUPLICATE opaque-id(s) %s — skipping ALL colliding cabinets "
                         "(install must mint unique ids; never clobber the immutable anchor)",
                         sorted(dup_ids))
            built = [(s, cp) for s, cp in built if cp["cabinet_public_id"] not in dup_ids]

        cabinets = [cp for _s, cp in built]                       # PUBLIC records -> the manifest
        published = [s for s, _cp in built]                       # internal: published slugs (log)
        broken = [s for s, cp in built if not cp["chain_valid"]]  # internal: broken-chain slugs

        ts = _utc_now()
        manifest = {"checkpoint_ts": ts, "phase": 1, "signed": False, "cabinets": cabinets}
        _write_public_snapshot(manifest)
        _commit_git_mirror(manifest, ts)
    finally:
        lock.close()  # releases the flock

    if broken:
        logger.error("checkpoint: %d BROKEN chain(s) at checkpoint: %s", len(broken), broken)
    logger.info("checkpoint: published %d cabinet checkpoint(s) at %s", len(published), ts)
    return {"checkpoint_ts": ts, "published": published, "broken": broken}


def _write_public_snapshot(manifest: dict[str, Any]) -> None:
    """Write latest.json (full manifest) + one <slug>.json per cabinet to the served dir.

    Atomic per-file (write temp + os.replace) so a customer fetch never reads a half-written file.
    """
    _CHECKPOINT_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_write(_CHECKPOINT_PUBLIC_DIR / "latest.json", json.dumps(manifest, indent=2, sort_keys=True))
    for cp in manifest["cabinets"]:
        _atomic_write(
            _CHECKPOINT_PUBLIC_DIR / f"{cp['cabinet_public_id']}.json",
            json.dumps(cp, indent=2, sort_keys=True),
        )


def _atomic_write(path: pathlib.Path, text: str) -> None:
    # Write the temp in a NON-served scratch dir (not the served snapshot dir) so a transient .tmp
    # can never be served; os.replace from the same filesystem stays atomic (review minor b).
    _SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _SCRATCH_DIR / (path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        try:
            os.replace(tmp, path)
        except OSError as exc:
            if exc.errno == errno.EXDEV:
                # scratch + served on DIFFERENT filesystems -> os.replace is not atomic across
                # devices. Fail LOUD (not a silent torn/partial write): the deploy MUST keep
                # AUDIT_CHECKPOINT_DIR on the same fs as its parent (where the scratch sibling
                # lives). Re-raise so the run aborts publishing NOTHING rather than a torn file
                # (CPO PR-2 item 1). The checkpoint-loop logs it + retries next cycle.
                logger.error("checkpoint: scratch %s and served dir %s are on DIFFERENT filesystems "
                             "— os.replace cannot be atomic; fix the deploy so AUDIT_CHECKPOINT_DIR "
                             "shares a filesystem with its parent. NOT writing %s.",
                             _SCRATCH_DIR, path.parent, path.name)
            raise
    finally:
        # After a successful os.replace the tmp is already renamed away, so unlink is a no-op.
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _commit_git_mirror(manifest: dict[str, Any], ts: str) -> None:
    """Append each cabinet's checkpoint to its APPEND-ONLY ledger in the Git mirror, then commit
    (UNSIGNED, Phase 1). No-op (logged) if the mirror is not yet a git repo — deploy wires that +
    the `git push` to the public refslund-cabinet-checkpoints remote (PR-2)."""
    gitdir = _CHECKPOINT_GIT_DIR
    if not (gitdir / ".git").is_dir():
        logger.info(
            "checkpoint: git mirror not initialized at %s — snapshot written, commit skipped "
            "(deploy initializes the repo + remote, PR-2)",
            gitdir,
        )
        return
    name, email = _GIT_COMMITTER
    base = ["git", "-C", str(gitdir)]
    # Discard any uncommitted tracked changes from a prior ABORTED run BEFORE appending, so a
    # killed-before-commit run cannot carry its ledger append forward into a duplicate line. The
    # mirror is fully derived from the SSOT, so a reset never loses data (this run re-anchors the
    # current — at-or-newer — tail). Best-effort: a reset failure (e.g. fresh repo, no HEAD yet)
    # must not block the append or the snapshot.
    try:
        subprocess.run([*base, "reset", "--hard", "HEAD"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        pass
    for cp in manifest["cabinets"]:
        ledger = gitdir / f"{cp['cabinet_public_id']}.checkpoints.jsonl"
        with ledger.open("a", encoding="utf-8") as fh:  # APPEND-ONLY: never rewrite a line
            fh.write(json.dumps(cp, sort_keys=True) + "\n")
    try:
        subprocess.run([*base, "add", "-A"], check=True, capture_output=True)
        # --no-gpg-sign is explicit: Phase 1 is intentionally UNSIGNED (CTO #7).
        subprocess.run(
            [
                *base,
                "-c", f"user.name={name}",
                "-c", f"user.email={email}",
                "commit", "--no-gpg-sign",
                "-m", f"checkpoint {ts} ({len(manifest['cabinets'])} cabinet(s))",
            ],
            check=True,
            capture_output=True,
        )
        logger.info("checkpoint: committed git mirror at %s", gitdir)
    except subprocess.CalledProcessError as exc:
        # An empty commit (nothing changed since last run) exits non-zero with the "nothing to
        # commit" notice on STDOUT (not stderr) — inspect BOTH streams so a benign no-op is never
        # misclassified as a failure (which would cause alarm-fatigue + mask a real failure).
        out = ((exc.stdout or b"") + b"\n" + (exc.stderr or b"")).decode("utf-8", "replace")
        if "nothing to commit" in out or "nothing added" in out:
            logger.info("checkpoint: git mirror unchanged since last checkpoint (no commit)")
        else:
            logger.warning("checkpoint: git mirror commit failed (non-fatal): %s", out.strip())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(emit_all(), indent=2))
