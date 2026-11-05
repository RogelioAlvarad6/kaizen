# Builds Kaizen and deploys it to a Linux server (e.g. a Raspberry Pi over Tailscale) via SSH + Docker Compose.
# Usage (from this folder):  powershell -ExecutionPolicy Bypass -File .\deploy.ps1 [-Target user@host]
# The target can also come from $env:KAIZEN_DEPLOY_TARGET or a one-line, git-ignored ".deploy-target" file.
param([string]$Target = $env:KAIZEN_DEPLOY_TARGET)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not $Target -and (Test-Path (Join-Path $root ".deploy-target"))) { $Target = (Get-Content (Join-Path $root ".deploy-target") -TotalCount 1).Trim() }
if (-not $Target) { throw "No deploy target. Pass -Target user@host, set KAIZEN_DEPLOY_TARGET, or create .deploy-target" }
$pi = $Target
$piHost = $pi.Split("@")[-1]
$remote = "docker/sims-tracker"
$env:Path = "C:\Program Files\nodejs;$env:Path"

Write-Host "1/4 Building frontend..." -ForegroundColor Cyan
Push-Location (Join-Path $root "frontend"); npm run build; if ($LASTEXITCODE) { throw "frontend build failed" }; Pop-Location

Write-Host "2/4 Packaging..." -ForegroundColor Cyan
$tar = Join-Path $env:TEMP "sims-tracker.tar"
if (Test-Path $tar) { Remove-Item $tar }
tar -cf $tar -C $root --exclude=__pycache__ backend/app backend/requirements.txt frontend/dist deploy
if ($LASTEXITCODE) { throw "tar failed" }

Write-Host "3/4 Uploading to $pi..." -ForegroundColor Cyan
ssh $pi "mkdir -p ~/$remote/src ~/bin /mnt/data1/sims-tracker"
scp -q $tar "${pi}:~/$remote/sims-tracker.tar"
if ($LASTEXITCODE) { throw "upload failed" }

Write-Host "4/4 Building and restarting on the Pi..." -ForegroundColor Cyan
$cmd = @(
  "set -e",
  "cd ~/$remote",
  "rm -rf src && mkdir src && tar -xf sims-tracker.tar -C src && rm sims-tracker.tar",
  "cp src/deploy/docker-compose.yml ./docker-compose.yml",
  "install -m 755 src/deploy/nightly-backup.sh ~/bin/nightly-backup.sh",
  "install -m 755 src/deploy/pi-health.sh ~/bin/pi-health.sh",
  "docker compose up -d --build",
  "docker image prune -f >/dev/null",
  "docker builder prune -f --filter until=168h >/dev/null",
  "docker ps --filter name=sims-tracker --format '{{.Names}}: {{.Status}}'"
) -join " && "
ssh $pi $cmd
if ($LASTEXITCODE) { throw "remote deploy failed" }

Write-Host "Done -> http://${piHost}:8100" -ForegroundColor Green
