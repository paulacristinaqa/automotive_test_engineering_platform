# X-7.2 — Browser client lifecycle

`clients/dashboard/stream-client.mjs` is a dependency-free ES module for the existing browser
stream. It is a reusable transport client, not a login page or complete dashboard. The test
fixture serves this exact module, rather than duplicating its reconnect implementation.

## State and resource contract

The caller supplies a trusted endpoint URL, an in-memory access token and a non-throwing
`onState` callback. Endpoints are restricted to the three browser-stream views, WSS (or WS on
loopback), with no URL credentials, query or fragment. Tokens are private, never emitted in
state, written to storage or logged; only the versioned authentication frame transmits them.
The client cannot publish vehicle commands. The caller remains responsible for secure login,
trusted endpoint configuration, UI rendering and deployment origin/TLS policy.

| State/event | Behavior |
|---|---|
| Connecting/authenticating | Snapshot remains stale; first-snapshot deadline is 30 seconds |
| Valid snapshot | Live server-query snapshot; reset failure count and require increasing sequence |
| No next snapshot for 35 seconds | Mark stale (30-second refresh plus 5-second grace), without claiming vehicle freshness |
| Connection closes, including normal session completion | Retain previous snapshot but mark stale immediately; schedule bounded reconnect |
| 4401/4403 | Stop retries, clear token and snapshot, expose auth-required/forbidden state |
| Protocol error, invalid envelope, repeated sequence | Stop and clear sensitive state |
| Explicit stop | Cancel timers, close socket, clear token/snapshot and ignore late callbacks |

Retries wait 30, 60, then at most 120 seconds, with non-negative jitter up to 20% (capped at 120).
Five consecutive retries are allowed; then explicit restart/login is required. A valid snapshot
resets that failure count. No parallel connections or refresh requests are created. Browser
timer throttling may lengthen waits; this is not a hard real-time scheduling guarantee. An open
but silent stream becomes stale without automatically creating another connection.

Only the current snapshot is retained by the client itself. Clearing drops its references; it
does not erase copies retained by consumers or zeroize JavaScript strings. Stale means the server query is overdue or
disconnected, not that the vehicle is unsafe or its measurements were current. Consumers must
preserve the source timestamps and limitations. Envelope checks do not replace domain schemas.

## Verification

Run `node --test tests/browser/stream-client.test.mjs` (Node 20+). Fourteen deterministic tests use
fake sockets and a virtual clock, so exponential waits and ten-frame session completion consume
milliseconds rather than minutes. The CI fast gates run these tests in addition to Python checks.

The optional `tools/run_integration_tests.ps1 -DashboardBrowserAcceptance` now runs eight real
browser checks. On 2026-09-14 at 08:29:04 UTC, headless Chrome/152.0.0.0 on Windows passed the
original five protocol cases plus stale-on-disconnect, reconnect after at least 30 real seconds,
and terminal authentication rejection in this client. The fixture uses zero jitter for a
repeatable minimum-wait check; production defaults retain jitter. A controlled socket close
causes the disconnect, not a real network partition. Long exponential retries, silence expiry
and complete ten-frame sessions are virtual-clock evidence, not full-duration browser evidence.

The page was visually inspected before execution, while displaying `reconnecting` with a stale
retained snapshot, and after all eight checks passed. It then displayed stopped/no retained
snapshot. The isolated browser used `--disable-gpu` and was closed after capture. Report schema
`dashboard-browser-acceptance-v2` remains sanitized and local in `dr-evidence`; screenshots use
the `dashboard-x72-` prefix. No credentials or snapshot payloads appear in these artifacts.

Host samples: CPU 7%/GPU 11% during integration and CPU 37%/GPU 19% during browser reconnection.
API memory in the latter sample was 152.1 MiB. These are samples, not peaks or isolated process
attribution. The GPU-disabled browser setting does not imply zero GPU use by the entire machine.

## Remaining X-7 work

Real end-user login/product UI, deployment TLS/proxy acceptance and AAOS remain pending. This
increment provides client lifecycle behavior and fixture evidence, not final product UI
acceptance. No Android repository, emulator or paid service was added. The browser skills
required real-engine execution, visual inspection and isolated-session cleanup.
