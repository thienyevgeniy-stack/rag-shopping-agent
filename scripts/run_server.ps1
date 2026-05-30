$ErrorActionPreference = "Stop"

Set-Location (Split-Path -Parent $PSScriptRoot)

$env:PYTHONPATH = (Get-Location).Path

python -m uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload
