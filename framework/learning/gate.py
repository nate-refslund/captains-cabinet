"""Evidence Gate [D15/D16, sovereign spec §4 SOV-8] — evidence runs LIVE,
germline CODE auto-apply stays DARK.

`ratify()` is the ONLY sanctioned reviewer for self-improvement *code diffs*:
it produces an evidence pack and **applies nothing** — the apply lane
(`cabinet/scripts/gate-apply.sh` + the `com.cabinet.gate-apply` root daemon)
ships DARK and is never loaded by any setup script. Until the Captain builds the
unprivileged sandbox harness and explicitly `sudo launchctl load`s the daemon,
germline code apply stays Captain-manual in every posture (D15).

Stage pipeline (short-circuit on first failure):

  S0 scope    — REFUSE any diff touching a Ring-0 path. Ring-0 is enumerated
                by `framework/policies/immutable-core.yml` (SOV-9a) — every
                class refuses equally (files, dirs, runtime_appended,
                hook_protected). An unreadable enumeration also refuses: a
                gate that cannot see Ring-0 must not pass anything. Refusal
                files a deduped `kind=decision` need (eval-019).
  S1 verify   — full pytest + golden-eval shells, UNPRIVILEGED. The default
                runner refuses euid==0 (NO root pytest — the S1/S2/S3-as-root
                design was killed, D15) and needs a prepared candidate
                worktree; absent one it FAILS closed ("sandbox harness not
                built") rather than minting evidence from nothing.
  S2 falsify  — the falsifier corpus (same unprivileged runner discipline).
  S3 ceilings — sweep the six hard ceilings × 5 states × BOTH postures
                against the live floor (in-process, read-only — candidate
                code is never imported into this process): no cell may
                resolve unconditional `auto`.
  S4 archive  — content-hash-named variant archive of the exact diff.
  S5 verdict  — pass/fail evidence pack JSON. `applies_nothing` is stamped
                into every pack as a structural reminder.

`run_gate_review()` is the D16 fuel producer: it stamps
`review={verdict: confirmed, source: verdict_gate}` (via the ONE superseding
builder, `binder_wire.acted_verdict_event`) onto acted consequence rows that
clear the FULL machine bar — ttl_ok ∧ no undo ∧ no veto on the cell ∧
canary+falsifier green in window ∧ cell not within `cooldown_days` of a
demote. It is sovereign-gated at run time (guardian ⇒ no-op, ledger
untouched — guardian world bit-identical) and NEVER overwrites an existing
review of any source; `consequence.compute_ratios` (SOV-7) decides whether
the stamps count, again at compute time.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

STAGES = ("S0_scope", "S1_verify", "S2_falsifier", "S3_ceilings",
          "S4_archive", "S5_verdict")

# The confidence states every verdict table carries (matrix._validate_verdicts
# vocabulary) — S3 sweeps all five per ceiling per posture.
_STATES = ("graduated", "eligible", "propose_only", "unmeasured", "demote")

# D16 machine-bar defaults. window: how fresh canary+falsifier evidence must
# be; cooldown: a cell with ANY wrong verdict this recent is demote-adjacent
# and gets no gate fuel (ALIGNMENT anti-flap — mirrors the kind breaker's 14d).
REVIEW_WINDOW_DAYS = 7
REVIEW_COOLDOWN_DAYS = 14

# The reconcile sweep's ttl_ok outcome evidence prefix (binder_wire
# _ACTED_VERDICTS["ttl_ok"]) — the ONE marker that says "TTL survived and the
# artifact was probed intact". Clock math here would be weaker than the probe.
_TTL_OK_MARKER = "ttl-48h survived"

_GATE_EVIDENCE_SUBDIR = ("shared", "interfaces", "gate-evidence")


# ---------------------------------------------------------------------------
# Roots + small helpers
# ---------------------------------------------------------------------------

def _root(root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(os.environ.get("CABINET_ROOT") or str(_FRAMEWORK_ROOT))


def evidence_dir(root: str | Path | None = None) -> Path:
    """shared/interfaces/gate-evidence/ under the cabinet root (runtime data,
    SKIP-class — the gate CODE is Ring-0, its evidence output is not)."""
    return _root(root).joinpath(*_GATE_EVIDENCE_SUBDIR)


def _now(now: str | None = None) -> str:
    if now:
        return now
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _no_marker(s: str) -> str:
    # U+00B7 pid-marker strip — same binder-injection defense as needs.py.
    return (s or "").replace("·", "")


def diff_sha256(diff_text: str) -> str:
    return hashlib.sha256((diff_text or "").encode("utf-8")).hexdigest()


def _emit_org(event_type: str, payload: dict[str, Any], actor: str) -> None:
    """Best-effort org-event breadcrumb using EXISTING emitter vocabulary
    (eval_run_started / eval_passed / eval_failed) — SOV-8 adds no event
    types (emitter.py is SOV-1's file)."""
    try:
        from framework.events.emitter import emit
        emit(event_type, actor=actor, payload=payload)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Ring-0 enumeration (immutable-core.yml — SOV-9a artifact)
# ---------------------------------------------------------------------------

def ring0_path(root: str | Path | None = None) -> Path:
    return _root(root) / "framework" / "policies" / "immutable-core.yml"


def load_ring0(root: str | Path | None = None) -> dict[str, list[str]] | None:
    """Parse immutable-core.yml → {'files': [...], 'dirs': [...]} path lists
    (dirs bucket = every prefix-matched class: dirs + runtime_appended data
    parents are NOT merged — runtime_appended/hook_protected entries are exact
    files and land in 'files'). None on ANY failure — the caller must refuse,
    never guess (a gate that cannot see Ring-0 must not pass anything)."""
    try:
        import yaml  # deferred — available in the cabinet runtime + CI
        data = yaml.safe_load(ring0_path(root).read_text())
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    files: list[str] = []
    dirs: list[str] = []
    for cls, bucket in (("files", files), ("dirs", dirs),
                        ("runtime_appended", files), ("hook_protected", files)):
        entries = data.get(cls) or []
        if not isinstance(entries, list):
            return None
        for e in entries:
            p = e.get("path") if isinstance(e, dict) else e
            if not isinstance(p, str) or not p.strip():
                return None
            bucket.append(p.strip())
    if not files and not dirs:
        return None
    return {"files": files, "dirs": dirs}


_DIFF_PREFIXES = ("+++ b/", "--- a/", "rename to ", "rename from ")


def diff_paths(diff_text: str) -> list[str]:
    """Repo-relative paths a unified diff touches. `/dev/null` sides are
    dropped. An absolute or `..`-traversing path is KEPT verbatim so the
    Ring-0 check can refuse it (touches_ring0 treats escapes as Ring-0)."""
    paths: list[str] = []
    for line in (diff_text or "").splitlines():
        if line.startswith("diff --git a/"):
            # `diff --git a/X b/Y` — take both sides.
            rest = line[len("diff --git a/"):]
            if " b/" in rest:
                a, b = rest.split(" b/", 1)
                for p in (a, b):
                    if p and p != "/dev/null" and p not in paths:
                        paths.append(p)
            continue
        for pref in _DIFF_PREFIXES:
            if line.startswith(pref):
                p = line[len(pref):].strip()
                # `+++ b/path<TAB>timestamp` form
                p = p.split("\t", 1)[0]
                if p and p != "/dev/null" and p not in paths:
                    paths.append(p)
                break
    return paths


def _escapes_repo(path: str) -> bool:
    return path.startswith("/") or path.startswith("..") or "/../" in path


def touches_ring0(paths: list[str], ring0: dict[str, list[str]]) -> list[str]:
    """The subset of `paths` that are Ring-0 (exact file match, under a Ring-0
    dir, or escaping the repo — an escape can alias a locked path, so it
    refuses too). Every immutable-core class refuses equally."""
    hits: list[str] = []
    files = set(ring0.get("files") or [])
    dirs = [d.rstrip("/") + "/" for d in (ring0.get("dirs") or [])]
    for p in paths:
        norm = p.strip().lstrip("./")
        if _escapes_repo(p) or norm in files or any(norm.startswith(d) for d in dirs):
            hits.append(p)
    return hits


# ---------------------------------------------------------------------------
# S1/S2 runner (UNPRIVILEGED — no root pytest, ever)
# ---------------------------------------------------------------------------

def _default_runner(stage: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Run one verify-stage command set UNPRIVILEGED. Fail-closed:

      * euid==0 ⇒ refuse (the killed design ran S1/S2/S3 as root; the gate
        structurally cannot — eval-019).
      * no prepared candidate worktree (spec['cwd']) ⇒ fail with "sandbox
        harness not built": evidence is never minted from nothing (D15 keeps
        germline apply Captain-manual until the harness exists).

    Commands are arg-lists (no shell). Git hook execution is disabled for the
    child both ways: `-c core.hooksPath=/dev/null` belongs on any git argv the
    spec carries, and the env pins core.hooksPath too.
    """
    if os.geteuid() == 0:
        return {"ok": False, "detail": "refused: gate verify never runs as root"}
    cwd = spec.get("cwd")
    if not cwd or not Path(cwd).is_dir():
        return {"ok": False,
                "detail": "no candidate worktree prepared (sandbox harness "
                          "not built) — stage cannot pass without evidence"}
    env = {**os.environ,
           "GIT_CONFIG_COUNT": "1",
           "GIT_CONFIG_KEY_0": "core.hooksPath",
           "GIT_CONFIG_VALUE_0": "/dev/null"}
    tails: list[str] = []
    for argv in spec.get("commands") or []:
        try:
            cp = subprocess.run(list(argv), cwd=str(cwd), env=env,
                                capture_output=True, text=True, timeout=1800)
        except Exception as exc:  # noqa: BLE001 — one broken command fails the stage
            return {"ok": False, "detail": f"{stage}: {argv[0]}: {exc}"}
        out_lines = (cp.stdout or "").strip().splitlines()
        if out_lines:
            tails.append(out_lines[-1])
        if cp.returncode != 0:
            err = ((cp.stderr or "").strip().splitlines() or ["(no stderr)"])[-1]
            return {"ok": False,
                    "detail": f"{stage}: exit {cp.returncode}: {err[:300]}"}
    return {"ok": True, "detail": "; ".join(t for t in tails if t)[:300] or "ok"}


def _verify_spec(stage: str, workdir: str | None, root: Path) -> dict[str, Any]:
    """The default command set per verify stage. pytest is invoked plainly
    (never via sudo); golden shells run under bash; the falsifier corpus is
    the authority golden-eval enforcing pytests + the golden shell dir."""
    py = "python3.12"
    if stage == "S1_verify":
        cmds: list[list[str]] = [[py, "-m", "pytest", "-q", "-p", "no:cacheprovider"]]
        gdir = root / "memory" / "golden-evals" / "framework"
        if gdir.is_dir():
            cmds += [["/bin/bash", str(sh)] for sh in sorted(gdir.glob("*.sh"))]
        return {"cwd": workdir, "commands": cmds}
    # S2_falsifier — the adversarial corpus that tries to falsify the change.
    return {"cwd": workdir, "commands": [
        [py, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "framework/authority/tests/test_golden_evals_a0.py"],
    ]}


# ---------------------------------------------------------------------------
# S3 — ceiling probes, both postures, in-process + read-only
# ---------------------------------------------------------------------------

def ceiling_probe(root: str | Path | None = None) -> dict[str, Any]:
    """Sweep every hard-ceiling class × 5 states × {guardian, sovereign}
    against the LIVE floor: no cell may resolve unconditional `auto`.

    Read-only and in-process over OUR shipped modules — candidate code is
    never imported into the gate's process (it is only ever exercised inside
    the unprivileged sandbox runner). Fail-closed: any load/validate error is
    a failing probe."""
    try:
        from cabinet.scripts.lib.policy_engine import resolve_verdict
        from framework.authority import matrix as matrix_mod
        data = matrix_mod.load_matrix(
            str(Path(_root(root)) / "framework" / "policies" / "authority-matrix.yml")
        )
        policy = matrix_mod.matrix_policy(data)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": f"floor unloadable: {exc}"}
    verdicts = policy.get("verdicts")
    postures = policy.get("postures")
    ceilings = sorted(policy.get("hard_ceiling") or [])
    if not ceilings:
        return {"ok": False, "detail": "floor declares no hard ceiling"}
    bad: list[str] = []
    for posture in (None, "sovereign"):
        for rc in ceilings:
            for state in _STATES:
                v = resolve_verdict(verdicts, rc, state,
                                    posture=posture, postures=postures)
                if v == "auto":
                    bad.append(f"{posture or 'guardian'}:{rc}:{state}")
    if bad:
        return {"ok": False,
                "detail": "ceiling resolved unconditional auto: " + ", ".join(bad)}
    return {"ok": True,
            "detail": f"{len(ceilings)} ceilings × {len(_STATES)} states × "
                      f"2 postures: no unconditional auto"}


# ---------------------------------------------------------------------------
# ratify — S0..S5, evidence only, applies NOTHING
# ---------------------------------------------------------------------------

def _refusal_need(proposal: dict[str, Any], hits: list[str],
                  root: str | Path | None) -> str | None:
    """Deduped Ring-0-refusal need — best-effort, gated by needs_enabled."""
    try:
        from framework.authority import needs
        return needs.file_need(
            "decision",
            action_type="gate_ring0_refusal",
            lane=proposal.get("lane"),
            why=_no_marker(
                "gate.ratify refused a Ring-0-touching self-improvement diff "
                f"({', '.join(hits[:5])}) — germline changes reach the tree "
                "only via a Captain amendment in an unlock window"),
            unblocks="the refused proposal, if the Captain wants it",
            filed_by="gate.ratify",
            root=root,
        )
    except Exception:
        return None


def ratify(
    proposal: dict[str, Any],
    *,
    root: str | Path | None = None,
    runner: Optional[Callable[[str, dict[str, Any]], dict[str, Any]]] = None,
    probe_fn: Optional[Callable[[], dict[str, Any]]] = None,
    now: str | None = None,
    actor: str = "gate",
) -> dict[str, Any]:
    """Produce the evidence pack for one self-improvement code proposal.

    `proposal`: {id?, gap_id?, lane?, summary?, diff (unified diff text),
    workdir? (prepared candidate worktree for the unprivileged verify)}.
    Returns the pack dict (also written to shared/interfaces/gate-evidence/).
    APPLIES NOTHING — verdict `pass` only licenses the DARK apply lane /
    the Captain's manual unlock window. Never raises.
    """
    ts = _now(now)
    rootp = _root(root)
    run = runner or _default_runner
    probe = probe_fn or (lambda: ceiling_probe(rootp))
    diff = str(proposal.get("diff") or "")
    sha = diff_sha256(diff)
    pack: dict[str, Any] = {
        "pack_id": f"pack-{sha[:16]}",
        "proposal_id": proposal.get("id"),
        "gap_id": proposal.get("gap_id"),
        "lane": proposal.get("lane"),
        "summary": _no_marker(str(proposal.get("summary") or ""))[:300],
        "sha256": sha,
        "ts": ts,
        "stages": [],
        "verdict": "fail",
        "applies_nothing": True,
    }
    stages: list[dict[str, Any]] = pack["stages"]

    def _stage(name: str, status: str, detail: str) -> None:
        stages.append({"stage": name, "status": status,
                       "detail": _no_marker(detail)[:500]})

    def _skip_rest(after: str) -> None:
        idx = STAGES.index(after)
        for name in STAGES[idx + 1:-1]:  # S5 verdict always records
            _stage(name, "skipped", f"short-circuit after {after}")

    _emit_org("eval_run_started", {"kind": "gate_ratify", "pack_id": pack["pack_id"],
                                   "proposal_id": pack["proposal_id"]}, actor)
    try:
        # S0 — scope: refuse Ring-0 (unreadable enumeration also refuses).
        ring0 = load_ring0(rootp)
        if not diff.strip():
            _stage("S0_scope", "refused", "empty diff — nothing to ratify")
            pack["verdict"] = "refused"
            _skip_rest("S0_scope")
        elif ring0 is None:
            _stage("S0_scope", "refused",
                   "immutable-core.yml unreadable — a gate that cannot see "
                   "Ring-0 must not pass anything")
            pack["verdict"] = "refused"
            _skip_rest("S0_scope")
        else:
            hits = touches_ring0(diff_paths(diff), ring0)
            if hits:
                _stage("S0_scope", "refused",
                       "diff touches Ring-0: " + ", ".join(hits[:10]))
                pack["verdict"] = "refused"
                pack["need_id"] = _refusal_need(proposal, hits, rootp)
                _skip_rest("S0_scope")
            else:
                _stage("S0_scope", "pass",
                       f"{len(diff_paths(diff))} path(s), none Ring-0")
                workdir = proposal.get("workdir")
                short_circuited = False
                for name in ("S1_verify", "S2_falsifier"):
                    try:
                        res = run(name, _verify_spec(name, workdir, rootp))
                    except Exception as exc:  # noqa: BLE001
                        res = {"ok": False, "detail": f"runner error: {exc}"}
                    _stage(name, "pass" if res.get("ok") else "fail",
                           str(res.get("detail") or ""))
                    if not res.get("ok"):
                        _skip_rest(name)
                        short_circuited = True
                        break
                if not short_circuited:
                    try:
                        res = probe()
                    except Exception as exc:  # noqa: BLE001
                        res = {"ok": False, "detail": f"probe error: {exc}"}
                    _stage("S3_ceilings", "pass" if res.get("ok") else "fail",
                           str(res.get("detail") or ""))
                    if not res.get("ok"):
                        _skip_rest("S3_ceilings")
                    else:
                        try:
                            vdir = evidence_dir(rootp) / "variants"
                            vdir.mkdir(parents=True, exist_ok=True)
                            (vdir / f"{sha[:16]}.patch").write_text(diff)
                            _stage("S4_archive", "pass", f"variants/{sha[:16]}.patch")
                            pack["verdict"] = "pass"
                        except OSError as exc:
                            _stage("S4_archive", "fail", f"archive write: {exc}")
    except Exception as exc:  # noqa: BLE001 — the gate itself must never raise
        _stage("S5_verdict", "error", f"gate error: {exc}")
        pack["verdict"] = "fail"

    _stage("S5_verdict", pack["verdict"],
           "evidence only — applies nothing; germline apply stays "
           "Captain-manual (D15)")
    try:
        edir = evidence_dir(rootp)
        edir.mkdir(parents=True, exist_ok=True)
        (edir / f"{pack['pack_id']}.json").write_text(
            json.dumps(pack, indent=2, default=str))
    except OSError:
        pass
    _emit_org("eval_passed" if pack["verdict"] == "pass" else "eval_failed",
              {"kind": "gate_ratify", "pack_id": pack["pack_id"],
               "verdict": pack["verdict"]}, actor)
    return pack


# ---------------------------------------------------------------------------
# Evidence lookups (capability_gaps.can_install consumes these)
# ---------------------------------------------------------------------------

def _packs(root: str | Path | None = None) -> list[dict[str, Any]]:
    edir = evidence_dir(root)
    out: list[dict[str, Any]] = []
    try:
        for p in sorted(edir.glob("pack-*.json")):
            try:
                data = json.loads(p.read_text())
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and data.get("pack_id"):
                out.append(data)
    except OSError:
        return []
    out.sort(key=lambda d: str(d.get("ts") or ""))
    return out


def evidence_for(
    *,
    gap_id: str | None = None,
    proposal_id: str | None = None,
    root: str | Path | None = None,
) -> dict[str, Any] | None:
    """Newest evidence pack for a gap/proposal id, or None. Fail-closed on
    every read problem (no pack = no evidence = no allow)."""
    if not gap_id and not proposal_id:
        return None
    newest: dict[str, Any] | None = None
    for pack in _packs(root):
        if gap_id and pack.get("gap_id") != gap_id:
            continue
        if proposal_id and pack.get("proposal_id") != proposal_id:
            continue
        newest = pack  # _packs is ts-ascending; keep the last match
    return newest


def evidence_verdict(
    *,
    gap_id: str | None = None,
    proposal_id: str | None = None,
    root: str | Path | None = None,
) -> str | None:
    pack = evidence_for(gap_id=gap_id, proposal_id=proposal_id, root=root)
    return pack.get("verdict") if pack else None


# ---------------------------------------------------------------------------
# run_gate_review — D16 verdict_gate fuel (sovereign-gated, 5-condition bar)
# ---------------------------------------------------------------------------

def _resolve_posture_safe() -> str:
    try:
        from framework.authority.posture import resolve_posture
        return resolve_posture()
    except Exception:
        return "guardian"


def _default_canary_green(kind: str, *, now: str, window_days: int) -> bool:
    """A green canary receipt for `kind` within the window, with no newer red
    (a recently-red kind must never read clean). Fail-closed on any error."""
    try:
        from framework.frontdoor.action_undo import canary_receipts
        nowdt = datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
        floor = nowdt - timedelta(days=window_days)
        state = None  # newest receipt inside the window wins
        for r in canary_receipts(kind):
            try:
                ts = datetime.strptime(str(r.get("ts") or ""),
                                       "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc)
            except ValueError:
                continue
            if floor <= ts <= nowdt:
                state = bool(r.get("green"))
        return state is True
    except Exception:
        return False


def _default_falsifier_green(*, root: str | Path | None, now: str,
                             window_days: int) -> bool:
    """The falsifier telemetry is ALIVE: falsifier-series.jsonl carries a line
    dated within the window ("a falsifier you cannot measure is theater" —
    stale telemetry withholds gate fuel). Fail-closed."""
    try:
        path = _root(root) / "shared" / "interfaces" / "falsifier-series.jsonl"
        nowdt = datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
        floor = (nowdt - timedelta(days=window_days)).date().isoformat()
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and str(row.get("date") or "") >= floor:
                return True
        return False
    except Exception:
        return False


def _is_acted(ev: dict[str, Any]) -> bool:
    """Unattended-act rows: proposal.required is False + a stamped action_type
    (the RT-B1 marker semantics actfirst_canary/falsifier-report use)."""
    prop = ev.get("proposal")
    if not isinstance(prop, dict) or prop.get("required") is not False:
        return False
    at = ev.get("action_type")
    return isinstance(at, str) and bool(at) and not at.startswith("__")


def _cell_of(ev: dict[str, Any]) -> tuple[str, Any, Any]:
    actor = ev.get("actor") or {}
    return (f"{actor.get('kind')}:{actor.get('id')}", ev.get("lane"),
            ev.get("action_type"))


def run_gate_review(
    *,
    ledger: list[dict[str, Any]] | None = None,
    root: str | Path | None = None,
    now: str | None = None,
    posture: str | None = None,
    window_days: int = REVIEW_WINDOW_DAYS,
    cooldown_days: int = REVIEW_COOLDOWN_DAYS,
    canary_green_fn: Optional[Callable[..., bool]] = None,
    falsifier_green_fn: Optional[Callable[..., bool]] = None,
    is_vetoed_fn: Optional[Callable[[Optional[str]], bool]] = None,
    emit_fn: Optional[Callable[..., Any]] = None,
) -> dict[str, Any]:
    """Stamp `verdict_gate` confirms on acted rows clearing the FULL machine
    bar [D16]: ttl_ok ∧ no undo ∧ no veto on the cell ∧ canary+falsifier
    green in window ∧ cell not within `cooldown_days` of a demote.

    Sovereign-gated: `posture` (default `resolve_posture()`, exception ⇒
    guardian) must be "sovereign" or the review is a NO-OP — the guardian
    ledger stays bit-identical. A row with ANY existing review is never
    touched (a machine stamp must never overwrite a human 👍/undo or a judge
    verdict), so re-runs are idempotent. Never raises; per-row failures are
    isolated. Returns {posture, stamped: [...], considered, skipped?}.
    """
    ts = _now(now)
    eff = posture if posture is not None else _resolve_posture_safe()
    if eff != "sovereign":
        return {"posture": eff, "stamped": [], "considered": 0,
                "skipped": "posture"}
    try:
        from framework.fidelity.consequence import emit_consequence, read_ledger
        from framework.frontdoor.binder_wire import acted_verdict_event
        rows = ledger if ledger is not None else read_ledger()
    except Exception as exc:  # noqa: BLE001
        return {"posture": eff, "stamped": [], "considered": 0,
                "skipped": f"ledger unavailable: {exc}"}
    emitter = emit_fn or emit_consequence
    canary_green = canary_green_fn or (
        lambda kind: _default_canary_green(kind, now=ts, window_days=window_days))
    falsifier_green = falsifier_green_fn or (
        lambda: _default_falsifier_green(root=root, now=ts, window_days=window_days))

    def _vetoed(action_type: str) -> bool:
        if is_vetoed_fn is not None:
            return bool(is_vetoed_fn(action_type))
        try:
            from framework.frontdoor.veto_registry import is_vetoed
            return bool(is_vetoed(action_type))
        except Exception:
            return True  # unreadable veto registry withholds fuel (fail-closed)

    # Demote adjacency: the newest wrong-verdict ts per cell (any source —
    # wrong demotes from anywhere, D16), for the cooldown condition.
    cooldown_floor = ""
    try:
        nowdt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
        cooldown_floor = (nowdt - timedelta(days=cooldown_days)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        pass
    recent_wrong: set[tuple[str, Any, Any]] = set()
    for ev in rows:
        if not isinstance(ev, dict):
            continue
        review = ev.get("review") or {}
        if review.get("verdict") == "wrong" and \
                str(ev.get("ts") or "") >= cooldown_floor:
            recent_wrong.add(_cell_of(ev))

    stamped: list[dict[str, Any]] = []
    considered = 0
    falsifier_ok: bool | None = None  # one probe per run
    for ev in rows:
        if not isinstance(ev, dict) or not _is_acted(ev):
            continue
        outcome = ev.get("outcome") or {}
        evidence = str(outcome.get("evidence") or "")
        # Condition 1+2 — ttl_ok (the reconcile sweep's probe-backed marker)
        # and no undo (an undo supersedes to outcome=failed + review=wrong).
        if outcome.get("status") != "ok" or not evidence.startswith(_TTL_OK_MARKER):
            continue
        if ev.get("review"):
            continue  # already verdicted (any source) — never overwrite
        considered += 1
        cell = _cell_of(ev)
        action_type = str(ev.get("action_type"))
        try:
            # Condition 5 — not demote-adjacent.
            if cell in recent_wrong:
                continue
            # Condition 3 — no active veto on the cell.
            if _vetoed(action_type):
                continue
            # Condition 4 — canary + falsifier green in window.
            if not canary_green(action_type):
                continue
            if falsifier_ok is None:
                falsifier_ok = bool(falsifier_green())
            if not falsifier_ok:
                continue
            stamp = acted_verdict_event(
                ev, "confirmed",
                source="verdict_gate",
                evidence=("verdict_gate: 5-condition machine bar cleared "
                          "(ttl_ok, no undo, no veto, canary+falsifier "
                          "green, no recent demote)"),
                reviewed_at=ts,
            )
            emitter(**stamp)
            stamped.append({"subject": ev.get("subject"), "cell": list(cell)})
        except Exception:
            continue  # isolate — one bad row never stops the review
    return {"posture": eff, "stamped": stamped, "considered": considered}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI
    import argparse
    parser = argparse.ArgumentParser(
        description="Evidence Gate — ratify a self-improvement diff "
                    "(evidence only) or run the D16 gate review.")
    parser.add_argument("--ratify", metavar="DIFF_FILE",
                        help="Path to a unified diff to ratify")
    parser.add_argument("--summary", default="")
    parser.add_argument("--gap-id", default=None)
    parser.add_argument("--workdir", default=None,
                        help="Prepared candidate worktree for unprivileged verify")
    parser.add_argument("--review", action="store_true",
                        help="Run run_gate_review (sovereign-gated)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.ratify:
        diff = Path(args.ratify).read_text()
        out: dict[str, Any] = ratify({"diff": diff, "summary": args.summary,
                                      "gap_id": args.gap_id,
                                      "workdir": args.workdir})
    elif args.review:
        out = run_gate_review()
    else:
        parser.print_help()
        return 2
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(out.get("verdict") or out.get("posture"))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
