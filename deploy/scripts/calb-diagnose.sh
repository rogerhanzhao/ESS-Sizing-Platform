#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Personal Open-Source Notice
#
# Copyright (c) 2026 Alex.Zhao. All rights reserved.
#
# This repository is released under the MIT License (see LICENSE file).
# Intended use: learning, evaluation, and engineering reference for Utility-scale
# BESS/ESS sizing and Reporting workflows.
#
# DISCLAIMER: This software is provided "AS IS", without warranty of any kind,
# express or implied. In no event shall the author(s) be liable for any claim,
# damages, or other liability arising from, out of, or in connection with the
# software or the use or other dealings in the software.
#
# NOTE: This is a personal project. It is not an official product or statement
# of any company or organization.
# -----------------------------------------------------------------------------
#
# READ-ONLY server diagnostic for the storage/retention story.
#
# Deletes nothing, writes nothing, restarts nothing. Every command here either
# reads a file, queries docker, or asks the app to COUNT. Safe to run on a live
# production host at any time.
#
# It answers the questions that actually decide whether the weekly sweep is
# doing its job:
#
#   1. Is the maintenance timer installed, enabled, and firing?
#   2. What did the last few runs report?
#   3. How big is the runtime root, and which part of it is growing?
#   4. Does the RUNNING container carry the retention knobs? (a container built
#      before 2026-08-06 does not, and silently uses built-in defaults)
#   5. How many artifact files does no registry row point at?
#
# Usage:
#     cd /opt/calb-sizingtool/app
#     sudo bash deploy/scripts/calb-diagnose.sh
#
# Paste the whole output when asking for help with retention or disk usage.

set -uo pipefail   # deliberately NOT -e: a failing probe must not stop the rest

PROJECT_NAME="${COMPOSE_PROJECT_NAME:-calb-sizingtool}"
SERVICE="${CALB_APP_SERVICE:-app}"
RUNTIME_ROOT="${CALB_RUNTIME_ROOT:-/opt/calb-sizingtool/runtime}"

section() { printf '\n\033[1m=== %s ===\033[0m\n' "$1"; }

section "0. Host and checkout"
date -Is
uname -sr
if git -C . rev-parse --short HEAD >/dev/null 2>&1; then
  echo "checkout : $(git -C . rev-parse --abbrev-ref HEAD) @ $(git -C . rev-parse --short HEAD)"
  echo "behind   : $(git -C . rev-list --count HEAD..@{upstream} 2>/dev/null || echo 'no upstream info')"
else
  echo "checkout : not a git working tree"
fi

section "1. Maintenance timer"
systemctl list-timers --all 2>/dev/null | grep -i calb || echo "NO calb timer found — the weekly sweep is not scheduled"
for unit in calb-sizingtool-maintenance.timer calb-sizingtool-maintenance.service; do
  echo "-- $unit: $(systemctl is-enabled "$unit" 2>&1) / $(systemctl is-active "$unit" 2>&1)"
done

section "2. Last maintenance runs"
journalctl -u calb-sizingtool-maintenance --since "60 days ago" --no-pager 2>/dev/null | tail -60 \
  || echo "(no journal entries — never ran, or journald is not retaining them)"

section "3. Runtime root usage"
df -h "$RUNTIME_ROOT" 2>/dev/null | tail -1
du -sh "$RUNTIME_ROOT" 2>/dev/null
for sub in outputs outputs/artifacts outputs/external_ai outputs/logs state; do
  path="$RUNTIME_ROOT/$sub"
  [ -e "$path" ] && printf '%-34s %s\n' "$sub" "$(du -sh "$path" 2>/dev/null | cut -f1)"
done
echo "artifact run directories: $(find "$RUNTIME_ROOT/outputs/artifacts" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)"
echo "artifact files          : $(find "$RUNTIME_ROOT/outputs/artifacts" -type f 2>/dev/null | wc -l)"
echo "oldest artifact file    : $(find "$RUNTIME_ROOT/outputs/artifacts" -type f -printf '%TY-%Tm-%Td\n' 2>/dev/null | sort | head -1)"
ls -la "$RUNTIME_ROOT/state" 2>/dev/null

section "4a. Which build is actually running"
docker compose -p "$PROJECT_NAME" exec -T "$SERVICE" \
  python -c 'from calb_sizing_tool.app_version import version_detail; print(version_detail())' 2>/dev/null \
  || echo "(container down, or an image built before the version stamp existed)"
echo "This is the SAME string shown at the bottom of the app's left sidebar."
echo "Compare its revision with the head commit of that branch on GitHub."

section "4. Container: is it carrying the retention knobs?"
docker compose -p "$PROJECT_NAME" ps 2>/dev/null || echo "(compose stack not reachable)"
echo "-- retention environment INSIDE the running container:"
docker compose -p "$PROJECT_NAME" exec -T "$SERVICE" \
  sh -c 'env | grep -E "^CALB_(ARTIFACT|SNAPSHOT|AUDIT|OPLOG|UNREFERENCED|PRUNE)" | sort' 2>/dev/null \
  || echo "(container not running)"
echo "NOTE: an EMPTY list means this container predates the 2026-08-06 compose"
echo "      change — the sweep can only use built-in defaults and the"
echo "      unreferenced-file sweep cannot be enabled. Fix: git pull, then"
echo "      'docker compose -p $PROJECT_NAME up -d --force-recreate app'."

section "5. What the sweep WOULD prune (counts only, deletes nothing)"
# --dry-run is what makes this section honest. Without it the sweep really
# deletes artifact rows and files, snapshot generations, audit rows and oplogs —
# on a production host, from a script whose header promises it is read-only.
# Blanking CALB_PRUNE_UNREFERENCED_FILES alone held back ONLY the file sweep.
docker compose -p "$PROJECT_NAME" exec -T "$SERVICE" \
  env CALB_PRUNE_UNREFERENCED_FILES= \
  python -m calb_sizing_tool.services.maintenance_service --dry-run 2>/dev/null \
  || echo "(could not run the sweep — container down, or an image predating --dry-run)"
echo "NOTE: nothing above was deleted. The weekly timer runs the same sweep"
echo "      WITHOUT --dry-run; these are the numbers it would act on."

section "6. Docker's own disk usage"
docker system df 2>/dev/null || echo "(docker not reachable)"

printf '\n\033[1mDiagnostic complete. Nothing was deleted by sections 0-4 or 6.\033[0m\n'
