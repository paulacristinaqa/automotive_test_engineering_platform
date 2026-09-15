# X-7.5 — Real dashboard shell lifecycle acceptance

## Scope

The optional Windows acceptance runner now exercises the actual X-7.4 shell, not an alternate
UI or a fake token provider. It retains the existing login/logout/no-role checks and adds keyboard
navigation, live role removal, controlled disconnect/reconnect and local session expiration.
Production UI, authentication policy, database schema and dependencies are unchanged.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\run_integration_tests.ps1 -DashboardLifecycleAcceptance
```

This switch enables the UI only in the disposable integration stack. It uses the existing five-minute
access-token setting: the initial attempt to use two minutes was rejected by configuration validation
and was removed. The policy minimum is not weakened for testing. The session controller clears local
access approximately ten seconds before the advertised lifetime ends; the test waits on real time.
It does not prove server-side JWT rejection after expiry, because the client closes first.

## Scenarios and objectives

| Scenario | Objective and expected evidence |
|---|---|
| Keyboard traversal | Starting at email, Tab reaches password, view and sign-in in order. |
| Keyboard submission/focus | Enter submits credentials; successful login focuses sign-out. |
| Live role removal | Grant a dashboard-capable role only to a newly created disposable user, open its stream, remove that role through the API and observe denial within the next authorization cycle. |
| Permission cleanup | Denial clears rendered data and restores focus to email; this is not instantaneous push revocation. |
| Controlled disconnect | Close one real browser WebSocket, retain the previous snapshot visibly stale, and observe no immediate replacement connection. |
| Reconnect | A replacement real socket opens after at least 30 seconds and a valid snapshot restores live state. |
| Local expiration | Without clock acceleration, the five-minute session reaches local expiry, clears the snapshot and returns login focus; browser storage remains empty. |

Only the isolated browser replaces its WebSocket constructor with a subclass that observes socket
opens and permits the test to close one socket. It does not record tokens or payloads, change the
client retry algorithm, inject data, fake responses or simulate a real network partition. The native
constructor is restored and the browser is closed. This instrumentation is not shipped in the UI.

The permission fixture may temporarily receive the existing administrator role if it is the only
dashboard-capable role. Only its newly created user is modified, and the whole database is disposable.
No existing user or production role is altered. Tokens used by fixture API calls remain in process
memory and are not written to evidence or printed.

Waits have scenario deadlines (45 seconds for role removal, 50 for reconnect and 310 for local
expiry) and short polling intervals. These are test bounds, not product SLAs. The runner performs
the regular integration suite and restore drill and removes the temporary stack on exit.

## Evidence status

On 2026-09-14, all listed scenarios passed in real Chrome on Windows, using the installed Docker
application and real identity API. Local expiration was observed by 20:50:39 UTC. Login, stale-data
and expired-session screenshots were visually inspected using the browser verification skills.
Keyboard traversal, Enter submission, focus restoration, live role removal and reconnect assertions
passed; the reconnect assertion measured a minimum of 30 seconds. No clock was accelerated.
The local suite passed 597 Python tests, 28 Node tests, Ruff and mypy. Docker integration passed
both tests in 19.00 seconds. The initial unavailable-Docker and rejected two-minute-profile attempts
are not counted as successful runs; the latter stack was cleaned before the corrected run.
The final PostgreSQL restore drill passed; Chrome was closed and the disposable containers and
network were removed. CI runs the regular automated gates; this Windows browser run is local evidence.

Whole-host samples during browser work were CPU 61% / GPU 13%, and during the expiry wait CPU 5%
/ GPU 13%. The latter API sample was 0.39% CPU and 151.7 MiB RAM. These are point samples, not
peaks or attribution of whole-host utilization to ATEP. No emulator or GPU job was started.
Screenshots are retained locally under ignored `dr-evidence/dashboard-x75-stale.png` and
`dr-evidence/dashboard-x75-expired.png`; no authentication state is saved.

Remaining gates include responsive-layout inspection, broader keyboard/accessibility coverage,
network-partition behavior, AAOS and trusted TLS proxy deployment acceptance. These checks do not
constitute accessibility or automotive safety certification. Markdown is current; DOCX is unchanged.
