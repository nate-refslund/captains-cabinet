#!/usr/bin/env python3
"""Authority-matrix enforcement DRY RUN — measure the blast radius of adding
`authority_matrix` to the live enforcing set BEFORE flipping it.

WHY THIS EXISTS. `cabinet/scripts/policy-shadow.py` computes an authority-matrix
verdict on every tool call and then discards it: `_LEGACY_ENFORCING_TYPES`
excludes the type, so a cruder pattern-matcher decides. Flipping that exclusion
is a one-line change whose consequence is unbounded until it is measured — and a
gate that blocks routine work is switched off within a week, which is strictly
worse than shadow mode. So: replay the matrix over REAL recorded tool calls and
count what would NEWLY block.

WHAT IT MEASURES (the delta, not the absolute). For each recorded call it
computes two decisions over the SAME loaded policy stack:

  * `baseline`  — exactly today's live decision: `evaluate_policy` over the
                  types in `policy_shadow._LEGACY_ENFORCING_TYPES`.
  * `candidate` — the same loop with `authority_matrix` added, in the same
                  first-match-wins order `load_policies` returns.

NEWLY-BLOCKED = baseline allow AND candidate block. That is the only number that
matters: the matrix can never *widen* at this hook (an authority allow falls
through to the bash floor below it), so the flip is monotone-narrowing and its
entire cost is this delta.

HONESTY PROPERTIES (each one is a sensor that could otherwise lie):
  * It calls the REAL `policy_engine.evaluate_policy` / `load_policies` — no
    second copy of the verdict logic to drift (the duplicate-source failure this
    codebase keeps deleting). If the engine cannot be imported it EXITS NONZERO
    rather than reporting a clean zero.
  * It imports the enforcing set FROM `policy-shadow.py` itself, so if that set
    changes the baseline moves with it and this instrument cannot silently
    measure a stale baseline.
  * It refuses an EMPTY corpus (exit 2). A dry run over zero records otherwise
    prints "0 newly blocked" — the degenerate answer that reads exactly like a
    safe flip.
  * `officer` is taken PER RECORD, not from the environment, because
    `read_cell_state` joins graduation evidence on the officer id.
  * It is READ-ONLY, and that is ENFORCED rather than assumed. The candidate arm
    calls the GATE path (`_eval_authority_matrix`), which on a ceiling row under
    a non-guardian posture calls `standing_grant_resolution(..., act=True)` —
    the need-FILING, rate-CONSUMING path. A measurement that files needs is not
    a measurement. `_install_side_effect_guards()` therefore forces `act=False`
    and neuters the gate-tell emitter for the process, and the run ABORTS if the
    resolved posture is not guardian and the guards could not be installed.
    `ORG_POLICY_SHADOW_RECORD=0` is also forced, though that flag is read only by
    policy-shadow.py and never by the engine.

RE-RUNNING IT (the whole point — this number decides when the flip becomes
possible, so it must not be a one-off):

    # 1. rebuild the corpus from the live shadow record, read-only
    python3.12 cabinet/scripts/authority-matrix-dryrun.py --extract corpus.jsonl
    # 2. measure
    python3.12 cabinet/scripts/authority-matrix-dryrun.py corpus.jsonl \
        --verify-cache 300 --policy-timeout 1.5 --json out.json

`--extract` reads `cabinet/cache/org-runtime.sqlite3` through a `mode=ro` URI,
takes `event_type='policy.shadow_decision'` (the record pre-tool-use.sh writes
itself), de-duplicates on (officer, tool, input, second), drops the pytest
fixture rows suites leave in the live DB, and drops `officer=unknown`
(developer/CI sessions, `$OFFICER` unset). Those filters are the corpus's
honesty and are applied HERE rather than in a one-off script so the next
session gets the same population.

BASELINE OF RECORD — 2026-07-27, master 0ab0cc2b, guardian posture:
    80,307 records · 10,652 blocked today · 52 no-verdict · 69,603 allowed today
    52,659 NEWLY BLOCKED = 75.66%
Compare against this. A materially different number means the corpus, the
classifier or the matrix moved — find out which before trusting it.

CORPUS FORMAT — JSONL, one object per line, any of these shapes:
    {"tool_name": "Bash", "tool_input": {"command": "..."}, "officer": "cos"}
    {"tool_name": "Read", "tool_input": {...}, "ts": "2026-07-20T10:00:00Z"}
Records missing `tool_name` are counted as `skipped_malformed` and reported —
never silently dropped.

USAGE
    python3.12 cabinet/scripts/authority-matrix-dryrun.py CORPUS.jsonl [...]
        [--json OUT.json] [--top N] [--examples N]
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = SCRIPT_DIR.parent.parent

# READ-ONLY: no shadow event may be appended by a measurement run.
os.environ["ORG_POLICY_SHADOW_RECORD"] = "0"

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from framework.authority import policy_engine
except Exception as exc:  # noqa: BLE001
    print(f"FATAL: policy_engine unavailable ({exc}) — a dry run that cannot "
          f"load the engine must not report a clean result.", file=sys.stderr)
    raise SystemExit(3) from exc

# Import the enforcing set from the live shadow so the baseline can never be
# a stale hand-copy. policy-shadow.py is not an importable module name
# (hyphen), so load it by path.
try:
    import importlib.util as _ilu

    _spec = _ilu.spec_from_file_location(
        "_policy_shadow_for_dryrun", SCRIPT_DIR / "policy-shadow.py"
    )
    if _spec is None or _spec.loader is None:
        raise ImportError("cannot build spec for policy-shadow.py")
    _ps = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_ps)
    BASELINE_TYPES = frozenset(_ps._LEGACY_ENFORCING_TYPES)
except Exception as exc:  # noqa: BLE001
    print(f"FATAL: cannot read the live enforcing set from policy-shadow.py "
          f"({exc}) — refusing to measure against a guessed baseline.",
          file=sys.stderr)
    raise SystemExit(3) from exc

CANDIDATE_TYPES = BASELINE_TYPES | {"authority_matrix"}

# Risk buckets for the report. Derived from the matrix's own hard_ceiling list
# at run time where possible; this is the fallback ordering only.
_CEILING_FALLBACK = (
    "external_comms", "deploy_prod", "spend",
    "secrets", "network_write", "credentials_grant",
)


def _install_side_effect_guards() -> list[str]:
    """Neuter every WRITE the gate path can perform, and report what was pinned.

    The gate is not a pure function. Two writes hide in it:
      * `standing_grant_resolution(..., act=True)` — files a deduped NEED and
        counts a standing-grant rate use. Reached on a hard-ceiling row whenever
        the posture table resolves `standing_grant` (i.e. sovereign). ~11,500 of
        the 80k corpus records are ceiling rows, so this is not a corner.
      * `_emit_gate_tell(...)` — writes an org_event on every `notify_after`
        verdict.
    Guardian posture happens to avoid the first, but a dry run must not depend on
    the deployment's posture for its read-only property — §7 of the report
    mandates re-running this instrument as a flip precondition, and by then the
    posture may not be guardian.

    Returns the list of guards installed; the caller aborts if the list is empty
    and the posture is not guardian.
    """
    installed: list[str] = []

    original_grant = getattr(policy_engine, "standing_grant_resolution", None)
    if callable(original_grant):
        def probe_only(*args: Any, **kwargs: Any) -> Any:
            kwargs["act"] = False           # never file, never count
            return original_grant(*args, **kwargs)

        policy_engine.standing_grant_resolution = probe_only  # type: ignore[assignment]
        installed.append("standing_grant_resolution(act=False)")

    if callable(getattr(policy_engine, "_emit_gate_tell", None)):
        policy_engine._emit_gate_tell = lambda *a, **k: None  # type: ignore[assignment]
        installed.append("_emit_gate_tell(no-op)")

    # THIRD write, added with the propose/gate split: a propose verdict files
    # a deduped `capability` need. Replaying ~41k propose records would write
    # the ledger the report then reads — a measurement that files needs is not
    # a measurement. The id is still computed so `.need_id` stays populated;
    # only the append is suppressed.
    if callable(getattr(policy_engine, "_file_propose_need", None)):
        def _id_only(risk_class: str, action_type: str, lane: Any,
                     officer: str) -> Any:
            needs_mod = getattr(policy_engine, "_needs", None)
            if needs_mod is None:
                return None
            try:
                return needs_mod.need_id(
                    "capability", risk_class, action_type, lane)
            except Exception:
                return None

        policy_engine._file_propose_need = _id_only  # type: ignore[assignment]
        installed.append("_file_propose_need(id-only, no append)")

    return installed


def _install_cell_state_memo() -> "tuple[Any, dict]":
    """Memoize `read_cell_state` for the duration of a replay.

    WHY IT IS EXACT, not an approximation: `read_cell_state(officer, lane,
    action_type)` reads the consequence ledger, and a dry run WRITES NOTHING —
    no consequence row, no graduation transition. The answer for a given key is
    therefore constant across the whole replay, and the cache is a pure-function
    memo over ~O(officers x action_types) keys, not a staleness trade.

    It exists only because the uncached call is ~17ms (measured 2026-07-27) and
    a corpus is ~80k records. `--no-cache` disables it; `--verify-cache`
    proves equality on a sample rather than asserting it.

    Returns (original_function, cache_dict) so the caller can restore.
    """
    original = policy_engine.read_cell_state
    cache: dict[tuple[str, Any, str], str] = {}

    def memoized(officer: str, lane: Any, action_type: str) -> str:
        key = (officer, lane, action_type)
        if key not in cache:
            cache[key] = original(officer, lane, action_type)
        return cache[key]

    policy_engine.read_cell_state = memoized  # type: ignore[assignment]
    return original, cache


class EngineTimeout(Exception):
    """One policy evaluation exceeded the per-policy wall-clock budget.

    NOT a measurement inconvenience — a SENSOR. The live hook runs these same
    evaluations with NO time bound, so a policy that cannot answer inside a
    couple of seconds here is a policy that can WEDGE an officer in production.
    Timeouts are counted and reported as their own category; they are never
    silently treated as "allow".
    """


def _raise_timeout(signum: int, frame: Any) -> None:  # noqa: ARG001
    raise EngineTimeout()


def _first_block(policies: list[dict], types: frozenset[str],
                 tool_name: str, tool_input: dict, officer: str,
                 budget: float = 0.0
                 ) -> tuple[str, Any] | None:
    """First-match-wins over `policies` restricted to `types`.

    Returns (policy_name, reason) for the first blocking policy, else None.
    Mirrors both live loops (policy_shadow._engine_decision and
    policy_engine.main) — same order, same short-circuit.

    `budget` > 0 bounds EACH policy evaluation with SIGALRM and raises
    EngineTimeout naming the offender. Zero disables the bound (matching the
    live hook, which has none).
    """
    for policy in policies:
        if not isinstance(policy, dict):
            continue
        if policy.get("type") not in types:
            continue
        name = str(policy.get("name") or policy.get("type") or "policy")
        if budget > 0:
            signal.setitimer(signal.ITIMER_REAL, budget)
        try:
            result = policy_engine.evaluate_policy(policy, tool_name, tool_input, officer)
        except EngineTimeout:
            raise EngineTimeout(name) from None
        finally:
            if budget > 0:
                signal.setitimer(signal.ITIMER_REAL, 0)
        if result:
            # NOT `str(result)`: the engine returns a GateDecision (a str
            # subclass) carrying the structured verdict kind, and coercing it
            # here silently flattened every record to "legacy_typed" — a
            # counter wired to something other than the thing it measures.
            # Every downstream use is a plain string operation, which a str
            # subclass satisfies unchanged.
            return name, result
    return None


def _risk_bucket(reason: str, ceilings: tuple[str, ...]) -> str:
    """Categorise an authority block message into a risk class for the report.

    The gate's own message strings are the source: `GATED (hard ceiling: X)`,
    `PROPOSE-ONLY (unclassified action 'ambiguous')`, `PROPOSE-ONLY (X,
    confidence=Y)`. Anything unrecognised is reported as `other` rather than
    folded into a neighbouring bucket.
    """
    if "hard ceiling" in reason:
        for c in ceilings:
            if c in reason:
                return f"ceiling:{c}"
        return "ceiling:other"
    if "unclassified action" in reason:
        return "unclassified"
    if "failed validation" in reason:
        return "quarantined_floor"
    if "classifier unavailable" in reason:
        return "classifier_unavailable"
    if "act_with_undo" in reason:
        return "undo_gap"
    if "misplaced standing_grant" in reason:
        return "misplaced_grant"
    if reason.startswith("PROPOSE-ONLY ("):
        head = reason.split("PROPOSE-ONLY (", 1)[1].split(",", 1)[0]
        return f"below_bar:{head.strip()}"
    if reason.startswith("GATED ("):
        return "gated:other"
    return "other"


def _action_type(tool_name: str, tool_input: dict) -> str:
    try:
        return str(policy_engine.classify_action(tool_name, tool_input))
    except Exception:  # noqa: BLE001
        return "<classifier-error>"


_FIXTURE_MARKERS = ("/workspace/product/", "sed -i \'s/x/y/\'", "/workspace/testburg/")


def extract_corpus(db_path: str, out_path: str) -> int:
    """Rebuild the replay corpus from the live shadow record. READ-ONLY.

    Opened through a `mode=ro` URI so a measurement can never write the
    deployment's event store. Returns the record count written.
    """
    import hashlib
    import sqlite3

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT actor, created_at, payload_json FROM org_events "
        "WHERE event_type='policy.shadow_decision'"
    )
    seen: set = set()
    kept = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for actor, ts, payload_json in rows:
            try:
                payload = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(payload, dict) or not payload.get("tool_name"):
                continue
            tool_input = payload.get("tool_input")
            if not isinstance(tool_input, dict):
                tool_input = {}
            officer = (payload.get("shadow_decision") or {}).get("officer") or actor or "unknown"
            if officer == "unknown":
                continue                     # developer/CI session, not the fleet
            blob = json.dumps(tool_input, sort_keys=True)
            if any(m in blob for m in _FIXTURE_MARKERS):
                continue                     # pytest fixtures written into the live DB
            key = (officer, payload["tool_name"],
                   hashlib.sha1(blob.encode()).hexdigest(), str(ts or "")[:19])
            if key in seen:
                continue
            seen.add(key)
            fh.write(json.dumps({"officer": officer, "tool_name": payload["tool_name"],
                                 "tool_input": tool_input, "ts": ts}) + "\n")
            kept += 1
    con.close()
    return kept


def _load_corpus(paths: list[str]) -> tuple[list[dict], int]:
    records: list[dict] = []
    malformed = 0
    for p in paths:
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    malformed += 1
                    continue
                if not isinstance(rec, dict) or not rec.get("tool_name"):
                    malformed += 1
                    continue
                if not isinstance(rec.get("tool_input"), dict):
                    rec["tool_input"] = {}
                records.append(rec)
    return records, malformed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    # nargs="*" not "+": `--extract` BUILDS the corpus and has none to read.
    # Requiring one made the documented extract command fail with a usage
    # error unless a dummy path was passed.
    ap.add_argument("corpus", nargs="*", help="JSONL corpus file(s)")
    ap.add_argument("--extract", metavar="OUT.jsonl",
                    help="rebuild the corpus from the live shadow record "
                         "(read-only) and exit; pass the output path")
    ap.add_argument("--db", default=None,
                    help="event store for --extract "
                         "(default <CABINET_ROOT>/cabinet/cache/org-runtime.sqlite3)")
    ap.add_argument("--json", dest="json_out", help="write the full result object here")
    ap.add_argument("--top", type=int, default=25, help="rows per breakdown table")
    ap.add_argument("--examples", type=int, default=3, help="example calls per bucket")
    ap.add_argument("--no-cache", action="store_true",
                    help="disable the read_cell_state memo (slow; ~17ms/record)")
    ap.add_argument("--verify-cache", type=int, default=200, metavar="N",
                    help="prove the memo is exact on the first N records (0 = skip)")
    ap.add_argument("--policy-timeout", type=float, default=2.0, metavar="SEC",
                    help="per-policy wall-clock bound; a breach is REPORTED, not "
                         "swallowed (0 = unbounded, like the live hook)")
    args = ap.parse_args(argv)

    if args.extract:
        db = args.db or str(Path(os.environ.get("CABINET_ROOT") or _REPO_ROOT)
                            / "cabinet" / "cache" / "org-runtime.sqlite3")
        if not Path(db).is_file():
            print(f"FATAL: no event store at {db} — pass --db.", file=sys.stderr)
            return 2
        n = extract_corpus(db, args.extract)
        print(f"wrote {n} records to {args.extract} (read-only from {db})")
        return 0

    records, malformed = _load_corpus(args.corpus)
    if not records:
        print("FATAL: corpus is EMPTY — refusing to report a blast radius of 0 "
              "from zero records (that is the degenerate answer, not a safe "
              "flip).", file=sys.stderr)
        return 2

    root = os.environ.get("CABINET_ROOT") or str(_REPO_ROOT)
    policies = policy_engine.load_policies(root)
    matrix = next(
        (p for p in policies
         if isinstance(p, dict) and p.get("type") == "authority_matrix"),
        None,
    )
    if matrix is None:
        print("FATAL: no authority_matrix policy in the loaded stack — nothing "
              "to dry-run.", file=sys.stderr)
        return 3
    ceilings = tuple(matrix.get("hard_ceiling") or _CEILING_FALLBACK)

    # --- read-only enforcement, before a single record is evaluated ---------
    guards = _install_side_effect_guards()
    try:
        posture = policy_engine.resolve_gate_posture()
    except Exception:  # noqa: BLE001
        posture = "<unresolvable>"
    if not guards and posture != "guardian":
        print(f"FATAL: posture is {posture!r} and the gate's write paths could "
              f"not be neutered — refusing to run, because this measurement "
              f"would file needs and consume standing-grant budget.",
              file=sys.stderr)
        return 5

    # --- memo + its sensor -------------------------------------------------
    cache_verified = "skipped"
    if not args.no_cache:
        if args.verify_cache:
            if args.policy_timeout > 0:
                signal.signal(signal.SIGALRM, _raise_timeout)

            def _probe(r: dict) -> Any:
                try:
                    return _first_block(
                        policies, CANDIDATE_TYPES, str(r.get("tool_name") or ""),
                        r.get("tool_input") or {}, str(r.get("officer") or "unknown"),
                        args.policy_timeout)
                except EngineTimeout as exc:
                    return ("<timeout>", str(exc))

            sample = records[: args.verify_cache]
            uncached = [_probe(r) for r in sample]
            _install_cell_state_memo()
            cached = [_probe(r) for r in sample]
            if uncached != cached:
                print("FATAL: the read_cell_state memo changed a verdict on the "
                      "verification sample — it is not exact here. Re-run with "
                      "--no-cache.", file=sys.stderr)
                return 4
            cache_verified = f"exact on {len(sample)} records"
        else:
            _install_cell_state_memo()

    if args.policy_timeout > 0:
        signal.signal(signal.SIGALRM, _raise_timeout)
    budget = args.policy_timeout
    timeouts: Counter[str] = Counter()
    timeout_examples: list[dict] = []

    by_officer: Counter[str] = Counter()
    by_tool: Counter[str] = Counter()
    by_action_type: Counter[str] = Counter()
    by_risk: Counter[str] = Counter()
    by_officer_risk: Counter[tuple[str, str]] = Counter()
    examples: dict[str, list[dict]] = defaultdict(list)

    total = len(records)
    baseline_blocks = 0
    newly_blocked = 0
    by_kind: Counter[str] = Counter()
    already_blocked_examples: Counter[str] = Counter()

    progress_every = max(1, total // 20)
    for seen, rec in enumerate(records, 1):
        if seen % progress_every == 0:
            print(f"  ... {seen}/{total} records "
                  f"({100.0 * seen / total:.0f}%) — {newly_blocked} newly blocked "
                  f"so far", file=sys.stderr, flush=True)
        tool_name = str(rec.get("tool_name") or "")
        tool_input = rec.get("tool_input") or {}
        officer = str(rec.get("officer") or "unknown")

        try:
            base = _first_block(policies, BASELINE_TYPES, tool_name, tool_input,
                                officer, budget)
        except EngineTimeout as exc:
            policy_name = str(exc) or "?"
            timeouts[f"baseline:{policy_name}"] += 1
            if len(timeout_examples) < 5:
                probe = tool_input.get("command") or tool_input.get("file_path") or ""
                timeout_examples.append({
                    "arm": "baseline", "policy": policy_name, "officer": officer,
                    "tool_name": tool_name, "input_bytes": len(json.dumps(tool_input)),
                    "probe": str(probe)[:160],
                })
            continue
        if base is not None:
            baseline_blocks += 1
            already_blocked_examples[base[0]] += 1
            continue

        try:
            cand = _first_block(policies, CANDIDATE_TYPES, tool_name, tool_input,
                                officer, budget)
        except EngineTimeout as exc:
            policy_name = str(exc) or "?"
            timeouts[f"candidate:{policy_name}"] += 1
            continue
        if cand is None:
            continue

        newly_blocked += 1
        reason = cand[1]
        bucket = _risk_bucket(reason, ceilings)
        atype = _action_type(tool_name, tool_input)
        # THE distinction the enforcement plane could not express before
        # 2026-07-27: a hard ceiling (no auto path exists) vs a cell above the
        # bar (withheld, filed, grantable) vs a call the classifier cannot see
        # at all. Counting them as one number is what made the flip read as an
        # undifferentiated 75.66%.
        by_kind[policy_engine.decision_kind(reason) or "legacy_typed"] += 1

        by_officer[officer] += 1
        by_tool[tool_name] += 1
        by_action_type[atype] += 1
        by_risk[bucket] += 1
        by_officer_risk[(officer, bucket)] += 1

        if len(examples[bucket]) < args.examples:
            probe = tool_input.get("command") or tool_input.get("file_path") \
                or tool_input.get("path") or ""
            examples[bucket].append({
                "tool_name": tool_name,
                "officer": officer,
                "action_type": atype,
                "probe": str(probe)[:160],
                "reason": reason[:200],
            })

    # A timed-out record has NO verdict. Excluding it from the denominator is
    # the honest move: counting it as "allowed today" would quietly assert the
    # allow the EngineTimeout docstring says we never assert. Reported
    # separately so the gap is visible, never absorbed.
    # SENSOR-ON-THE-SENSOR. `by_kind` reads a field off the engine's return
    # value; a single `str()` anywhere on that path flattens every record to
    # "legacy_typed" and the report still prints a clean, plausible number.
    # That happened once. If the authority matrix is in the candidate set and
    # produced blocks, it is IMPOSSIBLE for none of them to carry a kind.
    if newly_blocked and "authority_matrix" in CANDIDATE_TYPES:
        if not (set(by_kind) - {"legacy_typed"}):
            print("FATAL: every newly-blocked record came back without a "
                  "verdict kind. The engine returns GateDecision (a str "
                  "subclass); something on the return path coerced it, so the "
                  "propose/gate split is UNMEASURED. Refusing to report.",
                  file=sys.stderr)
            return 3

    timed_out = sum(timeouts.values())
    allowed_today = total - baseline_blocks - timed_out
    pct = (100.0 * newly_blocked / allowed_today) if allowed_today else 0.0

    out = {
        "corpus_files": args.corpus,
        "records_total": total,
        "records_malformed_skipped": malformed,
        "cell_state_memo": cache_verified,
        "gate_posture": posture,
        "side_effect_guards": guards,
        "policy_timeout_sec": args.policy_timeout,
        "policy_timeouts": dict(timeouts.most_common()),
        "policy_timeout_examples": timeout_examples,
        "blocked_today_by_legacy_types": baseline_blocks,
        "records_without_a_verdict_timed_out": timed_out,
        "allowed_today": allowed_today,
        "newly_blocked": newly_blocked,
        "newly_blocked_pct_of_allowed_today": round(pct, 2),
        "newly_blocked_by_verdict_kind": dict(by_kind.most_common()),
        "newly_blocked_pct_hard_ceiling": round(
            (100.0 * by_kind.get("gate", 0) / allowed_today)
            if allowed_today else 0.0, 2),
        "baseline_types": sorted(BASELINE_TYPES),
        "candidate_types": sorted(CANDIDATE_TYPES),
        "by_officer": dict(by_officer.most_common()),
        "by_tool_name": dict(by_tool.most_common()),
        "by_action_type": dict(by_action_type.most_common()),
        "by_risk_class": dict(by_risk.most_common()),
        "by_officer_risk": {f"{o}|{r}": n for (o, r), n in by_officer_risk.most_common()},
        "examples_by_risk_class": dict(examples),
    }

    def table(title: str, counter: Counter, denom: int) -> None:
        print(f"\n## {title}")
        if not counter:
            print("  (none)")
            return
        width = max((len(str(k)) for k, _ in counter.most_common(args.top)), default=10)
        for key, n in counter.most_common(args.top):
            share = (100.0 * n / denom) if denom else 0.0
            print(f"  {str(key):<{width}}  {n:>7}  {share:>6.2f}%")

    print("=" * 72)
    print("AUTHORITY-MATRIX ENFORCEMENT DRY RUN")
    print("=" * 72)
    print(f"corpus files            : {', '.join(args.corpus)}")
    print(f"records total           : {total}")
    print(f"gate posture            : {posture}")
    print(f"side-effect guards      : {', '.join(guards) or 'NONE'}")
    print(f"malformed skipped       : {malformed}")
    print(f"blocked TODAY (legacy)  : {baseline_blocks}")
    print(f"no verdict (timed out)  : {timed_out}  (excluded from the denominator)")
    print(f"allowed TODAY           : {allowed_today}")
    print(f"NEWLY BLOCKED by flip   : {newly_blocked}  ({pct:.2f}% of what runs today)")
    if timeouts:
        print(f"POLICY TIMEOUTS         : {sum(timeouts.values())} "
              f"(>{args.policy_timeout}s in ONE policy — the live hook has no bound)")
        for k, n in timeouts.most_common(10):
            print(f"    {k:<48} {n:>7}")
        for ex in timeout_examples:
            print(f"    e.g. {ex['tool_name']}/{ex['officer']} "
                  f"({ex['input_bytes']}B): {ex['probe'][:110]}")

    table("newly blocked by officer", by_officer, newly_blocked)
    table("newly blocked by tool_name", by_tool, newly_blocked)
    table("newly blocked by action_type", by_action_type, newly_blocked)
    table("newly blocked by risk class", by_risk, newly_blocked)

    print("\n## examples per risk class")
    for bucket, rows in sorted(examples.items()):
        print(f"  [{bucket}]")
        for r in rows:
            print(f"    {r['tool_name']}/{r['officer']} ({r['action_type']}): {r['probe']}")
            print(f"      -> {r['reason']}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(out, indent=2, sort_keys=True),
                                       encoding="utf-8")
        print(f"\nwrote {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
