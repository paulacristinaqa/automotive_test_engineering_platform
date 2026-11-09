# X-7.13 — AAOS local session expiration

Status: real-device scenario passed on 2026-09-16.

## Purpose and scenario

This scenario isolates the Android client's conservative local session timer from
server-side JWT expiration. It deliberately enters a shorter local lifetime of
30 seconds for a still-valid disposable reader token. The existing client subtracts
a ten-second safety margin; no production timer, token lifetime or server policy
is changed. This is a test budget, not a claim about the token's actual remaining life.

The device must first show LIVE, then AUTH_REQUIRED after the local timer fires.
The test rejects an immediate authorization failure as expiration by checking at
least 19 seconds elapsed from the connection action. It verifies an empty token
field and no snapshot envelope in the accessible UI tree. AUTH_REQUIRED is then
observed repeatedly for another 32 seconds, beyond the first 30-second reconnect
backoff. Only an explicit subsequent connection may restart the session.

After this observation, the host calls `/api/v1/auth/me` with the exact same token
and requires HTTP 200, an active account and `dashboard:read`. This distinguishes
local expiration from server rejection. The existing permission-loss scenario
runs afterward, also demonstrating explicit reconnection with the still-valid token.

## Coordination and boundaries

An exact `local-expired` checkpoint triggers the host probe once. Missing,
duplicate, unexpected or out-of-order checkpoints fail. Role removal cannot
occur before the expiry probe passes. Four additional Python tests cover correct
ordering, missing checkpoint, duplicate checkpoint and failed server validation;
the coordinator suite now contains eleven tests.

The original local-expiry run used a 180-second subprocess deadline; X-7.14
extends the combined scenario to 480 seconds for natural server JWT expiration.
Bounded output and host-only administrator credentials remain unchanged.
Screenshots are local ignored evidence, not logs of
tokens or raw instrumentation output. Interface cleanup is not proof of complete
process-memory erasure. No new paid service or runtime dependency is introduced.

Server-side JWT expiration, expiration during real network retry, inactive-user
handling, real reconnect/staleness and ten-snapshot normal completion remain
separate device gates. Do not infer their acceptance from this local-timer test.
Reproduction follows the sequential procedure in `dashboard-aaos-acceptance.md`.

## Evidence

The API 35 driver-user scenario passed: LIVE transitioned to AUTH_REQUIRED,
the form/evidence cleared, the 32-second observation completed without automatic
restart, and the host confirmed HTTP 200 with the same still-authorized token.
The following explicit connection and permission-loss scenario also passed.
The inspected local screenshot is `dr-evidence/dashboard-aaos-expired.png`.

Eleven coordinator tests, Ruff/mypy and both integration tests passed (19.70 seconds).
Android build/lint passed in 28 seconds with 57 passing JVM tests and zero lint
errors/15 warnings. PostgreSQL restore passed: 87 tables/296 rows, 75.14 seconds.
CPU samples were 25–67%, with 11 GiB RAM free during one device-stage sample;
these are not peak measurements. The temporary stack and emulator were shut down.
DOCX is unchanged; changes remain uncommitted.
