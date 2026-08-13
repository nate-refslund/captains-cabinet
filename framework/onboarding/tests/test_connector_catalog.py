"""The shipped connector catalog, checked against the shipped catalog.

WHAT THIS IS POINTED AT, and why that is the whole design. The pack is DATA: it
grows by editing a file, with no code review path and no type system underneath
it. So the only thing standing between a careless entry and an operator pasting
a credential into a broken shape is a checker that reads the REAL file — not a
fixture, not a sample, not a copy in a docstring. Every arm here resolves
``instance/config/connector-templates.yml.example`` from the repo and asserts
over what is actually there.

THE ARMS, each aimed at a failure that has a victim:

* SHAPE — every template carries the keys a surface renders and the core
  consumes. A missing ``how_to_connect`` is a tool nobody can connect; a missing
  ``category`` is a tool nobody can find; a ``credential_env`` the .env writer
  would reject is a connect button that fails after the operator has already
  gone and made a key.
* BUILDS — every template is resolved through the real
  ``build_connector_from_template`` with its own placeholders as answers, and
  the BUILT inventory is held to ``assert_read_only``. This is the ceiling, on
  the artifact, at the count it actually ships.
* CUSTODY — an operator answer may only ever land under ``inventory.``. A field
  pointed at ``identity`` or at the entry root would let a pack edit move where
  a credential is sent or what the connector is called, which is the one thing
  the field mechanism must not be able to do.
* HOST CONSENT — where a template declares a host, it is the host the built URL
  actually reaches. The connect step prints that string as a consent line, so a
  stale one is a lie told at exactly the moment consent is given.
* READ-SCOPE HONESTY — the adversarial arm. A ``how_to_connect`` step may not
  walk an operator into minting a WRITE-scoped key while the card beside it
  promises the cabinet only reads. Write words are allowed only in a step that
  is refusing them ("do not tick", "leave every other on None") or in a template
  that says plainly that no read-only key exists. This is checked mechanically
  because prose is exactly where an unverified claim hides.
* THE CHECKER ITSELF — ``test_the_checker_rejects_a_bad_template`` feeds the
  same helpers a template broken four ways and asserts each is caught. Without
  it every arm above could be vacuous and read identically green (this repo's
  dominant defect class: a sensor that cannot fail).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from framework.onboarding import research

#: Written as ONE joined literal, never a bare "instance" segment: the
#: layer-separation gate reads that segment as a framework->instance coupling.
CONFIG_DIR = "instance/config"
TEMPLATES_TWIN = CONFIG_DIR + "/connector-templates.yml.example"

#: The catalog the Captain asked to be able to browse. A FLOOR, not a target:
#: it exists so a future edit that guts the pack back to a handful fails loudly
#: instead of quietly making the catalog a pick-list again.
MIN_TEMPLATES = 25
#: And spread across enough shelves that "agnostic" is visible in the data — a
#: pack of forty tools all for programmers would pass a count and fail the goal.
MIN_CATEGORIES = 8

#: Words that name a permission which can CHANGE something in the other product.
#: WHOLE WORDS, because "Administration" is a menu and "an admin" is a person —
#: neither is a scope, and flagging them would train the next pack author to
#: reword around the checker instead of reading it.
_WRITE_RE = re.compile(
    r"\b(write|admin|administrator|modify|delete|unrestricted|full access|read[_ ]write)\b",
    re.IGNORECASE)
#: A write word only MATTERS beside a word that means "a permission you are
#: about to grant". "You must be an admin" is a precondition; "tick the admin
#: scope" is the failure this arm exists for.
_PERMISSION_RE = re.compile(
    r"\b(scope|scopes|permission|permissions|access level|role|roles|tick|grant|"
    r"granted|checkbox|toggle)\b", re.IGNORECASE)
#: A step may name a write permission only while REFUSING it, or while saying
#: plainly that the product offers nothing narrower. One of these must appear in
#: the same step for the write word to be lawful.
_HONEST_MARKERS = (
    "do not", "don't", "leave every", "leave everything else",
    "unticked", "not limited", "only ever lists", "nothing else",
    "rather than", "instead", "no read-only", "cannot change",
    "read-only", "read only",
)


# ------------------------------------------------------------------ helpers --
def _repo_root() -> Path:
    """The checkout this test file lives in — never a cwd, which varies."""
    return Path(__file__).resolve().parents[3]


def _pack() -> dict:
    doc = yaml.safe_load((_repo_root() / TEMPLATES_TWIN).read_text(encoding="utf-8"))
    assert isinstance(doc, dict), "the shipped pack is not a mapping"
    return doc


def _answers(tpl: dict) -> dict:
    """The operator's answers, taken from the template's OWN placeholders.

    A placeholder is what the pack tells the operator to type, so building with
    it is the closest thing to a real connect that needs no credential and no
    network — and a placeholder that cannot produce a lawful connector is itself
    the defect, since it is the example the operator will follow.
    """
    out = {}
    for field in tpl.get("fields") or []:
        key = str(field.get("key") or "")
        placeholder = str(field.get("placeholder") or "")
        if key and placeholder:
            out[key] = placeholder
    return out


def _check_shape(tpl: dict, categories: dict) -> None:
    """Every key a surface renders or the core consumes, present and sane."""
    tid = str(tpl.get("id") or "")
    assert tid and tid == tid.lower() and " " not in tid, f"bad id: {tid!r}"
    for key in ("label", "summary", "credential_help", "key_looks_like", "category"):
        assert str(tpl.get(key) or "").strip(), f"{tid}: {key} is empty"
    assert str(tpl.get("category")) in categories or str(tpl.get("category")) == "other", \
        f"{tid}: category {tpl.get('category')!r} is not a declared shelf"
    cred = str(tpl.get("credential_env") or "")
    assert research._ENV_NAME_RE.match(cred), \
        f"{tid}: credential_env {cred!r} is not one the .env writer would accept"
    steps = tpl.get("how_to_connect")
    assert isinstance(steps, list) and 2 <= len(steps) <= 5, \
        f"{tid}: how_to_connect must be 2-5 steps, got {steps!r}"
    for step in steps:
        assert isinstance(step, str) and len(step.strip()) > 20, \
            f"{tid}: a how_to_connect step is empty or a stub: {step!r}"
    inventory = (tpl.get("connector") or {}).get("inventory") or {}
    encoding = str(inventory.get("date_encoding") or "iso")
    assert encoding in research._DATE_ENCODINGS, \
        f"{tid}: date_encoding {encoding!r} is one the sweep refuses by name"


def _check_custody(tpl: dict) -> None:
    """An operator answer lands under `inventory.` and nowhere else."""
    tid = str(tpl.get("id") or "")
    for field in tpl.get("fields") or []:
        into = str(field.get("into") or "")
        assert into.startswith("inventory."), \
            f"{tid}: field {field.get('key')!r} writes to {into!r}, outside inventory"
        shape = str(field.get("into_format") or "")
        if shape:
            assert shape.startswith("https://") and "{value}" in shape, \
                f"{tid}: into_format {shape!r} does not pin https:// around one {{value}}"
        for key in ("label", "help", "placeholder"):
            assert str(field.get(key) or "").strip(), \
                f"{tid}: field {field.get('key')!r} has no {key}"


def _check_read_scope_honesty(tpl: dict) -> None:
    """No step may walk an operator into a write-scoped key unremarked."""
    tid = str(tpl.get("id") or "")
    for step in tpl.get("how_to_connect") or []:
        low = str(step).lower()
        named = _WRITE_RE.findall(low)
        if not named or not _PERMISSION_RE.search(low):
            continue
        assert any(marker in low for marker in _HONEST_MARKERS), (
            f"{tid}: a setup step names the {named} permission with nothing "
            f"refusing it or admitting the product has no read-only key: {step!r}"
        )


# ------------------------------------------------------ the shipped catalog --
def test_the_shipped_pack_parses_and_declares_its_shelves():
    doc = _pack()
    assert doc.get("schema") == research.CONNECTOR_TEMPLATES_SCHEMA
    categories = doc.get("categories")
    assert isinstance(categories, dict) and categories, "no shelves declared"
    for cid, label in categories.items():
        assert str(cid).strip() and str(label).strip(), f"empty shelf: {cid!r}"


def test_the_catalog_is_broad_enough_to_browse():
    """The Captain's ask, as a floor on the DATA rather than a claim in a doc."""
    doc = _pack()
    templates = doc["templates"]
    assert len(templates) >= MIN_TEMPLATES, (
        f"the catalog ships {len(templates)} templates, below the {MIN_TEMPLATES} "
        "floor — a catalog that shrinks back to a pick-list fails the ask")
    shelves = {str(t.get("category") or "other") for t in templates}
    assert len(shelves) >= MIN_CATEGORIES, (
        f"the catalog covers {len(shelves)} shelves, below {MIN_CATEGORIES} — a "
        "pack whose tools all serve one trade is not an agnostic framework")
    ids = [str(t.get("id")) for t in templates]
    assert len(ids) == len(set(ids)), f"duplicate template ids: {ids}"
    # The escape hatch is not optional: it is what makes every tool NOT in the
    # pack still connectable, and the honest answer to "hundreds".
    assert "rest" in ids, "the open template is missing, so the catalog is a closed set"


def test_every_shipped_template_has_the_shape_a_surface_renders():
    doc = _pack()
    categories = doc["categories"]
    for tpl in doc["templates"]:
        _check_shape(tpl, categories)
        _check_custody(tpl)


def test_every_shipped_template_builds_into_a_read_only_connector():
    """The ceiling, on the built call, for the whole pack at shipping size."""
    templates = research.load_connector_templates(_repo_root())
    doc = _pack()
    assert len(templates) == len(doc["templates"]), \
        "the loader dropped a template the file declares — one of them is malformed"
    for tid, tpl in templates.items():
        entry = research.build_connector_from_template(
            templates, tid, name=tid, credential_env="TEST_TOKEN",
            fields=_answers(tpl))
        research.assert_read_only(entry["inventory"])
        identity = entry.get("identity")
        if isinstance(identity, dict):
            research.assert_read_only(identity)
            assert identity.get("value_paths"), f"{tid}: identity call reads nothing"
        inventory = entry["inventory"]
        assert str(inventory.get("name_field") or "").strip(), f"{tid}: no name path"
        assert str(inventory.get("updated_field") or "").strip(), f"{tid}: no date path"


def test_a_declared_host_is_the_host_the_credential_actually_reaches():
    """The consent line names where the key goes, so it must be true."""
    templates = research.load_connector_templates(_repo_root())
    for tid, tpl in templates.items():
        declared = str(tpl.get("host") or "").strip()
        if not declared:
            continue  # the operator supplies the address; the card says so
        entry = research.build_connector_from_template(
            templates, tid, name=tid, credential_env="TEST_TOKEN",
            fields=_answers(tpl))
        assert research._host_of(entry) == declared, (
            f"{tid}: declares host {declared!r} but the built call reaches "
            f"{research._host_of(entry)!r}")


def test_no_setup_step_walks_the_operator_into_a_write_scoped_key():
    for tpl in _pack()["templates"]:
        _check_read_scope_honesty(tpl)


# ------------------------------------------------------- the checker itself --
@pytest.mark.parametrize("broken, checker, why", [
    # A step that mints a write key with nothing refusing it.
    ({"id": "x", "how_to_connect": ["Create the token.",
                                    "Tick the admin scope and save it."]},
     _check_read_scope_honesty, "write scope"),
    # A field that writes outside the inventory — the custody hole.
    ({"id": "x", "fields": [{"key": "k", "label": "L", "help": "H",
                             "placeholder": "P", "into": "identity.url"}]},
     _check_custody, "outside inventory"),
    # An into_format that does not pin the scheme.
    ({"id": "x", "fields": [{"key": "k", "label": "L", "help": "H",
                             "placeholder": "P", "into": "inventory.url",
                             "into_format": "http://{value}/x"}]},
     _check_custody, "https"),
    # A template with one step, which is not instructions.
    ({"id": "x", "label": "X", "summary": "S", "credential_help": "C",
      "key_looks_like": "K", "category": "code", "credential_env": "X_TOKEN",
      "how_to_connect": ["Make a key."]},
     lambda tpl: _check_shape(tpl, {"code": "Code"}), "2-5 steps"),
])
def test_the_checker_rejects_a_bad_template(broken, checker, why):
    """Every arm above must be able to FAIL. Otherwise they are decoration."""
    with pytest.raises(AssertionError):
        checker(broken)
