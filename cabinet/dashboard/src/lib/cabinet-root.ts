import path from 'path'

/**
 * CABINET_ROOT resolver — single source for the running checkout's root.
 *
 * The live deployment is native Mac launchd: start-dashboard.sh /
 * start-officer-mac.sh export CABINET_ROOT and it always wins. When unset
 * (bare `npm run dev` / vitest in cabinet/dashboard), fall back to two
 * directories above the dashboard's cwd — the dashboard lives at
 * <root>/cabinet/dashboard. The extinct Docker default /opt/founders-cabinet
 * is gone (egg plan R086).
 *
 * A function, not a module constant, so the env var is honored per call
 * (tests and long-lived server processes may set it after module load).
 */
export function cabinetRoot(): string {
  return process.env.CABINET_ROOT || path.resolve(process.cwd(), '..', '..')
}

/** Join path segments onto the resolved cabinet root. */
export function cabinetPath(...segments: string[]): string {
  return path.join(cabinetRoot(), ...segments)
}
