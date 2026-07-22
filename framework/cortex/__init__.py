"""framework.cortex — the shadow temporal epistemic world model ("Cortex").

COG-2. A DISPOSABLE, read-only bitemporal projection over domain truth: it
answers "what did we believe, as of when, on what evidence" and NEVER becomes a
second authority (foundry.md §4.3). Rebuildable-projection ownership is declared
in cabinet/config/cognitive-architecture-contract.yml.

Import-inert by design: importing this package pulls in no submodule, no driver,
no clock, no environment read. Import framework.cortex.belief / .engine /
.adapters explicitly. No authority/action code imports this package (the shadow
boundary is mechanically gated in a later COG-2 unit).
"""
from __future__ import annotations

__all__: list[str] = []
