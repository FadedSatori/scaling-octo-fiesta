<#
.SYNOPSIS
  Hermes bootstrap for Windows 11 (Lenovo + G14).

.DESCRIPTION
  Stage 1 installer. Installs system deps via winget, clones the Hermes repo,
  creates a venv, pulls Ollama models sized to detected VRAM, renders the
  daemon config, and registers an NSSM Windows service that runs the Hermes
  daemon. Final step hands off to the Hermes installer agent for self-check
  and mesh registration.

.PARAMETER DeviceRole
  'g14' or 'lenovo'. Determines model selection and whether this device hosts
  the NATS/Qdrant cluster (G14 does by default).

.PARAMETER RepoUrl
  Git URL of the Hermes repo. Defaults to the public scaling-octo-fiesta repo.

.PARAMETER InstallRoot
  Where to clone the repo and place the venv. Default: %LOCALAPPDATA%\Hermes.

.EXAMPLE
  irm https://raw.githubusercontent.com/fadedsatori/scaling-octo-fiesta/main/scripts/bootstrap-windows.ps1 | iex
#>

[CmdletBinding()]
param(
    [ValidateSet('g14','lenovo')]
    [string]$DeviceRole,
    [string]$RepoUrl     = 'https://github.com/fadedsatori/scaling-octo-fiesta.git',
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Hermes')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Section($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok($msg)      { Write-Host "[ok] $msg"    -ForegroundColor Green }
function Write-Warn2($msg)   { Write-Host "[warn] $msg"  -ForegroundColor Yellow }
function Write-Fail($msg)    { Write-Host "[fail] $msg"  -ForegroundColor Red }

function Assert-Admin {
    $id  = [Security.Principal.WindowsIdentity]::GetCurrent()
    $isAdmin = ([Security.Principal.WindowsPrincipal]$id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        throw 'Run this script from an elevated PowerShell (Run as Administrator). Required for NSSM service registration.'
    }
}

function Test-Command($name) {
    return $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

function Install-Winget($id, $displayName) {
    Write-Host "Installing $displayName ..."
    winget install --id $id --silent --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) {
        # -1978335189 = APPINSTALLER_CLI_ERROR_PACKAGE_ALREADY_INSTALLED
        throw "winget failed for $id (exit $LASTEXITCODE)"
    }
    Write-Ok "$displayName"
}

function Get-VRAMGigabytes {
    try {
        $gpus = Get-CimInstance Win32_VideoController |
            Where-Object { $_.AdapterRAM -gt 0 }
        if (-not $gpus) { return 0 }
        $maxBytes = ($gpus | Measure-Object AdapterRAM -Maximum).Maximum
        # Win32_VideoController.AdapterRAM is uint32 and caps at 4GB; for >4GB
        # GPUs the value is wrong. Cross-check via dxdiag if available.
        $gb = [math]::Round($maxBytes / 1GB, 1)
        if ($gb -ge 3.9) {
            $dx = Get-DxDiagVRAM
            if ($dx -gt $gb) { return $dx }
        }
        return $gb
    } catch {
        Write-Warn2 "VRAM detection failed: $_"
        return 0
    }
}

function Get-DxDiagVRAM {
    $tmp = New-TemporaryFile
    try {
        Start-Process dxdiag -ArgumentList "/t `"$tmp`"" -Wait -WindowStyle Hidden
        $text = Get-Content $tmp -Raw
        $match = [regex]::Match($text, 'Dedicated Memory:\s*(\d+)\s*MB')
        if ($match.Success) {
            return [math]::Round([int]$match.Groups[1].Value / 1024.0, 1)
        }
    } catch {
        # ignore
    } finally {
        Remove-Item $tmp -ErrorAction SilentlyContinue
    }
    return 0
}

function Pick-CoderModel($vramGb) {
    if ($vramGb -ge 20) { return 'qwen2.5-coder:32b' }
    if ($vramGb -ge 10) { return 'qwen2.5-coder:14b' }
    if ($vramGb -ge 5)  { return 'qwen2.5-coder:7b'  }
    return 'qwen2.5-coder:3b'
}

# ----------------------------------------------------------------------
# 0. Preflight
# ----------------------------------------------------------------------
Write-Section 'Preflight'
Assert-Admin

if (-not $DeviceRole) {
    $DeviceRole = Read-Host 'Device role? (g14/lenovo)'
    if ($DeviceRole -notin @('g14','lenovo')) { throw "Invalid role '$DeviceRole'." }
}
Write-Ok "Role: $DeviceRole"

if (-not (Test-Command winget)) {
    throw 'winget is required. Install "App Installer" from the Microsoft Store.'
}

# ----------------------------------------------------------------------
# 1. System deps via winget
# ----------------------------------------------------------------------
Write-Section 'Installing system dependencies (winget)'
Install-Winget 'Tailscale.Tailscale'      'Tailscale'
Install-Winget 'Ollama.Ollama'            'Ollama'
Install-Winget 'Python.Python.3.12'       'Python 3.12'
Install-Winget 'Git.Git'                  'Git'
# Docker Desktop: G14 only — hosts Qdrant vector store via Docker Compose.
if ($DeviceRole -eq 'g14') {
    Install-Winget 'Docker.DockerDesktop'     'Docker Desktop'
}
# NSSM is not in winget mainline reliably; install via direct download below.

# ----------------------------------------------------------------------
# 2. NSSM (manual download — winget coverage is spotty)
# ----------------------------------------------------------------------
Write-Section 'Installing NSSM'
$nssmDir = Join-Path $InstallRoot 'nssm'
if (-not (Test-Path (Join-Path $nssmDir 'nssm.exe'))) {
    New-Item -ItemType Directory -Force -Path $nssmDir | Out-Null
    $zip = Join-Path $env:TEMP 'nssm.zip'
    Invoke-WebRequest -Uri 'https://nssm.cc/release/nssm-2.24.zip' -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $env:TEMP -Force
    $arch = if ([Environment]::Is64BitOperatingSystem) { 'win64' } else { 'win32' }
    Copy-Item (Join-Path $env:TEMP "nssm-2.24\$arch\nssm.exe") $nssmDir -Force
    Remove-Item $zip
}
$nssm = Join-Path $nssmDir 'nssm.exe'
Write-Ok "NSSM: $nssm"

# ----------------------------------------------------------------------
# 3. Tailscale up
# ----------------------------------------------------------------------
Write-Section 'Tailscale'
$tailscale = 'C:\Program Files\Tailscale\tailscale.exe'
if (-not (Test-Path $tailscale)) {
    Write-Warn2 'Tailscale binary not found at expected path; check installation.'
} else {
    $tsName = if ($DeviceRole -eq 'g14') { 'UNIT-G14-MainNode' } else { 'UNIT-Lenovo-MIA' }
    & $tailscale up --hostname $tsName --accept-routes
    Write-Ok "Tailscale up as $tsName"
}

# ----------------------------------------------------------------------
# 4. Clone repo
# ----------------------------------------------------------------------
Write-Section 'Cloning Hermes repo'
$repoDir = Join-Path $InstallRoot 'repo'
if (Test-Path $repoDir) {
    Write-Host 'Repo exists — pulling latest.'
    git -C $repoDir pull --ff-only
} else {
    git clone $RepoUrl $repoDir
}
Write-Ok "Repo: $repoDir"

# ----------------------------------------------------------------------
# 4b. NATS JetStream server (G14 only — must run after repo clone for nats.conf)
# ----------------------------------------------------------------------
if ($DeviceRole -eq 'g14') {
    Write-Section 'Installing NATS JetStream server (G14)'
    $natsDir = Join-Path $InstallRoot 'nats'
    $natsBin = Join-Path $natsDir 'nats-server.exe'

    if (-not (Test-Path $natsBin)) {
        New-Item -ItemType Directory -Force -Path $natsDir | Out-Null
        $natsVersion = '2.10.14'
        $natsZipUrl  = "https://github.com/nats-io/nats-server/releases/download/v${natsVersion}/nats-server-v${natsVersion}-windows-amd64.zip"
        $natsZip     = Join-Path $env:TEMP 'nats-server.zip'
        Invoke-WebRequest -Uri $natsZipUrl -OutFile $natsZip
        Expand-Archive -Path $natsZip -DestinationPath $env:TEMP -Force
        Copy-Item (Join-Path $env:TEMP "nats-server-v${natsVersion}-windows-amd64\nats-server.exe") $natsBin -Force
        Remove-Item $natsZip -ErrorAction SilentlyContinue
    }
    Write-Ok "nats-server: $natsBin"

    # JetStream store dir — matches the path declared in configs/nats.conf
    New-Item -ItemType Directory -Force -Path 'C:\ProgramData\Hermes\nats-jetstream' | Out-Null

    # Copy nats.conf to a stable location outside the repo so a future
    # git-pull in propagate.ps1 doesn't change the path the service uses.
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot 'logs') | Out-Null
    $natsConf = Join-Path $InstallRoot 'nats.conf'
    Copy-Item (Join-Path $repoDir 'configs\nats.conf') $natsConf -Force

    $natsSvc = 'HermesNATS'
    & $nssm stop    $natsSvc confirm 2>$null | Out-Null
    & $nssm remove  $natsSvc confirm 2>$null | Out-Null
    & $nssm install $natsSvc $natsBin '-c' "`"$natsConf`""
    & $nssm set     $natsSvc AppDirectory   $natsDir
    & $nssm set     $natsSvc AppStdout      (Join-Path $InstallRoot 'logs\nats-stdout.log')
    & $nssm set     $natsSvc AppStderr      (Join-Path $InstallRoot 'logs\nats-stderr.log')
    & $nssm set     $natsSvc AppRotateFiles 1
    & $nssm set     $natsSvc AppRotateBytes 10485760
    & $nssm set     $natsSvc Start          SERVICE_AUTO_START
    & $nssm start   $natsSvc
    Write-Ok 'Service HermesNATS installed and started'
} else {
    Write-Host 'Skipping NATS install (not g14)' -ForegroundColor Gray
}

# ----------------------------------------------------------------------
# 4c. Qdrant vector store via Docker Compose (G14 only)
# ----------------------------------------------------------------------
if ($DeviceRole -eq 'g14') {
    Write-Section 'Starting Qdrant vector store (Docker Compose, G14)'
    if (-not (Test-Command docker)) {
        Write-Warn2 'Docker not found. Install Docker Desktop and re-run to start Qdrant.'
        Write-Warn2 'Download: https://docs.docker.com/desktop/install/windows-install/'
    } else {
        New-Item -ItemType Directory -Force -Path 'C:\ProgramData\Hermes\qdrant-storage' | Out-Null
        $composeFile = Join-Path $repoDir 'configs\docker-compose.qdrant.yml'
        docker compose -f $composeFile up -d --pull missing
        Write-Ok 'Qdrant started on port 6333'
    }
} else {
    Write-Host 'Skipping Qdrant (not g14)' -ForegroundColor Gray
}

# ----------------------------------------------------------------------
# 5. Python venv + install daemon
# ----------------------------------------------------------------------
Write-Section 'Python venv + Hermes daemon'
$venv = Join-Path $InstallRoot 'venv'
if (-not (Test-Path $venv)) {
    py -3.12 -m venv $venv
}
$py = Join-Path $venv 'Scripts\python.exe'
& $py -m pip install --upgrade pip wheel
& $py -m pip install -e (Join-Path $repoDir 'hermes')
Write-Ok 'Daemon installed in venv'

# ----------------------------------------------------------------------
# 5b. Ollama as an NSSM service
#     Without this the Hermes service (LocalSystem at boot) talks to a
#     dead 127.0.0.1:11434 until the desktop user logs in.
# ----------------------------------------------------------------------
Write-Section 'Registering Ollama as a service (HermesOllama)'

# winget can install Ollama to either Program Files (system) or
# LOCALAPPDATA\Programs\Ollama (per-user). Resolve at bootstrap time
# so the NSSM service holds an absolute path and LocalSystem doesn't
# need a PATH lookup.
$ollamaBin = $null
$cmd = Get-Command ollama -ErrorAction SilentlyContinue
if ($cmd) { $ollamaBin = $cmd.Source }
if (-not $ollamaBin) {
    $fallback = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path $fallback) { $ollamaBin = $fallback }
}
if (-not $ollamaBin) {
    throw 'ollama.exe not found after winget install; reopen PowerShell to refresh PATH or set OLLAMA path manually.'
}
Write-Ok "ollama.exe: $ollamaBin"

# System-wide model store: lets the admin's `ollama pull` (next step)
# and the LocalSystem service share one cache. Without this, LocalSystem
# would look in C:\Windows\System32\config\systemprofile\.ollama and miss
# every model pulled during bootstrap.
$ollamaModels = 'C:\ProgramData\Hermes\ollama-models'
New-Item -ItemType Directory -Force -Path $ollamaModels | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot 'logs') | Out-Null

$ollamaSvc = 'HermesOllama'
& $nssm stop    $ollamaSvc confirm 2>$null | Out-Null
& $nssm remove  $ollamaSvc confirm 2>$null | Out-Null
& $nssm install $ollamaSvc $ollamaBin 'serve'
& $nssm set     $ollamaSvc AppDirectory   (Split-Path $ollamaBin)
& $nssm set     $ollamaSvc AppEnvironmentExtra "OLLAMA_MODELS=$ollamaModels" "OLLAMA_HOST=127.0.0.1:11434"
& $nssm set     $ollamaSvc AppStdout      (Join-Path $InstallRoot 'logs\ollama-stdout.log')
& $nssm set     $ollamaSvc AppStderr      (Join-Path $InstallRoot 'logs\ollama-stderr.log')
& $nssm set     $ollamaSvc AppRotateFiles 1
& $nssm set     $ollamaSvc AppRotateBytes 10485760
& $nssm set     $ollamaSvc Start          SERVICE_AUTO_START
& $nssm start   $ollamaSvc
Write-Ok 'Service HermesOllama installed and started'

# Wait for the service to bind 11434 before pulling models.
$deadline = (Get-Date).AddSeconds(30)
$ready = $false
while ((Get-Date) -lt $deadline) {
    try {
        Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' `
            -UseBasicParsing -TimeoutSec 2 | Out-Null
        $ready = $true; break
    } catch { Start-Sleep -Seconds 1 }
}
if (-not $ready) { throw 'HermesOllama did not respond on 127.0.0.1:11434 within 30s' }
Write-Ok 'HermesOllama responding on 127.0.0.1:11434'

# ----------------------------------------------------------------------
# 6. Pull Ollama models
# ----------------------------------------------------------------------
Write-Section 'Pulling Ollama models'
# Point the admin-user `ollama pull` at the HermesOllama service so the
# downloaded blobs land in the shared store, not the admin's profile.
$env:OLLAMA_MODELS = $ollamaModels
$env:OLLAMA_HOST   = '127.0.0.1:11434'
$vram = Get-VRAMGigabytes
Write-Host "Detected VRAM: $vram GB"
$coderModel = Pick-CoderModel $vram
$models = @('hermes3:8b', $coderModel)
foreach ($m in $models) {
    Write-Host "ollama pull $m ..."
    ollama pull $m
    if ($LASTEXITCODE -ne 0) {
        throw "ollama pull $m failed (exit $LASTEXITCODE) — check HermesOllama logs at $InstallRoot\logs"
    }
}
Write-Ok ("Models: " + ($models -join ', '))

# ----------------------------------------------------------------------
# 7. Render daemon config
# ----------------------------------------------------------------------
Write-Section 'Rendering daemon config'
$cfgTpl = Join-Path $repoDir 'configs\daemon.example.yml'
$cfgOut = Join-Path $InstallRoot 'daemon.yml'
$tpl = Get-Content $cfgTpl -Raw
$natsHost = if ($DeviceRole -eq 'g14') { '127.0.0.1' } else { 'UNIT-G14-MainNode' }
$rendered = $tpl `
    -replace '\{\{device\}\}',      $DeviceRole `
    -replace '\{\{coder_model\}\}', $coderModel `
    -replace '\{\{nats_host\}\}',   $natsHost `
    -replace '\{\{username\}\}',    $env:USERNAME `
    -replace '\{\{repo_root\}\}',   $repoDir.Replace('\', '/')
Set-Content -Path $cfgOut -Value $rendered -Encoding UTF8
Write-Ok "Config: $cfgOut"

# ----------------------------------------------------------------------
# 8. Register NSSM service
# ----------------------------------------------------------------------
Write-Section 'Registering NSSM service "Hermes"'
$svcName = 'Hermes'
& $nssm stop    $svcName confirm 2>$null | Out-Null
& $nssm remove  $svcName confirm 2>$null | Out-Null
& $nssm install $svcName $py '-m' 'hermes.daemon' '--config' "`"$cfgOut`""
& $nssm set     $svcName AppDirectory   $repoDir
& $nssm set     $svcName AppStdout      (Join-Path $InstallRoot 'logs\stdout.log')
& $nssm set     $svcName AppStderr      (Join-Path $InstallRoot 'logs\stderr.log')
& $nssm set     $svcName AppRotateFiles 1
& $nssm set     $svcName AppRotateBytes 10485760
& $nssm set     $svcName Start          SERVICE_AUTO_START
# Hermes needs Ollama on every device, and NATS on the G14. NSSM accepts
# a space-separated list under DependOnService; SCM will serialize starts.
$deps = @('HermesOllama')
if ($DeviceRole -eq 'g14') { $deps += 'HermesNATS' }
& $nssm set     $svcName DependOnService ($deps -join ' ')
New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot 'logs') | Out-Null
& $nssm start   $svcName
Write-Ok 'Service Hermes installed and started'

# ----------------------------------------------------------------------
# 9. Hand off to installer agent
# ----------------------------------------------------------------------
Write-Section 'Handing off to Hermes installer agent'
& $py -m hermes.daemon.installer --config $cfgOut --device $DeviceRole
Write-Ok 'Bootstrap complete.'
Write-Host ''
Write-Host "Daemon:   sc query Hermes" -ForegroundColor Gray
Write-Host "Logs:     $(Join-Path $InstallRoot 'logs')" -ForegroundColor Gray
Write-Host "Config:   $cfgOut" -ForegroundColor Gray
