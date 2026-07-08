"""Mechanical aesthetic ratchets for Cabinet World renders + map data.

IMPORT CONTRACT: this package is loaded via world-aesthetic/_loader.py under
the unique module name "world_aesthetic_gates" — NEVER as top-level "gates"
(cabinet/scripts/gates is a different, pre-existing package with that name).

Each gate module exposes check(...) -> list[finding-dict]; the runner is
../aesthetic_gates.py. Finding + map/labels schemas: see _common.py.
"""

from . import _common, _png, _synth  # noqa: F401
from . import (edge_continuity, connectivity, scale_lint,  # noqa: F401
               label_overlap, palette_coherence, clustering)

GATE_ORDER = ["edge_continuity", "connectivity", "scale_lint",
              "label_overlap", "palette_coherence", "clustering"]

GATES = {
    "edge_continuity": edge_continuity,
    "connectivity": connectivity,
    "scale_lint": scale_lint,
    "label_overlap": label_overlap,
    "palette_coherence": palette_coherence,
    "clustering": clustering,
}

FINDINGS_SCHEMA = "cabinet.world.aesthetic-findings/v1"
