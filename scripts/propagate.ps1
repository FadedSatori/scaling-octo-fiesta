<#
.SYNOPSIS
  Push local config changes to the Hermes mesh.

.DESCRIPTION
  Commits the current state of configs/ and prompt files to the repo, pushes,
  then publishes hermes.events.config_changed on NATS so the other devices
  pull and hot-reload.
#>
[CmdletBinding()]
param(
    [string]$NatsUrl = 'nats://g14.hermes-net:4222',
    [string]$Message = 'config update'
)

$ErrorActionPreference = 'Stop'

$repoDir = Join-Path $env:LOCALAPPDATA 'Hermes\repo'
if (-not (Test-Path $repoDir)) { throw "Hermes repo not found at $repoDir" }
Push-Location $repoDir
try {
    git add configs/ docs/
    # `git diff --cached --quiet` writes nothing to stdout; PowerShell's
    # `if (cmd)` treats stdout as the condition, so the natural reading is
    # always false. Use $LASTEXITCODE: 0 = no diff, 1 = diff present.
    git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'No config changes to push.'
    } else {
        git commit -m "propagate: $Message"
        git push
    }

    $venv = Join-Path $env:LOCALAPPDATA 'Hermes\venv\Scripts\python.exe'
    & $venv -m hermes.routing publish `
        --nats $NatsUrl `
        --subject 'hermes.events.config_changed' `
        --payload "{`"by`": `"$env:COMPUTERNAME`", `"msg`": `"$Message`"}"
    Write-Host 'Propagation event sent.' -ForegroundColor Green
} finally {
    Pop-Location
}
