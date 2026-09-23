param(
    [Parameter(Position=0)]
    [ValidateSet('setup', 'test', 'db-init', 'db-smoke', 'ollama-smoke', 'seed', 'target-demo', 'eval-target')]
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
    } elseif ($Task -eq 'seed') {
        & '.venv/Scripts/python.exe' -c 'from tracefix.target_agent.cli import seed_main; raise SystemExit(seed_main())'
    } elseif ($Task -eq 'target-demo') {
        & '.venv/Scripts/python.exe' -m tracefix.target_agent.cli --task-id T18
    } elseif ($Task -eq 'eval-target') {
        & '.venv/Scripts/python.exe' -m tracefix.evaluation.runner --subset all
    }
    if ($LASTEXITCODE -ne 0) { throw "Task '$Task' failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}
