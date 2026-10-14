param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create .venv and install requirements.txt first; see README.md.'
}
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.env'))) {
    throw 'Create .env from .env.example and add your OpenAI key.'
}
& docker compose -f (Join-Path $PSScriptRoot 'compose.yaml') up -d --wait redis
if ($LASTEXITCODE -ne 0) { throw 'Redis did not start. Check Docker Desktop and localhost port 6381.' }
& $pythonPath -X utf8 -m uvicorn server:app --host 127.0.0.1 --port $Port --no-proxy-headers
if ($LASTEXITCODE -ne 0) { throw 'The shopping server did not start successfully.' }
