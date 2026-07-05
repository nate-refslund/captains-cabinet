"""``flavor_a`` — this deployment's Flavor-A (captain Nate, screenpipe brain)
instance code, importable once ``instance/flavor-a`` is on ``sys.path`` (the
``framework.sources`` resolver adds it via the joined literal
``"instance/flavor-a"``; the autoreply cell uses the same convention).

Instance-scoped by construction: modules here MAY import ``framework`` AND the
screenpipe ``_shared`` libs — the launcher coupling ``framework/`` CORE must not
carry. Framework never imports this package (the one-way ``framework/ → instance/``
layer-separation boundary, ``cabinet/scripts/check-layer-separation.sh``).

Kept import-light (no side effects at package load) so binding a source stays
cheap: the heavy screenpipe imports live inside the adapter's methods, fired only
on real use.
"""
