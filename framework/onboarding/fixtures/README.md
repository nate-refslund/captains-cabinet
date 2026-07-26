# Onboarding v2 adversarial personas

These are small, deterministic First Window estates, not polished demos.

- `software-product/` is the primary dogfood case. Its release guide names a
  production command that does not exist and two documents disagree on launch.
- `client-services/` contains a delivery-date conflict across the proposal and
  project plan.
- `community-nonprofit/` uses ordinary language and contains an uncovered
  welcome-desk shift. It exercises a low-technical-confidence, accessibility-
  sensitive context without making the person's age or job a caricature.
- `enterprise-employee/` is an employee's slice of a large estate: a service
  they contribute to but do not own, a tracker CSV export, and a partial sync
  of a shared docs space. It is the only estate spanning more than one system,
  and it is deliberately NOT tuned to the detectors. Several facts in it
  matter only in the join between systems — a runbook step naming a flag the
  code deleted, an incident action item with no ticket, a ticket assigned to
  someone the roster says left, a deadline the design doc and the tracker
  disagree about. The current detectors find none of them. That miss is the
  measurement; see docs/persona-employee-slice-2026-07-26.md. Do not
  "fix" this fixture by adding content the detectors can see.

The first three estates are registered in `evaluate_personas.PERSONAS` and run
by the acceptance harness. `enterprise-employee/` is NOT, and the reason is
mechanical rather than editorial: `evaluate_personas.py` is a framework
production module, `framework_production_noncomment_lines` is a census budget
pinned at observed==max with zero headroom, and the contract file that would
carry an allowance is frozen under the COG-4 review digest. Registering the
estate costs one line and that line cannot be paid today. It is exercised
instead by `tests/test_journey.py::test_employee_estate_*`, which drive the
same `journey.act` path the harness drives and additionally pin the
measurement. Register it when the budget can move.

The evaluation requires a useful cited finding for every estate, while the
detector priority deliberately differs by context.
