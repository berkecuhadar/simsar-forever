# Sets Simsar Forever up on first run, then starts the dashboard.
#   powershell -ExecutionPolicy Bypass -File start.ps1             start the dashboard
#   powershell -ExecutionPolicy Bypass -File start.ps1 -Demo       start with synthetic demo data
#   powershell -ExecutionPolicy Bypass -File start.ps1 -NoBrowser  do not open a browser tab
param([switch]$Demo, [switch]$Rebuild, [switch]$NoBrowser)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment..."
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { & py -3 -m venv .venv } else { & python -m venv .venv }
    if (-not (Test-Path $venvPython)) {
        throw "Could not create .venv. Install Python 3.12 or newer from https://www.python.org/downloads/ and run start.bat again."
    }
}

$pyVersion = (& $venvPython -c "import sys; print('%d.%d' % sys.version_info[:2])").Trim()
if ([version]$pyVersion -lt [version]"3.12") {
    throw "Simsar Forever needs Python 3.12 or newer, but .venv uses Python $pyVersion. Install a newer Python from https://www.python.org/downloads/, delete the .venv folder and run start.bat again."
}

# Reinstall when dependencies changed or the folder was moved or renamed (the editable install
# remembers the old path).
$stamp = Join-Path $PSScriptRoot ".venv\.simsar-forever-installed"
$installedFrom = ""
if (Test-Path $stamp) { $installedFrom = "$(Get-Content $stamp -Raw)".Trim().Trim([char]0xFEFF) }
if ($installedFrom -ne $PSScriptRoot -or (Get-Item pyproject.toml).LastWriteTime -gt (Get-Item $stamp).LastWriteTime) {
    Write-Host "Installing Python packages..."
    & $venvPython -m pip install --quiet --upgrade pip
    & $venvPython -m pip install --quiet --prefer-binary -e .
    if ($LASTEXITCODE -ne 0) {
        throw ("Installing the Python packages failed (details above). This usually means one of them has no " +
               "ready-made build for Python $pyVersion yet. Install Python 3.13 from https://www.python.org/downloads/, " +
               "delete the .venv folder and run start.bat again.")
    }
    [IO.File]::WriteAllText($stamp, $PSScriptRoot)
}

$index = Join-Path $PSScriptRoot "simsar_forever\web\static\index.html"
$sources = Get-ChildItem frontend\src -Recurse -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$haveNpm = [bool](Get-Command npm -ErrorAction SilentlyContinue)
$stale = (Test-Path $index) -and $sources.LastWriteTime -gt (Get-Item $index).LastWriteTime
# Release archives ship the UI already built, so Node.js is only needed when there is none.
if ($Rebuild -or -not (Test-Path $index) -or ($stale -and $haveNpm)) {
    if (-not $haveNpm) {
        throw "The web UI needs to be built once and Node.js (npm) was not found. Install Node.js 20 or newer."
    }
    Write-Host "Building the web UI..."
    Push-Location frontend
    if (-not (Test-Path node_modules)) { npm ci --no-audit --no-fund }
    npm run build
    Pop-Location
    if (-not (Test-Path $index)) { throw "UI build failed" }
}

$extra = @()
if ($NoBrowser) { $extra += "--no-browser" }
if ($Demo) { & $venvPython -m simsar_forever demo @extra } else { & $venvPython -m simsar_forever serve @extra }
