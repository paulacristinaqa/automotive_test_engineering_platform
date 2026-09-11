# Dashboard Foundation

## X-6.4 populated isolated verification

The integration profile now runs a second case with connection-local temporary component tables.
Three batteries, two motor/inverter records and one thermal record provide distinct populations,
negative temperatures and known averages. The test verifies counts `[3,3,3,2,2,1]`, means
`[50,90,20,50,60,22]`, battery temperature bounds and state distributions, in addition to
independent SQL equivalence and the ten-SELECT budget.

Fixture setup copies only table structure (no public rows or constraints) and inserts exclusively
into `pg_temp`. It commits setup before starting the repeatable-read/read-only measurement.
The connection closes and its engine is disposed afterward; no temporary fixture is shared with
the API connection pool. Public component row counts are checked before and after. The existing
empty-population case remains, and the report nests the populated result under `populated_fixture`.

This is a small SQL projection fixture, not a complete vehicle/domain simulation or a fleet-load
benchmark. Temporary tables intentionally omit production constraints because no domain write path
is under test. Source retention and production deployment configuration are unchanged.

## X-6.3 query-count regression and retention verification

Mobility numeric aggregates now group by source table: three battery statistics share one
query, two motor/inverter statistics share another, and cabin temperature uses the third.
The full view issues ten SELECTs instead of thirteen, without changing metric ordering,
units, population counts or null semantics. This is a query/round-trip reduction, not an
assertion of a particular latency speedup.

`tools/profile_dashboard_queries.py` is exercised by integration against the disposable
PostgreSQL fixture. A repeatable-read, read-only transaction and five-second local statement
timeout bound this small verification. Six independent reference numeric queries are compared
with the optimized view; exact metric equality and ten SELECTs are required. All three exports
are then exercised in the same read-only transaction. Any database mutation would fail.

The non-sensitive `dashboard-query-profile.json` records query counts, population sizes,
export byte sizes and elapsed samples. Numeric-only reference and full-view times measure
different workloads and must not be interpreted as a speedup ratio. CI retains this evidence
with the existing restore report for 14 days. Local reports are ignored by Git and remain until
manually removed. These test reports are not retained dashboard snapshots or production exports.

Production source retention remains unchanged. Exports and live snapshots create no server
artifact; HTTP exports retain their no-store policy. This verification is not a production-scale
load benchmark or a distributed admission-control assessment.

## X-6.2 periodic live snapshots and freshness

`/api/v1/dashboard/stream/{view}` is a WebSocket endpoint for the same three allowlisted export
views. It uses a fixed 24-hour activity window and `Authorization: Bearer ...` headers, never
query-string tokens. Clients must support custom handshake headers (for example the Android
client). A browser ticket/cookie flow is not implemented in this slice.

Each `atep.dashboard.snapshot.v1` frame contains a sequence, server `observed_at`,
`refresh_not_before`, a 30-second minimum refresh interval, and the versioned snapshot.
`freshness_basis=server_query_not_vehicle_measurement` prevents a recent query from implying
recent vehicle telemetry. Source timestamps and all limitations remain inside the snapshot.
Queries start only after the previous send and wait period: this is periodic sampling, not
event-driven delivery, and intermediate changes can be missed. There is no replay guarantee.

Token expiry, active-user state and dashboard:read are checked on admission, before generation
and again before transmission. Revocation during the idle interval closes the connection at
the next check; no claim of immediate idle-connection teardown is made. Concurrent revocation
after the final check remains a normal check/send race, not a transactionally atomic boundary.

Limits: 16 admitted connections per worker process, 10 snapshots per connection, five seconds
per send, and a cooperative 15-second authentication/generation cycle. Existing export generation
and byte limits apply to the embedded snapshot, not the small outer WebSocket envelope. No database
session is held during idle waits. Disconnects, cancellation, errors and normal completion release
the connection slot. Client application messages close the read-only stream with 1008; capacity
or operational errors close with 1013. Authentication/permission close codes are 4401/4403 after
acceptance; denial before acceptance is an HTTP handshake rejection (403 under this server).

No dashboard data is persisted. Limits are process-local, not a distributed connection or handshake
rate limiter; production ingress admission, browser authentication and measured multi-worker capacity
remain part of later hardening. The existing test-run stream is unchanged.

## X-6.1 bounded transient exports

`GET /api/v1/dashboard/exports/{view}?window_hours=24` supports only `operations`, `mobility`
and `evidence-readiness`, under `dashboard:read` and the existing API rate limiter. The JSON
attachment wraps the original source contract in `dashboard-export-v1`; all interpretation
limitations are preserved. Names are selected from a fixed allowlist, not arbitrary file paths.

The server creates no persisted export record or file. Responses set `Cache-Control: no-store`
and `X-Content-Type-Options: nosniff`. Downloaded client copies remain the recipient's retention
responsibility. Existing source-domain retention policies are unchanged.

Generation uses a cooperative 10-second asyncio timeout and rejects serialized output larger
than 256 KiB. Errors use the global contract: `dashboard_export_timeout` (504) and
`dashboard_export_too_large` (422). Cancellation depends on the database driver; this is not a
hard database statement deadline. Serialization is synchronous and the byte check occurs after
serialization, so neither control is a strict peak-memory bound. Only aggregate views are included;
raw logs, AI text cards and bulk records are intentionally outside this first export slice.

Live updates, freshness, measured query optimization and broader retention verification remain
pending in X-6. This slice does not claim to complete the entire increment.

## X-5 supporting evidence and gaps

`GET /api/v1/dashboard/evidence-readiness?window_hours=24` requires `dashboard:read`.
It returns current diagnostic flash and requirement coverage distributions, together with
administrative audit outcomes from an inclusive 1–720-hour UTC window. Only grouped counts
are selected: no firmware image, audit details, actor identity or security material is exposed.

Four explicit gap cards describe the implemented source inventory, not an assessment:

- OTA: not implemented; diagnostic flashing is supporting technology, not OTA delivery.
- Cybersecurity: not assessed; administrative audit is not an attack/vulnerability counter.
- ASPICE: not assessed; generic requirement coverage is not process capability evidence.
- ISO 26262: not assessed; generic test coverage is not conformity or certification.

Source references are identifiers, not verified evidence links or standards clause mappings.
The inventory is versioned in code and must be reviewed when the underlying capabilities
change. Empty and populated databases retain the same gaps and `assessment=not_assessed`.
No readiness percentage is computed. Sequential queries do not promise snapshot consistency.
This deliberately reduced X-5 scope was approved before implementation; formal mappings and
OTA lifecycle views remain deferred until their source capabilities exist.

Volume X starts with a backend read model rather than a browser framework. The endpoint
`GET /api/v1/dashboard/overview` consolidates existing ATEP evidence into a stable,
consumer-oriented contract while leaving source domains authoritative.

X-2 adds two read-only test quality contracts:

- `GET /api/v1/dashboard/test-quality/trends` returns 1 to 90 complete UTC daily buckets;
- `GET /api/v1/dashboard/test-quality/failures` returns a paginated failed-case drill-down.

## Architecture

X-3 adds `GET /api/v1/dashboard/operations?window_hours=24`, protected by
`dashboard:read`. The `dashboard-operations-v1` contract returns current vehicle status,
ECU operational states, diagnostic session types, stored DTC severity distributions, and
CAN/CAN FD inventory totals. CAN transmission, fault execution, and diagnostic command
counts use an inclusive server-time window of 1 to 720 hours, ending at `generated_at`.
Independent scalar subqueries avoid join multiplication. No raw CAN payload, ECU memory,
diagnostic request, security key, or DTC snapshot is selected or returned.

These are recorded states, not live health checks. Stored DTCs are not necessarily active
faults, and fault-execution counts include recovery operations. Sequential reads do not
promise a transactionally consistent cross-domain snapshot. Detailed vehicle control
remains in the source-domain APIs.

The dashboard service issues bounded aggregate queries against test runs, case results,
requirements, mutation executions, cross-platform automation reports, and dashboard-targeted AI
evidence. It does not copy data into a dashboard table, emit events, or mutate operational state.

The `dashboard-overview-v1` response contains:

- a UTC generation timestamp and selected time window;
- execution, pass-rate, coverage, mutation, automation, and AI evidence KPIs;
- sorted status and severity distributions for heatmap and chart clients;
- a bounded list of recent cited AI evidence cards;
- explicit interpretation limitations.

## X-4 mobility analytics

`GET /api/v1/dashboard/mobility?window_hours=24` returns the
`dashboard-mobility-analytics-v1` chart contract under `dashboard:read`.

| Data | Scope | Interpretation |
|---|---|---|
| SOC and SOH | Current battery records | Unweighted percent minimum, mean, maximum and count |
| Battery, motor, inverter and cabin temperatures | Current component records | Celsius minimum, mean, maximum and count |
| Battery, motor, charging and thermal states | Current component records | Sorted source-state distributions |
| EV and ADAS scenario outcomes | Inclusive 1–720-hour UTC window | Stored execution status counts |
| ADAS maneuvers | Same activity window | Planning evaluations, not actual maneuvers |

Empty numeric populations have zero samples and `null` statistics. No capacity weighting,
cross-vehicle thermal threshold, pass-rate inference, live health claim or certification is
invented. Different component populations can have different counts. Ten sequential
aggregate queries avoid cross-domain join multiplication and loading raw cells, scenes,
predictions or request payloads. This is a fixed-size numeric projection plus state groups,
not a history series or atomic snapshot. X-6.3 groups numeric queries by table; further work measures caching
needs; a bounded time window alone does not bound database scan cost.

## Safety and cost controls (all contracts)

- `dashboard:read` is required independently from source-domain permissions.
- `window_hours` accepts 1 through 720 hours and defaults to 24.
- `evidence_limit` accepts 1 through 50 records and defaults to 10.
- Trend windows accept 1 through 90 days and always include zero-activity days.
- Failure windows accept 1 through 2160 hours, with pages limited to 100 records.
- Failure observations are limited to 500 characters and report whether truncation occurred.
- Source prompts, raw logs, and unrestricted analysis context are excluded.
- Empty denominators return `null`; the API never presents missing evidence as zero percent.
- The implementation uses existing PostgreSQL and FastAPI services and requires no paid API,
  cloud service, model download, or GPU.

## Current limitations

Requirement coverage represents the current snapshot because those records describe present
traceability state. Other operational counts use the requested creation-time window. This first
increment provides the backend contract. X-2 supplies daily history and failed-case evidence;
interactive presentation, comparison baselines, live streaming, and export remain planned.
