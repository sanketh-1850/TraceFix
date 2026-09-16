param(
    [Parameter(Position=0)]
    [ValidateSet('setup', 'test', 'db-init', 'db-smoke', 'ollama-smoke')]
    [string]$Task = 'test'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    if ($Task -eq 'setup') {
        if (-not (Test-Path '.venv/Scripts/python.exe')) {
            python -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
        }
        & '.venv/Scripts/python.exe' -m pip install -e '.[dev]'
    } elseif ($Task -eq 'test') {
        & '.venv/Scripts/python.exe' -m pytest
    } elseif ($Task -eq 'db-init') {
        & '.venv/Scripts/python.exe' -m tracefix.persistence.cli init
    } elseif ($Task -eq 'db-smoke') {
        & '.venv/Scripts/python.exe' -m tracefix.persistence.cli smoke
    } elseif ($Task -eq 'ollama-smoke') {
        & '.venv/Scripts/python.exe' scripts/smoke_ollama.py --all-models
    }
    if ($LASTEXITCODE -ne 0) { throw "Task '$Task' failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}
