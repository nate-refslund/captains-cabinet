"""Broker-attested producer identity (Phase 2, A6 seam) — contracts.

Pins: freeze-once-per-process semantics (idempotent identical re-attest,
typed refusal on conflict), fail-closed accessors, defensive copies,
validation against the recorder vocabulary (actor kinds, id alphabet,
provenance shape, secret-shape refusal), the reserved ``attestation_mode``
detail key's registration + redaction survival + officer-projection
exclusion, and the module's posture: one-way imports, no emit surface, no
environment reads.  The process-global attestation is reset around every
test via monkeypatch so the suite never leaks a frozen identity.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from framework.evidence import (
    EvidenceRecorder,
    attest_process_identity,
    attestation_detail,
    attested_actor,
    attested_component,
    classification,
    is_attested,
)
from framework.evidence import identity as identity_mod
from framework.evidence.recorder import PROJECTION_ALLOWED_DETAIL, EvidenceError
from framework.evidence.redaction import (
    RAW_CONTENT_KEY_RE,
    REASONING_KEY_RE,
    SECRET_KEY_RE,
    sanitize,
)
from framework.evidence.verifier import verify_trial

PACKAGE_DIR = Path(identity_mod.__file__).resolve().parent


@pytest.fixture(autouse=True)
def _fresh_process_identity(monkeypatch):
    """Isolate the process-global attestation per test (and restore after)."""
    monkeypatch.setattr(identity_mod, "_ATTESTED", None)


def test_attest_freezes_identity_and_accessors_return_copies():
    assert is_attested() is False
    frozen = attest_process_identity(
        "system", "org-event-mirror", "org-event-mirror",
        component_version="1", component_commit="abc123",
    )
    assert is_attested() is True
    assert frozen == {
        "actor": {"kind": "system", "id": "org-event-mirror"},
        "component": {
            "name": "org-event-mirror", "version": "1", "commit": "abc123",
        },
        "mode": "process",
    }
    actor = attested_actor()
    component = attested_component()
    assert actor == {"kind": "system", "id": "org-event-mirror"}
    assert component == {
        "name": "org-event-mirror", "version": "1", "commit": "abc123",
    }
    # Defensive copies: mutating a returned dict never touches the frozen
    # identity (payloads must not be able to rewrite it by reference).
    actor["id"] = "forged"
    component["name"] = "forged"
    frozen["actor"]["kind"] = "captain"
    assert attested_actor() == {"kind": "system", "id": "org-event-mirror"}
    assert attested_component()["name"] == "org-event-mirror"


def test_reattest_identical_is_idempotent_and_different_refuses():
    attest_process_identity("system", "consequence-mirror", "consequence-mirror")
    # Identical values: idempotent no-op (a re-imported producer module may
    # attest again at startup).
    again = attest_process_identity(
        "system", "consequence-mirror", "consequence-mirror"
    )
    assert again["actor"] == {"kind": "system", "id": "consequence-mirror"}
    # Any differing value refuses: identity is frozen for the process.
    for kwargs in (
        dict(actor_kind="officer", actor_id="consequence-mirror",
             component_name="consequence-mirror"),
        dict(actor_kind="system", actor_id="another-producer",
             component_name="consequence-mirror"),
        dict(actor_kind="system", actor_id="consequence-mirror",
             component_name="another-component"),
        dict(actor_kind="system", actor_id="consequence-mirror",
             component_name="consequence-mirror", component_commit="fff999"),
    ):
        with pytest.raises(EvidenceError) as caught:
            attest_process_identity(
                kwargs.pop("actor_kind"), kwargs.pop("actor_id"),
                kwargs.pop("component_name"), **kwargs,
            )
        assert caught.value.code == "identity_conflict"
    # The frozen identity survived every refused attempt.
    assert attested_actor() == {"kind": "system", "id": "consequence-mirror"}


@pytest.mark.parametrize(
    ("actor_kind", "actor_id", "component_name", "code"),
    [
        ("root", "mirror", "mirror", "identity_actor_invalid"),
        ("", "mirror", "mirror", "identity_actor_invalid"),
        (None, "mirror", "mirror", "identity_actor_invalid"),
        ("system", "bad id!", "mirror", "identity_actor_invalid"),
        ("system", "", "mirror", "identity_actor_invalid"),
        ("system", 42, "mirror", "identity_actor_invalid"),
        ("system", "mirror", "bad name!", "identity_component_invalid"),
        ("system", "mirror", None, "identity_component_invalid"),
    ],
)
def test_invalid_attestations_refuse_typed(actor_kind, actor_id, component_name, code):
    with pytest.raises(EvidenceError) as caught:
        attest_process_identity(actor_kind, actor_id, component_name)
    assert caught.value.code == code
    assert is_attested() is False


def test_secret_shaped_or_malformed_provenance_refuses_at_the_seam():
    for kwargs in (
        {"component_version": "sk-" + "Ab1" * 12},   # provider key shape
        {"component_commit": "sk-" + "Ab1" * 12},
        {"component_version": "has spaces"},          # provenance alphabet
        {"component_commit": ""},
        {"component_version": None},
    ):
        with pytest.raises(EvidenceError) as caught:
            attest_process_identity("system", "mirror", "mirror", **kwargs)
        assert caught.value.code == "identity_component_invalid"
    assert is_attested() is False


def test_unattested_accessors_fail_closed():
    for accessor in (attested_actor, attested_component, attestation_detail):
        with pytest.raises(EvidenceError) as caught:
            accessor()
        assert caught.value.code == "identity_unattested"
    assert is_attested() is False


def test_attested_identity_records_verifies_and_never_reaches_officers(
    tmp_path: Path, monkeypatch,
):
    """End-to-end: attested identity rides append() and stays audit-only.

    The explicit attested component also proves the A10 point: with
    version/commit attested, the recorder's environment provenance fallback
    is never consulted, so a hostile env value cannot enter the event.
    """
    monkeypatch.setenv("CABINET_BUILD_VERSION", "evil value with spaces")
    monkeypatch.setenv("CABINET_GIT_COMMIT", "sk-" + "Ab1" * 12)
    attest_process_identity(
        "system", "org-event-mirror", "org-event-mirror",
        component_version="1", component_commit="abc123",
    )
    recorder = EvidenceRecorder(tmp_path)
    trial = "evt-orgmirror-20260717"
    event = recorder.append(
        recorder.trace(trial, surface="system"),
        phase="system",
        status="succeeded",
        actor=attested_actor(),
        component=attested_component(),
        detail={**attestation_detail(), "action": "mirror_receipt"},
    )
    assert event["actor"] == {"kind": "system", "id": "org-event-mirror"}
    assert event["component"] == {
        "name": "org-event-mirror", "version": "1", "commit": "abc123",
    }
    assert event["detail"]["attestation_mode"] == "process"
    assert event["detail"]["action"] == "mirror_receipt"
    # No redaction fired: the attested values are clean by validation and
    # the env fallback was never consulted.
    assert event["redactions"] == []
    assert verify_trial(tmp_path, trial)["ok"] is True
    # Never-a-score / officer boundary: the attestation stamp is dropped by
    # the fail-closed officer projection.
    record = recorder.cabinet_projection(trial)["records"][-1]
    assert "attestation_mode" not in record["detail"]
    assert record["detail"]["action"] == "mirror_receipt"


def test_attestation_key_is_registered_and_survives_redaction():
    key = identity_mod.ATTESTATION_DETAIL_KEY
    assert key == "attestation_mode"
    # Registered in the Phase-1 classification registry via its documented
    # pattern: producer-asserted today (R2 honesty caveat).
    assert key in classification.DETAIL_FIELD_CLASSIFICATION
    assert classification.classify_detail_key(key) == classification.PRODUCER_ASSERTED
    # Audit-only: never officer-projected.
    assert key not in PROJECTION_ALLOWED_DETAIL
    # The key name dodges every redaction key pattern and the value is
    # stored byte-exact.
    assert not SECRET_KEY_RE.search(key)
    assert not REASONING_KEY_RE.search(key)
    assert not RAW_CONTENT_KEY_RE.search(key)
    safe, notes = sanitize({key: identity_mod.ATTESTATION_MODE_PROCESS})
    assert safe == {key: "process"} and notes == []


def test_identity_is_a_one_way_import_seam_with_no_emit_surface():
    source = (PACKAGE_DIR / "identity.py").read_text(encoding="utf-8")
    # No emit surface: identity returns dicts only — it must never construct
    # a recorder, wrap append, grow a CLI, or read the environment (A10).
    assert "EvidenceRecorder" not in source
    assert "argparse" not in source and "def main" not in source
    assert "os.environ" not in source and "getenv" not in source
    # One-way coupling: Ring-0 evidence code never imports identity
    # (classification.py precedent) — and the evidence CLI never exposes it.
    for ring0 in ("recorder.py", "verifier.py", "redaction.py", "__main__.py"):
        ring0_source = (PACKAGE_DIR / ring0).read_text(encoding="utf-8")
        assert "from .identity" not in ring0_source, ring0
        assert "evidence.identity" not in ring0_source, ring0
        assert "import identity" not in ring0_source, ring0
