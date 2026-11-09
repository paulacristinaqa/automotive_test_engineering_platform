# X-7.14 — AAOS server JWT expiration

Status: real-device scenario passed on 2026-09-16.

A separate disposable user receives a dashboard-reader role and a normal access
token issued by `/api/v1/auth/token`. The fixture requires the existing integration
policy of 300 seconds. No clock is changed, no JWT is forged and no server expiry
setting is reduced. Earlier scenarios consume part of that lifetime before this
client connects, so expiry precedes the normal ten-snapshot session limit.

The device enters a deliberately longer 600-second local budget and must receive
a real LIVE snapshot. It then waits for AUTH_REQUIRED from server rejection,
before the client's 590-second conservative deadline. The token input and visible
envelope must clear. The host requires at least 298 seconds since token issuance,
checks that the exact token now receives HTTP 401 / `invalid_credentials`, and
uses a fresh administrator login to confirm the account is still active with
`dashboard:read`. Thus role loss or deactivation cannot silently substitute for
the intended expiration scenario.

The expanded instrumentation run has a bounded 480-second deadline to cover the
unaltered five-minute token lifetime. Output/queue bounds remain unchanged. Exact
ordered checkpoints and positive completion are required; missing, early,
duplicate or failed server-expiry verification cannot pass. The coordinator suite
contains sixteen tests after adding these cases.

The deliberately long client budget is an adversarial test input, not recommended
operator behavior. No administrator token is sent to Android. No new service,
dependency or paid infrastructure is required. Local evidence is retained only
after successful instrumentation. Interface cleanup is not memory-erasure proof.

Inactive-user handling, real network partitions/reconnect/staleness, expiry during
retry and ten-snapshot completion remain separate gates. Follow the sequential
execution procedure in `dashboard-aaos-acceptance.md`.

## Evidence

The combined API 35 driver-user run passed. The final device state was
AUTH_REQUIRED with the 600-second local budget still unexpired, empty token input
and no displayed snapshot. The inspected local screenshot is
`dr-evidence/dashboard-aaos-server-expired.png`. The host confirmed rejection of
the original JWT and separately confirmed an active, dashboard-authorized account.
The earlier local-expiry, initial-denial and active-role-loss scenarios also passed.

Sixteen coordinator tests and Ruff/strict mypy passed. Android build/lint passed
in 41 seconds, retaining 57 JVM tests and zero lint errors/15 warnings. Two backend
integration tests passed in 24.86 seconds. Sampled CPU was 37–70%, GPU 6–16%, with
10.1 GiB RAM free in one device-stage sample; these are not measured peaks.
No paid infrastructure or production configuration was changed. DOCX is unchanged.

PostgreSQL restore passed with 87 tables/303 rows in 85.218 seconds. Final
coordinator recheck passed all sixteen tests in 0.91 seconds. Cleanup was verified:
no owned emulator or `atep-integration` containers remained; final sampled CPU
was 34%. Changes remain local and uncommitted; no PR or merge was performed.
