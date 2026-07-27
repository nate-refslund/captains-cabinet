# Settlement migration plan

Deadline: 2026-09-30

## Scope

Move all settlement writes off the v1 router, then delete it. The dual-write
path is already gone; see ADR-0007.

## Sequencing

1. Shadow-read parity for two weeks.
2. Flip `settlement_v2_router` to default-on.
3. Delete the v1 router and its configuration.

## Open question

Nobody has confirmed who signs off the cutover.
