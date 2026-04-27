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
  irm https://raw.githubusercontent.com/<you>/scaling-octo-fiesta/main/scripts/bootstrap-windows.ps1 | iex
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
    & $tailscale up --hostname "$DeviceRole.hermes-net" --accept-routes
    Write-Ok "Tailscale up as $DeviceRole.hermes-net"
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
# 6. Pull Ollama models
# ----------------------------------------------------------------------
Write-Section 'Pulling Ollama models'
Start-Service Ollama -ErrorAction SilentlyContinue
$vram = Get-VRAMGigabytes
Write-Host "Detected VRAM: $vram GB"
$coderModel = Pick-CoderModel $vram
$models = @('hermes3:8b', $coderModel)
foreach ($m in $models) {
    Write-Host "ollama pull $m ..."
    ollama pull $m
}
Write-Ok ("Models: " + ($models -join ', '))

# ----------------------------------------------------------------------
# 7. Render daemon config
# ----------------------------------------------------------------------
Write-Section 'Rendering daemon config'
$cfgTpl = Join-Path $repoDir 'configs\daemon.example.yml'
$cfgOut = Join-Path $InstallRoot 'daemon.yml'
$tpl = Get-Content $cfgTpl -Raw
$natsHost = if ($DeviceRole -eq 'g14') { '127.0.0.1' } else { 'g14.hermes-net' }
$rendered = $tpl `
    -replace '\{\{device\}\}',     $DeviceRole `
    -replace '\{\{coder_model\}\}', $coderModel `
    -replace '\{\{nats_host\}\}',  $natsHost
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
