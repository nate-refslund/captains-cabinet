# cabinet/officer-skills — post-compaction skill-refresh lists

One `<officer>.txt` per officer id. The germline hook
`cabinet/scripts/hooks/post-compact.sh` cats
`cabinet/officer-skills/<officer>.txt` into the post-compaction injection
("OFFICER-SPECIFIC — also read:"). A missing file degrades gracefully — the
hook falls back to "re-read your role definition".

This directory ships only GENERIC role files in the egg (egg plan row R090).
Deployment-specific refresh lists (captain name, bot handles, lane and
personal-estate references) live in `instance/officer-skills/<officer>.txt`
and are materialized here as untracked, gitignored symlinks (see
`instance/officer-skills/README.md`):

    ln -s ../../instance/officer-skills/<officer>.txt cabinet/officer-skills/<officer>.txt

Live-roster overlays as of 2026-07-07: `cos`, `comms-officer`, `polads-ceo`,
`stephie-ceo` — the full active portfolio roster
(`instance/config/roster.yml`).

The retired work-preset fleet files (`coo.txt`, `cpo.txt`, `cro.txt`,
`cto.txt`) were deleted 2026-07-07 (audit #24a): they targeted the retired
5-officer fleet, referenced skills/paths that no longer exist, and `cto.txt`
codified the removed `TeamCreate` primitive (gone since CLI v2.1.178 — see
the `agent-team-workflow` skill). If a `work`-preset deployment needs refresh
lists, generate them fresh from the preset role defs in
`presets/work/agents/` — do not resurrect the deleted files.
