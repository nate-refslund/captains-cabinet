"""Outcome lifecycle acts — the governance half of an outcome's life.

Onboarding DERIVES drafts (``framework.onboarding.genesis`` owns the
propose-only staging file). This package owns what happens to a draft
AFTERWARDS: ratification, the one act that turns a proposed card into a
responsibility the org may compile.

It lives here rather than beside genesis because a proposal will come from
more than one organ (a discovery pass, a supervisor's gap, an operator's own
words), and because ratifying is a decision about the outcome lifecycle, not a
step of onboarding.
"""
