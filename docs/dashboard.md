# Dashboard Foundation

Volume X starts with a backend read model rather than a browser framework. The endpoint
`GET /api/v1/dashboard/overview` consolidates existing ATEP evidence into a stable,
consumer-oriented contract while leaving source domains authoritative.

X-2 adds two read-only test quality contracts:

- `GET /api/v1/dashboard/test-quality/trends` returns 1 to 90 complete UTC daily buckets;
- `GET /api/v1/dashboard/test-quality/failures` returns a paginated failed-case drill-down.

## Architecture

The dashboard service issues bounded aggregate queries against test runs, case results,
requirements, mutation executions, cross-platform automation reports, and dashboard-targeted AI
evidence. It does not copy data into a dashboard table, emit events, or mutate operational state.

The `dashboard-overview-v1` response contains:

- a UTC generation timestamp and selected time window;
- execution, pass-rate, coverage, mutation, automation, and AI evidence KPIs;
- sorted status and severity distributions for heatmap and chart clients;
- a bounded list of recent cited AI evidence cards;
- explicit interpretation limitations.

## Safety and cost controls

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
