"""Scoped auto-reply (graduated autonomy — the FIRST auto-send to a human).

Captain choice (2026-06-25, "let's try (a) for this case"): when Kristoffer
sends a UAT bug report on Teams, the cabinet sends him a bounded ACK directly —
scoped to him + UAT only — instead of waiting for the Captain to tap "send" on a draft.

This is the first time the cabinet auto-sends to a human, so the whole package
is built safety-first and ships DISARMED (the kill-switch defaults OFF). See
``kristoffer_uat.py`` for the mechanism and ``docs/`` for the design note.
"""
