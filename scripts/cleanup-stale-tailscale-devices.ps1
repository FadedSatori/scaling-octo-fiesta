<#
.SYNOPSIS
  Delete stale `*-hermes-net` device records from the Tailscale tailnet.

.DESCRIPTION
  Before the UNIT-<model>-<role> rename, the bootstrap registered devices
  with hostnames like `g14.hermes-net`, which Tailscale rewrote
  server-side to `g14-hermes-net`. After the rename, those stale records
  remain in the tailnet alongside the new `UNIT-*` ones. This script
  finds every device whose hostname ends with `-hermes-net` and deletes
  it via the Tailscale API.

  Requires a Tailscale API token with device:delete scope. Mint one at
  https://login.tailscale.com/admin/settings/keys and either pass it via
  -ApiToken or set $env:TAILSCALE_API_TOKEN.

  Default tailnet (`-`) targets the API key owner's tailnet, which is
  correct for personal accounts. Pass -Tailnet for org tailnets
  (e.g. `example.com`).

.PARAMETER ApiToken
  Tailscale API access token. Defaults to $env:TAILSCALE_API_TOKEN.

.PARAMETER Tailnet
  Tailnet identifier. Defaults to `-` (the API key owner's tailnet).

.PARAMETER Force
  Delete without per-device confirmation.

.EXAMPLE
  $env:TAILSCALE_API_TOKEN = 'tskey-api-...'
  ./cleanup-stale-tailscale-devices.ps1 -WhatIf
  ./cleanup-stale-tailscale-devices.ps1 -Force
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [string]$ApiToken = $env:TAILSCALE_API_TOKEN,
    [string]$Tailnet  = '-',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($ApiToken)) {
    throw 'No API token. Pass -ApiToken or set $env:TAILSCALE_API_TOKEN.'
}

$headers = @{ Authorization = "Bearer $ApiToken" }
$base    = 'https://api.tailscale.com/api/v2'

Write-Host "Listing devices in tailnet '$Tailnet'..." -ForegroundColor Cyan
$resp    = Invoke-RestMethod -Uri "$base/tailnet/$Tailnet/devices" -Headers $headers -Method Get
$devices = @($resp.devices)
Write-Host "Found $($devices.Count) total devices." -ForegroundColor Cyan

$stale = @($devices | Where-Object { $_.hostname -match '-hermes-net$' })

if ($stale.Count -eq 0) {
    Write-Host 'No stale *-hermes-net devices to remove.' -ForegroundColor Green
    return
}

Write-Host "`nStale devices to delete:" -ForegroundColor Yellow
$stale | ForEach-Object {
    Write-Host ("  {0}  ({1})  last seen {2}" -f $_.hostname, $_.id, $_.lastSeen)
}

$ok = 0
$fail = 0
foreach ($d in $stale) {
    $target = "$($d.hostname) [$($d.id)]"
    if ($PSCmdlet.ShouldProcess($target, 'DELETE')) {
        if (-not $Force) {
            $ans = Read-Host "Delete $target ? [y/N]"
            if ($ans -notmatch '^[Yy]') { Write-Host "  skipped: $target"; continue }
        }
        try {
            Invoke-RestMethod -Uri "$base/device/$($d.id)" -Headers $headers -Method Delete | Out-Null
            Write-Host "  deleted: $target" -ForegroundColor Green
            $ok++
        } catch {
            Write-Host "  FAILED:  $target -- $($_.Exception.Message)" -ForegroundColor Red
            $fail++
        }
    }
}

Write-Host "`nDone. Deleted: $ok. Failed: $fail." -ForegroundColor Cyan
