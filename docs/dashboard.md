# Dashboard Foundation

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
invented. Different component populations can have different counts. Thirteen sequential
aggregate queries avoid cross-domain join multiplication and loading raw cells, scenes,
predictions or request payloads. This is a fixed-size numeric projection plus state groups,
not a history series or atomic snapshot. Future X-6 work will measure query cost and caching
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
