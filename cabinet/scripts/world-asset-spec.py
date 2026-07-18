#!/usr/bin/env python3.12
"""world-asset-spec.py — canonical asset worklist/checklist generator (spec-gen).

Turns the world grammar (the REAL law files, parsed live — never a hardcoded
copy) into the canonical asset checklist consumed by BOTH:
  * the artist — the promised per-phase checklist (one era = one phase via
    --eras; era-agnostic sections ride the `camp` phase), grouped by the art
    brief's phase order: village core → harbor → law/observatory/fields →
    services → UI & props, with the ship estate and animation families as
    separate sections;
  * the forge (cabinet/scripts/world-asset-forge.py) — its machine worklist.

Inputs (law family, world-data class):
  cabinet/world/growth-ladders.yml   ERA×RUNG growth ladders (rung truth)
  cabinet/world/morphology.yml       bound elements + codex.day0 art notes
  cabinet/world/show-grammar.yml     animation/overlay families
  cabinet/world/asset-worklist-supplement.yml  curated overlay (districts,
      ladder-coverage map, meanings, size/frames hints, extra entries)

Expansion law (mirrors spec docs/plans/world-unified-spec-v2-2026-07-09.md
§15.1–15.3 — ERA styles, RUNG measures):
  * per ladder, vocab words repeated across eras dedupe into unique FAMILIES,
    each recording every era it serves;
  * tier/flag/per_lane ladders emit one entry per (family × rung state),
    skipping rung states literally named "none" (bare_pole / empty_plinth /
    dark_cairn / bucket_empty ARE real art and are kept);
  * count-mode ladders emit one entry per family, annotated "rendered N×"
    (count rungs repeat the same sprite);
  * morphology entries emit one day-0 entry each (the two meta axis entries
    are excluded; entries whose art a ladder already supplies are marked
    covered_by:<ladder> instead of duplicated; scope:dark ⇒ staged);
  * animation families derive from show-grammar block content (actor anims
    from vocab.anims at officer + apprentice scale, idle program, group
    table meeting, weather rain strip+splash — fog/storm/sun are renderer
    tint/light passes, no sprite —, construction site phases + wright crew,
    fauna per species with staged flags, killswitch lever states + far-zoom
    pin, mailbox flag up/down, and the voyage cross-ref which reuses the
    harbor_boat ladder families and needs no new art).

Honesty contract:
  * PRE-FLIGHT: the ladders file must pass cabinet/scripts/world-growth-
    validate.py (loaded via importlib — its ERA_NAMES/MODES/CLASSES are
    reused, never re-hardcoded); refusal ⇒ exit 2, nothing written.
  * unknown YAML keys ⇒ stderr WARNING (schema drift made visible);
    missing required keys ⇒ REFUSED, exit 2.
  * deterministic output: no timestamps, no RNG, insertion-order iteration
    (installer determinism law) — regenerate-and-diff IS the freshness check.
  * an --eras filtered run refuses to write the canonical default paths
    (the tracked canon can never be silently clobbered with a subset).

Outputs:
  --out-json  machine worklist  {schema: cabinet.world.asset-worklist/v1,
              sources: {path: sha256}, counts, entries: [...]}  (entries are
              one-line JSON objects — reviewable line diffs)
  --out-md    human checklist grouped by phase/district (checkbox rows)

Suggested canvas sizes come from the ladder class (great 96×96, quick 32×32,
texture 16×16), per-block animation defaults, and supplement overrides — all
validated as 16-px grid multiples (world-asset-gate.py GRID law).

Exit codes: 0 = generated; 2 = refused (validator, schema drift, bad args).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parents[1]

DEFAULT_LADDERS = REPO / "cabinet" / "world" / "growth-ladders.yml"
DEFAULT_MORPHOLOGY = REPO / "cabinet" / "world" / "morphology.yml"
DEFAULT_SHOW_GRAMMAR = REPO / "cabinet" / "world" / "show-grammar.yml"
DEFAULT_SUPPLEMENT = REPO / "cabinet" / "world" / "asset-worklist-supplement.yml"
DEFAULT_OUT_JSON = REPO / "cabinet" / "world" / "asset-worklist.json"
DEFAULT_OUT_MD = REPO / "cabinet" / "world" / "asset-checklist.md"

WORKLIST_SCHEMA = "cabinet.world.asset-worklist/v1"
SUPPLEMENT_SCHEMA = "cabinet.world.asset-worklist-supplement/v1"
GRID = 16  # world-asset-gate.py law: every canvas a 16-px grid multiple

# Art-brief phase order (the artist's production phases). Ship estate and
# animation families render as their own separate sections after phase 5.
DISTRICT_ORDER = [
    "village_core",
    "harbor",
    "law_observatory_fields",
    "services",
    "ui_props",
    "ship_estate",
]
DISTRICT_TITLES = {
    "village_core": "Village core",
    "harbor": "Harbor",
    "law_observatory_fields": "Law / Observatory / Fields",
    "services": "Services",
    "ui_props": "UI & props",
    "ship_estate": "Ship estate",
    "unassigned": "Unassigned (no district mapping — fix the supplement)",
}
UNASSIGNED = "unassigned"

# Default suggested canvas by ladder class (grid multiples; supplement overrides).
CLASS_SIZES = {"great": (96, 96), "quick": (32, 32), "texture": (16, 16)}
MORPH_DEFAULT_SIZE = (32, 32)

# The two morphology META entries describe the ERA/RUNG axes themselves (law
# machinery, not world surfaces) — excluded from the checklist by policy.
# Drift honesty: their absence, or a NEW entry whose mechanism_path points at
# the axis law files, is warned about.
META_MORPH_IDS = ("era_vocabulary", "ladder_rungs")
AXIS_LAW_PATHS = (
    "cabinet/world/growth-ladders.yml",
    "cabinet/scripts/world-growth-validate.py",
)

# Known-key registries (schema-drift warnings — parse the real file, warn on
# anything new so drift is never silent).
KNOWN_LADDERS_TOP = {"schema", "version", "candidate", "calibrated", "era", "ladders"}
KNOWN_LADDER_KEYS = {"metric", "source", "verified", "mode", "base", "at",
                     "rungs", "hysteresis_evals", "class", "vocab"}
KNOWN_MORPH_TOP = {"version", "law", "entries"}
KNOWN_MORPH_ENTRY = {"id", "represents", "source_binding", "scope", "tier",
                     "replay", "base", "codex"}
KNOWN_CODEX = {"represents", "mechanism_path", "day0"}
# show-grammar blocks this tool consumes; known-but-unconsumed blocks don't
# warn (verbs/stations map actors to fixtures, not new art; night/scenes/etc.
# are renderer law with no sprite demand beyond what other sections carry).
CONSUMED_SHOW_BLOCKS = ("vocab", "idle_program", "group_scenes", "weather",
                        "construction", "fauna", "apprentices",
                        "killswitch_lever", "mailbox_view", "voyage")
KNOWN_SHOW_UNCONSUMED = {"version", "fallback", "verbs", "night",
                         "killswitch_scene", "scenes", "commute",
                         "portrait_rail", "roof_cutaway", "chart_table_view"}
KNOWN_SUPPLEMENT_TOP = {"schema", "version", "districts", "coverage",
                        "meanings", "size_overrides", "animated", "extra_entries"}


class SpecError(Exception):
    """Refusal — printed as `spec-gen REFUSED:` and exits 2."""


def warn(msg: str) -> None:
    print(f"spec-gen WARN: {msg}", file=sys.stderr)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel_to_repo(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def load_yaml(path: Path, what: str) -> dict:
    if not path.is_file():
        raise SpecError(f"{what} file not found: {path}")
    try:
        doc = yaml.safe_load(path.read_text())
    except Exception as exc:
        raise SpecError(f"{what} is unparseable YAML ({path}): {exc}") from exc
    if not isinstance(doc, dict):
        raise SpecError(f"{what} top level must be a mapping ({path})")
    return doc


def load_validator():
    """Load cabinet/scripts/world-growth-validate.py (dash-named) via importlib.

    Truth-gate reuse: its validate() refuses malformed/untruthful ladder
    configs, and its ERA_NAMES/MODES/CLASSES constants are the single source
    for era/mode vocabulary here (never re-hardcoded)."""
    vpath = SCRIPT_DIR / "world-growth-validate.py"
    if not vpath.is_file():
        raise SpecError(f"validator not found at {vpath} — cannot pre-flight the ladders file")
    spec = importlib.util.spec_from_file_location("world_growth_validate", vpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def slug(token: str, ctx: str) -> str:
    """Id tokens: lowercase [a-z0-9_]. Anything else is slugified with a warning
    (downstream forge path construction must never receive traversal-capable ids)."""
    out = "".join(c if (c.isascii() and (c.isalnum() or c == "_")) else "_"
                  for c in str(token).lower()).strip("_")
    if out != str(token):
        warn(f"{ctx}: token {token!r} slugified to {out!r}")
    if not out:
        raise SpecError(f"{ctx}: token {token!r} slugifies to nothing — unusable id")
    return out


def first_sentence(text: str, cap: int = 170) -> str:
    text = " ".join(str(text or "").split())
    idx = text.find(". ")
    if idx > 0:
        text = text[: idx + 1]
    return text[:cap].rstrip()


def warn_unknown(mapping: dict, known: set, ctx: str) -> None:
    for key in mapping:
        if key not in known:
            warn(f"{ctx}: unknown key {key!r} (schema drift? tool ignores it)")


def parse_size(value, ctx: str) -> tuple[int, int]:
    if isinstance(value, str) and "x" in value:
        try:
            w, h = (int(p) for p in value.lower().split("x", 1))
        except ValueError as exc:
            raise SpecError(f"{ctx}: size {value!r} must be WxH integers") from exc
    else:
        raise SpecError(f"{ctx}: size {value!r} must be a 'WxH' string")
    if w <= 0 or h <= 0 or w % GRID or h % GRID:
        raise SpecError(f"{ctx}: size {w}x{h} must be positive multiples of {GRID} (grid law)")
    return w, h


def prefix_lookup(table: dict, entry_id: str):
    """Longest boundary-safe prefix match: key == id or id startswith key + '.'"""
    best_key, best_val = None, None
    for key, val in table.items():
        if entry_id == key or entry_id.startswith(key + "."):
            if best_key is None or len(key) > len(best_key):
                best_key, best_val = key, val
    return best_val


# ── supplement ──────────────────────────────────────────────────────────────

def load_supplement(path: Path | None, ladder_ids: list[str]) -> dict:
    if path is None or not path.is_file():
        if path is not None:
            warn(f"supplement not found at {path} — defaults only (districts will be '{UNASSIGNED}')")
        return {"districts": {"ladders": {}, "morphology": {}}, "coverage": {},
                "meanings": {}, "size_overrides": {}, "animated": {}, "extra_entries": []}
    doc = load_yaml(path, "supplement")
    warn_unknown(doc, KNOWN_SUPPLEMENT_TOP, "supplement")
    if doc.get("schema") != SUPPLEMENT_SCHEMA:
        raise SpecError(f"supplement schema must be '{SUPPLEMENT_SCHEMA}', got {doc.get('schema')!r}")
    districts = doc.get("districts") or {}
    if not isinstance(districts, dict):
        raise SpecError("supplement districts must be a mapping {ladders: {...}, morphology: {...}}")
    for group in ("ladders", "morphology"):
        for name, dist in (districts.get(group) or {}).items():
            if dist not in DISTRICT_ORDER:
                raise SpecError(f"supplement districts.{group}.{name}: unknown district {dist!r} "
                                f"(must be one of {DISTRICT_ORDER})")
    coverage = doc.get("coverage") or {}
    for morph_id, ladder in coverage.items():
        if ladder not in ladder_ids:
            raise SpecError(f"supplement coverage.{morph_id}: ladder {ladder!r} does not exist "
                            "in growth-ladders.yml — untruthful coverage refused")
    size_overrides = {}
    for key, val in (doc.get("size_overrides") or {}).items():
        size_overrides[key] = parse_size(val, f"supplement size_overrides.{key}")
    animated = {}
    for key, val in (doc.get("animated") or {}).items():
        if not isinstance(val, int) or val < 2:
            raise SpecError(f"supplement animated.{key}: frame count must be an int >= 2, got {val!r}")
        animated[key] = val
    extra = doc.get("extra_entries") or []
    if not isinstance(extra, list):
        raise SpecError("supplement extra_entries must be a list")
    for i, entry in enumerate(extra):
        if not isinstance(entry, dict) or not all(k in entry for k in ("id", "district", "meaning")):
            raise SpecError(f"supplement extra_entries[{i}]: each needs at least id, district, meaning")
        if entry["district"] not in DISTRICT_ORDER:
            raise SpecError(f"supplement extra_entries[{i}]: unknown district {entry['district']!r}")
    return {"districts": {"ladders": districts.get("ladders") or {},
                          "morphology": districts.get("morphology") or {}},
            "coverage": coverage, "meanings": doc.get("meanings") or {},
            "size_overrides": size_overrides, "animated": animated, "extra_entries": extra}


# ── entry construction ──────────────────────────────────────────────────────

def make_entry(entry_id, section, district, obj, source_file, source_key, eras,
               era_word, rung_state, mode, cls, day0, day0_state, staged,
               covered_by, size, animated, frames, meaning, notes) -> dict:
    return {
        "id": entry_id, "section": section, "district": district, "object": obj,
        "source": {"file": source_file, "key": source_key},
        "eras": eras, "era_word": era_word, "rung_state": rung_state,
        "mode": mode, "class": cls, "day0": day0, "day0_state": day0_state,
        "staged": staged, "covered_by": covered_by,
        "size": ({"w": size[0], "h": size[1]} if size else None),
        "animated": animated, "frames": frames, "meaning": meaning, "notes": notes,
    }


def apply_hints(entry: dict, supp: dict) -> dict:
    size = prefix_lookup(supp["size_overrides"], entry["id"])
    if size is not None:
        entry["size"] = {"w": size[0], "h": size[1]}
    frames = prefix_lookup(supp["animated"], entry["id"])
    if frames is not None:
        entry["animated"], entry["frames"] = True, frames
    return entry


def families_of(vocab: dict, era_names: list[str]) -> list[dict]:
    """Era-dedupe: vocab words repeated across eras collapse into one family
    recording every era it serves (era order preserved)."""
    fams, seen = [], {}
    for era in era_names:
        if era not in vocab:
            continue
        word = vocab[era]
        if word in seen:
            seen[word]["eras"].append(era)
        else:
            fam = {"word": word, "eras": [era]}
            seen[word] = fam
            fams.append(fam)
    return fams


def expand_ladders(doc: dict, supp: dict, validator, src_rel: str,
                   morph_meaning_by_ladder: dict) -> list[dict]:
    warn_unknown(doc, KNOWN_LADDERS_TOP, f"{src_rel}")
    ladders = doc.get("ladders")
    if not isinstance(ladders, dict) or not ladders:
        raise SpecError(f"{src_rel}: ladders block missing or empty")
    entries = []
    for name, lad in ladders.items():
        ctx = f"{src_rel}:ladders.{name}"
        if not isinstance(lad, dict):
            raise SpecError(f"{ctx}: must be a mapping")
        warn_unknown(lad, KNOWN_LADDER_KEYS, ctx)
        for req in ("metric", "mode", "rungs", "class", "vocab"):
            if req not in lad:
                raise SpecError(f"{ctx}: missing required key '{req}' — cannot derive art entries")
        mode, rungs, cls, vocab = lad["mode"], lad["rungs"], lad["class"], lad["vocab"]
        if mode not in validator.MODES:
            raise SpecError(f"{ctx}: unknown mode {mode!r} (validator MODES {sorted(validator.MODES)})")
        if cls not in validator.CLASSES:
            raise SpecError(f"{ctx}: unknown class {cls!r} (validator CLASSES {sorted(validator.CLASSES)})")
        if not isinstance(vocab, dict) or not vocab:
            raise SpecError(f"{ctx}: vocab must be a non-empty era→word mapping")
        if not isinstance(rungs, list) or not rungs:
            raise SpecError(f"{ctx}: rungs must be a non-empty list")
        district = supp["districts"]["ladders"].get(name)
        if district is None:
            warn(f"{ctx}: no district mapping in the supplement — filed under '{UNASSIGNED}'")
            district = UNASSIGNED
        meaning = (supp["meanings"].get(name)
                   or morph_meaning_by_ladder.get(name)
                   or f"Growth ladder '{name}' — metric {lad['metric']} ({lad.get('source', '?')})")
        lname = slug(name, ctx)
        size = CLASS_SIZES[cls]
        base_notes = []
        if mode == "flag" and lad.get("at") is not None:
            base_notes.append(f"flag raises at metric >= {lad['at']}")
        if mode == "per_lane":
            base_notes.append("per_lane mode — one ring per product lane; rung state is per lane")
        for fam in families_of(vocab, validator.ERA_NAMES):
            word = slug(fam["word"], ctx)
            if mode == "count":
                n_max = len(rungs) - 1
                notes = base_notes + [
                    f"count mode — one sprite per real thing, rendered up to {n_max}x "
                    f"(top rung: {rungs[-1]})"]
                entries.append(apply_hints(make_entry(
                    f"ladder.{lname}.{word}", "ladder", district, name, src_rel,
                    f"ladders.{name}", fam["eras"], fam["word"], None, mode, cls,
                    False, None, False, None, size, False, None, meaning, notes), supp))
            else:
                for idx, rung in enumerate(rungs):
                    if rung == "none":
                        continue  # literal 'none' = no art; bare_pole/dark_cairn etc. ARE art
                    day0 = idx == 0 and "camp" in fam["eras"]
                    entries.append(apply_hints(make_entry(
                        f"ladder.{lname}.{word}.{slug(rung, ctx)}", "ladder", district,
                        name, src_rel, f"ladders.{name}", fam["eras"], fam["word"],
                        rung, mode, cls, day0, None, False, None, size, False, None,
                        meaning, list(base_notes)), supp))
    return entries


def expand_morphology(doc: dict, supp: dict, src_rel: str) -> list[dict]:
    warn_unknown(doc, KNOWN_MORPH_TOP, src_rel)
    raw = doc.get("entries")
    if not isinstance(raw, list) or not raw:
        raise SpecError(f"{src_rel}: entries list missing or empty")
    present_ids = {e.get("id") for e in raw if isinstance(e, dict)}
    for meta in META_MORPH_IDS:
        if meta not in present_ids:
            warn(f"{src_rel}: expected meta axis entry '{meta}' is absent (schema drift?)")
    entries = []
    for morph in raw:
        if not isinstance(morph, dict):
            raise SpecError(f"{src_rel}: every morphology entry must be a mapping")
        mid = morph.get("id")
        if not mid:
            raise SpecError(f"{src_rel}: morphology entry without an id")
        ctx = f"{src_rel}:entries[id={mid}]"
        if mid in META_MORPH_IDS:
            continue  # axis-law meta entries — machinery, not world art
        warn_unknown(morph, KNOWN_MORPH_ENTRY, ctx)
        codex = morph.get("codex")
        if not isinstance(codex, dict) or not codex.get("day0"):
            raise SpecError(f"{ctx}: codex.day0 is required (the day-0 art requirement)")
        warn_unknown(codex, KNOWN_CODEX, ctx + ".codex")
        if not morph.get("represents"):
            raise SpecError(f"{ctx}: represents is required")
        if str(codex.get("mechanism_path", "")) in AXIS_LAW_PATHS:
            warn(f"{ctx}: mechanism_path points at axis law — possible new meta entry "
                 f"not in the exclusion policy {META_MORPH_IDS}")
        staged = morph.get("scope") == "dark"
        covered_by = supp["coverage"].get(mid)
        district = supp["districts"]["morphology"].get(mid)
        if district is None:
            warn(f"{ctx}: no district mapping in the supplement — filed under '{UNASSIGNED}'")
            district = UNASSIGNED
        notes = []
        if staged:
            notes.append("staged/dark — nothing renders until its feed or art lands")
        if covered_by:
            notes.append(f"no new art — sprite family supplied by ladder '{covered_by}'")
        entries.append(apply_hints(make_entry(
            f"morph.{slug(mid, ctx)}.day0", "morphology", district, mid, src_rel,
            f"entries[id={mid}]", [], None, None, None, None,
            (not staged) and covered_by is None, str(codex["day0"]), staged,
            (f"ladder.{covered_by}" if covered_by else None), MORPH_DEFAULT_SIZE,
            False, None, first_sentence(morph["represents"]), notes), supp))
    return entries


def _require_block(show: dict, name: str, src_rel: str) -> dict:
    block = show.get(name)
    if not isinstance(block, dict) or not block:
        raise SpecError(f"{src_rel}: consumed block '{name}' missing or empty — "
                        "the animation section cannot be derived honestly")
    return block


def expand_animation(show: dict, supp: dict, src_rel: str) -> tuple[list[dict], list[str]]:
    known = set(KNOWN_SHOW_UNCONSUMED) | set(CONSUMED_SHOW_BLOCKS)
    warn_unknown(show, known, src_rel)
    entries: list[dict] = []
    section_notes: list[str] = []

    def add(item_id, obj, key, day0, day0_state, staged, covered_by, size,
            animated, frames, meaning, notes):
        entries.append(apply_hints(make_entry(
            item_id, "animation", None, obj, src_rel, key, [], None, None, None,
            None, day0, day0_state, staged, covered_by, size, animated, frames,
            meaning, notes), supp))

    vocab = _require_block(show, "vocab", src_rel)
    anims = vocab.get("anims")
    if not isinstance(anims, list) or not anims:
        raise SpecError(f"{src_rel}: vocab.anims missing — actor animation set underivable")
    appr = _require_block(show, "apprentices", src_rel)
    appr_meaning = first_sentence((appr.get("codex") or {}).get("represents", "Apprentices — real subagent actors."))
    for anim in anims:
        a = slug(anim, f"{src_rel}:vocab.anims")
        add(f"anim.actor.officer_{a}", "actor", "vocab.anims", True, None, False, None,
            (16, 32), True, 4,
            f"Officer actor — '{anim}' loop; every grammar verb renders one of {'/'.join(map(str, anims))} at a real officer's station.",
            [])
        add(f"anim.actor.apprentice_{a}", "actor", "vocab.anims + apprentices", False, None,
            False, None, (16, 32), True, 4,
            f"{appr_meaning} — '{anim}' loop at apprentice scale (small transient figure).",
            [f"cap {appr.get('cap_per_officer', '?')} per officer, overflow renders a +N chip"])

    idle = _require_block(show, "idle_program", src_rel)
    idle_meaning = first_sentence((idle.get("codex") or {}).get("represents", "Idle wander."))
    waypoints = ", ".join(map(str, idle.get("waypoints") or []))
    add("anim.idle_program.wander", "idle_program", "idle_program", True,
        str((idle.get("codex") or {}).get("day0") or ""), False, None, (16, 32), True, 4,
        f"{idle_meaning} — daytime wander between waypoints ({waypoints}).",
        ["may reuse the walk cycle frames"])
    if idle.get("night_station"):
        add("anim.idle_program.sleep", "idle_program", "idle_program.night_station", True,
            None, False, None, (16, 32), True, 2,
            f"Officer asleep at the rest alcove ('{idle['night_station']}') during the night bucket.",
            [])

    groups = _require_block(show, "group_scenes", src_rel)
    for gname, group in groups.items():
        if not isinstance(group, dict):
            raise SpecError(f"{src_rel}: group_scenes.{gname} must be a mapping")
        gmeaning = first_sentence((group.get("codex") or {}).get("represents", gname))
        add(f"anim.group_scenes.{slug(gname, src_rel)}", "group_scenes",
            f"group_scenes.{gname}", False, None, False, None, (16, 32), True, 2,
            gmeaning,
            [f"seated meeting poses at station '{group.get('station', '?')}' "
             f"for >= {group.get('min_officers', 2)} officers"])

    weather = _require_block(show, "weather", src_rel)
    states = weather.get("states")
    if not isinstance(states, dict) or not states:
        raise SpecError(f"{src_rel}: weather.states missing — weather art underivable")
    if "rain" in states:
        rain_meaning = first_sentence((states["rain"].get("codex") or {}).get("represents", "Rain."))
        add("anim.weather.rain_strip", "weather", "weather.states.rain", False, None,
            False, None, (16, 16), True, 3,
            f"{rain_meaning} — tiling diagonal rain strip overlay.", [])
        add("anim.weather.rain_splash", "weather", "weather.states.rain", False, None,
            False, None, (16, 16), True, 2,
            "Ground splash frames paired with the rain strip.", [])
    no_art = [s for s in states if s != "rain"]
    if no_art:
        section_notes.append(
            "weather states with no sprite art (renderer tint/light passes, per the "
            f"install cozy notes): {', '.join(no_art)} — rain is the only sprite-bearing state")

    cons = _require_block(show, "construction", src_rel)
    phases = cons.get("phases")
    if not isinstance(phases, dict) or not phases:
        raise SpecError(f"{src_rel}: construction.phases missing — site stages underivable")
    cons_meaning = first_sentence((cons.get("codex") or {}).get("represents", "Construction."))
    for phase, frac in phases.items():
        add(f"anim.construction.{slug(phase, src_rel)}", "construction",
            f"construction.phases.{phase}", False, None, False, None, (48, 48), False, None,
            f"Construction site — '{phase}' stage dressing (progress {frac}).",
            ["site states are static dressings; progress is a pure function of (T0, now_tick)"])
    if cons.get("crew_rule"):
        add("anim.construction.wright_crew", "construction", "construction.crew_rule",
            False, None, False, None, (16, 32), True, 4,
            f"{cons_meaning} — seeded wright crew sprites ({cons['crew_rule']}).",
            ["decorative-honest staging of a real witnessed transition, never officer claims"])

    fauna = _require_block(show, "fauna", src_rel)
    for species, spec_f in fauna.items():
        if not isinstance(spec_f, dict):
            raise SpecError(f"{src_rel}: fauna.{species} must be a mapping")
        staged = bool(spec_f.get("staged", False))
        smeaning = first_sentence((spec_f.get("codex") or {}).get("represents", species))
        notes = [f"home: {spec_f.get('home', '?')}"]
        if staged:
            notes.append("STAGED — awaiting art: PRIORITY checklist item "
                         "(nothing renders until its art lands; flip staged off in the binding commit)")
        else:
            notes.append("replacement-of-existing (currently rendered from pack art being replaced)")
        add(f"anim.fauna.{slug(species, src_rel)}", "fauna", f"fauna.{species}",
            not staged, str((spec_f.get("codex") or {}).get("day0") or ""), staged, None,
            (16, 16), True, 2, smeaning, notes)

    lever = _require_block(show, "killswitch_lever", src_rel)
    lever_meaning = first_sentence((lever.get("codex") or {}).get("represents", "Killswitch lever."))
    placement = first_sentence(str(lever.get("placement", "")), cap=120)
    for state, extra in (
        ("up", "lever up — normal state, never pulled"),
        ("armed", "armed — amber glow, auto-expires"),
        ("pulled", "pulled — the one red interactive element anywhere"),
        ("far_pin", "far-zoom 6-px lever pin at the same anchor (16-px canvas)"),
    ):
        add(f"anim.killswitch_lever.{state}", "killswitch_lever", "killswitch_lever",
            state in ("up", "far_pin"), None, False, None, (16, 16),
            state == "armed", (2 if state == "armed" else None),
            f"{lever_meaning} — {extra}.", ([f"placement: {placement}"] if placement else []))

    mailbox = _require_block(show, "mailbox_view", src_rel)
    mb_meaning = first_sentence((mailbox.get("codex") or {}).get("represents", "Mailbox."))
    for state, extra in (("flag_up", "flag raised while Captain decisions wait"),
                         ("flag_down", "flag down — empty box")):
        add(f"anim.mailbox.{state}", "mailbox_view", "mailbox_view", False, None, False,
            None, (16, 16), False, None, f"{mb_meaning} — {extra}.",
            ["structure binding is morphology mailbox_pending (staged until the P1 feed lands)"])

    voyage = _require_block(show, "voyage", src_rel)
    v_meaning = first_sentence((voyage.get("codex") or {}).get("represents", "Voyage."))
    add("anim.voyage.harbor_boat", "voyage", "voyage", False, None, False,
        "ladder.harbor_boat", None, False, None, v_meaning,
        ["no new art — reuses the harbor_boat ladder era families; "
         "the voyage block binds position/dressing only (dual-view D7)"])
    return entries, section_notes


def expand_extras(supp: dict) -> list[dict]:
    entries = []
    for extra in supp["extra_entries"]:
        entries.append(apply_hints(make_entry(
            slug_id_passthrough(extra["id"]), extra.get("section", "extra"),
            extra["district"], extra.get("object", extra["id"]),
            "cabinet/world/asset-worklist-supplement.yml", "extra_entries",
            list(extra.get("eras", [])), extra.get("era_word"), extra.get("rung_state"),
            None, None, bool(extra.get("day0", False)), extra.get("day0_state"),
            bool(extra.get("staged", False)), extra.get("covered_by"),
            parse_size(extra["size"], f"extra_entries.{extra['id']}") if extra.get("size") else MORPH_DEFAULT_SIZE,
            bool(extra.get("animated", False)), extra.get("frames"),
            extra["meaning"], list(extra.get("notes", []))), supp))
    return entries


def slug_id_passthrough(entry_id: str) -> str:
    parts = [slug(p, f"extra_entries.{entry_id}") for p in str(entry_id).split(".") if p]
    return ".".join(parts)


# ── worklist assembly ───────────────────────────────────────────────────────

def build_worklist(ladders_path: Path, morph_path: Path, show_path: Path,
                   supplement_path: Path | None, eras_filter: list[str] | None) -> dict:
    validator = load_validator()
    # PRE-FLIGHT: the rung source of truth must be valid before anything derives from it.
    errors = validator.validate(ladders_path.resolve())
    if errors:
        detail = "\n  - ".join(errors[:20])
        raise SpecError(f"growth-ladders pre-flight failed world-growth-validate "
                        f"({len(errors)} problem(s)):\n  - {detail}")
    if eras_filter:
        bad = [e for e in eras_filter if e not in validator.ERA_NAMES]
        if bad:
            raise SpecError(f"--eras {bad} not in era names {validator.ERA_NAMES}")

    ladders_doc = load_yaml(ladders_path, "growth-ladders")
    morph_doc = load_yaml(morph_path, "morphology")
    show_doc = load_yaml(show_path, "show-grammar")
    supp = load_supplement(supplement_path, list((ladders_doc.get("ladders") or {}).keys()))

    # Inverse coverage gives ladders a represents-derived meaning fallback.
    morph_meaning_by_ladder = {}
    for morph in (morph_doc.get("entries") or []):
        if isinstance(morph, dict) and morph.get("id") in supp["coverage"]:
            morph_meaning_by_ladder[supp["coverage"][morph["id"]]] = first_sentence(
                morph.get("represents", ""))

    ladder_entries = expand_ladders(ladders_doc, supp, validator,
                                    rel_to_repo(ladders_path), morph_meaning_by_ladder)
    morph_entries = expand_morphology(morph_doc, supp, rel_to_repo(morph_path))
    anim_entries, section_notes = expand_animation(show_doc, supp, rel_to_repo(show_path))
    extra_entries = expand_extras(supp)

    if eras_filter:
        fset = set(eras_filter)
        keep_agnostic = "camp" in fset  # era-agnostic sections ride the first phase
        ladder_entries = [e for e in ladder_entries if fset & set(e["eras"])]
        morph_entries = morph_entries if keep_agnostic else []
        anim_entries = anim_entries if keep_agnostic else []
        extra_entries = [e for e in extra_entries
                         if (fset & set(e["eras"])) or (not e["eras"] and keep_agnostic)]

    entries = ladder_entries + morph_entries + anim_entries + extra_entries
    seen_ids = set()
    for entry in entries:
        if entry["id"] in seen_ids:
            raise SpecError(f"duplicate entry id {entry['id']!r} — id scheme must stay stable/unique")
        seen_ids.add(entry["id"])

    by_district: dict[str, int] = {}
    for entry in entries:
        if entry["district"]:
            by_district[entry["district"]] = by_district.get(entry["district"], 0) + 1
    counts = {
        "ladder": len(ladder_entries), "morphology": len(morph_entries),
        "animation": len(anim_entries), "extra": len(extra_entries),
        "total": len(entries),
        "day0": sum(1 for e in entries if e["day0"]),
        "staged": sum(1 for e in entries if e["staged"]),
        "covered_no_new_art": sum(1 for e in entries if e["covered_by"]),
        "new_art": sum(1 for e in entries if not e["covered_by"]),
        "by_district": {d: by_district[d] for d in DISTRICT_ORDER + [UNASSIGNED] if d in by_district},
    }
    sources = {rel_to_repo(p): sha256_of(p) for p in (ladders_path, morph_path, show_path)}
    if supplement_path is not None and supplement_path.is_file():
        sources[rel_to_repo(supplement_path)] = sha256_of(supplement_path)
    return {
        "schema": WORKLIST_SCHEMA,
        "version": 1,
        "generator": "cabinet/scripts/world-asset-spec.py",
        "era_names": list(validator.ERA_NAMES),
        "era_filter": list(eras_filter) if eras_filter else None,
        "sources": sources,
        "counts": counts,
        "section_notes": {"animation": section_notes},
        "entries": entries,
    }


# ── serialization ───────────────────────────────────────────────────────────

def dump_json(doc: dict) -> str:
    """Pretty head + one line per entry (reviewable line diffs, deterministic)."""
    head = {k: v for k, v in doc.items() if k != "entries"}
    head_json = json.dumps(head, indent=2, ensure_ascii=False)
    assert head_json.endswith("}")
    entry_lines = ",\n".join(
        "    " + json.dumps(e, ensure_ascii=False, separators=(", ", ": "))
        for e in doc["entries"])
    return (head_json[:-1].rstrip().rstrip(",")
            + ',\n  "entries": [\n' + entry_lines + "\n  ]\n}\n")


def _tags(entry: dict) -> str:
    tags = []
    if entry["day0"]:
        tags.append("[day-0]")
    if entry["staged"]:
        tags.append("[STAGED — priority]")
    if entry["covered_by"]:
        tags.append(f"[covered → {entry['covered_by']}]")
    if entry["animated"]:
        tags.append(f"[animated {entry['frames'] or '?'}f]")
    return (" " + " ".join(tags)) if tags else ""


def _row(entry: dict) -> str:
    bits = [f"`{entry['id']}`"]
    if entry["era_word"]:
        bits.append(f"**{entry['era_word']}** ({'/'.join(entry['eras'])})")
    if entry["rung_state"]:
        bits.append(f"rung `{entry['rung_state']}`")
    if entry["size"]:
        bits.append(f"{entry['size']['w']}×{entry['size']['h']}")
    row = f"- [ ] {' · '.join(bits)}{_tags(entry)}"
    if entry["day0_state"]:
        row += f" — day-0: {entry['day0_state']}"
    for note in entry["notes"]:
        row += f"\n  - {note}"
    return row


def _object_heading(entry: dict) -> str:
    if entry["section"] == "ladder":
        return (f"### `{entry['object']}` — {entry['mode']} ladder, class {entry['class']}\n\n"
                f"{entry['meaning']}\n")
    return f"### `{entry['object']}` — {entry['section']}\n\n{entry['meaning']}\n"


def dump_markdown(doc: dict) -> str:
    counts = doc["counts"]
    lines = [
        "# Cabinet World — canonical asset checklist",
        "",
        "> GENERATED by `cabinet/scripts/world-asset-spec.py` — do not hand-edit;",
        "> regenerate-and-diff is the freshness check (deterministic: no timestamps).",
        "",
        f"Era scope: **{', '.join(doc['era_filter']) if doc['era_filter'] else 'ALL eras'}**"
        " — era-agnostic sections (morphology day-0 objects, animation families)"
        " ride the `camp` phase when filtering.",
        "",
        "Sources:",
        "",
    ]
    for path, digest in doc["sources"].items():
        lines.append(f"- `{path}` — sha256 `{digest[:12]}…`")
    lines += [
        "",
        f"Counts: **{counts['total']}** entries — {counts['ladder']} ladder · "
        f"{counts['morphology']} morphology · {counts['animation']} animation"
        + (f" · {counts['extra']} extra" if counts.get("extra") else "")
        + f" — day-0 {counts['day0']} · staged {counts['staged']} · "
          f"covered (no new art) {counts['covered_no_new_art']} · new art {counts['new_art']}",
        "",
        "Legend: `[day-0]` = appears in the day-0 egg render · `[STAGED]` = awaiting"
        " art/feed, nothing renders until it lands (priority) · `[covered → x]` = no"
        " new sprite, art supplied by x · sizes are suggested canvases on the 16-px grid.",
        "",
    ]
    world = [e for e in doc["entries"] if e["section"] in ("ladder", "morphology", "extra")]
    phases = [d for d in DISTRICT_ORDER if d != "ship_estate"]
    for num, district in enumerate(phases, start=1):
        block = [e for e in world if e["district"] == district]
        if not block:
            continue
        lines.append(f"## Phase {num} — {DISTRICT_TITLES[district]}")
        lines.append("")
        lines.extend(_district_body(block))
    ship = [e for e in world if e["district"] == "ship_estate"]
    if ship:
        lines.append("## Ship estate (separate section)")
        lines.append("")
        lines.extend(_district_body(ship))
    unassigned = [e for e in world if e["district"] == UNASSIGNED]
    if unassigned:
        lines.append(f"## {DISTRICT_TITLES[UNASSIGNED]}")
        lines.append("")
        lines.extend(_district_body(unassigned))
    anim = [e for e in doc["entries"] if e["section"] == "animation"]
    if anim:
        lines.append("## Animation families (separate section)")
        lines.append("")
        for note in doc["section_notes"].get("animation", []):
            lines.append(f"> NOTE: {note}")
            lines.append("")
        lines.extend(_district_body(anim, group_key="object"))
    lines.append(f"_Total: {counts['total']} entries._")
    lines.append("")
    return "\n".join(lines)


def _district_body(block: list[dict], group_key: str = "object") -> list[str]:
    lines: list[str] = []
    current = None
    for entry in block:
        marker = (entry["section"], entry[group_key])
        if marker != current:
            current = marker
            lines.append(_object_heading(entry))
        lines.append(_row(entry))
    lines.append("")
    return lines


# ── main ────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate the canonical Cabinet World asset worklist (JSON) "
                    "+ artist checklist (markdown) from the world grammar files.")
    ap.add_argument("--ladders", type=Path, default=DEFAULT_LADDERS)
    ap.add_argument("--morphology", type=Path, default=DEFAULT_MORPHOLOGY)
    ap.add_argument("--show-grammar", type=Path, default=DEFAULT_SHOW_GRAMMAR)
    ap.add_argument("--supplement", type=Path, default=DEFAULT_SUPPLEMENT,
                    help="curated overlay (districts/coverage/meanings/sizes); "
                         "missing file = defaults with warnings")
    ap.add_argument("--eras", type=str, default=None,
                    help="comma-separated era filter (the per-phase artist checklist; "
                         "one era = one phase). Filtered runs must name explicit outputs.")
    ap.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    args = ap.parse_args(argv)

    try:
        eras_filter = None
        if args.eras:
            eras_filter = [e.strip() for e in args.eras.split(",") if e.strip()]
            for out, canon in ((args.out_json, DEFAULT_OUT_JSON), (args.out_md, DEFAULT_OUT_MD)):
                if out.resolve() == canon.resolve():
                    raise SpecError(
                        "--eras filtered runs refuse to write the canonical default "
                        f"path {canon} — pass explicit --out-json/--out-md "
                        "(the tracked canon is never a silent subset)")
        doc = build_worklist(args.ladders, args.morphology, args.show_grammar,
                             args.supplement, eras_filter)
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(dump_json(doc))
        args.out_md.write_text(dump_markdown(doc))
    except SpecError as exc:
        print(f"spec-gen REFUSED: {exc}", file=sys.stderr)
        return 2
    counts = doc["counts"]
    scope = ",".join(eras_filter) if eras_filter else "ALL"
    print(f"asset-worklist: {counts['ladder']} ladder + {counts['morphology']} morphology + "
          f"{counts['animation']} animation"
          + (f" + {counts['extra']} extra" if counts.get("extra") else "")
          + f" = {counts['total']} entries (era scope: {scope})")
    print(f"  day-0 {counts['day0']} · staged {counts['staged']} · covered {counts['covered_no_new_art']}"
          f" · new-art {counts['new_art']}")
    print("  by district: " + " · ".join(f"{d} {n}" for d, n in counts["by_district"].items()))
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
