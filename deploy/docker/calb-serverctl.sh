#!/usr/bin/env bash

set -euo pipefail

ACTION="${1:-}"
TARGET_BRANCH="${2:-}"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/deploy/docker/docker-compose.ubuntu.yml"
ENV_FILE="${REPO_ROOT}/deploy/docker/.env"
DEFAULT_PROJECT_NAME="calb-sizingtool"
NGROK_CONTAINER_NAME="calb-sizingtool-ngrok"

usage() {
  cat <<'EOF'
Usage: bash deploy/docker/calb-serverctl.sh <command> [branch]

Commands:
  start         Build and start the CALB stack
  stop          Stop and remove the CALB stack
  restart       Rebuild and restart the CALB stack
  status        Show docker compose status
  logs          Follow CALB app logs
  config        Render docker compose config
  url           Print the internal access URLs
  update        Git pull the target branch (or current branch) and restart
  ngrok-start   Start an optional ngrok tunnel in parallel
  ngrok-stop    Stop the optional ngrok tunnel
  ngrok-status  Show the optional ngrok container status
  ngrok-logs    Follow ngrok logs
  ngrok-url     Print the detected ngrok public URL
EOF
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command not found: $1" >&2
    exit 1
  fi
}

require_env_file() {
  if [ ! -f "$ENV_FILE" ]; then
    echo "Error: missing $ENV_FILE" >&2
    echo "Copy deploy/docker/.env.example to deploy/docker/.env and edit it first." >&2
    exit 1
  fi
}

load_env() {
  require_env_file
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
}

compose() {
  load_env
  require_command docker
  docker compose \
    --env-file "$ENV_FILE" \
    --file "$COMPOSE_FILE" \
    --project-name "${COMPOSE_PROJECT_NAME:-$DEFAULT_PROJECT_NAME}" \
    "$@"
}

ensure_runtime_dirs() {
  load_env
  local runtime_root="${CALB_RUNTIME_ROOT:-/opt/calb-sizingtool/runtime}"
  mkdir -p "${runtime_root}/outputs" "${runtime_root}/state"
}

print_internal_urls() {
  load_env
  local port="${CALB_HOST_PORT:-18511}"
  local hostname_value
  hostname_value="$(hostname -f 2>/dev/null || hostname)"
  echo "Internal URL: http://${hostname_value}:${port}"
  echo "Fallback URL: http://<server-ip>:${port}"
}

ensure_git_clean() {
  if [ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]; then
    echo "Error: git worktree is dirty. Commit or stash changes before running update." >&2
    exit 1
  fi
}

update_repo() {
  require_command git
  if [ ! -d "${REPO_ROOT}/.git" ]; then
    echo "Error: ${REPO_ROOT} is not a git checkout." >&2
    exit 1
  fi

  ensure_git_clean

  local branch="${1:-}"
  if [ -z "$branch" ]; then
    branch="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
  fi
  if [ "$branch" = "HEAD" ]; then
    echo "Error: detached HEAD detected. Pass a branch name to update." >&2
    exit 1
  fi

  git -C "$REPO_ROOT" fetch origin "$branch"
  if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/${branch}"; then
    git -C "$REPO_ROOT" checkout "$branch"
  else
    git -C "$REPO_ROOT" checkout --track "origin/${branch}"
  fi
  git -C "$REPO_ROOT" pull --ff-only origin "$branch"
}

start_ngrok() {
  load_env
  require_command docker

  if [ -z "${NGROK_AUTHTOKEN:-}" ]; then
    echo "Error: NGROK_AUTHTOKEN is empty in ${ENV_FILE}" >&2
    exit 1
  fi

  local port="${CALB_HOST_PORT:-18511}"
  local args=("http" "${port}")
  if [ -n "${NGROK_URL:-}" ]; then
    args+=("--url" "${NGROK_URL}")
  fi

  docker rm -f "${NGROK_CONTAINER_NAME}" >/dev/null 2>&1 || true
  docker run -d \
    --name "${NGROK_CONTAINER_NAME}" \
    --restart unless-stopped \
    --network host \
    -e NGROK_AUTHTOKEN="${NGROK_AUTHTOKEN}" \
    ngrok/ngrok:latest \
    "${args[@]}" >/dev/null

  echo "ngrok tunnel started for http://127.0.0.1:${port}"
}

print_ngrok_url() {
  local url
  url="$(docker logs "${NGROK_CONTAINER_NAME}" 2>&1 | grep -Eo 'https://[A-Za-z0-9._:-]+' | head -n 1 || true)"
  if [ -n "$url" ]; then
    echo "$url"
  else
    echo "No ngrok URL found yet. Check logs with: bash deploy/docker/calb-serverctl.sh ngrok-logs" >&2
    exit 1
  fi
}

case "$ACTION" in
  start)
    ensure_runtime_dirs
    compose up -d --build
    print_internal_urls
    compose ps
    ;;
  stop)
    compose down
    ;;
  restart)
    ensure_runtime_dirs
    compose up -d --build
    print_internal_urls
    compose ps
    ;;
  status)
    compose ps
    if docker ps --format '{{.Names}}' | grep -qx "${NGROK_CONTAINER_NAME}"; then
      docker ps --filter "name=${NGROK_CONTAINER_NAME}"
    fi
    ;;
  logs)
    compose logs -f --tail 200 app
    ;;
  config)
    compose config
    ;;
  url)
    print_internal_urls
    ;;
  update)
    update_repo "$TARGET_BRANCH"
    ensure_runtime_dirs
    compose up -d --build
    print_internal_urls
    compose ps
    ;;
  ngrok-start)
    start_ngrok
    ;;
  ngrok-stop)
    require_command docker
    docker rm -f "${NGROK_CONTAINER_NAME}" >/dev/null 2>&1 || true
    ;;
  ngrok-status)
    require_command docker
    docker ps -a --filter "name=${NGROK_CONTAINER_NAME}"
    ;;
  ngrok-logs)
    require_command docker
    docker logs -f "${NGROK_CONTAINER_NAME}"
    ;;
  ngrok-url)
    require_command docker
    print_ngrok_url
    ;;
  ""|-h|--help|help)
    usage
    ;;
  *)
    echo "Error: unknown command: ${ACTION}" >&2
    usage
    exit 1
    ;;
esac
