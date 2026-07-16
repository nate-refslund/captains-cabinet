# instance/officer-skills — deployment officer-skill overlays

Post-compaction skill-refresh content that is specific to THIS deployment
(captain name, bot handles, personal-estate references) lives here — not in
`cabinet/officer-skills/`, which ships only the generic role files in the egg
(egg plan row R090).

The consumer is germline and reads one fixed path
(`cabinet/scripts/hooks/post-compact.sh` → `cabinet/officer-skills/<officer>.txt`),
so a deployment overlay is materialized as an **untracked symlink** — same
pattern as the derived `.claude/agents/` copies:

    ln -s ../../instance/officer-skills/<officer>.txt cabinet/officer-skills/<officer>.txt

The symlinks are gitignored (see `.gitignore` "officer-skill overlays" block);
re-create them if lost (e.g. after `git clean -fdx`). A missing overlay
degrades gracefully — the hook falls back to "re-read your role definition".

Current overlays (the full live roster): `cos.txt`, `comms-officer.txt`
(moved out of `cabinet/officer-skills/` by egg plan row R090), plus
`acme-ceo.txt`, `widgets-ceo.txt` (added 2026-07-07, audit #24a — the two
lane CEOs previously had no refresh file at all).
