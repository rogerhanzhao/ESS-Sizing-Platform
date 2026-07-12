# Cutover Runbook — 2026-07-12 version (b992818 / 943383c)

Goal: switch the shared Ubuntu server from the currently deployed version to
the SLD Proposal Package V1 milestone with near-zero user impact.

Target branch: `ops/ubuntu-docker-coexist-20260311`
Target commits: `b992818` (feature milestone) + `943383c` (status/navigation docs)

## Why this switch is low-risk

1. **No schema change.** This version adds no Alembic migration; head remains
   `20260617_0007_add_sld_project_settings`. If the server already runs the
   `d8b3396` era, the switch is code-only and rollback is schema-identical.
2. **Startup migration is automatic and fail-fast.** `app.py` runs
   `alembic upgrade head` on boot and refuses to start on failure
   (`CALB_ALLOW_CREATE_ALL_FALLBACK=false` in compose). An older server DB is
   migrated forward automatically on first boot of the new container.
3. **All user data is DB/disk-persisted (DB-first refactor).** Runs, AC
   snapshots, artifacts and engineering settings survive the container swap.
   Users only lose transient page state and simply re-open their run.
4. **Old artifacts stay readable.** Artifact kinds are unchanged for existing
   data; new proposal-package kinds are additive. Renamed output file names
   apply only to newly generated documents. The nav rename ships a legacy
   alias for restored sessions.
5. **The swap window is seconds, not minutes.** `compose up -d --build`
   builds the new image while the old container keeps serving; the recreate
   at the end is the only downtime (~5–15 s websocket reconnect).

## Step 0 — Record current state (on the server)

```bash
cd /opt/calb-sizingtool/app
git rev-parse --short HEAD              # note the rollback commit
bash deploy/docker/calb-serverctl.sh status
```

Keep the printed commit hash; it is the rollback target.

## Step 1 — Backup runtime state (mandatory, cheap)

```bash
STAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p /opt/calb-sizingtool/backups
cp -a /opt/calb-sizingtool/runtime/state "/opt/calb-sizingtool/backups/state_${STAMP}"
# outputs are regenerable but tiny; include them for a complete restore point:
tar -C /opt/calb-sizingtool/runtime -czf "/opt/calb-sizingtool/backups/outputs_${STAMP}.tgz" outputs
```

The SQLite file is ~2 MB; the whole backup takes seconds. Prefer an off-peak
moment so no write is in flight.

## Step 2 — Update (single command)

```bash
cd /opt/calb-sizingtool/app
bash deploy/docker/calb-serverctl.sh update ops/ubuntu-docker-coexist-20260311
```

The command refuses a dirty worktree, pulls `--ff-only`, rebuilds the image
(old container still serving), then recreates the container.

## Step 3 — Verify (5 minutes)

```bash
bash deploy/docker/calb-serverctl.sh status
curl -I http://127.0.0.1:18511
bash deploy/docker/calb-serverctl.sh logs   # confirm no migration error, Ctrl-C to exit
```

Then in a browser:

1. Log in; open an **existing historical run** in Run Registry.
2. Report Export on that old run — SLD/layout images and docx still resolve.
3. Generate a new SLD — expect the concept/official status line, the
   NOT-FOR-CONSTRUCTION watermark on non-official output, and the
   SLD-01/03/04 Proposal Package expanders.
4. Open **Typical AC Block Arrangement** (renamed from Site Layout) — the
   P2 readiness gate and template download appear.
5. Export a combined report — section heading reads
   "Typical AC Block Arrangement (Concept Only)".

## Step 4 — User communication (what "seamless" means here)

- Active browser sessions reconnect automatically after the ~10 s swap; any
  page state is reset. Persisted runs are untouched — users re-select their
  run and continue.
- The nav item "Site Layout" is now "Typical AC Block Arrangement"; restored
  sessions are aliased automatically.
- Newly generated non-official documents now carry concept/draft watermarks
  by design; this is the headline behavioural change to announce.

## Rollback (if verification fails)

```bash
cd /opt/calb-sizingtool/app
git checkout <commit-from-step-0>
bash deploy/docker/calb-serverctl.sh restart
```

No schema rollback is needed: this version added no migration. Even if the
server was older than `20260617_0007` before cutover, that migration is
additive (`sld_project_settings` table) and is ignored by older code. The
Step 1 backup is the belt-and-braces restore point:

```bash
bash deploy/docker/calb-serverctl.sh stop
cp -a /opt/calb-sizingtool/backups/state_<STAMP>/. /opt/calb-sizingtool/runtime/state/
bash deploy/docker/calb-serverctl.sh start
```
