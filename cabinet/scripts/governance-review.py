#!/usr/bin/env python3.12
"""governance-review.py — the Captain's weekly governance review (RAMP-2).

The evidence design's Phase 3 named deliverable (whole-cabinet evidence
design of record 2026-07-16 §3 Phase 3 item 3; onboarding plan 2026-07-14
RAMP-2): one TTY command, five stations with printed time budgets — posture
tile · cost vs caps · graduation digest + pending petitions · receipts
sample · LABELING — that turns onboarding into governance and starts
accruing the Captain-verdict ground truth the Phase-4 machine judge is
calibrated against.

WHAT THE LABELING STATION DOES: samples VERIFIED evidence trials (stratified
toward the weakest evidence basis and the high-risk tail), presents each
trial's redacted officer projection with every machine-verdict event HIDDEN
(blind labeling — agreement is measured, never manufactured), and lands the
Captain's right/wrong/unclear verdict as verification(+outcome) events on
THE SAME TRIAL via the germline recorder API, so "was it right" finally
lives next to "what happened". Each landed label also appends one
CONTENT-FREE digest line to the Captain-owned labels journal
(shared/interfaces/governance-labels.jsonl), which rides the daily external
evidence anchor (cabinet/scripts/evidence-anchor.py DEFAULT_LABEL_FILES) —
HP-3's external leg: label digests land off-store, and the anchor re-count
verb (evidence-anchor.py --recount-labels) proves the journal append-only
against the anchored history and cross-joins it with the store (design §2.3).

PHASE-4 JOIN CONTRACT (why the label events look the way they do): the
machine leg (undo-sweep reconciler) lands on the trial named by the journal
row's ``evidence_trial_id`` with ``detail.source == "verdict_judge"``;
Captain labels land on that SAME trial with ``actor.kind == "captain"``,
``detail.source == "verdict_human"``, ``detail.action ==
"governance_review_label"``, ``detail.result_code`` in confirmed|wrong
(scoreable; ``unclear`` is recorded but never scoreable), the evidence
BASIS AT LABEL TIME, and ``detail.jid`` + ``links=["undo-journal:<jid>"]``
for the consequence-ledger join. judge_calibration's exact polarity, reused.

ANTI-FORGERY STANCE (inherited from label-fidelity-cases.py, plus the
evidence plane's own token):
  * Captain capability token REQUIRED for EVERY mode, dry-run included —
    the EXISTING store-bound token (HMAC(store signing key,
    framework.evidence.__main__.CAPTAIN_TOKEN_PURPOSE)), minted by
    ``python3.12 -m framework.evidence grant-token``, presented via
    --captain-token-file or $CABINET_CAPTAIN_TOKEN_FILE. Never a new auth
    scheme. Without a valid token this CLI refuses (exit 3) BEFORE touching
    the store: the no-token path provably mutates nothing.
  * Interactive labeling REFUSES a non-TTY stdin (exit 2): no cron, agent,
    or pipe can mint verdict_human events through it. There is deliberately
    NO services.yml row for this script — no machine can schedule a review.
  * Hard per-session label cap: ``MAX_LABELS_PER_SESSION`` is a CODE
    CONSTANT, not a flag (a bar someone can lower from argv is not a bar;
    design §2.5 B4 — capped labeling sessions, quality over coverage).
  * Machine verdicts are hidden from every presentation (anti-anchoring);
    sampling is stratified-random with a full presentation shuffle, never
    "suspected disagreements only"; skip/quit write nothing.

FAIL-CLOSED DISPLAY: every trial is verified (framework.evidence.verifier
.verify_trial) immediately before presentation; a failing trial renders as
an explicit UNVERIFIED line (trial id + error codes, ZERO content) and is
excluded from labeling — labels are the ground truth the whole calibration
tower rests on, and minting them off unverifiable bytes poisons the well.

OFFICER POSTURE (documented, structural): the officer hook layer already
blocks interpreter access to the recorder modules and raw store paths, and
the only officer evidence read stays cabinet/scripts/evidence-read.sh. This
script is additionally unusable from officer context because (a) it demands
the Captain capability token, which officers cannot mint (grant-token and
the signing key are both behind the same hook screens) and (b) labeling
demands a live TTY. Honest limit (design §2.2 R2 / HP-3): every label now
carries a channel-provenance attestation (detail.label_channel — the TTY
path records "captain-token+tty"; "telegram-captain-dm" is reserved for a
future Captain-DM writer gated on the platform.yml captain_telegram_chat_id
allowlist), and calibration pairs ONLY attested labels. This is
tamper-EVIDENT, not tamper-proof: until HP-1's key isolation a same-OS-user
process that can read the signing key can derive the token and forge the
channel field along with the events themselves, and root can forge
everything. The external anchor re-count (evidence-anchor.py
--recount-labels) is the after-the-fact detection leg.

Read-only everywhere EXCEPT the designed Captain-token label write (the
recorder append) and its two Captain-owned exports (labels journal +
session transcript, both OUTSIDE the store). The verifier's anti-rollback
watermark advance on clean verifies is the same sanctioned side effect as
``python3.12 -m framework.evidence verify`` — and even that never runs on
the no-token or --dry-run paths.

Usage:
  python3.12 cabinet/scripts/governance-review.py --dry-run     # inspect plan
  python3.12 cabinet/scripts/governance-review.py               # the ritual
  python3.12 cabinet/scripts/governance-review.py --skip-stations --seed 7

Exit codes: 0 ok (labels landed / dry-run / nothing to review);
            1 labels landed but a Captain-owned export degraded (LOUD);
            2 refused (non-TTY labeling / bad invocation);
            3 Captain-token or evidence-plane typed refusal.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Captain-side, import-only reuse of the germline evidence plane. The token
# mechanism, recorder API, and verifier are NEVER reimplemented here — no
# new auth scheme, no second writer, no parallel verifier (design §2.1 #5).
from framework.evidence import __main__ as evidence_cli  # noqa: E402
from framework.evidence import verifier  # noqa: E402
from framework.evidence.lifecycle import valid_id_or_none  # noqa: E402
from framework.evidence.recorder import (  # noqa: E402
    EvidenceError,
    EvidenceRecorder,
)

# --- constants (code, not flags) ---------------------------------------------------

# RAMP-2 / design §2.5 B4: the hard per-session label cap. A bar someone can
# lower (or raise) from argv is not a bar — pinned by test_governance_review.
MAX_LABELS_PER_SESSION = 8

# Bound on how many trial dirs one session will raw-scan for candidates
# (most-recent first). A perf knob, not a safety bar — the label cap above
# is the bar. Overridable via --scan-cap.
SCAN_CAP_DEFAULT = 200

# The stable label verb marker Phase 4 joins on (detail.action).
LABEL_ACTION = "governance_review_label"
LABEL_COMPONENT = {"name": "governance-review", "version": "1+evidence-p3"}
# Fixed actor slug: recorder ids must match the evidence id alphabet (a
# display name with spaces fails _validate_id) and authenticated provenance
# comes from the token + anchor, never from the asserted string.
LABEL_ACTOR = {"kind": "captain", "id": "captain"}

# Evidence-basis vocabulary (design §3 Phase 3 item 2 / B6), weakest first.
# Derivation is from raw event fields (see classify_trial):
#   self_asserted     producer said "succeeded"; no leg beyond the producer
#   persistence_only  the reconciler's ttl_ok — "artifact persisted, nobody
#                     complained" — a weak green rendered as exactly that
#   machine_labeled   an undo-sweep verdict_judge leg exists (registered
#                     producer-asserted per classification.py, but a real
#                     machine observation in substance)
#   human_verified    a Captain leg exists (actor.kind=captain or
#                     detail.source=verdict_human)
BASIS_ORDER = ("self_asserted", "persistence_only", "machine_labeled",
               "human_verified")
_BASIS_WEIGHT = {"self_asserted": 4, "persistence_only": 3,
                 "machine_labeled": 2, "human_verified": 1}

# High-risk tail markers, matched as substrings against detail.action /
# detail.lane / component names on the trial's own events. Deliberately a
# code constant (tested) — the risk stratum drives oversampling only, never
# any write decision.
HIGH_RISK_TOKENS = ("external", "send", "email", "message", "deploy", "push",
                    "purge", "delete", "secret", "billing", "payment",
                    "grant", "prod")

# Event fields that mark a MACHINE (or prior-human) verdict — hidden from
# every presentation (anti-anchoring; label-fidelity-cases mitigation #2).
_JUDGE_SOURCES = frozenset({"verdict_judge", "verdict_human"})
_JUDGE_ACTIONS = frozenset({"undo_sweep_reconcile", LABEL_ACTION})

# --- HP-3: label channel-provenance attestation (design §2.3, §2.8 B1) ------
# The attestation VOCABULARY is fixed here (code constants, never argv/env);
# the recordable facts are exactly the gates this CLI itself enforces:
#   captain-token+tty    the Captain capability token matched THIS store's
#                        signing key AND stdin was a live TTY — the two
#                        gates main() enforces before any label write.
#   telegram-captain-dm  RESERVED: no Captain-DM label writer exists yet
#                        (deliberately — this TTY CLI is the only label
#                        writer). attest_telegram_channel() below is the
#                        sanctioned resolver any future wiring must call;
#                        its allowlist config-of-record is
#                        instance/config/platform.yml captain_telegram_chat_id.
# The chat id itself is NEVER recorded — evidence detail, journal rows, and
# error text carry only the fixed vocabulary string (no-secrets-in-detail).
# The detail key stays UNREGISTERED in the germline classification registry:
# classify_detail_key() fail-closed-defaults it to producer_asserted, which
# is honest — registry promotion is a Captain ceremony line item.
# THREAT HONESTY: attestation here is tamper-EVIDENT, not tamper-proof. It
# stops nothing a same-OS-user forger can do until HP-1 (the token derives
# from the readable signing key; the store accepts direct appends), and root
# forges everything. What it buys TODAY: calibration fail-closed excludes
# unattested labels, and the anchor re-count proves the journal append-only
# after the fact.
LABEL_CHANNEL_KEY = "label_channel"    # store-event detail key (redaction-safe)
LABEL_CHANNEL_JOURNAL_KEY = "channel"  # journal digest-row mirror key
CHANNEL_TTY = "captain-token+tty"
CHANNEL_TELEGRAM = "telegram-captain-dm"
ATTESTED_LABEL_CHANNELS = frozenset({CHANNEL_TTY, CHANNEL_TELEGRAM})

_VERDICT_RESULT = {"right": "confirmed", "wrong": "wrong",
                   "unclear": "unclear"}
_VERDICT_VERIFICATION_STATUS = {"right": "verified", "wrong": "unverified",
                                "unclear": "skipped"}
_VERDICT_OUTCOME_STATUS = {"right": "succeeded", "wrong": "failed"}

_NOTE_CAP = 400

LABELS_JOURNAL_REL = "shared/interfaces/governance-labels.jsonl"
TRANSCRIPT_DIR_REL = "shared/interfaces/governance-reviews"

BANNER = f"""\
================================================================================
 governance-review — the Captain's weekly ritual (RAMP-2, evidence Phase 3)
--------------------------------------------------------------------------------
 * Requires YOUR capability token (the evidence store's captain token) for
   every mode. Writes NOTHING until you answer a trial; skip/quit never write.
 * Hard cap: {MAX_LABELS_PER_SESSION} labels per session (code constant — quality over coverage).
 * Trials are VERIFIED before you see them; anything unverifiable is shown as
   UNVERIFIED (id + error codes only) and cannot be labeled.
 * Machine verdicts on each trial are HIDDEN (you label blind; agreement is
   measured, never manufactured). Sampling leans toward the weakest evidence
   basis and the high-risk tail, then shuffles.
 * Your verdicts land as verification/outcome events on the SAME trial
   (actor captain, source verdict_human) + one content-free digest line in
   {LABELS_JOURNAL_REL} for the daily external anchor.
 * This supplies calibration DATA only. No gate arms itself here; machine
   judgment (Phase 4) and any auto tier remain separate Captain decisions.
================================================================================
"""

STATIONS = (
    ("1/5 POSTURE TILE", "~1 min"),
    ("2/5 COST VS CAPS", "~2 min"),
    ("3/5 GRADUATION DIGEST + PENDING PETITIONS", "~2 min"),
    ("4/5 RECEIPTS SAMPLE", "~2 min"),
    ("5/5 LABELING", "~3 min"),
)

PROMPT = ("verdict — was this the RIGHT thing done RIGHT?\n"
          "  [r]ight / [w]rong / [u]nclear / [s]kip / [q]uit > ")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ---------------------------------------------------------------------------
# Captain capability gate (reuses the evidence CLI's primitives verbatim)
# ---------------------------------------------------------------------------

def require_captain_token(store: Path, args: argparse.Namespace) -> None:
    """Fail closed unless the caller presents THIS store's Captain token.

    Same semantics as framework.evidence.__main__._require_captain_capability
    but the expected token is derived from the signing key via the verifier's
    side-effect-free loader instead of a constructed recorder, so the refused
    path provably never creates, heals, or otherwise touches the store."""
    path = evidence_cli._presented_token_path(args)
    if path is None:
        raise EvidenceError(
            "captain_capability_required",
            "This is a Captain-only ritual. Provide the Captain capability "
            "token file via --captain-token-file or "
            "CABINET_CAPTAIN_TOKEN_FILE (mint one with: python3.12 -m "
            "framework.evidence --store <store> grant-token --output <file>).",
        )
    presented = evidence_cli._read_captain_token(path)
    try:
        key = verifier._key(store)
    except ValueError as exc:
        raise EvidenceError(
            "captain_capability_unavailable",
            f"The evidence store signing key is unavailable ({exc}); "
            "cannot check the Captain capability token.",
        ) from exc
    expected = hmac.new(
        key, evidence_cli.CAPTAIN_TOKEN_PURPOSE.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(presented.encode("utf-8"),
                               expected.encode("utf-8")):
        raise EvidenceError(
            "captain_capability_invalid",
            "The presented Captain capability token does not authorize this "
            "evidence store.",
        )


# ---------------------------------------------------------------------------
# HP-3 label-channel attestation (fail-closed resolvers; no new CLI flags)
# ---------------------------------------------------------------------------

def attest_tty_channel(*, token_ok: bool, stdin_tty: bool) -> str:
    """The TTY channel attestation: BOTH gates this CLI enforces must have
    passed. Returns the vocabulary value; an unattestable context gets a
    typed refusal (fail-closed — it never reaches the label writer)."""
    if token_ok and stdin_tty:
        return CHANNEL_TTY
    raise EvidenceError(
        "label_channel_unattested",
        "Label channel unattestable: the Captain-token gate and a live TTY "
        "are both required for the TTY label channel.",
    )


def _configured_captain_chat_id(config_path: Path) -> Optional[int]:
    """The telegram allowlist: platform.yml ``captain_telegram_chat_id``,
    parsed strictly. None = unconfigured — absent/symlinked file,
    unparseable YAML, missing key, or a placeholder/zero value (the
    committed example ships "<YOUR-TELEGRAM-CHAT-ID>" and scrubbed
    instances ship a ten-zero placeholder; neither may ever attest)."""
    try:
        if config_path.is_symlink() or not config_path.is_file():
            return None
        import yaml  # lazy: this CLI must not hard-depend on PyYAML

        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — any trouble reads as unconfigured
        return None
    if not isinstance(data, dict):
        return None
    try:
        value = int(str(data.get("captain_telegram_chat_id")).strip())
    except (TypeError, ValueError):
        return None
    return value or None  # zero placeholders = unconfigured, never attested


def attest_telegram_channel(claimed_chat_id: Any,
                            config_path: Optional[Path] = None) -> str:
    """RESERVED channel resolver — no Captain-DM label writer exists yet
    (this TTY CLI stays the only writer); any future wiring MUST attest
    through here. Attests ONLY when the claimed sender id equals the
    configured ``captain_telegram_chat_id`` (instance/config/platform.yml,
    the allowlist config-of-record). Fail-closed dark default: an
    unconfigured allowlist refuses — a deployment without it cannot attest
    telegram while the TTY path keeps working. The chat id NEVER enters
    evidence detail, journal rows, or error text — the recorded value is
    CHANNEL_TELEGRAM only."""
    if config_path is None:
        config_path = _REPO_ROOT / "instance" / "config" / "platform.yml"
    configured = _configured_captain_chat_id(Path(config_path))
    if configured is None:
        raise EvidenceError(
            "label_channel_unconfigured",
            "Telegram label channel refused: no captain_telegram_chat_id "
            "allowlist is configured (platform.yml) — the TTY ritual "
            "remains the only label path.",
        )
    try:
        claimed = int(str(claimed_chat_id).strip())
    except (TypeError, ValueError):
        raise EvidenceError(
            "label_channel_unattested",
            "Telegram label channel refused: the claimed sender id is not "
            "an id.",
        ) from None
    if claimed != configured:
        raise EvidenceError(
            "label_channel_mismatch",
            "Telegram label channel refused: the sender is not the "
            "configured Captain chat.",
        )
    return CHANNEL_TELEGRAM


# ---------------------------------------------------------------------------
# candidate collection (raw, read-only — hints for sampling ONLY; the
# authoritative gate is verify-before-present)
# ---------------------------------------------------------------------------

def _read_raw_events(store: Path, trial_id: str) -> list[dict[str, Any]]:
    """Unverified raw rows (verifier _read_event_lines framing: b"\\n" only,
    corrupt lines skipped). Used for stratification hints and the blind
    filter; NEVER served as content — presentation happens only after
    verify_trial passes. The id is regex-validated before the one fixed
    ``trials/<id>/events.jsonl`` layout lookup; nothing else is path-joined."""
    if not verifier.TRIAL_ID_RE.fullmatch(trial_id):
        return []
    path = store / "trials" / trial_id / "events.jsonl"
    try:
        if path.is_symlink() or not path.is_file():
            return []
        raw = path.read_bytes()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in raw.split(b"\n"):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (UnicodeDecodeError, ValueError):
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def classify_trial(events: list[dict[str, Any]]) -> dict[str, Any]:
    """{basis, risk, jid, machine_event_ids, count} from raw event fields.

    Basis (weakest wins only when nothing stronger exists — see BASIS_ORDER
    docs above). Risk: "high" when any event's detail.action / detail.lane /
    component.name carries a HIGH_RISK_TOKENS substring. jid: the first
    id-alphabet-valid detail.jid (the consequence-ledger join key).
    machine_event_ids: every event carrying a judge verdict or a prior label
    — the blind filter's hide set."""
    saw_captain = False
    saw_machine = False
    saw_ttl = False
    saw_producer_claim = False
    risk = "normal"
    jid: Optional[str] = None
    machine_ids: set = set()
    for ev in events:
        if not isinstance(ev, dict):
            continue
        detail = ev.get("detail") if isinstance(ev.get("detail"), dict) else {}
        actor = ev.get("actor") if isinstance(ev.get("actor"), dict) else {}
        component = (ev.get("component")
                     if isinstance(ev.get("component"), dict) else {})
        phase = ev.get("phase")
        source = detail.get("source")
        action = str(detail.get("action") or "")
        if source in _JUDGE_SOURCES or action in _JUDGE_ACTIONS:
            if isinstance(ev.get("event_id"), str):
                machine_ids.add(ev["event_id"])
        if jid is None:
            jid = valid_id_or_none(str(detail.get("jid") or ""))
        haystack = " ".join((action, str(detail.get("lane") or ""),
                             str(component.get("name") or ""))).lower()
        if any(tok in haystack for tok in HIGH_RISK_TOKENS):
            risk = "high"
        if phase in ("verification", "outcome", "feedback"):
            if actor.get("kind") == "captain" or source == "verdict_human":
                saw_captain = True
            elif source == "verdict_judge":
                if detail.get("result_code") == "ttl_ok":
                    saw_ttl = True
                else:
                    saw_machine = True
            elif detail.get("result_code") == "ttl_ok":
                saw_ttl = True
            else:
                saw_producer_claim = True
        elif phase == "execution":
            saw_producer_claim = True
    if saw_captain:
        basis = "human_verified"
    elif saw_machine:
        basis = "machine_labeled"
    elif saw_ttl:
        basis = "persistence_only"
    else:
        basis = "self_asserted"
    del saw_producer_claim  # absence of every leg is still self_asserted
    return {"basis": basis, "risk": risk, "jid": jid,
            "machine_event_ids": machine_ids, "count": len(events)}


def enumerate_trials(store: Path, scan_cap: int) -> list[str]:
    """Most-recent trial dir names (regex-validated, symlinks skipped),
    bounded by scan_cap — verify_store's enumeration precedent."""
    root = store / "trials"
    if not root.is_dir():
        return []
    entries: list[tuple[float, str]] = []
    for path in root.iterdir():
        if path.is_symlink() or not path.is_dir():
            continue
        if not verifier.TRIAL_ID_RE.fullmatch(path.name):
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        entries.append((mtime, path.name))
    entries.sort(reverse=True)
    return [name for _, name in entries[:max(1, int(scan_cap))]]


def collect_candidates(store: Path, *, scan_cap: int,
                       relabel: bool) -> list[dict[str, Any]]:
    """Classified candidates for sampling. Trials that already carry a
    Captain leg (basis human_verified) are excluded unless --relabel — they
    are ground truth already; a re-label supersedes on the human side."""
    out: list[dict[str, Any]] = []
    for trial_id in enumerate_trials(store, scan_cap):
        events = _read_raw_events(store, trial_id)
        if not events:
            continue
        cand = classify_trial(events)
        cand["trial_id"] = trial_id
        if cand["basis"] == "human_verified" and not relabel:
            continue
        out.append(cand)
    return out


def stratified_sample(candidates: list[dict[str, Any]], n: int,
                      rng: random.Random) -> list[dict[str, Any]]:
    """Weakest-basis-weighted stratified sample with a high-risk tail bias.

    Strata are the (hidden-direction) evidence-basis classes; allocation is
    proportional to weight*size (largest remainder, >=1 per non-empty
    stratum) with _BASIS_WEIGHT leaning hard toward self_asserted /
    persistence_only. Within a stratum, high-risk candidates are drawn
    first. The final order is fully shuffled and hard-sliced to n, so
    presentation order reveals nothing and the cap is absolute."""
    if n <= 0:
        return []
    if n >= len(candidates):
        sample = list(candidates)
        rng.shuffle(sample)
        return sample
    strata: dict[str, list[dict[str, Any]]] = {}
    for cand in candidates:
        strata.setdefault(str(cand.get("basis")), []).append(cand)
    names = sorted(strata)  # deterministic under a fixed seed
    total_weight = sum(_BASIS_WEIGHT.get(name, 1) * len(strata[name])
                       for name in names)
    quotas: dict[str, int] = {}
    remainders: list[tuple[float, str]] = []
    used = 0
    for name in names:
        exact = n * (_BASIS_WEIGHT.get(name, 1) * len(strata[name])) / total_weight
        quota = max(1, int(exact))
        quota = min(quota, len(strata[name]))
        quotas[name] = quota
        used += quota
        remainders.append((exact - int(exact), name))
    remainders.sort(reverse=True)
    i = 0
    while used < n and i < len(remainders) * 2:
        name = remainders[i % len(remainders)][1]
        if quotas[name] < len(strata[name]):
            quotas[name] += 1
            used += 1
        i += 1
    while used > n:
        biggest = max(names, key=lambda s: quotas[s])
        if quotas[biggest] <= 1:
            break
        quotas[biggest] -= 1
        used -= 1
    sample: list[dict[str, Any]] = []
    for name in names:
        rows = strata[name]
        high = [r for r in rows if r.get("risk") == "high"]
        norm = [r for r in rows if r.get("risk") != "high"]
        rng.shuffle(high)
        rng.shuffle(norm)
        sample.extend((high + norm)[:quotas[name]])
    rng.shuffle(sample)
    return sample[:n]


# ---------------------------------------------------------------------------
# presentation (blind: machine verdicts hidden)
# ---------------------------------------------------------------------------

def present_trial(projection: dict[str, Any], cand: dict[str, Any]) -> str:
    """The trial as shown to the Captain: the redacted officer projection
    (the SAME view a Phase-4 machine judge would read — design A8) minus
    every machine-verdict event (anti-anchoring). The basis tag names the
    evidence STRENGTH class honestly (§2.5: weak signals rendered as exactly
    what they are) while every verdict DIRECTION stays hidden."""
    hidden = cand.get("machine_event_ids") or set()
    lines = [
        f"trial     : {cand.get('trial_id')}",
        f"basis     : {cand.get('basis')}   risk: {cand.get('risk')}   "
        f"jid: {cand.get('jid') or '-'}",
        f"boundary  : {projection.get('instruction_boundary')}",
    ]
    shown = 0
    hidden_count = 0
    for rec in projection.get("records") or []:
        if not isinstance(rec, dict):
            continue
        if rec.get("event_id") in hidden:
            hidden_count += 1
            continue
        detail = rec.get("detail") if isinstance(rec.get("detail"), dict) else {}
        bits = [f"#{rec.get('sequence')}",
                f"{rec.get('phase')}/{rec.get('status')}",
                str((rec.get("component") or {}).get("name") or "?")]
        if detail.get("action"):
            bits.append(f"action={detail['action']}")
        for key in ("result_code", "reason_code", "error_code", "verification"):
            if detail.get(key):
                bits.append(f"{key}={detail[key]}")
        if rec.get("redactions"):
            bits.append(f"redactions={len(rec['redactions'])}")
        lines.append("  " + "  ".join(bits))
        shown += 1
    lines.append(f"  ({shown} event(s) shown; {hidden_count} machine-verdict "
                 "event(s) HIDDEN — you label blind)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# the ONE designed write: Captain label events on the SAME trial
# ---------------------------------------------------------------------------

def write_label(recorder: EvidenceRecorder, trial_id: str, verdict: str,
                note: str, cand: dict[str, Any],
                session: str, *,
                channel: Optional[str] = None) -> list[dict[str, Any]]:
    """Append the Captain's verdict to the trial via the germline recorder.

    HP-3 fail-closed: ``channel`` must be an ATTESTED_LABEL_CHANNELS value
    (minted by attest_tty_channel / attest_telegram_channel — never a
    caller-invented string in spirit; the vocabulary set is the bar). An
    unattested context is REFUSED with a typed error BEFORE any store
    touch: a label without channel provenance is not calibration ground
    truth and must never exist. The value rides the signed event as
    ``detail.label_channel`` (hash-covered; NOT officer-projected —
    recorder.PROJECTION_ALLOWED_DETAIL is unchanged).

    right   -> verification/verified  + outcome/succeeded
    wrong   -> verification/unverified + outcome/failed
    unclear -> verification/skipped ONLY (no outcome is asserted; recorded,
               never scoreable — calibration pairs use confirmed|wrong)

    detail carries the Phase-4 join contract (action/source/result_code/
    basis/jid/session). Of those, exactly the two allow-listed keys surface
    in the officer projection (recorder.PROJECTION_ALLOWED_DETAIL admits
    ``action`` and ``result_code`` — a landed label is an ordinary record,
    not a secret); ``source``/``basis``/``jid``/``session``/``note`` are NOT
    allow-listed and stay redacted from every officer view (pinned by
    test_evidence_label_join.py). Raises on failure — the Captain is
    present, and a silently lost label corrupts the calibration floor (the
    RECEIPT-class never-raise stance is for absent humans, not this TTY)."""
    if channel not in ATTESTED_LABEL_CHANNELS:
        raise EvidenceError(
            "label_channel_unattested",
            "Label write refused: no attested channel provenance (HP-3 "
            "fail-closed — an unattested context never mints labels).",
        )
    if valid_id_or_none(trial_id) is None:
        raise EvidenceError("trial_id_invalid",
                            "That trial id is not labelable.")
    result_code = _VERDICT_RESULT[verdict]
    detail: dict[str, Any] = {
        "action": LABEL_ACTION,
        "source": "verdict_human",
        "result_code": result_code,
        "basis": cand.get("basis") or "self_asserted",
        "session": session,
        LABEL_CHANNEL_KEY: channel,
    }
    jid = valid_id_or_none(str(cand.get("jid") or ""))
    links: list[str] = []
    if jid:
        detail["jid"] = jid
        links.append("undo-journal:" + jid)
    if note:
        detail["note"] = note[:_NOTE_CAP]
    context = recorder.trace(trial_id, surface="cli")
    events = [recorder.append(
        context, phase="verification",
        status=_VERDICT_VERIFICATION_STATUS[verdict],
        actor=dict(LABEL_ACTOR), component=dict(LABEL_COMPONENT),
        detail=detail, links=links,
    )]
    if verdict in _VERDICT_OUTCOME_STATUS:
        events.append(recorder.append(
            context, phase="outcome",
            status=_VERDICT_OUTCOME_STATUS[verdict],
            actor=dict(LABEL_ACTOR), component=dict(LABEL_COMPONENT),
            detail=detail, links=links,
        ))
    return events


# ---------------------------------------------------------------------------
# Captain-owned exports (outside the store): labels journal + transcript
# ---------------------------------------------------------------------------

def _append_journal_line(journal: Path, record: dict[str, Any]) -> None:
    journal.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    fd = os.open(journal,
                 os.O_WRONLY | os.O_CREAT | os.O_APPEND
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def label_digest_record(session: str, trial_id: str, verdict: str,
                        cand: dict[str, Any],
                        events: list[dict[str, Any]], *,
                        channel: Optional[str] = None) -> dict[str, Any]:
    """One CONTENT-FREE per-label digest line (the external anchor's
    re-count source, design B1/HP-3): ids, hashes, verdict, basis, and the
    channel attestation — never the note text, never event content. The
    additive ``channel`` mirror key lets the anchor re-count and the
    calibration pairing bucket without opening the store; the STORE copy
    (``detail.label_channel``, hash-covered and signed) stays authoritative
    and is re-verified per pair. Fail-closed like write_label: an
    unattested digest row is never minted."""
    if channel not in ATTESTED_LABEL_CHANNELS:
        raise EvidenceError(
            "label_channel_unattested",
            "Label digest refused: no attested channel provenance.",
        )
    return {
        "schema": "cabinet.governance-label-digest/v1",
        "ts": _now_iso(),
        "session": session,
        "trial_id": trial_id,
        "verdict": _VERDICT_RESULT[verdict],
        "basis": cand.get("basis"),
        LABEL_CHANNEL_JOURNAL_KEY: channel,
        "event_ids": [e.get("event_id") for e in events],
        "event_hashes": [e.get("event_hash") for e in events],
    }


def session_marker_record(session: str, *, labels: int, skipped: int,
                          unverified: int, completed: bool,
                          stations: str) -> dict[str, Any]:
    """The session-complete marker row (what RAMP-5 later automates the
    REPORT_ONLY flip condition against — 'first weekly review ran')."""
    return {
        "schema": "cabinet.governance-review-session/v1",
        "kind": "session_complete",
        "ts": _now_iso(),
        "session": session,
        "labels": labels,
        "skipped": skipped,
        "unverified": unverified,
        "completed": completed,
        "stations": stations,
    }


def _write_transcript(path: Path, lines: list[str], out) -> Optional[Path]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        target = path
        for attempt in range(1, 100):
            try:
                fd = os.open(target,
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | getattr(os, "O_NOFOLLOW", 0), 0o600)
                break
            except FileExistsError:
                target = path.with_name(f"{path.stem}-{attempt}{path.suffix}")
        else:  # pragma: no cover — 100 same-second sessions do not happen
            raise OSError("transcript name space exhausted")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return target
    except OSError as exc:
        print(f"WARN: session transcript write failed ({exc}) — the labels "
              "themselves are already on their trials.", file=out)
        return None


# ---------------------------------------------------------------------------
# stations 1-4 (read-only, best-effort, honest about absence)
# ---------------------------------------------------------------------------

def _run_fixed(argv: list[str], timeout: int = 20) -> Optional[str]:
    """Run a FIXED argv (shell never involved), bounded; None on any trouble."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stdout or "").strip()
    return text if proc.returncode == 0 and text else None


def _tail_jsonl(path: Path, n: int = 3) -> list[dict[str, Any]]:
    try:
        if path.is_symlink() or not path.is_file():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
        if len(rows) >= n:
            break
    return list(reversed(rows))


def render_stations(repo_root: Path, out) -> None:
    """Stations 1-4: read-only glances over existing surfaces, each with the
    RAMP-2 time budget printed and an honest 'unavailable' when a surface is
    not wired on this deployment. Never raises, never writes, never networks."""
    def head(i: int) -> None:
        name, budget = STATIONS[i]
        print(f"\n--- {name} [{budget}] " + "-" * max(1, 46 - len(name)),
              file=out)

    head(0)
    posture = _run_fixed([sys.executable,
                          str(repo_root / "cabinet/scripts/posture-status.py")])
    print(posture or "(posture tile unavailable — cabinet/scripts/"
          "posture-status.py did not answer)", file=out)

    head(1)
    cost = _run_fixed(["bash", str(repo_root / "cabinet/scripts/cost-report.sh")])
    if cost:
        print("\n".join(cost.splitlines()[:20]), file=out)
    else:
        print("(cost report unavailable — cabinet/scripts/cost-report.sh "
              "did not answer; check caps in your cost dashboard)", file=out)

    head(2)
    event_dir = Path(os.environ.get("CABINET_EVENT_LOG_DIR")
                     or os.path.expanduser(
                         "~/Library/Application Support/cabinet/events"))
    grad_lines: list[str] = []
    try:
        if event_dir.is_dir():
            day_files = sorted(event_dir.glob("events-*.jsonl"))[-7:]
            for day in day_files:
                for row in _tail_jsonl(day, n=50):
                    kind = str(row.get("kind") or row.get("event") or "")
                    if "graduation" in kind:
                        grad_lines.append(
                            f"  {row.get('ts', '')[:10]} {kind} "
                            f"{row.get('cell') or row.get('subject') or ''}")
    except OSError:
        pass
    print("graduation transitions (last 7d): "
          + (f"{len(grad_lines)}" if grad_lines else "none seen"), file=out)
    for line in grad_lines[-5:]:
        print(line, file=out)
    needs = _tail_jsonl(repo_root / "shared/interfaces/needs-ledger.jsonl", n=3)
    print(f"pending petitions (needs-ledger tail): {len(needs)}", file=out)
    for row in needs:
        print(f"  {str(row.get('ts') or '')[:10]} "
              f"{row.get('kind') or row.get('need') or row.get('summary') or '?'}",
              file=out)

    head(3)
    falsifier = _tail_jsonl(
        repo_root / "shared/interfaces/falsifier-series.jsonl", n=1)
    if falsifier:
        print(f"falsifier series (latest): "
              f"{json.dumps(falsifier[-1], ensure_ascii=False, sort_keys=True)[:400]}",
              file=out)
    else:
        print("falsifier series: not wired on this deployment", file=out)
    violations = _tail_jsonl(
        repo_root / "shared/interfaces/envelope-violations.jsonl", n=3)
    print(f"envelope violations (tail): {len(violations)}", file=out)
    print("would-apply receipts: grep REPORT_ONLY_SUMMARY in the "
          "self-improvement loop log (report-only soak stays on until this "
          "ritual is a habit)", file=out)


# ---------------------------------------------------------------------------
# the ritual
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="governance-review",
        description="The Captain's weekly governance review (RAMP-2): five "
                    "stations ending in a blind, verified, hard-capped "
                    "labeling session. Captain capability token required.",
    )
    parser.add_argument("--store", type=Path,
                        default=_REPO_ROOT / "instance" / "evidence" / "v1",
                        help="Evidence store root (default instance/evidence/v1)")
    parser.add_argument("--captain-token-file", type=Path, default=None,
                        help="Captain capability token file (falls back to "
                             "$CABINET_CAPTAIN_TOKEN_FILE)")
    parser.add_argument("--seed", type=int, default=None,
                        help="RNG seed for a reproducible sample")
    parser.add_argument("--scan-cap", type=int, default=SCAN_CAP_DEFAULT,
                        help=f"How many most-recent trials to consider "
                             f"(default {SCAN_CAP_DEFAULT}; perf knob — the "
                             f"label cap is a constant, not a flag)")
    parser.add_argument("--relabel", action="store_true",
                        help="Include trials that already carry a Captain "
                             "label (a new label supersedes on the human side)")
    parser.add_argument("--dry-run", action="store_true",
                        help="List the would-be sample and stop: no station "
                             "commands, no verification, no writes of any kind")
    parser.add_argument("--skip-stations", action="store_true",
                        help="Skip stations 1-4 (labeling-only session)")
    parser.add_argument("--labels-journal", type=Path,
                        default=_REPO_ROOT / LABELS_JOURNAL_REL,
                        help=f"Per-label digest journal (default "
                             f"{LABELS_JOURNAL_REL}; anchored daily)")
    parser.add_argument("--transcript-dir", type=Path,
                        default=_REPO_ROOT / TRANSCRIPT_DIR_REL,
                        help=f"Session transcript directory (default "
                             f"{TRANSCRIPT_DIR_REL})")
    return parser


def main(argv: Optional[list] = None,
         input_fn: Callable[[str], str] = input,
         isatty: Optional[bool] = None,
         out=None) -> int:
    out = out or sys.stdout
    args = _build_parser().parse_args(argv)
    print(BANNER, file=out)

    store = Path(args.store)
    if not store.is_dir() or not (store / ".signing-key").exists():
        print(f"No evidence store at {store} — nothing to review. (The store "
              "is runtime-created by the first recording producer.)", file=out)
        return 0

    # Token gate FIRST, every mode — before any store read beyond the key,
    # before any verification, before any recorder construction. The refused
    # path leaves the store byte-identical.
    try:
        require_captain_token(store, args)
    except EvidenceError as exc:
        print(f"REFUSED ({exc.code}): {exc}", file=out)
        return 3

    session = "gr-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    candidates = collect_candidates(store, scan_cap=args.scan_cap,
                                    relabel=args.relabel)
    if not candidates:
        print("Nothing to review: no labelable trials in the store "
              f"(scan cap {args.scan_cap}, relabel={args.relabel}).", file=out)
        return 0

    rng = random.Random(args.seed)
    # Queue up to 2x the cap so verify-failures and skips cannot starve the
    # session; the label cap itself is absolute and enforced in the loop.
    queue = stratified_sample(
        candidates, min(len(candidates), MAX_LABELS_PER_SESSION * 2), rng)
    strata = sorted({c["basis"] for c in candidates})
    print(f"{len(candidates)} candidate trial(s) across strata "
          f"{strata}; queued {len(queue)} for presentation "
          f"(label cap {MAX_LABELS_PER_SESSION}).", file=out)

    if args.dry_run:
        print("\nDRY RUN — nothing will be verified or written. Would present "
              "(UNVERIFIED plan — every trial is verified before any real "
              "presentation):", file=out)
        for i, cand in enumerate(queue, 1):
            print(f"  {i:2d}. {cand['trial_id']}  basis={cand['basis']}  "
                  f"risk={cand['risk']}  events={cand['count']}", file=out)
        return 0

    if isatty is None:
        isatty = sys.stdin.isatty()
    if not isatty:
        print("REFUSED: stdin is not a TTY. Captain labels must come from a "
              "live Captain session — no pipe/cron/agent may mint "
              "verdict_human events. Use --dry-run to inspect.", file=out)
        return 2

    # HP-3: both gates passed (token above, TTY here) — attest the label
    # channel ONCE for the session; every write_label/label_digest_record
    # below is fail-closed on it. token_ok is True by control flow (the
    # token gate raised otherwise); the TTY fact is passed as observed.
    channel = attest_tty_channel(token_ok=True, stdin_tty=bool(isatty))

    stations_note = "skipped (--skip-stations)"
    if not args.skip_stations:
        stations_note = "rendered"
        render_stations(_REPO_ROOT, out)

    name, budget = STATIONS[4]
    print(f"\n--- {name} [{budget}] " + "-" * max(1, 46 - len(name)), file=out)

    recorder = EvidenceRecorder(store)
    transcript: list[str] = [
        f"# Governance review {session}",
        "",
        f"- when: {_now_iso()}",
        f"- store: {store}",
        f"- stations 1-4: {stations_note}",
        f"- candidates: {len(candidates)}; queued: {len(queue)}; "
        f"label cap: {MAX_LABELS_PER_SESSION}",
        "",
        "## Labels",
        "",
    ]
    labels = skipped = unverified = 0
    export_degraded = False
    completed = True

    for position, cand in enumerate(queue, 1):
        if labels >= MAX_LABELS_PER_SESSION:
            print(f"\nSession label cap reached "
                  f"({MAX_LABELS_PER_SESSION}) — quality over coverage.",
                  file=out)
            break
        trial_id = cand["trial_id"]
        print(f"\n=== trial {position}/{len(queue)} "
              + "=" * max(1, 50 - len(str(position)) - len(str(len(queue)))),
              file=out)

        # Fail-closed display: verify IMMEDIATELY before presenting; an
        # unverifiable trial shows id + error codes ONLY and cannot be labeled.
        verdict_report = verifier.verify_trial(store, trial_id)
        if not verdict_report.get("ok"):
            errors = ",".join(str(e) for e in
                              (verdict_report.get("errors") or [])[:6])
            print(f"UNVERIFIED: {trial_id} — excluded from labeling "
                  f"(errors: {errors or 'unknown'}). Nothing from this trial "
                  "is shown; investigate via the verifier.", file=out)
            transcript.append(f"- {trial_id}: UNVERIFIED ({errors}) — excluded")
            unverified += 1
            continue

        # Re-read + re-classify AFTER verification so the presented basis is
        # the basis AT LABEL TIME (and the blind filter covers any machine
        # leg that landed since sampling).
        cand = {**cand, **classify_trial(_read_raw_events(store, trial_id))}
        cand["trial_id"] = trial_id
        try:
            projection = recorder.cabinet_projection(trial_id)
        except EvidenceError as exc:
            print(f"UNVERIFIED: {trial_id} — projection refused "
                  f"({exc.code}); excluded from labeling.", file=out)
            transcript.append(f"- {trial_id}: UNVERIFIED ({exc.code}) — excluded")
            unverified += 1
            continue
        print(present_trial(projection, cand), file=out)

        while True:
            try:
                answer = input_fn(PROMPT).strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "q"
            if answer in ("r", "right"):
                verdict = "right"
            elif answer in ("w", "wrong"):
                verdict = "wrong"
            elif answer in ("u", "unclear"):
                verdict = "unclear"
            elif answer in ("s", "skip"):
                skipped += 1
                transcript.append(f"- {trial_id}: skipped")
                break
            elif answer in ("q", "quit"):
                completed = False
                break
            else:
                print("  answer r / w / u / s / q", file=out)
                continue

            try:
                note = input_fn("  note (optional, enter to skip) > ").strip()
            except (EOFError, KeyboardInterrupt):
                note = ""
            try:
                events = write_label(recorder, trial_id, verdict, note,
                                     cand, session, channel=channel)
            except EvidenceError as exc:
                if exc.code == "trial_purged":
                    print(f"  trial purged since sampling — legal skip "
                          f"({trial_id}).", file=out)
                    transcript.append(f"- {trial_id}: purged mid-session — skip")
                    skipped += 1
                    break
                # LOUD: the Captain is present; a silently lost label
                # corrupts the calibration floor.
                print(f"  LABEL FAILED ({exc.code}): {exc} — verdict NOT "
                      "recorded; the evidence plane refused the append.",
                      file=out)
                transcript.append(
                    f"- {trial_id}: LABEL FAILED ({exc.code}) — not recorded")
                break
            labels += 1
            print(f"  recorded {_VERDICT_RESULT[verdict]} "
                  f"({len(events)} event(s)) on {trial_id} "
                  f"[label {labels}/{MAX_LABELS_PER_SESSION}]", file=out)
            transcript.append(
                f"- {trial_id}: {_VERDICT_RESULT[verdict]} "
                f"(basis={cand['basis']}, events="
                f"{[e.get('event_id') for e in events]})"
                + (f" — note: {note[:_NOTE_CAP]}" if note else ""))
            try:
                _append_journal_line(
                    Path(args.labels_journal),
                    label_digest_record(session, trial_id, verdict, cand,
                                        events, channel=channel))
            except OSError as exc:
                export_degraded = True
                print(f"  WARN: label digest export failed ({exc}) — the "
                      "label IS on the trial, but today's external anchor "
                      "will not carry its digest. Fix the journal path.",
                      file=out)
            break

        if not completed:
            break

    summary = (f"\nSession {session}: {labels} label(s) written, "
               f"{skipped} skipped, {unverified} unverified/excluded.")
    print(summary, file=out)
    transcript += ["", "## Summary", "",
                   f"- labels: {labels}", f"- skipped: {skipped}",
                   f"- unverified: {unverified}",
                   f"- completed: {completed}"]

    try:
        _append_journal_line(
            Path(args.labels_journal),
            session_marker_record(session, labels=labels, skipped=skipped,
                                  unverified=unverified, completed=completed,
                                  stations=stations_note))
    except OSError as exc:
        export_degraded = True
        print(f"WARN: session marker export failed ({exc}).", file=out)

    written = _write_transcript(
        Path(args.transcript_dir) / f"{session}.md", transcript, out)
    if written is None:
        export_degraded = True
    else:
        print(f"Transcript: {written}", file=out)

    print("Anchor the label digests off-box: python3.12 "
          "cabinet/scripts/evidence-anchor.py --json  (or let the daily "
          "job run — the journal rides record.captain_labels).", file=out)
    return 1 if export_degraded else 0


if __name__ == "__main__":
    sys.exit(main())
