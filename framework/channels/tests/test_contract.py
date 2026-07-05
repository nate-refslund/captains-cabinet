"""AX-5 — the channel contract: UndoContract strictness, org-domain
classification (fail-closed), journaled send, declaration validation."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.channels import contract as C
from framework.channels.tests.conftest import write_channels_yml
from framework.events.emitter import replay


class RecordingAdapter(C.ChannelAdapter):
    """Minimal concrete adapter: records dispatches, outcome injectable."""

    name = "recorder"
    capabilities = frozenset({"send"})
    undo_contract = C.UndoContract.delete_window(60)

    def __init__(self, outcome="art-1", **kwargs):
        super().__init__(**kwargs)
        self.outcome = outcome
        self.calls = []

    def _dispatch_send(self, recipient, body, thread_id):
        self.calls.append((recipient, body, thread_id))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


# ---------------------------------------------------------------------------
# UndoContract
# ---------------------------------------------------------------------------

class TestUndoContract:
    def test_parse_round_trips_the_manifest_strings(self):
        for text in ("none", "delete_window(600)", "delete_window(172800)"):
            assert str(C.UndoContract.parse(text)) == text

    def test_none_is_not_undoable_window_is(self):
        assert not C.UndoContract.none().undoable
        assert C.UndoContract.delete_window(1).undoable

    @pytest.mark.parametrize("text", [
        "", " none", "None", "NONE", "delete_window()", "delete_window(-5)",
        "delete_window(1.5)", "delete_window(60) ", "delete-window(60)",
        "delete_window(60);none", None, 42,
    ])
    def test_parse_rejects_everything_else(self, text):
        with pytest.raises(ValueError):
            C.UndoContract.parse(text)

    def test_zero_second_window_rejected(self):
        # matches the schema pattern but is a meaningless undo — fail-closed
        with pytest.raises(ValueError):
            C.UndoContract.parse("delete_window(0)")

    def test_constructor_fail_closed(self):
        with pytest.raises(ValueError):
            C.UndoContract("none", 5)
        with pytest.raises(ValueError):
            C.UndoContract("delete_window")
        with pytest.raises(ValueError):
            C.UndoContract("delete_window", True)  # bool is not a window
        with pytest.raises(ValueError):
            C.UndoContract("forever")

    def test_equality_and_hash(self):
        a = C.UndoContract.delete_window(60)
        b = C.UndoContract.parse("delete_window(60)")
        assert a == b and hash(a) == hash(b)
        assert a != C.UndoContract.delete_window(61)
        assert C.UndoContract.none() != a
        assert a != "delete_window(60)"


# ---------------------------------------------------------------------------
# classify_recipient
# ---------------------------------------------------------------------------

class TestClassifyRecipient:
    ORG = frozenset({"acme.com"})

    def test_org_domain_is_internal(self):
        assert C.classify_recipient("bob@acme.com", self.ORG) == C.INTERNAL

    def test_subdomain_and_case_and_whitespace(self):
        assert C.classify_recipient(" Bob@Mail.ACME.com ", self.ORG) == C.INTERNAL

    def test_lookalike_domain_is_external(self):
        assert C.classify_recipient("bob@evilacme.com", self.ORG) == C.EXTERNAL

    def test_unknown_domain_is_external(self):
        assert C.classify_recipient("bob@other.com", self.ORG) == C.EXTERNAL

    @pytest.mark.parametrize("recipient", [
        "", "   ", "C0123CHANNEL", "no-at-sign", None, 42, ["a@acme.com"],
    ])
    def test_unmatchable_recipients_fail_closed_external(self, recipient):
        assert C.classify_recipient(recipient, self.ORG) == C.EXTERNAL

    def test_multiple_at_signs_use_the_real_domain(self):
        assert C.classify_recipient("a@b@acme.com", self.ORG) == C.INTERNAL
        assert C.classify_recipient("a@acme.com@evil.com", self.ORG) == C.EXTERNAL

    def test_empty_domain_set_classifies_everything_external(self):
        assert C.classify_recipient("bob@acme.com", frozenset()) == C.EXTERNAL


# ---------------------------------------------------------------------------
# load_org_domains — fail-closed matrix
# ---------------------------------------------------------------------------

class TestLoadOrgDomains:
    def test_absent_file_loads_empty(self, tmp_path):
        assert C.load_org_domains(root=tmp_path) == frozenset()

    def test_valid_file_loads_normalized(self, tmp_path):
        write_channels_yml(tmp_path, org_domains=[" .ACME.Com ", "beta.org"])
        assert C.load_org_domains(root=tmp_path) == {"acme.com", "beta.org"}

    def test_empty_list_is_valid_and_empty(self, tmp_path):
        write_channels_yml(tmp_path, org_domains=[])
        assert C.load_org_domains(root=tmp_path) == frozenset()

    @pytest.mark.parametrize("overrides", [
        {"extra": True},                      # unknown key
        {"version": 2},                       # wrong version
        {"version": True},                    # bool is not the integer 1
        {"org_domains": "acme.com"},          # not a list
        {"org_domains": [42]},                # non-string entry
        {"org_domains": ["a@b.com"]},         # @ in a domain
        {"org_domains": ["acme .com"]},       # whitespace inside
        {"org_domains": ["intranet"]},        # bare label, no TLD
        {"org_domains": ["acme.com/path"]},   # path separator
    ])
    def test_any_malformation_loads_empty(self, tmp_path, overrides):
        write_channels_yml(tmp_path, **overrides)
        assert C.load_org_domains(root=tmp_path) == frozenset()

    def test_missing_org_domains_key_is_corrupt(self, tmp_path):
        write_channels_yml(tmp_path, text="version: 1\n")
        assert C.load_org_domains(root=tmp_path) == frozenset()

    def test_unparseable_yaml_loads_empty(self, tmp_path):
        write_channels_yml(tmp_path, text="org_domains: [unclosed")
        assert C.load_org_domains(root=tmp_path) == frozenset()

    def test_symlinked_config_is_refused(self, tmp_path):
        real = tmp_path / "elsewhere.yml"
        real.write_text("version: 1\norg_domains: [acme.com]\n")
        d = tmp_path / "instance/config"
        d.mkdir(parents=True)
        os.symlink(real, d / "channels.yml")
        assert C.load_org_domains(root=tmp_path) == frozenset()

    def test_cabinet_root_env_is_honored(self, tmp_path, monkeypatch):
        write_channels_yml(tmp_path)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        assert C.load_org_domains() == {"acme.com"}

    def test_explicit_root_beats_env(self, tmp_path, monkeypatch):
        env_root = tmp_path / "env-root"
        arg_root = tmp_path / "arg-root"
        write_channels_yml(env_root, org_domains=["envonly.com"])
        write_channels_yml(arg_root, org_domains=["argonly.com"])
        monkeypatch.setenv("CABINET_ROOT", str(env_root))
        assert C.load_org_domains(root=arg_root) == {"argonly.com"}


# ---------------------------------------------------------------------------
# ChannelAdapter.send — journaled, fail-closed
# ---------------------------------------------------------------------------

class TestChannelAdapterSend:
    def _dispatched(self):
        return replay(event_types=["outbox_dispatched"])

    def _failed(self):
        return replay(event_types=["outbox_failed"])

    def test_send_returns_artifact_and_journals(self):
        a = RecordingAdapter(org_domains={"acme.com"}, actor="tester")
        art = a.send("bob@acme.com", "hello world", thread_id="t-1")
        assert art == "art-1"
        assert a.calls == [("bob@acme.com", "hello world", "t-1")]
        events = self._dispatched()
        assert len(events) == 1
        ev = events[0]
        assert ev["actor"] == "tester"
        p = ev["payload"]
        assert p["kind"] == "channel_send"
        assert p["channel"] == "recorder"
        assert p["recipient"] == "bob@acme.com"
        assert p["thread_id"] == "t-1"
        assert p["audience"] == C.INTERNAL
        assert p["action_type"] == "internal_message"
        assert p["undo_contract"] == "delete_window(60)"
        assert p["artifact_id"] == "art-1"
        assert p["outbox_id"] == "art-1"
        assert p["body_sha256"] == hashlib.sha256(b"hello world").hexdigest()
        assert p["body_chars"] == 11

    def test_body_is_never_journaled(self):
        a = RecordingAdapter(org_domains={"acme.com"})
        a.send("bob@acme.com", "SECRET-BODY-CONTENT")
        dump = json.dumps(self._dispatched())
        assert "SECRET-BODY-CONTENT" not in dump

    def test_external_recipient_stamps_external_action_type(self):
        a = RecordingAdapter(org_domains={"acme.com"})
        a.send("eve@other.com", "hi")
        p = self._dispatched()[0]["payload"]
        assert p["audience"] == C.EXTERNAL
        assert p["action_type"] == "external_message"

    def test_transport_failure_journals_and_reraises(self):
        a = RecordingAdapter(outcome=RuntimeError("boom"),
                             org_domains={"acme.com"})
        with pytest.raises(RuntimeError, match="boom"):
            a.send("bob@acme.com", "hi")
        assert self._dispatched() == []
        failed = self._failed()
        assert len(failed) == 1
        p = failed[0]["payload"]
        assert p["kind"] == "channel_send"
        assert p["error"].startswith("RuntimeError")
        assert p["outbox_id"] == "unsent"

    @pytest.mark.parametrize("bad_artifact", ["", None, 42, b"art"])
    def test_bad_artifact_id_is_a_failed_send(self, bad_artifact):
        a = RecordingAdapter(outcome=bad_artifact, org_domains={"acme.com"})
        with pytest.raises(C.ChannelSendError, match="artifact id"):
            a.send("bob@acme.com", "hi")
        assert self._dispatched() == []
        assert len(self._failed()) == 1

    @pytest.mark.parametrize("recipient,body,thread_id", [
        ("", "hi", None),
        ("   ", "hi", None),
        (None, "hi", None),
        ("bob@acme.com", "", None),
        ("bob@acme.com", "  ", None),
        ("bob@acme.com", None, None),
        ("bob@acme.com", "hi", 42),
    ])
    def test_invalid_inputs_raise_without_dispatch_or_journal(
            self, recipient, body, thread_id):
        a = RecordingAdapter(org_domains={"acme.com"})
        with pytest.raises(C.ChannelSendError):
            a.send(recipient, body, thread_id)
        assert a.calls == []
        assert self._dispatched() == [] and self._failed() == []

    def test_journal_failure_never_masks_a_completed_send(self, monkeypatch, capsys):
        def exploding_emit(*_a, **_k):
            raise OSError("ledger disk gone")
        monkeypatch.setattr(C, "emit", exploding_emit)
        a = RecordingAdapter(org_domains={"acme.com"})
        assert a.send("bob@acme.com", "hi") == "art-1"  # no raise
        assert "WARN ledger journal failed" in capsys.readouterr().err

    def test_delete_default_is_capability_refused(self):
        a = RecordingAdapter(org_domains={"acme.com"})
        with pytest.raises(C.ChannelCapabilityError):
            a.delete("art-1")


# ---------------------------------------------------------------------------
# Adapter declaration — fail-closed at construction
# ---------------------------------------------------------------------------

class TestAdapterDeclaration:
    def test_unknown_capability_refused(self):
        class Bad(RecordingAdapter):
            capabilities = frozenset({"send", "teleport"})
        with pytest.raises(C.ChannelConfigError, match="teleport"):
            Bad(org_domains=set())

    def test_empty_name_refused(self):
        class Bad(RecordingAdapter):
            name = ""
        with pytest.raises(C.ChannelConfigError, match="name"):
            Bad(org_domains=set())

    def test_non_undo_contract_refused(self):
        class Bad(RecordingAdapter):
            undo_contract = "delete_window(60)"  # a string is not a contract
        with pytest.raises(C.ChannelConfigError, match="UndoContract"):
            Bad(org_domains=set())

    def test_org_domains_default_loads_from_instance_config(self, tmp_path):
        write_channels_yml(tmp_path, org_domains=["acme.com"])
        a = RecordingAdapter(root=tmp_path)
        assert a.org_domains == {"acme.com"}
        assert a.classify("bob@acme.com") == C.INTERNAL

    def test_no_config_classifies_everything_external(self, tmp_path):
        a = RecordingAdapter(root=tmp_path)  # no channels.yml under tmp
        assert a.org_domains == frozenset()
        assert a.classify("bob@acme.com") == C.EXTERNAL


class TestQueueDraftStub:
    def test_stub_raises_pointing_at_the_brain_bridge(self):
        stub = C.queue_draft_stub("teams")
        with pytest.raises(NotImplementedError) as ei:
            stub("someone@acme.com", "hi", None)
        msg = str(ei.value)
        assert "queue_draft" in msg
        assert "brain-bridge.md" in msg
