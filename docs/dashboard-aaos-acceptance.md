# X-7.11 — Sequential AAOS device acceptance

Status: basic device smoke passed on 2026-09-16. The broader AAOS gate remains
in progress; real network/reconnect scenarios remain required.
Active permission loss passed in X-7.12, local expiry in X-7.13 and natural server
JWT expiry in X-7.14, and active-user deactivation in X-7.15. See their dedicated acceptance records.

## Local execution order

1. In the companion `CarSystemUI_android/showcase` directory, build with one
   Gradle worker and no parallel tasks while the emulator is stopped:
   `gradlew.bat --no-daemon --max-workers=1 --no-parallel :app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleDebugAndroidTest`.
2. In ATEP, run `tools/run_integration_tests.ps1 -DashboardAaosAcceptance -StartAaosEmulator`.
   This builds/starts the disposable backend and runs integration tests first.
   Only then does it start `ATEP_AAOS_API35`, using one guest core, 2048 MiB RAM,
   software graphics and no visible emulator window.
3. The smoke runner installs the APKs, selects the current AAOS user, obtains a
   disposable fixture token and invokes the instrumentation runner. It emits only
   allowlisted failure-stage identifiers, never raw command output or credentials.
4. Cleanup stops the owned emulator and removes only the temporary integration
   stack. The usual PostgreSQL restore drill follows successful AAOS acceptance.

`-UseExistingImages` skips builds and pulls. Use it only after explicitly building
the current backend source; it is not proof that an arbitrary cached image is current.
It was introduced after a Docker Hub TLS handshake timeout with images already local.

## Scenario and evidence boundaries

| Scenario | Objective | Status |
|---|---|---|
| Native LIVE snapshot | Verify the real Android client connects to the local backend | Instrumented PASS and local screenshot |
| Token form clearing | Verify the editable credential field is empty after connection | Instrumented PASS; nonempty set of editable nodes required |
| Background and return | Stop the session, clear displayed evidence, require explicit reconnect | Instrumented PASS; STOPPED and no envelope in the accessible tree |
| Initial no-role denial | Reject a valid token for a disposable user without dashboard permission | Instrumented PASS: FORBIDDEN, empty token field and no accessible envelope |
| Permission loss | Deny subsequent snapshots at the next authorization check | X-7.12 instrumented PASS after host removed the role following device LIVE |
| Inactive user | Deny subsequent snapshots after account deactivation | X-7.15 instrumented PASS before token/local expiry, retained role and same-token HTTP 401 |
| Local expiry | Clear the session without automatic restart while the JWT is still valid | X-7.13 instrumented PASS and host HTTP 200 probe |
| Server JWT expiry | Reject the naturally expired JWT before the longer local deadline | X-7.14 instrumented PASS, exact-token HTTP 401 and authorized-account probe |
| Reconnect / stale state | Verify real client behavior under network failure | Pending |
| Ten-snapshot completion | Verify bounded normal completion without automatic restart | Pending |

The first real run reached LIVE and returned to STOPPED, but `startActivitySync`
could wait indefinitely when returning to an existing activity. The runner now
distinguishes initial launch from activity reuse. A separate startup probe fix
handles expected adb-not-connected errors during Windows PowerShell boot polling.

Resource samples during sequential execution ranged from 33–82% host CPU; an
active-client sample had about 11 GiB RAM free. These are intermittent samples,
not peak measurements or a capacity benchmark. No paid infrastructure is needed.
Screenshots remain in ignored local `dr-evidence`; no token-containing process
arguments or raw instrumentation output are retained as evidence.

The completed basic run also passed both backend integration tests and the
PostgreSQL restore drill (87 tables, 283 rows, migration
`0064_ai_evidence_projections`; restore duration 77.578 seconds). This fixture is
not a capacity benchmark. The APK was built with Gradle 8.13/Java 21 for the
API 35 AAOS emulator, driver user 10. The executable source is currently uncommitted
on the companion `codex/x711-aaos-smoke` branch. DOCX has not been regenerated.

The final expanded run repeated the basic smoke and passed initial no-role denial.
Both integration tests passed in 19.25 seconds; the restore drill passed with
87 tables/287 rows in 77.906 seconds. Android verification retained 57 passing
JVM tests and lint with zero errors/15 warnings; Python Ruff/mypy and PowerShell
syntax checks passed. The emulator and all `atep-integration` containers were
confirmed absent after cleanup. No commit, pull request or merge was made in this run.
