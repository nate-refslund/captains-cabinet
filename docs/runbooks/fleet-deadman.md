# Runbook — the fleet dead-man

**What it answers:** *is this cabinet's fleet alive, dead, or can I not tell?* —
and it answers it from outside the fleet, so the fleet dying cannot suppress the
answer.

**Why it exists.** On 2026-07-25 every `com.cabinet.*` launchd label on the live
box was unloaded. Every in-repo sensor was a job in that same set, so the fault
and its detectors were removed in one act; every escalation tier terminated at
the Chair, which is itself a supervised officer. Nothing reported anything for
five days while the dashboard rendered and every gate stayed green. The only
sensor that fired lived outside the repo entirely, so a fresh hatch would have
had no survivor at all.

---

## The shape, in one paragraph

The fleet **proves it is alive** by writing a small file per source. A watcher
**outside** the fleet reads those files and produces one of three verdicts. When
— and only when — the verdict is `ALIVE` it pings an off-machine watcher. So the
absence of that ping means one of exactly three things, all of which you want to
be woken for: **the fleet is down**, **the watcher is down**, or **the machine
is down**. A watcher that must *notice* a failure fails with it; a watcher that
must be *reassured* does not.

---

## The three states, and why the third is not optional

| verdict | means | pings? | exit |
|---|---|---|---|
| `ALIVE` | every expected source pulsed inside its limit | yes | 0 |
| `DEAD` | the pulse store **answered**, and a source is stale or has never pulsed | no | 1 |
| `UNKNOWN` | the store could not be read · a pulse could not be believed · the clocks disagree · nothing is configured to expect | no | 2 |

`DEAD` and `UNKNOWN` are told apart by one observation: whether the pulse
directory's **parent** is readable. Parent readable and no pulses ⇒ I can see
where the fleet writes and it has written nothing ⇒ that is a **measurement**,
and a loud one. Parent unreadable ⇒ I cannot see the store at all ⇒ `UNKNOWN`.

This is the distinction that failed on 2026-07-25: with every label unloaded,
`launchctl list` answered perfectly well with zero cabinet rows, and the check
written for exactly that event read "answered with nothing" as "could not ask"
and switched **itself** off.

`UNKNOWN` never pings. The predicate is `state == ALIVE`, deliberately not
`state != DEAD` — the negated form turns every state the code has not thought of
yet into a silent all-clear.

---

## The two legs, and what each survives

| leg | what it is | survives | does **not** survive |
|---|---|---|---|
| **local** | `instance/config/fleetwatch.yml` + a LaunchAgent under `com.cabinet-liveness.*` | a `com.cabinet.*` fleet teardown; writes a verdict file and posts a macOS notification on a state change | logout · reboot without login · a broader teardown · the machine being off |
| **external** | the `fleet_alive` slug in `instance/config/liveness.yml` | everything above, **including the whole machine** | the ping account being deleted |

**Be honest about the local leg.** macOS offers no privilege-free domain
isolation: `gui/<uid>` is the only domain a non-root user can bootstrap into —
`launchctl bootstrap user/<uid>` and `system` both return `Bootstrap failed: 5:
Input/output error` without root (measured 2026-07-31). So the watcher shares a
domain with the fleet and survives only because the teardown names a *prefix*.
That is real but weak. **The external leg is the one that actually survives this
box, and a deployment with only the local leg is not covered.**
`--status` reports the two separately for exactly that reason.

A LaunchDaemon or a `user/<uid>` agent would give true isolation and needs
`sudo` — a Captain act, not a delegable one. The user crontab is a genuinely
independent subsystem and also needs the Captain's say-so. Both are open options,
neither is wired.

---

## Arming it (this is the hatch step — unarmed is silent, and silent looks healthy)

```bash
cp instance/config/fleetwatch.yml.example instance/config/fleetwatch.yml
cp instance/config/liveness.yml.example  instance/config/liveness.yml
$EDITOR instance/config/liveness.yml     # instance_id, base_url, the three slugs
$EDITOR instance/config/fleetwatch.yml   # keep only the sources you actually run

python3.12 cabinet/scripts/fleet-deadman.py --status    # expect local + external
python3.12 cabinet/scripts/fleet-deadman.py --dry-run   # expect a verdict, no writes

python3.12 cabinet/scripts/fleet-deadman-install.py --install
# then run the two launchctl lines it prints — it never runs them for you
```

Register the external check on your ping service with **period ~1h, grace ~30m**,
and **assign an alert channel** (API-created checks ship with an empty channel
list — 2026-07-02 drill). Slugs must be **per-instance**: N cabinets sharing one
slug make a dead instance indistinguishable from a quiet one.

---

## Verifying it — do not trust a green

A dead-man you have never starved is an assumption, not a control.

```bash
# 1. confirm ALIVE while the fleet runs
python3.12 cabinet/scripts/fleet-deadman.py --json

# 2. starve one source: stop it, or backdate its pulse past max_age_s
python3.12 -c "import json,os,time; from framework.liveness import deadman as f; \
p=os.path.join(f.pulse_dir(),'outcome-watchdog.json'); \
o=json.load(open(p)); o['ts']-=10**5; json.dump(o,open(p,'w'))"

# 3. it must flip to DEAD, stop pinging, and notify ONCE
python3.12 cabinet/scripts/fleet-deadman.py ; echo "exit=$?"    # expect exit=1

# 4. the external check must go DOWN within its grace, and the alert must ARRIVE
```

Step 4 is the one people skip and it is the only one that proves delivery.

---

## Reading it

- **verdict file** — `<fleet_liveness_dir>/fleet-state.json`. The standing signal: a
  plain file, readable with everything else on the box down.
- **notification** — fires on a *state change* only. A watcher that notifies
  every poll trains its reader to dismiss it; one that notifies once and goes
  quiet is indistinguishable from a fixed problem. Hence: transition notifies,
  file and external ping stand.
- **exit status** — a standing `1` next to the label in `launchctl list` is a
  true report about the fleet, not a broken job.

---

## Known limits, stated rather than discovered later

- **It measures the sources it is told to expect, and nothing else.** A service
  running with no `pulse()` call site is invisible to it. Two are wired today
  (`outcome-watchdog`, `officer-inbound`); adding a third is one guarded call.
- **The local leg cannot report the box being off.** Only the external leg can.
- **`rm` on a plist does not stop a loaded job** (measured 2026-07-31) — a
  removed plist with the job still resident keeps pulsing. `bootout` first.
- **The macOS notification path is not exercised by CI**, which is ubuntu. Its
  argv construction is asserted there; the `osascript` call itself is covered
  only by the manual verification above.
- **`framework/liveness/deadman.py` holds BOTH emitters** — the Captain-contact
  heartbeats and `pulse()` — because both are called from inside the thing they
  measure and both must never cost the work that earned them. The scanning, the
  decision and the notification live in `cabinet/scripts/fleet-deadman.py`,
  beside `ledger-liveness-check.py` and `healthchecks-drill.py`, because that is
  what they are: a scheduled runner that looks at this box and pings out. The
  contact legs prove the Captain lane, not fleet health; complementary, and
  neither replaces the other.
