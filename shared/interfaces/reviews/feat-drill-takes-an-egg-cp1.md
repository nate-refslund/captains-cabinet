# feat/drill-takes-an-egg — checkpoint 1

Reviewed-Scope-Digest: 301a7357b568623fe2df3bff901359466acf7e66e0f27681d9c0a08f083aea76

## What the change is

The phase-1 acceptance drill could not be pointed at an installed Cabinet.
It hatched by staging its source tree and then applying
`cabinet/scripts/egg-export-manifest.txt` to tell this deployment's state from
the framework's. An install **is** an export, and the packaging pass deletes
that manifest out of it by design — so on the Captain's own box, 2026-09-10,
`--tree /path/to/install` exited **64 at hatch**:

    no export manifest at cabinet/scripts/egg-export-manifest.txt — the drill
    cannot tell this deployment's state from the framework's

The gate "the drill passes on the installed Cabinet" had therefore only ever
been taken against the identical git tree in a clone, and in CI. That is a
sensor pointed at something other than the control (evidence class 11), and it
is the class this programme keeps paying for.

The drill now reads which of three subject shapes it was handed, off the tree
rather than off a flag:

| Subject | Recognised by | Staged how |
|---|---|---|
| a git checkout | `cabinet/scripts/egg-export-manifest.txt` present | unchanged: `git archive HEAD` / `--tree` copy, then the manifest scrub |
| an egg or an install | `egg-manifest.json` present AND no export manifest | copied minus the operator's own data, which the egg declares |
| neither | both absent | unchanged: exit 64 at hatch with the sentence above |

The gitless `REPO_ROOT` branch takes the same shape test, so an installed
Cabinet running its **own** copy of the drill with no arguments lands on the
egg path too.

## The three judgment calls, and why

**1. What "the operator's data" is, on a tree with no manifest.** Derived, never
hand-listed. `update_bundle.preserve_set()` is the parser the updater itself
calls: the generated `cabinet/config/egg-preserve-set.txt` unioned with
`runtime-provision.sh lists` and the header-only interface ledgers. It RAISES
when neither side declares anything, which is the fail-closed property this
hatch needs — "no declaration" must never read as "this deployment has nothing
of its own". A second copy of that rule inside the drill would be a second
thing to keep in step, and the copy is always the one that goes stale.

The keep-list points the other way and is equally load-bearing:
`cabinet/scripts/shipped-ignored-paths.txt` names force-tracked content the
export SHIPS, and some of it sits under a preserved directory
(`memory/tier3/*/.gitkeep`). Dropping the directory whole would delete shipped
structure and call it operator data — the same defect pointed backwards. Both
directions are proved by mutation below.

Then the artefacts an install grows by running and no export ships: `.updates/`,
`node_modules`, build output, bytecode. The update ledger is the one that
matters most; a scratch that inherited `.updates/` would replay another run's
history and every P7 delta would be taken around somebody else's rows.

**2. P7 on an egg subject — REAL or THIN, never silent.** A bundle is a cut of a
checkout and an egg ships no exporter (`cabinet/scripts/egg-export.sh` is absent
from a fresh cut — asserted, not assumed). So the update leg takes its bundle
source from `CABINET_DRILL_BUNDLE_SOURCE`, or records **THIN** and names what
would make it REAL. What an egg subject genuinely adds when it does run: the
publish and apply legs execute the **egg's own** `cabinet-update.sh`, the egg's
dashboard library and the egg's `node_modules`, while only the bundle comes
from the checkout. The scratch install is exported from the bundle source, and
the stage line says so.

*Rejected alternative:* making the pruned egg copy itself the install. It would
prove more, and it would red for reasons unrelated to the change under test —
the operator's preserved paths are gone from the copy, so a bundle cut from any
checkout differs from it at paths the locked/preserve guards refuse on (exit 3,
the failure the existing P7 comment already documents).

**3. Hermeticity now watches the subject.** An egg subject is the one shape where
`--tree` points at a tree a person is running, so "the drill cannot damage your
install" is a claim worth a sensor. Honest limit, stated in the file: it
compares the file LIST, so it catches a creation or a deletion and not an
in-place overwrite. The drill never opens the subject for writing — it is
tar-copied once and hardlinked from — and that is the residual the line does
not close.

## Evidence

Base `84e03225`, measured this session.

| Sensor | Base | After |
|---|---|---|
| drill `--tree <egg cut by egg-export.sh from HEAD>` | **64** at hatch, "no export manifest …" | **0**, `verdict: pass`, `tree_source: egg:<path> @ 84e03225` |
| planted operator data under preserve-set paths | (unreachable — 64) | **0 occurrences** in the scratch root; 7 of 7 shipped-ignored paths survived |
| a git tree as `--tree` | `tree:` + "scrubbed 26 …" | unchanged: `tree:` + "scrubbed 26 …" |
| P7 with `CABINET_DRILL_BUNDLE_SOURCE` | (unreachable — 64) | `p7_rebuild: REAL`, both apply legs green, 6 m 37 s |
| P7 without it | (unreachable — 64) | `P7 thin`, note names `CABINET_DRILL_BUNDLE_SOURCE` and the commit to point it at |
| a tree with NEITHER manifest | 64, "no export manifest …" | unchanged: 64, same sentence |

The prune sensor was mutated in both directions and fires both ways:
dropping `instance/` from the preserve set leaks
`instance/tools/operator-only.txt` and `instance/config/outcomes.yml` into the
scratch; ignoring the keep-list deletes the three `memory/tier3` `.gitkeep`
files. Neither mutation is silent.

## What this does NOT prove

* The egg leg's bundle is cut from a checkout, not from the egg, so P7 still
  does not prove that *this* egg's bytes can be updated from *this* egg. What
  it does prove is that the egg's own updater, library and dependency tree
  carry a real bundle through a red gate, a green gate and a locked-path
  refusal.
* The subject watch is a file-list comparison, not a content hash.
* Both legs were measured on one box (macOS, arm64) plus CI.

## One defect this checkpoint found in itself

The first cut of the operator-data arm used a literal marker string. Committed,
the egg cut from `HEAD` then SHIPPED the test file carrying that literal, and
the leak scan found its own source in the scratch root and called it operator
data. It passed in the working tree and failed on the committed one — the same
class of defect the arm exists to catch, arriving by the same route (evidence
class 2). The marker is now generated per run and can never be in the tree.
