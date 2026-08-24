Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

$venvPython = "$root\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    $venvPython = "$root\.venv\bin\python.exe"
}

if (-not (Test-Path $venvPython)) {
    throw "Could not find the Python executable inside the virtual environment."
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r "$root\environment\requirements.txt"
& $venvPython "$root\environment\run_student_checks.py"

Write-Host "Environment setup complete."
