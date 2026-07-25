"""framework.outbound_identity — WHO the cabinet is when it reaches a human who
is not the Captain.

THE PROBLEM THIS EXISTS TO SOLVE. Before this module the cabinet had no outbound
identity of its own: the frontdoor draft path closed every outbound email with
the CAPTAIN'S OWN signature (``chair_drafts.present_draft`` →
``get_dispatch().ensure_signature``) before he ever saw the text, and the only
machine-provenance mark anywhere in the tree was a Monday-board TITLE banner
(``framework.frontdoor.action_exec.PROVENANCE_BANNER``). Every message the
cabinet sent was therefore, on its face, written and signed by the Captain
personally. With the cabinet authorised to contact real people that is a
liability the Captain carries for words he did not write.

WHAT THIS MODULE OWNS. Two separable things, both deployment-config driven and
neither hardcoding an address, a person or an org:

  1. **Identity** — a from-address / reply-to / display name / credential-env
     NAME / sign-off the cabinet uses AS ITSELF, plus the ``mode`` switch that
     selects between that and the Captain's own identity.
  2. **Disclosure** — a loud, human-legible machine-provenance line stamped onto
     outbound text on every channel that reaches a non-Captain human, so the
     recipient can tell a machine wrote it. This is the SAME obligation the
     act-first Monday surfaces already carry, lifted out of "board artifacts
     only" and made channel-general.

FAIL-CLOSED, TO THE SAFE SIDE. Absent config, unreadable config, a symlinked or
traversed config path, unparseable YAML, an unknown key, a wrong version, or ANY
malformed field all resolve to ``SAFE_DEFAULT``: ``mode="cabinet"`` (the
Captain's personal signature is NOT applied) with disclosure ENABLED on every
channel and every address field EMPTY. A partial parse is never accepted — a
typo in the identity block must not silently half-configure who the cabinet is.
The permissive posture (sign as the Captain) is reachable only by an explicit,
well-formed ``mode: captain``.

SECRETS. The config carries the NAME of the credential environment variable
(``credential_env``), never its value; this module never reads that variable and
never logs it. Same discipline as the act-first acting-identity block.

LAYER SEPARATION. This is universal-base ``framework`` code: it hardcodes no
launcher, product, person or address. The Captain's display name reaches the
default disclosure text only through ``framework.env.captain_name()`` (the
sanctioned resolver), and the instance-config directory is named as ONE combined
path segment split at use — the same statement ``framework/channels/contract.py``
makes, and for the same reason (the layer-separation gate greps a bare quoted
``instance`` token).

System Python compatibility: stdlib only at module scope; ``yaml`` is imported
lazily inside the loader so importing this module can never fail on a box
without PyYAML. Nothing here raises — every public entry point degrades to the
safe default rather than breaking an egress path.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Iterable, NamedTuple

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: The cabinet acts under its OWN identity — the Captain's personal signature is
#: never applied. The safe default.
MODE_CABINET = "cabinet"
#: The cabinet acts under the CAPTAIN'S identity (his signature closes the mail).
#: The pre-2026-07-25 behaviour; reachable only by explicit config.
MODE_CAPTAIN = "captain"
MODES = frozenset({MODE_CABINET, MODE_CAPTAIN})

PLACEMENT_APPEND = "append"
PLACEMENT_PREPEND = "prepend"
PLACEMENTS = frozenset({PLACEMENT_APPEND, PLACEMENT_PREPEND})

#: The loud machine mark. Same glyph family as the Monday banner
#: (``action_exec.PROVENANCE_BANNER``) so one visual cue means "a machine made
#: this" everywhere the cabinet touches a human.
MACHINE_MARK = "\U0001F916"

#: The default disclosure. ``{captain}`` is substituted from
#: ``framework.env.captain_name()`` — a plain string replace, never ``str.format``
#: (a stray brace in Captain-authored config must not raise inside an egress).
#: Deliberately says only what is true on EVERY path: the machine sent it. It
#: does not claim who wrote the words, so it stays honest on a Captain-edited
#: draft too.
DEFAULT_DISCLOSURE_TEXT = MACHINE_MARK + " Sent by an AI assistant acting for {captain}."

_CAPTAIN_TOKEN = "{captain}"

# The instance-config dir as ONE combined relative segment, split at use. See the
# module docstring (and the identical statement in framework/channels/contract.py)
# for why this is written as one string.
_INST_CFG = "instance/config"
_CONFIG_LEAF = "outbound-identity.yml"

# Closed key sets — an unknown key is CORRUPT (⇒ safe default), never ignored.
_TOP_KEYS = frozenset({"version", "identity", "disclosure"})
_IDENTITY_KEYS = frozenset({
    "mode", "display_name", "from_address", "reply_to", "credential_env",
    "signature",
})
_DISCLOSURE_KEYS = frozenset({
    "enabled", "text", "placement", "channels", "captain_surfaces",
})

_SUPPORTED_VERSION = 1

# Channels on which a configured cabinet SIGN-OFF is appended. Mirrors the
# adapter-side captain-signature contract (``PersonalDispatch.ensure_signature``
# is email-only, never a chat message) so switching identity mode changes WHOSE
# sign-off appears, not WHERE sign-offs appear. Chat channels still carry the
# disclosure — that, not a sign-off, is what identifies the sender there.
_SIGNATURE_CHANNEL_TOKENS = ("email", "mail")


class OutboundIdentity(NamedTuple):
    """The resolved outbound identity + disclosure policy for this deployment."""

    mode: str
    display_name: str
    from_address: str
    reply_to: str
    credential_env: str
    signature: str
    disclosure_enabled: bool
    disclosure_text: str
    disclosure_placement: str
    #: channel (lowercased) -> explicit enable/disable override.
    disclosure_channels: dict
    #: channels that ARE the Captain himself — never stamped (his own chat).
    captain_surfaces: frozenset
    #: "default" (no config file), "config" (a well-formed file was read) or
    #: "corrupt" (a file existed but was refused). Audit/telemetry only.
    source: str


#: The posture every failure mode resolves to: act as the cabinet, disclose
#: everywhere, invent no address.
SAFE_DEFAULT = OutboundIdentity(
    mode=MODE_CABINET,
    display_name="",
    from_address="",
    reply_to="",
    credential_env="",
    signature="",
    disclosure_enabled=True,
    disclosure_text=DEFAULT_DISCLOSURE_TEXT,
    disclosure_placement=PLACEMENT_APPEND,
    disclosure_channels={},
    captain_surfaces=frozenset(),
    source="default",
)

_CORRUPT_DEFAULT = SAFE_DEFAULT._replace(source="corrupt")


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

def cabinet_root(root: "str | Path | None" = None) -> Path:
    """Resolve the deployment root: explicit arg → ``CABINET_ROOT`` → repo root
    (this file's parent). Fixed relative suffixes only — mirrors
    ``framework.channels.contract.cabinet_root``."""
    if root is not None:
        return Path(root)
    return Path(os.environ.get("CABINET_ROOT")
                or str(Path(__file__).resolve().parents[1]))


def config_path(root: "str | Path | None" = None) -> Path:
    """The outbound-identity config under the deployment's instance-config dir."""
    return cabinet_root(root).joinpath(*_INST_CFG.split("/"), _CONFIG_LEAF)


def _is_real_config_path(path: Path, root: "str | Path | None") -> bool:
    """Containment probe: the config must BE the real file at
    ``<root>/instance/config/outbound-identity.yml`` — no symlink or traversal
    anywhere in the suffix. A planted symlink pointing at an attacker-writable
    file must not be able to turn disclosure off, so a failed probe refuses
    fail-closed (mirrors ``contract._is_real_config_path`` /
    ``posture._is_real_ruling_path``)."""
    try:
        expected = os.path.join(
            os.path.realpath(str(cabinet_root(root))), _INST_CFG, _CONFIG_LEAF)
        return os.path.realpath(str(path)) == expected
    except OSError:
        return False


def _clean_str(value: Any) -> "str | None":
    """A string field: must BE a string (``None`` ⇒ absent, anything else ⇒
    malformed). Returns the stripped value, or ``None`` when malformed."""
    if value is None:
        return ""
    if not isinstance(value, str):
        return None
    return value.strip()


def _parse_identity(block: Any, out: dict) -> bool:
    """Fold a well-formed ``identity:`` block into ``out``. False ⇒ malformed."""
    if block is None:
        return True
    if not isinstance(block, dict) or (set(block) - _IDENTITY_KEYS):
        return False
    mode = _clean_str(block.get("mode"))
    if mode is None:
        return False
    if mode:
        mode = mode.lower()
        if mode not in MODES:
            return False
        out["mode"] = mode
    for key in ("display_name", "from_address", "reply_to", "credential_env",
                "signature"):
        if key not in block:
            continue
        # A signature is multi-line prose: strip only the surrounding blank
        # lines, never the interior. Everything else is a single token.
        raw = block.get(key)
        if raw is None:
            out[key] = ""
            continue
        if not isinstance(raw, str):
            return False
        out[key] = raw.strip("\n").strip() if key != "signature" else raw.strip("\n")
    return True


def _parse_disclosure(block: Any, out: dict) -> bool:
    """Fold a well-formed ``disclosure:`` block into ``out``. False ⇒ malformed."""
    if block is None:
        return True
    if not isinstance(block, dict) or (set(block) - _DISCLOSURE_KEYS):
        return False
    if "enabled" in block:
        enabled = block.get("enabled")
        if not isinstance(enabled, bool):
            return False
        out["disclosure_enabled"] = enabled
    if "text" in block:
        text = _clean_str(block.get("text"))
        # A blank disclosure text is a silent kill switch wearing a typo's
        # clothes — refuse the whole file rather than ship an empty banner.
        if not text:
            return False
        out["disclosure_text"] = text
    if "placement" in block:
        placement = _clean_str(block.get("placement"))
        if not placement or placement.lower() not in PLACEMENTS:
            return False
        out["disclosure_placement"] = placement.lower()
    if "channels" in block:
        channels = block.get("channels")
        if channels is None:
            channels = {}
        if not isinstance(channels, dict):
            return False
        resolved = {}
        for name, value in channels.items():
            if not isinstance(name, str) or not name.strip():
                return False
            if not isinstance(value, bool):
                return False
            resolved[name.strip().lower()] = value
        out["disclosure_channels"] = resolved
    if "captain_surfaces" in block:
        surfaces = block.get("captain_surfaces")
        if surfaces is None:
            surfaces = []
        if not isinstance(surfaces, (list, tuple)):
            return False
        names = set()
        for entry in surfaces:
            if not isinstance(entry, str) or not entry.strip():
                return False
            names.add(entry.strip().lower())
        out["captain_surfaces"] = frozenset(names)
    return True


def load(root: "str | Path | None" = None) -> OutboundIdentity:
    """The deployment's outbound identity. Never raises; never returns a partial
    parse. Read fresh on every call so a Captain edit takes effect without a
    restart (these are per-message decisions, not a hot loop)."""
    path = config_path(root)
    try:
        if not path.exists():
            return SAFE_DEFAULT
    except OSError:
        return _CORRUPT_DEFAULT
    if not _is_real_config_path(path, root):
        return _CORRUPT_DEFAULT
    try:
        import yaml  # lazy: this module must import on a box without PyYAML
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return _CORRUPT_DEFAULT
    if data is None:
        return _CORRUPT_DEFAULT
    if not isinstance(data, dict) or (set(data) - _TOP_KEYS):
        return _CORRUPT_DEFAULT
    version = data.get("version")
    if isinstance(version, bool) or version != _SUPPORTED_VERSION:
        return _CORRUPT_DEFAULT
    out = SAFE_DEFAULT._asdict()
    if not _parse_identity(data.get("identity"), out):
        return _CORRUPT_DEFAULT
    if not _parse_disclosure(data.get("disclosure"), out):
        return _CORRUPT_DEFAULT
    out["source"] = "config"
    return OutboundIdentity(**out)


# ---------------------------------------------------------------------------
# Policy predicates
# ---------------------------------------------------------------------------

def _ident(ident: "OutboundIdentity | None") -> OutboundIdentity:
    return ident if isinstance(ident, OutboundIdentity) else load()


def _chan(channel: Any) -> str:
    return str(channel or "").strip().lower()


def captain_display_name(default: str = "Captain") -> str:
    """The Captain's display name for substitution into the disclosure — via the
    sanctioned resolver, so framework carries no launcher's name. Any failure
    degrades to the generic default."""
    try:
        from framework import env
        name = env.captain_name(default)
    except Exception:
        return default
    return name if isinstance(name, str) and name.strip() else default


def signs_as_captain(ident: "OutboundIdentity | None" = None) -> bool:
    """True only under an explicit, well-formed ``mode: captain``."""
    return _ident(ident).mode == MODE_CAPTAIN


def is_captain_surface(channel: Any,
                       ident: "OutboundIdentity | None" = None) -> bool:
    """True when this channel IS the Captain (his own chat) — the one audience
    that needs no disclosure, because he knows what his cabinet is."""
    return _chan(channel) in _ident(ident).captain_surfaces


def requires_disclosure(channel: Any,
                        ident: "OutboundIdentity | None" = None) -> bool:
    """Does outbound text on this channel need the machine-provenance line?

    Default YES for every channel that is not a declared Captain surface. A
    channel the deployment has never heard of therefore discloses — an unknown
    audience is treated as a stranger, not as the Captain."""
    resolved = _ident(ident)
    if not resolved.disclosure_enabled:
        return False
    name = _chan(channel)
    if name in resolved.captain_surfaces:
        return False
    override = resolved.disclosure_channels.get(name)
    if isinstance(override, bool):
        return override
    return True


def disclosure_line(channel: Any = None,
                    ident: "OutboundIdentity | None" = None) -> str:
    """The rendered disclosure line for this channel (empty when not required)."""
    resolved = _ident(ident)
    if not requires_disclosure(channel, resolved):
        return ""
    text = resolved.disclosure_text or DEFAULT_DISCLOSURE_TEXT
    return text.replace(_CAPTAIN_TOKEN, captain_display_name())


def has_disclosure(text: Any, channel: Any = None,
                   ident: "OutboundIdentity | None" = None) -> bool:
    """Does ``text`` already carry this channel's rendered disclosure, verbatim?

    Deliberately an EXACT match on the rendered line rather than a scan for the
    machine glyph: an inbound message that happens to contain the glyph (quoted
    into a reply, or planted by a hostile correspondent) must not be able to
    suppress the stamp. If this returns True the property we care about — the
    disclosure is present in the outgoing bytes — actually holds."""
    line = disclosure_line(channel, _ident(ident))
    if not line:
        return False
    return line in (text if isinstance(text, str) else "")


def stamp(text: Any, channel: Any = None,
          ident: "OutboundIdentity | None" = None) -> str:
    """Return ``text`` carrying this channel's machine-provenance disclosure.

    Idempotent, and a no-op when the channel needs no disclosure. This is the
    one function every outbound path calls; ``prepare_outbound`` composes it
    with the identity's sign-off."""
    resolved = _ident(ident)
    body = text if isinstance(text, str) else ""
    line = disclosure_line(channel, resolved)
    if not line or line in body:
        return body
    if not body.strip():
        return line
    if resolved.disclosure_placement == PLACEMENT_PREPEND:
        return line + "\n\n" + body.lstrip("\n")
    return body.rstrip() + "\n\n" + line


def _wants_signature(channel: Any) -> bool:
    name = _chan(channel)
    return any(token in name for token in _SIGNATURE_CHANNEL_TOKENS)


def apply_signature(text: Any, channel: Any = None,
                    ident: "OutboundIdentity | None" = None) -> str:
    """Close an outbound email with the CABINET'S OWN configured sign-off.

    Idempotent, email-channels only, and a no-op when no cabinet signature is
    configured (a deployment that has not written one sends unsigned rather than
    borrowing the Captain's)."""
    resolved = _ident(ident)
    body = text if isinstance(text, str) else ""
    signature = (resolved.signature or "").strip("\n")
    if not signature.strip() or not _wants_signature(channel):
        return body
    if signature in body:
        return body
    if not body.strip():
        return signature
    return body.rstrip() + "\n\n" + signature


def prepare_outbound(text: Any, channel: Any = None,
                     captain_signature: "Callable[[str, str], str] | None" = None,
                     ident: "OutboundIdentity | None" = None) -> str:
    """The composition seam: sign as whoever this deployment says the cabinet is,
    then disclose.

    ``captain_signature`` is the adapter callable that appends the CAPTAIN'S own
    signature (``PersonalDispatch.ensure_signature``). It is invoked ONLY under
    ``mode: captain`` — that is the whole point of the mode — and its failure is
    swallowed exactly as the pre-existing adapter call swallowed it (a missing
    signature must not break a send). The disclosure is applied either way, so
    even the Captain-identity mode tells the recipient a machine sent it."""
    resolved = _ident(ident)
    body = text if isinstance(text, str) else ""
    if resolved.mode == MODE_CAPTAIN:
        if captain_signature is not None:
            try:
                signed = captain_signature(body, channel)
            except Exception:
                signed = None
            if isinstance(signed, str) and signed:
                body = signed
    else:
        body = apply_signature(body, channel, resolved)
    return stamp(body, channel, resolved)


def sender_headers(channel: Any = None,
                   ident: "OutboundIdentity | None" = None) -> dict:
    """The addressing a transport needs to send AS THE CABINET.

    Every value is a plain string and empty means "not configured" — the caller
    decides what to do about that (the Flavor-A dispatch refuses rather than
    silently falling back to the Captain's mailbox). ``credential_env`` is the
    NAME of an environment variable; this module never reads its value."""
    resolved = _ident(ident)
    return {
        "mode": resolved.mode,
        "display_name": resolved.display_name,
        "from_address": resolved.from_address,
        "reply_to": resolved.reply_to,
        "credential_env": resolved.credential_env,
        "disclosure_required": requires_disclosure(channel, resolved),
    }


def describe(channels: "Iterable[str] | None" = None,
             root: "str | Path | None" = None) -> dict:
    """A flat, loggable summary (doctor/audit surface). Names only — never a
    credential value, never the Captain's address unless he configured it."""
    resolved = load(root)
    names = list(channels or ())
    return {
        "source": resolved.source,
        "mode": resolved.mode,
        "from_address_configured": bool(resolved.from_address),
        "reply_to_configured": bool(resolved.reply_to),
        "credential_env": resolved.credential_env,
        "signature_configured": bool(resolved.signature.strip()),
        "disclosure_enabled": resolved.disclosure_enabled,
        "captain_surfaces": sorted(resolved.captain_surfaces),
        "channels": {n: requires_disclosure(n, resolved) for n in names},
    }
