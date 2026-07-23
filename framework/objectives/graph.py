"""framework.objectives.graph — the PURE build fold (COG-3 contract rev-1 §5.3 /
§5.4 / §5.6 / §4.1): roots + verified cortex beliefs -> canonical graph.jsonl +
graph-manifest.json under a caller-declared cache_dir.

PURITY (A-M6): every input is a declared parameter (roots_path, cache_dir, scope,
cutoff) recorded in the manifest epoch tuple — NO env read, NO clock. The sibling
cortex store (cache_dir/../cortex) is the ONE cortex read path (§5.1), served
DEFAULTS-ONLY through the whitelisted query surface. Epistemic state is DERIVED at
compile via states.derive_edge_state and written into the built answer surface —
never re-derived at serve (§5.4); the manifest carries the epoch so serve refuses
mismatches.

ROOT PARSING (§7.6): framework code imports NO yaml — the CLI owns yaml.safe_load
and hands a structure. The corpus hands build_graph a path: a canonical JSON
objectives-input file (sim1/sim5) OR the provisional roots/adapter text surface
(sim2/sim3/sim4). Both are read stdlib-only: json.loads first, else a minimal
stdlib line reader over the provisional fixture shape (no third-party parser).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; U2 (the graph + serve surface).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from framework.objectives import model, states
from framework.cortex.query import as_of, load_beliefs_verified

GRAPH_BUILDER_VERSION = "objectives-graph-builder/1"

# Graph-owned canonical cutoff shape (§7.5 fail-closed). REPLICATED, not imported:
# the §6.5 symbol pin admits only the seven cortex query-surface symbols, so the
# cortex's private query._CANON_TS_RE is RED here — it is mirrored by VALUE, the
# same idiom as states.HUMAN_VERDICT_SOURCE mirroring the consequence domain's
# _REVIEW_SOURCES. A legal-but-non-canonical cutoff ("+00:00", fractional seconds,
# or garbage) fences OPEN, so the build HARD-ERRORS on it at the _compile entry —
# even when no as_of fires (empty store / no causal edges), which is the exact
# fence-open hole cortex.as_of would otherwise be the only guard for.
_CANON_CUTOFF_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# known node kinds inferable from a `<kind>/<slug>` subject_key prefix (§4.1).
_KIND_PREFIXES = frozenset({
    "direction", "objective", "outcome", "constraint", "instrument", "intervention",
})


class SchemaRejection(Exception):
    """The PRESENCE limb (§4.1/N4): a schema-enforced field is absent (e.g. an
    objective with no root_ref). DISTINCT from states.BuildFailure (the fold's
    resolvability limb) — the two failure limbs are never collapsed to one type
    (G-M2). Presence is checked stdlib-side here because jsonschema is a
    third-party import forbidden inside framework/objectives (§6.5)."""


# ===========================================================================
# Lightweight derivation-edge view (the shape states.derive_edge_state reads)
# ===========================================================================

@dataclass(frozen=True)
class _Binding:
    subject_key: str
    belief_id: str


@dataclass(frozen=True)
class _EdgeView:
    authored: bool
    expected_effect: str
    assumptions: tuple
    admissible_subjects: frozenset
    join_spec: tuple
    evidence_bindings: tuple


# ===========================================================================
# Root parsing — stdlib only (json, else the provisional fixture line reader)
# ===========================================================================

def _strip_comment(line: str) -> str:
    """Drop a trailing `# …` comment (or a whole-line comment), honoring double
    quotes so a `#` inside a quoted statement is preserved."""
    in_quote = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quote = not in_quote
        elif ch == "#" and not in_quote and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def _scalar(text: str):
    """A provisional-shape scalar: a JSON-quoted string decodes via json.loads;
    everything else is the bare token stripped."""
    text = text.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        try:
            return json.loads(text)
        except ValueError:
            return text[1:-1]
    return text


def _flow_mapping(text: str) -> dict:
    """Parse a `{k: v, k: v}` inline mapping (the provisional nodes/edges shape)."""
    inner = text.strip()[1:-1]
    out: dict = {}
    for part in inner.split(","):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        out[key.strip()] = _scalar(value)
    return out


def _parse_provisional(raw: str) -> dict:
    """Minimal stdlib reader for the provisional roots/adapter text surface
    (fixtures: `write_roots_yml` + the sim4 nodes/edges shape). Handles top-level
    list sections, `- key: value` block items with indented continuations, and
    `- {flow: mapping}` items. Comments stripped; NO third-party parser."""
    sections: dict = {}
    current_section = None
    current_item = None
    for rawline in raw.splitlines():
        line = _strip_comment(rawline)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if indent == 0 and stripped.endswith(":") and " " not in stripped[:-1]:
            current_section = stripped[:-1]
            sections[current_section] = []
            current_item = None
            continue
        if stripped.startswith("- "):
            content = stripped[2:].strip()
            if current_section is None:
                continue
            if content.startswith("{"):
                sections[current_section].append(_flow_mapping(content))
                current_item = None
            elif ":" in content:
                key, value = content.split(":", 1)
                current_item = {key.strip(): _scalar(value)}
                sections[current_section].append(current_item)
            else:
                sections[current_section].append(_scalar(content))
                current_item = None
            continue
        if ":" in stripped and current_item is not None:
            key, value = stripped.split(":", 1)
            current_item[key.strip()] = _scalar(value)
    return sections


def _load_roots(roots_path):
    """Return (payload, is_json). JSON (the canonical objectives-input) parses
    strict; anything else is the provisional text surface (lenient)."""
    raw = Path(roots_path).read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload, True
    except ValueError:
        pass
    return _parse_provisional(raw), False


def _roots_hash(roots_path) -> str:
    """Whole-file canonical hash of the root bytes (§4.1/§5.4) — CONTENT only, so
    two builds of byte-identical roots at distinct paths agree, and a text edit is
    an honest bump."""
    return hashlib.sha256(Path(roots_path).read_bytes()).hexdigest()


# ===========================================================================
# Cortex read (§5.1) — the ONE path, defaults-only
# ===========================================================================

def _cortex_context(cortex_dir):
    """Load the sibling verified cortex store (or an empty context when absent).
    Returns (beliefs, store_hash, fold_epoch, trust_version)."""
    cortex_dir = Path(cortex_dir)
    manifest_path = cortex_dir / "fold-manifest.json"
    store_path = cortex_dir / "beliefs.jsonl"
    if not (manifest_path.exists() and store_path.exists()):
        return [], None, None, None
    beliefs = load_beliefs_verified(cortex_dir)          # C-F15 bound read
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    epoch = manifest.get("epoch", {}) if isinstance(manifest, dict) else {}
    return (beliefs, manifest.get("belief_store_hash"),
            epoch.get("engine_version"), epoch.get("trust_table_version"))


def _direction_of(beliefs, subject_key, scope, cutoff):
    """The adapter-pinned movement reading of a subject's fenced head (§5.6), or
    None when unknown. Defaults-only as_of (§5.1 discipline 1)."""
    if not beliefs:
        return None
    result = as_of(beliefs, subject_key, scope=scope, observation=cutoff)
    for view in result.views:
        value = view.value
        if isinstance(value, dict) and "observed_effect" in value:
            return value["observed_effect"]
    return None


def _first_belief_id(beliefs, subject_key, scope, cutoff):
    if not beliefs:
        return None
    result = as_of(beliefs, subject_key, scope=scope, observation=cutoff)
    return result.views[0].belief_id if result.views else None


# ===========================================================================
# Cycle detection (§11 sim1) — SCCs over depends_on, represented + flagged
# ===========================================================================

def _cycles(node_ids, depends_edges):
    """Return the sorted list of cyclic member-id lists over the depends_on
    directed graph (every edge kept — never topo-sorted away). A member set of
    size >1, or a self-loop, is a cycle."""
    adj = {nid: [] for nid in node_ids}
    for src, tgt in depends_edges:
        if src in adj and tgt in adj:
            adj[src].append(tgt)
    for nid in adj:
        adj[nid].sort()

    index = {}
    low = {}
    on_stack = {}
    stack = []
    counter = [0]
    sccs = []

    def _strongconnect(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack[v] = True
        for w in adj[v]:
            if w not in index:
                _strongconnect(w)
                low[v] = min(low[v], low[w])
            elif on_stack.get(w):
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                comp.append(w)
                if w == v:
                    break
            sccs.append(comp)

    for nid in sorted(adj):
        if nid not in index:
            _strongconnect(nid)

    self_loops = {src for src, tgt in depends_edges if src == tgt}
    cycles = []
    for comp in sccs:
        if len(comp) > 1 or (len(comp) == 1 and comp[0] in self_loops):
            cycles.append(sorted(comp))
    return sorted(cycles)


# ===========================================================================
# The compile core — used by build_graph (canonical) and build_branch (§5.3)
# ===========================================================================

def _compile(roots_path, out_dir, cortex_dir, scope, cutoff, *,
             counterfactual, assumption_overrides):
    # §5.1(2)/§7.5 fence-open guard: the ONE canonical build cutoff must be
    # canonical HERE, at the entry — a non-canonical cutoff would fence OPEN in any
    # branch where no as_of call fires (empty store / no causal edges), silently
    # recording garbage in the epoch. Hard error, graph-owned (never the cortex's
    # private regex). Covers the canonical build AND every counterfactual branch
    # cutoff (both route through this one choke point).
    if not isinstance(cutoff, str) or not _CANON_CUTOFF_RE.match(cutoff):
        raise states.BuildFailure(
            f"non-canonical build cutoff {cutoff!r}: a build cutoff must be a "
            "canonical YYYY-MM-DDTHH:MM:SSZ timestamp (§5.1(2)/§7.5) — a "
            "non-canonical cutoff fences OPEN, a hard error even when no as_of "
            "fires")
    payload, is_json = _load_roots(roots_path)
    roots_hash = _roots_hash(roots_path)
    scope = dict(scope)
    beliefs, store_hash, fold_epoch, trust_version = _cortex_context(cortex_dir)

    directions = list(payload.get("directions", []) or [])
    objectives = list(payload.get("objectives", []) or [])
    outcomes = list(payload.get("outcomes", []) or [])
    constraints = list(payload.get("constraints", []) or [])
    decl_nodes = list(payload.get("nodes", []) or [])
    indicates_edges = list(payload.get("indicates_edges", []) or [])
    causal_edges = list(payload.get("causal_edges", []) or [])

    node_records = []
    edge_records = []

    # --- direction_root nodes (subject_key = direction/<entry-digest>, §4.1) ---
    direction_by_slug = {}
    direction_node_ids = set()
    for entry in directions:
        slug = entry.get("slug")
        if slug is None:
            continue
        sk = "direction/" + model.digest({"slug": slug,
                                          "statement": entry.get("statement", "")})
        nid = model.node_id("direction_root", sk)
        direction_by_slug[slug] = nid
        direction_node_ids.add(nid)
        node_records.append({"node_id": nid, "kind": "direction_root",
                             "subject_key": sk})

    # --- objective nodes (root authentication two limbs, §4.1/N4) -------------
    objective_id_by_slug = {}
    for obj in objectives:
        slug = obj.get("slug")
        if slug is None:
            continue
        sk = "objective/" + slug
        nid = model.node_id("objective", sk)
        objective_id_by_slug[slug] = nid
        record = {"node_id": nid, "kind": "objective", "subject_key": sk}
        flags = []

        if is_json:
            # PRESENCE limb (schema): a rootless objective is a SchemaRejection —
            # NOT the fold's structural failure (N4).
            if "root_ref" not in obj:
                raise SchemaRejection(
                    f"objective {slug!r} has no root_ref (§4.1 schema PRESENCE)")
            root_slug = obj["root_ref"]
            if root_slug not in direction_by_slug:
                # a removed/edited-away root: ORPHANED, answerable-with-flag (§9 r5)
                flags.append("orphaned")
                record["root_ref"] = {"root_slug": root_slug, "roots_hash": roots_hash}
            else:
                # RESOLVABILITY limb (fold): authenticate the recorded node id +
                # roots_hash epoch — a dangling/forged ref or a stale hash is a
                # states.BuildFailure (never a schema rejection, N4/G-M2).
                recorded_node_id = obj.get("forged_root_node_id",
                                           direction_by_slug[root_slug])
                recorded_hash = obj.get("recorded_roots_hash", roots_hash)
                if recorded_node_id not in direction_node_ids:
                    raise states.BuildFailure(
                        f"objective {slug!r} root_ref {recorded_node_id!r} resolves "
                        "to no direction_root node in this build (§4.1 fold limb i)")
                if recorded_hash != roots_hash:
                    raise states.BuildFailure(
                        f"objective {slug!r} recorded roots_hash {recorded_hash!r} "
                        f"!= build roots_hash (§4.1 fold limb ii)")
                record["root_ref"] = {"node_id": recorded_node_id,
                                      "roots_hash": roots_hash}
        elif obj.get("root_ref") in direction_by_slug:
            record["root_ref"] = {"node_id": direction_by_slug[obj["root_ref"]],
                                  "roots_hash": roots_hash}

        if flags:
            record["flags"] = sorted(flags)
        node_records.append(record)

    # --- outcome nodes --------------------------------------------------------
    for oc in outcomes:
        slug = oc.get("slug")
        if slug is None:
            continue
        sk = "outcome/" + slug
        record = {"node_id": model.node_id("outcome", sk), "kind": "outcome",
                  "subject_key": sk}
        if oc.get("dimension") is not None:
            record["dimension"] = oc["dimension"]
        node_records.append(record)

    # --- constraint nodes (retained + marked, evidence refs kept — §11 sim1) --
    for cx in constraints:
        slug = cx.get("slug")
        if slug is None:
            continue
        sk = "constraint/" + slug
        bindings = []
        for esk in cx.get("evidence_subjects", []) or []:
            bindings.append({"subject_key": esk,
                             "belief_id": _first_belief_id(beliefs, esk, scope, cutoff)})
        record = {"node_id": model.node_id("constraint", sk), "kind": "constraint",
                  "subject_key": sk, "evidence_bindings": bindings,
                  # unknown never passes a floor (§4.4): a constraint is marked
                  # NOT met unless positively proven satisfied — none is provable
                  # symbolically here, so it is retained + marked unsatisfiable.
                  "met": False}
        if cx.get("dimension") is not None and cx.get("floor") is not None:
            record["floors"] = {cx["dimension"]: cx["floor"]}
        node_records.append(record)

    # --- explicit provisional nodes (sim4 adapter surface) --------------------
    node_kind_by_sk = {}
    for nrec in node_records:
        node_kind_by_sk[nrec["subject_key"]] = nrec["kind"]
    for dn in decl_nodes:
        kind = dn.get("kind")
        sk = dn.get("subject_key")
        if kind is None or sk is None:
            continue
        node_kind_by_sk[sk] = kind
        if sk not in {n["subject_key"] for n in node_records}:
            node_records.append({"node_id": model.node_id(kind, sk), "kind": kind,
                                 "subject_key": sk})

    def _kind_of(subject_key):
        if subject_key in node_kind_by_sk:
            return node_kind_by_sk[subject_key]
        prefix = subject_key.split("/", 1)[0]
        return prefix if prefix in _KIND_PREFIXES else None

    def _node_id_for(subject_key):
        kind = _kind_of(subject_key) or "outcome"
        return model.node_id(kind, subject_key)

    # --- relational edges: conflicts_with (symmetric + SORTED, never LWW) -----
    conflict_pairs = set()
    for obj in objectives:
        slug = obj.get("slug")
        if slug is None:
            continue
        src_sk = "objective/" + slug
        for peer in obj.get("conflicts_with", []) or []:
            peer_sk = "objective/" + peer
            conflict_pairs.add(frozenset({src_sk, peer_sk}))
    for pair in sorted((tuple(sorted(p)) for p in conflict_pairs)):
        a_sk, b_sk = pair                                    # canonical (a <= b)
        edge_records.append({
            "edge_id": model.edge_id(model.node_id("objective", a_sk),
                                     model.node_id("objective", b_sk),
                                     "conflicts_with", family="relational"),
            "source_node_id": model.node_id("objective", a_sk),
            "target_node_id": model.node_id("objective", b_sk),
            "relation": "conflicts_with"})

    # --- relational edges: depends_on (directional, every edge kept) ----------
    depends_pairs = []
    for obj in objectives:
        slug = obj.get("slug")
        if slug is None:
            continue
        src_sk = "objective/" + slug
        for dep in obj.get("depends_on", []) or []:
            dep_sk = "objective/" + dep
            depends_pairs.append((model.node_id("objective", src_sk),
                                  model.node_id("objective", dep_sk)))
            edge_records.append({
                "edge_id": model.edge_id(model.node_id("objective", src_sk),
                                         model.node_id("objective", dep_sk),
                                         "depends_on", family="relational"),
                "source_node_id": model.node_id("objective", src_sk),
                "target_node_id": model.node_id("objective", dep_sk),
                "relation": "depends_on"})

    # --- relational edges: indicates (instrument -> outcome trend, §4.2) ------
    for ind in indicates_edges:
        src = ind.get("source")
        tgt = ind.get("target")
        if src is None or tgt is None:
            continue
        edge_records.append({
            "edge_id": model.edge_id(_node_id_for(src), _node_id_for(tgt),
                                     ind.get("dimension", ""), family="relational"),
            "source_node_id": _node_id_for(src), "target_node_id": _node_id_for(tgt),
            "relation": "indicates", "dimension": ind.get("dimension")})

    # --- causal edges (target-kind gate + compile-time state derivation) ------
    for ce in causal_edges:
        src = ce.get("source")
        tgt = ce.get("target")
        if src is None or tgt is None:
            continue
        target_kind = _kind_of(tgt)
        # §4.2 SIM-4 structural rule: an instrument is never a legal causal target.
        model.assert_legal_causal_target(target_kind if target_kind else "unknown")
        derived = states.derive_edge_state(
            _EdgeView(authored=True, expected_effect=ce.get("expected_effect", "maintain"),
                      assumptions=(), admissible_subjects=frozenset(), join_spec=(),
                      evidence_bindings=()),
            (), cutoff)
        edge_records.append({
            "edge_id": model.edge_id(_node_id_for(src), _node_id_for(tgt),
                                     ce.get("dimension", ""), family="causal"),
            "source_node_id": _node_id_for(src), "target_node_id": _node_id_for(tgt),
            "target_kind": target_kind, "dimension": ce.get("dimension"),
            "expected_effect": ce.get("expected_effect"),
            "state": derived.state, "flags": sorted(derived.flags)})

    # --- divergence report (§5.6) — instrument/outcome opposition, display-only
    causal_targets = {ce.get("target") for ce in causal_edges}
    divergence_report = []
    for ind in indicates_edges:
        src = ind.get("source")
        tgt = ind.get("target")
        if src is None or tgt is None or tgt not in causal_targets:
            continue
        instr_dir = _direction_of(beliefs, src, scope, cutoff)
        outcome_dir = _direction_of(beliefs, tgt, scope, cutoff)
        if instr_dir is not None and outcome_dir is not None and instr_dir != outcome_dir:
            divergence_report.append({
                "instrument_node": _node_id_for(src), "outcome_node": _node_id_for(tgt),
                "dimension": ind.get("dimension"),
                "instrument_direction": instr_dir, "outcome_direction": outcome_dir})
    divergence_report.sort(key=lambda e: (e["instrument_node"], e["outcome_node"],
                                          e.get("dimension") or ""))

    # --- cycles over depends_on ----------------------------------------------
    all_node_ids = [n["node_id"] for n in node_records]
    cycles = _cycles(all_node_ids, depends_pairs)

    # --- bound subjects (the staleness instrument's source, §5.1(7)) ----------
    bound_subjects = sorted({b.subject_key for b in beliefs})

    # --- write canonical artifacts -------------------------------------------
    node_records.sort(key=lambda r: (r["node_id"]))
    edge_records.sort(key=lambda r: (r.get("relation", "causal"),
                                     r["source_node_id"], r["target_node_id"],
                                     r["edge_id"]))
    records = node_records + edge_records

    manifest = {
        "schema_version": "objectives-graph-manifest/v1",
        "epoch": {
            "graph_builder_version": GRAPH_BUILDER_VERSION,
            "roots_hash": roots_hash,
            "cortex_belief_store_hash": store_hash,
            "cortex_fold_epoch": fold_epoch,
            "trust_table_version": trust_version,
            "scope": scope,
            "cutoff": cutoff,
        },
        # §5.3 completeness: every build PARAMETER is recorded in the manifest,
        # including the roots_path the CLI injects (§7.6). This is provenance only
        # — build IDENTITY stays roots_hash (the content hash, in the epoch tuple);
        # roots_path is deliberately OUTSIDE the epoch so it never enters identity.
        "roots_path": str(roots_path),
        # §5.4/C-F15: the chained rows-hash of the graph rows (re-parsed, sorted —
        # the A-m11 discipline the epoch's cortex_belief_store_hash already uses).
        # serve_graph re-derives this from graph.jsonl and REFUSES on mismatch, so a
        # tampered/partial row can never serve silently (the manufactured-certainty
        # class). Over the ROWS only — it cannot include the manifest that holds it.
        "graph_rows_hash": _rows_chain(records),
        "divergence_report": divergence_report,
        "cycles": cycles,
        "bound_subjects": bound_subjects,
        "bound_cutoff": cutoff,
        "node_count": len(node_records),
        "edge_count": len(edge_records),
    }
    if counterfactual:
        manifest["counterfactual"] = True
        manifest["assumption_overrides"] = assumption_overrides

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":")) + "\n" for r in records)
    (out_dir / "graph.jsonl").write_text(body, encoding="utf-8")
    (out_dir / "graph-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    return {"nodes": len(node_records), "edges": len(edge_records),
            "cache_dir": str(out_dir)}


def build_graph(roots_path, cache_dir, scope, cutoff):
    """The pure canonical build (§5.3). Requires a CANONICAL cutoff (hard error
    otherwise — §7.5 fence-open guard). Reads the sibling cortex store
    (cache_dir/../cortex), derives every edge state at compile against the
    cutoff-fenced evidence, and writes canonical graph.jsonl + graph-manifest.json
    (which records every build parameter incl. roots_path, plus the graph_rows_hash
    serve binds) under cache_dir. Writes NOTHING outside cache_dir (root bytes
    byte-identical after build — §7.2/N4)."""
    cache_dir = Path(cache_dir)
    return _compile(roots_path, cache_dir, cache_dir.parent / "cortex", scope, cutoff,
                    counterfactual=False, assumption_overrides=None)


def _read_graph_rows(cache_dir):
    """Re-parse graph.jsonl into row dicts (empty when the file is absent)."""
    rows = []
    graph_path = Path(cache_dir) / "graph.jsonl"
    if graph_path.exists():
        for line in graph_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _rows_chain(rows) -> str:
    """The N1 chained hash over graph ROWS only (never the manifest that carries
    it) — sorted by canonical bytes so it is seed-independent across the C-F3
    subprocess triple (A-m11/§5.4). This is the value the manifest records as
    graph_rows_hash; serve_graph re-derives + binds it (C-F15, §5.4)."""
    chain = ""
    for row in sorted(rows, key=model.canonical_bytes):
        chain = model.digest([chain, row])
    return chain


def graph_rows_hash(cache_dir) -> str:
    """Re-derive the rows-only chained hash from graph.jsonl on disk — the serve-
    time binding value (§5.4/C-F15). A tampered/partial graph.jsonl no longer
    reproduces the manifest's recorded graph_rows_hash, so serve_graph REFUSES."""
    return _rows_chain(_read_graph_rows(cache_dir))


def chained_graph_hash(cache_dir) -> str:
    """The N1 chained hash over the RE-PARSED graph rows + manifest (never file
    bytes — A-m11), sorted, so it is seed-independent across the C-F3 subprocess
    triple (§5.4)."""
    cache_dir = Path(cache_dir)
    rows = _read_graph_rows(cache_dir)
    manifest_path = cache_dir / "graph-manifest.json"
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.exists() else {})
    return model.digest([_rows_chain(rows), manifest])
