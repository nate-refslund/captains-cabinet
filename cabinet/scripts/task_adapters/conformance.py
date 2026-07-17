"""Adapter conformance kit — the machine bar every implemented adapter passes.

Pytest-free, stdlib-only. `tests/test_conformance.py` auto-discovers
ADAPTER_REGISTRY and runs `run_conformance()` against every row registered
`implemented=True`; a row without a passing fixture is a red CI. The suite
itself is calibrated by two anchors:

  * POSITIVE control — `reference_inmemory.InMemoryReferenceAdapter` must
    pass every check (a suite an honest implementation cannot pass is a
    broken suite);
  * NEGATIVE control — `_template.TemplateAdapter` must FAIL every check (a
    scaffold that passes proves the suite tests nothing).

Checks (ids are stable — cite them in reviews):

  C1 round-trip        push → pull returns the task with field fidelity
                       (incl. tags — reserved-marker filtering is exact-
                       match, so user tags like 'wip-cleanup' survive) +
                       external_id set; health_check is True with auth.
  C2 idempotent        re-pushing the same canonical_id returns the same
                       external_id and never duplicates; an updated push
                       overwrites in place INCLUDING priority downgrades
                       and role reassignment (stale managed labels must not
                       resurrect the old values on the next pull).
  C3 conflict rule     canonical wins: after an out-of-band mirror edit, the
                       next push restores canonical state. Fixtures with
                       `detects_conflicts=True` must also SURFACE the event
                       (counter via `conflict_count()`); transports that
                       cannot detect (stateless CLIs) declare why in
                       `conflict_detection_note` — recorded in the report,
                       visible debt, never silent.
  C4 backoff           rate-limited writes retry through
                       TaskAdapter._with_backoff with GROWING delays that
                       FLATTEN AT backoff_cap_s — the cap leg rides a steep
                       policy probe, because the default ladder (0.5·2³=4s)
                       never reaches the 30s cap on its own — and give up
                       with RateLimitedError after max_retries (bounded,
                       never an infinite spin). Server-supplied retry_after
                       is honored as a lower bound but CLAMPED at
                       retry_after_cap_s: an untrusted rate-limit reply
                       must never dictate an unbounded sleep. All observed
                       on an injected fake sleep — no real sleeping.
  C5 credential hygiene the token comes ONLY from env: a decoy planted in
                       config is ignored; the env sentinel never appears in
                       repr/str, logging output, stdout or stderr of a full
                       adapter cycle; `requires_env_token` fixtures must
                       fail-closed health_check without the env var.
  C6 injection inertness hostile tracker text (shell substitution,
                       backticks, SQL/jq metacharacters, ANSI/control bytes,
                       newline smuggling) is stored VERBATIM as inert data
                       and never executed: an embedded `$(touch <marker>)`
                       proves nothing ran, and the adapter module's source
                       must be free of shell=True / os.system.

SECURITY: fixtures fake their transports IN-PROCESS (no network, no real
`gh`, no disk beyond the provided tmp dir). Sentinels are generated per run.
"""

from __future__ import annotations

import ast
import contextlib
import importlib
import io
import logging
import os
import tempfile
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from cabinet.scripts.task_adapters.base import (
    CanonicalTask,
    RateLimitedError,
    TaskAdapter,
)


# ---------------------------------------------------------------------------
# Fixture contract
# ---------------------------------------------------------------------------


class ConformanceFixture(ABC):
    """What an adapter author supplies so the suite can drive their adapter.

    The fixture owns the FAKE transport: `make_adapter()` must return an
    adapter whose external system is an in-process double the fixture can
    tamper with and rate-limit. See conformance_fixtures.py for the two
    shipped examples (in-memory reference; subprocess-patched gh emulator).
    """

    #: human label for report lines
    adapter_label: str = "adapter"

    #: env var to plant with a per-run secret sentinel (None = no env secret)
    secret_env: str | None = None

    #: True → health_check() must NOT be True when secret_env is absent
    requires_env_token: bool = False

    #: True → the adapter surfaces out-of-band-edit conflicts via
    #: conflict_count(); False requires conflict_detection_note (honest debt)
    detects_conflicts: bool = False
    conflict_detection_note: str = ""

    def __init__(self) -> None:
        self.secret_sentinel = f"CONF-SECRET-{uuid.uuid4().hex}"

    # -- lifecycle hooks (default no-op) --
    def setup(self) -> None:  # start transport patches
        return None

    def teardown(self) -> None:  # stop transport patches
        return None

    def env_vars(self) -> dict[str, str]:
        """Env planted for the whole run (sentinel under secret_env)."""
        return {self.secret_env: self.secret_sentinel} if self.secret_env else {}

    # -- required surface --
    @abstractmethod
    def make_adapter(self) -> TaskAdapter:
        """Fresh adapter bound to a FRESH external double."""

    @abstractmethod
    def read_external(self, adapter: TaskAdapter, external_id: str) -> dict[str, Any]:
        """Raw mirror state: at least {'title', 'status'} (+ 'description'
        when the system stores one) — values EXACTLY as the external system
        holds them (verbatim; the injection check depends on it)."""

    @abstractmethod
    def tamper_external(self, adapter: TaskAdapter, external_id: str) -> None:
        """Simulate an operator editing the mirror out-of-band (change the
        title AND flip the item toward a closed/other state)."""

    @abstractmethod
    def arm_rate_limit(self, adapter: TaskAdapter, n: int) -> None:
        """Make the next n WRITE calls to the external double rate-limit."""

    # -- optional surface --
    def conflict_count(self, adapter: TaskAdapter) -> int:
        raise NotImplementedError(
            "fixture declares detects_conflicts=True but no conflict_count()"
        )


@dataclass
class ConformanceReport:
    adapter_label: str
    failures: list[tuple[str, str]] = field(default_factory=list)  # (check_id, message)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def failed_ids(self) -> set[str]:
        return {cid for cid, _ in self.failures}

    def summary(self) -> str:
        if self.ok:
            return f"{self.adapter_label}: conformance OK ({len(self.notes)} notes)"
        lines = [f"{self.adapter_label}: {len(self.failures)} conformance failure(s)"]
        lines += [f"  [{cid}] {msg}" for cid, msg in self.failures]
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# capture helpers
# ---------------------------------------------------------------------------


class _LogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D102
        with contextlib.suppress(Exception):
            self.lines.append(self.format(record))


@contextlib.contextmanager
def _captured_everything():
    """Capture root logging + stdout + stderr for hygiene assertions."""
    handler = _LogCapture()
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            yield lambda: "\n".join(handler.lines) + "\n" + out.getvalue() + "\n" + err.getvalue()
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)


@contextlib.contextmanager
def _planted_env(env: dict[str, str], *, drop: tuple[str, ...] = ()):
    saved: dict[str, str | None] = {}
    for key, value in env.items():
        saved[key] = os.environ.get(key)
        os.environ[key] = value
    for key in drop:
        saved.setdefault(key, os.environ.get(key))
        os.environ.pop(key, None)
    try:
        yield
    finally:
        for key, old in saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _task(cid: str, **overrides: Any) -> CanonicalTask:
    base = dict(
        canonical_id=cid,
        title=f"Conformance {cid}",
        description=f"Body for {cid} — deterministic fixture text.",
        status="in_progress",
        priority="high",
        tags=["conformance"],
    )
    base.update(overrides)
    return CanonicalTask(**base)


def _pull_by_cid(adapter: TaskAdapter, cid: str) -> list[CanonicalTask]:
    return [t for t in adapter.pull() if t.canonical_id == cid]


# ---------------------------------------------------------------------------
# checks — each returns a list of failure messages (empty = pass)
# ---------------------------------------------------------------------------


def _check_round_trip(fixture: ConformanceFixture, ctx: dict[str, Any]) -> list[str]:
    fails: list[str] = []
    adapter = fixture.make_adapter()
    if adapter.health_check() is not True:
        fails.append("health_check() is not True with auth env planted")
    # 'wip-cleanup'/'blocked-on-x' are prefix bait: user tags that merely
    # START with a reserved status marker must round-trip as ordinary data
    # (exact-match filtering only — a prefix filter silently eats them).
    task = _task("conf-rt-001", tags=["conformance", "wip-cleanup", "blocked-on-x"])
    external_id = adapter.push(task)
    if not isinstance(external_id, str) or not external_id:
        return fails + [f"push() must return a non-empty external_id str, got {external_id!r}"]
    matches = _pull_by_cid(adapter, task.canonical_id)
    if len(matches) != 1:
        return fails + [f"pull() returned {len(matches)} tasks for the pushed canonical_id (want 1)"]
    got = matches[0]
    for fld in ("title", "description", "status", "priority"):
        want, have = getattr(task, fld), getattr(got, fld)
        if want != have:
            fails.append(f"round-trip lost {fld}: pushed {want!r}, pulled {have!r}")
    if sorted(got.tags) != sorted(task.tags):
        fails.append(
            f"round-trip lost tags: pushed {task.tags!r}, pulled {got.tags!r} "
            "(reserved-marker filtering must be exact-match)"
        )
    if got.external_id != external_id:
        fails.append(f"pulled external_id {got.external_id!r} != push() return {external_id!r}")
    if not got.external_url:
        fails.append("pulled task carries no external_url")
    return fails


def _check_idempotent_resync(fixture: ConformanceFixture, ctx: dict[str, Any]) -> list[str]:
    fails: list[str] = []
    adapter = fixture.make_adapter()
    task = _task("conf-idem-001", assigned_role="quartermaster")
    first = adapter.push(task)
    second = adapter.push(task)
    if first != second:
        fails.append(f"re-push minted a new external_id ({first!r} → {second!r}) — not an upsert")
    if len(_pull_by_cid(adapter, task.canonical_id)) != 1:
        fails.append("re-push duplicated the task in the external system")
    # The updated push DOWNGRADES priority (high→normal) and REASSIGNS the
    # role: label/field-mapped trackers must strip the stale markers, or the
    # next pull() resurrects the old values (canonical must fully win).
    updated = _task("conf-idem-001", title="Conformance conf-idem-001 v2",
                    status="open", priority="normal", assigned_role="bosun")
    third = adapter.push(updated)
    if third != first:
        fails.append(f"updating push moved the task to a new external_id ({first!r} → {third!r})")
    matches = _pull_by_cid(adapter, task.canonical_id)
    if len(matches) != 1 or matches[0].title != updated.title:
        fails.append("updating push did not overwrite in place (duplicate or stale title)")
    if matches:
        got = matches[0]
        if got.priority != updated.priority:
            fails.append(
                f"priority downgrade did not win on update: pulled {got.priority!r} "
                f"(want {updated.priority!r}) — stale priority marker left behind?"
            )
        if got.assigned_role != updated.assigned_role:
            fails.append(
                f"role reassignment did not win on update: pulled {got.assigned_role!r} "
                f"(want {updated.assigned_role!r}) — stale role marker left behind?"
            )
    return fails


def _check_conflict_canonical_wins(fixture: ConformanceFixture, ctx: dict[str, Any]) -> list[str]:
    fails: list[str] = []
    adapter = fixture.make_adapter()
    task = _task("conf-conflict-001")
    external_id = adapter.push(task)
    fixture.tamper_external(adapter, external_id)
    adapter.push(task)  # canonical unchanged — must overwrite the tamper
    raw = fixture.read_external(adapter, external_id)
    if raw.get("title") != task.title:
        fails.append(
            f"canonical did NOT win: mirror title {raw.get('title')!r} after re-push "
            f"(want {task.title!r})"
        )
    pulled = _pull_by_cid(adapter, task.canonical_id)
    if not pulled or pulled[0].status != task.status:
        fails.append(
            "canonical did NOT win on status: pulled "
            f"{pulled[0].status if pulled else '<missing>'} (want {task.status!r})"
        )
    if fixture.detects_conflicts:
        count = fixture.conflict_count(adapter)
        if count < 1:
            fails.append("out-of-band edit was overwritten but never surfaced (conflict_count=0)")
    elif not fixture.conflict_detection_note:
        fails.append(
            "fixture declares detects_conflicts=False without a "
            "conflict_detection_note — undetectability must be explained, not silent"
        )
    return fails


def _check_backoff(fixture: ConformanceFixture, ctx: dict[str, Any]) -> list[str]:
    fails: list[str] = []
    adapter = fixture.make_adapter()
    sleeps: list[float] = []
    adapter._sleep = sleeps.append  # injected fake clock — the suite never really sleeps
    task = _task("conf-backoff-001")
    adapter.push(task)  # baseline create, no limits armed

    fixture.arm_rate_limit(adapter, 2)
    adapter.push(_task("conf-backoff-001", title="Conformance conf-backoff-001 v2"))
    if len(sleeps) != 2:
        fails.append(f"2 rate-limited replies should cause exactly 2 backoff sleeps, saw {len(sleeps)}")
    elif not (sleeps[1] > sleeps[0] > 0):
        fails.append(f"backoff delays must grow: {sleeps!r}")
    if any(s > adapter.backoff_cap_s for s in sleeps):
        fails.append(f"backoff exceeded cap {adapter.backoff_cap_s}s: {sleeps!r}")

    exhaustion = list(sleeps)
    fixture.arm_rate_limit(adapter, adapter.max_retries + 1)
    try:
        adapter.push(_task("conf-backoff-001", title="Conformance conf-backoff-001 v3"))
        fails.append(
            f"{adapter.max_retries + 1} consecutive rate limits must exhaust retries "
            "and raise RateLimitedError — push returned instead"
        )
    except RateLimitedError:
        new_sleeps = len(sleeps) - len(exhaustion)
        if new_sleeps != adapter.max_retries:
            fails.append(
                f"exhaustion path slept {new_sleeps}x (want exactly max_retries="
                f"{adapter.max_retries} — bounded, never an infinite spin)"
            )
    except Exception as exc:  # noqa: BLE001
        fails.append(f"exhaustion must raise RateLimitedError, got {type(exc).__name__}: {exc}")

    # CAP teeth (2026-07-17 review): on the conformance-pinned defaults the
    # ladder tops out at base·2³ = 4s, far below the 30s cap — the checks
    # above can never see the cap bind. Probe a STEEP policy (instance-level
    # override, base = cap/2) so attempt 2 reaches the cap and attempt 3
    # would DOUBLE PAST it if uncapped: delays must flatten AT backoff_cap_s.
    capped = fixture.make_adapter()
    cap_sleeps: list[float] = []
    capped._sleep = cap_sleeps.append
    capped.max_retries = 4  # pin the probe policy regardless of adapter overrides
    capped.backoff_base_s = capped.backoff_cap_s / 2
    fixture.arm_rate_limit(capped, 3)
    capped.push(_task("conf-backoff-cap-001"))
    if len(cap_sleeps) != 3:
        fails.append(
            f"steep-policy cap probe: 3 rate-limited replies should sleep 3x, "
            f"saw {len(cap_sleeps)} ({cap_sleeps!r})"
        )
    else:
        if any(s > capped.backoff_cap_s for s in cap_sleeps):
            fails.append(
                f"steep-policy probe exceeded backoff_cap_s={capped.backoff_cap_s}s: "
                f"{cap_sleeps!r} — the cap is not applied"
            )
        if cap_sleeps[2] != capped.backoff_cap_s:
            fails.append(
                "steep-policy probe: third delay must sit AT the cap "
                f"({capped.backoff_cap_s}s), saw {cap_sleeps!r} — delays must "
                "flatten once the ladder crosses backoff_cap_s"
            )

    # retry_after contract, probed straight through _with_backoff (fixture
    # transports need no retry_after seam; adapters inherit or override the
    # helper either way). Leg 1: a server-supplied retry_after ABOVE the
    # computed delay is honored as a lower bound.
    floor_adapter = fixture.make_adapter()
    floor_sleeps: list[float] = []
    floor_adapter._sleep = floor_sleeps.append
    server_wait = floor_adapter.backoff_base_s * 8 + 1.0
    floor_state = {"raised": False}

    def _limited_once_floor() -> str:
        if not floor_state["raised"]:
            floor_state["raised"] = True
            raise RateLimitedError("rate limited", retry_after=server_wait)
        return "ok"

    floor_adapter._with_backoff(_limited_once_floor, op="retry-after-floor")
    if len(floor_sleeps) != 1 or floor_sleeps[0] < server_wait:
        fails.append(
            f"server retry_after={server_wait}s must raise the computed delay "
            f"(lower bound), saw sleeps {floor_sleeps!r}"
        )

    # Leg 2: retry_after is UNTRUSTED tracker input — a hostile reply
    # claiming retry_after=1e9 must be clamped at retry_after_cap_s, never
    # dictate the sleep.
    clamp_adapter = fixture.make_adapter()
    clamp_sleeps: list[float] = []
    clamp_adapter._sleep = clamp_sleeps.append
    clamp_state = {"raised": False}

    def _limited_once_hostile() -> str:
        if not clamp_state["raised"]:
            clamp_state["raised"] = True
            raise RateLimitedError("rate limited", retry_after=1e9)
        return "ok"

    clamp_adapter._with_backoff(_limited_once_hostile, op="retry-after-clamp")
    ceiling = getattr(clamp_adapter, "retry_after_cap_s", clamp_adapter.backoff_cap_s)
    if len(clamp_sleeps) != 1 or clamp_sleeps[0] > ceiling:
        fails.append(
            f"hostile retry_after=1e9 must be clamped to retry_after_cap_s={ceiling}s "
            f"(untrusted input cannot dictate sleep duration), saw {clamp_sleeps!r}"
        )
    return fails


def _check_credential_hygiene(fixture: ConformanceFixture, ctx: dict[str, Any]) -> list[str]:
    fails: list[str] = []
    sentinel = fixture.secret_sentinel
    adapter = fixture.make_adapter()

    # A decoy token smuggled into config must be IGNORED (env is the only
    # credential source) and must never surface anywhere either.
    decoy = f"CONF-DECOY-{uuid.uuid4().hex}"
    adapter.project_config["token"] = decoy
    adapter.adapter_config["api_token"] = decoy
    token = adapter.auth_token()
    if token == decoy:
        fails.append("auth_token() accepted a config-embedded value — creds must be env-only")
    # Only adapters whose auth IS the env token must read it back (e.g. the
    # gh adapter authenticates via keychain; its fixture plants GH_TOKEN
    # purely as leak bait).
    if fixture.requires_env_token and fixture.secret_env and token != sentinel:
        fails.append(
            f"auth_token() did not read the planted env var {fixture.secret_env} "
            f"(got {'<none>' if token is None else '<other>'})"
        )

    with _captured_everything() as captured:
        text = repr(adapter) + " " + str(adapter)
        try:
            eid = adapter.push(_task("conf-hygiene-001"))
            adapter.pull()
            adapter.link("conf-hygiene-001", eid)
            adapter.delete(eid)
        except Exception as exc:  # noqa: BLE001
            fails.append(f"hygiene probe cycle failed: {type(exc).__name__}: {exc}")
        text += " " + captured()
    for name, value in (("secret sentinel", sentinel), ("config decoy", decoy)):
        if value in text:
            fails.append(f"{name} leaked into repr/logs/stdout/stderr")

    if fixture.requires_env_token and fixture.secret_env:
        with _planted_env({}, drop=(fixture.secret_env,)):
            bare = fixture.make_adapter()
            if bare.health_check() is True:
                fails.append(
                    f"health_check() claims healthy with {fixture.secret_env} unset — "
                    "must fail closed"
                )
    return fails


def _hostile_strings(marker: Path) -> dict[str, Any]:
    return {
        "title": f"pwn $(touch {marker}) `touch {marker}` ; rm -rf / | tee /dev/null &",
        "description": (
            "line1\nline2\r\n'; DROP TABLE officer_tasks;-- \" OR \"1\"=\"1 "
            "\x1b[31mansi\x07bell {p.__class__} %(x)s %s $(id)"
        ),
        "tags": ["conformance", "$(reboot)", "`shutdown`", "'; DELETE FROM t;--"],
    }


def _check_injection_inertness(fixture: ConformanceFixture, ctx: dict[str, Any]) -> list[str]:
    fails: list[str] = []
    adapter = fixture.make_adapter()
    marker = ctx["tmp_dir"] / "conformance-executed.flag"
    hostile = _hostile_strings(marker)
    task = _task("conf-inject-001", **hostile)

    external_id = adapter.push(task)
    if marker.exists():
        return fails + [
            "INJECTION EXECUTED: pushing hostile task text created the marker file — "
            "task text reached a shell"
        ]
    raw = fixture.read_external(adapter, external_id)
    if raw.get("title") != hostile["title"]:
        fails.append(
            "hostile title was transformed on the way to the external system "
            "(must be stored verbatim as inert data)"
        )
    pulled = _pull_by_cid(adapter, task.canonical_id)
    if not pulled or pulled[0].title != hostile["title"]:
        fails.append("hostile title did not round-trip verbatim through pull()")
    if pulled and pulled[0].description != hostile["description"]:
        fails.append("hostile description did not round-trip verbatim through pull()")
    if marker.exists():
        fails.append("INJECTION EXECUTED during pull()")

    # Belt: the adapter module's own CODE must never open a shell (AST scan —
    # a `shell=True` keyword or an `os.system(...)` call is a command-
    # injection sink; adapters must use subprocess argv lists only. Prose in
    # docstrings/comments is exempt: the scan walks calls, not text).
    module_file = type(adapter).__module__
    try:
        tree = ast.parse(Path(importlib.import_module(module_file).__file__).read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if (kw.arg == "shell" and isinstance(kw.value, ast.Constant)
                        and kw.value.value is True):
                    fails.append(f"adapter module passes shell=True (line {node.lineno})")
            func = node.func
            if (isinstance(func, ast.Attribute) and func.attr == "system"
                    and isinstance(func.value, ast.Name) and func.value.id == "os"):
                fails.append(f"adapter module calls os.system (line {node.lineno})")
    except Exception:  # noqa: BLE001 — unreadable source is not an injection failure
        pass
    return fails


CHECKS: list[tuple[str, Callable[[ConformanceFixture, dict[str, Any]], list[str]]]] = [
    ("C1", _check_round_trip),
    ("C2", _check_idempotent_resync),
    ("C3", _check_conflict_canonical_wins),
    ("C4", _check_backoff),
    ("C5", _check_credential_hygiene),
    ("C6", _check_injection_inertness),
]


def run_conformance(fixture: ConformanceFixture, tmp_dir: Path | str | None = None) -> ConformanceReport:
    """Run every check against the fixture's adapter; never raises — a check
    that blows up records its exception as that check's failure."""
    report = ConformanceReport(adapter_label=fixture.adapter_label)
    if not fixture.detects_conflicts and fixture.conflict_detection_note:
        report.notes.append(
            f"conflict detection not implemented: {fixture.conflict_detection_note}"
        )
    ctx: dict[str, Any] = {
        "tmp_dir": Path(tmp_dir) if tmp_dir else Path(tempfile.mkdtemp(prefix="conf-")),
    }
    fixture.setup()
    try:
        with _planted_env(fixture.env_vars()):
            for check_id, check in CHECKS:
                try:
                    for msg in check(fixture, ctx):
                        report.failures.append((check_id, msg))
                except Exception as exc:  # noqa: BLE001 — a crash IS a failure
                    report.failures.append(
                        (check_id, f"check crashed: {type(exc).__name__}: {exc}")
                    )
    finally:
        fixture.teardown()
    return report


def load_fixture(spec_path: str) -> ConformanceFixture:
    """Resolve a registry `conformance_fixture` ("module:Class") to an instance."""
    module_name, _, cls_name = spec_path.partition(":")
    module = importlib.import_module(module_name)
    cls = getattr(module, cls_name)
    fixture = cls()
    if not isinstance(fixture, ConformanceFixture):
        raise TypeError(f"{spec_path} is not a ConformanceFixture")
    return fixture
