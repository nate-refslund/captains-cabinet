"""Repo-root pytest fence — NO pytest run may write the live audit ledger.

WHY THIS EXISTS (2026-07-04 leak incident): framework/events/emitter.py's
JSONL write falls back to the DURABLE live ledger
(~/Library/Application Support/cabinet/events) when CABINET_EVENT_LOG_DIR is
unset. The Store SQLite mirror auto-skips under pytest
(emitter._write_to_store); the JSONL write did NOT — which is how 1,969
fidelity test-fixture rows (payload.subject == "abc1234567"; 1,996 by prep
time) leaked into the live audit ledger. Suites that fence themselves with a
per-test fixture (e.g. framework/events/tests/test_emitter.py) were fine, but
fixture-less tests, import-time emits, and subprocesses spawned by tests all
fell through to the live default. (Adversarial-review addendum, 2026-07-04:
the same suites DUAL-EMIT via framework/fidelity/fidelity_events.py, so the
same 1,996 rows also leaked into consequence-events-*.jsonl — the graduation
read path. framework/fidelity/consequence.py honours the same env var, so
this fence covers that family too; the purge script cleans both.)

Worse: the runtime launch EXPORTS CABINET_EVENT_LOG_DIR pointing AT the live
ledger (framework/env.py — "the runtime launch sets it"), so a pytest run
started from inside an officer session inherits the live path. That is why
this fence is UNCONDITIONAL — a set-only-when-unset fence would do nothing
exactly where the risk is highest.

Mechanics: pytest imports the rootdir conftest before collecting/importing
any test module, so overriding the env HERE (module import time, not a
fixture) fences:
  * every in-process emit — fixture-less tests and import-time emits included,
  * every subprocess a test spawns (the environment is inherited),
  * the sibling durable surfaces with the same fallback shape:
      - the undo journal (framework/frontdoor/action_undo.py, CABINET_UNDO_DIR),
      - the consequence ledger (framework/fidelity/consequence.py, which
        honours CABINET_EVENT_LOG_DIR like the emitter does).

Per-test isolation is NOT this file's job — suites keep their own
tmp_path/monkeypatch fixtures, which run later and take precedence. This is
the outermost fail-safe only.

LOAD-BEARING TWIN #1 — pytest.ini (repo root): without an ini anchor, an
invocation like `python3 -m pytest framework/ -q` (the CI shape,
.github/workflows/cabinet-ci.yml) computes rootdir at the ARG directory and
never loads this conftest. pytest.ini pins rootdir to the repo root so this
fence is on the conftest path for every in-repo invocation. Do not delete
one without the other.

LOAD-BEARING TWIN #2 — emitter-level redirect:
framework/events/emitter.py::_event_log_dir() also redirects to a temp dir
when PYTEST_CURRENT_TEST is set and CABINET_EVENT_LOG_DIR is unset. That
layer catches any pytest invocation this conftest cannot see (e.g. a future
out-of-tree ini that re-cuts confcutdir). Keep both.

The purge of the already-leaked rows is a separate, Captain-gated one-shot:
cabinet/scripts/ledger-purge-testrows.sh — it REFUSES to run unless this
fence file exists (purging before the fence lands just invites the same rows
straight back).
"""

from __future__ import annotations

import os
import tempfile

# One fresh sandbox per pytest session (mkdtemp => mode 0700). Session-scoped
# on purpose: a single stable pair of paths means emit-then-replay style tests
# and test-spawned subprocesses all agree on where the sandboxed ledger lives
# for the duration of the run, while distinct pytest sessions never share
# state through a fixed path.
_SESSION_SANDBOX = tempfile.mkdtemp(prefix="cabinet-pytest-session-")

# UNCONDITIONAL override — see module docstring for why respecting a pre-set
# value would defeat the fence (officer sessions export the LIVE path).
os.environ["CABINET_EVENT_LOG_DIR"] = os.path.join(_SESSION_SANDBOX, "events")
os.environ["CABINET_UNDO_DIR"] = os.path.join(_SESSION_SANDBOX, "undo")

# Bare-root collection sweep guard (2026-07-07): officers/ holds gitignored
# runtime officer mirror checkouts (full-repo copies) — collecting them
# duplicates every conftest plugin registration and same-basename test module
# (ImportPathMismatchError). CI runs scoped suites and never hits this; the
# glob just keeps an ad-hoc repo-root `pytest` from drowning in mirror noise.
collect_ignore_glob = ["officers/*"]

import pytest  # noqa: E402  (after the env fence on purpose — fence first)


@pytest.fixture(autouse=True)
def _cabinet_root_env_fence():
    """Restore CABINET_ROOT around every test (cross-suite leak fence).

    framework/measurement role_evals/*.py and scenarios/*.py set
    os.environ["CABINET_ROOT"] = <tmpdir> inside their run() bodies with no
    restore; when those suites run earlier in the same pytest process, later
    suites (e.g. instance/flavor-a test_screenpipe_dispatch) resolve config
    under a dead tmp root and fail-close to Null bindings. Snapshot/restore
    per test so a leaked assignment can never cross a test boundary.
    """
    prev = os.environ.get("CABINET_ROOT")
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("CABINET_ROOT", None)
        else:
            os.environ["CABINET_ROOT"] = prev
