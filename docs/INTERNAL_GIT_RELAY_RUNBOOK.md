# Internal Git Relay Runbook

## Purpose

Use this relay when the deployment server cannot reach GitHub over outbound HTTPS.
The relay carries Git objects and refs over SSH. It is not a file copy, archive
upload, or manual replacement of application files.

## Fixed topology

- GitHub repository: `https://github.com/rogerhanzhao/ESS-Sizing-Platform.git`
- Deployment branch: `ops/ubuntu-docker-coexist-20260311`
- SSH host alias: `calb-server`
- Server application repository: `/opt/calb-sizingtool/app`
- Server bare relay repository: `/opt/calb-sizingtool/relay.git`
- Server application URL: `http://127.0.0.1:18511/`

The application repository remains the deployment working tree. The relay is a
bare Git repository used only as an internal fetch source.

## Standard update procedure

Run this procedure after the local branch has been tested and pushed to GitHub.
Replace `<sha>` only with the exact commit intended for the deployment branch.

1. Confirm the local branch and GitHub branch point to the same `<sha>`.
2. Push Git objects and the branch ref to the relay:

   ```powershell
   git -c core.sshCommand='ssh -o BatchMode=yes -o ConnectTimeout=10' push `
     ssh://calb-server/opt/calb-sizingtool/relay.git `
     HEAD:refs/heads/ops/ubuntu-docker-coexist-20260311
   ```

3. On the server, fetch from the relay into a reviewable remote-tracking ref:

   ```bash
   sudo git -c safe.directory=/opt/calb-sizingtool/app \
     -C /opt/calb-sizingtool/app fetch \
     /opt/calb-sizingtool/relay.git \
     refs/heads/ops/ubuntu-docker-coexist-20260311:\
     refs/remotes/relay/ops/ubuntu-docker-coexist-20260311
   ```

4. Fast-forward the checked-out application branch only:

   ```bash
   sudo git -c safe.directory=/opt/calb-sizingtool/app \
     -C /opt/calb-sizingtool/app merge --ff-only \
     refs/remotes/relay/ops/ubuntu-docker-coexist-20260311
   ```

5. Rebuild and restart with the existing deployment entrypoint:

   ```bash
   cd /opt/calb-sizingtool/app
   sudo bash deploy/docker/calb-serverctl.sh restart
   ```

6. Record and verify all three refs, the clean worktree, and HTTP health:

   ```bash
   sudo git -c safe.directory=/opt/calb-sizingtool/app \
     -C /opt/calb-sizingtool/app rev-parse HEAD
   git -C /opt/calb-sizingtool/relay.git rev-parse \
     refs/heads/ops/ubuntu-docker-coexist-20260311
   curl -fsSI --max-time 10 http://127.0.0.1:18511/
   ```

The GitHub commit SHA, relay SHA, application SHA, deployment time, deploy
result, and health result are the minimum maintenance record for each update.

## Initial bootstrap and recovery

The first full push to an empty relay can transfer the complete repository
history and may be slow over an SSH connection. If the server application
already contains the required history, seed the relay with a Git-native fetch
from the application repository, then push only the local delta:

```bash
sudo git -C /opt/calb-sizingtool/relay.git fetch \
  /opt/calb-sizingtool/app \
  refs/heads/ops/ubuntu-docker-coexist-20260311:\
  refs/heads/ops/ubuntu-docker-coexist-20260311
sudo chown -R guoxia:guoxia /opt/calb-sizingtool/relay.git
```

Do not use `scp`, `rsync`, or manual application-directory copying as a
deployment substitute. If the relay is damaged, stop deployment, preserve the
current application SHA, recreate the bare repository with the same ownership,
and bootstrap it through Git fetch/push before resuming the standard procedure.

## Rollback policy

Normal rollback is a new tested Git commit that reverts the faulty change and
then follows the same GitHub -> relay -> server fast-forward procedure. Do not
reset the server working tree to an arbitrary commit or force-push a rollback
without an explicit incident decision.

## Deployment record

| Date | Branch | Previous app SHA | Deployed SHA | Result |
| --- | --- | --- | --- | --- |
| 2026-07-14 | `ops/ubuntu-docker-coexist-20260311` | `0fd2a93` | `2d0e29a` | Relay push, server `ff-only`, Docker rebuild/restart, HTTP 200 |
| 2026-07-14 | `ops/ubuntu-docker-coexist-20260311` | `2c7d5c1` | `24ba9e0` | Project/Case access isolation and Run restore workflow; relay push, server `ff-only`, Docker rebuild/restart, HTTP 200 |
| 2026-07-16 | `ops/ubuntu-docker-coexist-20260311` | `eb8b68f` | `7bc4191` | SLD/Layout drawing-quality hardening batch (13 commits). Direct server→GitHub pull re-tested first: port 443 still times out (admin ticket open), so relay path used. Relay push, server `ff-only`, Docker rebuild/restart, HTTP 200 |
| 2026-07-16 | `ops/ubuntu-docker-coexist-20260311` | `7bc4191` | `4396902` | Report V2.1 customer-readability pass (milestone chart restored, cover/footer/table styling, Meets-Target semantics). First relay attempt hit a VPN outage (host unreachable); completed after VPN recovery. Relay push, server `ff-only`, Docker rebuild/restart, HTTP 200 |
| 2026-07-17 | `ops/ubuntu-docker-coexist-20260311` | `4396902` | `e66cc11` | Brand-profile centralization: Guoxia white-label variant no longer leaks CALB copy (cover issuer, confidentiality notice); dual-brand GUOXIA-LOGO2 header; equipment-name neutralization; brand-separation regression tests. VPN outage delayed relay push. Relay push, server `ff-only`, Docker rebuild/restart, HTTP 200; logo asset confirmed on server |
| 2026-07-18 | `ops/ubuntu-docker-coexist-20260311` | `e66cc11` (app worktree at `5d9a842` docs) | `4d23c6b` | Layout L1: rule-based AC block arrangement engine + report §8 figure/basis table; knowledge base, roadmap, handoff docs. Server→GitHub 443 regressed (TLS reset then timeout) so `calb-serverctl.sh update` failed at pull; fell back to relay. Relay push, server `ff-only`, Docker rebuild/restart, HTTP 200 |
| 2026-07-18 | `ops/ubuntu-docker-coexist-20260311` | `4d23c6b` | `ce97c9b` | Report §8 primary figure switched to the rule-based arrangement (legacy 2.0 m artifact demoted to fallback), removing the contradictory-aisle double figure. Internal LAN direct SSH (no VPN); GitHub egress still blocked so relay used. Relay push, server `ff-only`, Docker rebuild/restart, HTTP 200 |

The first attempted full relay push was interrupted after the empty relay had
received a partial pack. The partial state was discarded before the relay was
seeded from the server application repository. The successful update transferred
37 Git objects (17.58 KiB) as an incremental push.
