# X-7.16 — AAOS transport stall and recovery

## Scope and mechanism

This opt-in scenario connects the real API 35 Android client to the disposable
ATEP API through a loopback-only TCP fault fixture. It does not change Wi-Fi,
firewall rules, production authentication policy or the application's retry
algorithm. No paid service or new runtime dependency is required.

The fixture binds `127.0.0.1:18001` and forwards only to
`127.0.0.1:18000`. The emulator uses `http://10.0.2.2:18001` with the existing
explicit debug HTTP opt-in. A disposable reader has only `dashboard:read`;
the administrator credential stays on the host. Wire data is neither logged
nor persisted. Only the first four accepted connections can be forwarded,
uses bounded socket operations, and closes its listener and peers on exit.

## Assertions

| Phase | Objective and pass criterion |
|---|---|
| Initial LIVE | Receive a real versioned snapshot before injecting a fault. |
| Forwarding paused | Reach STALE after the existing freshness deadline; retain the exact previous preview and mark it STALE / NOT LIVE. |
| Connection cut | Reach RECONNECTING while the retained preview remains explicitly stale. |
| Forwarding restored | Reconnect after the existing 30-second backoff, not an immediate retry loop. |
| Fresh LIVE | Receive a different versioned preview, show CURRENT SERVER QUERY, and retain an empty credential input. |

Ordered instrumentation checkpoints coordinate the host and device. The host
also requires exactly two accepted connections and at least 29 seconds from
cut to recovered checkpoint, allowing scheduling tolerance around the
30-second retry policy. The device independently checks elapsed time. The
instrumentation is bounded to 180 seconds; output retains the existing queue,
chunk and total-size limits. Raw child output and credentials are not printed.

## Reproduction

Compile the companion Android project first, without an emulator running:

```powershell
cd C:\projetos\CarSystemUI_android\showcase
.\gradlew.bat --no-daemon --max-workers=1 --no-parallel :app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleDebugAndroidTest
```

Then run from ATEP with Docker Desktop ready:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\run_integration_tests.ps1 -DashboardAaosNetworkAcceptance -StartAaosEmulator -UseExistingImages
```

Use `-UseExistingImages` only when the images already match the backend source;
otherwise omit it. Authentication and network scenarios are separate opt-ins
to avoid repeatedly running the longer expiry suite. The runner starts a
headless software-rendered emulator with one guest core and 2 GiB RAM, then
cleans owned resources. Monitor host CPU/GPU separately; these settings are
not a guarantee of maximum host utilization.

## Evidence boundary

Automated fixture/coordinator tests cover ordered signals, missing/duplicate/
out-of-order signals, forwarding, pause/resume, cut/reconnect, broken-route
rejection, the connection budget and cleanup. All 31 tests passed, as did
Ruff and strict mypy. Android compilation completed in 1m14s with 57 passing
JVM tests, zero lint errors and 15 existing lint warnings.

On 2026-09-17, the instrumented API 35 scenario passed every ordered checkpoint:
LIVE, unchanged stale evidence, RECONNECTING, and fresh LIVE after one delayed
reconnect. The host confirmed exactly two accepted connections. Inspected local
screenshots `dr-evidence/dashboard-aaos-network-stale.png` and
`dr-evidence/dashboard-aaos-network-reconnected.png` show the corresponding
status, an empty token input and different server query timestamps.

The successful run passed both backend integration tests in 19.17 seconds.
An earlier attempt failed before the first LIVE checkpoint; its exact cause
was not established because detailed child output was intentionally suppressed.
Safe, allowlisted phase diagnostics were added before repeating the scenario.
The repeat passed without changing production behavior or relaxing assertions;
this is one successful device run, not a claim of repeated-run stability.

CPU samples across compilation and device attempts ranged from 20% to 63%,
GPU from 7% to 12%; device-stage free RAM samples included 10.4 and 12.1 GiB.
These are intermittent observations, not measured peaks or capacity guarantees.

The PostgreSQL restore drill passed with 87 tables and 292 rows in 77.0 seconds
at migration `0064_ai_evidence_projections`. All 31 fixture/coordinator tests
passed again in 3.71 seconds; Ruff, mypy and diff checks passed. The owned
emulator and integration containers were confirmed absent after cleanup.
Final sampled CPU was 31%, GPU 12%. Changes remain local and uncommitted;
no PR or merge was performed. English Markdown is current; DOCX is unchanged.

This is a controlled TCP stall and interruption, not a physical radio outage,
arbitrary network partition, capacity benchmark or vehicle-safety claim.
Expiry during retry, retry exhaustion and normal ten-snapshot completion
remain separate acceptance cases. Broader accessibility and trusted-proxy
deployment gates remain open.
