#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/deploy/docker/.env"
DEFAULT_PROJECT_NAME="calb-sizingtool"
DEFAULT_IMAGE_NAME="calb-sizingtool"
NGROK_CONTAINER_NAME="calb-sizingtool-ngrok"

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

# Database-side retention FIRST, then whatever files it left behind.
#
# Order matters. This script used to delete FILES ONLY. The artifact_registry
# rows survived, pointing at files that no longer existed, and the reader
# swallows every error — so an old run's report lost its figures silently, with
# nothing in any log. Rows and files must expire together, so the application's
# own sweep runs first and the find below is only a floor for anything the
# database never knew about.
cleanup_database_retention() {
  local project_name="${COMPOSE_PROJECT_NAME:-$DEFAULT_PROJECT_NAME}"
  local service="${CALB_APP_SERVICE:-app}"

  echo "Running CALB database retention sweep (rows + their files)"
  docker compose -p "$project_name" exec -T "$service" \
    python -m calb_sizing_tool.services.maintenance_service \
    || echo "Database retention sweep skipped (container not running?)"
}

cleanup_outputs() {
  local runtime_root="${CALB_RUNTIME_ROOT:-/opt/calb-sizingtool/runtime}"
  local retention_days="${CALB_OUTPUT_RETENTION_DAYS:-30}"
  local outputs_dir="${runtime_root}/outputs"

  mkdir -p "$outputs_dir"
  echo "Cleaning CALB output files older than ${retention_days} days in ${outputs_dir}"
  find "$outputs_dir" -type f -mtime +"${retention_days}" -print -delete || true
  find "$outputs_dir" -type d -empty -delete || true
}

cleanup_stopped_compose_containers() {
  local project_name="${COMPOSE_PROJECT_NAME:-$DEFAULT_PROJECT_NAME}"
  mapfile -t stopped_ids < <(docker ps -a \
    --filter "label=com.docker.compose.project=${project_name}" \
    --filter "status=exited" \
    --quiet)

  if [ "${#stopped_ids[@]}" -gt 0 ]; then
    echo "Removing stopped CALB compose containers"
    docker rm -f "${stopped_ids[@]}" >/dev/null
  fi
}

cleanup_ngrok_container() {
  local status_value
  status_value="$(docker inspect --format '{{.State.Status}}' "${NGROK_CONTAINER_NAME}" 2>/dev/null || true)"
  case "$status_value" in
    exited|dead|created)
      echo "Removing stale ngrok helper container"
      docker rm -f "${NGROK_CONTAINER_NAME}" >/dev/null 2>&1 || true
      ;;
  esac
}

cleanup_old_calb_images() {
  local project_name="${COMPOSE_PROJECT_NAME:-$DEFAULT_PROJECT_NAME}"
  local image_name="${CALB_IMAGE_NAME:-$DEFAULT_IMAGE_NAME}"
  local running_container_id
  local running_image_id=""

  running_container_id="$(docker ps \
    --filter "label=com.docker.compose.project=${project_name}" \
    --filter "label=com.docker.compose.service=app" \
    --quiet | head -n 1)"

  if [ -n "$running_container_id" ]; then
    running_image_id="$(docker inspect --format '{{.Image}}' "$running_container_id")"
  fi

  mapfile -t image_ids < <(docker images "$image_name" --format '{{.ID}}' | awk '!seen[$0]++')
  for image_id in "${image_ids[@]}"; do
    [ -z "$image_id" ] && continue
    [ "$image_id" = "$running_image_id" ] && continue
    echo "Removing unused CALB image ${image_id}"
    docker image rm "$image_id" >/dev/null 2>&1 || true
  done
}

maybe_vacuum_global_journal() {
  local enabled="${CALB_ENABLE_GLOBAL_JOURNAL_VACUUM:-false}"
  local retention="${CALB_GLOBAL_JOURNAL_RETENTION:-14d}"

  if [ "$enabled" = "true" ]; then
    require_command journalctl
    echo "Vacuuming global systemd journal older than ${retention}"
    journalctl --vacuum-time="${retention}" >/dev/null
  else
    echo "Skipping global journal vacuum. Set CALB_ENABLE_GLOBAL_JOURNAL_VACUUM=true to enable it."
  fi
}

main() {
  require_command docker
  load_env

  cleanup_database_retention
  cleanup_outputs
  cleanup_stopped_compose_containers
  cleanup_ngrok_container
  cleanup_old_calb_images
  maybe_vacuum_global_journal

  echo "CALB maintenance cleanup completed."
}

main "$@"
