# Volume X Dashboard Requirements

## X-7.9 native transport prerequisite

| ID | Requirement | Evidence |
|---|---|---|
| DASH-NF-052 | Wire native lifecycle to header-authenticated read-only sockets, cancel obsolete connections and clear local sessions on expiry. | Companion adapter tests with fake transport |
| DASH-NF-053 | Validate bounded envelopes, view/version and query-time metadata before displaying data. | Companion JSON tests; full per-view and Android parser validation remain pending |

## X-7.8 native lifecycle prerequisite

| ID | Requirement | Evidence |
|---|---|---|
| DASH-NF-050 | Bound consecutive reconnect attempts, mark retained evidence stale, and ignore obsolete connection callbacks. | Companion virtual-time lifecycle tests; real transport pending |
| DASH-NF-051 | Clear evidence on authorization/protocol termination and complete a ten-snapshot session without automatic restart. | Companion populated cleanup and normal-completion tests |

## X-7.7 native request prerequisite

| ID | Requirement | Evidence |
|---|---|---|
| DASH-NF-048 | Construct only allowlisted native dashboard requests with Authorization and no Origin or URL credentials. | Companion request unit tests; device acceptance pending |
| DASH-NF-049 | Require HTTPS, except explicitly enabled local development; reject base paths, queries, fragments and invalid/bounded token values. | Companion positive/negative/boundary tests |

## X-7.6 responsive/accessibility checks

| ID | Requirement | Evidence |
|---|---|---|
| DASH-NF-045 | Expose a keyboard-visible skip link to main content and preserve the next input focus order. | Real Chrome keyboard and markup tests |
| DASH-NF-046 | Keep login/live page layouts within 320/768/1280-pixel widths and avoid page overflow with 200% root text at 320 pixels. | Optional presentation runner and inspected screenshots |
| DASH-NF-047 | Retain labeled controls, explicit atomic status messages and associated credential guidance. | Markup regression; screen-reader acceptance remains pending |

## X-7.5 shell lifecycle acceptance requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-NF-042 | Exercise real-shell reconnect and local expiration with real elapsed time, preserving production authentication limits. | Optional lifecycle runner; execution evidence in dashboard-shell-lifecycle.md |
| DASH-NF-043 | Observe role removal on an already authenticated shell and verify data cleanup and login focus at the next authorization check. | Disposable user role-removal scenario |
| DASH-NF-044 | Verify login tab order, Enter submission and focus transfer to logout and back to email. | Real Chrome keyboard scenarios; not complete accessibility conformance |

## X-7.4 login shell requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-F-023 | Provide a same-origin login/logout shell with view selection, aggregate snapshot and explicit freshness state. | Chrome form-login and snapshot scenario |
| DASH-NF-040 | Disable the shell by default, serve only packaged allowlisted assets and apply restrictive response headers. | Python asset tests and Docker-installed wheel |
| DASH-NF-041 | Clear password inputs and rendered data on appropriate lifecycle transitions; render server values as text; deny no-role users. | Browser invalid-login/logout/no-role checks and session tests |

## X-7.3 session controller requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-F-022 | Authenticate using the existing same-origin form contract and connect the read-only stream without persistent browser credentials. | Session Node tests; UI acceptance pending |
| DASH-NF-038 | Bound requests, suppress duplicate submissions and prevent cancelled or expired sessions from restarting transport. | Virtual-clock and race tests |
| DASH-NF-039 | Clear local snapshots before logout; distinguish confirmed revocation from offline uncertainty; never expose credentials in public state. | Logout and state tests |

## X-7.2 client lifecycle requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-F-021 | Expose server-snapshot liveness/staleness and restore live state on a valid reconnected stream without implying vehicle freshness. | Client clock tests and Chromium fixture |
| DASH-NF-036 | Bound reconnect delay to a 30-second minimum, 120-second cap and five consecutive retries, with non-negative jitter. | Virtual-clock Node tests |
| DASH-NF-037 | Clear token/snapshot and stop retrying on auth/permission rejection or explicit stop; ignore retired socket callbacks. | Client lifecycle tests and browser authentication-stop case |

## X-7.1 browser acceptance requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-NF-034 | Record real browser-engine evidence for authenticated snapshots, invalid/late authentication, read-only enforcement and native Origin denial. | `dashboard-browser-acceptance.md` and local sanitized report |
| DASH-NF-035 | Keep the optional acceptance fixture loopback-only, bounded, disposable and separate from production login; retain no credentials or snapshots in its report. | Fixture origin/schema tests, runner cleanup and report inspection |

## X-6.7 browser authentication requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-F-020 | Provide a separate browser snapshot route using the versioned first-message authentication contract, preserving native behavior. | Browser stream integration and shared runner |
| DASH-NF-031 | Default browser access to disabled; require exactly one allowlisted Origin and reject query/header credential alternatives. | Configuration/transport tests |
| DASH-NF-032 | Require a text authentication frame of at most 4096 bytes within five seconds, with no snapshot before JWT and live RBAC checks. | Parser, timeout, authentication and integration tests |
| DASH-NF-033 | Share worker slots and Redis quota with native streams; release slots on failure/cancellation and revalidate the token before/after snapshot queries. | Shared runner and lifecycle tests |

Protocol and deployment limitations are documented in `dashboard-browser-authentication.md`.

## X-6.6 native boundary and integration requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-NF-029 | The native stream shall reject any Origin header before admission, authentication and snapshot work. Header absence shall not bypass authentication. | Origin matrix unit tests and real HTTP 403 handshake integration |
| DASH-NF-030 | Verify the shared handshake counter, quota rejection, bounded TTL and post-expiration recovery against real Redis without altering other peer counters. | `test_dashboard_admission_redis.py` |

## X-6.5 admission requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-NF-027 | Enforce a shared Redis handshake budget of 30 attempts per peer per 60 seconds, failing closed on unavailable protection. | `test_dashboard_admission.py` |
| DASH-NF-028 | Reserve a bounded worker slot and admit the handshake before database authentication; release owned slots on exit. | `test_dashboard_realtime.py` |

Cross-platform release gates and unverified client boundaries are in `dashboard-acceptance.md`.

## Functional requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-F-001 | The platform shall expose an authenticated dashboard overview. | `GET /api/v1/dashboard/overview` |
| DASH-F-002 | The overview shall aggregate test-run and case-result status counts. | Dashboard service and tests |
| DASH-F-003 | The overview shall calculate case pass rate without dividing by zero. | `test_dashboard.py` |
| DASH-F-004 | The overview shall expose current requirement coverage and rate. | Dashboard service and tests |
| DASH-F-005 | The overview shall summarize mutation, automation, and dashboard AI evidence. | Dashboard service and tests |
| DASH-F-006 | Recent AI cards shall preserve citations and exclude source context. | Response schema and service |
| DASH-F-007 | The platform shall expose complete UTC daily test-quality buckets for a bounded historical window. | Trends service and tests |
| DASH-F-008 | Each trend bucket shall expose run outcomes, case outcomes, and truthful pass-rate semantics. | Trend calculation tests |
| DASH-F-009 | The platform shall expose failed case results with run, definition, suite, duration, observation, and evidence references. | Failure drill-down API |
| DASH-F-010 | Failure results shall support bounded pagination, time window, and suite filtering. | OpenAPI and integration tests |

## X-3 operational requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-F-011 | Expose current vehicle, ECU, session and stored-DTC distributions. | Operations service and aggregate tests |
| DASH-F-012 | Distinguish CAN inventory from time-windowed CAN and diagnostic activity. | Independent SQL aggregates and integration |
| DASH-NF-010 | Operations require dashboard:read and reject windows outside 1–720 hours. | Integration 403/422 and OpenAPI tests |
| DASH-NF-011 | Exclude memory, keys, command payloads and diagnostic snapshots. | Explicit column selection and response schema |

## Non-functional requirements

### X-4 mobility requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-F-013 | Expose SOC/SOH and component temperature distributions with units and sample counts. | Mobility projection and unit tests |
| DASH-F-014 | Expose battery, motor, charging and thermal source-state distributions. | Mobility aggregate queries |
| DASH-F-015 | Expose windowed EV/ADAS scenario outcomes and ADAS planning maneuvers. | SQL boundary tests |
| DASH-NF-012 | Empty numeric populations shall return null statistics, not invented zeros. | Empty-state tests |
| DASH-NF-013 | Mobility access requires dashboard:read and windows of 1–720 hours. | OpenAPI and integration 403/422 checks |

| ID | Requirement | Evidence |
|---|---|---|
| DASH-NF-001 | Dashboard access shall require `dashboard:read`. | Permission catalogue and router |
| DASH-NF-002 | Query windows shall be limited to 720 hours. | OpenAPI contract test |
| DASH-NF-003 | Evidence cards shall be limited to 50 per request. | OpenAPI contract test |
| DASH-NF-004 | The read model shall not mutate source records or emit events. | Read-only service design |
| DASH-NF-005 | KPI ordering and rounding shall be deterministic. | Unit tests |
| DASH-NF-006 | The increment shall require no paid service or GPU. | Local architecture |
| DASH-NF-007 | Trend responses shall contain no more than 90 daily buckets. | Query contract |
| DASH-NF-008 | Failure observations shall expose no more than 500 characters. | Mapping tests |
| DASH-NF-009 | Empty daily buckets and undefined rates shall remain explicit. | Trend tests |

## Traceability status

### X-6.4 populated verification

| ID | Requirement | Evidence |
|---|---|---|
| DASH-NF-025 | Validate distinct populated component statistics and state groups against known values and SQL reference queries. | Populated integration profile |
| DASH-NF-026 | Isolate synthetic setup in connection-local temporary tables and verify public component row counts remain unchanged. | Fixture safety unit test and integration before/after checks |

### X-6.3 measured query and retention checks

| ID | Requirement | Evidence |
|---|---|---|
| DASH-NF-022 | Mobility shall use at most ten SELECTs with unchanged numeric metrics. | PostgreSQL reference comparison and query-count unit test |
| DASH-NF-023 | Verify aggregate/export paths in a read-only transaction with bounded statement duration. | PostgreSQL integration profile |
| DASH-NF-024 | Retain non-sensitive query-profile evidence with explicit limits and no production data retention changes. | Integration JSON report and 14-day CI artifact policy |

### X-6.2 live snapshot requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-F-019 | Stream versioned periodic snapshots for three allowlisted views with server-query freshness metadata. | WebSocket integration and frame tests |
| DASH-NF-019 | Revalidate token, active user and dashboard permission before generating and sending each snapshot. | Auth and revocation tests |
| DASH-NF-020 | Bound admitted connections per process, snapshot count, refresh interval and send duration. | Capacity, periodic and slow-consumer tests |
| DASH-NF-021 | Release connection capacity on disconnect or failure; accept no client refresh commands or URL tokens. | Cleanup and read-only tests |

### X-6.1 export requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-F-018 | Export three allowlisted aggregate dashboard views as versioned JSON attachments. | Router, schema, integration |
| DASH-NF-016 | Exports require dashboard:read and 1–720-hour windows. | OpenAPI and HTTP 403/422 integration |
| DASH-NF-017 | Do not persist export artifacts; instruct HTTP caches not to store responses. | Service design and response-header tests |
| DASH-NF-018 | Apply cooperative generation timeout and serialized-byte limit with stable errors. | Cancellation and exact-size boundary tests |

### X-5 approved supporting-evidence scope

| ID | Requirement | Evidence |
|---|---|---|
| DASH-F-016 | Summarize current diagnostic flash and requirement coverage states plus windowed administrative audit outcomes. | Evidence aggregation service |
| DASH-F-017 | Expose four explicit gap cards with source identifiers, missing capabilities and limitations. | Empty/populated unit tests |
| DASH-NF-014 | Keep assessment not_assessed regardless of evidence volume; do not compute conformity/readiness percentages. | Literal schema and unit tests |
| DASH-NF-015 | Enforce dashboard:read, 1–720-hour windows and aggregate-only data selection. | OpenAPI, SQL and integration tests |

These requirements implement the approved reduced X-5 scope. Formal standards mappings and
OTA lifecycle capabilities are deferred, not certified or inferred from generic evidence.

Requirements DASH-F-001 through DASH-F-015 and DASH-NF-001 through DASH-NF-013 are implemented
through X-4. Visual clients and historical materialization are outside this increment.
