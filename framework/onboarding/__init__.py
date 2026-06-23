"""framework.onboarding — the Chair's autonomous product-onboarding pipeline.

research_repo (read a product repo → profile) → build_lane_plan (profile →
answers lane-entry + plugin manifest + gated proposals + germline diffs) →
onboard_lane (render the lane-CEO + readiness report; SAFE-by-default — never
executes gated/external/germline actions, only proposes them).
"""
