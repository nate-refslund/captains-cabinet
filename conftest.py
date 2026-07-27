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
        honours CABINET_EVENT_LOG_DIR like the emitter does),
      - the attention feed (framework/attention/feed.py, CABINET_FEED_DIR —
        2026-07-16: fixture-less acting tests (test_actfirst_gate.py) wrote
        demote rows into the live feed via the same unset-env fallback),
      - the attention state dir (queue.py/verdicts.py/t2.py/gate.py/…,
        CABINET_ATTENTION_DIR — OVERWRITTEN files like queue.json, so a
        leak here corrupts live org state rather than accreting rows),
      - the draft queue (framework/acting/draft_queue.py,
        CABINET_DRAFT_QUEUE_DIR) and the evidence store
        (framework/evidence/recorder.py, CABINET_EVIDENCE_DIR) — same
        fallback shape, fenced 2026-07-16 before a third incident: both
        prior leaks (events 2026-07-04, feed 2026-07-16) began as a
        production write path added later, driven by an existing
        fixture-less test,
      - the captain-inbound archive (cabinet/scripts/
        officer-inbound-poller.py::archive_captain_dm,
        CABINET_CAPTAIN_INBOUND_DIR — fenced at birth, 2026-07-17),
      - the Captain's briefing-score store (cabinet/scripts/lib/
        briefing_score.py, CABINET_BRIEFING_SCORES_DIR — fenced at birth,
        2026-07-26). Append-only and tiny, but it is the ONLY record of what
        the Captain thought of his briefings: a fabricated row there does not
        pollute a log, it corrupts the one measurement the trial exists to
        take. The knob relocates the whole instance-memory directory, so a
        fenced run also reads the sandbox briefing archive rather than the
        live one — no test can invent a score for a real briefing,
      - the Captain's availability dial (cabinet/scripts/lib/
        captain_availability.py + framework.env.captain_availability_path(),
        CABINET_CAPTAIN_AVAILABILITY_FILE — fenced at birth, 2026-07-26, for
        exactly the reason the score store was). It is the ONLY record of how
        much of his day the cabinet may use: a fabricated row there does not
        pollute a log, it tells the whole org it may spend time the Captain
        never offered — and the pacing cap and the Captain-Seat emission bar
        both read it. Pointing it at a path inside the sandbox that is never
        created also makes every in-test resolve return the honest UNKNOWN
        rather than inheriting the live deployment's declaration,
      - the Captain's dated commitments (cabinet/scripts/lib/
        captain_dates.py + framework.env.captain_dates_path(),
        CABINET_CAPTAIN_DATES_FILE — fenced at birth, 2026-07-27, for the
        same reason as the two above). It is the ONLY record of the dates he
        set, and the briefing renders every open row: a fabricated row there
        would put a deadline nobody declared in front of the Captain twice a
        day, and a test that DELETED a row would silently drop a real one —
        which is the exact failure (a captain-set date absent from twelve
        days of briefings) this store exists to prevent. The path points
        inside the sandbox and is never created, so every in-test resolve
        returns the honest empty list,
      - the Captain-contact dead-man (framework/liveness/deadman.py,
        CABINET_LIVENESS_CONFIG — fenced at birth, 2026-07-25). The only
        OUTBOUND member of this list: it would send a fake heartbeat to the
        off-machine watcher rather than write a local file, and a fake
        heartbeat SUPPRESSES a real outage alarm.

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

The purge of already-leaked rows is a separate, Captain-gated one-shot per
family: cabinet/scripts/ledger-purge-testrows.sh (events + consequence,
2026-07-04) and cabinet/scripts/feed-purge-testrows.sh (attention feed,
2026-07-16) — each REFUSES to run unless this fence covers its env var
(purging before the fence lands just invites the same rows straight back).
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
os.environ["CABINET_FEED_DIR"] = os.path.join(_SESSION_SANDBOX, "feed")
os.environ["CABINET_ATTENTION_DIR"] = os.path.join(_SESSION_SANDBOX, "attention")
os.environ["CABINET_DRAFT_QUEUE_DIR"] = os.path.join(_SESSION_SANDBOX, "draft-queue")
os.environ["CABINET_EVIDENCE_DIR"] = os.path.join(_SESSION_SANDBOX, "evidence")
os.environ["CABINET_CAPTAIN_INBOUND_DIR"] = os.path.join(
    _SESSION_SANDBOX, "captain-inbound")
os.environ["CABINET_BRIEFING_SCORES_DIR"] = os.path.join(
    _SESSION_SANDBOX, "instance-memory")
os.environ["CABINET_CAPTAIN_AVAILABILITY_FILE"] = os.path.join(
    _SESSION_SANDBOX, "captain-availability.yml")
os.environ["CABINET_CAPTAIN_DATES_FILE"] = os.path.join(
    _SESSION_SANDBOX, "captain-dates.yml")

# Captain-contact dead-man (2026-07-25) — an OUTBOUND fence, not a write fence,
# and the first of its kind here. framework/liveness/deadman.py fires from inside
# channel.send and the inbound poller, so on a deployment that has configured
# instance/config/liveness.yml a plain `pytest framework/` would ping the real
# off-machine watcher with fabricated heartbeats — telling the watcher the
# cabinet is talking to its Captain when it is running a test suite. That is
# worse than the ledger leaks above: those polluted a record, this one would
# suppress a genuine outage alarm. Point the config resolver at a path inside the
# session sandbox that is never created, so every emit resolves `no-config` and
# no request leaves the box. Unconditional for the same reason as the rest: an
# officer session exports the live config path.
os.environ["CABINET_LIVENESS_CONFIG"] = os.path.join(
    _SESSION_SANDBOX, "liveness-absent.yml")

# Bare-root collection sweep guard (2026-07-07): officers/ holds gitignored
# runtime officer mirror checkouts (full-repo copies) — collecting them
# duplicates every conftest plugin registration and same-basename test module
# (ImportPathMismatchError). CI runs scoped suites and never hits this; the
# glob just keeps an ad-hoc repo-root `pytest` from drowning in mirror noise.
collect_ignore_glob = ["officers/*"]

import pytest  # noqa: E402  (after the env fence on purpose — fence first)


def _reset_channel_cache():
    """Clear the comms channel-adapter module cache (best-effort)."""
    try:
        import framework.comms.get_channel as _gc
        _gc._CACHE = None
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _cabinet_root_env_fence():
    """Two cross-suite leak fences around every test.

    (1) CABINET_ROOT: the measurement seed's role_evals/*.py and scenarios/*.py
    (shipped in presets/work/measurement/, installed into
    framework/measurement/) set os.environ["CABINET_ROOT"] = <tmpdir> inside
    their run() bodies with no restore; when those suites run earlier in the
    same pytest process, later suites (e.g. instance/flavor-a
    test_screenpipe_dispatch) resolve config under a dead tmp root and
    fail-close to Null bindings. Snapshot/restore per test so a leaked
    assignment can never cross a test boundary.

    (2) The comms channel adapter: framework.comms.get_channel caches the
    resolved ChannelAdapter in a module global (_CACHE). A suite that binds a
    non-default channel (e.g. test_channel_seam forcing the null adapter via
    get_channel(force=True)) leaves it cached — monkeypatch reverts the env, not
    the global — so a LATER suite that expects the real channel (e.g. test_t2's
    floor-page sweep) silently gets the NullAdapter and its send no-ops
    ("fallback-send-failed"). Reset _CACHE per test so a bound adapter never
    crosses a test boundary.
    """
    prev = os.environ.get("CABINET_ROOT")
    _reset_channel_cache()
    try:
        yield
    finally:
        _reset_channel_cache()
        if prev is None:
            os.environ.pop("CABINET_ROOT", None)
        else:
            os.environ["CABINET_ROOT"] = prev
