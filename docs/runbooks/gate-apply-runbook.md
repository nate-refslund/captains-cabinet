# Gate-Apply Runbook — the DARK germline code-apply lane (SOV-8, D15)

**Status: DARK.** Nothing in this lane applies code today. `gate.ratify`
produces evidence packs LIVE; the apply half (`cabinet/scripts/gate-apply.sh`
+ the `com.cabinet.gate-apply` root daemon) ships disabled, is loaded by **no
setup script** (pinned by `framework/learning/tests/test_gate_apply_dark.py`),
and is armed only by the Captain, explicitly, after the unprivileged sandbox
verify harness exists. Until then germline code apply stays **Captain-manual
in every posture** — the spec's directive-f exemption extended to the apply
lane itself.

## The pieces

| Piece | State | What it does |
|---|---|---|
| `framework/learning/gate.py` `ratify()` | **LIVE** | S0–S5 evidence pipeline for self-improvement code diffs. Applies nothing, ever. |
| `framework/learning/gate.py` `run_gate_review()` | **LIVE** (sovereign-gated) | D16 fuel: stamps `verdict_gate` confirms on acted rows clearing the 5-condition machine bar. Guardian ⇒ no-op. |
| `framework/learning/apply_watch.py` | **LIVE** (decisions only) | 72h watch ledger; returns `rollback / close / watch` decisions. Executes nothing. |
| `cabinet/scripts/gate-apply.sh` | **DARK** | verify (unprivileged) / apply (root, non-executing hash-matched `git apply`) / watch (rollback executor). |
| `cabinet/launchd/com.cabinet.gate-apply.plist` | **DARK** | Root daemon for `watch`, `Disabled=true`, `RunAtLoad=false`. |

## The stage pipeline (`gate.ratify`)

- **S0 scope** — refuses any diff touching a Ring-0 path per
  `framework/policies/immutable-core.yml` (every class: files, dirs,
  runtime_appended, hook_protected). An **unreadable** enumeration also
  refuses. Refusal files a deduped `kind=decision` need (eval-019).
- **S1 verify** — full pytest + golden-eval shells, **unprivileged only**
  (the default runner refuses `euid==0`; there is no root pytest anywhere in
  this lane). Needs a prepared candidate worktree; without one it fails
  closed: *"sandbox harness not built"*.
- **S2 falsifier** — the falsifier corpus, same runner discipline.
- **S3 ceilings** — six hard ceilings × 5 states × {guardian, sovereign}
  against the live floor: no cell may resolve unconditional `auto`.
  Candidate code is never imported into the gate's process.
- **S4 archive** — content-hash-named variant archive
  (`shared/interfaces/gate-evidence/variants/<sha16>.patch`).
- **S5 verdict** — `pass | fail | refused`; pack written to
  `shared/interfaces/gate-evidence/pack-<sha16>.json` with
  `applies_nothing: true` stamped in.

First failing stage short-circuits; later stages record `skipped`.

## What consumes the evidence

- **Today (dark):** the Captain. A `pass` pack is the review artifact for a
  manual apply in a `germline-lock.sh unlock` window.
- **`capability_gaps.can_install`** — sovereign + non-ceiling + a passing
  pack for the gap may allow an install **only when no Captain decision
  exists**; a Captain decline is absolute in every posture, and the
  ceiling-touch veto is absolute everywhere.
- **Once armed:** the daemon's `watch` pass evaluates `apply_watch`
  decisions and executes recorded revert plans.

## Refusal matrix (`gate-apply.sh`)

| Condition | Result |
|---|---|
| `instance/config/posture.yml` absent or not `schg`-locked | refuse (`apply`) — an unlocked estate means a Captain edit window is open |
| `pack.json` verdict ≠ `pass` | refuse |
| sha256(`bundle.patch`) ≠ `pack.json.sha256` | refuse — forged pack |
| diff touches Ring-0 per the **locked live tree's** `immutable-core.yml` (never the bundle's copy) | refuse |
| `verify` as root without a drop path | refuse — no root pytest |
| test mode (`CABINET_GATE_APPLY_TEST=1`) targeting the live repo | refuse — scratch `CABINET_GATE_APPLY_ROOT` only |

## Arming the daemon (Captain-only, later)

Do **not** do this until the unprivileged sandbox verify harness exists and
you have decided to arm it:

```bash
sudo cp cabinet/launchd/com.cabinet.gate-apply.plist /Library/LaunchDaemons/
sudo launchctl load -w /Library/LaunchDaemons/com.cabinet.gate-apply.plist
```

Disarm:

```bash
sudo launchctl bootout system/com.cabinet.gate-apply
sudo rm /Library/LaunchDaemons/com.cabinet.gate-apply.plist
```

§8 step 9 of the sovereign build spec is the standing instruction: **do NOT
load it** as part of the posture flip.

## 72h watch + rollback

`gate-apply.sh apply` records `{pack_id, applied_at, revert_plan}` via
`apply_watch.record_apply` (O_APPEND JSONL,
`shared/interfaces/gate-apply-watch.jsonl`). `apply_watch.evaluate()`:

- red signal inside 72h (a kind frozen after the apply, a red canary
  receipt, or any daemon-injected probe) ⇒ **rollback** decision carrying
  the recorded plan (`git -c core.hooksPath=/dev/null apply -R <variant>`);
- 72h clean ⇒ **close**;
- otherwise ⇒ **watch**.

Only the daemon executes decisions; the module never mutates the tree.

## Manual apply today (the ONLY apply path while dark)

1. Read the pack: `shared/interfaces/gate-evidence/pack-<sha16>.json` —
   verdict must be `pass`, stages S0–S4 all recorded.
2. `sudo bash cabinet/scripts/germline-lock.sh unlock`
3. `git -c core.hooksPath=/dev/null apply shared/interfaces/gate-evidence/variants/<sha16>.patch`
4. Run the suite; commit; `sudo bash cabinet/scripts/germline-lock.sh lock`
5. Optionally open a watch row yourself:
   `python3.12 -c "from framework.learning.apply_watch import record_apply; record_apply('pack-<sha16>', revert_plan='git -c core.hooksPath=/dev/null apply -R shared/interfaces/gate-evidence/variants/<sha16>.patch')"`
