$ErrorActionPreference = "Stop"

Set-Location (Split-Path -Parent $PSScriptRoot)

$env:PYTHONPATH = (Get-Location).Path

$serverHost = $env:SERVER_HOST
$serverPort = $env:SERVER_PORT
$envFile = Join-Path (Get-Location).Path ".env"

if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }
        $parts = $line.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($key -eq "SERVER_HOST" -and -not $serverHost) {
            $serverHost = $value
        }
        if ($key -eq "SERVER_PORT" -and -not $serverPort) {
            $serverPort = $value
        }
    }
}

if (-not $serverHost) {
    $serverHost = "127.0.0.1"
}
if (-not $serverPort) {
    $serverPort = "8000"
}

python -m uvicorn server.main:app --host $serverHost --port $serverPort --reload
