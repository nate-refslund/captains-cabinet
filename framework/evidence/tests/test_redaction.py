"""Redaction coverage: secret and PII value shapes, key classes, unicode scrub.

Each test is a regression tooth for a reviewed defect: it fails on the
pre-fix redaction module and passes with the fix.  End-to-end tests assert
the property that matters — the sensitive bytes never reach any file in the
store, the Cabinet projection, or a Captain export — while the event itself
stays recorded and verifiable.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from framework.evidence import EvidenceRecorder
from framework.evidence.redaction import (
    SECRET_VALUE_RES,
    contains_secret_shape,
    sanitize,
    sanitize_string,
)
from framework.evidence.verifier import verify_trial

TRIAL = "REDACTION-001"

# A structurally real (fake) bot token: numeric id, colon, 35-char secret.
BOT_TOKEN = "8123456789:AAEhBOweik6ad9r_QXMENQjcrGbqCr4K-eo"
BOT_SECRET = BOT_TOKEN.split(":", 1)[1]
BOT_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

DB_URLS = (
    ("postgres", "postgres://admin:hunter2secret@db.example.com:5432/app", "hunter2secret"),
    ("redis-empty-user", "redis://:sup3rs3cretpw@cache.internal:6379/0", "sup3rs3cretpw"),
)


def _context(recorder: EvidenceRecorder, trial: str = TRIAL):
    return recorder.trace(trial, surface="test")


def _append_detail(recorder: EvidenceRecorder, detail: dict, **kwargs):
    return recorder.append(
        _context(recorder),
        phase="execution",
        status="started",
        actor={"kind": "system", "id": "redaction-test"},
        component={"name": "redaction-test", "version": "1"},
        detail=detail,
        **kwargs,
    )


def _store_text(root: Path) -> str:
    return "\n".join(
        path.read_text(errors="replace") for path in sorted(root.rglob("*")) if path.is_file()
    )


# --- Finding 7: URI userinfo credentials (scheme://user:password@host) -------


@pytest.mark.parametrize("url,password", [(u, p) for _, u, p in DB_URLS], ids=[i[0] for i in DB_URLS])
def test_uri_credentials_are_redacted_from_sanitize_output(url: str, password: str):
    clean, notes = sanitize_string(f"connect failed for {url} after 3 tries")
    assert password not in clean
    assert "secret_value" in notes
    assert contains_secret_shape(url) is True


def test_uri_credentials_keep_host_reviewable():
    clean, _ = sanitize_string("db url postgres://admin:hunter2secret@db.example.com:5432/app down")
    assert "hunter2secret" not in clean
    assert "admin" not in clean  # the whole userinfo goes, not just the password
    assert "db.example.com" in clean  # the event stays auditable


def test_uri_credentials_never_reach_ledger_projection_or_export(tmp_path: Path):
    recorder = EvidenceRecorder(tmp_path / "store")
    for _, url, _ in DB_URLS:
        _append_detail(recorder, {"action": f"connect {url}"})
    projection = json.dumps(recorder.cabinet_projection(TRIAL))
    recorder.export_bundle(TRIAL, tmp_path / "export")
    persisted = _store_text(tmp_path / "store")
    exported = _store_text(tmp_path / "export")
    for _, _, password in DB_URLS:
        assert password not in persisted
        assert password not in projection
        assert password not in exported
    assert verify_trial(tmp_path / "store", TRIAL)["ok"] is True


# --- Finding 8: bot token survives in URL form (/bot<id>:<secret>) -----------


def test_bot_token_in_url_form_is_redacted():
    clean, notes = sanitize_string(f"POST {BOT_URL} returned 502")
    assert BOT_SECRET not in clean
    assert "secret_value" in notes
    assert contains_secret_shape(BOT_URL) is True


def test_bot_token_url_never_reaches_ledger(tmp_path: Path):
    recorder = EvidenceRecorder(tmp_path)
    _append_detail(recorder, {"transport": f"POST {BOT_URL} failed"})
    assert BOT_SECRET not in _store_text(tmp_path)
    assert verify_trial(tmp_path, TRIAL)["ok"] is True


def test_path_substitution_cannot_uncover_a_secret():
    # The absolute-path rewrite must never leave a secret behind that the
    # first pattern pass missed; the value patterns re-run after it.
    clean, _ = sanitize_string(f"see https://api.telegram.org/bot{BOT_TOKEN}/x and /tmp/a/b")
    assert BOT_SECRET not in clean


# --- Finding 16: email PII, underscore-joined keywords, chat-id keys ---------


def test_email_values_are_redacted():
    clean, notes = sanitize_string("escalate to case-owner@example-mail.dk today")
    assert "case-owner@example-mail.dk" not in clean
    assert "@" not in clean
    assert "secret_value" in notes
    assert contains_secret_shape("ping person.name@example-mail.dk") is True


def test_underscore_joined_keyword_secret_is_redacted():
    line = "loaded aws_secret_access_key=wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY from env"
    clean, notes = sanitize_string(line)
    assert "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY" not in clean
    assert "secret_value" in notes
    assert contains_secret_shape(line) is True


def test_plain_boundary_keyword_secrets_still_redacted():
    # Guard: widening the keyword prefix to underscores must not lose the
    # boundaries the old \b caught (start, space, slash, quote, colon).
    for line in (
        "password=hunter2secret",
        "a password: hunter2secret",
        "/etc/password=hunter2secret read",
        '"api_key": "hunter2secret"',
    ):
        clean, _ = sanitize_string(line)
        assert "hunter2secret" not in clean, line


def test_chat_id_shaped_keys_are_redacted_and_flagged():
    safe, notes = sanitize(
        {"chat_id": 987654321, "telegram_chat_id": "987654321", "total_bytes": 4096}
    )
    assert safe["chat_id"] == "[REDACTED_SECRET_FIELD]"
    assert safe["telegram_chat_id"] == "[REDACTED_SECRET_FIELD]"
    assert safe["total_bytes"] == 4096  # counters stay auditable by design
    assert "secret_field" in notes
    assert contains_secret_shape({"chat_id": 987654321}) is True
    assert contains_secret_shape(safe) is False


def test_chat_id_never_reaches_ledger(tmp_path: Path):
    recorder = EvidenceRecorder(tmp_path)
    _append_detail(recorder, {"chat_id": 987654321, "reason_code": "notify_sent"})
    persisted = _store_text(tmp_path)
    assert "987654321" not in persisted
    assert "notify_sent" in persisted
    assert verify_trial(tmp_path, TRIAL)["ok"] is True


# --- Finding 17: every secret value shape is exercised end to end ------------

SECRET_SHAPES = (
    ("sk-token", "sk-abcdefghijklmnopqrstuvwxyz012345", "sk-abcdefghijklmnopqrstuvwxyz012345"),
    ("github-token", "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345", "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"),
    ("aws-access-key-id", "AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE"),
    ("bot-token-bare", BOT_TOKEN, BOT_SECRET),
    ("bot-token-url", BOT_URL, BOT_SECRET),
    ("pem-header", "-----BEGIN RSA PRIVATE KEY-----", "BEGIN RSA PRIVATE KEY"),
    ("bearer", "Bearer abcdef1234567890TOKEN", "abcdef1234567890TOKEN"),
    ("keyword-assignment", "password=correct-horse-battery", "correct-horse-battery"),
    ("keyword-underscore", "aws_secret_access_key=wJalrXUtnFEMIK7MDENG", "wJalrXUtnFEMIK7MDENG"),
    ("uri-credentials", "postgres://admin:hunter2secret@db.example.com/app", "hunter2secret"),
    ("uri-credentials-empty-user", "redis://:sup3rs3cretpw@cache.internal:6379/0", "sup3rs3cretpw"),
    ("email", "person.name@example-mail.dk", "person.name@example-mail.dk"),
)


def test_every_secret_value_pattern_is_covered_by_shapes():
    # Structural tooth: if a pattern is added to SECRET_VALUE_RES without a
    # shape here, this fails and forces coverage.
    matched: set[int] = set()
    for _, payload, _ in SECRET_SHAPES:
        for index, rx in enumerate(SECRET_VALUE_RES):
            if rx.search(payload):
                matched.add(index)
    assert matched == set(range(len(SECRET_VALUE_RES)))


@pytest.mark.parametrize("payload,sensitive", [(p, s) for _, p, s in SECRET_SHAPES], ids=[i[0] for i in SECRET_SHAPES])
def test_secret_shape_is_scrubbed_and_kept_out_of_the_ledger(tmp_path: Path, payload: str, sensitive: str):
    clean, notes = sanitize_string(f"observed {payload} during onboarding")
    assert sensitive not in clean
    assert "secret_value" in notes
    assert contains_secret_shape(payload) is True
    recorder = EvidenceRecorder(tmp_path)
    _append_detail(recorder, {"reason_code": "shape_probe", "observed": f"seen {payload}"})
    persisted = _store_text(tmp_path)
    assert sensitive not in persisted
    assert "shape_probe" in persisted  # the event itself is recorded
    assert verify_trial(tmp_path, TRIAL)["ok"] is True


# --- Finding 12: lone UTF-16 surrogates must not deny evidence ---------------


def test_lone_surrogate_value_is_scrubbed_and_annotated():
    clean, notes = sanitize_string("partial \ud83d emoji")
    clean.encode("utf-8")  # must not raise
    assert "\ud83d" not in clean
    assert "invalid_unicode" in notes


def test_surrogate_scrub_is_identity_on_valid_strings():
    for value in ("plain ascii", "æøå ✓ 🚀 valid astral", "tab\tand newline\n"):
        clean, notes = sanitize_string(value)
        assert clean == value
        assert notes == []


def test_lone_surrogate_event_is_recorded_not_refused(tmp_path: Path):
    recorder = EvidenceRecorder(tmp_path)
    first = _append_detail(
        recorder,
        {"reason_code": "unicode_probe", "no\ud800te": "value \udfff tail"},
    )
    second = _append_detail(recorder, {}, links=["evidence://x\ud800y"])
    assert "invalid_unicode" in first["redactions"]
    assert "invalid_unicode" in second["redactions"]
    events = recorder.read_events(TRIAL)
    assert [event["sequence"] for event in events] == [1, 2]
    # The stored bytes are strict UTF-8: nothing unencodable reached disk.
    (tmp_path / "trials" / TRIAL / "events.jsonl").read_bytes().decode("utf-8")
    assert verify_trial(tmp_path, TRIAL)["ok"] is True


# --- Review round 2: sanitize must never stall or brick the trial ------------

# Keyword-dense but secret-free: an unbounded backtracking tail in the keyword
# pattern turns this into minutes of regex work inside recorder.append.
REDOS_PAYLOAD = "token_" * 33000  # ~198 KB

# Truncation edges: the full string contains no secret shape, but cutting at
# MAX_STRING and appending the marker manufactures one ('…' supplies the word
# boundary).  The email edge straddles the cut after 'a@bb.com'; the AKIA edge
# ends its 16-char run exactly at the cut.
TRUNCATION_EDGES = (
    ("email-straddling-cut", "x" * 503 + " a@bb.como12345", "a@bb.com"),
    ("akia-at-cut", "y" * 491 + " AKIA" + "B" * 16 + "lowercase_tail", "AKIA" + "B" * 16),
)


def test_keyword_pattern_is_not_superlinear_on_dense_input():
    # Tooth for the ReDoS: quadratic backtracking took ~3 minutes on this
    # input; the bounded possessive tail completes in milliseconds.  The 2s
    # budget is ~50x the observed fixed cost, so the tooth is not flaky.
    start = time.perf_counter()
    clean, notes = sanitize_string(REDOS_PAYLOAD)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"sanitize_string stalled for {elapsed:.1f}s"
    assert "string_truncated" in notes  # the event itself is still recorded
    assert clean.endswith("…[TRUNCATED]")


def test_bounded_keyword_tail_still_matches_real_key_names():
    # Guard: the possessive bound must not lose the shapes it exists for.
    for line in (
        "aws_secret_access_key=wJalrXUtnFEMIK7MDENG",
        '"api_key": "hunter2secret"',
        "token=hunter2secret",
    ):
        clean, _ = sanitize_string(line)
        assert "hunter2secret" not in clean and "wJalrXUtnFEMIK7MDENG" not in clean, line


@pytest.mark.parametrize("payload,shape", [(p, s) for _, p, s in TRUNCATION_EDGES], ids=[i[0] for i in TRUNCATION_EDGES])
def test_truncation_cannot_manufacture_a_secret_shape(payload: str, shape: str):
    assert contains_secret_shape(payload) is False  # the full string is clean
    clean, notes = sanitize_string(payload)
    assert contains_secret_shape(clean) is False, clean[-60:]
    assert shape not in clean
    assert "string_truncated" in notes


@pytest.mark.parametrize("payload", [p for _, p, _ in TRUNCATION_EDGES], ids=[i[0] for i in TRUNCATION_EDGES])
def test_truncation_edge_does_not_brick_the_trial(tmp_path: Path, payload: str):
    # Tooth for the denial-of-evidence brick: a manufactured shape in a
    # stored row made the verifier refuse every later append on the trial.
    recorder = EvidenceRecorder(tmp_path)
    _append_detail(recorder, {"observed": payload})
    second = _append_detail(recorder, {"reason_code": "still_recording"})
    assert second["sequence"] == 2  # the trial keeps accepting real actions
    events = recorder.read_events(TRIAL)
    assert [event["sequence"] for event in events] == [1, 2]
    assert verify_trial(tmp_path, TRIAL)["ok"] is True
