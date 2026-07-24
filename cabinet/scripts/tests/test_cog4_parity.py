"""COG-4 N9 — the outcome/evidence PARITY gate (§5.3, SF4; foundry L188
"outcome/evidence parity holds", made mechanical).

Contract: docs/plans/cognitive-core-phase-4-contract-2026-07-23.md §1 N9 + §5.3
+ §12 batteries. The parity law: for every operation in the pilot set + ALL
THREE §12 fixture cabinets, the descriptor-resolved tuple
`(risk_class, ceiling, undo_contract, shadow verdict)` MUST equal the
ACTION_TYPES-path tuple, recorded in `cog4-parity-record.json` (written by
`cabinet/scripts/cog4-parity.py`, the ONE sanctioned dual-plane comparator).
Any divergence is a STRUCTURAL BUILD FAILURE, never a warning.

This battery lands tests-first (W2):
  * the divergence checker + record-shape checker are defined HERE as the
    reference the CLI's record must satisfy, and are proven LIVE on synthetic
    records — including the biting negative control the §12 table demands: a
    synthetic record carrying ONE divergent tuple REDs, per member;
  * the REAL-ARTIFACT arm is vacuity-guarded (the W1-u2 idiom) — RETIREMENT
    CONDITION: retire the skip when `cabinet/scripts/cog4-parity.py` AND a
    tracked `cog4-parity-record.json` land (W5/W6); the retired arm loads the
    TRACKED record and asserts record_errors == [] and divergent_rows == []
    and that coverage spans the ENTIRE pilot set + the three fixture cabinets
    (§12 N9). The COMPANION absence assertions RED the moment either lands, so
    the skip cannot silently persist.
    CONVERTED to RECORD-KEYED (integrator corpus surgery per §13 + the unit
    contradictions[] routes, W4 landing 2026-07-24): the CLI landed in W4 v2
    (9df66b12) while the tracked record DELIBERATELY rides the W5/W6 pilot +
    fixture cabinets, so the original either-artifact companion pair would RED
    on the CLI leg alone; the arm now keys on the RECORD — still armed, still
    the N9 exit tripwire, retirement = the tracked record landing.

Record shape (the reference the CLI must produce — two INDEPENDENT legs, §5.3:
the ACTION_TYPES leg is never derived FROM the descriptor leg):
  {"schema": "cog4-parity-record/v1",
   "rows": [{"operation": "<domain>/<op>", "organ": "<name>",
             "descriptor_path":   {"risk_class", "ceiling", "undo_contract",
                                    "shadow_verdict"},
             "action_types_path": {same four members}}, ...]}
Ceiling compares as a SET (member order is presentation, not divergence);
the other three members compare exactly. An EMPTY rows list is an ERROR (the
COG-3 R-A non-empty idiom: a vacuously green parity gate is no gate).

S0: python3.12, no DB, no network, deterministic. Provenance: authored per the
2026-07-07 full-autonomy grant + the 2026-07-20 cognitive-masterplan continuous
grant (COG-4 W2 corpus, unit T3).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_PARITY_CLI_REL = "cabinet/scripts/cog4-parity.py"
_RECORD_BASENAME = "cog4-parity-record.json"

_TUPLE_MEMBERS = ("risk_class", "ceiling", "undo_contract", "shadow_verdict")
_LEGS = ("descriptor_path", "action_types_path")


# ---------------------------------------------------------------------------
# the reference checkers (what test_cog4_parity gates the REAL record with)
# ---------------------------------------------------------------------------
def record_errors(record: object) -> list[str]:
    """Shape errors — reported separately from divergence so a malformed
    record can never masquerade as a clean one."""
    errs: list[str] = []
    if not isinstance(record, dict):
        return ["record is not a mapping"]
    if record.get("schema") != "cog4-parity-record/v1":
        errs.append(f"schema must be 'cog4-parity-record/v1' "
                    f"(got {record.get('schema')!r})")
    rows = record.get("rows")
    if not isinstance(rows, list):
        return errs + ["rows must be a list"]
    if not rows:
        errs.append("rows is EMPTY — a vacuously green parity record is no "
                    "evidence (R-A non-empty idiom); the record must cover the "
                    "entire pilot set + all three fixture cabinets")
    seen_ops: set[str] = set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            errs.append(f"rows[{i}]: not a mapping")
            continue
        op = row.get("operation")
        if not isinstance(op, str) or "/" not in op:
            errs.append(f"rows[{i}]: operation must be a namespaced "
                        f"'<domain>/<operation>' id (got {op!r})")
        elif op in seen_ops:
            errs.append(f"rows[{i}]: duplicate operation {op!r}")
        else:
            seen_ops.add(op)
        for leg in _LEGS:
            leg_obj = row.get(leg)
            if not isinstance(leg_obj, dict):
                errs.append(f"rows[{i}].{leg}: missing or not a mapping")
                continue
            for member in _TUPLE_MEMBERS:
                if member == "ceiling":
                    if not isinstance(leg_obj.get("ceiling"), list):
                        errs.append(f"rows[{i}].{leg}.ceiling: must be a list")
                elif not isinstance(leg_obj.get(member), str) or not leg_obj.get(member):
                    errs.append(f"rows[{i}].{leg}.{member}: must be a non-empty string")
    return errs


def _leg_tuple(leg_obj: dict) -> tuple:
    return (
        leg_obj.get("risk_class"),
        tuple(sorted(leg_obj.get("ceiling") or [])),  # ceiling is a SET
        leg_obj.get("undo_contract"),
        leg_obj.get("shadow_verdict"),
    )


def divergent_rows(record: dict) -> list[str]:
    """Every row whose two legs disagree, with the diverging members named.
    Precondition: record_errors(record) == [] (the gate asserts both)."""
    out: list[str] = []
    for row in record.get("rows", []):
        if not isinstance(row, dict):
            continue
        a = row.get("descriptor_path") or {}
        b = row.get("action_types_path") or {}
        if _leg_tuple(a) == _leg_tuple(b):
            continue
        diverging = []
        for member in _TUPLE_MEMBERS:
            va, vb = a.get(member), b.get(member)
            if member == "ceiling":
                va, vb = sorted(va or []), sorted(vb or [])
            if va != vb:
                diverging.append(f"{member}: descriptor={va!r} vs action_types={vb!r}")
        out.append(f"{row.get('operation')!r} DIVERGES on "
                   + "; ".join(diverging))
    return out


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
def _row(op: str, organ: str, risk: str, ceiling: list[str], undo: str,
         verdict: str, overrides: dict | None = None) -> dict:
    base = {"risk_class": risk, "ceiling": list(ceiling), "undo_contract": undo,
            "shadow_verdict": verdict}
    other = dict(base)
    other.update(overrides or {})    # overrides mutate ONLY the action_types leg
    return {"operation": op, "organ": organ,
            "descriptor_path": base, "action_types_path": other}


def _clean_record() -> dict:
    return {
        "schema": "cog4-parity-record/v1",
        "rows": [
            _row("undo/sweep.expired", "undo-sweep",
                 "read_only_dispatch", [], "none", "shadow_ok"),
            _row("census/rooms.count", "world-census",
                 "reversible", [], "delete_window(3600)", "shadow_ok"),
            # ceiling ORDER differs between the legs — a set, never a divergence
            {"operation": "mail/outbox.flush", "organ": "outbox-organ",
             "descriptor_path": {
                 "risk_class": "external_comms",
                 "ceiling": ["external_comms", "network_write"],
                 "undo_contract": "journal:outbox-flush",
                 "shadow_verdict": "always_gated"},
             "action_types_path": {
                 "risk_class": "external_comms",
                 "ceiling": ["network_write", "external_comms"],
                 "undo_contract": "journal:outbox-flush",
                 "shadow_verdict": "always_gated"}},
        ],
    }


# ---------------------------------------------------------------------------
# live fixture proofs — the checker works, and the mutant BITES, NOW
# ---------------------------------------------------------------------------
class TestParityCheckerLive:
    def test_clean_record_is_clean(self, tmp_path):
        record = _clean_record()
        # prove the JSON round-trip too — the real gate reads a file
        p = tmp_path / _RECORD_BASENAME
        p.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        loaded = json.loads(p.read_text(encoding="utf-8"))
        assert record_errors(loaded) == []
        assert divergent_rows(loaded) == []

    def test_ceiling_order_is_presentation_not_divergence(self):
        record = _clean_record()
        assert divergent_rows(record) == []          # row 3 has re-ordered ceilings

    @pytest.mark.parametrize("member,mutation", [
        ("risk_class", {"risk_class": "spend"}),
        ("ceiling", {"ceiling": ["spending"]}),
        ("undo_contract", {"undo_contract": "delete_window(60)"}),
        ("shadow_verdict", {"shadow_verdict": "act_with_undo"}),
    ])
    def test_single_member_divergence_reds(self, member, mutation):
        """THE §12 N9 negative control: a synthetic parity record with ONE
        divergent tuple REDs — proven per tuple member."""
        record = _clean_record()
        record["rows"][0] = _row("undo/sweep.expired", "undo-sweep",
                                 "read_only_dispatch", [], "none", "shadow_ok",
                                 overrides=mutation)
        assert record_errors(record) == []
        div = divergent_rows(record)
        assert len(div) == 1, div
        assert "undo/sweep.expired" in div[0]
        assert member in div[0], div[0]
        # the untouched rows stay clean — divergence is per-row, never global
        assert "census/rooms.count" not in div[0]

    def test_empty_rows_record_is_an_error(self):
        assert any("EMPTY" in e for e in
                   record_errors({"schema": "cog4-parity-record/v1", "rows": []}))

    def test_malformed_records_error(self):
        assert record_errors([]) == ["record is not a mapping"]
        assert any("schema" in e for e in
                   record_errors({"schema": "wrong/v9", "rows": [_clean_record()["rows"][0]]}))
        # a leg missing a tuple member is a SHAPE error, never silently equal
        record = _clean_record()
        del record["rows"][0]["action_types_path"]["shadow_verdict"]
        assert any("shadow_verdict" in e for e in record_errors(record))
        # a flat (non-namespaced) operation id is a shape error (§5.2 namespace law)
        record2 = _clean_record()
        record2["rows"][0]["operation"] = "sweep_expired"
        assert any("namespaced" in e for e in record_errors(record2))
        # duplicate operations cannot double-count coverage
        record3 = _clean_record()
        record3["rows"].append(record3["rows"][0])
        assert any("duplicate" in e for e in record_errors(record3))


# ---------------------------------------------------------------------------
# the real-artifact arm — vacuity-guarded until W5/W6 land the tracked record
# (record-keyed since the W4 landing: the CLI landed in W4 v2)
# ---------------------------------------------------------------------------
def _tracked_records(repo: Path) -> list[Path]:
    """Every tracked cog4-parity-record.json in the working tree (the record's
    landing location is W5/W6's choice — search, don't guess), .git excluded."""
    return [p for p in repo.rglob(_RECORD_BASENAME) if ".git" not in p.parts]


class TestParityGateRealArtifact:
    def test_real_record_arm(self):
        """VACUITY GUARD, RECORD-KEYED (converted by integrator corpus surgery
        per §13 + the unit contradictions[] routes, W4 landing 2026-07-24: the
        CLI landed in W4 v2 (9df66b12) while the tracked record DELIBERATELY
        rides the W5/W6 pilot + fixture cabinets, so the original
        either-artifact companion pair would have gone RED on the CLI leg
        alone; the arm now keys on the RECORD — still armed, still the N9 exit
        tripwire) — RETIREMENT CONDITION: retire this skip when a tracked
        cog4-parity-record.json lands (W5/W6); the retired arm loads THE
        tracked record and asserts record_errors == [] and divergent_rows ==
        [] and coverage spans the entire pilot set + the three §12 fixture
        cabinets (N9: any divergence is a structural build failure). The
        COMPANION assertions below RED the moment the record appears (or the
        landed CLI vanishes), so the skip cannot silently persist (the W1-u2
        idiom)."""
        cli = _REPO / _PARITY_CLI_REL
        records = _tracked_records(_REPO)
        assert cli.exists(), (
            f"{_PARITY_CLI_REL} VANISHED — the record-keyed arm presumes the "
            f"landed W4 comparator; the N9 gate lost its record writer")
        assert records == [], (
            f"a {_RECORD_BASENAME} exists in the tree ({records}) — retire this "
            f"vacuity skip and gate it per the docstring RETIREMENT CONDITION")
        pytest.skip(
            f"VACUITY: {_RECORD_BASENAME} absent this phase-stage (the record "
            f"rides the W5/W6 pilot + fixtures; the CLI landed W4 v2) — the "
            f"divergence checker is proven live on synthetic records above; "
            f"retire when the tracked record lands.")
