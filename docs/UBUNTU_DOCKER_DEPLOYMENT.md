# Ubuntu Docker Deployment Plan

This document defines the recommended Ubuntu deployment target for the CALB sizing tool when it must coexist with the already-running EnerGain stack on the same server.

## 1. Target architecture

The CALB sizing tool should run as a single Dockerized Streamlit service.

- No database container is required.
- No reverse proxy is required for internal access.
- ngrok is optional and should not be the primary entrypoint anymore.
- Internal users should access the app directly by host/IP and port.

## 2. Coexistence rules with EnerGain

EnerGain already occupies:

- Install root: `/opt/energain`
- Host ports: `9995`, `9996`
- Systemd names: `energain-compose.service`, `energain-healthcheck.service`, `energain-cleanup.service`

The CALB deployment in this repo avoids those conflicts by default:

- Recommended install root: `/opt/calb-sizingtool`
- Recommended repo checkout: `/opt/calb-sizingtool/app`
- Recommended runtime data root: `/opt/calb-sizingtool/runtime`
- Recommended host port: `18511`
- Compose project name: `calb-sizingtool`
- Optional systemd names:
  - `calb-sizingtool-compose.service`
  - `calb-sizingtool-ngrok.service`

## 3. Internal and external access model

Recommended default:

- Internal direct URL: `http://<server-ip>:18511`
- Optional internal DNS URL: `http://calb-sizingtool.intra:18511`

Optional parallel external access:

- Keep the internal direct URL unchanged.
- Start a separate ngrok tunnel only when external sharing is required.
- Do not make ngrok the only access path.

This repo now ships `deploy/docker/calb-serverctl.sh` with `ngrok-start`, `ngrok-stop`, `ngrok-logs`, and `ngrok-url` commands for that optional path.

## 4. What is persisted

The application writes only lightweight runtime artifacts.

- Generated diagrams:
  - `${CALB_RUNTIME_ROOT}/outputs`
- Local app state:
  - `${CALB_RUNTIME_ROOT}/state/user_preferences.json`

The Excel dictionaries remain inside the image because they are part of the repo and versioned together with the code.

## 5. Files added for Ubuntu deployment

- `Dockerfile`
- `deploy/docker/docker-compose.ubuntu.yml`
- `deploy/docker/.env.example`
- `deploy/docker/calb-serverctl.sh`
- `deploy/docker/systemd/calb-sizingtool-compose.service.example`
- `deploy/docker/systemd/calb-sizingtool-ngrok.service.example`

## 6. Server prep

Install Docker and Docker Compose plugin on the Ubuntu server first.

Recommended directory layout:

```text
/opt/calb-sizingtool/
  app/        # git checkout of this repo
  runtime/    # bind-mounted outputs and preferences
```

Clone the repo into the new root, not into `/opt/energain`.

## 7. First-time deployment

1. Clone the repo:

   ```bash
   sudo mkdir -p /opt/calb-sizingtool
   sudo chown "$USER":"$USER" /opt/calb-sizingtool
   git clone -b <branch> <repo-url> /opt/calb-sizingtool/app
   ```

2. Create the deployment env file:

   ```bash
   cd /opt/calb-sizingtool/app
   cp deploy/docker/.env.example deploy/docker/.env
   ```

   Important:
   Do not paste `vi deploy/docker/.env` and `bash deploy/docker/calb-serverctl.sh start`
   in the same multi-line block. `vi` is interactive, and any later pasted lines may end
   up inside the editor instead of being executed by the shell.

3. Edit `deploy/docker/.env` and confirm at least:

   ```dotenv
   COMPOSE_PROJECT_NAME=calb-sizingtool
   CALB_HOST_PORT=18511
   CALB_RUNTIME_ROOT=/opt/calb-sizingtool/runtime
   TZ=UTC
   ```

4. Start the stack:

   ```bash
   bash deploy/docker/calb-serverctl.sh start
   ```

   If you just want the default port `18511`, you can skip editing and start directly after
   copying `.env.example`.

5. Verify:

   ```bash
   bash deploy/docker/calb-serverctl.sh status
   curl -I http://127.0.0.1:18511
   ```

Single-line first install after you choose a branch:

```bash
sudo mkdir -p /opt/calb-sizingtool && sudo chown "$USER":"$USER" /opt/calb-sizingtool && git clone -b <branch> <repo-url> /opt/calb-sizingtool/app && cd /opt/calb-sizingtool/app && cp deploy/docker/.env.example deploy/docker/.env && bash deploy/docker/calb-serverctl.sh start
```

## 8. One-line update flow

After the server-side `deploy/docker/.env` file exists, updates are intentionally simple:

```bash
cd /opt/calb-sizingtool/app && bash deploy/docker/calb-serverctl.sh update <branch>
```

If you already checked out the correct branch and want to keep the current branch, run:

```bash
cd /opt/calb-sizingtool/app && bash deploy/docker/calb-serverctl.sh update
```

The update command is conservative:

- It refuses to run if the git worktree is dirty.
- It uses `git pull --ff-only`.
- It rebuilds and restarts the Docker stack after pulling.

## 9. Optional systemd integration

If you want Docker Compose to auto-start on boot:

1. Copy `deploy/docker/systemd/calb-sizingtool-compose.service.example` to `/etc/systemd/system/calb-sizingtool-compose.service`.
2. Adjust `WorkingDirectory=` if your repo path is different.
3. Reload and enable:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now calb-sizingtool-compose.service
   ```

If you also want an always-on ngrok tunnel, install `calb-sizingtool-ngrok.service` separately. Keep it optional.

## 10. Optional ngrok parallel access

If you need external access without changing the internal direct URL:

1. Set `NGROK_AUTHTOKEN` in `deploy/docker/.env`.
2. Optionally set `NGROK_URL` if you already own a fixed ngrok domain.
3. Start the tunnel:

   ```bash
   bash deploy/docker/calb-serverctl.sh ngrok-start
   bash deploy/docker/calb-serverctl.sh ngrok-url
   ```

4. Stop it when no longer needed:

   ```bash
   bash deploy/docker/calb-serverctl.sh ngrok-stop
   ```

The ngrok helper follows the current official Docker guidance from ngrok:

- https://ngrok.com/docs/using-ngrok-with/docker/
- https://ngrok.com/docs/using-ngrok-with/docker/compose

## 11. Rollback

Rollback stays simple because the deployment is still git-based:

```bash
cd /opt/calb-sizingtool/app
git checkout <previous-tag-or-commit>
bash deploy/docker/calb-serverctl.sh restart
```

## 12. Recommended migration order from N1

1. Keep the existing N1 deployment untouched during the first Ubuntu bring-up.
2. Deploy CALB to Ubuntu on a new port such as `18511`.
3. Verify the full workflow:
   - DC sizing
   - AC sizing
   - SLD export
   - layout export
   - DOCX export
4. Switch internal users to the Ubuntu direct URL.
5. Only enable ngrok if external sharing is still needed.

This keeps the migration low-risk and avoids coupling CALB to EnerGain's existing stack.
