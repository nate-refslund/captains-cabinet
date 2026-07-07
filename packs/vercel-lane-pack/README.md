# vercel-lane-pack

Deployment skills for Cabinet lanes that ship on Vercel:

- `deploy-and-verify` — push → poll Vercel until READY → validate live →
  only then announce (with the high-tempo batching variant)
- `engineering-development-loop` — plan → execute → spawned review → fix →
  commit, ending in Vercel deploy verification

**Copied, not moved.** Parallel copies of the skills in `.claude/skills/`;
the core plugin still ships the originals this wave. Skip this pack entirely
if your lanes do not deploy on Vercel — that is the point of carving it out.

The skills reference `$VERCEL_TOKEN` / `$PROJECT_ID` / `$TEAM_ID` as
environment placeholders; no credentials ship in this pack.

Install: `/plugin install vercel-lane-pack@captains-cabinet-marketplace`, or
the governed path via `instance/config/extensions.yml` (see
`cabinet/docs/cabinet-plugin-installation.md` § Capability packs).

Extension gate: `bash cabinet/scripts/validate-extension.sh packs/vercel-lane-pack`
(manifest: `manifest.yml`).
