"""COG-4 §9.1 — the FLEET-TRUTH pin: the manifest is not the whole fleet.

`cabinet/services.yml` is the census-pinned fleet measure (57 rows / 44 enabled), but a
set of template-plist ORGANS in `cabinet/launchd/` have NO manifest row — so a "shrink"
that merely moves a service OUT of services.yml into a row-less template is paper-shrink,
not real shrink. Contract §9.1 requires W1 to land THIS test BEFORE any shrink claim: it
pins the EXACT out-of-manifest template-plist organ set (re-derived from the tree, never
trusted as a literal), and the pairing law that every OTHER template pairs with a manifest
row or the roster mechanism. Any service moved OUT of services.yml, or any NEW row-less
template plist, REDs. The exit shrink claim (§9.4) then reports BOTH numbers: manifest rows
(must fall) and row-less organ count (must not grow).

Row→template pairing (byte-derived at tip de5d16c4):
  * 15 `com.cabinet.<stem>.template.plist` files exist.
  * `officer` is the ROSTER mechanism — deploy-mac.sh renders com.cabinet.officer.<slug>.plist
    from the template + instance/config/roster.yml; there is no `officer` services row.
  * 5 templates pair with a manifest row (stem == a services.yml name): apoptosis-sweep,
    dashboard, limit-reset-watchdog, mission-supervisor, self-improvement-loop.
  * the remaining 9 are ROW-LESS organs — the pinned set below.

Officer-plist instance leakage (§9.1): three committed concrete-slug officer plists
(cos, cos-inbound, comms-officer — comms-officer is not even in the 5-officer seed) are
instance leakage against the 2026-07-14 roster-derivation doctrine. Unit u3 removes them
(moves to the instance/deploy surface or deletes). This test asserts them via a TOLERANT
EXPECTED-LEAKAGE constant: present exactly as today OR absent (u3's removal keeps the
subset green), never a NEW committed concrete officer plist.

S0: python3.12, no DB, no network. Provenance: authored per the 2026-07-07 full-autonomy
grant + the 2026-07-20 cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]

LAUNCHD_DIR = _REPO / "cabinet" / "launchd"
SERVICES_YML = _REPO / "cabinet" / "services.yml"

_PREFIX = "com.cabinet."
_TEMPLATE_SUFFIX = ".template.plist"
_PLIST_SUFFIX = ".plist"

# ---------------------------------------------------------------------------
# the PINS (re-derived from the tree by the tests below; these are the tripwires)
# ---------------------------------------------------------------------------
# the EXACT out-of-manifest template-plist organs at tip de5d16c4 — any grow REDs.
EXPECTED_ROWLESS_ORGANS = frozenset({
    "chrome-profile", "cost-summary", "dashboard-kiosk", "egress-proxy",
    "heartbeat-watchdog", "outbox-relay", "ovi-weekly", "role-evals-weekly",
    "worktree-listener",
})
# template stems rendered from a template + roster (NOT a services.yml row).
ROSTER_TEMPLATE_STEMS = frozenset({"officer"})
# the committed concrete-slug officer plists = instance leakage, retired by unit u3.
# TOLERANT: the subset assertion stays green as u3 removes these; only a NEW one REDs.
EXPECTED_OFFICER_LEAKAGE = frozenset({
    "com.cabinet.officer.cos.plist",
    "com.cabinet.officer.cos-inbound.plist",
    "com.cabinet.officer.comms-officer.plist",
})


# ---------------------------------------------------------------------------
# derivation helpers (take explicit paths so the scratch-tree mutants can exercise them)
# ---------------------------------------------------------------------------
def _template_stems(launchd_dir: Path) -> set[str]:
    """The stem of every com.cabinet.<stem>.template.plist under launchd_dir."""
    out: set[str] = set()
    for p in launchd_dir.glob(f"{_PREFIX}*{_TEMPLATE_SUFFIX}"):
        name = p.name
        out.add(name[len(_PREFIX):-len(_TEMPLATE_SUFFIX)])
    return out


def _service_names(services_yml: Path) -> set[str]:
    doc = yaml.safe_load(services_yml.read_text(encoding="utf-8"))
    rows = doc.get("services") if isinstance(doc, dict) else doc
    if not isinstance(rows, list):
        raise AssertionError("services.yml must contain a services list")
    return {row["name"] for row in rows if isinstance(row, dict) and "name" in row}


def _concrete_officer_plists(launchd_dir: Path) -> set[str]:
    """Committed com.cabinet.officer.<slug>.plist basenames, EXCLUDING the template."""
    out: set[str] = set()
    for p in launchd_dir.glob(f"{_PREFIX}officer.*{_PLIST_SUFFIX}"):
        if p.name.endswith(_TEMPLATE_SUFFIX):
            continue
        out.add(p.name)
    return out


def _derive_rowless(template_stems: set[str], service_names: set[str]) -> set[str]:
    """A template stem is a row-less organ unless it is the roster mechanism or pairs
    with a services.yml row. Re-derives §9.1's out-of-manifest organ set from the tree."""
    rowless: set[str] = set()
    for stem in template_stems:
        if stem in ROSTER_TEMPLATE_STEMS:
            continue                       # rendered from template + roster
        if stem in service_names:
            continue                       # pairs with a manifest row
        rowless.add(stem)
    return rowless


def _write_plist(launchd_dir: Path, name: str) -> None:
    launchd_dir.mkdir(parents=True, exist_ok=True)
    (launchd_dir / name).write_text("<plist/>\n", encoding="utf-8")


# ===========================================================================
# real-tree pins (§9.1)
# ===========================================================================
class TestFleetTruthRealTree:
    def test_rowless_organ_set_is_exactly_the_pinned_nine(self):
        stems = _template_stems(LAUNCHD_DIR)
        names = _service_names(SERVICES_YML)
        rowless = _derive_rowless(stems, names)
        assert rowless == EXPECTED_ROWLESS_ORGANS, (
            "out-of-manifest template-organ set drifted — "
            f"NEW row-less (a new template or a service moved OUT of services.yml): "
            f"{sorted(rowless - EXPECTED_ROWLESS_ORGANS)}; "
            f"MISSING (row-less organ removed/paired — update the pin deliberately): "
            f"{sorted(EXPECTED_ROWLESS_ORGANS - rowless)}")

    def test_no_new_rowless_template_organ(self):
        # the enforceable §9.1 law — never grow the row-less set (shrink is welcome). A NEW
        # row-less template plist, or a service moved OUT of services.yml (which un-pairs its
        # template), both surface here.
        stems = _template_stems(LAUNCHD_DIR)
        names = _service_names(SERVICES_YML)
        new_rowless = _derive_rowless(stems, names) - EXPECTED_ROWLESS_ORGANS
        assert not new_rowless, (
            f"NEW out-of-manifest template organ(s) — paper-shrink risk: {sorted(new_rowless)}")

    def test_every_non_rowless_template_pairs_with_row_or_roster(self):
        # the pairing law: every template that is NOT a pinned row-less organ must pair
        # with a manifest row or the roster mechanism. A service moved OUT of services.yml
        # gives a precise failure here (its template pairs with neither).
        stems = _template_stems(LAUNCHD_DIR)
        names = _service_names(SERVICES_YML)
        unpaired = sorted(
            stem for stem in stems
            if stem not in EXPECTED_ROWLESS_ORGANS
            and stem not in ROSTER_TEMPLATE_STEMS
            and stem not in names)
        assert unpaired == [], (
            "template(s) pair with neither a services.yml row nor the roster mechanism "
            f"(service moved OUT of the manifest?): {unpaired}")

    def test_officer_template_is_the_roster_mechanism(self):
        stems = _template_stems(LAUNCHD_DIR)
        names = _service_names(SERVICES_YML)
        assert "officer" in stems, "the officer template is missing"
        assert "officer" not in names, (
            "an `officer` services row appeared — the officer template is the roster "
            "mechanism (deploy-mac.sh + roster.yml), not a manifest row")

    def test_all_fifteen_templates_classify(self):
        # every template partitions into exactly one of: row-less | paired-with-row | roster.
        stems = _template_stems(LAUNCHD_DIR)
        names = _service_names(SERVICES_YML)
        rowless = _derive_rowless(stems, names)
        paired = {s for s in stems if s not in ROSTER_TEMPLATE_STEMS and s in names}
        roster = {s for s in stems if s in ROSTER_TEMPLATE_STEMS}
        assert rowless | paired | roster == stems
        assert rowless == EXPECTED_ROWLESS_ORGANS
        assert roster == ROSTER_TEMPLATE_STEMS

    def test_concrete_officer_plists_within_expected_leakage(self):
        # TOLERANT: present-as-today OR absent (u3 removes them), NEVER a new one.
        actual = _concrete_officer_plists(LAUNCHD_DIR)
        new_leakage = actual - EXPECTED_OFFICER_LEAKAGE
        assert not new_leakage, (
            "NEW committed concrete officer plist(s) — instance leakage must render from "
            f"the template + roster, never be committed: {sorted(new_leakage)}")


# ===========================================================================
# scratch-tree mutants — prove the derivation + leakage guards BITE (§12 law)
# ===========================================================================
class TestFleetTruthDerivationBites:
    def test_template_stem_extraction_is_template_only(self, tmp_path):
        d = tmp_path / "launchd"
        for n in (f"{_PREFIX}foo{_TEMPLATE_SUFFIX}", f"{_PREFIX}bar-baz{_TEMPLATE_SUFFIX}",
                  f"{_PREFIX}officer{_TEMPLATE_SUFFIX}", f"{_PREFIX}qux{_PLIST_SUFFIX}"):
            _write_plist(d, n)
        assert _template_stems(d) == {"foo", "bar-baz", "officer"}   # excludes the non-template

    def test_new_rowless_template_surfaces(self):
        # a NEW row-less template (stem not a services row, not roster) surfaces in the
        # derivation → breaks the exact-nine pin.
        derived = _derive_rowless({"chrome-profile", "newthing"}, set())
        assert "newthing" in derived
        assert derived != EXPECTED_ROWLESS_ORGANS

    def test_service_moved_out_surfaces(self):
        # `dashboard` pairs with a row at tip; drop its row → its template un-pairs and
        # becomes a row-less organ (paper-shrink), which the derivation surfaces.
        with_row = _derive_rowless({"dashboard"}, {"dashboard"})
        without_row = _derive_rowless({"dashboard"}, set())
        assert with_row == set()
        assert without_row == {"dashboard"}

    def test_paired_and_roster_are_excluded(self):
        derived = _derive_rowless({"dashboard", "officer", "chrome-profile"}, {"dashboard"})
        assert derived == {"chrome-profile"}         # dashboard paired, officer roster


class TestFleetTruthLeakageBites:
    def test_concrete_officer_extraction_excludes_template(self, tmp_path):
        d = tmp_path / "launchd"
        for n in (f"{_PREFIX}officer{_TEMPLATE_SUFFIX}", f"{_PREFIX}officer.cos{_PLIST_SUFFIX}",
                  f"{_PREFIX}officer.foo{_PLIST_SUFFIX}"):
            _write_plist(d, n)
        assert _concrete_officer_plists(d) == {
            f"{_PREFIX}officer.cos{_PLIST_SUFFIX}", f"{_PREFIX}officer.foo{_PLIST_SUFFIX}"}

    def test_new_concrete_officer_plist_is_flagged(self, tmp_path):
        d = tmp_path / "launchd"
        for n in EXPECTED_OFFICER_LEAKAGE:
            _write_plist(d, n)
        _write_plist(d, f"{_PREFIX}officer.newbie{_PLIST_SUFFIX}")   # a NEW leak
        new_leakage = _concrete_officer_plists(d) - EXPECTED_OFFICER_LEAKAGE
        assert new_leakage == {f"{_PREFIX}officer.newbie{_PLIST_SUFFIX}"}

    def test_removed_officer_plist_still_subset(self, tmp_path):
        # u3-compatibility: removing leakage keeps the tolerant subset green.
        d = tmp_path / "launchd"
        _write_plist(d, "com.cabinet.officer.cos.plist")            # only one remains
        actual = _concrete_officer_plists(d)
        assert actual <= EXPECTED_OFFICER_LEAKAGE
        assert actual - EXPECTED_OFFICER_LEAKAGE == set()
