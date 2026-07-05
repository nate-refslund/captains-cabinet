# Package marker so pytest imports the suite below as `gates.tests.*`.
# Without it, gates/tests and cabinet/scripts/lib/tests (plus the other
# top-level */tests dirs) all claim the package name `tests`, and a combined
# invocation fails collection with ModuleNotFoundError ('tests.test_gate_3_hash').
