# Starts the SIMS AI Office backend (port 8000) and frontend dev server (port 5173).
# First run installs dependencies. Usage:  .\start.ps1
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
# Fresh installs may not be on PATH until you open a new terminal.
$env:Path = "C:\Program Files\nodejs;$env:LOCALAPPDATA\Programs\Python\Python312;$env:Path"

# --- backend ---
$venv = Join-Path $root "backend\.venv"
if (-not (Test-Path $venv)) {
    Write-Host "Creating Python venv..." -ForegroundColor Cyan
    python -m venv $venv
    & "$venv\Scripts\python.exe" -m pip install --upgrade pip
    & "$venv\Scripts\python.exe" -m pip install -r (Join-Path $root "backend\requirements.txt")
}
$envFile = Join-Path $root "backend\.env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $root "backend\.env.example") $envFile
    Write-Host "Created backend\.env - add your ANTHROPIC_API_KEY there, then re-run." -ForegroundColor Yellow
}

# --- frontend ---
$fe = Join-Path $root "frontend"
if (-not (Test-Path (Join-Path $fe "node_modules"))) {
    Write-Host "Installing frontend packages..." -ForegroundColor Cyan
    Push-Location $fe; npm install; Pop-Location
}

Start-Process -FilePath "$venv\Scripts\python.exe" -ArgumentList "-m", "uvicorn", "app.main:app", "--port", "8000" -WorkingDirectory (Join-Path $root "backend")
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "npm run dev" -WorkingDirectory $fe
Start-Sleep -Seconds 4
Start-Process "http://localhost:5173"
