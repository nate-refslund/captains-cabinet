# Evidence HP-1/2/3 deploy ceremony — fresh-cabinet launch (Captain sudo)

**This document is the hand-off artifact for the launch checklist.** It is
the ONE place that sequences everything the HP-1/2/3 batch left dark. The
branch that ships it executes NONE of this: every service is
`disabled: true`, no signing config exists, no OS user is created, and the
unconfigured tree is byte-identical to pre-HP behavior (proven — see
`shared/interfaces/reviews/evidence-hp-preconditions-cp1.md`). Each step
below is Captain-run; every command that needs root is written with
`sudo` explicitly. Per-step source of truth is the named runbook — if
this page and a step's runbook ever disagree, the runbook wins and this
page is the bug.

Design of record: whole-cabinet evidence design 2026-07-16 §2.3 (HP-1
identity/key isolation, HP-2 independent recomputation, HP-3 authenticated
Captain-label channel), §8 D1. Germline contract for the shipped bytes:
the evidence-HP germline amendment (an internal proposal record, 2026-07-17).

THREAT HONESTY (repeat it at the ceremony, not just here): HP-1 raises the
evidence-forgery bar from same-OS-user to **root** — root can still forge
events, anchors, watermarks, the broker's request log, and the key itself.
That residual is accepted and stated. Before the ceremony, HP-2's
"independent" legs re-derive raw artifacts under the SAME OS user
(corroboration, not a trust boundary) and HP-3 labels are tamper-EVIDENT,
not tamper-proof. The ceremony is what turns these from protocols into a
boundary.

---

## 0. Hard blockers — do not start the ceremony without them

1. **Verifier broker seam (BLOCKS Part A entirely).** The recorder signs
   through the broker, but `framework/evidence/verifier.py` still reads
   `<store>/.signing-key` directly and runs in-path on every append and in
   the officer read doorway. Until officer-context verification routes
   through the broker's boolean verify verbs (a germline ceremony of its
   own, queued in `docs/runbooks/evidence-signing-broker.md`
   "Hard preconditions"), the key must remain at the store root and HP-1's
   isolation is **not achieved**. Running Part A before that seam lands
   buys a daemon and no boundary.
2. **Captain capability token minted BEFORE the key moves** — post-
   ceremony the officer-context recorder holds no key handle:

       python3.12 -m framework.evidence grant-token --store instance/evidence/v1

3. **Germline-set widening prepared** (executed in Part A step 5): the
   real `instance/config/evidence-signing.yml`, the broker module, and the
   LaunchDaemon plist join the lock set via the
   `framework/policies/immutable-core.yml` `pending:` mechanism — wire all
   four lists (`germline-lock.sh FILES[]`, `pre-tool-use.sh` §5 + §5b,
   `base-safety.yml`) and delete the pending flag in the same commit so
   `test_germline_lockstep_consistency.py` flips xfail→hard.

Substitute throughout: `$OFFICER` = the account officers run as, `$REPO` =
the cabinet checkout, `$STORE` = `$REPO/instance/evidence/v1`.

---

## Part A — HP-1: OS-user split, key custody, broker daemon (Captain sudo)

Source of truth: `docs/runbooks/evidence-signing-broker.md` §"Deploy
ceremony". Summary sequence with the load-bearing commands:

**A1. Create the broker service account + shared group** *(sudo)*:

    sudo sysadminctl -addUser cabinet-evidence-signer \
      -fullName "Cabinet Evidence Signer" -home /var/empty \
      -shell /usr/bin/false -password -
    sudo dseditgroup -o create cabinet-evidence
    sudo dseditgroup -o edit -a "$OFFICER" -t user cabinet-evidence
    sudo dseditgroup -o edit -a cabinet-evidence-signer -t user cabinet-evidence

**A2. Relocate the HMAC key to a broker-only path** *(sudo; keep the
store-root copy until the verifier seam of blocker 1 is live, then remove
it so local loaders cannot mint a split-brain key)*:

    sudo mkdir -p /var/db/cabinet-evidence-signer
    sudo cp "$STORE/.signing-key" /var/db/cabinet-evidence-signer/signing-key
    sudo chown -R cabinet-evidence-signer:cabinet-evidence /var/db/cabinet-evidence-signer
    sudo chmod 0700 /var/db/cabinet-evidence-signer
    sudo chmod 0400 /var/db/cabinet-evidence-signer/signing-key

**A3. Write the broker daemon config** *(sudo; `identities:` maps kernel
peer uids — `id -u "$OFFICER"` — to attested names, fixed at daemon
start)*:

    sudo mkdir -p /etc/cabinet
    sudo tee /etc/cabinet/evidence-signing-broker.yml >/dev/null <<'EOF'
    socket: /var/run/cabinet/evidence-signing.sock
    key: /var/db/cabinet-evidence-signer/signing-key
    log: /var/db/cabinet-evidence-signer/requests.jsonl
    identities:
      501: officer-core
    EOF
    sudo chown root:wheel /etc/cabinet/evidence-signing-broker.yml
    sudo chmod 0644 /etc/cabinet/evidence-signing-broker.yml

**A4. Write the recorder-side signing config** *(sudo, root-owned; the
dark default until this exact moment is the ABSENCE of this file — see
`instance/config/evidence-signing.yml.example`)*:

    sudo tee "$REPO/instance/config/evidence-signing.yml" >/dev/null <<'EOF'
    mode: broker
    socket: /var/run/cabinet/evidence-signing.sock
    identity: officer-core
    EOF
    sudo chown root:wheel "$REPO/instance/config/evidence-signing.yml"

**A5. Germline-set widening** per blocker 3 (`pending:` → wire all four
lists → delete pending, one commit), then `sudo bash
cabinet/scripts/germline-lock.sh lock` the SAME day.

**A6. Install + start the LaunchDaemon** *(sudo; deliberately NOT
`generate-plists` — the generator renders same-user LaunchAgents, and a
same-user broker is zero isolation)*:

    sudo tee /Library/LaunchDaemons/com.cabinet.evidence-signing-broker.plist >/dev/null <<'EOF'
    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
      "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0"><dict>
      <key>Label</key><string>com.cabinet.evidence-signing-broker</string>
      <key>UserName</key><string>cabinet-evidence-signer</string>
      <key>GroupName</key><string>cabinet-evidence</string>
      <key>WorkingDirectory</key><string>/Users/OFFICER/captains-cabinet</string>
      <key>ProgramArguments</key><array>
        <string>/usr/local/bin/python3.12</string>
        <string>-m</string><string>framework.evidence_signing_broker</string>
        <string>serve</string>
        <string>--config</string>
        <string>/etc/cabinet/evidence-signing-broker.yml</string>
      </array>
      <key>RunAtLoad</key><true/>
      <key>KeepAlive</key><true/>
    </dict></plist>
    EOF
    sudo launchctl load -w /Library/LaunchDaemons/com.cabinet.evidence-signing-broker.plist

**A7. Socket permissions for cross-user access** *(sudo; the staged 0700/
0600 posture is same-user-simulation only — post-ceremony the group is the
transport gate and the in-process peer-uid allowlist is the REAL boundary;
never `chmod 0777` a refusal, widen the group)*:

    sudo mkdir -p /var/run/cabinet
    sudo chown cabinet-evidence-signer:cabinet-evidence /var/run/cabinet
    sudo chmod 0750 /var/run/cabinet
    # after first daemon start:
    sudo chgrp cabinet-evidence /var/run/cabinet/evidence-signing.sock
    sudo chmod 0660 /var/run/cabinet/evidence-signing.sock

**A8. Red-team proof (record the transcript in the ceremony notes):**

    sudo -u "$OFFICER" cat /var/db/cabinet-evidence-signer/signing-key
    # → MUST fail at the OS (Permission denied) — HP-1's red-team bar:
    #   the key read fails at the OS, not at a hook.

Then from officer context: one recorder append + one
`python3.12 -m framework.evidence verify` — both must succeed through the
broker.

**A9. Relock + fresh verify** *(sudo for the lock)*:

    sudo bash cabinet/scripts/germline-lock.sh lock
    bash cabinet/scripts/germline-lock.sh verify
    bash cabinet/scripts/germline-lock.sh status

---

## Part B — HP-3: Captain-label channel configuration

The TTY label channel (`captain-token+tty`) needs ZERO config — the
governance-review CLI attests it from the two gates it already enforces
(Captain token + live TTY). Nothing to enable.

**B1. Telegram chat-id allowlist** *(only when/if a Captain-DM label
writer ever lands — the `telegram-captain-dm` channel is RESERVED today
and refuses unconfigured, fail-closed)*: set the config-of-record key in
`instance/config/platform.yml`:

    # instance/config/platform.yml
    captain_telegram_chat_id: "<the Captain's numeric chat id>"

The chat id itself never enters evidence events, journal rows, or error
text (`attest_telegram_channel()` in
`cabinet/scripts/governance-review.py` is the only consumer).

**B2. Legacy-label honesty check** (first governance session after any
upgrade): run one calibration pass and confirm the report's excluded-label
count line names every pre-HP-3 label as `legacy pre-HP-3` — excluded
from pairing, counted, never silently dropped:

    python3.12 -m framework.evidence_calibration

---

## Part C — service enables (Captain ceremony; the ONLY enable path)

**C1. `evidence-signing-broker`** — enabled BY Part A (LaunchDaemon by
hand). Do NOT remove its `disabled: true` flag in `cabinet/services.yml`
for the generator: the row stays a documented tombstone pointing at this
ceremony (see the row's `disabled_reason`).

**C2. `evidence-recompute`** (source of truth:
`docs/runbooks/evidence-recompute.md` §"Deploy ceremony"):

1. Remove `disabled: true` from the `evidence-recompute` row in
   `cabinet/services.yml`; run the plist generator; load the LaunchAgent:

       python3.12 cabinet/scripts/generate-plists.py
       launchctl load ~/Library/LaunchAgents/com.cabinet.evidence-recompute.plist

2. Uncomment `evidence-recompute-liveness` in
   `instance/config/watchdog.yml` and land its catalog row in
   `framework/watchdog/registry.py` in the same step.
3. **Classification-registry promotion** (germline ceremony, separately
   queued in `docs/runbooks/evidence-recompute.md`): promote the recompute
   detail keys to `independently_established` in
   `framework/evidence/classification.py` ONLY via that registry's
   documented ceremony pattern. Until then its events read back
   producer-asserted (fail-closed) and the fuel-integrity third leg stays
   report-only — which is correct and honest.

---

## Part D — exit checks (same day)

    bash cabinet/scripts/germline-lock.sh verify
    python3.12 -m pytest framework/evidence framework/tests/test_signing_broker.py \
      framework/tests/test_evidence_recompute.py framework/tests/test_fuel_integrity.py \
      framework/tests/test_evidence_calibration.py \
      framework/tests/test_germline_lockstep_consistency.py -q
    python3.12 cabinet/scripts/evidence-anchor.py --json
    python3.12 cabinet/scripts/evidence-anchor.py --recount-labels

Any red here is stop-and-page, not a workaround. Rollback per runbook:
`sudo launchctl unload -w` the daemon, remove
`instance/config/evidence-signing.yml` (local mode resumes byte-identical),
re-add `disabled: true` to re-darken `evidence-recompute`, relock.
