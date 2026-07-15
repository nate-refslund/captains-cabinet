"""The sole Telegram poller deterministically bridges onboarding to loopback."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "cabinet/scripts/officer-inbound-poller.py"
spec = importlib.util.spec_from_file_location("inbound_poller_onboarding", MODULE)
poller = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(poller)


class _Response:
    def __init__(self, status=200, body=b'{"ok":true,"handled":true,"delivered":true}'):
        self.status = status
        self._body = io.BytesIO(body)
    def getcode(self):
        return self.status
    def read(self, size=-1):
        return self._body.read(size)
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False


def _message(text="/onboard", update_id=7):
    return {
        "update_id": update_id,
        "message": {
            "message_id": 9,
            "from": {"id": 123},
            "chat": {"id": 123, "type": "private"},
            "text": text,
        },
    }


def test_intent_router_is_narrow_and_includes_callbacks():
    assert poller.is_onboarding_update(_message("/onboard status"))
    assert poller.is_onboarding_update(_message("orientation"))
    assert poller.is_onboarding_update({
        "callback_query": {"data": "onboard:continue", "message": {"chat": {"id": 123}}}
    })
    assert not poller.is_onboarding_update(_message("please onboard our new engineer"))
    assert not poller.is_onboarding_update(_message("ordinary Captain message"))


def test_forward_posts_exact_update_and_secret_to_loopback_only():
    seen = []
    update = _message("/onboard")

    def opener(request, timeout):
        seen.append((request, timeout))
        return _Response()

    result = poller.forward_onboarding_update(
        update,
        dashboard_url="http://127.0.0.1:3100",
        webhook_secret="fixture-webhook-secret",
        opener=opener,
    )
    assert result == poller.OnboardingForwardResult(handled=True, delivered=True)
    assert poller.onboarding_forward_disposition(result) == "ack"
    request, timeout = seen[0]
    assert request.full_url.endswith("/api/telegram/provisioning-webhook")
    assert json.loads(request.data) == update
    assert request.get_header("X-telegram-bot-api-secret-token") == "fixture-webhook-secret"
    assert timeout == 10


def test_forward_refuses_external_url_before_secret_egress():
    called = []
    result = poller.forward_onboarding_update(
        _message(),
        dashboard_url="https://attacker.example",
        webhook_secret="must-not-egress",
        opener=lambda *_a, **_k: called.append(True),
    )
    assert result == poller.OnboardingForwardResult(False, False)
    assert poller.onboarding_forward_disposition(result) == "fallback"
    assert called == []


def test_forward_unavailability_preserves_visible_chair_fallback():
    assert poller.forward_onboarding_update(
        _message(),
        dashboard_url="http://localhost:3100",
        webhook_secret="fixture",
        opener=lambda *_a, **_k: (_ for _ in ()).throw(OSError("down")),
    ) == poller.OnboardingForwardResult(False, False)
    assert poller.forward_onboarding_update(
        _message(),
        dashboard_url="http://localhost:3100",
        webhook_secret="",
        opener=lambda *_a, **_k: _Response(),
    ) == poller.OnboardingForwardResult(False, False)


def test_explicit_delivery_failure_retains_offset_for_canonical_retry():
    result = poller.forward_onboarding_update(
        _message(),
        dashboard_url="http://localhost:3100",
        webhook_secret="fixture",
        opener=lambda *_a, **_k: _Response(
            status=503,
            body=b'{"ok":false,"handled":true,"delivered":false,"retryable":true}',
        ),
    )
    assert result == poller.OnboardingForwardResult(True, False)
    assert poller.onboarding_forward_disposition(result) == "retry"


def test_http_error_body_preserves_explicit_delivery_failure():
    error = poller.urllib.error.HTTPError(
        "http://localhost:3100/api/telegram/provisioning-webhook",
        503,
        "Service Unavailable",
        None,
        io.BytesIO(b'{"ok":false,"handled":true,"delivered":false}'),
    )
    result = poller.forward_onboarding_update(
        _message(),
        dashboard_url="http://localhost:3100",
        webhook_secret="fixture",
        opener=lambda *_a, **_k: (_ for _ in ()).throw(error),
    )
    assert result == poller.OnboardingForwardResult(True, False)
    assert poller.onboarding_forward_disposition(result) == "retry"


def test_legacy_ok_without_explicit_delivery_is_not_acked():
    result = poller.forward_onboarding_update(
        _message(),
        dashboard_url="http://localhost:3100",
        webhook_secret="fixture",
        opener=lambda *_a, **_k: _Response(body=b'{"ok":true}'),
    )
    assert result == poller.OnboardingForwardResult(False, False)
    assert poller.onboarding_forward_disposition(result) == "fallback"
