"""Outcome-probe machinery (blueprint Gate 2 / plan-B Phase B2).

Probes observe EXTERNAL artifacts (deploys, releases, commits, support threads)
and emit schema-valid outcome events joined back to the proposal that caused
them. ``correlation`` is the join standard every probe imports (B2.1); the
individual probes (B2.3-B2.7) land on top of it.
"""
