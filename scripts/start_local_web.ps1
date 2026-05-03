param(
    [int]$Port = 8511
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

# ── Schema migrations (Alembic-first) ────────────────────────────────────────
Write-Output "Running database migrations..."
Push-Location $repoRoot
try {
    python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "alembic upgrade head failed (exit $LASTEXITCODE). Check migrations/versions/."
    }
} finally {
    Pop-Location
}
Write-Output "Migrations OK."
$listen = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq $Port }
if ($listen) {
    $owners = $listen | Select-Object -ExpandProperty OwningProcess -Unique
    $procInfo = foreach ($pid in $owners) {
        Get-CimInstance Win32_Process -Filter "ProcessId=$pid" | Select-Object ProcessId, Name, CommandLine
    }
    $ours = $procInfo | Where-Object { $_.CommandLine -like "*streamlit*run app.py*" }
    if ($ours) {
        Write-Output "CALB Streamlit is already running on http://127.0.0.1:$Port"
        exit 0
    }

    $details = $procInfo | ForEach-Object { "$($_.Name) PID=$($_.ProcessId)" }
    throw "Port $Port is already in use by another process. Refusing to auto-switch ports. Occupants: $($details -join ', ')"
}

$streamlitPath = (Get-Command streamlit).Source
if (-not $streamlitPath) {
    throw "streamlit executable not found in PATH."
}

$process = Start-Process `
    -FilePath $streamlitPath `
    -ArgumentList @(
        "run",
        "app.py",
        "--server.address", "127.0.0.1",
        "--server.port", "$Port",
        "--server.headless", "true",
        "--server.fileWatcherType", "none"
    ) `
    -WorkingDirectory $repoRoot `
    -PassThru

for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    $active = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq $Port }
    if ($active) {
        Write-Output "CALB Streamlit started on http://127.0.0.1:$Port (PID $($process.Id))"
        exit 0
    }
    if ($process.HasExited) {
        throw "Streamlit exited early with code $($process.ExitCode)."
    }
}

throw "Streamlit did not bind to port $Port within the expected time."
