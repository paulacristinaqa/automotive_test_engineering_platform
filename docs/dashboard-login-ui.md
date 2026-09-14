# X-7.4 — Same-origin dashboard login shell

## Delivery and boundary

The optional `/dashboard/` shell connects the X-7.3 session controller to labeled email/password
inputs, a three-view selector, login/cancel/logout controls, accessible status messages and a
read-only aggregate JSON snapshot. It is an engineering viewer, not the finished KPI/heatmap UI.
The API remains authoritative for identity and `dashboard:read` on every stream authorization check.

The shell is disabled by default. `ATEP_DASHBOARD_UI_ENABLED=true` enables only five allowlisted
assets. It does not enable WebSocket origins automatically. Wheel packaging includes the same
client files used in development; Docker copies them before building the wheel. No proxy, browser
CORS expansion, Node production service, migration or paid service was added.

Responses use no-store, nosniff, no-referrer, frame denial and a restrictive CSP: scripts/styles
and connections are same-origin, while inline scripts, framing and native form submission are
blocked. Login is handled by JavaScript; a script failure must not send passwords through a GET
query. Snapshot content is rendered with `textContent`, never HTML interpretation.

Passwords are cleared synchronously on submission. The authenticated email is cleared from the
input, tokens stay in the existing private-memory controllers, and local/session storage is unused.
Logout, expiration and terminal authorization rejection remove the rendered snapshot. Page exit
disposes the session; returning from browser history requires login. Browser password managers,
developer tools, compromised same-origin code and memory zeroization remain outside this guarantee.

## Local use

Set these in your existing local environment, preserving all other settings:

```dotenv
ATEP_DASHBOARD_UI_ENABLED=true
ATEP_DASHBOARD_BROWSER_ORIGINS=http://localhost:8000
```

Rebuild/restart the existing API deployment and open `http://localhost:8000/dashboard/`.
Use an existing active user with `dashboard:read`. Origin matching is exact: `127.0.0.1` is
different from `localhost`. Do not use the disposable integration credentials in a real deployment.
Production use requires HTTPS and a reviewed reverse-proxy configuration; that acceptance is pending.

## Test objectives and reproduction

- Python asset tests: disabled-by-default behavior; fixed file allowlist; traversal rejection;
  response security headers; labeled inputs and absence of inline event handlers.
- Existing Node suites: session cancellation, deadlines, expiration, logout uncertainty, stream
  authorization rejection, stale state and bounded reconnect behavior.
- Optional real Chrome acceptance: shell rendering; invalid password rejection and input clearing;
  actual form login against the disposable API; authorized snapshot; no persistent credential
  storage; confirmed logout and cleared data; denial for a newly created user with no roles.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\run_integration_tests.ps1 -DashboardUiAcceptance
```

This Windows-only optional check requires Chrome and Node compatible with agent-browser 0.37.1.
It uses an isolated browser with GPU acceleration disabled, no saved browser state and only
disposable users. The initialization command is not captured into a PowerShell pipeline: doing so
held the first attempt open on Windows. Subsequent command output is suppressed to avoid retaining
credential values. Screenshots under ignored `dr-evidence/` show login, live and logout states.
The runner closes Chrome and removes the disposable stack after the restore drill. CI continues
to run deterministic client tests and Docker integration; it does not run this Windows browser check.

## Evidence and remaining gates

On 2026-09-14, local regression passed 597 Python tests and 28 Node tests; Ruff and mypy passed.
The real-browser flow passed invalid login, authenticated snapshot, logout and no-role denial.
The final Docker integration run passed both tests in 20.19 seconds; the PostgreSQL restore drill
passed and the temporary containers/network were removed. Chrome was closed.
Visual inspection guided a fix to replace the pending-access message after the first valid snapshot.
The first automation attempt was interrupted and its temporary stack explicitly cleaned before
the corrected final run. No user project data was deleted.

Whole-host samples during this work were CPU 23% / GPU 9% during preparation and CPU 19% / GPU 8%
during browser testing; API memory was approximately 152 MiB in the latter sample. These are not
peaks or project-specific CPU/GPU attribution. No emulator or GPU computation job was started.

Remaining X-7 work: real-browser expired-session/role-removal/reconnect behavior on this final
shell (unit and earlier fixture evidence are not equivalent), responsive/keyboard acceptance,
AAOS client acceptance and trusted TLS proxy/resource-limit acceptance. Formal standards and OTA
gaps remain deferred. Markdown is current; existing DOCX workbook snapshots are unchanged.
