# ATEP Volume X Dashboard Engineering Workbook

Version 0.7.10 records the Android engineering panel and session ownership.

## X-7.10 — Android presentation and session owner

Added a companion Compose panel with transient masked token input, remaining
lifetime, view selection and explicit connect/clear. Session generations reject
queued obsolete callbacks. Activity onStop clears data and closes the transport;
return and rotation require reconnection. Four owner tests cover cleanup and
replacement. `dashboard-android-panel.md` records scope and remaining device gates.
This is an engineering preview, not end-user login or road-use certification.
No new dependencies/paid services; DOCX unchanged.
Companion validation: 57 JVM tests passed; lint zero errors/15 existing warnings;
debug APK passed in 1m 2s. No emulator or visual/device acceptance was run.

## X-7.9 — Native socket and envelope adapter

Connected the companion request/lifecycle code to OkHttp, with synchronized events,
monotonic polling, generation-based socket cancellation and conservative local token
expiry. Added bounded envelope/version/view/freshness checks and nine JVM tests.
`dashboard-native-transport.md` records scope and limitations. These are fake-transport
tests, not live server or device acceptance. Android presentation is still pending.
No new production dependencies or paid services; DOCX unchanged.
Companion validation: 53 JVM tests passed; lint and debug APK build passed in
52 seconds. A JUnit test-signature issue was corrected during verification.
Final timer/dependency adjustments passed build/lint in 1m 4s, with zero errors
and 15 existing warnings; fixed-delay polling avoids suspension catch-up bursts.

## X-7.8 — Native lifecycle state machine

Added virtual-time companion tests for a deterministic connection lifecycle:
stale data, bounded retries, obsolete callbacks, authorization cleanup, normal
completion and initial timeout. `dashboard-native-lifecycle.md` records scope.
The engine holds no credentials and opens no sockets; the real adapter, envelope
parser, UI and device evidence remain pending. DOCX remains unchanged.
Companion evidence: 44 tests passed, lint zero errors/15 warnings, debug APK build
passed in 56 seconds. Virtual-time tests required no emulator or active network.

## X-7.7 — Native Android request prerequisite

The companion showcase is consolidated into main. A dedicated dashboard request
builder now defines three native routes, header-only authentication, absent Origin,
HTTPS by default and explicit loopback/emulator-host HTTP opt-in. Five focused JVM
tests cover positive, negative and boundary behavior without starting an emulator.
`dashboard-aaos-prerequisites.md` records scope and the remaining ordered gates.
This is not a connected dashboard, device acceptance or a production credential flow.
No new service/dependency or paid infrastructure; DOCX remains unchanged.

Local companion verification: 37 tests passed, lint had zero errors and 15 warnings,
and the debug APK built successfully. Full cross-platform/deployment acceptance remains pending.

## X-7.6 — Responsive presentation and additional keyboard access

Added a skip-to-main link, explicit atomic live-region semantics, associated credential guidance
and wrapping/minimum-width CSS improvements. The optional presentation runner checks login and
live operations at 320/768/1280 pixels and at 200% root text on the narrow viewport, plus skip-link,
native validation and logout-focus behavior. All browser assertions passed and eight screenshots
were inspected using the browser skills. Inspection identified native-selector abbreviation and
word breaks at the most constrained size; these are recorded, not hidden behind a conformance claim.
`dashboard-responsive-accessibility.md` lists objectives, resource samples, reproduction and gaps.
Docker integration passed both tests in 19.71 seconds. No paid services or emulator were introduced.
English Markdown is current; DOCX remains unchanged. AAOS/deployment gates remain pending.

## X-7.5 — Real-shell lifecycle and keyboard acceptance

Extended the optional Windows browser runner with tab traversal, Enter submission, focus checks,
live role removal, controlled socket disconnect/reconnect and real-time local expiration.
The initial two-minute test configuration was rejected by the existing five-minute minimum;
the experiment was removed, preserving authentication policy and using real waiting instead.
`dashboard-shell-lifecycle.md` records test objectives, instrumentation boundaries and execution
status. No production client hooks, dependencies or paid services are introduced. Browser skills
are used for real-page inspection and isolated-browser cleanup. DOCX remains unchanged.
All added browser scenarios passed on 2026-09-14, including a minimum 30-second reconnect and
real local expiry of the existing five-minute profile. Visual inspection confirmed stale-data and
expired-session states. Local checks passed: 597 Python tests, 28 Node tests, Ruff and mypy;
Docker integration passed both tests in 19.00 seconds. Responsive and broader accessibility
verification remain next; neither complete accessibility conformance nor AAOS acceptance is claimed.

## X-7.4 — Same-origin login/logout shell

Implemented opt-in packaged assets, restrictive headers, accessible form/status markup and
text-only aggregate rendering. Password fields are cleared on submission; login, local cleanup,
remote logout and no-role rejection use the existing identity/stream contracts.
`dashboard-login-ui.md` records configuration, test objectives, resource samples and limitations.
Browser verification skills required real page inspection; inspection exposed and guided correction
of a pending-access message that remained after a successful snapshot. The Windows automation's
initial output-capture hang was corrected without changing authentication policy.
Local verification: 597 Python tests and 28 Node tests passed; Ruff and mypy passed. Real-browser
login/logout/no-role checks passed. Further shell lifecycle, AAOS and deployment acceptance remain
planned; this is an engineering JSON viewer, not the final KPI interface. No paid services added.
English Markdown is current; DOCX snapshots remain unchanged.

## X-7.3 — In-memory login/session foundation

Added a same-origin REST session controller for the existing stream client. Authentication is
separate from snapshot authorization. Requests and token contracts are bounded; late responses
cannot resurrect disposed sessions. Local logout precedes remote revocation, which may remain
unconfirmed offline. `dashboard-client-session.md` records design, integration obligations,
test objectives and evidence. No storage, automatic refresh, CORS expansion or paid service.
Local regression: 594 Python and 28 Node tests passed; Ruff and mypy passed. New client tests use virtual
clocks rather than load generation. Login UI, real end-user acceptance and AAOS remain pending.
Markdown is current; DOCX snapshots are unchanged.

## X-7.2 — Reconnect and stale snapshot lifecycle

Implemented a reusable, dependency-free browser stream module with private in-memory credentials,
bounded retry, stale snapshot indication, terminal permission/authentication handling and timer
cleanup. The same module is served by the acceptance fixture. Virtual-clock tests keep long
retry/session scenarios lightweight; CI now includes the Node client tests.

Eight real Chromium fixture checks passed at 2026-09-14 08:29:04 UTC, including a controlled
disconnect, visible stale retained snapshot, reconnect after 30 real seconds and auth-stop.
`dashboard-client-lifecycle.md` records design, test objectives, resource samples and limitations.
Browser skills guided actual page inspection at the initial, reconnecting and completed states.
The browser was closed. Real product login/UI, AAOS and deployment acceptance remain pending.
Verification: 594 Python tests, 14 Node client tests and both integration tests passed; Ruff and
mypy passed. Integration took 19.02 seconds; the restore drill passed and temporary services
were removed. Browser evidence is local, while CI runs the deterministic Node suite.
Markdown is current; DOCX snapshots are unchanged. No paid infrastructure was introduced.

## X-7.1 — Real browser protocol acceptance

Added an optional loopback-only acceptance fixture and Windows runner switch. Real headless Chrome
passed five sequential scenarios on 2026-09-14: snapshot, invalid token, missing-auth timeout,
read-only command rejection and native Origin denial. `dashboard-browser-acceptance.md` records
browser/tool versions, reproduction, resource samples and limitations. The browser automation
skills required actual page inspection and isolated-session cleanup, both performed.

The regular integration suite passed both tests in 19.37 seconds and the restore drill passed.
Final fast verification: 594 tests passed, two integration tests deselected; Ruff and mypy passed.
Docker services and the isolated browser were closed. This fixture uses a disposable seeded token;
end-user login, client reconnect/staleness, AAOS and deployment acceptance remain pending.
Markdown is current; DOCX snapshots are unchanged. No paid services or emulator were added.

## X-6.7 — Opt-in browser authentication

Added a separate browser stream without changing the native header contract. An exact-Origin
allowlist defaults to empty. Accepted clients must send a bounded versioned token frame within
five seconds; JWT and live RBAC checks gate all snapshot work. One shared runner preserves quota,
capacity, refresh, timeout, read-only and revocation semantics for both transports.

The architecture decision, protocol, deployment constraints and primary design reference are
recorded in `dashboard-browser-authentication.md`. Tokens are not placed in URLs or cookies;
application errors never echo frames. Operators must disable protocol frame logging and configure
ingress limits. No new service, persistence layer, paid infrastructure or GPU workload was added.

Local verification: 592 fast tests passed, two integration tests deselected; Ruff and mypy passed.
Both Docker integration tests passed in 19.31 seconds; the restore drill passed and disposable
services were removed. The resource sample was collected after cleanup (host CPU 16%, GPU 15%),
so it is not evidence of test-time utilization or peaks. No GPU workload was introduced.
Markdown is current; DOCX snapshots are not regenerated. X-6 backend implementation is complete within the documented lab scope;
X-7 must still validate real browser/AAOS clients and deployment conditions.

## X-6.6 — Native transport boundary and Redis integration

The native dashboard stream now rejects Origin-bearing handshakes before any downstream work.
This makes the unsupported browser boundary explicit, including empty/null/same-origin values.
No JWT, RBAC or quota check is bypassed by omitting Origin. This is not a browser login solution.

Unit tests verify no admission, authentication, export or slot consumption on Origin denial.
Real WebSocket integration tests admin-token requests with browser/null Origin against HTTP 403.
A dedicated Redis integration alternates independent connection pools through the production
30-attempt budget and checks rejection, TTL and recovery. A random test key isolates cleanup and
accelerated expiry from user counters. No parallel load, production-policy change or paid service
is involved. Test Redis is exposed on loopback only; application deployment settings are unchanged.

Verification: 563 fast tests passed, two integration tests deselected; Ruff and mypy passed.
Both Docker integration tests passed in 20.01 seconds; the restore drill passed and disposable
services were removed. Resource sample: host CPU 49%, GPU 9%, API container CPU 28.07% and RAM
149.1 MiB. These are samples, not peaks; host usage includes other applications. No ATEP GPU
workload was introduced.
The Markdown workbook is updated; existing DOCX snapshots remain unchanged.

## X-6.5 — Handshake admission hardening

The connection slot now covers admission and authentication, not only accepted streams.
A dedicated Redis fixed-window policy allows 30 handshake attempts per transport peer per
60 seconds across workers sharing Redis. It applies independently of the HTTP limiter switch.
Admission precedes database authentication; quota exhaustion or Redis failure denies entry.
The counter uses a SHA-256 peer digest, never credentials or raw forwarding headers. This is
pseudonymization, not anonymity. NAT clients share a budget; trusted proxy configuration must
prevent spoofed transport addresses. Sixteen simultaneous slots remain a per-worker limit.

Tests cover peer identity, missing peer fallback, quota exhaustion, unavailable Redis,
denial before authentication, and capacity rejection without downstream work. Existing tests
cover live permission rechecks, revocation, bounded sends, refresh and slot cleanup.
Local verification: 560 tests passed, one integration test deselected; Ruff and mypy passed.
The separate Docker integration scenario passed (18.78 seconds), followed by a successful restore
drill and temporary-service cleanup. Resource samples: host CPU 19%, GPU 6%, RabbitMQ 257.66%
(approximately 2.58 logical cores). Samples are not peaks and host usage is not wholly attributable
to ATEP. No GPU workload or paid infrastructure was introduced.
See `dashboard-acceptance.md` for X-7 gates and deliberately unsupported browser authentication.
The Markdown workbook is current; existing DOCX snapshots are not regenerated by this increment.

## Scope and architecture

The dashboard is a read-only projection over existing ATEP domains. FastAPI publishes a versioned
overview, PostgreSQL performs bounded aggregations, and source services remain authoritative. The
first contract supports KPI cards, charts, heatmaps, and evidence lists without choosing a
frontend framework prematurely.

## Engineering decisions

- Require the dedicated `dashboard:read` permission.
- Use UTC windows from 1 to 720 hours, with a 24-hour default.
- Limit recent evidence to 50 cards and default to 10.
- Return `null` for undefined rates rather than implying zero performance.
- Include citations but exclude prompts, raw logs, and source context.
- Keep requirement coverage as a documented current snapshot.
- Avoid materialized copies until measured query demand justifies them.
- Produce complete UTC day sequences so chart clients do not invent missing buckets.
- Limit failure observations to 500 characters while preserving evidence references.

## Tests and objectives

- KPI tests verify totals, active executions, percentages, rounding, and evidence mapping.
- Empty-state tests verify truthful undefined-rate behavior.
- OpenAPI tests verify response type and safe query limits.
- Permission tests preserve the stable `dashboard:read` name.
- Full regression tests protect all preceding volumes.
- PostgreSQL integration validates the endpoint and RBAC against the deployed schema.
- Ruff and mypy protect formatting and type contracts.
- Trend tests verify UTC bucketing, zero-activity days, outcome counts, and pass rates.
- Failure tests verify filtering, ordering, pagination, evidence mapping, and truncation.

## Risks and controls

Large time windows can make aggregate queries expensive: overview and operations use at most
30 days, while test-quality trends and failures allow at most 90 days.
Dashboard figures can be misread as certification evidence, so the response contains an explicit
limitation. AI evidence can contain explanatory text, so the service returns only previously
governed dashboard projections and a bounded citation list.

## Cost and resource profile

X-1 and X-2 reuse FastAPI and PostgreSQL, perform no external network call, and require no paid
API, cloud account, model, or GPU. Tests are CPU-light and use small deterministic fixtures.

## X-3 — Operational views (2026-09-11)

The operations API adds read-only cross-domain summaries for vehicles, ECUs, CAN and
diagnostics. FastAPI validates the bounded UTC activity window, the existing permission
dependency enforces `dashboard:read`, and SQLAlchemy performs PostgreSQL aggregates.
No migration, external provider, GPU workload or paid infrastructure is introduced.

Design decisions:

- Current inventory and stored DTC distributions are separate from activity history.
- Each activity query has both lower and upper timestamp bounds.
- Independent scalar subqueries prevent duplicate counts from cross-domain joins.
- Only aggregate columns are selected: no secrets or command payloads are loaded.
- Explicit limitations distinguish stored evidence from live health and safety certification.
- Sequential reads are not presented as an atomic vehicle snapshot.

Tests and objectives:

- Populated/empty aggregate tests verify mappings and zero-activity behavior.
- OpenAPI tests verify time limits and exclusion of raw payload fields.
- Integration compares vehicle, ECU and network totals with database counts.
- Integration checks authorized access, forbidden access and invalid time windows.
- Regression: 532 tests passed; Ruff passed; mypy passed for src and tests.
- Docker integration: 1 end-to-end test passed; PostgreSQL backup/restore drill passed.
- Resource sample: GPU 7%; RabbitMQ approximately 225% container CPU (2.25 cores).
  Windows CPU counters were unavailable due to permissions. Samples are not peak measurements.

The existing DOCX edition remains version 0.2.0 (X-1/X-2); this Markdown workbook is
the current development record for X-3 until the next document export.

## X-4 — EV, charging, thermal and ADAS analytics

The mobility endpoint supplies chart-ready distributions without adding a frontend framework.
Six metric summaries expose units and population sizes. Seven sorted state/outcome groups
preserve the terminology of the source services. Current component records are distinct from
time-windowed scenario executions and planning evaluations.

Engineering decisions:

- Reuse FastAPI, Pydantic, SQLAlchemy and PostgreSQL; no new dependencies or migrations.
- Compute unweighted per-component statistics in SQL, without loading raw simulation payloads.
- Use explicit UTC lower and upper boundaries only on activity data.
- Return null numeric statistics for absent components; never infer that missing data is healthy.
- Avoid fleet-wide thermal alarm thresholds: source models own operating-state decisions.
- Keep queries sequential to avoid concurrent session use; do not claim snapshot consistency.
- Defer interactive charts and query-cost hardening to their planned increments.

Tests and objectives:

- Populated and empty fixtures verify metric mapping, counts, statistics and missing-data semantics.
- SQL inspection checks both activity boundaries, deterministic group order and absence of joins.
- OpenAPI checks window limits, metric units and population-count fields.
- PostgreSQL integration compares battery statistics against direct database aggregates.
- Integration checks authorized access, forbidden access and invalid query windows.
- Local regression: 535 tests passed; Ruff and mypy passed.
- Docker integration: 1 test passed, including the mobility endpoint and RBAC.
- PostgreSQL backup and isolated restore drill passed; temporary containers were removed.
- Resource samples: Windows CPU 4% during integration; API container CPU 12.14%.
  GPU utilization was 12% after regression. These samples are not peak measurements.

No paid service, model download, GPU computation or AWS account is required. The DOCX edition
remains X-1/X-2; this Markdown workbook records the current development evidence.

## X-5 — Supporting evidence and explicit gaps

Scope decision: repository inspection found diagnostic flashing, audit and generic requirement
coverage, but no OTA lifecycle or formal standards mappings. The user approved delivering an
evidence/gap panel instead of prematurely implementing those future domains.

The read-only evidence-readiness API executes three sorted aggregate queries. Flash and coverage
are current states; audit outcomes use inclusive UTC bounds. Pydantic fixes the assessment to
not_assessed. Versioned gap cards preserve the distinction between existing supporting records
and missing capabilities. No standards clauses, capability level, ASIL or certification is inferred.

Tests and objectives:

- Empty and populated cases prove successful records never erase implementation/assessment gaps.
- SQL tests verify time bounds, deterministic order and exclusion of sensitive detail columns.
- OpenAPI validates the fixed assessment contract and safe query limits.
- Integration compares flash totals against PostgreSQL and verifies HTTP 403/422 behavior.
- Local regression: 538 tests passed; Ruff and mypy passed for src and tests.
- Docker integration: 1 test passed, including aggregate comparison and HTTP 403/422 checks.
- PostgreSQL backup/restore drill passed; temporary test containers were removed.
- Initial Docker Hub TLS timeout occurred before startup; one retry succeeded.
- Resource samples: Windows CPU 27%, GPU 12%; RabbitMQ 181.67% container CPU
  (approximately 1.8 cores) during integration. These are samples, not peak measurements.

No new dependency, migration, paid provider, GPU workload or cloud account is introduced.
The Markdown workbook is current; the DOCX export remains the X-1/X-2 edition.

## X-6.1 — Bounded transient exports

The first X-6 slice reuses existing aggregate view builders and adds a versioned JSON envelope.
Only operations, mobility and evidence-readiness are exportable. Authentication/RBAC and the
global API rate limiter remain active; fixed names prevent user-controlled filesystem paths.
No server file, artifact row, cloud object or export history is created. Client copies are outside
server retention control; source records are not deleted or modified.

Controls: 256 KiB serialized payload ceiling, cooperative 10-second generation timeout, no-store
and nosniff headers. Timeout cancels the awaited builder; it is not a database statement timeout.
The byte check is post-serialization, not a hard memory ceiling. Remaining X-6 hardening must
measure real query costs before claiming performance guarantees.

Tests and objectives:

- Envelope test preserves source limitations, four gap cards and not-assessed semantics.
- Exact-limit and one-byte-over tests validate the byte ceiling and stable error code.
- Blocked-builder test verifies cooperative cancellation and the timeout error.
- OpenAPI restricts view names and time windows.
- Integration checks all three downloads, headers, byte limits, invalid views/windows and RBAC.
- Local regression: 541 passed; Ruff and mypy passed for src and tests.
- Docker integration: 1 end-to-end test passed across all three exports and validation/RBAC cases.
- PostgreSQL backup/restore drill passed; temporary containers were removed afterward.
- Resource samples: Windows CPU 53%, GPU 8%, API container CPU 2.03%; these are not peak
  measurements and total host utilization cannot be attributed solely to this test run.

No new dependencies, paid services or GPU workloads. Markdown remains the current workbook;
the existing DOCX edition remains X-1/X-2.

## X-6.2 — Periodic authenticated snapshots

The existing test-run stream authenticates only on admission. Dashboard streaming instead
revalidates access before queries and again before each send, using existing identity services.
This change is isolated to the dashboard; it does not modify the earlier test-run stream.

Design: reuse bounded aggregate exports; sample no faster than 30 seconds, send at most ten
snapshots, admit sixteen connections per worker, and time out slow sends. Database sessions
are closed between refreshes. Freshness describes server query observation, not vehicle telemetry
age. Periodic sampling intentionally does not promise event replay or instantaneous change delivery.

Tests and objectives:

- Header, inactive-user, permission and expired-token tests verify admission checks.
- Revocation during generation prevents sending the snapshot.
- Freshness and periodic tests verify the frame contract and maximum snapshot count.
- Capacity rejection avoids admitting another connection; all tested termination paths free slots.
- Slow consumers and client commands close safely without recording sensitive exception text.
- Real WebSocket integration checks a governed snapshot and unauthorized handshake rejection.
- Regression: 552 tests passed; Ruff and mypy passed for src and tests.
- Docker integration: 1 end-to-end test passed, including WebSocket snapshot and 403 handshake.
- PostgreSQL backup/restore drill passed; temporary containers were removed.
- Resource samples: host CPU 25%, GPU 14%, RabbitMQ container CPU 281.56%; these are not
  peak measurements and do not establish attribution of all host resource usage.

No cloud provider, paid API, database migration or GPU workload is added. Browser authentication,
distributed handshake limiting and capacity measurements remain explicit later work. The Markdown
workbook is current; DOCX remains the X-1/X-2 edition.

## X-6.3 — Query profile and read-only verification

Inspection identified six individual numeric queries in the mobility view, including repeated
scans of battery and motor tables. Grouping metrics by table reduces numeric queries from six
to three and the full-view query count from thirteen to ten. Status queries and API contracts
remain unchanged. No new cache, index or migration is added without measured justification.

Integration compares the optimized metrics with six independent SQL reference calculations
inside one repeatable-read transaction. PostgreSQL read-only enforcement also covers all three
exports, validating that these paths do not mutate source records. The test uses a local
five-second statement timeout; production timeout behavior is unchanged.

Evidence records sample counts, query totals, export sizes and elapsed times. Timings are one
small-fixture observation, not a latency target, speedup comparison or fleet capacity claim.
The report contains no tokens, record identifiers or raw payloads. CI retention is fourteen days;
local evidence is ignored by Git and manually managed. This differs from production dashboard
snapshots/exports, which have no server-side persistence. Source retention policies are untouched.

Test objectives: preserve numeric/null semantics; prevent extra joins or SELECT regressions;
verify PostgreSQL equivalence and read-only export execution. Final local regression: 553 tests passed;
Ruff and mypy passed. Integration and PostgreSQL restore both passed.

Observed profile: ten SELECTs for the optimized view (previously thirteen), with three numeric
queries instead of six. All six numeric populations were empty in the integration fixture.
The observed full-view time was 24.614 ms; the numeric-only reference was 59.083 ms.
These different workloads and empty populations do not substantiate a populated-fleet speedup.
Export sizes were 867, 1506 and 1893 bytes for operations, mobility and evidence-readiness.
A distinct-population unit case additionally guards field alignment, negative temperatures and
null populations. Populated PostgreSQL performance characterization remains future validation.

No new paid service, GPU workload or production data cleanup is introduced. DOCX remains the
X-1/X-2 edition; Markdown is the current development record.

## X-6.4 — Populated isolated projection fixture

The X-6.3 report revealed empty PostgreSQL metric populations. This increment retains that
case and adds a second profile using temporary component tables on a dedicated connection.
Three batteries, two motor/inverters and one thermal record have known, distinct values.
Temporary setup does not enforce domain constraints and is not an end-to-end vehicle fixture.

Setup copies no public data and inserts only into pg_temp; it commits before starting a new
read-only repeatable-read measurement. Session closure and engine disposal remove connection-local
state. Public component counts are compared before and after. Source records and retention
policies remain unchanged, and no migration or production service configuration is added.

Tests check fixed temporary-only writes, known averages/populations, negative temperature bounds,
source-state distributions, independent SQL equivalence and ten SELECTs. The existing three export
paths also run under read-only measurement. The combined report retains the same 14-day CI policy.
Local regression: 554 tests passed; Ruff and mypy passed. This is not a fleet-scale latency SLA.

Local PostgreSQL evidence: integration passed, with metric populations 3/3/3/2/2/1 and ten
SELECTs. The populated full view took 21.082 ms in one observation; the numeric-only reference
took 11.678 ms (different workload, not a speedup comparison). Public component counts were
unchanged. Resource samples: host CPU 19%, GPU 8%, RabbitMQ 270.91% container CPU; not peaks.
PostgreSQL backup/restore passed, and temporary integration containers were removed.

No paid services, new dependencies or GPU workload. Markdown remains current; DOCX remains X-1/X-2.

## X-7.11 — AAOS acceptance preparation (in progress)

The companion Android project now contains a platform instrumentation smoke runner
and stable Compose test tags. The optional `-DashboardAaosAcceptance` integration
switch connects that runner to the disposable localhost backend; it does not change
the default integration workflow or require a paid service.

Test objectives: establish a native live snapshot, verify that the token field is
cleared, and verify background cleanup with explicit reconnection required. These
objectives are not yet validated on the device. Permission loss, server-side expiry,
network partitions and broader accessibility acceptance remain separate gaps.

Local preparation evidence (2026-09-16): Android debug and instrumentation APKs
built successfully; 57 JVM tests passed with zero failures/errors; the lint task,
Python harness Ruff/mypy checks and PowerShell syntax check passed. The actual AAOS
application rendered on the emulator, but this is not dashboard acceptance.
AAOS uses driver user 10 on this AVD; the harness selects the active Android user
rather than assuming that the system-user accessibility context can inspect it.

The combined emulator/backend attempt was stopped when host CPU remained at 100%,
including after lowering emulator priority and limiting its CPU affinity. No live
dashboard smoke result was obtained. Subsequent checks confirmed no emulator,
matching test-runner process or `atep-integration` containers remained running.
Resume device execution only in a lower-load window. Do not mark X-7.11 accepted
or merge it as verified on the basis of compilation alone. Changes remain uncommitted.
Markdown is the current record; the DOCX workbook has not been regenerated.

Sequential follow-up on 2026-09-16: the basic real-device smoke passed after
correcting first-launch versus resumed-activity synchronization. LIVE snapshot,
token-field clearing and background/return cleanup were verified on AAOS API 35.
Both backend integration tests and the PostgreSQL restore drill passed, and the
temporary stack/emulator were removed. CPU samples during the sequential workload
were 33–82%, not a sustained 100%; these are samples, not measured peaks.
See `dashboard-aaos-acceptance.md` for reproduction and remaining acceptance gaps.
The subsequent initial no-role denial scenario also passed on device: a valid
token from a newly created disposable account without roles produced FORBIDDEN,
an empty token field and no envelope in the accessible tree. This is initial
authorization denial, not loss of permission during an established session.
Real permission loss, expiry, reconnect and normal ten-snapshot completion
remain pending.

Final expanded verification: two integration tests passed (19.25 seconds),
AAOS smoke plus no-role denial passed, and PostgreSQL restore passed
(87 tables/287 rows, 77.906 seconds). Ruff/mypy/PowerShell syntax checks passed;
Android retained 57 passing JVM tests and lint with zero errors/15 warnings.
Owned emulator and disposable containers were confirmed removed. Changes are
saved locally; no commit/PR/merge or DOCX regeneration was performed in this run.

## X-7.12 — Active-session AAOS permission loss

A dedicated disposable user starts with only `dashboard:read`. The Android
instrumentation waits for LIVE, emits an exact checkpoint, and the host then
removes that user's fixture role through the public API. Administrator credentials
are no longer sent to the Android smoke; both permitted sessions use the narrow
dashboard-reader token. No production authorization or refresh settings change.

The real device scenario passed: FORBIDDEN was observed at the next authorization
check, the credential field was empty and the accessible tree contained no snapshot.
The retained local screenshot was inspected. This does not establish instantaneous
revocation, inactive-user acceptance or whole-process memory erasure.

Seven new host coordinator tests cover exact/missing/duplicate checkpoints,
bounded timeout/output, callback failure and child failure. All passed, as did
Ruff/strict mypy. Android build/lint passed in 27 seconds with one worker, retaining
57 passing JVM tests and zero lint errors/15 warnings. Two integration tests
passed in 19.93 seconds. Sampled host CPU was 27–57%, GPU 10–21%; one active-device
sample had 10.5 GiB RAM free. Compilation and emulator execution were sequential.

See `dashboard-aaos-permission-loss.md` for reproduction and evidence boundaries.
The restore drill passed (87 tables/296 rows, 77.594 seconds), and the owned
emulator/temporary containers were confirmed removed. Final sampled CPU was 33%.
Changes remain local and uncommitted; no PR or merge was performed in this increment.
Expiry, inactive-user handling, reconnect/staleness and ten-snapshot completion
remain pending; trusted-proxy acceptance follows the Android gate. No paid service
was added. Markdown is current; DOCX has not been regenerated.

## X-7.13 — AAOS local session expiration

The real device reached LIVE with a 30-second local budget, applied the existing
ten-second safety margin, then reached AUTH_REQUIRED. The token input and visible
evidence cleared, and the state remained terminal over a 32-second observation.
The host confirmed the exact JWT still returned HTTP 200 with dashboard permission.
Explicit reconnection and the following permission-loss scenario also passed.

Eleven coordinator tests and Ruff/mypy passed. Android build/lint passed in
28 seconds with 57 JVM tests retained and zero lint errors/15 warnings. Both
integration tests passed (19.70 seconds); restore passed with 87 tables/296 rows
in 75.14 seconds. Resources were cleaned up. CPU samples were 25–67%, not peak
measurements. See `dashboard-aaos-local-expiry.md`. DOCX is unchanged.

## X-7.14 — Natural server JWT expiration

A distinct disposable reader uses an API-issued five-minute JWT and a longer
600-second local client budget. No clock, JWT signature, production policy or
server token lifetime is modified. Device AUTH_REQUIRED must precede the local
deadline. The host must confirm HTTP 401 for the same token and separately verify
that the account remains active and retains dashboard permission.

The expanded run has a bounded 480-second deadline. Sixteen coordinator tests
cover checkpoint ordering, missing/duplicate signals and failed verification;
Ruff/mypy passed. Android build/lint passed in 41 seconds, retaining 57 JVM tests
and zero lint errors/15 warnings. The real AAOS scenario passed: AUTH_REQUIRED
preceded the local deadline, the input/evidence cleared, and the host confirmed
HTTP 401 for the original token with the account still active and authorized.
The retained screenshot was inspected. Two integration tests passed in
24.86 seconds. CPU samples were 37–70%, GPU 6–16%; one sample retained 10.1 GiB
RAM free. See `dashboard-aaos-server-expiry.md`. No paid service was added.

Final restore passed (87 tables/303 rows, 85.218 seconds); all sixteen coordinator
tests passed again in 0.91 seconds, with Ruff/mypy passing. Owned emulator and
temporary containers were confirmed absent, and final sampled CPU was 34%.
Documentation remains in English Markdown; DOCX is unchanged. Changes are local
and uncommitted; no PR or merge was performed. Next is inactive-user acceptance,
followed by the remaining real network/reconnect and normal-completion gates.

## X-7.15 — AAOS active-user deactivation

A separate disposable dashboard reader reaches LIVE before the host disables
its account through the public status API. The role remains assigned; the host
checks HTTP 401 with the same token. Timing guards reserve an unexpired JWT
window longer than the 65-second device assertion, and the client uses a longer
600-second local budget. Thus expiry or role removal cannot substitute for the
intended cause. Production policies and server refresh intervals are unchanged.

Six new coordinator cases cover successful ordering, early/duplicate signals,
missing completion, server-expiry ordering and failed deactivation. All 22
coordinator tests passed, as did Ruff/strict mypy. Android build/lint passed in
30 seconds with one worker and no emulator, retaining 57 passing JVM tests and
zero lint errors/15 warnings. Real-device verification passed: LIVE transitioned
to AUTH_REQUIRED within the unexpired window, with empty token input and no
displayed envelope. The host confirmed an inactive account, retained role and
HTTP 401 using the same JWT. The local screenshot was inspected; previous AAOS
scenarios also passed. Two integration tests passed in 20.52 seconds.
CPU samples were 40–71%, GPU 13–18%; device-stage samples retained 10.4 GiB RAM
free. See `dashboard-aaos-inactive-user.md`. No paid service was introduced.
Markdown remains current and DOCX unchanged.

Final restore passed (87 tables/310 rows, 81.578 seconds), and all 22 coordinator
tests passed again in 1.16 seconds with Ruff/mypy passing. Owned emulator and
temporary containers were confirmed removed; final sampled CPU was 39%.
Changes remain local and uncommitted; no PR/merge was performed. The next gate
is real network failure/reconnect/staleness, followed by remaining completion
and deployment acceptance.

## X-7.16 — AAOS stalled transport, staleness and recovery

Added a loopback-only, bounded TCP fault fixture and a separate opt-in Android
network scenario. After a real LIVE checkpoint, forwarding pauses; Android
marks the unchanged preview STALE. The host then cuts the connection, Android
retains stale evidence while RECONNECTING, and the restored route permits one
delayed reconnect to a fresh LIVE snapshot. Host/device elapsed-time guards
and an exact two-connection assertion supplement the visible state checks.
The application retry and authentication policies are unchanged; only a preview
test tag was added to runtime presentation. No paid service is used.

Thirty-one coordinator/fixture tests passed, with Ruff and strict mypy passing.
Android build/lint completed in 1m14s with one worker and no emulator, 57 passing
JVM tests, zero lint errors and 15 existing warnings. The successful actual
API 35 run passed both integration tests in 19.17 seconds and all four ordered
network checkpoints. Both local screenshots were inspected: empty token input,
explicit STALE / NOT LIVE, then CURRENT SERVER QUERY with a newer timestamp.

The first device attempt stopped before LIVE for an undetermined reason.
Allowlisted phase diagnostics were added; the repeat passed without changing
production behavior or weakening assertions. One successful run is recorded,
not repeated-run reliability. Sampled CPU was 20–63%, GPU 7–12%; free RAM during
device execution included 10.4 and 12.1 GiB. These are samples, not peak bounds.
See `dashboard-aaos-network-recovery.md` for reproduction and limitations.
Next are remaining retry-terminal cases and normal ten-snapshot completion,
before the broader deployment gate. English Markdown is updated; DOCX unchanged.

Final restore passed (87 tables/292 rows, 77.0 seconds). All 31 targeted tests
passed again in 3.71 seconds with Ruff/mypy and diff checks passing. Owned
emulator and integration containers were confirmed removed; final sampled
CPU was 31%, GPU 12%. Changes remain local and uncommitted; no PR/merge was
performed in this increment.

## X-7.17 — AAOS expiry during reconnect backoff

The next retry-terminal work is split into two bounded increments: expiry
during retry first, actual-device five-retry exhaustion next (at least 450
seconds of production backoff). This preserves the planned acceptance scope
without accelerating production timers or claiming JVM tests as device proof.

A new opt-in scenario reaches LIVE, cuts the local TCP route, observes
RECONNECTING and then local AUTH_REQUIRED. A 40-second input uses the existing
ten-second safety margin. The host verifies that the same JWT still receives
HTTP 200 for an active, authorized account, then restores the route. Android
remains terminal for 32 seconds and the host confirms only one accepted
connection. The inspected screenshot has an empty token field and no envelope.
No production runtime behavior or paid service was added.

Five coordinator tests require every ordered phase; a new JVM boundary test
proves expiry wins at the exact retry deadline and rejects late callbacks.
All 36 coordinator/proxy tests and 58 Android JVM tests passed. Android build
took 37 seconds; lint had zero errors and 15 existing warnings. Two integration
tests passed in 19.79 seconds. Ruff, strict mypy, PowerShell parsing and diff
checks passed. CPU samples were 53–67%, GPU 6–10%, with 12.9 GiB free RAM during
device execution; these are not measured peaks. See
`dashboard-aaos-retry-expiry.md`. English Markdown updated; DOCX unchanged.

Final restore passed with 87 tables/292 rows in 76.125 seconds. All 36 targeted
tests passed again in 3.86 seconds with Ruff/mypy and diff checks passing.
Owned containers/emulator were confirmed removed; final CPU sample was 34%,
GPU 8%. Changes remain local and uncommitted; no PR/merge was performed.

## X-7.18 — Actual AAOS retry exhaustion

Added an opt-in real-time exhaustion scenario, bounded accept timestamp history
and host checks for each 30/60/120/120/120-second delay. Actual API 35 reached
STOPPED after exactly five failed retries, cleared credentials/evidence and
made no new connection during 122 seconds after route restoration. The local
900-second budget isolates exhaustion; failed retries never reach the server,
so the normal five-minute JWT expiration cannot return an auth failure.

All 53 host tests, 59 Android tests, Ruff and mypy passed. Android build took
38 seconds with zero lint errors/15 existing warnings; two integration tests
passed in 19.51 seconds. Restore passed (87 tables/292 rows, 74.578 seconds).
The screenshot was inspected after resumption. Interactive monitoring had
been interrupted by account limits; the completed process returned success
and recorded automatic cleanup. Sampled CPU 36–79%, GPU 9–17%, not measured
peaks. English Markdown updated, DOCX unchanged; no commit/PR/merge performed.
Next is normal ten-snapshot completion; see dashboard-aaos-retry-exhaustion.md.

## X-7.19 — Normal completion (initial attempts and resolution)

Added an opt-in actual-AAOS ten-snapshot scenario with a single-connection
check, final sequence/preview retention, empty token input and 32-second
terminal observation. Four new host cases require all three checkpoints.
The scenario alone uses a ten-minute disposable JWT fixture; other runner
modes explicitly retain five minutes. Production configuration is unchanged.

Three device attempts were made. The first failed before LIVE confirmation
under the narrow five-minute setup budget. The second failed in the combined
completion phase. Timing review moved the origin from UI recognition of LIVE
to Connect and added a host TCP-acceptance duration check. The third reached
COMPLETE and passed timing/stale-status checks, but failed reading/validating
the final preview. Consequently retention, credential cleanup and no-restart
are not yet accepted. Further long runs were paused to diagnose the precise
assertion rather than repeat unchanged tests. A finer preview-sequence phase
was added afterward but has not yet been rebuilt/executed.

57 host tests, Ruff/mypy and diff checks passed before the final diagnostic
split. Android initial build/lint passed (37 seconds, 59 JVM tests, zero errors/
15 existing warnings); instrumentation timing rebuild passed in 19 seconds.
Backend integration passed in 24.33, 19.11 and 19.28 seconds. All failed runs
cleaned owned resources; no new restore success is claimed for X-7.19.
Sampled CPU 26–62%, GPU 10–19%, not measured peaks. English Markdown updated;
DOCX unchanged. No commit/PR/merge. Next work is preview diagnostics and the
remaining normal-completion assertions, not a new roadmap feature.

### Resumed validation — successful acceptance

Explicitly refreshed the preview accessibility node before reading its text,
split lookup/text/sequence diagnostic phases, and added safe local failure
screenshots after the form stage. The resumed actual API 35 run passed: ten
snapshots on one connection, COMPLETE with stale indication, empty credential
input and the identical sequence-10 preview retained for 32 seconds without
automatic restart. The final screenshot was inspected. The earlier failure
was consistent with stale accessibility data, but its exact cause cannot be
proved from the older combined diagnostics. No runtime behavior was changed.

Instrumentation build passed in 22 seconds; retained JVM evidence has 59 tests.
All 57 host tests passed again in 5.05 seconds, with Ruff/mypy passing on six
files. Two integration tests passed in 20.28 seconds. Sampled CPU 36–74%, GPU
5–16%, with 10.3 GiB free RAM in a device-stage sample; not measured peaks.
The targeted X-7.19 gate is now passed. Next is trusted-proxy deployment
acceptance, with broader accessibility/device-matrix gaps still explicit.

Final restore passed (87 tables/292 rows, 79.828 seconds). Owned containers
and emulator were confirmed absent; final sampled CPU was 40%, GPU 5%.
Both repository diff checks passed. English Markdown updated; DOCX unchanged.
Changes remain local and uncommitted, with no PR or merge performed.

## Remaining acceptance work after populated verification

X-6: live updates, exports, retention and performance hardening. Full OTA and formal standards
mapping views remain explicitly deferred until their source capabilities are implemented.
