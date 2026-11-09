# X-7.17 — Local expiry during AAOS reconnect backoff

## Objective

Verify that an expired local session cannot reopen a dashboard connection when
the network recovers. This is independent of server JWT expiration: the host
checks that the same JWT still authenticates an active dashboard reader.

## Scenario

1. A disposable reader connects through the X-7.16 loopback TCP fixture and
   reaches actual AAOS LIVE.
2. The host cuts that connection. Android must visibly reach RECONNECTING with
   an explicit stale indicator before expiry can be accepted.
3. The configured 40-second local lifetime uses the existing conservative
   ten-second margin. AUTH_REQUIRED must occur no earlier than 29 seconds
   after Connect, with an empty credential field and no displayed envelope.
4. The host independently calls `/api/v1/auth/me` with the exact JWT and checks
   an active account with `dashboard:read`, then restores forwarding.
5. Android remains AUTH_REQUIRED for another 32 seconds. The proxy must still
   have accepted exactly one connection: no automatic restart after recovery.

The instrumented sequence has a 180-second bound. All four ordered checkpoints
are mandatory. No credentials or raw instrumentation output are printed;
only allowlisted diagnostic phase names can be emitted. No production clock,
JWT policy, retry delay or application behavior is modified.

## Tests and reproduction

The JVM boundary test puts local expiry exactly at the scheduled retry instant:
expiry must win, cancel the old transport, clear evidence and ignore late
snapshot/failure callbacks and later polls. Five coordinator cases verify the
complete sequence and omission of each required checkpoint.

Build Android first with one Gradle worker, as documented in
`dashboard-aaos-network-recovery.md`. Then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\run_integration_tests.ps1 -DashboardAaosNetworkAcceptance -DashboardAaosRetryExpiry -StartAaosEmulator -UseExistingImages
```

Omit `-UseExistingImages` unless local images match the current backend source.
The emulator uses one guest core, 2 GiB RAM and software rendering. Owned test
resources are cleaned automatically. No paid API or cloud service is required.

## Boundaries

This increment covers local expiry during a real reconnect wait, not all
network failures. Actual-device five-retry exhaustion is the next separate
increment: production delays total at least 450 seconds. Normal ten-snapshot
completion and trusted-proxy deployment acceptance remain open. Unit tests
do not replace those device/deployment gates. DOCX is unchanged.

## Evidence — 2026-09-17

The real API 35 scenario passed all four ordered checkpoints. The host verified
HTTP 200 for the exact JWT with active status and dashboard permission after
local expiry, restored the route, and confirmed only one accepted connection
after the 32-second terminal-state observation. The inspected screenshot
`dr-evidence/dashboard-aaos-network-retry-expired.png` shows AUTH_REQUIRED,
an empty token input and no displayed envelope.

All 36 coordinator/proxy tests passed. Android build completed in 37 seconds,
with 58 passing JVM tests, zero lint errors and 15 existing lint warnings.
Both backend integration tests passed in 19.79 seconds. Ruff, strict mypy,
PowerShell parsing and both repository diff checks passed. Sampled CPU was
53–67%, GPU 6–10%; device-stage free RAM was 12.9 GiB. These are intermittent
observations, not measured peaks or resource/capacity guarantees.

The restore drill passed with 87 tables/292 rows in 76.125 seconds. All 36
targeted tests passed again in 3.86 seconds, with Ruff/mypy and diff checks
passing. Owned integration containers and emulator were confirmed absent;
final sampled CPU was 34%, GPU 8%. Changes remain local and uncommitted;
no PR or merge was performed in this increment.
