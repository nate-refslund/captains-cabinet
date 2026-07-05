# Docker deployment target (`org-docker` preset)

The `docker` value of the `deployment_target` axis (axes spec 2026-07-05 §3;
AX-4). Same authority semantics as every other target — targets select
**backends** (attestation, scheduler, adapters), never authority rules. The
extinct `/opt/founders-cabinet` deployment is the ancestor; this revives it
as a first-class target.

| Concern | macbook / mac_mini | docker (this preset) |
|---|---|---|
| Attestation backend | `schg` (`chflags schg`, root-only clear) | `ro_mount` (host-side read-only bind mounts) |
| Scheduler | launchd (`generate-plists.py`) | container init + cron (`generate-services-cron.py`) |
| Lock/unlock ritual | `sudo germline-lock.sh unlock/lock` | edit on the **host**, `docker compose restart cabinet` |

## Quick start

```bash
cd cabinet/deploy/docker

# 1. every bind-mount source must EXIST first (docker otherwise creates a
#    DIRECTORY in its place — engine behavior, silent and wrong):
touch ../../../cabinet/.env
cp ../../../instance/config/posture.yml.example        ../../../instance/config/posture.yml         # or leave it empty ⇒ guardian
cp ../../../instance/config/standing-grants.yml.example ../../../instance/config/standing-grants.yml

# 2. build + run (cabinet + redis sidecar)
docker compose up -d --build

# 3. watch the schedule land
docker compose exec cabinet crontab -l
docker compose logs -f cabinet
```

## The attestation model (`ro_mount`)

`framework/authority/posture.py` dispatches `is_locked()` on the ruling's
`deployment_target`. In a container there is no `schg`; the Captain's
signature is the **host's `:ro` bind mount** over `instance/config/posture.yml`
(and `standing-grants.yml`). The backend attests a file only when **all
three** hold, and ANY ambiguity resolves guardian:

1. the path is symlink-free (lstat + realpath containment — a link is never
   attestable);
2. an `O_NOFOLLOW` open-append probe on the real path is refused with
   `EROFS`/`EACCES` (an open that succeeds proves writability);
3. `/proc/mounts` is present and shows the containing mount `ro` — a
   permissions-only refusal (chmod 444, same uid) never attests.

Consequences worth knowing:

- **Guardian is the default here exactly as everywhere**: absent, corrupt,
  writable, or unverifiable posture.yml ⇒ guardian.
- A ruling declaring `deployment_target: docker` never attests on a Mac (no
  ro `/proc/mounts` entry) and a `macbook` ruling never attests in a
  container (no schg) — attestation is deployment-matched, fail-closed.
- The container **cannot** forge an unlock: remounting `ro→rw` needs
  `CAP_SYS_ADMIN` (dropped — `cap_drop: [ALL]`), and `no-new-privileges`
  forbids re-acquiring it. Container root changes nothing.
- `CABINET_POSTURE` env (compose `environment:`) stays **narrow-only**:
  `guardian`/`earn_up` cap the resolved posture; `sovereign` is ignored.

## Host-side lock/unlock ritual

The upgrade ritual (`unlock → edit posture.yml → lock`) happens **on the
host**, where the files are plain files:

```bash
# on the HOST
$EDITOR instance/config/posture.yml        # e.g. posture: sovereign, deployment_target: docker
docker compose restart cabinet             # remount picks up the edit, still :ro
```

If the host is itself a Mac that arms schg over these files, unlock there
first (`sudo bash cabinet/scripts/germline-lock.sh unlock <path>` … edit …
`lock`). Inside the container, `germline-lock.sh` is a deliberate no-op:

```bash
bash cabinet/scripts/germline-lock.sh --backend ro-mount status   # prints this ritual
```

## Scheduling — one manifest, two renderers

`cabinet/services.yml` stays the single fleet truth. This target renders it
with `cabinet/scripts/generate-services-cron.py` (the image CMD does it at
boot, installs the crontab, then `exec cron -f`):

- a row is container-scheduled **only when it opts in** with
  `platform: linux` or `platform: any` (default `darwin` = launchd-only, so
  a fresh clone renders a header-only crontab — nothing thrashes);
- `interval_s` must be whole cron minutes/hours; `calendar` entries map
  1:1 to 5-field lines (launchd weekday `7` → cron `0`);
- `schedule: keepalive` rows are cron-inexpressible and are emitted as
  comments — the container init owns them (extend the image CMD or add a
  supervisor when the first keepalive row opts in);
- unknown `kind`/`platform` values hard-error the render — the
  no-silent-skip lesson from `generate-plists.py` (lane-ops 2026-07-04).

Preview from any checkout: `python3 cabinet/scripts/generate-services-cron.py`
(stdout; `--root/--redis-host/--log-dir/--output` to shape it).

## Clean-room CI gate (axes spec §6.2)

The framework suite must pass on this bare image — no personal sources, no
screenpipe, no vault:

```bash
docker build -f cabinet/deploy/docker/Dockerfile -t captains-cabinet:docker ../../..
docker run --rm captains-cabinet:docker python3 -m pytest framework/ -q
```

## Footguns

- **Missing bind source ⇒ docker creates a directory** at the host path.
  `touch`/`cp` the three single-file sources before first `up` (see Quick
  start). An empty `posture.yml` is safe: unparseable-as-mapping ⇒ guardian.
- **Build context is the repo root** (compose sets it). A large working
  checkout makes slow builds — consider a repo-root `.dockerignore`
  excluding runtime state before building from a live deployment.
- **Secrets** live in host `cabinet/.env`, mounted `:ro`, sourced at run
  time by every cron line — never bake them into the image.
- Runtime-written state (`shared/`, `instance/memory/`, logs, redis) lives
  in named volumes and survives restarts; `docker compose down -v` erases it.
