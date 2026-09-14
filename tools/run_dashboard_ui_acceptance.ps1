# Called only by the disposable integration runner; never use personal credentials.
[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
if ($env:ATEP_INTEGRATION_API_URL -ne "http://localhost:18000" -or
    -not $env:ATEP_INTEGRATION_ADMIN_PASSWORD) { throw "Disposable runner environment required." }
$nodeDirectory = Join-Path $env:USERPROFILE ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin"
if (Test-Path $nodeDirectory) { $env:PATH = "$nodeDirectory;$env:PATH" }
$chrome = Join-Path $env:ProgramFiles "Google/Chrome/Application/chrome.exe"
if (-not (Test-Path $chrome)) { throw "Google Chrome is required for this optional Windows acceptance." }
$deniedEmail = "dashboard-denied-$([guid]::NewGuid().ToString('N'))@atep.example.com"
$deniedPassword = "Temporary-$([guid]::NewGuid().ToString('N'))!"
try {
    $pair = Invoke-RestMethod -Method Post -Uri "$($env:ATEP_INTEGRATION_API_URL)/api/v1/auth/token" `
        -ContentType "application/x-www-form-urlencoded" -Body @{
            username = $env:ATEP_INTEGRATION_ADMIN_EMAIL; password = $env:ATEP_INTEGRATION_ADMIN_PASSWORD
        }
    $null = Invoke-RestMethod -Method Post -Uri "$($env:ATEP_INTEGRATION_API_URL)/api/v1/users" `
        -Headers @{ Authorization = "Bearer $($pair.access_token)" } -ContentType "application/json" `
        -Body (@{ email = $deniedEmail; password = $deniedPassword; display_name = "Disposable no-role user" } | ConvertTo-Json)
    $pair = $null
}
catch { throw "Could not create disposable permission fixture." }

function Invoke-Browser([string[]]$Arguments) {
    Write-Host "Browser check: $($Arguments[0])"
    $output = & npm exec --yes --package=agent-browser@0.37.1 -- agent-browser `
        --session atep-x74 @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Browser acceptance command failed; no credential output retained." }
    return ($output -join "`n")
}
function Assert-Browser([string]$Expression) {
    $result = Invoke-Browser @("eval", $Expression)
    if ($result.Trim() -ne "true") { throw "Browser assertion failed." }
}

try {
    & npm exec --yes --package=agent-browser@0.37.1 -- agent-browser `
        --session atep-x74 --executable-path $chrome --args '--disable-gpu' open http://localhost:18000/dashboard/
    if ($LASTEXITCODE -ne 0) { throw "Browser initialization failed." }
    $null = Invoke-Browser @("snapshot", "-i")
    $null = Invoke-Browser @("screenshot", "--full", "dr-evidence/dashboard-x74-login.png")
    Assert-Browser "document.title.includes('ATEP') && !!document.querySelector('#login-form')"
    Write-Host "Login shell loaded and controls verified."

    $null = Invoke-Browser @("fill", "#email", $env:ATEP_INTEGRATION_ADMIN_EMAIL)
    $null = Invoke-Browser @("fill", "#password", "deliberately-invalid-test-password")
    $null = Invoke-Browser @("click", "#sign-in")
    $null = Invoke-Browser @("wait", "#sign-in:not([disabled])")
    $null = Invoke-Browser @("snapshot", "-i")
    Assert-Browser "document.querySelector('#session-status').textContent.includes('not accepted') && document.querySelector('#password').value === ''"

    # Never print browser command output or save authentication state.
    $null = Invoke-Browser @("fill", "#email", $env:ATEP_INTEGRATION_ADMIN_EMAIL)
    $null = Invoke-Browser @("fill", "#password", $env:ATEP_INTEGRATION_ADMIN_PASSWORD)
    $null = Invoke-Browser @("click", "#sign-in")
    $null = Invoke-Browser @("wait", "#snapshot:not([hidden])")
    $null = Invoke-Browser @("snapshot", "-i")
    Assert-Browser "document.querySelector('#login-form').hidden && document.querySelector('#password').value === '' && localStorage.length === 0 && sessionStorage.length === 0 && document.querySelector('#session-status').textContent.includes('access confirmed')"
    $null = Invoke-Browser @("screenshot", "--full", "dr-evidence/dashboard-x74-live.png")
    Write-Host "Real form login and authenticated snapshot passed."

    $null = Invoke-Browser @("click", "#sign-out")
    $null = Invoke-Browser @("wait", "#login-form:not([hidden])")
    $null = Invoke-Browser @("snapshot", "-i")
    Assert-Browser "document.querySelector('#snapshot').hidden && document.querySelector('#snapshot').textContent === '' && document.querySelector('#session-status').textContent === 'Sign in to continue.'"
    $null = Invoke-Browser @("screenshot", "--full", "dr-evidence/dashboard-x74-logout.png")
    Write-Host "Logout cleared the snapshot and server revocation was confirmed."

    $null = Invoke-Browser @("fill", "#email", $deniedEmail)
    $null = Invoke-Browser @("fill", "#password", $deniedPassword)
    $null = Invoke-Browser @("click", "#sign-in")
    $null = Invoke-Browser @("wait", "#login-form:not([hidden]) #sign-in:not([disabled])")
    $null = Invoke-Browser @("snapshot", "-i")
    Assert-Browser "document.querySelector('#session-status').textContent.includes('does not have dashboard access') && document.querySelector('#snapshot').hidden && document.querySelector('#password').value === ''"
    Write-Host "User without dashboard permission was denied and local data cleared."
}
finally {
    $null = Invoke-Browser @("close")
}
