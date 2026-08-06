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
<#
.SYNOPSIS
    Reclaim a developer checkout's outputs/ directory.

.DESCRIPTION
    The deployed host is swept weekly by deploy/docker/calb-maintenance.sh. A
    developer checkout was swept by NOTHING, which is how one accumulated 479
    run directories / 172 MB. This wraps the retention sweep so that the safe
    order — look at the number, THEN delete — is the shape of the command
    rather than something to remember.

    Without -Delete it changes nothing at all: it counts and prints.

.PARAMETER Delete
    Actually delete. Without it this is a dry run.

.PARAMETER GraceDays
    Artifact files younger than this are never candidates, because their
    registry row may not have committed yet. Default 7.

    DO NOT set this to 0 on a machine whose database holds real work. It is
    defensible only after confirming the artifact registry is genuinely empty —
    with real rows present, the grace period is the thing standing between a
    just-written figure and deletion.

.PARAMETER SkipMigrate
    Skip 'alembic upgrade head'. The sweep reads artifact_registry, so on a
    database whose schema is missing it refuses to run (correctly — an
    unreadable registry must never authorise deletion).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\clean_outputs.ps1
    Count only. Read the number before going further.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\clean_outputs.ps1 -Delete
#>
[CmdletBinding()]
param(
    [switch]$Delete,
    [int]$GraceDays = 7,
    [switch]$SkipMigrate
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot

try {
    Write-Host "Repository : $repoRoot"

    if (-not $SkipMigrate) {
        Write-Host "`n[1/3] alembic upgrade head" -ForegroundColor Cyan
        # The sweep reads artifact_registry. On a database missing that table it
        # refuses outright, so migrating first is what lets it run at all.
        python -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw "alembic upgrade failed; not sweeping a database in an unknown state." }
    }

    Write-Host "`n[2/3] Measuring" -ForegroundColor Cyan
    $env:CALB_UNREFERENCED_GRACE_DAYS = "$GraceDays"
    $env:CALB_PRUNE_UNREFERENCED_FILES = ""
    $dryJson = python -m calb_sizing_tool.services.maintenance_service | Out-String
    $dry = $dryJson | ConvertFrom-Json

    $before        = $dry.before
    $unreferenced  = $dry.pruned.unreferenced_files
    $registryRows  = $dry.before.row_counts.artifact_registry

    Write-Host ("  outputs/            : {0} files, {1} MB" -f $before.output_files, $before.output_mb)
    Write-Host ("  artifact_registry   : {0} rows" -f $registryRows)
    Write-Host ("  unreferenced files  : {0}" -f $unreferenced) -ForegroundColor Yellow

    # The one mistake this script exists to catch. An operator pointed at the
    # wrong database sees an empty registry, and a sweep that trusted it would
    # condemn every artifact on disk. Say so loudly rather than proceed.
    if ($unreferenced -gt 0 -and $registryRows -eq 0) {
        Write-Host "`n  WARNING: the registry has 0 rows while files exist on disk." -ForegroundColor Red
        Write-Host "  That is normal ONLY for a database that never ran a sizing." -ForegroundColor Red
        Write-Host "  If this machine has real work in it, you are pointed at the" -ForegroundColor Red
        Write-Host "  wrong database (check CALB_DATABASE_URL) — STOP HERE." -ForegroundColor Red
    }

    if (-not $Delete) {
        Write-Host "`n[3/3] Dry run — nothing was deleted." -ForegroundColor Green
        Write-Host "  Re-run with -Delete once the numbers above look right."
        return
    }

    Write-Host "`n[3/3] Deleting" -ForegroundColor Cyan
    $env:CALB_PRUNE_UNREFERENCED_FILES = "1"
    $runJson = python -m calb_sizing_tool.services.maintenance_service | Out-String
    $run = $runJson | ConvertFrom-Json

    $freedMb = [math]::Round($run.pruned.bytes_freed / 1MB, 1)
    Write-Host ("  deleted files : {0}" -f $run.pruned.unreferenced_files)
    Write-Host ("  freed         : {0} MB" -f $freedMb)
    Write-Host ("  outputs/ now  : {0} files, {1} MB" -f $run.after.output_files, $run.after.output_mb) -ForegroundColor Green
}
finally {
    Remove-Item Env:\CALB_PRUNE_UNREFERENCED_FILES -ErrorAction SilentlyContinue
    Remove-Item Env:\CALB_UNREFERENCED_GRACE_DAYS -ErrorAction SilentlyContinue
    Pop-Location
}
