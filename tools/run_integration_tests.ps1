[CmdletBinding()]
param(
    [string]$ProjectName = "atep-integration",
    [switch]$DashboardBrowserAcceptance,
    [switch]$DashboardUiAcceptance,
    [switch]$DashboardLifecycleAcceptance,
    [switch]$DashboardPresentationAcceptance,
    [switch]$DashboardAaosAcceptance,
    [switch]$DashboardAaosNetworkAcceptance,
    [switch]$DashboardAaosRetryExpiry,
    [switch]$DashboardAaosRetryExhaustion,
    [switch]$DashboardAaosNormalCompletion,
    [switch]$DashboardProxyAcceptance,
    [switch]$DashboardProxyTlsAcceptance,
    [switch]$DashboardCertificateLifecycleAcceptance,
    [switch]$DashboardMultiProcessAcceptance,
    [switch]$StartAaosEmulator,
    [switch]$UseExistingImages
)

$ErrorActionPreference = "Stop"
if ($DashboardCertificateLifecycleAcceptance) {
    $DashboardProxyTlsAcceptance = $true
}
if ($DashboardMultiProcessAcceptance -and ($DashboardProxyAcceptance -or $DashboardProxyTlsAcceptance)) {
    throw "Run multiprocess and single-proxy profiles separately."
}
if (($DashboardProxyAcceptance -or $DashboardProxyTlsAcceptance -or $DashboardMultiProcessAcceptance) -and ($DashboardAaosAcceptance -or $DashboardAaosNetworkAcceptance -or $StartAaosEmulator)) {
    throw "Run proxy and emulator scenarios separately."
}
if ($DashboardAaosNormalCompletion -and (-not $DashboardAaosNetworkAcceptance -or $DashboardAaosRetryExpiry -or $DashboardAaosRetryExhaustion)) {
    throw "Normal completion requires network acceptance and cannot combine with fault scenarios."
}
if ($DashboardAaosRetryExhaustion -and (-not $DashboardAaosNetworkAcceptance -or $DashboardAaosRetryExpiry)) {
    throw "Retry exhaustion requires network acceptance and cannot combine with retry expiry."
}
if ($DashboardAaosRetryExpiry -and -not $DashboardAaosNetworkAcceptance) {
    throw "DashboardAaosRetryExpiry requires DashboardAaosNetworkAcceptance."
}
if ($StartAaosEmulator -and -not ($DashboardAaosAcceptance -or $DashboardAaosNetworkAcceptance)) {
    throw "StartAaosEmulator requires an AAOS acceptance scenario."
}
if ($DashboardAaosAcceptance -and $DashboardAaosNetworkAcceptance) {
    throw "Run AAOS authentication and network scenarios separately."
}
$ownedAaos = $false
$adb = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root "compose.integration.yaml"
$composeArgs = @('-p', $ProjectName, '-f', $composeFile)
if ($DashboardProxyAcceptance -or $DashboardProxyTlsAcceptance -or $DashboardMultiProcessAcceptance) {
    $composeArgs += @('-f', (Join-Path $root 'compose.proxy-acceptance.yaml'))
}
if ($DashboardMultiProcessAcceptance) {
    $composeArgs += @('-f', (Join-Path $root 'compose.proxy-multiprocess-acceptance.yaml'))
}
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
$env:ATEP_INTEGRATION_ACCESS_TOKEN_MINUTES = if ($DashboardAaosNormalCompletion) { "10" } else { "5" }
$env:ATEP_INTEGRATION_DASHBOARD_UI_ENABLED = if ($DashboardUiAcceptance -or $DashboardLifecycleAcceptance -or $DashboardPresentationAcceptance) { "true" } else { "false" }
$env:ATEP_INTEGRATION_POSTGRES_PORT = "15432"
$env:ATEP_INTEGRATION_REDIS_PORT = "16379"
$env:ATEP_INTEGRATION_REDIS_URL = "redis://127.0.0.1:16379/0"
$env:ATEP_INTEGRATION_RABBITMQ_PORT = "15673"
$env:ATEP_INTEGRATION_OUTBOX_METRICS_PORT = "19101"
$env:ATEP_INTEGRATION_API_URL = "http://localhost:$($env:ATEP_INTEGRATION_API_PORT)"
$env:ATEP_INTEGRATION_OUTBOX_METRICS_URL = "http://localhost:$($env:ATEP_INTEGRATION_OUTBOX_METRICS_PORT)"
$env:ATEP_INTEGRATION_DATABASE_URL = "postgresql://atep:$($env:ATEP_INTEGRATION_DB_PASSWORD)@localhost:$($env:ATEP_INTEGRATION_POSTGRES_PORT)/atep"
$env:ATEP_INTEGRATION_RABBITMQ_URL = "amqp://$($env:ATEP_INTEGRATION_RABBITMQ_USER):$($env:ATEP_INTEGRATION_RABBITMQ_PASSWORD)@localhost:$($env:ATEP_INTEGRATION_RABBITMQ_PORT)/"

$failed = $true
Push-Location $root
try {
    if ($UseExistingImages) {
        # Opt-in only: caller must build the current source before using this.
        docker compose @composeArgs up --no-build --pull never -d
    }
    else {
        docker compose @composeArgs up --build -d
    }
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

    if ($DashboardUiAcceptance -or $DashboardLifecycleAcceptance -or $DashboardPresentationAcceptance) {
        & (Join-Path $PSScriptRoot "run_dashboard_ui_acceptance.ps1") -Lifecycle:$DashboardLifecycleAcceptance -Presentation:$DashboardPresentationAcceptance
    }

    if ($DashboardBrowserAcceptance) {
        & $python tools\dashboard_browser_fixture.py
        if ($LASTEXITCODE -ne 0) {
            throw "Dashboard browser acceptance failed or timed out."
        }
    }

    if ($DashboardAaosAcceptance -or $DashboardAaosNetworkAcceptance) {
        if ($StartAaosEmulator) {
            $devices = & $adb devices
            if ($LASTEXITCODE -ne 0 -or ($devices -match 'emulator-5554')) {
                throw "Cannot start an owned emulator: adb failed or target is already in use."
            }
            $emulator = Join-Path $env:LOCALAPPDATA "Android\Sdk\emulator\emulator.exe"
            $process = Start-Process -FilePath $emulator -ArgumentList '-avd ATEP_AAOS_API35 -port 5554 -no-window -no-snapshot-save -no-audio -cores 1 -memory 2048 -gpu swiftshader_indirect' -WindowStyle Hidden -PassThru
            $ownedAaos = $true
            $process.PriorityClass = 'BelowNormal'
            $booted = $false
            for ($attempt = 0; $attempt -lt 120; $attempt++) {
                # Windows PowerShell treats adb's expected startup stderr as an
                # error record; tolerate it only inside this bounded boot probe.
                $savedPreference = $ErrorActionPreference
                try {
                    $ErrorActionPreference = 'Continue'
                    $boot = & $adb -s emulator-5554 shell getprop sys.boot_completed 2>$null
                }
                finally { $ErrorActionPreference = $savedPreference }
                if ($boot -eq '1') { $booted = $true; break }
                Start-Sleep -Seconds 2
            }
            if (-not $booted) { throw "AAOS did not boot within the bounded wait." }
        }
        if ($DashboardAaosNetworkAcceptance) {
            if ($DashboardAaosNormalCompletion) {
                & $python -m tools.run_dashboard_aaos_network_acceptance --normal-completion
            }
            elseif ($DashboardAaosRetryExhaustion) {
                & $python -m tools.run_dashboard_aaos_network_acceptance --retry-exhaustion
            }
            elseif ($DashboardAaosRetryExpiry) {
                & $python -m tools.run_dashboard_aaos_network_acceptance --expiry-during-retry
            }
            else { & $python -m tools.run_dashboard_aaos_network_acceptance }
        }
        else { & $python tools\run_dashboard_aaos_acceptance.py }
        if ($LASTEXITCODE -ne 0) { throw "AAOS dashboard acceptance failed." }
    }

    if ($DashboardProxyAcceptance) {
        & $python -m tools.run_dashboard_proxy_acceptance
        if ($LASTEXITCODE -ne 0) { throw "Dashboard proxy acceptance failed." }
    }

    if ($DashboardProxyTlsAcceptance) {
        $tlsArgs = @('--project', $ProjectName)
        if ($DashboardCertificateLifecycleAcceptance) { $tlsArgs += '--lifecycle' }
        & $python -m tools.run_dashboard_tls_acceptance @tlsArgs
        if ($LASTEXITCODE -ne 0) { throw "Dashboard TLS acceptance failed." }
    }

    if ($DashboardMultiProcessAcceptance) {
        & $python -m tools.run_dashboard_proxy_acceptance --multi-process --project $ProjectName
        if ($LASTEXITCODE -ne 0) { throw "Dashboard multiprocess acceptance failed." }
        docker compose @composeArgs stop api-peer
        if ($LASTEXITCODE -ne 0) { throw "Second API could not be quiesced before restore." }
    }

    docker compose @composeArgs stop api outbox-worker
    if ($LASTEXITCODE -ne 0) {
        throw "Application writers could not be quiesced before the restore drill."
    }

    & $python tools\run_postgres_restore_drill.py `
        --compose-file $composeFile `
        --project-name $ProjectName `
        --output-directory (Join-Path $root "dr-evidence")
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL backup and restore drill failed."
    }
    $failed = $false
}
finally {
    if ($ownedAaos) {
        try { & $adb -s emulator-5554 emu kill }
        catch { Write-Warning 'Emulator shutdown could not be confirmed; continuing stack cleanup.' }
    }
    if ($failed) {
        docker compose @composeArgs logs --no-color --tail 200
    }
    docker compose @composeArgs down -v --remove-orphans
    Pop-Location
}
