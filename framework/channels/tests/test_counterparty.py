"""Counterparty registry — the typed non-Captain party [framework.channels].

WHAT THIS ASSERTS. The property the registry exists to DELIVER is that the org
can say WHO it contacted, not merely which string it addressed: a send to a
registered party must land an identity in the audit ledger, and a send to an
unregistered one must land an honest absence. Class `TestTheDeliveredProperty`
is that assertion, driven end-to-end through the REAL adapter, the REAL loader
and a REAL config file — not through internal state.

The second property is that the registry can only ever NARROW: it never
changes `classify_recipient`, and `outbound_permitted` is False for every
recipient that is not simultaneously resolved, consented, and in scope — even
one sitting at a configured internal org domain.

VACUITY ARMING. This module is BRAND NEW, so "the test fails if you delete the
file" is worthless evidence. Every safety arm below is therefore paired with a
TARGETED SOURCE MUTANT in `TestMutantsBite`: the module source is re-exec'd
with exactly one guard disabled and the corresponding property is asserted to
FLIP. `_mutant` refuses to run unless its anchor matched exactly once, so a
no-op replacement (a mutation that silently did nothing and "passed") cannot
certify an arm. Each positive control — a good file loading, a granted+in-scope
send being permitted — is present precisely so the negative arms cannot pass
vacuously against a loader that returns empty for everything.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.channels import counterparty as C          # noqa: E402
from framework.channels.contract import (                 # noqa: E402
    ChannelAdapter, UndoContract, classify_recipient,
)

_SRC_PATH = Path(C.__file__).resolve()
_SRC = _SRC_PATH.read_text()

# The instance-config segments, SOURCED from the module under test rather than
# spelled here: the test can never drift from the real config path, and the
# bare path token the layer-separation gate greps for never appears in a
# framework file (the same statement contract.py/counterparty.py make).
_CFG_SEGMENTS = tuple(C._INST_CFG.split("/"))


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _entry(**overrides) -> dict:
    """A minimal VALID entry; overrides mutate exactly one field per arm."""
    base = {
        "kind": "person",
        "relationship": "customer",
        "handles": ["ada@acme.com"],
        "consent": "granted",
        "captain_scope": {"channels": ["teams"]},
    }
    base.update(overrides)
    return base


def write_registry(root: Path, text: "str | None" = None, **cfg) -> Path:
    """Materialize <root>/instance/config/counterparties.yml (raw `text` wins).

    Writes the REAL path the loader resolves, so every loader arm below runs
    through the shipped containment probe rather than around it.
    """
    d = root.joinpath(*_CFG_SEGMENTS)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "counterparties.yml"
    if text is not None:
        p.write_text(text)
        return p
    data = {"version": 1, "counterparties": {"ada": _entry()}}
    data.update(cfg)
    p.write_text(yaml.safe_dump(data))
    return p


class _Adapter(ChannelAdapter):
    """Concrete adapter over an in-memory transport (journal captured)."""

    name = "teams"
    capabilities = frozenset({"send"})
    undo_contract = UndoContract.none()
    internal_action_type = "internal_message"
    external_action_type = "external_message"

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.journalled: list = []

    def _dispatch_send(self, recipient, body, thread_id):
        return "artifact-1"

    def _journal(self, event_type, payload):
        self.journalled.append((event_type, payload))


@pytest.fixture()
def registry(tmp_path) -> dict:
    """One granted party (ada@acme.com, teams) loaded from a real file."""
    write_registry(tmp_path)
    reg = C.load_counterparties(tmp_path)
    assert reg, "positive control: the good registry must load non-empty"
    return reg


# ---------------------------------------------------------------------------
# 1. THE DELIVERED PROPERTY — the audit record names WHO, not just a string
# ---------------------------------------------------------------------------

class TestTheDeliveredProperty:
    def test_send_to_a_registered_party_journals_its_identity(self, tmp_path):
        """The headline: before this registry the ledger recorded a bare
        recipient string; now it records the standing relationship."""
        write_registry(tmp_path)
        a = _Adapter(org_domains=["acme.com"], root=tmp_path)
        a.send("ada@acme.com", "hello")

        assert len(a.journalled) == 1
        event_type, payload = a.journalled[0]
        assert event_type == "outbox_dispatched"
        assert payload["counterparty_id"] == "ada"
        assert payload["counterparty_consent"] == "granted"
        assert payload["counterparty_relationship"] == "customer"

    def test_send_to_an_unregistered_recipient_journals_honest_absence(
            self, tmp_path):
        write_registry(tmp_path)
        a = _Adapter(org_domains=["acme.com"], root=tmp_path)
        a.send("stranger@acme.com", "hello")

        _, payload = a.journalled[0]
        assert payload["counterparty_id"] is None
        assert payload["counterparty_consent"] == "unknown"
        assert payload["counterparty_relationship"] is None

    def test_a_failed_send_still_journals_the_identity(self, tmp_path):
        """A refused/failed outbound is exactly when knowing the counterparty
        matters — the failure row carries it too."""
        write_registry(tmp_path)

        class _Boom(_Adapter):
            def _dispatch_send(self, recipient, body, thread_id):
                raise RuntimeError("transport down")

        a = _Boom(org_domains=["acme.com"], root=tmp_path)
        with pytest.raises(RuntimeError):
            a.send("ada@acme.com", "hello")
        event_type, payload = a.journalled[0]
        assert event_type == "outbox_failed"
        assert payload["counterparty_id"] == "ada"

    def test_free_text_never_reaches_the_ledger(self, tmp_path):
        """display_name/notes are Captain-authored free text; audit fields
        stay closed-vocabulary identifiers so config can never inject prose
        into the ledger."""
        write_registry(tmp_path, counterparties={
            "ada": _entry(display_name="Ada L; DROP", notes="private note"),
        })
        a = _Adapter(org_domains=["acme.com"], root=tmp_path)
        a.send("ada@acme.com", "hello")
        blob = repr(a.journalled[0][1])
        assert "Ada L" not in blob
        assert "private note" not in blob
        assert "ada" == a.journalled[0][1]["counterparty_id"]

    def test_journalled_values_are_closed_vocabulary(self, registry):
        f = C.journal_fields("ada@acme.com", registry)
        assert C._ID_RE.match(f["counterparty_id"])
        assert f["counterparty_consent"] in (C.CONSENT_STATES | {C.CONSENT_UNKNOWN})
        assert f["counterparty_relationship"] in C.RELATIONSHIPS

    def test_adapter_exposes_the_resolved_party(self, tmp_path):
        write_registry(tmp_path)
        a = _Adapter(org_domains=["acme.com"], root=tmp_path)
        cp = a.counterparty("ada@acme.com")
        assert cp is not None and cp.id == "ada" and cp.is_consented
        assert a.counterparty("stranger@acme.com") is None


# ---------------------------------------------------------------------------
# 2. THE NARROWING INVARIANT — the registry never widens anything
# ---------------------------------------------------------------------------

class TestNeverWidens:
    def test_classification_is_untouched_by_the_registry(self, tmp_path):
        """`classify_recipient` is an ADDRESS property; the registry is a
        PARTY property. Registering (or not) a handle must not move a single
        recipient across the internal/external line."""
        write_registry(tmp_path)
        a = _Adapter(org_domains=["acme.com"], root=tmp_path)
        for rec in ("ada@acme.com", "stranger@acme.com", "who@other.com",
                    "opaque-chat-id", ""):
            assert a.classify(rec) == classify_recipient(rec, {"acme.com"})

    def test_action_type_is_untouched_by_the_registry(self, tmp_path):
        write_registry(tmp_path)
        a = _Adapter(org_domains=["acme.com"], root=tmp_path)
        # A consented external party is still `external`; a consented internal
        # one is still `internal` — consent is not an audience.
        assert a.action_type_for("ada@acme.com") == "internal_message"
        assert a.action_type_for("who@other.com") == "external_message"

    def test_granted_and_in_scope_is_permitted(self, registry):
        """POSITIVE CONTROL for the whole refusal battery below — without it
        every False assertion could pass against a broken predicate."""
        assert C.outbound_permitted("ada@acme.com", registry, "teams") is True

    @pytest.mark.parametrize("consent", ["pending", "withdrawn"])
    def test_unconsented_is_refused_even_in_scope(self, tmp_path, consent):
        write_registry(tmp_path, counterparties={
            "ada": _entry(consent=consent)})
        reg = C.load_counterparties(tmp_path)
        assert reg, "positive control: this file must still LOAD"
        assert C.outbound_permitted("ada@acme.com", reg, "teams") is False
        assert C.consent_of("ada@acme.com", reg) == consent

    def test_out_of_scope_channel_is_refused(self, registry):
        assert C.outbound_permitted("ada@acme.com", registry, "outlook") is False

    def test_empty_scope_is_refused(self, tmp_path):
        write_registry(tmp_path, counterparties={
            "ada": _entry(captain_scope={"channels": []})})
        reg = C.load_counterparties(tmp_path)
        assert reg, "positive control: an empty scope is a LEGAL file"
        assert C.outbound_permitted("ada@acme.com", reg, "teams") is False

    def test_unregistered_recipient_is_refused(self, registry):
        assert C.outbound_permitted("stranger@acme.com", registry, "teams") is False
        assert C.consent_of("stranger@acme.com", registry) == C.CONSENT_UNKNOWN

    def test_internal_org_domain_grants_nothing(self, registry):
        """Being inside the org's own domain is NOT consent. This is the
        widening path a naive implementation takes."""
        assert classify_recipient("stranger@acme.com", {"acme.com"}) == "internal"
        assert C.outbound_permitted("stranger@acme.com", registry, "teams") is False

    def test_empty_registry_permits_nobody(self):
        assert C.outbound_permitted("ada@acme.com", {}, "teams") is False
        assert C.consent_of("ada@acme.com", {}) == C.CONSENT_UNKNOWN

    @pytest.mark.parametrize("channel", [None, "", 123, "   ", "with space"])
    def test_non_channel_is_refused(self, registry, channel):
        assert C.outbound_permitted("ada@acme.com", registry, channel) is False

    def test_a_withdrawn_party_still_loads_but_permits_nothing(self, tmp_path):
        """Withdrawal is recorded, not erased: the party stays resolvable (so
        the ledger still names WHO) while permitting nothing."""
        write_registry(tmp_path, counterparties={
            "ada": _entry(),
            "bob": _entry(consent="withdrawn", handles=["bob@acme.com"]),
        })
        reg = C.load_counterparties(tmp_path)
        assert set(reg) == {"ada", "bob"}          # positive control
        assert C.resolve("bob@acme.com", reg).id == "bob"
        assert C.outbound_permitted("bob@acme.com", reg, "teams") is False
        assert C.outbound_permitted("ada@acme.com", reg, "teams") is True


# ---------------------------------------------------------------------------
# 3. FAIL-CLOSED LOADER — every guard, with a positive control alongside
# ---------------------------------------------------------------------------

class TestLoaderFailsClosed:
    def test_a_good_file_loads(self, tmp_path):
        """POSITIVE CONTROL for this whole class."""
        write_registry(tmp_path)
        reg = C.load_counterparties(tmp_path)
        assert set(reg) == {"ada"}
        cp = reg["ada"]
        assert cp.kind == "person" and cp.relationship == "customer"
        assert cp.handles == frozenset({"ada@acme.com"})
        assert cp.channels == frozenset({"teams"})

    def test_absent_file(self, tmp_path):
        assert C.load_counterparties(tmp_path) == {}

    def test_explicitly_empty_registry_is_legal(self, tmp_path):
        write_registry(tmp_path, counterparties={})
        assert C.load_counterparties(tmp_path) == {}

    def test_symlinked_config_is_refused(self, tmp_path):
        real = tmp_path / "elsewhere.yml"
        real.write_text(yaml.safe_dump(
            {"version": 1, "counterparties": {"ada": _entry()}}))
        d = tmp_path.joinpath(*_CFG_SEGMENTS)
        d.mkdir(parents=True, exist_ok=True)
        (d / "counterparties.yml").symlink_to(real)
        assert C.load_counterparties(tmp_path) == {}

    @pytest.mark.parametrize("text", [
        "version: 1\ncounterparties: {}\nextra: 1\n",      # unknown root key
        "version: 2\ncounterparties: {}\n",                # wrong version
        "version: true\ncounterparties: {}\n",             # bool version
        "counterparties: {}\n",                            # missing version
        "version: 1\n",                                    # missing map
        "version: 1\ncounterparties: []\n",                # not a mapping
        "just a string\n",                                 # not a mapping
        "version: 1\ncounterparties: {\n",                 # unparseable
    ])
    def test_malformed_root(self, tmp_path, text):
        write_registry(tmp_path, text=text)
        assert C.load_counterparties(tmp_path) == {}

    @pytest.mark.parametrize("entry", [
        _entry(kind="robot"),                              # off-vocab kind
        _entry(relationship="frenemy"),                    # off-vocab rel
        _entry(consent="maybe"),                           # off-vocab consent
        _entry(consent="unknown"),                         # absence answer declared
        _entry(consent=True),                              # non-string consent
        _entry(handles=[]),                                # empty handles
        _entry(handles="ada@acme.com"),                    # handles not a list
        _entry(handles=["ada acme"]),                      # whitespace handle
        _entry(handles=[123]),                             # non-string handle
        _entry(handles=["  "]),                            # blank handle
        _entry(captain_scope={"channels": ["teams"], "x": 1}),   # extra scope key
        _entry(captain_scope={"chans": ["teams"]}),        # wrong scope key
        _entry(captain_scope=["teams"]),                   # scope not a mapping
        _entry(captain_scope={"channels": "teams"}),       # channels not a list
        _entry(captain_scope={"channels": ["Teams Chat"]}),  # non-slug channel
        _entry(captain_scope={"channels": [7]}),           # non-string channel
        _entry(display_name=7),                            # non-string free text
        _entry(notes=[]),                                  # non-string free text
    ])
    def test_malformed_entry(self, tmp_path, entry):
        write_registry(tmp_path, counterparties={"ada": entry})
        assert C.load_counterparties(tmp_path) == {}

    @pytest.mark.parametrize("missing", [
        "kind", "relationship", "handles", "consent", "captain_scope"])
    def test_missing_required_entry_key(self, tmp_path, missing):
        e = _entry()
        e.pop(missing)
        write_registry(tmp_path, counterparties={"ada": e})
        assert C.load_counterparties(tmp_path) == {}

    def test_unknown_entry_key(self, tmp_path):
        write_registry(tmp_path, counterparties={
            "ada": dict(_entry(), tier="gold")})
        assert C.load_counterparties(tmp_path) == {}

    def test_entry_not_a_mapping(self, tmp_path):
        write_registry(tmp_path, counterparties={"ada": ["nope"]})
        assert C.load_counterparties(tmp_path) == {}

    @pytest.mark.parametrize("cid", ["Ada", "ada_l", "-ada", "", "a" * 65,
                                     "ada party"])
    def test_bad_id_slug(self, tmp_path, cid):
        write_registry(tmp_path, counterparties={cid: _entry()})
        assert C.load_counterparties(tmp_path) == {}

    def test_duplicate_handle_across_entries_corrupts_the_file(self, tmp_path):
        """Two parties claiming one address is exactly the ambiguity a consent
        record may not resolve arbitrarily — no first-wins, no last-wins."""
        write_registry(tmp_path, counterparties={
            "ada": _entry(),
            "bob": _entry(handles=["ADA@acme.com"]),   # same party, cased
        })
        assert C.load_counterparties(tmp_path) == {}

    def test_one_bad_entry_corrupts_the_whole_file(self, tmp_path):
        """A typo must never best-effort-consent the surviving entries."""
        write_registry(tmp_path, counterparties={
            "ada": _entry(),
            "bob": _entry(consent="maybe", handles=["bob@acme.com"]),
        })
        assert C.load_counterparties(tmp_path) == {}

    def test_handles_are_case_folded_and_stripped(self, tmp_path):
        write_registry(tmp_path, counterparties={
            "ada": _entry(handles=["  Ada@Acme.COM  "])})
        reg = C.load_counterparties(tmp_path)
        assert reg["ada"].handles == frozenset({"ada@acme.com"})
        assert C.resolve("ADA@ACME.com", reg).id == "ada"

    def test_opaque_chat_ids_are_valid_handles(self, tmp_path):
        """Not every counterparty handle is an email — Teams/Slack ids are
        opaque tokens and must register."""
        write_registry(tmp_path, counterparties={
            "ada": _entry(handles=["19:abc123def@thread.tacv2"])})
        reg = C.load_counterparties(tmp_path)
        assert C.resolve("19:abc123def@thread.tacv2", reg).id == "ada"

    def test_oversized_handle_is_refused(self, tmp_path):
        write_registry(tmp_path, counterparties={
            "ada": _entry(handles=["x" * (C._HANDLE_MAX + 1)])})
        assert C.load_counterparties(tmp_path) == {}

    def test_loader_never_raises(self, tmp_path):
        d = tmp_path.joinpath(*_CFG_SEGMENTS)
        d.mkdir(parents=True, exist_ok=True)
        (d / "counterparties.yml").write_bytes(b"\xff\xfe\x00binary")
        assert C.load_counterparties(tmp_path) == {}


# ---------------------------------------------------------------------------
# 4. RESOLUTION — absence is reported as absence, never guessed
# ---------------------------------------------------------------------------

class TestResolution:
    @pytest.mark.parametrize("recipient", [None, "", "   ", 42, b"ada@acme.com",
                                           "unknown@acme.com", "with space"])
    def test_unresolvable_recipients_are_none(self, registry, recipient):
        assert C.resolve(recipient, registry) is None
        assert C.consent_of(recipient, registry) == C.CONSENT_UNKNOWN

    def test_registry_of_the_wrong_type_resolves_none(self):
        for bad in (None, [], "x", 7):
            assert C.resolve("ada@acme.com", bad) is None
            assert C.outbound_permitted("ada@acme.com", bad, "teams") is False
            assert C.consent_of("ada@acme.com", bad) == C.CONSENT_UNKNOWN

    def test_multi_handle_party_resolves_on_each(self, tmp_path):
        write_registry(tmp_path, counterparties={
            "ada": _entry(handles=["ada@acme.com", "ada.l@other.com"])})
        reg = C.load_counterparties(tmp_path)
        assert C.resolve("ada@acme.com", reg).id == "ada"
        assert C.resolve("ada.l@other.com", reg).id == "ada"
        assert reg["ada"].handles == frozenset(
            {"ada@acme.com", "ada.l@other.com"})

    def test_counterparty_is_immutable(self, registry):
        with pytest.raises(Exception):
            registry["ada"].consent = "granted"


# ---------------------------------------------------------------------------
# 5. THE SHIPPED EXAMPLE TWIN
# ---------------------------------------------------------------------------

class TestShippedExample:
    EXAMPLE = _REPO_ROOT.joinpath(*_CFG_SEGMENTS, "counterparties.yml.example")

    def test_example_exists_and_parses(self):
        data = yaml.safe_load(self.EXAMPLE.read_text())
        assert set(data) == {"version", "counterparties"}
        assert data["version"] == 1

    def test_example_ships_unconsented(self):
        """Same law as peers.yml.example: a fresh instance never arrives with
        a pre-consented party."""
        data = yaml.safe_load(self.EXAMPLE.read_text())
        for cid, entry in data["counterparties"].items():
            assert entry["consent"] != C.CONSENT_GRANTED, cid
            assert entry["captain_scope"]["channels"] == [], cid

    def test_example_validates_against_the_real_loader(self, tmp_path):
        """The twin is not just parseable — it is a LOADABLE registry."""
        write_registry(tmp_path, text=self.EXAMPLE.read_text())
        reg = C.load_counterparties(tmp_path)
        assert set(reg) == {"example-counterparty"}
        assert not reg["example-counterparty"].is_consented

    def test_example_carries_no_real_party(self):
        text = self.EXAMPLE.read_text()
        assert "example.invalid" in text


# ---------------------------------------------------------------------------
# 6. MUTANTS BITE — the anti-vacuity battery
# ---------------------------------------------------------------------------

_MUTANT_SEQ = [0]


def _mutant(*replacements):
    """Re-exec the module source with EXACTLY the given guards disabled.

    Refuses unless every anchor matched exactly once, so a replacement that
    silently no-ops (evidence-discipline: "reported is not measured") can
    never certify an arm as armed.

    The mutant is registered in `sys.modules` under a unique name for the
    duration of the exec: `@dataclass` under postponed annotations resolves
    field types through `sys.modules[cls.__module__]`, so an unregistered
    namespace cannot build `Counterparty`.
    """
    src = _SRC
    for old, new in replacements:
        n = src.count(old)
        assert n == 1, "mutation anchor matched %d times: %r" % (n, old)
        src = src.replace(old, new, 1)
    assert src != _SRC

    _MUTANT_SEQ[0] += 1
    mod_name = "counterparty_mutant_%d" % _MUTANT_SEQ[0]
    mod = types.ModuleType(mod_name)
    mod.__file__ = str(_SRC_PATH)
    sys.modules[mod_name] = mod
    try:
        exec(compile(src, str(_SRC_PATH), "exec"), mod.__dict__)
    finally:
        sys.modules.pop(mod_name, None)
    return mod


class TestMutantsBite:
    """Each arm proves the paired assertion above is load-bearing: with one
    guard removed the module gives the WRONG answer, so the passing arm is
    measuring that guard and not the absence of the feature."""

    def test_consent_guard_is_live(self, tmp_path):
        write_registry(tmp_path, counterparties={
            "ada": _entry(consent="withdrawn")})
        m = _mutant((
            "    if not cp.is_consented:\n        return False\n",
            "    if False:\n        return False\n",
        ))
        reg = m.load_counterparties(tmp_path)
        # Real module refuses a withdrawn party; the mutant permits it.
        assert C.outbound_permitted("ada@acme.com",
                                    C.load_counterparties(tmp_path), "teams") is False
        assert m.outbound_permitted("ada@acme.com", reg, "teams") is True

    def test_scope_guard_is_live(self, tmp_path):
        write_registry(tmp_path)
        m = _mutant((
            "    return norm_channel in cp.channels\n",
            "    return True\n",
        ))
        reg = m.load_counterparties(tmp_path)
        assert C.outbound_permitted(
            "ada@acme.com", C.load_counterparties(tmp_path), "outlook") is False
        assert m.outbound_permitted("ada@acme.com", reg, "outlook") is True

    def test_duplicate_handle_guard_is_live(self, tmp_path):
        write_registry(tmp_path, counterparties={
            "ada": _entry(),
            "bob": _entry(handles=["ADA@acme.com"]),
        })
        m = _mutant((
            "            if handle in seen_handles:",
            "            if False:",
        ))
        assert C.load_counterparties(tmp_path) == {}
        assert set(m.load_counterparties(tmp_path)) == {"ada", "bob"}

    def test_containment_probe_is_live(self, tmp_path):
        real = tmp_path / "elsewhere.yml"
        real.write_text(yaml.safe_dump(
            {"version": 1, "counterparties": {"ada": _entry()}}))
        d = tmp_path.joinpath(*_CFG_SEGMENTS)
        d.mkdir(parents=True, exist_ok=True)
        (d / "counterparties.yml").symlink_to(real)
        m = _mutant((
            "    if not _is_real_config_path(path, root):\n        return {}\n",
            "    if False:\n        return {}\n",
        ))
        assert C.load_counterparties(tmp_path) == {}
        assert set(m.load_counterparties(tmp_path)) == {"ada"}

    def test_declared_unknown_consent_guard_is_live(self, tmp_path):
        write_registry(tmp_path, counterparties={
            "ada": _entry(consent="unknown")})
        m = _mutant((
            "    if not isinstance(consent, str) or consent not in CONSENT_STATES:\n",
            "    if not isinstance(consent, str) or consent not in "
            "(CONSENT_STATES | {CONSENT_UNKNOWN}):\n",
        ))
        assert C.load_counterparties(tmp_path) == {}
        assert set(m.load_counterparties(tmp_path)) == {"ada"}

    def test_whole_file_corruption_is_live(self, tmp_path):
        write_registry(tmp_path, counterparties={
            "ada": _entry(),
            "bob": _entry(consent="maybe", handles=["bob@acme.com"]),
        })
        m = _mutant((
            "        if cp is None:\n            return {}\n",
            "        if cp is None:\n            continue\n",
        ))
        # Real module: one bad entry corrupts everything. Mutant: ada survives
        # and would be treated as consented — the exact best-effort behaviour
        # a consent registry must not have.
        assert C.load_counterparties(tmp_path) == {}
        assert set(m.load_counterparties(tmp_path)) == {"ada"}

    def test_free_text_exclusion_is_live(self, tmp_path):
        write_registry(tmp_path, counterparties={
            "ada": _entry(display_name="Ada L; DROP")})
        m = _mutant((
            '        "counterparty_relationship": cp.relationship,\n    }\n',
            '        "counterparty_relationship": cp.relationship,\n'
            '        "counterparty_display_name": cp.display_name,\n    }\n',
        ))
        reg = C.load_counterparties(tmp_path)
        assert "Ada L; DROP" not in repr(C.journal_fields("ada@acme.com", reg))
        assert "Ada L; DROP" in repr(
            m.journal_fields("ada@acme.com", m.load_counterparties(tmp_path)))

    def test_handle_normalization_guard_is_live(self, tmp_path):
        write_registry(tmp_path, counterparties={
            "ada": _entry(handles=["ada@acme.com"])})
        m = _mutant((
            "    norm = handle.strip().lower()\n",
            "    norm = handle.strip()\n",
        ))
        reg_real = C.load_counterparties(tmp_path)
        reg_mut = m.load_counterparties(tmp_path)
        assert C.resolve("ADA@ACME.com", reg_real) is not None
        assert m.resolve("ADA@ACME.com", reg_mut) is None

    def test_id_slug_guard_is_live(self, tmp_path):
        write_registry(tmp_path, counterparties={"Ada Party": _entry()})
        m = _mutant((
            "    if not isinstance(cid, str) or not _ID_RE.match(cid):\n"
            "        return None\n",
            "    if not isinstance(cid, str):\n        return None\n",
        ))
        assert C.load_counterparties(tmp_path) == {}
        assert set(m.load_counterparties(tmp_path)) == {"Ada Party"}

    def test_journal_wiring_is_live(self, tmp_path):
        """The contract-side wiring, not just the module: strip the payload
        update and the delivered property disappears."""
        contract_src = (
            _REPO_ROOT / "framework" / "channels" / "contract.py").read_text()
        anchor = ("        payload.update(\n"
                  "            _counterparty.journal_fields"
                  "(recipient, self._counterparties))\n")
        assert contract_src.count(anchor) == 1
        mutated = contract_src.replace(anchor, "", 1)
        ns = {"__name__": "contract_mutant",
              "__file__": str(_REPO_ROOT / "framework/channels/contract.py")}
        exec(compile(mutated, ns["__file__"], "exec"), ns)

        class _M(ns["ChannelAdapter"]):
            name = "teams"
            capabilities = frozenset({"send"})
            undo_contract = ns["UndoContract"].none()

            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.journalled = []

            def _dispatch_send(self, recipient, body, thread_id):
                return "artifact-1"

            def _journal(self, event_type, payload):
                self.journalled.append((event_type, payload))

        write_registry(tmp_path)
        real = _Adapter(org_domains=["acme.com"], root=tmp_path)
        real.send("ada@acme.com", "hello")
        assert real.journalled[0][1]["counterparty_id"] == "ada"

        mut = _M(org_domains=["acme.com"], root=tmp_path)
        mut.send("ada@acme.com", "hello")
        assert "counterparty_id" not in mut.journalled[0][1]
