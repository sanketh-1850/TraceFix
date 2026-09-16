# Start the optional project-local portable Ollama server in a hidden window.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$binary = Join-Path $projectRoot '.tools/ollama/ollama.exe'
if (-not (Test-Path -LiteralPath $binary)) {
    throw 'Extract the official Windows Ollama archive into .tools/ollama first.'
}
try {
    $null = Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 2
    Write-Output 'An Ollama server is already running on port 11434.'
    return
} catch {
    # Start only when no Ollama API is reachable.
}
$artifactDir = Join-Path $projectRoot 'artifacts'
New-Item -ItemType Directory -Force $artifactDir | Out-Null
$previousModels = $env:OLLAMA_MODELS
$previousHost = $env:OLLAMA_HOST
try {
    $env:OLLAMA_MODELS = Join-Path $projectRoot '.models'
    $env:OLLAMA_HOST = '127.0.0.1:11434'
    $process = Start-Process -FilePath $binary -ArgumentList 'serve' -WindowStyle Hidden `
        -WorkingDirectory $projectRoot -PassThru `
        -RedirectStandardOutput (Join-Path $artifactDir 'ollama-stdout.log') `
        -RedirectStandardError (Join-Path $artifactDir 'ollama-stderr.log')
    $process.Id | Set-Content (Join-Path $artifactDir 'ollama.pid')
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($process.HasExited) { throw 'Ollama exited. Check artifacts/ollama-stderr.log.' }
        try {
            $null = Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 1
            Write-Output "Ollama ready on localhost:11434 (PID $($process.Id))."
            return
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    throw 'Ollama did not become ready. Check artifacts/ollama-stderr.log.'
} finally {
    $env:OLLAMA_MODELS = $previousModels
    $env:OLLAMA_HOST = $previousHost
}
