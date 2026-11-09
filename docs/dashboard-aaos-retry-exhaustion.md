# X-7.18 — Actual AAOS retry exhaustion

## Objective and isolation

Validate the production five-retry policy on actual AAOS with unmodified
monotonic timers: 30, 60, 120, 120 and 120 seconds. A real LIVE snapshot precedes
the fault. The loopback fixture then cuts the socket and rejects subsequent
TCP connections before any request reaches the upstream API.

The device deliberately uses a 900-second local budget, longer than the
720-second instrumentation bound. The normal integration JWT still expires
after five minutes; its policy is not extended. This does not confound the
intended transport failure: no retry is forwarded to the server, so it cannot
return an authentication failure. The expected terminal status is STOPPED,
not AUTH_REQUIRED. This fixture is not guidance for normal client token TTLs.

## Pass criteria

| Assertion | Purpose |
|---|---|
| Actual LIVE before cut | Establish a successful session before injecting failure. |
| RECONNECTING with stale indication | Never label retained disconnected data as current. |
| Exactly six TCP accepts | One initial connection plus five retries; no unbounded retry loop. |
| Every retry delay checked on the host | Preserve the 30/60/120/120/120-second policy with one-second observation tolerance. |
| STOPPED between 449 and 540 seconds after LIVE | Distinguish exhaustion from immediate failure or local expiry. |
| Empty token input and absent envelope | Clear credentials and displayed evidence on terminal failure. |
| No restart for 122 seconds after route restoration | Observe beyond the maximum 120-second backoff, with TCP count unchanged. |

The proxy retains at most 16 monotonic accept timestamps, never payloads.
The coordinator requires four exact ordered checkpoints, bounds output and
terminates instrumentation after 720 seconds. Only allowlisted phase names
may be emitted on failure; raw child output and credentials remain suppressed.
The fixture's lifetime forwarding cap remains unchanged; any unexpected new
TCP accept after restoration fails the count check even if not forwarded.

## Reproduction and resource policy

Build the companion Android project first with one Gradle worker, using the
procedure in `dashboard-aaos-network-recovery.md`. Then, with Docker ready:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\run_integration_tests.ps1 -DashboardAaosNetworkAcceptance -DashboardAaosRetryExhaustion -StartAaosEmulator -UseExistingImages
```

Only reuse images when they match current backend source. The expiry and
exhaustion opt-ins are mutually exclusive. Expect about ten minutes of device
execution plus setup and restore verification; most time is waiting for real
backoff. The emulator has one guest core, 2 GiB RAM and software rendering.
Monitor host CPU/GPU, keep compilation sequential, and clean owned resources.
No paid service or new runtime dependency is introduced.

## Automated coverage and remaining gates

Host tests reject missing/extra connections, truncated timestamp history and
every too-short retry interval. The new JVM adapter test starts with populated
evidence, checks all five exact deadlines, cancellation of each discarded
socket, terminal cleanup and rejection of late callbacks from all six sockets.

Actual-device evidence must be recorded separately. This controlled TCP
scenario does not establish radio reliability, capacity or safety compliance.
Normal ten-snapshot completion is the next planned AAOS gate, followed by the
remaining cross-platform/deployment acceptance. English Markdown is maintained;
DOCX is unchanged.

## Evidence — 2026-09-17

Actual API 35 instrumentation passed: exactly six accepted TCP connections,
all five minimum backoff intervals, STOPPED with empty token/evidence, and
122 seconds without a new connection after restoration. The retained local
`dr-evidence/dashboard-aaos-network-exhausted.png` was visually inspected.
The run completed after interactive monitoring was interrupted by account
limits; its successful process result and cleanup were retrieved on resumption.

All 53 host tests and 59 Android JVM tests passed; Ruff/mypy passed. Android
build took 38 seconds with zero lint errors/15 existing warnings. Both integration
tests passed in 19.51 seconds. Restore passed with 87 tables/292 rows in 74.578
seconds. CPU samples ranged 36–79%, GPU 9–17%, with 12.6 GiB free RAM in a
device-stage sample. Monitoring was intermittent and interrupted before the
end, so these are not peak measurements. Changes remain local; no PR/merge.
