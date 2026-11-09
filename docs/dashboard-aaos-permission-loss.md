# X-7.12 — Active-session AAOS permission loss

Status: real-device scenario passed on 2026-09-16.

## Scenario

The disposable host fixture creates a dedicated user and a role containing only
`dashboard:read`. The Android test authenticates with that user's token and waits
for a real LIVE snapshot. Only then does it emit the exact instrumentation
checkpoint `revocation-ready`. The host removes that specific fixture role using
the public identity API. Administrator credentials stay on the host; the Android
test receives only dashboard-reader and no-role fixture tokens.

The Android test waits up to 65 seconds for FORBIDDEN, covering the normal
30-second server reauthorization interval. It checks that the token input is
empty, the accessible UI tree contains no snapshot envelope and FORBIDDEN is
still shown after a short observation. A local screenshot records the denied
state. This is not instantaneous push revocation or proof of whole-process
memory erasure. Unit session/lifecycle tests provide complementary state evidence.

## Coordination safeguards and tests

The host reacts only to one exact checkpoint after device LIVE. It does not
infer readiness from a delay, launch, or connection attempt. Missing or duplicate
checkpoints fail; duplicate output cannot repeat the role mutation. Child output
is bounded to 65,536 characters with a bounded queue and a 180-second deadline.
The child is terminated on timeout, callback failure or output overflow. Raw
instrumentation output and credential-bearing arguments are never printed.

Seven Python tests verify exact/missing/duplicate checkpoint handling, timeout
without output disclosure, output bounds, role-removal failure and child failure.
The fixture uses only the local disposable backend and changes no production
roles, server refresh interval, authorization policy, or paid infrastructure.

## Reproduction and remaining gates

Use the sequential commands in `dashboard-aaos-acceptance.md`; this scenario is
included in the same opt-in AAOS runner. Compile with the emulator stopped, then
start the backend and only then the single-core/2 GiB emulator. Reusing images
requires a known current backend build.

Inactive-user behavior, server-side token expiry, local expiry, real reconnect/
staleness, ten-snapshot completion and trusted-proxy deployment acceptance remain
separate gates. Passing this scenario must not mark those gates complete.

## Verification evidence

AAOS API 35, driver user 10: the live checkpoint was observed, the host confirmed
successful removal of the fixture's only role, and the instrumentation completed
with PASS after observing FORBIDDEN and cleanup. The inspected local screenshot
`dr-evidence/dashboard-aaos-revoked.png` shows FORBIDDEN / STALE / NOT LIVE, an
empty credential input and no displayed envelope. Previous basic smoke and
initial no-role denial scenarios also passed in this execution.

Seven coordinator tests passed; Ruff and strict mypy passed on the harness/tests.
Android debug/test APKs and lint completed in 27 seconds with one Gradle worker;
57 JVM tests remain passing, with zero lint errors/15 existing warnings. Both
backend integration tests passed in 19.93 seconds. Sampled CPU was 27–57%, GPU
10–21%; during the active-device stage 10.5 GiB RAM remained free. These samples
are not peak measurements or a capacity guarantee. DOCX is unchanged.

The PostgreSQL restore drill also passed: 87 tables, 296 rows, migration
`0064_ai_evidence_projections`, 77.594 seconds. Final coordinator recheck passed
all seven tests in 0.54 seconds. The owned emulator and temporary integration
containers were confirmed absent after cleanup; final sampled CPU was 33%.
Changes remain local and uncommitted; no pull request or merge was performed.
