[CmdletBinding()]
param(
    [string]$ProjectName = "atep-integration"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root "compose.integration.yaml"
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Local Python environment not found at $python"
}

$env:ATEP_INTEGRATION_DB_PASSWORD = [guid]::NewGuid().ToString("N")
$env:ATEP_INTEGRATION_RABBITMQ_USER = "atep-integration"
$env:ATEP_INTEGRATION_RABBITMQ_PASSWORD = [guid]::NewGuid().ToString("N")
$env:ATEP_INTEGRATION_JWT_SECRET = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
$env:ATEP_INTEGRATION_ADMIN_EMAIL = "integration-admin@atep.example.com"
$env:ATEP_INTEGRATION_ADMIN_PASSWORD = "Integration-$([guid]::NewGuid().ToString('N'))!"
$env:ATEP_INTEGRATION_API_PORT = "18000"
$env:ATEP_INTEGRATION_POSTGRES_PORT = "15432"
$env:ATEP_INTEGRATION_RABBITMQ_PORT = "15673"
$env:ATEP_INTEGRATION_API_URL = "http://localhost:$($env:ATEP_INTEGRATION_API_PORT)"
$env:ATEP_INTEGRATION_DATABASE_URL = "postgresql://atep:$($env:ATEP_INTEGRATION_DB_PASSWORD)@localhost:$($env:ATEP_INTEGRATION_POSTGRES_PORT)/atep"
$env:ATEP_INTEGRATION_RABBITMQ_URL = "amqp://$($env:ATEP_INTEGRATION_RABBITMQ_USER):$($env:ATEP_INTEGRATION_RABBITMQ_PASSWORD)@localhost:$($env:ATEP_INTEGRATION_RABBITMQ_PORT)/"

$failed = $true
Push-Location $root
try {
    docker compose -p $ProjectName -f $composeFile up --build -d
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed to start the integration stack."
    }

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            $response = Invoke-RestMethod -Uri "$($env:ATEP_INTEGRATION_API_URL)/health/ready" -TimeoutSec 3
            if ($response.status -eq "ready") {
                $ready = $true
                break
            }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }
    if (-not $ready) {
        throw "Integration API did not become ready within 120 seconds."
    }

    & $python -m pytest -p no:cacheprovider -o "addopts=" -m integration tests\integration
    if ($LASTEXITCODE -ne 0) {
        throw "Integration test suite failed."
    }
    $failed = $false
}
finally {
    if ($failed) {
        docker compose -p $ProjectName -f $composeFile logs --no-color --tail 200
    }
    docker compose -p $ProjectName -f $composeFile down -v --remove-orphans
    Pop-Location
}
