$ErrorActionPreference = "Stop"

Set-Location (Split-Path -Parent $PSScriptRoot)
$env:PYTHONPATH = (Get-Location).Path

python -m compileall server
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

python -m pytest server/tests -q
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
