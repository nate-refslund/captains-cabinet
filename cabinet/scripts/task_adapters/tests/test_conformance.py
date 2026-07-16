"""Conformance-suite CI wiring (authoring kit, 2026-07-17).

THE teeth: ADAPTER_REGISTRY is auto-discovered here, so
  * registering implemented=True without a conformance fixture → red CI;
  * an implemented adapter whose fixture fails any check → red CI;
  * an implemented=False row whose skeleton lies (healthy health_check, or
    silently-succeeding methods) → red CI;
  * dropping a new TaskAdapter module into the package WITHOUT a registry
    row → red CI (the module scan below).

Calibration anchors: the in-memory reference adapter must PASS everything
(positive control) and the _template scaffold must FAIL everything (negative
control) — a suite that cannot tell them apart tests nothing.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).parent.parent.parent.parent.parent)
sys.path.insert(0, _ROOT)

from cabinet.scripts.task_adapters.base import (  # noqa: E402
    ADAPTER_REGISTRY,
    CanonicalTask,
    TaskAdapter,
    get_adapter,
)
from cabinet.scripts.task_adapters.conformance import (  # noqa: E402
    CHECKS,
    load_fixture,
    run_conformance,
)

_IMPLEMENTED = sorted(s for s, r in ADAPTER_REGISTRY.items() if r.implemented)
_SKELETONS = sorted(s for s, r in ADAPTER_REGISTRY.items() if not r.implemented)
_ALL_CHECK_IDS = {cid for cid, _ in CHECKS}


# ---------------------------------------------------------------------------
# implemented adapters: full conformance, auto-discovered
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slug", _IMPLEMENTED)
def test_implemented_adapter_passes_conformance(slug, tmp_path):
    spec = ADAPTER_REGISTRY[slug]
    assert spec.conformance_fixture, (
        f"{slug}: implemented=True but no conformance_fixture — every implemented "
        "adapter must prove itself against the suite "
        "(cabinet/runbooks/task-adapter-authoring.md §conformance)"
    )
    fixture = load_fixture(spec.conformance_fixture)
    report = run_conformance(fixture, tmp_dir=tmp_path)
    assert report.ok, report.summary()


def test_reference_adapter_is_a_registered_positive_anchor():
    """The suite's positive control must stay in the registry — deleting it
    silently would leave the suite uncalibrated."""
    spec = ADAPTER_REGISTRY.get("reference-inmemory")
    assert spec is not None and spec.implemented and not spec.selectable


# ---------------------------------------------------------------------------
# negative control: the template scaffold must FAIL every check
# ---------------------------------------------------------------------------


def test_conformance_fails_the_template_scaffold(tmp_path):
    from cabinet.scripts.task_adapters.conformance_fixtures import TemplateConformanceFixture

    report = run_conformance(TemplateConformanceFixture(), tmp_dir=tmp_path)
    assert not report.ok, (
        "the _template scaffold PASSED conformance — the suite has lost its "
        "teeth (a NotImplementedError scaffold must fail every check)"
    )
    assert report.failed_ids() == _ALL_CHECK_IDS, (
        f"template must fail EVERY check; only failed {sorted(report.failed_ids())} "
        f"of {sorted(_ALL_CHECK_IDS)}\n{report.summary()}"
    )


# ---------------------------------------------------------------------------
# skeletons: honest-not-implemented, never lying healthy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slug", _SKELETONS)
def test_skeleton_is_honest(slug):
    spec = ADAPTER_REGISTRY[slug]
    module = importlib.import_module(spec.module)
    adapter = getattr(module, spec.cls_name)(dict(spec.config_example))
    assert adapter.health_check() is not True, (
        f"{slug}: skeleton health_check() claims healthy — it would lie to the "
        "sync runner (a skeleton must return False until implemented)"
    )
    task = CanonicalTask(canonical_id="skel-001", title="skeleton probe")
    for call in (adapter.pull,
                 lambda: adapter.push(task),
                 lambda: adapter.delete("1"),
                 lambda: adapter.link("skel-001", "1")):
        with pytest.raises(NotImplementedError):
            call()


# ---------------------------------------------------------------------------
# registry teeth: no unregistered adapter modules, no harness leakage
# ---------------------------------------------------------------------------

_HARNESS_MODULES = {"base", "conformance", "conformance_fixtures"}


def test_every_adapter_module_is_registered():
    import cabinet.scripts.task_adapters.base as base_mod

    pkg_dir = Path(base_mod.__file__).parent
    registered_modules = {spec.module for spec in ADAPTER_REGISTRY.values()}
    for mod_info in pkgutil.iter_modules([str(pkg_dir)]):
        name = mod_info.name
        if name.startswith("_") or name in _HARNESS_MODULES:
            continue  # scaffolds (_template) + harness modules + tests pkg
        full = f"cabinet.scripts.task_adapters.{name}"
        module = importlib.import_module(full)
        for attr in vars(module).values():
            if (inspect.isclass(attr) and issubclass(attr, TaskAdapter)
                    and attr.__module__ == full and not inspect.isabstract(attr)):
                assert full in registered_modules, (
                    f"{full} defines TaskAdapter subclass {attr.__name__} with no "
                    "ADAPTER_REGISTRY row — register it (implemented=False while "
                    "building; implemented=True + conformance fixture when done). "
                    "See cabinet/runbooks/task-adapter-authoring.md"
                )


def test_template_module_stays_unregistered():
    assert all(
        spec.module != "cabinet.scripts.task_adapters._template"
        for spec in ADAPTER_REGISTRY.values()
    ), "_template is a scaffold to copy, never a registered adapter"


def test_registry_config_examples_instantiate():
    """config_example must satisfy each adapter's constructor validation —
    a stale example breaks the skeleton/conformance harness silently."""
    for slug, spec in ADAPTER_REGISTRY.items():
        module = importlib.import_module(spec.module)
        adapter = getattr(module, spec.cls_name)(dict(spec.config_example))
        assert adapter.destination == slug, (
            f"{slug}: adapter.destination {adapter.destination!r} != registry slug"
        )


# ---------------------------------------------------------------------------
# factory posture for harness rows
# ---------------------------------------------------------------------------


def test_get_adapter_refuses_the_harness_reference():
    with pytest.raises(ValueError, match="conformance-harness reference"):
        get_adapter({"tasks": {"system": "reference-inmemory", "config": {}}})


def test_unknown_system_error_points_at_the_runbook():
    with pytest.raises(ValueError, match="task-adapter-authoring"):
        get_adapter({"tasks": {"system": "not-a-real-system"}})
