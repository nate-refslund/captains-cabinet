"""framework.outbound_identity — the cabinet's own outbound identity + the
machine-provenance disclosure.

EVIDENCE NOTE (read this before trusting the file). This module is BRAND NEW, so
"the test fails without the change" is worth almost nothing here: every arm
would fail pre-change with an ImportError, which proves the file is new and
nothing else. The real evidence in this suite is of two other kinds:

  * PROPERTY arms assert what the component EXISTS TO DELIVER — that a machine
    message reaching a human says so, and that the Captain's personal signature
    is not applied unless he explicitly asked for it — not internal bookkeeping.
  * GUARD-MUTATION arms (``TestGuardsAreLoadBearing``) each disable exactly ONE
    guard by monkeypatching the module datum it consults, and assert the
    protected property FLIPS. A guard that can be removed without any arm
    noticing is decoration; these arms are what prove it is not.

Every malformed-config arm additionally plants a VALID ``mode: captain`` beside
the malformation and asserts the resolved mode is ``cabinet``. That is the
discriminator between "the whole file was refused" (what fail-closed means) and
"the bad field was ignored" (a partial parse, which would let a typo silently
half-configure who the cabinet is) — both would otherwise look identical.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from framework import outbound_identity as oi


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

#: The config's location, stated once as a combined path segment. Tests build
#: fixtures through ``oi.config_path`` so they never hardcode the layout; the
#: arm below pins that resolver against this literal so the coupling cannot hide
#: a wrong path from both sides at once.
EXPECTED_SUFFIX = "instance/config/outbound-identity.yml"


def _write(root: Path, text: str) -> Path:
    p = oi.config_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


CAPTAIN_MODE_CFG = "version: 1\nidentity:\n  mode: captain\n"


class SigSpy:
    """Stands in for the adapter's captain-signature callable."""

    def __init__(self, marker="CAPTAIN-SIG", boom=False):
        self.calls = []
        self.marker = marker
        self.boom = boom

    def __call__(self, text, channel):
        self.calls.append((text, channel))
        if self.boom:
            raise RuntimeError("signature backend down")
        return text + "\n\n" + self.marker


# ---------------------------------------------------------------------------
# The default posture — what a deployment gets before it configures anything
# ---------------------------------------------------------------------------

class TestSafeDefault:
    def test_the_config_lives_where_the_captain_is_told_it_lives(self, tmp_path):
        assert oi.config_path(tmp_path).as_posix().endswith(EXPECTED_SUFFIX)
        assert oi.config_path(tmp_path).is_relative_to(tmp_path)

    def test_absent_config_resolves_to_the_safe_side(self, tmp_path):
        ident = oi.load(root=tmp_path)
        assert ident.source == "default"
        assert ident.mode == oi.MODE_CABINET      # NOT the captain
        assert ident.disclosure_enabled is True
        # nothing invented on the captain's behalf
        assert (ident.from_address, ident.reply_to, ident.credential_env,
                ident.signature, ident.display_name) == ("", "", "", "", "")

    def test_every_channel_discloses_including_ones_never_heard_of(self, tmp_path):
        ident = oi.load(root=tmp_path)
        for channel in ("email", "teams", "outlook", "slack", "carrier-pigeon", ""):
            out = oi.stamp("Hi Bo, shipping Tuesday.", channel, ident)
            assert oi.MACHINE_MARK in out, channel
            assert oi.has_disclosure(out, channel, ident), channel

    def test_captain_identity_needs_an_explicit_well_formed_opt_in(self, tmp_path):
        assert oi.signs_as_captain(oi.load(root=tmp_path)) is False
        _write(tmp_path, CAPTAIN_MODE_CFG)
        assert oi.signs_as_captain(oi.load(root=tmp_path)) is True

    def test_a_configured_deployment_still_discloses_under_captain_mode(self, tmp_path):
        """Signing as the captain does not buy silence: a machine-sent message
        says a machine sent it, whichever name closes it."""
        _write(tmp_path, CAPTAIN_MODE_CFG)
        ident = oi.load(root=tmp_path)
        assert oi.requires_disclosure("email", ident) is True


# ---------------------------------------------------------------------------
# Fail-closed parsing — a malformed file is REFUSED, never half-applied
# ---------------------------------------------------------------------------

class TestFailClosedParsing:
    @pytest.mark.parametrize("body,why", [
        ("version: 1\nmode: captain\nidentity:\n  mode: captain\n",
         "unknown TOP-level key"),
        ("version: 1\nidentity:\n  mode: captain\n  sign_as: nate\n",
         "unknown identity key"),
        ("version: 1\nidentity:\n  mode: captain\ndisclosure:\n  off: true\n",
         "unknown disclosure key"),
        ("version: 2\nidentity:\n  mode: captain\n", "unsupported version"),
        ("version: 1\nidentity:\n  mode: cap\n", "unknown mode value"),
        ("version: 1\nidentity:\n  mode: captain\ndisclosure:\n  text: '   '\n",
         "blank disclosure text — a kill switch dressed as a typo"),
        ("version: 1\nidentity:\n  mode: captain\ndisclosure:\n  enabled: 'yes'\n",
         "non-boolean enabled"),
        ("version: 1\nidentity:\n  mode: captain\ndisclosure:\n  placement: sideways\n",
         "unknown placement"),
        ("version: 1\nidentity:\n  mode: captain\ndisclosure:\n  channels:\n    email: nope\n",
         "non-boolean channel override"),
        ("version: 1\nidentity:\n  mode: captain\ndisclosure:\n  captain_surfaces:\n    - 7\n",
         "non-string captain surface"),
        ("version: 1\nidentity:\n  mode: captain\n  from_address: 42\n",
         "non-string address"),
        ("version: 1\nidentity: [captain]\n", "identity is not a mapping"),
        ("- version: 1\n", "document is not a mapping"),
        ("version: 1\nidentity:\n  mode: captain\n  : :\n", "unparseable yaml"),
        ("", "empty file"),
    ])
    def test_malformed_config_refuses_the_whole_file(self, tmp_path, body, why):
        _write(tmp_path, body)
        ident = oi.load(root=tmp_path)
        # The discriminator: every fixture above carries a VALID `mode: captain`
        # (except the ones where that is what is malformed). If the bad field had
        # merely been IGNORED, mode would be "captain" here.
        assert ident.mode == oi.MODE_CABINET, why
        assert ident.disclosure_enabled is True, why
        assert ident.source == "corrupt", why

    def test_a_symlinked_config_is_refused(self, tmp_path):
        """A planted symlink must not be able to turn disclosure off."""
        elsewhere = tmp_path / "attacker.yml"
        elsewhere.write_text(
            "version: 1\nidentity:\n  mode: captain\ndisclosure:\n  enabled: false\n",
            encoding="utf-8")
        planted = oi.config_path(tmp_path / "root")
        planted.parent.mkdir(parents=True)
        planted.symlink_to(elsewhere)
        ident = oi.load(root=tmp_path / "root")
        assert ident.source == "corrupt"
        assert ident.disclosure_enabled is True and ident.mode == oi.MODE_CABINET

    def test_well_formed_config_is_actually_honoured(self, tmp_path):
        """The counterweight to every refusal above: this IS a control surface,
        not a decoration. A valid file changes behaviour."""
        _write(tmp_path, (
            "version: 1\n"
            "identity:\n"
            "  mode: cabinet\n"
            "  display_name: Cabinet\n"
            "  from_address: cabinet@example.com\n"
            "  reply_to: replies@example.com\n"
            "  credential_env: CABINET_OUTBOUND_TOKEN\n"
            "  signature: |\n"
            "    --\n"
            "    Cabinet\n"
            "disclosure:\n"
            "  enabled: true\n"
            "  text: 'BOT: machine-written, for {captain}.'\n"
            "  placement: prepend\n"
            "  channels:\n"
            "    teams: false\n"
            "  captain_surfaces:\n"
            "    - chair\n"))
        ident = oi.load(root=tmp_path)
        assert ident.source == "config"
        assert ident.from_address == "cabinet@example.com"
        assert ident.credential_env == "CABINET_OUTBOUND_TOKEN"
        assert ident.disclosure_placement == oi.PLACEMENT_PREPEND
        assert oi.requires_disclosure("teams", ident) is False    # explicit off
        assert oi.requires_disclosure("chair", ident) is False    # captain surface
        assert oi.requires_disclosure("email", ident) is True     # unlisted => on
        assert oi.stamp("Body", "email", ident).startswith("BOT: ")


# ---------------------------------------------------------------------------
# The stamp — the property the module exists to deliver
# ---------------------------------------------------------------------------

class TestStamp:
    def test_is_idempotent(self, tmp_path):
        ident = oi.load(root=tmp_path)
        once = oi.stamp("Body", "email", ident)
        assert oi.stamp(once, "email", ident) == once
        assert once.count(oi.MACHINE_MARK) == 1

    def test_a_quoted_machine_glyph_cannot_suppress_it(self, tmp_path):
        """An inbound message that quotes the robot glyph (accidentally, or
        planted by a hostile correspondent) must not be able to make the cabinet
        skip its own disclosure. Idempotency keys on the RENDERED LINE, not on
        the presence of the mark."""
        ident = oi.load(root=tmp_path)
        hostile = "You wrote: %s Sent by an AI assistant acting for Someone Else." % oi.MACHINE_MARK
        out = oi.stamp(hostile, "email", ident)
        assert out != hostile
        assert oi.has_disclosure(out, "email", ident)

    def test_an_empty_body_becomes_just_the_disclosure(self, tmp_path):
        ident = oi.load(root=tmp_path)
        assert oi.stamp("   ", "email", ident) == oi.disclosure_line("email", ident)

    def test_non_string_input_never_raises(self, tmp_path):
        ident = oi.load(root=tmp_path)
        for junk in (None, 7, [], {}, object()):
            assert isinstance(oi.stamp(junk, "email", ident), str)

    def test_has_disclosure_is_false_on_an_unstamped_body(self, tmp_path):
        ident = oi.load(root=tmp_path)
        assert oi.has_disclosure("plain text", "email", ident) is False


# ---------------------------------------------------------------------------
# prepare_outbound — WHOSE name closes the message
# ---------------------------------------------------------------------------

class TestPrepareOutbound:
    def test_default_never_reaches_for_the_captains_signature(self, tmp_path):
        spy = SigSpy()
        out = oi.prepare_outbound("Body", "email", captain_signature=spy,
                                  ident=oi.load(root=tmp_path))
        assert spy.calls == []                      # not even called
        assert "CAPTAIN-SIG" not in out
        assert oi.MACHINE_MARK in out

    def test_captain_mode_uses_it_and_still_discloses(self, tmp_path):
        _write(tmp_path, CAPTAIN_MODE_CFG)
        spy = SigSpy()
        out = oi.prepare_outbound("Body", "email", captain_signature=spy,
                                  ident=oi.load(root=tmp_path))
        assert len(spy.calls) == 1
        assert "CAPTAIN-SIG" in out and oi.MACHINE_MARK in out

    def test_a_broken_signature_backend_never_blocks_the_disclosure(self, tmp_path):
        _write(tmp_path, CAPTAIN_MODE_CFG)
        out = oi.prepare_outbound("Body", "email",
                                  captain_signature=SigSpy(boom=True),
                                  ident=oi.load(root=tmp_path))
        assert "CAPTAIN-SIG" not in out             # fail-open, as before
        assert oi.MACHINE_MARK in out               # but never silent

    def test_cabinet_signature_is_email_only_and_idempotent(self, tmp_path):
        _write(tmp_path, "version: 1\nidentity:\n  signature: '-- Cabinet'\n")
        ident = oi.load(root=tmp_path)
        mail = oi.prepare_outbound("Body", "email", ident=ident)
        chat = oi.prepare_outbound("Body", "teams", ident=ident)
        assert "-- Cabinet" in mail and "-- Cabinet" not in chat
        assert oi.MACHINE_MARK in chat              # chat still discloses
        assert oi.apply_signature(mail, "email", ident) == mail


# ---------------------------------------------------------------------------
# Secret hygiene + no hardcoded identity
# ---------------------------------------------------------------------------

class TestHygiene:
    def test_credential_is_a_variable_name_and_its_value_is_never_read(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv("CABINET_OUTBOUND_TOKEN", "SENTINEL-SECRET-VALUE")
        _write(tmp_path, "version: 1\nidentity:\n"
                         "  credential_env: CABINET_OUTBOUND_TOKEN\n")
        ident = oi.load(root=tmp_path)
        headers = oi.sender_headers("email", ident)
        described = oi.describe(("email",), root=tmp_path)
        assert headers["credential_env"] == "CABINET_OUTBOUND_TOKEN"
        assert "SENTINEL-SECRET-VALUE" not in repr(headers)
        assert "SENTINEL-SECRET-VALUE" not in repr(described)
        assert "SENTINEL-SECRET-VALUE" not in repr(ident)

    def test_module_hardcodes_no_address(self):
        """Universal-base code must invent no address for anybody."""
        src = Path(oi.__file__).read_text(encoding="utf-8")
        # an email-shaped literal: local@domain.tld
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", src)

    def test_sender_headers_are_empty_until_configured(self, tmp_path):
        headers = oi.sender_headers("email", oi.load(root=tmp_path))
        assert headers["from_address"] == "" and headers["reply_to"] == ""
        assert headers["mode"] == oi.MODE_CABINET
        assert headers["disclosure_required"] is True


# ---------------------------------------------------------------------------
# GUARD MUTATIONS — each disables ONE guard and proves the property flips
# ---------------------------------------------------------------------------

class TestGuardsAreLoadBearing:
    def test_closed_top_key_set_is_what_refuses_an_unknown_key(
            self, tmp_path, monkeypatch):
        body = "version: 1\nmode: captain\nidentity:\n  mode: captain\n"
        _write(tmp_path, body)
        assert oi.load(root=tmp_path).source == "corrupt"      # guard ON
        monkeypatch.setattr(oi, "_TOP_KEYS", oi._TOP_KEYS | {"mode"})
        assert oi.load(root=tmp_path).source == "config"       # guard OFF -> flips

    def test_closed_identity_key_set_is_what_refuses_a_typo(
            self, tmp_path, monkeypatch):
        _write(tmp_path, "version: 1\nidentity:\n  mode: captain\n  sign_as: x\n")
        assert oi.load(root=tmp_path).mode == oi.MODE_CABINET
        monkeypatch.setattr(oi, "_IDENTITY_KEYS", oi._IDENTITY_KEYS | {"sign_as"})
        assert oi.load(root=tmp_path).mode == oi.MODE_CAPTAIN

    def test_version_pin_is_what_refuses_a_future_schema(
            self, tmp_path, monkeypatch):
        _write(tmp_path, "version: 2\nidentity:\n  mode: captain\n")
        assert oi.load(root=tmp_path).mode == oi.MODE_CABINET
        monkeypatch.setattr(oi, "_SUPPORTED_VERSION", 2)
        assert oi.load(root=tmp_path).mode == oi.MODE_CAPTAIN

    def test_mode_vocabulary_is_what_refuses_a_bogus_mode(
            self, tmp_path, monkeypatch):
        _write(tmp_path, "version: 1\nidentity:\n  mode: impersonate\n")
        assert oi.load(root=tmp_path).source == "corrupt"
        monkeypatch.setattr(oi, "MODES", oi.MODES | {"impersonate"})
        assert oi.load(root=tmp_path).mode == "impersonate"

    def test_realpath_containment_is_what_refuses_the_symlink(
            self, tmp_path, monkeypatch):
        elsewhere = tmp_path / "attacker.yml"
        elsewhere.write_text("version: 1\ndisclosure:\n  enabled: false\n",
                             encoding="utf-8")
        root = tmp_path / "root"
        planted = oi.config_path(root)
        planted.parent.mkdir(parents=True)
        planted.symlink_to(elsewhere)
        assert oi.load(root=root).disclosure_enabled is True
        monkeypatch.setattr(oi, "_is_real_config_path", lambda *a, **k: True)
        assert oi.load(root=root).disclosure_enabled is False

    def test_the_fallback_posture_is_where_every_failure_routes(
            self, tmp_path, monkeypatch):
        """load() must not hardcode its own answers — every failure path returns
        SAFE_DEFAULT, so swapping that constant swaps every failure's outcome."""
        permissive = oi.SAFE_DEFAULT._replace(mode=oi.MODE_CAPTAIN,
                                              disclosure_enabled=False)
        monkeypatch.setattr(oi, "SAFE_DEFAULT", permissive)
        monkeypatch.setattr(oi, "_CORRUPT_DEFAULT",
                            permissive._replace(source="corrupt"))
        assert oi.load(root=tmp_path).mode == oi.MODE_CAPTAIN        # absent file
        _write(tmp_path, "nope: 1\n")
        assert oi.load(root=tmp_path).disclosure_enabled is False    # corrupt file

    def test_unlisted_channels_default_to_disclosing(self, tmp_path):
        """The polarity itself: an unknown audience is a stranger, not the
        Captain. Flipping this default would silence every channel nobody
        remembered to list."""
        _write(tmp_path, "version: 1\ndisclosure:\n  channels:\n    email: true\n")
        ident = oi.load(root=tmp_path)
        assert oi.requires_disclosure("some-new-channel", ident) is True


# ---------------------------------------------------------------------------
# Never-raises contract (an egress path may not be broken by this module)
# ---------------------------------------------------------------------------

class TestNeverRaises:
    @pytest.mark.parametrize("body", [
        "\x00\x01binary", "version: 1\n\tbad indent", "%YAML 9.9\n---\n{}",
        "!!python/object:os.system []\n", "version: 1\nidentity: null\n",
        "version: 1\ndisclosure: null\n",
    ])
    def test_hostile_config_never_raises(self, tmp_path, body):
        _write(tmp_path, body)
        ident = oi.load(root=tmp_path)
        assert isinstance(ident, oi.OutboundIdentity)
        assert oi.stamp("Body", "email", ident)

    def test_unreadable_config_falls_back_not_up(self, tmp_path):
        p = _write(tmp_path, "version: 1\nidentity:\n  mode: captain\n")
        os.chmod(p, 0o000)
        try:
            if os.access(p, os.R_OK):        # root / permissive FS — no signal
                pytest.skip("this filesystem ignores chmod 000")
            ident = oi.load(root=tmp_path)
            assert ident.mode == oi.MODE_CABINET and ident.source == "corrupt"
        finally:
            os.chmod(p, 0o600)
