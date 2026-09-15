# Called only by the disposable integration runner; never use personal credentials.
[CmdletBinding()]
param([switch]$Lifecycle, [switch]$Presentation)
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
    $deniedUser = Invoke-RestMethod -Method Post -Uri "$($env:ATEP_INTEGRATION_API_URL)/api/v1/users" `
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
function Wait-BrowserCondition([string]$Expression, [int]$Seconds) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    do {
        if ((Invoke-Browser @("eval", $Expression)).Trim() -eq "true") { return }
        Start-Sleep -Seconds 2
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Browser lifecycle condition timed out."
}
function Test-Presentation([string]$State) {
    foreach ($width in @(320, 768, 1280)) {
        $null = Invoke-Browser @("set", "viewport", "$width", "900")
        $null = Invoke-Browser @("snapshot", "-i")
        Assert-Browser "window.innerWidth === $width && document.documentElement.scrollWidth <= window.innerWidth"
        Assert-Browser "Array.from(document.querySelectorAll('input,select,button')).filter(e=>e.getClientRects().length).every(e=>{const r=e.getBoundingClientRect();return r.left>=0 && r.right<=innerWidth && r.height>=44})"
        $null = Invoke-Browser @("screenshot", "--full", "dr-evidence/dashboard-x76-$State-$width.png")
    }
    # Text enlargement is explicit; this is not an operating-system zoom test.
    $null = Invoke-Browser @("set", "viewport", "320", "900")
    $null = Invoke-Browser @("eval", "document.documentElement.style.fontSize='200%'; true")
    Assert-Browser "parseFloat(getComputedStyle(document.documentElement).fontSize) >= 32 && document.documentElement.scrollWidth <= window.innerWidth"
    $null = Invoke-Browser @("screenshot", "--full", "dr-evidence/dashboard-x76-$State-large-text.png")
    $null = Invoke-Browser @("eval", "document.documentElement.style.fontSize=''; true")
    $null = Invoke-Browser @("set", "viewport", "1280", "900")
    Write-Host "Responsive $State checks passed at three widths and 200-percent text."
}

try {
    & npm exec --yes --package=agent-browser@0.37.1 -- agent-browser `
        --session atep-x74 --executable-path $chrome --args '--disable-gpu' open http://localhost:18000/dashboard/
    if ($LASTEXITCODE -ne 0) { throw "Browser initialization failed." }
    $null = Invoke-Browser @("snapshot", "-i")
    $null = Invoke-Browser @("screenshot", "--full", "dr-evidence/dashboard-x74-login.png")
    Assert-Browser "document.title.includes('ATEP') && !!document.querySelector('#login-form')"
    Write-Host "Login shell loaded and controls verified."
    if ($Presentation) {
        $null = Invoke-Browser @("press", "Tab")
        Assert-Browser "document.activeElement.classList.contains('skip-link') && document.activeElement.getBoundingClientRect().top >= 0"
        $null = Invoke-Browser @("press", "Enter")
        Assert-Browser "document.activeElement.id === 'main-content'"
        $null = Invoke-Browser @("press", "Tab")
        Assert-Browser "document.activeElement.id === 'email'"
        $null = Invoke-Browser @("fill", "#email", "invalid-email")
        $null = Invoke-Browser @("click", "#sign-in")
        Assert-Browser "!document.querySelector('#email').validity.valid && document.activeElement.id === 'email' && !document.querySelector('#login-form').hidden"
        $null = Invoke-Browser @("fill", "#email", "")
        Test-Presentation "login"
    }
    if ($Lifecycle) {
        # Keyboard focus sequence, not a claim of complete accessibility conformance.
        $null = Invoke-Browser @("click", "#email")
        foreach ($expected in @("password", "view", "sign-in")) {
            $null = Invoke-Browser @("press", "Tab")
            Assert-Browser "document.activeElement.id === '$expected'"
        }
        Write-Host "Keyboard tab order passed."
    }

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
    if ($Presentation) {
        Test-Presentation "live"
        $null = Invoke-Browser @("click", "#sign-out")
        $null = Invoke-Browser @("wait", "#login-form:not([hidden])")
        Assert-Browser "document.activeElement.id === 'email'"
        # Re-login so the shared logout scenario below remains unchanged.
        $null = Invoke-Browser @("fill", "#email", $env:ATEP_INTEGRATION_ADMIN_EMAIL)
        $null = Invoke-Browser @("fill", "#password", $env:ATEP_INTEGRATION_ADMIN_PASSWORD)
        $null = Invoke-Browser @("press", "Enter")
        $null = Invoke-Browser @("wait", "#snapshot:not([hidden])")
    }

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
    if ($Lifecycle) {
        # Grant and remove a role only on the newly created disposable user.
        try {
            $pair = Invoke-RestMethod -Method Post -TimeoutSec 10 -Uri "$($env:ATEP_INTEGRATION_API_URL)/api/v1/auth/token" `
                -ContentType "application/x-www-form-urlencoded" -Body @{
                    username = $env:ATEP_INTEGRATION_ADMIN_EMAIL; password = $env:ATEP_INTEGRATION_ADMIN_PASSWORD
                }
            $headers = @{ Authorization = "Bearer $($pair.access_token)" }
            $roles = Invoke-RestMethod -TimeoutSec 10 -Uri "$($env:ATEP_INTEGRATION_API_URL)/api/v1/roles" -Headers $headers
            $role = $roles.items | Where-Object { $_.permissions -contains "dashboard:read" } | Select-Object -First 1
            if (-not $role) { throw "No dashboard role available" }
            $roleUrl = "$($env:ATEP_INTEGRATION_API_URL)/api/v1/users/$($deniedUser.id)/roles/$($role.id)"
            $null = Invoke-RestMethod -Method Put -TimeoutSec 10 -Uri $roleUrl -Headers $headers
        }
        catch { throw "Could not prepare disposable role-removal fixture." }
        $null = Invoke-Browser @("fill", "#email", $deniedEmail)
        $null = Invoke-Browser @("fill", "#password", $deniedPassword)
        $null = Invoke-Browser @("press", "Enter")
        $null = Invoke-Browser @("wait", "#snapshot:not([hidden])")
        $null = Invoke-Browser @("snapshot", "-i")
        Assert-Browser "document.activeElement.id === 'sign-out'"
        try { $null = Invoke-RestMethod -Method Delete -TimeoutSec 10 -Uri $roleUrl -Headers $headers }
        catch { throw "Could not remove disposable role." }
        $headers = $null; $pair = $null
        Write-Host "Waiting for the next server permission check (up to 45 seconds)."
        Wait-BrowserCondition "document.querySelector('#session-status').textContent.includes('does not have dashboard access')" 45
        Assert-Browser "document.querySelector('#snapshot').hidden && document.querySelector('#snapshot').textContent === '' && document.activeElement.id === 'email'"
        Write-Host "Live permission loss cleared the snapshot and restored login focus."

        # Test-only socket observation. No tokens or payloads are recorded; no production hook.
        $null = Invoke-Browser @("eval", "window.__opens=0; window.__NativeSocket=window.WebSocket; window.WebSocket=class extends window.__NativeSocket { constructor(...args) { super(...args); window.__testSocket=this; this.addEventListener('open',()=>{window.__opens++;window.__openedAt=Date.now()}); } }; true")
        $null = Invoke-Browser @("fill", "#email", $env:ATEP_INTEGRATION_ADMIN_EMAIL)
        $null = Invoke-Browser @("fill", "#password", $env:ATEP_INTEGRATION_ADMIN_PASSWORD)
        $null = Invoke-Browser @("press", "Enter")
        $null = Invoke-Browser @("wait", "#snapshot:not([hidden])")
        $null = Invoke-Browser @("snapshot", "-i")
        $null = Invoke-Browser @("eval", "window.__closedAt=Date.now(); window.__testSocket.close(); true")
        Wait-BrowserCondition "document.querySelector('#freshness').textContent === 'Stale snapshot'" 10
        Assert-Browser "!document.querySelector('#snapshot').hidden && window.__opens === 1"
        $null = Invoke-Browser @("screenshot", "--full", "dr-evidence/dashboard-x75-stale.png")
        Write-Host "Controlled disconnect retained stale data; waiting for bounded reconnect."
        Wait-BrowserCondition "window.__opens === 2 && document.querySelector('#freshness').textContent === 'Current server snapshot'" 50
        Assert-Browser "window.__openedAt-window.__closedAt >= 30000"
        Write-Host "Reconnect restored a live snapshot after at least 30 real seconds."
        Write-Host "Waiting for real client session expiration; no clock acceleration."
        Wait-BrowserCondition "document.querySelector('#session-status').textContent.includes('session expired')" 310
        Assert-Browser "document.querySelector('#snapshot').hidden && document.querySelector('#snapshot').textContent === '' && document.activeElement.id === 'email' && localStorage.length === 0 && sessionStorage.length === 0"
        $null = Invoke-Browser @("screenshot", "--full", "dr-evidence/dashboard-x75-expired.png")
        $null = Invoke-Browser @("eval", "window.WebSocket=window.__NativeSocket; delete window.__testSocket; true")
        Write-Host "Real local session expiration cleared data and restored login focus."
    }
}
finally {
    $null = Invoke-Browser @("close")
}
