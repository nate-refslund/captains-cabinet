"""Gate 3 — scale lint (MAP): 16px source grid + entity height band.

Rules (the giant-barn ratchet):
  * every placed region's [x,y,w,h] must be 16px multiples (SCALE_MISALIGNED);
  * a sheet whose native grid is 48px is the giant-barn class — LimeZu packs
    ship 16/32/48px prerendered scale variants and a 48px-source region in a
    16px world renders 3x too big (SCALE_48PX_SOURCE); any non-16 grid errors
    (SCALE_NON16_SOURCE);
  * sheets absent from map["sheets"] fall back to a name heuristic for the
    48px variants (…48x48…, @3x) and otherwise warn once (SCALE_SHEET_UNKNOWN)
    + flag all-48-multiple regions as suspect (SCALE_SUSPECT_48);
  * entity-layer sprites must sit in the charset band: LimeZu charsets are
    16px wide x 16..32px tall rows at 1x — outside that is a mis-scaled actor
    (SCALE_ENTITY_BAND).
"""

from __future__ import annotations

import re

from . import _common as C

GATE = "scale_lint"
GRID = 16
ENTITY_BAND = (16, 32)  # min/max px for entity sprite width AND height
_NAME_48 = re.compile(r"48x48|[_-]48(?:px)?(?![0-9])|@3x", re.IGNORECASE)


def check(map_data: dict, config: dict | None = None) -> list[dict]:
    cfg = config or {}
    band_lo, band_hi = cfg.get("entity_band", ENTITY_BAND)
    grid = cfg.get("grid_px", GRID)
    sheets = map_data.get("sheets", {})
    findings: list[dict] = []
    unknown_warned: set = set()

    for layer in map_data.get("layers", []):
        lname = layer.get("name", "?")
        kind = layer.get("kind", "")
        for t in layer.get("tiles", []):
            px, py, pw, ph = t["region"]
            where = {"layer": lname, "cell": [t["x"], t["y"]]}
            data = {"sheet": t["sheet"], "region": [px, py, pw, ph]}

            if px % grid or py % grid or pw % grid or ph % grid:
                findings.append(C.finding(
                    GATE, "SCALE_MISALIGNED", C.SEV_ERROR,
                    f"region {data['region']} from '{t['sheet']}' is not "
                    f"{grid}px-grid aligned", where=where, data=data))

            sheet = sheets.get(t["sheet"])
            if sheet is not None:
                sgrid = sheet.get("grid", grid)
                if sgrid == 48:
                    findings.append(C.finding(
                        GATE, "SCALE_48PX_SOURCE", C.SEV_ERROR,
                        f"sheet '{t['sheet']}' is a 48px-grid source — the "
                        "giant-barn class (3x prerender in a 16px world)",
                        where=where, data={**data, "sheet_grid": sgrid}))
                elif sgrid != grid:
                    findings.append(C.finding(
                        GATE, "SCALE_NON16_SOURCE", C.SEV_ERROR,
                        f"sheet '{t['sheet']}' grid is {sgrid}px, world grid "
                        f"is {grid}px", where=where,
                        data={**data, "sheet_grid": sgrid}))
            else:
                if _NAME_48.search(t["sheet"]):
                    findings.append(C.finding(
                        GATE, "SCALE_48PX_SOURCE", C.SEV_ERROR,
                        f"sheet '{t['sheet']}' looks like a 48px-scale "
                        "variant by name — the giant-barn class",
                        where=where, data=data))
                else:
                    if t["sheet"] not in unknown_warned:
                        unknown_warned.add(t["sheet"])
                        findings.append(C.finding(
                            GATE, "SCALE_SHEET_UNKNOWN", C.SEV_WARN,
                            f"sheet '{t['sheet']}' not declared in "
                            "map.sheets — grid unverifiable", data=data))
                    if (pw >= 48 and ph >= 48
                            and not px % 48 and not py % 48
                            and not pw % 48 and not ph % 48):
                        findings.append(C.finding(
                            GATE, "SCALE_SUSPECT_48", C.SEV_WARN,
                            f"region {data['region']} of undeclared sheet "
                            f"'{t['sheet']}' is all-48px-multiples — "
                            "possible 48px-scale source",
                            where=where, data=data))

            if kind == "entity":
                if not (band_lo <= pw <= band_hi and band_lo <= ph <= band_hi):
                    findings.append(C.finding(
                        GATE, "SCALE_ENTITY_BAND", C.SEV_ERROR,
                        f"entity sprite {pw}x{ph}px outside charset band "
                        f"{band_lo}..{band_hi}px", where=where,
                        data={**data, "band": [band_lo, band_hi]}))
    return C.cap_findings(findings, GATE)
