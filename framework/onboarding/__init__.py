"""framework.onboarding — the Chair's autonomous product-onboarding pipeline.

research_repo (read a product repo → profile) → build_lane_plan (profile →
answers lane-entry + plugin manifest + gated proposals + germline diffs) →
onboard_lane (render the lane-CEO + readiness report; SAFE-by-default — never
executes gated/external/germline actions, only proposes them).

genesis (ONBOARD-1/2, Perfect Cabinet Wave A): the hatch-end half — the org
PROPOSES 2–4 outcome cards from the cabinet-init answers (propose-only,
``instance/config/outcomes-proposed.yml``) and attempts the genesis research
brief into the Library shelf (claude CLI, fixed argv; honest IOU on failure).
Feeds the LOCAL-FIRST first briefing via ``genesis_intake_items``.

quiet_hours (Phase-2 interview question, Captain insight 2026-07-17): the
present-the-default quiet-hours question — ``render_question`` reads the
LIVE framework default (never hardcoded), ``apply_answer`` materializes
keep/change/disable through ``framework.attention.charter.amend`` (fixed
verb enum, fail-closed, never widening the quiet-hours floor).
"""
