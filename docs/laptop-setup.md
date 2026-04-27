# Laptop setup (Lenovo + G14, Windows 11)

## One-liner

From an elevated PowerShell:

```powershell
irm https://raw.githubusercontent.com/fadedsatori/scaling-octo-fiesta/main/scripts/bootstrap-windows.ps1 | iex
```

This installs Tailscale, Ollama, Python 3.12, Git, NSSM, then clones the
repo, creates a venv, pulls models sized to detected VRAM, renders the
config, and registers a Windows service.

## What it actually does (step by step)

1. **Preflight** — verifies you're elevated and that winget is available;
   prompts for `g14` / `lenovo` role if not passed.
2. **System deps** — winget installs Tailscale, Ollama, Python 3.12, Git.
3. **NSSM** — direct download from nssm.cc (winget coverage is unreliable).
4. **Tailscale** — runs `tailscale up --hostname <role>.hermes-net`.
5. **Repo clone** — to `%LOCALAPPDATA%\Hermes\repo`.
6. **venv + pip install** — installs the daemon as an editable package.
7. **Models** — pulls `hermes3:8b` plus a Qwen2.5-Coder model sized via
   dxdiag VRAM detection:
   - ≥20GB → `qwen2.5-coder:32b`
   - ≥10GB → `qwen2.5-coder:14b`
   - ≥5GB  → `qwen2.5-coder:7b`
   - else  → `qwen2.5-coder:3b`
8. **Config** — renders `configs/daemon.example.yml` to
   `%LOCALAPPDATA%\Hermes\daemon.yml` with the device, model, and NATS host
   filled in.
9. **NSSM service** — registers `Hermes`, points it at
   `python -m hermes.daemon --config <daemon.yml>`, sets log paths,
   starts it.
10. **Installer agent** — runs `python -m hermes.daemon.installer` once
    in the foreground to verify `/healthz` and run the smoke prompts.

## Verifying

```powershell
sc query Hermes                          # service running?
curl http://127.0.0.1:8765/healthz       # daemon responsive?
ollama list                              # models downloaded?
tailscale status                         # mesh up?
```

Logs land in `%LOCALAPPDATA%\Hermes\logs\stdout.log` and `stderr.log`.

## Manual commands

If you skipped the bootstrap and want to run the daemon by hand:

```powershell
cd %LOCALAPPDATA%\Hermes\repo
.\..\venv\Scripts\python.exe -m hermes.daemon --config ..\daemon.yml --log-level DEBUG
```

## Uninstall

```powershell
$nssm = "$env:LOCALAPPDATA\Hermes\nssm\nssm.exe"
& $nssm stop Hermes confirm
& $nssm remove Hermes confirm
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\Hermes"
ollama rm hermes3:8b
ollama rm qwen2.5-coder:14b   # adjust to whichever you pulled
```
