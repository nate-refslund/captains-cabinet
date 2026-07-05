"""Probe deploy shell — config, guard, and per-source orchestration (2026-07-05).

The B2.3/B2.4/B2.5 probe modules were built import-only: each carries a
"DEPLOY TEMPLATE (Nate-gated)" comment describing the __main__ it would need —
build the real client, read the product repo(s)/app(s) from config, call
run_probe, guarded by CABINET_PROBES_ENABLED. The 2026-07-03 re-review found
exactly that: nothing wakes the stack. This module is the shared shell those
__main__ blocks (probe_github / probe_vercel / probe_sentry) delegate to, so
the config/guard/state plumbing exists ONCE and each probe stays its own
source-specific read-back rule (the B2.2 doctrine, lib.py:1-16).

CONFIG — instance/config/probes.yml (instance layer: per-deployment products;
see that file for the schema). A missing file, a missing checkout, or an empty
API key SKIPS the probe with a printed reason and emits NOTHING — a config gap
is fail-closed silence, never a fabricated observation and never an hc /fail
(hc /fail is reserved for a silent SOURCE while activity was expected —
lib.freshness_guard's page path inside run_probe).

WHY chdir per product: the injectable clients' git reads (GhClient.reverts /
local_commits_since, VercelClient.commit_message, SentryClient._commit_message)
are subprocess arg-lists that use the process CWD — the freshness signal and
the B2.1 trailer fallback must read the PRODUCT checkout, not the cabinet
repo. Each entrypoint is a one-shot launchd process, so a plain os.chdir per
product is safe (no concurrent probe shares the process).

SECRETS: tokens are read from the environment ONLY (VERCEL_API_KEY,
SENTRY_AUTH_TOKEN — sourced by cabinet/scripts/run-probes.sh from cabinet/.env
+ ~/.screenpipe/pipes/_shared/.env). Never argv, never printed, never in
plists. An empty value is ABSENT (cabinet/.env ships empty placeholders —
"empty env values never claim keys").

DRY-RUN: emit is an in-memory collector and hc a no-op — zero ledger writes,
zero healthchecks noise; external READS still happen (the probes are read-only
by construction), so a fenced dry-run is a true rehearsal of the join.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from framework.probes import lib

# Config path is INJECTED, not hardcoded — framework/ must not name the instance
# layer (three-layer gate: framework cannot reference instance/). The mechanism
# lives here; the per-deployment config path is supplied by the caller: an
# explicit --config arg, else the CABINET_PROBES_CONFIG env var that the
# cabinet/scripts glue (run-probes.sh) sets to the deployment's config (that
# script IS allowed to reference instance/). Unset + no arg → no config → every
# probe skips with a visible reason (fail-safe no-op). This is the plugin
# contract: framework = mechanism, instance = config, glue = injection.
CONFIG_PATH_ENV = "CABINET_PROBES_CONFIG"
# Sentry cross-cycle seen-state (probe_sentry.py deploy template names this
# exact location); dir env-overridable so tests never touch the durable copy.
STATE_DIR_ENV = "CABINET_PROBE_STATE_DIR"
STATE_DIR_DEFAULT = "~/Library/Application Support/cabinet"
SENTRY_SEEN_FILE = "probe-sentry-seen.json"


def probes_enabled() -> bool:
    """THE one-knob live guard (previously comment-only — now honored). Only
    the literal '1' enables; anything else is off (fail-closed default)."""
    return os.environ.get("CABINET_PROBES_ENABLED") == "1"


def load_config(path: Path | str | None = None) -> dict:
    """instance/config/probes.yml → dict. Missing/empty/broken file → {} (every
    probe then skips with a visible reason — config gaps never crash a cycle).
    yaml import deferred: the probe modules stay stdlib-only at import time."""
    if path:
        p = Path(path)
    elif os.environ.get(CONFIG_PATH_ENV):
        p = Path(os.environ[CONFIG_PATH_ENV])
    else:
        return {}                       # no injected config → no products → no-op
    try:
        import yaml   # deferred — same posture as run_action_lane.py:160
        data = yaml.safe_load(p.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — absent/corrupt config = no products = no-op run
        return {}


def _state_path() -> Path:
    return Path(os.path.expanduser(
        os.environ.get(STATE_DIR_ENV, STATE_DIR_DEFAULT))) / SENTRY_SEEN_FILE


def load_sentry_seen() -> dict:
    """Prior cycle's per-version last-event map ({project: {version: ts}}).
    Missing/corrupt state → {} — first sighting reads as not-advanced, so the
    frozen-feed guard stays conservative (probe_sentry._advanced:163)."""
    try:
        data = json.loads(_state_path().read_text())
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def save_sentry_seen(seen: dict) -> None:
    """Persist the updated seen-map. Best-effort: a failed save costs one
    conservative cycle (everything reads not-advanced next run), never a crash."""
    try:
        p = _state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(seen, sort_keys=True))
    except Exception as e:  # noqa: BLE001
        print(f"probe-sentry: seen-state save failed ({e!r}) — next cycle conservative")


def _collector():
    """(probe_emit, sink) for dry runs. CRITICAL: a probe's ``emit`` param is
    ``lib.emit_outcome`` (the HIGH-level probe emit that joins, validates, and
    returns ``{emitted: bool, ...}`` which run_probe then inspects), NOT the
    low-level ledger writer. So the collector must PRESERVE that contract — it
    wraps lib.emit_outcome with the inner ledger write redirected to a sink, so
    the real join/validate still runs and the proper dict is returned, but
    nothing reaches the ledger. (A bare ``def f(**ev): sink.append(ev)`` returns
    None and crashes run_probe's ``res.get('emitted')`` the moment any artifact
    actually joins — caught by the 2026-07-05 self-review.)"""
    sink: list[dict] = []

    def _low_emit(**ev):        # stands in for emit_consequence — captures, no write
        sink.append(ev)

    def probe_emit(**kw):
        return lib.emit_outcome(emit=_low_emit, **kw)
    return probe_emit, sink


def _noop_hc(slug: str, fail: bool = False) -> str:
    return "dry-run-no-ping"


# --- per-source orchestration (client_factory injectable — tests NEVER build
# --- the real clients; the __main__ blocks pass the real classes) ------------

def run_github_products(cfg: dict, *, client_factory: Callable[..., Any],
                        emit: Callable[..., Any] | None = None,
                        hc: Callable[..., Any] | None = None,
                        chdir: Callable[[str], None] = os.chdir,
                        rows: list | None = None) -> list[dict]:
    from framework.probes import probe_github
    out: list[dict] = []
    for entry in cfg.get("github") or []:
        repo, checkout = entry.get("repo"), entry.get("checkout")
        if not repo:
            out.append({"entry": entry, "skipped": "no repo slug"})
            continue
        if not checkout or not Path(checkout).is_dir():
            # No checkout ⇒ no git freshness signal / trailer fallback ⇒ the
            # probe cannot honor its own silent-source guard — skip, no verdict.
            out.append({"repo": repo, "skipped": f"checkout missing: {checkout}"})
            continue
        chdir(checkout)
        res = probe_github.run_probe(
            repo=repo, client=client_factory(), rows=rows,
            emit=emit or lib.emit_outcome, hc=hc or lib.hc_ping)
        out.append({"repo": repo, **{k: res[k] for k in ("fresh", "emitted", "skipped")}})
    return out


def run_vercel_products(cfg: dict, *, client_factory: Callable[..., Any],
                        emit: Callable[..., Any] | None = None,
                        hc: Callable[..., Any] | None = None,
                        chdir: Callable[[str], None] = os.chdir,
                        rows: list | None = None) -> list[dict]:
    from framework.probes import probe_vercel
    out: list[dict] = []
    if not os.environ.get("VERCEL_API_KEY"):
        # Empty placeholder = absent key = probe-wide skip (never a blind read
        # that 403s into an empty list and false-pages freshness).
        return [{"skipped": "VERCEL_API_KEY unset/empty — probe disabled this run"}]
    for entry in cfg.get("vercel") or []:
        app, checkout = entry.get("app"), entry.get("checkout")
        if not app:
            out.append({"entry": entry, "skipped": "no app name"})
            continue
        if not checkout or not Path(checkout).is_dir():
            out.append({"app": app, "skipped": f"checkout missing: {checkout}"})
            continue
        chdir(checkout)
        res = probe_vercel.run_probe(
            product=app, client=client_factory(), rows=rows,
            emit=emit or lib.emit_outcome, hc=hc or lib.hc_ping)
        out.append({"app": app, **{k: res[k] for k in ("fresh", "emitted", "skipped")}})
    return out


def run_sentry_products(cfg: dict, *, client_factory: Callable[..., Any],
                        emit: Callable[..., Any] | None = None,
                        hc: Callable[..., Any] | None = None,
                        chdir: Callable[[str], None] = os.chdir,
                        rows: list | None = None,
                        persist_state: bool = True) -> list[dict]:
    from framework.probes import probe_sentry
    out: list[dict] = []
    if not os.environ.get("SENTRY_AUTH_TOKEN"):
        return [{"skipped": "SENTRY_AUTH_TOKEN unset/empty — probe disabled this run"}]
    sc = cfg.get("sentry") or {}
    org = sc.get("org")
    if not org:
        return [{"skipped": "sentry.org missing in probes.yml"}]
    seen_all = load_sentry_seen()
    for entry in sc.get("projects") or []:
        project, checkout = entry.get("project"), entry.get("checkout")
        if not project:
            out.append({"entry": entry, "skipped": "no project slug"})
            continue
        if not checkout or not Path(checkout).is_dir():
            out.append({"project": project, "skipped": f"checkout missing: {checkout}"})
            continue
        chdir(checkout)
        res = probe_sentry.run_probe(
            org=org, project=project, client=client_factory(org=org), rows=rows,
            prior_seen=seen_all.get(project) or {},
            emit=emit or lib.emit_outcome, hc=hc or lib.hc_ping)
        seen_all[project] = res.get("seen") or {}
        out.append({"project": project,
                    **{k: res[k] for k in ("fresh", "emitted", "skipped")}})
    if persist_state:
        save_sentry_seen(seen_all)
    return out


# --- the shared __main__ body -------------------------------------------------

def probe_main(source: str, run_fn: Callable[..., list],
               client_factory: Callable[..., Any],
               argv: list | None = None) -> int:
    """The thin, uniform entrypoint each probe module's __main__ calls.

    Live emits require CABINET_PROBES_ENABLED=1 (disabled exit is 0 — a
    declared state, not a failure). --dry-run bypasses the guard but swaps in
    the collector emit + no-op hc: external READS happen, ledger writes don't.
    Any unhandled exception → loud stderr + exit 1 + NO verdict (each emit is
    schema-validated before write, so a crash never leaves a half row)."""
    ap = argparse.ArgumentParser(description=f"{source} outcome probe (read-only)")
    ap.add_argument("--dry-run", action="store_true",
                    help="collector emit + no hc pings — zero writes")
    ap.add_argument("--config", default=None, help="alternate probes.yml (tests)")
    args = ap.parse_args(argv)

    if not args.dry_run and not probes_enabled():
        print(f"probe-{source}: disabled (CABINET_PROBES_ENABLED != '1') — nothing emitted")
        return 0

    cfg = load_config(args.config)
    kw: dict[str, Any] = {"client_factory": client_factory}
    collected: list | None = None
    if args.dry_run:
        emit_fn, collected = _collector()
        kw.update(emit=emit_fn, hc=_noop_hc)
        if source == "sentry":
            kw["persist_state"] = False   # a rehearsal never advances the feed clock
    try:
        results = run_fn(cfg, **kw)
    except Exception as e:  # noqa: BLE001 — fail-closed: error → no verdict, loud log
        print(f"probe-{source}: ERROR — no verdicts emitted ({e!r})", file=sys.stderr)
        return 1

    summary = {"probe": source,
               "mode": "dry-run" if args.dry_run else "live",
               "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "products": results}
    if collected is not None:
        summary["would_write"] = len(collected)
    print(json.dumps(summary, indent=2, default=str))
    return 0
