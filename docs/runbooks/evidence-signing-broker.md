# Evidence signing broker — HP-1 key custody (staged dark; deploy ceremony)

Status: **STAGED DARK.** Everything in this runbook describes machinery that
ships disabled and unconfigured. Unconfigured = byte-identical pre-seam
recorder behavior (the golden seam test pins it). The ceremony below is a
FRESH-CABINET LAUNCH step executed by the Captain with sudo — it is
never executed by a build workflow, never by an officer, and never by any
script in this repo.

## Why this exists

The Phase-4 fuel-integrity check ships with a NAMED gap: a same-OS-user
attacker who forges BOTH the consequence ledger AND the evidence store
consistently passes every check. The store's HMAC key lives at
`<store>/.signing-key`, readable by the same user that runs officers, so
"signed" means "signed by anyone on this account". HP-1 moves the key into
a separate OS user behind a Unix-socket broker
(`framework/evidence_signing_broker.py`) so officer-context processes can
record and verify evidence without ever being able to read the key.

**THREAT HONESTY (accepted residuals, stated wherever relevant):**

* HP-1 raises the forgery bar from **same-OS-user to root**. Root can still
  forge events, anchors, watermarks, the broker's request log, and the key
  itself. That residual is accepted and stated, not hidden. External
  anchoring (`evidence-anchor`, design D3 both-surfaces) is the cross-check
  that survives it for after-the-fact detection.
* A compromise of the broker user is a key compromise.
* Integrity ≠ veracity (R1): any identity with sign-event access can still
  author lies under its own name. What HP-1 buys is: no key exfiltration
  (residual = root), no officer-context control/purge signature minting,
  cross-identity forgery bounded by the kernel-attested uid→identity map,
  and a broker-side request log that makes bulk re-signing (history
  rewrite) visible.
* Pre-ceremony, `instance/config/evidence-signing.yml` does not exist and
  cannot be immutability-locked (locks skip absent paths). A same-user
  writer creating a bogus one buys evidence-plane DENIAL (loud,
  fail-closed) or a redirect to an attacker socket — nothing beyond the
  same-user forgery power that already exists without HP-1.

## Architecture (staged shape)

* `framework/evidence/signing.py` (germline, inside the locked
  `framework/evidence/` dir — zero lock-list edits by construction):
  resolves `<store>/../../config/evidence-signing.yml`. Absent or
  non-broker config → `LocalKeySigner` (byte-identical). `mode: broker` →
  `BrokerSigner`, typed fail-closed errors
  (`signing_broker_unavailable` / `signing_broker_refused`), NEVER a
  silent local fallback.
* `framework/evidence_signing_broker.py` (non-germline while staged — the
  `evidence_anchor.py` precedent): the daemon. Peer-credential
  authentication (`SO_PEERCRED` Linux / `LOCAL_PEERCRED` macOS,
  feature-detected; neither → refuse to serve), uid→identity allowlist
  fixed at start, per-uid rate limit, newline-framed single-JSON-object
  protocol, request cap.
* Verbs: `sign-event {trial_id, sequence, event_hash}` (broker builds the
  frozen `event\n…` preimage itself — arbitrary bytes are never MAC'd);
  `sign-object` for the `anchor` purpose only, exact payload schema;
  `verify-event` / `verify-object` → boolean only, never the MAC.
  `control`/`purge`/`watermark` MINTING is refused in v1 — a strict
  tightening: store birth, `configure()`, and purges become
  broker-user/ceremony operations (see "Captain operations" below).
* Divergence rule: re-requesting the SAME `(trial_id, sequence)` with a
  DIFFERENT hash is refused loudly (history-rewrite shape); identical
  triples stay idempotent because crash recovery legitimately re-verifies
  the same triple.
* Request log: one JSONL row per request (ts, uid, identity, verb, ids,
  outcome) appended to a broker-owned file. Fail-closed: a request that
  cannot be logged is not served. Key bytes and the key path never appear
  in any response, log row, or error.

## Hard preconditions for the ceremony (do not proceed without them)

1. **The verifier seam.** The recorder's signing seam is live, but the
   independent verifier (`framework/evidence/verifier.py`) still reads
   `<store>/.signing-key` directly — and `verify_trial` runs in-path on
   every append and in the officer read doorway. Until officer-context
   verification routes through the broker's boolean verify verbs, the key
   must REMAIN at the store root, which means HP-1's isolation is NOT yet
   achieved. **The ceremony below is BLOCKED on the verifier seam
   landing** (a germline ceremony of its own). When it lands, officer-
   context verification must pass `advance=False` for watermarks — an
   officer-facing watermark-sign verb would allow minting a LOWERED
   watermark (rollback laundering); a broker-user scheduled verify owns
   advances.
2. **Captain capability token.** The token is `HMAC(signing-key,
   purpose)`. Mint it (`python3.12 -m framework.evidence grant-token …`)
   BEFORE relocating the key: post-ceremony the officer-context recorder
   has no key handle (`recorder._key` is `None` in broker mode) and token
   minting moves behind the broker user.
3. **Germline set widening prepared.** The real
   `instance/config/evidence-signing.yml`, the broker script, and the
   LaunchDaemons plist join the lock set via the
   `framework/policies/immutable-core.yml` `pending:` mechanism —
   enumerate the paths, wire all four lists (`germline-lock.sh FILES[]`,
   `pre-tool-use.sh` §5 + §5b `GERM_PATH_RE`, `base-safety.yml`), delete
   the pending flag in the same commit so
   `test_germline_lockstep_consistency.py` flips xfail→hard.

## Deploy ceremony (Captain sudo; fresh-cabinet launch)

Substitute `$OFFICER` (the account officers run as), `$REPO` (the cabinet
checkout), `$STORE` (`$REPO/instance/evidence/v1`).

1. **Create the broker service account + shared group:**

       sudo sysadminctl -addUser cabinet-evidence-signer \
         -fullName "Cabinet Evidence Signer" -home /var/empty \
         -shell /usr/bin/false -password -
       sudo dseditgroup -o create cabinet-evidence
       sudo dseditgroup -o edit -a "$OFFICER" -t user cabinet-evidence
       sudo dseditgroup -o edit -a cabinet-evidence-signer -t user cabinet-evidence

2. **Relocate the HMAC key to a broker-only path** (do NOT remove the
   store-root copy until the verifier seam has landed — precondition 1;
   with the verifier seam live, remove `<store>/.signing-key` so local
   loaders cannot recreate a split-brain key):

       sudo mkdir -p /var/db/cabinet-evidence-signer
       sudo cp "$STORE/.signing-key" /var/db/cabinet-evidence-signer/signing-key
       sudo chown -R cabinet-evidence-signer:cabinet-evidence /var/db/cabinet-evidence-signer
       sudo chmod 0700 /var/db/cabinet-evidence-signer
       sudo chmod 0400 /var/db/cabinet-evidence-signer/signing-key

3. **Write the broker's own config** (broker-user-owned; format below):

       sudo tee /etc/cabinet/evidence-signing-broker.yml >/dev/null <<'EOF'
       socket: /var/run/cabinet/evidence-signing.sock
       key: /var/db/cabinet-evidence-signer/signing-key
       log: /var/db/cabinet-evidence-signer/requests.jsonl
       identities:
         501: officer-core
       EOF
       sudo chown root:wheel /etc/cabinet/evidence-signing-broker.yml
       sudo chmod 0644 /etc/cabinet/evidence-signing-broker.yml

   `identities:` maps kernel peer uids to attested identity names and is
   fixed at daemon start — never influenced by a request. Use the real
   officer uid (`id -u "$OFFICER"`).

4. **Write the real recorder-side config** (root-owned; see
   `instance/config/evidence-signing.yml.example`):

       sudo tee "$REPO/instance/config/evidence-signing.yml" >/dev/null <<'EOF'
       mode: broker
       socket: /var/run/cabinet/evidence-signing.sock
       identity: officer-core
       EOF
       sudo chown root:wheel "$REPO/instance/config/evidence-signing.yml"

5. **Germline set widening** per precondition 3 (pending: → wire all four
   lists → delete pending same commit), then relock the germline the SAME
   day (`sudo bash cabinet/scripts/germline-lock.sh lock`).

6. **Install the LaunchDaemon** (NOT generate-plists — the generator
   renders same-user LaunchAgents; a cross-user daemon needs
   `/Library/LaunchDaemons` + `UserName` by hand):

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

7. **Loosen socket perms for cross-user access.** The STAGED daemon binds
   0700 dir / 0600 socket (captain-law-broker parity — correct for
   same-user simulation, and a cross-user officer cannot connect to it).
   Post-ceremony the socket dir must be 0750 `cabinet-evidence`-group and
   the socket 0660 group-shared; the in-process peer-credential allowlist
   is the REAL boundary. Do NOT "fix" a post-ceremony connection refusal
   with `chmod 0777` — widen the group instead:

       sudo mkdir -p /var/run/cabinet
       sudo chown cabinet-evidence-signer:cabinet-evidence /var/run/cabinet
       sudo chmod 0750 /var/run/cabinet
       # after first daemon start:
       sudo chgrp cabinet-evidence /var/run/cabinet/evidence-signing.sock
       sudo chmod 0660 /var/run/cabinet/evidence-signing.sock

8. **Red-team proof (record the transcript):**

       sudo -u "$OFFICER" cat /var/db/cabinet-evidence-signer/signing-key
       # → MUST fail at the OS (Permission denied)
       sudo -u "$OFFICER" python3.12 - <<'EOF'
       # officer-context append + read still work via broker verbs
       EOF

9. **Relock the germline the same day.** Verify fresh:
   `bash cabinet/scripts/germline-lock.sh status` and `ls -lO` on every
   touched path.

## Captain operations post-ceremony

`configure()` and `purge_trial()` need `control`/`purge` signatures, which
the v1 broker refuses to mint. They become broker-user operations: the
Captain runs them via `sudo -u cabinet-evidence-signer` with a local-mode
override store view, or a later ceremony adds Captain-token-gated minting
verbs to the broker. This is a deliberate strict tightening — officer
context losing control/purge minting is the point — and the cost (Captain
friction for purge/config) is accepted and stated.

## Broker config file format

Top-level scalars `socket:` / `key:` / `log:` plus an `identities:` block
of `uid: identity-name` lines. Anything else does not bind. The identity
map is fixed at start; SIGHUP is not honored (restart to change it).

## Rollback

Delete `instance/config/evidence-signing.yml` (recorder returns to local
mode over the store-root key — byte-identical pre-seam behavior),
`sudo launchctl unload -w …` the daemon, and keep
`/var/db/cabinet-evidence-signer` until a decision is recorded. Rollback
REOPENS the same-user forgery residual; say so in the decision entry.
