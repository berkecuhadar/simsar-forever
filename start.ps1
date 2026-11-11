# Sets Simsar Forever up on first run, then starts the dashboard.
#   powershell -ExecutionPolicy Bypass -File start.ps1           start the dashboard
#   powershell -ExecutionPolicy Bypass -File start.ps1 -Demo     start with synthetic demo data
param([switch]$Demo, [switch]$Rebuild, [switch]$NoBrowser)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment..."
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { & py -3 -m venv .venv } else { & python -m venv .venv }
    if (-not (Test-Path $venvPython)) { throw "Could not create .venv. Install Python 3.12 or newer." }
}

$stamp = Join-Path $PSScriptRoot ".venv\.simsar-installed"
if (-not (Test-Path $stamp) -or (Get-Item pyproject.toml).LastWriteTime -gt (Get-Item $stamp).LastWriteTime) {
    Write-Host "Installing Python packages..."
    & $venvPython -m pip install --quiet --upgrade pip
    & $venvPython -m pip install --quiet -e .
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    New-Item -ItemType File -Force $stamp | Out-Null
}

$index = Join-Path $PSScriptRoot "simsar\web\static\index.html"
$sources = Get-ChildItem frontend\src -Recurse -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($Rebuild -or -not (Test-Path $index) -or $sources.LastWriteTime -gt (Get-Item $index).LastWriteTime) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "The web UI needs to be built once and Node.js (npm) was not found. Install Node.js 20 or newer."
    }
    Write-Host "Building the web UI..."
    Push-Location frontend
    if (-not (Test-Path node_modules)) { npm ci --no-audit --no-fund }
    npm run build
    Pop-Location
    if (-not (Test-Path $index)) { throw "UI build failed" }
}

if (-not (Test-Path config.yaml)) {
    Copy-Item config.example.yaml config.yaml
    Write-Host "Created config.yaml. Set wow.game_dir in it so Simsar Forever can read your Auctionator scans."
}

$simsar = Join-Path $PSScriptRoot ".venv\Scripts\simsar.exe"
$extra = @()
if ($NoBrowser) { $extra += "--no-browser" }
if ($Demo) { & $simsar demo @extra } else { & $simsar serve @extra }
