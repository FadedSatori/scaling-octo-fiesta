<#
.SYNOPSIS
  VRAM-aware Ollama model puller for Hermes.

.DESCRIPTION
  Detects dedicated GPU VRAM and pulls a Hermes-3 8B + a Qwen2.5-Coder model
  sized to fit. Idempotent — re-run after a GPU upgrade to upgrade the coder
  model.
#>
[CmdletBinding()]
param([switch]$DryRun)

$ErrorActionPreference = 'Stop'

function Get-VRAMGB {
    try {
        $tmp = New-TemporaryFile
        Start-Process dxdiag -ArgumentList "/t `"$tmp`"" -Wait -WindowStyle Hidden
        $text = Get-Content $tmp -Raw
        Remove-Item $tmp -ErrorAction SilentlyContinue
        $m = [regex]::Match($text, 'Dedicated Memory:\s*(\d+)\s*MB')
        if ($m.Success) { return [math]::Round([int]$m.Groups[1].Value / 1024.0, 1) }
    } catch { }
    return 0
}

$vram = Get-VRAMGB
Write-Host "VRAM: $vram GB"

$coder =
    if ($vram -ge 20) { 'qwen2.5-coder:32b' }
    elseif ($vram -ge 10) { 'qwen2.5-coder:14b' }
    elseif ($vram -ge 5)  { 'qwen2.5-coder:7b'  }
    else                  { 'qwen2.5-coder:3b'  }

$models = @('hermes3:8b', $coder, 'nomic-embed-text')

foreach ($m in $models) {
    if ($DryRun) {
        Write-Host "would pull: $m"
    } else {
        Write-Host "pulling: $m"
        ollama pull $m
    }
}
